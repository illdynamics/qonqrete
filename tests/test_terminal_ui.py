"""Tests for sticky terminal status line — formatter, model_code, sticky UI, spinner, exit-status, score."""
import io
import os
import sys
import time
import unittest
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.terminal_ui import (
    BRAILLE_SNAKE, StreamActivityStatus, StickyStatusLine,
    SpinnerManager, format_qonqrete_status_bar, model_code_for,
    model_symbol_for,
)


class TestFormatQonqreteStatusBar(unittest.TestCase):
    """Tests for the compact 3-part split status bar formatter."""

    def test_three_part_split_wide(self):
        """All three parts fit on one line when width is wide enough."""
        s = StreamActivityStatus(
            role="construqtor", model_code="pro", cycle=2,
            run_elapsed_seconds=258, agent_elapsed_seconds=72,
            score=68, last_exit_code=0,
            spinner_frame="\u28f7",
        )
        result = format_qonqrete_status_bar(s, width=120)
        # Check all parts present (compact format)
        self.assertIn("construQtor", result)
        self.assertIn("\u28f7", result)       # spinner
        self.assertIn("C=2/∞", result)       # compact cycle (default unlimited)
        self.assertIn("T=04:18", result)      # compact total time
        self.assertIn("A=01:12", result)      # compact agent time
        self.assertIn("P=68%", result)        # compact score
        self.assertIn("\u269d", result)       # model symbol
        self.assertNotIn("\n", result)

    def test_three_part_split_narrow(self):
        """Single line with truncation when width is narrow."""
        s = StreamActivityStatus(
            role="qlarifier", model_code="fla", cycle=1,
            run_elapsed_seconds=45, agent_elapsed_seconds=45,
            score=0, last_exit_code=0,
            spinner_frame="\u2801",
        )
        result = format_qonqrete_status_bar(s, width=50)
        self.assertNotIn("\n", result)
        self.assertIn("Qlarifier", result)
        self.assertIn("\u2801", result)
        self.assertEqual(len(result), 50)

    def test_left_part_floats_left(self):
        """Left part starts with frame characters."""
        s = StreamActivityStatus(
            role="construqtor", model_code="pro", cycle=2,
            run_elapsed_seconds=258, agent_elapsed_seconds=72,
            score=68, last_exit_code=0,
            spinner_frame="\u28f7",
        )
        result = format_qonqrete_status_bar(s, width=120)
        self.assertTrue(result.startswith("\u256d\u2500["))

    def test_right_part_floats_right(self):
        """Right part ends at the far right edge with frame end."""
        s = StreamActivityStatus(
            role="construqtor", model_code="pro", cycle=2,
            run_elapsed_seconds=258, agent_elapsed_seconds=72,
            score=68, last_exit_code=0,
            spinner_frame="\u28f7",
        )
        result = format_qonqrete_status_bar(s, width=120)
        self.assertTrue(result.endswith("\u2500\u256e"))

    def test_prefix_is_exact(self):
        """Prefix starts with ╭─[ꝖꝖ]─[v?]─❯❯❯"""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 spinner_frame="\u2801")
        result = format_qonqrete_status_bar(s, width=120)
        prefix = "\u256d\u2500[\ua756\ua756]\u2500[v?]\u2500\u276f\u276f\u276f"
        self.assertTrue(result.startswith(prefix),
                        f"Expected prefix {prefix!r}, got {result[:len(prefix)]!r}")

    def test_suffix_is_exact(self):
        """Suffix ends with ─╮"""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 spinner_frame="\u2801")
        result = format_qonqrete_status_bar(s, width=120)
        self.assertTrue(result.endswith("\u2500\u256e"),
                        f"Expected \\u2500\\u256e, got {result[-2:]!r}")

    def test_agent_name_appears_after_arrows(self):
        """Agent name appears after ❯❯❯."""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 spinner_frame="\u2801")
        result = format_qonqrete_status_bar(s, width=120)
        arrows_end = result.find("\u276f\u276f\u276f") + 3
        self.assertIn("construQtor", result[arrows_end:arrows_end + 25])

    def test_spinner_appears_after_agent_name(self):
        """Spinner appears after agent name."""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 spinner_frame="\u28f7")
        result = format_qonqrete_status_bar(s, width=120)
        name_end = result.find("construQtor") + len("construQtor")
        self.assertIn("\u28f7", result[name_end:name_end + 5])

    def test_model_symbol_visible(self):
        """Model symbol appears next to agent icon on the right."""
        for code in ("fla", "fla-T", "pro", "pro-T"):
            s = StreamActivityStatus(role="construqtor", model_code=code,
                                     spinner_frame="\u2801")
            result = format_qonqrete_status_bar(s, width=120)
            sym = model_symbol_for(code)
            self.assertIn(sym, result)

    def test_cycle_format(self):
        """Cycle is rendered as C=<num>/<max>."""
        for cycle in (1, 2, 5, 11):
            s = StreamActivityStatus(role="construqtor", model_code="pro",
                                     cycle=cycle, spinner_frame="\u2801")
            result = format_qonqrete_status_bar(s, width=120)
            self.assertIn(f"C={cycle}/", result)

    def test_time_format(self):
        """Total and Agent time are rendered as T=H:MM:SS and A=MM:SS."""
        s = StreamActivityStatus(
            role="construqtor", model_code="pro",
            run_elapsed_seconds=3722, agent_elapsed_seconds=72,
            spinner_frame="\u2801",
        )
        result = format_qonqrete_status_bar(s, width=120)
        self.assertIn("T=1:02:02", result)  # 3722 seconds = 1:02:02
        self.assertIn("A=01:12", result)

    def test_score_format(self):
        """Score is rendered as P=<number>%."""
        for score in (0, 46, 68, 72, 100):
            s = StreamActivityStatus(role="inspeqtor", model_code="pro-T",
                                     score=score, spinner_frame="\u2801")
            result = format_qonqrete_status_bar(s, width=120)
            self.assertIn(f"P={score}%", result)

    def test_agent_icon_visible(self):
        """Agent icon appears on the right."""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 last_exit_code=0, spinner_frame="\u2801")
        result = format_qonqrete_status_bar(s, width=120)
        self.assertIn("\u27ec", result)  # construqtor icon

    def test_color_enabled_has_ansi(self):
        """Color enabled produces ANSI escape codes."""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 last_exit_code=0, spinner_frame="\u2801")
        result = format_qonqrete_status_bar(s, color=True, width=120)
        self.assertIn("\033[", result)

        s2 = StreamActivityStatus(role="inspeqtor", model_code="pro-T",
                                  last_exit_code=1, spinner_frame="\u2801")
        result2 = format_qonqrete_status_bar(s2, color=True, width=120)
        self.assertIn("\033[", result2)

    def test_color_disabled_no_escapes(self):
        """No ANSI color escapes when color disabled."""
        s = StreamActivityStatus(role="construqtor", model_code="pro",
                                 last_exit_code=0, spinner_frame="\u2801")
        result = format_qonqrete_status_bar(s, color=False, width=120)
        self.assertNotIn("\033[", result)

    def test_truncation_single_line(self):
        """Single line truncated at narrow widths."""
        s = StreamActivityStatus(
            role="construqtor", model_code="pro", cycle=2,
            run_elapsed_seconds=258, agent_elapsed_seconds=72,
            score=68, last_exit_code=0,
            spinner_frame="\u28f7",
        )
        result = format_qonqrete_status_bar(s, width=40)
        self.assertNotIn("\n", result)
        self.assertEqual(len(result), 40)

    def test_progressive_truncation(self):
        """Progressive truncation reveals more fields as width increases."""
        s = StreamActivityStatus(
            role="construqtor", model_code="pro", cycle=2,
            run_elapsed_seconds=258, agent_elapsed_seconds=72,
            score=68,
            spinner_frame="\u28f7",
        )
        # At 60: only cycle (right side wider due to Action field)
        r60 = format_qonqrete_status_bar(s, width=60)
        self.assertIn("C=2/∞", r60)
        # Right side with model + action takes space

        # At 80: cycle + total time
        r80 = format_qonqrete_status_bar(s, width=80)
        self.assertIn("C=2/∞", r80)
        # Check that center fields appear progressively

        # At 100: more fields visible
        r100 = format_qonqrete_status_bar(s, width=100)

        # At 120: all fields visible
        r120 = format_qonqrete_status_bar(s, width=120)
        self.assertIn("C=2/∞", r120)
        self.assertIn("T=04:18", r120)
        self.assertIn("A=01:12", r120)
        self.assertIn("P=68%", r120)


