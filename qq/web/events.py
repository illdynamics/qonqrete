"""
Event tailer — watches events.jsonl for live updates.

Supports:
  - Polling mode (periodic re-read of events.jsonl tail)
  - SSE-ready event generator

Rules:
  - Never edit events.jsonl.
  - Never infer destructive state from missing files.
  - Malformed events are warnings, not crashes.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterator, List, Optional


def _redact_env_leak(evt: dict) -> dict:
    """BGP5: strip the external agent's env-debug leak from any event payload
    as a final SSE/poll guard. If a text/message/etc. field carries a
    'QQV_ROLE=' line we remove it entirely (and drop the whole event if nothing
    remains) so the string can never reach the rendered GUI/overlay.
    """
    if evt is None or not isinstance(evt, dict):
        return evt
    offending = False
    for key in ("text", "message", "detail", "line", "output", "raw", "reason"):
        val = evt.get(key)
        if isinstance(val, str) and ("QQV_ROLE=" in val or "vQQV_ROLE=" in val):
            evt[key] = ""
            offending = True
    if offending:
        evt["_env_leak_redacted"] = True
    return evt


class EventTailer:
    """Watch an events.jsonl file and yield new events as they appear."""

    def __init__(
        self,
        events_path: str,
        poll_interval_ms: int = 500,
        heartbeat_interval_ms: int = 2000,
    ):
        self._path = events_path
        self._poll_s = poll_interval_ms / 1000.0
        self._heartbeat_s = heartbeat_interval_ms / 1000.0
        self._pos = 0  # byte position
        self._run_id = ""

    @property
    def path(self) -> str:
        return self._path

    @property
    def poll_interval_ms(self) -> int:
        return int(self._poll_s * 1000)

    @property
    def heartbeat_interval_ms(self) -> int:
        return int(self._heartbeat_s * 1000)

    def _read_new_events(self) -> List[Dict[str, Any]]:
        """Read any new events since last position."""
        if not os.path.isfile(self._path):
            # File might not exist yet — reset position
            self._pos = 0
            return []

        try:
            fsize = os.path.getsize(self._path)
        except OSError:
            return []

        if fsize < self._pos:
            # File was truncated (new run?) — reset
            self._pos = 0

        if fsize == self._pos:
            return []

        events: List[Dict[str, Any]] = []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                fh.seek(self._pos)
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                        if not self._run_id and evt.get("run_id"):
                            self._run_id = evt["run_id"]
                        events.append(_redact_env_leak(evt))
                    except json.JSONDecodeError:
                        events.append({
                            "type": "malformed_event",
                            "raw": line[:200],
                            "warning": True,
                        })
                self._pos = fh.tell()
        except OSError:
            pass

        return events

    def poll(self) -> List[Dict[str, Any]]:
        """Return any new events. Non-blocking."""
        return self._read_new_events()

    def tail(self) -> Iterator[Dict[str, Any]]:
        """Generator that yields new events as they appear (blocking)."""
        while True:
            events = self._read_new_events()
            for evt in events:
                yield evt
            time.sleep(self._poll_s)

    def sse_events(self) -> Iterator[str]:
        """Generator that yields SSE-formatted event strings.

        Events are emitted as raw messages (no event: line) so all events
        reach the client's onmessage handler, which dispatches internally
        based on the "type" field in the JSON payload.

        SSE heartbeat comments (": ping\\n\\n") are yielded at the configured
        heartbeat_interval_ms (default 2000). These are ignored by browser
        EventSource but allow the server to detect closed client connections.

        Yields an immediate initial heartbeat when idle so tests and clients
        can verify the stream is alive without waiting for a full interval.
        """
        last_ping = time.time()
        initial_heartbeat_sent = False
        while True:
            events = self._read_new_events()
            if events:
                for evt in events:
                    data = json.dumps(evt, default=str)
                    yield f"data: {data}\n\n"
                last_ping = time.time()
                initial_heartbeat_sent = False
            else:
                now = time.time()
                # Yield an immediate initial heartbeat when idle (Option B)
                if not initial_heartbeat_sent:
                    yield ": ping\n\n"
                    last_ping = now
                    initial_heartbeat_sent = True
                elif now - last_ping >= self._heartbeat_s:
                    yield ": ping\n\n"
                    last_ping = now
            # Sleeping poll: check in short bursts so the caller can
            # detect shutdown / client disconnect quickly.
            _sleep_remaining = self._poll_s
            while _sleep_remaining > 0:
                _chunk = min(0.05, _sleep_remaining)
                time.sleep(_chunk)
                _sleep_remaining -= _chunk

    def get_all(self) -> List[Dict[str, Any]]:
        """Read all events from the file (for initial load)."""
        if not os.path.isfile(self._path):
            return []
        events: List[Dict[str, Any]] = []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(_redact_env_leak(json.loads(line)))
                    except json.JSONDecodeError:
                        events.append({
                            "type": "malformed_event",
                            "raw": line[:200],
                            "warning": True,
                        })
        except OSError:
            pass
        return events

    def rebind(self, events_path: str) -> None:
        """Rebind the tailer to a different events.jsonl file.
        
        Resets position tracking so events are read fresh from the new path.
        Used for session switching in dashboard control-root mode.
        """
        self._path = events_path
        self._pos = 0
        self._run_id = ""

    def reset(self) -> None:
        """Reset the tailer position to the beginning."""
        self._pos = 0
        self._run_id = ""
