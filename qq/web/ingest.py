"""
QonQrete external run-trigger API — authenticated endpoint for creating
QonQrete runs from external sources (Obelisk transcription, API, etc.).

Receives structured run-trigger requests, saves the task prompt as a
timestamped markdown file, resolves repo/folder/default target behavior,
queues or starts a QonQrete run, and returns run metadata.

QonQrete remains the source of truth.  External sources only send
structured trigger requests.  briQsQope displays live dashboard state.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess
import shlex
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Trigger = Literal["qonqrete", "concrete"]
Mode = Literal["repo", "folder"]
QueueMode = Literal["queue", "reject_if_running", "latest_wins"]
TargetKind = Literal["default", "alias", "explicit"]

_VALID_TRIGGERS: set[str] = {"qonqrete", "concrete"}
_VALID_MODES: set[str] = {"repo", "folder"}


@dataclasses.dataclass
class IngestRequest:
    """Parsed + validated incoming request payload."""
    source: str
    raw_transcription: str
    trigger: str
    mode: str
    target: str
    task_text: str
    source_channel: Optional[str] = None
    sender_id: Optional[str] = None
    sender_display: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    transcription_id: Optional[str] = None
    sender_name: Optional[str] = None
    chat_title: Optional[str] = None
    task_title: Optional[str] = None
    reply_to: Optional[Dict[str, Any]] = None
    callback_url: Optional[str] = None
    callback_token: Optional[str] = None
    callback_token_ref: Optional[str] = None
    delimiter: Optional[str] = None
    received_at: Optional[str] = None
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    raw_transcription_synthesized: bool = False
    yolo: Optional[bool] = None
    force_retry: bool = False
    idempotency_key: str = ""

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "IngestRequest":
        task_text = data.get("task_text", "")
        raw_transcription = data.get("raw_transcription")
        raw_transcription_synthesized = False
        # Fallback: if raw_transcription is missing, use task_text
        if raw_transcription is None:
            raw_transcription = task_text if task_text else ""
            raw_transcription_synthesized = bool(raw_transcription)
        # YOLO: from payload, explicit None means "use default"
        yolo_val = data.get("yolo")
        if yolo_val is not None:
            yolo_val = bool(yolo_val)
        return cls(
            source=data.get("source") or "manual-api",
            raw_transcription=raw_transcription,
            trigger=data.get("trigger") or "qonqrete",
            mode=data.get("mode", ""),
            target=data.get("target", ""),
            task_text=task_text,
            source_channel=data.get("source_channel") or "api",
            sender_id=data.get("sender_id") or "manual",
            sender_display=data.get("sender_display"),
            chat_id=data.get("chat_id"),
            message_id=data.get("message_id"),
            transcription_id=data.get("transcription_id"),
            sender_name=data.get("sender_name"),
            chat_title=data.get("chat_title"),
            task_title=data.get("task_title"),
            reply_to=data.get("reply_to"),
            callback_url=data.get("callback_url"),
            callback_token=data.get("callback_token"),
            callback_token_ref=data.get("callback_token_ref"),
            delimiter=data.get("delimiter") or None,
            received_at=data.get("received_at") or data.get("timestamp"),
            metadata=data.get("metadata", {}),
            raw_transcription_synthesized=raw_transcription_synthesized,
            yolo=yolo_val,
            force_retry=bool(data.get("force_retry", False)),
            idempotency_key=data.get("idempotency_key", ""),
        )


@dataclasses.dataclass
class ResolvedTarget:
    """Structured result of target resolution, preserving kind for path checks."""
    path: str
    kind: TargetKind
    alias_name: Optional[str] = None


@dataclasses.dataclass
class RunTriggerResult:
    """Result of creating/queuing a run trigger."""
    ok: bool
    run_id: str
    task_path: str
    target_path: str
    mode: str = ""
    started: bool = False
    queued: bool = False
    duplicate: bool = False
    queue_position: int = 0
    command_preview: str = ""
    dashboard_url: str = ""
    message: str = ""
    error: str = ""
    resolved_target_kind: str = ""     # "default" | "alias" | "explicit"
    endpoint: str = ""                 # canonical endpoint path
    legacy_endpoint: bool = False      # True if request came via legacy alias
    run_root: str = ""                 # explicit run root (e.g. /x/qq/runs/<run_id>)
    events_path: str = ""              # events.jsonl path under run_root
    runner: str = ""                   # "local_exec" | "tmux"
    tmux_session: str = ""             # tmux session name (if tmux runner)
    attach_command: str = ""           # tmux attach command (if tmux runner)
    pid: Optional[int] = None          # pid (if local_exec runner)
    stdout_log: str = ""               # stdout log path (if local_exec)
    stderr_log: str = ""               # stderr log path (if local_exec)
    pointer_update_failed: bool = False  # True if current-run.json update failed post-launch
    duplicate_state: str = ""            # dedupe state when duplicate=True (e.g. "started")
    yolo: Optional[bool] = None          # YOLO mode enabled/disabled
    source: str = ""                      # origin source (e.g. "obelisk")
    source_channel: str = ""              # origin channel (e.g. "telegram", "signal")
    completion_callback_configured: bool = False  # True when completion callback URL is set
    queue_policy: str = ""                # queue policy that was applied
    linked_run_id: Optional[str] = None   # dashboard-linked run
    active_run_id: Optional[str] = None   # executor active run
    pending_run_id: Optional[str] = None  # pending run
    superseded_run_ids: List[str] = dataclasses.field(default_factory=list)  # superseded runs


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RunsAPIConfig:
    """Configuration for the QonQrete external runs API.

    This replaces the old Obelisk-specific ObeliskIngestConfig.
    Both old and new env var names, and both old and new YAML sections,
    are supported for backwards compatibility.

    Separate roots:
      - control_root: where current-run.json, runs.jsonl live
      - default_run_root: metadata runs root (legacy name, kept for compat)
      - runs_root: explicit metadata runs root (preferred over default_run_root)
      - default_target_root: where generated code/targets live
    """
    enabled: bool = True
    default_run_root: str = "~/Desktop/qq/qonqrete-runs"
    runs_root: str = ""                   # preferred over default_run_root for metadata
    default_target_root: str = ""         # code workspace parent for default targets
    task_dir: str = "~/.qonqrete/ingest/tasks"
    queue_mode: QueueMode = "latest_wins"
    allowed_target_roots: List[str] = dataclasses.field(default_factory=list)
    allowed_senders: List[str] = dataclasses.field(default_factory=list)
    aliases: Dict[str, str] = dataclasses.field(default_factory=dict)
    max_task_length: int = 64000
    dev_no_auth: bool = False
    runner: str = "local_exec"          # "local_exec" | "tmux"
    control_root: str = "/x/qq/control"  # where current-run.json lives
    dashboard_url: str = ""              # QONQRETE_PUBLIC_DASHBOARD_URL
    yolo_default: bool = True            # Default YOLO for API runs


# Backwards-compatible alias so existing imports don't break
ObeliskIngestConfig = RunsAPIConfig


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

# Precedence for env vars:
#   1. QONQRETE_RUNS_* (new, explicit)
#   2. QONQRETE_INGEST_* (old, deprecated)
# For YAML:
#   1. qonqrete_runs_api section
#   2. obelisk_ingest section (fallback)
#   3. hardcoded defaults

# Map of old env var names -> new
_OLD_TO_NEW_ENV = {
    "QONQRETE_DEFAULT_RUN_ROOT": "QONQRETE_RUNS_DEFAULT_ROOT",
    "QONQRETE_INGEST_TASK_DIR": "QONQRETE_RUNS_TASK_DIR",
    "QONQRETE_INGEST_QUEUE_MODE": "QONQRETE_RUNS_QUEUE_MODE",
    "QONQRETE_ALLOWED_TARGET_ROOTS": "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS",
    "QONQRETE_ALLOWED_INGEST_SENDERS": "QONQRETE_RUNS_ALLOWED_SENDERS",
    "QONQRETE_MAX_TASK_LENGTH": "QONQRETE_RUNS_MAX_TASK_LENGTH",
    "QONQRETE_DEV_NO_AUTH": "QONQRETE_RUNS_DEV_NO_AUTH",
}


def _get_env(key_new: str, key_old: str) -> Optional[str]:
    """Get env var value with precedence: new > old."""
    val = os.environ.get(key_new)
    if val is not None:
        return val
    return os.environ.get(key_old)


def load_obelisk_config_from_env() -> RunsAPIConfig:
    """Load runs API config with correct precedence.

    Precedence (highest wins):
      1. New env var names (QONQRETE_RUNS_*)
      2. Old env var names (QONQRETE_INGEST_* / QONQRETE_*)
      3. YAML config (qq.yaml)
      4. Hardcoded defaults

    Also reads from qq.yaml if available.  Old names are supported
    as fallbacks but new names win.
    """
    cfg = RunsAPIConfig()

    # Step 1: Load YAML (can override defaults)
    _try_load_yaml_config(cfg)

    # Step 2: Apply old env vars (override YAML)
    _apply_old_env_vars(cfg)

    # Step 3: Apply new env vars (override old env + YAML)
    _apply_new_env_vars(cfg)

    # Step 4: Apply aliases with new env overriding old env
    alias_prefixes = [("QONQRETE_INGEST_ALIAS_", False), ("QONQRETE_RUNS_ALIAS_", True)]
    seen_aliases: set[str] = set()
    for prefix, is_new in alias_prefixes:
        for k, v in os.environ.items():
            if k.startswith(prefix):
                alias_name = k[len(prefix):].lower()
                if not is_new and alias_name in seen_aliases:
                    continue  # New already set this alias
                cfg.aliases[alias_name] = v
                if is_new:
                    seen_aliases.add(alias_name)

    return cfg


def _apply_old_env_vars(cfg: RunsAPIConfig) -> None:
    """Apply old/deprecated env var names. Overrides YAML, overridden by new names."""
    # Default run root
    if os.environ.get("QONQRETE_DEFAULT_RUN_ROOT"):
        cfg.default_run_root = os.environ["QONQRETE_DEFAULT_RUN_ROOT"]

    # Task dir
    if os.environ.get("QONQRETE_INGEST_TASK_DIR"):
        cfg.task_dir = os.environ["QONQRETE_INGEST_TASK_DIR"]

    # Queue mode
    qm = os.environ.get("QONQRETE_INGEST_QUEUE_MODE", "")
    if qm in ("queue", "reject_if_running", "latest_wins"):
        cfg.queue_mode = qm  # type: ignore[assignment]

    # Allowed target roots
    if os.environ.get("QONQRETE_ALLOWED_TARGET_ROOTS"):
        cfg.allowed_target_roots = [
            r.strip() for r in os.environ["QONQRETE_ALLOWED_TARGET_ROOTS"].split(",") if r.strip()
        ]

    # Allowed senders
    if os.environ.get("QONQRETE_ALLOWED_INGEST_SENDERS"):
        cfg.allowed_senders = [
            s.strip() for s in os.environ["QONQRETE_ALLOWED_INGEST_SENDERS"].split(",") if s.strip()
        ]

    # Max task length
    if os.environ.get("QONQRETE_MAX_TASK_LENGTH"):
        try:
            cfg.max_task_length = int(os.environ["QONQRETE_MAX_TASK_LENGTH"])
        except ValueError:
            pass

    # Dev no auth
    if os.environ.get("QONQRETE_DEV_NO_AUTH", "").lower() in ("1", "true", "yes"):
        cfg.dev_no_auth = True


def _apply_new_env_vars(cfg: RunsAPIConfig) -> None:
    """Apply new env var names. These win over everything (old env + YAML)."""
    # Default run root
    if os.environ.get("QONQRETE_RUNS_DEFAULT_ROOT"):
        cfg.default_run_root = os.environ["QONQRETE_RUNS_DEFAULT_ROOT"]

    # Task dir
    if os.environ.get("QONQRETE_RUNS_TASK_DIR"):
        cfg.task_dir = os.environ["QONQRETE_RUNS_TASK_DIR"]

    # Queue mode
    qm = os.environ.get("QONQRETE_RUNS_QUEUE_MODE", "")
    if qm in ("queue", "reject_if_running", "latest_wins"):
        cfg.queue_mode = qm  # type: ignore[assignment]

    # Allowed target roots
    if os.environ.get("QONQRETE_RUNS_ALLOWED_TARGET_ROOTS"):
        cfg.allowed_target_roots = [
            r.strip() for r in os.environ["QONQRETE_RUNS_ALLOWED_TARGET_ROOTS"].split(",") if r.strip()
        ]

    # Allowed senders
    if os.environ.get("QONQRETE_RUNS_ALLOWED_SENDERS"):
        cfg.allowed_senders = [
            s.strip() for s in os.environ["QONQRETE_RUNS_ALLOWED_SENDERS"].split(",") if s.strip()
        ]

    # Max task length
    if os.environ.get("QONQRETE_RUNS_MAX_TASK_LENGTH"):
        try:
            cfg.max_task_length = int(os.environ["QONQRETE_RUNS_MAX_TASK_LENGTH"])
        except ValueError:
            pass

    # Dev no auth
    if os.environ.get("QONQRETE_RUNS_DEV_NO_AUTH", "").lower() in ("1", "true", "yes"):
        cfg.dev_no_auth = True

    # Runs root (preferred over default_run_root for metadata location)
    runs_root_env = os.environ.get("QONQRETE_RUNS_ROOT", "")
    if runs_root_env:
        cfg.runs_root = os.path.expanduser(runs_root_env)
        # When QONQRETE_RUNS_ROOT is set, it takes precedence over default_run_root
        # for the metadata runs location
        cfg.default_run_root = cfg.runs_root

    # Default target root (code workspace, separate from runs root)
    target_root_env = os.environ.get("QONQRETE_DEFAULT_TARGET_ROOT", "")
    if target_root_env:
        cfg.default_target_root = os.path.expanduser(target_root_env)

    # Runner config: QONQRETE_RUNS_RUNNER.
    runner_env = os.environ.get("QONQRETE_RUNS_RUNNER")
    if runner_env in ("local_exec", "tmux"):
        cfg.runner = runner_env

    # Control root for current-run.json pointer
    control_env = os.environ.get("QONQRETE_CONTROL_ROOT", "")
    if control_env:
        cfg.control_root = os.path.expanduser(control_env)

    # Public dashboard URL
    dashboard_env = os.environ.get("QONQRETE_PUBLIC_DASHBOARD_URL", "")
    if dashboard_env:
        cfg.dashboard_url = dashboard_env

    # YOLO defaults
    yolo_env = os.environ.get("QONQRETE_RUNS_YOLO_DEFAULT", "")
    if yolo_env in ("0", "false", "no"):
        cfg.yolo_default = False
    elif yolo_env in ("1", "true", "yes"):
        cfg.yolo_default = True

    # Also check QONQRETE_YOLO env var
    qyolo = os.environ.get("QONQRETE_YOLO", "")
    if qyolo in ("0", "false", "no"):
        cfg.yolo_default = False
    elif qyolo in ("1", "true", "yes"):
        cfg.yolo_default = True


def _try_load_yaml_config(cfg: RunsAPIConfig) -> None:
    """Attempt to load qonqrete_runs_api or obelisk_ingest section from qq.yaml."""
    try:
        import yaml
        _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        yaml_path = os.path.join(_repo_root, "config", "qq.yaml")
        if not os.path.isfile(yaml_path):
            return
        with open(yaml_path, "r") as f:
            raw = yaml.safe_load(f) or {}

        # Prefer new section, fall back to old
        section = raw.get("qonqrete_runs_api")
        if not isinstance(section, dict):
            section = raw.get("obelisk_ingest", {})
        if not isinstance(section, dict):
            return

        _apply_yaml_section(cfg, section)
    except Exception:
        pass


def _apply_yaml_section(cfg: RunsAPIConfig, section: dict) -> None:
    """Apply a YAML config section to a RunsAPIConfig.

    Env vars override YAML — YAML is only supplemental.
    """
    if section.get("enabled") is False:
        cfg.enabled = False
    if section.get("default_run_root"):
        cfg.default_run_root = section["default_run_root"]
    if section.get("task_dir"):
        cfg.task_dir = section["task_dir"]
    if section.get("queue_mode") in ("queue", "reject_if_running", "latest_wins"):
        cfg.queue_mode = section["queue_mode"]
    if isinstance(section.get("allowed_target_roots"), list):
        cfg.allowed_target_roots = section["allowed_target_roots"]
    if isinstance(section.get("allowed_senders"), list):
        cfg.allowed_senders = section["allowed_senders"]
    if isinstance(section.get("aliases"), dict):
        cfg.aliases.update(section["aliases"])
    if section.get("max_task_length"):
        cfg.max_task_length = int(section["max_task_length"])
    if section.get("dev_no_auth"):
        cfg.dev_no_auth = bool(section["dev_no_auth"])
    # Runner, control_root, dashboard_url from YAML (env overrides these in load_obelisk_config_from_env)
    if section.get("runner") in ("local_exec", "tmux"):
        cfg.runner = section["runner"]
    if section.get("control_root"):
        cfg.control_root = os.path.expanduser(section["control_root"])
    if section.get("runs_root"):
        cfg.runs_root = os.path.expanduser(section["runs_root"])
        cfg.default_run_root = cfg.runs_root
    if section.get("default_target_root"):
        cfg.default_target_root = os.path.expanduser(section["default_target_root"])
    if section.get("dashboard_url"):
        cfg.dashboard_url = section["dashboard_url"]
    # YOLO default from YAML
    if "yolo_default" in section:
        cfg.yolo_default = bool(section["yolo_default"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def check_auth(auth_header: Optional[str], config: RunsAPIConfig) -> bool:
    """Validate Bearer token.

    Prefers QONQRETE_RUNS_API_TOKEN, falls back to QONQRETE_INGEST_TOKEN.
    """
    if config.dev_no_auth:
        return True
    # Prefer new env var, fall back to old
    expected = os.environ.get("QONQRETE_RUNS_API_TOKEN") or os.environ.get("QONQRETE_INGEST_TOKEN", "")
    if not expected:
        return False
    if not auth_header:
        return False
    parts = auth_header.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    return parts[1] == expected


def check_runs_api_auth(auth_header: Optional[str], config: RunsAPIConfig) -> bool:
    """New canonical name for auth check. Delegates to check_auth for compat."""
    return check_auth(auth_header, config)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    def __init__(self, error: str, message: str, status: int = 400):
        self.error = error
        self.message = message
        self.status = status


def validate_request(req: IngestRequest, config: RunsAPIConfig) -> None:
    """Validate the run-trigger request. Raises ValidationError on failure."""
    # source is optional — defaults to "manual-api" via from_payload
    # raw_transcription is optional — falls back to task_text via from_payload
    # trigger is optional — defaults to "qonqrete" via from_payload
    if not req.mode:
        raise ValidationError("missing_mode", "mode is required")
    if not req.target:
        raise ValidationError("missing_target", "target is required")

    # task_text: reject missing, empty, and whitespace-only
    if not req.task_text:
        raise ValidationError("missing_task_text", "task_text is required and must not be empty")
    if req.task_text.strip() == "":
        raise ValidationError("empty_task_text", "task_text must not be empty or whitespace-only")

    if req.trigger not in _VALID_TRIGGERS:
        raise ValidationError("invalid_trigger", f"trigger must be one of: {', '.join(sorted(_VALID_TRIGGERS))}")
    if req.mode not in _VALID_MODES:
        raise ValidationError("invalid_mode", f"mode must be one of: {', '.join(sorted(_VALID_MODES))}")

    # Task text length
    if len(req.task_text) > config.max_task_length:
        raise ValidationError("task_too_long", f"task_text exceeds max length ({config.max_task_length})")

    # Sender allowlist: if configured AND sender_id present, check inclusion.
    # If allowlist is configured and sender_id is missing, reject.
    if config.allowed_senders:
        if not req.sender_id:
            raise ValidationError("missing_sender_id", "sender_id is required when sender allowlist is configured")
        if req.sender_id not in config.allowed_senders:
            raise ValidationError("sender_not_allowed", "sender_id not in allowed senders list", status=403)

    # Null bytes check in key fields
    for field_name in ("target", "task_text", "raw_transcription", "source"):
        val = getattr(req, field_name, "")
        if val and "\x00" in val:
            raise ValidationError("invalid_characters", f"{field_name} contains null bytes")

    # Also check IDs for null bytes
    for field_name in ("transcription_id", "message_id", "sender_id", "chat_id"):
        val = getattr(req, field_name, None)
        if val and "\x00" in val:
            raise ValidationError("invalid_characters", f"{field_name} contains null bytes")


# ---------------------------------------------------------------------------
# Resolve target path
# ---------------------------------------------------------------------------

def resolve_target(req: IngestRequest, config: RunsAPIConfig, ts: str) -> ResolvedTarget:
    """Resolve the target path from mode/target/timestamp.

    Returns a ResolvedTarget with path and kind metadata.

    'default' target resolves to <default_target_root>/<run_id> (code workspace).
    This is SEPARATE from the metadata run root (<runs_root>/<run_id>).
    """
    target = req.target.strip()

    # Normalize common misspellings: "defaults" -> "default"
    if target.lower() in ("default", "defaults"):
        # Use default_target_root for code files, NOT runs_root
        target_parent = config.default_target_root
        if not target_parent:
            # Fallback: check env vars first, then sensible defaults
            runs_root_env = os.environ.get("QONQRETE_RUNS_DEFAULT_ROOT", "")
            if runs_root_env:
                runs_root_env = os.path.expanduser(runs_root_env)
                # Use sibling directory: if runs_root is /x/qq/runs, target is /x/qq/targets
                parent = os.path.dirname(runs_root_env.rstrip("/"))
                target_parent = os.path.join(parent, "targets")
            elif os.path.isdir("/x/qq"):
                target_parent = "/x/qq/targets"
            elif os.path.isdir(os.path.expanduser("~/Desktop/qq")):
                target_parent = "~/Desktop/qq/qonqrete-targets"
            else:
                # Ultimate fallback: use a temp-safe default
                import tempfile
                target_parent = os.path.join(tempfile.gettempdir(), "qonqrete-targets")
        target_parent = os.path.expanduser(target_parent)
        run_id = _run_stamp_to_run_id(ts) if ts else "default"
        return ResolvedTarget(
            path=os.path.join(target_parent, run_id),
            kind="default",
        )

    # Check alias (case-insensitive)
    alias_lower = target.lower()
    if alias_lower in config.aliases:
        return ResolvedTarget(
            path=os.path.expanduser(config.aliases[alias_lower]),
            kind="alias",
            alias_name=alias_lower,
        )

    # Explicit path: expand ~, resolve absolute
    expanded = os.path.expanduser(target)
    if not os.path.isabs(expanded):
        raise ValidationError(
            "relative_path_not_allowed",
            "Relative paths are not allowed. Use absolute paths, aliases, or 'default'.",
            status=403,
        )
    return ResolvedTarget(
        path=os.path.abspath(expanded),
        kind="explicit",
    )


def check_path_allowed(resolved: ResolvedTarget, config: RunsAPIConfig) -> None:
    """Check if the resolved target path is allowed.

    Rules:
      - kind=default: always allowed
      - kind=alias:   always allowed (optionally also root-checked if roots configured)
      - kind=explicit: must be within allowed_target_roots if configured;
                       if no roots configured and not dev mode, reject
    """
    # Default is always allowed
    if resolved.kind == "default":
        return

    # Aliases are allowed by default; optionally check roots too
    if resolved.kind == "alias":
        # If allowed_target_roots is configured, also verify the alias resolves inside a root
        if config.allowed_target_roots:
            _check_in_roots(resolved.path, config.allowed_target_roots)
        return

    # Explicit path checks
    if resolved.kind == "explicit":
        if config.allowed_target_roots:
            _check_in_roots(resolved.path, config.allowed_target_roots)
            return
        # No roots configured and not dev mode -> reject
        if not config.dev_no_auth:
            raise ValidationError(
                "target_not_allowed",
                "Explicit target paths require QONQRETE_RUNS_ALLOWED_TARGET_ROOTS to be configured.",
                status=403,
            )
        return

    # Should not reach here
    raise ValidationError("target_not_allowed", "Could not verify target path", status=403)


def _check_in_roots(resolved_path: str, allowed_roots: List[str]) -> None:
    """Raise ValidationError if resolved_path is not inside any allowed root."""
    resolved_abs = os.path.abspath(resolved_path)
    for root in allowed_roots:
        root_exp = os.path.abspath(os.path.expanduser(root))
        try:
            Path(resolved_abs).relative_to(root_exp)
            return  # allowed
        except ValueError:
            continue

    raise ValidationError(
        "target_not_allowed",
        f"Target path '{resolved_path}' is not within allowed roots.",
        status=403,
    )


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

_DEDUPE_PATH = os.path.expanduser("~/.qonqrete/ingest/dedupe.jsonl")


def _ensure_dedupe_dir() -> None:
    os.makedirs(os.path.dirname(_DEDUPE_PATH), exist_ok=True)


def _compute_dedupe_key(req: IngestRequest) -> Optional[str]:
    """Compute a dedupe key for the request. Returns None if no stable key.

    Only dedupe when an external stable ID is provided.
    Manual API calls without transcription_id or message_id do NOT dedupe.
    """
    # Preference 1: source + transcription_id
    if req.transcription_id:
        return f"{req.source}:trans:{req.transcription_id}"
    # Preference 2: source + source_channel + message_id
    if req.source_channel and req.message_id:
        return f"{req.source}:{req.source_channel}:msg:{req.message_id}"
    # No external ID — do NOT dedupe. Return None so each call creates a new run.
    return None


def _is_dedupe_record_actually_active(entry: Dict[str, Any]) -> bool:
    """Check if a dedupe record represents a genuinely active run.

    Validates against:
    - runner.finished marker (declares finished)
    - tmux session existence (for tmux runner)
    - local_exec pid liveness (for local_exec runner)
    - current-run.json state

    Returns True only if there is real evidence the run is still running.
    Returns False (allowing retry) for stale records.
    """
    run_root = entry.get("run_root", "")
    runner = entry.get("runner", "")
    run_id = entry.get("run_id", "")

    # If no run_root, we can't validate — be conservative and trust the record
    if not run_root:
        return True

    # Check runner.finished marker — if it exists, the run is definitely done
    finished_path = os.path.join(run_root, "runner.finished")
    if os.path.isfile(finished_path):
        # Record stale state and allow retry
        try:
            record_dedupe(entry.get("dedupe_key", ""), run_id,
                          entry.get("task_path", ""),
                          entry.get("target_path", ""),
                          run_root=run_root,
                          events_path=entry.get("events_path", ""),
                          mode=entry.get("mode", ""),
                          runner=runner,
                          command_preview=entry.get("command_preview", ""),
                          pid=entry.get("pid") if runner == "local_exec" else None,
                          tmux_session=entry.get("tmux_session", "") if runner == "tmux" else "",
                          attach_command=entry.get("attach_command", "") if runner == "tmux" else "",
                          state="stale")
        except Exception:
            pass
        return False

    # For tmux runner: check tmux session existence
    if runner == "tmux" and run_id:
        tmux_session = entry.get("tmux_session") or f"qonqrete-{run_id}"
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", tmux_session],
                capture_output=True, timeout=2
            )
            if result.returncode != 0:
                # Session doesn't exist — stale
                try:
                    record_dedupe(entry.get("dedupe_key", ""), run_id,
                                  entry.get("task_path", ""),
                                  entry.get("target_path", ""),
                                  run_root=run_root,
                                  events_path=entry.get("events_path", ""),
                                  mode=entry.get("mode", ""),
                                  runner=runner,
                                  command_preview=entry.get("command_preview", ""),
                                  state="stale",
                                  tmux_session=tmux_session)
                except Exception:
                    pass
                return False
            # Session exists — genuinely active
            return True
        except FileNotFoundError:
            # tmux binary is missing entirely — only treat as active
            # if there is real in-memory evidence
            import qq.web.ingest as _mod2
            if _mod2._active_run and _mod2._active_run_id == run_id:
                return True
            # No in-memory evidence — stale
            try:
                record_dedupe(entry.get("dedupe_key", ""), run_id,
                              entry.get("task_path", ""),
                              entry.get("target_path", ""),
                              run_root=run_root,
                              events_path=entry.get("events_path", ""),
                              mode=entry.get("mode", ""),
                              runner=runner,
                              command_preview=entry.get("command_preview", ""),
                              state="stale",
                              tmux_session=tmux_session)
            except Exception:
                pass
            return False
        except Exception:
            # Subprocess error (timeout, etc.) — use evidence from
            # current-run.json and in-memory, do not block forever
            import qq.web.ingest as _mod2
            if _mod2._active_run and _mod2._active_run_id == run_id:
                return True
            # Check runner.finished one more time (may have appeared)
            if run_root:
                finished_path = os.path.join(run_root, "runner.finished")
                if os.path.isfile(finished_path):
                    return False
            # No evidence — stale
            try:
                record_dedupe(entry.get("dedupe_key", ""), run_id,
                              entry.get("task_path", ""),
                              entry.get("target_path", ""),
                              run_root=run_root,
                              events_path=entry.get("events_path", ""),
                              mode=entry.get("mode", ""),
                              runner=runner,
                              command_preview=entry.get("command_preview", ""),
                              state="stale",
                              tmux_session=tmux_session)
            except Exception:
                pass
            return False

    # For local_exec: check pid liveness
    if runner == "local_exec":
        pid = entry.get("pid")
        if pid:
            try:
                os.kill(int(pid), 0)  # Signal 0 just checks existence
                return True  # PID exists — genuinely active
            except (OSError, ProcessLookupError, ValueError):
                # PID doesn't exist — stale
                try:
                    record_dedupe(entry.get("dedupe_key", ""), run_id,
                                  entry.get("task_path", ""),
                                  entry.get("target_path", ""),
                                  run_root=run_root,
                                  events_path=entry.get("events_path", ""),
                                  mode=entry.get("mode", ""),
                                  runner=runner,
                                  command_preview=entry.get("command_preview", ""),
                                  pid=entry.get("pid"),
                                  state="stale")
                except Exception:
                    pass
                return False
        # No PID to check — no runner.finished either
        # Check if there's a matching in-memory active item
        # MUST verify _active_run is True AND _active_run_id matches
        # AND _active_item exists and has matching run_id.
        # An _active_run_id that matches with _active_run=False is stale.
        import qq.web.ingest as _mod2
        memory_active = (
            _mod2._active_run is True
            and _mod2._active_run_id is not None
            and _mod2._active_run_id == run_id
            and _mod2._active_item is not None
            and _mod2._active_item.get("run_id") == run_id
        )
        if not memory_active:
            # No real in-memory active state — stale
            try:
                record_dedupe(entry.get("dedupe_key", ""), run_id,
                              entry.get("task_path", ""),
                              entry.get("target_path", ""),
                              run_root=run_root,
                              events_path=entry.get("events_path", ""),
                              mode=entry.get("mode", ""),
                              runner=runner,
                              command_preview=entry.get("command_preview", ""),
                              pid=entry.get("pid"),
                              state="stale")
            except Exception:
                pass
            return False
        # Real in-memory active match — active
        return True

    # Unknown runner — be conservative
    return True

def check_duplicate(dedupe_key: str) -> Optional[Dict[str, Any]]:
    """Check if this dedupe key has been seen. Returns stored metadata if duplicate.

    Reads the entire dedupe file and keeps the LAST matching entry for each
    dedupe_key. Only the latest record determines the outcome — old states
    never override newer ones.

    Only returns duplicate for active/useful states that are still valid:
      - queued, starting, started, running
    Does NOT block retries for:
      - finished, launch_failed, pointer_failed, validation_failed,
        cancelled, rejected, failed_before_launch, stale

    Restart-safe: stale records (queued/started with no evidence of active
    process) are detected and don't block retries. The caller should also
    call _reconcile_active_run() before this to ensure in-memory state
    matches reality.
    """
    import qq.web.ingest as _mod
    _ensure_dedupe_dir()
    if not os.path.isfile(_DEDUPE_PATH):
        return None
    try:
        last_match = None
        with open(_DEDUPE_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("dedupe_key") == dedupe_key:
                        last_match = entry
                except json.JSONDecodeError:
                    continue
        if last_match is not None:
            state = last_match.get("state", "finished")
            if state not in ACTIVE_DEDUPE_STATES:
                return None  # finished/launch_failed/stale — allow retry

            # For queued state: only treat as duplicate if the run_id
            # is still in the in-memory queue.
            if state == "queued":
                with _queue_lock:
                    for q_item in _mod._queue:
                        if q_item.get("dedupe_key") == dedupe_key:
                            return last_match
                # Not in queue anymore — stale, append stale record
                try:
                    record_dedupe(dedupe_key, last_match.get("run_id", ""),
                                  last_match.get("task_path", ""),
                                  last_match.get("target_path", ""),
                                  run_root=last_match.get("run_root", ""),
                                  events_path=last_match.get("events_path", ""),
                                  mode=last_match.get("mode", ""),
                                  runner=last_match.get("runner", ""),
                                  command_preview=last_match.get("command_preview", ""),
                                  pid=last_match.get("pid"),
                                  tmux_session=last_match.get("tmux_session", ""),
                                  attach_command=last_match.get("attach_command", ""),
                                  state="stale")
                except Exception:
                    pass
                return None

            # For started/starting/running: check if there's real evidence
            # the run is still active.
            if not _is_dedupe_record_actually_active(last_match):
                # Run not actually active -> stale, allow retry
                return None

            # Real evidence of active run → duplicate
            return last_match
    except (OSError, IOError):
        pass
    return None


def record_dedupe(dedupe_key: str, run_id: str, task_path: str, target_path: str,
               state: str = "finished", run_root: str = "", events_path: str = "",
               mode: str = "", runner: str = "", command_preview: str = "",
               tmux_session: str = "", attach_command: str = "",
               pid: Optional[int] = None) -> None:
    """Record a dedupe key for future deduplication.

    Args:
        state: Lifecycle state — "queued", "starting", "started", "running",
               "finished", "launch_failed", "pointer_failed", "stale".
               Default "finished" for backward compatibility.
        run_root: Root directory of the run.
        events_path: Path to events.jsonl.
        mode: "repo" or "folder".
        runner: "local_exec" or "tmux".
        command_preview: Shell command preview.
        tmux_session: Tmux session name (when runner=tmux).
        attach_command: Tmux attach command (when runner=tmux).
        pid: Process ID (when runner=local_exec).
    """
    _ensure_dedupe_dir()
    entry = {
        "dedupe_key": dedupe_key,
        "run_id": run_id,
        "task_path": task_path,
        "target_path": target_path,
        "state": state,
        "run_root": run_root,
        "events_path": events_path,
        "mode": mode,
        "runner": runner,
        "command_preview": command_preview,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Include optional runner-specific fields
    if tmux_session:
        entry["tmux_session"] = tmux_session
    if attach_command:
        entry["attach_command"] = attach_command
    if pid is not None:
        entry["pid"] = pid
    try:
        with open(_DEDUPE_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, IOError):
        pass


# ---------------------------------------------------------------------------

def _record_item_dedupe(item: Dict[str, Any], state: str) -> None:
    """Record a dedupe entry from a queue/run item dict with full metadata.

    This is the canonical helper for all queue/watcher/reconcile paths
    where a full item dict is available. Ensures every dedupe record
    carries all available metadata fields.
    """
    dedupe_key = item.get("dedupe_key")
    if not dedupe_key:
        return
    runner_name = item.get("runner", "local_exec")
    record_dedupe(
        dedupe_key=dedupe_key,
        run_id=item.get("run_id", ""),
        task_path=item.get("task_path", ""),
        target_path=item.get("target_path", ""),
        run_root=item.get("run_root", ""),
        events_path=item.get("events_path", ""),
        mode=item.get("mode", ""),
        runner=runner_name,
        command_preview=item.get("command_preview", ""),
        state=state,
        pid=item.get("pid") if runner_name == "local_exec" else None,
        tmux_session=item.get("tmux_session", "") if runner_name == "tmux" else "",
        attach_command=item.get("attach_command", "") if runner_name == "tmux" else "",
    )


# Collision-safe timestamp + run ID
# ---------------------------------------------------------------------------


def _ingest_idempotency_path(control_root: str, kind: str = "idempotency") -> str:
    """Return the path to ingest-idempotency.jsonl or ingest-dead-letter.jsonl."""
    return os.path.join(control_root, f"ingest-{kind}.jsonl")


def _write_ingest_idempotency(req: "IngestRequest", dedupe_key: str,
                              run_id: str, run_root: str, events_path: str,
                              target_path: str, task_path: str,
                              command_preview: str, config: "RunsAPIConfig",
                              status: str = "started") -> None:
    """Write a durable idempotency entry to control_root/ingest-idempotency.jsonl."""
    control_root = config.control_root if config else ""
    if not control_root:
        return
    try:
        import hashlib
        os.makedirs(control_root, exist_ok=True)
        entry = {
            "idempotency_key": dedupe_key,
            "message_id": req.message_id,
            "transcription_id": req.transcription_id,
            "source": req.source,
            "source_channel": req.source_channel,
            "status": status,
            "command_text": req.task_text[:500],
            "normalized_command": req.task_text.strip().lower()[:500],
            "run_id": run_id,
            "run_root": run_root,
            "target_path": target_path,
            "task_path": task_path,
            "events_path": events_path,
            "command_preview": command_preview,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_at": "",
            "error": "",
            "force_retry_used": getattr(req, "force_retry", False),
        }
        path = _ingest_idempotency_path(control_root, "idempotency")
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, IOError, TypeError):
        pass


def _write_ingest_dead_letter(req: "IngestRequest", dedupe_key: str,
                              reason: str, config: "RunsAPIConfig") -> None:
    """Write a dead-letter entry to control_root/ingest-dead-letter.jsonl."""
    control_root = config.control_root if config else ""
    if not control_root:
        return
    try:
        os.makedirs(control_root, exist_ok=True)
        entry = {
            "idempotency_key": dedupe_key,
            "message_id": req.message_id,
            "transcription_id": req.transcription_id,
            "source": req.source,
            "source_channel": req.source_channel,
            "status": "dead_lettered",
            "reason": reason,
            "command_text": req.task_text[:500],
            "normalized_command": req.task_text.strip().lower()[:500],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path = _ingest_idempotency_path(control_root, "dead-letter")
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, IOError, TypeError):
        pass


def _reconcile_active_run(config: "RunsAPIConfig") -> bool:
    """Read current-run.json and verify if a run is actually still active.

    Returns True only when there is real evidence of a still-running job.
    Checks runner.finished marker, tmux session existence, and pid liveness.

    Call this before the queue/reject/start decision so that:
      - API restart during active tmux run doesn't allow accidental concurrency.
      - API restart after finished run does allow a new run.
    """
    import qq.web.ingest as _mod
    control_root = config.control_root
    pointer_path = os.path.join(control_root, "current-run.json")
    if not os.path.isfile(pointer_path):
        # No pointer means we have no evidence either way.
        # Keep the in-memory state as-is — tests may have set it explicitly.
        # In production, _active_run starts False and only becomes True
        # when a launch succeeds, so no pointer = no active run.
        return _mod._active_run

    try:
        with open(pointer_path, "r") as f:
            cr = json.load(f)
    except (json.JSONDecodeError, OSError):
        _clear_active_run_state(force=True)
        return False

    state = cr.get("state", "")
    run_root = cr.get("run_root", "")
    runner = cr.get("runner", "local_exec")
    run_id = cr.get("run_id", "")

    # Terminal states: definitely not active
    if state in ("launch_failed", "pointer_failed", "finished",
                 "cancelled", "aborted", "failed", "stale"):
        _clear_active_run_state(run_id=run_id)
        return False

    # Pending states (queued/accepted): trust in-memory evidence.
    # These represent queued items waiting for the active executor.
    if state in ("queued", "accepted"):
        if _mod._active_run and _mod._active_run_id:
            return True
        return bool(_mod._active_run)

    # Running states: need to verify
    if state in ("starting", "started", "running"):
        # Check for runner.finished marker
        if run_root:
            finished_path = os.path.join(run_root, "runner.finished")
            if os.path.isfile(finished_path):
                # Runner already finished — update pointer and report inactive
                try:
                    exit_code_path = os.path.join(run_root, "runner.exit_code")
                    exit_code = None
                    if os.path.isfile(exit_code_path):
                        with open(exit_code_path) as ef:
                            exit_code = int(ef.read().strip())
                    _update_current_run_pointer_guarded(
                        run_id=run_id, run_root=run_root,
                        events_path=cr.get("events_path", ""),
                        task_path=cr.get("task_path", ""),
                        target_path=cr.get("target_path", ""),
                        mode=cr.get("mode", ""),
                        source=cr.get("source", "manual-api"),
                        runner=runner, tmux_session=cr.get("tmux_session", ""),
                        created_at=cr.get("created_at", ""),
                        command_preview=cr.get("command_preview", ""),
                        control_root=control_root,
                        state="finished",
                        finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        exit_code=exit_code,
                    )
                except Exception:
                    pass
                _clear_active_run_state(run_id=run_id)
                return False

        # For tmux runner: check if tmux session exists.
        # Use tmux_session from current-run.json when available;
        # fall back to qonqrete-<run_id> for back-compat.
        if runner == "tmux" and run_id:
            tmux_session = cr.get("tmux_session") or f"qonqrete-{run_id}"
            try:
                result = subprocess.run(
                    ["tmux", "has-session", "-t", tmux_session],
                    capture_output=True, timeout=2
                )
                if result.returncode != 0:
                    # Session doesn't exist — run is stale
                    try:
                        _update_current_run_pointer_guarded(
                            run_id=run_id, run_root=run_root,
                            events_path=cr.get("events_path", ""),
                            task_path=cr.get("task_path", ""),
                            target_path=cr.get("target_path", ""),
                            mode=cr.get("mode", ""),
                            source=cr.get("source", "manual-api"),
                            runner=runner, tmux_session="",
                            created_at=cr.get("created_at", ""),
                            command_preview=cr.get("command_preview", ""),
                            control_root=control_root,
                            state="stale",
                        )
                    except Exception:
                        pass
                    _clear_active_run_state(run_id=run_id)
                    return False
                # Session exists → still active
                _mod._active_run = True
                return True
            except FileNotFoundError:
                # tmux binary is missing — only treat as active if there is
                # real in-memory evidence matching this run
                if _mod._active_run and _mod._active_run_id == run_id:
                    _mod._active_run = True
                    return True
                # No in-memory evidence — stale
                try:
                    _update_current_run_pointer_guarded(
                        run_id=run_id, run_root=run_root,
                        events_path=cr.get("events_path", ""),
                        task_path=cr.get("task_path", ""),
                        target_path=cr.get("target_path", ""),
                        mode=cr.get("mode", ""),
                        source=cr.get("source", "manual-api"),
                        runner=runner, tmux_session="",
                        created_at=cr.get("created_at", ""),
                        command_preview=cr.get("command_preview", ""),
                        control_root=control_root,
                        state="stale",
                    )
                except Exception:
                    pass
                _clear_active_run_state(run_id=run_id)
                return False
            except Exception:
                # Subprocess error — check runner.finished before blocking
                if run_root:
                    finished_path = os.path.join(run_root, "runner.finished")
                    if os.path.isfile(finished_path):
                        try:
                            exit_code_path = os.path.join(run_root, "runner.exit_code")
                            exit_code = None
                            if os.path.isfile(exit_code_path):
                                with open(exit_code_path) as ef:
                                    exit_code = int(ef.read().strip())
                            _update_current_run_pointer_guarded(
                                run_id=run_id, run_root=run_root,
                                events_path=cr.get("events_path", ""),
                                task_path=cr.get("task_path", ""),
                                target_path=cr.get("target_path", ""),
                                mode=cr.get("mode", ""),
                                source=cr.get("source", "manual-api"),
                                runner=runner, tmux_session="",
                                created_at=cr.get("created_at", ""),
                                command_preview=cr.get("command_preview", ""),
                                control_root=control_root,
                                state="finished",
                                finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                exit_code=exit_code,
                            )
                        except Exception:
                            pass
                        _clear_active_run_state(run_id=run_id)
                        return False
                # Have in-memory evidence? Trust it.
                if _mod._active_run and _mod._active_run_id == run_id:
                    _mod._active_run = True
                    return True
                # No evidence either way — stale
                try:
                    _update_current_run_pointer_guarded(
                        run_id=run_id, run_root=run_root,
                        events_path=cr.get("events_path", ""),
                        task_path=cr.get("task_path", ""),
                        target_path=cr.get("target_path", ""),
                        mode=cr.get("mode", ""),
                        source=cr.get("source", "manual-api"),
                        runner=runner, tmux_session="",
                        created_at=cr.get("created_at", ""),
                        command_preview=cr.get("command_preview", ""),
                        control_root=control_root,
                        state="stale",
                    )
                except Exception:
                    pass
                _clear_active_run_state(run_id=run_id)
                return False

        # For local_exec: check if the PID is still alive
        if runner == "local_exec":
            pid = cr.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)  # Signal 0 just checks existence
                    _mod._active_run = True
                    return True
                except (OSError, ProcessLookupError):
                    # PID doesn't exist → stale
                    try:
                        _update_current_run_pointer_guarded(
                            run_id=run_id, run_root=run_root,
                            events_path=cr.get("events_path", ""),
                            task_path=cr.get("task_path", ""),
                            target_path=cr.get("target_path", ""),
                            mode=cr.get("mode", ""),
                            source=cr.get("source", "manual-api"),
                            runner=runner, tmux_session="",
                            created_at=cr.get("created_at", ""),
                            command_preview=cr.get("command_preview", ""),
                            control_root=control_root,
                            state="stale",
                        )
                    except Exception:
                        pass
                    _clear_active_run_state(run_id=run_id)
                    return False

        # No PID to check — without runner.finished AND no PID,
        # this is a stale record. Only treat as active if ALL of:
        #   - _active_run is True
        #   - _active_run_id matches run_id
        #   - _active_item is not None
        #   - _active_item["run_id"] matches run_id
        # are satisfied. A stale _active_run_id alone cannot revive a run.
        if (not _mod._active_run
                or not _mod._active_run_id
                or _mod._active_run_id != run_id
                or _mod._active_item is None
                or _mod._active_item.get("run_id") != run_id):
            # No complete in-memory active match and no PID — stale
            try:
                _update_current_run_pointer_guarded(
                    run_id=run_id, run_root=run_root,
                    events_path=cr.get("events_path", ""),
                    task_path=cr.get("task_path", ""),
                    target_path=cr.get("target_path", ""),
                    mode=cr.get("mode", ""),
                    source=cr.get("source", "manual-api"),
                    runner=runner, tmux_session="",
                    created_at=cr.get("created_at", ""),
                    command_preview=cr.get("command_preview", ""),
                    control_root=control_root,
                    state="stale",
                )
            except Exception:
                pass
            _clear_active_run_state(run_id=run_id)
            return False
        # In-memory active item matches fully — assume active
        _mod._active_run = True
        return True

    # Unknown state: assume not active
    _clear_active_run_state(force=True)
    return False


def _write_origin_metadata(run_root: str, req: "IngestRequest", run_id: str,
                         target_path: str = "", events_path: str = "",
                         dashboard_url: str = "") -> None:
    """Persist origin metadata from the ingest request for completion callbacks.

    Writes run_root/state/origin.json with enough metadata for Obelisk
    to route the completion reply over the same channel (Telegram/Signal).
    Stores resolved target_path, events_path, and dashboard_url.
    """
    from qq.completion_callback import write_origin_metadata
    # Check for obelisk callback metadata in the request payload
    # This is typically injected by the API endpoint caller or by Obelisk
    obelisk_block = req.metadata.get("obelisk") if isinstance(req.metadata, dict) else None
    # Also check top-level obelisk in metadata
    if not obelisk_block:
        obelisk_block = req.metadata.get("obelisk") if isinstance(req.metadata, dict) else None

    origin_data = {
        "source": req.source,
        "source_channel": req.source_channel,
        "sender_id": req.sender_id,
        "sender_name": req.sender_name or req.sender_display or "",
        "sender_display": req.sender_display,
        "chat_id": req.chat_id,
        "chat_title": req.chat_title,
        "message_id": req.message_id,
        "transcription_id": req.transcription_id,
        "raw_transcription": req.raw_transcription,
        "trigger": req.trigger,
        "task_text": req.task_text,
        "task_title": req.task_title,
        "mode": req.mode,
        "target": req.target,
        "target_path": target_path,
        "events_path": events_path,
        "dashboard_url": dashboard_url,
        "run_root": run_root,
        "reply_to": req.reply_to,
        "callback_url": req.callback_url,
        "callback_token": req.callback_token or "",
        "callback_token_ref": req.callback_token_ref,
        "metadata": req.metadata,
        "obelisk": obelisk_block if obelisk_block else None,
    }
    # Remove None values so they don't serialise
    origin_data = {k: v for k, v in origin_data.items() if v is not None}
    write_origin_metadata(run_root, origin_data, run_id=run_id,
                          target_path=target_path, events_path=events_path,
                          dashboard_url=dashboard_url)

def _resolve_callback_configured(run_root: str = "") -> bool:
    '''Return True if completion callback is configured and enabled.

    Checks both global config and per-run callback URLs.'''
    try:
        from qq.completion_callback import get_run_aware_callback_config
        cfg = get_run_aware_callback_config(run_root)
        return cfg.get("configured", False) and cfg.get("enabled", False)
    except Exception:
        return bool(os.environ.get("QONQRETE_OBELISK_CALLBACK_URL", ""))


def _preflight_control_root(control_root: str) -> bool:
    """Verify the control root can be written to.

    Returns True if a temp file can be created and renamed atomically.
    Returns False if the directory is unwritable or the rename fails.
    This catches read-only filesystems, permission errors, and broken symlinks
    before any launch is attempted.
    """
    try:
        os.makedirs(control_root, exist_ok=True)
    except OSError:
        return False

    try:
        fd, tmp_path = tempfile.mkstemp(dir=control_root, prefix=".preflight.", suffix=".tmp")
    except OSError:
        return False

    try:
        os.close(fd)
        # Try the full write+rename cycle that _write_current_run_pointer uses
        json.dump({"preflight": True}, open(tmp_path, "w"))
        target = os.path.join(control_root, ".preflight-test")
        os.replace(tmp_path, target)
        try:
            os.unlink(target)
        except OSError:
            pass
        return True
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False



def _update_current_run_pointer_guarded(
    run_id: str,
    run_root: str,
    events_path: str,
    task_path: str,
    target_path: str,
    mode: str,
    source: str,
    runner: str,
    tmux_session: str,
    created_at: str,
    command_preview: str,
    control_root: str,
    state: str,
    pid: Optional[int] = None,
    attach_command: str = "",
    launch_error: str = "",
    finished_at: str = "",
    exit_code: Optional[int] = None,
    runner_finished_path: str = "",
    runner_exit_code_path: str = "",
    allow_switch_to_new_run: bool = False,
    yolo: Optional[bool] = None,
    final_status: Optional[str] = None,
) -> bool:
    """Atomically update current-run.json with explicit run switching protection.

    Rules:
    - Terminal states (finished, stale, launch_failed, etc.) can NEVER
      be overwritten by an active state (starting, started, running)
      for the same run_id.
    - "started" is only allowed if current state is "starting" or missing.
    - "finished" is allowed only if pointer still points to same run_id.
    - "stale" is allowed only if pointer still points to same run_id.
    - Old run must never overwrite a newer run pointer.
    - Switching to a DIFFERENT run_id from an active state is ONLY
      allowed when allow_switch_to_new_run=True. Without this,
      a stale old run delayed "started" write cannot overwrite
      a newer run (even a terminal one).
    - Switching from a terminal state to an active state is also
      only allowed when allow_switch_to_new_run=True.
    """
    with _CURRENT_RUN_POINTER_LOCK:
        current_path = os.path.join(control_root, "current-run.json")
        if os.path.isfile(current_path):
            try:
                with open(current_path, "r") as f:
                    current = json.load(f)
                current_state = current.get("state", "")
                current_run_id = current.get("run_id", "")
            except (json.JSONDecodeError, OSError):
                current_state = ""
                current_run_id = ""
        else:
            current_state = ""
            current_run_id = ""

        # If pointer points to the same run_id:
        if current_run_id == run_id:
            # Never regress from terminal to active state
            if current_state in TERMINAL_STATES and state not in TERMINAL_STATES:
                return True  # Silently skip — don't regress
            # "started" only allowed from "starting" or missing
            if state == "started" and current_state not in ("", "starting"):
                return True  # Silently skip
            # "finished" only allowed if pointer points to same run_id
            if state == "finished" and current_state in TERMINAL_STATES:
                return True  # Already terminal, skip
            # "stale" only allowed if pointer points to same run_id
            if state == "stale" and current_state in ("finished", "stale", "cancelled"):
                return True  # Already terminal, skip

        # If pointer points to a DIFFERENT run_id:
        if current_run_id and current_run_id != run_id:
            # Old run finishing — never overwrite a newer active run pointer
            if current_state in ACTIVE_STATES and state in TERMINAL_STATES:
                return True  # Silently skip old finish
            # Switching to a different active run is ONLY allowed
            # when allow_switch_to_new_run=True and the caller has
            # established that no other active run exists.
            if current_state in TERMINAL_STATES and state in ACTIVE_STATES:
                if allow_switch_to_new_run:
                    pass  # Allow — explicit new run starting
                else:
                    return True  # Reject — stale old run must not overwrite newer terminal pointer
            # Old run wants to write active state over an active one — block
            if current_state in ACTIVE_STATES and state in ACTIVE_STATES:
                if allow_switch_to_new_run:
                    pass  # Allow — explicit switch from stale active to new run
                else:
                    return True  # Block — different active run already exists

        # Write the pointer atomically
        return _write_current_run_pointer(
            run_id=run_id, run_root=run_root, events_path=events_path,
            task_path=task_path, target_path=target_path, mode=mode,
            source=source, runner=runner, tmux_session=tmux_session,
            created_at=created_at, command_preview=command_preview,
            control_root=control_root, state=state, pid=pid,
            attach_command=attach_command, launch_error=launch_error,
            finished_at=finished_at, exit_code=exit_code,
            runner_finished_path=runner_finished_path,
            runner_exit_code_path=runner_exit_code_path,
            yolo=yolo,
            final_status=final_status,
        )


def _write_current_run_pointer(
    run_id: str,
    run_root: str,
    events_path: str,
    task_path: str,
    target_path: str,
    mode: str,
    source: str,
    runner: str,
    tmux_session: str,
    created_at: str,
    command_preview: str,
    control_root: str,
    state: str = "started",
    pid: Optional[int] = None,
    attach_command: str = "",
    launch_error: str = "",
    finished_at: str = "",
    exit_code: Optional[int] = None,
    runner_finished_path: str = "",
    runner_exit_code_path: str = "",
    yolo: Optional[bool] = None,
    final_status: Optional[str] = None,
) -> bool:
    """Atomically write current-run.json pointer to the control root.

    Returns True on success, False on failure (never raises).
    The 'state' field tracks lifecycle: "starting", "started", "launch_failed", "finished".
    When state="launch_failed", launch_error provides the failure reason.
    When state="finished", finished_at and exit_code are included.

    IMPORTANT: Monotonic state protection is handled by
    _update_current_run_pointer_guarded(). This function is the raw
    write implementation and does not perform state checks.
    """

    pointer = {
        "run_id": run_id,
        "run_root": run_root,
        "events_path": events_path,
        "task_path": task_path,
        "target_path": target_path,
        "mode": mode,
        "source": source,
        "runner": runner,
        "tmux_session": tmux_session,
        "created_at": created_at,
        "command_preview": command_preview,
        "state": state,
    }
    # Add optional runner-specific fields
    if pid is not None:
        pointer["pid"] = pid
    if attach_command:
        pointer["attach_command"] = attach_command
    if yolo is not None:
        pointer["yolo"] = yolo
    if final_status is not None:
        pointer["final_status"] = final_status
    if launch_error:
        pointer["launch_error"] = launch_error
    if finished_at:
        pointer["finished_at"] = finished_at
    if exit_code is not None:
        pointer["exit_code"] = exit_code
    if state == "finished":
        pointer["runner_finished_path"] = runner_finished_path or os.path.join(run_root, "runner.finished")
        pointer["runner_exit_code_path"] = runner_exit_code_path or os.path.join(run_root, "runner.exit_code")

    # Filter out None values
    pointer = {k: v for k, v in pointer.items() if v is not None}

    # Atomic write: write to temp file, fsync, rename
    try:
        os.makedirs(control_root, exist_ok=True)
    except OSError:
        # Can't create control root (read-only fs, permissions, etc.)
        return False

    try:
        fd, tmp_path = tempfile.mkstemp(dir=control_root, prefix=".current-run.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(pointer, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False
        os.replace(tmp_path, os.path.join(control_root, "current-run.json"))
        return True
    except Exception:
        return False


def _generate_run_stamp() -> str:
    """Generate a collision-safe run stamp: YYYY-MM-DD_HH-MM-SS_<uuid_short>."""
    ts = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    # 8 hex chars from a UUID4 is 2^32 ~ 4B space, collision-safe enough
    suffix = uuid.uuid4().hex[:8]
    return f"{ts}_{suffix}"


def _run_stamp_to_run_id(stamp: str) -> str:
    """Convert stamp YYYY-MM-DD_HH-MM-SS_abc12345 -> YYYYMMDD-HHMMSS-abc12345."""
    # stamp: 2026-07-03_14-55-12_8f3a2c01
    # ->      20260703-145512-8f3a2c01
    parts = stamp.replace("_", "-").split("-")
    if len(parts) >= 7:  # YYYY MM DD HH MM SS suffix
        return f"{parts[0]}{parts[1]}{parts[2]}-{parts[3]}{parts[4]}{parts[5]}-{parts[6]}"
    return stamp.replace("_", "-")  # fallback


# ---------------------------------------------------------------------------
# Task file writing
# ---------------------------------------------------------------------------

def _safe_yaml_value(val: str) -> str:
    """Escape a value for YAML frontmatter to prevent injection.

    Values containing colons, quotes, newlines, etc. are JSON-encoded
    so they don't break the YAML structure.
    """
    if not val:
        return '""'
    # If value contains newlines, colons, or quotes, JSON-encode it
    if "\n" in val or ":" in val or '"' in val or val.startswith("#"):
        return json.dumps(val, ensure_ascii=False)
    return val


def write_task_files(
    req: IngestRequest,
    config: RunsAPIConfig,
    stamp: str,
    resolved: ResolvedTarget,
    dedupe_key: Optional[str] = None,
    command_args: Optional[List[str]] = None,
    endpoint_path: str = "/api/qonqrete/runs",
    legacy_endpoint: bool = False,
    request_ip: Optional[str] = None,
) -> str:
    """Write the task .md and .meta.json files. Returns task file path."""
    task_dir = os.path.expanduser(config.task_dir)
    os.makedirs(task_dir, exist_ok=True)

    task_filename = f"task_{stamp}.md"
    task_path = os.path.join(task_dir, task_filename)

    # Safe YAML frontmatter values
    safe_raw = _safe_yaml_value(req.raw_transcription)
    safe_source = _safe_yaml_value(req.source)

    # Build markdown content with safe YAML frontmatter
    md_parts = [
        "---",
        f"source: {safe_source}",
        f"source_channel: {req.source_channel or ''}",
        f"sender_id: {req.sender_id or ''}",
        f"sender_display: {req.sender_display or ''}",
        f"chat_id: {req.chat_id or ''}",
        f"message_id: {req.message_id or ''}",
        f"transcription_id: {req.transcription_id or ''}",
        f"received_at: {req.received_at or ''}",
        f"trigger: {req.trigger}",
        f"mode: {req.mode}",
        f"target: {req.target}",
        f"delimiter: {req.delimiter or ''}",
        f"raw_transcription: {safe_raw}",
        "---",
        "",
        req.task_text,
        "",
    ]
    with open(task_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_parts))

    # Construct command_preview for metadata
    cmd_preview = " ".join(command_args) if command_args else ""

    # Write metadata JSON
    meta_path = os.path.join(task_dir, f"task_{stamp}.meta.json")
    meta = {
        "original_payload": {
            "source": req.source,
            "source_channel": req.source_channel,
            "sender_id": req.sender_id,
            "sender_display": req.sender_display,
            "chat_id": req.chat_id,
            "message_id": req.message_id,
            "transcription_id": req.transcription_id,
            "raw_transcription": req.raw_transcription,
            "raw_transcription_synthesized": req.raw_transcription_synthesized,
            "trigger": req.trigger,
            "mode": req.mode,
            "target": req.target,
            "delimiter": req.delimiter,
            "task_text": req.task_text,
            "received_at": req.received_at,
            "metadata": req.metadata,
        },
        "resolved_target": resolved.path,
        "resolved_target_kind": resolved.kind,
        "resolved_target_alias": resolved.alias_name,
        "task_path": task_path,
        "command_args": command_args,
        "command_preview": cmd_preview,
        "dedupe_key": dedupe_key,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_ip": request_ip,
        "endpoint_path": endpoint_path,
        "legacy_endpoint": legacy_endpoint,
        "state": "accepted",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    return task_path


# ---------------------------------------------------------------------------
# Command generation
# ---------------------------------------------------------------------------

def generate_command(
    *,
    runner: str = "local_exec",
    task_path: str,
    target_path: str,
    mode: Mode,
    run_root: str = "",
    events_path: str = "",
    yolo: Optional[bool] = None,
) -> List[str]:
    """Generate argv list for running QonQrete. Never shell-concatenates.

    Two runners:
      - local_exec: plain `qq run --no-web --no-tui --run-root ...`
        Never uses qq-tui.
      - tmux: `qq-tui run --exit-when-done --qq-events <events_path> -- qq run ...`
        Includes the proper wrapper with events path.

    repo  mode: no --no-repo flag
    folder mode: --no-repo flag included
    """
    if runner == "tmux":
        # tmux runner: outer qq-tui with events path, inner qq run
        base = ["qq-tui", "run", "--exit-when-done"]
        if events_path:
            base.extend(["--qq-events", events_path])
        base.append("--")
        base.append("qq")
        base.append("run")
    else:
        # local_exec: plain qq run, no qq-tui
        base = ["qq", "run"]

    # Always include --no-web to prevent qq from starting its own web server
    base.append("--no-web")

    # Always include --no-tui for API runs
    base.append("--no-tui")

    # YOLO flag
    if yolo:
        base.append("--yolo")
    elif yolo is False:
        base.append("--no-yolo")

    # Always include explicit --run-root when provided
    if run_root:
        base.extend(["--run-root", run_root])

    if mode == "folder":
        return base + ["--no-repo", task_path, target_path]
    else:
        return base + [task_path, target_path]


def command_preview(args: List[str]) -> str:
    """Generate display-only command preview string."""
    import shlex as _shlex
    return " ".join(_shlex.quote(str(a)) for a in args)


def _state_artifact(run_root: str, name: str) -> str:
    """Return the canonical path for a state artifact, checking both
    state/<name> (canonical) and <run_root>/<name> (legacy).

    Returns the primary (canonical) path; callers should check both
    via os.path.isfile() at the primary path first, then the legacy.
    """
    primary = os.path.join(run_root, "state", name)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(run_root, name)
    if os.path.isfile(legacy):
        return legacy
    return primary


# ---------------------------------------------------------------------------
# Queue management
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tmux session metadata resolution
# ---------------------------------------------------------------------------

def _resolve_tmux_session(session_name: str, candidate_run_id: str, control_root: str = "") -> Dict[str, Any]:
    """Resolve a tmux session's QonQrete metadata via multiple sources.

    Checks (in order): tmux user options, tmux environment, tmux-sessions.jsonl,
    runs.jsonl, run directory scan, and pane capture fallback.

    Returns a dict with at minimum run_id, and optionally run_root, events_path,
    target_path, task_path, runner, yolo, state, link_status, selectable.
    """
    result: Dict[str, Any] = {
        "run_id": candidate_run_id,
        "state": "unknown",
        "runner": "tmux",
        "source": "tmux+resolved",
    }

    def _tmux_opt(opt_name: str) -> Optional[str]:
        try:
            r = subprocess.run(
                ["tmux", "show-options", "-v", "-t", session_name, opt_name],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        return None

    def _tmux_env(var_name: str) -> Optional[str]:
        try:
            r = subprocess.run(
                ["tmux", "show-environment", "-t", session_name, var_name],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().split("\n"):
                    if "=" in line and line.split("=", 1)[0] == var_name:
                        return line.split("=", 1)[1]
        except Exception:
            pass
        return None

    # 1. tmux user options (most reliable)
    resolved_run_root = _tmux_opt("@qonqrete_run_root")
    resolved_events = _tmux_opt("@qonqrete_events_path")
    resolved_target = _tmux_opt("@qonqrete_target_path")
    resolved_task = _tmux_opt("@qonqrete_task_path")
    resolved_run_id = _tmux_opt("@qonqrete_run_id")
    resolved_yolo = _tmux_opt("@qonqrete_yolo")
    resolved_managed = _tmux_opt("@qonqrete_managed")
    if resolved_managed:
        result["managed_tmux"] = resolved_managed == "1"
    if resolved_run_root:
        result["run_root"] = resolved_run_root
    if resolved_events:
        result["events_path"] = resolved_events
    if resolved_target:
        result["target_path"] = resolved_target
    if resolved_task:
        result["task_path"] = resolved_task
    if resolved_run_id:
        result["run_id"] = resolved_run_id
    if resolved_yolo is not None:
        # result["yolo"] = resolved_yolo.lower() == "true"
        from qq.web.status_resolver import parse_boolish
        parsed = parse_boolish(resolved_yolo)
        if parsed is not None:
            result["yolo"] = parsed

    # 2. tmux environment variables (fallback)
    if not result.get("run_root"):
        env_root = _tmux_env("QONQRETE_RUN_ROOT")
        if env_root:
            result["run_root"] = env_root
    if not result.get("events_path"):
        env_events = _tmux_env("QONQRETE_EVENTS_PATH")
        if env_events:
            result["events_path"] = env_events
    if not result.get("target_path"):
        env_target = _tmux_env("QONQRETE_TARGET_PATH")
        if env_target:
            result["target_path"] = env_target
    if not result.get("run_id") or result["run_id"] == candidate_run_id:
        env_id = _tmux_env("QONQRETE_RUN_ID")
        if env_id:
            result["run_id"] = env_id

    # 3. tmux-sessions.jsonl — last-record-wins
    if not result.get("run_root") and control_root:
        try:
            jsonl_path = os.path.join(control_root, "tmux-sessions.jsonl")
            if os.path.isfile(jsonl_path):
                last_tmux_match = None
                with open(jsonl_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("tmux_session") == session_name:
                            last_tmux_match = entry  # keep reading, last wins
                if last_tmux_match:
                    for k in ("run_root", "events_path", "target_path", "task_path", "run_id", "yolo"):
                        if last_tmux_match.get(k) and not result.get(k):
                            result[k] = last_tmux_match[k]
        except (OSError, IOError):
            pass

    # 4. runs.jsonl — last-record-wins (later lifecycle records override earlier)
    if not result.get("run_root") and control_root:
        try:
            runs_path = os.path.join(control_root, "runs.jsonl")
            if os.path.isfile(runs_path):
                last_match = None
                with open(runs_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if (entry.get("tmux_session") == session_name or
                            entry.get("run_id") == result.get("run_id", candidate_run_id)):
                            last_match = entry  # keep reading, last wins
                if last_match:
                    for k in ("run_root", "events_path", "target_path", "task_path", "yolo", "state"):
                        if last_match.get(k) and not result.get(k):
                            result[k] = last_match[k]
        except (OSError, IOError):
            pass

    # 5. Scan run roots directory for candidate run_id
    if not result.get("run_root"):
        run_id_to_find = result.get("run_id", candidate_run_id)
        for runs_root in _get_runs_roots(control_root):
            candidate = os.path.join(runs_root, run_id_to_find)
            if os.path.isdir(candidate):
                # Check for marker files
                has_marker = False
                for m in ("events.jsonl", "state/task.json", "state/plan.json",
                          "state/final.json", "task.md", "runner.exit_code",
                          "runner.finished"):
                    if os.path.isfile(os.path.join(candidate, m)):
                        has_marker = True
                        break
                if has_marker:
                    result["run_root"] = candidate
                    if not result.get("events_path"):
                        result["events_path"] = os.path.join(candidate, "events.jsonl")
                    break
                # Also try with "qq-" and "qonqrete-" prefixes removed
                for prefix in ("qonqrete-", "qq-"):
                    short_id = run_id_to_find
                    if run_id_to_find.startswith(prefix):
                        short_id = run_id_to_find[len(prefix):]
                    short_candidate = os.path.join(runs_root, short_id)
                    if os.path.isdir(short_candidate) and any(
                        os.path.isfile(os.path.join(short_candidate, m))
                        for m in ("events.jsonl", "state/task.json", "task.md", "runner.exit_code")):
                        result["run_root"] = short_candidate
                        if not result.get("events_path"):
                            result["events_path"] = os.path.join(short_candidate, "events.jsonl")
                        break

    # 6. Pane capture fallback (last resort)
    if not result.get("run_root"):
        try:
            pane_text = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", session_name, "-S", "-200"],
                capture_output=True, text=True, timeout=3,
            )
            if pane_text.returncode == 0:
                import re as _re
                # Look for --run-root <path> pattern
                m = _re.search(r'--run-root\s+(\S+)', pane_text.stdout)
                if m:
                    result["run_root"] = m.group(1)
                # Look for events.jsonl paths
                m2 = _re.search(r'(/\S*events\.jsonl)', pane_text.stdout)
                if m2 and not result.get("events_path"):
                    result["events_path"] = m2.group(1)
                # Look for target paths
                m3 = _re.search(r'(/x/qq/targets/\S+)', pane_text.stdout)
                if m3 and not result.get("target_path"):
                    result["target_path"] = m3.group(1)
        except Exception:
            pass

    # Determine link status and selectability
    if result.get("run_root") and result.get("events_path"):
        result["link_status"] = "resolved"
        result["selectable"] = True
    elif result.get("events_path"):
        result["link_status"] = "partial"
        result["selectable"] = True
    else:
        result["link_status"] = "tmux_only_unresolved"
        result["selectable"] = False

    # Validate existence
    if result.get("events_path"):
        result["events_exists"] = os.path.isfile(result["events_path"])
    return result


def _get_runs_roots(control_root: str = "") -> List[str]:
    """Return a list of candidate runs root directories to scan."""
    roots = []
    # Env var
    env_root = os.environ.get("QONQRETE_RUNS_ROOT", "")
    if env_root:
        roots.append(os.path.expanduser(env_root))
    # Config
    try:
        cfg = load_obelisk_config_from_env()
        if cfg.default_run_root:
            roots.append(cfg.default_run_root)
    except Exception:
        pass
    # Standard paths
    for p in ("/x/qq/runs", os.path.expanduser("~/Desktop/qq/qonqrete-runs")):
        if p not in roots:
            roots.append(p)
    return roots


# ---------------------------------------------------------------------------
# Failed run metadata
# ---------------------------------------------------------------------------

def _maybe_callback_launch_failure(item: Dict[str, Any]) -> None:
    """Attempt terminal callback for launch/pointer failures if origin.json exists.

    Does not block or raise — callback failure must never affect the run lifecycle.
    """
    run_root = item.get("run_root", "")
    if not run_root:
        return
    origin_path = os.path.join(run_root, "state", "origin.json")
    if not os.path.isfile(origin_path):
        return
    try:
        from qq.completion_callback import maybe_send_terminal_callback as _mstc
        _mstc(run_root)
    except Exception:
        pass


def _write_failed_run_file(item: Dict[str, Any], reason: str) -> None:
    """Write a runner.failed.json metadata file under run_root if it exists.

    Provides durable evidence of a failed launch or pointer write failure
    so operators can diagnose issues without checking in-memory state.
    """
    run_root = item.get("run_root", "")
    if not run_root:
        return
    try:
        os.makedirs(run_root, exist_ok=True)
    except OSError:
        return
    failed_data = {
        "run_id": item.get("run_id", ""),
        "task_path": item.get("task_path", ""),
        "target_path": item.get("target_path", ""),
        "mode": item.get("mode", ""),
        "source": item.get("source", ""),
        "runner": item.get("runner", "local_exec"),
        "reason": reason,
        "launch_error": item.get("launch_error", ""),
        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        failed_path = os.path.join(run_root, "runner.failed.json")
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(failed_data, f, indent=2, default=str)
    except (OSError, IOError):
        pass


# In-process queue state. Simple list-based queue.
# Using RLock to fix the potential deadlock where _mark_run_finished()
# holds the lock and calls _maybe_start_next() which tries to re-acquire.
_queue: List[Dict[str, Any]] = []
_queue_lock = threading.RLock()
_active_run: bool = False
_active_run_id: Optional[str] = None
_active_item: Optional[Dict[str, Any]] = None
_finished_run_ids: set = set()  # Exactly-once finish guard

# Canonical state sets -- imported from run_registry
from qq.web.run_registry import (
    ACTIVE_STATES,
    PENDING_STATES,
    TERMINAL_STATES,
    ACTIVE_DEDUPE_STATES,
    is_terminal_state,
    is_active_state,
    is_pending_state,
    normalize_state,
    resolve_run_timestamp,
    load_latest_run_records,
    load_latest_tmux_records,
    resolve_run_state,
    merge_run_sources,
    newest_run,
    atomic_write_json,
    atomic_read_json,
    append_jsonl,
    ControlLock,
    build_session_entry,
    sort_sessions_newest_first,
    reconcile_managed_runtime,
    _run_id_to_sort_key,
    _iso_to_sort_key,
)

_CURRENT_RUN_POINTER_LOCK = threading.RLock()



def _clear_active_run_state(run_id: Optional[str] = None, force: bool = False) -> None:
    """Clear active run state consistently.

    This is the single place where _active_run, _active_run_id, and _active_item
    are cleared. All code that previously set _active_run = False must use this.

    Args:
        run_id: If provided, only clear if _active_run_id matches.
        force: If True, clear unconditionally regardless of run_id match.
    """
    global _active_run, _active_run_id, _active_item
    with _queue_lock:
        if force:
            _active_run = False
            _active_run_id = None
            _active_item = None
        elif run_id is not None:
            if _active_run_id == run_id:
                _active_run = False
                _active_run_id = None
                _active_item = None
        else:
            _active_run = False
            _active_run_id = None
            _active_item = None


def _mark_run_active(item: Dict[str, Any]) -> None:
    """Mark a run as active with identity tracking.

    Sets both _active_run flag and _active_run_id so stale watchers
    from previous runs cannot clear a newer active run.
    """
    global _active_run, _active_run_id, _active_item
    with _queue_lock:
        _active_run = True
        _active_run_id = item.get("run_id")
        _active_item = item


def _append_to_runs_jsonl(control_root: str, entry: Dict[str, Any]) -> None:
    """Append a run lifecycle event to runs.jsonl atomically."""
    if not control_root:
        return
    try:
        os.makedirs(control_root, exist_ok=True)
    except OSError:
        return
    runs_path = os.path.join(control_root, "runs.jsonl")
    try:
        with open(runs_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def _mark_run_finished(run_id: str) -> None:
    """Mark a run as finished ONLY if it matches the active run ID.

    A stale watcher from run A calling _mark_run_finished("A") while
    run B is active will NOT clear the active state for run B.
    """
    global _active_run, _active_run_id, _active_item
    with _queue_lock:
        was_active = bool(_active_run_id and _active_run_id == run_id)
    if was_active:
        _clear_active_run_state(run_id=run_id)
        _maybe_start_next()


def _mark_runner_finished(
    item: Dict[str, Any],
    exit_code: Optional[int] = None,
    reason: str = "finished",
    state: str = "finished",
) -> None:
    """Centralized exactly-once finish handler.

    This is the single place where runner finish logic lives.
    Removes duplicated code from local_exec and tmux watchers.

    Args:
        item: The queue/run item dict with run_id, run_root, etc.
        exit_code: Numeric exit code if available.
        reason: Human-readable reason string.
        state: Pointer state to write ("finished", "stale").
    """
    run_id = item.get("run_id", "")
    run_root_val = item.get("run_root", "")
    runner_name = item.get("runner", "local_exec")

    # Exactly-once guard: only process each run_id once
    with _queue_lock:
        if run_id and run_id in _finished_run_ids:
            return
        if run_id:
            _finished_run_ids.add(run_id)

    # Write runner.finished marker if possible
    if run_root_val:
        finished_path = os.path.join(run_root_val, "runner.finished")
        try:
            with open(finished_path, "w") as ff:
                ff.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        except OSError:
            pass

    # Write runner.exit_code if missing
    if run_root_val and exit_code is not None:
        exit_code_path = os.path.join(run_root_val, "runner.exit_code")
        if not os.path.isfile(exit_code_path):
            try:
                with open(exit_code_path, "w") as ef:
                    ef.write(str(exit_code))
            except OSError:
                pass

    # Resolve final status if possible
    final_status_val = None
    if run_root_val:
        try:
            from qq.web.status_resolver import resolve_final_status as _rfs
            final_status_val = _rfs(run_root_val)
        except Exception:
            pass

    # Build pointer fields with full metadata
    pointer_fields = {
        "run_id": run_id,
        "run_root": run_root_val,
        "events_path": item.get("events_path", ""),
        "task_path": item.get("task_path", ""),
        "target_path": item.get("target_path", ""),
        "mode": item.get("mode", ""),
        "source": item.get("source", "manual-api"),
        "runner": runner_name,
        "tmux_session": item.get("tmux_session", ""),
        "created_at": item.get("created_at", ""),
        "command_preview": item.get("command_preview", ""),
        "control_root": item.get("control_root", "/x/qq/control"),
        "state": state,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "exit_code": exit_code,
        "yolo": item.get("yolo"),
        "final_status": final_status_val,
        "runner_finished_path": os.path.join(run_root_val, "runner.finished") if run_root_val else "",
        "runner_exit_code_path": os.path.join(run_root_val, "runner.exit_code") if run_root_val else "",
    }
    if runner_name == "local_exec":
        pointer_fields["pid"] = item.get("pid")
    elif runner_name == "tmux":
        pointer_fields["tmux_session"] = item.get("tmux_session", "")
        pointer_fields["attach_command"] = item.get("attach_command", "")

    # Update current-run.json only if it still points to this run_id
    _update_current_run_pointer_guarded(**pointer_fields)

    # Append to runs.jsonl history
    control_root = item.get("control_root", "/x/qq/control")
    history_entry = {
        "run_id": run_id,
        "control_root": control_root,
        "run_root": run_root_val,
        "target_path": item.get("target_path", ""),
        "task_path": item.get("task_path", ""),
        "events_path": item.get("events_path", ""),
        "state": state,
        "runner": runner_name,
        "yolo": item.get("yolo"),
        "tmux_session": item.get("tmux_session", ""),
        "attach_command": item.get("attach_command", ""),
        "pid": item.get("pid") if runner_name == "local_exec" else None,
        "command_preview": item.get("command_preview", ""),
        "created_at": item.get("created_at", ""),
        "started_at": item.get("created_at", ""),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "exit_code": exit_code,
    }
    _append_to_runs_jsonl(control_root, history_entry)

    # Record dedupe with full metadata via canonical helper
    _record_item_dedupe(item, state)

    # Clear active state only if this is the active run
    _mark_run_finished(run_id)

    # Terminalize active-run.json if this was the executor run
    control_root = item.get("control_root", "/x/qq/control")
    active_path = os.path.join(control_root, "active-run.json")
    if os.path.isfile(active_path):
        try:
            with open(active_path, "r") as af:
                ar = json.load(af)
            if ar.get("run_id") == run_id:
                # Update to terminal state
                ar["state"] = state
                ar["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                ar["exit_code"] = exit_code
                atomic_write_json(control_root, "active-run.json", ar)
            else:
                # Different run is active — remove this old active-run.json
                os.unlink(active_path)
        except (json.JSONDecodeError, OSError):
            try:
                os.unlink(active_path)
            except OSError:
                pass

    # Remove runner.lock when the run becomes terminal
    if run_root_val:
        lock_path = os.path.join(run_root_val, "runner.lock")
        if os.path.isfile(lock_path):
            try:
                os.unlink(lock_path)
            except OSError:
                pass

    # Attempt terminal callback recovery for failure states
    # This covers runs that finished outside normal qontroller success flow
    should_recover_callback = (
        run_root_val
        and (
            state in ("failed", "failed_early", "finished_incomplete",
                      "launch_failed", "stale")
            or (exit_code is not None and exit_code != 0)
        )
    )
    if should_recover_callback:
        try:
            from qq.completion_callback import maybe_send_terminal_callback as _mstc
            _mstc(run_root_val)
        except Exception:
            pass


def _clear_stale_queued_runs() -> None:
    """Clear all queued run items that are stale (already finished or launched).

    Scans the in-memory queue and removes any item whose run_root already has
    runner.finished, runner.exit_code, or runner.lock markers.

    Called before inserting a new manual/API run into the queue to prevent
    stale entries from auto-starting when a new run finishes.
    """
    global _queue
    with _queue_lock:
        kept = []
        removed_count = 0
        for item in _queue:
            run_root = item.get("run_root", "")
            run_id = item.get("run_id", "")
            if run_root:
                finished_path = os.path.join(run_root, "runner.finished")
                lock_path = os.path.join(run_root, "runner.lock")
                exit_code_path = os.path.join(run_root, "runner.exit_code")
                if os.path.isfile(finished_path) or os.path.isfile(lock_path):
                    # Mark as stale in dedupe
                    _record_item_dedupe(item, "stale")
                    removed_count += 1
                    # Also check for tmux session still running
                    if os.path.isfile(lock_path):
                        try:
                            lock_age = time.time() - os.path.getmtime(lock_path)
                            if lock_age > 60:
                                # Stale lock, but also check tmux
                                pass
                        except Exception:
                            pass
                    continue
                # Check events for terminal state
                events_path = os.path.join(run_root, "events.jsonl")
                if os.path.isfile(events_path):
                    try:
                        from qq.web.status_resolver import resolve_final_status
                        status = resolve_final_status(run_root)
                        if status and status.upper() in ("FULLY_DONE", "DONE", "FAILED", "ABORTED"):
                            _record_item_dedupe(item, "stale")
                            removed_count += 1
                            continue
                    except Exception:
                        pass
            kept.append(item)
        if removed_count > 0:
            _queue = kept

def _maybe_start_next() -> None:
    """Pop and launch the single newest pending item.

    Under latest_wins, collapses the queue to the single newest item,
    supersedes all older items, and launches only the newest.

    Under legacy FIFO "queue" mode, pops from the front.
    """
    global _active_run

    while True:
        with _queue_lock:
            if _active_run:
                return
            if not _queue:
                return

            # Determine if any item has latest_wins policy
            has_latest = any(
                qi.get("queue_policy") == "latest_wins" for qi in _queue
            )

            if has_latest:
                # latest_wins: find the single newest item
                best_idx = 0
                best_ts = 0.0
                for i, qi in enumerate(_queue):
                    ts = resolve_run_timestamp(qi)
                    if ts <= 0:
                        ts = _run_id_to_sort_key(qi.get("run_id", ""))
                    if ts > best_ts:
                        best_ts = ts
                        best_idx = i
                # Pop the newest item
                next_item = _queue.pop(best_idx)
                # Supersede all remaining items
                superseded_now = []
                while _queue:
                    superseded_now.append(_queue.pop(0))
                next_run_id = next_item.get("run_id", "")
                control_root = next_item.get("control_root", "/x/qq/control")
                for si in superseded_now:
                    s_rid = si.get("run_id", "")
                    if s_rid and s_rid != next_run_id:
                        _append_to_runs_jsonl(control_root, {
                            "run_id": s_rid,
                            "control_root": control_root,
                            "run_root": si.get("run_root", ""),
                            "target_path": si.get("target_path", ""),
                            "task_path": si.get("task_path", ""),
                            "events_path": si.get("events_path", ""),
                            "state": "superseded",
                            "runner": si.get("runner", ""),
                            "yolo": si.get("yolo"),
                            "command_preview": si.get("command_preview", ""),
                            "created_at": si.get("created_at", ""),
                            "superseded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "superseded_by_run_id": next_run_id,
                            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        })
                        _record_item_dedupe(si, "superseded")
                        s_run_root = si.get("run_root", "")
                        if s_run_root:
                            _write_failed_run_file(si, "superseded_by_newer_request")
                # Remove pending-run.json since we're about to launch
                pending_path = os.path.join(control_root, "pending-run.json")
                if os.path.isfile(pending_path):
                    try:
                        os.unlink(pending_path)
                    except OSError:
                        pass
            else:
                # Legacy FIFO queue mode
                next_item = _queue.pop(0)

        # Write pointer in "starting" state BEFORE launch.
        # If this write fails, DO NOT launch — the dashboard cannot follow
        # an orphan run.
        created_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        pointer_ok = _update_current_run_pointer_guarded(
            run_id=next_item.get("run_id", ""),
            run_root=next_item.get("run_root", ""),
            events_path=next_item.get("events_path", ""),
            task_path=next_item.get("task_path", ""),
            target_path=next_item.get("target_path", ""),
            mode=next_item.get("mode", ""),
            source=next_item.get("source", "manual-api"),
            runner=next_item.get("runner", "local_exec"),
            tmux_session="",
            created_at=next_item.get("created_at", created_at_iso),
            command_preview=next_item.get("command_preview", ""),
            control_root=next_item.get("control_root", "/x/qq/control"),
            state="starting",
            allow_switch_to_new_run=True,
            yolo=next_item.get("yolo"),
        )
        if not pointer_ok:
            # Cannot write pointer — mark the item and continue to next.
            next_item["launch_ok"] = False
            next_item["launch_error"] = "current_run_pointer_write_failed"
            # Update dedupe state to pointer_failed so retries are not blocked
            _record_item_dedupe(next_item, "pointer_failed")
            # Write a failed-run metadata file if run_root exists
            _write_failed_run_file(next_item, "current_run_pointer_write_failed")
            # Attempt terminal callback if origin metadata exists
            _maybe_callback_launch_failure(next_item)
            # continue to next item in loop
            continue

        # Launch outside the lock
        success = _do_launch(next_item)

        if success and next_item.get("launch_ok") is True:
            # Launch succeeded — update to "started" with runner details
            tmux_session = next_item.get("tmux_session", "")
            attach_cmd = next_item.get("attach_command", "")
            runner_pid = next_item.get("pid", None)
            runner_name = next_item.get("runner", "local_exec")
            _update_current_run_pointer_guarded(
                run_id=next_item.get("run_id", ""),
                run_root=next_item.get("run_root", ""),
                events_path=next_item.get("events_path", ""),
                task_path=next_item.get("task_path", ""),
                target_path=next_item.get("target_path", ""),
                mode=next_item.get("mode", ""),
                source=next_item.get("source", "manual-api"),
                runner=runner_name,
                tmux_session=tmux_session,
                created_at=next_item.get("created_at", created_at_iso),
                command_preview=next_item.get("command_preview", ""),
                control_root=next_item.get("control_root", "/x/qq/control"),
                state="started",
                pid=runner_pid if runner_name == "local_exec" else None,
                attach_command=attach_cmd if runner_name == "tmux" else "",
            yolo=next_item.get("yolo"),
            )
            # Update dedupe state to started when launch succeeds from queue
            dedupe_key = next_item.get("dedupe_key")
            if dedupe_key:
                record_dedupe(dedupe_key, next_item.get("run_id", ""),
                              next_item.get("task_path", ""),
                              next_item.get("target_path", ""),
                              run_root=next_item.get("run_root", ""),
                              events_path=next_item.get("events_path", ""),
                              mode=next_item.get("mode", ""),
                              runner=next_item.get("runner", ""),
                              command_preview=next_item.get("command_preview", ""),
                              state="started")
            # Success: exit loop, run is active
            return

        # Launch failed — update to "launch_failed"
        launch_error = next_item.get("launch_error", "launch_failed")
        _update_current_run_pointer_guarded(
            run_id=next_item.get("run_id", ""),
            run_root=next_item.get("run_root", ""),
            events_path=next_item.get("events_path", ""),
            task_path=next_item.get("task_path", ""),
            target_path=next_item.get("target_path", ""),
            mode=next_item.get("mode", ""),
            source=next_item.get("source", "manual-api"),
            runner=next_item.get("runner", "local_exec"),
            tmux_session="",
            created_at=next_item.get("created_at", created_at_iso),
            command_preview=next_item.get("command_preview", ""),
            control_root=next_item.get("control_root", "/x/qq/control"),
            state="launch_failed",
            launch_error=launch_error,
        )
        # Update dedupe state to launch_failed so retries are not poisoned
        _record_item_dedupe(next_item, "launch_failed")
        # Write failed-run metadata file
        _write_failed_run_file(next_item, launch_error)
        # Attempt terminal callback if origin metadata exists
        _maybe_callback_launch_failure(next_item)
        # continue loop to try next queued item


def _has_qonqrete_runner_binary() -> bool:
    """Check if qq-tui or qq binary is available on PATH."""
    import shutil as _shutil_bin
    return bool(_shutil_bin.which("qq-tui") or _shutil_bin.which("qq"))


def _do_launch_tmux(item: Dict[str, Any]) -> bool:
    """Launch a QonQrete run inside a tmux session.

    Returns True if tmux session was created, False otherwise.
    Sets item["launch_ok"] appropriately.
    """
    args = item["args"]
    run_id = item["run_id"]
    command_preview = item.get("command_preview", " ".join(args))
    control_root = item.get("control_root", "/x/qq/control")

    # Sanitize session name
    session_name = f"qonqrete-{run_id}"
    # Replace chars that could break tmux
    session_name = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name)

    # Build the shell command to run inside tmux
    # Use shlex.quote to safely quote all paths
    try:
        import shlex as _shlex
    except ImportError:
        item["launch_ok"] = False
        item["launch_error"] = "shlex_import_failed"
        return False

    repo_root = os.environ.get("QQ_SRC", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    # Build command as quoted string for tmux send-keys / new-session
    quoted_args = " ".join(_shlex.quote(a) for a in args)

    # Use qq-tui run --exit-when-done so that when the QonQrete command exits,
    # we can capture the exit code and write marker files. The tmux pane stays
    # we can capture the exit code and write marker files before the shell exits.
    run_root_quoted = _shlex.quote(item.get("run_root", ""))
    final_json_quoted = _shlex.quote(os.path.join(item.get("run_root", ""), "state", "final.json"))
    runner_exit_code_quoted = _shlex.quote(os.path.join(item.get("run_root", ""), "runner.exit_code"))
    runner_finished_quoted = _shlex.quote(os.path.join(item.get("run_root", ""), "runner.finished"))
    # Build the inner shell command using shell variables for proper
    # exit-code capture. Use single-quoted Python strings to avoid
    # f-string double-quote nesting issues with the $QQ_EXIT variable.
    # Build the inner shell command using the canonical Python status resolver.
    # This is more robust than inline Python JSON parsing, handles filesystem
    # flush delays, and prints plain text (no broken ANSI escapes).
    _repo_root_py = _shlex.quote(repo_root)
    _run_root_py = _shlex.quote(item.get("run_root", ""))
    inner_cmd = (
        "cd " + _shlex.quote(repo_root) + " && "
        "export TTY=true && "
        + quoted_args + "; "
        "QQ_EXIT=$?; "
        "printf '%s\n' \"$QQ_EXIT\" > " + runner_exit_code_quoted + "; "
        "date -Is > " + runner_finished_quoted + "; "
        "printf '\033[0m'; "
        "echo; echo; "
        "FINAL_STATUS=''; "
        "for _retry in $(seq 1 10); do "
        "  sleep 0.5; "
        "  FINAL_STATUS=$(python3 -c \""
        "import sys; sys.path.insert(0, '" + _repo_root_py + "'); "
        "from qq.web.status_resolver import resolve_final_status; "
        "status = resolve_final_status('" + _run_root_py + "'); "
        "print(status or '')\" 2>/dev/null); "
        "  if [ \"$FINAL_STATUS\" = \"FULLY_DONE\" ]; then break; fi; "
        "done; "
        "if [ \"$QQ_EXIT\" = \"0\" ] && [ \"$FINAL_STATUS\" = \"FULLY_DONE\" ]; then "
        "echo \"QonQrete run finished with status: FULLY_DONE. Session: " + session_name + "\"; "
        "elif [ \"$FINAL_STATUS\" != \"\" ]; then "
        "echo \"QonQrete run finished with status: $FINAL_STATUS. Session: " + session_name + "\" \"(exit code $QQ_EXIT)\"; "
        "else "
        "echo \"QonQrete run finished with exit code $QQ_EXIT. Session: " + session_name + "\"; "
        "fi; "
        "exit \"$QQ_EXIT\""
    )

    # Per-run atomic lock to prevent double-launch
    run_root_val_lock = item.get("run_root", "")
    lock_path = os.path.join(run_root_val_lock, "runner.lock") if run_root_val_lock else ""
    if lock_path:
        try:
            os.makedirs(run_root_val_lock, exist_ok=True)
            # Check for existing lock file
            if os.path.isfile(lock_path):
                # Check if the lock is stale (older than 30 seconds with no tmux session)
                try:
                    lock_age = time.time() - os.path.getmtime(lock_path)
                    if lock_age < 30:
                        # Check if there's already a running tmux session for this run
                        existing_tmux = subprocess.run(
                            ["tmux", "has-session", "-t", session_name],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        if existing_tmux.returncode == 0:
                            item["launch_ok"] = False
                            item["launch_error"] = "already_running"
                            return False
                except Exception:
                    pass
            # Create/update lock file atomically
            with open(lock_path, "w") as lf:
                lf.write(json.dumps({
                    "run_id": run_id,
                    "session": session_name,
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }))
        except OSError:
            pass

    # Preflight: validate tmux is installed
    try:
        subprocess.run(
            ["tmux", "-V"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except FileNotFoundError:
        item["launch_ok"] = False
        item["launch_error"] = "tmux_not_installed"
        return False
    except Exception:
        item["launch_ok"] = False
        item["launch_error"] = "tmux_preflight_failed"
        return False

    # Validate qq-tui exists (check with which or direct check)
    if not _has_qonqrete_runner_binary():
        item["launch_ok"] = False
        item["launch_error"] = "qq_binary_not_found"
        return False

    # Check for existing session — do NOT kill it silently
    try:
        has_session = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if has_session.returncode == 0:
            item["launch_ok"] = False
            item["launch_error"] = "tmux_session_exists"
            return False
    except FileNotFoundError:
        item["launch_ok"] = False
        item["launch_error"] = "tmux_not_installed"
        return False
    except Exception:
        pass

    try:
        # Create new detached session running bash
        proc_create = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "bash"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        if proc_create.returncode != 0:
            item["launch_ok"] = False
            item["launch_error"] = "tmux_create_failed"
            return False

        # Send the command to the session — check return code (fix #5)
        proc_send = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, inner_cmd, "Enter"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        if proc_send.returncode != 0:
            # send-keys failed — clean up the just-created empty tmux session
            try:
                subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                pass
            item["launch_ok"] = False
            item["launch_error"] = "tmux_send_keys_failed"
            return False

        # Store tmux session name in the item for response
        item["launch_ok"] = True
        item["tmux_session"] = session_name
        item["attach_command"] = f"tmux attach -t {session_name}"
        item["runner"] = "tmux"

        # Write runner metadata to run root for status resolution
        try:
            import json as _json
            runner_meta = {
                "mode": "tmux",
                "session": session_name,
                "started_at": __import__('time').strftime("%Y-%m-%dT%H:%M:%SZ", __import__('time').gmtime()),
                "command": item.get("command_preview", ""),
                "pid": None,
            "yolo": item.get("yolo"),
            }
            runner_meta_path = os.path.join(item.get("run_root", ""), "state", "runner.json")
            os.makedirs(os.path.dirname(runner_meta_path), exist_ok=True)
            with open(runner_meta_path, "w") as _rf:
                _json.dump(runner_meta, _rf, indent=2, default=str)
        except Exception:
            pass
        # Preserve events_path so current-run.json and qq-tui use the same path
        # events_path is already set in the item from create_external_run_trigger

        # Make future tmux sessions self-describing:
        # Set tmux user options for durable metadata resolution
        run_id_val = item.get("run_id", "")
        run_root_q = item.get("run_root", "")
        events_path_q = item.get("events_path", "")
        target_path_q = item.get("target_path", "")
        task_path_q = item.get("task_path", "")
        yolo_val = "true" if item.get("yolo", False) else "false"
        _tmux_options = {
            "@qonqrete_managed": "1",
            "@qonqrete_run_id": run_id_val,
            "@qonqrete_control_root": control_root,
            "@qonqrete_run_root": run_root_q,
            "@qonqrete_events_path": events_path_q,
            "@qonqrete_target_path": target_path_q,
            "@qonqrete_task_path": task_path_q,
            "@qonqrete_runner": "tmux",
            "@qonqrete_yolo": yolo_val,
        }
        for opt_key, opt_val in _tmux_options.items():
            if opt_val:
                try:
                    subprocess.run(
                        ["tmux", "set-option", "-t", session_name, opt_key, str(opt_val)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                    )
                except Exception:
                    pass

        # Inject env vars into the tmux session environment
        if run_id_val:
            try:
                subprocess.run(
                    ["tmux", "set-environment", "-t", session_name, "QONQRETE_RUN_ID", run_id_val],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                )
            except Exception:
                pass
        if run_root_q:
            try:
                subprocess.run(
                    ["tmux", "set-environment", "-t", session_name, "QONQRETE_RUN_ROOT", run_root_q],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                )
            except Exception:
                pass
        if events_path_q:
            try:
                subprocess.run(
                    ["tmux", "set-environment", "-t", session_name, "QONQRETE_EVENTS_PATH", events_path_q],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                )
            except Exception:
                pass
        if target_path_q:
            try:
                subprocess.run(
                    ["tmux", "set-environment", "-t", session_name, "QONQRETE_TARGET_PATH", target_path_q],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                )
            except Exception:
                pass

        # Write durable tmux-sessions.jsonl entry
        try:
            _tmux_entry = {
                "run_id": run_id_val,
                "tmux_session": session_name,
                "control_root": control_root,
                "run_root": run_root_q,
                "events_path": events_path_q,
                "target_path": target_path_q,
                "task_path": task_path_q,
                "runner": "tmux",
                "yolo": item.get("yolo", False),
                "attach_command": f"tmux attach -t {session_name}",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _tmux_jsonl_path = os.path.join(control_root, "tmux-sessions.jsonl")
            os.makedirs(os.path.dirname(_tmux_jsonl_path), exist_ok=True)
            with open(_tmux_jsonl_path, "a") as _tf:
                _tf.write(json.dumps(_tmux_entry) + "\n")
        except (OSError, IOError):
            pass

        _mark_run_active(item)

        # Background watcher to detect when QonQrete command exits.
        # Monitors runner.finished marker file (primary) with fallback to
        # tmux session disappearance.
        run_root_val = item.get("run_root", "")

        def _watch_tmux():
            import time as _time
            # No pre-add to _finished_run_ids — _mark_runner_finished owns the guard

            _finished_path = os.path.join(run_root_val, "runner.finished")
            _already_finished = False
            _finished_at = 0.0
            while True:
                _time.sleep(3)
                # Primary check: runner.finished marker
                if not _already_finished and os.path.isfile(_finished_path):
                    _already_finished = True
                    _finished_at = _time.time()
                    # Read exit_code if available
                    _exit_code = None
                    _exit_code_path = os.path.join(run_root_val, "runner.exit_code")
                    if os.path.isfile(_exit_code_path):
                        try:
                            with open(_exit_code_path) as ef:
                                _exit_code = int(ef.read().strip())
                        except (ValueError, OSError):
                            pass
                    # Determine state based on exit code
                    _final_state = "finished"
                    if _exit_code is not None and _exit_code != 0:
                        _has_tmux_events = os.path.isfile(os.path.join(run_root_val, "events.jsonl")) if run_root_val else False
                        if not _has_tmux_events:
                            _final_state = "failed_early"
                        else:
                            _final_state = "failed"
                        # Write runner.failed.json
                        try:
                            import json as _json2
                            _failed_data = {
                                "run_id": item.get("run_id", ""),
                                "exit_code": _exit_code,
                                "reason": _final_state,
                                "failed_at": __import__('time').strftime("%Y-%m-%dT%H:%M:%SZ", __import__('time').gmtime()),
                            }
                            _failed_path = os.path.join(run_root_val, "runner.failed.json")
                            with open(_failed_path, "w") as _ff:
                                _json2.dump(_failed_data, _ff, indent=2, default=str)
                        except (OSError, IOError):
                            pass
                    elif _exit_code == 0:
                        _has_final = os.path.isfile(_state_artifact(run_root_val, "final.json")) if run_root_val else False
                        if not _has_final:
                            _final_state = "finished_incomplete"
                    # Use centralized finish handler (owns _finished_run_ids guard)
                    _mark_runner_finished(
                        item,
                        exit_code=_exit_code,
                        reason=f"tmux_watcher_{_final_state}",
                        state=_final_state,
                    )
                    # Short grace period: keep watching briefly in case
                    # the tmux session disappears naturally, but don't
                    # poll forever. Exit watcher after grace period.
                    continue
                # Fallback: tmux session disappeared without marker
                if not _already_finished:
                    try:
                        result = subprocess.run(
                            ["tmux", "has-session", "-t", session_name],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception:
                        # tmux itself might not exist anymore — route through central finish
                        _mark_runner_finished(
                            item,
                            exit_code=None,
                            reason="tmux_session_disappeared_before_marker",
                            state="stale",
                        )
                        break
                    if result.returncode != 0:
                        # Session disappeared — route through central finish
                        _mark_runner_finished(
                            item,
                            exit_code=None,
                            reason="tmux_session_disappeared_before_marker",
                            state="stale",
                        )
                        break
                # After marked finished, wait for session to disappear
                # or grace period to expire (10 seconds after completion)
                else:
                    # Exit watcher after grace period (10s) even if tmux pane stays open
                    if _time.time() - _finished_at > 10.0:
                        break
                    try:
                        result = subprocess.run(
                            ["tmux", "has-session", "-t", session_name],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        if result.returncode != 0:
                            break  # Session gone, stop watching
                    except Exception:
                        break

        t = threading.Thread(target=_watch_tmux, daemon=True)
        t.start()
        return True
    except Exception as e:
        item["launch_ok"] = False
        item["launch_error"] = "tmux_exception"
        return False


def _do_launch(item: Dict[str, Any]) -> bool:
    """Actually launch a QonQrete run in a subprocess.

    Returns True if launch succeeded, False if launch failed.
    Sets item["launch_ok"] appropriately.
    Supports both local_exec and tmux runners.

    Uses explicit run_root for log files in local_exec mode.
    """
    args = item["args"]
    run_id = item["run_id"]
    run_root = item.get("run_root", "")
    runner = item.get("runner", "local_exec")

    if runner == "tmux":
        return _do_launch_tmux(item)

    # local_exec mode
    try:
        # Per-run atomic lock to prevent double-launch
        lock_path = os.path.join(run_root, "runner.lock") if run_root else ""
        if lock_path:
            try:
                os.makedirs(run_root, exist_ok=True)
                if os.path.isfile(lock_path):
                    import time as _time_local
                    lock_age = _time_local.time() - os.path.getmtime(lock_path)
                    if lock_age < 30:
                        # Check if runner.finished exists (run already done)
                        if os.path.isfile(os.path.join(run_root, "runner.finished")):
                            pass  # Run finished, allow re-launch
                        else:
                            item["launch_ok"] = False
                            item["launch_error"] = "already_running"
                            return False
                with open(lock_path, "w") as lf:
                    lf.write(json.dumps({
                        "run_id": run_id,
                        "pid": None,
                        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }))
            except OSError:
                pass

        # Set up log files under run_root
        stdout_log = None
        stderr_log = None
        if run_root:
            os.makedirs(run_root, exist_ok=True)
            stdout_path = os.path.join(run_root, "runner.stdout.log")
            stderr_path = os.path.join(run_root, "runner.stderr.log")
            try:
                stdout_log = open(stdout_path, "w")
                stderr_log = open(stderr_path, "w")
            except OSError:
                stdout_log = subprocess.DEVNULL
                stderr_log = subprocess.DEVNULL
        else:
            stdout_log = subprocess.DEVNULL
            stderr_log = subprocess.DEVNULL

        proc = subprocess.Popen(
            args,
            stdout=stdout_log,
            stderr=stderr_log,
            start_new_session=True,
        )
        item["launch_ok"] = True
        item["pid"] = proc.pid
        item["runner"] = "local_exec"

        # Write runner metadata to run root for status resolution
        try:
            import json as _json_local
            _runner_meta = {
                "mode": "local",
                "started_at": __import__('time').strftime("%Y-%m-%dT%H:%M:%SZ", __import__('time').gmtime()),
                "command": item.get("command_preview", ""),
                "pid": proc.pid,
                "yolo": item.get("yolo"),
            }
            _runner_meta_path = os.path.join(run_root, "state", "runner.json")
            os.makedirs(os.path.dirname(_runner_meta_path), exist_ok=True)
            with open(_runner_meta_path, "w") as _rf2:
                _json_local.dump(_runner_meta, _rf2, indent=2, default=str)
        except Exception:
            pass
        if run_root:
            item["stdout_log"] = os.path.join(run_root, "runner.stdout.log")
            item["stderr_log"] = os.path.join(run_root, "runner.stderr.log")

        _mark_run_active(item)

        # Capture references needed by the watcher thread
        _run_root = run_root
        _runner = item.get("runner", "local_exec")

        def _watch():
            exit_code = proc.wait()
            # Write runner.exit_code
            if _run_root:
                try:
                    exit_code_path = os.path.join(_run_root, "runner.exit_code")
                    with open(exit_code_path, "w") as ef:
                        ef.write(str(exit_code))
                except OSError:
                    pass
            # Print terminal finish message (plain text, no ANSI)
            _runner_final_status = None
            if _run_root:
                try:
                    from qq.web.status_resolver import resolve_final_status as _rfs2
                    _runner_final_status = _rfs2(_run_root)
                except Exception:
                    pass
            if exit_code == 0 and _runner_final_status and _runner_final_status.upper() == "FULLY_DONE":
                print(f"\nQonQrete run finished with status: FULLY_DONE. Session: local-{item.get('run_id', '')}", flush=True)
            elif _runner_final_status:
                print(f"\nQonQrete run finished with status: {_runner_final_status}. Session: local-{item.get('run_id', '')} (exit code {exit_code})", flush=True)
            else:
                print(f"\nQonQrete run finished with exit code {exit_code}. Session: local-{item.get('run_id', '')}", flush=True)
            # Determine state based on exit code and whether final.json exists
            final_state = "finished"
            has_events = os.path.isfile(os.path.join(_run_root, "events.jsonl")) if _run_root else False
            has_final = os.path.isfile(_state_artifact(_run_root, "final.json")) if _run_root else False
            if exit_code != 0:
                # Nonzero exit: failed or failed_early (no events produced)
                if not has_events:
                    final_state = "failed_early"
                else:
                    final_state = "failed"
            elif not has_final:
                # Zero exit but no final.json: finished_incomplete
                final_state = "finished_incomplete"
            # Write runner.failed.json for failed states
            if final_state in ("failed", "failed_early"):
                try:
                    import json as _json
                    failed_data = {
                        "run_id": item.get("run_id", ""),
                        "exit_code": exit_code,
                        "reason": final_state,
                        "failed_at": __import__('time').strftime("%Y-%m-%dT%H:%M:%SZ", __import__('time').gmtime()),
                    }
                    failed_path = os.path.join(_run_root, "runner.failed.json")
                    with open(failed_path, "w") as ff:
                        _json.dump(failed_data, ff, indent=2, default=str)
                except (OSError, IOError):
                    pass
            # Use centralized finish handler (owns _finished_run_ids guard)
            _mark_runner_finished(
                item,
                exit_code=exit_code,
                reason=f"local_exec_watcher_{final_state}",
                state=final_state,
            )
            # Clean up log file handles
            import io as _io
            if isinstance(stdout_log, _io.IOBase):
                try:
                    stdout_log.close()
                except Exception:
                    pass
            if isinstance(stderr_log, _io.IOBase):
                try:
                    stderr_log.close()
                except Exception:
                    pass
        t = threading.Thread(target=_watch, daemon=True)
        t.start()
        return True
    except Exception as e:
        # Launch failed — do NOT mark as active.
        # Do NOT call _maybe_start_next() here — the caller owns queue advancement.
        item["launch_ok"] = False
        item["launch_error"] = "local_exec_failed"
        return False


# ---------------------------------------------------------------------------
# Main trigger function
# ---------------------------------------------------------------------------

def create_external_run_trigger(
    *,
    source: str,
    raw_transcription: str,
    task_text: str,
    mode: str,
    target: str,
    trigger: str = "qonqrete",
    source_channel: Optional[str] = None,
    sender_id: Optional[str] = None,
    sender_display: Optional[str] = None,
    chat_id: Optional[str] = None,
    message_id: Optional[str] = None,
    transcription_id: Optional[str] = None,
    sender_name: Optional[str] = None,
    chat_title: Optional[str] = None,
    task_title: Optional[str] = None,
    reply_to: Optional[Dict[str, Any]] = None,
    callback_url: Optional[str] = None,
    callback_token: Optional[str] = None,
    callback_token_ref: Optional[str] = None,
    obelisk: Optional[Dict[str, Any]] = None,
    delimiter: Optional[str] = None,
    received_at: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[RunsAPIConfig] = None,
    request_ip: Optional[str] = None,
    endpoint_path: str = "/api/qonqrete/runs",
    legacy_endpoint: bool = False,
    yolo: Optional[bool] = None,
) -> RunTriggerResult:
    """Create a QonQrete run trigger from an external source.

    This is the single internal function used by both the canonical API
    endpoint and any future watch-folder adapters. It handles validation,
    deduplication, file writing, target resolution, and run launching.

    Args:
        source: Source identifier (e.g., "obelisk").
        raw_transcription: Full raw transcription text.
        task_text: The extracted task text to execute.
        mode: "repo" or "folder".
        target: "default", an alias name, or an absolute path.
        trigger: "qonqrete" or "concrete".
        delimiter: Optional delimiter used to extract task_text.
        ... (other fields)
        endpoint_path: Canonical endpoint path for response metadata.
        legacy_endpoint: True if request came via deprecated path.
    """
    if config is None:
        config = load_obelisk_config_from_env()

    # Build request object
    # Detect if raw_transcription was synthesized (missing or empty but task_text present)
    _raw_synthesized = (not raw_transcription or raw_transcription.strip() == "") and bool(task_text and task_text.strip())
    _effective_raw = raw_transcription if (raw_transcription and raw_transcription.strip()) else task_text

    # Resolve YOLO: request param > env var > config > default
    resolved_yolo = yolo
    if resolved_yolo is None:
        # Check if the request has yolo in its payload
        resolved_yolo = config.yolo_default

    # Merge top-level obelisk into metadata.obelisk
    _meta = dict(metadata or {})
    if obelisk and isinstance(obelisk, dict):
        # Merge with existing metadata.obelisk if present
        _existing_obelisk = _meta.get("obelisk", {})
        if isinstance(_existing_obelisk, dict):
            _merged = dict(_existing_obelisk)
            _merged.update(obelisk)
            _meta["obelisk"] = _merged
        else:
            _meta["obelisk"] = obelisk

    # Also merge flat callback_url/callback_token into metadata.obelisk for nested form support
    if callback_url and not _meta.get("obelisk"):
        _meta["obelisk"] = {"callback_url": callback_url}

    req = IngestRequest(
        source=source,
        raw_transcription=_effective_raw,
        trigger=trigger,
        mode=mode,
        target=target,
        task_text=task_text,
        source_channel=source_channel,
        sender_id=sender_id,
        sender_display=sender_display,
        sender_name=sender_name,
        chat_id=chat_id,
        chat_title=chat_title,
        message_id=message_id,
        transcription_id=transcription_id,
        task_title=task_title,
        reply_to=reply_to,
        callback_url=callback_url,
        callback_token=callback_token,
        callback_token_ref=callback_token_ref,
        delimiter=delimiter,
        received_at=received_at,
        metadata=_meta,
        raw_transcription_synthesized=_raw_synthesized,
        yolo=resolved_yolo,
    )

    # Validate
    try:
        validate_request(req, config)
    except ValidationError as e:
        return RunTriggerResult(ok=False, run_id="", task_path="", target_path="",
                                error=e.error, message=e.message)

    # Generate collision-safe stamp
    stamp = _generate_run_stamp()
    run_id = _run_stamp_to_run_id(stamp)
    created_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Compute the explicit run_root (metadata root)
    # Uses: runs_root > default_run_root > ~/Desktop/qq/qonqrete-runs
    # The metadata run root is SEPARATE from the target (code) directory
    run_root_parent = os.path.expanduser(config.default_run_root) if config.default_run_root else os.path.expanduser("~/Desktop/qq/qonqrete-runs")
    # QONQRETE_RUNS_ROOT overrides if set
    env_runs_root = os.environ.get("QONQRETE_RUNS_ROOT", os.environ.get("QONQRETE_RUNS_DEFAULT_ROOT", ""))
    if env_runs_root:
        run_root_parent = os.path.expanduser(env_runs_root)
    run_root = os.path.join(run_root_parent, run_id)
    events_path = os.path.join(run_root, "events.jsonl")

    # Build dashboard_url early — needed for dedupe responses
    if config.dashboard_url:
        dashboard_url = config.dashboard_url
    else:
        host = os.environ.get("QQ_WEB_HOST", "0.0.0.0")
        port = os.environ.get("QQ_WEB_PORT", "31337")
        # Normalize 0.0.0.0, ::, and empty host to 127.0.0.1
        display_host = host if host not in ("0.0.0.0", "::", "") else "127.0.0.1"
        dashboard_url = f"http://{display_host}:{port}"

    # Resolve target
    try:
        resolved = resolve_target(req, config, stamp)
        check_path_allowed(resolved, config)
    except ValidationError as e:
        return RunTriggerResult(ok=False, run_id="", task_path="", target_path="",
                                error=e.error, message=e.message, endpoint=endpoint_path,
                                legacy_endpoint=legacy_endpoint)

    # Reconcile active run state from current-run.json BEFORE dedupe check.
    # This ensures stale dedupe entries from a previous process lifetime
    # don't block retries before we've verified the current state.
    _reconcile_active_run(config)

    # Clear stale queued runs so they don't auto-launch after this new run finishes
    _clear_stale_queued_runs()

    # Dedupe
    dedupe_key = _compute_dedupe_key(req)
    if dedupe_key:
        existing = check_duplicate(dedupe_key)
        if existing:
            return RunTriggerResult(
                ok=True, duplicate=True,
                run_id=existing.get("run_id", ""),
                run_root=existing.get("run_root", run_root),
                events_path=existing.get("events_path",
                    os.path.join(existing.get("run_root", run_root), "events.jsonl")
                    if existing.get("run_root") else ""),
                task_path=existing.get("task_path", ""),
                target_path=existing.get("target_path", ""),
                mode=existing.get("mode", req.mode),
                runner=existing.get("runner", config.runner),
                command_preview=existing.get("command_preview", ""),
                dashboard_url=dashboard_url,
                message="Duplicate transcription already accepted",
                endpoint=endpoint_path,
                legacy_endpoint=legacy_endpoint,
                duplicate_state=existing.get("state", "unknown"),
            )

    # Ensure run_root directory exists — only after dedupe check passes.
    os.makedirs(run_root, exist_ok=True)

    # Persist origin metadata for completion callback
    _write_origin_metadata(run_root, req, run_id,
                          target_path=resolved.path,
                          events_path=events_path,
                          dashboard_url=dashboard_url)

    # Write task files (command_args will be filled in after we have task_path)
    task_path = write_task_files(
        req, config, stamp, resolved,
        dedupe_key=dedupe_key,
        command_args=None,  # placeholder
        endpoint_path=endpoint_path,
        legacy_endpoint=legacy_endpoint,
        request_ip=request_ip,
    )

    # Now generate full command with real task_path and explicit run_root
    args = generate_command(
        runner=config.runner,
        task_path=task_path,
        target_path=resolved.path,
        mode=req.mode,  # type: ignore[arg-type]
        run_root=run_root,
        events_path=events_path,
        yolo=resolved_yolo,
    )
    cmd_preview_str = command_preview(args)

    # Update metadata with real command args
    _update_meta_command(task_path, stamp, args, cmd_preview_str, config)

    # Ensure target directory exists (best-effort, don't fail on readonly)
    try:
        os.makedirs(resolved.path, exist_ok=True)
    except OSError:
        pass  # Target dir creation is best-effort; run may still succeed

    # Preflight: verify control root is writable BEFORE any launch attempt.
    # This prevents orphan runs when current-run.json cannot be written.
    if not _preflight_control_root(config.control_root):
        return RunTriggerResult(
            ok=False,
            error="control_root_preflight_failed",
            message=f"Control root {config.control_root} is not writable. Cannot launch run.",
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            mode=req.mode,
            resolved_target_kind=resolved.kind,
            endpoint=endpoint_path,
            legacy_endpoint=legacy_endpoint,
            runner=config.runner,
        )

    # Queue or launch
    with _queue_lock:
        is_active = _active_run

    if config.queue_mode == "reject_if_running" and is_active:
        return RunTriggerResult(
            ok=False,
            run_id=run_id,
            task_path=task_path,
            target_path=resolved.path,
            error="run_already_active",
            message="A QonQrete run is already active. Queue mode is 'reject_if_running'.",
            resolved_target_kind=resolved.kind,
            endpoint=endpoint_path,
            legacy_endpoint=legacy_endpoint,
        )

    # ── latest_wins queue policy ──
    if config.queue_mode == "latest_wins" and is_active:
        # Atomically supersede all older pending items, keep only this one.
        with _queue_lock:
            superseded = []
            kept_pending = None
            for qi in _queue:
                if qi.get("run_id") != run_id:
                    superseded.append(qi)
            _queue.clear()
            # Build pending-runs.json item
            pending_item = {
                "run_id": run_id,
                "run_root": run_root,
                "events_path": events_path,
                "args": args,
                "task_path": task_path,
                "target_path": resolved.path,
                "mode": req.mode,
                "source": req.source,
                "runner": config.runner,
                "control_root": config.control_root,
                "command_preview": cmd_preview_str,
                "dedupe_key": dedupe_key,
                "created_at": created_at_iso,
                "yolo": resolved_yolo,
                "queue_position": 1,
                "queue_policy": "latest_wins",
            }
            _queue.append(pending_item)

        # Write pending-run.json atomically
        atomic_write_json(config.control_root, "pending-run.json", {
            "run_id": run_id,
            "run_root": run_root,
            "events_path": events_path,
            "task_path": task_path,
            "target_path": resolved.path,
            "runner": config.runner,
            "created_at": created_at_iso,
            "queue_policy": "latest_wins",
        })

        # Mark superseded items in history and dedupe
        superseded_run_ids = []
        for si in superseded:
            s_rid = si.get("run_id", "")
            if s_rid:
                superseded_run_ids.append(s_rid)
                # Append superseded lifecycle record
                _append_to_runs_jsonl(config.control_root, {
                    "run_id": s_rid,
                    "control_root": config.control_root,
                    "run_root": si.get("run_root", ""),
                    "target_path": si.get("target_path", ""),
                    "task_path": si.get("task_path", ""),
                    "events_path": si.get("events_path", ""),
                    "state": "superseded",
                    "runner": si.get("runner", ""),
                    "yolo": si.get("yolo"),
                    "command_preview": si.get("command_preview", ""),
                    "created_at": si.get("created_at", ""),
                    "superseded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "superseded_by_run_id": run_id,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                # Mark dedupe as superseded (terminal — won't block retries)
                _record_item_dedupe(si, "superseded")
                # Write runner.failed.json for terminal evidence
                s_run_root = si.get("run_root", "")
                if s_run_root:
                    _write_failed_run_file(si, "superseded_by_newer_request")

        # Write current-run.json to link to this newest pending run
        _update_current_run_pointer_guarded(
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            mode=req.mode,
            source=req.source,
            runner=config.runner,
            tmux_session="",
            created_at=created_at_iso,
            command_preview=cmd_preview_str,
            control_root=config.control_root,
            state="accepted",
            allow_switch_to_new_run=True,
            yolo=resolved_yolo,
        )

        # Record dedupe for new pending item
        if dedupe_key:
            record_dedupe(dedupe_key, run_id, task_path, resolved.path,
                          run_root=run_root, events_path=events_path,
                          mode=req.mode, runner=config.runner,
                          command_preview=cmd_preview_str, state="queued")
            _write_ingest_idempotency(req, dedupe_key, run_id, run_root,
                                      events_path, resolved.path, task_path,
                                      cmd_preview_str, config, "queued")

        # Append accepted history for the new run
        _append_to_runs_jsonl(config.control_root, {
            "run_id": run_id,
            "control_root": config.control_root,
            "run_root": run_root,
            "events_path": events_path,
            "task_path": task_path,
            "target_path": resolved.path,
            "mode": req.mode,
            "runner": config.runner,
            "yolo": resolved_yolo,
            "command_preview": cmd_preview_str,
            "state": "accepted",
            "created_at": created_at_iso,
            "queue_policy": "latest_wins",
            "queue_position": 1,
        })

        return RunTriggerResult(
            ok=True,
            queued=True,
            started=False,
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            queue_position=1,
            mode=req.mode,
            command_preview=cmd_preview_str,
            dashboard_url=dashboard_url,
            resolved_target_kind=resolved.kind,
            endpoint=endpoint_path,
            legacy_endpoint=legacy_endpoint,
            runner=config.runner,
            source=req.source,
            source_channel=req.source_channel or "api",
            completion_callback_configured=_resolve_callback_configured(run_root),
            queue_policy="latest_wins",
            superseded_run_ids=superseded_run_ids,
            linked_run_id=run_id,
            active_run_id=_active_run_id,
            pending_run_id=run_id,
        )

    if config.queue_mode == "queue" and is_active:
        # Check for duplicate in the queue by dedupe_key before adding.
        # This prevents the same transcription from being queued multiple
        # times while another run is active.
        if dedupe_key:
            with _queue_lock:
                for existing_q in _queue:
                    if existing_q.get("dedupe_key") == dedupe_key:
                        # Already queued — return duplicate response
                        return RunTriggerResult(
                            ok=True,
                            duplicate=True,
                            run_id=existing_q.get("run_id", run_id),
                            task_path=task_path,
                            target_path=resolved.path,
                            message="Duplicate transcription already queued",
                            endpoint=endpoint_path,
                            legacy_endpoint=legacy_endpoint,
                            run_root=existing_q.get("run_root", run_root),
                            events_path=existing_q.get("events_path", events_path),
                            runner=config.runner,
                        )

        queue_item = {
            "run_id": run_id,
            "run_root": run_root,
            "events_path": events_path,
            "args": args,
            "task_path": task_path,
            "target_path": resolved.path,
            "mode": req.mode,
            "source": req.source,
            "runner": config.runner,
            "control_root": config.control_root,
            "command_preview": cmd_preview_str,
            "dedupe_key": dedupe_key,
            "created_at": created_at_iso,
            "yolo": resolved_yolo,
        }
        with _queue_lock:
            _queue.append(queue_item)
            queue_pos = len(_queue)

        # Record dedupe AFTER successful queue insertion so that future
        # retries (even after the queue item is dequeued) return duplicate=True.
        if dedupe_key:
            record_dedupe(dedupe_key, run_id, task_path, resolved.path, run_root=run_root, events_path=events_path, mode=req.mode, runner=config.runner, command_preview=cmd_preview_str, state="queued")
            _write_ingest_idempotency(req, dedupe_key, run_id, run_root, events_path, resolved.path, task_path, cmd_preview_str, config, "queued")

        return RunTriggerResult(
            ok=True,
            queued=True,
            started=False,
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            queue_position=queue_pos,
            mode=req.mode,
            command_preview=cmd_preview_str,
            dashboard_url=dashboard_url,
            resolved_target_kind=resolved.kind,
            endpoint=endpoint_path,
            legacy_endpoint=legacy_endpoint,
            runner=config.runner,
            source=req.source,
            source_channel=req.source_channel or "api",
            completion_callback_configured=_resolve_callback_configured(run_root),
        )

    # Start immediately
    queue_item = {
        "run_id": run_id,
        "run_root": run_root,
        "events_path": events_path,
        "args": args,
        "task_path": task_path,
        "target_path": resolved.path,
        "mode": req.mode,
        "source": req.source,
        "runner": config.runner,
        "control_root": config.control_root,
        "command_preview": cmd_preview_str,
        "dedupe_key": dedupe_key,
        "created_at": created_at_iso,
        "yolo": resolved_yolo,
    }

    # Write current-run.json in "starting" state BEFORE any launch attempt.
    # If this write fails, DO NOT launch — the dashboard cannot follow
    # an orphan run.
    pointer_ok = _update_current_run_pointer_guarded(
        run_id=run_id,
        run_root=run_root,
        events_path=events_path,
        task_path=task_path,
        target_path=resolved.path,
        mode=req.mode,
        source=req.source,
        runner=config.runner,
        tmux_session="",
        created_at=created_at_iso,
        command_preview=cmd_preview_str,
        control_root=config.control_root,
        state="starting",
        allow_switch_to_new_run=True,
        yolo=resolved_yolo,
    )
    
    # Append to runs.jsonl on acceptance/creation
    _append_to_runs_jsonl(config.control_root, {
        "run_id": run_id,
        "control_root": config.control_root,
        "run_root": run_root,
        "events_path": events_path,
        "task_path": task_path,
        "target_path": resolved.path,
        "mode": req.mode,
        "runner": config.runner,
        "yolo": resolved_yolo,
        "command_preview": cmd_preview_str,
        "state": "accepted",
        "created_at": created_at_iso,
        "started_at": "",
        "finished_at": "",
        "exit_code": None,
    })
    if not pointer_ok:
        # Write failed-run metadata and attempt terminal callback
        _write_failed_run_file(queue_item, "current_run_pointer_write_failed")
        _maybe_callback_launch_failure(queue_item)
        return RunTriggerResult(
            ok=False,
            error="current_run_pointer_write_failed",
            message="Cannot write current-run.json pointer. Launch aborted to prevent orphan run.",
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            mode=req.mode,
            resolved_target_kind=resolved.kind,
            endpoint=endpoint_path,
            legacy_endpoint=legacy_endpoint,
            runner=config.runner,
        )

    # Clear stale queue entries before inserting new run
    _clear_stale_queued_runs()

    # Insert and attempt launch
    with _queue_lock:
        _queue.insert(0, queue_item)

    _maybe_start_next()

    # Check if launch actually happened (launch_ok field, works for both local_exec and tmux)
    launched = queue_item.get("launch_ok") is True

    if not launched:
        # _do_launch failed — update pointer to "launch_failed" state
        # Do NOT record dedupe — retries should not be blocked
        launch_error = queue_item.get("launch_error", "launch_failed")
        _update_current_run_pointer_guarded(
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            mode=req.mode,
            source=req.source,
            runner=config.runner,
            tmux_session="",
            created_at=created_at_iso,
            command_preview=cmd_preview_str,
            control_root=config.control_root,
            state="launch_failed",
            launch_error=launch_error,
        )
        # Write failed-run metadata and attempt terminal callback
        _write_failed_run_file(queue_item, launch_error)
        _maybe_callback_launch_failure(queue_item)
        return RunTriggerResult(
            ok=False,
            error=launch_error,
            message=f"Failed to start QonQrete process: {launch_error}",
            run_id=run_id,
            run_root=run_root,
            events_path=events_path,
            task_path=task_path,
            target_path=resolved.path,
            mode=req.mode,
            resolved_target_kind=resolved.kind,
            endpoint=endpoint_path,
            legacy_endpoint=legacy_endpoint,
            runner=config.runner,
        )

    # Launch succeeded — record dedupe ONLY now (fix #2)
    if dedupe_key:
        record_dedupe(dedupe_key, run_id, task_path, resolved.path, run_root=run_root, events_path=events_path, mode=req.mode, runner=config.runner, command_preview=cmd_preview_str, state="started")

    # Update current-run.json pointer to "started" state with runner details.
    # Uses guarded update: if the run already finished (e.g. fast fake local_exec),
    # the "started" write is silently skipped so "finished" is never regressed.
    # Best-effort: if this write fails, the run was already launched successfully,
    # so we include pointer_update_failed but do NOT return an error.
    tmux_session_name = queue_item.get("tmux_session", f"qonqrete-{run_id}" if config.runner == "tmux" else "")
    attach_command = queue_item.get("attach_command", "")
    runner_pid = queue_item.get("pid", None)
    started_pointer_ok = _update_current_run_pointer_guarded(
        run_id=run_id,
        run_root=run_root,
        events_path=events_path,
        task_path=task_path,
        target_path=resolved.path,
        mode=req.mode,
        source=req.source,
        runner=config.runner,
        tmux_session=tmux_session_name if config.runner == "tmux" else "",
        created_at=created_at_iso,
        command_preview=cmd_preview_str,
        control_root=config.control_root,
        state="started",
        pid=runner_pid if config.runner == "local_exec" else None,
        attach_command=attach_command if config.runner == "tmux" else "",
        yolo=resolved_yolo,
    )

    # Write active-run.json atomically (executor state, not dashboard linkage)
    # This is done alongside current-run.json, both in "started" state.
    _active_data = {
        "run_id": run_id,
        "run_root": run_root,
        "events_path": events_path,
        "task_path": task_path,
        "target_path": resolved.path,
        "mode": req.mode,
        "source": req.source,
        "runner": config.runner,
        "created_at": created_at_iso,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": "started",
        "yolo": resolved_yolo,
        "command_preview": cmd_preview_str,
        "launcher_pid": os.getpid(),
    }
    if config.runner == "tmux" or queue_item.get("runner") == "tmux":
        _active_data["tmux_session"] = queue_item.get("tmux_session", f"qonqrete-{run_id}")
        _active_data["attach_command"] = queue_item.get("attach_command", "")
    elif queue_item.get("pid"):
        _active_data["pid"] = queue_item.get("pid")
    atomic_write_json(config.control_root, "active-run.json", _active_data)

    # Also write pending-run.json removal if it existed
    pending_path = os.path.join(config.control_root, "pending-run.json")
    if os.path.isfile(pending_path):
        try:
            os.unlink(pending_path)
        except OSError:
            pass

    # Build runner-specific fields
    runner_fields = {}
    if not started_pointer_ok:
        runner_fields["pointer_update_failed"] = True
    if config.runner == "tmux" or queue_item.get("runner") == "tmux":
        runner_fields["tmux_session"] = queue_item.get("tmux_session", f"qonqrete-{run_id}")
        runner_fields["attach_command"] = queue_item.get("attach_command", f"tmux attach -t {runner_fields['tmux_session']}")
    elif launched:
        # local_exec: include pid and log paths
        runner_fields["pid"] = queue_item.get("pid")
        if run_root:
            runner_fields["stdout_log"] = os.path.join(run_root, "runner.stdout.log")
            runner_fields["stderr_log"] = os.path.join(run_root, "runner.stderr.log")

    # Determine completion_callback_configured
    _callback_configured = _resolve_callback_configured(run_root)

    return RunTriggerResult(
        ok=True,
        started=True,
        queued=False,
        run_id=run_id,
        run_root=run_root,
        events_path=events_path,
        task_path=task_path,
        target_path=resolved.path,
        mode=req.mode,
        command_preview=cmd_preview_str,
        dashboard_url=dashboard_url,
        resolved_target_kind=resolved.kind,
        endpoint=endpoint_path,
        legacy_endpoint=legacy_endpoint,
        runner=config.runner,
        source=req.source,
        source_channel=req.source_channel or "api",
        completion_callback_configured=_callback_configured,
        yolo=resolved_yolo,
        linked_run_id=run_id,
        active_run_id=run_id,
        queue_policy=config.queue_mode,
        **runner_fields,
    )


def _update_meta_command(task_path: str, stamp: str, args: List[str], cmd_preview_str: str, config: RunsAPIConfig) -> None:
    """Update an existing meta.json with command info after writing."""
    task_dir = os.path.expanduser(config.task_dir)
    meta_path = os.path.join(task_dir, f"task_{stamp}.meta.json")
    try:
        if os.path.isfile(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)
            meta["command_args"] = args
            meta["command_preview"] = cmd_preview_str
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2, default=str)
    except Exception:
        pass
