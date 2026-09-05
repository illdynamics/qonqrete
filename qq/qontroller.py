"""
Qontroller — the orchestration loop.

Deliberately contains zero AI calls of its own.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Callable, Dict, List, Optional, Set

import time as _time

from .adapters.base import AgentAdapter
from .agents.construqtor import run_construqtor_for_group
from .agents.inspeqtor import run_inspeqtor
from .agents.instruqtor import run_instruqtor
from .agents.qlarifier import run_qlarifier
from .streaming import _ROLE_DISPLAY, _RESET
from .eventlog import EventLog
from .harness import HarnessContext, HarnessFailure, HarnessResult, ShellHarness
from .models import (
    BriQ, BriqStatus, BuildGroup, ClarifiedTask, Plan,
    ReviewIssue, ReviewVerdict, RunState, RunStatus, Task,
)
from . import __version__ as _qq_version
from .terminal_ui import (
    BRAILLE_SNAKE, StreamActivityStatus,
    StickyStatusLine, SpinnerManager, model_code_for, model_symbol_for,
)
from .workspaces import WorkspaceManager
from .completion_callback import maybe_send_terminal_callback as _maybe_callback
from .progress import calculate_progress



def _fmt(role: str, msg: str, *, no_color: bool = False) -> str:
    """Format an on_event message with a colored [AgentName] prefix and >>>."""
    info = _ROLE_DISPLAY.get(role)
    if info is None:
        return f">>> [{role}] {msg}"
    label, color = info
    if no_color:
        return f">>> {label} {msg}"
    return f">>> {color}{label}{_RESET} {msg}"


class QontrollerConfig:
    def __init__(
        self, *, repo_root: str, run_root: str,
        model_qlarifier: str, model_instruqtor: str,
        model_construqtor: str, model_inspeqtor: str,
        briq_sensitivity: int = 0, max_cycles: int = 0,
        max_parallel_build_groups: int = 4,
        parallel_spawn_delay_seconds: float = 1.0,
        max_time_seconds: int = 0,
        harness_commands: Optional[List[str]] = None,
        review_on_harness_failure: bool = False,
        allow_dirty: bool = False,
        run_id: Optional[str] = None,
        stream_agent_output: bool = False,
        stream_mode: str = "prefixed",
        stream_stderr: bool = True,
        stream_indicator: str = "stream",
        show_prompts: bool = False,
        stream_status_line: str = "off",
        stream_line_prefix: str = "auto",
        no_color: bool = False,
        agent_color_output: str = "agent",
        no_repo: bool = False,
        reasoning_effort: str = "",
        reasoning_qlarifier: str = "",
        reasoning_instruqtor: str = "",
        reasoning_construqtor: str = "",
        reasoning_inspeqtor: str = "",
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        yolo: bool = False,
    ):
        self.repo_root = repo_root
        self.run_root = run_root
        self.model_qlarifier = model_qlarifier
        self.model_instruqtor = model_instruqtor
        self.model_construqtor = model_construqtor
        self.model_inspeqtor = model_inspeqtor
        self.briq_sensitivity = briq_sensitivity
        self.max_cycles = max_cycles
        self.max_parallel_build_groups = max_parallel_build_groups
        self.parallel_spawn_delay_seconds = parallel_spawn_delay_seconds
        self.max_time_seconds = max_time_seconds
        self.harness_commands = harness_commands or []
        self.review_on_harness_failure = review_on_harness_failure
        self.allow_dirty = allow_dirty
        self.run_id = run_id
        self.stream_agent_output = stream_agent_output
        self.stream_mode = stream_mode
        self.stream_stderr = stream_stderr
        self.stream_indicator = stream_indicator
        self.show_prompts = show_prompts
        self.stream_status_line = stream_status_line
        self.stream_line_prefix = stream_line_prefix
        self.no_color = no_color
        self.agent_color_output = agent_color_output
        self.no_repo = no_repo
        self.reasoning_effort = reasoning_effort
        self.reasoning_qlarifier = reasoning_qlarifier or reasoning_effort
        self.reasoning_instruqtor = reasoning_instruqtor or reasoning_effort
        self.reasoning_construqtor = reasoning_construqtor or reasoning_effort
        self.reasoning_inspeqtor = reasoning_inspeqtor or reasoning_effort
        self.temperature = temperature
        self.top_p = top_p
        self.yolo = yolo
        # Web dashboard
        self.web_enabled: bool = True
        self.web_start_with_run: bool = True
        self.web_host: str = "0.0.0.0"
        self.web_port: int = 31337
        self.web_open_browser: bool = False
        self.web_hard_fail: bool = False

# ---------------------------------------------------------------------------
# Artifact markdown writers
# ---------------------------------------------------------------------------
def _write_artifact_md(run_root: str, filename: str, content: str) -> None:
    """Write a markdown artifact under <run_root>/artifacts/."""
    arts_dir = os.path.join(run_root, "artifacts")
    os.makedirs(arts_dir, exist_ok=True)
    with open(os.path.join(arts_dir, filename), "w", encoding="utf-8") as fh:
        fh.write(content)


def _write_planning_md(run_root: str, plan) -> None:
    """Write a human-readable planning markdown document."""
    if not plan:
        return
    lines = [
        "# QonQrete Build Plan",
        "",
        f"**Summary**: {plan.summary}",
        f"**BriQs**: {len(plan.briqs)} across {len(plan.build_groups)} build group(s)",
        "",
    ]

    for bg_id, bg in plan.build_groups.items():
        lines.append(f"## Build Group: {bg.name}")
        lines.append("")
        lines.append(f"- **ID**: {bg.id}")
        lines.append(f"- **Parallel Safe**: {bg.parallel_safe}")
        if bg.description:
            lines.append(f"- **Description**: {bg.description}")
        lines.append("")
        lines.append("### BriQs")
        for bid in bg.briq_ids:
            briq = plan.briqs.get(bid)
            if briq:
                lines.append(f"- **{briq.title}** ({briq.id})")
                lines.append(f"  - Sensitivity: {briq.sensitivity}")
                lines.append(f"  - {briq.description[:200]}")
                if briq.expected_files:
                    lines.append(f"  - Expected files: {', '.join(briq.expected_files)}")
        lines.append("")

    _write_artifact_md(run_root, "planning.md", "\n".join(lines))



def run(
    task_text: str, adapter: AgentAdapter, config: QontrollerConfig,
    ask_human: Callable[[List[str]], List[str]],
    on_event: Callable[[str], None] = lambda *_: None,
) -> RunState:
    os.makedirs(config.run_root, exist_ok=True)
    # Use run ID from config or derive it from run_root
    run_id = config.run_id or os.path.basename(config.run_root)

    # Create a color-aware formatter closure
    _no_color = config.no_color
    def _fmtc(role: str, msg: str) -> str:
        return _fmt(role, msg, no_color=_no_color)
    log = EventLog(os.path.join(config.run_root, "events.jsonl"),
                   run_id=run_id)

    # If YOLO mode, wrap ask_human to auto-answer without blocking
    if config.yolo:
        def _yolo_ask(questions):
            log.emit("approval.bypassed", reason="yolo_enabled", stage="qontroller_ask_human")
            return ["[YOLO: auto-approved]" for _ in questions]
        ask_human = _yolo_ask

    state = RunState(
        run_id=run_id,
        max_cycles=config.max_cycles,
        workspace_root=config.repo_root,
        task=Task(raw_text=task_text),
    )

    log.emit("run.started",
             max_cycles=config.max_cycles,
             max_time_seconds=config.max_time_seconds)

    # ---- Initialize terminal UI ----
    import sys as _sys
    sticky_line = None
    spinner_mgr = SpinnerManager()
    activity = StreamActivityStatus(
        max_cycles=config.max_cycles,
        max_time_seconds=config.max_time_seconds,
    )
    run_start_time = _time.monotonic()
    agent_start_time = run_start_time

    if config.stream_status_line != "off" and config.stream_agent_output:
        sticky_line = StickyStatusLine(
            _sys.stderr,
            position=config.stream_status_line,
            enabled=True,
            color=not config.no_color,
            version=_qq_version,
        )
        sticky_line.start()
        if not sticky_line.is_active:
            # TTY unavailable — warn the user
            _sys.stderr.write(
                "[qq] sticky status line requested but terminal is not a TTY.\n"
                "[qq] Falling back to clean line streaming.\n"
            )
            _sys.stderr.flush()
        activity.run_elapsed_seconds = 0.0
        activity.agent_elapsed_seconds = 0.0
        activity.spinner_frame = BRAILLE_SNAKE[0]
        activity.cycle = 1  # Start at C=1 (clarification is cycle 1)
        activity.score = 0
        activity.last_exit_code = 0
        activity.action_status = "Preparing"
        activity.chunks_seen = 0
        activity.model_code = "?"
        activity.model_symbol = "???"
        activity.role = "qlarifier"
        sticky_line.render(activity)

    def _update_activity(**kwargs):
        nonlocal activity
        for k, v in kwargs.items():
            if hasattr(activity, k):
                setattr(activity, k, v)

    def _set_active_agent(role: str, call_id: str = "", model_code: str = ""):
        nonlocal agent_start_time
        old_role = activity.role
        activity.role = role
        activity.call_id = call_id
        activity.chunks_seen = 0
        activity.agent_elapsed_seconds = 0.0
        agent_start_time = _time.monotonic()
        if model_code:
            activity.model_code = model_code
        activity.model_symbol = model_symbol_for(activity.model_code)
        # Set action_status based on agent role
        if role == "qlarifier":
            activity.action_status = "Preparing"
        elif role == "instruqtor":
            activity.action_status = "Planning"
        elif role == "construqtor":
            activity.action_status = "Building"
        elif role == "inspeqtor":
            activity.action_status = "Reviewing"
        spinner_mgr.reset(role, call_id)
        activity.spinner_frame = spinner_mgr.get_current_frame()
        log.emit("active_agent_changed", role=role, call_id=call_id, model=activity.model_code,
                 previous_role=old_role)
        log.emit("action_status_changed", action_status=activity.action_status,
                 source="active_agent_changed", role=role)
        if sticky_line and sticky_line.is_active:
            _refresh_sticky()

    def _refresh_sticky():
        activity.run_elapsed_seconds = _time.monotonic() - run_start_time
        activity.agent_elapsed_seconds = _time.monotonic() - agent_start_time
        if sticky_line and sticky_line.is_active:
            sticky_line.render(activity)

    # Idle spinner ticker — periodic animation when agent is running but quiet
    _idle_ticker_running = True
    def _idle_ticker():
        while _idle_ticker_running:
            _time.sleep(0.15)  # ~6.7 fps
            if sticky_line and sticky_line.is_active:
                frame = spinner_mgr.idle_tick()
                if frame is not None:
                    activity.spinner_frame = frame
                    # model_symbol is static, not a spinner
                    _refresh_sticky()
    import threading
    _idle_thread = threading.Thread(target=_idle_ticker, daemon=True)
    _idle_thread.start()
    # Wrap on_event to route through sticky line when active
    _user_on_event = on_event
    def _wrapped_on_event(msg: str) -> None:
        """Route on_event messages through sticky line when active,
        otherwise use the user-provided callback."""
        if sticky_line and sticky_line.is_active:
            sticky_line.write_stream_line(msg + "\n")
        if _user_on_event:
            _user_on_event(msg)
    on_event = _wrapped_on_event


    # Build stream config for agent calls
    _stream_config_base = {} if not config.stream_agent_output else {
        "stream_agent_output": config.stream_agent_output,
        "stream_mode": config.stream_mode,
        "stream_stderr": config.stream_stderr,
        "stream_indicator": config.stream_indicator,
        "show_prompts": config.show_prompts,
        # Always pass stream_line_prefix so it works even when sticky is off
        "stream_line_prefix": config.stream_line_prefix,
        "no_color": config.no_color,
        "agent_color_output": config.agent_color_output,
    }

    # Always include temperature and top_p in stream config
    if config.temperature is not None:
        _stream_config_base["temperature"] = config.temperature
    if config.top_p is not None:
        _stream_config_base["top_p"] = config.top_p

    # Wire sticky status line into stream config
    _sticky_requested = (config.stream_status_line != "off" and config.stream_agent_output)
    _sticky_active = _sticky_requested and sticky_line is not None and sticky_line.is_active
    if _sticky_requested:
        # Always apply clean-body settings when sticky line is requested,
        # even if TTY is unavailable — the user asked for clean output.
        line_prefix = config.stream_line_prefix
        if line_prefix == "auto":
            line_prefix = "none"
        if sticky_line is not None:
            _stream_config_base["sticky_status"] = sticky_line
        _stream_config_base["spinner_manager"] = spinner_mgr
        _stream_config_base["activity_tracker"] = activity
        _stream_config_base["refresh_sticky_cb"] = _refresh_sticky
        _stream_config_base["stream_line_prefix"] = line_prefix
        _stream_config_base["stream_indicator"] = "none"

    def _stream_config():
        return _stream_config_base.copy()

    # Bridge agent subprocess output lines into the event log so the web
    # dashboard's SSE stream can deliver them in real time (Issue 3.4).
    def _emit_stream_output(role: str = "", text: str = "",
                            stream: str = "stdout", call_id: str = "") -> None:
        """Emit a single 'stream.output' event for one agent output line.

        Guarded by try/except so a logging failure can never break the run.
        Volume stays bounded: one event per delivered line (lines are already
        capped by the streamer/adapter), and over-long lines are trimmed.
        """
        if not log:
            return
        text_str = str(text).strip() if text is not None else ""
        if not text_str:
            return
        # BGP5: strip the external agent's env-debug leak ('QQV_ROLE=...') at the
        # earliest server capture point so it never reaches the SSE/polled payload.
        if 'QQV_ROLE=' in text_str or 'vQQV_ROLE=' in text_str:
            return
        # Keep event volume reasonable: trim overly long lines and skip empties.
        if len(text_str) > 2000:
            text_str = text_str[:2000]
        stream_val = stream or "stdout"
        try:
            log.emit(
                "stream.output",
                role=str(role or ""),
                text=text_str,
                stream=stream_val,
                call_id=str(call_id or ""),
            )
        except Exception:
            # A logging failure must never break the run.
            pass

    def _stream_to_event_log(chunk: dict) -> None:
        # Adapter-facing sink: normalise a chunk dict and forward to the event log.
        if not chunk:
            return
        role = (chunk or {}).get('role', '') or ''
        text = (chunk or {}).get('text', '') or ''
        stream_name = (chunk or {}).get('stream_name', '') or 'stdout'
        call_id = (chunk or {}).get('call_id', '') or ''
        _emit_stream_output(role=role, text=text, stream=stream_name,
                            call_id=call_id)

    # Wire the bridge into the adapter (instance-level sink fallback) and into
    # the stream config so the adapter may also pick it up from spec/config.
    try:
        if adapter is not None and not getattr(adapter, '_output_event_log', None):
            setattr(adapter, '_output_event_log', _stream_to_event_log)
    except Exception:
        pass
    if config.stream_agent_output:
        _stream_config_base["event_log"] = _stream_to_event_log

    log.emit("config.loaded", provider=adapter.name,
             stream_agent_output=config.stream_agent_output,
             stream_mode=config.stream_mode,
             stream_stderr=config.stream_stderr,
             stream_indicator=config.stream_indicator,
             show_prompts=config.show_prompts,
             agent_color_output=config.agent_color_output,
             models={"qlarifier": config.model_qlarifier,
                     "instruqtor": config.model_instruqtor,
                     "construqtor": config.model_construqtor,
                     "inspeqtor": config.model_inspeqtor},
             max_cycles=config.max_cycles,
             max_time_seconds=config.max_time_seconds,
             briq_sensitivity=config.briq_sensitivity)

    # Web dashboard events
    web_started = getattr(config, 'web_started', False)
    if getattr(config, 'web_enabled', False) and getattr(config, 'web_start_with_run', False):
        log.emit("web.dashboard_starting",
                 host=getattr(config, 'web_host', '0.0.0.0'),
                 port=getattr(config, 'web_port', 31337))
        if web_started:
            log.emit("web.dashboard_started",
                     host=getattr(config, 'web_host', '0.0.0.0'),
                     port=getattr(config, 'web_port', 31337))
        else:
            log.emit("web.dashboard_failed",
                     reason="dashboard_process_did_not_start")

    # Write initial task snapshot
    # Write original task artifact (human-readable markdown)
    _write_artifact_md(config.run_root, "task-original.md",
                       task_text)
    _write_snapshot(config.run_root, "task.json",
                    state.task.to_dict())

    workspaces = WorkspaceManager(
        config.repo_root, config.run_root, run_id,
        allow_dirty=config.allow_dirty,
        no_repo=config.no_repo,
    )

    try:
        # ========================================================
        # Phase 1: Qlarifier (once)
        # ========================================================
        _ = on_event; _(_fmtc("qlarifier", "reading the task..."))
        state.status = RunStatus.CLARIFYING
        _set_active_agent("qlarifier", model_code=model_code_for(config.model_qlarifier))
        _refresh_sticky()
        state.clarified_task = run_qlarifier(
            adapter, state.task,
            os.path.join(config.run_root, "agents", "cycle-000",
                        "qlarifier"),
            config.model_qlarifier, ask_human, event_log=log,
            run_root=config.run_root,
            workspace_root=config.repo_root,
            stream_config=_stream_config(),
            reasoning_effort=config.reasoning_qlarifier,
            yolo=config.yolo,
        )
        log.emit("clarification.done",
                 clarified=state.clarified_task.to_dict())
        _write_snapshot(config.run_root, "clarified_task.json",
                        state.clarified_task.to_dict())

        # Write enhanced task artifact (human-readable markdown)
        _write_artifact_md(config.run_root, "task-enhanced.md",
                           state.clarified_task.clarified_text)

        # ========================================================
        # Phase 2: InstruQtor (once)
        # ========================================================
        _ = on_event; _(_fmtc("instruqtor", "splitting into briQs and build groups..."))
        state.status = RunStatus.PLANNING
        _set_active_agent("instruqtor", model_code=model_code_for(config.model_instruqtor))
        _refresh_sticky()
        state.plan = run_instruqtor(
            adapter, state.clarified_task,
            os.path.join(config.run_root, "agents", "cycle-000",
                        "instruqtor"),
            config.model_instruqtor,
            briq_sensitivity=config.briq_sensitivity,
            event_log=log,
            run_root=config.run_root,
            workspace_root=config.repo_root,
            stream_config=_stream_config(),
            reasoning_effort=config.reasoning_instruqtor,
        )
        log.emit("plan.created", plan=state.plan.to_dict())
        activity.action_status = "Creating build groups"
        log.emit("action_status_changed", action_status=activity.action_status, source="plan")

        # Auto-detect parallel safety: groups writing to different files
        # should be marked parallel_safe for concurrent building.
        parallel_before = sum(1 for g in state.plan.build_groups.values() if g.parallel_safe)
        _auto_mark_parallel_safe(state.plan)
        parallel_after = sum(1 for g in state.plan.build_groups.values() if g.parallel_safe)
        auto_marked = parallel_after - parallel_before
        if auto_marked:
            log.emit("plan.parallel_auto_marked", auto_marked=auto_marked,
                     total_parallel=parallel_after, total_groups=len(state.plan.build_groups))

        _write_snapshot(config.run_root, "plan.json",
                        state.plan.to_dict())

        # Write planning artifact (human-readable markdown)
        _write_planning_md(config.run_root, state.plan)

        _ = on_event
        _(_fmtc("instruqtor",
            f"{len(state.plan.briqs)} briQ(s) across "
            f"{len(state.plan.build_groups)} build group(s)."))

        # Validate plan
        plan_issues = state.plan.validate()
        if plan_issues:
            log.emit("plan.validation_issues", issues=plan_issues)
            _ = on_event
            _(_fmtc("instruqtor",
                f"Plan validation: {len(plan_issues)} issue(s) — "
                f"continuing anyway."))

        # All groups start as active. After first build+review cycle,
        # only groups with NEEDS_REPAIR briQs will be rebuilt.
        active_groups = list(state.plan.build_groups.values())

        # ========================================================
        # Phase 3: Build → Harness → Review → Repair loop
        # ========================================================
        # The initial build (entering the loop from instruQtor planning) is
        # cycle 1. state.cycle starts at 0 (run start) and is incremented by
        # exactly +1 on every SUBSEQUENT build, which is always reached via the
        # inspeQtor -> construQtor review-to-build handoff (a NOT_DONE verdict
        # feeding fixes back to construQtor). That single increment lives in the
        # NOT_DONE branch below so cycle advances only when the reviewer returns
        # the output to the builder — never on Qlarifier/instruQtor/construQtor
        # entry or on the construQtor -> inspeQtor review transition.
        state.cycle = 1

        while True:
            # Check time limit (0 = unlimited)
            if state.max_time_seconds > 0:
                elapsed = _time.monotonic() - run_start_time
                remaining = state.max_time_seconds - elapsed
                if remaining <= 0:
                    state.status = RunStatus.ABORTED
                    activity.action_status = "STOPPED"
                    log.emit("run.aborted", reason="max_time_exceeded",
                             cycle=state.cycle, elapsed_seconds=elapsed,
                             max_time_seconds=state.max_time_seconds)
                    _write_snapshot(config.run_root, "final.json",
                                    _final_snapshot(state, config))
                    if sticky_line and sticky_line.is_active:
                        _refresh_sticky()
                    _ = on_event
                    _(_fmtc("qontroller",
                        f"Hit max_time ({state.max_time_seconds}s) without "
                        f"\033[31mFULLY_DONE\033[0m. Time limit reached — Stopping."))
                    # Send terminal callback for max-time abort
                    try:
                        _maybe_callback(config.run_root)
                    except Exception:
                        pass
                    break

            # Staleness detection: if the same issue count persists
            # for too many cycles, escalate with a warning and extra
            # guidance for the agents.
            _staleness_streak_limit = 5
            _prev_issue_count = getattr(state, '_prev_build_issue_count', None)
            _curr_issue_count = len([
                b for b in (state.plan.briqs.values() if state.plan else [])
                if b.status in (BriqStatus.NEEDS_REPAIR, BriqStatus.FAILED)
            ])
            if (_prev_issue_count is not None
                    and _curr_issue_count == _prev_issue_count
                    and _curr_issue_count > 0):
                _streak = getattr(state, '_staleness_streak', 0) + 1
            else:
                _streak = 1
            state._staleness_streak = _streak
            state._prev_build_issue_count = _curr_issue_count
            if _streak >= _staleness_streak_limit and _curr_issue_count > 0:
                _ = on_event
                _(_fmtc("qontroller",
                    f"\033[33mSTALENESS WARNING\033[0m: {_curr_issue_count} "
                    f"briQ(s) stuck in NEEDS_REPAIR/FAILED for "
                    f"{_streak} consecutive cycles. "
                    f"InspeQtor will be asked to provide more specific guidance."))
                log.emit("run.staleness_warning",
                         streak=_streak,
                         stuck_briq_count=_curr_issue_count,
                         cycle=state.cycle)

            state.status = RunStatus.BUILDING
            _ = on_event
            _(_fmtc("construqtor",
                f"cycle {state.cycle}, building..."))
            activity.cycle = state.cycle
            _set_active_agent("construqtor", model_code=model_code_for(config.model_construqtor))
            _refresh_sticky()
            _write_snapshot(
                config.run_root,
                f"cycle-{state.cycle:03d}-before-build.json",
                _cycle_snapshot(state),
            )

            # Emit build_group events for this cycle
            active = _active_groups(state)

            # Early exit: if no groups are active and work is complete.
            if not active and state.plan:
                all_briqs_done = all(
                    b.status == BriqStatus.DONE
                    for b in state.plan.briqs.values()
                )
                if all_briqs_done and state.plan.briqs:
                    # Check if the last harness run failed — if so, don't
                    # claim DONE; let max_cycles handle the abort.
                    last_harness_failed = (
                        state.harness_results
                        and not state.harness_results[-1].passed
                    )
                    if not last_harness_failed:
                        state.status = RunStatus.DONE
                        _ = on_event
                        _(_fmtc("qontroller",
                            f"All briQs verified DONE — work complete in {state.cycle} cycle(s)."))
                        log.emit("run.completed", status="success",
                                 cycle=state.cycle)
                        _write_snapshot(config.run_root, "final.json",
                                        _final_snapshot(state, config))
                        # Send completion callback to Obelisk (non-blocking)
                        try:
                            _maybe_callback(config.run_root)
                        except Exception:
                            pass  # Never fail run because callback failed
                        break

            for g in active:
                log.emit("build_group.queued",
                         build_group_id=g.id, safe_id=g.safe_id,
                         name=g.name, cycle=state.cycle)
            sequential_groups = [g for g in active if not g.parallel_safe]
            parallel_groups = [g for g in active if g.parallel_safe]

            # ====================================================
            # Sequential groups: build one, merge immediately, then build next
            # ====================================================
            build_issues: List[ReviewIssue] = []
            merge_issues: List[ReviewIssue] = []

            _sc = _stream_config()
            # Emit started for sequential groups
            for g in sequential_groups:
                activity.action_status = "Building"
                log.emit("action_status_changed", action_status=activity.action_status, source="build")
                log.emit("build_group.started",
                         build_group_id=g.id, safe_id=g.safe_id,
                         name=g.name, cycle=state.cycle)
            abort_cycle = _build_and_merge_sequential_groups(
                sequential_groups, adapter, state, workspaces,
                config, log, build_issues, merge_issues,
                stream_config=_sc,
            )
            if abort_cycle:
                _write_snapshot(
                    config.run_root,
                    f"cycle-{state.cycle:03d}-after-build.json",
                    _cycle_snapshot(state),
                )
                # Merge issues take priority — apply repair notes first
                if merge_issues:
                    _handle_merge_failures(merge_issues, state, log, on_event, config)
                    merge_issues.clear()  # Clear to avoid double-handling in parallel section
                elif build_issues:
                    _handle_build_failures(build_issues, state, log, on_event)
                # DO NOT skip — fall through to build parallel groups
                # and then InspeQtor will review everything

            # ====================================================
            # Parallel groups: build concurrently from the new integrated HEAD
            # (which now includes all sequential merges)
            # ====================================================
            briqs_by_group = {
                g.id: [state.plan.briqs[bid]
                       for bid in g.briq_ids]
                for g in parallel_groups
            }

            if parallel_groups:
                _sc = _stream_config()
                parallel_build_results = _build_parallel_groups(
                    parallel_groups, adapter, state, briqs_by_group,
                    workspaces, config, log,
                    stream_config=_sc,
                )
                # Collect all parallel build results and check for failures
                for g in parallel_groups:
                    result = parallel_build_results.get(g.id, {})
                    # Persist construqtor output for the chain
                    state.build_results[g.id] = result
                    if result.get("status") == "failed":
                        issue = ReviewIssue(
                            build_group_id=g.id, briq_id=None,
                            severity="blocking",
                            what_is_wrong=(
                                f"ConstruQtor build failed for group "
                                f"'{g.name}': {result.get('error', 'unknown error')}"
                            ),
                            what_to_fix=(
                                f"Fix the build failure in group '{g.name}'"
                            ),
                        )
                        build_issues.append(issue)
                        log.emit("build.failed",
                                 build_group_id=g.id, cycle=state.cycle,
                                 error=result.get("error", ""))
                    else:
                        # Build succeeded — emit completed event for read model
                        log.emit("build_group.completed",
                                 build_group_id=g.id, safe_id=g.safe_id,
                                 name=g.name, cycle=state.cycle,
                                 **_progress_event_fields(state))

                if build_issues:
                    _handle_build_failures(build_issues, state, log, on_event)
                    _write_snapshot(
                        config.run_root,
                        f"cycle-{state.cycle:03d}-after-build.json",
                        _cycle_snapshot(state),
                    )
                    # DO NOT skip — fall through to InspeQtor for review

                # Merge parallel groups one by one (all from same HEAD)
                # Skip groups whose build failed — they have nothing to merge.
                _failed_group_ids = {issue.build_group_id for issue in build_issues}
                for g in parallel_groups:
                    if g.id in _failed_group_ids:
                        log.emit("workspace.merge.skipped",
                                 build_group_id=g.id, cycle=state.cycle,
                                 reason="build_failed")
                        continue
                    ok, err = _merge_and_log(g, workspaces, state.cycle,
                                             log, config.repo_root)
                    if not ok:
                        issue = workspaces.merge_conflict_issue(
                            g.id, state.cycle, err or "")
                        merge_issues.append(issue)

                if merge_issues:
                    _handle_merge_failures(merge_issues, state, log, on_event, config)
                    _write_snapshot(
                        config.run_root,
                        f"cycle-{state.cycle:03d}-after-build.json",
                        _cycle_snapshot(state),
                    )
                    # DO NOT skip — fall through to InspeQtor for review

            _write_snapshot(
                config.run_root,
                f"cycle-{state.cycle:03d}-after-build.json",
                _cycle_snapshot(state),
            )

            # ---- Harness ----
            if config.harness_commands:
                state.status = RunStatus.HARNESSING
                _ = on_event
                _(_fmtc("qontroller",
                    f"running {len(config.harness_commands)} harness check(s)..."))
                activity.action_status = "Running checks"
                log.emit("action_status_changed", action_status=activity.action_status, source="harness")
                log.emit("harness.started", cycle=state.cycle,
                         commands=config.harness_commands)

                harness = ShellHarness(config.harness_commands)
                hr = harness.run(HarnessContext(
                    run_id=run_id, cycle=state.cycle,
                    repo_root=config.repo_root,
                    run_root=config.run_root,
                ))
                state.harness_results.append(hr)

                _write_snapshot(
                    config.run_root,
                    f"cycle-{state.cycle:03d}-after-harness.json",
                    _cycle_snapshot(state),
                )

                if hr.passed:
                    activity.last_exit_code = 0
                    activity.action_status = "Building"
                    log.emit("action_status_changed", action_status=activity.action_status, source="harness")
                    log.emit("harness.completed", cycle=state.cycle,
                             total_checks=hr.total_checks,
                             duration=hr.duration_seconds)
                    log.emit("last_exit_status_updated",
                             exit_code=0, symbol="\u2713", source="harness")
                else:
                    exit_code = hr.failures[0].exit_code if hr.failures else 1
                    activity.last_exit_code = exit_code
                    log.emit("last_exit_status_updated",
                             exit_code=exit_code, symbol="\u21af", source="harness")
                    log.emit("harness.failed", cycle=state.cycle,
                             failures=[_failure_dict(f)
                                       for f in hr.failures])
                    _ = on_event
                    _(_fmtc("qontroller",
                        f"{len(hr.failures)} harness check(s) FAILED."))

                    harness_issues = _harness_to_review_issues(
                        hr, parallel_groups + sequential_groups)
                    log.emit("repair.issues_mapped",
                             issue_count=len(harness_issues),
                             source="harness")
                    _apply_repair_issues(state.plan, harness_issues, log, state.cycle)

                    if not config.review_on_harness_failure:
                        # DO NOT skip — fall through to InspeQtor for review
                        pass

            # ---- Review (InspeQtor) ----
            state.status = RunStatus.REVIEWING
            _ = on_event

            # #4: Narrow scope — only review groups that haven't been fully accepted
            all_groups = parallel_groups + sequential_groups
            groups_to_review = _filter_unaccepted_groups(all_groups, state.cycle)
            skipped_count = len(all_groups) - len(groups_to_review)
            if skipped_count > 0:
                _(_fmtc("inspeqtor",
                    f"skipping {skipped_count} already-accepted group(s), "
                    f"reviewing {len(groups_to_review)} group(s)..."))
            else:
                _(_fmtc("inspeqtor", "reviewing against the clarified task..."))
            _set_active_agent("inspeqtor", model_code=model_code_for(config.model_inspeqtor))
            _refresh_sticky()

            # #3: Parallel inspeQtor per group (when >1 group to review)
            verdict = _run_inspeqtor_parallel(
                adapter, state.clarified_task,
                groups_to_review,
                workspaces, config.repo_root,
                config.model_inspeqtor, state.cycle,
                config.run_root, event_log=log,
                stream_config=_stream_config(),
                plan=state.plan,
                verdict_history=list(state.verdict_history),
                log=log,
                reasoning_effort=config.reasoning_inspeqtor,
            )

            # #4: Mark groups with no issues as fully_accepted
            _mark_accepted_groups(groups_to_review, verdict)

            # Re-include skipped groups in the verdict's effective perspective:
            # if all reviewed groups pass AND all skipped groups were accepted,
            # the whole cycle passes.
            skipped_accepted = [g for g in all_groups if g.id not in {gr.id for gr in groups_to_review}]
            if verdict.passed and skipped_accepted:
                # All reviewed pass + all skipped were previously accepted → DONE
                pass  # verdict.passed stays True

            state.verdict_history.append(verdict)
            log.emit("review.verdict",
                     **verdict.to_dict(),
                     **_progress_event_fields(
                         state, score=verdict.score,
                         final_verdict=verdict.status,
                         active_agent="inspeqtor"))
            activity.action_status = "Evaluating the result"
            log.emit("action_status_changed", action_status=activity.action_status, source="review")

            # Update score from inspeQtor verdict
            activity.score = verdict.score
            log.emit("inspection_score_recorded", role="inspeqtor",
                     cycle=state.cycle, score=verdict.score,
                     status=verdict.status, call_id=activity.call_id,
                     **_progress_event_fields(
                         state, score=verdict.score,
                         final_verdict=verdict.status,
                         active_agent="inspeqtor"))
            _refresh_sticky()

            _write_snapshot(
                config.run_root,
                f"cycle-{state.cycle:03d}-after-review.json",
                _cycle_snapshot(state),
            )

            if verdict.passed:
                # InspeQtor approved — mark all AWAITING_REVIEW briQs as DONE.
                # This covers both reviewed and previously-accepted groups,
                # because parallel inspeQtor may have accepted some groups
                # in prior cycles but their briQs stayed at AWAITING_REVIEW.
                if state.plan:
                    for briq in state.plan.briqs.values():
                        if briq.status == BriqStatus.AWAITING_REVIEW:
                            briq.status = BriqStatus.DONE
                            log.emit("briq.status_changed",
                                     briq_id=briq.id, status="done",
                                     build_group_id=briq.build_group_id,
                                     cycle=state.cycle,
                                     source="inspeqtor_approved")
                state.status = RunStatus.DONE
                activity.action_status = "FULLY_DONE"
                _ = on_event
                _(_fmtc("inspeqtor",
                    f"\033[32mFULLY_DONE\033[0m. Done in {state.cycle} cycle(s)."))
                log.emit("run.completed", status="success",
                         cycle=state.cycle)
                if sticky_line and sticky_line.is_active:
                    _refresh_sticky()
                _write_snapshot(config.run_root, "final.json",
                                _final_snapshot(state, config))
                # Send completion callback to Obelisk (non-blocking)
                try:
                    _maybe_callback(config.run_root)
                except Exception:
                    pass  # Never fail run because callback failed
                break

            _ = on_event
            _(_fmtc("inspeqtor",
                f"\033[31mNOT_DONE\033[0m ({len(verdict.issues)} issue(s)). "
                f"Feeding fixes back to construQtor."))

            # ---- inspeQtor -> construQtor review-to-build handoff ----
            # The reviewer returned the output to the builder for another build.
            # This is the ONLY place the cycle advances: exactly +1 per handoff.
            state.cycle += 1
            # Check cycle limit (0 = unlimited) AFTER the increment so a handoff
            # that would exceed max_cycles is aborted here, before rebuilding.
            if state.max_cycles > 0 and state.cycle > state.max_cycles:
                state.status = RunStatus.ABORTED
                activity.action_status = "STOPPED"
                log.emit("run.aborted", reason="max_cycles_exceeded",
                         cycle=state.cycle)
                _write_snapshot(config.run_root, "final.json",
                                _final_snapshot(state, config))
                if sticky_line and sticky_line.is_active:
                    _refresh_sticky()
                _ = on_event
                _(_fmtc("qontroller",
                    f"Hit max_cycles ({state.max_cycles}) without "
                    f"\033[31mNOT_DONE\033[0m. Hit max_cycles — Stopping, check events.jsonl."))
                # Send terminal callback for max-cycles abort
                try:
                    _maybe_callback(config.run_root)
                except Exception:
                    pass
                break

            state.status = RunStatus.REPAIRING
            _apply_repair_issues(state.plan, verdict.issues, log, state.cycle,
                                 force=True,
                                 reviewed_group_ids=set(g.id for g in parallel_groups + sequential_groups))
            log.emit("repair.issues_mapped",
                     issue_count=len(verdict.issues),
                     source="inspeqtor")

    except Exception as exc:
        activity.action_status = "FAILED"
        if sticky_line and sticky_line.is_active:
            _refresh_sticky()
        log.emit("run.failed", error=str(exc), cycle=state.cycle)
        _write_snapshot(config.run_root, "final.json",
                        _final_snapshot(state, config, error=str(exc)))
        # Send terminal callback for failure before re-raising
        try:
            _maybe_callback(config.run_root)
        except Exception:
            pass  # Never fail run because callback failed
        raise
    finally:
        _idle_ticker_running = False
        # Ensure idle ticker thread exits cleanly before other teardown.
        # The thread is daemon=True so it won't keep the process alive,
        # but a brief join prevents race conditions during cleanup.
        try:
            _idle_thread.join(timeout=0.5)
        except Exception:
            pass
        log.emit("web.dashboard_stopped")
        if sticky_line:
            try:
                sticky_line.stop()
            except Exception:
                pass
        log.close()
        workspaces.cleanup_stale_worktrees()

    return state


# ---------------------------------------------------------------------------
# Sequential build + merge (one at a time, with immediate merge)
# ---------------------------------------------------------------------------
def _build_and_merge_sequential_groups(
    sequential_groups: List[BuildGroup],
    adapter: AgentAdapter,
    state: RunState,
    workspaces: WorkspaceManager,
    config: QontrollerConfig,
    log: EventLog,
    build_issues: List[ReviewIssue],
    merge_issues: List[ReviewIssue],
    stream_config: dict = None,
) -> bool:
    """Build each sequential group and merge immediately.
    Returns True if the cycle should be aborted (build or merge failure)."""
    if not sequential_groups:
        return False

    for g in sequential_groups:
        if not state.plan:
            continue
        briqs = [state.plan.briqs[bid]
                 for bid in g.briq_ids
                 if bid in state.plan.briqs]
        if not briqs:
            continue

        # Build this one group
        try:
            result = run_construqtor_for_group(
                adapter, state.clarified_task, g, briqs,
                workspaces, config.model_construqtor, state.cycle,
                event_log=log,
                run_root=config.run_root,
                workspace_root=config.repo_root,
                stream_config=stream_config,
                reasoning_effort=config.reasoning_construqtor,
            )
            # Persist construqtor output for the chain
            state.build_results[g.id] = result
            if result.get("status") == "failed":
                issue = ReviewIssue(
                    build_group_id=g.id, briq_id=None,
                    severity="blocking",
                    what_is_wrong=(
                        f"ConstruQtor build failed for sequential group "
                        f"'{g.name}': {result.get('error', 'unknown error')}"
                    ),
                    what_to_fix=(
                        f"Fix the build failure in sequential group '{g.name}'"
                    ),
                )
                build_issues.append(issue)
                log.emit("build.failed",
                         build_group_id=g.id, cycle=state.cycle,
                         error=result.get("error", ""))
                return True
        except Exception as exc:
            state.build_results[g.id] = {"status": "failed", "error": str(exc)}
            issue = ReviewIssue(
                build_group_id=g.id, briq_id=None,
                severity="blocking",
                what_is_wrong=(
                    f"ConstruQtor exception for sequential group "
                    f"'{g.name}': {exc}"
                ),
                what_to_fix=(
                    f"Fix the exception in sequential group '{g.name}'"
                ),
            )
            build_issues.append(issue)
            log.emit("build.failed",
                     build_group_id=g.id, cycle=state.cycle,
                     error=str(exc))
            return True

        # Emit build_group.completed so the read model knows all briQs in this group are done
        log.emit("build_group.completed",
                 build_group_id=g.id, safe_id=g.safe_id,
                 name=g.name, cycle=state.cycle,
                 **_progress_event_fields(state))

        # Merge immediately so next sequential group sees this group's changes
        ok, err = _merge_and_log(g, workspaces, state.cycle,
                                 log, config.repo_root)
        if not ok:
            issue = workspaces.merge_conflict_issue(
                g.id, state.cycle, err or "")
            merge_issues.append(issue)
            return True

    return False


# ---------------------------------------------------------------------------
# Parallel group builder
# ---------------------------------------------------------------------------
def _build_sibling_info(parallel_groups: List[BuildGroup],
                        briqs_by_group: Dict[str, List[BriQ]]) -> dict:
    """Collect sibling info so parallel agents are aware of each others' files.
    Returns dict keyed by group id with a summary of what other groups are doing."""
    sibling_info: dict = {}
    for g in parallel_groups:
        others = []
        for og in parallel_groups:
            if og.id == g.id:
                continue
            og_briqs = briqs_by_group.get(og.id, [])
            og_expected = set()
            for b in og_briqs:
                if b.expected_files:
                    og_expected.update(b.expected_files)
            others.append({
                "group_name": og.name,
                "group_id": og.id,
                "briqs": [b.title for b in og_briqs],
                "expected_files": sorted(og_expected),
            })
        sibling_info[g.id] = others
    return sibling_info


def _build_parallel_groups(
    parallel_groups: List[BuildGroup],
    adapter: AgentAdapter,
    state: RunState,
    briqs_by_group: Dict[str, List[BriQ]],
    workspaces: WorkspaceManager,
    config: QontrollerConfig,
    log: EventLog,
    stream_config: dict = None,
) -> Dict[str, Dict]:
    """Build all parallel groups concurrently from the same HEAD.

    Staggered spawning with configurable delay to avoid overwhelming
    the provider (e.g. codeseeq) with simultaneous spawns.
    Groups are also made aware of sibling group files to avoid conflicts.
    Returns dict of build results keyed by group id."""
    import concurrent.futures
    import time as _time
    import threading

    results: Dict[str, Dict] = {}
    if not parallel_groups:
        return results

    delay = getattr(config, 'parallel_spawn_delay_seconds', 1.0)

    # Build sibling awareness data
    sibling_info = _build_sibling_info(parallel_groups, briqs_by_group)

    # Lock and event for staggered submission
    submit_lock = threading.Lock()
    next_submit_time = [0.0]  # mutable counter

    def _submit_with_delay(pool, fn, group, briqs, sibling):
        """Submit with staggered delay — only one thread runs this at a time
        due to submit_lock, so delay is measured between actual spawns."""
        with submit_lock:
            now = _time.monotonic()
            wait = next_submit_time[0] - now
            if wait > 0:
                log.emit("build.parallel_stagger_delay",
                         build_group_id=group.id, group_name=group.name,
                         delay_seconds=round(wait, 2))
                _time.sleep(wait)
            next_submit_time[0] = _time.monotonic() + delay
            return pool.submit(
                fn, adapter, state.clarified_task,
                group, briqs, workspaces,
                config.model_construqtor, state.cycle, event_log=log,
                run_root=config.run_root,
                stream_config=stream_config,
                workspace_root=config.repo_root,
                reasoning_effort=config.reasoning_construqtor,
                sibling_info=sibling,
            )

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=config.max_parallel_build_groups) as pool:
        futures = {}
        for g in parallel_groups:
            sibling = sibling_info.get(g.id, [])
            briqs = briqs_by_group.get(g.id, [])
            fut = _submit_with_delay(pool, run_construqtor_for_group,
                                     g, briqs, sibling)
            futures[fut] = g

        for fut in concurrent.futures.as_completed(futures):
            g = futures[fut]
            try:
                results[g.id] = fut.result()
            except Exception as exc:
                results[g.id] = {
                    "status": "failed", "error": str(exc)}

    return results


# ---------------------------------------------------------------------------
# Failure handlers
# ---------------------------------------------------------------------------
def _handle_build_failures(
    build_issues: List[ReviewIssue],
    state: RunState,
    log: EventLog,
    on_event: Callable[[str], None],
) -> None:
    """Handle build failures: map to repair issues, then route to InspeQtor for review."""
    state.status = RunStatus.REPAIRING
    log.emit("repair.issues_mapped",
             issue_count=len(build_issues),
             source="build")
    _apply_repair_issues(state.plan, build_issues, log, state.cycle,
                         force=True)
    _ = on_event
    _(_fmt("qontroller",
        f"Build failure(s): {len(build_issues)} issue(s). "
        f"Repair notes applied — routing to InspeQtor for review."))


def _handle_merge_failures(
    merge_issues: List[ReviewIssue],
    state: RunState,
    log: EventLog,
    on_event: Callable[[str], None],
    config: QontrollerConfig,
) -> None:
    """Handle merge failures: map to repair issues, then route to InspeQtor for review."""
    state.status = RunStatus.REPAIRING
    log.emit("repair.issues_mapped",
             issue_count=len(merge_issues),
             source="merge")
    _apply_repair_issues(state.plan, merge_issues, log, state.cycle,
                         force=True)
    _ = on_event
    _(_fmt("qontroller",
        f"Merge failure(s): {len(merge_issues)} issue(s). "
        f"Repair notes applied — routing to InspeQtor for review."))


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auto-detect parallel safety by checking expected_files overlap
# ---------------------------------------------------------------------------
def _auto_mark_parallel_safe(plan) -> None:
    """Analyze all build groups and auto-mark non-overlapping ones as
    parallel_safe: true. Different .svelte / component files never conflict.
    Only groups that share expected_files are kept sequential."""
    if not plan or not plan.build_groups:
        return
    groups = list(plan.build_groups.values())
    # Collect expected files per group
    group_files: dict = {}
    for g in groups:
        files = set()
        for bid in g.briq_ids:
            briq = plan.briqs.get(bid)
            if briq and briq.expected_files:
                files.update(briq.expected_files)
        group_files[g.id] = files

    for g in groups:
        if not g.parallel_safe:
            # Check if this group overlaps with any other group
            my_files = group_files.get(g.id, set())
            if not my_files:
                continue  # Can't determine, leave as-is
            overlaps = False
            for other in groups:
                if other.id == g.id:
                    continue
                other_files = group_files.get(other.id, set())
                if other_files and my_files & other_files:
                    overlaps = True
                    break
            if not overlaps:
                g.parallel_safe = True



# ---------------------------------------------------------------------------
# Parallel inspeQtor per group + scope narrowing (qq-efficiency.md #3 + #4)
# ---------------------------------------------------------------------------
def _filter_unaccepted_groups(groups: list, cycle: int) -> list:
    """Return only groups that haven't been fully accepted yet (#4)."""
    if cycle == 1:
        return list(groups)  # First cycle: review everything
    unaccepted = [g for g in groups if not g.fully_accepted]
    if not unaccepted:
        return list(groups)  # Safety: if all accepted, re-review all
    return unaccepted


