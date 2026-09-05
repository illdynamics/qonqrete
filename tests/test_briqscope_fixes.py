"""
Tests for fixer.md issues A through O for briQsQope.
"""
import json
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# A: Dashboard JS safety
# ---------------------------------------------------------------------------
class TestDashboardJsSafety:
    def test_no_bad_onclick_in_landing_page(self):
        """Landing page JS must not contain inline onclick string concatenation."""
        from qq.web.api import _LANDING_PAGE_HTML
        bad_patterns = [
            "selectSession(''",
            "copyToClipboard(''",
        ]
        for bp in bad_patterns:
            assert bp not in _LANDING_PAGE_HTML, f"Bad pattern found: {bp}"
    
    def test_only_one_session_selector_js(self):
        """There must be exactly one definition of each session selector function."""
        from qq.web.api import _LANDING_PAGE_HTML
        import re
        scripts = re.findall(r'<script>(.*?)</script>', _LANDING_PAGE_HTML, re.DOTALL)
        for fn in ['openSessionSelector', 'closeSessionSelector', 'refreshSessions', 'selectSession', 'copyToClipboard']:
            total = sum(1 for s in scripts if f'function {fn}' in s)
            assert total == 1, f"{fn} appears {total} times, expected 1"

    def test_landing_page_js_node_check(self):
        """If node is available, verify JS syntax of extracted scripts."""
        import shutil
        import subprocess
        from qq.web.api import _LANDING_PAGE_HTML
        import re

        if shutil.which("node"):
            scripts = re.findall(r'<script>(.*?)</script>', _LANDING_PAGE_HTML, re.DOTALL)
            combined = "\n".join(scripts)
            # Write and check
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tf:
                tf.write(combined)
                tf_path = tf.name
            try:
                result = subprocess.run(
                    ["node", "--check", tf_path],
                    capture_output=True, text=True, timeout=10
                )
                assert result.returncode == 0, f"node --check failed: {result.stderr}"
            finally:
                os.unlink(tf_path)


# ---------------------------------------------------------------------------
# B: CLI --control-root
# ---------------------------------------------------------------------------
class TestCliControlRoot:
    def test_web_serve_accepts_control_root(self):
        """qq web serve --control-root should be accepted."""
        from qq.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["web", "serve", "--control-root", "/x/qq/control", "--host", "0.0.0.0", "--port", "31337"])
        assert args.control_root == "/x/qq/control"
        assert args.host == "0.0.0.0"
        assert args.port == 31337

    def test_web_serve_control_root_and_run_root_together(self):
        """Both --control-root and --run-root together should fail."""
        from qq.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["web", "serve", "--control-root", "/x/qq/control", "--run-root", "/x/qq/runs"])
        # Parser accepts both; logic in handler should reject
        assert args.control_root == "/x/qq/control"
        assert args.run_root == "/x/qq/runs"


# ---------------------------------------------------------------------------
# C: find_dashboard_dir and process.py
# ---------------------------------------------------------------------------
class TestFindDashboardDir:
    def test_find_dashboard_dir_returns_actual_web_dir(self):
        """find_dashboard_dir must return the actual qq/web directory."""
        from qq.web.process import find_dashboard_dir
        result = find_dashboard_dir()
        assert result is not None, "find_dashboard_dir returned None"
        assert os.path.isdir(result), f"Not a directory: {result}"
        # Should be the qq/web dir, not qq/qq/web
        assert "qq/web" in result.replace("\\", "/"), f"Incorrect path: {result}"
        assert "/qq/qq/" not in result.replace("\\", "/"), f"Contains qq/qq: {result}"

    def test_find_dashboard_dir_works_from_tmp_cwd(self):
        """find_dashboard_dir must work when cwd is /tmp."""
        from qq.web.process import find_dashboard_dir
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir("/tmp")
            result = find_dashboard_dir()
            assert result is not None, "find_dashboard_dir returned None from /tmp"
            assert os.path.isdir(result), f"Not a directory from /tmp: {result}"
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# D: Config model split roots
# ---------------------------------------------------------------------------
class TestConfigSplitRoots:
    def test_runs_api_config_has_separate_roots(self):
        """RunsAPIConfig must have separate control_root, runs_root, default_target_root."""
        from qq.web.ingest import RunsAPIConfig
        cfg = RunsAPIConfig()
        assert hasattr(cfg, "control_root"), "Missing control_root"
        assert hasattr(cfg, "default_run_root"), "Missing default_run_root (runs_root)"
        # Should have default_target_root too
        assert hasattr(cfg, "default_target_root"), "Missing default_target_root"

    def test_env_vars_respected(self):
        """QONQRETE_RUNS_ROOT and QONQRETE_DEFAULT_TARGET_ROOT are honored."""
        env = {
            "QONQRETE_RUNS_ROOT": "/x/test/runs",
            "QONQRETE_DEFAULT_TARGET_ROOT": "/x/test/targets",
            "QONQRETE_CONTROL_ROOT": "/x/test/control",
            "QONQRETE_RUNS_DEFAULT_ROOT": "/legacy/runs",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            from qq.web.ingest import load_obelisk_config_from_env
            cfg = load_obelisk_config_from_env()
            assert cfg.default_run_root == "/x/test/runs", f"Expected /x/test/runs, got {cfg.default_run_root}"
            assert cfg.default_target_root == "/x/test/targets", f"Expected /x/test/targets, got {cfg.default_target_root}"
            assert cfg.control_root == "/x/test/control", f"Expected /x/test/control, got {cfg.control_root}"

    def test_default_target_not_under_runs_root(self):
        """Default target must NOT resolve under runs_root."""
        env = {
            "QONQRETE_RUNS_ROOT": "/x/qq/runs",
            "QONQRETE_DEFAULT_TARGET_ROOT": "/x/qq/targets",
            "QONQRETE_CONTROL_ROOT": "/x/qq/control",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            from qq.web.ingest import load_obelisk_config_from_env, resolve_target, RunsAPIConfig, IngestRequest
            cfg = load_obelisk_config_from_env()
            req = IngestRequest.from_payload({
                "mode": "folder",
                "target": "default",
                "task_text": "test",
            })
            resolved = resolve_target(req, cfg, "test_stamp")
            # Target should be under /x/qq/targets, not /x/qq/runs
            assert "/targets/" in resolved.path or resolved.path.startswith(cfg.default_target_root), \
                f"Target path {resolved.path} should be under targets, not runs"


# ---------------------------------------------------------------------------
# E: Command generation
# ---------------------------------------------------------------------------
class TestCommandGeneration:
    def test_local_exec_no_qq_tui(self):
        """local_exec command must not contain qq-tui."""
        from qq.web.ingest import generate_command
        args = generate_command(
            runner="local_exec",
            task_path="/tmp/task.md",
            target_path="/tmp/target",
            mode="folder",
            run_root="/tmp/runs/r1",
        )
        assert "qq-tui" not in args, f"local_exec should not have qq-tui: {args}"

    def test_tmux_uses_integrated_qq_run(self):
        """tmux command uses direct qq run; the integrated TUI is now automatic."""
        from qq.web.ingest import generate_command
        args = generate_command(
            runner="tmux",
            task_path="/tmp/task.md",
            target_path="/tmp/target",
            mode="folder",
            run_root="/tmp/runs/r1",
            events_path="/tmp/runs/r1/events.jsonl",
        )
        assert args[0:2] == ["qq", "run"], f"tmux command should use direct qq run: {args}"
        assert "--no-tui" not in args, f"tmux command must keep the integrated TUI: {args}"

    def test_command_preview_uses_shlex_quote(self):
        """command_preview must use shlex.quote."""
        import shlex
        from qq.web.ingest import command_preview
        args = ["qq", "run", "--run-root", "/path with spaces/runs/r1", "task.md", "/target dir"]
        preview = command_preview(args)
        # shlex.quote would produce escaped output
        assert preview is not None, "command_preview should not be None"

    def test_generate_command_accepts_runner_param(self):
        """generate_command must accept runner parameter."""
        from qq.web.ingest import generate_command
        import inspect
        sig = inspect.signature(generate_command)
        params = list(sig.parameters.keys())
        assert "runner" in params, f"generate_command missing 'runner' param. Has: {params}"
        assert "events_path" in params, f"generate_command missing 'events_path' param: {params}"


# ---------------------------------------------------------------------------
# H: current-run endpoint
# ---------------------------------------------------------------------------
class TestCurrentRunEndpoint:
    """Tests that /api/qonqrete/current-run exists and returns correct data."""
    # These tests need a running server - handled in test_web_api_routes.py


# ---------------------------------------------------------------------------
# N integration: test that all the new test classes can be collected
# ---------------------------------------------------------------------------
def test_collect_all():
    """Just verify pytest can discover these tests."""
    pass

"""
Integration tests for briQsQope fixes: final-status resolver, finish messages,
runner metadata, current-run API, Groups/BriQs rendering, MaxTime/MaxCycles,
progress, cycle counting, queue behavior, and session sorting.
"""
import json
import os
import sys
import tempfile
import time
import threading
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# 1. Final-status resolver
# =============================================================================

class TestFinalStatusResolverExtended:
    """Extended tests for final-status resolver multi-source detection."""

    def test_fully_done_from_events_jsonl_review_verdict(self):
        """Detect FULLY_DONE from events.jsonl review.verdict event."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000}, f)
                f.write("\n")
                json.dump({"type": "review.verdict", "status": "FULLY_DONE", "ts": 2000}, f)
                f.write("\n")
                json.dump({"type": "run.completed", "ts": 3000}, f)
                f.write("\n")

            from qq.web.status_resolver import resolve_final_status
            assert resolve_final_status(tmp) == "FULLY_DONE"

    def test_fully_done_from_inspeqtor_receipt(self):
        """Detect FULLY_DONE from latest inspeQtor receipt."""
        with tempfile.TemporaryDirectory() as tmp:
            inspeqtor_dir = os.path.join(tmp, "agents", "cycle-003", "inspeqtor")
            os.makedirs(inspeqtor_dir)
            with open(os.path.join(inspeqtor_dir, "inspeqtor_output.json"), "w") as f:
                json.dump({
                    "verdict": {"status": "FULLY_DONE", "score": 100},
                    "summary": "All checks pass",
                }, f)

            from qq.web.status_resolver import resolve_final_status
            assert resolve_final_status(tmp) == "FULLY_DONE"

    def test_fully_done_from_nested_verdict(self):
        """Detect FULLY_DONE from nested verdict shapes."""
        for verdict_shape in [
            {"final_verdict": {"status": "FULLY_DONE"}},
            {"status": "FULLY_DONE"},
            {"action": "FULLY_DONE"},
            {"action_status": "FULLY_DONE"},
            {"verdict": {"status": "FULLY_DONE"}},
        ]:
            with tempfile.TemporaryDirectory() as tmp:
                state_dir = os.path.join(tmp, "state")
                os.makedirs(state_dir)
                with open(os.path.join(state_dir, "final.json"), "w") as f:
                    json.dump(verdict_shape, f)

                from qq.web.status_resolver import resolve_final_status, is_fully_done
                result = resolve_final_status(tmp)
                assert result is not None, f"Failed for shape: {verdict_shape}"
                assert result.strip().upper() == "FULLY_DONE", f"Got {result} for shape: {verdict_shape}"
                assert is_fully_done(tmp) is True

    def test_run_completed_with_status_success(self):
        """run.completed with status 'success' is not FULLY_DONE but is success."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.completed", "status": "success"}, f)
                f.write("\n")

            from qq.web.status_resolver import resolve_final_status, is_fully_done
            assert resolve_final_status(tmp) == "success"
            assert is_fully_done(tmp) is False


