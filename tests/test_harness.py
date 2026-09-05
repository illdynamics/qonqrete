"""Tests for harness plugin layer."""
import unittest
import sys
import os
import tempfile
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.harness import ShellHarness, HarnessContext


class TestShellHarness(unittest.TestCase):
    def test_passing_command(self):
        harness = ShellHarness(["echo hello"])
        ctx = HarnessContext(run_id="test", cycle=1,
                             repo_root="/tmp", run_root="/tmp/qq/runs/test")
        result = harness.run(ctx)
        self.assertTrue(result.passed)
        self.assertEqual(len(result.failures), 0)
        self.assertEqual(result.total_checks, 1)

    def test_failing_command(self):
        harness = ShellHarness(["exit 1"])
        ctx = HarnessContext(run_id="test", cycle=1,
                             repo_root="/tmp", run_root="/tmp/qq/runs/test")
        result = harness.run(ctx)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].exit_code, 1)

    def test_mixed_commands(self):
        harness = ShellHarness(["echo ok", "exit 2", "echo also ok"])
        ctx = HarnessContext(run_id="test", cycle=1,
                             repo_root="/tmp", run_root="/tmp/qq/runs/test")
        result = harness.run(ctx)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].exit_code, 2)
        self.assertEqual(result.total_checks, 3)

    def test_nonexistent_command(self):
        harness = ShellHarness(["nonexistent_command_xyz_123"])
        ctx = HarnessContext(run_id="test", cycle=1,
                             repo_root="/tmp", run_root="/tmp/qq/runs/test")
        result = harness.run(ctx)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failures), 1)

    def test_stdout_capture(self):
        harness = ShellHarness(["echo captured_output"])
        ctx = HarnessContext(run_id="test", cycle=1,
                             repo_root="/tmp", run_root="/tmp/qq/runs/test")
        result = harness.run(ctx)
        self.assertTrue(result.passed)
        self.assertEqual(result.total_checks, 1)


if __name__ == "__main__":
    unittest.main()
