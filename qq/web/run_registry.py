"""
Canonical run registry and lifecycle resolver for QonQrete.

Centralizes all common lifecycle logic: canonical state sets, run record
loading/folding, state resolution, record merging, newest-run selection,
and process-shared locking.

Move all common lifecycle logic here. Do not leave separate, slightly
different implementations in api.py, cli.py, and ingest.py.
"""

from __future__ import annotations

import datetime
import fcntl
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Canonical state sets
# ---------------------------------------------------------------------------

ACTIVE_STATES: Set[str] = {
    "starting",
    "started",
    "running",
}

PENDING_STATES: Set[str] = {
    "accepted",
    "queued",
}

TERMINAL_STATES: Set[str] = {
    "finished",
    "fully_done",
    "done",
    "failed",
    "failed_early",
    "finished_incomplete",
    "aborted",
    "cancelled",
    "canceled",
    "stale",
    "launch_failed",
    "pointer_failed",
    "superseded",
    "orphaned",
}

# States that block new dedupe (non-terminal)
ACTIVE_DEDUPE_STATES: Set[str] = {"starting", "started", "running", "queued", "accepted"}

# Lower-case index for case-insensitive checks
_TERMINAL_LOWER: Set[str] = {s.lower() for s in TERMINAL_STATES}
_ACTIVE_LOWER: Set[str] = {s.lower() for s in ACTIVE_STATES}
_PENDING_LOWER: Set[str] = {s.lower() for s in PENDING_STATES}


def is_terminal_state(state: Optional[str]) -> bool:
    """Check if a state string represents a terminal state (case-insensitive)."""
    if not state:
        return False
    return state.lower() in _TERMINAL_LOWER


def is_active_state(state: Optional[str]) -> bool:
    """Check if a state string represents an active state (case-insensitive)."""
    if not state:
        return False
    return state.lower() in _ACTIVE_LOWER


def is_pending_state(state: Optional[str]) -> bool:
    """Check if a state string represents a pending state (case-insensitive)."""
    if not state:
        return False
    return state.lower() in _PENDING_LOWER


def normalize_state(state: Optional[str]) -> Optional[str]:
    """Normalize a state string to its canonical lower-case form."""
    if not state:
        return None
    return state.lower()


# ---------------------------------------------------------------------------
# Timestamp / run ID parsing
# ---------------------------------------------------------------------------

# Supported run ID formats:
#   YYYYMMDD-HHMMSS-xxxxxxxx
#   YYYY-MM-DD_HH-MM-SS_xxxxxxxx
#   legacy variants

_RUN_ID_PATTERNS = [
    re.compile(r'^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-[\w]{8,}$'),   # 20260710-140530-abcd1234
    re.compile(r'^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})_[\w]{8,}$'),  # 2026-07-10_14-05-30_abcd1234
    re.compile(r'^(\d{4})-(\d{2})-(\d{2})[\s_T](\d{2}):?(\d{2}):?(\d{2})'),     # ISO-ish prefix
]


def _run_id_to_sort_key(run_id: Optional[str]) -> float:
    """Convert a run_id to a numeric sort key (higher = newer)."""
    if not run_id:
        return 0.0
    for pat in _RUN_ID_PATTERNS:
        m = pat.match(run_id)
        if m:
            try:
                parts = [int(g) for g in m.groups()]
                dt = datetime.datetime(*parts[:6])
                return dt.timestamp()
            except (ValueError, OverflowError):
                pass
    return 0.0


def _iso_to_sort_key(iso_str: Optional[str]) -> float:
    """Convert an ISO timestamp string to a numeric sort key."""
    if not iso_str:
        return 0.0
    try:
        # Handle various ISO formats
        s = iso_str.strip().replace('Z', '+00:00')
        # Try standard parsing
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y%m%dT%H%M%S",
        ):
            try:
                if fmt.endswith('%z'):
                    dt = datetime.datetime.strptime(s, fmt)
                else:
                    dt = datetime.datetime.strptime(s, fmt)
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt.timestamp()
            except ValueError:
                continue
        # Try fromisoformat
        try:
            return datetime.datetime.fromisoformat(s).timestamp()
        except (ValueError, TypeError):
            pass
    except Exception:
        pass
    return 0.0