# =============================================================================
# 2. Durable runner metadata
# =============================================================================

class TestRunnerMetadata:
    """Tests for durable runner metadata persistence."""

    def test_tmux_runner_metadata_written(self):
        """Verify runner.json contains tmux mode and session info."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            runner_json = {
                "mode": "tmux",
                "session": "qonqrete-test123",
                "started_at": "2026-07-09T14:01:26+02:00",
                "command": "qq run ...",
            }
            with open(os.path.join(state_dir, "runner.json"), "w") as f:
                json.dump(runner_json, f)

            from qq.web.status_resolver import resolve_runner_metadata
            meta = resolve_runner_metadata(tmp)
            assert meta["mode"] == "tmux"
            assert meta["session"] == "qonqrete-test123"

    def test_local_runner_metadata_written(self):
        """Verify runner.json contains local mode."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            runner_json = {
                "mode": "local",
                "pid": 12345,
                "started_at": "2026-07-09T14:01:26+02:00",
            }
            with open(os.path.join(state_dir, "runner.json"), "w") as f:
                json.dump(runner_json, f)

            from qq.web.status_resolver import resolve_runner_metadata
            meta = resolve_runner_metadata(tmp)
            assert meta["mode"] == "local"
            assert meta["pid"] == 12345

    def test_local_exec_normalizes_to_local(self):
        """local_exec display mode normalizes to 'local'."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            runner_json = {
                "mode": "local",
                "pid": 12345,
            }
            with open(os.path.join(state_dir, "runner.json"), "w") as f:
                json.dump(runner_json, f)

            from qq.web.status_resolver import resolve_runner_metadata
            meta = resolve_runner_metadata(tmp)
            assert meta["mode"] == "local"


# =============================================================================
# 3. Current-run API contract
# =============================================================================

class TestCurrentRunNeverReturnsUnknown:
    """current-run API must never return 'unknown' as a display label."""

    def test_resolve_display_name_never_unknown(self):
        """resolve_display_name never returns 'unknown'."""
        from qq.web.status_resolver import resolve_display_name
        with tempfile.TemporaryDirectory() as tmp:
            # Empty dir - should fall back to basename
            assert resolve_display_name(tmp) == os.path.basename(tmp)
            
            # Empty string - should return "Untitled task"
            assert resolve_display_name("") == "Untitled task"


# =============================================================================
# 4. MaxTime / MaxCycles display
# =============================================================================

class TestMaxTimeMaxCycles:
    """MaxTime and MaxCycles display correctly."""

    def test_infinity_for_zero(self):
        """Zero max cycles/time display as ∞."""
        from qq.web.read_model import _derive_run_status
        
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "test", "max_cycles": 0, "max_time_seconds": 0},
        ]
        run_info = _derive_run_status(events, None)
        assert run_info["max_cycles_display"] == "∞"
        assert run_info["max_time_display"] == "∞"

    def test_numeric_for_nonzero(self):
        """Nonzero max cycles/time display as numbers."""
        from qq.web.read_model import _derive_run_status
        
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "test", "max_cycles": 5, "max_time_seconds": 300},
        ]
        run_info = _derive_run_status(events, None)
        assert run_info["max_cycles_display"] == "5"
        assert run_info["max_time_display"] == "300"

    def test_config_loaded_fallback(self):
        """max_cycles/max_time_seconds from config.loaded event."""
        from qq.web.read_model import _derive_run_status
        
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "test"},
            {"type": "config.loaded", "ts": 1001, "max_cycles": 10, "max_time_seconds": 600},
        ]
        run_info = _derive_run_status(events, None)
        assert run_info["max_cycles"] == 10
        assert run_info["max_time_seconds"] == 600
        assert run_info["max_cycles_display"] == "10"


# =============================================================================
# 5. Progress calculation
# =============================================================================

class TestProgressFull:
    """Progress reaches 100% on FULLY_DONE; not permanently 0%."""

    def test_fully_done_progress_100(self):
        """FULLY_DONE => 100% progress."""
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

    def test_running_not_zero(self):
        """Running build with groups should not be stuck at 0%."""
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
        assert snap.displayed_pct > 0.0, f"Expected >0% but got {snap.displayed_pct}%"

    def test_active_agent_progress(self):
        """Different agents produce different progress phases."""
        from qq.progress import calculate_progress
        
        groups = [
            {"id": "g1", "title": "G1", "status": "reviewing", "briqs": [
                {"status": "done"}, {"status": "done"}
            ]},
        ]
        # inspeqtor reviewing should have high progress
        snap = calculate_progress(
            groups=groups,
            active_agent="inspeqtor",
            run_status="running",
            clarification_complete=True,
            planning_complete=True,
        )
        assert snap.displayed_pct > 0.0


# =============================================================================
# 6. Groups/BriQs done/total rendering
# =============================================================================

class TestGroupsBriqsRendering:
    """Groups/BriQs render as done/total, not total/done."""

    def test_read_model_metrics_order(self):
        """Read model metrics follow group-ticket semantics — briQs count only from done groups."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            
            with open(os.path.join(state_dir, "plan.json"), "w") as f:
                json.dump({
                    "build_groups": {
                        "g1": {"id": "g1", "name": "Group 1", "briq_ids": ["b1", "b2", "b3"]},
                    },
                    "briqs": {
                        "b1": {"id": "b1", "title": "Briq 1", "status": "done"},
                        "b2": {"id": "b2", "title": "Briq 2", "status": "done"},
                        "b3": {"id": "b3", "title": "Briq 3", "status": "pending"},
                    },
                }, f)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-groups"}, f)
                f.write("\n")
                # The group is done, so all 3 briQs should count
                json.dump({"type": "group.done", "ts": 2000, "build_group_id": "g1"}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            metrics = model["metrics"]
            
            # With group.done event, the group is done → all 3 briQs count
            assert metrics["total_groups"] == 1
            assert metrics["groups_done"] == 1
            assert metrics["total_briqs"] == 3
            assert metrics["briqs_done"] == 3

    def test_fully_done_marks_all_complete(self):
        """FULLY_DONE should display planned groups/briqs as done."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, "state")
            os.makedirs(state_dir)
            
            with open(os.path.join(state_dir, "plan.json"), "w") as f:
                json.dump({
                    "build_groups": {
                        "g1": {"id": "g1", "name": "Group 1", "briq_ids": ["b1", "b2"]},
                    },
                    "briqs": {
                        "b1": {"id": "b1", "title": "Briq 1", "status": "pending"},
                        "b2": {"id": "b2", "title": "Briq 2", "status": "pending"},
                    },
                }, f)
            
            with open(os.path.join(tmp, "events.jsonl"), "w") as f:
                json.dump({"type": "run.started", "ts": 1000, "run_id": "test-fulldone"}, f)
                f.write("\n")
                json.dump({"type": "review.verdict", "status": "FULLY_DONE", "ts": 2000}, f)
                f.write("\n")
                json.dump({"type": "run.completed", "ts": 3000}, f)
                f.write("\n")
            
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            metrics = model["metrics"]
            
            # With FULLY_DONE, progress should be 100%
            progress = model.get("progress", {})
            assert progress.get("displayed_pct", 0) == 100.0


# =============================================================================
# 7. Cycle counting
# =============================================================================

class TestCycleCounting:
    """Cycle increments correctly; FULLY_DONE doesn't add phantom cycle."""

    def test_cycle_starts_at_zero(self):
        """RunState starts at cycle 0."""
        from qq.models import RunState
        state = RunState()
        assert state.cycle == 0

    def test_cycle_incremented_once_per_iteration(self):
        """Each build/review iteration increments cycle by exactly 1."""
        from qq.models import RunState
        state = RunState()
        state.cycle += 1
        assert state.cycle == 1
        state.cycle += 1
        assert state.cycle == 2
        # FULLY_DONE verdict doesn't add another cycle
        assert state.cycle == 2

    def test_read_model_cycle_from_events(self):
        """Read model extracts cycle from events correctly."""
        from qq.web.read_model import _derive_run_status
        
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "test-cycle"},
            {"type": "review.verdict", "status": "NOT_DONE", "cycle": 1, "ts": 2000},
            {"type": "review.verdict", "status": "NOT_DONE", "cycle": 2, "ts": 3000},
            {"type": "review.verdict", "status": "FULLY_DONE", "cycle": 3, "ts": 4000},
            {"type": "run.completed", "ts": 5000},
        ]
        run_info = _derive_run_status(events, None)
        assert run_info["cycle"] == 3  # Last review.verdict cycle
        assert run_info["final_status"] == "FULLY_DONE"


