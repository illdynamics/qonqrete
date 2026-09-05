"""
Tests for read model fixes: display_name, runner metadata, groups/briqs totals,
max_time/max_cycles display, progress calculation.
"""
import json
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestReadModelDisplayName:
    def test_display_name_in_model(self):
        """build_read_model includes display_name and task_title."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create minimal run structure
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            os.makedirs(os.path.join(tmp, "artifacts"), exist_ok=True)
            
            # Write minimal task
            with open(os.path.join(tmp, "state", "task.json"), "w") as f:
                json.dump({"task_title": "Fix the login bug", "raw_text": "Fix login"}, f)
            
            # Write events
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-1"}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            assert "display_name" in model
            assert "task_title" in model
            assert model["display_name"] == "Fix the login bug"
            assert model["task_title"] == "Fix the login bug"

    def test_display_name_fallback(self):
        """display_name falls back to artifacts/task-original.md."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "artifacts"), exist_ok=True)
            
            with open(os.path.join(tmp, "artifacts", "task-original.md"), "w") as f:
                f.write("# Build REST API\n\nDetailed task description.")
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-2"}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            assert model["display_name"] == "Build REST API"


class TestReadModelRunnerMetadata:
    def test_runner_metadata_in_model(self):
        """build_read_model includes runner_metadata."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            
            with open(os.path.join(tmp, "state", "runner.json"), "w") as f:
                json.dump({"mode": "tmux", "session": "qonqrete-test"}, f)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-3"}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            assert "runner_metadata" in model
            assert model["runner_metadata"]["mode"] == "tmux"
            assert model["runner_metadata"]["session"] == "qonqrete-test"


class TestReadModelMaxDisplay:
    def test_max_cycles_display_infinity(self):
        """max_cycles_display is '∞' when max_cycles is 0."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({
                    "type": "run.started", "ts": 1000, "run_id": "test-4",
                    "max_cycles": 0, "max_time_seconds": 0,
                }, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            run = model["run"]
            assert run["max_cycles_display"] == "∞"
            assert run["max_time_display"] == "∞"

    def test_max_cycles_display_number(self):
        """max_cycles_display shows the number when max_cycles > 0."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({
                    "type": "run.started", "ts": 1000, "run_id": "test-5",
                    "max_cycles": 5, "max_time_seconds": 300,
                }, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            run = model["run"]
            assert run["max_cycles_display"] == "5"
            assert run["max_time_display"] == "300"


class TestReadModelGroupsBriqsTotals:
    def test_total_groups_known_flag(self):
        """metrics include total_groups_known and total_briqs_known."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            
            # Write a plan with groups
            with open(os.path.join(tmp, "state", "plan.json"), "w") as f:
                json.dump({
                    "build_groups": {
                        "g1": {"id": "g1", "name": "Group 1", "briq_ids": ["b1", "b2"]},
                    },
                    "briqs": {
                        "b1": {"id": "b1", "title": "Briq 1", "status": "done"},
                        "b2": {"id": "b2", "title": "Briq 2", "status": "pending"},
                    },
                }, f)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-6"}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            metrics = model["metrics"]
            assert metrics["total_groups_known"] is True
            assert metrics["total_groups"] == 1
            assert metrics["total_briqs_known"] is True
            assert metrics["total_briqs"] == 2

    def test_total_unknown_when_no_plan(self):
        """total_groups_known is False when no plan data exists."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-7"}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            metrics = model["metrics"]
            assert metrics["total_groups_known"] is False
            assert metrics["total_groups"] == 0


class TestReadModelFinalStatus:
    def test_final_status_in_run_info(self):
        """run_info includes final_status field."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-8"}, f)
                f.write("\n")
                json.dump({"type": "review.verdict", "status": "FULLY_DONE", "ts": 2000}, f)
                f.write("\n")
                json.dump({"type": "run.completed", "status": "success", "ts": 3000}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            
            assert "final_status" in model["run"]
            assert model["run"]["final_status"] == "FULLY_DONE"


class TestProgressCalculation:
    def test_fully_done_is_100_percent(self):
        """Progress is 100% when run is done/FULLY_DONE."""
        from qq.progress import calculate_progress
        
        groups = [
            {"id": "g1", "title": "G1", "status": "done", "briqs": [
                {"status": "done"}, {"status": "done"}
            ]},
        ]
        snap = calculate_progress(
            groups=groups,
            final_verdict="FULLY_DONE",
            run_status="done",
        )
        assert snap.displayed_pct == 100.0

    def test_unlimited_cycles_has_progress(self):
        """Progress is not stuck at 0% for unlimited cycles."""
        from qq.progress import calculate_progress
        
        groups = [
            {"id": "g1", "title": "G1", "status": "building", "briqs": [
                {"status": "done"}, {"status": "in_progress"}
            ]},
        ]
        snap = calculate_progress(
            groups=groups,
            active_agent="construqtor",
            run_status="running",
            clarification_complete=True,
            planning_complete=True,
        )
        # Should be >0% because building is in progress
        assert snap.displayed_pct > 0.0

    def test_finite_cycles_progress(self):
        """Progress with finite max cycles is > 0 during build."""
        from qq.progress import calculate_progress
        
        groups = [
            {"id": "g1", "title": "G1", "status": "reviewing", "briqs": [
                {"status": "done"}, {"status": "done"}
            ]},
        ]
        snap = calculate_progress(
            groups=groups,
            active_agent="inspeqtor",
            run_status="running",
            clarification_complete=True,
            planning_complete=True,
        )
        # Reviewing should have progress > 0
        assert snap.displayed_pct > 0.0

    def test_no_groups_progress_is_zero(self):
        """Progress is 0% when there are no groups and still clarifying."""
        from qq.progress import calculate_progress
        
        snap = calculate_progress(
            groups=[],
            active_agent="qlarifier",
            run_status="running",
        )
        assert snap.displayed_pct == 0.0

    def test_failed_state_preserves_progress(self):
        """Failed state shows latest working progress."""
        from qq.progress import calculate_progress
        
        groups = [
            {"id": "g1", "title": "G1", "status": "done", "briqs": [
                {"status": "done"}
            ]},
            {"id": "g2", "title": "G2", "status": "building", "briqs": [
                {"status": "in_progress"}
            ]},
        ]
        snap = calculate_progress(
            groups=groups,
            run_status="failed",
            clarification_complete=True,
            planning_complete=True,
        )
        # Should show working progress, not 0
        assert snap.displayed_pct > 0.0


class TestReviewPhaseNoCrash:
    """Regression tests: entering the inspeQtor/reviewing phase (with
    malformed review.* / cycle events) must never crash build_read_model
    or 502 the web UI."""

    def _seed(self, tmp, events):
        os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
        with open(os.path.join(tmp, "state", "task.json"), "w") as f:
            json.dump({"task_title": "Review crash test"}, f)
        with open(os.path.join(tmp, "state", "plan.json"), "w") as f:
            json.dump({
                "build_groups": {
                    "g1": {"id": "g1", "name": "G1", "briq_ids": ["b1", "b2"]},
                },
                "briqs": {
                    "b1": {"id": "b1", "title": "B1"},
                    "b2": {"id": "b2", "title": "B2"},
                },
            }, f)
        with open(os.path.join(tmp, "events.jsonl"), "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def test_unhashable_build_group_id_does_not_crash(self):
        """A review event with a dict/list build_group_id must not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            events = [
                {"type": "run.started", "ts": 1, "run_id": "r1"},
                {"type": "build_group.started", "ts": 2, "build_group_id": "g1"},
                {"type": "build_group.completed", "ts": 3, "build_group_id": "g1"},
                {"type": "review.started", "ts": 4, "build_group_id": {"status": "X"}, "cycle": "abc"},
                {"type": "review.verdict", "ts": 5, "status": {"status": 5}},
            ]
            self._seed(tmp, events)
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            assert model["run"]["status"] in ("running", "done")
            assert "error" not in model

    def test_review_phase_endpoint_model(self):
        """A full build→review→repair→review cycle returns a valid model."""
        with tempfile.TemporaryDirectory() as tmp:
            events = [
                {"type": "run.started", "ts": 1, "run_id": "r2"},
                {"type": "active_agent_changed", "ts": 2, "role": "construqtor"},
                {"type": "build_group.started", "ts": 3, "build_group_id": "g1"},
                {"type": "build_group.completed", "ts": 4, "build_group_id": "g1"},
                {"type": "active_agent_changed", "ts": 5, "role": "inspeqtor"},
                {"type": "review.started", "ts": 6, "build_group_id": "g1", "cycle": 1},
                {"type": "review.verdict", "ts": 7, "status": {"status": "NOT_DONE"}, "cycle": 1},
                {"type": "cycle_summary", "ts": 8, "cycle": 1},
                {"type": "qontroller.cycle_done", "ts": 9, "cycle": 1},
                {"type": "active_agent_changed", "ts": 10, "role": "construqtor"},
                {"type": "repair.started", "ts": 11, "build_group_id": "g1"},
                {"type": "repair.completed", "ts": 12, "build_group_id": "g1"},
                {"type": "active_agent_changed", "ts": 13, "role": "inspeqtor"},
                {"type": "review.started", "ts": 14, "build_group_id": "g1", "cycle": 2},
                {"type": "review.passed", "ts": 15, "build_group_id": "g1", "cycle": 2},
                {"type": "review.verdict", "ts": 16, "status": "FULLY_DONE", "cycle": 2},
            ]
            self._seed(tmp, events)
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            assert "error" not in model
            assert isinstance(model["build_groups"], list)
            assert model["run"]["active_agent"] == "inspeqtor"

    def test_final_status_dict_does_not_crash(self):
        """A malformed final.json with a non-string 'status' (dict from a
        review phase) must never crash the recovery/terminal checks."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            with open(os.path.join(tmp, "state", "final.json"), "w") as f:
                json.dump({"status": {"x": 1}, "cycle": "2"}, f)
            events = [
                {"type": "run.started", "ts": 1, "run_id": "r3"},
                {"type": "active_agent_changed", "ts": 2, "role": "inspeqtor"},
                {"type": "review.verdict", "ts": 3, "status": None, "cycle": "2"},
            ]
            self._seed(tmp, events)
            with open(os.path.join(tmp, "state", "final.json"), "w") as f:
                json.dump({"status": {"x": 1}, "cycle": "2"}, f)
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            assert "error" not in model
            assert isinstance(model["run"]["status"], str)

    def test_verdict_none_and_non_numeric_cycle_do_not_crash(self):
        """review.verdict with None status + non-numeric cycle must never
        crash the read model (review/inspeQtor phase entry)."""
        with tempfile.TemporaryDirectory() as tmp:
            events = [
                {"type": "run.started", "ts": 1, "run_id": "r4"},
                {"type": "active_agent_changed", "ts": 2, "role": "inspeqtor"},
                {"type": "review.started", "ts": 3, "build_group_id": None},
                {"type": "review.verdict", "ts": 4, "status": None, "cycle": {"c": 1}},
                {"type": "cycle.completed", "ts": 5, "cycle": "three"},
                {"type": "qontroller.cycle_done", "ts": 6},
            ]
            self._seed(tmp, events)
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            assert "error" not in model
            assert model["run"]["active_agent"] == "inspeqtor"
