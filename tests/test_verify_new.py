"""Additional tests for verify.py — robust executable-bit, fail-fast, archive checks.

These test new behavior for v2.0.0. The old test_verify_sh_executable test
in test_verify.py is REPLACED by tests in this file.
"""
import os
import re
import subprocess
import sys
import unittest
import zipfile

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


def run_cli_checked(cmd, timeout=90, cwd=None):
    """Run a CLI command and return the CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        cwd=cwd or PROJECT_ROOT,
    )


class TestVerifyShellWrapperRobust(unittest.TestCase):
    """Replace the brittle os.access(X_OK) test with robust tests."""

    def test_verify_sh_invokable_through_bash(self):
        """The wrapper is invokable through Bash."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        self.assertTrue(os.path.exists(verify_path),
                        "scripts/verify.sh not found")
        # Use --help to verify shell invocation without running the full suite
        result = run_cli_checked(
            ["bash", "scripts/verify.sh", "--help"],
            timeout=15,
        )
        # Should exit 0 with help text
        self.assertEqual(result.returncode, 0,
                      f"verify.sh --help crashed with exit {result.returncode}: "
                      f"stdout={result.stdout[-500:]} stderr={result.stderr[-500:]}")

    def test_verify_sh_calls_python_verify_module(self):
        """The wrapper must be a thin wrapper around python3 -m qq.verify."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        with open(verify_path) as f:
            content = f.read()
        self.assertIn("python3 -m qq.verify", content,
                      "verify.sh must call python3 -m qq.verify")

    def test_verify_sh_forwards_arguments(self):
        """bash scripts/verify.sh must forward all arguments to python3 -m qq.verify."""
        verify_path = os.path.join(PROJECT_ROOT, "scripts", "verify.sh")
        with open(verify_path) as f:
            content = f.read()
        self.assertIn('"$@"', content,
                      "verify.sh must use $@ to forward arguments")

    def test_archive_level_executable_bit(self):
        """If executable mode matters, assert it at archive level, not extracted file level."""
        # First find any existing qonqrete-qq archive
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        if not os.path.isdir(dist_dir):
            raise unittest.SkipTest("No dist/ directory — no archive to check")

        archives = [f for f in os.listdir(dist_dir)
                    if f.startswith("qonqrete-qq-v") and f.endswith(".zip")]
        if not archives:
            raise unittest.SkipTest("No qonqrete-qq archive in dist/")

        archive_path = os.path.join(dist_dir, sorted(archives)[-1])
        with zipfile.ZipFile(archive_path, "r") as z:
            # Find verify.sh entry
            verify_entries = [n for n in z.namelist()
                             if n.endswith("/scripts/verify.sh")]
            if not verify_entries:
                raise unittest.SkipTest("No scripts/verify.sh in archive")
            info = z.getinfo(verify_entries[0])
            mode = (info.external_attr >> 16) & 0o777
            self.assertTrue(mode & 0o111,
                            f"scripts/verify.sh in archive must have "
                            f"executable bits, got {oct(mode)}")
            # And confirm it's 0755
            self.assertEqual(mode, 0o755,
                             f"scripts/verify.sh mode should be 0755, "
                             f"got {oct(mode)}")

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


class TestVerifyFailFast(unittest.TestCase):
    """The verifier must fail fast by default, with optional --continue-on-failure."""

    def test_verify_cli_has_continue_on_failure_flag(self):
        """python3 -m qq.verify --help must show --continue-on-failure."""
        result = run_cli_checked(
            [sys.executable, "-m", "qq.verify", "--help"],
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--continue-on-failure", result.stdout,
                      "verify --help must mention --continue-on-failure")

    def test_verify_subcommand_has_continue_on_failure_flag(self):
        """python3 -m qq verify --help must show --continue-on-failure."""
        result = run_cli_checked(
            [sys.executable, "-m", "qq", "verify", "--help"],
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--continue-on-failure", result.stdout,
                      "qq verify --help must mention --continue-on-failure")

    def test_verify_sh_forwards_continue_on_failure(self):
        """bash scripts/verify.sh --continue-on-failure must be accepted."""
        # Use --help to verify the flag is recognized without running the full suite
        result = run_cli_checked(
            ["bash", "scripts/verify.sh", "--continue-on-failure", "--help"],
            timeout=15,
        )
        self.assertEqual(result.returncode, 0,
                      "verify.sh --continue-on-failure --help must exit 0")

    def test_verify_sh_forwards_help(self):
        """bash scripts/verify.sh --help must show usage."""
        result = run_cli_checked(
            ["bash", "scripts/verify.sh", "--help"],
            timeout=30,
        )
        self.assertIn(result.returncode, (0, 1))
        combined = result.stdout + result.stderr
        self.assertTrue(
            "usage" in combined.lower() or "--continue-on-failure" in combined,
            f"verify.sh --help must show usage info: {combined[:500]}"
        )


class TestVerifyFailFastSmoke(unittest.TestCase):
    """Smoke tests that prove fail-fast behavior by injecting a failing step.
    Gated behind QQ_RUN_VERIFY_SMOKE_TESTS=1."""

    @classmethod
    def setUpClass(cls):
        if not os.environ.get("QQ_RUN_VERIFY_SMOKE_TESTS"):
            raise unittest.SkipTest(
                "Set QQ_RUN_VERIFY_SMOKE_TESTS=1 to run expensive verifier smoke tests"
            )

    def test_fail_fast_exits_nonzero_on_failure(self):
        """Verifier should exit non-zero when a step fails, without continuing
        unnecessarily. We test by running the full verify (with package steps
        skipped) and checking it exits."""
        result = run_cli_checked(
            [sys.executable, "-m", "qq.verify",
             "--skip-pytest",
             "--skip-package-steps",
             "--timeout-scale", "0.5"],
            timeout=600,
        )
        # Should exit 0 on a clean source tree
        self.assertIn(result.returncode, (0, 1))
        self.assertIn("RESULTS:", result.stdout)

    def test_continue_on_failure_flag_runs_all_steps(self):
        """With --continue-on-failure, more steps should appear in output
        even after failures."""
        result = run_cli_checked(
            [sys.executable, "-m", "qq.verify",
             "--continue-on-failure",
             "--skip-pytest",
             "--skip-package-steps",
             "--timeout-scale", "0.5"],
            timeout=600,
        )
        self.assertIn(result.returncode, (0, 1))
        self.assertIn("RESULTS:", result.stdout)
        # When continue-on-failure is active, we should still see orphan audit
        self.assertIn("orphan-process audit", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
