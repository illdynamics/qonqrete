"""
Agent output streaming — live terminal output for agent subprocess stdout/stderr.

Design:
  AgentOutputStreamer is a light renderer/sink that receives structured
  line chunks from adapters and prints them (or routes them to any callable).
  It handles redaction, prefixed vs raw mode, and stderr gating.

  Adapters call sink(chunk) with a dict containing:
    role, cycle, call_id, stream_name ("stdout"|"stderr"), text

Stream indicator modes:
  stream  — shows literal stream name (stdout/stderr) after role prefix (default)
  spinner — shows a braille_snake spinner frame after role prefix (terminal display only)
  none    — shows only the role prefix, no stream indicator

Example output:
  spinner → "[Role] <braille_snake_frame> "
  stream  → "[Role] stdout " or "[Role] stderr "
  none    → "[Role] "

Agent color output modes:
  agent    — each agent's output is fully colored with that agent's color
  original — preserve original codeseeq output colors (wraps in agent prefix only)
  none     — no color at all in agent output
"""
from __future__ import annotations

import re
import sys
from typing import Callable, Dict, Literal, Optional, Tuple

from .adapters.codeseeq import _redact_secrets


# Prefix labels and colors for each role
_ROLE_DISPLAY = {
    "qlarifier":   ("[Qlarifier]",  "\033[36m"),    # cyan
    "instruqtor":  ("[instruQtor]", "\033[35m"),    # magenta
    "construqtor": ("[construQtor]","\033[33m"),    # yellow
    "inspeqtor":   ("[inspeQtor]",  "\033[32m"),    # green
    "qualifier":   ("[Qualifier]",  "\033[36m"),    # cyan
    "sqavenger":   ("[sQavenger]",  "\033[34m"),    # blue
    "attraqtor":   ("[attraQtor]",  "\033[31m"),    # red
    "qontroller":  ("[Qontroller]", "\033[95m"),    # bright magenta
}
_RESET = "\033[0m"

# Regex to detect ANSI escape sequences
_ANSI_ESCAPE_RE = re.compile(r'\033\[[0-9;]*[a-zA-Z]')

# Braille spinner frames
_SPINNER_STYLES = {
    "braille_snake": [
        "⠁", "⠃", "⠇", "⡇", "⣇", "⣧", "⣷",
        "⣿", "⡿", "⠿", "⠟", "⠛", "⠙", "⠉",
    ],
}
_SPINNER_FRAMES = _SPINNER_STYLES["braille_snake"]

# Per-stream spinner state: (role, stream_name, call_id) → frame index
_spinner_state: Dict[Tuple[str, str, str], int] = {}


def _next_spinner(role: str, stream_name: str, call_id: str = "") -> str:
    """Return the next spinner frame for a given (role, stream, call_id).

    State is keyed per-stream so concurrent streams don't share a frame counter.
    """
    key = (role, stream_name, call_id or "")
    idx = _spinner_state.get(key, 0)
    frame = _SPINNER_FRAMES[idx]
    _spinner_state[key] = (idx + 1) % len(_SPINNER_FRAMES)
    return frame


def _format_prefix(role: str, stream: str, call_id: str = "",
                   indicator: str = "stream",
                   no_color: bool = False) -> str:
    """Build the colored prefix line for a given role.

    Indicator modes:
      "stream"  → "[Role] stdout " or "[Role] stderr "
      "spinner" → "[Role] <braille_snake_frame> " (terminal display only)
      "none"    → "[Role] "
    """
    info = _ROLE_DISPLAY.get(role)
    if info is None:
        label = f"[{role}]"
        color = ""
    else:
        label, color = info

    if indicator == "stream":
        suffix = stream
    elif indicator == "spinner":
        suffix = _next_spinner(role, stream, call_id)
    else:  # "none"
        suffix = ""

    if no_color:
        color = ""

    if color:
        return f"{color}{label} {suffix}{_RESET} " if suffix else f"{color}{label}{_RESET} "
    else:
        return f"{label} {suffix} " if suffix else f"{label} "


def _wrap_in_agent_color(role: str, text: str, no_color: bool = False) -> str:
    """Wrap an entire line in the agent's color, stripping existing ANSI codes first.

    In 'agent' mode, all output for this agent is rendered in that agent's color.
    Existing ANSI color codes in the text are stripped so the agent color prevails.
    """
    info = _ROLE_DISPLAY.get(role)
    if info is None or no_color:
        return text
    _, color = info
    # Strip existing ANSI sequences and replace with the agent's color
    stripped = _ANSI_ESCAPE_RE.sub('', text)
    # Wrap the whole text in agent color and reset at end
    return f"{color}{stripped}{_RESET}"


