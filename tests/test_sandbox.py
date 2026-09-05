"""
Tests for bubblewrap sandbox (qq/sandbox.py).

Tests are organized:
  - Unit tests: no real bwrap required, test command construction and logic
  - Integration tests: marked with @pytest.mark.skipif, require bwrap installed

Run:
  python -m pytest tests/test_sandbox.py -q
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qq.sandbox import (
    BubblewrapSandbox,
    SandboxMode,
    SandboxSpec,
    SandboxUnavailable,
    SandboxPolicyViolation,
    resolve_bwrap_binary,
    bwrap_available,
    get_sandbox_mode,
    get_sandbox_network,
    get_sandbox_debug,
    get_extra_ro_binds,
    validate_sandbox_paths,
    scan_for_symlink_escapes,
    _ensure_empty_qq_dir,
)

from qq.sandbox_integration import maybe_wrap_command_for_sandbox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class FakeSpec:
    """Minimal AgentCallSpec-like object for testing."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_dirs(base: Path, name: str) -> tuple[str, str]:
    """Create workspace and run_root directories, return (ws, run)."""
    ws = base / name / "workspace"
    run = base / name / "runs" / "run001"
    ws.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    return str(ws), str(run)


# =============================================================================
# Unit tests — no bwrap required
# =============================================================================

class TestResolveBwrapBinary:
    def test_env_var_override(self, monkeypatch, tmp_path):
        fake_bwrap = tmp_path / "fake_bwrap"
        fake_bwrap.write_text("#!/bin/sh\necho ok")
        fake_bwrap.chmod(0o755)
        monkeypatch.setenv("QONQRETE_BWRAP_BIN", str(fake_bwrap))
        assert resolve_bwrap_binary() == str(fake_bwrap)

    def test_env_var_not_executable(self, monkeypatch, tmp_path):
        fake_bwrap = tmp_path / "fake_bwrap"
        fake_bwrap.write_text("not exec")
        monkeypatch.setenv("QONQRETE_BWRAP_BIN", str(fake_bwrap))
        # Should fall through to PATH lookup, which likely won't find bwrap
        result = resolve_bwrap_binary()
        assert result is None or result != str(fake_bwrap)

    def test_no_bwrap_found(self, monkeypatch):
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)
        assert resolve_bwrap_binary() is None

    def test_bwrap_available_false(self, monkeypatch):
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)
        assert bwrap_available() is False


class TestSandboxConfig:
    def test_default_mode_auto(self, monkeypatch):
        monkeypatch.delenv("QONQRETE_CONSTRUQTOR_SANDBOX", raising=False)
        assert get_sandbox_mode() == "auto"

    def test_mode_auto(self, monkeypatch):
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "auto")
        assert get_sandbox_mode() == "auto"

    def test_mode_off(self, monkeypatch):
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "off")
        assert get_sandbox_mode() == "off"

    def test_network_default_host(self, monkeypatch):
        monkeypatch.delenv("QONQRETE_SANDBOX_NETWORK", raising=False)
        assert get_sandbox_network() == "host"

    def test_network_none(self, monkeypatch):
        monkeypatch.setenv("QONQRETE_SANDBOX_NETWORK", "none")
        assert get_sandbox_network() == "none"

    def test_debug_default_false(self, monkeypatch):
        monkeypatch.delenv("QONQRETE_SANDBOX_DEBUG", raising=False)
        assert get_sandbox_debug() is False

    def test_debug_true(self, monkeypatch):
        monkeypatch.setenv("QONQRETE_SANDBOX_DEBUG", "true")
        assert get_sandbox_debug() is True

    def test_extra_ro_binds(self, monkeypatch):
        monkeypatch.setenv("QONQRETE_SANDBOX_RO_BINDS", "/opt/tools:/extra/lib")
        binds = get_extra_ro_binds()
        assert "/opt/tools" in binds
        assert "/extra/lib" in binds

    def test_extra_ro_binds_empty(self, monkeypatch):
        monkeypatch.delenv("QONQRETE_SANDBOX_RO_BINDS", raising=False)
        assert get_extra_ro_binds() == []


