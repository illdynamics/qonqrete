"""
TUI launcher — bridges the Python QonQrete CLI to the Rust internal TUI cockpit.

Design:
  - locate_qq_tui() finds the Rust binary via env var, PATH, or repo build.
  - launch_tui(argv) resolves args, detects TUI intent, and either execs
    internal TUI in child-run mode or falls back to plain Python streaming.
  - The TUI child command is always `python -m qq run <task> ...` with
    clean-stream flags so the Python side never enables its own sticky bar.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, NoReturn, Optional

from .terminal_ui import model_code_for


def locate_qq_tui() -> Optional[str]:
    """Find the Rust `internal TUI` binary. Returns path or None."""
    # 1) Env override
    env_bin = os.environ.get("QQ_TUI_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    # No public TUI binary is searched on PATH; the TUI is an internal
    # implementation built from qq/tui.
    # Repo-local build:
    repo_root = os.environ.get(
        "QQ_SRC", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    for candidate in (
        os.path.join(repo_root, "qq", "tui", "target", "release", "qq-internal-tui"),
        os.path.join(repo_root, "qq", "tui", "target", "debug", "qq-internal-tui"),
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





def _partition_args(args: List[str]):
    """Split a flat argv into leading positional args and trailing options.

    The `qq run` subparser takes two positional arguments (task_file and an
    optional repo_root). argparse rejects options that appear between the two
    positionals, so we must always keep the positionals first.
    """
    positionals: List[str] = []
    options: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if not a.startswith("-"):
            positionals.append(a)
            i += 1
            continue
        options.append(a)
        i += 1
        if i < len(args) and not args[i].startswith("-"):
            options.append(args[i])
            i += 1
    return positionals, options


def _build_child_command(
    task_file: str,
    extra_args: List[str],
    repo_root: str,
) -> List[str]:
    """Build the full Python child command for TUI mode.

    Returns a list suitable for passing as the trailing args to internal TUI run.
    """
    python = _resolve_python()
    run_root = _build_run_root(repo_root)

    # Base command: python -m qq run <task> [repo_root] ...
    # Keep the optional positional repo_root immediately after task_file, then
    # add fixed options, then pass through any user options.
    positionals, options = _partition_args(extra_args)
    cmd = [python, "-m", "qq", "run", task_file]
    cmd.extend(positionals)
    cmd.extend(["--run-root", run_root, "--no-tui"])
    cmd.extend(options)

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
    """Build a fallback plain-Python streaming command when internal TUI is missing."""
    python = _resolve_python()
    _tui_opts, child_args = _split_tui_options(extra_args)

    positionals, options = _partition_args(child_args)
    cmd = [python, "-m", "qq", "run", task_file]
    cmd.extend(positionals)
    cmd.append("--no-tui")
    cmd.extend(options)

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



_TUI_VALUE_FLAGS = {
    "--agent": "agent",
    "--model": "model",
    "--budget": "budget",
    "--progress": "progress",
    "--config": "config",
    "--status-command": "status_command",
    "--events-out": "events_out",
    "--debug-log": "debug_log",
    "--refresh-ms": "refresh_ms",
    "--status-refresh-ms": "status_refresh_ms",
}
_TUI_BOOL_FLAGS = {"--ascii": "ascii", "--no-color": "no_color"}

def _split_tui_options(args: List[str]):
    """Split internal TUI options from QonQrete child options."""
    tui = {}
    child = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in _TUI_VALUE_FLAGS:
            if i + 1 >= len(args):
                raise ValueError(f"{a} requires a value")
            tui[_TUI_VALUE_FLAGS[a]] = args[i + 1]
            if a == "--config":
                child.extend([a, args[i + 1]])
            i += 2
            continue
        if a in _TUI_BOOL_FLAGS:
            tui[_TUI_BOOL_FLAGS[a]] = True
            # --no-color also belongs to the child CLI.
            if a == "--no-color":
                child.append(a)
            i += 1
            continue
        child.append(a)
        i += 1
    return tui, child

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
            "qq: no task.md found and internal TUI not installed.",
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



_TUI_UNAVAILABLE = object()  # sentinel: no binary built, caller falls through silently


def launch_tui_with_args(argv: List[str]):
    """Launch TUI with explicit args (called from main() for `qq run` without --no-tui).

    Returns an int exit code when the TUI binary is found and runs.
    Returns the sentinel _TUI_UNAVAILABLE when no binary is found — the caller
    should fall through to the normal argparse / _cmd_run path instead of
    re-execing a subprocess. This keeps the fallback silent and seamless:
    ``qq run task.md target`` behaves identically to
    ``qq run task.md target --no-tui`` when the Rust TUI binary has not been built.
    """
    qq_tui = locate_qq_tui()

    # Resolve task file from argv (format: ["run", task_file, repo_root, ...])
    if len(argv) >= 2:
        task_file = argv[1]
    else:
        task_file = _find_task_file(argv[1:])

    if not task_file:
        if qq_tui:
            os.execv(qq_tui, [qq_tui])
        # No task file and no TUI — let argparse emit the proper error
        return _TUI_UNAVAILABLE

    repo_root = _resolve_repo_root()

    # Build extra args: everything after task_file in the original argv
    extra_args: List[str] = []
    if len(argv) > 2:
        extra_args = argv[2:]

    if qq_tui:
        return _launch_tui_mode(qq_tui, task_file, extra_args, repo_root)

    # TUI binary not built — signal caller to fall through to _cmd_run silently
    return _TUI_UNAVAILABLE

def _launch_tui_mode(
    qq_tui: str,
    task_file: str,
    extra_args: List[str],
    repo_root: str,
    tui_overrides: Optional[dict] = None,
) -> NoReturn:
    """Exec the internal QonQrete TUI with a Python child command."""
    tui_overrides = tui_overrides or {}
    try:
        tui_opts, child_args = _split_tui_options(extra_args)
    except ValueError as exc:
        print(f"qq: {exc}", file=sys.stderr)
        return 2
    tui_opts.update(tui_overrides)
    child_cmd = _build_child_command(task_file, child_args, repo_root)
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

    tui_args = ["qq-internal-tui"]
    tui_args += ["--model", str(tui_opts.get("model", model_display))]
    tui_args += ["--agent", str(tui_opts.get("agent", agent_display))]
    for key, flag in (("budget", "--budget"), ("progress", "--progress"),
                      ("config", "--config"), ("status_command", "--status-command"),
                      ("events_out", "--events-out"), ("debug_log", "--debug-log"),
                      ("refresh_ms", "--refresh-ms"), ("status_refresh_ms", "--status-refresh-ms")):
        if key in tui_opts:
            tui_args += [flag, str(tui_opts[key])]
    if tui_opts.get("ascii"):
        tui_args.append("--ascii")
    if tui_opts.get("no_color"):
        tui_args.append("--no-color")
    tui_args += [
        "run",
        "--qq-events", events_jsonl,
        "--exit-when-done",
        "--",
    ] + child_cmd

    os.execv(qq_tui, tui_args)


def _launch_fallback_mode(task_file: str, extra_args: List[str]) -> int:
    """Fallback to plain Python streaming when internal TUI binary is not built.

    Silent by design — no warning printed. The Rust TUI is an optional
    enhancement; its absence is not an error. Streaming output looks and
    feels the same whether or not the TUI cockpit wraps it.
    Build the TUI with: cd qq/tui && cargo build --release
    Or set QQ_TUI_BIN to point at a pre-built binary.
    """
    cmd = _build_fallback_command(task_file, extra_args)
    result = subprocess.run(cmd)
    return result.returncode


def launch_internal_mode(mode: str, argv: List[str]) -> int:
    """Launch a migrated TUI mode without exposing the legacy internal TUI CLI."""
    qq_tui = locate_qq_tui()
    if not qq_tui:
        print("qq: internal TUI binary is not built; run the installer to build it.", file=sys.stderr)
        return 1
    try:
        tui_opts, child_args = _split_tui_options(argv)
    except ValueError as exc:
        print(f"qq: {exc}", file=sys.stderr)
        return 2
    cmd = [qq_tui]
    for key, flag in (("agent","--agent"),("model","--model"),("budget","--budget"),
                      ("progress","--progress"),("config","--config"),
                      ("status_command","--status-command"),("events_out","--events-out"),
                      ("debug_log","--debug-log"),("refresh_ms","--refresh-ms"),
                      ("status_refresh_ms","--status-refresh-ms")):
        if key in tui_opts:
            cmd += [flag, str(tui_opts[key])]
    if tui_opts.get("ascii"): cmd.append("--ascii")
    if tui_opts.get("no_color"): cmd.append("--no-color")
    cmd.append(mode)
    cmd.extend(child_args)
    return subprocess.run(cmd).returncode
