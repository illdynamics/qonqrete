"""
briQsQope bridge package — QonQrete-side web dashboard integration.

This package provides:
  - read_model.py  → Build a stable JSON read model from QonQrete artifacts
  - events.py      → Tail events.jsonl for live updates (SSE / polling)
  - process.py     → Start/stop the briQsQope dashboard process
  - api.py         → Optional lightweight local HTTP API for the dashboard

Architecture rules (non-negotiable):
  1. QonQrete is the single source of truth — always.
  2. Qontroller is the only loop controller — always.
  3. briQsQope is an optional read-only cockpit — never the pilot.
  4. briQsQope must never run agents directly.
  5. briQsQope must never declare a run done.
"""
from .read_model import build_read_model
from .events import EventTailer
from .process import start_dashboard, stop_dashboard, dashboard_status, find_dashboard_dir

__all__ = [
    "build_read_model",
    "EventTailer",
    "start_dashboard",
    "stop_dashboard",
    "dashboard_status",
    "find_dashboard_dir",
]
