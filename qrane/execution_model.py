from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PASS_BUILD = "build"
PASS_REPAIR = "repair"
ESTIMATE_MODE_ADVISORY = "advisory"
ESTIMATE_MODE_SCHEDULER = "scheduler"
RESUME_MODE_QUEUED_NEXT_PASS = "queued_next_pass"
RESUME_MODE_INTERRUPTED_ACTIVE_PASS = "interrupted_active_pass"
RESUME_MODE_ADVANCE_DEFAULT_BUILD_PASS = "advance_default_build_pass"
RESUME_MODE_LEGACY_ACTIVE_PASS = "legacy_active_pass"
RESUME_MODE_INTAKE_WAITING_FOR_INPUT = "intake_waiting_for_input"

ACTIVE_LIFECYCLE_STATES = {
    "CLARIFYING",
    "CONSTRAINING",
    "PLANNING",
    "ESTIMATING",
    "BUILDING",
    "VALIDATING",
    "REALIZING",
    "INSPECTING",
    "REPAIRING",
}


@dataclass
class ExecutionLimits:
    max_total_iterations: int
    max_build_passes: int
    max_attempts_per_build_pass: int


@dataclass
class ExecutionState:
    global_iteration_index: int = 0
    pass_kind: str = PASS_BUILD
    build_pass_index: int = 0
    repair_pass_index: int = 0
    repairing_build_pass_index: int | None = None
    cycle_estimate_mode: str = ESTIMATE_MODE_ADVISORY
    estimated_build_passes: int | None = None
    scheduled_build_pass_target: int | None = None
    pending_next_pass_kind: str | None = None
    pending_repairing_build_pass_index: int | None = None
    stop_reason: str | None = None


@dataclass
class ContinuationDecision:
    action: str
    reason: str
    next_pass_kind: str | None = None
    repairing_build_pass_index: int | None = None


@dataclass
class ResumeDecision:
    mode: str
    next_pass_kind: str
    repairing_build_pass_index: int | None = None
    resume_active_pass: bool = False
    confidence: str = "explicit"
    detail: str = ""


def normalize_pass_kind(value: Any) -> str:
    return PASS_REPAIR if str(value or "").strip().lower() == PASS_REPAIR else PASS_BUILD


def normalize_estimate_mode(value: Any) -> str:
    return ESTIMATE_MODE_SCHEDULER if str(value or "").strip().lower() == ESTIMATE_MODE_SCHEDULER else ESTIMATE_MODE_ADVISORY


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _infer_resume_pass_kind(raw_pass_kind: Any, lifecycle_state: str, current_stage: str) -> str:
    if raw_pass_kind not in (None, ""):
        return normalize_pass_kind(raw_pass_kind)
    if lifecycle_state == "REPAIRING" or current_stage == "REPAIR":
        return PASS_REPAIR
    return PASS_BUILD


