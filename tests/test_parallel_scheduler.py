#!/usr/bin/env python3
"""Tests for parallel_scheduler.py — safe parallel/sequential dispatch."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from briq_planner import BriqGroup, PlannerResult
from parallel_scheduler import (
    SchedulerConfig,
    execute_plan,
    resolve_execution_plan,
    _detect_path_conflicts,
)
from worker_contract import WorkerResult, SelfReview


def _make_worker_fn(
    results: dict[str, WorkerResult] | None = None,
) -> Any:
    """Create a worker function that returns predetermined results."""
    if results is None:
        results = {}

    def worker_fn(group: BriqGroup) -> WorkerResult:
        if group.id in results:
            return results[group.id]
        return WorkerResult(
            worker_id=f"test_worker_{group.id}",
            briq_id=group.id,
            status="PASS",
            changed_files=group.allowed_paths[:],
            summary=f"Built {group.name}",
            self_review=SelfReview(issues_found=[], fixes_applied=[]),
            tests_run=[f"test_{group.id}.sh"],
            validation_notes=[f"Validated {group.id}"],
        )

    return worker_fn


class TestPathConflictDetection(unittest.TestCase):
    def test_same_path_conflict(self):
        a = BriqGroup(id="a", name="A", allowed_paths=["src/app.py"])
        b = BriqGroup(id="b", name="B", allowed_paths=["src/app.py"])
        self.assertTrue(_detect_path_conflicts(a, b))

    def test_nested_path_conflict(self):
        a = BriqGroup(id="a", name="A", allowed_paths=["src/"])
        b = BriqGroup(id="b", name="B", allowed_paths=["src/app.py"])
        self.assertTrue(_detect_path_conflicts(a, b))

    def test_different_paths_no_conflict(self):
        a = BriqGroup(id="a", name="A", allowed_paths=["src/app.py"])
        b = BriqGroup(id="b", name="B", allowed_paths=["tests/"])
        self.assertFalse(_detect_path_conflicts(a, b))

    def test_empty_paths_no_conflict(self):
        a = BriqGroup(id="a", name="A", allowed_paths=[])
        b = BriqGroup(id="b", name="B", allowed_paths=[])
        self.assertFalse(_detect_path_conflicts(a, b))


class TestResolveExecutionPlan(unittest.TestCase):
    def test_serial_fallback(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=[]),
            BriqGroup(id="b", name="B", depends_on=["a"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)
        config = SchedulerConfig(parallel_enabled=False)
        parallel, serial, order = resolve_execution_plan(result, config)
        self.assertEqual(len(parallel), 0)
        self.assertTrue(len(serial) >= 2)

    def test_parallel_enabled(self):
        groups = [
            BriqGroup(id="html", name="HTML", depends_on=[], allowed_paths=["index.html"]),
            BriqGroup(id="css", name="CSS", depends_on=[], allowed_paths=["styles.css"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)
        config = SchedulerConfig(parallel_enabled=True)
        parallel, serial, order = resolve_execution_plan(result, config)
        self.assertEqual(len(order), 2)

    def test_execution_order_respects_dependencies(self):
        """Dependencies must execute before dependents."""
        groups = [
            BriqGroup(id="a", name="A", depends_on=[]),
            BriqGroup(id="b", name="B", depends_on=["a"]),
            BriqGroup(id="c", name="C", depends_on=["a"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)
        config = SchedulerConfig(parallel_enabled=True)
        _, _, order = resolve_execution_plan(result, config)
        self.assertEqual(set(order), {"a", "b", "c"})
        # 'a' (dependency) must come before 'b' and 'c' (dependents)
        self.assertLess(order.index("a"), order.index("b"))
        self.assertLess(order.index("a"), order.index("c"))

    def test_execution_dispatch_uses_depth_order_not_batch_type_order(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=[], allowed_paths=["a.txt"]),
            BriqGroup(id="b", name="B", depends_on=[], allowed_paths=["b.txt"]),
            BriqGroup(id="c", name="C", depends_on=["a"], allowed_paths=["c.txt"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)
        seen: list[str] = []

        def worker(group: BriqGroup) -> WorkerResult:
            seen.append(group.id)
            return WorkerResult(worker_id=f"w_{group.id}", briq_id=group.id, status="PASS")

        sched_result = execute_plan(result, worker, SchedulerConfig(parallel_enabled=True))
        self.assertEqual(seen, sched_result.execution_order)
        self.assertLess(seen.index("a"), seen.index("c"))
        self.assertLess(seen.index("b"), seen.index("c"))


class TestExecutePlan(unittest.TestCase):
    def test_all_pass(self):
        groups = [
            BriqGroup(id="html", name="HTML", depends_on=[], allowed_paths=["index.html"]),
            BriqGroup(id="css", name="CSS", depends_on=[], allowed_paths=["styles.css"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)
        sched_result = execute_plan(result, _make_worker_fn())
        self.assertEqual(sched_result.overall_status, "PASS")
        self.assertEqual(len(sched_result.worker_results), 2)

    def test_some_fail(self):
        groups = [
            BriqGroup(id="ok", name="OK", depends_on=[], allowed_paths=["ok.txt"]),
            BriqGroup(id="fail", name="FAIL", depends_on=[], allowed_paths=["fail.txt"]),
        ]
        custom_results = {
            "ok": WorkerResult(worker_id="w1", briq_id="ok", status="PASS",
                               changed_files=["ok.txt"], summary="OK"),
            "fail": WorkerResult(worker_id="w2", briq_id="fail", status="FAIL_REPAIRABLE",
                                 changed_files=[], summary="Failed"),
        }
        result = PlannerResult(status="PASS", groups=groups)
        sched_result = execute_plan(result, _make_worker_fn(custom_results))
        self.assertEqual(sched_result.overall_status, "FAIL_REPAIRABLE")
        self.assertEqual(len(sched_result.worker_results), 2)

    def test_worker_exception_is_reported_as_repairable_failure(self):
        """Worker exceptions should not abort scheduler result collection."""
        groups = [
            BriqGroup(id="a", name="A", depends_on=[], allowed_paths=["a.txt"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)

        def failing_worker(group):
            raise RuntimeError(f"boom in {group.id}")

        sched_result = execute_plan(result, failing_worker)
        self.assertEqual(sched_result.overall_status, "FAIL_REPAIRABLE")
        self.assertTrue(sched_result.errors)
        self.assertEqual(len(sched_result.worker_results), 1)
        self.assertEqual(sched_result.worker_results[0].status, "FAIL_REPAIRABLE")

    def test_timing_recorded(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=[], allowed_paths=["a.txt"]),
        ]
        result = PlannerResult(status="PASS", groups=groups)
        sched_result = execute_plan(result, _make_worker_fn())
        self.assertGreater(sched_result.timing_seconds, 0)


if __name__ == "__main__":
    unittest.main()
