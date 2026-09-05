"""
Read model builder — constructs a stable JSON view of a QonQrete run.

Inputs (all under run_root/):
  - events.jsonl
  - task.json
  - clarified_task.json
  - plan.json
  - cycle-*-after-build.json
  - cycle-*-after-harness.json
  - cycle-*-after-review.json
  - final.json

Output: dict matching the stable read-model schema (schema_version 1).

Rules:
  - Never infer destructive state from missing files.
  - Malformed events are reported as warnings, never crash.
  - final.json is authoritative for final state if present.

Speed optimizations:
  - Incremental caching: tracks events.jsonl byte position, only
    re-reads new events on subsequent calls. Full rebuild only when
    artifacts (plan.json, task.json, etc.) change or final.json appears.
  - Cache TTL: 1 second in-memory cache via _get_cached_read_model
    in api.py, which deduplicates burst polling.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

# Canonical progress calculator
from qq.progress import calculate_progress, calculate_from_read_model
from qq.web.status_resolver import (
    resolve_display_name,
    resolve_final_status,
    resolve_runner_metadata,
    is_fully_done,
)

SCHEMA_VERSION = 2

# Done group statuses for counter calculation
_DONE_GROUP_STATUSES = {
    "done",
    "completed",
    "merged",
    "fully_done",
    "success",
    "valid_done",
    "inspeqtor_approved",
    "approved",
    "accepted",
    "finalized",
}

def _coerce_verdict_str(value: Any) -> Any:
    """Coerce a possibly-malformed verdict/status value to a plain string.

    Review verdicts can arrive as a string, a dict (e.g. {'status':
    'NOT_DONE'}), a number, or be missing entirely.  Normalise the common
    shapes to a string so downstream `.upper()`/equality checks can never
    raise; return None when nothing usable is present.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, dict):
        for key in ("status", "verdict", "result", "outcome"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    if isinstance(value, (int, float, bool)):
        s = str(value).strip()
        return s or None
    return None


def _coerce_uid(value: Any) -> str:
    """Coerce a possibly-malformed group/briq id to a safe hashable string.

    Review/cycle events sometimes carry a 'build_group_id' / 'gid' /
    'briq_id' that is a dict, list, None, or other non-hashable value.
    Such values must never be used as dict keys or be iterated directly,
    because that would raise ``TypeError: unhashable type`` (or worse) and
    crash the read model during the inspeQtor/reviewing phase.  A value like
    ``{'id': 'g1'}`` is unwrapped to ``'g1'``; otherwise a plain string is
    returned (or ``''`` when nothing usable is present).
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("id", "gid", "briq_id", "build_group_id", "group_id"):
            v = value.get(key)
            if isinstance(v, (str, int, float, bool)):
                s = str(v).strip()
                if s:
                    return s
    return ""


# Status lifecycle mapping
_GROUP_STATUS_MAP = {
    "planned": "planned",
    "picked_up": "picked_up",
    "building": "building",
    "built": "built",
    "validating": "validating",
    "validation_failed": "validation_failed",
    "reviewing": "reviewing",
    "repair_needed": "repair_needed",
    "done": "done",
    "blocked": "blocked",
    "aborted": "aborted",
}


# ---------------------------------------------------------------------------
# Incremental read-model cache
# ---------------------------------------------------------------------------
class ReadModelCache:
    """Incremental cache for read-model builds.

    Tracks the byte position in events.jsonl and the mtimes of static
    artifacts.  On successive calls with the same run_root:
      - Only new events are parsed (from the last known byte position).
      - Static artifacts are re-read only when their mtimes change.
      - The cached read model is patched incrementally.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}          # {run_root: full_model}
        self._events_pos: Dict[str, int] = {}      # {run_root: byte_position}
        self._artifact_mtimes: Dict[str, Dict[str, float]] = {}  # {run_root: {path: mtime}}
        self._cache_times: Dict[str, float] = {}    # {run_root: timestamp}

    def get(self, run_root: str, ttl: float = 1.0) -> Optional[Dict[str, Any]]:
        """Return cached read model if within TTL. Returns None if stale."""
        now = time.time()
        with self._lock:
            if run_root in self._cache:
                ts = self._cache_times.get(run_root, 0)
                if now - ts < ttl:
                    return self._cache[run_root]
        return None

    def set(self, run_root: str, model: Dict[str, Any]):
        """Store model in cache."""
        now = time.time()
        with self._lock:
            self._cache[run_root] = model
            self._cache_times[run_root] = now

    def get_events_position(self, run_root: str) -> int:
        """Get the byte position up to which events have been parsed."""
        with self._lock:
            return self._events_pos.get(run_root, 0)

    def set_events_position(self, run_root: str, pos: int):
        """Set the byte position up to which events have been parsed."""
        with self._lock:
            self._events_pos[run_root] = pos

    def artifacts_changed(self, run_root: str, artifacts: Dict[str, str]) -> bool:
        """Check whether any static artifact has changed mtime.
        Returns True if any artifact is new/changed/removed, False if all same."""
        prev = self._artifact_mtimes.get(run_root, {})
        current: Dict[str, float] = {}
        for name, path in artifacts.items():
            try:
                current[name] = os.path.getmtime(path)
            except OSError:
                current[name] = 0.0

        if prev != current:
            self._artifact_mtimes[run_root] = current
            return True
        return False

    def invalidate(self, run_root: Optional[str] = None):
        """Invalidate cache for a specific run_root or all."""
        with self._lock:
            if run_root is None:
                self._cache.clear()
                self._events_pos.clear()
                self._artifact_mtimes.clear()
                self._cache_times.clear()
            else:
                self._cache.pop(run_root, None)
                self._events_pos.pop(run_root, None)
                self._artifact_mtimes.pop(run_root, None)
                self._cache_times.pop(run_root, None)


# Module-level cache instance
_read_model_cache = ReadModelCache()


