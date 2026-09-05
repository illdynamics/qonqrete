"""
Shared helper: call an adapter, parse the JSON it was told to write to a
file, and retry with a sharper instruction if the JSON is missing or
malformed.

Updated: New runs write receipts to canonical run_root paths.
Legacy fallback reads for old runs are preserved.

Receipt path invariant (new runs):
  <run_root>/agents/cycle-XXX/<role>/<receipt_filename>.json

The agent prompt MUST instruct the agent to write its JSON to the absolute
receipt path. The old "write to relative filename in workdir" pattern is
removed for new runs.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
import dataclasses
from typing import Any, Dict, Optional, Tuple

from ..adapters.base import AgentAdapter, AgentCallResult, AgentCallSpec
from ..streaming import create_streamer
from ..path_guards import move_qonqrete_metadata_out_of_target


# ---------------------------------------------------------------------------
# Legacy: move-and-sweep support (kept for old-run compatibility only)
# ---------------------------------------------------------------------------

def _move_output_to_runroot(run_root: str, workdir: str, output_file: str,
                            cycle: int = 0, event_log=None) -> str:
    """[LEGACY] Move an agent output JSON from workdir to the run_root
    artifacts/agent-outputs/ location. Returns the moved-to path.

    New runs: receipts go directly under run_root/agents/cycle-XXX/<role>/
    This function is kept only for backward compatibility with old runs
    where agents wrote receipts into the target workspace.
    """
    if not run_root or not workdir or not output_file:
        return os.path.join(workdir, output_file)

    src = os.path.join(workdir, output_file)
    if not os.path.isfile(src):
        return src

    # If already under run_root, don't move
    try:
        real_src = os.path.realpath(src)
        real_run = os.path.realpath(run_root)
        if real_src.startswith(real_run):
            return src
    except (ValueError, OSError):
        pass

    # Move to artifacts/agent-outputs/ under run_root (legacy area)
    dest_dir = os.path.join(run_root, "artifacts", "agent-outputs")
    os.makedirs(dest_dir, exist_ok=True)

    base, ext = os.path.splitext(output_file)
    dest = os.path.join(dest_dir, output_file)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        counter += 1

    try:
        import shutil
        shutil.move(src, dest)
        if event_log:
            event_log.emit("metadata.moved_from_target",
                           from_path=src, to_path=dest,
                           reason="qonqrete_metadata_written_to_target",
                           cycle=cycle)
        return dest
    except OSError:
        return src


def _find_and_move_output_from_target(
    workdir: str, output_file: str, run_root: str,
    cycle: int = 0, event_log=None,
) -> str:
    """[LEGACY] Find output_file anywhere under workdir/target_path and
    move to run_root.  Returns the final path (under run_root).
    Falls back to workdir path if run_root is not provided.

    New runs: receipts go directly under run_root; this is legacy only.
    """
    from pathlib import Path
    src = ""
    try:
        for candidate in Path(workdir).rglob(output_file):
            src = str(candidate)
            break
    except (OSError, PermissionError):
        pass

    if not src:
        return os.path.join(workdir, output_file)

    if not run_root:
        return src

    # Check if already under run_root
    try:
        real_src = os.path.realpath(src)
        real_run = os.path.realpath(run_root)
        if real_src.startswith(real_run):
            return src
    except (ValueError, OSError):
        pass

    dest_dir = os.path.join(run_root, "artifacts", "agent-outputs")
    os.makedirs(dest_dir, exist_ok=True)
    base, ext = os.path.splitext(output_file)
    dest = os.path.join(dest_dir, output_file)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        counter += 1

    try:
        import shutil
        shutil.move(src, dest)
        if event_log:
            event_log.emit("metadata.moved_from_target",
                           from_path=src, to_path=dest,
                           reason="qonqrete_metadata_written_to_target",
                           cycle=cycle)
        return dest
    except OSError:
        return src


# ---------------------------------------------------------------------------
# Progressive timeouts
# ---------------------------------------------------------------------------

_ROLE_TIMEOUTS = {
    "qlarifier": 600,
    "instruqtor": 600,
    "construqtor": 600,
    "inspeqtor": 600,
}


class AgentOutputError(RuntimeError):
    pass


# Signatures that indicate the agent *process* itself hit a transient
# network/bridge failure (as opposed to the model simply not writing JSON).
# These come from the codeseeq CLI / OpenAI SDK / httpx and are printed to
# stderr AFTER the startup banner.
_CONNECTION_ERROR_SIGNATURES = (
    "stream disconnected",
    "connection error",
    "connect error",
    "error sending request",
    "remote protocol error",
    "read error",
    "write error",
    "peer closed connection",
    "connection reset",
    "connection refused",
    "broken pipe",
    "timed out",
    "read timed out",
    "http 502",
    "http 503",
    "http 504",
)


def _is_connection_error(text: str) -> bool:
    """Return True when adapter output looks like a transient connection error."""
    if not text:
        return False
    lowered = text.lower()
    return any(sig in lowered for sig in _CONNECTION_ERROR_SIGNATURES)


def _stderr_tail(stderr: str, limit: int = 1000) -> str:
    """Return the most diagnostic portion of stderr.

    Agent CLIs (codeseeq in particular) print a startup banner to stderr
    first; the actual error (stream disconnect, connection failure, ...) is
    emitted later. Truncating from the start therefore hides the root cause,
    so we keep the *tail* instead.
    """
    if not stderr:
        return ""
    stderr = stderr.strip()
    if len(stderr) <= limit:
        return stderr
    return "…" + stderr[-limit:]


def _generate_call_id() -> str:
    return f"call-{uuid.uuid4().hex[:8]}"


def _resolve_output_path(spec: AgentCallSpec) -> str:
    """Resolve the actual output file path.

    If spec.output_file is absolute, use it as-is.
    If it's relative, resolve against spec.workdir (legacy behavior).
    """
    if os.path.isabs(spec.output_file):
        return spec.output_file
    return os.path.join(spec.workdir, spec.output_file)


def _ensure_artifact_dir(spec: AgentCallSpec, run_root: str,
                         cycle: int) -> str:
    """Create and return the artifact directory for this call."""
    if spec.artifact_dir:
        arts_dir = spec.artifact_dir
    elif run_root and spec.role:
        from .receipts import agent_artifact_dir
        cycle_str = f"cycle-{cycle:03d}" if cycle is not None else "cycle-000"
        call_id = spec.call_id or _generate_call_id()
        arts_dir = str(agent_artifact_dir(run_root, cycle, spec.role, call_id))
    else:
        arts_dir = ""
    if arts_dir:
        os.makedirs(arts_dir, exist_ok=True)
    return arts_dir


def _write_artifact_files(arts_dir: str, spec: AgentCallSpec,
                          result: AgentCallResult, streaming: bool = False,
                          stdout_bytes: int = 0, stderr_bytes: int = 0) -> None:
    """Write call artifacts: prompt.md, stdout.txt, stderr.txt,
    result.json, metadata.json."""
    if not arts_dir:
        return
    # prompt.md
    with open(os.path.join(arts_dir, "prompt.md"), "w",
              encoding="utf-8") as fh:
        fh.write(spec.prompt)
    # stdout.txt — if NOT already written by streaming, write from result
    stdout_file = os.path.join(arts_dir, "stdout.txt")
    if not os.path.exists(stdout_file):
        with open(stdout_file, "w", encoding="utf-8") as fh:
            fh.write(result.stdout or "")
    # stderr.txt
    stderr_file = os.path.join(arts_dir, "stderr.txt")
    if not os.path.exists(stderr_file):
        with open(stderr_file, "w", encoding="utf-8") as fh:
            fh.write(result.stderr or "")
    # result.json
    if result.raw_output_text:
        with open(os.path.join(arts_dir, "result.json"), "w",
                  encoding="utf-8") as fh:
            fh.write(result.raw_output_text)
    # metadata.json
    metadata = {
        "role": spec.role,
        "model": spec.model,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "output_path_exists": result.output_path_exists,
        "output_file": spec.output_file,
        "thinking": spec.thinking,
        "sandbox": spec.sandbox,
        "approval": spec.approval,
        "call_id": spec.call_id,
        "stream_agent_output": streaming,
        "stream_mode": getattr(spec, 'stream_mode', 'prefixed'),
        "stream_indicator": getattr(spec, 'stream_indicator', 'stream'),
        "stdout_bytes": stdout_bytes or len(result.stdout.encode("utf-8")),
        "stderr_bytes": stderr_bytes or len(result.stderr.encode("utf-8")),
        "return_code": result.exit_code,
        "duration": result.duration_seconds,
        "timeout_seconds": spec.timeout_seconds,
    }
    with open(os.path.join(arts_dir, "metadata.json"), "w",
              encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)


def cleanup_agent_artifacts(spec: AgentCallSpec) -> None:
    """Remove the prompt/output scratch files a call left in spec.workdir."""
    _pfx = spec.call_id if spec.call_id else spec.role
    # Only clean up relative output files in workdir
    if not os.path.isabs(spec.output_file):
        out_path = os.path.join(spec.workdir, spec.output_file)
        if os.path.exists(out_path):
            os.remove(out_path)
    for fname in (f".qq_prompt_{_pfx}.md",):
        path = os.path.join(spec.workdir, fname)
        if os.path.exists(path):
            os.remove(path)
    arts = os.path.join(spec.workdir, ".qq_artifacts")
    if os.path.isdir(arts):
        import shutil
        shutil.rmtree(arts, ignore_errors=True)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise AgentOutputError(
        f"Could not parse JSON from agent output: {text[:300]!r}")


def _find_output_file(workdir: str, output_file: str) -> str:
    """Search for output_file recursively within workdir.
    Returns its full path, or '' if not found.
    Used as a legacy fallback when the agent writes the file to a
    subdirectory instead of the expected path."""
    if not workdir or not output_file:
        return ""
    from pathlib import Path
    try:
        for candidate in Path(workdir).rglob(output_file):
            return str(candidate)
    except (OSError, PermissionError):
        pass
    return ""


def _try_read_receipt(output_path: str, spec: AgentCallSpec,
                      event_log=None) -> Optional[str]:
    """Try to read an agent receipt from the given path. Returns contents or None."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as fh:
                return fh.read()
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _find_legacy_receipt_in_target(spec: AgentCallSpec,
                                   event_log=None) -> Optional[str]:
    """Legacy fallback: search for receipt in target_path/workdir."""
    if not spec.workdir:
        return None
    from pathlib import Path
    fname = os.path.basename(spec.output_file)
    try:
        for candidate in Path(spec.workdir).rglob(fname):
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    raw = fh.read()
                if event_log:
                    event_log.emit("metadata.legacy_receipt_read",
                                   from_path=str(candidate),
                                   role=spec.role,
                                   note="legacy_receipt_found_in_target_path")
                return raw
            except OSError:
                pass
    except (OSError, PermissionError):
        pass
    return None


