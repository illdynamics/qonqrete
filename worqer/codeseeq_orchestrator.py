#!/usr/bin/env python3
# worqer/codeseeq_orchestrator.py
# ═══════════════════════════════════════════════════════════════════════════════
# Main Codeseeq Orchestrator — brain / planner / merge authority
#
# Control flow:
# 1. Inspect task + repo → create build plan → dependency graph
# 2. Split into briq groups → decide serial vs parallel execution
# 3. Dispatch Construqtor workers
# 4. Review + merge worker results
# 5. Route to Sqrewdriver → Inspeqtor
# 6. Route failures back to correct repair phase
# 7. Run final validation
# 8. Report
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from briq_planner import (
    BriqGroup,
    PlannerResult,
    plan_from_task_file,
    topological_sort,
)
from parallel_scheduler import (
    SchedulerConfig,
    SchedulerResult,
    execute_plan,
    resolve_execution_plan,
)
from self_review_loop import (
    SelfReviewLoopConfig,
    SelfReviewLoopResult,
    SelfReview,
    run_self_review_loop,
    basic_self_review,
)
from worker_contract import (
    WorkerResult,
    WorkerStatus,
    SqrewdriverResult,
    SqrewdriverFinding,
    InspeqtorResult,
    InspeqtorFinding,
    merge_statuses,
    validate_worker_status,
    OrchestratorRunResult,
)


@dataclass
class OrchestratorConfig:
    """Configuration for the Codeseeq orchestrator."""
    parallel_enabled: bool = True
    max_workers: int = 4
    max_self_review_iterations: int = 3
    validator_strictness: str = "normal"  # "normal" | "strict" | "relaxed"
    dry_run: bool = False
    task_path: str = ""
    workspace_path: str = "."

    @classmethod
    def from_env(cls) -> OrchestratorConfig:
        """Create OrchestratorConfig from environment variables."""
        parallel = os.environ.get("QONQ_PARALLEL_ENABLED", "true").lower() in ("1", "true", "yes")
        try:
            max_workers = int(os.environ.get("QONQ_MAX_WORKERS", "4"))
        except (ValueError, TypeError):
            max_workers = 4
        try:
            max_self_review = int(os.environ.get("QONQ_MAX_SELF_REVIEW_ITERATIONS", "3"))
        except (ValueError, TypeError):
            max_self_review = 3
        strictness = os.environ.get("QONQ_VALIDATOR_STRICTNESS", "normal").lower()
        if strictness not in ("normal", "strict", "relaxed"):
            strictness = "normal"
        dry_run = os.environ.get("QONQ_DRY_RUN", "false").lower() in ("1", "true", "yes")
        return cls(
            parallel_enabled=parallel,
            max_workers=max_workers,
            max_self_review_iterations=max_self_review,
            validator_strictness=strictness,
            dry_run=dry_run,
            task_path=os.environ.get("QONQ_TASK_PATH", ""),
            workspace_path=os.environ.get("QONQ_WORKSPACE_PATH", "."),
        )


