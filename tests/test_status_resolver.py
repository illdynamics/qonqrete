"""
Tests for the canonical final-status resolver and related helpers.
"""
import json
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qq.web.status_resolver import (
    resolve_final_status,
    resolve_display_name,
    resolve_runner_metadata,
    is_fully_done,
    generate_final_status_shell_script,
)


class TestResolveFinalStatus:
    def test_fully_done_from_final_json(self):
        """Resolve FULLY_DONE from state/final.json."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "final.json"), "w") as f:
                json.dump({
                    "status": "done",
                    "final_verdict": {"status": "FULLY_DONE", "score": 100},
                    "cycle": 3,
                }, f)
            assert resolve_final_status(tmp) == "FULLY_DONE"
            assert is_fully_done(tmp) is True

    def test_fully_done_from_status_field(self):
        """Resolve FULLY_DONE when it's in the top-level status field."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "final.json"), "w") as f:
                json.dump({"status": "FULLY_DONE", "cycle": 1}, f)
            assert resolve_final_status(tmp) == "FULLY_DONE"

    def test_not_done_from_review_verdict(self):
        """Resolve NOT_DONE from events.jsonl when no final.json exists."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "review.verdict", "status": "NOT_DONE", "cycle": 2}, f)
                f.write("\n")
            assert resolve_final_status(tmp) == "NOT_DONE"
            assert is_fully_done(tmp) is False

    def test_fallback_to_run_completed(self):
        """Fall back to run.completed event when no final.json or verdict exists."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.completed", "status": "success"}, f)
                f.write("\n")
            assert resolve_final_status(tmp) == "success"

    def test_fallback_to_runner_exit_code(self):
        """Fall back to runner.exit_code when no events or final.json."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "runner.finished"), "w") as f:
                f.write("2024-01-01T00:00:00Z")
            with open(os.path.join(tmp, "runner.exit_code"), "w") as f:
                f.write("0")
            assert resolve_final_status(tmp) == "finished"

    def test_runner_nonzero_exit(self):
        """Nonzero exit code without final.json -> failed."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "runner.finished"), "w") as f:
                f.write("2024-01-01T00:00:00Z")
            with open(os.path.join(tmp, "runner.exit_code"), "w") as f:
                f.write("1")
            assert resolve_final_status(tmp) == "failed"

    def test_none_when_no_sources(self):
        """Return None when no state sources exist."""
        with tempfile.TemporaryDirectory() as tmp:
            assert resolve_final_status(tmp) is None
            assert is_fully_done(tmp) is False

    def test_case_insensitive_fully_done(self):
        """Accept case variations of FULLY_DONE."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "final.json"), "w") as f:
                json.dump({"final_verdict": {"status": "fully_done"}}, f)
            assert is_fully_done(tmp) is True

    def test_whitespace_normalization(self):
        """Trim whitespace from status values."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "final.json"), "w") as f:
                json.dump({"final_verdict": {"status": "  FULLY_DONE  "}}, f)
            assert resolve_final_status(tmp) == "FULLY_DONE"


class TestResolveDisplayName:
    def test_from_task_json_title(self):
        """Resolve display name from state/task.json task_title."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "task.json"), "w") as f:
                json.dump({"task_title": "Build a REST API", "raw_text": "some text"}, f)
            assert resolve_display_name(tmp) == "Build a REST API"

    def test_from_task_original_md(self):
        """Fall back to artifacts/task-original.md first line."""
        with tempfile.TemporaryDirectory() as tmp:
            arts_dir = os.path.join(tmp, "artifacts")
            os.makedirs(arts_dir)
            with open(os.path.join(arts_dir, "task-original.md"), "w") as f:
                f.write("# My Heading\n\nActual task description here.\n")
            assert resolve_display_name(tmp) == "My Heading"

    def test_from_run_root_basename(self):
        """Fall back to run root basename."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "20260709-140126-77f11553")
            os.makedirs(run_dir)
            assert resolve_display_name(run_dir) == "20260709-140126-77f11553"

    def test_untitled_task_fallback(self):
        """Fall back to 'Untitled task' when nothing available."""
        # Note: resolve_display_name will return the run root basename
        # if no other data is available. The "Untitled task" fallback
        # only triggers when there's literally no basename to use.
        assert resolve_display_name("") == "Untitled task"