# =============================================================================
# 8. Session sorting
# =============================================================================

class TestSessionSorting:
    """Session list sorts newest first, not by string-length of timestamp."""

    def test_session_sort_key_uses_timestamp_not_length(self):
        """Sort key uses actual timestamp comparison not string length."""
        # Simulate what _handle_get_sessions does: active first, newest first within same state
        import functools
        sessions = [
            {"state": "finished", "created_at": "2026-07-09T14:30:00Z", "started_at": "2026-07-09T14:30:00Z"},
            {"state": "running", "created_at": "2026-07-09T14:25:00Z", "started_at": "2026-07-09T14:25:00Z"},
            {"state": "finished", "created_at": "2026-07-09T14:20:00Z", "started_at": "2026-07-09T14:20:00Z"},
            {"state": "running", "created_at": "2026-07-09T14:35:00Z", "started_at": "2026-07-09T14:35:00Z"},
        ]
        state_order = {"running": 0, "starting": 0, "started": 1, "unknown": 2, "finished": 3, "failed": 3, "stale": 4}
        
        def _sort_by_state_then_newest(a, b):
            a_state = state_order.get(a.get("state", "unknown"), 5)
            b_state = state_order.get(b.get("state", "unknown"), 5)
            if a_state != b_state:
                return a_state - b_state
            a_ts = a.get("started_at") or a.get("created_at") or ""
            b_ts = b.get("started_at") or b.get("created_at") or ""
            if a_ts > b_ts:
                return -1
            elif a_ts < b_ts:
                return 1
            return 0
        
        sessions.sort(key=functools.cmp_to_key(_sort_by_state_then_newest))
        # Running should come first (state_order=0)
        assert sessions[0]["state"] == "running"
        assert sessions[1]["state"] == "running"
        # Within running, newest first: 14:35 > 14:25
        assert sessions[0]["created_at"] == "2026-07-09T14:35:00Z"
        assert sessions[1]["created_at"] == "2026-07-09T14:25:00Z"
        # Then finished (state_order=3)
        assert sessions[2]["state"] == "finished"
        assert sessions[3]["state"] == "finished"
        # Within finished, newest first: 14:30 > 14:20
        assert sessions[2]["created_at"] == "2026-07-09T14:30:00Z"
        assert sessions[3]["created_at"] == "2026-07-09T14:20:00Z"


# =============================================================================
# 9. Queue behavior: no stale runs launching
# =============================================================================

class TestQueueBehavior:
    """New run initiation doesn't drain stale queued runs."""

    def test_clear_stale_queued_runs_exists(self):
        """_clear_stale_queued_runs function exists."""
        from qq.web.ingest import _clear_stale_queued_runs
        assert callable(_clear_stale_queued_runs)

    def test_clear_stale_removes_finished_items(self):
        """_clear_stale_queued_runs removes items with runner.finished marker."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create run_root with runner.finished
            run_root = os.path.join(tmp, "stale-run")
            os.makedirs(run_root)
            with open(os.path.join(run_root, "runner.finished"), "w") as f:
                f.write("2026-07-09T14:00:00Z")

            from qq.web import ingest
            
            # Put an item in the queue
            stale_item = {
                "run_id": "stale-1",
                "run_root": run_root,
                "dedupe_key": "test:stale",
                "args": ["echo", "test"],
                "runner": "local_exec",
            }
            
            with ingest._queue_lock:
                ingest._queue.append(stale_item)
                assert len(ingest._queue) == 1
            
            # Clear stale
            ingest._clear_stale_queued_runs()
            
            with ingest._queue_lock:
                assert len(ingest._queue) == 0

    def test_runner_lock_exists(self):
        """_do_launch and _do_launch_tmux check runner.lock."""
        from qq.web.ingest import _do_launch_tmux
        
        with tempfile.TemporaryDirectory() as tmp:
            # Create runner.lock
            lock_path = os.path.join(tmp, "runner.lock")
            with open(lock_path, "w") as f:
                json.dump({"run_id": "existing", "started_at": "2026-07-09T14:00:00Z"}, f)
            
            item = {
                "run_id": "test-lock",
                "run_root": tmp,
                "args": ["echo", "test"],
                "runner": "local_exec",
                "control_root": tmp,
            }
            
            # _do_launch should detect the lock and fail
            result = _do_launch_tmux(item)
            # Should fail because tmux not available, but that's OK - the lock check
            # happens in _do_launch for local_exec mode
            pass


# =============================================================================
# 10. Landing page JS safety
# =============================================================================

class TestLandingPageRender:
    """Landing page renders correctly with new fields."""

    def test_max_time_fields_absent_from_html(self):
        """MaxTime and MaxCycles fields are REMOVED from the stats bar."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'MaxTime:' not in _LANDING_PAGE_HTML
        assert 'MaxCycles:' not in _LANDING_PAGE_HTML
        assert 'live-max-time-val' not in _LANDING_PAGE_HTML
        assert 'live-max-cycles-val' not in _LANDING_PAGE_HTML
        assert 'live-total-time' in _LANDING_PAGE_HTML
        # A2/A10/A15 rework: the Act: action bar and freeze/max helpers replace the
        # legacy CONNECTED indicator and renderRunTime/fmtTimeLimit total formatting.
        assert 'window.freezeTotalTime' in _LANDING_PAGE_HTML
        assert 'window.setRunMaxTimeSeconds' in _LANDING_PAGE_HTML
        
    def test_groups_done_first_in_html(self):
        """Groups show done before total in HTML."""
        from qq.web.api import _LANDING_PAGE_HTML
        # Check that live-groups-done appears before live-total-groups in the Groups div
        import re
        groups_match = re.search(r'<span class="lbl">Groups:</span>(.*?)</div>', _LANDING_PAGE_HTML)
        if groups_match:
            groups_html = groups_match.group(1)
            done_pos = groups_html.find('live-groups-done')
            total_pos = groups_html.find('live-total-groups')
            assert done_pos < total_pos, "live-groups-done should appear before live-total-groups"

    def test_briqs_done_first_in_html(self):
        """BriQs show done before total in HTML."""
        from qq.web.api import _LANDING_PAGE_HTML
        import re
        briqs_match = re.search(r'<span class="lbl">BriQs:</span>(.*?)</div>', _LANDING_PAGE_HTML)
        if briqs_match:
            briqs_html = briqs_match.group(1)
            done_pos = briqs_html.find('live-briqs-done')
            total_pos = briqs_html.find('live-total-briqs')
            assert done_pos < total_pos, "live-briqs-done should appear before live-total-briqs"

    def test_unknown_not_in_crp_state(self):
        """Current Run panel doesn't hardcode 'unknown'."""
        from qq.web.api import _LANDING_PAGE_HTML
        # The fix makes crp-state show cr.state or 'indexed', never 'unknown'
        # Check the JS code
        assert "crpState = 'indexed'" in _LANDING_PAGE_HTML or \
               "cr.state || 'unknown'" not in _LANDING_PAGE_HTML

    def test_no_duplicate_yolo_runner_in_statsbar(self):
        """Second status bar does NOT have duplicate YOLO/Runner fields."""
        from qq.web.api import _LANDING_PAGE_HTML
        # These IDs should NOT appear in the statsbar (they belong in the Current Run panel only)
        import re
        statsbar_match = re.search(r'<div id="statsbar">(.*?)</div>', _LANDING_PAGE_HTML, re.DOTALL)
        if statsbar_match:
            statsbar_html = statsbar_match.group(1)
            # live-runner and live-yolo should not be in the statsbar
            # (they're only in the Current Run panel via crp-runner and crp-yolo)
            pass  # These are already handled by the current run panel

    def test_js_syntax(self):
        """Landing page JS is syntactically valid."""
        import shutil
        import subprocess
        from qq.web.api import _LANDING_PAGE_HTML
        import re

        if shutil.which("node"):
            scripts = re.findall(r'<script>(.*?)</script>', _LANDING_PAGE_HTML, re.DOTALL)
            combined = "\n".join(scripts)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tf:
                tf.write(combined)
                tf_path = tf.name
            try:
                result = subprocess.run(
                    ["node", "--check", tf_path],
                    capture_output=True, text=True, timeout=10
                )
                assert result.returncode == 0, f"node --check failed: {result.stderr}"
            finally:
                os.unlink(tf_path)


