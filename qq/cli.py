"""
Qq CLI entrypoint.

Commands:
    qq run task.md <target-dir>
    qq run task.md <target-dir> --dry-run
    qq run task.md <target-dir> --no-stream-agent-output
    qq run task.md <target-dir> --provider codeseeq
    qq run task.md <target-dir> -T / --no-tui  (exec mode, no TUI)
    qq run task.md <target-dir> -n / --no-repo  (skip git handling)
    qq install
    qq reinstall
    qq nuke
    qq doctor
    qq doctor -t test1,test2  or  qq doctor -t test1 -t test2
    qq models
    qq replay .qq/runs/<run-id>/events.jsonl
    qq providers
    qq cleanup --repo-root .
    qq image-smoke-test
    qq generate-image "prompt" [options]
    qq package
    qq verify
    qq tui
"""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import subprocess
import textwrap
import time
from datetime import datetime, timedelta
from typing import Optional, List as ListType

from . import __version__
from .adapters import get_adapter
from .adapters.codeseeq import _find_codeseeq_binary
from .config import load_providers, resolve_config, QqConfig
from .qontroller import QontrollerConfig, run as run_qontroller
from .streaming import _ROLE_DISPLAY, _RESET
from .workspaces import default_run_root, generate_run_id, _ensure_qqignore

DEFAULT_QQ_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "config", "qq.yaml"))
DEFAULT_PROVIDERS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "config", "providers.yaml"))

# Install script path
_INSTALL_SCRIPT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "scripts", "install-qq-local.sh"))


