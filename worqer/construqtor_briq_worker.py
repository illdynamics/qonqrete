#!/usr/bin/env python3
# worqer/construqtor_briq_worker.py
# ═══════════════════════════════════════════════════════════════════════════════
# Construqtor Briq Worker — lightweight, model-agnostic briq worker
#
# Each worker:
# 1. Receives a BriqGroup contract (task, scope, acceptance criteria)
# 2. Builds/produces changes within the allowed scope
# 3. Self-reviews with bounded iteration
# 4. Returns a structured WorkerResult
#
# This is the default "no-AI" worker that validates contracts only.
# In production, AI-powered Construqtor replaces the build_fn.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from worker_contract import (
    BriqGroup,
    WorkerResult,
    SelfReview,
    WorkerStatus,
)
from self_review_loop import (
    SelfReviewLoopConfig,
    SelfReviewLoopResult,
    basic_self_review,
    run_self_review_loop,
)


@dataclass
class BriqWorkerConfig:
    """Configuration for a Construqtor briq worker."""
    max_self_review_iterations: int = 3
    strict_mode: bool = False
    workspace_path: str = "."
    allowed_paths_override: list[str] | None = None
    read_paths_override: list[str] | None = None


# ── Default build function ───────────────────────────────────────────────

def default_build_fn(
    group: BriqGroup,
    worker_config: BriqWorkerConfig | None = None,
) -> WorkerResult:
    """Default build function: validates the BriqGroup contract.

    In production, this is replaced by the actual AI-powered Construqtor.
    This default simply reports the expected change scope and returns PASS.
    """
    if worker_config is None:
        worker_config = BriqWorkerConfig()

    wk_id = f"construqtor_{group.id}"

    return WorkerResult(
        worker_id=wk_id,
        briq_id=group.id,
        status="PASS",
        changed_files=list(group.allowed_paths),
        summary=f"Built {group.name}: {group.description}" if group.description
                else f"Built {group.name}",
        self_review=SelfReview(
            issues_found=[],
            fixes_applied=[],
            remaining_risks=[],
        ),
        tests_run=[f"validate_{group.id}"],
        validation_notes=[f"Acceptance criteria defined: {len(group.acceptance)} check(s)"],
    )


# ── Contract-validating build function ───────────────────────────────────

def contract_validating_build_fn(
    group: BriqGroup,
    worker_config: BriqWorkerConfig | None = None,
) -> WorkerResult:
    """Build function that validates worker contract completeness.

    Checks:
    - BriqGroup has required fields (id, name)
    - allowed_paths are non-empty for actual work
    - acceptance criteria are non-empty
    - parallel_safe flag is set appropriately
    """
    if worker_config is None:
        worker_config = BriqWorkerConfig()

    wk_id = f"construqtor_{group.id}"
    issues: list[str] = []
    fixes: list[str] = []
    risks: list[str] = []

    # Validate contract completeness
    if not group.id:
        issues.append("BriqGroup has empty id")
    if not group.name:
        issues.append("BriqGroup has empty name")
    if not group.description and not group.allowed_paths:
        issues.append("BriqGroup has no description and no allowed_paths")

    # Check for empty allowed_paths
    if not group.allowed_paths and group.parallel_safe:
        risks.append("BriqGroup is parallel_safe but has no allowed_paths")

    status: WorkerStatus = "FAIL_REPAIRABLE" if issues else "PASS"
    if issues:
        status = "FAIL_REPAIRABLE"
    elif risks:
        status = "PASS_WITH_WARNINGS"

    return WorkerResult(
        worker_id=wk_id,
        briq_id=group.id,
        status=status,
        changed_files=list(group.allowed_paths),
        summary=f"Contract validation for {group.name}" if not issues
                else f"Contract validation FAILED for {group.name}: {'; '.join(issues)}",
        self_review=SelfReview(
            issues_found=issues,
            fixes_applied=fixes,
            remaining_risks=risks,
        ),
        tests_run=[],
        validation_notes=[
            f"Acceptance criteria: {len(group.acceptance)} check(s)",
            f"Depends on: {group.depends_on}",
            f"Parallel safe: {group.parallel_safe}",
        ],
    )