class AgentOutputStreamer:
    """Renders agent subprocess output to terminal.

    Parameters:
      enabled:    If False, all emit() calls are no-ops.
      mode:       "prefixed" or "raw".
      indicator:  "stream" (default), "spinner", or "none" — what to show after the role prefix.
      stream_stderr: Whether to emit stderr chunks.
      redact:     Redact secrets from terminal output.
      sink:       Optional custom callable; if None, prints to sys.stderr
                  and flushes after every write.
    """

    def __init__(
        self,
        enabled: bool = True,
        mode: str = "prefixed",
        indicator: str = "stream",
        stream_stderr: bool = True,
        redact: bool = True,
        sink: Optional[Callable[[dict], None]] = None,
        sticky_status: object = None,
        spinner_manager: object = None,
        activity_tracker: object = None,
        refresh_sticky_cb: object = None,
        stream_line_prefix: str = "auto",
        no_color: bool = False,
        agent_color_output: str = "agent",
    ):
        self.enabled = enabled
        self.mode = mode
        self.indicator = indicator
        self.stream_stderr = stream_stderr
        self.do_redact = redact
        self._sink = sink
        self._sticky = sticky_status
        self._spinner_mgr = spinner_manager
        self._activity = activity_tracker
        self._refresh_sticky = refresh_sticky_cb
        self._line_prefix = stream_line_prefix
        self._no_color = no_color
        self._agent_color_output = agent_color_output  # "agent", "original", "none"

        # Determine if we should show body prefixes.
        # This logic can be re-evaluated whenever sticky status changes.
        self._determine_prefix(stream_line_prefix)

    def _determine_prefix(self, prefix_mode: str) -> None:
        """Determine whether to show body prefixes based on current state."""
        if prefix_mode == "none":
            self._use_prefix = False
        elif prefix_mode == "auto":
            # When sticky is active, default to no body prefixes
            self._use_prefix = not (self._sticky and self._sticky.is_active)
        elif prefix_mode == "agent" or prefix_mode == "stream":
            self._use_prefix = True
        else:
            self._use_prefix = True

    def emit(self, chunk: dict) -> None:
        """Emit one structured chunk to the terminal.

        Chunk keys:
          role:         str (qlarifier, instruqtor, construqtor, inspeqtor)
          stream_name:  "stdout" | "stderr"
          text:         str  (a single line, with trailing newline if present)
          cycle:        optional int
          call_id:      optional str

        Every emit flushes the terminal sink immediately so output
        appears live, not buffered.
        """
        if not self.enabled:
            return
        if not self.stream_stderr and chunk.get("stream_name") == "stderr":
            return

        text = chunk.get("text", "")
        if self.do_redact:
            text = _redact_secrets(text)

        role = chunk.get("role", "unknown")
        stream = chunk.get("stream_name", "stdout")
        call_id = chunk.get("call_id", "")

        # Track chunk count and advance spinner
        if self._activity:
            self._activity.chunks_seen += 1
            if self._spinner_mgr:
                spinner_frame = self._spinner_mgr.advance(role, stream, call_id)
                self._activity.spinner_frame = spinner_frame
                # model_symbol is static, set by qontroller on agent switch

        # Re-evaluate prefix state if sticky status may have changed
        if hasattr(self, '_line_prefix'):
            self._determine_prefix(self._line_prefix)

        if self.mode == "prefixed" and self._use_prefix:
            line = _format_prefix(role, stream, call_id=call_id,
                                  indicator=self.indicator,
                                  no_color=self._no_color) + text
        else:
            line = text

        # Apply agent color output mode
        if not self._no_color and self._agent_color_output == "agent":
            # Agent color mode: wrap everything in the agent's color, stripping originals
            # The prefix is already colored, so just color the body text
            if self.mode == "prefixed" and self._use_prefix:
                # Prefix is already colored. Only wrap the body part.
                # Split by first RESET if present
                prefix, sep, body = self._split_prefix_from_body(line, role)
                if sep:
                    line = prefix + sep + _wrap_in_agent_color(role, body, no_color=self._no_color)
                else:
                    line = _wrap_in_agent_color(role, line, no_color=self._no_color)
            else:
                line = _wrap_in_agent_color(role, line, no_color=self._no_color)
        elif not self._no_color and self._agent_color_output == "original":
            # Original mode: preserve codeseeq colors, just add agent prefix
            pass  # line is already correct
        # "none" mode: no color; _no_color handles that

        # Write to sticky line sink or normal sink
        if self._sticky and self._sticky.is_active:
            self._sticky.write_stream_line(line)
        elif self._sink:
            self._sink({"line": line, **chunk})
            # If the sink is file-like, try to flush
            if hasattr(self._sink, 'flush'):
                try:
                    self._sink.flush()
                except Exception:
                    pass
        else:
            # Print to stderr so we don't contaminate stdout-based piping
            # Flush immediately so output appears live
            sys.stderr.write(line)
            sys.stderr.flush()

        # Refresh sticky status after emitting chunk
        if self._refresh_sticky:
            try:
                self._refresh_sticky()
            except Exception:
                pass

    def _split_prefix_from_body(self, line: str, role: str) -> Tuple[str, str, str]:
        """Split a prefixed line into prefix, separator, and body.

        Returns (prefix, sep, body). sep is the RESET/color boundary.
        When there's no colored prefix, returns (line, '', '').
        """
        info = _ROLE_DISPLAY.get(role)
        if info is None:
            return (line, '', '')

        # The prefix format is: <color>[Role] suffix<RESET> <body>
        # Find the first RESET
        reset_idx = line.find(_RESET)
        if reset_idx == -1:
            return (line, '', '')

        prefix = line[:reset_idx + len(_RESET)]
        # The sep is the space between prefix end and body
        body = line[reset_idx + len(_RESET):]
        return (prefix, '', body)


# Convenience factory
def create_streamer(
    enabled: bool,
    mode: str = "prefixed",
    indicator: str = "stream",
    stream_stderr: bool = True,
    redact: bool = True,
    sink: Optional[Callable] = None,
    sticky_status: object = None,
    spinner_manager: object = None,
    activity_tracker: object = None,
    refresh_sticky_cb: object = None,
    stream_line_prefix: str = "auto",
    no_color: bool = False,
    agent_color_output: str = "agent",
) -> AgentOutputStreamer:
    return AgentOutputStreamer(
        enabled=enabled, mode=mode, indicator=indicator,
        stream_stderr=stream_stderr, redact=redact, sink=sink,
        sticky_status=sticky_status,
        spinner_manager=spinner_manager,
        activity_tracker=activity_tracker,
        refresh_sticky_cb=refresh_sticky_cb,
        stream_line_prefix=stream_line_prefix,
        no_color=no_color,
        agent_color_output=agent_color_output,
    )