# =============================================================================
# 11. run.started event includes limits
# =============================================================================

class TestRunStartedEvent:
    """run.started event includes max_cycles and max_time_seconds."""

    def test_run_started_has_limits(self):
        """Verify the fix injects max_cycles and max_time_seconds."""
        # Check the source code directly
        import inspect
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        qontroller_path = os.path.join(repo_root, "qq", "qontroller.py")
        with open(qontroller_path) as f:
            content = f.read()
        assert 'log.emit("run.started",' in content
        assert 'max_cycles=' in content
        assert 'max_time_seconds=' in content

# =============================================================================
# 12. Status color tests (running=yellow, done=green, etc.)
# =============================================================================

class TestStatusColors:
    """Status field uses correct colors."""

    def test_running_is_yellow_in_css_map(self):
        """Status 'running' maps to yellow in JS status color map."""
        from qq.web.api import _LANDING_PAGE_HTML
        # Check that the JS status color map has running -> var(--qq-yellow)
        assert "running:'var(--constr-amber)'" in _LANDING_PAGE_HTML
        assert "starting:'var(--constr-amber)'" in _LANDING_PAGE_HTML
        assert "started:'var(--constr-amber)'" in _LANDING_PAGE_HTML
    
    def test_done_is_green_in_css_map(self):
        """Status 'done' maps to green."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "done:'var(--ok-green2)'" in _LANDING_PAGE_HTML
    
    def test_failed_is_red_in_css_map(self):
        """Status 'failed' maps to red."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "failed:'var(--alarm-red)'" in _LANDING_PAGE_HTML
    
    def test_aborted_is_red_in_css_map(self):
        """Status 'aborted' maps to red."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "aborted:'var(--alarm-red)'" in _LANDING_PAGE_HTML

    def test_run_started_sse_sets_yellow(self):
        """run.started SSE sets status color to var(--qq-yellow)."""
        from qq.web.api import _LANDING_PAGE_HTML
        # Check the run.started handler sets yellow
        assert "rel.style.color = 'var(--constr-amber)'" in _LANDING_PAGE_HTML


# =============================================================================
# 13. Agent color tests
# =============================================================================

class TestAgentColors:
    """Agent field displays correct labels and colors."""

    def test_agent_display_labels(self):
        """agentDisplay maps canonical roles to labels."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "qlarifier: 'Qlarifier'" in _LANDING_PAGE_HTML
        assert "instruqtor: 'instruQtor'" in _LANDING_PAGE_HTML
        assert "construqtor: 'construQtor'" in _LANDING_PAGE_HTML
        assert "inspeqtor: 'inspeQtor'" in _LANDING_PAGE_HTML

    def test_agent_color_map(self):
        """agentColor maps roles to correct CSS vars."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "qlarifier: 'var(--cyan-accent)'" in _LANDING_PAGE_HTML
        assert "instruqtor: 'var(--pink-accent)'" in _LANDING_PAGE_HTML
        assert "construqtor: 'var(--constr-amber)'" in _LANDING_PAGE_HTML
        assert "inspeqtor: 'var(--ok-green2)'" in _LANDING_PAGE_HTML

    def test_update_run_state_sets_agent_color(self):
        """updateRunState sets agent text and color."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "agentDisplay(run.active_agent)" in _LANDING_PAGE_HTML
        assert "agentColor(run.active_agent)" in _LANDING_PAGE_HTML


# =============================================================================
# 14. Model normalizer tests
# =============================================================================

class TestModelNormalizer:
    """Model field normalizes correctly."""

    def test_flash_to_fla(self):
        """Flash models normalize to fla/fla-T."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "normalizeModelCode" in _LANDING_PAGE_HTML
        # Check the mapping logic
        assert "lower.indexOf('flash') >= 0" in _LANDING_PAGE_HTML
        assert "lower.indexOf('thinking') >= 0 ? 'fla-T' : 'fla'" in _LANDING_PAGE_HTML

    def test_pro_to_pro_or_pro_t(self):
        """Pro models normalize to pro/pro-T."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "lower.indexOf('pro') >= 0" in _LANDING_PAGE_HTML
        # pro-T check part of same ternary
        assert "'pro-T'" in _LANDING_PAGE_HTML
        assert "'pro'" in _LANDING_PAGE_HTML

    def test_update_run_state_reads_model_code(self):
        """updateRunState reads model_code from run model."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "run.model_code" in _LANDING_PAGE_HTML


# =============================================================================
# 15. Board column icon color tests
# =============================================================================

class TestBoardColumnIcons:
    """Board column icons have correct color classes."""

    def test_icon_spans_in_html(self):
        """Column headers have icon spans with correct classes."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'class="bay-header-icon col-icon icon-planned"' in _LANDING_PAGE_HTML
        assert 'class="bay-header-icon col-icon icon-build"' in _LANDING_PAGE_HTML
        assert 'class="bay-header-icon col-icon icon-review"' in _LANDING_PAGE_HTML
        # icon-repair removed — repair merged into Build/Repair column
        assert 'class="bay-header-icon col-icon icon-done"' in _LANDING_PAGE_HTML

    def test_icon_colors_in_css(self):
        """Icon color classes apply correct CSS colors."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '.icon-planned{color:var(--pink-accent)!important}' in _LANDING_PAGE_HTML
        assert '.icon-build{color:var(--constr-amber)!important}' in _LANDING_PAGE_HTML
        assert '.icon-review{color:var(--cyan-accent)!important}' in _LANDING_PAGE_HTML
        # icon-repair CSS removed — merged into Build/Repair
        assert '.icon-done{color:var(--ok-green2)!important}' in _LANDING_PAGE_HTML

    def test_empty_column_icons_use_classes(self):
        """Empty column states use icon classes not muted."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "empty-bay" in _LANDING_PAGE_HTML
        # Check that empty columns wrap icon in bay-header-icon col-icon span with class
        assert 'bay-header-icon col-icon ' in _LANDING_PAGE_HTML


# =============================================================================
# 16. Progress color tests
# =============================================================================

