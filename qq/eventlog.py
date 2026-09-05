"""
JSONL event log — the source of truth for a run.

Plain newline-delimited JSON, append-only. Gives you replay, debugging,
metrics, and resumability for free, and means the terminal output can stay
dumb (qontroller.py just prints short status lines) without losing any
detail — the detail lives here.

Required event types (as per spec):
  run.started, config.loaded, agent.call.started, agent.call.finished,
  agent.call.failed, clarification.questioned, clarification.done,
  plan.created, workspace.created, workspace.committed,
  workspace.merge.started, workspace.merge.completed, workspace.merge.failed,
  harness.started, harness.completed, harness.failed,
  review.verdict, repair.issues_mapped,
  active_agent_changed, stream_activity_updated,
  inspection_score_recorded, inspection_score_inconsistent,
  last_exit_status_updated,
  run.completed, run.aborted, run.failed
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterator


class EventLog:
    def __init__(self, path: str, run_id: str = ""):
        self.path = path
        self.run_id = run_id
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    def emit(self, event_type: str, **fields: Any) -> Dict[str, Any]:
        record = {
            "ts": time.time(),
            "run_id": self.run_id,
            "type": event_type,
            **fields,
        }
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()
        return record

    def close(self) -> None:
        self._fh.close()

    @staticmethod
    def replay(path: str) -> Iterator[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