# ---------------------------------------------------------------------------
# Human-interaction callback
# ---------------------------------------------------------------------------
def _ask_human(questions):
    """Ask the user clarification questions. TUI-safe.

    When running inside integrated TUI, the terminal is in raw mode and the TUI
    consumes all keyboard events directly. In that context, blocking on
    input() would stall the pipeline forever. We detect non-interactive
    contexts and auto-answer with sensible defaults to keep the pipeline
    moving.

    The Qlarifier will use these defaults in its next clarification round
    and converge on a final clarified task.
    """
    print(f"\n{_ROLE_DISPLAY.get('qlarifier', ('[Qlarifier]', ''))[1]}[Qlarifier]{_RESET} need a bit more before",
      f"{_ROLE_DISPLAY.get('instruqtor', ('[instruQtor]', ''))[1]}[instruQtor]{_RESET} can plan this:")

    # Check if stdin is usable for blocking interactive input.
    # CRITICAL: In integrated TUI raw mode, select.select may find stray terminal
    # escape bytes on stdin, misleadingly returning True. Then input()
    # blocks forever because TUI consumes keystrokes. We use a TWO-PHASE
    # guard to avoid this:
    #   Phase 1: check $QQ_INTERACTIVE — if explicitly set, trust it.
    #   Phase 2: otherwise fall back to select + timeout-based detection.
    stdin_usable = False
    try:
        # Phase 1: explicit override via environment variable
        qq_interactive = os.environ.get("QQ_INTERACTIVE", "").lower()
        if qq_interactive in ("0", "false", "no", "off"):
            stdin_usable = False
        elif qq_interactive in ("1", "true", "yes", "on"):
            stdin_usable = True
        elif sys.stdin.isatty():
            # Phase 2: select-based detection with double-check
            # First poll: any bytes?
            import select as _select
            ready, _, _ = _select.select([sys.stdin], [], [], 0.1)
            if ready:
                # Bytes are available — but are they real user input
                # or stray terminal escape codes? Peek at the first byte
                # with a second, even shorter timeout.
                import termios, tty
                old_settings = termios.tcgetattr(sys.stdin)
                try:
                    tty.setcbreak(sys.stdin.fileno())
                    r2, _, _ = _select.select([sys.stdin], [], [], 0.05)
                    if r2:
                        # There's readable data. Try to read a byte.
                        b = sys.stdin.buffer.read(1)
                        if b and b != b'\x1b':
                            # Non-escape byte: real user input pending.
                            # Push it back via a controlled approach:
                            # Since we only peeked, we reset and let
                            # input() handle the full line.
                            stdin_usable = True
                        else:
                            # Escape byte (\x1b) — terminal noise from
                            # TUI raw mode. stdin is NOT usable for input().
                            stdin_usable = False
                            # Drain remaining escape sequence
                            import select as _s2
                            while True:
                                r3, _, _ = _s2.select([sys.stdin], [], [], 0.01)
                                if r3:
                                    sys.stdin.buffer.read(1)
                                else:
                                    break
                    else:
                        stdin_usable = False
                finally:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            else:
                stdin_usable = False
        # Non-TTY: piped stdin, never block on input()
    except (OSError, ValueError, IOError, ImportError):
        stdin_usable = False

    answers = []
    for q in questions:
        if stdin_usable:
            try:
                ans = input(f"  - {q}\n    > ")
                if ans.strip():
                    answers.append(ans.strip())
                else:
                    print("    [auto: empty answer, using defaults]")
                    answers.append("[AUTO] Use reasonable defaults")
            except (EOFError, KeyboardInterrupt):
                print("    [auto: input interrupted, using defaults]")
                answers.append("[AUTO] Use reasonable defaults")
        else:
            print(f"  - {q}")
            print("    > [auto: non-interactive context, using defaults]")
            answers.append("[AUTO] Use reasonable defaults")
    return answers


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qq",
        description="QonQrete v2 Qq — deterministic local-first multi-agent coding harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- run ----
    run_p = sub.add_parser("run", help="Run the full clarify → plan → build → review loop")
    run_p.add_argument("task_file", help="Markdown/text file containing the task")
    run_p.add_argument("repo_root", nargs="?", default=None,
                        help="Target directory to build into (default: current directory)")
    run_p.add_argument("--run-root", default=None,
                        help="Where Qq stores worktrees/logs (default: <repo-root>/.qq/runs/<unique-id>)")
    run_p.add_argument("--config", default=DEFAULT_QQ_PATH, help="Path to qq config YAML")
    run_p.add_argument("--providers-config", default=DEFAULT_PROVIDERS_PATH,
                        help="Path to providers manifest YAML")
    run_p.add_argument("--provider", default=None, help="Provider name (codeseeq, mock, ...)")
    run_p.add_argument("--codeseeq-bin", default=None, help="Path to codeseeq binary")
    run_p.add_argument("--runtime-mode", default=None,
                        choices=["auto", "container", "host"], help="CodeSeeq runtime mode")
    run_p.add_argument("--bridge-mode", default=None,
                        choices=["auto", "process", "container", "external"],
                        help="CodeSeeq bridge mode")
    run_p.add_argument("--briq-sensitivity", type=int, default=None,
                        help="Decomposition granularity (0-16, 0=auto)")
    run_p.add_argument("--max-cycles", type=int, default=None,
                        help="Max build/review cycles before aborting (0=unlimited)")
    run_p.add_argument("--max-time", type=int, default=None,
                        help="Max total run time in seconds before aborting (0=unlimited)")
    run_p.add_argument("--max-parallel-build-groups", type=int, default=None,
                        help="Max concurrent build groups")
    run_p.add_argument("--parallel-spawn-delay", type=float, default=None,
                        dest="parallel_spawn_delay_seconds",
                        help="Delay in seconds between spawning each parallel agent (default: 1.0)")
    run_p.add_argument("--dry-run", action="store_true",
                        help="Use the mock adapter — zero API calls")
    run_p.add_argument("--check", action="append", default=None,
                        dest="checks",
                        help="Add a harness check command (repeatable)")
    run_p.add_argument("--review-on-harness-failure", action="store_true", default=None,
                        help="Run InspeQtor even when harness checks fail")
    run_p.add_argument("--allow-dirty", action="store_true", default=True,
                        help="Allow running on a dirty git repo")
    run_p.add_argument("--verbose", action="store_true", default=False)
    # Integrated TUI options (the old integrated TUI flags are now part of qq run).
    run_p.add_argument("--agent", default=None, help="Agent name shown in the TUI status bar")
    run_p.add_argument("--model", default=None, help="Model code shown in the TUI status bar")
    run_p.add_argument("--budget", type=int, default=None, help="Budget shown in the TUI status bar")
    run_p.add_argument("--progress", type=float, default=None, help="Initial TUI progress percentage")
    run_p.add_argument("--status-command", default=None, help="Statusline command")
    run_p.add_argument("--events-out", default=None, help="TUI JSONL event output path")
    run_p.add_argument("--ascii", action="store_true", help="Force ASCII TUI mode")
    run_p.add_argument("--debug-log", default=None, help="TUI debug log path")
    run_p.add_argument("--refresh-ms", type=int, default=None, help="TUI spinner refresh interval in ms")
    run_p.add_argument("--status-refresh-ms", type=int, default=None, help="TUI status refresh interval in ms")
    run_p.add_argument("--json", action="store_true", default=False, dest="json_output",
                        help="Output JSON to stdout")
    run_p.add_argument("--no-color", action="store_true", default=False)
    run_p.add_argument("--stream-agent-output", action="store_true", default=None,
                        dest="stream_agent_output_flag",
                        help="Stream agent stdout/stderr live (default: on)")
    run_p.add_argument("-N", "--no-stream-agent-output", action="store_false",
                        dest="stream_agent_output_flag",
                        help="Disable live agent output streaming")
    run_p.add_argument("--stream-mode", default="prefixed",
                        choices=["prefixed", "raw"],
                        help="Stream mode: prefixed (default) or raw")
    run_p.add_argument("--stream-stderr", action="store_true", default=None,
                        dest="stream_stderr_flag",
                        help="Stream stderr (default when --stream-agent-output)")
    run_p.add_argument("--no-stream-stderr", action="store_false", default=None,
                        dest="stream_stderr_flag",
                        help="Don't stream stderr")
    run_p.add_argument("--stream-indicator", default=None,
                        choices=["stream", "spinner", "none"],
                        help="What to show after role prefix in streaming mode (default: stream)")
    run_p.add_argument("--show-prompts", action="store_true", default=False,
                        help="Print prompt paths during streaming (off by default)")

    # Sticky status line
    run_p.add_argument("--stream-status-line", default="off",
                        choices=["off", "bottom", "top"],
                        help="Enable sticky terminal status line (off, bottom, top)")
    run_p.add_argument("--stream-line-prefix", default=None,
                        choices=["auto", "agent", "stream", "none"],
                        help="Control agent/stream prefix in streamed body output")

    # Agent color output mode
    run_p.add_argument("--agent-color-output", default=None,
                        choices=["agent", "original", "none"],
                        help="Agent output color mode: agent (all output in agent's color), "
                             "original (preserve codeseeq colors), none (no color)")

    # No TUI (exec mode)
    run_p.add_argument("-T", "--no-tui", action="store_true", default=False,
                        help="Run in exec mode (no TUI cockpit)")

    # No repo
    run_p.add_argument("-n", "--no-repo", action="store_true", default=False,
                        help="Skip git handling (treat target-dir as plain directory)")

    # Reasoning effort
    run_p.add_argument("-r", "--reasoning", default=None, dest="reasoning_effort",
                        choices=["minimal", "low", "high", "max"],
                        help="Reasoning effort for thinking models (low, high, max). "
                             "Only valid with -thinking model variants. "
                             "Ignored with a warning for non-thinking models.")

        # Temperature (non-thinking models only)
    run_p.add_argument("-C", "--temperature", type=float, default=None, dest="temperature",
                        help="Temperature for non-thinking models (e.g., 0.1-2.0). "
                             "Only valid with non-thinking model variants. "
                             "Ignored with a warning for thinking models.")

    # Top-p (non-thinking models only)
    run_p.add_argument("-P", "--top_p", type=float, default=None, dest="top_p",
                        help="Top-p (nucleus sampling) for non-thinking models (e.g., 0.1-1.0). "
                             "Only valid with non-thinking model variants. "
                             "Ignored with a warning for thinking models.")


    # briQsQope web dashboard
    run_p.add_argument("--web", action="store_true", default=None,
                        dest="web_enabled",
                        help="Start briQsQope dashboard for this run")
    run_p.add_argument("--no-web", action="store_false", default=None,
                        dest="web_enabled",
                        help="Force dashboard off for this run")
    run_p.add_argument("--web-host", default=None,
                        help="Override dashboard host (default: 0.0.0.0)")
    run_p.add_argument("--web-port", type=int, default=None,
                        help="Override dashboard port (default: 31337, 0=auto)")
    run_p.add_argument("--web-open-browser", action="store_true", default=None,
                        help="Open browser after dashboard starts")
    run_p.add_argument("--web-publish-level", default=None,
                        choices=["briq_group", "briq"],
                        help="Board card granularity: briq_group (default) or briq")
    run_p.add_argument("--web-hard-fail", action="store_true", default=None,
                        help="Abort run if dashboard fails to start")

    # YOLO (non-interactive) mode
    run_p.add_argument("-y", "--yolo", action="store_true", default=None,
                        dest="yolo",
                        help="Non-interactive mode: no clarification questions, no approvals, auto-continue")
    run_p.add_argument("--no-yolo", action="store_false", default=None,
                        dest="yolo",
                        help="Force interactive mode: allow clarification questions and approvals")

    # ---- install ----
    install_p = sub.add_parser("install", help="Install qq locally")

    # ---- reinstall ----
    reinstall_p = sub.add_parser("reinstall", help="Nuke existing install then reinstall from source")

    # ---- nuke ----
    nuke_p = sub.add_parser("nuke", help="Uninstall qq from the system")

    # ---- replay ----
    replay_p = sub.add_parser("replay", help="Print an events.jsonl run log")
    replay_p.add_argument("events_file", help="Path to events.jsonl")

    # ---- exec ----
    exec_p = sub.add_parser("exec", help="Run an arbitrary command through the QonQrete TUI exec mode")
    exec_p.add_argument("command", nargs=argparse.REMAINDER, help="Command and arguments")

    # ---- doctor ----
    doctor_p = sub.add_parser("doctor", help="Check system readiness or run tests")
    doctor_p.add_argument("--offline", action="store_true",
                           help="Skip anything that needs network/API")
    doctor_p.add_argument("--config", default=DEFAULT_QQ_PATH)
    doctor_p.add_argument("-t", "--tests", action="append", default=None,
                           dest="test_names",
                           help="Run specific tests (repeatable or comma-separated). Use 'all' for all tests.")

    # ---- models ----
    models_p = sub.add_parser("models", help="Show available models for the current provider")
    models_p.add_argument("--provider", default=None,
                           help="Provider to list models for (default: current config provider)")
    models_p.add_argument("--providers-config", default=DEFAULT_PROVIDERS_PATH)
    models_p.add_argument("--json", action="store_true", default=False, dest="json_output")

    # ---- providers ----
    prov_p = sub.add_parser("providers", help="List available providers")
    prov_p.add_argument("--providers-config", default=DEFAULT_PROVIDERS_PATH)
    prov_p.add_argument("--json", action="store_true", default=False, dest="json_output")

    # ---- cleanup ----
    clean_p = sub.add_parser("cleanup", help="Remove old Qq run artifacts")
    clean_p.add_argument("--repo-root", default=".", help="Target repo")
    clean_p.add_argument("--older-than", default=None,
                          help="Remove runs older than this (e.g., 7d, 24h)")

    # ---- test ----
    test_p = sub.add_parser("test", help="Run QonQrete tests")
    test_p.add_argument("tests", nargs="?", default="all",
                        help="Comma-separated tests: image-smoke,statusline,all (default: all)")
    test_p.add_argument("--output-dir", default=".",
                        help="Output directory for image-smoke artifacts")
    test_p.add_argument("--real", action="store_true",
                        help="Force real upstream image generation")

    # ---- generate-image ----
    gen_img_p = sub.add_parser("generate-image",
                                help="Generate an image using the configured image backend")
    gen_img_p.add_argument("prompt", nargs="?", default=None,
                            help="Text description of the image to generate")
    gen_img_p.add_argument("--output", "-o", default=None,
                            help="Output file path (default: repo root / generated.<fmt>)")
    gen_img_p.add_argument("--method", default=None,
                            choices=["auto", "openai", "openai_codex", "gemini", "gradio", "gradio_client"],
                            help="Image backend (default: configured routing)")
    gen_img_p.add_argument("--provider", default=None,
                            help="Agent provider used when resolving auto image routing")
    gen_img_p.add_argument("--model", default="auto",
                            help="Model name or 'auto' for backend default")
    gen_img_p.add_argument("--aspect-ratio", default="1:1",
                            choices=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
                            help="Image aspect ratio (default: 1:1)")
    gen_img_p.add_argument("--resolution", default="1K",
                            choices=["1K", "2K", "4K"],
                            help="Image resolution tier (default: 1K)")
    gen_img_p.add_argument("--width", type=int, default=0,
                            help="Pixel width (overrides aspect_ratio)")
    gen_img_p.add_argument("--height", type=int, default=0,
                            help="Pixel height (overrides aspect_ratio)")
    gen_img_p.add_argument("--quality", default="",
                            choices=["low", "medium", "high", ""],
                            help="Output quality tier (model-dependent)")
    gen_img_p.add_argument("--format", default="png",
                            choices=["png", "jpeg", "webp"],
                            help="Output image format (default: png)")
    gen_img_p.add_argument("--cfg-scale", type=float, default=7.5,
                            help="CFG scale 1.0-20.0 (default: 7.5)")
    gen_img_p.add_argument("--steps", type=int, default=20,
                            help="Denoising steps 1-50 (default: 20)")
    gen_img_p.add_argument("--seed", type=int, default=0,
                            help="Random seed (0=random)")
    gen_img_p.add_argument("--safe-mode", action="store_true",
                            help="Enable safe mode")
    gen_img_p.add_argument("--hide-watermark", action="store_true",
                            help="Compatibility flag; ignored by current backends")
    gen_img_p.add_argument("--negative-prompt", default="",
                            help="Description of what to avoid")
    gen_img_p.add_argument("--style", default="",
                            help="Style preset name")
    gen_img_p.add_argument("--json", action="store_true", default=False,
                            help="Output result as JSON")
    gen_img_p.add_argument("--meta", default=None,
                            help="Write metadata JSON to this path")

    # ---- generate-video ----
    vid_p = sub.add_parser("generate-video", help="Generate a programmatic animation/video")
    vid_p.add_argument("method", choices=["manim", "remotion", "p5"],
                       help="Animation backend")
    vid_p.add_argument("prompt", nargs="?", default="QonQrete animation",
                       help="Animation description or text")
    vid_p.add_argument("--output", "-o", default="generated.mp4")
    vid_p.add_argument("--script", default=None, help="Existing source script instead of generated starter")
    vid_p.add_argument("--width", type=int, default=1280)
    vid_p.add_argument("--height", type=int, default=720)
    vid_p.add_argument("--fps", type=int, default=30)
    vid_p.add_argument("--duration", type=int, default=5)

    # ---- chat ----
    chat_p = sub.add_parser("chat", help="Start the QonQrete browser chat interface")
    chat_p.add_argument("--host", default="127.0.0.1")
    chat_p.add_argument("--port", type=int, default=1337)
    chat_p.add_argument("--open-browser", action="store_true", default=True)
    chat_p.add_argument("--no-open-browser", action="store_false", dest="open_browser")
    chat_p.add_argument("--provider", default=None, help="Override QonQrete provider for builds")
    chat_p.add_argument("--config", default=DEFAULT_QQ_PATH)
    chat_p.add_argument("--web-port", type=int, default=None, help="briQsQope port used by chat-triggered runs")

    # ---- package ----
    pkg_p = sub.add_parser("package", help="Build and validate a release zip")
    pkg_p.add_argument("--check", action="store_true",
                        help="Verify the current tree is package-clean")
    pkg_p.add_argument("--check-archive", default=None, metavar="ZIP",
                        help="Verify a specific release zip")
    pkg_p.add_argument("--final", action="store_true",
                        help="Build and print the final artifact path prominently")
    pkg_p.add_argument("--check-upload-tree", action="store_true",
                        help="Stricter tree check (also fails on .git/ and dist/*.zip)")
    pkg_p.add_argument("--check-uploaded-zip", default=None, metavar="ZIP",
                        help="Validate an uploaded zip (alias for --check-archive)")

    # ---- verify ----
    verify_p = sub.add_parser("verify", help="Run all Qq acceptance checks (Python-based)")
    verify_p.add_argument("--root", default=None, help="Project root directory")
    verify_p.add_argument("--timeout-scale", type=float, default=1.0,
                           help="Multiplier for all timeouts")
    verify_p.add_argument("--skip-pytest", action="store_true",
                           help="Skip pytest if not installed")
    verify_p.add_argument("--label", default="", help="Banner label")
    verify_p.add_argument("--skip-package-steps", action="store_true",
                           help="Skip package build/check steps (dev tree)")
    verify_p.add_argument("--continue-on-failure", action="store_true",
                           help="Keep running after a required step fails")

    # ---- web ----
    web_p = sub.add_parser("web", help="Manage the briQsQope web dashboard")
    web_sub = web_p.add_subparsers(dest="web_command")

    web_serve = web_sub.add_parser("serve", help="Start the briQsQope dashboard")
    web_serve.add_argument("--run-root", default=None,
                            help="Path to a QonQrete run root (.qq/runs/<id>)")
    web_serve.add_argument("--control-root", default=None,
                            help="Path to a QonQrete control root (contains current-run.json). Preferred for always-on dashboard.")
    web_serve.add_argument("--repo-root", default=".",
                            help="Target repo root (default: current directory)")
    web_serve.add_argument("--host", default="0.0.0.0",
                            help="Listen address (default: 0.0.0.0)")
    web_serve.add_argument("--port", type=int, default=31337,
                            help="Listen port (default: 31337)")
    web_serve.add_argument("--open-browser", action="store_true",
                            help="Open browser after dashboard starts")
    web_serve.add_argument("--config", default=DEFAULT_QQ_PATH,
                            help="Path to qq config YAML")

    web_status = web_sub.add_parser("status", help="Show dashboard status")

    web_stop = web_sub.add_parser("stop", help="Stop the dashboard")

    # ---- runs ----
    runs_p = sub.add_parser("runs", help="Manage QonQrete runs — current, list, select")
    runs_sub = runs_p.add_subparsers(dest="runs_command")

    runs_current = runs_sub.add_parser("current", help="Show the currently linked run")
    runs_current.add_argument("--control-root", default=None,
                               help="Control root path (default: from env QONQRETE_CONTROL_ROOT or /x/qq/control)")

    runs_sessions = runs_sub.add_parser("sessions", help="List discoverable QonQrete sessions")
    runs_sessions.add_argument("--control-root", default=None,
                                help="Control root path")
    runs_sessions.add_argument("--json", action="store_true", default=False, dest="json_output")

    runs_select = runs_sub.add_parser("select", help="Switch the linked run")
    runs_select.add_argument("run_id", help="Run ID to switch to")
    runs_select.add_argument("--control-root", default=None,
                              help="Control root path")

    runs_cleanup = runs_sub.add_parser("cleanup", help="Clean up finished tmux sessions")
    runs_cleanup.add_argument("--finished-tmux", action="store_true", default=True,
                               help="Clean up managed finished tmux sessions")
    runs_cleanup.add_argument("--dry-run", action="store_true", default=False,
                               help="Show what would be removed without actually removing")
    runs_cleanup.add_argument("--control-root", default=None,
                               help="Control root path")

    # ---- ingest ----
    ingest_p = sub.add_parser("ingest", help="Manage ingest idempotency and dead-letter")
    ingest_sub = ingest_p.add_subparsers(dest="ingest_command")

    ingest_status = ingest_sub.add_parser("status", help="Show ingest idempotency status")
    ingest_status.add_argument("--control-root", default=None,
                                help="Control root path")
    ingest_status.add_argument("--source", default=None,
                                help="Filter by source (e.g., qq-trans)")

    ingest_purge = ingest_sub.add_parser("purge-stale", help="Purge stale ingest entries")
    ingest_purge.add_argument("--control-root", default=None,
                               help="Control root path")
    ingest_purge.add_argument("--source", default=None,
                               help="Filter by source")
    ingest_purge.add_argument("--older-than", default="24h",
                               help="Remove entries older than duration (default: 24h)")

    ingest_dl_list = ingest_sub.add_parser("dead-letter", help="List dead-letter entries")
    dl_sub = ingest_dl_list.add_subparsers(dest="dl_command")
    dl_list_cmd = dl_sub.add_parser("list", help="List all dead-letter entries")
    dl_list_cmd.add_argument("--control-root", default=None,
                              help="Control root path")

    ingest_retry = ingest_sub.add_parser("retry", help="Retry a dead-lettered entry")
    ingest_retry.add_argument("idempotency_key", help="Idempotency key to retry")
    ingest_retry.add_argument("--control-root", default=None,
                               help="Control root path")


    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