def get_read_model_cache() -> ReadModelCache:
    """Return the module-level ReadModelCache instance."""
    return _read_model_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    """Read a JSON file, returning None if missing or malformed."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _safe_read_jsonl(path: str, start_pos: int = 0) -> tuple:
    """Read all events from a JSONL file starting at byte position.
    Returns (events_list, new_byte_position)."""
    if not os.path.isfile(path):
        return [], 0
    events: List[Dict[str, Any]] = []
    new_pos = start_pos
    try:
        fsize = os.path.getsize(path)
        if fsize < start_pos:
            # File truncated — read from beginning
            new_pos = 0
            start_pos = 0
        if fsize == start_pos:
            return [], start_pos
        with open(path, "r", encoding="utf-8") as fh:
            fh.seek(start_pos)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({
                        "type": "malformed_event",
                        "raw": line[:200],
                        "warning": True,
                    })
            new_pos = fh.tell()
    except OSError:
        pass
    return events, new_pos


def _derive_run_status(events: List[Dict[str, Any]],
                       final_data: Optional[Dict[str, Any]],
                       previous_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Derive run-level status from events and final snapshot.

    When previous_status is provided, it acts as the baseline — only
    events newer than the last known position are applied as overrides.

    Tracks cycle from multiple event types (review.verdict, cycle_completed,
    cycle.*, etc.) and maintains active_agent_started_at for Agent Time reset.
    """
    status = "running"
    active_agent = "qlarifier"
    cycle = 1
    final_verdict = None
    started_at = 0
    updated_at = 0
    active_agent_started_at = 0
    model_code = "?"
    action_status = "Preparing"
    action_updated_at = 0

    if previous_status:
        status = previous_status.get("status", "running")
        active_agent = previous_status.get("active_agent", "qlarifier")
        cycle = previous_status.get("cycle", 1)
        final_verdict = previous_status.get("final_verdict")
        started_at = previous_status.get("started_at", 0)
        updated_at = previous_status.get("updated_at", 0)
        active_agent_started_at = previous_status.get("active_agent_started_at", 0)
        model_code = previous_status.get("model_code", "?")
        action_status = previous_status.get("action_status", "Preparing")
        action_updated_at = previous_status.get("action_updated_at", 0)

    # Apply events on top
    for evt in events:
        t = evt.get("type", "")
        ts = evt.get("ts", 0)
        if t == "active_agent_changed":
            active_agent = evt.get("role", active_agent)
            active_agent_started_at = ts  # Reset agent time on agent change
            if evt.get("model"):
                model_code = evt.get("model", model_code)
            # Set action status based on new agent role
            role = evt.get("role", "")
            if role == "qlarifier":
                action_status = "Preparing"
            elif role == "instruqtor":
                action_status = "Planning"
            elif role == "construqtor":
                action_status = "Building"
            elif role == "inspeqtor":
                action_status = "Reviewing"
            action_updated_at = ts
        if t == "run.completed":
            status = "done"
            final_verdict = "FULLY_DONE"
            action_status = "FULLY_DONE"
            action_updated_at = ts
        elif t == "config.loaded" and model_code == "?":
            models = evt.get("models", {})
            if models and active_agent in models:
                model_code = models[active_agent]
            elif models:
                model_code = next(iter(models.values()), "?")
        elif t == "run.aborted":
            status = "aborted"
            action_status = "STOPPED"
            action_updated_at = ts
        elif t == "run.failed":
            status = "failed"
            action_status = "FAILED"
            action_updated_at = ts
        elif t == "action_status_changed":
            _candidate = evt.get("action_status", action_status)
            # Never surface a ready-to-review status on the GUI. Coerce the
            # forbidden literal to "Building" if it ever leaks through.
            if _candidate in ("Ready for review", "ready_for_review", "READY_FOR_REVIEW"):
                _candidate = "Building"
            action_status = _candidate
            action_updated_at = ts
        elif t in ("review.verdict", "cycle_completed", "cycle.started",
                    "cycle_summary", "qontroller.cycle_done"):
            new_cycle = evt.get("cycle")
            if new_cycle is not None and isinstance(new_cycle, (int, float)):
                cycle = max(cycle, int(new_cycle))
            if t == "review.verdict":
                coerced = _coerce_verdict_str(evt.get("status"))
                if coerced is not None:
                    final_verdict = coerced
        # Track build/review/repair events for action status
        elif t == "build_group.started":
            action_status = "Building"
        elif t == "build_group.completed":
            action_status = "Building"
        elif t == "review.started":
            action_status = "Reviewing"
        elif t == "review.passed":
            action_status = "Evaluating the result"
        elif t == "review.failed":
            action_status = "Adjusting based on review"
        elif t == "repair.started":
            action_status = "Repairing the Qode"
        elif t == "repair.completed":
            action_status = "Building"
        elif t == "plan.created":
            action_status = "Creating build groups"
        # Also track cycle from any event that has a cycle field
        elif evt.get("cycle") is not None:
            nc = evt.get("cycle")
            if isinstance(nc, (int, float)):
                cycle = max(cycle, int(nc))

    # final.json is authoritative — always re-read it
    if final_data:
        fd_status = final_data.get("status", status)
        # A malformed review/final payload may put a non-string 'status'
        # (dict, int, list) here. Coerce to a safe string so downstream
        # .lower()/comparisons can never crash while entering review phase.
        _coerced_status = _coerce_verdict_str(fd_status)
        status = _coerced_status if _coerced_status is not None else (
            fd_status if isinstance(fd_status, str) else str(status)
        )
        fd_cycle = final_data.get("cycle")
        # Guard malformed cycle (non-numeric) so the read model never crashes
        # while finalizing/entering the review phase.
        if fd_cycle is not None:
            try:
                cycle = max(cycle, int(fd_cycle))
            except (TypeError, ValueError):
                pass
        fd_verdict = final_data.get("final_verdict")
        if isinstance(fd_verdict, dict):
            fv = fd_verdict.get("status")
            if fv:
                final_verdict = fv
        elif isinstance(fd_verdict, str) and fd_verdict.strip():
            final_verdict = fd_verdict.strip()

    # If the run is in a terminal fully-done state, unconditionally force
    # action_status to FULLY_DONE regardless of any earlier non-terminal value
    # (e.g. a stale 'Evaluating the result') so the Act: bar shows green.
    if (final_verdict == "FULLY_DONE"
            or str(status).lower() in ("done", "completed", "fully_done")
            or (final_data and str(final_data.get("status", "")).lower() == "done")):
        action_status = "FULLY_DONE"

    if events and not started_at:
        started_at = events[0].get("ts", 0)
    if events:
        updated_at = events[-1].get("ts", 0)

    # If no active_agent_started_at yet, use started_at as baseline
    if not active_agent_started_at:
        # Scan backwards for last active_agent_changed
        for evt in reversed(events):
            if evt.get("type") == "active_agent_changed":
                active_agent_started_at = evt.get("ts", 0)
                break
        if not active_agent_started_at:
            active_agent_started_at = started_at

    # Extract last exit code from events
    last_exit_code = None
    for evt in reversed(events):
        if evt.get("type") == "last_exit_status_updated":
            last_exit_code = evt.get("exit_code")
            break
        elif evt.get("type") == "agent.call.finished":
            last_exit_code = evt.get("exit_code")
            break

    # Scan events for max_cycles/max_time_seconds from run.started or config.loaded
    max_cycles_val = 0
    max_time_val = 0
    for evt in events:
        if evt.get("type") in ("run.started", "config.loaded"):
            mc = evt.get("max_cycles")
            mt = evt.get("max_time_seconds")
            if mc is not None and isinstance(mc, (int, float)):
                max_cycles_val = max(max_cycles_val, int(mc))
            if mt is not None and isinstance(mt, (int, float)):
                max_time_val = max(max_time_val, int(mt))

    max_cycles_display = "∞" if max_cycles_val == 0 else str(max_cycles_val)
    max_time_display = "∞" if max_time_val == 0 else str(max_time_val)

    return {
        "run_id": events[0].get("run_id", "") if events else "",
        "status": status,
        "final_status": final_verdict,
        "cycle": cycle,
        "max_cycles": max_cycles_val,
        "max_cycles_display": max_cycles_display,
        "max_time_seconds": max_time_val,
        "max_time_display": max_time_display,
        "started_at": started_at,
        "updated_at": updated_at,
        "active_agent": active_agent,
        "active_agent_started_at": active_agent_started_at,
        "final_verdict": final_verdict,
        "last_exit_code": last_exit_code,
        "model_code": model_code,
        "action_status": action_status,
        "action_updated_at": action_updated_at,
    }