def _run_inspeqtor_parallel(
    adapter, clarified, groups, workspaces, repo_root, model, cycle,
    run_root, event_log, stream_config, plan, verdict_history, log,
    reasoning_effort: str = "",
) -> ReviewVerdict:
    """Run inspeQtor per group in parallel and aggregate verdicts (#3).

    Each group gets its own inspeQtor call via ThreadPoolExecutor.
    Results are aggregated into a single composite verdict.
    """
    import concurrent.futures
    from .models import ReviewVerdict, ReviewIssue

    if len(groups) == 0:
        return ReviewVerdict(cycle=cycle, status="FULLY_DONE", score=100,
                             summary="No groups to review.", issues=[])

    if len(groups) == 1:
        # Single group — no parallelism needed
        return run_inspeqtor(
            adapter, clarified, groups, workspaces, repo_root,
            model, cycle, run_root, event_log=event_log,
            workspace_root=repo_root,
            stream_config=stream_config, plan=plan,
            verdict_history=verdict_history,
            reasoning_effort=reasoning_effort,
        )

    # Multiple groups: run inspeQtor per group in parallel
    def _review_one(group):
        # Use a unique suffix per group to avoid prompt/output file races
        # when multiple inspeQtor agents run concurrently in the same workdir.
        suffix = f"_{group.id}" if group.id else ""
        return run_inspeqtor(
            adapter, clarified, [group], workspaces, repo_root,
            model, cycle, run_root, event_log=event_log,
            workspace_root=repo_root,
            stream_config=stream_config, plan=plan,
            verdict_history=verdict_history,
            reasoning_effort=reasoning_effort,
            group_suffix=suffix,
        )

    max_workers = min(len(groups), 8)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_review_one, g): g for g in groups}
        results = []
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                g = futures[fut]
                log.emit("review.per_group_error",
                         group_id=g.id, group_name=g.name, error=str(exc))

    if not results:
        return ReviewVerdict(cycle=cycle, status="NOT_DONE", score=0,
                             summary="All per-group reviews failed.",
                             issues=[])

    # Aggregate: PASS only if ALL groups PASS
    all_issues = []
    all_scores = []
    all_summaries = []
    for v in results:
        all_issues.extend(v.issues)
        all_scores.append(v.score)
        all_summaries.append(v.summary)

    avg_score = sum(all_scores) // len(all_scores)
    all_passed = all(v.passed for v in results)

    aggregate = ReviewVerdict(
        cycle=cycle,
        status="FULLY_DONE" if all_passed else "NOT_DONE",
        score=avg_score,
        summary="; ".join(all_summaries),
        issues=all_issues,
    )
    return aggregate