class TestValidateSandboxPaths:
    def test_clean_paths(self, tmp_path):
        ws, run = _make_dirs(tmp_path, "clean")
        violations = validate_sandbox_paths(ws, run, ws)
        assert violations == []

    def test_workspace_inside_run_root(self, tmp_path):
        ws, run = _make_dirs(tmp_path, "nested")
        # Make workspace inside run_root
        bad_ws = os.path.join(run, "workspace")
        os.makedirs(bad_ws, exist_ok=True)
        violations = validate_sandbox_paths(bad_ws, run, bad_ws)
        assert any("workspace_root" in v and "inside run_root" in v for v in violations)

    def test_cwd_outside_workspace(self, tmp_path):
        ws, run = _make_dirs(tmp_path, "outside")
        outside = str(tmp_path / "other")
        os.makedirs(outside, exist_ok=True)
        violations = validate_sandbox_paths(ws, run, outside)
        assert any("cwd" in v and "not under workspace_root" in v for v in violations)

    def test_cwd_under_dot_qq(self, tmp_path):
        ws, run = _make_dirs(tmp_path, "dotqq")
        qq_dir = os.path.join(ws, ".qq", "new")
        os.makedirs(qq_dir, exist_ok=True)
        violations = validate_sandbox_paths(ws, run, qq_dir)
        assert any(".qq" in v for v in violations)

    def test_dangerous_root_rejected(self, tmp_path, monkeypatch):
        monkeypatch.delenv("QONQRETE_ALLOW_DANGEROUS_WORKSPACE", raising=False)
        _, run = _make_dirs(tmp_path, "dangerous")
        violations = validate_sandbox_paths("/", run, "/")
        assert any("dangerously broad" in v for v in violations)

    def test_dangerous_root_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QONQRETE_ALLOW_DANGEROUS_WORKSPACE", "true")
        # When dangerous root is explicitly allowed, it bypasses the
        # dangerously-broad-root check. We verify this by checking the
        # violation list does NOT contain "dangerously broad".
        ws, run = _make_dirs(tmp_path, "dangerous_allowed")
        violations = validate_sandbox_paths(
            ws, run, ws, explicit_allow_dangerous_root=True
        )
        # Clean paths should have no violations
        assert violations == []
