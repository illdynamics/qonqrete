"""
Terminal UI — sticky status line renderer for Qq streaming output.

Provides:
  - format_qonqrete_status_bar()  — pure formatter, unit-testable
  - StickyStatusLine             — ANSI terminal sticky line management
  - StreamActivityStatus          — dataclass tracking all status fields
  - model_code_for()             — derives M=F|FT|P|PT|? from model string

Design:
  Keep terminal control separate from stream backend. The sticky line
  uses ANSI codes (save/restore cursor, scroll regions) only when TTY is
  active. Non-TTY sinks degrade automatically to plain clean streaming.
"""
from __future__ import annotations

import dataclasses
import os
import shutil
import sys
import time as time_mod
from typing import Callable, Dict, List, Literal, Optional, Tuple

try:
    import wcwidth
    def _display_width(text: str) -> int:
        """Return the display width of a string, accounting for wide chars."""
        return wcwidth.wcswidth(text)
except ImportError:
    def _display_width(text: str) -> int:
        """Fallback display width using len()."""
        return len(text)


# ---------------------------------------------------------------------------
# Braille snake spinner (the one true spinner for Qq)
# ---------------------------------------------------------------------------
BRAILLE_SNAKE = [
    "\u2801", "\u2803", "\u2807", "\u2847", "\u28c7", "\u28e7", "\u28f7",
    "\u28ff", "\u287f", "\u283f", "\u281f", "\u281b", "\u2819", "\u2809",
]

# ---------------------------------------------------------------------------
# Quarter-circle spinner (4-frame, used on the right side of status bar)
# ---------------------------------------------------------------------------
QUARTER_CIRCLE_SPINNER = [
    "\u25f0",  # ◰
    "\u25f3",  # ◳
    "\u25f2",  # ◲
    "\u25f1",  # ◱
]

# ---------------------------------------------------------------------------
# Agent icons (matching Rust TUI)
# ---------------------------------------------------------------------------
AGENT_ICONS = {
    "qlarifier":   "\u00bfQ\u003f",    # ¿Q?
    "instruqtor":  "\u22a2Q\u21e2",    # ⊢Q⇢
    "construqtor": "\u27ecQ\u27ed",    # ⟬Q⟭
    "inspeqtor":   "\u29c9Q\u2316",    # ⧉Q⌖
    "qualifier":   "\u29bfQ\u2713",    # ⦿Q✓
}

def agent_icon(role: str) -> str:
    """Return the Unicode agent icon for a given role name."""
    return AGENT_ICONS.get(role.lower(), AGENT_ICONS["qlarifier"])


# ---------------------------------------------------------------------------
# Model code derivation
# ---------------------------------------------------------------------------
def model_code_for(model: str, *, provider_metadata: Optional[Dict] = None) -> str:
    """Derive the display model code (fla, fla-T, pro, pro-T, ?) from a model string.

    If provider_metadata declares an explicit model class, use that.
    Otherwise derive from model string heuristics:
      - 'flash' → base F → fla
      - 'flash' + 'thinking' → fla-T
      - 'pro' → base P → pro
      - 'pro' + 'thinking' → pro-T
      - unknown → '?'

    Examples:
      deepseek-v4-flash → fla
      deepseek-v4-flash-thinking → fla-T
      deepseek-v4-pro → pro
      deepseek-v4-pro-thinking → pro-T
    """
    if provider_metadata:
        mc = provider_metadata.get("model_class") or provider_metadata.get("model_code")
        if mc in ("F", "FT", "P", "PT"):
            if mc == "F":
                return "fla"
            if mc == "FT":
                return "fla-T"
            if mc == "P":
                return "pro"
            if mc == "PT":
                return "pro-T"
            return mc

    m = model.lower()
    if "flash" in m:
        if "thinking" in m:
            return "fla-T"
        return "fla"
    elif "pro" in m:
        if "thinking" in m:
            return "pro-T"
        return "pro"
    return "?"


# ---------------------------------------------------------------------------
# Model symbol mapping (for right side display)
# ---------------------------------------------------------------------------
_MODEL_SYMBOLS = {
    "fla":    "↯  ",   # ↯  
    "fla-T":  "↯ ⨪",  # ↯ ⫪
    "pro":    "⚝  ",   # ⚝  
    "pro-T":  "⚝ ⨪",  # ⚝ ⫪
}

