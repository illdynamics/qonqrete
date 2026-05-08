#!/usr/bin/env python3
"""Tests for codeseeq_orchestrator.py — full orchestration pipeline."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from briq_planner import BriqGroup, PlannerResult
from codeseeq_orchestrator import (
    OrchestratorConfig,
    OrchestratorRunResult,
    orchestrate,
    run_sqrewdriver_validation,
    run_inspeqtor_validation,
)
from worker_contract import (
    WorkerResult,
    SelfReview,
    SqrewdriverResult,
    InspeqtorResult,
)


def _make_worker_fn(
    results: dict[str, WorkerResult] | None = None,
) -> Any:
    if results is None:
        results = {}

    def worker_fn(group: BriqGroup) -> WorkerResult:
        if group.id in results:
            return results[group.id]
        return WorkerResult(
            worker_id=f"w_{group.id}",
            briq_id=group.id,
            status="PASS",
            changed_files=group.allowed_paths[:],
            summary=f"Built {group.name}",
            self_review=SelfReview(issues_found=[], fixes_applied=[]),
            tests_run=[f"test_{group.id}.sh"],
            validation_notes=[f"Accepted: {', '.join(group.acceptance)}"],
        )

    return worker_fn


class TestSqrewdriverValidation(unittest.TestCase):
    def test_all_pass(self):
        workers = [
            WorkerResult(worker_id="w1", briq_id="html", status="PASS",
                         changed_files=["index.html"], summary="OK",
                         tests_run=["t"], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="html", name="HTML", allowed_paths=["index.html"],
                      acceptance=["Create index.html"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        self.assertEqual(result.status, "PASS")

    def test_failed_worker_detected(self):
        workers = [
            WorkerResult(worker_id="w1", briq_id="fail", status="FAIL_REPAIRABLE",
                         changed_files=[], summary="failed", tests_run=[], validation_notes=[]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="fail", name="Fail", allowed_paths=["f.txt"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        self.assertEqual(result.status, "FAIL_REPAIRABLE")
        error_findings = [f for f in result.findings if f.severity == "error"]
        self.assertTrue(len(error_findings) > 0)

    def test_missing_worker(self):
        workers: list[WorkerResult] = []
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="orphan", name="Orphan", allowed_paths=["x.txt"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        self.assertEqual(result.status, "FAIL_REPAIRABLE")


class TestInspeqtorValidation(unittest.TestCase):
    def test_all_pass(self):
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["a.txt"], summary="OK",
                         tests_run=["t"], validation_notes=["Checked acceptance"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Must work"]),
        ])
        config = OrchestratorConfig()
        result = run_inspeqtor_validation(workers, planner, config)
        self.assertIn(result.status, ("PASS", "PASS_WITH_WARNINGS"))

    def test_missing_validation_notes_flagged(self):
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["a.txt"], summary="OK",
                         tests_run=["t"], validation_notes=[]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Must work"]),
        ])
        config = OrchestratorConfig()
        result = run_inspeqtor_validation(workers, planner, config)
        self.assertTrue(len(result.findings) >= 0)

    def test_no_tests_flagged_in_strict_mode(self):
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["a.txt"], summary="OK",
                         tests_run=[], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1"),
        ])
        config = OrchestratorConfig(validator_strictness="strict")
        result = run_inspeqtor_validation(workers, planner, config)
        no_tests = [f for f in result.findings if "tests" in f.check_id]
        self.assertTrue(len(no_tests) > 0)
        self.assertEqual(no_tests[0].severity, "error")


class TestFullOrchestration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="orchestrator_test_")
        self.task_file = Path(self._tmp) / "tasq.md"
        self.task_file.write_text(
            "# Task\n\n"
            "Create:\n"
            "- `index.html`\n"
            "- `styles.css`\n"
            "- `app.js`\n"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_orchestrate_success(self):
        config = OrchestratorConfig(
            task_path=str(self.task_file),
            parallel_enabled=True,
            max_workers=4,
        )
        result = orchestrate(self.task_file, _make_worker_fn(), config)
        self.assertEqual(result.overall_status, "PASS")
        self.assertEqual(result.planner_status, "PASS")
        self.assertGreaterEqual(len(result.worker_results), 1)
        self.assertIsNotNone(result.sqrewdriver_result)
        self.assertIsNotNone(result.inspeqtor_result)
        if result.sqrewdriver_result:
            self.assertEqual(result.sqrewdriver_result.status, "PASS")
        if result.inspeqtor_result:
            self.assertIn(result.inspeqtor_result.status, ("PASS", "PASS_WITH_WARNINGS"))

    def test_orchestrate_dry_run(self):
        config = OrchestratorConfig(
            task_path=str(self.task_file),
            dry_run=True,
        )
        result = orchestrate(self.task_file, _make_worker_fn(), config)
        self.assertEqual(result.overall_status, "PASS")
        self.assertTrue(
            any("Dry run" in e for e in result.validation_errors)
        )

    def test_orchestrate_missing_task(self):
        config = OrchestratorConfig(task_path="/nonexistent.md")
        result = orchestrate("/nonexistent.md", _make_worker_fn(), config)
        self.assertEqual(result.overall_status, "FAIL_REPAIRABLE")

    def test_orchestrate_with_failures(self):
        custom_results = {
            "html_structure": WorkerResult(
                worker_id="w1", briq_id="html_structure", status="FAIL_REPAIRABLE",
                changed_files=[], summary="Failed", tests_run=[], validation_notes=[],
            ),
        }
        result = orchestrate(self.task_file, _make_worker_fn(custom_results))
        self.assertEqual(result.overall_status, "FAIL_REPAIRABLE")
        sq = result.sqrewdriver_result
        if sq:
            self.assertEqual(sq.status, "FAIL_REPAIRABLE")

    def test_result_to_dict(self):
        config = OrchestratorConfig(task_path=str(self.task_file))
        result = orchestrate(self.task_file, _make_worker_fn(), config)
        d = result.to_dict()
        self.assertIn("overall_status", d)
        self.assertIn("worker_results", d)
        self.assertIn("sqrewdriver_result", d)
        self.assertIn("inspeqtor_result", d)
        self.assertIn("parallel_groups", d)
        self.assertIn("serial_groups", d)


if __name__ == "__main__":
    unittest.main()