# ---------------------------------------------------------------------------
# Agent output routing
# ---------------------------------------------------------------------------
_CANONICAL_ROLES = ("qlarifier", "instruqtor", "construqtor", "inspeqtor")
_ROLE_LABELS = {
    "qlarifier": "Qlarifier",
    "instruqtor": "instruQtor",
    "construqtor": "construQtor",
    "inspeqtor": "inspeQtor",
}
_ROLE_ALIASES = {
    "qlarifier": ["qlarifier", "clarifier", "Qlarifier", "qlr"],
    "instruqtor": ["instruqtor", "instructor", "instruQtor", "ins"],
    "construqtor": ["construqtor", "constructor", "construQtor", "con"],
    "inspeqtor": ["inspeqtor", "inspector", "inspeQtor", "insp"],
}


def _normalize_role(role: str) -> str:
    """Normalize variant role strings to canonical role key."""
    if not role:
        return ""
    if not isinstance(role, str):
        # Role can arrive as a dict/list/int in a malformed review/cycle
        # ``active_agent_changed`` event — never let it crash routing.
        return ""
    r = role.lower().strip()
    for canonical, aliases in _ROLE_ALIASES.items():
        if r in aliases:
            return canonical
    return r


def _build_agent_outputs(
    events: List[Dict[str, Any]],
    previous_outputs: Optional[Dict[str, Any]] = None,
    max_lines_per_agent: int = 2000,
) -> Dict[str, Any]:
    """Build per-agent output buffers from events.

    Routes output lines to agents based on active_agent at the time of emission.
    Preserves previous output buffers across incremental builds.

    Args:
        events: Full list of events.
        previous_outputs: Previous agent_outputs dict for continuation.
        max_lines_per_agent: Cap on lines per agent buffer.

    Returns:
        Dict with canonical agent keys, each containing role, label, model,
        status, started_at, ended_at, and lines list.
    """
    # Initialize agents
    agents: Dict[str, Any] = {}
    for role in _CANONICAL_ROLES:
        if previous_outputs and role in previous_outputs:
            agents[role] = previous_outputs[role].copy()
            # Ensure lines list exists
            if "lines" not in agents[role]:
                agents[role]["lines"] = []
        else:
            agents[role] = {
                "role": role,
                "label": _ROLE_LABELS.get(role, role),
                "model": "",
                "status": "waiting",
                "started_at": None,
                "ended_at": None,
                "lines": [],
            }

    # Track current active agent for routing output
    current_agent = "qlarifier"
    # Config-loaded models keyed by canonical role (Issue 3.6)
    cfg_models: Dict[str, str] = {}

    for evt in events:
        t = evt.get("type", "")
        ts = evt.get("ts", 0)
        ts_str = ""
        if isinstance(ts, (int, float)) and ts > 0:
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts))

        # Agent changes
        if t == "active_agent_changed":
            new_role = _normalize_role(evt.get("role", ""))
            if new_role and new_role in agents:
                # Mark previous agent as completed
                if current_agent in agents:
                    if agents[current_agent]["status"] == "active":
                        agents[current_agent]["status"] = "completed"
                        agents[current_agent]["ended_at"] = ts
                current_agent = new_role
                if agents[current_agent]["status"] == "waiting":
                    agents[current_agent]["status"] = "active"
                    agents[current_agent]["started_at"] = ts
                if evt.get("model"):
                    agents[current_agent]["model"] = evt.get("model", "")

        # Output/stream events
        elif t in ("stream.output", "agent.output", "output.line",
                    "agent_call.output", "stream.line", "stream_chunk",
                    "agent.stream", "agent_log", "stderr.line",
                    "stdout.line", "agent_thought", "agent_tool_call"):
            text = evt.get("text") or evt.get("output") or evt.get("line") or ""
            level = evt.get("level", "info")
            event_type = evt.get("event_type") or evt.get("subtype") or t

            if current_agent in agents:
                agents[current_agent]["lines"].append({
                    "ts": ts_str,
                    "level": level,
                    "text": str(text),
                    "event": event_type,
                })

        # Tool call input/output
        elif t in ("tool_call.start", "tool.input"):
            text = evt.get("text") or evt.get("input") or ""
            if current_agent in agents:
                agents[current_agent]["lines"].append({
                    "ts": ts_str,
                    "level": "tool",
                    "text": str(text),
                    "event": t,
                })

        elif t in ("tool_call.result", "tool.output", "tool_call.end"):
            text = evt.get("text") or evt.get("output") or evt.get("result") or ""
            if current_agent in agents:
                agents[current_agent]["lines"].append({
                    "ts": ts_str,
                    "level": "tool",
                    "text": str(text),
                    "event": t,
                })

        # Agent call finished
        elif t in ("agent.call.finished", "agent_call.finished"):
            if current_agent in agents and agents[current_agent]["status"] == "active":
                agents[current_agent]["status"] = "completed"
                agents[current_agent]["ended_at"] = ts

        # Run completion: all agents done
        elif t in ("run.completed", "run.finished", "run.done"):
            for role in agents:
                if agents[role]["status"] == "active":
                    agents[role]["status"] = "completed"
                    agents[role]["ended_at"] = ts
            # The final agent gets FULLY_DONE
            if current_agent in agents:
                agents[current_agent]["status"] = "completed"

        # Run abort/fail
        elif t in ("run.aborted", "run.failed"):
            for role in agents:
                if agents[role]["status"] == "active":
                    agents[role]["status"] = "failed"
                    agents[role]["ended_at"] = ts

        # Config loaded: gather per-role models for later backfill (Issue 3.6)
        elif t == "config.loaded":
            models_dict = evt.get("models", {}) or {}
            if isinstance(models_dict, dict):
                for role, model in models_dict.items():
                    norm = _normalize_role(role)
                    if norm in agents and model:
                        cfg_models[norm] = model

    # Backfill model info per role from collected config.loaded models (Issue
    # 3.6), only when the model was not already set on the agent (e.g. from
    # active_agent_changed or call_id activity).
    for role in agents:
        if not agents[role].get("model") and role in cfg_models:
            agents[role]["model"] = cfg_models[role]
    # Ensure a missing 'lines' list is never None
    for role in agents:
        if "lines" not in agents[role] or agents[role]["lines"] is None:
            agents[role]["lines"] = []

    # Cap lines per agent
    for role in agents:
        lines = agents[role]["lines"] or []
        if len(lines) > max_lines_per_agent:
            agents[role]["lines"] = lines[-max_lines_per_agent:]

    return agents


