"""
TUI launcher — bridges the Python QonQrete CLI to the Rust qq-tui cockpit.

Design:
  - locate_qq_tui() finds the Rust binary via env var, PATH, or repo build.
  - launch_tui(argv) resolves args, detects TUI intent, and either execs
    qq-tui in child-run mode or falls back to plain Python streaming.
  - The TUI child command is always `python -m qq run <task> ...` with
    clean-stream flags so the Python side never enables its own sticky bar.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import List, NoReturn, Optional

from .terminal_ui import model_code_for


def locate_qq_tui() -> Optional[str]:
    """Find the Rust `qq-tui` binary. Returns path or None."""
    # 1) Env override
    env_bin = os.environ.get("QQ_TUI_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    # 2) On PATH
    path_bin = shutil.which("qq-tui")
    if path_bin:
        return path_bin

    # 3) Repo-local builds
    repo_root = os.environ.get(
        "QQ_SRC", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    for candidate in (
        os.path.join(repo_root, "qq-tui", "target", "release", "qq-tui"),
        os.path.join(repo_root, "qq-tui", "target", "debug", "qq-tui"),
    ):
        if os.path.isfile(candidate):
            return candidate

    return None


def _find_task_file(argv: List[str]) -> Optional[str]:
    """Resolve a task file from argv or cwd default."""
    if argv and (argv[0].endswith(".md") or os.path.isfile(argv[0])):
        return argv[0]
    default = os.path.join(os.getcwd(), "task.md")
    if os.path.isfile(default):
        return default
    return None


def _resolve_python() -> str:
    """Return the Python interpreter to use for child processes."""
    return os.environ.get("QQ_PYTHON", sys.executable)


def _resolve_repo_root() -> str:
    """Return the QonQrete repo root (where qq module lives)."""
    return os.environ.get(
        "QQ_SRC",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


def _build_run_root(repo_root: str) -> str:
    """Generate a deterministic run_root before launching the child."""
    from .workspaces import default_run_root
    return default_run_root(repo_root)


def _build_child_command(
    task_file: str,
    extra_args: List[str],
    repo_root: str,
) -> List[str]:
    """Build the full Python child command for TUI mode.

    Returns a list suitable for passing as the trailing args to qq-tui run.
    """
    python = _resolve_python()
    run_root = _build_run_root(repo_root)

    # Base command: python -m qq run <task> ...
    cmd = [python, "-m", "qq", "run", task_file, "--run-root", run_root]

    # Append user-provided extra args (pass-through from qq tui ...)
    cmd.extend(extra_args)

    # Ensure clean-stream defaults for TUI mode unless user overrides
    # Keep colors ON for the TUI to render multi-colored output
    _ensure_flag(cmd, "--stream-agent-output", "--stream-agent-output")
    _ensure_flag(cmd, "--stream-mode", "prefixed")
    _ensure_flag(cmd, "--stream-indicator", "none")
    _ensure_flag(cmd, "--stream-status-line", "off")
    _ensure_flag(cmd, "--stream-line-prefix", "agent")

    # Do NOT force --no-color — let colors flow through to TUI
    # The TUI will parse ANSI colors or use its own color scheme

    return cmd


def _ensure_flag(cmd: List[str], flag: str, value: str) -> None:
    """Ensure a flag=value pair (or boolean flag) is set in cmd if not already present.

    When flag == value (boolean flags like --stream-agent-output), the flag is
    appended once. Otherwise the pair [flag, value] is appended.
    """
    if flag.startswith("--no-"):
        if flag in cmd:
            return
        positive = flag.replace("--no-", "--")
        if positive in cmd:
            try:
                idx = cmd.index(positive)
                cmd.pop(idx)
            except ValueError:
                pass
        cmd.append(flag)
    else:
        if flag in cmd:
            return
        if flag == value:
            # Boolean flag (e.g. --stream-agent-output)
            cmd.append(flag)
        else:
            cmd.extend([flag, value])


def _build_fallback_command(
    task_file: str,
    extra_args: List[str],
) -> List[str]:
    """Build a fallback plain-Python streaming command when qq-tui is missing."""
    python = _resolve_python()
    cmd = [python, "-m", "qq", "run", task_file]

    cmd.extend(extra_args)

    _ensure_flag(cmd, "--stream-agent-output", "--stream-agent-output")
    _ensure_flag(cmd, "--stream-indicator", "spinner")
    if "--stream-status-line" not in cmd and all(
        "--stream-status-line" not in a for a in extra_args
    ):
        cmd.extend(["--stream-status-line", "bottom"])
    if "--stream-line-prefix" not in cmd and all(
        "--stream-line-prefix" not in a for a in extra_args
    ):
        cmd.extend(["--stream-line-prefix", "auto"])

    return cmd


_KNOWN_SUBCOMMANDS = frozenset({
    "run", "replay", "doctor", "providers", "cleanup",
    "image-smoke-test", "package", "verify", "tui",
})


def launch_tui(argv: List[str]) -> int:
    """Resolve TUI intent and launch. Returns exit code (int).

    Called when the user wants the TUI:
      - qq           (no args, task.md exists)
      - qq task.md
      - qq tui [task.md] [flags...]
    """
    task_file = _find_task_file(argv)
    extra_args: List[str] = []

    if argv and argv[0] == "tui":
        remaining = argv[1:]
        if remaining and (
            remaining[0].endswith(".md") or os.path.isfile(remaining[0])
        ):
            task_file = remaining[0]
            extra_args = remaining[1:]
        else:
            extra_args = remaining
    elif argv and (argv[0].endswith(".md") or os.path.isfile(argv[0])):
        task_file = argv[0]
        extra_args = argv[1:]
    else:
        extra_args = argv

    if not task_file:
        qq_tui = locate_qq_tui()
        if qq_tui:
            os.execv(qq_tui, [qq_tui])
        print(
            "qq: no task.md found and qq-tui not installed.",
            file=sys.stderr,
        )
        print(
            "Usage: qq task.md       # run a task in the TUI",
            file=sys.stderr,
        )
        print(
            "       qq run task.md    # headless CLI run",
            file=sys.stderr,
        )
        return 1

    repo_root = _resolve_repo_root()
    qq_tui = locate_qq_tui()

    if qq_tui:
        return _launch_tui_mode(qq_tui, task_file, extra_args, repo_root)
    else:
        return _launch_fallback_mode(task_file, extra_args)



def launch_tui_with_args(argv: List[str]) -> int:
    """Launch TUI with explicit args (called from _cmd_run when --no-tui is not set).

    This is used by `qq run task.md target-dir` to launch the TUI.
    """
    # Resolve task file from argv (format: ["run", task_file, repo_root, ...])
    if len(argv) >= 2:
        task_file = argv[1]
    else:
        task_file = _find_task_file(argv[1:])

    if not task_file:
        qq_tui = locate_qq_tui()
        if qq_tui:
            os.execv(qq_tui, [qq_tui])
        print("qq: no task.md found and qq-tui not installed.", file=sys.stderr)
        return 1

    repo_root = _resolve_repo_root()
    qq_tui = locate_qq_tui()

    # Build extra args: everything after task_file in the original argv
    extra_args: List[str] = []
    if len(argv) > 2:
        # argv[2] is typically repo_root; pass everything beyond as CLI args to run
        extra_args = argv[2:]

    if qq_tui:
        return _launch_tui_mode(qq_tui, task_file, extra_args, repo_root)
    else:
        return _launch_fallback_mode(task_file, extra_args)

def _launch_tui_mode(
    qq_tui: str,
    task_file: str,
    extra_args: List[str],
    repo_root: str,
) -> NoReturn:
    """Exec qq-tui with child Python command."""
    child_cmd = _build_child_command(task_file, extra_args, repo_root)
    run_root = next(
        (child_cmd[i + 1] for i, a in enumerate(child_cmd) if a == "--run-root"),
        "",
    )
    events_jsonl = os.path.join(run_root, "events.jsonl") if run_root else ""

    # Resolve model display code and agent name for the initial agent (qlarifier)
    model_display = "?"
    agent_display = "Qlarifier"
    try:
        from .config import resolve_config
        cfg = resolve_config(repo_root=repo_root)
        model_display = model_code_for(cfg.model_qlarifier)
        if not model_display or model_display == "?":
            # Try to derive from the raw model string
            raw = cfg.model_qlarifier or ""
            if "flash" in raw.lower():
                model_display = "fla-T" if "thinking" in raw.lower() else "fla"
            elif "pro" in raw.lower():
                model_display = "pro-T" if "thinking" in raw.lower() else "pro"
    except Exception as e:
        import sys
        print(f"[qq] Warning: could not resolve config for model display: {e}", file=sys.stderr)

    tui_args = [
        "qq-tui",
        "--model", model_display,
        "--agent", agent_display,
        "run",
        "--qq-events", events_jsonl,
        "--",
    ] + child_cmd

    os.execv(qq_tui, tui_args)


def _launch_fallback_mode(task_file: str, extra_args: List[str]) -> int:
    """Fallback to plain Python streaming when qq-tui is not available."""
    cmd = _build_fallback_command(task_file, extra_args)
    print(
        "[qq] qq-tui not found. Falling back to plain streaming:",
        file=sys.stderr,
    )
    print(f"[qq] {' '.join(cmd)}", file=sys.stderr)
    import subprocess
    result = subprocess.run(cmd)
    return result.returncode