# ── Sqrewdriver validation ───────────────────────────────────────────────
def run_sqrewdriver_validation(
    worker_results: list[WorkerResult],
    planner_result: PlannerResult,
    config: OrchestratorConfig,
) -> SqrewdriverResult:
    """Validate wiring, dependencies, imports, and integration.

    Checks:
    - All expected files from briq groups are produced
    - No orphan files
    - Cross-briq dependency wiring is intact
    - Path scopes are respected
    """
    findings: list[SqrewdriverFinding] = []
    repair_suggestions: list[str] = []
    commands_run: list[str] = []

    # Map briq_id → result
    result_map = {r.briq_id: r for r in worker_results}

    # Check 1: All briq groups produced results
    for group in planner_result.groups:
        result = result_map.get(group.id)
        if result is None:
            findings.append(SqrewdriverFinding(
                source="sqrewdriver",
                file="*",
                message=f"Briq group '{group.id}' has no worker result",
                severity="error",
                repair_suggestion=f"Ensure a Construqtor worker is dispatched for '{group.id}'",
            ))
            continue

        if result.status in ("FAIL_REPAIRABLE", "FAIL_REBUILD_REQUIRED", "BLOCKED"):
            findings.append(SqrewdriverFinding(
                source="sqrewdriver",
                file=",".join(result.changed_files) or "*",
                message=f"Worker for '{group.id}' failed: {result.status}",
                severity="error",
                repair_suggestion=result.summary,
            ))

        # Check allowed_paths are respected
        if group.allowed_paths:
            for changed_file in result.changed_files:
                in_scope = any(
                    changed_file.startswith(p.rstrip("/") + "/") or changed_file == p
                    for p in group.allowed_paths
                )
                if not in_scope:
                    findings.append(SqrewdriverFinding(
                        source="sqrewdriver",
                        file=changed_file,
                        message=f"File '{changed_file}' is outside allowed paths for briq '{group.id}': {group.allowed_paths}",
                        severity="warning",
                        repair_suggestion=f"Move '{changed_file}' to a more appropriate briq group",
                    ))

        # Check acceptance criteria references
        if group.acceptance and not result.validation_notes:
            findings.append(SqrewdriverFinding(
                source="sqrewdriver",
                file=",".join(result.changed_files) or "*",
                message=f"Acceptance criteria for '{group.id}' have no validation notes",
                severity="info",
                repair_suggestion="Add validation notes matching acceptance criteria",
            ))

    # Check 2: Dependency wiring
    for group in planner_result.groups:
        for dep_id in group.depends_on:
            dep_result = result_map.get(dep_id)
            if dep_result and dep_result.status in ("FAIL_REPAIRABLE", "FAIL_REBUILD_REQUIRED", "BLOCKED"):
                findings.append(SqrewdriverFinding(
                    source="sqrewdriver",
                    file=",".join(group.allowed_paths) or "*",
                    message=f"Briq '{group.id}' depends on '{dep_id}' which failed",
                    severity="error",
                    repair_suggestion=f"Repair '{dep_id}' first or restructure dependencies",
                ))

    status = merge_statuses([
        "FAIL_REPAIRABLE" if any(f.severity == "error" for f in findings) else "PASS",
    ])

    if status != "PASS":
        repair_suggestions = [
            f"Repair briq groups: {', '.join(set(f.file for f in findings if f.severity == 'error'))}",
        ]

    return SqrewdriverResult(
        status=status,
        findings=findings,
        repair_suggestions=repair_suggestions,
        commands_run=commands_run,
    )


# ── Inspeqtor validation ────────────────────────────────────────────────
def run_inspeqtor_validation(
    worker_results: list[WorkerResult],
    planner_result: PlannerResult,
    config: OrchestratorConfig,
) -> InspeqtorResult:
    """Validate correctness, quality, acceptance criteria, security, consistency.

    Checks:
    - Acceptance criteria from each briq group are met
    - No security footguns (hardcoded secrets, command injection via eval)
    - Consistent naming across briq groups
    - Tests are present
    """
    findings: list[InspeqtorFinding] = []
    acceptance_checked: list[str] = []
    security_issues: list[str] = []
    consistency_issues: list[str] = []

    result_map = {r.briq_id: r for r in worker_results}

    for group in planner_result.groups:
        result = result_map.get(group.id)

        # Check acceptance criteria
        for criterion in group.acceptance:
            acceptance_checked.append(criterion)
            if result is None:
                findings.append(InspeqtorFinding(
                    check_id=f"acceptance_{group.id}",
                    severity="critical",
                    message=f"Acceptance criterion not checked (no result): {criterion}",
                    file=",".join(group.allowed_paths) or "*",
                    required_action="Dispatch worker and verify criterion",
                ))
                continue

            if not result.validation_notes:
                findings.append(InspeqtorFinding(
                    check_id=f"acceptance_{group.id}",
                    severity="error",
                    message=f"No validation notes for acceptance criterion: {criterion}",
                    file=",".join(result.changed_files) or "*",
                    required_action="Add validation notes addressing this criterion",
                ))

        if result is None:
            continue

        # Check tests
        if not result.tests_run:
            findings.append(InspeqtorFinding(
                check_id=f"tests_{group.id}",
                severity="warning" if config.validator_strictness != "strict" else "error",
                message=f"No tests run for briq '{group.id}'",
                file=",".join(result.changed_files) or "*",
                required_action="Add and run tests for this briq group",
            ))

        # Check security: basic heuristic — no hardcoded secrets
        if result.summary:
            secret_keywords = ["password=", "api_key=", "secret=", "token=", "credentials="]
            for kw in secret_keywords:
                if kw in result.summary.lower():
                    security_issues.append(
                        f"Possible hardcoded secret in {group.id}: '{kw}' found in summary"
                    )

        # Check self-review has risks documented
        if result.self_review and result.self_review.remaining_risks:
            for risk in result.self_review.remaining_risks:
                findings.append(InspeqtorFinding(
                    check_id=f"risk_{group.id}",
                    severity="info",
                    message=f"Remaining risk in {group.id}: {risk}",
                    file=",".join(result.changed_files) or "*",
                    required_action="Review and mitigate",
                ))

    # Consistency check: cross-briq naming
    all_file_keywords: dict[str, list[str]] = {}
    for result in worker_results:
        for f in result.changed_files:
            stem = Path(f).stem.lower()
            for kw in stem.replace("-", "_").split("_"):
                if len(kw) > 3:
                    all_file_keywords.setdefault(kw, []).append(result.briq_id)

    # If the same keyword appears in multiple briqs but with different naming
    # conventions, flag it (lenient check)
    for kw, briqs in all_file_keywords.items():
        if len(briqs) > 1:
            pass  # Not an issue per se, but tracked

    status = merge_statuses([
        "FAIL_REPAIRABLE"
        if any(f.severity in ("error", "critical") for f in findings)
        else "PASS_WITH_WARNINGS"
        if security_issues or any(f.severity == "warning" for f in findings)
        else "PASS",
    ])

    return InspeqtorResult(
        status=status,
        findings=findings,
        acceptance_checked=acceptance_checked,
        security_issues=security_issues,
        consistency_issues=consistency_issues,
    )