class TestResolveRunnerMetadata:
    def test_tmux_from_runner_json(self):
        """Resolve tmux mode from state/runner.json."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "runner.json"), "w") as f:
                json.dump({
                    "mode": "tmux",
                    "session": "qonqrete-test123",
                    "started_at": "2024-01-01T00:00:00Z",
                }, f)
            meta = resolve_runner_metadata(tmp)
            assert meta["mode"] == "tmux"
            assert meta["session"] == "qonqrete-test123"

    def test_local_from_runner_json(self):
        """Resolve local mode from state/runner.json."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "runner.json"), "w") as f:
                json.dump({
                    "mode": "local",
                    "pid": 12345,
                }, f)
            meta = resolve_runner_metadata(tmp)
            assert meta["mode"] == "local"
            assert meta["pid"] == 12345

    def test_unknown_with_no_sources(self):
        """Return unknown when no runner metadata exists."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = resolve_runner_metadata(tmp)
            assert meta["mode"] == "unknown"

    def test_finished_at_from_marker(self):
        """Read finished_at from runner.finished marker."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "runner.finished"), "w") as f:
                f.write("2024-06-15T10:30:00Z")
            meta = resolve_runner_metadata(tmp)
            assert meta["finished_at"] == "2024-06-15T10:30:00Z"


class TestShellScriptGeneration:
    def test_generates_valid_shell(self):
        """Generate a shell script that is syntactically valid."""
        script = generate_final_status_shell_script(
            "/tmp/test_run", "qonqrete-test123"
        )
        assert "FULLY_DONE" in script
        assert "resolve_final_status" in script
        assert "runner.exit_code" in script
        assert "runner.finished" in script
        # Should NOT contain broken ANSI escapes
        assert "\\033" not in script
        assert "\\e" not in script

    def test_plain_text_output(self):
        """Shell script uses plain text, not ANSI color codes."""
        script = generate_final_status_shell_script(
            "/tmp/test_run", "qonqrete-test456"
        )
        # Should use plain text "FULLY_DONE" without color codes
        assert "status: FULLY_DONE. Session:" in script
        assert "\033" not in script  # No ANSI escapes


class TestFirstNonEmptyLine:
    def test_skips_headings(self):
        """_first_non_empty_line strips markdown headings."""
        from qq.web.status_resolver import _first_non_empty_line
        assert _first_non_empty_line("# Title\nBody") == "Title"
        assert _first_non_empty_line("## Subtitle\nText") == "Subtitle"
        assert _first_non_empty_line("\n\nActual text") == "Actual text"
        assert _first_non_empty_line("") is None


class TestResolveFinalStatusDefensive:
    """Non-string / malformed verdict & status payloads must never raise —
    these occur during the inspeQtor/reviewing phase and are the root
    cause of the web UI 502."""

    def _write_final(self, tmp, payload):
        state_dir = os.path.join(tmp, "state")
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "final.json"), "w") as f:
            json.dump(payload, f)

    def test_dict_status_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_final(tmp, {"status": {"x": 1}, "cycle": 1})
            # must not raise
            resolve_final_status(tmp)

    def test_int_verdict_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_final(tmp, {"final_verdict": {"status": 123}, "cycle": 1})
            assert resolve_final_status(tmp) is None

    def test_dict_action_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_final(tmp, {"action": {"a": 1}})
            assert resolve_final_status(tmp) is None

    def test_none_verdict_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_final(tmp, {"final_verdict": None, "status": "done"})
            assert resolve_final_status(tmp) == "done"

    def test_list_verdict_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_final(tmp, {"final_verdict": [1, 2, 3]})
            assert resolve_final_status(tmp) is None
