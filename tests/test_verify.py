"""Tests for the Python verification runner (qq.verify).

These tests validate the verifier's CLI, command list, timeout handling,
and that scripts/verify.sh is a thin wrapper. The full verifier is NOT
run during unit tests — it is too expensive.
"""
import os
import re
import subprocess
import sys
import time
import unittest
import uuid

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


class TestVerifyCLI(unittest.TestCase):
    """Test the verifier's CLI entrypoints."""

    def test_verify_help_module(self):
        """python3 -m qq.verify --help should work."""
        result = subprocess.run(
            [sys.executable, "-m", "qq.verify", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0,
                         f"qq.verify --help failed: {result.stderr}")
        self.assertIn("usage:", result.stdout.lower())

    def test_verify_help_subcommand(self):
        """python3 -m qq verify --help should work."""
        result = subprocess.run(
            [sys.executable, "-m", "qq", "verify", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0,
                         f"qq verify --help failed: {result.stderr}")
        self.assertIn("usage:", result.stdout.lower())

    def test_verify_help_both_identical(self):
        """Both entry points should produce equivalent help."""
        r1 = subprocess.run(
            [sys.executable, "-m", "qq.verify", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        r2 = subprocess.run(
            [sys.executable, "-m", "qq", "verify", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        # Both should succeed
        self.assertEqual(r1.returncode, 0)
        self.assertEqual(r2.returncode, 0)
        # Both should mention key options (--root, --timeout-scale)
        self.assertIn("acceptance", r1.stdout)
        self.assertIn("--root", r2.stdout)
        self.assertIn("--timeout-scale", r2.stdout)


class TestVerifyArchiveName(unittest.TestCase):
    """The verifier must expose the current archive name."""

    def test_get_archive_name_current(self):
        """qq.verify.get_archive_name() should use qq.__version__."""
        from qq.verify import get_archive_name
        from qq import __version__
        name = get_archive_name()
        expected = f"dist/qonqrete-qq-v{__version__}.zip"
        self.assertEqual(name, expected)

    def test_get_archive_name_matches_version(self):
        """Archive name must contain the current version."""
        from qq.verify import get_archive_name
        from qq import __version__
        name = get_archive_name()
        self.assertIn(__version__, name)
        self.assertTrue(name.endswith(".zip"))


class TestVerifyTimeoutHandling(unittest.TestCase):
    """The verifier's subprocess runner must handle timeouts without hanging."""

    def test_run_subprocess_timeout_returns_runtime_error(self):
        """run_subprocess with a short timeout on a sleeping process must
        raise RuntimeError, not hang."""
        from qq.process import run_subprocess

        start = time.time()
        with self.assertRaises(RuntimeError) as ctx:
            run_subprocess(
                [sys.executable, "-c", "import time; time.sleep(300)"],
                timeout=2,
                label="timeout-test",
            )
        elapsed = time.time() - start

        self.assertLess(elapsed, 30,
                        f"Timeout handling took {elapsed:.1f}s — should be < 30s")
        self.assertIn("timed out", str(ctx.exception).lower())

    def test_run_subprocess_timeout_cleanup_no_orphans(self):
        """After a timeout, no orphan process should remain."""
        from qq.process import run_subprocess
        marker = f"verify_timeout_test_{uuid.uuid4().hex[:8]}"

        with self.assertRaises(RuntimeError):
            run_subprocess(
                [sys.executable, "-c",
                 f"import sys, time; print('MARKER={marker}', flush=True); time.sleep(300)"],
                timeout=1,
                label="orphan-test",
            )

        time.sleep(1)
        result = subprocess.run(
            ["ps", "-eo", "args"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotIn(marker, result.stdout,
                         f"Orphan process with marker '{marker}' still alive after timeout!")


class TestVerifyShellWrapper(unittest.TestCase):
    """scripts/verify.sh must be a thin wrapper calling python3 -m qq.verify."""

    def test_verify_sh_calls_python_verify(self):
        """scripts/verify.sh must invoke python3 -m qq.verify."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        self.assertTrue(os.path.exists(verify_path),
                        "scripts/verify.sh not found")

        with open(verify_path) as f:
            content = f.read()

        self.assertIn("python3 -m qq.verify", content,
                      "verify.sh must call python3 -m qq.verify")

    def test_verify_sh_no_run_with_timeout(self):
        """scripts/verify.sh must NOT contain the old run_with_timeout shell function."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        with open(verify_path) as f:
            content = f.read()

        self.assertNotIn("run_with_timeout", content,
                         "verify.sh must not contain the old run_with_timeout() shell function")

    def test_verify_sh_no_kill_descendants(self):
        """scripts/verify.sh must NOT contain the old _kill_descendants helpers."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        with open(verify_path) as f:
            content = f.read()

        self.assertNotIn("_kill_descendants", content,
                         "verify.sh must not contain old _kill_descendants helpers")

    def test_verify_sh_no_setsid(self):
        """scripts/verify.sh must NOT use setsid for process management."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        with open(verify_path) as f:
            content = f.read()

        self.assertNotIn("setsid", content,
                         "verify.sh must not use setsid")

    def test_verify_sh_executable(self):
        """scripts/verify.sh must be executable."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        self.assertTrue(os.access(verify_path, os.X_OK),
                        "scripts/verify.sh must be executable")


class TestVerifyCommandList(unittest.TestCase):
    """The verifier's command list must include all required acceptance checks."""

    def test_verify_step_labels_include_all_required_checks(self):
        """The CHECK_STEPS and dependent steps must cover all acceptance criteria."""
        from qq.verify import CHECK_STEPS

        labels = {step[0] for step in CHECK_STEPS}

        required = {
            "compileall",
            "unittest discover",
            "pytest",
            "providers --json",
            "doctor --offline",
        }

        for req in required:
            self.assertIn(req, labels,
                          f"Required check '{req}' not in CHECK_STEPS")

    def test_verify_has_dry_run_steps(self):
        """The verifier must include dry-run and streaming dry-run steps."""
        from qq.verify import _build_dry_run_step, _build_streaming_step

        dry = _build_dry_run_step()
        self.assertEqual(dry[0], "dry-run")
        self.assertIn("examples/example_task.md", " ".join(dry[2]))
        self.assertIn("--dry-run", dry[2])

        stream = _build_streaming_step()
        self.assertEqual(stream[0], "streaming dry-run")
        self.assertIn("--stream-agent-output", stream[2])

    def test_verify_has_package_steps(self):
        """The verifier must include package check, final, check-archive, and check-uploaded-zip."""
        from qq.verify import _PACKAGE_DEPENDENT_STEPS

        labels = {builder()[0] for builder in _PACKAGE_DEPENDENT_STEPS}

        required = {
            "package --check",
            "package --final",
            "package --check-archive",
            "package --check-uploaded-zip",
        }

        for req in required:
            self.assertIn(req, labels,
                          f"Required package step '{req}' not in _PACKAGE_DEPENDENT_STEPS")

    def test_package_step_archive_paths_use_current_version(self):
        """Package-dependent steps must reference the current version archive."""
        from qq.verify import _build_check_archive_step, _build_check_uploaded_zip_step
        from qq import __version__

        for builder in [_build_check_archive_step, _build_check_uploaded_zip_step]:
            label, timeout, cmd = builder()
            archive = cmd[-1]
            self.assertIn(__version__, archive,
                          f"{label} archive path '{archive}' missing version {__version__}")


class TestVerifySmoke(unittest.TestCase):
    """Lightweight smoke tests that actually invoke the verifier.

    These tests are expensive (~5 min each) and gated behind
    QQ_RUN_VERIFY_SMOKE_TESTS=1 so the default suite stays fast.
    """

    @classmethod
    def setUpClass(cls):
        if not os.environ.get("QQ_RUN_VERIFY_SMOKE_TESTS"):
            raise unittest.SkipTest(
                "Set QQ_RUN_VERIFY_SMOKE_TESTS=1 to run expensive verifier smoke tests"
            )

    def test_verify_skip_all_fast_exit_zero(self):
        """python3 -m qq.verify --skip-pytest --skip-package-steps --timeout-scale 0.5
        must exit 0 within a finite timeout."""
        result = subprocess.run(
            [sys.executable, "-m", "qq.verify",
             "--skip-pytest",
             "--skip-package-steps",
             "--timeout-scale", "0.5"],
            capture_output=True, text=True,
            timeout=600,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(result.returncode, 0,
                         f"verify smoke failed: stdout={result.stdout[-500:]} stderr={result.stderr[-500:]}")
        self.assertIn("PASS:", result.stdout)
        self.assertIn("RESULTS:", result.stdout)

    def test_verify_smoke_pytest_command_uses_no_capture(self):
        """Verifier must use pytest -s (--capture=no) to avoid nested capture hangs."""
        from qq.verify import CHECK_STEPS
        for label, timeout, cmd in CHECK_STEPS:
            if label == "pytest":
                self.assertIn("-s", cmd,
                              "Verifier pytest step must use -s flag")
                break
        else:
            self.fail("pytest step not found in CHECK_STEPS")

    def test_verify_sh_skip_all_fast_exit_zero(self):
        """bash scripts/verify.sh --skip-pytest --skip-package-steps --timeout-scale 0.5
        must exit 0 within a finite timeout."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        result = subprocess.run(
            ["bash", verify_path,
             "--skip-pytest",
             "--skip-package-steps",
             "--timeout-scale", "0.5"],
            capture_output=True, text=True,
            timeout=600,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(result.returncode, 0,
                         f"verify.sh smoke failed: stdout={result.stdout[-500:]} stderr={result.stderr[-500:]}")
        self.assertIn("PASS:", result.stdout)
        self.assertIn("RESULTS:", result.stdout)


if __name__ == "__main__":
    unittest.main()

    unittest.main()