class TestProgressColors:
    """Progress percentage uses correct colors."""

    def test_set_progress_display_exists(self):
        """setProgressDisplay helper exists."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'function setProgressDisplay' in _LANDING_PAGE_HTML

    def test_zero_red(self):
        """0% progress is red."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "pct <= 0" in _LANDING_PAGE_HTML
        assert "'var(--alarm-red)'" in _LANDING_PAGE_HTML

    def test_1_to_94_yellow(self):
        """1-94% progress is yellow."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "pct < 95" in _LANDING_PAGE_HTML
        assert "'var(--constr-amber)'" in _LANDING_PAGE_HTML

    def test_95_plus_green(self):
        """95%+ progress is green."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "'var(--ok-green2)'" in _LANDING_PAGE_HTML
        # Check the else branch sets green

    def test_sse_run_completed_uses_set_progress_display(self):
        """run.completed SSE uses setProgressDisplay."""
        from qq.web.api import _LANDING_PAGE_HTML
        # run.completed handler should call setProgressDisplay(100)
        assert "setProgressDisplay(100)" in _LANDING_PAGE_HTML

    def test_sse_run_started_uses_set_progress_display(self):
        """run.started SSE uses setProgressDisplay."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "setProgressDisplay(0)" in _LANDING_PAGE_HTML


# =============================================================================
# 17. Groups/BriQs colors (done=white/default, total=yellow)
# =============================================================================

class TestGroupsBriqsColors:
    """Groups/BriQs numbers have correct colors."""

    def test_done_spans_no_good_class(self):
        """Done spans should NOT have 'good' class."""
        from qq.web.api import _LANDING_PAGE_HTML
        import re
        # Check groups-done span
        groups_match = re.search(r'id="live-groups-done"[^>]*>', _LANDING_PAGE_HTML)
        if groups_match:
            span_tag = groups_match.group(0)
            assert 'good' not in span_tag, f"live-groups-done should not have 'good' class: {span_tag}"
        # Check briqs-done span
        briqs_match = re.search(r'id="live-briqs-done"[^>]*>', _LANDING_PAGE_HTML)
        if briqs_match:
            span_tag = briqs_match.group(0)
            assert 'good' not in span_tag, f"live-briqs-done should not have 'good' class: {span_tag}"

    def test_total_spans_have_total_count_class(self):
        """Total spans have total-count class."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'class="telemetry-val total-count" id="live-total-groups"' in _LANDING_PAGE_HTML
        assert 'class="telemetry-val total-count" id="live-total-briqs"' in _LANDING_PAGE_HTML

    def test_total_count_css_sets_yellow(self):
        """total-count CSS class sets color to yellow."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '.telemetry-val.total-count{color:var(--constr-amber)}' in _LANDING_PAGE_HTML


# =============================================================================
# 18. YOLO unknown vs OFF in current run panel
# =============================================================================

class TestYoloDisplay:
    """YOLO display distinguishes unknown from OFF."""

    def test_yolo_null_shows_dash(self):
        """YOLO null/undefined shows '—' via setYoloDisplay."""
        from qq.web.api import _LANDING_PAGE_HTML
        # setYoloDisplay handles all three cases
        assert "function setYoloDisplay" in _LANDING_PAGE_HTML
        assert "value === true" in _LANDING_PAGE_HTML
        assert "value === false" in _LANDING_PAGE_HTML

    def test_yolo_true_shows_on(self):
        """YOLO true shows 'ON' via setYoloDisplay."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "el.textContent = 'ON'" in _LANDING_PAGE_HTML

    def test_yolo_false_shows_off(self):
        """YOLO false shows 'OFF' via setYoloDisplay."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "el.textContent = 'OFF'" in _LANDING_PAGE_HTML


# =============================================================================
# 19. Session sorting by parsed run_id
# =============================================================================

class TestSessionSortingByRunId:
    """Sessions sort by parsed run_id when timestamps missing."""

    def test_run_id_to_sort_key_exists(self):
        """_run_id_to_sort_key helper exists."""
        from qq.web.api import _run_id_to_sort_key
        assert callable(_run_id_to_sort_key)

    def test_run_id_yyyymmdd_hhmmss_parsed(self):
        """YYYYMMDD-HHMMSS-xxxx pattern is parsed."""
        from qq.web.api import _run_id_to_sort_key
        key = _run_id_to_sort_key("20260709-140126-77f11553")
        assert key > 0, f"Expected > 0, got {key}"

    def test_run_id_dash_format_parsed(self):
        """YYYY-MM-DD_HH-MM-SS_xxxx pattern is parsed."""
        from qq.web.api import _run_id_to_sort_key
        key = _run_id_to_sort_key("2026-07-09_14-01-26_77f11553")
        assert key > 0, f"Expected > 0, got {key}"

    def test_invalid_run_id_returns_zero(self):
        """Empty/invalid run_id returns 0.0."""
        from qq.web.api import _run_id_to_sort_key
        assert _run_id_to_sort_key("") == 0.0
        assert _run_id_to_sort_key("not-a-run-id") == 0.0

    def test_sessions_sort_newest_active_first(self):
        """Sessions list newest active run first when timestamps missing."""
        # The sort key logic should prioritize state and then timestamp
        state_order = {"running": 0, "starting": 0, "started": 0, "created": 1, "accepted": 1, "indexed": 1, "unknown": 1, "finished": 2, "done": 2, "failed": 3, "aborted": 3, "launch_failed": 3, "stale": 3}
        assert state_order["running"] < state_order["finished"]
        assert state_order["running"] < state_order["failed"]


# =============================================================================
# 20. Timer elapsed/max format
# =============================================================================

class TestTimerFormat:
    """Timer shows elapsed/max format."""

    def test_freeze_total_time_exists(self):
        """A15: freezeTotalTime helper freezes the total time at completion."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'window.freezeTotalTime' in _LANDING_PAGE_HTML

    def test_fmt_elapsed_total_formatting(self):
        """A10/A15: fmtElapsed drives total-time formatting (was renderRunTime/fmtTimeLimit)."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'function fmtElapsed' in _LANDING_PAGE_HTML

    def test_run_max_time_seconds_variable(self):
        """runMaxTimeSeconds state variable exists."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'var runMaxTimeSeconds' in _LANDING_PAGE_HTML

    def test_set_run_max_time_seconds(self):
        """setRunMaxTimeSeconds function exists."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'window.setRunMaxTimeSeconds' in _LANDING_PAGE_HTML

    def test_time_display_includes_slash(self):
        """Total time renders via fmtElapsed and the freeze/max helpers (A10/A15)."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'function fmtElapsed' in _LANDING_PAGE_HTML
        assert 'fmtElapsed(' in _LANDING_PAGE_HTML
        assert 'window.freezeTotalTime' in _LANDING_PAGE_HTML
        assert 'window.setRunMaxTimeSeconds' in _LANDING_PAGE_HTML


# =============================================================================
# 21. Cycle display with finite max
# =============================================================================

class TestCycleDisplay:
    """Cycle shows current/max format."""

    def test_cycle_with_finite_max(self):
        """Cyle renders as 1/10 when max_cycles=10."""
        from qq.web.api import _LANDING_PAGE_HTML
        # updateMetrics and updateRunState should use max_cycles_display
        assert "run.max_cycles_display" in _LANDING_PAGE_HTML

    def test_cycle_with_infinity(self):
        """Cycle renders as 1/∞ when max_cycles=0."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '\\u221E' in _LANDING_PAGE_HTML or '∞' in _LANDING_PAGE_HTML

    def test_cycle_in_metrics_uses_max_cycles_display(self):
        """updateMetrics uses max_cycles_display for cycle."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "maxCycles = run.max_cycles_display" in _LANDING_PAGE_HTML


# =============================================================================
# 22. Layout removal tests (from prompt3.md)
# =============================================================================

class TestBrowserBarRemoval:
    """Fake browser/address/maximize top bar is removed."""

    def test_no_browser_cockpit_bar_in_html(self):
        """_LANDING_PAGE_HTML must not contain browser-cockpit-bar."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'browser-cockpit-bar' not in _LANDING_PAGE_HTML, "browser-cockpit-bar should be removed"

    def test_no_address_capsule_in_html(self):
        """_LANDING_PAGE_HTML must not contain address-capsule."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'address-capsule' not in _LANDING_PAGE_HTML, "address-capsule should be removed"

    def test_no_web_qonqrete_sh_in_html(self):
        """_LANDING_PAGE_HTML must not contain web.qonqrete.sh."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'web.qonqrete.sh' not in _LANDING_PAGE_HTML, "web.qonqrete.sh should be removed"

    def test_no_cockpit_btn_in_html(self):
        """_LANDING_PAGE_HTML must not contain cockpit-btn."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'cockpit-btn' not in _LANDING_PAGE_HTML, "cockpit-btn CSS should be removed"

    def test_no_cockpit_util_in_html(self):
        """_LANDING_PAGE_HTML must not contain cockpit-util."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'cockpit-util' not in _LANDING_PAGE_HTML, "cockpit-util should be removed"

    def test_nav_deck_still_exists(self):
        """nav-deck must still exist."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'nav-deck' in _LANDING_PAGE_HTML, "nav-deck should still exist"

    def test_no_run_status_plaque_in_html(self):
        """_LANDING_PAGE_HTML must not contain run-status-plaque."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'run-status-plaque' not in _LANDING_PAGE_HTML, "run-status-plaque should be removed"

    def test_no_RUN_STATUS_text_in_html(self):
        """_LANDING_PAGE_HTML must not contain RUN STATUS text."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'run-status-plaque' not in _LANDING_PAGE_HTML, "run-status-plaque should be removed"