def _mark_accepted_groups(groups: list, verdict: ReviewVerdict) -> None:
    """Mark groups with no blocking issues as fully_accepted (#4).

    A group is accepted if no issue in the verdict references its ID.
    """
    if not verdict or not groups:
        return
    # Collect group IDs that have issues
    groups_with_issues = set()
    for issue in verdict.issues:
        if issue.build_group_id:
            groups_with_issues.add(issue.build_group_id)

    for g in groups:
        if g.id not in groups_with_issues and not g.fully_accepted:
            g.fully_accepted = True


def _active_groups(state: RunState) -> List[BuildGroup]:
    """Return build groups that need work this cycle.

    A group is "active" if it contains at least one briQ with status
    PENDING, IN_PROGRESS, AWAITING_REVIEW, NEEDS_REPAIR, or FAILED -
    i.e. not all briQs are DONE. A group where every briQ is DONE has been verified by
    inspeQtor and does not need re-building.

    The "all groups first cycle" behaviour: if NO briQs are DONE yet
    (all PENDING), all groups are active - that's the fresh start."""
    if not state.plan:
        return []
    all_groups = list(state.plan.build_groups.values())

    # A group is fully done when ALL its briQs are DONE
    active = []
    for bg in all_groups:
        briqs_in_group = [
            state.plan.briqs[bid] for bid in bg.briq_ids
            if bid in state.plan.briqs
        ]
        if not briqs_in_group:
            continue
        all_done = all(b.status == BriqStatus.DONE for b in briqs_in_group)
        if not all_done:
            active.append(bg)
    return active