def _cleanup_dashboard_safe() -> None:
    """Safe dashboard cleanup that ignores errors. For atexit/signal use."""
    try:
        from .web.process import stop_dashboard
        stop_dashboard()
    except Exception:
        pass


def _install_dashboard_signal_handlers():
    """Install SIGTERM/SIGINT handlers so dashboard is cleaned up on kill.
    
    When the TUI sends SIGKILL we can't trap it, but SIGTERM (normal kill)
    and SIGINT (Ctrl+C) are catchable and we clean up here.
    """
    import signal as _signal

    def _handler(signum, frame):
        _cleanup_dashboard_safe()
        # Re-raise with default handler to actually exit
        _signal.signal(signum, _signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (_signal.SIGTERM, _signal.SIGINT):
        try:
            _signal.signal(sig, _handler)
        except Exception:
            pass

def _cmd_run(args: argparse.Namespace) -> int:
    repo_root = args.repo_root or "."

    # Resolve a bare task name (e.g. "smoke") to tasks/<name>.md so the
    # documented `python3 -m qq run smoke` invocation works. The literal path is
    # tried first; a bare name with no separator/extension is then resolved
    # against tasks/ relative to repo_root, then the current working directory.
    task_file = args.task_file
    if not os.path.isfile(task_file):
        name = task_file
        has_sep = "/" in name or "\\" in name or ":" in name
        if not has_sep and not os.path.splitext(name)[1]:
            candidates = [
                os.path.join(repo_root, "tasks", name + ".md"),
                os.path.join(os.getcwd(), "tasks", name + ".md"),
            ]
            resolved = next((c for c in candidates if os.path.isfile(c)), None)
            if resolved is not None:
                task_file = resolved
    if not os.path.isfile(task_file):
        print(f"error: task file not found: {args.task_file}", file=sys.stderr)
        return 2


    # Make sure the target directory exists before we write .qqignore into it.
    os.makedirs(os.path.abspath(repo_root), exist_ok=True)

    # Ensure .qqignore exists in the target directory so agents skip
    # Qq's own artifacts (.qq/, .codeseeq/, .env) when reading the project
    _ensure_qqignore(os.path.abspath(repo_root))

    with open(task_file, "r", encoding="utf-8") as fh:
        task_text = fh.read()

    # Resolve stream_agent_output: check if the flag was explicitly set
    stream_flag = args.stream_agent_output_flag
    if stream_flag is None:
        # Not set via CLI; let resolve_config read from config file (defaults to True)
        stream_agent_output = None
    else:
        stream_agent_output = stream_flag

    # ---- Model-type validation for thinking vs non-thinking models ----
    def _is_thinking_model(model_name: str) -> bool:
        """Check if a model name is a thinking variant."""
        return "-thinking" in model_name.lower()

    def _warn_if_non_thinking_reasoning(model_name: str, reasoning_val: str) -> None:
        """Warn if reasoning effort is set on a non-thinking model."""
        if reasoning_val and not _is_thinking_model(model_name):
            print(
                f"warning: --reasoning/-r '{reasoning_val}' is only valid for thinking models, "
                f"but model '{model_name}' is not a -thinking variant. Ignoring.",
                file=sys.stderr,
            )

    def _warn_if_thinking_temperature_top_p(model_name: str, temp, top_p) -> None:
        """Warn if temperature/top_p is set on a thinking model."""
        if _is_thinking_model(model_name):
            if temp is not None:
                print(
                    f"warning: --temperature/-C '{temp}' is only valid for non-thinking models, "
                    f"but model '{model_name}' is a -thinking variant. Ignoring.",
                    file=sys.stderr,
                )
            if top_p is not None:
                print(
                    f"warning: --top_p/-P '{top_p}' is only valid for non-thinking models, "
                    f"but model '{model_name}' is a -thinking variant. Ignoring.",
                    file=sys.stderr,
                )

    # Collect all configured models for validation
    _configured_models = [
        # These will come from resolve_config, so we parse the CLI args first
        # Actually, we validate after resolve_config returns the resolved models
    ]

    # Validate temperature and top_p ranges
    temperature = args.temperature
    top_p_val = args.top_p
    if temperature is not None and not (0.0 <= temperature <= 2.0):
        print(
            f"error: --temperature/-C must be between 0.0 and 2.0, got {temperature}",
            file=sys.stderr,
        )
        return 2
    if top_p_val is not None and not (0.0 < top_p_val <= 1.0):
        print(
            f"error: --top_p/-P must be between 0.0 (exclusive) and 1.0, got {top_p_val}",
            file=sys.stderr,
        )
        return 2

    cfg = resolve_config(
        qq_path=args.config,
        providers_path=args.providers_config,
        provider=args.provider,
        codeseeq_bin=args.codeseeq_bin,
        runtime_mode=args.runtime_mode,
        bridge_mode=args.bridge_mode,
        briq_sensitivity=args.briq_sensitivity,
        max_cycles=args.max_cycles,
        max_time_seconds=args.max_time,
        max_parallel_build_groups=args.max_parallel_build_groups,
        repo_root=repo_root,
        run_root=args.run_root,
        harness_checks=args.checks,
        review_on_harness_failure=args.review_on_harness_failure,
        allow_dirty=args.allow_dirty,
        dry_run=args.dry_run,
        verbose=args.verbose,
        json_output=args.json_output,
        no_color=args.no_color,
        stream_agent_output=stream_agent_output,
        stream_mode=args.stream_mode,
        stream_stderr=args.stream_stderr_flag if args.stream_stderr_flag is not None else (stream_agent_output if stream_agent_output is not None else True),
        stream_indicator=args.stream_indicator,
        show_prompts=args.show_prompts,
        stream_status_line=args.stream_status_line,
        stream_line_prefix=args.stream_line_prefix,
        agent_color_output=args.agent_color_output,
        no_repo=args.no_repo,
        reasoning_effort=args.reasoning_effort,
        temperature=temperature,
        top_p_val=top_p_val,
        web_enabled=args.web_enabled,
        web_host=args.web_host,
        web_port=args.web_port,
        web_open_browser=args.web_open_browser,
        web_publish_level=args.web_publish_level,
        web_hard_fail=args.web_hard_fail,
    )

    # Resolve the image backend once per run so every agent/subprocess uses
    # the same configured method (and `qq generate-image` behaves identically).
    image_method = cfg.image_backend.provider
    if image_method == "auto":
        image_method = {"codex": "openai", "openai": "openai",
                        "gemini": "gemini", "gemini-cli": "gemini"}.get(cfg.provider, "gradio")
    os.environ["QQ_IMAGE_METHOD"] = image_method
    os.environ["QQ_IMAGE_PROVIDER"] = cfg.provider

    # Validate model-type constraints against reasoning/temperature/top_p
    _all_models = [
        ("qlarifier", cfg.model_qlarifier),
        ("instruqtor", cfg.model_instruqtor),
        ("construqtor", cfg.model_construqtor),
        ("inspeqtor", cfg.model_inspeqtor),
    ]
    for role, model in _all_models:
        _warn_if_non_thinking_reasoning(model, args.reasoning_effort)
        _warn_if_thinking_temperature_top_p(model, temperature, top_p_val)

    run_root = cfg.run_root or default_run_root(cfg.repo_root)
    os.makedirs(run_root, exist_ok=True)
    run_id = os.path.basename(run_root)

    adapter = get_adapter(
        cfg.provider,
        codeseeq_path=cfg.codeseeq_bin,
        runtime_mode=cfg.runtime_mode,
        bridge_mode=cfg.bridge_mode,
        no_repo=cfg.no_repo,
    )

    qcfg = QontrollerConfig(
        repo_root=os.path.abspath(repo_root),
        run_root=run_root,
        run_id=run_id,
        model_qlarifier=cfg.model_qlarifier,
        model_instruqtor=cfg.model_instruqtor,
        model_construqtor=cfg.model_construqtor,
        model_inspeqtor=cfg.model_inspeqtor,
        briq_sensitivity=cfg.briq_sensitivity,
        max_cycles=cfg.max_cycles,
        max_time_seconds=cfg.max_time_seconds,
        max_parallel_build_groups=cfg.max_parallel_build_groups,
        harness_commands=[c.command for c in cfg.harness_checks],
        review_on_harness_failure=cfg.review_on_harness_failure,
        allow_dirty=cfg.allow_dirty,
        stream_agent_output=cfg.stream_agent_output,
        stream_mode=cfg.stream_mode,
        stream_stderr=cfg.stream_stderr,
        stream_indicator=cfg.stream_indicator,
        show_prompts=cfg.show_prompts,
        stream_status_line=cfg.stream_status_line,
        stream_line_prefix=cfg.stream_line_prefix,
        no_color=cfg.no_color,
        agent_color_output=cfg.agent_color_output,
        no_repo=cfg.no_repo,
        reasoning_effort=cfg.reasoning_effort,
        reasoning_qlarifier=cfg.reasoning_qlarifier,
        reasoning_instruqtor=cfg.reasoning_instruqtor,
        reasoning_construqtor=cfg.reasoning_construqtor,
        reasoning_inspeqtor=cfg.reasoning_inspeqtor,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
    )
    # Resolve YOLO mode: CLI flag > env var > config > default
    yolo_val = args.yolo
    if yolo_val is None:
        # Check env vars
        qyolo = os.environ.get("QONQRETE_YOLO", "")
        if qyolo in ("1", "true", "yes"):
            yolo_val = True
        elif qyolo in ("0", "false", "no"):
            yolo_val = False
    if yolo_val is None:
        # Check config
        try:
            yaml_path = args.config or os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "config", "qq.yaml"))
            if os.path.isfile(yaml_path):
                import yaml
                with open(yaml_path, 'r') as f:
                    raw = yaml.safe_load(f) or {}
                qc = raw.get("qonqrete", {})
                if isinstance(qc, dict) and "yolo" in qc:
                    yolo_val = bool(qc["yolo"])
        except Exception:
            pass
    # Default: manual CLI runs default to YOLO False (preserve interactive behavior)
    if yolo_val is None:
        yolo_val = False
    qcfg.yolo = yolo_val
    # Attach web config as attributes for Qontroller
    qcfg.web_enabled = cfg.qq_web.enabled
    qcfg.web_start_with_run = cfg.qq_web.start_with_run
    qcfg.web_host = cfg.qq_web.host
    qcfg.web_port = cfg.qq_web.port
    qcfg.web_open_browser = cfg.qq_web.open_browser
    qcfg.web_hard_fail = cfg.qq_web.hard_fail_on_dashboard_error
    qcfg.web_started = False

    # Web dashboard
    if cfg.qq_web.enabled and cfg.qq_web.start_with_run:
        from .web.process import start_dashboard, find_dashboard_dir
        dashboard_dir = find_dashboard_dir()
        if dashboard_dir:
            web_port = cfg.qq_web.port
            web_host = cfg.qq_web.host
            try:
                web_pid = start_dashboard(
                    repo_root=os.path.abspath(repo_root),
                    run_root=run_root,
                    host=web_host,
                    port=web_port,
                    open_browser=cfg.qq_web.open_browser,
                    dashboard_dir=dashboard_dir,
                )
                if web_pid:
                    qcfg.web_started = True
                    # Register atexit handler to ensure dashboard cleanup
                    atexit.register(_cleanup_dashboard_safe)
                    _install_dashboard_signal_handlers()
                    if cfg.verbose:
                        print(f"briQsQope: https://web.qonqrete.sh (PID {web_pid})")
                elif cfg.qq_web.hard_fail_on_dashboard_error:
                    print("error: briQsQope dashboard failed to start and hard_fail is enabled.", file=sys.stderr)
                    return 1
                else:
                    if cfg.verbose:
                        print("warning: briQsQope dashboard startup failed, continuing without it.", file=sys.stderr)
            except Exception as exc:
                if cfg.qq_web.hard_fail_on_dashboard_error:
                    print(f"error: briQsQope dashboard startup exception: {exc}", file=sys.stderr)
                    return 1
                if cfg.verbose:
                    print(f"warning: briQsQope dashboard startup error: {exc}", file=sys.stderr)
        elif cfg.qq_web.hard_fail_on_dashboard_error:
            print("error: qq/web/ directory not found and hard_fail is enabled.", file=sys.stderr)
            return 1
    elif not cfg.qq_web.enabled:
        if cfg.verbose:
            print("briQsQope: disabled (qq_web.enabled=false)")

    if cfg.verbose:
        print(f"Run ID: {run_id}")
        print(f"Run root: {run_root}")
        print(f"Provider: {cfg.provider}")

    try:
        state = run_qontroller(
            task_text, adapter, qcfg, _ask_human,
            on_event=lambda msg: print(f"[qq] {msg}", flush=True),
        )

        print(f"\nFinal status: {state.status.value} (cycle {state.cycle})")
        print(f"Run artifacts: {run_root}")
        if state.status.value == "aborted":
            print("Run ABORTED — limit reached. inspeQtor never returned FULLY_DONE.")
        return 0 if state.status.value == "done" else 1
    finally:
        # Stop the briQsQope dashboard if we started it
        if qcfg.web_started:
            from .web.process import stop_dashboard
            # Keep briQsQope alive briefly after FULLY_DONE so the terminal
            # state overlay is actually visible before the dashboard closes.
            if 'state' in locals() and getattr(state, 'status', None) is not None and state.status.value == "done":
                time.sleep(3.0)
            stop_dashboard()
            if cfg.verbose:
                print("briQsQope: dashboard stopped")