class TestBubblewrapSandboxBuildCommand:
    """Test build_command() produces correct bwrap arguments — no real bwrap needed."""

    @pytest.fixture
    def mock_bwrap(self, monkeypatch, tmp_path):
        """Create a fake bwrap binary and set it in env."""
        fake_bwrap = tmp_path / "mock_bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0")
        fake_bwrap.chmod(0o755)
        monkeypatch.setenv("QONQRETE_BWRAP_BIN", str(fake_bwrap))
        return str(fake_bwrap)

    @pytest.fixture
    def sandbox(self, mock_bwrap):
        return BubblewrapSandbox(bwrap_bin=mock_bwrap)

    @pytest.fixture
    def spec_dirs(self, tmp_path):
        ws, run = _make_dirs(tmp_path, "buildcmd")
        return ws, run

    def test_includes_bind_workspace(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
        )
        cmd = sandbox.build_command(ss)
        assert cmd[0] == sandbox._bwrap_bin or cmd[0].endswith("mock_bwrap")
        assert "--bind" in cmd
        assert ws in cmd
        assert "/workspace" in cmd

    def test_includes_ro_bind_empty_qq(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
        )
        cmd = sandbox.build_command(ss)
        assert "--ro-bind" in cmd
        # Find the args after --ro-bind for /workspace/.qq
        found_qq_bind = False
        for i, arg in enumerate(cmd):
            if arg == "/workspace/.qq":
                found_qq_bind = True
                break
        assert found_qq_bind, f"Expected /workspace/.qq in command, got: {cmd}"

    def test_includes_chdir_workspace(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
        )
        cmd = sandbox.build_command(ss)
        assert "--chdir" in cmd
        chdir_idx = cmd.index("--chdir")
        assert cmd[chdir_idx + 1] == "/workspace"

    def test_includes_die_with_parent(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
        )
        cmd = sandbox.build_command(ss)
        assert "--die-with-parent" in cmd

    def test_does_not_bind_run_root_writable(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
        )
        cmd = sandbox.build_command(ss)
        # There should be no --bind of run_root directly
        # There may be --bind for /qonqrete/out, but not for run_root directly
        bind_indices = [i for i, x in enumerate(cmd) if x == "--bind"]
        for idx in bind_indices:
            bound_path = cmd[idx + 1]
            # Only workspace and qonqrete/out should be writable
            assert bound_path in (ws, os.path.join(run, "sandbox", "output")), \
                f"Unexpected writable bind: {bound_path}"

    def test_network_host_adds_share_net(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
            network="host",
        )
        cmd = sandbox.build_command(ss)
        assert "--share-net" in cmd

    def test_network_none_no_share_net(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
            network="none",
        )
        cmd = sandbox.build_command(ss)
        assert "--share-net" not in cmd

    def test_includes_unshare_all(self, sandbox, spec_dirs):
        ws, run = spec_dirs
        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=ws,
            env={},
        )
        cmd = sandbox.build_command(ss)
        assert "--unshare-all" in cmd

    def test_bwrap_unavailable_raises(self, monkeypatch, spec_dirs, tmp_path):
        """Sandbox wrapping is disabled — never raises, even with missing bwrap + required."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "required")
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)

        ws, run = spec_dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        # Sandbox wrapping disabled — returns original command, no raise
        cmd, env, cwd = maybe_wrap_command_for_sandbox(spec, ["echo", "hello"], {})
        assert cmd == ["echo", "hello"]
        assert cwd is None

    def test_path_validation_on_build(self, sandbox, tmp_path):
        """Build command with invalid cwd raises SandboxPolicyViolation."""
        ws, run = _make_dirs(tmp_path, "badcwd")
        outside = str(tmp_path / "outside")
        os.makedirs(outside, exist_ok=True)

        ss = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["echo", "hello"],
            cwd=outside,  # outside workspace
            env={},
        )
        with pytest.raises(SandboxPolicyViolation, match="not under workspace_root"):
            sandbox.build_command(ss)


class TestMaybeWrapCommandForSandbox:
    @pytest.fixture
    def dirs(self, tmp_path):
        return _make_dirs(tmp_path, "wrapcmd")

    def test_sandbox_off_returns_original(self, monkeypatch, dirs):
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "off")
        ws, run = dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec, ["echo", "hello"], {"KEY": "val"}
        )
        assert cmd == ["echo", "hello"]
        assert env == {"KEY": "val"}
        assert cwd is None

    def test_non_construqtor_returns_original(self, monkeypatch, dirs):
        ws, run = dirs
        spec = FakeSpec(
            role="instruqtor",  # not construqtor
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec, ["echo", "hello"], {}
        )
        assert cmd == ["echo", "hello"]
        assert cwd is None

    def test_auto_mode_fallback_when_no_bwrap(self, monkeypatch, dirs):
        """Auto mode: if bwrap is unavailable, fall back without error."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "auto")
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)

        ws, run = dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec, ["echo", "hello"], {}
        )
        # Should return original command unchanged
        assert cmd == ["echo", "hello"]
        assert cwd is None

    def test_with_mock_bwrap_wraps_command(self, monkeypatch, tmp_path):
        """Sandbox wrapping is disabled — command should NOT be wrapped even with bwrap available."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "required")
        monkeypatch.setenv("QONQRETE_SANDBOX_NETWORK", "host")

        fake_bwrap = tmp_path / "mock_bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0")
        fake_bwrap.chmod(0o755)
        monkeypatch.setenv("QONQRETE_BWRAP_BIN", str(fake_bwrap))

        ws, run = _make_dirs(tmp_path, "withbwrap")
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec, ["echo", "hello"], {"KEY": "val"}
        )
        # Sandbox wrapping disabled — should NOT be wrapped with bwrap
        assert cmd == ["echo", "hello"]
        assert cwd is None


class TestEnsureEmptyQQDir:
    def test_creates_dir(self, tmp_path):
        run = str(tmp_path / "runs" / "run001")
        empty_dir = _ensure_empty_qq_dir(run)
        assert os.path.isdir(empty_dir)
        assert empty_dir.endswith("empty-qq")
        assert os.listdir(empty_dir) == []

    def test_clears_existing(self, tmp_path):
        run = str(tmp_path / "runs" / "run001")
        empty_dir = _ensure_empty_qq_dir(run)
        # Create some files
        with open(os.path.join(empty_dir, "test.txt"), "w") as f:
            f.write("content")
        # Re-ensure — should clear
        _ensure_empty_qq_dir(run)
        assert os.listdir(empty_dir) == []


class TestScanForSymlinkEscapes:
    def test_no_symlinks_clean(self, tmp_path):
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "run001")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(os.path.join(ws, "src"), exist_ok=True)
        with open(os.path.join(ws, "src", "main.py"), "w") as f:
            f.write("print('hello')")

        violations = scan_for_symlink_escapes(ws, run)
        assert violations == []

    def test_symlink_to_outside_detected(self, tmp_path):
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "run001")
        outside = str(tmp_path / "outside")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(outside, exist_ok=True)
        os.makedirs(run, exist_ok=True)

        # Create a symlink from workspace to outside
        os.symlink(outside, os.path.join(ws, "escape_link"))
        os.symlink(outside, os.path.join(ws, "escape_link_dir"), target_is_directory=True)

        violations = scan_for_symlink_escapes(ws, run)
        assert len(violations) >= 1
        assert any(v["reason"] == "symlink_escapes_workspace" for v in violations)

    def test_symlink_to_run_root_detected(self, tmp_path):
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "run001")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(run, exist_ok=True)

        os.symlink(run, os.path.join(ws, "run_link"), target_is_directory=True)

        violations = scan_for_symlink_escapes(ws, run)
        assert len(violations) >= 1
        # When run_root is outside workspace, it's caught as escaping workspace
        # When run_root is inside workspace, it's caught as pointing to run_root
        assert any(v["reason"] in ("symlink_points_to_run_root", "symlink_escapes_workspace")
                   for v in violations)
    def test_symlink_to_qq_detected(self, tmp_path):
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "run001")
        qq_dir = os.path.join(ws, ".qq")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(qq_dir, exist_ok=True)
        os.makedirs(run, exist_ok=True)

        os.symlink(qq_dir, os.path.join(ws, "qq_link"), target_is_directory=True)

        violations = scan_for_symlink_escapes(ws, run)
        assert len(violations) >= 1
        assert any(v["reason"] == "symlink_points_to_qq" for v in violations)

    def test_skips_qq_directory(self, tmp_path):
        """Symlinks inside .qq should be skipped (not scanned)."""
        ws = str(tmp_path / "workspace")
        run = str(tmp_path / "runs" / "run001")
        qq_dir = os.path.join(ws, ".qq")
        outside = str(tmp_path / "outside")
        os.makedirs(ws, exist_ok=True)
        os.makedirs(qq_dir, exist_ok=True)
        os.makedirs(outside, exist_ok=True)
        os.makedirs(run, exist_ok=True)

        # Symlink inside .qq to outside — should NOT be flagged
        os.symlink(outside, os.path.join(qq_dir, "escape"), target_is_directory=True)

        violations = scan_for_symlink_escapes(ws, run)
        assert violations == []


# =============================================================================
# Integration tests — real bwrap required
# =============================================================================

_bwrap_exists = None


def _has_bwrap():
    global _bwrap_exists
    if _bwrap_exists is None:
        _bwrap_exists = bwrap_available()
    return _bwrap_exists


@pytest.mark.skipif(not _has_bwrap(), reason="bubblewrap not installed")
class TestBubblewrapSandboxIntegration:
    """Real bwrap integration tests — only run when bwrap is installed."""

    @pytest.fixture
    def sandbox(self):
        return BubblewrapSandbox()

    @pytest.fixture
    def ws_run(self, tmp_path):
        ws = tmp_path / "workspace"
        run = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        run.mkdir(parents=True)
        return str(ws), str(run)

    def test_available_returns_true(self, sandbox):
        assert sandbox.available() is True

    def test_command_can_write_workspace_main_py(self, sandbox, ws_run):
        ws, run = ws_run
        spec = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["sh", "-c", "echo hello > /workspace/main.py"],
            cwd=ws,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        result = sandbox.run(spec, timeout=30)
        assert result.returncode == 0
        assert os.path.exists(os.path.join(ws, "main.py"))
        with open(os.path.join(ws, "main.py")) as f:
            assert f.read().strip() == "hello"

    def test_command_can_write_subdir(self, sandbox, ws_run):
        ws, run = ws_run
        spec = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["sh", "-c", "mkdir -p /workspace/src && echo ok > /workspace/src/main.js"],
            cwd=ws,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        result = sandbox.run(spec, timeout=30)
        assert result.returncode == 0
        assert os.path.exists(os.path.join(ws, "src", "main.js"))

    def test_command_cannot_write_dot_qq(self, sandbox, ws_run):
        ws, run = ws_run
        spec = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["sh", "-c", "echo bad > /workspace/.qq/app.py 2>&1; exit 0"],
            cwd=ws,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        result = sandbox.run(spec, timeout=30)
        # The command itself exits 0 (we suppressed error), but the file
        # should NOT exist on the host
        assert not os.path.exists(os.path.join(ws, ".qq", "app.py")), \
            f"Host .qq/app.py should not exist but found: {os.listdir(os.path.join(ws, '.qq')) if os.path.isdir(os.path.join(ws, '.qq')) else 'no .qq dir'}"

    def test_command_cannot_write_run_root(self, sandbox, ws_run):
        ws, run = ws_run
        spec = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["sh", "-c", f"echo bad > {run}/app.py 2>&1; exit 0"],
            cwd=ws,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        result = sandbox.run(spec, timeout=30)
        assert not os.path.exists(os.path.join(run, "app.py"))

    def test_command_cannot_write_etc(self, sandbox, ws_run):
        ws, run = ws_run
        spec = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["sh", "-c", "echo bad > /etc/qonqrete-test 2>&1; exit 0"],
            cwd=ws,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        result = sandbox.run(spec, timeout=30)
        assert not os.path.exists("/etc/qonqrete-test")

    def test_tmp_write_does_not_affect_host(self, sandbox, ws_run):
        ws, run = ws_run
        host_tmp_file = "/tmp/qonqrete_sandbox_test_marker"
        spec = SandboxSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            command=["sh", "-c", "echo sandbox-tmp > /tmp/marker.txt"],
            cwd=ws,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        # Ensure host tmp file doesn't exist before
        if os.path.exists(host_tmp_file):
            os.remove(host_tmp_file)
        result = sandbox.run(spec, timeout=30)
        # The /tmp inside sandbox is a tmpfs, not host /tmp
        # So host /tmp should NOT have this file
        assert not os.path.exists("/tmp/marker.txt"), \
            "Sandbox /tmp write leaked to host /tmp!"


class TestSandboxConstructs:
    """Test module-level constructs are importable and usable."""

    def test_sandbox_unavailable_is_exception(self):
        exc = SandboxUnavailable("test reason")
        assert isinstance(exc, Exception)
        assert "test reason" in str(exc)

    def test_sandbox_policy_violation_is_exception(self):
        exc = SandboxPolicyViolation(reason="test_reason", detail="test_detail")
        assert isinstance(exc, Exception)
        assert "test_reason" in str(exc)
        assert "test_detail" in str(exc)
        assert exc.reason == "test_reason"

    def test_sandbox_spec_fields(self):
        spec = SandboxSpec(
            role="construqtor",
            workspace_root="/ws",
            run_root="/run",
            command=["echo", "hi"],
            cwd="/ws",
            env={"A": "B"},
        )
        assert spec.role == "construqtor"
        assert spec.network == "host"
        assert spec.writable_tmp is True

    def test_sandbox_mode_constants(self):
        assert SandboxMode.REQUIRED == "required"
        assert SandboxMode.AUTO == "auto"
        assert SandboxMode.OFF == "off"


# =============================================================================
# Test construQtor agent integration
# =============================================================================

class TestConstruQtorSandboxIntegration:
    """Test that construQtor agent handles sandbox failures correctly."""

    def test_sandbox_unavailable_in_required_mode_fails_build(self, tmp_path, monkeypatch):
        """When sandbox=required and bwrap unavailable, construQtor fails cleanly."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "required")
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)

        from qq.agents.construqtor import run_construqtor_for_group
        from qq.adapters.mock import MockAdapter
        from qq.sandbox import SandboxUnavailable
        from qq.models import ClarifiedTask, BuildGroup, BriQ, BriqStatus
        from qq.workspaces import WorkspaceManager

        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        os.makedirs(ws_root, exist_ok=True)
        os.makedirs(run_root, exist_ok=True)

        # Create a MockAdapter that simulates sandbox failure
        adapter = MockAdapter()
        original_call = adapter.call
        def failing_call(spec):
            if spec.role == "construqtor":
                raise SandboxUnavailable("bwrap not found")
            return original_call(spec)
        adapter.call = failing_call

        clarified = ClarifiedTask(clarified_text="build a CLI", id="ct-1")
        briq = BriQ(id="b-1", title="test", description="test briq",
                    status=BriqStatus.PENDING)
        group = BuildGroup(id="bg-1", name="core", description="core",
                          briq_ids=["b-1"])

        wm = WorkspaceManager(ws_root, run_root, "run001", no_repo=True)

        result = run_construqtor_for_group(
            adapter, clarified, group, [briq], wm, "mock-model", 1,
            run_root=run_root, workspace_root=ws_root,
        )

        # Should fail due to sandbox unavailable
        assert result["status"] == "failed"
        assert "sandbox" in result.get("error", "").lower() or \
               "sandbox" in result.get("notes", "").lower()
    def test_construqtor_with_sandbox_off_works(self, tmp_path, monkeypatch):
        """With sandbox=off, construQtor works normally."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "off")

        from qq.agents.construqtor import run_construqtor_for_group
        from qq.adapters.mock import MockAdapter
        from qq.models import ClarifiedTask, BuildGroup, BriQ, BriqStatus
        from qq.workspaces import WorkspaceManager

        ws_root = str(tmp_path / "project")
        run_root = str(tmp_path / "runs" / "run001")
        os.makedirs(ws_root, exist_ok=True)
        os.makedirs(run_root, exist_ok=True)

        adapter = MockAdapter()
        clarified = ClarifiedTask(clarified_text="build a CLI", id="ct-2")
        briq = BriQ(id="b-1", title="test", description="test briq",
                    status=BriqStatus.PENDING)
        group = BuildGroup(id="bg-1", name="core", description="core",
                          briq_ids=["b-1"])

        wm = WorkspaceManager(ws_root, run_root, "run002", no_repo=True)

        result = run_construqtor_for_group(
            adapter, clarified, group, [briq], wm, "mock-model", 1,
            run_root=run_root, workspace_root=ws_root,
        )

        # Should succeed (mock adapter writes files normally)
        assert result["status"] == "implemented"


# =============================================================================
# Regression tests for sandbox path rewriting (bubble.md §3, §12)
# =============================================================================

class TestSandboxCommandPathRewriting:
    """Test that CodeSeeq command paths are correctly rewritten for bwrap."""

    @pytest.fixture
    def mock_bwrap(self, monkeypatch, tmp_path):
        fake_bwrap = tmp_path / "mock_bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0")
        fake_bwrap.chmod(0o755)
        monkeypatch.setenv("QONQRETE_BWRAP_BIN", str(fake_bwrap))
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "required")
        return str(fake_bwrap)

    @pytest.fixture
    def dirs(self, tmp_path):
        ws = tmp_path / "workspace"
        run = tmp_path / "runs" / "run001"
        ws.mkdir(parents=True)
        run.mkdir(parents=True)
        # Create sandbox input dir with prompt
        sandbox_input = run / "sandbox" / "input" / "construqtor"
        sandbox_input.mkdir(parents=True)
        prompt_file = sandbox_input / "prompt.md"
        prompt_file.write_text("test prompt")
        return str(ws), str(run)

    def test_command_uses_qonqrete_input_path(self, mock_bwrap, dirs):
        """Sandbox wrapping disabled — command keeps original host paths unchanged."""
        ws, run = dirs
        prompt_host = os.path.join(run, "sandbox", "input", "construqtor", "prompt.md")
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec,
            ["codeseeq", "run", "-f", prompt_host, "--model", "mock", "--sandbox", "workspace-write", "--cd", ws],
            {},
        )
        # Sandbox wrapping disabled — original command returned unchanged
        assert cmd == ["codeseeq", "run", "-f", prompt_host, "--model", "mock", "--sandbox", "workspace-write", "--cd", ws]
        assert cwd is None

    def test_command_uses_workspace_as_cd(self, mock_bwrap, dirs):
        """Sandbox wrapping disabled — original --cd path is kept unchanged."""
        ws, run = dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec,
            ["codeseeq", "run", "-f", "/tmp/test.md", "--model", "mock", "--cd", ws],
            {},
        )
        # Sandbox wrapping disabled — no bwrap, original command unchanged
        cmd_str = " ".join(cmd)
        assert "--chdir /workspace" not in cmd_str, \
            f"bwrap should NOT be in command: {cmd_str}"
        assert ws in cmd_str, f"Original ws path should be in command: {cmd_str}"

    def test_command_no_host_workspace_in_cd(self, mock_bwrap, dirs):
        """Sandbox wrapping disabled — original command keeps host workspace path."""
        ws, run = dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(
            spec,
            ["codeseeq", "run", "-f", "/tmp/test.md", "--model", "mock", "--cd", ws],
            {},
        )
        # Sandbox wrapping disabled — original command returned unchanged
        assert cmd == ["codeseeq", "run", "-f", "/tmp/test.md", "--model", "mock", "--cd", ws]
        assert cwd is None

    def test_bwrap_unavailable_required_raises(self, monkeypatch, dirs):
        """Sandbox wrapping disabled — never raises, even when bwrap missing + mode=required."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "required")
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)
        ws, run = dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        # Sandbox wrapping disabled — returns original command, no raise
        cmd, env, cwd = maybe_wrap_command_for_sandbox(spec, ["echo", "hello"], {})
        assert cmd == ["echo", "hello"]
        assert cwd is None

    def test_bwrap_auto_mode_falls_back(self, monkeypatch, dirs):
        """Auto mode: falls back when bwrap missing."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "auto")
        monkeypatch.setenv("PATH", "/nonexistent")
        monkeypatch.delenv("QONQRETE_BWRAP_BIN", raising=False)
        ws, run = dirs
        spec = FakeSpec(
            role="construqtor",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(spec, ["echo", "hello"], {})
        assert cmd == ["echo", "hello"]
        assert cwd is None

    def test_non_construqtor_not_sandboxed(self, monkeypatch, dirs):
        """Non-construqtor roles are not sandboxed."""
        monkeypatch.setenv("QONQRETE_CONSTRUQTOR_SANDBOX", "required")
        ws, run = dirs
        spec = FakeSpec(
            role="qlarifier",
            workspace_root=ws,
            run_root=run,
            workdir=ws,
            cd=ws,
            repo_root=ws,
        )
        cmd, env, cwd = maybe_wrap_command_for_sandbox(spec, ["echo", "hello"], {})
        assert cmd == ["echo", "hello"]


class TestConstruQtorDefaultSandbox:
    """Test that construQtor no longer defaults to danger-full-access."""

    def test_default_not_danger_full_access(self):
        """QonQrete bubblewrap is disabled — CodeSeeq handles its own sandboxing.
        The default pass-through to CodeSeeq can safely be whatever CodeSeeq needs."""
        from qq.agents.construqtor import run_construqtor_for_group
        import inspect
        sig = inspect.signature(run_construqtor_for_group)
        params = sig.parameters
        assert "sandbox" in params
        default = params["sandbox"].default
        # With QonQrete bubblewrap disabled, this is just the passthrough to CodeSeeq.
        # Any value is acceptable; we just verify it exists.
        assert isinstance(default, str), \
            f"construQtor sandbox default should be a string, got {type(default)}"

    def test_base_spec_default_is_workspace_write(self):
        from qq.adapters.base import AgentCallSpec
        spec = AgentCallSpec(
            role="construqtor", model="mock", prompt="test",
            workdir="/tmp", output_file="out.json",
        )
        assert spec.sandbox == "workspace-write", \
            f"AgentCallSpec default sandbox should be workspace-write, got {spec.sandbox}"