def _merge_and_log(g: BuildGroup, workspaces: WorkspaceManager,
                   cycle: int, log: EventLog,
                   repo_root: str) -> tuple:
    log.emit("workspace.merge.started",
             build_group_id=g.id, cycle=cycle)
    ok, err = workspaces.merge_build_group(g.id, cycle)
    if ok:
        log.emit("workspace.merge.completed",
                 build_group_id=g.id, cycle=cycle)
    else:
        log.emit("workspace.merge.failed",
                 build_group_id=g.id, cycle=cycle,
                 error=str(err or ""))
    return ok, err


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_snapshot(run_root: str, filename: str,
                    data: dict) -> None:
    state_dir = os.path.join(run_root, "state")
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, filename), "w",
              encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def _progress_event_fields(state: RunState, *,
                             score: Optional[float] = None,
                             final_verdict: Optional[str] = None,
                             active_agent: str = "") -> dict:
    """Compute the web read-model's canonical displayed progress and return the
    event fields that carry it to the TUI, so both UIs truncate the SAME decimal
    to the same integer tick-for-tick (B1 cross-cutting progress-source parity).

    The web dashboard reads effective_progress_pct = displayed_pct from
    qq/progress.calculate_progress(...). This helper derives the same groups
    from the live run state and feeds that exact formula, then returns the
    effective_progress_pct/displayed_pct pair for log.emit.
    """
    if not state.plan or not state.plan.build_groups:
        return {}

    groups = []
    for bg in state.plan.build_groups.values():
        briqs = []
        all_done = True
        any_needs_repair = False
        any_awaiting_review = False
        any_in_progress = False
        for bid in bg.briq_ids:
            b = state.plan.briqs.get(bid)
            bst = b.status.value if b else "pending"
            briqs.append({
                "id": b.id if b else bid,
                "safe_id": b.safe_id if b else bid,
                "status": bst,
            })
            if bst == "done":
                pass
            elif bst in ("needs_repair", "failed"):
                all_done = False
                any_needs_repair = True
            elif bst == "awaiting_review":
                all_done = False
                any_awaiting_review = True
            elif bst == "in_progress":
                all_done = False
                any_in_progress = True
            else:
                all_done = False

        if bg.fully_accepted:
            g_status = "done"
        elif all_done:
            g_status = "done"
        elif any_needs_repair:
            g_status = "repair_needed"
        elif any_awaiting_review:
            g_status = "ready_for_review"
        elif any_in_progress:
            g_status = "building"
        else:
            g_status = "planned"

        groups.append({
            "id": bg.id,
            "name": bg.name,
            "title": bg.name,
            "status": g_status,
            "progress_weight_pct": None,
            "briqs": briqs,
        })

    if final_verdict is None and state.last_verdict:
        final_verdict = state.last_verdict.status

    run_status = state.status.value
    snapshot = calculate_progress(
        groups=groups,
        active_agent=active_agent or run_status,
        final_verdict=final_verdict,
        run_status=run_status,
        inspeqtor_score=score,
    )
    displayed_pct = snapshot.to_dict().get("displayed_pct", 0.0)
    return {
        "effective_progress_pct": displayed_pct,
        "displayed_pct": displayed_pct,
    }