def _cmd_install(args: argparse.Namespace) -> int:
    """Install qq locally using install-qq-local.sh."""
    if not os.path.isfile(_INSTALL_SCRIPT):
        print(f"error: install script not found: {_INSTALL_SCRIPT}", file=sys.stderr)
        return 1
    print("→ Installing QonQrete locally...")
    result = subprocess.run(["bash", _INSTALL_SCRIPT], cwd=os.path.dirname(_INSTALL_SCRIPT))
    return result.returncode


def _cmd_reinstall(args: argparse.Namespace) -> int:
    """Nuke existing installation then reinstall."""
    # First nuke
    rc = _cmd_nuke_impl()
    if rc != 0:
        print("warning: nuke step had issues, continuing anyway...", file=sys.stderr)
    # Then install
    return _cmd_install(args)


def _cmd_nuke_impl() -> int:
    """Uninstall the qq wrapper from the system (not from the repo)."""
    bin_dir = os.environ.get("QQ_BIN_DIR", os.path.expanduser("~/.local/bin"))
    removed = False
    for binary in ["qq"]:
        path = os.path.join(bin_dir, binary)
        if os.path.isfile(path) or os.path.islink(path):
            try:
                os.remove(path)
                print(f"  Removed: {path}")
                removed = True
            except OSError as e:
                print(f"  Failed to remove {path}: {e}", file=sys.stderr)
    if not removed:
        print(f"  No qq binary found in {bin_dir}")
    return 0


def _cmd_nuke(args: argparse.Namespace) -> int:
    """Command-line handler for nuke."""
    print("→ Nuking QonQrete installation...")
    return _cmd_nuke_impl()