def resolve_resume_decision(manifest: dict[str, Any] | None = None) -> ResumeDecision:
    manifest = manifest or {}
    execution = (manifest.get("execution") or {})
    state = (execution.get("state") or {})
    resume_state = (execution.get("resume_state") or {})

    global_iteration_index = _int_or_none(state.get("global_iteration_index")) or 0
    build_pass_index = _int_or_none(state.get("build_pass_index")) or 0
    repairing_build_pass_index = _int_or_none(state.get("repairing_build_pass_index"))
    pending_next_pass_kind = normalize_pass_kind(state.get("pending_next_pass_kind")) if state.get("pending_next_pass_kind") else None
    pending_repairing_build_pass_index = _int_or_none(state.get("pending_repairing_build_pass_index"))
    stop_reason = str(state.get("stop_reason") or "").strip().lower()

    # Prioritize explicitly preserved prior state over fresh wrapper manifest state
    effective_run_status = str(resume_state.get("prior_run_status") or manifest.get("run_status") or "").strip().upper()
    effective_lifecycle_state = str(resume_state.get("prior_lifecycle_state") or manifest.get("lifecycle_state") or "").strip().upper()
    effective_current_stage = str(resume_state.get("prior_current_stage") or manifest.get("current_stage") or "").strip().upper()

    interrupted_pass_kind = _infer_resume_pass_kind(state.get("pass_kind"), effective_lifecycle_state, effective_current_stage)
    interrupted_repairing_build_pass_index = repairing_build_pass_index
    if interrupted_pass_kind == PASS_REPAIR and interrupted_repairing_build_pass_index is None:
        interrupted_repairing_build_pass_index = build_pass_index or None

    if pending_next_pass_kind:
        if pending_next_pass_kind == PASS_REPAIR and pending_repairing_build_pass_index is None:
            pending_repairing_build_pass_index = repairing_build_pass_index or build_pass_index or None
        return ResumeDecision(
            mode=RESUME_MODE_QUEUED_NEXT_PASS,
            next_pass_kind=pending_next_pass_kind,
            repairing_build_pass_index=pending_repairing_build_pass_index if pending_next_pass_kind == PASS_REPAIR else None,
            resume_active_pass=False,
            confidence="explicit",
            detail="Manifest contains an explicitly queued next pass.",
        )

    if effective_run_status == "RUN_REPAIR_PENDING":
        return ResumeDecision(
            mode=RESUME_MODE_QUEUED_NEXT_PASS,
            next_pass_kind=PASS_REPAIR,
            repairing_build_pass_index=interrupted_repairing_build_pass_index,
            resume_active_pass=False,
            confidence="inferred",
            detail="Run status indicates repair continuation is pending even though queued pass metadata is absent.",
        )

    clarification_blocked = (
        stop_reason in {"clarification_waiting_for_input", "clarification_round_limit_reached"}
        or (
            effective_run_status == "RUN_WAITING_FOR_INPUT"
            and (effective_lifecycle_state == "BLOCKED" or effective_current_stage == "CLARIFICATION")
        )
    )
    if clarification_blocked:
        return ResumeDecision(
            mode=RESUME_MODE_INTAKE_WAITING_FOR_INPUT,
            next_pass_kind=PASS_BUILD,
            repairing_build_pass_index=None,
            resume_active_pass=True,
            confidence="explicit" if stop_reason in {"clarification_waiting_for_input", "clarification_round_limit_reached"} else "inferred",
            detail="Run is waiting for intake clarification input; resuming cycle-1 clarification semantics.",
        )

    interrupted_active = effective_run_status == "RUN_ACTIVE" or effective_lifecycle_state in ACTIVE_LIFECYCLE_STATES
    if interrupted_active and global_iteration_index > 0:
        return ResumeDecision(
            mode=RESUME_MODE_INTERRUPTED_ACTIVE_PASS,
            next_pass_kind=interrupted_pass_kind,
            repairing_build_pass_index=interrupted_repairing_build_pass_index if interrupted_pass_kind == PASS_REPAIR else None,
            resume_active_pass=True,
            confidence="explicit" if state.get("pass_kind") not in (None, "") else "inferred",
            detail="Resuming interrupted active pass semantics from manifest state.",
        )

    if global_iteration_index <= 0:
        return ResumeDecision(
            mode=RESUME_MODE_ADVANCE_DEFAULT_BUILD_PASS,
            next_pass_kind=PASS_BUILD,
            repairing_build_pass_index=None,
            resume_active_pass=False,
            confidence="explicit",
            detail="No prior pass index recorded; starting first build pass.",
        )

    has_run_status = bool(resume_state.get("prior_run_status") or (manifest.get("run_status") and str(manifest.get("run_status")).strip()))
    if not has_run_status:
        return ResumeDecision(
            mode=RESUME_MODE_LEGACY_ACTIVE_PASS,
            next_pass_kind=interrupted_pass_kind,
            repairing_build_pass_index=interrupted_repairing_build_pass_index if interrupted_pass_kind == PASS_REPAIR else None,
            resume_active_pass=True,
            confidence="low",
            detail="Legacy manifest does not record run_status; conservatively resuming the recorded pass kind.",
        )

    return ResumeDecision(
        mode=RESUME_MODE_ADVANCE_DEFAULT_BUILD_PASS,
        next_pass_kind=PASS_BUILD,
        repairing_build_pass_index=None,
        resume_active_pass=False,
        confidence="inferred",
        detail="No queued continuation or interrupted active pass marker found; defaulting to next build pass.",
    )


