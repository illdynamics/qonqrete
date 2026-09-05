"""
CodeSeeq adapter — with live output streaming via subprocess.Popen.

When streaming is enabled on the AgentCallSpec:
  - Uses subprocess.Popen instead of subprocess.run
  - Reads stdout/stderr concurrently via threads to prevent deadlock
  - Writes original (non-redacted) output to artifact files live
  - Emits redacted output to the terminal sink live
  - Handles timeout and KeyboardInterrupt cleanly
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from .base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities
from ..path_guards import assert_command_cwd_allowed, PathPolicyViolation
from ..env import build_codeseeq_env
from ..sandbox import SandboxUnavailable, SandboxPolicyViolation
from ..sandbox_integration import maybe_wrap_command_for_sandbox


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------
_SECRET_REDACT = "[ƇΞƝƧØⱤΞƊ]"

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)(sk-[a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    re.compile(r"(DEEPSEEK_API_KEY\s*=\s*)([^\s\n]+)", re.IGNORECASE),
    re.compile(r"(OPENAI_API_KEY\s*=\s*)([^\s\n]+)", re.IGNORECASE),
    re.compile(r"([Aa][Pp][Ii][_-]?[Kk][Ee][Yy]\s*=\s*)([^\s\n]+)"),
    re.compile(r"([Kk][Ee][Yy]\s*=\s*)(sk-[^\s\n]+)", re.IGNORECASE),
    re.compile(r"([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*=\s*)([^\s\n]+)"),
    re.compile(r"([Tt][Oo][Kk][Ee][Nn]\s*=\s*)([^\s\n]+)"),
    re.compile(r"([Ss][Ee][Cc][Rr][Ee][Tt]\s*=\s*)([^\s\n]+)"),
    re.compile(r'(OPENAI_API_KEY\s*=\s*\")([^"]+)\"', re.IGNORECASE),
    re.compile(r'(DEEPSEEK_API_KEY\s*=\s*\")([^"]+)\"', re.IGNORECASE),
    re.compile(r'(export\s+[A-Z_]+KEY\s*=\s*\"?)([^\s\"]+)\"?', re.IGNORECASE),
]


def _redact_secrets(text: str) -> str:
    """Redact secret values from text."""
    for pat in _SECRET_PATTERNS:
        samp = pat.search(text)
        if samp and samp.groups():
            text = pat.sub(r"\1" + _SECRET_REDACT, text)
        else:
            text = pat.sub(_SECRET_REDACT, text)
    return text


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------
def _find_codeseeq_binary(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return explicit_path
    env_path = os.environ.get("QQ_CODESEEQ_BIN")
    if env_path:
        return env_path
    found = shutil.which("codeseeq")
    if found:
        return found
    for candidate in ("../codeseeq/codeseeq", "./codeseeq/codeseeq",
                       "./codeseeq"):
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        "Could not find a `codeseeq` binary. Install it "
        "(see https://github.com/illdynamics/codeseeq) and either put it on "
        "PATH, set QQ_CODESEEQ_BIN, or pass codeseeq_path= explicitly "
        "to CodeSeeqAdapter()."
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class CodeSeeqAdapter(AgentAdapter):
    name = "codeseeq"

    def __init__(self, codeseeq_path: Optional[str] = None,
                 runtime_mode: str = "auto", bridge_mode: str = "auto",
                 no_repo: bool = False,
                 event_log_cb: Optional[Callable] = None):
        self.codeseeq_path = _find_codeseeq_binary(codeseeq_path)
        self.runtime_mode = runtime_mode
        self.bridge_mode = bridge_mode
        self.no_repo = no_repo
        # Optional stream->event-log bridge (set by qontroller for web streaming)
        self._output_event_log = event_log_cb

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_sessions=False,
            supports_interactive_tui=True,
            supports_exec_mode=True,
            supports_tools=True,
            supports_thinking_mode=True,
            requires_host_mode=False,
            safe_in_container=True,
        )

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        # Path policy: validate cwd before launching subprocess
        ws_root = getattr(spec, 'workspace_root', '') or spec.repo_root or spec.cd or spec.workdir
        run_root = getattr(spec, 'run_root', '') or ''
        if ws_root and run_root:
            # Validate workdir
            assert_command_cwd_allowed(spec.workdir, ws_root, run_root)
            # Validate cd/repo_root
            cd_path = getattr(spec, 'cd', '') or getattr(spec, 'repo_root', '')
            if cd_path:
                assert_command_cwd_allowed(cd_path, ws_root, run_root)
        os.makedirs(spec.workdir, exist_ok=True)

        # Determine if sandbox wrapping will be active for this call
        sandbox_active = False
        sandbox_output_dir = ""  # Always initialized
        try:
            from ..sandbox_integration import maybe_wrap_command_for_sandbox as _check_sandbox
            # Quick check without actually wrapping
            role = getattr(spec, 'role', '')
            if role == 'construqtor':
                from ..sandbox import get_sandbox_mode, SandboxMode, resolve_bwrap_binary
                mode = get_sandbox_mode()
                if mode != SandboxMode.OFF:
                    bwrap_bin = resolve_bwrap_binary()
                    if bwrap_bin is not None or mode == SandboxMode.REQUIRED:
                        sandbox_active = bwrap_bin is not None
        except Exception:
            sandbox_active = False

        # Write prompt file — location depends on sandbox
        _pfx = spec.call_id if spec.call_id else spec.role
        run_root = getattr(spec, 'run_root', '') or ''

        if sandbox_active and run_root and spec.role == 'construqtor':
            # Sandbox mode: write prompt to run_root/sandbox/input/<call_id>/prompt.md
            sandbox_input_dir = os.path.join(run_root, 'sandbox', 'input', _pfx)
            os.makedirs(sandbox_input_dir, exist_ok=True)
            prompt_file = os.path.join(sandbox_input_dir, 'prompt.md')
            # Also create the output directory
            sandbox_output_dir = os.path.join(run_root, 'sandbox', 'output', _pfx)
            os.makedirs(sandbox_output_dir, exist_ok=True)
        else:
            # Non-sandbox: write to workdir as before (will be cleaned up)
            prompt_file = os.path.join(
                spec.workdir, f".qq_prompt_{_pfx}.md")

        with open(prompt_file, "w", encoding="utf-8") as fh:
            fh.write(spec.prompt)

        # Remove stale output file — location depends on sandbox
        if sandbox_active and run_root and spec.role == 'construqtor':
            output_path = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(sandbox_output_dir, spec.output_file)
            # Also check workdir for stale output
            workdir_output = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(spec.workdir, spec.output_file)
            if os.path.exists(workdir_output):
                os.remove(workdir_output)
        else:
            output_path = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(spec.workdir, spec.output_file)
        if os.path.exists(output_path):
            os.remove(output_path)

        cmd = [
            self.codeseeq_path, "run", "-f", prompt_file,
            "--model", spec.model,
            "--sandbox", spec.sandbox,
        ]
        # Pass --cd to change directory if a repo_root/cd path is specified
        cd_path = getattr(spec, 'cd', '') or getattr(spec, 'repo_root', '')
        if cd_path:
            cmd.extend(["--cd", cd_path])
        if spec.thinking and "-thinking" not in spec.model:
            cmd.append("--thinking")
        # NOTE: codeseeq wrapper already adds --skip-git-repo-check unconditionally
        # (line 1420 of codeseeq binary). Duplicate causes "cannot be used multiple times" error.
        if self.no_repo:
            pass  # no-op: codeseeq binary already adds this flag

        env = build_codeseeq_env()
        env["CODESEEQ_RUNTIME_MODE"] = self.runtime_mode
        env["CODESEEQ_BRIDGE_MODE"] = self.bridge_mode
        env["CODESEEQ_WORKSPACE_BANNER"] = "false"
        # Per-call CODEX_HOME isolation — prevents config.toml race conditions
        # when multiple agents run in parallel from the same working directory.
        # Each agent gets its own .codeseeq-home under run_root (or a temp dir
        # if run_root is not available).  The bridge port scanner is already
        # per-process safe, but config.toml, bridge.log, and bridge.pid all
        # live under CODEX_HOME and must not be shared across concurrent calls.
        if _pfx:
            if run_root:
                codeseeq_home = os.path.join(run_root, '.codeseeq-home', _pfx)
            else:
                import tempfile
                codeseeq_home = tempfile.mkdtemp(prefix='qq-codeseeq-home-', suffix=f'-{_pfx}')
            os.makedirs(codeseeq_home, exist_ok=True)
            env["CODESEEQ_HOST_CODEX_HOME"] = codeseeq_home
        if spec.extra_env:
            env.update(spec.extra_env)
        if spec.reasoning_effort:
            env["CODESEEQ_REASONING_EFFORT"] = spec.reasoning_effort
        if spec.temperature is not None:
            env["CODESEEQ_TEMPERATURE"] = str(spec.temperature)
        if spec.top_p is not None:
            env["CODESEEQ_TOP_P"] = str(spec.top_p)

        # Sandbox wrapping for construQtor (bubblewrap OS-level isolation)
        sandbox_cwd = None
        sandbox_was_active = False
        try:
            # Before wrapping, store original command to detect if wrapping happened
            original_cmd = list(cmd)
            cmd, env, sandbox_cwd = maybe_wrap_command_for_sandbox(
                spec, cmd, env, event_log=getattr(spec, 'event_log', None))
            if cmd != original_cmd:
                sandbox_was_active = True
        except SandboxUnavailable:
            # Clean up prompt scratch file in workspace before raising
            if not (sandbox_active and run_root):
                try:
                    os.remove(prompt_file)
                except OSError:
                    pass
            raise
        except SandboxPolicyViolation:
            if not (sandbox_active and run_root):
                try:
                    os.remove(prompt_file)
                except OSError:
                    pass
            raise

        # If sandboxed, the host cwd should be workspace_root (not run_root)
        run_cwd = sandbox_cwd if sandbox_cwd else spec.workdir

        # If sandbox is active, rewrite the output path to use sandbox directory
        if sandbox_was_active and run_root and spec.role == 'construqtor':
            sandbox_output_dir = os.path.join(run_root, 'sandbox', 'output', _pfx)
            output_path = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(sandbox_output_dir, spec.output_file)

        # If streaming is enabled, use live Popen path
        if getattr(spec, 'stream_output', False):
            return self._call_streaming(spec, cmd, env, output_path, cwd=run_cwd, sandbox_output_dir=sandbox_output_dir)
        else:
            return self._call_batch(spec, cmd, env, output_path, cwd=run_cwd, sandbox_output_dir=sandbox_output_dir)

    def _call_batch(self, spec: AgentCallSpec, cmd: list, env: dict,
                    output_path: str, cwd: str = "", sandbox_output_dir: str = "") -> AgentCallResult:
        """Original batch subprocess.run path."""
        start = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=cwd or spec.workdir, env=env,
                capture_output=True, text=True,
                timeout=spec.timeout_seconds,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            stdout = _redact_secrets(exc.stdout or "")
            stderr = _redact_secrets(
                f"TIMEOUT after {spec.timeout_seconds}s: {exc}")

        duration = time.time() - start
        
        # Check both the primary output path and, if sandboxed, the sandbox output dir
        exists = os.path.exists(output_path)
        raw_output = None
        if exists:
            with open(output_path, "r", encoding="utf-8") as fh:
                raw_output = fh.read()
        elif sandbox_output_dir:
            # Try the sandbox output dir
            sandbox_out = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(sandbox_output_dir, os.path.basename(spec.output_file))
            if os.path.exists(sandbox_out):
                exists = True
                output_path = sandbox_out
                with open(sandbox_out, "r", encoding="utf-8") as fh:
                    raw_output = fh.read()

        stdout = _redact_secrets(stdout)
        stderr = _redact_secrets(stderr)

        # Write artifact files
        if hasattr(spec, 'artifact_dir') and spec.artifact_dir:
            arts_dir = spec.artifact_dir
            os.makedirs(arts_dir, exist_ok=True)
            for fname, fcontent in [("stdout.txt", stdout),
                                   ("stderr.txt", stderr)]:
                with open(os.path.join(arts_dir, fname), "w",
                          encoding="utf-8") as fh:
                    fh.write(fcontent)

        return AgentCallResult(
            spec=spec, exit_code=exit_code, stdout=stdout, stderr=stderr,
            duration_seconds=duration, output_path_exists=exists,
            raw_output_text=raw_output,
        )

    def _call_streaming(self, spec: AgentCallSpec, cmd: list, env: dict,
                        output_path: str, cwd: str = "", sandbox_output_dir: str = "") -> AgentCallResult:
        """Live streaming path using subprocess.Popen with threaded readers."""
        sink = getattr(spec, 'output_sink', None)
        stream_stderr = getattr(spec, 'stream_stderr', True)
        role = spec.role
        call_id = getattr(spec, 'call_id', '')
        arts_dir = getattr(spec, 'artifact_dir', '')
        # Optional event-log bridge (web SSE streaming). Preferred from the
        # spec/config (mirrors the 'output_sink' pattern); falls back to the
        # instance-level callback set by qontroller.
        event_log_cb = getattr(spec, 'event_log', None) or getattr(self, '_output_event_log', None)

        # Open artifact files for live writing (non-redacted)
        stdout_art_fh = None
        stderr_art_fh = None
        if arts_dir:
            os.makedirs(arts_dir, exist_ok=True)
            stdout_art_fh = open(os.path.join(arts_dir, "stdout.txt"), "w",
                                 encoding="utf-8")
            stderr_art_fh = open(os.path.join(arts_dir, "stderr.txt"), "w",
                                 encoding="utf-8")

        stdout_lines = []
        stderr_lines = []
        lock = threading.Lock()

        def _emit(chunk: dict) -> None:
            """Emit to sink if present, and forward to the optional event-log bridge."""
            # BGP5: strip the external agent's env-debug leak ('QQV_ROLE=...') at the
            # earliest adapter/output-callback capture point — never forward it.
            ctext = (chunk or {}).get('text', '') or ''
            if isinstance(ctext, str) and ('QQV_ROLE=' in ctext or 'vQQV_ROLE=' in ctext):
                return
            if sink:
                try:
                    sink(chunk)
                except Exception:
                    pass
            if event_log_cb:
                try:
                    event_log_cb(chunk)
                except Exception:
                    pass

        def _read_stdout(stream, lines_list, artifact_fh, stream_name):
            try:
                for line in iter(stream.readline, ""):
                    lines_list.append(line)
                    if artifact_fh:
                        with lock:
                            artifact_fh.write(line)
                            artifact_fh.flush()
                    _emit({
                        "role": role,
                        "stream_name": stream_name,
                        "text": line,
                        "call_id": call_id,
                    })
            except (ValueError, IOError):
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        def _read_stderr(stream, lines_list, artifact_fh, stream_name):
            try:
                for line in iter(stream.readline, ""):
                    lines_list.append(line)
                    if artifact_fh:
                        with lock:
                            artifact_fh.write(line)
                            artifact_fh.flush()
                    # BGP5: never forward the external agent's env-debug leak
                    # ('vQQV_ROLE=...'), regardless of which funnel it reaches.
                    if isinstance(line, str) and ('QQV_ROLE=' in line or 'vQQV_ROLE=' in line):
                        continue
                    if stream_stderr:
                        _emit({
                            "role": role,
                            "stream_name": stream_name,
                            "text": line,
                            "call_id": call_id,
                        })
                    else:
                        # stderr not shown in terminal, but still forward it to the
                        # event-log bridge so the dashboard can display it.
                        if event_log_cb:
                            try:
                                event_log_cb({
                                    "role": role,
                                    "stream_name": stream_name,
                                    "text": line,
                                    "call_id": call_id,
                                })
                            except Exception:
                                pass
            except (ValueError, IOError):
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        start = time.time()
        exit_code = 0
        interrupted = False
        timed_out = False

        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd or spec.workdir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )

            t_out = threading.Thread(
                target=_read_stdout,
                args=(proc.stdout, stdout_lines, stdout_art_fh, "stdout"),
                daemon=True)
            t_err = threading.Thread(
                target=_read_stderr,
                args=(proc.stderr, stderr_lines, stderr_art_fh, "stderr"),
                daemon=True)
            t_out.start()
            t_err.start()

            try:
                exit_code = proc.wait(timeout=spec.timeout_seconds)
                t_out.join(timeout=5)
                t_err.join(timeout=5)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process(proc)
                t_out.join(timeout=3)
                t_err.join(timeout=3)
                exit_code = -1
            except KeyboardInterrupt:
                interrupted = True
                _terminate_process(proc)
                t_out.join(timeout=3)
                t_err.join(timeout=3)
                exit_code = -1

        except Exception as exc:
            exit_code = -1
            stdout_lines.append(f"ERROR: {exc}\n")
        finally:
            if stdout_art_fh:
                stdout_art_fh.close()
            if stderr_art_fh:
                stderr_art_fh.close()

        duration = time.time() - start

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        if timed_out:
            stderr = (stderr or "") + f"\nTIMEOUT after {spec.timeout_seconds}s\n"
        if interrupted:
            stderr = (stderr or "") + "\nINTERRUPTED (KeyboardInterrupt)\n"

        # Check primary output path
        exists = os.path.exists(output_path)
        raw_output = None
        if exists:
            try:
                with open(output_path, "r", encoding="utf-8") as fh:
                    raw_output = fh.read()
            except Exception:
                pass
        # If sandboxed, also check sandbox output dir
        if not exists and sandbox_output_dir:
            sandbox_out = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(sandbox_output_dir, os.path.basename(spec.output_file))
            if os.path.exists(sandbox_out):
                exists = True
                try:
                    with open(sandbox_out, "r", encoding="utf-8") as fh:
                        raw_output = fh.read()
                except Exception:
                    pass

        return AgentCallResult(
            spec=spec, exit_code=exit_code,
            stdout=stdout, stderr=stderr,
            duration_seconds=duration, output_path_exists=exists,
            raw_output_text=raw_output,
        )


def _terminate_process(proc: subprocess.Popen) -> None:
    """Terminate process cleanly: SIGTERM first, then SIGKILL."""
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