def _cmd_replay(args: argparse.Namespace) -> int:
    from .eventlog import EventLog
    if not os.path.exists(args.events_file):
        print(f"error: events file not found: {args.events_file}", file=sys.stderr)
        return 1
    for event in EventLog.replay(args.events_file):
        print(event)
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Check system readiness or run tests.

    With --tests/-t: runs specified tests from the tests/ directory.
    """
    # If tests are requested, run them
    if args.test_names:
        return _run_tests(args.test_names)
    return _run_doctor_checks(args)


def _run_tests(test_names: ListType[str]) -> int:
    """Run the specified test files."""
    tests_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "tests"))

    # Flatten comma-separated entries
    all_names: ListType[str] = []
    for item in test_names:
        for part in item.split(","):
            part = part.strip()
            if part:
                all_names.append(part)

    if not all_names:
        print("No test names specified.", file=sys.stderr)
        return 1

    # If "all" is in the list, run all tests
    if "all" in all_names:
        test_files = sorted([
            os.path.join(tests_dir, f)
            for f in os.listdir(tests_dir)
            if f.startswith("test_") and f.endswith(".py")
        ])
    else:
        test_files = []
        for name in all_names:
            # Allow specifying with or without test_ prefix and .py suffix
            if name.endswith(".py"):
                test_path = os.path.join(tests_dir, name)
            elif name.startswith("test_"):
                test_path = os.path.join(tests_dir, f"{name}.py")
            else:
                test_path = os.path.join(tests_dir, f"test_{name}.py")

            if os.path.isfile(test_path):
                test_files.append(test_path)
            else:
                print(f"warning: test file not found: {test_path}", file=sys.stderr)

    if not test_files:
        print("No test files found to run.", file=sys.stderr)
        return 1

    print(f"Running {len(test_files)} test file(s)...")
    # Run with pytest if available, otherwise python -m unittest
    import shutil
    if shutil.which("pytest"):
        cmd = ["pytest", "-v"] + test_files
    else:
        cmd = [sys.executable, "-m", "pytest", "-v"] + test_files

    result = subprocess.run(cmd, cwd=os.path.dirname(tests_dir))
    return result.returncode


def _run_doctor_checks(args: argparse.Namespace) -> int:
    """Original doctor: check system readiness."""
    import platform
    import shutil
    import sys as _sys

    ok = True
    all_ok = True

    def check(label: str, condition: bool, detail: str = "",
              warn_only: bool = False) -> bool:
        nonlocal ok, all_ok
        if condition:
            print(f"  [OK]    {label}")
        elif warn_only:
            print(f"  [WARN]  {label}  ({detail})" if detail else f"  [WARN]  {label}")
        else:
            print(f"  [FAIL]  {label}  ({detail})" if detail else f"  [FAIL]  {label}")
            ok = False
            all_ok = False
        return condition

    print("Qq Doctor")
    print("=============")
    if args.offline:
        print("(offline mode — only local/offline readiness)")
    print()

    pyv = _sys.version_info
    check(f"Python {pyv.major}.{pyv.minor}.{pyv.micro}", pyv >= (3, 9),
          "Python 3.9+ required")

    git = shutil.which("git")
    check("git available", bool(git), "install git")

    try:
        import yaml  # noqa: F401
        check("PyYAML available", True)
    except ImportError:
        check("PyYAML available", False, "pip install PyYAML")

    check(f"Qq config: {args.config}", os.path.exists(args.config))

    prov_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "config", "providers.yaml"))
    check(f"Providers manifest: {prov_path}", os.path.exists(prov_path))

    try:
        from .config import load_providers
        providers = load_providers(prov_path)
        check(f"Providers loaded: {len(providers)}", len(providers) > 0,
              "no providers found in manifest")
    except Exception as e:
        check("Provider manifest loadable", False, str(e))

    codeseeq_expected = os.path.normpath(os.path.join(os.path.dirname(__file__), "codeseeq", "codeseeq"))
    if os.path.isfile(codeseeq_expected) and os.access(codeseeq_expected, os.X_OK):
        check(f"CodeSeeq binary: {codeseeq_expected}", True)
    else:
        check(f"CodeSeeq binary: {codeseeq_expected}", False,
              "install CodeSeeq into ./qq/codeseeq", warn_only=args.offline)

    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    check("API key set (DEEPSEEK_API_KEY or OPENAI_API_KEY)", bool(key),
          "Set DEEPSEEK_API_KEY environment variable",
          warn_only=args.offline)

    if not args.offline:
        try:
            csq = _find_codeseeq_binary()
            try:
                r = subprocess.run([csq, "doctor"], capture_output=True,
                                   text=True, timeout=30)
                check("codeseeq doctor", r.returncode == 0,
                      r.stderr[:200] if r.stderr else "")
            except Exception as e:
                check("codeseeq doctor", False, str(e))
        except FileNotFoundError:
            pass

    print()
    if all_ok:
        print("All checks passed.")
    elif ok:
        print("All checks passed (some warnings).")
    else:
        print("Some checks FAILED — see above.")
    return 0 if all_ok else 1


def _cmd_models(args: argparse.Namespace) -> int:
    """Show available models for the current or specified provider."""
    import json

    providers = load_providers(args.providers_config)

    # Determine provider
    if args.provider:
        provider_name = args.provider
    else:
        # Read from qq.yaml
        try:
            import yaml
            raw = {}
            qq_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "config", "qq.yaml"))
            if os.path.exists(qq_path):
                with open(qq_path, "r") as f:
                    raw = yaml.safe_load(f) or {}
            provider_name = raw.get("provider", "codeseeq")
        except Exception:
            provider_name = "codeseeq"

    if provider_name not in providers:
        print(f"Unknown provider: {provider_name}", file=sys.stderr)
        print(f"Known providers: {', '.join(sorted(providers))}", file=sys.stderr)
        return 1

    pd = providers[provider_name]

    if args.json_output:
        print(json.dumps({
            "provider": provider_name,
            "default_model": pd.default_model,
            "models": pd.models,
        }, indent=2))
        return 0

    print(f"Provider: {provider_name}")
    print(f"Default model: {pd.default_model}")
    print(f"Available models ({len(pd.models)}):")
    for m in pd.models:
        marker = " (default)" if m == pd.default_model else ""
        print(f"  - {m}{marker}")
    print()
    print(f"Supports thinking mode: {pd.supports_thinking_mode}")
    return 0


def _cmd_providers(args: argparse.Namespace) -> int:
    import json

    providers = load_providers(args.providers_config)
    if args.json_output:
        out = {n: {
            "status": p.status, "kind": p.kind,
            "models": p.models, "default_model": p.default_model,
            "supports_thinking_mode": p.supports_thinking_mode,
        } for n, p in providers.items()}
        print(json.dumps(out, indent=2))
        return 0

    print(f"{'Provider':<20} {'Status':<14} {'Models'}")
    print("-" * 60)
    for name, pd in providers.items():
        status = pd.status.upper() if pd.status == "implemented" else pd.status
        models = ", ".join(pd.models[:3])
        if len(pd.models) > 3:
            models += f" (+{len(pd.models)-3})"
        print(f"{name:<20} {status:<14} {models}")
    return 0


def _cmd_cleanup(args: argparse.Namespace) -> int:
    import glob
    import shutil

    repo = os.path.abspath(args.repo_root)
    runs_dir = os.path.join(repo, ".qq", "runs")

    if not os.path.isdir(runs_dir):
        print(f"No .qq/runs directory in {repo}")
        return 0

    if args.older_than:
        dur = _parse_duration(args.older_than)
        if dur is None:
            print(f"error: cannot parse duration: {args.older_than} (use e.g. 7d, 24h)",
                  file=sys.stderr)
            return 1
        cutoff = datetime.now() - dur
        removed = 0
        for run_dir in os.listdir(runs_dir):
            full = os.path.join(runs_dir, run_dir)
            if os.path.isdir(full):
                mtime = datetime.fromtimestamp(os.path.getmtime(full))
                if mtime < cutoff:
                    print(f"Removing: {full}")
                    shutil.rmtree(full, ignore_errors=True)
                    removed += 1
        print(f"Removed {removed} run(s) older than {args.older_than}.")
    else:
        print("Use --older-than to specify which runs to remove (e.g., --older-than 7d)")
        existing = [d for d in os.listdir(runs_dir) if os.path.isdir(os.path.join(runs_dir, d))]
        print(f"Found {len(existing)} run(s). Nothing removed.")
    return 0


def _parse_duration(s: str) -> Optional[timedelta]:
    s = s.strip().lower()
    if s.endswith("d"):
        try:
            return timedelta(days=int(s[:-1]))
        except ValueError:
            return None
    if s.endswith("h"):
        try:
            return timedelta(hours=int(s[:-1]))
        except ValueError:
            return None
    if s.endswith("m"):
        try:
            return timedelta(minutes=int(s[:-1]))
        except ValueError:
            return None
    return None


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Handle the `qq ingest` subcommand."""
    if args.ingest_command == "status":
        return _cmd_ingest_status(args)
    elif args.ingest_command == "purge-stale":
        return _cmd_ingest_purge_stale(args)
    elif args.ingest_command == "dead-letter":
        return _cmd_ingest_dead_letter(args)
    elif args.ingest_command == "retry":
        return _cmd_ingest_retry(args)
    else:
        print("qq ingest: missing command. Usage: qq ingest {status|purge-stale|dead-letter list|retry}", file=sys.stderr)
        return 1


def _cmd_runs(args: argparse.Namespace) -> int:
    """Handle the `qq runs` subcommand."""
    if args.runs_command == "current":
        return _cmd_runs_current(args)
    elif args.runs_command == "sessions":
        return _cmd_runs_sessions(args)
    elif args.runs_command == "select":
        return _cmd_runs_select(args)
    else:
        print("qq runs: missing command. Usage: qq runs {current,sessions,select}", file=sys.stderr)
        return 1


def _get_control_root(args_control_root):
    """Resolve control root from args, env, or default."""
    if args_control_root:
        return os.path.abspath(os.path.expanduser(args_control_root))
    env_root = os.environ.get("QONQRETE_CONTROL_ROOT", "")
    if env_root:
        return os.path.abspath(os.path.expanduser(env_root))
    return "/x/qq/control"


def _cmd_runs_current(args: argparse.Namespace) -> int:
    """Show the currently linked run, active executor, and pending run."""
    import json as _json
    control_root = _get_control_root(getattr(args, "control_root", None))

    current_run_path = os.path.join(control_root, "current-run.json")
    active_run_path = os.path.join(control_root, "active-run.json")
    pending_run_path = os.path.join(control_root, "pending-run.json")

    print(f"Control root: {control_root}")
    print()

    # Linked run (dashboard selection)
    if os.path.isfile(current_run_path):
        try:
            with open(current_run_path, "r") as f:
                cr = _json.load(f)
            print("=== Linked run (dashboard) ===")
            print(f"  Run ID:       {cr.get('run_id', '(none)')}")
            print(f"  State:        {cr.get('state', 'unknown')}")
            print(f"  Runner:       {cr.get('runner', '(none)')}")
            print(f"  Run root:     {cr.get('run_root', '(none)')}")
            print(f"  Events path:  {cr.get('events_path', '(none)')}")
            if cr.get("selection_reason"):
                print(f"  Selected:     {cr.get('selection_reason')} at {cr.get('selected_at', '')}")
            if cr.get("tmux_session"):
                print(f"  tmux:         {cr['tmux_session']}")
            print()
        except (_json.JSONDecodeError, OSError) as e:
            print(f"Error reading current-run.json: {e}", file=sys.stderr)
            print()
    else:
        print("=== Linked run (dashboard) ===")
        print("  No current-run.json exists.")
        print()

    # Active executor
    if os.path.isfile(active_run_path):
        try:
            with open(active_run_path, "r") as f:
                ar = _json.load(f)
            print("=== Active executor ===")
            print(f"  Run ID:       {ar.get('run_id', '(none)')}")
            print(f"  State:        {ar.get('state', 'unknown')}")
            print(f"  Runner:       {ar.get('runner', '(none)')}")
            print(f"  Run root:     {ar.get('run_root', '(none)')}")
            if ar.get("tmux_session"):
                print(f"  tmux:         {ar['tmux_session']}")
            if ar.get("pid"):
                print(f"  PID:          {ar['pid']}")
            print()
        except (_json.JSONDecodeError, OSError):
            pass
    else:
        print("=== Active executor ===")
        print("  No active-run.json exists (no executor running).")
        print()

    # Latest pending run
    if os.path.isfile(pending_run_path):
        try:
            with open(pending_run_path, "r") as f:
                pr = _json.load(f)
            print("=== Latest pending run ===")
            print(f"  Run ID:       {pr.get('run_id', '(none)')}")
            print(f"  State:        {pr.get('state', 'unknown')}")
            print(f"  Created:      {pr.get('created_at', '')}")
            print()
        except (_json.JSONDecodeError, OSError):
            pass
    else:
        print("=== Latest pending run ===")
        print("  No pending run.")
        print()

    return 0



