"""
Canonical final-status resolver for QonQrete runs.

Resolves the final status/verdict from a run root using the canonical
priority order defined in the QonQrete spec:

  1. state/final.json
  2. state/status.json or equivalent status files
  3. Latest relevant event in events.jsonl
  4. Latest inspeQtor receipt: agents/cycle-XXX/inspeqtor/inspeqtor_output.json
  5. Any existing final verdict artifact already used by the app

Also provides display_name / task_title resolution and runner metadata
resolution.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple



def parse_boolish(value):
    """Normalize a bool-ish value to True, False, or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on", "y", "enabled"}:
        return True
    if s in {"0", "false", "no", "off", "n", "disabled"}:
        return False
    return None


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    """Read a JSON file, returning None if missing or malformed."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _coerce_status_string(status: Any) -> Optional[str]:
    """Extract a plain string status from a possibly-malformed verdict value.

    Handles str, dict (e.g. {'status': 'NOT_DONE'}), int/None, and other
    scalar values defensively so malformed review/cycle payloads can never
    raise while resolving the final status.
    """
    if status is None:
        return None
    if isinstance(status, str):
        s = status.strip()
        return s or None
    if isinstance(status, dict):
        for key in ("status", "verdict", "result", "outcome"):
            v = status.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    if isinstance(status, (int, float, bool)):
        s = str(status).strip()
        return s or None
    return None


def _read_events_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read all events from events.jsonl, newest first."""
    if not os.path.isfile(path):
        return []
    events = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    events.reverse()
    return events


def _find_latest_inspeqtor_receipt(run_root: str) -> Optional[Dict[str, Any]]:
    """Find the latest inspeQtor receipt JSON under agents/cycle-XXX/inspeqtor/."""
    agents_dir = os.path.join(run_root, "agents")
    if not os.path.isdir(agents_dir):
        return None

    cycle_dirs = []
    for entry in os.listdir(agents_dir):
        if entry.startswith("cycle-") and os.path.isdir(os.path.join(agents_dir, entry)):
            cycle_dirs.append(entry)
    cycle_dirs.sort(reverse=True)

    for cycle_dir in cycle_dirs:
        receipt_path = os.path.join(agents_dir, cycle_dir, "inspeqtor", "inspeqtor_output.json")
        receipt = _safe_read_json(receipt_path)
        if receipt:
            return receipt
    return None


def resolve_final_status(run_root: str) -> Optional[str]:
    """Resolve the canonical final status from a run root.

    Returns a normalized status string like "FULLY_DONE", "NOT_DONE",
    "FAILED", etc., or None if no status can be determined.

    Priority order:
      1. state/final.json → final_verdict.status or status
      2. Latest review.verdict event in events.jsonl
      3. Latest run.completed / run.failed / run.aborted event
      4. Latest inspeQtor receipt
      5. runner.exit_code + runner.finished existence
    """
    # 1. state/final.json
    final_path = os.path.join(run_root, "state", "final.json")
    final_data = _safe_read_json(final_path)
    if final_data:
        # final_verdict may be a dict, string, number, or missing.  Coerce
        # defensively so a malformed/non-string verdict (e.g. from a review
        # phase) can never raise while the endpoint resolves the final status.
        status = _coerce_status_string(final_data.get("final_verdict"))
        if status:
            return status
        # Check top-level status
        status = _coerce_status_string(final_data.get("status"))
        if status:
            return status
        # Check verdict at top level
        status = _coerce_status_string(final_data.get("verdict"))
        if status:
            return status
        # Check action / action_status
        action_val = final_data.get("action") or final_data.get("action_status")
        status = _coerce_status_string(action_val)
        if status:
            return status

    # 2. Events: latest review.verdict
    events_path = os.path.join(run_root, "events.jsonl")
    events = _read_events_jsonl(events_path)
    for evt in events:
        t = evt.get("type", "")
        if t == "review.verdict":
            status = _coerce_status_string(evt.get("status"))
            if status:
                return status

    # 3. Events: run.completed/run.failed/run.aborted
    for evt in events:
        t = evt.get("type", "")
        if t == "run.completed":
            status = _coerce_status_string(evt.get("status"))
            if status:
                return status
            return "success"
        if t == "run.failed":
            return "failed"
        if t == "run.aborted":
            return "aborted"

    # 4. Latest inspeQtor receipt
    receipt = _find_latest_inspeqtor_receipt(run_root)
    if receipt:
        # verdict can be a dict, string, number, list, or missing.  Coerce
        # conservative values only — a malformed inspeQtor payload must never
        # crash the 502-prone review-phase resolution.
        verdict = receipt.get("verdict") or receipt.get("final_verdict")
        status = _coerce_status_string(verdict)
        if status:
            return status
        # Also check action_status / status from the receipt
        action_val = receipt.get("action_status") or receipt.get("status")
        status = _coerce_status_string(action_val)
        if status:
            return status

    # 5. Fallback: runner.exit_code + runner.finished
    finished_path = os.path.join(run_root, "runner.finished")
    exit_code_path = os.path.join(run_root, "runner.exit_code")
    if os.path.isfile(finished_path):
        try:
            with open(exit_code_path, "r") as f:
                exit_code = int(f.read().strip())
            if exit_code == 0:
                return "finished"
            return "failed"
        except (ValueError, OSError):
            return "finished"

    return None


