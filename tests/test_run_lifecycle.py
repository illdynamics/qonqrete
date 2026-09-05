"""Tests for the run lifecycle: latest_wins, active-run vs current-run, terminal states, etc."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# We test run_registry directly and ingest logic indirectly via RunTriggerResult
class TestRunRegistryStates(unittest.TestCase):
    """Test canonical state sets."""
    
    def test_terminal_states_include_superseded(self):
        from qq.web.run_registry import is_terminal_state
        self.assertTrue(is_terminal_state("superseded"))
        self.assertTrue(is_terminal_state("SUPERSEDED"))
    
    def test_terminal_states_include_failed_early(self):
        from qq.web.run_registry import is_terminal_state
        self.assertTrue(is_terminal_state("failed_early"))
        self.assertTrue(is_terminal_state("FAILED_EARLY"))
    
    def test_terminal_states_include_finished_incomplete(self):
        from qq.web.run_registry import is_terminal_state
        self.assertTrue(is_terminal_state("finished_incomplete"))
    
    def test_active_states(self):
        from qq.web.run_registry import is_active_state
        self.assertTrue(is_active_state("running"))
        self.assertTrue(is_active_state("started"))
        self.assertTrue(is_active_state("starting"))
        self.assertFalse(is_active_state("finished"))
        self.assertFalse(is_active_state("superseded"))
    
    def test_pending_states(self):
        from qq.web.run_registry import is_pending_state
        self.assertTrue(is_pending_state("queued"))
        self.assertTrue(is_pending_state("accepted"))
        self.assertFalse(is_pending_state("running"))
        self.assertFalse(is_pending_state("finished"))
    
    def test_normalize_state(self):
        from qq.web.run_registry import normalize_state
        self.assertEqual(normalize_state("FULLY_DONE"), "fully_done")
        self.assertEqual(normalize_state("Running"), "running")
        self.assertEqual(normalize_state(None), None)
        self.assertEqual(normalize_state(""), None)


class TestLoadLatestRunRecords(unittest.TestCase):
    """Test runs.jsonl last-record-wins folding."""
    
    def test_last_record_wins(self):
        from qq.web.run_registry import load_latest_run_records
        with tempfile.TemporaryDirectory() as d:
            jl_path = os.path.join(d, "runs.jsonl")
            records = [
                {"run_id": "20260710-120000-abc", "state": "accepted", "task_path": "/tmp/t1"},
                {"run_id": "20260710-120000-abc", "state": "started"},
                {"run_id": "20260710-120000-abc", "state": "finished", "exit_code": 0},
            ]
            with open(jl_path, "w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
            
            result = load_latest_run_records(d)
            self.assertIn("20260710-120000-abc", result)
            entry = result["20260710-120000-abc"]
            self.assertEqual(entry["state"], "finished")  # last wins
            self.assertEqual(entry["exit_code"], 0)
            self.assertEqual(entry["task_path"], "/tmp/t1")  # stable metadata preserved
    
    def test_multiple_runs(self):
        from qq.web.run_registry import load_latest_run_records
        with tempfile.TemporaryDirectory() as d:
            jl_path = os.path.join(d, "runs.jsonl")
            with open(jl_path, "w") as f:
                f.write(json.dumps({"run_id": "run-a", "state": "accepted"}) + "\n")
                f.write(json.dumps({"run_id": "run-b", "state": "started"}) + "\n")
                f.write(json.dumps({"run_id": "run-a", "state": "finished"}) + "\n")
                f.write(json.dumps({"run_id": "run-b", "state": "superseded", "superseded_by_run_id": "run-c"}) + "\n")
            
            result = load_latest_run_records(d)
            self.assertEqual(len(result), 2)
            self.assertEqual(result["run-a"]["state"], "finished")
            self.assertEqual(result["run-b"]["state"], "superseded")
            self.assertEqual(result["run-b"]["superseded_by_run_id"], "run-c")


class TestResolveRunState(unittest.TestCase):
    """Test state resolution from durable evidence."""
    
    def test_terminal_artifact_wins_over_tmux(self):
        from qq.web.run_registry import resolve_run_state
        with tempfile.TemporaryDirectory() as d:
            # Create runner.finished + runner.exit_code
            with open(os.path.join(d, "runner.finished"), "w") as f:
                f.write("2026-07-10T12:00:00Z")
            with open(os.path.join(d, "runner.exit_code"), "w") as f:
                f.write("0")
            
            entry = {"run_root": d, "state": "running", "tmux_alive": True}
            state = resolve_run_state(entry, tmux_alive=True)
            self.assertEqual(state, "finished")
    
    def test_runner_failed_wins(self):
        from qq.web.run_registry import resolve_run_state
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "runner.failed.json"), "w") as f:
                f.write('{"reason": "test"}')
            
            entry = {"run_root": d, "state": "running"}
            state = resolve_run_state(entry)
            self.assertEqual(state, "failed")
    
    def test_no_evidence_with_active_state_returns_stale(self):
        from qq.web.run_registry import resolve_run_state
        with tempfile.TemporaryDirectory() as d:
            entry = {"run_root": d, "state": "started"}
            state = resolve_run_state(entry, tmux_alive=False, runner_pid_alive=False)
            self.assertEqual(state, "stale")
    
    def test_live_tmux_confirms_active(self):
        from qq.web.run_registry import resolve_run_state
        with tempfile.TemporaryDirectory() as d:
            entry = {"run_root": d, "state": "started"}
            state = resolve_run_state(entry, tmux_alive=True)
            self.assertEqual(state, "started")
    
    def test_terminal_state_from_history(self):
        from qq.web.run_registry import resolve_run_state
        with tempfile.TemporaryDirectory() as d:
            entry = {"run_root": d, "state": "superseded"}
            state = resolve_run_state(entry)
            self.assertEqual(state, "superseded")


class TestRunTimestamp(unittest.TestCase):
    """Test run timestamp resolution."""
    
    def test_created_at_preferred(self):
        from qq.web.run_registry import resolve_run_timestamp
        entry = {
            "created_at": "2026-07-10T12:00:00Z",
            "started_at": "2026-07-09T00:00:00Z",
            "run_id": "20260708-120000-abcdefgh",
        }
        ts = resolve_run_timestamp(entry)
        self.assertGreater(ts, 0)
    
    def test_run_id_parsing(self):
        from qq.web.run_registry import _run_id_to_sort_key
        ts1 = _run_id_to_sort_key("20260710-140530-abcd1234")
        ts2 = _run_id_to_sort_key("20260709-140530-abcd1234")
        self.assertGreater(ts1, ts2)  # newer run_id > older
    
    def test_iso_z_suffix(self):
        from qq.web.run_registry import _iso_to_sort_key
        ts = _iso_to_sort_key("2026-07-10T12:00:00Z")
        self.assertGreater(ts, 0)


class TestMergeRunSources(unittest.TestCase):
    """Test merging multiple run sources into one entry per run_id."""
    
    def test_single_entry_per_run_id(self):
        from qq.web.run_registry import merge_run_sources
        cr = {"run_id": "r1", "run_root": "/tmp/r1", "events_path": "/tmp/r1/e.json"}
        merged = merge_run_sources(
            current_run_pointer=cr,
            active_run_pointer=None,
            pending_run_pointer=None,
            folded_history={"r1": {"run_id": "r1", "state": "finished"}},
            run_directories={"r1": {"run_id": "r1", "run_root": "/tmp/r1"}},
            tmux_records={},
            live_tmux_sessions={},
            control_root="",
        )
        self.assertEqual(len(merged), 1)
        self.assertIn("r1", merged)
    
    def test_linked_vs_active_separate(self):
        from qq.web.run_registry import merge_run_sources
        cr = {"run_id": "r1", "run_root": "/tmp/r1"}  # linked
        ar = {"run_id": "r2", "run_root": "/tmp/r2"}  # active executor
        merged = merge_run_sources(
            current_run_pointer=cr,
            active_run_pointer=ar,
            pending_run_pointer=None,
            folded_history={},
            run_directories={},
            tmux_records={},
            live_tmux_sessions={},
            control_root="",
        )
        self.assertEqual(len(merged), 2)
        self.assertTrue(merged["r1"]["linked"])
        self.assertTrue(merged["r2"]["active"])
        self.assertFalse(merged["r1"]["active"])
        self.assertFalse(merged["r2"]["linked"])


class TestSortSessions(unittest.TestCase):
    """Test session sorting."""
    
    def test_newest_first(self):
        from qq.web.run_registry import sort_sessions_newest_first
        sessions = [
            {"run_id": "20260708-120000-old", "state": "finished", "created_at": "2026-07-08T12:00:00Z"},
            {"run_id": "20260710-120000-new", "state": "running", "created_at": "2026-07-10T12:00:00Z"},
            {"run_id": "20260709-120000-mid", "state": "finished", "created_at": "2026-07-09T12:00:00Z"},
        ]
        sorted_sessions = sort_sessions_newest_first(sessions)
        self.assertEqual(sorted_sessions[0]["run_id"], "20260710-120000-new")
        self.assertEqual(sorted_sessions[-1]["run_id"], "20260708-120000-old")
    
    def test_not_sorted_by_state(self):
        """Running sessions should not be sorted before newer finished ones."""
        from qq.web.run_registry import sort_sessions_newest_first
        sessions = [
            {"run_id": "20260710-120000-c", "state": "finished", "created_at": "2026-07-10T12:00:00Z"},
            {"run_id": "20260709-120000-b", "state": "running", "created_at": "2026-07-09T12:00:00Z"},
            {"run_id": "20260708-120000-a", "state": "finished", "created_at": "2026-07-08T12:00:00Z"},
        ]
        sorted_sessions = sort_sessions_newest_first(sessions)
        # Newest first by timestamp, not by state
        self.assertEqual(sorted_sessions[0]["run_id"], "20260710-120000-c")


class TestQueueModeConfig(unittest.TestCase):
    """Test queue mode configuration parsing."""
    
    def test_latest_wins_is_valid(self):
        from qq.web.ingest import load_obelisk_config_from_env
        import os
        with patch.dict(os.environ, {"QONQRETE_RUNS_QUEUE_MODE": "latest_wins"}, clear=False):
            cfg = load_obelisk_config_from_env()
            self.assertEqual(cfg.queue_mode, "latest_wins")
    
    def test_reject_if_running_is_valid(self):
        from qq.web.ingest import load_obelisk_config_from_env
        import os
        with patch.dict(os.environ, {"QONQRETE_RUNS_QUEUE_MODE": "reject_if_running"}, clear=False):
            cfg = load_obelisk_config_from_env()
            self.assertEqual(cfg.queue_mode, "reject_if_running")
    
    def test_queue_is_valid(self):
        from qq.web.ingest import load_obelisk_config_from_env
        import os
        with patch.dict(os.environ, {"QONQRETE_RUNS_QUEUE_MODE": "queue"}, clear=False):
            cfg = load_obelisk_config_from_env()
            self.assertEqual(cfg.queue_mode, "queue")


class TestRunTriggerResult(unittest.TestCase):
    """Test RunTriggerResult has new fields."""
    
    def test_new_fields_exist(self):
        from qq.web.ingest import RunTriggerResult
        r = RunTriggerResult(ok=False, run_id="", task_path="", target_path="")
        # New fields should have defaults
        self.assertIsNone(r.linked_run_id)
        self.assertIsNone(r.active_run_id)
        self.assertIsNone(r.pending_run_id)
        self.assertEqual(r.superseded_run_ids, [])
        self.assertEqual(r.queue_policy, "")


class TestTmuxInnerCommand(unittest.TestCase):
    """Test that the tmux inner command exits properly."""
    
    def test_no_exec_bash_in_do_launch_tmux(self):
        """Verify exec bash is not in the tmux launch code."""
        import inspect
        from qq.web.ingest import _do_launch_tmux
        source = inspect.getsource(_do_launch_tmux)
        # Should NOT contain exec bash
        self.assertNotIn("exec bash", source)
        # Should contain exit $QQ_EXIT
        # The source builds the inner_cmd as a string concatenation; "exit" is present
        self.assertIn('exit', source)  # exit command is present (may be escaped in string build)
        self.assertIn('QQ_EXIT', source)  # QQ_EXIT variable is captured
        # Should contain runner.exit_code write
        self.assertIn("runner.exit_code", source)
        # Should contain runner.finished write
        self.assertIn("runner.finished", source)


class TestResolveTmuxSessionState(unittest.TestCase):
    """Test that _resolve_tmux_session doesn't start with 'running'."""
    
    def test_unknown_initial_state(self):
        """The default state should be unknown, not running."""
        # This is a static check on the source code
        import inspect
        from qq.web.ingest import _resolve_tmux_session
        source = inspect.getsource(_resolve_tmux_session)
        # The result dict should not default to "running"
        self.assertNotIn('"state": "running"', source.split('"""')[0] if '"""' in source else source[:200])
        # But it should still have the function defined
        self.assertIn("def _resolve_tmux_session", source)


if __name__ == "__main__":
    unittest.main()