def _build_agent_outputs_incremental(
    new_events: List[Dict[str, Any]],
    previous_outputs: Dict[str, Any],
    current_active_agent: str = "",
) -> Dict[str, Any]:
    """Incrementally update agent_outputs with new events only.

    Args:
        new_events: Only the new events since last build.
        previous_outputs: Existing agent_outputs dict.
        current_active_agent: Current active agent from run info.

    Returns:
        Updated agent_outputs dict.
    """
    # Deep copy and update
    import copy
    agents = copy.deepcopy(previous_outputs)

    current_agent = current_active_agent or "qlarifier"
    # Config-loaded models keyed by canonical role (Issue 3.6)
    cfg_models: Dict[str, str] = {}

    for evt in new_events:
        t = evt.get("type", "")
        ts = evt.get("ts", 0)
        ts_str = ""
        if isinstance(ts, (int, float)) and ts > 0:
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts))

        if t == "active_agent_changed":
            new_role = _normalize_role(evt.get("role", ""))
            if new_role and new_role in agents:
                if current_agent in agents:
                    if agents[current_agent].get("status") == "active":
                        agents[current_agent]["status"] = "completed"
                        agents[current_agent]["ended_at"] = ts
                current_agent = new_role
                if agents[current_agent].get("status") == "waiting":
                    agents[current_agent]["status"] = "active"
                    agents[current_agent]["started_at"] = ts
                if evt.get("model"):
                    agents[current_agent]["model"] = evt.get("model", "")

        elif t in ("stream.output", "agent.output", "output.line",
                    "agent_call.output", "stream.line", "stream_chunk",
                    "agent.stream", "agent_log", "stderr.line",
                    "stdout.line", "agent_thought", "agent_tool_call",
                    "tool_call.start", "tool.input", "tool_call.result",
                    "tool.output", "tool_call.end"):
            text = evt.get("text") or evt.get("output") or evt.get(
                "line") or evt.get("input") or evt.get("result") or ""
            level = evt.get("level", "info")
            event_type = evt.get("event_type") or evt.get("subtype") or t

            if current_agent in agents:
                agents[current_agent].setdefault("lines", []).append({
                    "ts": ts_str,
                    "level": level,
                    "text": str(text),
                    "event": event_type,
                })

        elif t in ("agent.call.finished", "agent_call.finished"):
            if current_agent in agents and agents[current_agent].get("status") == "active":
                agents[current_agent]["status"] = "completed"
                agents[current_agent]["ended_at"] = ts

        elif t in ("run.completed", "run.done"):
            for role in agents:
                if agents[role].get("status") == "active":
                    agents[role]["status"] = "completed"
                    agents[role]["ended_at"] = ts

        elif t in ("run.aborted", "run.failed"):
            for role in agents:
                if agents[role].get("status") == "active":
                    agents[role]["status"] = "failed"
                    agents[role]["ended_at"] = ts

        # Config loaded: gather per-role models for later backfill (Issue 3.6)
        elif t == "config.loaded":
            models_dict = evt.get("models", {}) or {}
            if isinstance(models_dict, dict):
                for role, model in models_dict.items():
                    norm = _normalize_role(role)
                    if norm in agents and model:
                        cfg_models[norm] = model

    # Backfill model info per role from collected config.loaded models (Issue
    # 3.6), only when the model was not already set on the agent.
    for role in agents:
        if not agents[role].get("model") and role in cfg_models:
            agents[role]["model"] = cfg_models[role]

    # Cap lines
    for role in agents:
        lines = agents[role].get("lines", []) or []
        if len(lines) > 2000:
            agents[role]["lines"] = lines[-2000:]

    return agents