def _cycle_snapshot(state: RunState) -> dict:
    return {
        "run_id": state.run_id,
        "cycle": state.cycle,
        "status": state.status.value,
        "briq_statuses": {
            bid: b.status.value
            for bid, b in (state.plan.briqs.items()
                           if state.plan else {})
        },
        "verdicts": [v.to_dict() for v in state.verdict_history],
        "build_results": state.build_results,
    }


def _final_snapshot(state: RunState, config: QontrollerConfig,
                    error: str = None) -> dict:
    d = {
        "run_id": state.run_id,
        "status": state.status.value,
        "cycle": state.cycle,
        "run_root": config.run_root,
        "repo_root": config.repo_root,
        "final_verdict": (state.verdict_history[-1].to_dict()
                          if state.verdict_history else None),
        "harness_results": [
            {"passed": hr.passed, "total_checks": hr.total_checks,
             "duration_seconds": hr.duration_seconds}
            for hr in state.harness_results
        ],
        "build_results": state.build_results,
        "unresolved_issues": (
            [i for i in (state.last_verdict.issues
                         if state.last_verdict and not state.last_verdict.passed
                         else [])]
        ),
    }
    if error:
        d["error"] = error
    return d



def _apply_to_group_repairable(plan: Plan, bg_id: str, note: str,
                              log: EventLog, cycle: int,
                              force: bool = False,
                              reviewed_group_ids: set = None) -> None:
    """Apply a repair note only to briQs in the group that are NOT already
    DONE without repair notes. This prevents re-queuing already-verified briQs
    when a group-level issue only affects some briQs.

    When force=True (used for merge conflicts and build failures), DONE briQs
    that haven't been verified by inspeQtor are also re-opened. DONE briQs
    with existing repair notes were already flagged — those always re-open.

    When reviewed_group_ids is provided, DONE briQs in reviewed groups are
    considered unverified (this cycle's build) and re-openable."""
    bg = plan.build_groups.get(bg_id)
    if not bg:
        return
    in_reviewed_group = reviewed_group_ids and bg_id in reviewed_group_ids
    for bid in bg.briq_ids:
        briq = plan.briqs.get(bid)
        if not briq:
            continue
        if briq.status in (BriqStatus.PENDING, BriqStatus.FAILED, BriqStatus.AWAITING_REVIEW):
            briq.repair_notes.append(note)
            briq.status = BriqStatus.NEEDS_REPAIR
            log.emit("briq.status_changed",
                     briq_id=bid, status="needs_repair",
                     build_group_id=bg_id, cycle=cycle)
        elif briq.status == BriqStatus.DONE:
            # Re-queue if:
            #   a) The briQ already has repair notes (flagged by inspeQtor), OR
            #   b) The briQ is in a group being reviewed this cycle (just built,
            #      not yet verified), OR
            #   c) force=True (merge/build failure)
            re_open = bool(briq.repair_notes) or force or in_reviewed_group
            if re_open:
                briq.repair_notes.append(note)
                briq.status = BriqStatus.NEEDS_REPAIR
                log.emit("briq.status_changed",
                         briq_id=bid, status="needs_repair",
                         build_group_id=bg_id, cycle=cycle)
        # NEEDS_REPAIR and IN_PROGRESS briQs always get the note
        else:
            briq.repair_notes.append(note)
            briq.status = BriqStatus.NEEDS_REPAIR
            log.emit("briq.status_changed",
                     briq_id=bid, status="needs_repair",
                     build_group_id=bg_id, cycle=cycle)