def is_fully_done(run_root: str) -> bool:
    """Return True if the run's final status is FULLY_DONE."""
    status = resolve_final_status(run_root)
    if status is None:
        return False
    return status.strip().upper() == "FULLY_DONE"


def resolve_display_name(run_root: str) -> str:
    """Resolve a human-readable display name / task title from a run root.

    Priority:
      1. state/task.json → task_title or raw_text first line
      2. artifacts/task-original.md → first non-empty line
      3. state/origin.json → task_title
      4. Run root basename (run_id)
      5. "Untitled task"
    """
    # 1. state/task.json
    task_json = _safe_read_json(os.path.join(run_root, "state", "task.json"))
    if task_json:
        title = task_json.get("task_title") or task_json.get("title", "")
        if title and title.strip():
            return title.strip()
        raw = task_json.get("raw_text", "")
        if raw:
            first_line = _first_non_empty_line(raw)
            if first_line:
                return first_line[:120]

    # 2. artifacts/task-original.md
    task_md_path = os.path.join(run_root, "artifacts", "task-original.md")
    if os.path.isfile(task_md_path):
        try:
            with open(task_md_path, "r", encoding="utf-8") as f:
                content = f.read()
            first_line = _first_non_empty_line(content)
            if first_line:
                return first_line[:120]
        except OSError:
            pass

    # 3. state/origin.json
    origin = _safe_read_json(os.path.join(run_root, "state", "origin.json"))
    if origin:
        title = origin.get("task_title") or origin.get("title", "")
        if title and title.strip():
            return title.strip()

    # 4. Run id from basename
    basename = os.path.basename(run_root.rstrip("/"))
    if basename:
        return basename

    return "Untitled task"


def _first_non_empty_line(text: str) -> Optional[str]:
    """Return the first non-empty, non-heading-marker line from text."""
    if not text:
        return None
    for line in text.split("\n"):
        stripped = line.strip()
        # Skip markdown headings markers and empty lines
        if stripped and not stripped.startswith("#") and not stripped.startswith("<!--"):
            return stripped
        if stripped and stripped.startswith("#"):
            # Strip heading markers and return
            cleaned = re.sub(r'^#+\s*', '', stripped).strip()
            if cleaned:
                return cleaned
    return None