def model_symbol_for(model_code: str) -> str:
    """Return the display symbol for a model code.
    
    Maps model codes to Unicode symbols:
      fla   -> ↯   (lightning bolt, flash)
      fla-T -> ↯ ⫪ (lightning bolt + thinking)
      pro   -> ⚝   (star, pro)
      pro-T -> ⚝ ⫪ (star + thinking)
      ?     -> ???
    """
    return _MODEL_SYMBOLS.get(model_code, "???")


# ---------------------------------------------------------------------------
# Time formatting
# ---------------------------------------------------------------------------
def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS (under 1 hour) or H:MM:SS (1 hour+)."""
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


# ---------------------------------------------------------------------------
# Color constants
# ---------------------------------------------------------------------------
FRAME_GREY = "38;5;248"
Q_GOLD = "38;5;214"
Q_ORANGE = "38;5;208"
AGENT_COLORS: Dict[str, str] = {
    "qlarifier":   "36",    # cyan
    "instruqtor":  "35",    # magenta
    "construqtor": "33",    # yellow
    "inspeqtor":   "32",    # green
    "qualifier":   "36",    # cyan
    "sqavenger":   "34",    # blue
    "attraqtor":   "31",    # red
    "qontroller":  "95",    # bright magenta
}


# ---------------------------------------------------------------------------
# Stream activity status
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class StreamActivityStatus:
    """All metadata needed to render the sticky status line."""
    role: str = ""
    call_id: str = ""
    stream_name: str = "stdout"
    cycle: int = 1
    max_cycles: int = 0
    max_time_seconds: int = 0
    spinner_frame: str = BRAILLE_SNAKE[0]
    spinner_index: int = 0
    chunks_seen: int = 0
    bytes_seen: int = 0
    run_elapsed_seconds: float = 0.0
    agent_elapsed_seconds: float = 0.0
    model_code: str = "?"
    score: int = 0
    last_exit_code: int = 0
    model_symbol: str = "???"
    status_word: str = "running"
    action_status: str = "waiting"
    last_message_preview: Optional[str] = None


# ---------------------------------------------------------------------------
# Status bar formatter  (matches new TUI format)
# ---------------------------------------------------------------------------
def format_qonqrete_status_bar(
    status: StreamActivityStatus,
    *,
    color: bool = False,
    width: Optional[int] = None,
    version: str = "",
) -> str:
    """Format the QonQrete sticky status line.

    Three-part float layout (left / centered / right) on a single line:
      Left:   ╭─[ꝖꝖ]─❯❯❯ Qlarifier ⠛
      Center: C=N/M · T=MM:SS A=MM:SS · P=N%
      Right:  icon─[↯?]─╮

    Uses wcwidth for accurate Unicode display-width calculations.
    Content is truncated gracefully when the terminal is too narrow.
    """
    agent_display = _agent_display_name(status.role)
    model_sym = model_symbol_for(status.model_code)
    agent_icn = agent_icon(status.role) if status.role else "¿Q?"

    # ---- Build three separate parts ----
    ver = version if version else "?"

    # Left: logo + version + agent name + spinner
    left = (
        f"╭─[ꝖꝖ]"
        f"─[v{ver}]"
        f"─❯❯❯"
        f" {agent_display}"
        f" {status.spinner_frame}"
    )

    # Center: compact stats — use shorter labels with dot separators
    # Cycle display: C=N (if unlimited) or C=N/M
    if status.max_cycles > 0:
        cycle_str = f"C={status.cycle}/{status.max_cycles}"
    else:
        cycle_str = f"C={status.cycle}/∞"
    # Time display: T=elapsed (if unlimited) or T=elapsed/max
    if status.max_time_seconds > 0:
        time_str = f"T={_fmt_time(status.run_elapsed_seconds)}/{_fmt_time(status.max_time_seconds)}"
    else:
        time_str = f"T={_fmt_time(status.run_elapsed_seconds)}"
    center = (
        f"{cycle_str}"
        f" · "
        f"{time_str}"
        f" · "
        f"A={_fmt_time(status.agent_elapsed_seconds)}"
        f" · "
        f"P={status.score}%"
    )

    # Right: agent icon + model symbol + Action status
    action_display = status.action_status if status.action_status else ""
    if action_display:
        right = (
            f"{agent_icn}"
            f"─[{model_sym}]"
            f"─[{action_display[:16]}]"
            f"─╮"
        )
    else:
        right = (
            f"{agent_icn}"
            f"─[{model_sym}]"
            f"─╮"
        )

    # ---- Dynamic layout using display-width (wcwidth) ----
    w = width if width is not None else 80
    left_w = _display_width(left)
    center_w = _display_width(center)
    right_w = _display_width(right)

    SEP = 1  # minimum spaces between parts
    min_needed = left_w + SEP + right_w

    if w < min_needed:
        # Too narrow for all three parts: show left only
        if left_w > w:
            # Truncate left to fit: keep agent name visible, trim version
            core = _truncate_left(left, w)
        else:
            core = left + " " * (w - left_w)
    else:
        center_region = w - left_w - right_w - 2 * SEP
        if center_region >= center_w:
            # Center fits: pad evenly on both sides
            pad_left = (center_region - center_w) // 2
            pad_right = center_region - center_w - pad_left
            core = (
                left
                + (" " * (SEP + pad_left))
                + center
                + (" " * (pad_right + SEP))
                + right
            )
        elif center_region >= 1:
            # Center too wide: progressive truncation, then pad to width
            trim_center = _truncate_center(center, center_region)
            trim_w = _display_width(trim_center)
            pad = center_region - trim_w
            core = left + (" " * SEP) + trim_center + (" " * (SEP + pad)) + right
        else:
            # Not enough room even for truncated center: left + right only
            fill = w - left_w - right_w
            if fill >= 1:
                core = left + (" " * fill) + right
            else:
                # Even left+right don't fit: truncate left
                core = _truncate_left(left, w - 1) + "…"

    # Handle colorization
    if color:
        core = _colorize_bar(core, status.role)

    return core


def _truncate_center(center: str, max_w: int) -> str:
    """Truncate center string progressively, keeping the most important fields.

    Priority order: C=N/M > P=N% > T=MM:SS > A=MM:SS

    Uses additive building approach: start with the most critical field and
    add more fields as space permits.
    """
    if _display_width(center) <= max_w:
        return center

    # Parse fields from center string
    parts = center.split(" · ")
    # Reconstruct additively: try 1 part, then 2, then 3, then 4
    for count in range(len(parts), 0, -1):
        shorter = " · ".join(parts[:count])
        if _display_width(shorter) <= max_w:
            return shorter

    # Even the first part is too wide: character-level truncation
    for i in range(len(center) - 1, 0, -1):
        if _display_width(center[:i]) + 1 <= max_w:
            return center[:i] + "…"
    return center[:max(1, max_w - 1)] + "…"


def _truncate_left(left: str, max_w: int) -> str:
    """Truncate left part, keeping agent name and spinner visible."""
    if _display_width(left) <= max_w:
        return left + " " * (max_w - _display_width(left))
    
    # Find agent_display + spinner at the end — try to preserve them
    # The left format is: ╭─[ꝖꝖ]─[v?.?.?]─❯❯❯ AgentName ⠁
    # We want to keep at minimum: AgentName ⠁
    # Find the last occurrence of ❯❯❯
    arrow_pos = left.rfind("❯❯❯")
    if arrow_pos >= 0:
        # Keep everything after ❯❯❯
        suffix = left[arrow_pos + 3:]  # " AgentName ⠁"
        suffix_w = _display_width(suffix)
        if suffix_w + 1 <= max_w:
            # Show abbreviated prefix + suffix
            prefix_w = max_w - suffix_w
            return left[:prefix_w - 1] + "…" + suffix
        elif suffix_w <= max_w:
            return suffix + " " * (max_w - suffix_w)
    
    # Last resort: character truncation
    for i in range(len(left) - 1, 0, -1):
        if _display_width(left[:i]) + 1 <= max_w:
            return left[:i] + "…"
    return left[:max_w - 1] + "…"
def _agent_display_name(role: str) -> str:
    mapping = {
        "qlarifier": "Qlarifier",
        "instruqtor": "instruQtor",
        "construqtor": "construQtor",
        "inspeqtor": "inspeQtor",
    }
    return mapping.get(role, role)


def _colorize_bar(line: str, role: str = "") -> str:
    """Apply QonQrete colors to the status bar.

    Colors are applied by searching for known segments in the built line,
    similar to how the Rust TUI paints colored segments on top.
    """
    import re as _re
    result = line

    # Frame start: ╭─
    result = result.replace(
        "\u256d\u2500",
        f"\033[{FRAME_GREY}m\u256d\u2500\033[0m",
    )
    # QQ logo: ꝖꝖ in gold
    result = result.replace(
        "\ua756\ua756",
        f"\033[{Q_GOLD}m\ua756\ua756\033[0m",
    )
    # Frame brackets around QQ and version
    result = _re.sub(
        r'(\u2500\[)',
        f"\033[{FRAME_GREY}m\\1\033[0m",
        result
    )
    result = _re.sub(
        r'(\]\u2500)',
        f"\033[{FRAME_GREY}m\\1\033[0m",
        result
    )
    # Frame line ─ before right chevrons in grey
    result = _re.sub(
        r'(\u2500)(\u276f)',
        f"\033[{FRAME_GREY}m\\1\033[0m\\2",
        result
    )
    # Chevrons ❯❯❯ in gold
    result = result.replace(
        "\u276f\u276f\u276f",
        f"\033[{Q_GOLD}m\u276f\u276f\u276f\033[0m",
    )
    # Version bracket: [vX.X.X]
    result = _re.sub(
        r'(\[v[^\]]+\])',
        f"\033[{FRAME_GREY}m\\1\033[0m",
        result
    )
    # Frame end: ─╮
    result = result.replace(
        "\u2500\u256e",
        f"\033[{FRAME_GREY}m\u2500\u256e\033[0m",
    )
    # Agent name in role color
    result = _colorize_agent_name(result)
    # Middle dots · in dim grey
    result = result.replace(
        " \u00b7 ",
        f"\033[{FRAME_GREY}m \u00b7 \033[0m",
    )
    # Chevrons left ❮❮❮
    result = result.replace(
        "\u276e\u276e\u276e",
        f"\033[{Q_GOLD}m\u276e\u276e\u276e\033[0m",
    )

    return result




def _colorize_agent_name(agent_spinner_text: str) -> str:
    """Put agent name in its role color."""
    for role_key, ansi_color in AGENT_COLORS.items():
        display_name = _agent_display_name(role_key)
        if display_name in agent_spinner_text:
            before, after = agent_spinner_text.split(display_name, 1)
            colored = (
                before +
                f"\033[{ansi_color}m{display_name}\033[0m" +
                after
            )
            return colored
    return agent_spinner_text


# ---------------------------------------------------------------------------
# Sticky status line (ANSI terminal management)
# ---------------------------------------------------------------------------
class StickyStatusLine:
    """Manages an ANSI sticky status line at the top or bottom of the terminal.

    Only activates when sink is a TTY. In non-TTY mode, acts as a no-op
    pass-through for stream lines.
    """

    def __init__(
        self,
        sink,
        *,
        position: Literal["off", "bottom", "top"] = "off",
        enabled: bool = True,
        color: bool = True,
        version: str = "",
    ):
        self._sink = sink
        self._position = position
        self._enabled = enabled
        self._color = color
        self._version = version
        self._started = False
        self._tty = self._check_tty()
        try:
            ts = shutil.get_terminal_size()
            self._cols = ts.columns
            self._rows = ts.lines
        except Exception:
            self._cols = 80
            self._rows = 24
        self._last_status: Optional[StreamActivityStatus] = None

        if position == "off":
            self._enabled = False
        elif not self._tty:
            self._enabled = False

    def _check_tty(self) -> bool:
        if hasattr(self._sink, 'isatty'):
            try:
                if self._sink.isatty():
                    return True
            except Exception:
                pass
        import os as _os
        if _os.environ.get('TMUX') or _os.environ.get('STY'):
            term = _os.environ.get('TERM', '')
            if term and term != 'dumb':
                return True
        return False

    @property
    def is_active(self) -> bool:
        return self._enabled and self._started

    def start(self) -> None:
        if not self._enabled:
            return
        if self._started:
            return
        self._started = True
        ts = shutil.get_terminal_size()
        self._cols = ts.columns
        self._rows = ts.lines
        if self._position == "bottom":
            # Reserve last row: scroll rows 1..(rows-1), status at row=rows
            self._write_raw(f"\033[s\033[1;{self._rows - 1}r")
        elif self._position == "top":
            # Reserve first row: scroll rows 2..rows, status at row=1
            self._write_raw(f"\033[s\033[2;{self._rows}r")

    def render(self, status: StreamActivityStatus) -> None:
        self._last_status = status
        if not self.is_active:
            return
        try:
            ts = shutil.get_terminal_size()
            self._cols = ts.columns
            self._rows = ts.lines
        except Exception:
            pass
        line = format_qonqrete_status_bar(
            status, color=self._color, width=self._cols, version=self._version)
        if self._position == "bottom":
            self._write_raw(f"\033[s\033[{self._rows};1H\033[K{line}\033[u")
        elif self._position == "top":
            self._write_raw(f"\033[s\033[1;1H\033[K{line}\033[u")
        try:
            self._sink.flush()
        except Exception:
            pass

    def write_stream_line(self, text: str) -> None:
        if not self.is_active:
            self._write_raw(text)
            return
        self._write_raw(f"\033[s{text}\033[u")
        try:
            self._sink.flush()
        except Exception:
            pass

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        try:
            self._write_raw("\033[r")
            if self._position == "bottom":
                self._write_raw(f"\033[{self._rows};1H\033[K")
            elif self._position == "top":
                self._write_raw("\033[1;1H\033[K")
            self._write_raw("\033[u")
            self._sink.flush()
        except Exception:
            pass

    def _write_raw(self, text: str) -> None:
        try:
            self._sink.write(text)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Spinner manager
# ---------------------------------------------------------------------------
class SpinnerManager:
    """Manages per-stream spinner state for the sticky line."""

    def __init__(self):
        self._states: Dict[Tuple[str, str, str], int] = {}
        self._current_key: Optional[Tuple[str, str, str]] = None
        self._last_tick: float = 0.0

    def advance(self, role: str, stream_name: str, call_id: str) -> str:
        key = (role, stream_name, call_id or "")
        idx = self._states.get(key, 0)
        frame = BRAILLE_SNAKE[idx]
        self._states[key] = (idx + 1) % len(BRAILLE_SNAKE)
        self._current_key = key
        self._last_tick = time_mod.monotonic()
        return frame

    def advance_right_spinner(self) -> str:
        """Advance the quarter-circle spinner and return the current frame."""
        if not hasattr(self, '_right_spinner_idx'):
            self._right_spinner_idx = 0
        frame = QUARTER_CIRCLE_SPINNER[self._right_spinner_idx]
        self._right_spinner_idx = (self._right_spinner_idx + 1) % len(QUARTER_CIRCLE_SPINNER)
        return frame

    def get_current_right_frame(self) -> str:
        """Get the current quarter-circle spinner frame without advancing."""
        if not hasattr(self, '_right_spinner_idx'):
            self._right_spinner_idx = 0
        return QUARTER_CIRCLE_SPINNER[self._right_spinner_idx]

    def get_current_frame(self) -> str:
        if self._current_key is None:
            return BRAILLE_SNAKE[0]
        idx = self._states.get(self._current_key, 0)
        if idx == 0:
            return BRAILLE_SNAKE[0]
        idx = (idx - 1) % len(BRAILLE_SNAKE)
        return BRAILLE_SNAKE[idx]

    def idle_tick(self) -> Optional[str]:
        now = time_mod.monotonic()
        if now - self._last_tick < 0.16:
            return None
        if self._current_key is None:
            return None
        role, stream, call_id = self._current_key
        return self.advance(role, stream, call_id)

    def reset(self, role: str, call_id: str) -> None:
        key = (role, "stdout", call_id or "")
        stderr_key = (role, "stderr", call_id or "")
        if stderr_key in self._states:
            self._states[stderr_key] = 0
        self._states[key] = 0
        self._current_key = key
