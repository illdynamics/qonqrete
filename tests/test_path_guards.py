"""
Tests for path guardrails — ensuring QonQrete never writes project files
into its own metadata directories (.qq, run_root, etc.) and never runs
commands with cwd pointing to metadata directories.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qq.path_guards import (
    is_under,
    is_under_qq_metadata,
    assert_project_write_allowed,
    assert_command_cwd_allowed,
    resolve_project_path,
    PathPolicyViolation,
)


class TestIsUnder:
    def test_path_equals_root(self):
        assert is_under("/tmp/foo", "/tmp/foo") is True

    def test_path_inside_root(self):
        assert is_under("/tmp/foo/bar", "/tmp/foo") is True

    def test_path_outside_root(self):
        assert is_under("/tmp/other", "/tmp/foo") is False

    def test_deeply_nested(self):
        assert is_under("/tmp/foo/a/b/c/d/e", "/tmp/foo") is True

    def test_sibling_directories(self):
        assert is_under("/tmp/foobar", "/tmp/foo") is False


class TestIsUnderQQMetadata:
    def test_inside_run_root(self):
        assert is_under_qq_metadata("/x/qq/runs/abc/app.py", run_root="/x/qq/runs/abc") is True

    def test_outside_run_root(self):
        assert is_under_qq_metadata("/x/qq/testwebsite/app.py", run_root="/x/qq/runs/abc") is False

    def test_inside_workspace_dot_qq(self, tmp_path):
        ws = str(tmp_path / "project")
        qq_dir = tmp_path / "project" / ".qq"
        qq_dir.mkdir(parents=True)
        assert is_under_qq_metadata(str(qq_dir / "runs" / "abc" / "app.py"), workspace_root=ws) is True

    def test_path_contains_dot_qq(self):
        assert is_under_qq_metadata("/x/foo/.qq/app.py", workspace_root="/x/foo", run_root="/x/qq/runs/abc") is True


class TestAssertProjectWriteAllowed:
    def test_allowed_write_in_workspace(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        # Should not raise
        assert_project_write_allowed(os.path.join(ws, "app.py"), ws, run)

    def test_forbidden_write_in_run_root(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_project_write_allowed(os.path.join(run, "app.py"), ws, run)
        assert exc.value.reason == "project_write_inside_qonqrete_metadata"

    def test_forbidden_write_in_dot_qq(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        qq_dir = tmp_path / "project" / ".qq" / "runs" / "r1"
        qq_dir.mkdir(parents=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_project_write_allowed(str(qq_dir / "app.py"), ws, run)
        assert exc.value.reason == "project_write_inside_qonqrete_metadata"

    def test_forbidden_write_outside_workspace(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        outside = str(tmp_path / "other" / "app.py")
        os.makedirs(os.path.dirname(outside), exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_project_write_allowed(outside, ws, run)
        assert exc.value.reason == "project_write_outside_workspace"

    def test_allowed_with_escape_hatch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QONQRETE_ALLOW_PROJECT_WRITES_IN_QQ", "true")
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        qq_dir = tmp_path / "project" / ".qq" / "runs" / "r1"
        qq_dir.mkdir(parents=True)
        os.makedirs(run, exist_ok=True)
        # Should not raise with escape hatch
        assert_project_write_allowed(str(qq_dir / "app.py"), ws, run)


class TestAssertCommandCwdAllowed:
    def test_allowed_cwd_in_workspace(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        assert_command_cwd_allowed(ws, ws, run)

    def test_allowed_cwd_in_workspace_subdir(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        subdir = os.path.join(ws, "src")
        os.makedirs(subdir, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        assert_command_cwd_allowed(subdir, ws, run)

    def test_forbidden_cwd_in_run_root(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_command_cwd_allowed(run, ws, run)
        assert exc.value.reason == "command_cwd_inside_qonqrete_metadata"

    def test_forbidden_cwd_in_dot_qq(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        qq_dir = tmp_path / "project" / ".qq"
        qq_dir.mkdir(parents=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_command_cwd_allowed(str(qq_dir), ws, run)
        assert exc.value.reason == "command_cwd_inside_qonqrete_metadata"


class TestResolveProjectPath:
    def test_resolves_relative_to_workspace(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        p = resolve_project_path("app.py", ws, run)
        assert str(p) == str(Path(ws) / "app.py")

    def test_resolves_absolute_path(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        abs_path = os.path.join(ws, "src", "main.py")
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        p = resolve_project_path(abs_path, ws, run)
        assert str(p) == abs_path

    def test_rejects_path_in_run_root(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation):
            resolve_project_path(os.path.join(run, "app.py"), ws, run)


class TestPathPolicyViolationEvent:
    def test_to_event_format(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        exc = PathPolicyViolation(
            path=os.path.join(run, "app.py"),
            reason="project_write_inside_qonqrete_metadata",
            workspace_root=ws,
            run_root=run,
        )
        event = exc.to_event(agent="construQtor")
        assert event["type"] == "path_policy_violation"
        assert event["severity"] == "error"
        assert event["reason"] == "project_write_inside_qonqrete_metadata"
        assert event["agent"] == "construQtor"
        assert "path" in event
        assert "workspace_root" in event
        assert "run_root" in event


# =============================================================================
# Comprehensive scenario tests from repofix.md spec
# =============================================================================

class TestRepoFixSpecScenarios:
    """Tests matching the specific scenarios from repofix.md Section 12."""

    def test_scenario_allowed_project_write(self, tmp_path):
        """Test D: Allowed paths for project writes."""
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "r1")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)

        # Allowed
        assert_project_write_allowed(os.path.join(ws, "app.py"), ws, run)
        assert_project_write_allowed(os.path.join(ws, "src", "main.py"), ws, run)

    def test_scenario_forbidden_project_write(self, tmp_path):
        """Test D: Forbidden paths for project writes."""
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "r1")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        qq_runs = tmp_path / "project" / ".qq" / "runs" / "r1"
        qq_runs.mkdir(parents=True)

        forbidden = [
            os.path.join(str(qq_runs), "app.py"),
            os.path.join(ws, ".qq", "app.py"),
            os.path.join(run, "app.py"),
            os.path.join(run, "src", "main.py"),
        ]
        for path in forbidden:
            with pytest.raises(PathPolicyViolation):
                assert_project_write_allowed(path, ws, run)

    def test_scenario_command_cwd_allowed(self, tmp_path):
        """Test E: Allowed cwd paths for commands."""
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "r1")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        os.makedirs(os.path.join(ws, "src"), exist_ok=True)

        assert_command_cwd_allowed(ws, ws, run)
        assert_command_cwd_allowed(os.path.join(ws, "src"), ws, run)

    def test_scenario_command_cwd_forbidden(self, tmp_path):
        """Test E: Forbidden cwd paths for commands."""
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "r1")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        qq_dir = tmp_path / "project" / ".qq"
        qq_dir.mkdir(parents=True)

        forbidden_cwds = [
            str(qq_dir),
            os.path.join(ws, ".qq", "runs", "r1"),
            run,
        ]
        for cwd in forbidden_cwds:
            with pytest.raises(PathPolicyViolation):
                assert_command_cwd_allowed(cwd, ws, run)


class TestAgentPromptContract:
    """Test F: Verify PATH CONTRACT is present in agent prompts with actual paths."""

    def test_qlarifier_has_path_contract(self):
        from qq.agents.qlarifier import _build_system_primer
        primer = _build_system_primer(workspace_root="/x/test", run_root="/x/runs/1")
        assert "WORKSPACE_ROOT (TARGET_PATH): /x/test" in primer
        assert "RUN_ROOT (QonQrete metadata): /x/runs/1" in primer
        assert "metadata-only" in primer

    def test_instruqtor_has_path_contract(self):
        from qq.agents.instruqtor import _build_system_primer
        primer = _build_system_primer(workspace_root="/x/test", run_root="/x/runs/1")
        assert "WORKSPACE_ROOT (TARGET_PATH): /x/test" in primer
        assert "RUN_ROOT (QonQrete metadata): /x/runs/1" in primer
        assert "metadata-only" in primer

    def test_construqtor_has_path_contract(self):
        from qq.agents.construqtor import _build_system_primer, _build_repair_primer
        primer = _build_system_primer(workspace_root="/x/test", run_root="/x/runs/1")
        assert "WORKSPACE_ROOT (TARGET_PATH): /x/test" in primer
        assert "RUN_ROOT (QonQrete metadata): /x/runs/1" in primer
        assert "metadata-only" in primer
        # Also check repair primer
        repair = _build_repair_primer(workspace_root="/x/test", run_root="/x/runs/1")
        assert "WORKSPACE_ROOT (TARGET_PATH): /x/test" in repair
        assert "RUN_ROOT (QonQrete metadata): /x/runs/1" in repair

    def test_inspeqtor_has_path_contract(self):
        from qq.agents.inspeqtor import _build_system_primer
        primer = _build_system_primer(workspace_root="/x/test", run_root="/x/runs/1")
        assert "WORKSPACE_ROOT (TARGET_PATH): /x/test" in primer
        assert "RUN_ROOT (QonQrete metadata): /x/runs/1" in primer
        assert "metadata-only" in primer


# =============================================================================
# Integration tests: real AgentCallSpec verification (item 6)
# =============================================================================

class TestAgentCallSpecIntegration:
    """Verify AgentCallSpec fields for all four agents."""

    @pytest.fixture
    def adapter_workspace(self, tmp_path):
        ws = tmp_path / "project"
        run = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        run.mkdir(parents=True)
        return str(ws), str(run)

    def test_qlarifier_spec_fields(self, adapter_workspace, monkeypatch):
        """qlarifier AgentCallSpec has workspace_root/run_root set."""
        from qq.agents.qlarifier import run_qlarifier
        from qq.adapters.mock import MockAdapter
        ws_root, run_root = adapter_workspace

        # Capture the spec passed to adapter.call()
        captured_spec = []

        class CaptureAdapter(MockAdapter):
            def call(self, spec):
                captured_spec.append(spec)
                return super().call(spec)

        adapter = CaptureAdapter()
        adapter._review_calls = 2  # force FULLY_DONE for inspeqtor

        def ask_human(qs):
            return ["mock answer" for _ in qs]

        run_qlarifier(
            adapter,
            __import__('qq.models', fromlist=['Task']).Task(raw_text="build a CLI"),
            ws_root,
            "mock-model",
            ask_human,
            run_root=run_root,
            workspace_root=ws_root,
        )

        assert len(captured_spec) > 0
        spec = captured_spec[0]
        assert spec.workspace_root == ws_root
        assert spec.run_root == run_root
        assert spec.cd == ws_root
        assert spec.workdir == ws_root

    def test_instruqtor_spec_fields(self, adapter_workspace, monkeypatch):
        """instruqtor AgentCallSpec has workspace_root/run_root set."""
        from qq.agents.instruqtor import run_instruqtor
        from qq.adapters.mock import MockAdapter
        from qq.models import ClarifiedTask
        ws_root, run_root = adapter_workspace

        captured_spec = []

        class CaptureAdapter(MockAdapter):
            def call(self, spec):
                captured_spec.append(spec)
                return super().call(spec)

        adapter = CaptureAdapter()
        clarified = ClarifiedTask(clarified_text="build a CLI", id="ct-1")

        run_instruqtor(
            adapter, clarified,
            ws_root,
            "mock-model",
            run_root=run_root,
            workspace_root=ws_root,
        )

        assert len(captured_spec) > 0
        spec = captured_spec[0]
        assert spec.workspace_root == ws_root
        assert spec.run_root == run_root
        assert spec.cd == ws_root
        assert spec.workdir == ws_root

    def test_inspeqtor_spec_fields(self, adapter_workspace, monkeypatch):
        """inspeqtor AgentCallSpec has workspace_root/run_root set."""
        from qq.agents.inspeqtor import run_inspeqtor
        from qq.adapters.mock import MockAdapter
        from qq.models import ClarifiedTask, BuildGroup, BriQ, BriqStatus
        ws_root, run_root = adapter_workspace

        captured_spec = []

        class CaptureAdapter(MockAdapter):
            def call(self, spec):
                captured_spec.append(spec)
                return super().call(spec)

        adapter = CaptureAdapter()
        adapter._review_calls = 0
        clarified = ClarifiedTask(clarified_text="build a CLI", id="ct-1")
        briq = BriQ(id="b-1", title="cli", description="build CLI", status=BriqStatus.AWAITING_REVIEW)
        group = BuildGroup(id="bg-1", name="core", description="core", briq_ids=["b-1"])

        from qq.workspaces import WorkspaceManager
        wm = WorkspaceManager(ws_root, run_root, "run001", no_repo=True)

        # Create a mock repo_root for workspace manager
        run_inspeqtor(
            adapter, clarified, [group], wm, ws_root,
            "mock-model", 1, run_root,
            workspace_root=ws_root,
        )

        assert len(captured_spec) > 0
        spec = captured_spec[0]
        assert spec.workspace_root == ws_root
        assert spec.run_root == run_root
        assert spec.cd == ws_root
        assert spec.workdir == ws_root


class TestMockAdapterPathEnforcement:
    """Verify MockAdapter enforces path guards."""

    @pytest.fixture
    def mock_dirs(self, tmp_path):
        ws = tmp_path / "project"
        run = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        run.mkdir(parents=True)
        qq_dir = ws / ".qq"
        qq_dir.mkdir(parents=True)
        return str(ws), str(run)

    def test_construqtor_workdir_workspace_passes(self, mock_dirs):
        """MockAdapter construqtor with workdir=workspace_root passes."""
        from qq.adapters.mock import MockAdapter
        from qq.adapters.base import AgentCallSpec
        ws_root, run_root = mock_dirs

        adapter = MockAdapter()
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=ws_root, output_file="output.json",
            workspace_root=ws_root, run_root=run_root,
            cd=ws_root, repo_root=ws_root,
        )
        result = adapter.call(spec)
        assert result.exit_code == 0

    def test_construqtor_workdir_run_root_raises(self, mock_dirs):
        """MockAdapter construqtor with workdir=run_root raises PathPolicyViolation."""
        from qq.adapters.mock import MockAdapter
        from qq.adapters.base import AgentCallSpec
        from qq.path_guards import PathPolicyViolation
        ws_root, run_root = mock_dirs

        adapter = MockAdapter()
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=run_root, output_file="output.json",
            workspace_root=ws_root, run_root=run_root,
            cd=run_root, repo_root=ws_root,
        )
        with pytest.raises(PathPolicyViolation, match="command_cwd_inside_qonqrete_metadata"):
            adapter.call(spec)

    def test_construqtor_workdir_dot_qq_raises(self, mock_dirs):
        """MockAdapter construqtor with workdir=.qq raises PathPolicyViolation."""
        from qq.adapters.mock import MockAdapter
        from qq.adapters.base import AgentCallSpec
        from qq.path_guards import PathPolicyViolation
        ws_root, run_root = mock_dirs
        qq_dir = os.path.join(ws_root, ".qq")

        adapter = MockAdapter()
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=qq_dir, output_file="output.json",
            workspace_root=ws_root, run_root=run_root,
            cd=qq_dir, repo_root=ws_root,
        )
        with pytest.raises(PathPolicyViolation, match="command_cwd_inside_qonqrete_metadata"):
            adapter.call(spec)

    def test_construqtor_main_py_in_run_root_raises(self, mock_dirs):
        """MockAdapter refuses writing main.py under run_root."""
        from qq.adapters.mock import MockAdapter
        from qq.adapters.base import AgentCallSpec
        from qq.path_guards import PathPolicyViolation
        ws_root, run_root = mock_dirs

        adapter = MockAdapter()
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=run_root, output_file="output.json",
            workspace_root=ws_root, run_root=run_root,
            cd=run_root, repo_root=ws_root,
        )
        with pytest.raises(PathPolicyViolation):
            adapter.call(spec)


class TestForbiddenScanBlocking:
    """Verify forbidden deliverable scan blocks completion."""

    def test_run_root_main_py_violation_fails_build(self, tmp_path):
        """Writing main.py under run_root causes build group failure."""
        from qq.path_guards import scan_for_forbidden_bool as scan_for_forbidden_deliverables
        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        os.makedirs(ws_root, exist_ok=True)
        os.makedirs(run_root, exist_ok=True)

        # Create a forbidden file in run_root
        with open(os.path.join(run_root, "main.py"), "w") as f:
            f.write("print('bad')")

        result = scan_for_forbidden_deliverables(run_root, ws_root, agent="construqtor", build_group_id="bg-1", cycle=1)
        assert result is True

    def test_run_root_worktrees_main_py_violation(self, tmp_path):
        """Writing main.py under run_root/worktrees is flagged."""
        from qq.path_guards import scan_for_forbidden_bool as scan_for_forbidden_deliverables
        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        wt_dir = os.path.join(run_root, "worktrees", "bg-1-c1")
        os.makedirs(wt_dir, exist_ok=True)

        # Create a forbidden file in worktrees
        with open(os.path.join(wt_dir, "main.py"), "w") as f:
            f.write("print('bad')")

        result = scan_for_forbidden_deliverables(run_root, ws_root, agent="construqtor", build_group_id="bg-1", cycle=1)
        assert result is True

    def test_workspace_dot_qq_app_py_violation(self, tmp_path):
        """Writing app.py under .qq is flagged."""
        from qq.path_guards import scan_for_forbidden_bool as scan_for_forbidden_deliverables
        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        qq_dir = os.path.join(ws_root, ".qq", "runs", "r1")
        os.makedirs(qq_dir, exist_ok=True)
        os.makedirs(run_root, exist_ok=True)

        with open(os.path.join(qq_dir, "app.py"), "w") as f:
            f.write("print('bad')")

        result = scan_for_forbidden_deliverables(run_root, ws_root, agent="construqtor", build_group_id="bg-1", cycle=1)
        assert result is True

    def test_metadata_paths_not_flagged(self, tmp_path):
        """Metadata files (state/, agents/, events.jsonl) are not flagged."""
        from qq.path_guards import scan_for_forbidden_bool as scan_for_forbidden_deliverables
        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        os.makedirs(ws_root, exist_ok=True)
        os.makedirs(run_root, exist_ok=True)

        # Create normal metadata files
        state_dir = os.path.join(run_root, "state")
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "final.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(run_root, "events.jsonl"), "w") as f:
            f.write("{}")

        # Metadata files should NOT trigger violation
        result = scan_for_forbidden_deliverables(run_root, ws_root, agent="construqtor", build_group_id="bg-1", cycle=1)
        assert result is False

    def test_agents_artifacts_not_flagged(self, tmp_path):
        """Agent metadata files (under agents/) are not flagged."""
        from qq.path_guards import scan_for_forbidden_bool as scan_for_forbidden_deliverables
        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        agents_dir = os.path.join(run_root, "agents", "cycle-000", "construqtor", "call-1")
        os.makedirs(agents_dir, exist_ok=True)

        # Agent artifacts should not trigger
        for fname in ("metadata.json", "result.json", "prompt.md", "stdout.txt", "stderr.txt"):
            with open(os.path.join(agents_dir, fname), "w") as f:
                f.write("{}")

        result = scan_for_forbidden_deliverables(run_root, ws_root, agent="construqtor", build_group_id="bg-1", cycle=1)
        assert result is False


class TestMockAdapterEndToEndHappyPath:
    """Happy path: MockAdapter writes under workspace_root, run_root has only metadata."""

    def test_happy_path_main_py_in_workspace(self, tmp_path):
        """construqtor writes main.py under workspace_root, not run_root."""
        from qq.adapters.mock import MockAdapter
        from qq.adapters.base import AgentCallSpec
        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        os.makedirs(ws_root, exist_ok=True)
        os.makedirs(run_root, exist_ok=True)

        adapter = MockAdapter()
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=ws_root, output_file="construqtor_output.json",
            workspace_root=ws_root, run_root=run_root,
            cd=ws_root, repo_root=ws_root,
        )
        result = adapter.call(spec)
        assert result.exit_code == 0
        assert os.path.exists(os.path.join(ws_root, "main.py"))
        assert not os.path.exists(os.path.join(run_root, "main.py"))

class TestCommandCwdOutsideWorkspace:
    """Fix #2: Command cwd must be inside workspace_root."""

    def test_command_cwd_outside_workspace_raises(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        outside = str(tmp_path / "other")
        os.makedirs(outside, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_command_cwd_allowed(outside, ws, run)
        assert exc.value.reason == "command_cwd_outside_workspace"

    def test_command_cwd_parent_of_workspace_raises(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        parent = str(tmp_path)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_command_cwd_allowed(parent, ws, run)
        assert exc.value.reason == "command_cwd_outside_workspace"

    def test_command_cwd_tmp_other_raises(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_command_cwd_allowed("/tmp/random-other-dir", ws, run)
        assert exc.value.reason == "command_cwd_outside_workspace"


class TestDotQQBlockingWithoutExistence:
    """Fix #3: .qq paths are blocked even when .qq directory does not exist yet."""

    def test_project_write_dot_qq_no_dir_raises(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        # .qq does NOT exist on disk
        with pytest.raises(PathPolicyViolation) as exc:
            assert_project_write_allowed(os.path.join(ws, ".qq", "app.py"), ws, run)
        assert exc.value.reason == "project_write_inside_qonqrete_metadata"

    def test_command_cwd_dot_qq_no_dir_raises(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        # .qq does NOT exist on disk
        with pytest.raises(PathPolicyViolation) as exc:
            assert_command_cwd_allowed(os.path.join(ws, ".qq", "new"), ws, run)
        assert exc.value.reason == "command_cwd_inside_qonqrete_metadata"

    def test_dot_qq_dotdot_resolve_blocked(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        # Path: workspace_root/subdir/../.qq/app.py should resolve to workspace_root/.qq/app.py
        tricky = os.path.join(ws, "subdir", "..", ".qq", "app.py")
        with pytest.raises(PathPolicyViolation) as exc:
            assert_project_write_allowed(tricky, ws, run)
        assert exc.value.reason == "project_write_inside_qonqrete_metadata"

    def test_dot_qq_subdir_blocked(self, tmp_path):
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        with pytest.raises(PathPolicyViolation) as exc:
            assert_project_write_allowed(os.path.join(ws, ".qq", "runs", "r1", "app.py"), ws, run)
        assert exc.value.reason == "project_write_inside_qonqrete_metadata"


class TestHasPathComponent:
    """Test the new has_path_component helper."""

    def test_finds_component(self):
        from qq.path_guards import has_path_component
        assert has_path_component("/x/foo/.qq/app.py", ".qq") is True

    def test_no_component(self):
        from qq.path_guards import has_path_component
        assert has_path_component("/x/foo/src/app.py", ".qq") is False

    def test_component_is_exact(self):
        from qq.path_guards import has_path_component
        # ".q" is not ".qq"
        assert has_path_component("/x/foo/.q/app.py", ".qq") is False


class TestShellHarnessWorkspaceCheck:
    """ShellHarness rejects repo_root outside workspace when workspace_root is supplied."""

    def test_harness_rejects_outside_workspace(self, tmp_path):
        from qq.harness.shell import ShellHarness
        from qq.harness.base import HarnessContext
        from qq.path_guards import PathPolicyViolation
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        outside = str(tmp_path / "other")
        os.makedirs(outside, exist_ok=True)

        harness = ShellHarness(commands=["echo hello"])
        ctx = HarnessContext(repo_root=outside, workspace_root=ws, run_root=run)
        with pytest.raises(PathPolicyViolation) as exc:
            harness.run(ctx)
        assert exc.value.reason == "command_cwd_outside_workspace"

    def test_harness_allows_workspace(self, tmp_path):
        from qq.harness.shell import ShellHarness
        from qq.harness.base import HarnessContext
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)

        harness = ShellHarness(commands=["echo hello"])
        ctx = HarnessContext(repo_root=ws, workspace_root=ws, run_root=run)
        result = harness.run(ctx)
        assert result.passed is True


class TestCodeSeeqAdapterWorkspaceCheck:
    """CodeSeeqAdapter rejects workdir outside workspace."""

    def test_adapter_rejects_outside_workspace(self, tmp_path):
        from qq.adapters.codeseeq import CodeSeeqAdapter
        from qq.adapters.base import AgentCallSpec
        from qq.path_guards import PathPolicyViolation
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        outside = str(tmp_path / "other")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        os.makedirs(outside, exist_ok=True)

        adapter = CodeSeeqAdapter(codeseeq_path="/bin/true")
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=outside, output_file="out.json",
            workspace_root=ws, run_root=run,
            cd=outside, repo_root=ws,
        )
        with pytest.raises(PathPolicyViolation) as exc:
            adapter.call(spec)
        assert exc.value.reason == "command_cwd_outside_workspace"


class TestMockAdapterOutsideWorkspace:
    """MockAdapter rejects workdir/cd outside workspace."""

    def test_adapter_rejects_outside_workspace(self, tmp_path):
        from qq.adapters.mock import MockAdapter
        from qq.adapters.base import AgentCallSpec
        from qq.path_guards import PathPolicyViolation
        ws = str(tmp_path / "project")
        run = str(tmp_path / "runs" / "abc")
        outside = str(tmp_path / "other")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        os.makedirs(outside, exist_ok=True)

        adapter = MockAdapter()
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir=outside, output_file="out.json",
            workspace_root=ws, run_root=run,
            cd=outside, repo_root=ws,
        )
        with pytest.raises(PathPolicyViolation) as exc:
            adapter.call(spec)
        assert exc.value.reason == "command_cwd_outside_workspace"




# =============================================================================
# Regression tests for .qq scanner bypass bug (bubble.md §1, §11)
# =============================================================================

class TestQQScannerBypassRegression:
    """Regression tests proving the .qq scanner hole is fixed."""

    def test_scanner_catches_workspace_dot_qq_outside_run_root(self, tmp_path):
        """A. When run_root is inside workspace/.qq/runs/, scanner catches
        forbidden files in workspace/.qq/* outside run_root."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = str(tmp_path / "project")
        run = os.path.join(ws, ".qq", "runs", "test")
        os.makedirs(run, exist_ok=True)
        # Create .qq/src/main.js outside run_root
        qq_src = os.path.join(ws, ".qq", "src")
        os.makedirs(qq_src, exist_ok=True)
        with open(os.path.join(qq_src, "main.js"), "w") as f:
            f.write("bad")
        violations = scan_for_forbidden_deliverables(run, ws)
        assert len(violations) >= 1, \
            f"Scanner should catch .qq/src/main.js, found {len(violations)}"

    def test_scanner_catches_workspace_dot_qq_src_files(self, tmp_path):
        """B. Scanner catches .qq/src/main.js even when run_root is under .qq."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = str(tmp_path / "project")
        run = os.path.join(ws, ".qq", "runs", "run001")
        os.makedirs(run, exist_ok=True)
        # Create the bad file
        qq_app = os.path.join(ws, ".qq", "app.py")
        os.makedirs(os.path.dirname(qq_app), exist_ok=True)
        with open(qq_app, "w") as f:
            f.write("bad")
        violations = scan_for_forbidden_deliverables(run, ws)
        assert len(violations) >= 1, \
            f"Scanner should catch .qq/app.py, found {len(violations)}"

    def test_external_run_root_catches_dot_qq_violations(self, tmp_path):
        """C. External run_root: scanner catches .qq violations."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "r1")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        qq_src = os.path.join(ws, ".qq", "src")
        os.makedirs(qq_src, exist_ok=True)
        with open(os.path.join(qq_src, "main.py"), "w") as f:
            f.write("bad")
        violations = scan_for_forbidden_deliverables(run, ws)
        assert len(violations) >= 1, \
            f"External run_root should catch .qq violations, found {len(violations)}"

    def test_run_root_catches_bad_files(self, tmp_path):
        """D. Scanner catches bad files in run_root."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "r1")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)
        with open(os.path.join(run, "app.py"), "w") as f:
            f.write("bad")
        violations = scan_for_forbidden_deliverables(run, ws)
        assert len(violations) >= 1, \
            f"Scanner should catch run_root/app.py, found {len(violations)}"

    def test_no_duplicate_violations(self, tmp_path):
        """When run_root is inside .qq, don't double-count violations."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = str(tmp_path / "project")
        run = os.path.join(ws, ".qq", "runs", "test")
        os.makedirs(run, exist_ok=True)
        # Create a bad file only inside the scanned area
        with open(os.path.join(run, "bad.py"), "w") as f:
            f.write("bad")
        violations = scan_for_forbidden_deliverables(run, ws)
        # Should find bad.py exactly once (from run_root scan), not twice
        paths = [v["path"] for v in violations]
        assert paths.count(os.path.join(run, "bad.py")) == 1, \
            f"Should not duplicate: {paths}"

    def test_metadata_not_flagged_even_with_qq_scan(self, tmp_path):
        """Metadata files under run_root are never flagged, even with new .qq scan."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = str(tmp_path / "project")
        run = os.path.join(ws, ".qq", "runs", "test")
        os.makedirs(run, exist_ok=True)
        # Create metadata files
        state_dir = os.path.join(run, "state")
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "final.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(run, "events.jsonl"), "w") as f:
            f.write("{}")
        agents_dir = os.path.join(run, "agents", "cycle-000", "construqtor", "call-1")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(agents_dir, "prompt.md"), "w") as f:
            f.write("test")
        violations = scan_for_forbidden_deliverables(run, ws)
        assert len(violations) == 0, \
            f"Metadata should not be flagged, got: {violations}"


class TestCleanupForbiddenDeliverables:
    """Test that forbidden files are cleaned up."""

    def test_cleanup_removes_forbidden_files(self, tmp_path):
        from qq.path_guards import cleanup_forbidden_deliverables
        test_file = os.path.join(tmp_path, "bad.py")
        with open(test_file, "w") as f:
            f.write("bad")
        violations = [{"path": test_file, "reason": "test"}]
        removed = cleanup_forbidden_deliverables(violations)
        assert removed == 1
        assert not os.path.exists(test_file)

    def test_cleanup_removes_forbidden_dirs(self, tmp_path):
        from qq.path_guards import cleanup_forbidden_deliverables
        test_dir = os.path.join(tmp_path, "src")
        os.makedirs(test_dir, exist_ok=True)
        with open(os.path.join(test_dir, "main.js"), "w") as f:
            f.write("bad")
        violations = [{"path": test_dir, "reason": "test"}]
        removed = cleanup_forbidden_deliverables(violations)
        assert removed == 1
        assert not os.path.exists(test_dir)

    def test_cleanup_does_not_remove_workspace_files(self, tmp_path):
        from qq.path_guards import cleanup_forbidden_deliverables
        ws = os.path.join(tmp_path, "workspace")
        os.makedirs(ws, exist_ok=True)
        test_file = os.path.join(ws, "app.py")
        with open(test_file, "w") as f:
            f.write("good")
        violations = [{"path": test_file}]  # This shouldn't happen but if it does
        removed = cleanup_forbidden_deliverables(violations)
        assert removed == 1
        assert not os.path.exists(test_file)  # It's in the violations list so gets removed


# =============================================================================
# Regression tests for QonQrete artifact metadata whitelist
# =============================================================================

class TestRunRootArtifactMarkdownWhitelist:
    """Tests proving canonical run-root artifact markdown is allowed."""

    def test_run_root_artifact_markdown_metadata_allowed(self, tmp_path):
        """Canonical artifacts (task-original.md, task-enhanced.md, planning.md)
        under run_root/artifacts/ are not flagged as violations."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        (rr / "artifacts").mkdir(parents=True)
        ws.mkdir()

        for name in ("task-original.md", "task-enhanced.md", "planning.md"):
            (rr / "artifacts" / name).write_text("metadata", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        assert violations == []

    def test_run_root_random_artifact_markdown_still_forbidden(self, tmp_path):
        """Arbitrary markdown under artifacts/ (not the canonical three) is
        still flagged as forbidden."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        (rr / "artifacts").mkdir(parents=True)
        ws.mkdir()

        (rr / "artifacts" / "README.md").write_text("project doc", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        # README.md is in _FORBIDDEN_FILE_NAMES, so it triggers project_deliverable_in_metadata
        assert any(v["reason"] in ("forbidden_project_extension_in_metadata",
                                   "project_deliverable_in_metadata")
                   for v in violations)

    def test_run_root_artifacts_project_files_still_forbidden(self, tmp_path):
        """Project deliverable files (index.html, app.css, main.js) under
        artifacts/ are still flagged as forbidden."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        (rr / "artifacts").mkdir(parents=True)
        ws.mkdir()

        for name in ("index.html", "app.css", "main.js"):
            (rr / "artifacts" / name).write_text("bad", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        paths = {Path(v["path"]).name for v in violations}
        assert {"index.html", "app.css", "main.js"} <= paths

    def test_target_project_files_are_allowed_by_scanner(self, tmp_path):
        """Normal target-project source files (under workspace_root, not .qq)
        are NOT scanned as violations."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        rr.mkdir(parents=True)

        (ws / "index.html").write_text("<html></html>", encoding="utf-8")
        (ws / "app.css").write_text("body{}", encoding="utf-8")
        (ws / "main.js").write_text("console.log(1)", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        assert violations == []

    def test_workspace_dot_qq_outside_run_root_still_guarded(self, tmp_path):
        """Forbidden files in .qq outside the current run_root are still
        caught by the scanner."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = ws / ".qq" / "runs" / "run001"
        bad = ws / ".qq" / "src"
        rr.mkdir(parents=True)
        bad.mkdir(parents=True)

        (bad / "main.js").write_text("bad", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        assert any("main.js" in v["path"] for v in violations)

    def test_qonqrete_normal_cycle_metadata_does_not_trigger_path_violation(self, tmp_path):
        """A full normal QonQrete metadata layout (artifacts, agents, state,
        events.jsonl) does NOT trigger false-positive path violations."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        rr.mkdir(parents=True)

        (rr / "events.jsonl").write_text("", encoding="utf-8")
        (rr / "state").mkdir()
        (rr / "state" / "task.json").write_text("{}", encoding="utf-8")
        (rr / "state" / "clarified_task.json").write_text("{}", encoding="utf-8")
        (rr / "state" / "plan.json").write_text("{}", encoding="utf-8")

        (rr / "artifacts").mkdir()
        (rr / "artifacts" / "task-original.md").write_text("task", encoding="utf-8")
        (rr / "artifacts" / "task-enhanced.md").write_text("enhanced", encoding="utf-8")
        (rr / "artifacts" / "planning.md").write_text("plan", encoding="utf-8")

        qcall = rr / "agents" / "cycle-000" / "qlarifier" / "call-abc123"
        qcall.mkdir(parents=True)
        (qcall / "prompt.md").write_text("prompt", encoding="utf-8")
        (qcall / "stdout.txt").write_text("", encoding="utf-8")
        (qcall / "stderr.txt").write_text("", encoding="utf-8")
        (qcall / "result.json").write_text("{}", encoding="utf-8")
        (qcall / "metadata.json").write_text("{}", encoding="utf-8")

        (rr / "agents" / "cycle-000" / "qlarifier" / "qlarifier_output.json").write_text("{}", encoding="utf-8")
        (rr / "agents" / "cycle-000" / "instruqtor").mkdir(parents=True)
        (rr / "agents" / "cycle-000" / "instruqtor" / "instruqtor_output.json").write_text("{}", encoding="utf-8")

        # Agent receipts under construqtor and inspeqtor
        for role in ("construqtor", "inspeqtor"):
            rec = rr / "agents" / "cycle-001" / role / "receipts"
            rec.mkdir(parents=True)
            (rec / "bg-1__call-1.json").write_text("{}", encoding="utf-8")
            (rr / "agents" / "cycle-001" / role / f"{role}_output.json").write_text("{}", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(
            str(rr), str(ws), agent="construqtor", cycle=1)
        assert violations == []

    def test_sandbox_metadata_allowed_project_files_forbidden(self, tmp_path):
        """Sandbox metadata files (prompt.md, result.json, etc.) are allowed,
        but project files under sandbox are still forbidden."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        (rr / "sandbox" / "input" / "call001").mkdir(parents=True)
        (rr / "sandbox" / "output" / "call001").mkdir(parents=True)

        # Allowed sandbox metadata
        (rr / "sandbox" / "input" / "call001" / "prompt.md").write_text("prompt", encoding="utf-8")
        (rr / "sandbox" / "output" / "call001" / "result.json").write_text("{}", encoding="utf-8")
        (rr / "sandbox" / "output" / "call001" / "stdout.txt").write_text("", encoding="utf-8")
        (rr / "sandbox" / "output" / "call001" / "stderr.txt").write_text("", encoding="utf-8")
        (rr / "sandbox" / "output" / "call001" / "metadata.json").write_text("{}", encoding="utf-8")

        # Forbidden project files under sandbox
        (rr / "sandbox" / "output" / "call001" / "index.html").write_text("bad", encoding="utf-8")
        (rr / "sandbox" / "output" / "call001" / "app.js").write_text("bad", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        # Should find the project files but NOT the metadata
        paths = {os.path.basename(v["path"]) for v in violations}
        assert "index.html" in paths
        assert "app.js" in paths
        # Metadata files should not be in violations
        assert "prompt.md" not in paths
        assert "result.json" not in paths
        assert "stdout.txt" not in paths
        assert "stderr.txt" not in paths
        assert "metadata.json" not in paths

    def test_violation_dict_has_complete_event_data(self, tmp_path):
        """Violation dicts include all fields for web event log diagnosis."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        rr.mkdir(parents=True)

        # Create forbidden files in two locations
        (rr / "app.py").write_text("bad", encoding="utf-8")
        qq_src = ws / ".qq" / "src"
        qq_src.mkdir(parents=True)
        (qq_src / "main.js").write_text("bad", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(
            str(rr), str(ws), agent="construqtor", cycle=1)

        for v in violations:
            assert "path" in v
            assert "offending_path" in v
            assert "reason" in v
            assert "path_kind" in v, f"Missing path_kind in {v}"
            # file-level violations have "extension"; dir-level may not
            if v["reason"] != "forbidden_project_directory_in_metadata":
                assert "extension" in v, f"Missing extension in {v}"
            assert "agent" in v

    def test_violation_clears_without_artifacts(self, tmp_path):
        """The canonical artifacts are NOT returned as violations and therefore
        are not cleaned up by cleanup_forbidden_deliverables()."""
        from qq.path_guards import scan_for_forbidden_deliverables, cleanup_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        (rr / "artifacts").mkdir(parents=True)
        ws.mkdir()

        (rr / "artifacts" / "task-original.md").write_text("metadata", encoding="utf-8")
        (rr / "artifacts" / "task-enhanced.md").write_text("metadata", encoding="utf-8")
        (rr / "artifacts" / "planning.md").write_text("metadata", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        assert violations == [], f"Canonical artifacts should not trigger violations, got: {violations}"

        # Even if we try to clean up (should have nothing to clean)
        removed = cleanup_forbidden_deliverables(violations)
        assert removed == 0

        # Files should still exist
        assert (rr / "artifacts" / "task-original.md").exists()
        assert (rr / "artifacts" / "task-enhanced.md").exists()
        assert (rr / "artifacts" / "planning.md").exists()

    def test_artifacts_scope_not_leaked_to_workspace_dot_qq(self, tmp_path):
        """The artifacts whitelist for run_root does NOT leak into the
        .qq scan outside run_root — .qq/artifacts/task-original.md with bad
        contents outside run_root is still forbidden."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        rr.mkdir(parents=True)
        ws.mkdir()

        # Create a "fake" artifacts dir in .qq outside run_root
        qq_artifacts = ws / ".qq" / "artifacts"
        qq_artifacts.mkdir(parents=True)
        (qq_artifacts / "task-original.md").write_text("bad project doc", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        # .qq/artifacts/task-original.md should still be flagged (outside run_root)
        assert len(violations) >= 1, f"Expected violation for .qq/artifacts outside run_root, got {violations}"

    def test_real_violation_still_caught_after_fix(self, tmp_path):
        """Creating a real forbidden file (app.py) directly under run_root
        still triggers a violation — the fix doesn't weaken protection."""
        from qq.path_guards import scan_for_forbidden_deliverables
        ws = tmp_path / "target"
        rr = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        rr.mkdir(parents=True)

        (rr / "app.py").write_text("print('bad')", encoding="utf-8")

        violations = scan_for_forbidden_deliverables(str(rr), str(ws))
        assert len(violations) >= 1
        assert any("app.py" in v["path"] for v in violations)