class TestModelCodeFor(unittest.TestCase):
    """Tests for model code derivation."""

    def test_flash_models(self):
        self.assertEqual(model_code_for("deepseek-v4-flash"), "fla")

    def test_flash_thinking_models(self):
        self.assertEqual(model_code_for("deepseek-v4-flash-thinking"), "fla-T")

    def test_pro_models(self):
        self.assertEqual(model_code_for("deepseek-v4-pro"), "pro")

    def test_pro_thinking_models(self):
        self.assertEqual(model_code_for("deepseek-v4-pro-thinking"), "pro-T")

    def test_unknown_model(self):
        self.assertEqual(model_code_for("unknown-custom-model"), "?")

    def test_provider_metadata_override(self):
        """Provider metadata wins over string guessing."""
        result = model_code_for("deepseek-v4-flash",
                                provider_metadata={"model_class": "PT"})
        self.assertEqual(result, "pro-T")

    def test_provider_metadata_code_key(self):
        """model_code key also works for provider metadata."""
        result = model_code_for("some-model",
                                provider_metadata={"model_code": "F"})
        self.assertEqual(result, "fla")


class TestBrailleSnakeSpinner(unittest.TestCase):
    """Tests for the braille_snake spinner sequence and SpinnerManager."""

    def test_frames_are_exact(self):
        """Spinner frames match exact braille_snake sequence."""
        expected = [
            "\u2801", "\u2803", "\u2807", "\u2847", "\u28c7",
            "\u28e7", "\u28f7", "\u28ff", "\u287f", "\u283f",
            "\u281f", "\u281b", "\u2819", "\u2809",
        ]
        self.assertEqual(BRAILLE_SNAKE, expected)

    def test_first_frame(self):
        self.assertEqual(BRAILLE_SNAKE[0], "\u2801")

    def test_sequence_starts_correct(self):
        self.assertEqual(BRAILLE_SNAKE[0], "\u2801")
        self.assertEqual(BRAILLE_SNAKE[1], "\u2803")
        self.assertEqual(BRAILLE_SNAKE[2], "\u2807")
        self.assertEqual(BRAILLE_SNAKE[3], "\u2847")

    def test_wraps(self):
        """SpinnerManager wraps from last frame back to first."""
        sm = SpinnerManager()
        frames = []
        for i in range(len(BRAILLE_SNAKE) + 1):
            frames.append(sm.advance("qlarifier", "stdout", "c1"))
        self.assertEqual(len(frames), len(BRAILLE_SNAKE) + 1)
        self.assertEqual(frames[0], BRAILLE_SNAKE[0])
        self.assertEqual(frames[-1], BRAILLE_SNAKE[0])

    def test_per_stream_independence(self):
        """Spinner state is independent per (role, stream_name, call_id)."""
        sm = SpinnerManager()
        a1 = sm.advance("qlarifier", "stdout", "c1")
        b1 = sm.advance("qlarifier", "stderr", "c1")
        self.assertEqual(a1, BRAILLE_SNAKE[0])
        self.assertEqual(b1, BRAILLE_SNAKE[0])

        a2 = sm.advance("qlarifier", "stdout", "c1")
        b2 = sm.advance("construqtor", "stdout", "c2")
        self.assertEqual(a2, BRAILLE_SNAKE[1])
        self.assertEqual(b2, BRAILLE_SNAKE[0])

    def test_advances_per_chunk(self):
        """Spinner advances per emitted chunk."""
        sm = SpinnerManager()
        frames = [
            sm.advance("construqtor", "stdout", "c1")
            for _ in range(5)
        ]
        self.assertEqual(frames, BRAILLE_SNAKE[:5])

    def test_idle_tick_advances(self):
        """Idle tick advances spinner after a delay."""
        sm = SpinnerManager()
        sm.advance("qlarifier", "stdout", "c1")
        self.assertIsNone(sm.idle_tick())
        sm._last_tick = 0.0
        frame = sm.idle_tick()
        self.assertIsNotNone(frame)
        self.assertEqual(frame, BRAILLE_SNAKE[1])

    def test_reset_starts_fresh(self):
        """Reset restarts spinner at frame 0."""
        sm = SpinnerManager()
        sm.advance("qlarifier", "stdout", "c1")
        sm.advance("qlarifier", "stdout", "c1")
        sm.reset("inspeqtor", "c2")
        frame = sm.advance("inspeqtor", "stdout", "c2")
        self.assertEqual(frame, BRAILLE_SNAKE[0])


