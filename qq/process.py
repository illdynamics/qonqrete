"""
Reusable subprocess management with deterministic process-tree cleanup.

Factored from the well-tested run_cli_checked() in tests/__init__.py.
Production code should NOT import from tests; use this module instead.

Key guarantees:
  * start_new_session=True on POSIX (each subprocess gets its own process group)
  * communicate(timeout=...) with deterministic cleanup
  * On timeout: pre-discover descendants → kill process groups → drain pipes
  * Never hangs — even if communicate() TimeoutExpired leaves pipes in a bad state
  * Always calls proc.wait() after sending signals — never leaves zombies
  * Prints stdout/stderr on failures and timeouts
"""
from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import time
from typing import Dict, List, Optional


def _collect_pipe(pipe) -> str:
    """Read whatever is available on *pipe* without blocking.

    Returns empty string if pipe is None or already closed.
    """
    if pipe is None:
        return ""
    try:
        fd = pipe.fileno()
    except (ValueError, OSError):
        return ""  # pipe already closed
    chunks = []
    while True:
        try:
            r, _, _ = select.select([pipe], [], [], 0)
        except (ValueError, OSError):
            break  # pipe closed during select
        if not r:
            break
        try:
            data = os.read(fd, 65536)
        except (ValueError, OSError):
            break
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks).decode(errors="replace")


def _drain_pipes_nonblocking(proc) -> tuple:
    """Read whatever is available on stdout/stderr WITHOUT blocking.

    After timeout cleanup, child or grandchild processes may still hold
    pipe write-ends open.  Calling a blocking .read() on those pipes can
    hang forever.  This function reads only the data that is already
    buffered and returns immediately.

    Returns (stdout_str, stderr_str).
    """
    import fcntl

    stdout_chunks: list = []
    stderr_chunks: list = []

    for pipe, chunks in ((proc.stdout, stdout_chunks), (proc.stderr, stderr_chunks)):
        if pipe is None:
            continue
        try:
            fd = pipe.fileno()
        except Exception:
            continue

        # Set non-blocking mode so .read() returns immediately
        try:
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except Exception:
            pass

        while True:
            try:
                data = pipe.read()
            except BlockingIOError:
                break
            except Exception:
                break
            if not data:
                break
            chunks.append(data)

    def _dec(chunks):
        out = b"".join(
            c if isinstance(c, bytes) else c.encode(errors="replace")
            for c in chunks
        )
        return out.decode(errors="replace")

    return _dec(stdout_chunks), _dec(stderr_chunks)


def _drain_pipes(proc, timeout=5) -> tuple:
    """Non-blocking alias for _drain_pipes_nonblocking (backward compat).

    Uses non-blocking reads exclusively — will never hang even if child
    or grandchild processes still hold pipe write-ends open.
    """
    return _drain_pipes_nonblocking(proc)


def _child_pids_linux(ppid: int) -> List[int]:
    """Return all descendant PIDs of *ppid* from /proc (bottom-up)."""
    pids: List[int] = []
    try:
        for entry in os.listdir("/proc"):
            try:
                pid = int(entry)
            except ValueError:
                continue
            stat_path = f"/proc/{pid}/stat"
            try:
                with open(stat_path, "rb") as f:
                    stat = f.read()
                paren_close = stat.rfind(b")")
                if paren_close < 0:
                    continue
                fields = stat[paren_close + 2:].split()
                if len(fields) < 2:
                    continue
                ppid_val = int(fields[1])
                if ppid_val == ppid:
                    pids.extend(_child_pids_linux(pid))
                    pids.append(pid)
            except (ProcessLookupError, OSError, FileNotFoundError):
                continue
    except FileNotFoundError:
        pass
    return pids


