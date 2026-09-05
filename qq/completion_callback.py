"""
QonQrete completion callback — sends run-completed notifications to Obelisk.

Fires when a run reaches ANY terminal state (success, failed, aborted, etc.).
Never notifies on started, queued, planned, built, review, repair, partial
success, or still-running states.

QonQrete speaks only to Obelisk callback endpoint. QonQrete does NOT speak
Telegram or Signal directly — it provides enough metadata for Obelisk to
route the reply over the same channel that triggered the task.
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CompletionCallbackConfig:
    """Resolved completion callback configuration from env + YAML."""
    enabled: bool = False
    url: str = ""
    token: str = ""
    timeout_seconds: int = 10
    max_retries: int = 5
    retry_base_seconds: float = 2.0
    on_failure: str = "log_only"  # "log_only" | "mark_warning"
    dashboard_url: str = ""


@dataclasses.dataclass
class CallbackState:
    """Persisted callback state for exactly-once semantics."""
    enabled: bool = True
    state: str = "pending"  # pending | sending | sent | failed
    event: str = ""
    run_id: str = ""
    status: str = ""
    success: bool = False
    attempts: int = 0
    last_attempt_at: Optional[str] = None
    sent_at: Optional[str] = None
    callback_url: str = ""
    http_status: Optional[int] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        # Remove None values for cleanliness
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CallbackState":
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


@dataclasses.dataclass
class CompletionStatus:
    done: bool = False
    terminal: bool = False
    success: bool = False
    status: str = ""
    reason: str = ""
    final_summary: Optional[str] = None
    exit_code: Optional[int] = None


# ---------------------------------------------------------------------------
# Channel normalization
# ---------------------------------------------------------------------------

_CHANNEL_NORMALIZE = {
    "telegram": "telegram", "tg": "telegram",
    "signal": "signal", "signal-cli": "signal",
}

def _normalize_channel(raw: Optional[str]) -> str:
    """Normalize a channel string to canonical form."""
    if not raw:
        return ""
    return _CHANNEL_NORMALIZE.get(raw.lower().strip(), raw.lower().strip())


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_completion_callback_config() -> CompletionCallbackConfig:
    """Load completion callback configuration from env vars + optional YAML.

    Precedence (highest wins):
      1. Env vars (QONQRETE_COMPLETION_CALLBACK_*, QONQRETE_OBELISK_CALLBACK_*)
      2. YAML section qonqrete_completion_callback in config/qq.yaml
      3. Safe defaults (disabled)
    """
    cfg = CompletionCallbackConfig()

    # Try YAML first
    _try_load_callback_yaml(cfg)

    # Env: enabled
    env_enabled = os.environ.get("QONQRETE_COMPLETION_CALLBACK_ENABLED", "")
    _explicitly_disabled = False
    if env_enabled.lower() in ("1", "true", "yes"):
        cfg.enabled = True
    elif env_enabled.lower() in ("0", "false", "no"):
        cfg.enabled = False
        _explicitly_disabled = True

    # Env: URL
    env_url = os.environ.get("QONQRETE_OBELISK_CALLBACK_URL", "")
    if env_url:
        cfg.url = env_url

    # Auto-enable if URL is set and enabled was never explicitly set to False
    if cfg.url and not _explicitly_disabled:
        cfg.enabled = True

    # Env: token
    env_token = os.environ.get("QONQRETE_OBELISK_CALLBACK_TOKEN", "")
    if env_token:
        cfg.token = env_token

    # If YAML specifies token_env, read that env var
    _yaml_token_env = os.environ.get("_QONQRETE_CALLBACK_YAML_TOKEN_ENV", "")
    if _yaml_token_env:
        cfg.token = os.environ.get(_yaml_token_env, cfg.token)

    # Env: timeout
    env_timeout = os.environ.get("QONQRETE_COMPLETION_CALLBACK_TIMEOUT_SECONDS", "")
    if env_timeout:
        try:
            cfg.timeout_seconds = int(env_timeout)
        except ValueError:
            pass

    # Env: max retries
    env_retries = os.environ.get("QONQRETE_COMPLETION_CALLBACK_MAX_RETRIES", "")
    if env_retries:
        try:
            cfg.max_retries = int(env_retries)
        except ValueError:
            pass

    # Env: retry base seconds
    env_base = os.environ.get("QONQRETE_COMPLETION_CALLBACK_RETRY_BASE_SECONDS", "")
    if env_base:
        try:
            cfg.retry_base_seconds = float(env_base)
        except ValueError:
            pass

    # Env: on_failure
    env_failure = os.environ.get("QONQRETE_COMPLETION_CALLBACK_ON_FAILURE", "")
    if env_failure in ("log_only", "mark_warning"):
        cfg.on_failure = env_failure

    # Dashboard URL (for the reply text)
    dashboard_url = os.environ.get("QONQRETE_PUBLIC_DASHBOARD_URL", "")
    if dashboard_url:
        cfg.dashboard_url = dashboard_url

    return cfg


def get_run_aware_callback_config(run_root: str = "") -> Dict[str, Any]:
    """Return callback config that is run-aware (checks per-run callback URLs).

    This is used by API responses to correctly set completion_callback_configured
    when a per-run callback URL exists, even if no global URL is configured.
    """
    cfg = load_completion_callback_config()

    # Check if globally explicitly disabled
    env_enabled = os.environ.get("QONQRETE_COMPLETION_CALLBACK_ENABLED", "")
    if env_enabled.lower() in ("0", "false", "no"):
        return {
            "enabled": False,
            "configured": False,
            "url_configured": False,
            "timeout_seconds": cfg.timeout_seconds,
            "max_retries": cfg.max_retries,
            "on_failure": cfg.on_failure,
        }

    # Check for per-run callback URL
    per_run_url = ""
    if run_root:
        per_run_url = _resolve_per_run_callback_url(run_root)

    configured = bool(cfg.url or per_run_url)
    return {
        "enabled": True,
        "configured": configured,
        "url_configured": configured,
        "timeout_seconds": cfg.timeout_seconds,
        "max_retries": cfg.max_retries,
        "on_failure": cfg.on_failure,
    }


def is_callback_enabled_for_run(run_root: str) -> bool:
    """Check if callbacks are enabled for a specific run.

    Returns False only when QONQRETE_COMPLETION_CALLBACK_ENABLED is explicitly
    set to false/0/no. Otherwise, returns True if any callback URL exists
    (global or per-run).
    """
    env_enabled = os.environ.get("QONQRETE_COMPLETION_CALLBACK_ENABLED", "")
    if env_enabled.lower() in ("0", "false", "no"):
        return False

    cfg = load_completion_callback_config()
    if cfg.url:
        return True

    # Check per-run callback URL
    if _resolve_per_run_callback_url(run_root):
        return True

    return False


def _try_load_callback_yaml(cfg: CompletionCallbackConfig) -> None:
    """Attempt to load qonqrete_completion_callback section from qq.yaml."""
    try:
        import yaml
        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yaml_path = os.path.join(_repo_root, "config", "qq.yaml")
        if not os.path.isfile(yaml_path):
            return
        with open(yaml_path, "r") as f:
            raw = yaml.safe_load(f) or {}
        section = raw.get("qonqrete_completion_callback")
        if not isinstance(section, dict):
            return
        if section.get("enabled") is True:
            cfg.enabled = True
        if section.get("url"):
            cfg.url = section["url"]
        if section.get("timeout_seconds") is not None:
            cfg.timeout_seconds = int(section["timeout_seconds"])
        if section.get("max_retries") is not None:
            cfg.max_retries = int(section["max_retries"])
        if section.get("retry_base_seconds") is not None:
            cfg.retry_base_seconds = float(section["retry_base_seconds"])
        if section.get("on_failure") in ("log_only", "mark_warning"):
            cfg.on_failure = section["on_failure"]
        if section.get("dashboard_url"):
            cfg.dashboard_url = section["dashboard_url"]
        # YAML token_env support
        token_env_name = section.get("token_env", "")
        if token_env_name:
            os.environ["_QONQRETE_CALLBACK_YAML_TOKEN_ENV"] = token_env_name
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Origin metadata persistence
# ---------------------------------------------------------------------------


def write_origin_metadata(
    run_root: str,
    request_data: Dict[str, Any],
    run_id: str = "",
    target_path: str = "",
    events_path: str = "",
    dashboard_url: str = "",
) -> Dict[str, Any]:
    """Persist origin metadata from the API request into origin.json.

    Normalizes source_channel from channel/transport/source.
    Preserves flat callback_url, callback_token, callback_token_ref.
    Preserves nested obelisk block and metadata.
    Stores resolved target_path, events_path, dashboard_url, workspace_root.
    """
    state_dir = os.path.join(run_root, "state")
    os.makedirs(state_dir, exist_ok=True)

    # Normalize source_channel
    source_channel = _normalize_channel(
        request_data.get("source_channel") or
        request_data.get("channel") or
        request_data.get("transport") or
        ""
    )
    if not source_channel and "source" in request_data:
        src = request_data["source"].lower()
        if "telegram" in src:
            source_channel = "telegram"
        elif "signal" in src:
            source_channel = "signal"

    if not source_channel:
        source_channel = "unknown"

    # Preserve caller-provided reply_to if it's a dict; synthesize if missing
    caller_reply_to = request_data.get("reply_to")
    if isinstance(caller_reply_to, dict) and caller_reply_to:
        reply_to = dict(caller_reply_to)
        # Normalize channel in reply_to
        if "channel" in reply_to:
            reply_to["channel"] = _normalize_channel(reply_to["channel"])
    else:
        # Synthesize reply_to
        if source_channel == "telegram":
            reply_to = {
                "channel": "telegram",
                "chat_id": request_data.get("chat_id", ""),
                "message_id": request_data.get("message_id", ""),
            }
        elif source_channel == "signal":
            recipient = (
                request_data.get("recipient") or
                request_data.get("chat_id") or
                request_data.get("sender_id", "")
            )
            reply_to = {
                "channel": "signal",
                "recipient": recipient,
                "message_id": request_data.get("message_id", ""),
            }
        else:
            reply_to = {}

    # Persist obelisk callback block if provided
    obelisk_block = None
    _o = request_data.get("obelisk")
    if isinstance(_o, dict):
        obelisk_block = _o
    # Also check metadata.obelisk
    metadata = request_data.get("metadata", {})
    if not obelisk_block and isinstance(metadata, dict):
        _mo = metadata.get("obelisk")
        if isinstance(_mo, dict):
            obelisk_block = _mo

    # Resolved paths
    resolved_target = target_path or request_data.get("target_path", request_data.get("target", ""))
    resolved_events = events_path or request_data.get("events_path", "")
    resolved_dashboard = dashboard_url or request_data.get("dashboard_url", "")

    # workspace_root: derive from target_path
    workspace_root = resolved_target

    origin = {
        "source": request_data.get("source", "unknown"),
        "source_channel": source_channel,
        "sender_id": request_data.get("sender_id", ""),
        "sender_name": request_data.get("sender_name", ""),
        "sender_display": request_data.get("sender_display", ""),
        "chat_id": request_data.get("chat_id", ""),
        "chat_title": request_data.get("chat_title", ""),
        "message_id": request_data.get("message_id", ""),
        "transcription_id": request_data.get("transcription_id", ""),
        "raw_transcription": request_data.get("raw_transcription", ""),
        "trigger": request_data.get("trigger", "qonqrete"),
        "task_text": request_data.get("task_text", ""),
        "task_title": request_data.get("task_title", ""),
        "mode": request_data.get("mode", ""),
        "target": request_data.get("target", ""),
        "target_path": resolved_target,
        "workspace_root": workspace_root,
        "run_root": request_data.get("run_root", run_root or run_id),
        "run_id": run_id,
        "events_path": resolved_events,
        "dashboard_url": resolved_dashboard,
        "reply_to": reply_to,
        "callback_url": request_data.get("callback_url", ""),
        "callback_token": request_data.get("callback_token", ""),
        "callback_token_ref": request_data.get("callback_token_ref", ""),
        "metadata": metadata,
        "obelisk": obelisk_block,
    }

    origin_path = os.path.join(state_dir, "origin.json")
    with open(origin_path, "w", encoding="utf-8") as f:
        json.dump(origin, f, indent=2, default=str)

    return origin


def load_origin_metadata(run_root: str) -> Optional[Dict[str, Any]]:
    """Load origin metadata from a run's state/origin.json."""
    origin_path = os.path.join(run_root, "state", "origin.json")
    if not os.path.isfile(origin_path):
        return None
    try:
        with open(origin_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Terminal status detection
# ---------------------------------------------------------------------------


def is_run_terminal(run_root: str) -> bool:
    """Determine if a QonQrete run has reached any terminal state."""
    status = get_run_terminal_status(run_root)
    return status.terminal


def is_run_fully_done(run_root: str) -> bool:
    """Determine if a QonQrete run has reached true FULLY_DONE."""
    status = get_run_terminal_status(run_root)
    return status.done


FULLY_DONE_ACTION = "FULLY_DONE"


def run_is_fully_done(action_status, run_root):
    """Single shared 'terminal FULLY_DONE' predicate for the web (A15) and TUI (B3).

    This is the ONE agreed semantic definition both UIs call so they freeze the
    Total/Agent timers at the exact same moment. A run is considered terminal
    FULLY_DONE iff EITHER:

      1. the web poll path's ``action_status`` reads ``'FULLY_DONE'`` (the
         convention derived from the ``run.completed`` event in
         qq/web/read_model.py and observed live via /api/qonqrete poll), OR
      2. ``get_run_terminal_status()`` reports ``done=True`` with
         ``status == 'FULLY_DONE'`` (canonical, read from state/final.json or
         events.jsonl).

    Passing ``action_status is None`` (e.g. when a caller only has run_root)
    falls back to the disk-based terminal status alone.

    Backward compatible: the existing ``is_run_fully_done(run_root)``
    (any ``done`` state) and ``is_run_terminal(run_root)`` (any terminal state)
    predicates are unchanged — this is a strict, exact-status predicate layered
    on top so A15/B3 agree tick-for-tick.
    """
    if action_status == FULLY_DONE_ACTION:
        return True
    status = get_run_terminal_status(run_root)
    return status.done and status.status == FULLY_DONE_ACTION


def get_run_completion_status(run_root: str) -> CompletionStatus:
    """Get the completion status of a run (deprecated; use get_run_terminal_status)."""
    return get_run_terminal_status(run_root)


def get_run_terminal_status(run_root: str) -> CompletionStatus:
    """Get the terminal status of a run by reading canonical signals.

    Signal precedence:
      1. state/final.json (canonical, written by qontroller)
      2. events.jsonl terminal events
      3. Runner state files (inferior, never trusted alone)
    """
    # Check final.json first — the canonical source
    final_path = os.path.join(run_root, "state", "final.json")
    if os.path.isfile(final_path):
        try:
            with open(final_path, "r", encoding="utf-8") as f:
                final = json.load(f)
            status_val = final.get("status", "")

            # Check final_verdict.status first — this is the canonical verdict
            verdict = final.get("final_verdict", {})
            if isinstance(verdict, dict):
                v_status = verdict.get("status", "")
                v_status_upper = v_status.upper() if isinstance(v_status, str) else ""
                # FULLY_DONE in final_verdict takes precedence over top-level "done"
                if v_status_upper == "FULLY_DONE":
                    return CompletionStatus(
                        done=True, terminal=True, success=True,
                        status="FULLY_DONE",
                        reason="final_verdict_FULLY_DONE",
                        final_summary=verdict.get("summary", ""),
                    )
                # Also accept other positive verdict statuses
                if v_status_upper in ("DONE", "SUCCESS", "ACCEPTED", "PASSED"):
                    return CompletionStatus(
                        done=True, terminal=True, success=True,
                        status=v_status_upper,
                        reason="final_verdict_" + v_status,
                        final_summary=verdict.get("summary", ""),
                    )
                # Terminal but not done from verdict
                if v_status_upper in ("ABORTED", "FAILED", "NOT_DONE"):
                    return CompletionStatus(
                        done=False, terminal=True, success=False,
                        status=v_status_upper,
                        reason="final_verdict_" + v_status,
                        final_summary=verdict.get("summary", ""),
                    )

            # Top-level status
            done_states = {"DONE", "FULLY_DONE", "success", "accepted", "done"}
            if isinstance(status_val, str):
                status_upper = status_val.upper()
                if status_val in done_states or status_upper == "FULLY_DONE":
                    return CompletionStatus(
                        done=True, terminal=True, success=True,
                        status="FULLY_DONE" if status_upper == "FULLY_DONE" else status_upper,
                        reason="final.json_status_" + status_val,
                        final_summary=final.get("summary") or verdict.get("summary", ""),
                    )
                # Terminal but not done
                terminal_states = {"ABORTED", "FAILED", "aborted", "failed"}
                if status_val in terminal_states:
                    return CompletionStatus(
                        done=False, terminal=True, success=False,
                        status=status_val.upper(),
                        reason="final.json_status_" + status_val,
                    )

            # Check for error in final.json
            if final.get("error"):
                return CompletionStatus(
                    done=False, terminal=True, success=False,
                    status="FAILED",
                    reason="final_json_has_error",
                )
        except (json.JSONDecodeError, OSError):
            pass

    # Check events.jsonl for terminal events — read newest first
    events_path = os.path.join(run_root, "events.jsonl")
    if os.path.isfile(events_path):
        try:
            all_events = []
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        all_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            # Scan newest first
            for event in reversed(all_events):
                etype = event.get("type", "")
                if etype == "run.completed":
                    status_val = event.get("status", "")
                    if status_val in ("success", "FULLY_DONE", "DONE", "done"):
                        return CompletionStatus(
                            done=True, terminal=True, success=True,
                            status="FULLY_DONE",
                            reason="events_run_completed_" + str(status_val),
                            final_summary=event.get("summary", ""),
                        )
                elif etype == "run.failed":
                    return CompletionStatus(
                        done=False, terminal=True, success=False,
                        status="FAILED",
                        reason="events_run_failed",
                        final_summary=event.get("error", ""),
                    )
                elif etype == "run.aborted":
                    return CompletionStatus(
                        done=False, terminal=True, success=False,
                        status="ABORTED",
                        reason=event.get("reason", "events_run_aborted"),
                    )
        except (OSError, json.JSONDecodeError):
            pass

    # Check runner.failed.json for launch/pointer failures
    failed_path = os.path.join(run_root, "runner.failed.json")
    if os.path.isfile(failed_path):
        try:
            with open(failed_path, "r", encoding="utf-8") as f:
                failed = json.load(f)
            reason = failed.get("reason", "")
            launch_error = failed.get("launch_error", "")
            exit_code_val = failed.get("exit_code")
            # Determine status from reason
            if reason == "current_run_pointer_write_failed":
                status = "POINTER_FAILED"
            elif launch_error or "launch" in reason.lower():
                status = "LAUNCH_FAILED"
            else:
                status = "FAILED"
            return CompletionStatus(
                done=False, terminal=True, success=False,
                status=status,
                reason=reason or launch_error or "runner_failed",
                exit_code=exit_code_val,
            )
        except (json.JSONDecodeError, OSError):
            pass

    # Runner exit code — process exit is NOT FULLY_DONE
    exit_code_path = os.path.join(run_root, "runner.exit_code")
    if os.path.isfile(exit_code_path):
        try:
            with open(exit_code_path, "r") as f:
                exit_code = int(f.read().strip())
        except (ValueError, OSError):
            exit_code = None
    else:
        exit_code = None

    # Runner finished but QonQrete not done → not FULLY_DONE
    if exit_code is not None:
        terminal = True  # runner has exited
        if exit_code == 0:
            return CompletionStatus(
                done=False, terminal=terminal, success=False,
                status="FINISHED_INCOMPLETE",
                reason="runner_exit_code_0_but_no_qontroller_signal",
                exit_code=exit_code,
            )
        else:
            return CompletionStatus(
                done=False, terminal=terminal, success=False,
                status="PROCESS_FAILED",
                reason="runner_exit_code_nonzero_" + str(exit_code),
                exit_code=exit_code,
            )

    return CompletionStatus(
        done=False, terminal=False, success=False,
        status="unknown",
        reason="no_terminal_signal_found",
    )


# ---------------------------------------------------------------------------
# Callback state persistence
# ---------------------------------------------------------------------------


def _callback_state_path(run_root: str) -> str:
    return os.path.join(run_root, "state", "completion_callback.json")


def load_callback_state(run_root: str) -> Optional[CallbackState]:
    """Load the completion callback state file."""
    path = _callback_state_path(run_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return CallbackState.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        return None


def write_callback_state(run_root: str, state: CallbackState) -> None:
    """Write the completion callback state file."""
    path = _callback_state_path(run_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Write to temp file and atomically rename
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, default=str)
        os.replace(tmp_path, path)
    except OSError:
        # Fallback: direct write
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, default=str)


def acquire_callback_send_lock(
    run_root: str, lock_ttl_seconds: int = 300
) -> bool:
    """Atomically claim the callback send lock using O_CREAT|O_EXCL.

    Creates a lock file at <run_root>/state/completion_callback.lock.
    Uses os.open() with O_CREAT|O_EXCL which is truly atomic on POSIX.

    Returns True if this caller should proceed, False if lock is held.

    Lock TTL: if the lock is older than lock_ttl_seconds (default 5 min),
    it is considered stale and is broken.
    """
    lock_path = os.path.join(run_root, "state", "completion_callback.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    # First, check if callback was already sent
    existing = load_callback_state(run_root)
    if existing is not None and existing.state == "sent":
        return False

    # Try atomic lock creation
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(str(time.time()))
    except FileExistsError:
        # Lock exists — check if stale
        try:
            mtime = os.path.getmtime(lock_path)
            age = time.time() - mtime
            if age < lock_ttl_seconds:
                # Lock is fresh — another process is sending
                return False
            # Lock is stale — break it and acquire
            os.remove(lock_path)
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(str(time.time()))
        except (OSError, FileExistsError):
            # Could not break stale lock — another process grabbed it
            return False

    # Re-check exactly-once after claiming the lock.  A concurrent caller may
    # have completed and written state="sent" between our earlier pre-check
    # and this successful lock acquisition (the winner always writes "sent"
    # *before* releasing the lock file).  If so, release and decline so we
    # never POST twice.
    post = load_callback_state(run_root)
    if post is not None and post.state == "sent":
        release_callback_send_lock(run_root)
        return False

    # Claim the callback state
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state = existing or CallbackState()
    state.state = "sending"
    state.last_attempt_at = now
    state.attempts = (existing.attempts if existing else 0) + 1
    write_callback_state(run_root, state)
    return True


def release_callback_send_lock(run_root: str) -> None:
    """Release the completion callback lock file."""
    lock_path = os.path.join(run_root, "state", "completion_callback.lock")
    try:
        os.remove(lock_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Callback payload builder
# ---------------------------------------------------------------------------


def build_callback_payload(
    run_root: str,
    origin: Dict[str, Any],
    completion: CompletionStatus,
    cfg: CompletionCallbackConfig,
) -> Dict[str, Any]:
    """Build the HTTP callback payload for Obelisk.

    Handles both success (FULLY_DONE) and failure/abort payloads.
    """
    run_id = os.path.basename(run_root)

    # Extract task info
    task_text = origin.get("task_text", "") or origin.get("raw_transcription", "")
    task_title = origin.get("task_title", "") or (task_text[:80].strip() if task_text else "")
    if not task_title:
        # Try to derive from clarified task
        clarified_path = os.path.join(run_root, "state", "clarified_task.json")
        if os.path.isfile(clarified_path):
            try:
                with open(clarified_path, "r") as f:
                    clarified = json.load(f)
                task_title = clarified.get("clarified_text", "")[:80].strip()
            except (json.JSONDecodeError, OSError):
                pass

    # Use resolved actual target path, not the request "default"
    workspace_root = origin.get("target_path", "") or origin.get("workspace_root", "") or origin.get("target", "")

    # Get canonical status
    canonical_status = completion.status
    if canonical_status.upper() in ("DONE", "SUCCESS", "ACCEPTED", "COMPLETED"):
        canonical_status = "FULLY_DONE"

    # Build the reply text
    reply_text = _build_reply_text(
        status=canonical_status,
        task_title=task_title,
        target=workspace_root,
        run_id=run_id,
        success=completion.success,
        summary=completion.final_summary,
        dashboard_url=cfg.dashboard_url or origin.get("dashboard_url", ""),
        failure_reason=completion.reason if not completion.success else None,
        exit_code=completion.exit_code,
    )

    source_channel = origin.get("source_channel", "unknown")

    # Normalize reply_to.channel for routing preference
    reply_to = origin.get("reply_to", {})
    _rt_channel = _normalize_channel(reply_to.get("channel", "") if isinstance(reply_to, dict) else "")
    # Prefer reply_to.channel when source_channel is missing, "api", or "unknown"
    if source_channel in ("", "api", "unknown") and _rt_channel in ("telegram", "signal"):
        reply_channel = _rt_channel
    else:
        reply_channel = _rt_channel or source_channel or "unknown"

    reply_info = {
        "channel": reply_channel,
        "text": reply_text,
    }
    # Add channel-specific routing
    if reply_channel == "telegram":
        reply_info["chat_id"] = reply_to.get("chat_id", "") or origin.get("chat_id", "")
        reply_info["message_id"] = reply_to.get("message_id", "") or origin.get("message_id", "")
    elif reply_channel == "signal":
        # Recipient precedence: reply_to.recipient > reply_to.chat_id > origin.chat_id > origin.sender_id
        recipient = (
            reply_to.get("recipient") or
            reply_to.get("chat_id") or
            origin.get("chat_id") or
            origin.get("sender_id", "")
        )
        if recipient:
            reply_info["recipient"] = recipient
        if reply_to.get("message_id"):
            reply_info["message_id"] = reply_to.get("message_id")

    # Get finished_at from final.json
    finished_at = ""
    final_path = os.path.join(run_root, "state", "final.json")
    if os.path.isfile(final_path):
        try:
            with open(final_path, "r") as f:
                final = json.load(f)
            finished_at = final.get("finished_at", "")
        except (json.JSONDecodeError, OSError):
            pass
    if not finished_at:
        finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Duration estimate
    duration_seconds = None
    events_path = os.path.join(run_root, "events.jsonl")
    if os.path.isfile(events_path):
        try:
            start_ts = None
            end_ts = None
            with open(events_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "run.started":
                        start_ts = event.get("ts")
                    elif event.get("type") in ("run.completed", "run.aborted", "run.failed"):
                        end_ts = event.get("ts")
            if start_ts and end_ts:
                duration_seconds = int(end_ts - start_ts)
        except (OSError, json.JSONDecodeError):
            pass

    event_type = "qonqrete.run.completed" if completion.success else "qonqrete.run.failed"

    # Build origin section (exclude metadata to avoid deep nesting; included separately)
    origin_section = {
        k: v for k, v in origin.items()
        if k not in ("metadata",)
    }

    # ── Top-level Obelisk correlation fields ─────────────────────
    obelisk_block = origin.get("obelisk", {})
    if not isinstance(obelisk_block, dict):
        obelisk_block = {}

    top_callback_id = (
        obelisk_block.get("callback_id")
        or obelisk_block.get("qq_trans_event_id")
        or origin.get("transcription_id", "")
        or run_id
    )
    top_qq_trans_event_id = (
        obelisk_block.get("qq_trans_event_id")
        or top_callback_id
    )
    top_origin_event_id = (
        obelisk_block.get("origin_event_id")
        or top_callback_id
    )
    top_reply_channel = (
        _normalize_channel(obelisk_block.get("reply_channel", ""))
        or _normalize_channel(reply_info.get("channel", ""))
        or _normalize_channel(source_channel)
    )

    payload = {
        # Top-level correlation IDs from Obelisk
        "callback_id": top_callback_id,
        "qq_trans_event_id": top_qq_trans_event_id,
        "origin_event_id": top_origin_event_id,
        "reply_channel": top_reply_channel,
        "callback_kind": "qonqrete-run-terminal",
        "callback_version": 1,
        # Standard fields
        "event": event_type,
        "status": canonical_status,
        "state": canonical_status,
        "ok": completion.success,
        "success": completion.success,
        "fully_done": completion.done,
        "run_name": run_id,
        "run_id": run_id,
        "run_root": run_root,
        "workspace_root": workspace_root,
        "target_path": workspace_root,
        "target_dir": workspace_root,
        "target_directory": workspace_root,
        "output_dir": workspace_root,
        "mode": origin.get("mode", ""),
        "task_text": task_text[:2000] if task_text else "",
        "task_title": task_title,
        "summary": completion.final_summary or "",
        "dashboard_url": cfg.dashboard_url or origin.get("dashboard_url", ""),
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "origin": origin_section,
        "reply": reply_info,
    }

    # Add failure-specific fields
    if not completion.success:
        failure_msg = completion.reason or completion.status or "Run failed"
        payload["error"] = failure_msg
        payload["error_message"] = failure_msg
        payload["failure_reason"] = failure_msg
        if completion.exit_code is not None:
            payload["exit_code"] = completion.exit_code

    # Include metadata if present
    meta = origin.get("metadata", {})
    if meta:
        payload["origin"]["metadata"] = meta

    return payload


def _build_reply_text(
    status: str,
    task_title: str,
    target: str,
    run_id: str,
    success: bool = True,
    summary: Optional[str] = None,
    dashboard_url: str = "",
    failure_reason: Optional[str] = None,
    exit_code: Optional[int] = None,
) -> str:
    """Build the human-readable reply text for Telegram/Signal."""
    if success:
        lines = ["✅ QonQrete FULLY_DONE"]
    else:
        lines = [f"❌ QonQrete {status}"]

    if task_title:
        lines.append(f"Task: {task_title}")
    if target:
        lines.append(f"Target: {target}")
    lines.append(f"Run: {run_id}")
    lines.append(f"Status: {status}")

    if not success and failure_reason:
        lines.append(f"Reason: {failure_reason[:200]}")
    if exit_code is not None:
        lines.append(f"Exit code: {exit_code}")

    if dashboard_url:
        lines.append(f"Dashboard: {dashboard_url}")

    if summary:
        remaining = 1500 - sum(len(l) + 1 for l in lines)
        if remaining > 0:
            if len(summary) > remaining:
                summary = summary[:remaining - 3] + "..."
            lines.append("")
            lines.append("Summary:")
            lines.append(summary)

    text = "\n".join(lines)
    # Final safety truncation
    if len(text) > 1500:
        text = text[:1497] + "..."

    return text


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------


def _resolve_per_run_callback_url(run_root: str) -> str:
    """Resolve callback URL from per-run origin metadata.

    Precedence:
      1. state/origin.json -> origin.obelisk.callback_url
      2. state/origin.json -> origin.callback_url (flat field)
      3. Returns empty string if not found
    """
    origin = load_origin_metadata(run_root)
    if origin is None:
        return ""

    # 1. Obelisk-provided callback URL in nested obelisk block
    obelisk = origin.get("obelisk")
    if isinstance(obelisk, dict):
        url = obelisk.get("callback_url", "")
        if url:
            return url

    # 2. Flat callback_url field
    flat_url = origin.get("callback_url", "")
    if flat_url:
        return flat_url

    return ""


def _resolve_per_run_callback_token(run_root: str) -> str:
    """Resolve callback token from per-run origin metadata.

    Precedence:
      1. origin.obelisk.callback_auth.token
      2. origin.obelisk.callback_auth.token_env → read that env var
      3. origin.callback_token
      4. origin.callback_token_ref → read that env var
      5. QONQRETE_OBELISK_CALLBACK_TOKEN
      6. YAML token env config
    """
    origin = load_origin_metadata(run_root)
    if origin is None:
        return ""

    # 1. Obelisk-provided callback auth in nested obelisk block
    obelisk = origin.get("obelisk")
    if isinstance(obelisk, dict):
        auth = obelisk.get("callback_auth")
        if isinstance(auth, dict) and auth.get("type") == "bearer":
            token = auth.get("token", "")
            if token:
                return token
            # 2. token_env in callback_auth
            token_env = auth.get("token_env", "")
            if token_env:
                return os.environ.get(token_env, "")

    # 3. Flat callback_token field
    flat_token = origin.get("callback_token", "")
    if flat_token:
        return flat_token

    # 4. callback_token_ref → read env var
    token_ref = origin.get("callback_token_ref", "")
    if token_ref:
        return os.environ.get(token_ref, "")

    # 5. QONQRETE_OBELISK_CALLBACK_TOKEN
    env_token = os.environ.get("QONQRETE_OBELISK_CALLBACK_TOKEN", "")
    if env_token:
        return env_token

    # 6. YAML token env config
    yaml_token_env = os.environ.get("_QONQRETE_CALLBACK_YAML_TOKEN_ENV", "")
    if yaml_token_env:
        return os.environ.get(yaml_token_env, "")

    return ""


# ---------------------------------------------------------------------------
# HTTP dispatch with retry
# ---------------------------------------------------------------------------


def send_completion_callback(
    run_root: str,
    cfg: CompletionCallbackConfig,
    callback_url: str = "",
    force: bool = False,
) -> Optional[CallbackState]:
    """Send the terminal callback to Obelisk with retry and backoff.

    This is the main entry point for sending. It handles:
      - Exactly-once check (skip if already sent, unless force=True)
      - Failed cooldown check (skip recent failures with same URL)
      - Atomic claim
      - Payload building
      - HTTP POST with retry/backoff
      - State persistence

    Returns the final CallbackState, or None if already sent.
    """
    # Check global enablement
    if not cfg.enabled:
        return None

    if not callback_url:
        callback_url = cfg.url

    # Per-run callback config from origin.obelisk takes precedence over env
    _per_run_url = _resolve_per_run_callback_url(run_root)
    if _per_run_url:
        callback_url = _per_run_url

    if not callback_url:
        return None

    # Resolve token
    token = _resolve_per_run_callback_token(run_root) or cfg.token

    # ── Failed cooldown check ──────────────────────────────────
    existing_state = load_callback_state(run_root)
    current_cb_url = _resolve_per_run_callback_url(run_root) or callback_url or cfg.url

    if existing_state is not None and existing_state.state == "failed" and not force:
        cooldown_sec = float(os.environ.get(
            "QONQRETE_COMPLETION_CALLBACK_FAILED_RETRY_COOLDOWN_SECONDS", "600"
        ))
        # If URL changed since last attempt, allow retry immediately
        old_url = existing_state.callback_url or ""
        # Allow if URL changed
        if current_cb_url and old_url and old_url != current_cb_url:
            _emit_event(run_root, "completion_callback_retry_url_changed",
                        old_url=old_url, new_url=current_cb_url)
        else:
            # Same URL — check cooldown
            last_at = existing_state.last_attempt_at
            if last_at:
                try:
                    # Parse ISO timestamp
                    import datetime as _dt_mod
                    last_dt = _dt_mod.datetime.strptime(last_at, "%Y-%m-%dT%H:%M:%SZ")
                    last_dt = last_dt.replace(tzinfo=_dt_mod.timezone.utc)
                    elapsed = (time.time() - last_dt.timestamp())
                    if elapsed < cooldown_sec:
                        _emit_event(run_root, "completion_callback_skipped_failed_cooldown",
                                    state="failed",
                                    cooldown_seconds=cooldown_sec,
                                    elapsed_seconds=elapsed,
                                    last_attempt_at=last_at)
                        return existing_state
                except (ValueError, Exception):
                    pass  # Can't parse timestamp — allow retry

    # Exactly-once: atomic lock file for truly atomic claim
    if not force and not acquire_callback_send_lock(run_root):
        # Already sent or another process is sending
        return load_callback_state(run_root)

    lock_acquired = True
    try:
        # Load origin metadata
        origin = load_origin_metadata(run_root)
        if origin is None:
            # No origin metadata — can't send callback, maybe CLI-triggered run
            state = CallbackState(
                enabled=True, state="skipped", event="qonqrete.run.completed",
                run_id=os.path.basename(run_root),
                status="no_origin_metadata",
                callback_url=callback_url,
                last_error="no_origin_metadata",
            )
            write_callback_state(run_root, state)
            _emit_event(run_root, "completion_callback_skipped", reason="no_origin_metadata")
            return state

        # Get terminal status
        completion = get_run_terminal_status(run_root)
        if not completion.terminal:
            _emit_event(run_root, "completion_callback_skipped_not_terminal",
                        status=completion.status, reason=completion.reason)
            state = CallbackState(
                enabled=True, state="skipped", event="qonqrete.run.completed",
                run_id=os.path.basename(run_root),
                status=f"not_terminal_{completion.status}",
                callback_url=callback_url,
                last_error=f"not_terminal: {completion.reason}",
            )
            write_callback_state(run_root, state)
            return state

        # Build payload
        payload = build_callback_payload(run_root, origin, completion, cfg)

        event_type = payload.get("event", "qonqrete.run.completed")

        from urllib.parse import urlparse as _up
        _parsed = _up(callback_url) if callback_url else None
        _cb_diag = {}
        if _parsed:
            _cb_diag = {
                "callback_scheme": _parsed.scheme or "",
                "callback_host": _parsed.hostname or "",
                "callback_port": _parsed.port or (443 if _parsed.scheme == "https" else 80),
                "callback_path": _parsed.path or "",
            }
        _emit_event(run_root, "completion_callback_attempt",
                    run_id=os.path.basename(run_root),
                    channel=origin.get("source_channel", "unknown"),
                    callback_url_configured=True,
                    attempt=1,
                    **_cb_diag)

        # HTTP POST with retry
        body = json.dumps(payload, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        # Only add Authorization header if token is present
        if token:
            headers["Authorization"] = f"Bearer {token}"

        for attempt in range(1, cfg.max_retries + 1):
            try:
                req = urllib.request.Request(callback_url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
                    http_status = resp.getcode()
                    # Read up to 8KB of response body for diagnostics (no secrets)
                    _remote_body = b""
                    _remote_json = {}
                    _remote_ok = None
                    _remote_status = ""
                    _remote_notification_failed = None
                    _remote_orphaned = None
                    _remote_error_preview = ""
                    try:
                        _remote_body = resp.read(8192)
                        if _remote_body:
                            _remote_json = json.loads(_remote_body)
                            _remote_ok = _remote_json.get("ok")
                            _remote_status = _remote_json.get("status", "")
                            _remote_notification_failed = _remote_json.get("notification_failed")
                            _remote_orphaned = _remote_json.get("orphaned")
                            _remote_error = _remote_json.get("error", "")
                            if _remote_error:
                                _remote_error_preview = str(_remote_error)[:200]
                    except Exception:
                        pass
                    now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    state = CallbackState(
                        enabled=True, state="sent",
                        event=event_type,
                        run_id=os.path.basename(run_root),
                        status=completion.status,
                        success=completion.success,
                        attempts=attempt,
                        last_attempt_at=now_ts,
                        sent_at=now_ts,
                        callback_url=callback_url,
                        http_status=http_status,
                    )
                    write_callback_state(run_root, state)
                    lock_acquired = False  # Prevent double-release
                    release_callback_send_lock(run_root)

                    _emit_event(run_root, "completion_callback_sent",
                                run_id=os.path.basename(run_root),
                                channel=origin.get("source_channel", "unknown"),
                                http_status=http_status,
                                attempt=attempt,
                                remote_ok=_remote_ok,
                                remote_status=_remote_status,
                                remote_notification_failed=_remote_notification_failed,
                                remote_orphaned=_remote_orphaned,
                                remote_error_preview=_remote_error_preview)
                    return state
            except urllib.error.HTTPError as e:
                http_status = e.code
                error_msg = f"HTTP {http_status}"
                _log_attempt(run_root, attempt, error_msg, origin, cfg, callback_url=callback_url)
                if http_status is not None and 400 <= http_status < 500:
                    # Client error — don't retry
                    break
            except urllib.error.URLError as e:
                error_msg = f"URLError: {e.reason}"
                _log_attempt(run_root, attempt, error_msg, origin, cfg, callback_url=callback_url)
            except Exception as e:
                error_msg = f"Exception: {type(e).__name__}: {e}"
                _log_attempt(run_root, attempt, error_msg, origin, cfg, callback_url=callback_url)

            # Backoff before retry
            if attempt < cfg.max_retries:
                wait = cfg.retry_base_seconds ** attempt
                time.sleep(wait)

        # All retries exhausted
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state = CallbackState(
            enabled=True, state="failed",
            event=event_type,
            run_id=os.path.basename(run_root),
            status=completion.status,
            success=completion.success,
            attempts=cfg.max_retries,
            last_attempt_at=now_ts,
            callback_url=callback_url,
            last_error="max_retries_exhausted",
        )
        write_callback_state(run_root, state)

        _emit_event(run_root, "completion_callback_failed",
                    run_id=os.path.basename(run_root),
                    channel=origin.get("source_channel", "unknown"),
                    attempts=cfg.max_retries,
                    error="max_retries_exhausted")

        return state
    except Exception as e:
        # Unexpected exception after lock acquisition — release lock and
        # write failed state if possible so subsequent calls can retry.
        try:
            state = CallbackState(
                enabled=True, state="failed",
                event="qonqrete.run.completed",
                run_id=os.path.basename(run_root),
                status="exception",
                callback_url=callback_url,
                last_error=f"{type(e).__name__}: {e}",
            )
            write_callback_state(run_root, state)
        except Exception:
            pass
        try:
            _emit_event(run_root, "completion_callback_failed",
                        run_id=os.path.basename(run_root),
                        error=f"{type(e).__name__}: {e}")
        except Exception:
            pass
        raise
    finally:
        if lock_acquired:
            release_callback_send_lock(run_root)


def _log_attempt(run_root: str, attempt: int, error_msg: str,
                 origin: Dict[str, Any], cfg: CompletionCallbackConfig,
                 callback_url: str = "") -> None:
    """Log a failed callback attempt with safe URL diagnostics (no secrets)."""
    from urllib.parse import urlparse

    # Parse callback URL for safe diagnostics
    url_diag = {}
    if callback_url:
        try:
            parsed = urlparse(callback_url)
            url_diag["callback_url_configured"] = True
            url_diag["callback_scheme"] = parsed.scheme or ""
            url_diag["callback_host"] = parsed.hostname or ""
            url_diag["callback_port"] = parsed.port or (443 if parsed.scheme == "https" else 80)
            url_diag["callback_path"] = parsed.path or ""
        except Exception:
            url_diag["callback_url_configured"] = True
            url_diag["callback_host"] = "unknown"

    # Detect DNS resolution failures
    error_kind = ""
    hint = ""
    if "URLError" in error_msg and "Name or service not known" in error_msg:
        error_kind = "dns_resolution_failed"
        hint = (
            "Callback host could not be resolved from the QonQrete runtime. "
            "If host is 'obelisk', set OBELISK_QONQRETE_CALLBACK_BASE_URL in Obelisk "
            "to a URL reachable by QonQrete, e.g. https://o.wickednet.nl:443."
        )
    elif "URLError" in error_msg:
        error_kind = "url_error"
    elif "HTTPError" in error_msg:
        error_kind = "http_error"
    elif "Timeout" in error_msg or "timeout" in error_msg:
        error_kind = "timeout"

    event_data = {
        "run_id": os.path.basename(run_root),
        "attempt": attempt,
        "next_attempt": attempt + 1 if attempt < cfg.max_retries else None,
        "error": error_msg,
        "channel": origin.get("source_channel", "unknown"),
        **url_diag,
    }
    if error_kind:
        event_data["error_kind"] = error_kind
        event_data["hint"] = hint

    _emit_event(run_root, "completion_callback_retry", **event_data)


def _emit_event(run_root: str, event_type: str, **fields) -> None:
    """Emit an event to events.jsonl."""
    events_path = os.path.join(run_root, "events.jsonl")
    try:
        record = {
            "ts": time.time(),
            "run_id": os.path.basename(run_root),
            "type": event_type,
            **fields,
        }
        os.makedirs(os.path.dirname(events_path), exist_ok=True)
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Primary trigger — call from qontroller / ingest
# ---------------------------------------------------------------------------


def maybe_send_completion_callback(run_root: str) -> Optional[CallbackState]:
    """Trigger completion callback if the run is FULLY_DONE (legacy name).

    This is kept as a backwards-compatible wrapper. For new code, prefer
    maybe_send_terminal_callback().

    Returns the final CallbackState, or None if not configured/needed.
    """
    return maybe_send_terminal_callback(run_root)


def maybe_send_terminal_callback(run_root: str, force: bool = False) -> Optional[CallbackState]:
    """Trigger callback if the run is in any terminal state.

    Safe to call multiple times — exactly-once semantics apply.
    Set force=True to bypass failed cooldown and resend (admin use).

    Returns the final CallbackState, or None if not configured/needed.
    """
    # Quick check: does origin.json exist?
    if not os.path.isfile(os.path.join(run_root, "state", "origin.json")):
        return None

    # Check explicit disable
    env_enabled = os.environ.get("QONQRETE_COMPLETION_CALLBACK_ENABLED", "")
    if env_enabled.lower() in ("0", "false", "no"):
        return None

    # Check terminal
    if not is_run_terminal(run_root):
        return None

    # Check if callback already sent (skip unless force)
    existing = load_callback_state(run_root)
    if existing is not None and existing.state == "sent" and not force:
        return existing

    cfg = load_completion_callback_config()

    # Per-run callback URL auto-enables sending, even without global config.
    # If QONQRETE_COMPLETION_CALLBACK_ENABLED is explicitly false/0/no,
    # callbacks are globally disabled and we already returned None above.
    # Otherwise, if a per-run callback URL exists, enable sending.
    if not cfg.url:
        per_run_url = _resolve_per_run_callback_url(run_root)
        if per_run_url:
            # Construct a config with enabled=True so send_completion_callback
            # doesn't bail out before checking the per-run URL.
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="",  # Force per-run URL to be used, not empty global
                token=cfg.token,
                timeout_seconds=cfg.timeout_seconds,
                max_retries=cfg.max_retries,
                retry_base_seconds=cfg.retry_base_seconds,
                on_failure=cfg.on_failure,
                dashboard_url=cfg.dashboard_url,
            )

    return send_completion_callback(run_root, cfg, force=force)


# ---------------------------------------------------------------------------
# Recovery / reconciliation — safe background caller
# ---------------------------------------------------------------------------


def maybe_send_completion_callback_async(run_root: str) -> None:
    """Trigger callback in a background thread (non-blocking).

    Safe for use in dashboard / read-model / health-check paths where
    we don't want to block on HTTP calls.
    """
    def _bg():
        try:
            maybe_send_terminal_callback(run_root)
        except Exception:
            pass

    t = threading.Thread(target=_bg, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Backwards-compat (legacy import path)
# ---------------------------------------------------------------------------

def get_callback_config() -> Dict[str, Any]:
    """Return a sanitized dict of callback config (no token) for API responses."""
    cfg = load_completion_callback_config()
    return {
        "enabled": cfg.enabled,
        "configured": bool(cfg.url),
        "url_configured": bool(cfg.url),
        "timeout_seconds": cfg.timeout_seconds,
        "max_retries": cfg.max_retries,
        "on_failure": cfg.on_failure,
    }