def _find_legacy_receipt_in_artifacts(spec: AgentCallSpec, run_root: str,
                                      event_log=None) -> Optional[str]:
    """Legacy fallback: search for receipt in run_root/artifacts/agent-outputs/."""
    if not run_root:
        return None
    fname = os.path.basename(spec.output_file)
    legacy_dir = os.path.join(run_root, "artifacts", "agent-outputs")
    if not os.path.isdir(legacy_dir):
        return None
    candidate = os.path.join(legacy_dir, fname)
    if os.path.isfile(candidate):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                raw = fh.read()
            if event_log:
                event_log.emit("metadata.legacy_receipt_read",
                               from_path=candidate,
                               role=spec.role,
                               note="legacy_receipt_found_in_artifacts_agent_outputs")
            return raw
        except OSError:
            pass
    return None


def call_for_json(adapter: AgentAdapter, spec: AgentCallSpec,
                  event_log=None, max_repairs: int = 2,
                  run_root: str = "", cycle: int = 0,
                  stream_config: Optional[dict] = None
                  ) -> Tuple[Dict[str, Any], AgentCallResult]:
    """Call an adapter and parse its JSON output, with retry on failure.

    When spec.output_file is absolute, the agent is instructed to write
    directly under run_root. The adapter reads from that absolute path.

    When spec.output_file is relative (legacy), it is resolved against
    spec.workdir.

    Legacy fallback reads for old runs are preserved:
      - Search target_path/workdir for the receipt file
      - Search run_root/artifacts/agent-outputs/
      - Emit metadata.legacy_receipt_read events

    When stream_config is provided (with keys: stream_agent_output, stream_mode,
    stream_stderr, show_prompts), live streaming is enabled for the adapter call.
    """
    base_prompt = spec.prompt
    base_timeout = spec.timeout_seconds
    current_spec = spec
    last_error: Exception = AgentOutputError("unknown failure")
    result = None
    call_id = spec.call_id or _generate_call_id()

    # Apply role-specific timeout if not already explicitly set
    if spec.role in _ROLE_TIMEOUTS:
        role_timeout = _ROLE_TIMEOUTS[spec.role]
        if role_timeout != base_timeout:
            current_spec = dataclasses.replace(current_spec,
                                              timeout_seconds=role_timeout)
            base_timeout = role_timeout

    # Build streamer if enabled
    streaming = bool(stream_config and stream_config.get("stream_agent_output"))
    streamer = None
    if streaming:
        streamer = create_streamer(
            enabled=True,
            mode=stream_config.get("stream_mode", "prefixed"),
            indicator=stream_config.get("stream_indicator", "stream"),
            stream_stderr=stream_config.get("stream_stderr", True),
            sticky_status=stream_config.get("sticky_status"),
            spinner_manager=stream_config.get("spinner_manager"),
            activity_tracker=stream_config.get("activity_tracker"),
            refresh_sticky_cb=stream_config.get("refresh_sticky_cb"),
            stream_line_prefix=stream_config.get("stream_line_prefix", "auto"),
            no_color=stream_config.get("no_color", False),
        )

    for attempt in range(max_repairs + 1):
        attempt_call_id = f"{call_id}-a{attempt}" if attempt > 0 else call_id
        arts_dir = ""
        if run_root:
            from .receipts import agent_artifact_dir
            arts_dir = str(agent_artifact_dir(run_root, cycle, spec.role, attempt_call_id))

        # Ensure parent dirs exist for absolute output paths
        output_path = _resolve_output_path(current_spec)
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Attach artifact_dir, call_id, and streaming fields to the spec
        replace_kwargs = {
            "artifact_dir": arts_dir,
            "call_id": attempt_call_id,
        }
        if stream_config:
            if stream_config.get("temperature") is not None:
                replace_kwargs["temperature"] = stream_config["temperature"]
            if stream_config.get("top_p") is not None:
                replace_kwargs["top_p"] = stream_config["top_p"]
        if streaming:
            replace_kwargs["stream_output"] = True
            replace_kwargs["stream_mode"] = stream_config.get("stream_mode", "prefixed")
            replace_kwargs["stream_indicator"] = stream_config.get("stream_indicator", "stream")
            replace_kwargs["stream_stderr"] = stream_config.get("stream_stderr", True)
            replace_kwargs["output_sink"] = streamer.emit if streamer else None

        current_spec = dataclasses.replace(current_spec, **replace_kwargs)

        # Show prompt info if requested
        if streaming and stream_config.get("show_prompts") and arts_dir:
            prompt_path = os.path.join(arts_dir, "prompt.md")
            sys_stderr_write = __import__('sys').stderr.write
            sys_stderr_write(f"[{spec.role} prompt] {prompt_path}\n")
            __import__('sys').stderr.flush()

        if event_log:
            event_log.emit(
                "agent.call.started", role=spec.role, model=spec.model,
                attempt=attempt, call_id=attempt_call_id,
                timeout_seconds=current_spec.timeout_seconds,
                output_path=output_path,
            )
            if streaming:
                event_log.emit(
                    "agent.output.started", role=spec.role,
                    call_id=attempt_call_id,
                )

        result = adapter.call(current_spec)

        # Classify the failure mode so retries can be appropriate:
        #   * process_failed  -> the agent CLI crashed/timed out (non-zero exit)
        #   * connection_error -> the failure looks like a transient network issue
        process_failed = result.exit_code != 0
        connection_error = _is_connection_error(
            (result.stderr or "") + "\n" + (result.stdout or "")
        )

        # Write artifact files for every call
        if arts_dir:
            try:
                os.makedirs(arts_dir, exist_ok=True)
                _write_artifact_files(arts_dir, current_spec, result,
                                      streaming=streaming)
            except OSError as os_err:
                import sys as _sys
                _sys.stderr.write(
                    f"[qq] WARNING: failed to write artifacts to {arts_dir}: "
                    f"{os_err}\n")
                _sys.stderr.flush()

        # Compute stdout/stderr bytes
        stdout_bytes = len(result.stdout.encode("utf-8")) if result.stdout else 0
        stderr_bytes = len(result.stderr.encode("utf-8")) if result.stderr else 0

        if event_log:
            event_log.emit(
                "agent.call.finished", role=spec.role, model=spec.model,
                attempt=attempt, exit_code=result.exit_code,
                duration=result.duration_seconds,
                output_found=result.output_path_exists,
                call_id=attempt_call_id,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                streamed=streaming,
            )

        # ---- Primary read: absolute output path (new runs) ----
        if result.output_path_exists and result.raw_output_text:
            try:
                data, _result = _extract_json(result.raw_output_text), result
                # For new runs with absolute paths, the receipt is already
                # in the correct location — no move needed.

                # Still run sweeper for legacy safety (it's a no-op in new runs)
                if run_root and not os.path.isabs(spec.output_file):
                    _find_and_move_output_from_target(
                        current_spec.workdir, current_spec.output_file,
                        run_root, cycle=cycle, event_log=event_log)
                return data, _result
            except AgentOutputError as exc:
                last_error = exc
        else:
            # ---- Legacy fallback: agent wrote to subdir of workdir ----
            fname = os.path.basename(spec.output_file)
            found_path = _find_output_file(current_spec.workdir, fname)
            if found_path:
                try:
                    with open(found_path, "r", encoding="utf-8") as fh:
                        raw = fh.read()
                    data, _result = _extract_json(raw), result
                    if event_log:
                        event_log.emit("metadata.legacy_receipt_read",
                                       from_path=found_path,
                                       role=spec.role,
                                       note="legacy_receipt_found_in_subdirectory")
                    if run_root:
                        _find_and_move_output_from_target(
                            current_spec.workdir, fname,
                            run_root, cycle=cycle, event_log=event_log)
                    return data, _result
                except (AgentOutputError, OSError) as exc:
                    last_error = exc

            # ---- Legacy fallback: search target path for the file ----
            legacy_raw = _find_legacy_receipt_in_target(current_spec, event_log)
            if legacy_raw:
                try:
                    data, _result = _extract_json(legacy_raw), result
                    return data, _result
                except AgentOutputError as exc:
                    last_error = exc

            # ---- Legacy fallback: search artifacts/agent-outputs ----
            if run_root:
                legacy_raw2 = _find_legacy_receipt_in_artifacts(
                    current_spec, run_root, event_log)
                if legacy_raw2:
                    try:
                        data, _result = _extract_json(legacy_raw2), result
                        return data, _result
                    except AgentOutputError as exc:
                        last_error = exc

            if not found_path:
                tail = _stderr_tail(result.stderr)
                if process_failed:
                    reason = (
                        f"agent process failed (exit_code={result.exit_code}) "
                        f"before writing its receipt '{spec.output_file}'"
                    )
                else:
                    reason = (
                        f"agent did not write '{spec.output_file}' "
                        f"(exit_code={result.exit_code})"
                    )
                msg = f"{spec.role}: {reason}."
                if tail:
                    msg += f" stderr: {tail}"
                last_error = AgentOutputError(msg)

        # ---- Prepare for retry ----
        if process_failed:
            # The agent CLI itself crashed (network/bridge error, timeout, or a
            # non-zero exit). Telling the model to "write ONLY valid JSON" is
            # useless here — it never got to act on the prompt — and halving the
            # timeout only makes transient connection failures MORE likely to
            # recur. Retry the original prompt with the original timeout and add
            # a short backoff delay so a flaky bridge can recover.
            retry_timeout = base_timeout
            retry_prompt = base_prompt
            if attempt < max_repairs:
                delay = min(2 ** attempt, 5) if connection_error else 1
                time.sleep(delay)
        else:
            # The agent ran but produced no/malformed JSON. Sharpen the
            # instruction and halve the timeout so a model-refusal fails fast.
            retry_timeout = max(120, current_spec.timeout_seconds // 2)
            retry_prompt = base_prompt + (
                f"\n\n---\nPREVIOUS ATTEMPT FAILED. Write ONLY valid JSON "
                f"to '{current_spec.output_file}' — no markdown, no commentary."
            )

        current_spec = dataclasses.replace(
            current_spec,
            prompt=retry_prompt,
            timeout_seconds=retry_timeout,
        )

    if event_log:
        event_log.emit("agent.call.failed", role=spec.role,
                       error=str(last_error), call_id=call_id)
    raise last_error
