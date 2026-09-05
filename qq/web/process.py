"""
Dashboard process lifecycle — start/stop/status for the briQsQope web server.

This module manages the briQsQope dashboard as a child process.
It does NOT handle the Rust/TypeScript build — that is expected to be
done by the user via `qq-web/local-build.sh` or `pnpm install && pnpm run build`.

For now, the dashboard is started as a simple Python HTTP server that
serves the read-model API. The full briQsQope frontend integration
is gated behind the QQ_WEB_DEV_MODE env var or a built frontend dist/.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional


# PID file for tracking running dashboard
def _pid_file() -> str:
    """Path to the dashboard PID tracking file."""
    return os.path.join(
        os.path.expanduser("~"), ".qq", "briQsQope.pid"
    )


def _port_file() -> str:
    """Path to the dashboard port tracking file."""
    return os.path.join(
        os.path.expanduser("~"), ".qq", "briQsQope.port"
    )


def _run_root_file() -> str:
    """Path to the dashboard run-root tracking file."""
    return os.path.join(
        os.path.expanduser("~"), ".qq", "briQsQope.run_root"
    )


def find_dashboard_dir() -> Optional[str]:
    """Find the qq/web/ directory relative to the QonQrete package."""
    # Primary: this file is at qq/web/process.py, so its directory IS qq/web
    primary = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(primary):
        return primary

    # Secondary: <QQ_SRC>/qq/web
    qq_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(qq_parent, "web")
    if os.path.isdir(candidate):
        return candidate

    # Tertiary: <cwd>/qq/web
    cwd_candidate = os.path.join(os.getcwd(), "qq", "web")
    if os.path.isdir(cwd_candidate):
        return cwd_candidate

    return None


def start_dashboard(
    run_root: str,
    host: str = "0.0.0.0",
    port: int = 31337,
    open_browser: bool = False,
    dashboard_dir: Optional[str] = None,
    repo_root: str = "",
    control_root: Optional[str] = None,
) -> Optional[int]:
    """Start the briQsQope dashboard as a background process.

    Args:
        run_root: Path to the QonQrete run root (with events.jsonl etc.)
        host: Listen address.
        port: Listen port. 0 means auto-pick.
        open_browser: If True, open the default browser.
        dashboard_dir: Path to qq/web/ directory.

    Returns:
        PID of the dashboard process, or None if startup failed.
    """
    if dashboard_dir is None:
        dashboard_dir = find_dashboard_dir()

    if dashboard_dir is None:
        return None

    # Fix #2: Defensive canonicalization — resolve relative paths before
    # spawning the child process so the child always receives absolute paths.
    run_root = os.path.abspath(os.path.expanduser(run_root))
    repo_root = os.path.abspath(os.path.expanduser(repo_root)) if repo_root else ""

    # Ensure ~/.qq exists
    os.makedirs(os.path.expanduser("~/.qq"), exist_ok=True)

    # Stop any existing dashboard
    stop_dashboard()

    # Build the command to start the dashboard API server.
    # Prefer module-based launch (python -m qq.web.api) to avoid
    # relative-import issues. Fall back to direct script if needed.
    api_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "api.py"
    )

    # Always prefer module launch when possible
    # Fall back to script if we can't resolve the module
    # Use --control-root when in control-root mode, --run-root otherwise
    root_arg = "--control-root" if control_root else "--run-root"
    root_val = control_root if control_root else run_root
    try:
        import qq.web.api  # noqa: F401 — verify import works
        cmd = [
            sys.executable, "-m", "qq.web.api",
            root_arg, root_val,
            "--repo-root", repo_root or "",
            "--host", host,
            "--port", str(port),
        ]
    except ImportError:
        if os.path.isfile(api_script):
            cmd = [
                sys.executable, api_script,
                root_arg, root_val,
                "--repo-root", repo_root or "",
                "--host", host,
                "--port", str(port),
            ]
        else:
            return None

    env = os.environ.copy()
    env["QQ_WEB_RUN_ROOT"] = run_root
    env["QQ_WEB_REPO_ROOT"] = repo_root or os.getcwd()
    env["QQ_WEB_SOURCE_OF_TRUTH"] = "qonqrete"
    env["QQ_WEB_READ_ONLY"] = "1"
    env["QQ_WEB_PRODUCT_NAME"] = "briQsQope"
    env["QQ_WEB_HOST"] = host
    env["QQ_WEB_PORT"] = str(port)
    # Propagate runs API auth if set (new + legacy names)
    for ev in ("QONQRETE_RUNS_API_TOKEN", "QONQRETE_INGEST_TOKEN",
               "QONQRETE_RUNS_DEFAULT_ROOT", "QONQRETE_DEFAULT_RUN_ROOT",
               "QONQRETE_RUNS_TASK_DIR", "QONQRETE_INGEST_TASK_DIR",
               "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS", "QONQRETE_ALLOWED_TARGET_ROOTS",
               "QONQRETE_RUNS_QUEUE_MODE", "QONQRETE_INGEST_QUEUE_MODE",
               "QONQRETE_RUNS_DEV_NO_AUTH", "QONQRETE_DEV_NO_AUTH",
               "QONQRETE_RUNS_RUNNER", "QONQRETE_CONTROL_ROOT",
               "QONQRETE_PUBLIC_DASHBOARD_URL"):
        if ev in os.environ:
            env[ev] = os.environ[ev]

    try:
        # Open visible log files for stdout/stderr
        logs_dir = os.path.join(os.path.expanduser("~"), ".qq")
        os.makedirs(logs_dir, exist_ok=True)
        stdout_log = os.path.join(logs_dir, "briQsQope.stdout.log")
        stderr_log = os.path.join(logs_dir, "briQsQope.stderr.log")
        
        stdout_f = open(stdout_log, "a")
        stderr_f = open(stderr_log, "a")
        # Write startup markers
        import datetime
        ts = datetime.datetime.now().isoformat()
        stdout_f.write(f"\n--- briQsQope started at {ts} ---\n")
        stderr_f.write(f"\n--- briQsQope started at {ts} ---\n")
        stdout_f.flush()
        stderr_f.flush()
        
        proc = subprocess.Popen(
            cmd,
            cwd=dashboard_dir,
            env=env,
            stdout=stdout_f,
            stderr=stderr_f,
            preexec_fn=os.setpgrp,  # Own process group for clean signal isolation
        )

        # Give it a moment to start
        time.sleep(0.5)

        if proc.poll() is not None:
            # Process exited immediately
            return None

        # Write tracking files
        with open(_pid_file(), "w") as f:
            f.write(str(proc.pid))
        with open(_port_file(), "w") as f:
            f.write(str(port))
        with open(_run_root_file(), "w") as f:
            f.write(run_root)
        # Additional tracking for briQsQope
        with open(os.path.join(logs_dir, "briQsQope.mode"), "w") as f:
            f.write("control-root" if control_root else "run-root")
        with open(os.path.join(logs_dir, "briQsQope.root"), "w") as f:
            f.write(root_val)

        if open_browser:
            import webbrowser
            display_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
            local_url = f"http://{display_host}:{port}"
            webbrowser.open(local_url)

        return proc.pid

    except Exception:
        return None


def stop_dashboard() -> bool:
    """Stop a running dashboard process. Returns True if one was stopped."""
    pf = _pid_file()
    if not os.path.isfile(pf):
        return False

    try:
        with open(pf, "r") as f:
            pid_str = f.read().strip()
        pid = int(pid_str)
    except (ValueError, OSError):
        _cleanup_tracking_files()
        return False

    try:
        os.killpg(pid, signal.SIGTERM)  # Kill entire process group
        time.sleep(0.2)
        # Check if still alive, force kill
        try:
            os.kill(pid, 0)
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    except (OSError, ProcessLookupError):
        pass

    _cleanup_tracking_files()
    return True


def dashboard_status() -> Dict[str, Any]:
    """Return status info about the running dashboard.

    Shows: running/not running, pid, host, port, URL, serving mode,
    root path, active run id/state, active target path, tmux attach
    command, stdout/stderr log paths.
    """
    pf = _pid_file()
    portf = _port_file()
    runf = _run_root_file()

    status: Dict[str, Any] = {"running": False}

    if not os.path.isfile(pf):
        return status

    try:
        with open(pf, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return status

    # Check if process is alive
    try:
        os.kill(pid, 0)
        status["running"] = True
        status["pid"] = pid
    except OSError:
        _cleanup_tracking_files()
        return status

    host = os.environ.get("QQ_WEB_HOST", "0.0.0.0")
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host

    if os.path.isfile(portf):
        try:
            with open(portf, "r") as f:
                port = int(f.read().strip())
            status["port"] = port
            status["host"] = display_host
            status["url"] = "https://web.qonqrete.sh"
        except (ValueError, OSError):
            pass

    if os.path.isfile(runf):
        try:
            with open(runf, "r") as f:
                status["run_root"] = f.read().strip()
        except OSError:
            pass

    # Detect serving mode: check if run_root contains current-run.json
    run_root = status.get("run_root", "")
    if run_root and os.path.isfile(os.path.join(run_root, "current-run.json")):
        status["serving_mode"] = "control-root"
    elif run_root:
        status["serving_mode"] = "run-root"
    status["root_path"] = run_root

    # Try to read current-run.json for active run info
    if run_root:
        cr_path = os.path.join(run_root, "current-run.json")
        if os.path.isfile(cr_path):
            try:
                import json
                with open(cr_path, "r") as f:
                    cr = json.load(f)
                status["active_run_id"] = cr.get("run_id", "")
                status["active_run_state"] = cr.get("state", "")
                status["active_target_path"] = cr.get("target_path", "")
                status["active_tmux_attach"] = cr.get("attach_command", "")
            except Exception:
                pass

    # Log file paths
    logs_dir = os.path.join(os.path.expanduser("~"), ".qq")
    status["stdout_log"] = os.path.join(logs_dir, "briQsQope.stdout.log")
    status["stderr_log"] = os.path.join(logs_dir, "briQsQope.stderr.log")

    return status


def _cleanup_tracking_files() -> None:
    """Remove PID/port/run-root tracking files."""
    for f in [_pid_file(), _port_file(), _run_root_file()]:
        try:
            os.remove(f)
        except OSError:
            pass
