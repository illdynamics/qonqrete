#!/usr/bin/env python3
# worqer/self_review_loop.py
# ═══════════════════════════════════════════════════════════════════════════════
# Self-Review Loop — bounded iterative improvement for Construqtor workers
# Each worker runs: build → self-review → repair → self-review → return
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from worker_contract import (
    SelfReview,
    WorkerResult,
    WorkerStatus,
    merge_statuses,
    validate_worker_status,
)


DEFAULT_MAX_ITERATIONS = 3


@dataclass
class SelfReviewLoopConfig:
    """Configuration for the self-review loop."""
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    skip_if_no_issues: bool = True
    review_after_each_build: bool = True
    strict_mode: bool = False  # If True, PASS requires zero issues


@dataclass
class SelfReviewLoopResult:
    """Result from running a self-review loop."""
    final_result: WorkerResult
    iterations: int
    max_iterations: int
    iteration_results: list[WorkerResult] = field(default_factory=list)
    converged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_result": self.final_result.to_dict(),
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "iteration_results": [r.to_dict() for r in self.iteration_results],
            "converged": self.converged,
        }


# ── Review functions ──────────────────────────────────────────────────────

def basic_self_review(result: WorkerResult) -> SelfReview:
    """Perform a basic self-review on a worker result.

    Checks:
    - changed_files is non-empty or status is acceptable
    - summary is non-empty
    - tests_run is present
    - status is valid
    """
    issues: list[str] = []
    fixes: list[str] = []
    risks: list[str] = []

    # Check changed_files
    if not result.changed_files and result.status in ("PASS", "PASS_WITH_WARNINGS"):
        issues.append("No changed files reported despite PASS status")
    elif result.changed_files:
        fixes.append("Changed files documented")

    # Check summary
    if not result.summary:
        issues.append("Empty summary")
    else:
        fixes.append("Summary provided")

    # Check tests_run
    if not result.tests_run:
        issues.append("No tests run reported")
    else:
        fixes.append(f"{len(result.tests_run)} test(s) reported")

    # Check validation_notes
    if not result.validation_notes:
        risks.append("No validation notes — edge cases may be unverified")

    return SelfReview(
        issues_found=issues,
        fixes_applied=fixes,
        remaining_risks=risks,
    )


def run_self_review_loop(
    worker_id: str,
    briq_id: str,
    build_fn: Callable[..., WorkerResult],
    config: SelfReviewLoopConfig | None = None,
    review_fn: Callable[[WorkerResult], SelfReview] | None = None,
    repair_fn: Callable[[WorkerResult, SelfReview], WorkerResult] | None = None,
    **build_kwargs: Any,
) -> SelfReviewLoopResult:
    """Run a bounded self-review loop for a Construqtor worker.

    Args:
        worker_id: Identifier for the worker.
        briq_id: Briq group ID this worker is building.
        build_fn: Function that produces an initial WorkerResult.
        config: Loop configuration (max iterations, etc.)
        review_fn: Function that reviews a result and returns SelfReview.
        repair_fn: Function that attempts to fix issues found in review.
        **build_kwargs: Additional kwargs passed to build_fn.

    Returns:
        SelfReviewLoopResult with the final result and iteration history.
    """
    if config is None:
        config = SelfReviewLoopConfig()
    if review_fn is None:
        review_fn = basic_self_review
    if repair_fn is None:

        def _default_repair(
            prev_result: WorkerResult, review: SelfReview
        ) -> WorkerResult:
            # Default repair: just note the attempt
            return WorkerResult(
                worker_id=prev_result.worker_id,
                briq_id=prev_result.briq_id,
                status="FAIL_REPAIRABLE" if review.issues_found else prev_result.status,
                changed_files=prev_result.changed_files,
                summary=prev_result.summary + " [self-review attempted repair]",
                self_review=review,
                tests_run=prev_result.tests_run,
                validation_notes=prev_result.validation_notes
                + [f"Self-review found {len(review.issues_found)} issue(s)"],
            )

        repair_fn = _default_repair

    iteration_results: list[WorkerResult] = []
    current_result = build_fn(**build_kwargs)
    iteration_results.append(current_result)

    for iteration in range(config.max_iterations):
        # Self-review
        review = review_fn(current_result)

        # Update self_review on result
        current_result.self_review = review

        if not review.issues_found:
            # No issues — converged
            if current_result.status in ("PASS", "PASS_WITH_WARNINGS"):
                return SelfReviewLoopResult(
                    final_result=current_result,
                    iterations=iteration + 1,
                    max_iterations=config.max_iterations,
                    iteration_results=iteration_results,
                    converged=True,
                )
            # Status is not pass but no review issues — attempt one more build
            if iteration == config.max_iterations - 1:
                break
            current_result = repair_fn(current_result, review)
            iteration_results.append(current_result)
            continue

        # Issues found — attempt repair
        if iteration == config.max_iterations - 1:
            # Last iteration, can't repair further
            current_result.status = "FAIL_REPAIRABLE"
            current_result.validation_notes.append(
                f"Max iterations ({config.max_iterations}) reached with unresolved issues"
            )
            break

        repaired = repair_fn(current_result, review)
        repaired.self_review = SelfReview(
            issues_found=review.issues_found,
            fixes_applied=review.fixes_applied + ["Attempted self-repair"],
            remaining_risks=review.remaining_risks,
        )
        iteration_results.append(repaired)
        current_result = repaired

    # If we exit the loop without converging, mark as FAIL_REPAIRABLE if not already
    if current_result.status in ("PASS", "PASS_WITH_WARNINGS"):
        current_result.status = "PASS_WITH_WARNINGS"
        current_result.validation_notes.append(
            "Loop ended without full convergence; marked PASS_WITH_WARNINGS"
        )

    return SelfReviewLoopResult(
        final_result=current_result,
        iterations=len(iteration_results),
        max_iterations=config.max_iterations,
        iteration_results=iteration_results,
        converged=False,
    )