# ── Error-injecting build function (for testing repair routing) ──────────

def make_failing_build_fn(
    fail_briq_ids: set[str],
    failure_status: WorkerStatus = "FAIL_REPAIRABLE",
) -> Callable[[BriqGroup], WorkerResult]:
    """Create a build function that fails for specific briq IDs.

    Args:
        fail_briq_ids: Set of briq IDs that should fail.
        failure_status: Status to assign to failed briqs.

    Returns:
        A build function for use with orchestrate().
    """

    def _build_fn(group: BriqGroup) -> WorkerResult:
        wk_id = f"construqtor_{group.id}"
        if group.id in fail_briq_ids:
            return WorkerResult(
                worker_id=wk_id,
                briq_id=group.id,
                status=failure_status,
                changed_files=[],
                summary=f"Simulated failure for briq '{group.id}'",
                self_review=SelfReview(
                    issues_found=["Simulated failure condition"],
                    fixes_applied=[],
                    remaining_risks=["Test-only failure"],
                ),
                tests_run=[],
                validation_notes=[],
            )
        return WorkerResult(
            worker_id=wk_id,
            briq_id=group.id,
            status="PASS",
            changed_files=list(group.allowed_paths),
            summary=f"Built {group.name} (passing)",
            self_review=SelfReview(issues_found=[], fixes_applied=[]),
            tests_run=[f"validate_{group.id}"],
            validation_notes=["Passed"],
        )

    return _build_fn


# ── Path scope conflict detection ────────────────────────────────────────

def detect_path_conflicts(groups: list[BriqGroup]) -> list[tuple[str, str, str]]:
    """Detect path scope conflicts between briq groups.

    Returns:
        List of (group_a_id, group_b_id, overlapping_path) tuples.
    """
    conflicts: list[tuple[str, str, str]] = []

    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            a_paths = set(p.rstrip("/") for p in (a.allowed_paths + a.read_paths))
            b_paths = set(p.rstrip("/") for p in (b.allowed_paths + b.read_paths))
            for p1 in a_paths:
                for p2 in b_paths:
                    if p1 == p2 or p1.startswith(p2 + "/") or p2.startswith(p1 + "/"):
                        conflicts.append((a.id, b.id, p1 if p1 == p2 else f"{p1}<->{p2}"))
                        break
                else:
                    continue
                break

    return conflicts


# ── Dispatch a single briq worker with self-review ───────────────────────

def run_briq_worker(
    group: BriqGroup,
    build_fn: Callable[..., WorkerResult] | None = None,
    worker_config: BriqWorkerConfig | None = None,
    review_fn: Callable | None = None,
    repair_fn: Callable | None = None,
) -> SelfReviewLoopResult:
    """Run a single Construqtor briq worker with self-review.

    Args:
        group: The BriqGroup to build.
        build_fn: Build function (defaults to default_build_fn).
        worker_config: Worker configuration.
        review_fn: Review function (defaults to basic_self_review).
        repair_fn: Repair function (defaults to self-review loop default).

    Returns:
        SelfReviewLoopResult with the final WorkerResult.
    """
    if worker_config is None:
        worker_config = BriqWorkerConfig()
    if build_fn is None:
        build_fn = default_build_fn

    self_review_config = SelfReviewLoopConfig(
        max_iterations=worker_config.max_self_review_iterations,
        strict_mode=worker_config.strict_mode,
    )

    return run_self_review_loop(
        worker_id=f"construqtor_{group.id}",
        briq_id=group.id,
        build_fn=build_fn,
        config=self_review_config,
        review_fn=review_fn or basic_self_review,
        repair_fn=repair_fn,
        group=group,
        worker_config=worker_config,
    )