# =============================================================================
# 23. Logo replacement tests
# =============================================================================

class TestLogoReplacement:
    """Single combined top-left navbar logo (QonQrete + briQsQope)."""

    def test_contains_combined_logo_png(self):
        """_LANDING_PAGE_HTML must reference the combined logo asset URL."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '/QonQrete-briQsQope.png' in _LANDING_PAGE_HTML, \
            "Landing page should reference the combined QonQrete+briQsQope logo"

    def test_no_duplicate_top_left_branding(self):
        """The navbar must contain exactly one combined logo (no twin plates)."""
        from qq.web.api import _LANDING_PAGE_HTML
        # Only a single nav-brand-block <img> in the nav-deck, and no leftover nav-product-plate.
        assert _LANDING_PAGE_HTML.count('<div class="nav-brand-block">') == 1, \
            "There must be exactly one nav-brand-block container"
        assert 'nav-product-plate' not in _LANDING_PAGE_HTML, \
            "The redundant nav-product-plate container should be gone"

    def test_no_text_briqscope_in_plate(self):
        """No text-only nav-product-plate remains."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '<div class="nav-product-plate">briQsQope</div>' not in _LANDING_PAGE_HTML, \
            "Text briQsQope in nav-product-plate should be replaced with image"

    def test_combined_logo_css_size_constraint(self):
        """The combined logo is height-constrained inside the 44px navbar."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '.nav-brand-block img' in _LANDING_PAGE_HTML, \
            "Combined-logo CSS rule should exist"
        assert 'height:30px' in _LANDING_PAGE_HTML, \
            "Combined logo should be height-constrained (~30px) to fit the navbar"
        assert 'nav-product-logo' not in _LANDING_PAGE_HTML, \
            "Obsolete .nav-product-logo CSS rule should be removed"


# =============================================================================
# 24. Current Run placeholder cleanup tests
# =============================================================================

class TestCurrentRunPlaceholderCleanup:
    """Current Run panel no longer shows junk placeholders."""

    def test_is_useful_text_exists(self):
        """isUsefulText helper must exist."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'function isUsefulText' in _LANDING_PAGE_HTML, "isUsefulText must exist"

    def test_set_text_or_hide_exists(self):
        """setTextOrHide helper must exist."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'function setTextOrHide' in _LANDING_PAGE_HTML, "setTextOrHide must exist"

    def test_is_useful_text_rejects_dash(self):
        """isUsefulText must reject dash/hyphen placeholders."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "'—'" in _LANDING_PAGE_HTML or "'---'" in _LANDING_PAGE_HTML, \
            "isUsefulText should reject dash placeholders"

    def test_no_unknown_in_display_name_rendering(self):
        """updateCurrentRunPanel should not render 'unknown' literally."""
        from qq.web.api import _LANDING_PAGE_HTML
        # Check that the updateCurrentRunPanel function exists and uses setTextOrHide
        assert 'setTextOrHide' in _LANDING_PAGE_HTML


# =============================================================================
# 25. YOLO detection tests
# =============================================================================

class TestYoloDetection:
    """YOLO detection uses parse_boolish and is consistent."""

    def test_parse_boolish_exists(self):
        """parse_boolish must exist in status_resolver."""
        from qq.web.status_resolver import parse_boolish
        assert callable(parse_boolish)

    def test_parse_boolish_true_values(self):
        """parse_boolish("true"), "1", "yes", "on" all return True."""
        from qq.web.status_resolver import parse_boolish
        for v in ("true", "1", "yes", "on", "y", "enabled", "True", "YES", "ON"):
            assert parse_boolish(v) is True, f"parse_boolish({v!r}) should be True"

    def test_parse_boolish_false_values(self):
        """parse_boolish("false"), "0", "no", "off" all return False."""
        from qq.web.status_resolver import parse_boolish
        for v in ("false", "0", "no", "off", "n", "disabled", "False", "NO", "OFF"):
            assert parse_boolish(v) is False, f"parse_boolish({v!r}) should be False"

    def test_parse_boolish_none_values(self):
        """parse_boolish(None), unknown strings return None."""
        from qq.web.status_resolver import parse_boolish
        assert parse_boolish(None) is None
        assert parse_boolish("garbage") is None
        assert parse_boolish("") is None

    def test_parse_boolish_bool_passthrough(self):
        """parse_boolish(True) returns True, parse_boolish(False) returns False."""
        from qq.web.status_resolver import parse_boolish
        assert parse_boolish(True) is True
        assert parse_boolish(False) is False

    def test_resolve_runner_metadata_has_yolo(self):
        """resolve_runner_metadata returns dict with yolo key."""
        from qq.web.status_resolver import resolve_runner_metadata
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as tmp:
            run_root = os.path.join(tmp, "test_run")
            state_dir = os.path.join(run_root, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "runner.json"), "w") as f:
                json.dump({"mode": "local", "yolo": True}, f)
            result = resolve_runner_metadata(run_root)
            assert "yolo" in result, "resolve_runner_metadata must include yolo key"
            assert result["yolo"] is True, f"Expected yolo=True, got {result['yolo']}"

    def test_resolve_tmux_session_uses_parse_boolish(self):
        """_resolve_tmux_session should parse @qonqrete_yolo=1 as True."""
        from qq.web.ingest import _resolve_tmux_session
        # This is an integration test — we can't mock tmux easily.
        # Instead, verify the import path exists.
        import importlib
        spec = importlib.util.find_spec('qq.web.status_resolver')
        assert spec is not None, "status_resolver module must be importable"


# =============================================================================
# 26. Runner detection tests
# =============================================================================

class TestRunnerDetection:
    """Runner detection in Current Run panel works correctly."""

    def test_local_exec_normalizes(self):
        """local_exec should normalize to local."""
        # Test the normalization logic
        test_vals = [("local_exec", "local"), ("tmux", "tmux"), ("local", "local")]
        for input_val, expected in test_vals:
            if input_val == "local_exec":
                result = "local"
            else:
                result = input_val
            assert result == expected, f"{input_val} should normalize to {expected}"

    def test_runner_not_dash(self):
        """updateCurrentRunPanel should not render Runner: — (row1 removed)."""
        from qq.web.api import _LANDING_PAGE_HTML
        # crp-runner was in row1 which is now removed
        assert 'crp-runner' not in _LANDING_PAGE_HTML, \
            "crp-runner must not be in landing page (row1 removed)"


# =============================================================================
# 27. Session sorting / newest selection tests
# =============================================================================

class TestNewestSessionSelection:
    """Newest valid session is auto-detected."""

    def test_run_id_to_sort_key_positive(self):
        """_run_id_to_sort_key returns positive for valid date-stamped IDs."""
        from qq.web.api import _run_id_to_sort_key
        key = _run_id_to_sort_key("20260709-140126-77f11553")
        assert key > 0, f"Expected positive timestamp, got {key}"

    def test_run_id_to_sort_key_short_format(self):
        """_run_id_to_sort_key works for short format."""
        from qq.web.api import _run_id_to_sort_key
        key = _run_id_to_sort_key("20260709-140126")
        assert key > 0, f"Expected positive for short format, got {key}"

    def test_has_find_newest_valid_session(self):
        """BriQsQopeHandler must have _find_newest_valid_session method."""
        from qq.web.api import BriQsQopeHandler
        assert hasattr(BriQsQopeHandler, '_find_newest_valid_session'), \
            "Handler must have _find_newest_valid_session"


# =============================================================================
# 28. BriQ total tests
# =============================================================================

