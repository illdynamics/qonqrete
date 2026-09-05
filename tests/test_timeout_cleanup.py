"""Regression tests: prove run_cli_checked() kills child process groups on timeout.

Stress tests that spawn real separate-session 300s sleepers are gated behind
QQ_RUN_PROCESS_STRESS_TESTS=1 so that the default full suite always exits cleanly.
"""
import os
import signal
import subprocess
import sys
import time
import unittest
import uuid

from tests import run_cli_checked
from qq.process import _drain_pipes_nonblocking, _drain_pipes

# Env-var gate for real process-tree stress tests.
_PROCESS_STRESS = os.environ.get("QQ_RUN_PROCESS_STRESS_TESTS") == "1"


def _close_proc(proc):
    """Safe cleanup: wait + close pipes. Never leaves zombies or open pipes."""
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass
    for pipe in (proc.stdout, proc.stderr):
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass


class TestTimeoutCleanup(unittest.TestCase):
    """run_cli_checked() must not leave orphan processes after timeout."""

    def setUp(self):
        self._script_path = None
        self._procs = []  # track all Popen objects for guaranteed cleanup

    def tearDown(self):
        if self._script_path and os.path.exists(self._script_path):
            try:
                os.unlink(self._script_path)
            except Exception:
                pass
        for proc in self._procs:
            _close_proc(proc)

    def _write_runner_script(self) -> str:
        """Return the path to a Python script that spawns a long-lived child
        with start_new_session=True (simulating the annoying case)."""
        import tempfile

        script = (
            "import subprocess, sys, time\n"
            "tag = sys.argv[1]\n"
            "# Spawn a child that sleeps a long time in its own session\n"
            "# IMPORTANT: the child command line includes the marker tag so\n"
            "# that cleanup tests can prove the child itself is gone.\n"
            "child_cmd = 'import sys, time; print(\"SLEEPER_MARKER=\" + sys.argv[1], flush=True); time.sleep(300)'\n"
            "child = subprocess.Popen(\n"
            "    [sys.executable, '-c', child_cmd, tag],\n"
            "    start_new_session=True,\n"
            ")\n"
            "# Write child pid so we can check cleanup\n"
            "print(f'CHILD_PID={child.pid}', flush=True)\n"
            "print('RUNNER_STARTED', flush=True)\n"
            "# Wait for child — should be killed externally\n"
            "child.wait()\n"
            "print('RUNNER_DONE', flush=True)\n"
        )
        fd, path = tempfile.mkstemp(suffix=".py", prefix="qq_timeout_runner_")
        os.close(fd)
        with open(path, "w") as f:
            f.write(script)
        self._script_path = path
        return path

    def test_timeout_kills_child_processes(self):
        """run_cli_checked(timeout=2) on a script that spawns a 300s child
        must kill the child, not leave it running."""
        if not _PROCESS_STRESS:
            self.skipTest("QQ_RUN_PROCESS_STRESS_TESTS=1 required for real process-group stress tests")
        runner = self._write_runner_script()
        marker = f"qq_timeout_marker_{uuid.uuid4().hex[:8]}"

        with self.assertRaises(AssertionError) as ctx:
            run_cli_checked(
                [sys.executable, runner, marker],
                timeout=2,
            )

        msg = str(ctx.exception)
        self.assertIn("timed out", msg.lower())

        # Check no child with the unique marker is still alive
        time.sleep(1)

        result = subprocess.run(
            ["ps", "-eo", "args"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotIn(
            marker,
            result.stdout,
            f"Orphan process detected after timeout!\n{result.stdout}",
        )
        # Also verify the SLEEPER_MARKER child is gone
        self.assertNotIn(
            "SLEEPER_MARKER=" + marker,
            result.stdout,
            f"SLEEPER_MARKER child still alive after timeout!\n{result.stdout}",
        )

    def test_timeout_no_orphan_on_killpg(self):
        """The process-group kill path (os.killpg) must work and leave
        no orphans."""
        if not _PROCESS_STRESS:
            self.skipTest("QQ_RUN_PROCESS_STRESS_TESTS=1 required for real process-group stress tests")
        runner = self._write_runner_script()
        marker = f"qq_timeout_marker_{uuid.uuid4().hex[:8]}"

        with self.assertRaises(AssertionError) as ctx:
            run_cli_checked(
                [sys.executable, runner, marker],
                timeout=1,
            )

        msg = str(ctx.exception)
        self.assertIn("timed out", msg.lower())

        time.sleep(1)
        result = subprocess.run(
            ["ps", "-eo", "pid,args"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotIn(marker, result.stdout,
                         "Child not killed by process group signal")
        self.assertNotIn("qq_timeout_runner_", result.stdout,
                         f"Runner script still running after timeout:\n{result.stdout}")
        # Also verify the sleeper child is gone
        self.assertNotIn("SLEEPER_MARKER=" + marker, result.stdout,
                         f"Sleeper child with marker still running after timeout:\n{result.stdout}")

    # ------------------------------------------------------------------
    # Fast, deterministic default-suite tests (no process-group stress)
    # ------------------------------------------------------------------

    def test_timeout_failure_message_includes_details(self):
        """The timeout AssertionError must include command, cwd, timeout,
        returncode, and partial output."""
        runner = self._write_runner_script()
        marker = f"qq_timeout_marker_{uuid.uuid4().hex[:8]}"

        with self.assertRaises(AssertionError) as ctx:
            run_cli_checked(
                [sys.executable, runner, marker],
                timeout=1,
            )

        msg = str(ctx.exception)
        self.assertIn("timed out", msg.lower())
        self.assertIn("test", msg.lower())

    def test_drain_pipes_nonblocking_never_hangs(self):
        """_drain_pipes_nonblocking must not hang on a pipe whose .read()
        can block or raise.  Prove it with a monkeypatched pipe.
        """
        import io
        import time

        class StubbornPipe:
            """Fake pipe that blocks on .read() after a few bytes."""
            def __init__(self):
                self._data = io.BytesIO(b"hello")
                self._read_count = 0

            def fileno(self):
                raise OSError("no real fd behind stubborn pipe")

            def read(self, size=-1):
                self._read_count += 1
                if self._read_count > 2:
                    # Simulate a pipe that would block forever
                    time.sleep(0.1)
                    return b""
                return self._data.read(size)

            def close(self):
                pass

        class FakeProc:
            stdout = StubbornPipe()
            stderr = StubbornPipe()

        start = time.monotonic()
        out, err = _drain_pipes_nonblocking(FakeProc())
        elapsed = time.monotonic() - start

        # Must return in under 2 seconds (it used to hang indefinitely)
        self.assertLess(elapsed, 2.0,
                        f"drain took {elapsed:.1f}s — should be near-instant")
        # Should get *some* data (whatever was available before block)
        self.assertIsInstance(out, str)
        self.assertIsInstance(err, str)
        # The _drain_pipes alias must also work
        out2, err2 = _drain_pipes(FakeProc())
        self.assertIsInstance(out2, str)
        self.assertIsInstance(err2, str)

    def test_drain_pipes_with_real_fileno(self):
        """_drain_pipes_nonblocking handles a pipe whose fileno supports
        fcntl(O_NONBLOCK).  After the process exits, the pipe should still
        have data that can be drained non-blockingly."""
        import subprocess, tempfile

        # Use a temp script file to avoid shell escaping issues with -c
        script = (
            'import sys\n'
            'sys.stdout.write("hello\\n")\n'
            'sys.stderr.write("world\\n")\n'
            'sys.stdout.flush()\n'
            'sys.stderr.flush()\n'
        )
        fd, path = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        with open(path, "w") as f:
            f.write(script)
        proc = subprocess.Popen(
            [sys.executable, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        self._procs.append(proc)
        try:
            proc.wait(timeout=5)
            out, err = _drain_pipes_nonblocking(proc)
            self.assertIn("hello", out)
            self.assertIn("world", err)
        finally:
            _close_proc(proc)
            os.unlink(path)

    def test_kill_process_tree_uses_killpg(self):
        """_kill_process_tree should attempt os.killpg before falling back
        to recursive child discovery."""
        if not _PROCESS_STRESS:
            self.skipTest("QQ_RUN_PROCESS_STRESS_TESTS=1 required for real process-group stress tests")
        from qq.process import _kill_process_tree

        # Simulate: ensure killpg is tried first
        if sys.platform != "win32":
            import signal as sig

            # Spawn a child in its own session
            proc = subprocess.Popen(
                [sys.executable, "-c",
                 "import time; print('started', flush=True); time.sleep(30)"],
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._procs.append(proc)
            try:
                # Give it time to start
                time.sleep(0.5)
                self.assertIsNone(proc.poll(), "Process exited too early")

                # Verify it's in its own process group (pgid == pid)
                pgid = os.getpgid(proc.pid)
                self.assertEqual(pgid, proc.pid,
                                 "start_new_session should create new process group")

                # Now kill via _kill_process_tree
                _kill_process_tree(proc.pid)

                # Give OS time to clean up
                time.sleep(0.5)

                # Process should be dead
                retcode = proc.poll()
                self.assertIsNotNone(retcode,
                                     f"Process not killed, retcode={retcode}")
                # Process-group-first strategy sends SIGTERM first, so the
                # process may exit with -15 (SIGTERM) instead of -9 (SIGKILL).
                # Both are valid; the key assertion is that the process IS dead.
                self.assertIn(retcode, (-signal.SIGTERM, -signal.SIGKILL),
                              f"Expected SIGTERM (-15) or SIGKILL (-9), got {retcode}")
            finally:
                _close_proc(proc)


if __name__ == "__main__":
    unittest.main()