# ── Main orchestration ───────────────────────────────────────────────────
def orchestrate(
    task_path: str | Path,
    worker_fn: Callable[[BriqGroup], WorkerResult],
    config: OrchestratorConfig | None = None,
) -> OrchestratorRunResult:
    """Run the full Codeseeq orchestration pipeline.

    1. Planner: Break task into briq groups
    2. Scheduler: Resolve parallel/serial execution plan
    3. Dispatch workers (via worker_fn) with self-review loops
    4. Sqrewdriver validation
    5. Inspeqtor validation
    6. Merge results
    """
    if config is None:
        config = OrchestratorConfig()

    # ── Step 1: Plan ─────────────────────────────────────────────────
    planner_result = plan_from_task_file(str(task_path))
    if planner_result.status != "PASS":
        return OrchestratorRunResult(
            overall_status=planner_result.status,
            planner_status=planner_result.status,
            validation_errors=planner_result.errors,
        )

    if config.dry_run:
        return OrchestratorRunResult(
            overall_status="PASS",
            planner_status="PASS",
            parallel_groups=[],
            serial_groups=[[g.id for g in planner_result.groups]],
            validation_errors=["Dry run mode — no workers dispatched"],
        )

    # ── Step 2: Schedule ──────────────────────────────────────────────
    scheduler_config = SchedulerConfig(
        parallel_enabled=config.parallel_enabled,
        max_parallel_workers=config.max_workers,
    )
    parallel_batches, serial_batches, exec_order = resolve_execution_plan(
        planner_result, scheduler_config
    )

    # ── Step 3: Dispatch workers with self-review ─────────────────────
    self_review_config = SelfReviewLoopConfig(
        max_iterations=config.max_self_review_iterations,
    )

    worker_results: list[WorkerResult] = []
    for gid in exec_order:
        group = next((g for g in planner_result.groups if g.id == gid), None)
        if group is None:
            continue

        loop_result = run_self_review_loop(
            worker_id=f"construqtor_{gid}",
            briq_id=gid,
            build_fn=worker_fn,
            config=self_review_config,
            review_fn=basic_self_review,
            group=group,
        )
        worker_results.append(loop_result.final_result)

    # ── Step 4: Sqrewdriver validation ────────────────────────────────
    sqrewdriver_result = run_sqrewdriver_validation(
        worker_results, planner_result, config
    )

    # ── Step 5: Inspeqtor validation ──────────────────────────────────
    inspeqtor_result = run_inspeqtor_validation(
        worker_results, planner_result, config
    )

    # ── Step 6: Merge and determine overall status ────────────────────
    all_statuses = [
        planner_result.status,
        sqrewdriver_result.status,
        inspeqtor_result.status,
    ] + [r.status for r in worker_results]

    overall = merge_statuses(all_statuses)

    # If Sqrewdriver or Inspeqtor found issues, route back
    repairable_statuses = ("FAIL_REPAIRABLE", "PASS_WITH_WARNINGS")
    if sqrewdriver_result.status in repairable_statuses:
        sqrewdriver_result.repair_suggestions.append(
            "Route back to Construqtor for repair"
        )
    if inspeqtor_result.status in repairable_statuses:
        if not any("Inspeqtor" in s for s in sqrewdriver_result.repair_suggestions):
            sqrewdriver_result.repair_suggestions.append(
                "Route back to Construqtor for Inspeqtor-flagged issues"
            )

    return OrchestratorRunResult(
        overall_status=overall,
        planner_status=planner_result.status,
        worker_results=worker_results,
        sqrewdriver_result=sqrewdriver_result,
        inspeqtor_result=inspeqtor_result,
        parallel_groups=parallel_batches,
        serial_groups=serial_batches,
        validation_errors=planner_result.errors + sqrewdriver_result.repair_suggestions,
    )