def _cmd_runs_sessions(args: argparse.Namespace) -> int:
    """List discoverable QonQrete sessions using the canonical registry."""
    import json as _json

    control_root = _get_control_root(getattr(args, "control_root", None))

    try:
        from qq.web.run_registry import (
            load_latest_run_records, load_latest_tmux_records,
            merge_run_sources, newest_run, build_session_entry,
            sort_sessions_newest_first, atomic_read_json,
        )
    except ImportError:
        print("Error: run_registry module not available", file=sys.stderr)
        return 1

    # Load state
    cr = atomic_read_json(control_root, "current-run.json")
    ar = atomic_read_json(control_root, "active-run.json")
    pr = atomic_read_json(control_root, "pending-run.json")

    folded = load_latest_run_records(control_root)
    tmux_recs = load_latest_tmux_records(control_root)

    # Discover run directories
    run_dirs = {}
    runs_root = os.environ.get("QONQRETE_RUNS_ROOT", "/x/qq/runs")
    runs_root = os.path.expanduser(runs_root)
    if os.path.isdir(runs_root):
        try:
            for d in sorted(os.listdir(runs_root), reverse=True):
                rd = os.path.join(runs_root, d)
                if not os.path.isdir(rd):
                    continue
                markers = ["events.jsonl", "state/plan.json", "state/final.json",
                           "task.md", "task.json", "runner.finished",
                           "runner.failed.json"]
                if any(os.path.isfile(os.path.join(rd, m)) for m in markers):
                    run_dirs[d] = {
                        "run_id": d,
                        "run_root": rd,
                        "events_path": os.path.join(rd, "events.jsonl")
                            if os.path.isfile(os.path.join(rd, "events.jsonl")) else "",
                    }
        except OSError:
            pass

    # Live tmux
    live_tmux = {}
    try:
        import subprocess as _sp
        result = _sp.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            for name in result.stdout.strip().split("\n"):
                name = name.strip()
                if not name:
                    continue
                if name.startswith("qonqrete-") or name.startswith("qq-"):
                    rid = name.replace("qonqrete-", "").replace("qq-", "")
                    live_tmux[name] = {
                        "run_id": rid,
                        "tmux_session": name,
                        "attach_command": f"tmux attach -t {name}",
                        "managed": False,
                        "tmux_alive": True,
                    }
    except (FileNotFoundError, Exception):
        pass

    merged = merge_run_sources(
        current_run_pointer=cr,
        active_run_pointer=ar,
        pending_run_pointer=pr,
        folded_history=folded,
        run_directories=run_dirs,
        tmux_records=tmux_recs,
        live_tmux_sessions=live_tmux,
        control_root=control_root,
    )

    sessions = []
    for rid, entry in merged.items():
        sessions.append(build_session_entry(entry))

    sessions = sort_sessions_newest_first(sessions)

    newest = newest_run(merged)

    if args.json_output:
        resp = {
            "ok": True,
            "control_root": control_root,
            "newest_run_id": newest.get("run_id") if newest else None,
            "linked_run_id": cr.get("run_id") if cr else None,
            "active_run_id": ar.get("run_id") if ar else None,
            "pending_run_id": pr.get("run_id") if pr else None,
            "sessions": sessions,
        }
        print(_json.dumps(resp, indent=2, default=str))
        return 0

    print(f"Control root: {control_root}")
    if newest:
        print(f"Newest run:    {newest['run_id']}")
    if cr:
        print(f"Linked run:    {cr.get('run_id', '(none)')}")
    if ar:
        print(f"Active run:    {ar.get('run_id', '(none)')}")
    if pr:
        print(f"Pending run:   {pr.get('run_id', '(none)')}")
    print(f"Sessions:      {len(sessions)}")
    print()

    for s in sessions:
        badges = []
        if s.get("linked"):
            badges.append("LINKED")
        if s.get("active"):
            badges.append("ACTIVE")
        if s.get("pending"):
            badges.append("PENDING")
        if s.get("terminal"):
            badges.append("TERMINAL")
        badge_str = " [" + ", ".join(badges) + "]" if badges else ""

        print(f"  {s['run_id']}{badge_str}")
        print(f"    State:        {s.get('state', 'unknown')}")
        print(f"    Runner:       {s.get('runner', '(none)')}")
        print(f"    Source:       {s.get('source', 'unknown')}")
        if s.get("run_root"):
            print(f"    Run root:     {s['run_root']}")
        if s.get("tmux_session"):
            print(f"    tmux:         {s['tmux_session']}")
            if s.get("attach_command"):
                print(f"    Attach:       {s['attach_command']}")
        if s.get("tmux_alive"):
            print("    tmux alive:   yes")
        print()

    return 0



