#!/usr/bin/env python3
"""Tests for self_review_loop.py — bounded self-review iteration."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from self_review_loop import (
    SelfReviewLoopConfig,
    SelfReviewLoopResult,
    SelfReview,
    run_self_review_loop,
    basic_self_review,
)
from worker_contract import WorkerResult


def _make_build_fn(result: WorkerResult):
    """Create a build function that returns a fixed result."""
    def build_fn(**kwargs) -> WorkerResult:
        return WorkerResult(
            worker_id=result.worker_id,
            briq_id=result.briq_id,
            status=result.status,
            changed_files=list(result.changed_files),
            summary=result.summary,
            self_review=SelfReview(
                issues_found=list(result.self_review.issues_found) if result.self_review else [],
                fixes_applied=list(result.self_review.fixes_applied) if result.self_review else [],
                remaining_risks=list(result.self_review.remaining_risks) if result.self_review else [],
            ) if result.self_review else None,
            tests_run=list(result.tests_run),
            validation_notes=list(result.validation_notes),
        )
    return build_fn


class TestBasicSelfReview(unittest.TestCase):
    def test_perfect_result(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["a.txt"],
            summary="Done",
            tests_run=["pytest"],
            validation_notes=["OK"],
        )
        review = basic_self_review(r)
        self.assertEqual(len(review.issues_found), 0)

    def test_no_files_flagged(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=[],
            summary="Done",
            tests_run=["pytest"],
        )
        review = basic_self_review(r)
        self.assertTrue(len(review.issues_found) > 0)
        joined = " ".join(review.issues_found)
        self.assertIn("No changed files", joined)

    def test_no_summary_flagged(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["a.txt"],
            summary="",
            tests_run=["pytest"],
        )
        review = basic_self_review(r)
        self.assertTrue(len(review.issues_found) > 0)

    def test_no_tests_flagged(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["a.txt"],
            summary="Done",
            tests_run=[],
        )
        review = basic_self_review(r)
        self.assertTrue(len(review.issues_found) > 0)

    def test_remaining_risks(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["a.txt"],
            summary="Done",
            tests_run=["pytest"],
            validation_notes=[],
        )
        review = basic_self_review(r)
        self.assertEqual(len(review.remaining_risks), 1)


class TestSelfReviewLoop(unittest.TestCase):
    def test_perfect_first_try(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["a.txt"],
            summary="Perfect",
            tests_run=["pytest"],
            validation_notes=["OK"],
        )
        result = run_self_review_loop(
            worker_id="w1",
            briq_id="b1",
            build_fn=_make_build_fn(r),
        )
        self.assertTrue(result.converged)
        self.assertEqual(result.final_result.status, "PASS")
        self.assertEqual(result.iterations, 1)

    def test_repair_on_issues(self):
        """Test that a result with issues is repaired and loop iterates."""
        # Create a build_fn that returns a result with issues
        result_with_issues = WorkerResult(
            worker_id="w1", briq_id="b1", status="PASS",
            changed_files=[], summary="", tests_run=[], validation_notes=[],
        )

        # Custom repair function that fixes the issues
        def repair_fn(prev_result: WorkerResult, review: SelfReview) -> WorkerResult:
            return WorkerResult(
                worker_id=prev_result.worker_id,
                briq_id=prev_result.briq_id,
                status="PASS",
                changed_files=["a.txt"],
                summary="Fixed after review",
                self_review=SelfReview(
                    issues_found=review.issues_found,
                    fixes_applied=["Added missing files, summary, and tests"],
                    remaining_risks=[],
                ),
                tests_run=["pytest"],
                validation_notes=["Self-review repair applied"],
            )

        config = SelfReviewLoopConfig(max_iterations=3)
        result = run_self_review_loop(
            worker_id="w1",
            briq_id="b1",
            build_fn=_make_build_fn(result_with_issues),
            config=config,
            repair_fn=repair_fn,
        )
        # Should converge after repair
        self.assertTrue(result.converged)
        self.assertEqual(result.final_result.status, "PASS")
        self.assertGreaterEqual(len(result.iteration_results), 2)

    def test_max_iterations_honored(self):
        """Always-issue result should not exceed max iterations."""
        def always_bad(**kwargs) -> WorkerResult:
            return WorkerResult(
                worker_id="w1", briq_id="b1", status="PASS",
                changed_files=[], summary="", tests_run=[], validation_notes=[],
            )

        config = SelfReviewLoopConfig(max_iterations=2)
        result = run_self_review_loop(
            worker_id="w1", briq_id="b1", build_fn=always_bad, config=config,
        )
        # max_iterations=2 means at most 2 iterations of repair after initial build
        self.assertLessEqual(result.iterations, config.max_iterations + 1)

    def test_custom_review_fn(self):
        def strict_review(result: WorkerResult) -> SelfReview:
            issues = []
            if not result.changed_files:
                issues.append("NO FILES ALLOWED")
            return SelfReview(issues_found=issues, fixes_applied=[], remaining_risks=[])

        r = WorkerResult(
            worker_id="w1", briq_id="b1", status="PASS",
            changed_files=[], summary="x", tests_run=["t"], validation_notes=["ok"],
        )
        result = run_self_review_loop(
            worker_id="w1",
            briq_id="b1",
            build_fn=_make_build_fn(r),
            review_fn=strict_review,
        )
        self.assertFalse(result.converged)

    def test_result_serialization(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["a.txt"],
            summary="OK",
            tests_run=["t"],
            validation_notes=["v"],
        )
        result = run_self_review_loop(
            worker_id="w1",
            briq_id="b1",
            build_fn=_make_build_fn(r),
        )
        d = result.to_dict()
        self.assertIn("final_result", d)
        self.assertIn("iterations", d)
        self.assertIn("converged", d)

    def test_default_repair_with_no_issues(self):
        """When review finds no issues, loop converges without repair."""
        r = WorkerResult(
            worker_id="w1", briq_id="b1", status="PASS",
            changed_files=["a.txt"], summary="Good", tests_run=["t"], validation_notes=["v"],
        )
        result = run_self_review_loop(
            worker_id="w1", briq_id="b1", build_fn=_make_build_fn(r),
        )
        self.assertTrue(result.converged)
        self.assertEqual(result.iterations, 1)


if __name__ == "__main__":
    unittest.main()