def clamp_positive(value: Any, fallback: int, *, minimum: int = 1, maximum: int = 999) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def resolve_execution_limits(config: dict | None = None, cli_total_iterations: int | None = None, cli_build_passes: int | None = None) -> ExecutionLimits:
    config = config or {}
    options = config.get("options", {}) or {}
    repair = config.get("repair", {}) or {}

    # auto_cycle: when true (default) and no CLI overrides, the scheduler
    # determines when to stop. Config caps are generous ceilings so the
    # scheduler can continue as needed; CLI switches (--cyqles, -c) always
    # override and set exact limits.
    auto_cycle = bool(options.get("auto_cycle", True))
    has_cli_override = cli_total_iterations is not None

    if has_cli_override or not auto_cycle:
        # Manual mode: use explicit config or CLI values
        total_iterations = cli_total_iterations
        if total_iterations is None:
            total_iterations = options.get("max_total_iterations", options.get("auto_cycle_limit", 3))
        build_passes = cli_build_passes
        if build_passes is None:
            build_passes = options.get("max_build_passes", total_iterations)
    else:
        # Auto-cycle mode: high ceilings let the scheduler decide
        total_iterations = 200
        build_passes = 200

    repair_attempts = repair.get("max_attempts_per_build_pass", repair.get("max_attempts", 2))
    return ExecutionLimits(
        max_total_iterations=clamp_positive(total_iterations, 4, minimum=1, maximum=200),
        max_build_passes=clamp_positive(build_passes, int(total_iterations or 4), minimum=1, maximum=200),
        max_attempts_per_build_pass=max(0, int(repair_attempts or 0)),
    )


def resolve_cycle_estimate_mode(config: dict | None = None, cli_mode: str | None = None) -> str:
    if cli_mode:
        return normalize_estimate_mode(cli_mode)
    config = config or {}
    return normalize_estimate_mode((config.get("options", {}) or {}).get("cycle_estimate_mode", ESTIMATE_MODE_ADVISORY))


def resolve_scheduled_build_pass_target(
    cycle_estimate_mode: str,
    estimated_build_passes: int | None,
    current_build_pass_index: int,
    limits: ExecutionLimits,
) -> int | None:
    if normalize_estimate_mode(cycle_estimate_mode) != ESTIMATE_MODE_SCHEDULER:
        return None
    if estimated_build_passes is None:
        return None
    target = max(current_build_pass_index, int(estimated_build_passes))
    return min(target, limits.max_build_passes)


def start_next_pass(state: ExecutionState, pass_kind: str, repairing_build_pass_index: int | None = None) -> ExecutionState:
    pass_kind = normalize_pass_kind(pass_kind)
    state.global_iteration_index += 1
    state.pass_kind = pass_kind
    state.stop_reason = None
    if pass_kind == PASS_BUILD:
        state.build_pass_index += 1
        state.repair_pass_index = 0
        state.repairing_build_pass_index = None
    else:
        state.repair_pass_index += 1
        state.repairing_build_pass_index = repairing_build_pass_index or state.build_pass_index or None
    state.pending_next_pass_kind = None
    state.pending_repairing_build_pass_index = None
    return state


def total_iteration_cap_reached(state: ExecutionState, limits: ExecutionLimits) -> bool:
    return state.global_iteration_index >= limits.max_total_iterations


def build_pass_cap_reached(state: ExecutionState, limits: ExecutionLimits) -> bool:
    return state.build_pass_index >= limits.max_build_passes


def repair_cap_reached(state: ExecutionState, limits: ExecutionLimits) -> bool:
    return state.repair_pass_index >= limits.max_attempts_per_build_pass