def resolve_run_timestamp(entry: Dict[str, Any]) -> float:
    """Resolve the best timestamp for a run entry.

    Prefers, in order:
    - explicit created_at
    - explicit started_at
    - accepted_at
    - run_id date/time
    - final fallback: 0.0
    """
    for key in ("created_at", "started_at", "accepted_at"):
        val = entry.get(key, "")
        if val:
            ts = _iso_to_sort_key(str(val))
            if ts > 0:
                return ts
    rid = entry.get("run_id", "")
    if rid:
        ts = _run_id_to_sort_key(rid)
        if ts > 0:
            return ts
    return 0.0


# ---------------------------------------------------------------------------
# JSONL loading with last-record-wins folding
# ---------------------------------------------------------------------------

def load_latest_run_records(control_root: str) -> Dict[str, Dict[str, Any]]:
    """Read runs.jsonl once and fold entries by run_id.

    Since runs.jsonl is append-only, later matching records win.
    Preserves stable metadata from earlier entries when later
    lifecycle entries omit fields, but later lifecycle/state fields
    always replace earlier ones.
    """
    records: Dict[str, Dict[str, Any]] = {}
    runs_path = os.path.join(control_root, "runs.jsonl")
    if not os.path.isfile(runs_path):
        return records

    try:
        with open(runs_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = entry.get("run_id", "")
                if not rid:
                    continue
                if rid not in records:
                    records[rid] = entry
                else:
                    # Merge: later entry wins for lifecycle/state fields,
                    # but preserve stable metadata from earlier entries
                    _merge_later_wins(records[rid], entry)
    except OSError:
        pass

    return records


def load_latest_tmux_records(control_root: str) -> Dict[str, Dict[str, Any]]:
    """Read tmux-sessions.jsonl with last-record-wins by session name."""
    records: Dict[str, Dict[str, Any]] = {}
    tmux_path = os.path.join(control_root, "tmux-sessions.jsonl")
    if not os.path.isfile(tmux_path):
        return records

    try:
        with open(tmux_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session = entry.get("tmux_session", "")
                if not session:
                    continue
                if session not in records:
                    records[session] = entry
                else:
                    _merge_later_wins(records[session], entry)
    except OSError:
        pass

    return records


def _merge_later_wins(base: Dict[str, Any], newer: Dict[str, Any]) -> None:
    """Merge newer entry into base. Later lifecycle/state fields replace earlier ones,
    but stable metadata (run_root, task_path, target_path) is preserved from the
    first entry that provides it."""
    # Preserve stable metadata from base if not in newer
    stable_keys = {"run_root", "task_path", "target_path", "events_path",
                   "control_root", "mode", "source", "runner", "yolo",
                   "command_preview", "dedupe_key", "created_at", "accepted_at"}
    # Lifecycle keys: always let newer win
    lifecycle_keys = {"state", "started_at", "finished_at", "exit_code",
                      "superseded_at", "superseded_by_run_id", "launch_error",
                      "selection_reason", "selected_at", "queue_position",
                      "launch_generation", "launch_token", "launcher_pid",
                      "launch_claimed_at", "tmux_session", "attach_command",
                      "link_status"}

    for k, v in newer.items():
        if k in lifecycle_keys:
            base[k] = v
        elif k in stable_keys:
            if k not in base or not base[k]:
                base[k] = v
        else:
            base[k] = v


# ---------------------------------------------------------------------------
# Run state resolution from durable evidence
# ---------------------------------------------------------------------------

def resolve_run_state(
    run_entry: Dict[str, Any],
    tmux_alive: bool = False,
    runner_pid_alive: bool = False,
    control_root: str = "",
) -> str:
    """Determine state using durable evidence, in precedence order:

    a. runner.failed.json exists
    b. runner.finished + runner.exit_code exist
    c. canonical final.json / resolved final status
    d. latest runs.jsonl lifecycle record
    e. actual managed runner liveness
    f. queued/accepted metadata
    g. unknown

    A tmux session existing may enrich runner metadata but must not
    override terminal artifacts.
    """
    run_root = run_entry.get("run_root", "")
    state_from_entry = run_entry.get("state", "")

    if run_root:
        # a. runner.failed.json
        failed_path = os.path.join(run_root, "runner.failed.json")
        if os.path.isfile(failed_path):
            return "failed"

        # b. runner.finished + runner.exit_code
        finished_path = os.path.join(run_root, "runner.finished")
        exit_code_path = os.path.join(run_root, "runner.exit_code")
        if os.path.isfile(finished_path):
            if os.path.isfile(exit_code_path):
                try:
                    with open(exit_code_path) as ef:
                        ec = int(ef.read().strip())
                    if ec == 0:
                        # Check if final.json indicates FULLY_DONE
                        final_path = os.path.join(run_root, "state", "final.json")
                        if os.path.isfile(final_path):
                            try:
                                with open(final_path) as ff:
                                    final_data = json.load(ff)
                                verdict = final_data.get("final_verdict", {})
                                if isinstance(verdict, dict):
                                    vs = str(verdict.get("status", "")).upper()
                                    if vs == "FULLY_DONE":
                                        return "fully_done"
                            except Exception:
                                pass
                        return "finished"
                    return "failed"
                except (ValueError, OSError):
                    pass
            return "finished"

        # c. final.json
        final_path = os.path.join(run_root, "state", "final.json")
        if os.path.isfile(final_path):
            try:
                with open(final_path) as ff:
                    final_data = json.load(ff)
                verdict = final_data.get("final_verdict", {})
                if isinstance(verdict, dict):
                    vs = str(verdict.get("status", "")).upper()
                    if vs in ("FULLY_DONE", "DONE", "SUCCESS"):
                        return "fully_done"
                    if vs in ("ABORTED", "FAILED", "NOT_DONE"):
                        return "failed"
            except Exception:
                pass

    # d. Use the latest lifecycle record state
    if state_from_entry and is_terminal_state(state_from_entry):
        return normalize_state(state_from_entry) or "unknown"

    # e. Active runner liveness
    if is_active_state(state_from_entry):
        if tmux_alive or runner_pid_alive:
            return normalize_state(state_from_entry) or "running"
        # No liveness evidence -> stale
        return "stale"

    # f. Pending states
    if is_pending_state(state_from_entry):
        return normalize_state(state_from_entry) or "queued"

    # g. Unknown
    return state_from_entry or "unknown"


# ---------------------------------------------------------------------------
# Merge run sources into unified entries
# ---------------------------------------------------------------------------

def merge_run_sources(
    current_run_pointer: Optional[Dict[str, Any]],
    active_run_pointer: Optional[Dict[str, Any]],
    pending_run_pointer: Optional[Dict[str, Any]],
    folded_history: Dict[str, Dict[str, Any]],
    run_directories: Dict[str, Dict[str, Any]],
    tmux_records: Dict[str, Dict[str, Any]],
    live_tmux_sessions: Dict[str, Dict[str, Any]],
    control_root: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Merge all run sources into exactly one entry per run_id.

    Precedence is field-sensitive:
    - terminal artifacts win for state
    - active-run pointer identifies the executor
    - current-run pointer identifies dashboard linkage
    - tmux provides attach info and real liveness
    - folded history provides missing metadata
    - run directory provides artifact evidence
    """
    merged: Dict[str, Dict[str, Any]] = {}
    # Collect all run_ids from all sources
    all_run_ids: Set[str] = set()

    if current_run_pointer and current_run_pointer.get("run_id"):
        all_run_ids.add(current_run_pointer["run_id"])
    if active_run_pointer and active_run_pointer.get("run_id"):
        all_run_ids.add(active_run_pointer["run_id"])
    if pending_run_pointer and pending_run_pointer.get("run_id"):
        all_run_ids.add(pending_run_pointer["run_id"])
    all_run_ids.update(folded_history.keys())
    all_run_ids.update(run_directories.keys())
    # Map tmux records by run_id
    tmux_by_run_id: Dict[str, Dict[str, Any]] = {}
    for session_name, rec in tmux_records.items():
        rid = rec.get("run_id", "")
        if rid:
            tmux_by_run_id[rid] = rec
            all_run_ids.add(rid)
    for session_name, rec in live_tmux_sessions.items():
        rid = rec.get("run_id", "")
        if rid:
            tmux_by_run_id.setdefault(rid, rec)
            all_run_ids.add(rid)

    for rid in all_run_ids:
        entry: Dict[str, Any] = {"run_id": rid}

        # Merge order (later wins for lifecycle, earlier for stable metadata):
        # 1. Run directory
        # 2. Folded history
        # 3. Tmux records (metadata)
        # 4. Current-run pointer
        # 5. Active-run pointer
        # 6. Pending-run pointer
        # 7. Live tmux (attach info only)

        # 1. Run directory
        if rid in run_directories:
            rd = run_directories[rid]
            for k, v in rd.items():
                if k not in entry or not entry.get(k):
                    entry[k] = v

        # 2. Folded history (stable metadata only, state handled separately)
        if rid in folded_history:
            fh = folded_history[rid]
            for k in ("run_root", "task_path", "target_path", "events_path",
                       "control_root", "mode", "source", "runner", "yolo",
                       "command_preview", "dedupe_key", "created_at", "accepted_at",
                       "started_at", "finished_at", "exit_code", "tmux_session",
                       "attach_command"):
                if k in fh and (k not in entry or not entry.get(k)):
                    entry[k] = fh[k]

        # 3. Tmux records
        if rid in tmux_by_run_id:
            tr = tmux_by_run_id[rid]
            for k in ("tmux_session", "attach_command", "run_root", "events_path",
                       "target_path", "task_path", "control_root", "yolo", "runner"):
                if k in tr and tr[k] and (k not in entry or not entry.get(k)):
                    entry[k] = tr[k]

        # 4. Current-run pointer (dashboard linkage)
        if current_run_pointer and current_run_pointer.get("run_id") == rid:
            entry["linked"] = True
            entry["linked_run_id"] = rid
        else:
            entry["linked"] = False

        # 5. Active-run pointer (executor state)
        if active_run_pointer and active_run_pointer.get("run_id") == rid:
            entry["active"] = True
            entry["active_run_id"] = rid
            for k in ("runner", "tmux_session", "pid", "state", "started_at",
                       "command_preview", "yolo", "launch_generation",
                       "launcher_pid"):
                if k in active_run_pointer and active_run_pointer[k] is not None:
                    entry[k] = active_run_pointer[k]
        else:
            entry["active"] = False

        # 6. Pending-run pointer
        if pending_run_pointer and pending_run_pointer.get("run_id") == rid:
            entry["pending"] = True
            entry["pending_run_id"] = rid
        else:
            entry["pending"] = False

        # 7. Live tmux session (attach info only)
        for session_name, live in live_tmux_sessions.items():
            if live.get("run_id") == rid:
                entry.setdefault("tmux_session", session_name)
                entry.setdefault("attach_command", f"tmux attach -t {session_name}")
                entry["tmux_alive"] = True
                entry["managed_tmux"] = live.get("managed", False)
                break

        # Now resolve the canonical state
        state = resolve_run_state(
            entry,
            tmux_alive=entry.get("tmux_alive", False),
            runner_pid_alive=entry.get("pid_alive", False),
            control_root=control_root,
        )
        # But never override terminal evidence with tmux alive
        resolved_state = _resolve_final_state(entry, state)
        entry["state"] = resolved_state
        entry["terminal"] = is_terminal_state(resolved_state)

        # Build source label
        sources = []
        if entry.get("linked"):
            sources.append("current-run")
        if entry.get("active"):
            sources.append("active-run")
        if rid in folded_history:
            sources.append("runs-history")
        if rid in run_directories:
            sources.append("runs-root")
        if rid in tmux_by_run_id:
            sources.append("tmux")
        if entry.get("tmux_alive"):
            sources.append("live-tmux")
        entry["source"] = "+".join(sources) if sources else "unknown"

        merged[rid] = entry

    return merged


def _resolve_final_state(entry: Dict[str, Any], provisional_state: str) -> str:
    """Apply hard evidence overrides to the provisional state.

    Terminal artifacts ALWAYS beat tmux liveness or in-memory state.
    """
    run_root = entry.get("run_root", "")
    if not run_root:
        return provisional_state

    # runner.failed.json -> always failed
    if os.path.isfile(os.path.join(run_root, "runner.failed.json")):
        return "failed"

    # runner.finished + runner.exit_code -> terminal
    finished_path = os.path.join(run_root, "runner.finished")
    exit_code_path = os.path.join(run_root, "runner.exit_code")
    if os.path.isfile(finished_path) and os.path.isfile(exit_code_path):
        try:
            with open(exit_code_path) as ef:
                ec = int(ef.read().strip())
            if ec == 0:
                return resolve_final_status_from_artifacts(run_root) or "finished"
            return "failed"
        except (ValueError, OSError):
            return "finished"

    # runner.finished alone
    if os.path.isfile(finished_path):
        return resolve_final_status_from_artifacts(run_root) or "finished"

    # Check history state
    history_state = entry.get("history_state", "")
    if history_state and is_terminal_state(history_state):
        return normalize_state(history_state) or "unknown"

    return provisional_state


def resolve_final_status_from_artifacts(run_root: str) -> Optional[str]:
    """Read final.json or other artifacts to determine terminal status."""
    final_path = os.path.join(run_root, "state", "final.json")
    if os.path.isfile(final_path):
        try:
            with open(final_path) as ff:
                final_data = json.load(ff)
            verdict = final_data.get("final_verdict", {})
            if isinstance(verdict, dict):
                vs = str(verdict.get("status", "")).upper()
                if vs == "FULLY_DONE":
                    return "fully_done"
                if vs in ("DONE", "SUCCESS"):
                    return "done"
                if vs in ("ABORTED",):
                    return "aborted"
                if vs in ("FAILED", "NOT_DONE"):
                    return "failed"
            status = str(final_data.get("status", "")).upper()
            if status == "FULLY_DONE":
                return "fully_done"
            if status in ("DONE", "SUCCESS"):
                return "done"
            if status in ("ABORTED",):
                return "aborted"
            if status == "FAILED":
                return "failed"
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Newest run selection
# ---------------------------------------------------------------------------

def newest_run(entries: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the newest valid run by timestamp/run_id, independent of state."""
    best: Optional[Dict[str, Any]] = None
    best_ts: float = 0.0

    for rid, entry in entries.items():
        ts = resolve_run_timestamp(entry)
        if ts <= 0:
            ts = _run_id_to_sort_key(rid)
        if ts > best_ts:
            best_ts = ts
            best = entry

    return best


def newest_active_run(entries: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the newest genuinely active run."""
    active_entries = {
        rid: e for rid, e in entries.items()
        if e.get("active") or is_active_state(e.get("state"))
    }
    return newest_run(active_entries)


# ---------------------------------------------------------------------------
# Atomic JSON helpers and process-shared locking
# ---------------------------------------------------------------------------

def atomic_write_json(control_root: str, filename: str, data: Dict[str, Any]) -> bool:
    """Atomically write a JSON file using temp+rename pattern.

    Returns True on success, False on failure.
    """
    import tempfile
    try:
        os.makedirs(control_root, exist_ok=True)
    except OSError:
        return False

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=control_root,
            prefix=f".{filename}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False
        target_path = os.path.join(control_root, filename)
        os.replace(tmp_path, target_path)
        return True
    except OSError:
        return False


def atomic_read_json(control_root: str, filename: str) -> Optional[Dict[str, Any]]:
    """Read a JSON file that may have been written atomically."""
    path = os.path.join(control_root, filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def append_jsonl(control_root: str, filename: str, entry: Dict[str, Any]) -> None:
    """Append a JSON line to a JSONL file."""
    try:
        os.makedirs(control_root, exist_ok=True)
    except OSError:
        return
    path = os.path.join(control_root, filename)
    try:
        with open(path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Process-shared file lock
# ---------------------------------------------------------------------------

class ControlLock:
    """Process-shared file lock for the control root.

    Provides a context manager that uses fcntl.flock for cross-process
    mutual exclusion on lifecycle transactions.
    """

    def __init__(self, control_root: str):
        self._lock_path = os.path.join(control_root, "run-control.lock")
        self._fd: Optional[int] = None

    def __enter__(self) -> "ControlLock":
        try:
            os.makedirs(os.path.dirname(self._lock_path), exist_ok=True)
        except OSError:
            pass
        self._fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX)
        except Exception:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        return False


# ---------------------------------------------------------------------------
# Session entry builder helper
# ---------------------------------------------------------------------------

def build_session_entry(
    merged_entry: Dict[str, Any],
    run_root_check: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """Build a consistent session entry from a merged run entry.

    Args:
        merged_entry: The merged entry from merge_run_sources
        run_root_check: Optional function to check if paths exist

    Returns a dict suitable for the sessions API response.
    """
    rid = merged_entry.get("run_id", "")
    run_root = merged_entry.get("run_root", "")
    events_path = merged_entry.get("events_path", "")
    target_path = merged_entry.get("target_path", "")
    task_path = merged_entry.get("task_path", "")
    tmux_session = merged_entry.get("tmux_session", "")
    attach_command = merged_entry.get("attach_command", "")

    # Build events_exists etc
    events_exists = bool(events_path and os.path.isfile(events_path))
    plan_exists = bool(run_root and os.path.isfile(
        os.path.join(run_root, "state", "plan.json")
    ))
    final_exists = bool(run_root and os.path.isfile(
        os.path.join(run_root, "state", "final.json")
    ))
    target_exists = bool(target_path and os.path.isdir(target_path))

    entry = {
        "run_id": rid,
        "state": merged_entry.get("state", "unknown"),
        "runner": merged_entry.get("runner", ""),
        "run_root": run_root,
        "target_path": target_path,
        "events_path": events_path,
        "task_path": task_path,
        "tmux_session": tmux_session,
        "attach_command": attach_command,
        "linked": merged_entry.get("linked", False),
        "active": merged_entry.get("active", False),
        "pending": merged_entry.get("pending", False),
        "selectable": True,
        "tmux_alive": merged_entry.get("tmux_alive", False),
        "runner_alive": merged_entry.get("pid_alive", False),
        "managed_tmux": merged_entry.get("managed_tmux", False),
        "terminal": merged_entry.get("terminal", False),
        "events_exists": events_exists,
        "plan_exists": plan_exists,
        "final_exists": final_exists,
        "target_exists": target_exists,
        "target_file_count": 0,
        "created_at": merged_entry.get("created_at", ""),
        "started_at": merged_entry.get("started_at", ""),
        "finished_at": merged_entry.get("finished_at", ""),
        "exit_code": merged_entry.get("exit_code"),
        "source": merged_entry.get("source", "unknown"),
        "link_status": "linked" if (run_root and events_path) else "unresolved",
    }

    if merged_entry.get("yolo") is not None:
        entry["yolo"] = merged_entry["yolo"]

    # Count target files
    if target_path and os.path.isdir(target_path):
        try:
            count = 0
            for root, dirs, files in os.walk(target_path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                count += len(files)
                if count > 100:
                    break
            entry["target_file_count"] = count
        except OSError:
            pass

    return entry


def sort_sessions_newest_first(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort sessions strictly newest-first by canonical recency.

    Does NOT sort "running" ahead of newer runs. Linked/active runs
    are indicated with badges, not moved out of chronological order.
    """
    def sort_key(s: Dict[str, Any]) -> float:
        ts = resolve_run_timestamp(s)
        if ts <= 0:
            ts = _run_id_to_sort_key(s.get("run_id", ""))
        if ts <= 0:
            # Try run_root mtime
            rr = s.get("run_root", "")
            if rr and os.path.isdir(rr):
                try:
                    ts = os.path.getmtime(rr)
                except OSError:
                    pass
        return -ts  # negative for descending (newest first)

    sessions.sort(key=sort_key)
    return sessions


# ---------------------------------------------------------------------------
# Startup and pre-launch reconciliation
# ---------------------------------------------------------------------------

def reconcile_managed_runtime(control_root: str, runs_root: str = "") -> Dict[str, Any]:
    """Reconcile QonQrete runtime state on startup and before launch decisions.

    Discovers managed tmux sessions, resolves run metadata, checks terminal
    artifacts, closes lingering managed terminal sessions, and ensures at most
    one genuine managed executor is considered active.

    Returns reconciliation diagnostics.
    """
    diagnostics: Dict[str, Any] = {
        "ok": True,
        "tmux_sessions_found": 0,
        "tmux_sessions_closed": 0,
        "tmux_sessions_orphaned": 0,
        "active_run_reconciled": False,
        "errors": [],
    }

    if not control_root:
        return diagnostics

    # Discover QonQrete-managed tmux sessions
    import subprocess
    managed_sessions: Dict[str, Dict[str, Any]] = {}
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F",
             "#{session_name}\t#{session_created}\t#{pane_pid}\t#{pane_current_command}\t#{pane_dead}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                name = parts[0]
                if not name.startswith("qonqrete-") and not name.startswith("qq-"):
                    continue
                diagnostics["tmux_sessions_found"] += 1

                # Check managed status
                managed = False
                run_id = ""
                session_run_root = ""
                try:
                    mgr = subprocess.run(
                        ["tmux", "show-options", "-v", "-t", name, "@qonqrete_managed"],
                        capture_output=True, text=True, timeout=2,
                    )
                    managed = mgr.returncode == 0 and mgr.stdout.strip() == "1"
                    rid = subprocess.run(
                        ["tmux", "show-options", "-v", "-t", name, "@qonqrete_run_id"],
                        capture_output=True, text=True, timeout=2,
                    )
                    if rid.returncode == 0:
                        run_id = rid.stdout.strip()
                    srr = subprocess.run(
                        ["tmux", "show-options", "-v", "-t", name, "@qonqrete_run_root"],
                        capture_output=True, text=True, timeout=2,
                    )
                    if srr.returncode == 0:
                        session_run_root = srr.stdout.strip()
                except Exception:
                    pass

                managed_sessions[name] = {
                    "run_id": run_id or name.replace("qonqrete-", "").replace("qq-", ""),
                    "managed": managed,
                    "run_root": session_run_root,
                    "pane_pid": parts[2],
                    "pane_command": parts[3],
                    "pane_dead": parts[4],
                }
    except FileNotFoundError:
        pass
    except Exception as e:
        diagnostics["errors"].append(f"tmux_list_failed: {e}")

    # For each managed session, check if terminal
    for session_name, info in managed_sessions.items():
        s_run_root = info.get("run_root", "")
        s_run_id = info.get("run_id", "")

        # Check terminal artifacts
        is_terminal = False
        if s_run_root and os.path.isdir(s_run_root):
            if os.path.isfile(os.path.join(s_run_root, "runner.finished")):
                is_terminal = True
            elif os.path.isfile(os.path.join(s_run_root, "runner.failed.json")):
                is_terminal = True

        # Check folded history
        if not is_terminal and s_run_id:
            folded = load_latest_run_records(control_root)
            if s_run_id in folded:
                state = folded[s_run_id].get("state", "")
                if is_terminal_state(state):
                    is_terminal = True

        # Check pane_dead
        if not is_terminal and info.get("pane_dead") == "1":
            is_terminal = True

        if is_terminal:
            # Safely close managed terminal session
            if info.get("managed"):
                try:
                    subprocess.run(
                        ["tmux", "kill-session", "-t", session_name],
                        capture_output=True, timeout=5,
                    )
                    diagnostics["tmux_sessions_closed"] += 1
                except Exception as e:
                    diagnostics["errors"].append(f"kill_failed_{session_name}: {e}")
            else:
                # Legacy session with terminal proof
                diagnostics["tmux_sessions_orphaned"] += 1

    # Ensure at most one active-run.json points to a genuinely active executor
    active_path = os.path.join(control_root, "active-run.json")
    if os.path.isfile(active_path):
        try:
            with open(active_path, "r") as af:
                ar = json.load(af)
            a_run_id = ar.get("run_id", "")
            a_run_root = ar.get("run_root", "")

            # Verify active run is genuinely running
            genuinely_active = False
            if a_run_root and os.path.isdir(a_run_root):
                if not os.path.isfile(os.path.join(a_run_root, "runner.finished")):
                    # Check if tmux session exists
                    runner = ar.get("runner", "")
                    tmux_sess = ar.get("tmux_session", "")
                    if runner == "tmux" and tmux_sess:
                        try:
                            hs = subprocess.run(
                                ["tmux", "has-session", "-t", tmux_sess],
                                capture_output=True, timeout=2,
                            )
                            if hs.returncode == 0:
                                genuinely_active = True
                        except Exception:
                            pass
                    elif runner == "local_exec":
                        pid = ar.get("pid")
                        if pid:
                            try:
                                os.kill(int(pid), 0)
                                genuinely_active = True
                            except (OSError, ProcessLookupError, ValueError):
                                pass

            if not genuinely_active:
                # Terminalize or remove
                try:
                    os.unlink(active_path)
                    diagnostics["active_run_reconciled"] = True
                except OSError:
                    pass
                # Record as stale in history
                if a_run_id:
                    append_jsonl(control_root, "runs.jsonl", {
                        "run_id": a_run_id,
                        "state": "stale",
                        "reason": "reconciled_stale_active",
                        "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    })
        except (json.JSONDecodeError, OSError) as e:
            diagnostics["errors"].append(f"active_run_read_failed: {e}")
            try:
                os.unlink(active_path)
            except OSError:
                pass

    return diagnostics