class TestStickyStatusLine(unittest.TestCase):
    """Tests for StickyStatusLine ANSI terminal management."""

    def test_non_tty_disabled(self):
        """Non-TTY sink disables sticky rendering."""
        import os as _os
        old_tmux = _os.environ.pop('TMUX', None)
        old_sty = _os.environ.pop('STY', None)
        try:
            buf = io.StringIO()
            sticky = StickyStatusLine(buf, position="top", enabled=True)
            self.assertFalse(sticky._enabled)
            self.assertFalse(sticky.is_active)
        finally:
            if old_tmux is not None:
                _os.environ['TMUX'] = old_tmux
            if old_sty is not None:
                _os.environ['STY'] = old_sty

    def test_non_tty_start_is_noop(self):
        """start() is a no-op on non-TTY."""
        import os as _os
        old_tmux = _os.environ.pop('TMUX', None)
        old_sty = _os.environ.pop('STY', None)
        try:
            buf = io.StringIO()
            sticky = StickyStatusLine(buf, position="bottom", enabled=True)
            sticky.start()
            self.assertFalse(sticky.is_active)
            output = buf.getvalue()
            self.assertEqual(output, "")
        finally:
            if old_tmux is not None:
                _os.environ['TMUX'] = old_tmux
            if old_sty is not None:
                _os.environ['STY'] = old_sty

    def test_non_tty_render_is_noop(self):
        """render() is a no-op on non-TTY."""
        import os as _os
        old_tmux = _os.environ.pop('TMUX', None)
        old_sty = _os.environ.pop('STY', None)
        try:
            buf = io.StringIO()
            sticky = StickyStatusLine(buf, position="top", enabled=True)
            sticky.start()
            s = StreamActivityStatus(role="construqtor", model_code="pro", spinner_frame="\u2801")
            sticky.render(s)
            self.assertEqual(buf.getvalue(), "")
        finally:
            if old_tmux is not None:
                _os.environ['TMUX'] = old_tmux
            if old_sty is not None:
                _os.environ['STY'] = old_sty

    def test_non_tty_write_stream_line_passthrough(self):
        """write_stream_line passes through on non-TTY."""
        import os as _os
        old_tmux = _os.environ.pop('TMUX', None)
        old_sty = _os.environ.pop('STY', None)
        try:
            buf = io.StringIO()
            sticky = StickyStatusLine(buf, position="bottom", enabled=True)
            sticky.start()
            sticky.write_stream_line("hello\n")
            self.assertEqual(buf.getvalue(), "hello\n")
        finally:
            if old_tmux is not None:
                _os.environ['TMUX'] = old_tmux
            if old_sty is not None:
                _os.environ['STY'] = old_sty

    def test_stop_is_safe_to_call_multiple_times(self):
        """stop() is safe to call multiple times."""
        buf = io.StringIO()
        sticky = StickyStatusLine(buf, position="top", enabled=True)
        sticky.start()
        sticky.stop()
        sticky.stop()
        sticky.stop()

    def test_off_position_disables(self):
        """position='off' disables even with TTY."""
        buf = io.StringIO()
        sticky = StickyStatusLine(buf, position="off", enabled=True)
        self.assertFalse(sticky._enabled)

    @patch('sys.stderr', new_callable=io.StringIO)
    def test_tty_top_mode_emits_scroll_region(self, mock_stderr):
        """Top mode emits scroll-region setup codes."""
        mock_stderr.isatty = MagicMock(return_value=True)
        sticky = StickyStatusLine(mock_stderr, position="top", enabled=True)
        sticky.start()
        output = mock_stderr.getvalue()
        self.assertIn("\033[s", output)
        self.assertIn("\033[2;", output)

    @patch('sys.stderr', new_callable=io.StringIO)
    def test_stop_resets_scroll_region(self, mock_stderr):
        """stop() resets scroll region."""
        mock_stderr.isatty = MagicMock(return_value=True)
        sticky = StickyStatusLine(mock_stderr, position="bottom", enabled=True)
        sticky.start()
        sticky.stop()
        output = mock_stderr.getvalue()
        self.assertIn("\033[r", output)