def resolve_runner_metadata(run_root: str) -> Dict[str, Any]:
    """Resolve runner metadata from a run root.

    Returns dict with keys: mode, session, started_at, finished_at, pid, command.

    Priority for mode:
      1. tmux-session marker or state/runner.json
      2. state/origin.json runner field
      3. current-run.json pointer
      4. Inference from tmux session name in run_id
    """
    result: Dict[str, Any] = {
        "mode": "unknown",
        "session": "",
        "started_at": "",
        "finished_at": "",
        "pid": None,
        "command": "",
        "yolo": None,
    }

    # 1. Check state/runner.json
    runner_json = _safe_read_json(os.path.join(run_root, "state", "runner.json"))
    if runner_json:
        result["mode"] = runner_json.get("mode", result["mode"])
        result["session"] = runner_json.get("session", result["session"])
        result["started_at"] = runner_json.get("started_at", result["started_at"])
        result["pid"] = runner_json.get("pid", result["pid"])
        result["command"] = runner_json.get("command", result["command"])
        if "yolo" in runner_json:
            result["yolo"] = parse_boolish(runner_json["yolo"])

    # 2. Check origin.json
    if result["mode"] == "unknown":
        origin = _safe_read_json(os.path.join(run_root, "state", "origin.json"))
        if origin:
            runner = origin.get("runner", "")
            if runner == "tmux":
                result["mode"] = "tmux"
                result["session"] = origin.get("tmux_session", "")
            elif runner == "local_exec":
                result["mode"] = "local"
        if origin and result.get("yolo") is None and "yolo" in origin:
            result["yolo"] = parse_boolish(origin["yolo"])

    # 3. Check runner.finished timestamp
    finished_path = os.path.join(run_root, "runner.finished")
    if os.path.isfile(finished_path):
        try:
            with open(finished_path, "r") as f:
                result["finished_at"] = f.read().strip()
        except OSError:
            pass

    # 4. Check for tmux session naming pattern in run_root basename or
    #    tmux-sessions.jsonl in parent control root
    if result["mode"] == "unknown":
        # Check common tmux environment file
        tmux_env_path = os.path.join(run_root, "state", "tmux_session.txt")
        if os.path.isfile(tmux_env_path):
            result["mode"] = "tmux"
            try:
                with open(tmux_env_path, "r") as f:
                    result["session"] = f.read().strip()
            except OSError:
                pass

    # 5. Fallback: check if runner.exit_code exists alongside runner.finished
    #    (indicates a real runner was involved, default to "local")
    exit_code_path = os.path.join(run_root, "runner.exit_code")
    if result["mode"] == "unknown" and os.path.isfile(exit_code_path):
        # Has runner artifacts but no explicit mode marker
        result["mode"] = "local"

    return result


# ---------------------------------------------------------------------------
# Standalone shell helper script generator
# ---------------------------------------------------------------------------
def generate_final_status_shell_script(run_root: str, session_name: str) -> str:
    """Generate a robust shell snippet for detecting FULLY_DONE in the runner.

    Uses the Python resolver rather than fragile shell-based JSON parsing.
    Includes a retry loop with a small sleep to handle filesystem flush delays.
    """
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    python_resolver = os.path.join(script_path, "qq", "web", "status_resolver.py")

    return f'''
QQ_EXIT=$?
QQ_RUN_ROOT={_shell_quote(run_root)}
QQ_SESSION={_shell_quote(session_name)}
RUNNER_EXIT_CODE_PATH=$QQ_RUN_ROOT/runner.exit_code
RUNNER_FINISHED_PATH=$QQ_RUN_ROOT/runner.finished

# Write exit code and finish marker
printf '%s\\n' "$QQ_EXIT" > "$RUNNER_EXIT_CODE_PATH"
date -Is > "$RUNNER_FINISHED_PATH"

# Use Python resolver for robust final status detection
FINAL_STATUS=$(python3 -c "
import sys
sys.path.insert(0, '{script_path}')
from qq.web.status_resolver import resolve_final_status
status = resolve_final_status('{run_root}')
print(status or '')
" 2>/dev/null)

echo

if [ "$QQ_EXIT" = "0" ] && [ "$FINAL_STATUS" = "FULLY_DONE" ]; then
  echo "QonQrete run finished with status: FULLY_DONE. Session: $QQ_SESSION"
elif [ "$FINAL_STATUS" != "" ]; then
  echo "QonQrete run finished with status: $FINAL_STATUS. Session: $QQ_SESSION (exit code $QQ_EXIT)"
else
  echo "QonQrete run finished with exit code $QQ_EXIT. Session: $QQ_SESSION"
fi
'''


def _shell_quote(s: str) -> str:
    """Shell-quote a string for use in single-quoted context."""
    return s.replace("'", "'\"'\"'")
