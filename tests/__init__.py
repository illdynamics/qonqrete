"""Qq test suite.

Process helpers are imported from qq.process to keep timeout-cleanup
logic in a single, well-tested location.
"""
import os
import sys
from typing import List, Optional, Dict

from qq.process import run_subprocess, _kill_process_tree

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def run_cli_checked(
    args: List[str],
    *,
    cwd: str = None,
    timeout: int = 90,
    env: Optional[Dict[str, str]] = None,
) -> "subprocess.CompletedProcess":
    """Run a CLI command via subprocess with a finite timeout.

    Every subprocess call in tests MUST use this helper (or pass an
    explicit ``timeout`` to ``subprocess.run``).  If the child times out
    the resulting ``AssertionError`` includes the command, the timeout,
    and whatever stdout/stderr was captured up to that point.

    Wraps qq.process.run_subprocess() — the same production-grade helper
    used by qq.verify and the rest of the system.  Raises AssertionError
    on failure or timeout so unittest can self.fail() and self.assertRaises()
    work as expected.
    """
    import subprocess

    if cwd is None:
        cwd = PROJECT_ROOT

    try:
        result = run_subprocess(args, cwd=cwd, timeout=timeout, env=env, label="test")
    except RuntimeError as e:
        raise AssertionError(str(e)) from e

    if result.returncode != 0:
        raise AssertionError(
            f"Subprocess failed (exit code {result.returncode})\n"
            f"Command: {args}\n"
            f"cwd: {cwd}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result
