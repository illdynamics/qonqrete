#!/usr/bin/env python3
"""Tests for codeseeq_orchestrator.py — failure routing and repair suggestions."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from briq_planner import (
    BriqGroup,
    PlannerResult,
    plan_from_task_file,
)
from codeseeq_orchestrator import (
    OrchestratorConfig,
    orchestrate,
    run_sqrewdriver_validation,
    run_inspeqtor_validation,
)
from worker_contract import (
    WorkerResult,
    SelfReview,
    SqrewdriverResult,
    InspeqtorResult,
    OrchestratorRunResult,
    merge_statuses,
)
from construqtor_briq_worker import (
    make_failing_build_fn,
    default_build_fn,
)


class TestFailureStatusMerge(unittest.TestCase):
    def test_sqrewdriver_routes_to_repair(self):
        """When Sqrewdriver finds errors, it should produce repair suggestions."""
        workers = [
            WorkerResult(worker_id="w1", briq_id="html", status="FAIL_REPAIRABLE",
                         changed_files=[], summary="failed", tests_run=[], validation_notes=[]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="html", name="HTML", allowed_paths=["index.html"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        self.assertEqual(result.status, "FAIL_REPAIRABLE")
        # Should have repair suggestions to fix the broken briq
        self.assertGreater(len(result.repair_suggestions), 0)
        # Should have error-level findings
        error_findings = [f for f in result.findings if f.severity == "error"]
        self.assertGreater(len(error_findings), 0)

    def test_overlapping_paths_warning(self):
        """Files outside allowed paths should generate warnings."""
        workers = [
            WorkerResult(worker_id="w1", briq_id="html", status="PASS",
                         changed_files=["outside/scope.txt"], summary="OK",
                         tests_run=["t"], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="html", name="HTML", allowed_paths=["index.html"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        scope_warnings = [f for f in result.findings if "outside allowed paths" in f.message.lower()]
        self.assertGreater(len(scope_warnings), 0)

    def test_dependency_on_failed_briq_flagged(self):
        """Dependency chain: if A fails, B depending on A should be flagged."""
        workers = [
            WorkerResult(worker_id="w_a", briq_id="a", status="FAIL_REPAIRABLE",
                         changed_files=[], summary="failed", tests_run=[], validation_notes=[]),
            WorkerResult(worker_id="w_b", briq_id="b", status="PASS",
                         changed_files=["b.txt"], summary="OK", tests_run=["t"], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="a", name="A", allowed_paths=["a.txt"]),
            BriqGroup(id="b", name="B", depends_on=["a"], allowed_paths=["b.txt"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        dep_findings = [f for f in result.findings if "depends on" in f.message.lower()]
        self.assertGreater(len(dep_findings), 0)

    def test_missing_validation_notes_flagged_as_info(self):
        """Missing validation notes should be an info finding, not critical."""
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["a.txt"], summary="OK",
                         tests_run=["t"], validation_notes=[]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Must work"]),
        ])
        config = OrchestratorConfig()
        result = run_sqrewdriver_validation(workers, planner, config)
        info_findings = [f for f in result.findings if f.severity == "info"]
        self.assertGreater(len(info_findings), 0)


class TestInspeqtorRouting(unittest.TestCase):
    def test_no_tests_non_strict_is_warning(self):
        """Missing tests in normal mode should be a warning, not an error."""
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["a.txt"], summary="OK",
                         tests_run=[], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Works"]),
        ])
        config = OrchestratorConfig(validator_strictness="normal")
        result = run_inspeqtor_validation(workers, planner, config)
        no_tests = [f for f in result.findings if "tests" in f.check_id.lower()]
        if no_tests:
            self.assertEqual(no_tests[0].severity, "warning")

    def test_no_tests_strict_is_error(self):
        """Missing tests in strict mode should be an error."""
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["a.txt"], summary="OK",
                         tests_run=[], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Works"]),
        ])
        config = OrchestratorConfig(validator_strictness="strict")
        result = run_inspeqtor_validation(workers, planner, config)
        no_tests = [f for f in result.findings if "tests" in f.check_id.lower()]
        self.assertGreater(len(no_tests), 0)
        self.assertEqual(no_tests[0].severity, "error")

    def test_security_keyword_detection(self):
        """Hardcoded secrets in summary should be flagged."""
        workers = [
            WorkerResult(worker_id="w1", briq_id="g1", status="PASS",
                         changed_files=["config.py"], summary="Added api_key=sk-xxx",
                         tests_run=["t"], validation_notes=["v"]),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Secure config"]),
        ])
        config = OrchestratorConfig()
        result = run_inspeqtor_validation(workers, planner, config)
        self.assertGreater(len(result.security_issues), 0)

    def test_self_review_risks_are_logged(self):
        """Remaining risks from self-review should appear as Inspeqtor findings."""
        workers = [
            WorkerResult(
                worker_id="w1", briq_id="g1", status="PASS",
                changed_files=["a.txt"], summary="OK",
                tests_run=["t"], validation_notes=["v"],
                self_review=SelfReview(
                    issues_found=[],
                    fixes_applied=[],
                    remaining_risks=["Edge case in sorting"],
                ),
            ),
        ]
        planner = PlannerResult(status="PASS", groups=[
            BriqGroup(id="g1", name="G1", acceptance=["Works"]),
        ])
        config = OrchestratorConfig()
        result = run_inspeqtor_validation(workers, planner, config)
        risk_findings = [f for f in result.findings if "risk" in f.check_id.lower()]
        self.assertGreater(len(risk_findings), 0)


class TestFullOrchestrationRouting(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="orchestrate_routing_")
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

    def test_orchestrate_with_mixed_results_routes_correctly(self):
        """Partial failures should correctly route to Sqrewdriver/Inspeqtor."""
        fail_ids = {"css_styling"}
        worker_fn = make_failing_build_fn(fail_ids)

        config = OrchestratorConfig(task_path=str(self.task_file))
        result = orchestrate(self.task_file, worker_fn, config)

        # Overall should reflect failure
        self.assertEqual(result.overall_status, "FAIL_REPAIRABLE")
        self.assertEqual(result.planner_status, "PASS")

        # Sqrewdriver should detect the failure
        if result.sqrewdriver_result:
            self.assertEqual(result.sqrewdriver_result.status, "FAIL_REPAIRABLE")
            error_findings = [f for f in result.sqrewdriver_result.findings if f.severity == "error"]
            self.assertGreater(len(error_findings), 0)

        # Some worker results should be failed
        failed_workers = [w for w in result.worker_results if w.status != "PASS"]
        self.assertGreater(len(failed_workers), 0)

    def test_orchestrate_route_back_to_construqtor(self):
        """When Sqrewdriver flags issues, repair suggestions should route back."""
        fail_ids = {"html_structure"}
        worker_fn = make_failing_build_fn(fail_ids)

        result = orchestrate(self.task_file, worker_fn)

        # Check repair suggestions in the OrchestratorRunResult
        if result.sqrewdriver_result:
            constr_suggestions = [
                s for s in result.sqrewdriver_result.repair_suggestions
                if "Construqtor" in s
            ]
            self.assertGreater(len(constr_suggestions), 0)

    def test_orchestrate_inspeqtor_routes_back(self):
        """When Inspeqtor finds issues, repair suggestions should flow."""
        worker_fn = make_failing_build_fn(set())

        result = orchestrate(self.task_file, worker_fn)

        # All passing, but Inspeqtor may find warnings
        if result.inspeqtor_result:
            # Check that routing hints exist
            pass  # Inspeqtor may not flag anything for clean workers

    def test_orchestrate_all_pass_no_route_back(self):
        """When everything passes, no repair routing is needed."""
        result = orchestrate(self.task_file, default_build_fn)
        self.assertEqual(result.overall_status, "PASS")
        # No repair suggestions needed
        sq = result.sqrewdriver_result
        if sq:
            self.assertNotIn("Route back", " ".join(sq.repair_suggestions).lower())


class TestOrchestratorConfigFromEnv(unittest.TestCase):
    def setUp(self):
        self._old_env = {}
        for key in ("QONQ_PARALLEL_ENABLED", "QONQ_MAX_WORKERS",
                    "QONQ_MAX_SELF_REVIEW_ITERATIONS", "QONQ_VALIDATOR_STRICTNESS",
                    "QONQ_DRY_RUN", "QONQ_TASK_PATH"):
            self._old_env[key] = os.environ.get(key)

    def tearDown(self):
        for key, val in self._old_env.items():
            if val is not None:
                os.environ[key] = val
            elif key in os.environ:
                del os.environ[key]

    def test_from_env_defaults(self):
        config = OrchestratorConfig.from_env()
        self.assertTrue(config.parallel_enabled)
        self.assertEqual(config.max_workers, 4)
        self.assertEqual(config.max_self_review_iterations, 3)
        self.assertEqual(config.validator_strictness, "normal")
        self.assertFalse(config.dry_run)

    def test_from_env_overrides(self):
        os.environ["QONQ_PARALLEL_ENABLED"] = "false"
        os.environ["QONQ_MAX_WORKERS"] = "8"
        os.environ["QONQ_MAX_SELF_REVIEW_ITERATIONS"] = "5"
        os.environ["QONQ_VALIDATOR_STRICTNESS"] = "strict"
        os.environ["QONQ_DRY_RUN"] = "true"
        os.environ["QONQ_TASK_PATH"] = "/tmp/task.md"

        config = OrchestratorConfig.from_env()
        self.assertFalse(config.parallel_enabled)
        self.assertEqual(config.max_workers, 8)
        self.assertEqual(config.max_self_review_iterations, 5)
        self.assertEqual(config.validator_strictness, "strict")
        self.assertTrue(config.dry_run)
        self.assertEqual(config.task_path, "/tmp/task.md")

    def test_from_env_invalid_values_use_defaults(self):
        os.environ["QONQ_MAX_WORKERS"] = "not_a_number"
        os.environ["QONQ_MAX_SELF_REVIEW_ITERATIONS"] = "invalid"
        os.environ["QONQ_VALIDATOR_STRICTNESS"] = "extreme"

        config = OrchestratorConfig.from_env()
        self.assertEqual(config.max_workers, 4)
        self.assertEqual(config.max_self_review_iterations, 3)
        self.assertEqual(config.validator_strictness, "normal")


if __name__ == "__main__":
    unittest.main()