def _apply_repair_issues(plan: Plan,
                         issues: List[ReviewIssue],
                         log: EventLog,
                         cycle: int,
                         force: bool = False,
                         reviewed_group_ids: set = None) -> None:
    # Build name→id lookup tables for fuzzy matching
    group_name_to_id = {}
    group_id_to_name = {}
    briq_title_to_id = {}
    briq_id_to_title = {}
    for bg_id, bg in plan.build_groups.items():
        group_name_to_id[bg.name.lower().strip()] = bg_id
        group_id_to_name[bg_id] = bg.name.lower().strip()
    for b_id, b in plan.briqs.items():
        briq_title_to_id[b.title.lower().strip()] = b_id
        briq_id_to_title[b_id] = b.title.lower().strip()

    for issue in issues:
        note = (
            f"[{issue.severity}] {issue.what_is_wrong}"
            f" -> {issue.what_to_fix}"
        )
        matched = False

        # 1. Exact briq_id match
        if issue.briq_id and issue.briq_id in plan.briqs:
            plan.briqs[issue.briq_id].repair_notes.append(note)
            plan.briqs[issue.briq_id].status = BriqStatus.NEEDS_REPAIR
            matched = True

        # 2. Fuzzy briq_id match (inspeqtor may use title instead of ID)
        if not matched and issue.briq_id:
            fuzzy_key = issue.briq_id.lower().strip()
            if fuzzy_key in briq_title_to_id:
                real_id = briq_title_to_id[fuzzy_key]
                plan.briqs[real_id].repair_notes.append(note)
                plan.briqs[real_id].status = BriqStatus.NEEDS_REPAIR
                matched = True

        # 3. Exact build_group_id match — only apply to briQs that aren't
        # already DONE (without repair). DONE briQs stay done; inspeQtor already
        # verified them. Only escalates if the briQ is PENDING or FAILED.
        # When force=True (merge/build failures), re-opens DONE briQs too.
        if not matched and issue.build_group_id in plan.build_groups:
            _apply_to_group_repairable(
                plan, issue.build_group_id, note, log, cycle, force=force,
                reviewed_group_ids=reviewed_group_ids)
            matched = True

        # 4. Fuzzy build_group_id match (inspeqtor may use name instead of ID)
        if not matched and issue.build_group_id:
            fuzzy_key = issue.build_group_id.lower().strip()
            if fuzzy_key in group_name_to_id:
                _apply_to_group_repairable(
                    plan, group_name_to_id[fuzzy_key], note, log, cycle,
                    force=force,
                    reviewed_group_ids=reviewed_group_ids)
                matched = True

        # 5. Last resort — match only briQs that are PENDING, FAILED, or
        # AWAITING_REVIEW; never re-mark already-DONE briQs unless they already
        # have repair notes.
        if not matched:
            for briq in plan.briqs.values():
                if briq.status in (BriqStatus.PENDING, BriqStatus.FAILED, BriqStatus.AWAITING_REVIEW):
                    briq.repair_notes.append(note)
                    briq.status = BriqStatus.NEEDS_REPAIR
                elif briq.status == BriqStatus.DONE:
                    # Only add if the briQ already has pending repair notes
                    # (i.e. it's a known-broken briQ, which should stay broken).
                    if briq.repair_notes:
                        briq.repair_notes.append(note)
                        briq.status = BriqStatus.NEEDS_REPAIR


def _harness_to_review_issues(
        hr: HarnessResult,
        groups: List[BuildGroup]) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    for f in hr.failures:
        issues.append(ReviewIssue(
            build_group_id="", briq_id=None,
            severity="blocking",
            what_is_wrong=(
                f"Harness check '{f.check_name}' failed "
                f"(exit {f.exit_code}): {f.error_message}\n"
                f"stdout: {f.stdout[:500]}\n"
                f"stderr: {f.stderr[:500]}"
            ),
            what_to_fix=(
                f"Fix the issue that caused harness check "
                f"'{f.check_name}' to fail."
            ),
        ))
    return issues


def _failure_dict(f: HarnessFailure) -> dict:
    return {
        "check_name": f.check_name, "exit_code": f.exit_code,
        "stdout": f.stdout[:1000], "stderr": f.stderr[:1000],
        "duration_seconds": f.duration_seconds,
        "error_message": f.error_message,
    }