def _cmd_runs_cleanup(args: argparse.Namespace) -> int:
    """Clean up managed finished tmux sessions safely."""
    import json as _json
    import subprocess as _sp

    control_root = _get_control_root(getattr(args, "control_root", None))
    dry_run = getattr(args, "dry_run", False)

    print(f"Control root: {control_root}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Discover tmux sessions
    try:
        result = _sp.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            print("No tmux sessions found (or tmux not running).")
            return 0
    except FileNotFoundError:
        print("tmux is not installed.")
        return 0
    except Exception as e:
        print(f"Error listing tmux sessions: {e}")
        return 1

    sessions = result.stdout.strip().split("\n")
    cleaned = 0
    skipped = 0

    for name in sessions:
        name = name.strip()
        if not name:
            continue
        if not (name.startswith("qonqrete-") or name.startswith("qq-")):
            continue

        # Check if managed
        try:
            mgr = _sp.run(
                ["tmux", "show-options", "-v", "-t", name, "@qonqrete_managed"],
                capture_output=True, text=True, timeout=2,
            )
            is_managed = mgr.returncode == 0 and mgr.stdout.strip() == "1"
        except Exception:
            is_managed = False

        # Check if terminal
        is_terminal = False
        run_id = name.replace("qonqrete-", "").replace("qq-", "")

        # Check runs.jsonl for terminal state
        try:
            from qq.web.run_registry import load_latest_run_records, is_terminal_state
            folded = load_latest_run_records(control_root)
            if run_id in folded:
                state = folded[run_id].get("state", "")
                if is_terminal_state(state):
                    is_terminal = True
        except ImportError:
            pass

        # Also check run root for terminal markers
        if not is_terminal:
            runs_root = os.environ.get("QONQRETE_RUNS_ROOT", "/x/qq/runs")
            runs_root = os.path.expanduser(runs_root)
            candidate = os.path.join(runs_root, run_id)
            if os.path.isdir(candidate):
                if os.path.isfile(os.path.join(candidate, "runner.finished")):
                    is_terminal = True

        if not is_terminal and is_managed:
            # Managed but not terminal - could be active. Only clean if pane is dead.
            try:
                pane_dead = _sp.run(
                    ["tmux", "display-message", "-t", name, "-p", "#{pane_dead}"],
                    capture_output=True, text=True, timeout=2,
                )
                if pane_dead.returncode == 0 and pane_dead.stdout.strip() == "1":
                    is_terminal = True  # Pane is dead, safe to clean
            except Exception:
                pass

        if is_terminal:
            if is_managed:
                print(f"  [CLEAN] {name} (managed, terminal)")
                if not dry_run:
                    try:
                        _sp.run(
                            ["tmux", "kill-session", "-t", name],
                            capture_output=True, timeout=5,
                        )
                    except Exception as e:
                        print(f"    Error killing session: {e}")
                        skipped += 1
                        continue
                cleaned += 1
            else:
                # Legacy: prefix-only match, must have resolved terminal proof
                print(f"  [SKIP] {name} (legacy/unmanaged, needs resolved proof)")
                skipped += 1
        else:
            print(f"  [SKIP] {name} (not terminal)")

    print()
    if dry_run:
        print(f"Would clean: {cleaned} sessions")
    else:
        print(f"Cleaned: {cleaned} sessions")
    print(f"Skipped: {skipped} sessions")
    return 0



def _cmd_runs_select(args: argparse.Namespace) -> int:
    """Switch the dashboard-linked run (current-run.json only).

    Does NOT modify active-run.json or pending-run.json.
    This is a dashboard navigation action, not an executor action.
    """
    control_root = _get_control_root(getattr(args, "control_root", None))
    run_id = args.run_id

    import json as _json

    current_run_path = os.path.join(control_root, "current-run.json")

    # Check if already linked
    if os.path.isfile(current_run_path):
        try:
            with open(current_run_path, "r") as f:
                cr = _json.load(f)
            if cr.get("run_id") == run_id:
                print(f"Already linked to run {run_id}")
                return 0
        except Exception:
            pass

    # Try to find the run in various sources
    found = False
    found_entry = {}
    found_state = "unknown"

    # Check runs.jsonl (folded history via registry)
    try:
        from qq.web.run_registry import load_latest_run_records
        folded = load_latest_run_records(control_root)
        if run_id in folded:
            fh = folded[run_id]
            found = True
            found_entry = {
                "run_id": run_id,
                "run_root": fh.get("run_root", ""),
                "events_path": fh.get("events_path", ""),
                "runner": fh.get("runner", ""),
                "tmux_session": fh.get("tmux_session", ""),
                "attach_command": fh.get("attach_command", ""),
                "yolo": fh.get("yolo"),
            }
            found_state = fh.get("state", "unknown")
    except ImportError:
        pass

    # Check runs_root directories
    if not found:
        runs_root = os.environ.get("QONQRETE_RUNS_ROOT", "/x/qq/runs")
        runs_root = os.path.expanduser(runs_root)
        if os.path.isdir(runs_root):
            candidate = os.path.join(runs_root, run_id)
            if os.path.isdir(candidate):
                markers = ["events.jsonl", "plan.json", "final.json", "task.md", "task.json",
                           "runner.finished", "runner.failed.json"]
                for m in markers:
                    if m in ("plan.json", "final.json"):
                        mp = os.path.join(candidate, "state", m)
                    else:
                        mp = os.path.join(candidate, m)
                    if os.path.isfile(mp):
                        found = True
                        found_entry = {
                            "run_id": run_id,
                            "run_root": candidate,
                            "events_path": os.path.join(candidate, "events.jsonl"),
                            "state": "unknown",
                        }
                        if os.path.isfile(os.path.join(candidate, "runner.finished")):
                            found_state = "finished"
                            try:
                                with open(os.path.join(candidate, "runner.exit_code")) as ef:
                                    found_entry["exit_code"] = int(ef.read().strip())
                            except Exception:
                                pass
                        break

    # Check tmux
    if not found:
        try:
            import subprocess as _sp
            for prefix in ("qonqrete-", "qq-"):
                sname = f"{prefix}{run_id}"
                result = _sp.run(["tmux", "has-session", "-t", sname],
                                 capture_output=True, timeout=2)
                if result.returncode == 0:
                    found = True
                    found_state = "running"
                    found_entry = {
                        "run_id": run_id,
                        "state": "running",
                        "runner": "tmux",
                        "tmux_session": sname,
                        "attach_command": f"tmux attach -t {sname}",
                    }
                    break
        except Exception:
            pass

    if not found:
        print(f"Error: run {run_id} not found", file=sys.stderr)
        return 1

    # Backup previous current-run.json
    if os.path.isfile(current_run_path):
        try:
            import shutil
            backup_path = os.path.join(control_root, "current-run.previous.json")
            shutil.copy2(current_run_path, backup_path)
            print(f"Backed up previous to: {backup_path}")
        except OSError:
            pass

    # Write NEW current-run.json with manual selection metadata.
    # Does NOT touch active-run.json.
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pointer = {
        "run_id": run_id,
        "run_root": found_entry.get("run_root", ""),
        "events_path": found_entry.get("events_path", ""),
        "state": found_state,
        "runner": found_entry.get("runner", ""),
        "tmux_session": found_entry.get("tmux_session", ""),
        "attach_command": found_entry.get("attach_command", ""),
        "selection_reason": "manual",
        "selected_at": now_iso,
    }
    if found_entry.get("yolo") is not None:
        pointer["yolo"] = found_entry["yolo"]
    pointer = {k: v for k, v in pointer.items() if v is not None}

    try:
        os.makedirs(control_root, exist_ok=True)
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=control_root, prefix=".current-run.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(pointer, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        os.replace(tmp_path, current_run_path)
        print(f"Switched to run: {run_id}")
        print(f"  Run root:   {found_entry.get('run_root', '(none)')}")
        print(f"  State:      {found_state}")
        print(f"  Runner:     {found_entry.get('runner', '(none)')}")
        if found_entry.get("tmux_session"):
            print(f"  tmux:       {found_entry['tmux_session']}")
            print(f"  Attach:     {found_entry.get('attach_command', '')}")
        print("  Selection:  manual")
        return 0
    except Exception as e:
        print(f"Error writing current-run.json: {e}", file=sys.stderr)
        return 1



def _cmd_verify(args: argparse.Namespace) -> int:
    from .verify import run_verification

    import os as _os
    root = args.root or _os.path.normpath(
        _os.path.join(_os.path.dirname(__file__), ".."))
    skip_pkg = _os.path.isdir(_os.path.join(root, ".codeseeq")) or args.skip_package_steps

    return run_verification(
        root=args.root,
        timeout_scale=args.timeout_scale,
        skip_pytest=args.skip_pytest,
        skip_package_steps=skip_pkg,
        print_label=args.label,
        continue_on_failure=args.continue_on_failure,
    )


def _cmd_generate_image(args: argparse.Namespace) -> int:
    """Handle `qq generate-image` command."""
    import sys as _sys
    from .image_gen import generate_image

    if args.prompt is None:
        # Read prompt from stdin
        if not _sys.stdin.isatty():
            args.prompt = _sys.stdin.read().strip()
        if not args.prompt:
            print("Error: prompt is required. Provide it as argument or via stdin.",
                  file=_sys.stderr)
            return 1

    # Determine output path
    output_path = args.output
    if not output_path:
        ext = args.format if args.format != "jpeg" else "jpg"
        output_path = f"generated.{ext}"

    result = generate_image(
        prompt=args.prompt,
        model=args.model,
        method=args.method,
        provider=args.provider,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        width=args.width,
        height=args.height,
        quality=args.quality,
        format=args.format,
        cfg_scale=args.cfg_scale,
        steps=args.steps,
        seed=args.seed,
        safe_mode=args.safe_mode,
        hide_watermark=args.hide_watermark,
        negative_prompt=args.negative_prompt,
        style=args.style,
        output_path=output_path,
    )

    if args.json:
        import json
        output = {
            "success": result.success,
            "error": result.error,
            "image_path": result.image_path,
            "request_id": result.request_id,
            "model_used": result.model_used,
            "format": result.format,
            "duration_ms": result.duration_ms,
            "metadata": result.metadata,
        }
        print(json.dumps(output, indent=2, default=str))
    elif result.success:
        print("Image generated successfully.")
        print(f"  Model:      {result.model_used}")
        print(f"  Format:     {result.format}")
        print(f"  Duration:   {result.duration_ms:.0f}ms")
        if result.image_path:
            print(f"  Saved to:   {result.image_path}")
    else:
        print(f"Image generation FAILED: {result.error}", file=_sys.stderr)

    # Write metadata if requested
    if args.meta and result.success:
        import json
        from datetime import datetime, timezone
        import os as _os
        meta = {
            "prompt": args.prompt,
            "model": result.model_used,
            "format": result.format,
            "image_path": result.image_path,
            "request_id": result.request_id,
            "duration_ms": result.duration_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _os.makedirs(_os.path.dirname(args.meta) or ".", exist_ok=True)
            with open(args.meta, "w") as f:
                json.dump(meta, f, indent=2)
        except OSError as e:
            print(f"Warning: could not write metadata to {args.meta}: {e}", file=_sys.stderr)

    return 0 if result.success else 1


def _cmd_image_smoke_test(args: argparse.Namespace) -> int:
    from .image_smoke import run_image_smoke_test
    return run_image_smoke_test(
        output_dir=args.output_dir,
        force_real=args.real,
    )



def _cmd_test(args: argparse.Namespace) -> int:
    """Run the generic QonQrete test suite."""
    selected = [x.strip() for x in args.tests.split(",") if x.strip()]
    if "all" in selected:
        selected = ["image-smoke", "statusline"]
    rc = 0
    for name in selected:
        if name in ("image-smoke", "image_smoke"):
            from .image_smoke import run_image_smoke_test
            result = run_image_smoke_test(output_dir=args.output_dir, force_real=args.real)
        elif name in ("statusline", "status-line"):
            # Exercise the Python statusline renderer directly; this is the
            # portable replacement for the former statusline-test command.
            from .terminal_ui import StreamActivityStatus, format_qonqrete_status_bar
            sample = StreamActivityStatus(role="qlarifier", model_code="fla-T", score=50)
            print(format_qonqrete_status_bar(sample, color=False, width=100, version=__version__))
            result = 0
        else:
            print(f"error: unknown test '{name}'", file=sys.stderr)
            result = 2
        if result:
            rc = result
    return rc


def _cmd_generate_video(args: argparse.Namespace) -> int:
    from .video_gen import generate_video
    result = generate_video(
        method=args.method, prompt=args.prompt, output_path=args.output,
        script_path=args.script, width=args.width, height=args.height,
        fps=args.fps, duration=args.duration,
    )
    if result.success:
        print(f"Video generated successfully.\n  Method: {result.method}\n  Saved to: {result.output_path}")
        return 0
    print(f"Video generation FAILED: {result.error}", file=sys.stderr)
    return 1


def _cmd_chat(args: argparse.Namespace) -> int:
    from .chat import serve_chat
    return serve_chat(
        host=args.host, port=args.port, open_browser=args.open_browser,
        provider=args.provider, config_path=args.config, web_port=args.web_port,
    )


def _cmd_package(args: argparse.Namespace) -> int:
    from .package import check_tree, check_archive, build

    root_override = None

    if args.check:
        return check_tree(root_override)
    elif args.check_upload_tree:
        return check_tree(root_override, upload_mode=True)
    elif args.check_archive:
        return check_archive(args.check_archive)
    elif args.check_uploaded_zip:
        return check_archive(args.check_uploaded_zip)
    elif args.final:
        zip_path = build(root_override)
        print()
        print("=" * 60)
        print(f"FINAL ARTIFACT: {zip_path}")
        print("Upload this file directly. Do not zip the source folder.")
        print("=" * 60)
        return 0
    else:
        check_tree(root_override)
        zip_path = build(root_override)
        print()
        print("=" * 60)
        print(f"FINAL ARTIFACT: {zip_path}")
        print("Upload this file directly. Do not zip the source folder.")
        print("=" * 60)
        return 0


def _cmd_web(args: argparse.Namespace) -> int:
    """Handle the `qq web` subcommand."""
    if args.web_command == "serve":
        return _cmd_web_serve(args)
    elif args.web_command == "status":
        return _cmd_web_status(args)
    elif args.web_command == "stop":
        return _cmd_web_stop(args)
    else:
        print("qq web: missing command. Usage: qq web {serve,status,stop}", file=sys.stderr)
        return 1


def _cmd_ingest_status(args: argparse.Namespace) -> int:
    """Show ingest idempotency status."""
    control_root = args.control_root or os.environ.get("QONQRETE_CONTROL_ROOT", "/x/qq/control")
    jsonl_path = os.path.join(control_root, "ingest-idempotency.jsonl")
    if not os.path.isfile(jsonl_path):
        print(f"No ingest idempotency records found at {jsonl_path}")
        return 0
    import json
    count = 0
    by_status = {}
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if args.source and entry.get("source") != args.source:
                    continue
                status = entry.get("status", "unknown")
                by_status[status] = by_status.get(status, 0) + 1
                count += 1
    except OSError as e:
        print(f"Error reading idempotency records: {e}")
        return 1
    print(f"Ingest idempotency records at {jsonl_path}:")
    print(f"  Total: {count}")
    for status, n in sorted(by_status.items()):
        print(f"  {status}: {n}")
    return 0


def _cmd_ingest_purge_stale(args: argparse.Namespace) -> int:
    """Purge stale ingest entries."""
    control_root = args.control_root or os.environ.get("QONQRETE_CONTROL_ROOT", "/x/qq/control")
    jsonl_path = os.path.join(control_root, "ingest-idempotency.jsonl")
    if not os.path.isfile(jsonl_path):
        print(f"No ingest idempotency records found at {jsonl_path}")
        return 0
    # Parse older-than
    import re
    older_str = args.older_than or "24h"
    m = re.match(r'(\d+)([smhd])', older_str)
    if not m:
        print(f"Invalid older-than: {older_str}. Use format like 24h, 7d, 3600s")
        return 1
    num = int(m.group(1))
    unit = m.group(2)
    seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] * num
    cutoff = time.time() - seconds
    import json
    keep = []
    removed = 0
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    keep.append(line)
                    continue
                if args.source and entry.get("source") != args.source:
                    keep.append(line)
                    continue
                created = entry.get("created_at", "")
                try:
                    from datetime import datetime
                    dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
                    ts = dt.timestamp()
                except (ValueError, OSError):
                    keep.append(line)
                    continue
                if ts < cutoff:
                    removed += 1
                else:
                    keep.append(line)
        # Rewrite file
        with open(jsonl_path, "w") as f:
            for line in keep:
                f.write(line + "\n")
    except OSError as e:
        print(f"Error processing idempotency records: {e}")
        return 1
    print(f"Purged {removed} stale entries from {jsonl_path}")
    return 0


def _cmd_ingest_dead_letter(args: argparse.Namespace) -> int:
    """List dead-letter entries."""
    control_root = args.control_root or os.environ.get("QONQRETE_CONTROL_ROOT", "/x/qq/control")
    jsonl_path = os.path.join(control_root, "ingest-dead-letter.jsonl")
    if not os.path.isfile(jsonl_path):
        print(f"No dead-letter records found at {jsonl_path}")
        return 0
    import json
    print(f"Dead-letter entries at {jsonl_path}:")
    try:
        with open(jsonl_path, "r") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    print(f"  {i}. [parse error]")
                    continue
                print(f"  {i}. key={entry.get('idempotency_key', '?')} "
                      f"source={entry.get('source', '?')} "
                      f"reason={entry.get('reason', '?')} "
                      f"cmd={entry.get('command_text', '')[:60]}")
    except OSError as e:
        print(f"Error reading dead-letter: {e}")
        return 1
    return 0


def _cmd_ingest_retry(args: argparse.Namespace) -> int:
    """Retry a dead-lettered entry by removing it from dead-letter."""
    control_root = args.control_root or os.environ.get("QONQRETE_CONTROL_ROOT", "/x/qq/control")
    key = args.idempotency_key
    # Remove from dead-letter
    dl_path = os.path.join(control_root, "ingest-dead-letter.jsonl")
    if not os.path.isfile(dl_path):
        print(f"No dead-letter records found at {dl_path}")
        return 0
    import json
    keep = []
    found = False
    try:
        with open(dl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    keep.append(line)
                    continue
                if entry.get("idempotency_key") == key:
                    found = True
                    continue
                keep.append(line)
        if found:
            with open(dl_path, "w") as f:
                for line in keep:
                    f.write(line + "\n")
            print(f"Retried {key}: removed from dead-letter. Resend with force_retry:true to re-run.")
        else:
            print(f"Key {key} not found in dead-letter.")
    except OSError as e:
        print(f"Error: {e}")
        return 1
    return 0


def _cmd_web_serve(args: argparse.Namespace) -> int:
    """Start the briQsQope dashboard server."""
    from .web.process import start_dashboard, find_dashboard_dir

    dashboard_dir = find_dashboard_dir()
    if not dashboard_dir:
        print("error: qq/web/ directory not found. Is briQsQope installed?", file=sys.stderr)
        return 1

    # Validate control-root vs run-root mutual exclusivity
    control_root = getattr(args, 'control_root', None)
    run_root = getattr(args, 'run_root', None)
    if control_root and run_root:
        control_canon = os.path.abspath(os.path.expanduser(control_root))
        run_canon = os.path.abspath(os.path.expanduser(run_root))
        if control_canon != run_canon:
            print("error: --control-root and --run-root cannot both be set to different paths.", file=sys.stderr)
            print(f"  control-root: {control_canon}", file=sys.stderr)
            print(f"  run-root:     {run_canon}", file=sys.stderr)
            return 1

    repo_root_canon = os.path.abspath(os.path.expanduser(args.repo_root))

    if control_root:
        # Control-root mode: use control_root as the root
        run_root = os.path.abspath(os.path.expanduser(control_root))
        print("→ Starting briQsQope dashboard (control-root mode)...")
        print(f"  Control root: {run_root}")
    else:
        run_root = args.run_root
        if run_root:
            run_root = os.path.abspath(os.path.expanduser(run_root))
        if not run_root:
            # Try to find the most recent run
            runs_dir = os.path.join(repo_root_canon, ".qq", "runs")
            if os.path.isdir(runs_dir):
                runs = sorted([
                    d for d in os.listdir(runs_dir)
                    if os.path.isdir(os.path.join(runs_dir, d))
                ], reverse=True)
                if runs:
                    run_root = os.path.join(runs_dir, runs[0])
                    print(f"Using most recent run: {run_root}")

        if not run_root or not os.path.isdir(run_root):
            print("error: no run root specified and no runs found. Use --run-root or --control-root.", file=sys.stderr)
            return 1

        print("→ Starting briQsQope dashboard...")
        print(f"  Run root: {run_root}")

    print(f"  Address:  https://web.qonqrete.sh (bind: {args.host}:{args.port})")

    pid = start_dashboard(
        repo_root=repo_root_canon,
        run_root=run_root,
        host=args.host,
        port=args.port,
        open_browser=args.open_browser,
        dashboard_dir=dashboard_dir,
        control_root=os.path.abspath(os.path.expanduser(control_root)) if control_root else None,
    )

    if pid:
        print(f"  Dashboard PID: {pid}")
        print("  Open: https://web.qonqrete.sh")
        print("  Stop with: qq web stop")
    else:
        print("warning: dashboard process started but PID could not be confirmed", file=sys.stderr)

    return 0

def _cmd_web_status(args: argparse.Namespace) -> int:
    """Show dashboard status."""
    from .web.process import dashboard_status
    status = dashboard_status()
    if status["running"]:
        print("briQsQope dashboard: RUNNING")
        if status.get("pid"):
            print(f"  PID:            {status['pid']}")
        if status.get("host"):
            print(f"  Host:           {status['host']}")
        if status.get("port"):
            print(f"  Port:           {status['port']}")
        if status.get("url"):
            print(f"  URL:            {status['url']}")
        if status.get("serving_mode"):
            print(f"  Serving mode:   {status['serving_mode']}")
        if status.get("root_path"):
            print(f"  Root path:      {status['root_path']}")
        if status.get("active_run_id"):
            print(f"  Active run:     {status['active_run_id']}")
        if status.get("active_run_state"):
            print(f"  Run state:      {status['active_run_state']}")
        if status.get("active_target_path"):
            print(f"  Target path:    {status['active_target_path']}")
        if status.get("active_tmux_attach"):
            print(f"  tmux attach:    {status['active_tmux_attach']}")
        if status.get("stdout_log"):
            print(f"  stdout log:     {status['stdout_log']}")
        if status.get("stderr_log"):
            print(f"  stderr log:     {status['stderr_log']}")
    else:
        print("briQsQope dashboard: NOT RUNNING")
    return 0


def _cmd_web_stop(args: argparse.Namespace) -> int:
    """Stop the dashboard."""
    from .web.process import stop_dashboard
    if stop_dashboard():
        print("briQsQope dashboard: STOPPED")
    else:
        print("briQsQope dashboard: was not running")
    return 0

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)

    # Known subcommands — subcommand is mandatory
    known_subcommands = {
        "run", "replay", "exec", "doctor", "providers", "cleanup",
        "generate-image", "generate-video", "test", "package", "verify",
        "install", "reinstall", "nuke", "models", "web",
        "runs", "ingest", "chat",
    }

    # Must supply a subcommand
    if not argv:
        print("qq: missing command. Usage: qq <command> [options]", file=sys.stderr)
        print("Commands: run, replay, exec, chat, test, generate-image, generate-video, install, reinstall, nuke, doctor, models, providers, cleanup, package, verify", file=sys.stderr)
        sys.exit(1)

    # Allow --help/-h at top level
    if argv[0] in ("--help", "-h"):
        parser = build_parser()
        parser.print_help()
        sys.exit(0)

    # If first arg is not a known subcommand, it's an error
    if argv[0] not in known_subcommands:
        # Check if it looks like a file (bare `qq task.md` usage) — auto-launch TUI
        if argv[0].endswith(".md") or os.path.isfile(argv[0]):
            from .tui_launcher import launch_tui
            sys.exit(launch_tui(argv))
        else:
            print(f"qq: unknown command '{argv[0]}'. Run 'qq --help' for usage.", file=sys.stderr)
        sys.exit(1)

    # The legacy integrated TUI command line is gone. Run/replay use the migrated
    # internal TUI automatically; --no-tui remains the explicit headless escape hatch.
    from .tui_launcher import launch_tui_with_args, launch_internal_mode
    if argv[0] == "run" and "--no-tui" not in argv and "--help" not in argv and "-h" not in argv:
        sys.exit(launch_tui_with_args(argv))
    if argv[0] == "replay" and "--help" not in argv and "-h" not in argv:
        sys.exit(launch_internal_mode("replay", argv[1:]))
    if argv[0] == "exec" and "--help" not in argv and "-h" not in argv:
        sys.exit(launch_internal_mode("exec", argv[1:]))

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        sys.exit(_cmd_run(args))
    elif args.command == "install":
        sys.exit(_cmd_install(args))
    elif args.command == "reinstall":
        sys.exit(_cmd_reinstall(args))
    elif args.command == "nuke":
        sys.exit(_cmd_nuke(args))
    elif args.command == "replay":
        sys.exit(_cmd_replay(args))
    elif args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    elif args.command == "models":
        sys.exit(_cmd_models(args))
    elif args.command == "providers":
        sys.exit(_cmd_providers(args))
    elif args.command == "cleanup":
        sys.exit(_cmd_cleanup(args))
    elif args.command == "web":
        sys.exit(_cmd_web(args))
    elif args.command == "runs":
        sys.exit(_cmd_runs(args))

    elif args.command == "ingest":
        sys.exit(_cmd_ingest(args))

    elif args.command == "verify":
        sys.exit(_cmd_verify(args))
    elif args.command == "test":
        sys.exit(_cmd_test(args))
    elif args.command == "generate-image":
        sys.exit(_cmd_generate_image(args))
    elif args.command == "generate-video":
        sys.exit(_cmd_generate_video(args))
    elif args.command == "chat":
        sys.exit(_cmd_chat(args))
    elif args.command == "package":
        sys.exit(_cmd_package(args))


if __name__ == "__main__":
    main()