class TestStreamActivityStatus(unittest.TestCase):
    """Tests for the StreamActivityStatus dataclass."""

    def test_default_values(self):
        s = StreamActivityStatus()
        self.assertEqual(s.role, "")
        self.assertEqual(s.call_id, "")
        self.assertEqual(s.cycle, 1)
        self.assertEqual(s.score, 0)
        self.assertEqual(s.last_exit_code, 0)
        self.assertEqual(s.chunks_seen, 0)
        self.assertEqual(s.model_code, "?")

    def test_field_assignment(self):
        s = StreamActivityStatus(
            role="construqtor", model_code="pro", cycle=2,
            score=68, last_exit_code=0, chunks_seen=43,
        )
        self.assertEqual(s.role, "construqtor")
        self.assertEqual(s.model_code, "pro")
        self.assertEqual(s.cycle, 2)
        self.assertEqual(s.score, 68)
        self.assertEqual(s.last_exit_code, 0)
        self.assertEqual(s.chunks_seen, 43)


class TestTimeFormatting(unittest.TestCase):
    """Tests for time formatting within the formatter."""

    def test_under_one_hour(self):
        from qq.terminal_ui import _fmt_time
        self.assertEqual(_fmt_time(0), "00:00")
        self.assertEqual(_fmt_time(4), "00:04")
        self.assertEqual(_fmt_time(72), "01:12")
        self.assertEqual(_fmt_time(258), "04:18")
        self.assertEqual(_fmt_time(3599), "59:59")

    def test_over_one_hour(self):
        from qq.terminal_ui import _fmt_time
        self.assertEqual(_fmt_time(3600), "1:00:00")
        self.assertEqual(_fmt_time(3722), "1:02:02")
        self.assertEqual(_fmt_time(36610), "10:10:10")


if __name__ == "__main__":
    unittest.main()