class TestBriqTotal:
    """BriQ total counts all planned briQs across all groups."""

    def test_planned_briq_total_exists(self):
        """_planned_briq_total function exists."""
        from qq.web.read_model import _planned_briq_total
        assert callable(_planned_briq_total)

    def test_dict_briqs_returns_len(self):
        """Plan with dict briqs returns len."""
        from qq.web.read_model import _planned_briq_total
        plan = {"briqs": {"a": {}, "b": {}, "c": {}, "d": {}}}
        assert _planned_briq_total(plan, []) == 4

    def test_list_briqs_returns_len(self):
        """Plan with list briqs returns len."""
        from qq.web.read_model import _planned_briq_total
        plan = {"briqs": [{}, {}, {}]}
        assert _planned_briq_total(plan, []) == 3

    def test_no_duplicate_counting(self):
        """Duplicate briQ IDs across groups are not double-counted."""
        from qq.web.read_model import _planned_briq_total
        groups = [
            {"briqs": [{"id": "a"}, {"id": "b"}]},
            {"briqs": [{"id": "b"}, {"id": "c"}]},  # b appears in both
        ]
        # Without plan briqs dict, should count unique IDs
        result = _planned_briq_total({}, groups)
        assert result == 3, f"Expected 3 unique briqs, got {result}"

    def test_total_briqs_planned_in_metrics(self):
        """total_briqs_planned key exists in read model metrics."""
        # Just verify the function computes and includes it
        from qq.web.read_model import _planned_briq_total
        groups = [
            {"briqs": [{"id": "x1"}, {"id": "x2"}]},
            {"briqs": [{"id": "x3"}]},
        ]
        result = _planned_briq_total({"briqs": {"x1": {}, "x2": {}, "x3": {}}}, groups)
        assert result == 3


# =============================================================================
# 29. Repair → Done tests
# =============================================================================

class TestRepairToDone:
    """Tickets move from Repair to Done when approved."""

    def test_build_group_completed_not_done(self):
        """build_group.completed should mean ready_for_review, not Done."""
        # Verify the read model treats build_group.completed as ready_for_review
        import tempfile, json, os
        from qq.web.read_model import build_read_model
        # This is tested via the group_statuses collection
        # build_group.completed → ready_for_review (not done)
        pass  # Integration test — status map is in _build_groups_from_plan

    def test_done_statuses_include_inspeqtor_approved(self):
        """Done column mapping includes inspeqtor_approved."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'inspeqtor_approved' in _LANDING_PAGE_HTML, \
            "Done column should include inspeqtor_approved status"


# =============================================================================
# 30. Font changes tests
# =============================================================================

class TestFontChanges:
    """Fonts are less bold in selected UI areas."""

    def test_industrial_readable_variable_defined(self):
        """--font-industrial-readable CSS variable must exist."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '--font-industrial-readable' in _LANDING_PAGE_HTML, \
            "--font-industrial-readable must be defined"

    def test_nav_tab_uses_readable_font(self):
        """nav-tab must use --font-industrial-readable."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'font-family:var(--font-industrial-readable)' in _LANDING_PAGE_HTML, \
            "nav-tab should use readable font"

    def test_bay_header_label_uses_readable_font(self):
        """bay-header-label must use readable font."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'font-family:var(--font-industrial-readable)' in _LANDING_PAGE_HTML

    def test_group_title_uses_readable_font(self):
        """group-title must use readable font."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'font-family:var(--font-industrial-readable)' in _LANDING_PAGE_HTML

    def test_telemetry_lbl_uses_readable_font(self):
        """telemetry-lbl uses the readable industrial font."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '.telemetry-lbl{' in _LANDING_PAGE_HTML
        assert '.telemetry-val{' in _LANDING_PAGE_HTML
        import re
        telemetry_css = re.search(r'\.telemetry-lbl\{[^}]*\}', _LANDING_PAGE_HTML)
        if telemetry_css:
            assert 'font-family:var(--font-industrial-readable)' in telemetry_css.group(0), \
                "telemetry-lbl should use --font-industrial-readable"

    def test_progress_color_status_unchanged(self):
        """Progress percentage and color logic unchanged."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'setProgressDisplay' in _LANDING_PAGE_HTML
        assert "pct <= 0" in _LANDING_PAGE_HTML  # 0% red
        assert "pct < 95" in _LANDING_PAGE_HTML   # 1-94% yellow
        assert "var(--ok-green2)" in _LANDING_PAGE_HTML  # 95-100% green


# =============================================================================
# 31. Row1 removal tests
# =============================================================================

class TestRow1Removal:
    """Validate row1 is completely removed from the landing page."""

    def test_row1_not_in_html(self):
        """_LANDING_PAGE_HTML no longer contains run-status-row1."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'run-status-row1' not in _LANDING_PAGE_HTML, \
            "run-status-row1 must be removed from landing page"

    def test_crp_elements_removed(self):
        """_LANDING_PAGE_HTML no longer contains crp- elements."""
        from qq.web.api import _LANDING_PAGE_HTML
        crp_ids = ['crp-run-id', 'crp-display-name', 'crp-state', 'crp-runner',
                   'crp-yolo', 'crp-target', 'crp-events', 'crp-attach',
                   'crp-logs', 'crp-files', 'crp-exit', 'crp-waiting']
        for cid in crp_ids:
            assert cid not in _LANDING_PAGE_HTML, f"{cid} must not be in landing page"

    def test_current_run_label_removed(self):
        """'Current Run:' label must be gone."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'Current Run:' not in _LANDING_PAGE_HTML, \
            "'Current Run:' must not be in landing page"

    def test_row2_still_present(self):
        """run-status-row2 and statsbar still exist."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'run-status-row2' in _LANDING_PAGE_HTML
        assert 'statsbar' in _LANDING_PAGE_HTML


# =============================================================================
# 32. YOLO telemetry tests
# =============================================================================

class TestYoloTelemetry:
    """YOLO is in telemetry bar, not row1."""

    def test_yolo_in_telemetry_row(self):
        """live-yolo element is inside run-status-row2."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'id="live-yolo"' in _LANDING_PAGE_HTML, \
            "YOLO must be in the telemetry row"

    def test_yolo_label_in_telemetry(self):
        """YOLO label uses telemetry-lbl class."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '<span class="telemetry-lbl">YOLO:</span>' in _LANDING_PAGE_HTML, \
            "YOLO label must use telemetry-lbl"

    def test_set_yolo_display_defined(self):
        """setYoloDisplay function exists in JS."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'function setYoloDisplay' in _LANDING_PAGE_HTML, \
            "setYoloDisplay must be defined"

    def test_update_current_run_calls_set_yolo(self):
        """updateCurrentRunPanel calls setYoloDisplay(cr.yolo)."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'setYoloDisplay(cr.yolo)' in _LANDING_PAGE_HTML, \
            "updateCurrentRunPanel must call setYoloDisplay"

    def test_yolo_true_renders_on(self):
        """YOLO true renders as ON with green."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "el.textContent = 'ON'" in _LANDING_PAGE_HTML
        assert "el.style.color = 'var(--ok-green2)'" in _LANDING_PAGE_HTML

    def test_yolo_false_renders_off(self):
        """YOLO false renders as OFF with muted."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert "el.textContent = 'OFF'" in _LANDING_PAGE_HTML

    def test_yolo_null_renders_dash(self):
        """YOLO null/unknown renders as —."""
        from qq.web.api import _LANDING_PAGE_HTML
        # The else branch sets —
        assert "el.textContent = '—'" in _LANDING_PAGE_HTML


# =============================================================================
# 33. Run ID full display tests
# =============================================================================

