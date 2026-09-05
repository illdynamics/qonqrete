"""Shell-command harness — runs user-configured CLI commands as checks.

Commands are run in parallel via ThreadPoolExecutor when there are
multiple independent checks, drastically cutting harness wall-clock
time to max(check_time) instead of sum(check_times).
"""
from __future__ import annotations

import concurrent.futures
import subprocess
import time
from typing import List

from .base import Harness, HarnessContext, HarnessFailure, HarnessResult
from ..path_guards import assert_command_cwd_allowed


def _run_one_check(cmd: str, check_name: str, repo_root: str,
                   timeout: int) -> HarnessFailure:
    """Run a single harness check and return HarnessFailure if it fails,
    or None if it passes."""
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=repo_root,
            capture_output=True, text=True, timeout=timeout,
        )
        dur = time.time() - start
        if proc.returncode != 0:
            return HarnessFailure(
                check_name=check_name,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=dur,
                error_message=f"Command '{cmd}' exited with code {proc.returncode}",
            )
    except subprocess.TimeoutExpired:
        dur = time.time() - start
        return HarnessFailure(
            check_name=check_name,
            exit_code=-1,
            duration_seconds=dur,
            error_message=f"Command '{cmd}' timed out after {timeout}s",
        )
    except Exception as exc:
        dur = time.time() - start
        return HarnessFailure(
            check_name=check_name,
            exit_code=-1,
            duration_seconds=dur,
            error_message=f"Command '{cmd}' failed: {exc}",
        )
    return None  # Passed — no failure


class ShellHarness(Harness):
    """Runs one or more shell commands as deterministic checks.

    When there are multiple commands, they run in parallel via
    ThreadPoolExecutor, reducing total harness time from
    sum(check_times) to max(check_time). For a single command
    (common case), no thread overhead is incurred.
    """

    def __init__(self, commands: List[str], timeout_per_command: int = 300,
                 max_workers: int = 8):
        self._commands = commands
        self._timeout = timeout_per_command
        self._max_workers = max_workers

    @property
    def name(self) -> str:
        return "shell-harness"

    def run(self, ctx: HarnessContext) -> HarnessResult:
        # Path policy: validate cwd
        ws_root = getattr(ctx, 'workspace_root', '') or ctx.repo_root
        run_root = getattr(ctx, 'run_root', '')
        if ws_root and run_root:
            assert_command_cwd_allowed(ctx.repo_root, ws_root, run_root)
        failures: List[HarnessFailure] = []
        total_start = time.time()
        n_commands = len(self._commands)

        if n_commands == 0:
            return HarnessResult(
                passed=True, failures=[],
                total_checks=0, duration_seconds=0.0,
            )

        if n_commands == 1:
            # Single check — no ThreadPool overhead needed
            check_name = "shell-check-0"
            failure = _run_one_check(
                self._commands[0], check_name, ctx.repo_root,
                self._timeout,
            )
            if failure is not None:
                failures.append(failure)
        else:
            # Run all checks in parallel
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(self._max_workers, n_commands)) as pool:
                futures = {
                    pool.submit(
                        _run_one_check, cmd,
                        f"shell-check-{i}", ctx.repo_root, self._timeout,
                    ): i
                    for i, cmd in enumerate(self._commands)
                }
                for fut in concurrent.futures.as_completed(futures):
                    failure = fut.result()
                    if failure is not None:
                        failures.append(failure)

        total_dur = time.time() - total_start
        return HarnessResult(
            passed=len(failures) == 0,
            failures=failures,
            total_checks=n_commands,
            duration_seconds=total_dur,
        )