def _build_groups_from_plan(plan_data: Optional[Dict[str, Any]],
                            events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build group-level cards from plan + events."""
    if not plan_data:
        return []

    groups: List[Dict[str, Any]] = []
    bg_map = plan_data.get("build_groups", {})
    briq_map = plan_data.get("briqs", {})
    # Never assume build_groups/briqs are dicts — malformed plans must not
    # crash the read model (they were already tolerated at the file level).
    if not isinstance(bg_map, dict):
        bg_map = {}
    if not isinstance(briq_map, dict):
        briq_map = {}

    # Collect status changes from events
    group_statuses: Dict[str, str] = {}
    briq_statuses: Dict[str, str] = {}
    for evt in events:
        t = evt.get("type", "")
        gid = _coerce_uid(evt.get("build_group_id"))
        bid = _coerce_uid(evt.get("briq_id"))

        if t == "build_group.queued" and gid:
            group_statuses[gid] = "planned"
        elif t == "build_group.started" and gid:
            group_statuses[gid] = "building"
        elif t == "build_group.completed" and gid:
            group_statuses[gid] = "ready_for_review"
            # Mark all briqs in this group as done (from plan data)
            bg = bg_map.get(gid, {})
            if isinstance(bg, dict):
                for briq_id in bg.get("briq_ids", []) or []:
                    briq_statuses[briq_id] = "done"
        elif t == "build_group.failed" and gid:
            group_statuses[gid] = "repair_needed"
        elif t == "build_group.merged" and gid:
            group_statuses[gid] = "done"
        elif t == "build_group.merge_failed" and gid:
            group_statuses[gid] = "repair_needed"
        elif t == "build.failed" and gid:
            group_statuses[gid] = "repair_needed"
        elif t == "harness.started" and gid:
            group_statuses[gid] = "validating"
        elif t == "harness.completed" and gid:
            group_statuses[gid] = "validating"
        elif t == "harness.failed" and gid:
            group_statuses[gid] = "repair_needed"
        elif t == "briq.status_changed" and bid:
            briq_statuses[bid] = evt.get("status", "pending")
        # Review events
        elif t == "review.started" and gid:
            group_statuses[gid] = "reviewing"
        elif t == "review.completed" and gid:
            group_statuses[gid] = "ready_for_review"
        elif t == "review.passed" and gid:
            group_statuses[gid] = "done"
        elif t == "review.failed" and gid:
            group_statuses[gid] = "repair_needed"
        # Repair events
        elif t == "repair.started" and gid:
            group_statuses[gid] = "repairing"
        elif t == "repair.completed" and gid:
            group_statuses[gid] = "ready_for_review"
        # Inspection events
        elif t == "inspection.completed" and gid:
            score = evt.get("score")
            if score is not None and isinstance(score, (int, float)):
                if score >= 80:
                    group_statuses[gid] = "done"
                else:
                    group_statuses[gid] = "repair_needed"
        # Done events
        elif t == "group.done" and gid:
            group_statuses[gid] = "done"

    # Track cycle per group from events
    group_cycles: Dict[str, int] = {}
    for evt in events:
        gid = _coerce_uid(evt.get("build_group_id"))
        evt_cycle = evt.get("cycle")
        # Cycle may be absent or malformed (e.g. a string in review/cycle
        # events). Only a numeric cycle contributes — never let a bad value
        # propagate an exception out of the build.
        if gid and isinstance(evt_cycle, (int, float)):
            group_cycles[gid] = max(group_cycles.get(gid, 0), int(evt_cycle))

    # Build groups
    for bg_id, bg in bg_map.items():
        if not isinstance(bg, dict):
            continue
        raw_briq_ids = bg.get("briq_ids", []) or []
        # A malformed plan may put a non-list here (None, dict, scalar).
        # Only iterate a real list — never let it crash or iterate a string.
        briq_ids = [str(b) for b in raw_briq_ids] if isinstance(raw_briq_ids, list) else []
        briqs = []
        all_done = True
        any_needs_repair = False
        any_in_progress = False
        any_awaiting_review = False

        for bid in briq_ids:
            briq = briq_map.get(bid, {})
            if not isinstance(briq, dict):
                briq = {}
            b_status = briq_statuses.get(bid, briq.get("status", "pending"))
            briqs.append({
                "id": briq.get("id", bid),
                "safe_id": briq.get("safe_id", bid),
                "title": briq.get("title", ""),
                "description": briq.get("description", ""),
                "status": b_status,
                "sensitivity": briq.get("sensitivity", 0),
                "depends_on": briq.get("depends_on", []),
                "expected_files": briq.get("expected_files", []),
            })
            if b_status not in ("done",):
                all_done = False
            if b_status in ("needs_repair", "failed"):
                any_needs_repair = True
            if b_status in ("in_progress",):
                any_in_progress = True
            if b_status in ("awaiting_review",):
                any_awaiting_review = True

        # Derive group status
        g_status = group_statuses.get(bg_id, "planned")
        
        # Check for inspeqtor_approved briqs from events
        inspeqtor_approved_briqs = set()
        for evt in events:
            if evt.get("type") == "briq.status_changed" and evt.get("source") == "inspeqtor_approved":
                bid = _coerce_uid(evt.get("briq_id"))
                if bid and bid in briq_ids:
                    inspeqtor_approved_briqs.add(bid)
        
        all_inspeqtor_approved = len(inspeqtor_approved_briqs) == len(briq_ids) if briq_ids else False
        
        # all_done should only auto-promote to "done" when no explicit
        # review/repair flow status has been set.  This prevents
        # build_group.completed (which marks briqs as done) from
        # overriding "ready_for_review" back to "done".
        review_flow_statuses = (
            "ready_for_review", "reviewing", "repair_needed",
            "repairing", "validation_failed",
        )
        is_review_flow = g_status in review_flow_statuses
        
        # If all briqs inspeqtor_approved, force done regardless
        if all_inspeqtor_approved:
            g_status = "done"
        elif all_done and not is_review_flow:
            g_status = "done"
        elif any_needs_repair:
            g_status = "repair_needed"
        elif any_awaiting_review:
            g_status = "ready_for_review"
        elif any_in_progress:
            g_status = "building"

        # Check for repair events targeting this group only if no later done signal
        latest_repair_idx = -1
        latest_done_idx = -1
        for idx, evt in enumerate(events):
            t = evt.get("type", "")
            gid_evt = _coerce_uid(evt.get("build_group_id"))
            if gid_evt == bg_id:
                if t == "repair.issues_mapped" and evt.get("issue_count", 0) > 0:
                    latest_repair_idx = max(latest_repair_idx, idx)
                elif t == "repair.started":
                    latest_repair_idx = max(latest_repair_idx, idx)
                elif t in ("review.passed", "inspection.completed", "group.done",
                           "build_group.merged", "briq.status_changed"):
                    # Check if this is a done signal
                    if t == "review.passed":
                        latest_done_idx = max(latest_done_idx, idx)
                    elif t == "inspection.completed":
                        _score = evt.get("score")
                        if isinstance(_score, (int, float)) and _score >= 80:
                            latest_done_idx = max(latest_done_idx, idx)
                    elif t == "group.done":
                        latest_done_idx = max(latest_done_idx, idx)
                    elif t == "build_group.merged":
                        latest_done_idx = max(latest_done_idx, idx)
                    elif t == "briq.status_changed" and evt.get("source") == "inspeqtor_approved":
                        latest_done_idx = max(latest_done_idx, idx)
        
        # Also check global done signals
        for idx, evt in enumerate(events):
            t = evt.get("type", "")
            if t == "run.completed":
                latest_done_idx = max(latest_done_idx, idx)
            elif t == "review.verdict":
                status = evt.get("status", "")
                # 'status' may be a dict/int/None in malformed review payloads;
                # only a truthy string counts as a done signal.
                if isinstance(status, str) and status.strip().upper() in ("FULLY_DONE", "PASSED"):
                    latest_done_idx = max(latest_done_idx, idx)
        
        if latest_repair_idx >= 0 and latest_done_idx > latest_repair_idx:
            # Later done signal wins
            if g_status in ("repair_needed", "repairing"):
                g_status = "done"
        elif latest_repair_idx >= 0 and g_status not in ("done",):
            g_status = "repair_needed"

        # The intermediate 'ready_for_review' state must never surface to the
        # GUI.  Keep it only as an internal marker; map it to 'building' while
        # the run is still building (some tickets not yet ready) and drive it
        # straight to 'reviewing' once every ticket in the group is ready.
        if g_status in ("ready_for_review",):
            if all_done and not any_awaiting_review:
                g_status = "reviewing"
            else:
                g_status = "building"

        progress_weight = bg.get("progress_weight_pct")
        groups.append({
            "id": bg.get("id", bg_id),
            "safe_id": bg.get("safe_id", bg_id),
            "title": bg.get("name", bg_id),
            "description": bg.get("description", ""),
            "parallel_safe": bg.get("parallel_safe", False),
            "status": g_status,
            "cycle": group_cycles.get(bg_id, 1),
            "attempts": 0,
            "briqs": briqs,
            "progress_weight_pct": progress_weight if isinstance(progress_weight, (int, float)) else None,
            "validation": {
                "status": "not_available",
                "summary": "",
                "checks": [],
            },
            "review": {
                "status": "not_reviewed",
                "score": None,
                "issues": [],
            },
            "links": {
                "worktree_path": "",
                "branch": "",
                "snapshot_paths": [],
            },
        })

    return groups




def _maybe_recover_callback(run_root: str, run_info: dict, state_dir: str) -> None:
    """If run is terminal but callback hasn't been sent, trigger recovery.

    Handles ALL terminal states: FULLY_DONE, failed, aborted, etc.
    Safe to call on every read model build — callback system handles
    exactly-once semantics internally. Non-blocking (background thread).
    """
    import os as _os
    # Check for any terminal status: done, failed, aborted, etc.
    terminal_statuses = (
        "done", "completed", "FULLY_DONE", "success", "accepted", "DONE",
        "failed", "aborted", "finished_incomplete", "process_failed",
        "launch_failed", "failed_early",
    )
    _st = run_info.get("status", "")
    if not isinstance(_st, str):
        _st = str(_st) if _st is not None else ""
    status_lower = _st.lower()
    if status_lower not in terminal_statuses:
        # Also check if final.json exists (terminal but status not yet reflected)
        final_path = _os.path.join(state_dir, "final.json")
        if not _os.path.isfile(final_path):
            return

    # Check if origin.json exists (callback only for API-triggered runs)
    origin_path = _os.path.join(state_dir, "origin.json")
    if not _os.path.isfile(origin_path):
        return

    # Trigger non-blocking callback recovery
    try:
        from qq.completion_callback import maybe_send_completion_callback_async
        maybe_send_completion_callback_async(run_root)
    except Exception:
        pass


def _planned_briq_total(plan_data, groups):
    """Calculate total planned briQs across all groups, deduplicating by ID.
    
    Priority:
      1. Count unique briq_ids across plan_data["build_groups"]
      2. If zero, count unique briQ IDs across groups[*].briqs
      3. If zero, fallback to len(plan_data["briqs"]) if dict/list
      4. Final fallback: sum(len(g["briqs"]) for g in groups)
    """
    unique_ids = set()

    if plan_data:
        bg_raw = plan_data.get("build_groups") or {}
        if isinstance(bg_raw, dict):
            bg_iter = bg_raw.values()
        elif isinstance(bg_raw, list):
            bg_iter = bg_raw
        else:
            bg_iter = []

        for bg in bg_iter:
            if not isinstance(bg, dict):
                continue
            for bid in bg.get("briq_ids") or []:
                if bid:
                    unique_ids.add(str(bid))

        if unique_ids:
            return len(unique_ids)

    for g in groups or []:
        for b in g.get("briqs", []) or []:
            bid = b.get("id") or b.get("safe_id") or b.get("title")
            if bid:
                unique_ids.add(str(bid))

    if unique_ids:
        return len(unique_ids)

    if plan_data:
        briqs_raw = plan_data.get("briqs")
        if isinstance(briqs_raw, dict):
            return len(briqs_raw)
        if isinstance(briqs_raw, list):
            return len(briqs_raw)

    return sum(len(g.get("briqs", []) or []) for g in groups or [])


def build_read_model(run_root: str) -> Dict[str, Any]:
    """Build the full read model for a QonQrete run.

    This is a thin, never-throwing wrapper around :func:`_build_read_model_impl`.
    If anything inside the build (event parsing, group/action status resolution,
    final-status resolution, progress calculation) raises for any reason —
    especially on a malformed review/inspeQtor/cycle event during the
    reviewing phase — we must never 502/500 the web UI.  We catch it here and
    return a structurally-valid model with an ``error`` marker so the API can
    keep serving HTTP 200 with a JSON payload instead of crashing the server.
    """
    try:
        return _build_read_model_impl(run_root)
    except Exception as exc:  # noqa: BLE001 — last line of defence for the GUI
        # Invalidate this run's cache so we don't serve a stale/corrupt model.
        try:
            get_read_model_cache().invalidate(run_root)
        except Exception:
            pass
        return {
            "schema_version": SCHEMA_VERSION,
            "source_of_truth": "qonqrete",
            "run": {
                "run_id": "",
                "status": "running",
                "final_status": None,
                "cycle": 1,
                "max_cycles": 0,
                "max_cycles_display": "∞",
                "max_time_seconds": 0,
                "max_time_display": "∞",
                "started_at": 0,
                "updated_at": 0,
                "active_agent": "qlarifier",
                "active_agent_started_at": 0,
                "final_verdict": None,
                "last_exit_code": None,
                "model_code": "?",
                "action_status": "Building",
                "action_updated_at": 0,
            },
            "display_name": "QonQrete run",
            "task_title": "",
            "runner_metadata": {
                "mode": "unknown", "session": "", "started_at": "",
                "finished_at": "", "pid": None, "command": "", "yolo": None,
            },
            "task": {"raw_text": "", "clarified_text": "", "plan_summary": "",
                     "original_user_task": "", "enhanced_clarified_task": ""},
            "build_groups": [],
            "metrics": {
                "total_groups": 0, "groups_done": 0,
                "total_groups_planned": 0, "total_groups_known": False,
                "total_briqs": 0, "briqs_done": 0,
                "total_briqs_planned": 0, "total_briqs_known": False,
                "cycle_count": 1, "harness_passed": None,
                "latest_inspeqtor_score": None,
                "instruqtor_progress_pct": 0.0, "effective_progress_pct": 0.0,
            },
            "progress": {
                "accepted_pct": 0.0, "working_pct": 0.0,
                "displayed_pct": 0.0, "progress_pct": 0.0,
                "inspeqtor_quality_pct": None, "quality_confidence": "unknown",
                "confidence": "provisional", "phase": "clarification",
                "source": "hybrid_group_lifecycle",
                "components": {
                    "clarification_pct": 0.0, "planning_pct": 0.0,
                    "build_review_working_pct": 0.0,
                    "build_review_accepted_pct": 0.0, "finalization_pct": 0.0,
                },
                "groups": [],
            },
            "agent_outputs": {},
            "events_tail": [],
            "error": f"read_model.build_read_model failed: {type(exc).__name__}: {exc}",
        }


def _build_read_model_impl(run_root: str) -> Dict[str, Any]:
    """Build the full read model for a QonQrete run.

    Uses incremental caching: on subsequent calls with the same run_root,
    only new events since the last call are parsed. Static artifacts
    (plan.json, task.json, etc.) are re-read only when their mtimes change
    or when final.json appears (run completion).

    Supports control-root mode: if run_root is a control root and contains
    current-run.json, redirect to the active run's root.

    Args:
        run_root: Absolute path to .qq/runs/<run-id>/ or control root

    Returns:
        Stable JSON-serializable dict (schema_version 1).
    """
    cache = get_read_model_cache()

    # Control-root resolution: if this is a control root, follow the pointer
    original_root = run_root
    current_run_path = os.path.join(run_root, "current-run.json")
    if os.path.isfile(current_run_path):
        try:
            with open(current_run_path, "r") as f:
                cr = json.load(f)
            active = cr.get("run_root")
            if active and os.path.isdir(active):
                run_root = active
        except (json.JSONDecodeError, OSError):
            pass

    # Resolve state directory
    state_dir = os.path.join(run_root, "state")
    if not os.path.isdir(state_dir):
        state_dir = run_root

    events_path = os.path.join(run_root, "events.jsonl")
    task_path = os.path.join(state_dir, "task.json")
    clarified_path = os.path.join(state_dir, "clarified_task.json")
    plan_path = os.path.join(state_dir, "plan.json")
    final_path = os.path.join(state_dir, "final.json")

    # Check if static artifacts changed → full rebuild needed
    artifacts = {
        "task": task_path,
        "clarified": clarified_path,
        "plan": plan_path,
        "final": final_path,
    }
    need_full_rebuild = cache.artifacts_changed(run_root, artifacts)

    # Track whether we have new incremental data to apply
    has_new_incremental = False
    task_data_from_cache = None
    clarified_data_from_cache = None
    plan_data_from_cache = None
    events_data: List[Dict[str, Any]] = []  # Always initialized
    
    if need_full_rebuild:
        # Full rebuild from scratch — read all events
        events_data, new_pos = _safe_read_jsonl(events_path, 0)
        need_full_rebuild = False
    else:
        # Incremental: only read new events since last position
        prev_pos = cache.get_events_position(run_root)
        new_events, new_pos = _safe_read_jsonl(events_path, prev_pos)

        if new_events:
            # We have new events — need to rebuild
            has_new_incremental = True
            # Always do a full re-read of events for correct group/briq status derivation
            # The incremental position tracking is still used for the cache pos above
            events_data, _ = _safe_read_jsonl(events_path, 0)
            
            # Reuse static data from cache when artifacts haven't changed
            cached = cache.get(run_root, ttl=0)  # Don't apply TTL here
            if cached is not None:
                task_data_from_cache = cached.get("_task_raw")
                clarified_data_from_cache = cached.get("_clarified_raw")
                plan_data_from_cache = cached.get("_plan_raw")
        # else: no new events, can use TTL cache below (fast path)

    # Read static artifacts (use cached versions when available)
    task_data = task_data_from_cache if task_data_from_cache is not None else _safe_read_json(task_path)
    clarified_data = clarified_data_from_cache if clarified_data_from_cache is not None else _safe_read_json(clarified_path)
    plan_data = plan_data_from_cache if plan_data_from_cache is not None else _safe_read_json(plan_path)
    final_data = _safe_read_json(final_path)

    # TTL fast path: only when we have NO new events AND cache is still valid
    if not has_new_incremental and not need_full_rebuild:
        cached_ttl = cache.get(run_root, ttl=1.0)
        if cached_ttl is not None:
            return {k: v for k, v in cached_ttl.items() if not k.startswith("_")}
        # TTL expired — need to read all events for a fresh build
        events_data, new_pos = _safe_read_jsonl(events_path, 0)

    # Build run info
    run_info = _derive_run_status(events_data, final_data)

    # Build groups
    groups = _build_groups_from_plan(plan_data, events_data)

    # Metrics
    total_groups = len(groups)
    groups_done = sum(1 for g in groups if g.get("status") in _DONE_GROUP_STATUSES)

    # FULLY_DONE forcing: when run is terminal-success, override display metrics
    _is_terminal_success = (
        (run_info.get("final_status") or "").upper() == "FULLY_DONE"
        or run_info.get("status", "") in ("done", "completed")
    )
    if _is_terminal_success:
        # Force all groups to count as done for display
        groups_done = max(groups_done, total_groups) if total_groups > 0 else groups_done

    # ── Normalize progress weights ──
    # If any group has an explicit progress_weight_pct, normalize to 100.
    # Otherwise fall back to equal weights.
    weight_vals = [g.get("progress_weight_pct") for g in groups]
    has_explicit_weights = any(isinstance(w, (int, float)) for w in weight_vals)
    if has_explicit_weights:
        # Fill in missing weights with 0
        for g in groups:
            if not isinstance(g.get("progress_weight_pct"), (int, float)):
                g["progress_weight_pct"] = 0.0
        # Normalize to 100
        total_weight = sum(g.get("progress_weight_pct", 0.0) for g in groups)
        if total_weight > 0:
            for g in groups:
                g["progress_weight_pct"] = round(
                    g.get("progress_weight_pct", 0.0) * 100.0 / total_weight, 2
                )
    else:
        # Equal weight
        if total_groups > 0:
            eq_weight = round(100.0 / total_groups, 2)
            for g in groups:
                g["progress_weight_pct"] = eq_weight

    # ── Compute instruQtor progress ──
    instruqtor_progress_pct = 0.0
    for g in groups:
        if g["status"] in ("done", "completed", "merged", "fully_done", "success", "valid_done"):
            instruqtor_progress_pct += g.get("progress_weight_pct", 0.0)
    instruqtor_progress_pct = round(max(0.0, min(100.0, instruqtor_progress_pct)), 1)
    total_briqs = _planned_briq_total(plan_data, groups)
    briqs_done = sum(
        len(g.get("briqs", []) or [])
        for g in groups
        if g.get("status") in _DONE_GROUP_STATUSES
    )
    # FULLY_DONE forcing: all briqs count as done
    if _is_terminal_success:
        briqs_done = max(briqs_done, total_briqs) if total_briqs > 0 else briqs_done

    # Latest InspeQtor score
    latest_score = None
    for evt in reversed(events_data):
        if evt.get("type") == "inspection_score_recorded":
            latest_score = evt.get("score")
            break

    # Events tail (last 50, most recent first)
    events_tail = events_data[-50:][::-1]

    # ── Build agent outputs ──
    # Get previous agent outputs from cache for incremental update
    cached_model = cache.get(run_root, ttl=0)
    previous_agent_outputs = cached_model.get("agent_outputs") if cached_model else None
    agent_outputs = _build_agent_outputs(events_data, previous_outputs=previous_agent_outputs)

    # ── Compute canonical progress ──
    progress_snapshot = calculate_progress(
        groups=groups,
        active_agent=run_info.get("active_agent", ""),
        final_verdict=run_info.get("final_verdict"),
        run_status=run_info.get("status", "running"),
        inspeqtor_score=latest_score,
    )
    progress_dict = progress_snapshot.to_dict()

    model = {
        "schema_version": SCHEMA_VERSION,
        "source_of_truth": "qonqrete",
        "run": run_info,
        "display_name": resolve_display_name(run_root),
        "task_title": resolve_display_name(run_root),
        "runner_metadata": resolve_runner_metadata(run_root),
        "task": {
            "raw_text": (task_data or {}).get("raw_text", ""),
            "clarified_text": (clarified_data or {}).get("clarified_text", ""),
            "plan_summary": (plan_data or {}).get("summary", ""),
            "original_user_task": (task_data or {}).get("raw_text", ""),
            "enhanced_clarified_task": (clarified_data or {}).get("clarified_text", ""),
        },
        "build_groups": groups,
        "metrics": {
            "total_groups": total_groups,
            "groups_done": groups_done,
            "total_groups_planned": total_groups,
            "total_groups_known": total_groups > 0,
            "total_briqs": total_briqs,
            "briqs_done": briqs_done,
            "total_briqs_planned": total_briqs,
            "total_briqs_known": total_briqs > 0,
            "cycle_count": run_info["cycle"],
            "harness_passed": None,
            "latest_inspeqtor_score": latest_score,
            "instruqtor_progress_pct": instruqtor_progress_pct,
            "effective_progress_pct": progress_dict["displayed_pct"],
        },
        "progress": progress_dict,
        "agent_outputs": agent_outputs,
        "events_tail": events_tail,
        # Internal: store raw data for incremental patching
        "_task_raw": task_data,
        "_clarified_raw": clarified_data,
        "_plan_raw": plan_data,
    }

    # Recovery: if run is FULLY_DONE and callback may not have been sent, trigger it
    _maybe_recover_callback(run_root, run_info, state_dir)

    # Update cache (include internal fields for incremental patching)
    cache.set(run_root, model)
    cache.set_events_position(run_root, new_pos)

    # Strip internal cache keys before returning to caller
    clean_model = {k: v for k, v in model.items() if not k.startswith("_")}
    return clean_model