def _child_pids_macos(ppid: int) -> List[int]:
    """Return all descendant PIDs of *ppid* on macOS (uses pgrep recursively)."""
    pids: List[int] = []
    try:
        result = subprocess.run(
            ["pgrep", "-P", str(ppid)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            for child_pid_str in result.stdout.strip().splitlines():
                try:
                    child_pid = int(child_pid_str.strip())
                    pids.extend(_child_pids_macos(child_pid))
                    pids.append(child_pid)
                except (ProcessLookupError, OSError, ValueError):
                    pass
    except Exception:
        pass
    return pids


def _kill_process_tree(pid: int) -> None:
    """Kill *pid* and every descendant process.

    Strategy (process-group-first with pre-discovery):
      1. Discover descendants before killing (critical: parent may die
         and orphan children, making post-discovery impossible).
      2. Send SIGTERM to each descendant's process group (catches
         separate-session children that start_new_session creates).
      3. Send SIGTERM to the parent's process group.
      4. Wait briefly.
      5. Escalate to SIGKILL on all discovered descendants' process groups,
         the parent's process group, and each process directly.
    On POSIX: uses os.killpg first, then recursive /proc or pgrep fallback.
    On Windows: no-op (handled separately).
    """
    if sys.platform == "win32":
        return

    # 1. Pre-discover all descendants while parent is still alive.
    descendants = _child_pids_linux(pid) if os.path.isdir("/proc") else _child_pids_macos(pid)

    # 2. SIGTERM to each descendant's process group FIRST (catches separate-session children).
    for child in descendants:
        try:
            os.killpg(child, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            os.kill(child, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass

    # 3. SIGTERM to parent's process group.
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass

    time.sleep(0.3)

    # 4. SIGKILL escalation: descendants' process groups first, then parent's.
    for child in descendants:
        try:
            os.killpg(child, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        try:
            os.kill(child, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass

    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass

    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


def _cleanup_proc(proc) -> None:
    """Ensure a Popen process is waited for and pipes are closed.
    Never blocks indefinitely — uses timeouts everywhere.
    Never leaves zombies.
    """
    if sys.platform == "win32":
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
        for pipe in (proc.stdout, proc.stderr):
            if pipe:
                try:
                    pipe.close()
                except Exception:
                    pass
        return

    # POSIX cleanup with process-tree kill + wait
    if proc.poll() is None:
        # Kill the process tree first
        _kill_process_tree(proc.pid)

    # Always wait with timeout — never block indefinitely
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # Last resort: try again, then give up
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass
    except Exception:
        pass

    # Close pipes
    for pipe in (proc.stdout, proc.stderr):
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass


def run_subprocess(
    args: List[str],
    *,
    cwd: Optional[str] = None,
    timeout: int = 180,
    env: Optional[Dict[str, str]] = None,
    label: str = "",
    print_output_on_failure: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command via subprocess with finite timeout and deterministic cleanup.

    Returns a CompletedProcess with .stdout and .stderr as strings.

    On timeout, prints stdout/stderr and raises RuntimeError.
    On non-zero exit, prints stdout/stderr and raises RuntimeError.

    The caller is expected to catch RuntimeError for per-step pass/fail tracking.

    Unlike the tests helper, this is a production-grade helper that never
    leaves orphan processes and always calls proc.wait().
    """
    if cwd is None:
        cwd = os.getcwd()

    popen_kwargs: dict = {
        "cwd": cwd,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": False,
    }

    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(args, **popen_kwargs)

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # 1. Collect partial stdout/stderr non-blockingly
        partial_stdout = _collect_pipe(proc.stdout) if proc.stdout else ""
        partial_stderr = _collect_pipe(proc.stderr) if proc.stderr else ""

        # 2. Deterministic cleanup — kill tree + wait + close pipes
        _cleanup_proc(proc)

        # 3. Drain pipes non-blockingly after cleanup
        try:
            remaining_stdout, remaining_stderr = _drain_pipes(proc, timeout=5)
        except Exception:
            remaining_stdout, remaining_stderr = b"", b""

        def _dec(b):
            if b is None:
                return ""
            return b if isinstance(b, str) else b.decode(errors="replace")

        final_stdout = partial_stdout + _dec(remaining_stdout)
        final_stderr = partial_stderr + _dec(remaining_stderr)

        # Close pipes explicitly (double-safe)
        if proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if proc.stderr:
            try:
                proc.stderr.close()
            except Exception:
                pass

        prefix = f"[{label}] " if label else ""
        if print_output_on_failure:
            print(f"{prefix}TIMEOUT after {timeout}s")
            print(f"  Command: {' '.join(args)}")
            if final_stdout.strip():
                print(f"  stdout:\n{final_stdout}")
            if final_stderr.strip():
                print(f"  stderr:\n{final_stderr}")

        raise RuntimeError(f"{prefix}timed out after {timeout}s")

    def _dec(b):
        if b is None:
            return ""
        return b if isinstance(b, str) else b.decode(errors="replace")

    result = subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode,
        stdout=_dec(stdout),
        stderr=_dec(stderr),
    )

    if result.returncode != 0 and print_output_on_failure:
        prefix = f"[{label}] " if label else ""
        print(f"{prefix}FAILED (exit code {result.returncode})")
        print(f"  Command: {' '.join(args)}")
        if result.stdout.strip():
            print(f"  stdout:\n{result.stdout}")
        if result.stderr.strip():
            print(f"  stderr:\n{result.stderr}")

    # Ensure pipes are closed and proc is waited for even on success path
    for pipe in (proc.stdout, proc.stderr):
        try:
            if pipe:
                pipe.close()
        except Exception:
            pass
    try:
        proc.wait(timeout=1)
    except Exception:
        pass

    return result


def orphan_audit() -> List[str]:
    """Return any orphan qq processes relevant to the current project.

    Returns a list of matching process command lines (empty if clean).

    Scoped strictly to the current project so that concurrent qq pipelines
    building *other* repos (e.g. a sibling /x/nuxel agent cycle) are NEVER
    reported as orphans — only processes tied to this source tree or spawned
    by this verification run are considered. Runs are also excluded from ever
    reporting their own running ancestor pipeline.

    Uses a settle-then-retry strategy to avoid reporting transient test
    processes that are mid-cleanup. Only reports processes whose actual argv
    matches the pattern as a *command*, not processes that merely contain the
    pattern string as data (e.g. in a Python -c script or test source).
    """
    orphans = []
    patterns = [
        "python3 -m qq run",
        "qq_timeout_runner",
        "python3 -m qq.verify",
    ]
    _self_pid = os.getpid()

    # Current project root (one level above the qq package).
    _proj_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    def _get_ppid(pid: int) -> Optional[int]:
        """Return the parent PID of *pid*, or None if unavailable."""
        try:
            with open(f"/proc/{pid}/stat") as fh:
                parts = fh.read().rsplit(")", 1)[-1].split()
            # parts[0] is state after ') '; ppid is parts[1] (4th field)
            if len(parts) >= 3:
                return int(parts[1])
        except Exception:
            pass
        return None

    def _ancestor_pids(pid: int) -> set:
        """PIDs on the ancestry chain above *pid* (the running pipeline)."""
        chain = set()
        cur = _get_ppid(pid)
        guard = 0
        while cur and cur > 1 and guard < 64:
            if cur in chain:
                break
            chain.add(cur)
            cur = _get_ppid(cur)
            guard += 1
        return chain

    _ancestors = _ancestor_pids(_self_pid)

    def _cmdline_for(pid: int) -> Optional[str]:
        """Return the argv string for *pid*, or '' if unavailable."""
        try:
            r = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        return ""

    def _relevant_cmdline(cmdline: str) -> bool:
        """True if *cmdline* is tied to the current project or this verify run.

        Pure qq helpers (timeout runner / verifier) are always relevant. Other
        qq commands are relevant only when they operate on this source tree or
        on a verify temp dir.
        """
        if "qq_timeout_runner" in cmdline:
            return True
        if "qq.verify" in cmdline or "qq verify" in cmdline:
            return True
        if "qq_verify_dry_" in cmdline or "qq_verify_stream_" in cmdline:
            return True
        if _proj_root in cmdline:
            return True
        return False

    try:
        if sys.platform == "win32":
            return []

        def _collect() -> set:
            found = set()
            for pat in patterns:
                result = subprocess.run(
                    ["pgrep", "-f", pat],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        pid_str = line.strip()
                        try:
                            pid = int(pid_str)
                        except ValueError:
                            continue
                        if pid in _ancestors:
                            continue  # running pipeline controller — not an orphan
                        try:
                            os.kill(pid, 0)  # signal 0 = check existence
                        except OSError:
                            continue  # PID doesn't exist
                        cmdline = _cmdline_for(pid)
                        if not cmdline:
                            continue
                        if len(cmdline) > 2000 or "\n" in cmdline or "\\012" in cmdline:
                            continue  # likely a script body, not the command
                        if pat in cmdline and _relevant_cmdline(cmdline):
                            found.add(pid_str)
            return found

        # First pass
        first = _collect()
        if not first:
            return []

        # Wait and retry — only report processes that persist
        time.sleep(2.0)
        second = _collect()

        # Report only those present in both passes, sorted
        persistent = first & second
        orphans = sorted(persistent)

    except Exception:
        pass
    return orphans