def can_start_build_pass(state: ExecutionState, limits: ExecutionLimits) -> bool:
    return not total_iteration_cap_reached(state, limits) and not build_pass_cap_reached(state, limits)


def can_start_repair_pass(state: ExecutionState, limits: ExecutionLimits) -> bool:
    return not total_iteration_cap_reached(state, limits) and not repair_cap_reached(state, limits)


def _normalize_verdict_status(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"SUCCESS", "PASS"}:
        return "SUCCESS"
    if raw in {"FAIL", "FAILURE", "ERROR"}:
        return "FAILURE"
    if raw == "PARTIAL":
        return "PARTIAL"
    return raw


def decide_post_inspection(state: ExecutionState, limits: ExecutionLimits, inspection_verdict: dict | None, repair_plan: dict | None) -> ContinuationDecision:
    verdict = inspection_verdict or {}
    repair = repair_plan or {}
    if not verdict:
        return ContinuationDecision("stop_partial", "inspection_artifacts_missing")
    verdict_status = _normalize_verdict_status(verdict.get("status") or verdict.get("assessment"))
    hard_gate_status = str(verdict.get("hard_gate_status") or "").strip().upper()
    task_completed = bool(
        verdict.get("task_completed")
        or verdict_status == "SUCCESS"
        or hard_gate_status == "PASS"
    )
    
    # NEW v1.4: Enforce verdict consistency. SUCCESS cannot pair with repair_required=True.
    if "repair_needed" in verdict:
        repair_required = bool(verdict.get("repair_needed"))
    elif task_completed and verdict_status == "SUCCESS":
        repair_required = False
    elif "repair_required" in verdict:
        repair_required = bool(verdict.get("repair_required"))
    else:
        repair_required = verdict_status in {"PARTIAL", "FAILURE"} and not task_completed
    if hard_gate_status == "PASS":
        repair_required = False
        task_completed = True
    same_run_eligible = bool(repair.get("same_run_repair_eligible"))
    inspection_integrity = str(verdict.get("inspection_integrity") or "").strip().upper()

    if repair_required:
        if same_run_eligible:
            same_fix_repeat_limit = _int_or_none(repair.get("same_fix_repeat_limit"))
            if same_fix_repeat_limit is None or same_fix_repeat_limit <= 0:
                same_fix_repeat_limit = 3
            same_fix_repeat_count = _int_or_none(repair.get("same_fix_repeat_count")) or 0
            if same_fix_repeat_count >= same_fix_repeat_limit:
                return ContinuationDecision("stop_partial", "same_fix_repeat_cap_hit")
            if total_iteration_cap_reached(state, limits):
                return ContinuationDecision("stop_partial", "total_iteration_cap_hit")
            if repair_cap_reached(state, limits):
                return ContinuationDecision("stop_partial", "repair_cap_hit")
            return ContinuationDecision(
                "run_repair",
                "same_run_repair_requested",
                next_pass_kind=PASS_REPAIR,
                repairing_build_pass_index=state.build_pass_index,
            )
        return ContinuationDecision("stop_partial", "repair_requires_linked_continuation")

    if task_completed:
        return ContinuationDecision("stop", "completed")

    if inspection_integrity == "DEGRADED":
        return ContinuationDecision("stop_partial", "inspection_degraded")

    mode = normalize_estimate_mode(state.cycle_estimate_mode)
    if mode == ESTIMATE_MODE_SCHEDULER:
        target = state.scheduled_build_pass_target or state.estimated_build_passes or state.build_pass_index
        if target > state.build_pass_index:
            if total_iteration_cap_reached(state, limits):
                return ContinuationDecision("stop_partial", "total_iteration_cap_hit")
            if build_pass_cap_reached(state, limits):
                return ContinuationDecision("stop_partial", "build_pass_cap_hit")
            return ContinuationDecision("run_build", "scheduler_continuation", next_pass_kind=PASS_BUILD)
        if build_pass_cap_reached(state, limits):
            return ContinuationDecision("stop_partial", "build_pass_cap_hit")

    return ContinuationDecision("stop", "advisory_stop")