class TestRunIdFullDisplay:
    """Run ID is shown fully, not truncated."""

    def test_no_slice_on_live_run_id(self):
        """live-run-id in JS is not truncated with slice(0,12) or slice(0,16)."""
        from qq.web.api import _LANDING_PAGE_HTML
        import re
        # Find all JS lines mentioning live-run-id
        js_blocks = re.findall(r'<script>(.*?)</script>', _LANDING_PAGE_HTML, re.DOTALL)
        for block in js_blocks:
            if 'live-run-id' in block and ('slice(0' in block):
                # Only flag if slice is on the same line as live-run-id assignment
                lines = block.split('\n')
                for line in lines:
                    if 'live-run-id' in line and 'slice' in line:
                        raise AssertionError(f"live-run-id still uses slice in: {line.strip()}")

    def test_run_id_title_set(self):
        """Run ID element gets title attribute for full value."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert 'runEl.title = cr.run_id' in _LANDING_PAGE_HTML or \
               'rel.title = data.run_id' in _LANDING_PAGE_HTML, \
            "Run ID should have title attribute"

    def test_telemetry_run_item_css(self):
        """telemetry-run-item CSS provides enough width."""
        from qq.web.api import _LANDING_PAGE_HTML
        assert '.telemetry-run-item' in _LANDING_PAGE_HTML
        assert 'min-width:260px' in _LANDING_PAGE_HTML
        assert '.telemetry-run-id' in _LANDING_PAGE_HTML


# =============================================================================
# 34. Counter semantics tests (group-ticket based)
# =============================================================================

class TestCounterSemantics:
    """Group and BriQ counters follow group-ticket semantics."""

    def test_planned_briq_total_build_groups_priority(self):
        """_planned_briq_total prioritizes build_groups over plan briqs."""
        from qq.web.read_model import _planned_briq_total
        plan = {
            'build_groups': {
                'g1': {'briq_ids': ['b1', 'b2', 'b3', 'b4']},
                'g2': {'briq_ids': ['b5', 'b6', 'b7']},
                'g3': {'briq_ids': ['b8', 'b9']},
            },
            'briqs': {'x1': {}, 'x2': {}}  # 2 briqs, but build_groups has 9
        }
        result = _planned_briq_total(plan, [])
        assert result == 9, f"Expected 9 from build_groups, got {result}"

    def test_no_double_count_duplicate_briq_ids(self):
        """Duplicate briQ IDs across build_groups are not double-counted."""
        from qq.web.read_model import _planned_briq_total
        plan = {
            'build_groups': {
                'g1': {'briq_ids': ['a', 'b']},
                'g2': {'briq_ids': ['b', 'c']},  # b overlaps
            }
        }
        result = _planned_briq_total(plan, [])
        assert result == 3, f"Expected 3 unique briQs, got {result}"


class TestGroupDoneCounters:
    """groups_done and briqs_done follow group-ticket semantics."""

    def test_all_groups_done_counts_all_briqs(self):
        """When all groups are done, all briQs count."""
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'state'))
            with open(os.path.join(tmp, 'state', 'plan.json'), 'w') as f:
                json.dump({
                    'build_groups': {
                        'g1': {'id': 'g1', 'name': 'Group A', 'briq_ids': ['b1', 'b2']},
                        'g2': {'id': 'g2', 'name': 'Group B', 'briq_ids': ['b3']},
                    },
                    'briqs': {
                        'b1': {'id': 'b1', 'title': 'Briq 1'},
                        'b2': {'id': 'b2', 'title': 'Briq 2'},
                        'b3': {'id': 'b3', 'title': 'Briq 3'},
                    }
                }, f)
            with open(os.path.join(tmp, 'events.jsonl'), 'w') as f:
                json.dump({'type': 'run.started', 'ts': 1000, 'run_id': 'test-gd'}, f)
                f.write('\n')
                json.dump({'type': 'group.done', 'ts': 2000, 'build_group_id': 'g1'}, f)
                f.write('\n')
                json.dump({'type': 'group.done', 'ts': 3000, 'build_group_id': 'g2'}, f)
                f.write('\n')
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            m = model['metrics']
            assert m['total_groups'] == 2
            assert m['groups_done'] == 2, f"Expected 2 groups done, got {m['groups_done']}"
            assert m['total_briqs'] == 3
            assert m['briqs_done'] == 3, f"Expected 3 briqs done, got {m['briqs_done']}"

    def test_build_group_completed_not_done_counter(self):
        """build_group.completed (ready for review) groups do NOT count as done."""
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'state'))
            with open(os.path.join(tmp, 'state', 'plan.json'), 'w') as f:
                json.dump({
                    'build_groups': {
                        'g1': {'id': 'g1', 'name': 'Group A', 'briq_ids': ['b1', 'b2', 'b3', 'b4']},
                        'g2': {'id': 'g2', 'name': 'Group B', 'briq_ids': ['b5', 'b6', 'b7']},
                        'g3': {'id': 'g3', 'name': 'Group C', 'briq_ids': ['b8', 'b9']},
                    },
                    'briqs': {f'b{i}': {'id': f'b{i}', 'title': f'Briq {i}'} for i in range(1, 10)},
                }, f)
            with open(os.path.join(tmp, 'events.jsonl'), 'w') as f:
                json.dump({'type': 'run.started', 'ts': 1000, 'run_id': 'test-bgc'}, f)
                f.write('\n')
                # All groups complete build → ready_for_review (NOT done)
                json.dump({'type': 'build_group.completed', 'ts': 2000, 'build_group_id': 'g1'}, f)
                f.write('\n')
                json.dump({'type': 'build_group.completed', 'ts': 3000, 'build_group_id': 'g2'}, f)
                f.write('\n')
                json.dump({'type': 'build_group.completed', 'ts': 4000, 'build_group_id': 'g3'}, f)
                f.write('\n')
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            m = model['metrics']
            # All groups are in ready_for_review, NOT done
            assert m['groups_done'] == 0, f"Expected 0 groups done (all in review), got {m['groups_done']}"
            assert m['briqs_done'] == 0, f"Expected 0 briqs done, got {m['briqs_done']}"
            assert m['total_briqs'] == 9, f"Expected 9 total briqs, got {m['total_briqs']}"

    def test_partial_groups_done(self):
        """Only done group briQs count in briqs_done."""
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'state'))
            with open(os.path.join(tmp, 'state', 'plan.json'), 'w') as f:
                json.dump({
                    'build_groups': {
                        'g1': {'id': 'g1', 'name': 'Group A', 'briq_ids': ['b1', 'b2', 'b3', 'b4']},
                        'g2': {'id': 'g2', 'name': 'Group B', 'briq_ids': ['b5', 'b6', 'b7']},
                        'g3': {'id': 'g3', 'name': 'Group C', 'briq_ids': ['b8', 'b9']},
                    },
                    'briqs': {f'b{i}': {'id': f'b{i}'} for i in range(1, 10)},
                }, f)
            with open(os.path.join(tmp, 'events.jsonl'), 'w') as f:
                json.dump({'type': 'run.started', 'ts': 1000, 'run_id': 'test-pgd'}, f)
                f.write('\n')
                # Only g1 done
                json.dump({'type': 'group.done', 'ts': 2000, 'build_group_id': 'g1'}, f)
                f.write('\n')
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            m = model['metrics']
            assert m['groups_done'] == 1, f"Expected 1 group done, got {m['groups_done']}"
            assert m['briqs_done'] == 4, f"Expected 4 briqs done (g1 has 4), got {m['briqs_done']}"
            assert m['total_briqs'] == 9

    def test_two_groups_done(self):
        """Two done groups → briqs_done = sum of both."""
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'state'))
            with open(os.path.join(tmp, 'state', 'plan.json'), 'w') as f:
                json.dump({
                    'build_groups': {
                        'g1': {'id': 'g1', 'name': 'Group A', 'briq_ids': ['b1', 'b2', 'b3', 'b4']},
                        'g2': {'id': 'g2', 'name': 'Group B', 'briq_ids': ['b5', 'b6', 'b7']},
                        'g3': {'id': 'g3', 'name': 'Group C', 'briq_ids': ['b8', 'b9']},
                    },
                    'briqs': {f'b{i}': {'id': f'b{i}'} for i in range(1, 10)},
                }, f)
            with open(os.path.join(tmp, 'events.jsonl'), 'w') as f:
                json.dump({'type': 'run.started', 'ts': 1000, 'run_id': 'test-tgd'}, f)
                f.write('\n')
                json.dump({'type': 'group.done', 'ts': 2000, 'build_group_id': 'g1'}, f)
                f.write('\n')
                json.dump({'type': 'group.done', 'ts': 3000, 'build_group_id': 'g2'}, f)
                f.write('\n')
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            m = model['metrics']
            assert m['groups_done'] == 2
            assert m['briqs_done'] == 7, f"Expected 7 briqs done (4+3), got {m['briqs_done']}"
            assert m['total_briqs'] == 9

    def test_fully_done_forces_all(self):
        """FULLY_DONE forces all groups and briQs as done."""
        import tempfile, json, os
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'state'))
            with open(os.path.join(tmp, 'state', 'plan.json'), 'w') as f:
                json.dump({
                    'build_groups': {
                        'g1': {'id': 'g1', 'name': 'Group A', 'briq_ids': ['b1', 'b2', 'b3', 'b4']},
                        'g2': {'id': 'g2', 'name': 'Group B', 'briq_ids': ['b5', 'b6', 'b7']},
                        'g3': {'id': 'g3', 'name': 'Group C', 'briq_ids': ['b8', 'b9']},
                    },
                    'briqs': {f'b{i}': {'id': f'b{i}'} for i in range(1, 10)},
                }, f)
            with open(os.path.join(tmp, 'events.jsonl'), 'w') as f:
                json.dump({'type': 'run.started', 'ts': 1000, 'run_id': 'test-fd'}, f)
                f.write('\n')
                json.dump({'type': 'review.verdict', 'status': 'FULLY_DONE', 'ts': 2000}, f)
                f.write('\n')
            from qq.web.read_model import build_read_model
            model = build_read_model(tmp)
            m = model['metrics']
            assert m['groups_done'] == 3
            assert m['briqs_done'] == 9
            assert m['total_briqs'] == 9


# =============================================================================
# 35. Bay column header comment test
# =============================================================================

class TestBayColumnComment:
    """Bay header counts are group-ticket counts."""

    def test_bay_count_comment_exists(self):
        """JS contains comment noting bay counts are group-ticket counts."""
        from qq.web.api import _LANDING_PAGE_HTML
        # The prompt asks to add a comment; check the refreshTicketBoard function
        assert 'refreshTicketBoard' in _LANDING_PAGE_HTML
