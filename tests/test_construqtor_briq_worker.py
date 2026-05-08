#!/usr/bin/env python3
"""Tests for construqtor_briq_worker.py — Construqtor briq worker contract."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from worker_contract import (
    BriqGroup,
    WorkerResult,
    SelfReview,
)
from construqtor_briq_worker import (
    BriqWorkerConfig,
    default_build_fn,
    contract_validating_build_fn,
    make_failing_build_fn,
    detect_path_conflicts,
    run_briq_worker,
)


class TestDefaultBuildFn(unittest.TestCase):
    def test_basic_html_briq(self):
        group = BriqGroup(
            id="html",
            name="HTML Structure",
            description="Create index.html",
            allowed_paths=["index.html"],
            acceptance=["Create index.html"],
        )
        result = default_build_fn(group)
        self.assertEqual(result.status, "PASS")
        self.assertIn("index.html", result.changed_files)
        self.assertEqual(result.briq_id, "html")

    def test_multiple_files(self):
        group = BriqGroup(
            id="frontend",
            name="Frontend",
            allowed_paths=["index.html", "styles.css", "app.js"],
            acceptance=["Build frontend"],
        )
        result = default_build_fn(group)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.changed_files), 3)

    def test_worker_id_format(self):
        group = BriqGroup(id="test_group", name="Test", allowed_paths=["x.txt"])
        result = default_build_fn(group)
        self.assertEqual(result.worker_id, "construqtor_test_group")


class TestContractValidatingBuildFn(unittest.TestCase):
    def test_valid_contract(self):
        group = BriqGroup(
            id="valid",
            name="Valid Group",
            description="A valid group",
            allowed_paths=["src/"],
            acceptance=["Must work"],
        )
        result = contract_validating_build_fn(group)
        self.assertEqual(result.status, "PASS")

    def test_empty_id_flagged(self):
        group = BriqGroup(id="", name="Missing ID")
        result = contract_validating_build_fn(group)
        self.assertEqual(result.status, "FAIL_REPAIRABLE")
        self.assertTrue(any("empty id" in i.lower() for i in result.self_review.issues_found))

    def test_empty_name_flagged(self):
        group = BriqGroup(id="no_name", name="")
        result = contract_validating_build_fn(group)
        self.assertEqual(result.status, "FAIL_REPAIRABLE")
        self.assertTrue(any("empty name" in i.lower() for i in result.self_review.issues_found))

    def test_parallel_safe_without_paths_warns(self):
        group = BriqGroup(
            id="empty_paths",
            name="Empty Paths",
            description="desc",
            allowed_paths=[],
            parallel_safe=True,
        )
        result = contract_validating_build_fn(group)
        # parallel_safe=True with no allowed_paths should be at least PASS_WITH_WARNINGS
        self.assertNotEqual(result.status, "PASS")
        if result.self_review:
            self.assertTrue(len(result.self_review.remaining_risks) > 0)


class TestMakeFailingBuildFn(unittest.TestCase):
    def test_specific_briqs_fail(self):
        groups = [
            BriqGroup(id="pass1", name="Pass 1", allowed_paths=["a.txt"]),
            BriqGroup(id="fail1", name="Fail 1", allowed_paths=["b.txt"]),
            BriqGroup(id="pass2", name="Pass 2", allowed_paths=["c.txt"]),
        ]
        fn = make_failing_build_fn({"fail1"}, "FAIL_REPAIRABLE")

        for g in groups:
            result = fn(g)
            if g.id == "fail1":
                self.assertEqual(result.status, "FAIL_REPAIRABLE")
                self.assertEqual(result.changed_files, [])
            else:
                self.assertEqual(result.status, "PASS")
                self.assertGreater(len(result.changed_files), 0)

    def test_custom_failure_status(self):
        fn = make_failing_build_fn({"a"}, "BLOCKED")
        group = BriqGroup(id="a", name="A", allowed_paths=["x.txt"])
        result = fn(group)
        self.assertEqual(result.status, "BLOCKED")


class TestDetectPathConflicts(unittest.TestCase):
    def test_no_conflict(self):
        groups = [
            BriqGroup(id="html", name="HTML", allowed_paths=["index.html"]),
            BriqGroup(id="css", name="CSS", allowed_paths=["styles.css"]),
        ]
        conflicts = detect_path_conflicts(groups)
        self.assertEqual(len(conflicts), 0)

    def test_exact_path_conflict(self):
        groups = [
            BriqGroup(id="a", name="A", allowed_paths=["src/app.py"]),
            BriqGroup(id="b", name="B", allowed_paths=["src/app.py"]),
        ]
        conflicts = detect_path_conflicts(groups)
        self.assertEqual(len(conflicts), 1)
        ids = {c[0] for c in conflicts} | {c[1] for c in conflicts}
        self.assertIn("a", ids)
        self.assertIn("b", ids)

    def test_nested_path_conflict(self):
        groups = [
            BriqGroup(id="src", name="Src", allowed_paths=["src/"]),
            BriqGroup(id="file", name="File", allowed_paths=["src/app.py"]),
        ]
        conflicts = detect_path_conflicts(groups)
        self.assertEqual(len(conflicts), 1)

    def test_read_path_also_conflicts(self):
        """Read paths should also be checked for conflicts."""
        groups = [
            BriqGroup(id="read", name="Read", read_paths=["shared/"]),
            BriqGroup(id="write", name="Write", allowed_paths=["shared/data.txt"]),
        ]
        conflicts = detect_path_conflicts(groups)
        self.assertEqual(len(conflicts), 1)

    def test_empty_paths_no_conflict(self):
        groups = [
            BriqGroup(id="a", name="A", allowed_paths=[]),
            BriqGroup(id="b", name="B", allowed_paths=[]),
        ]
        conflicts = detect_path_conflicts(groups)
        self.assertEqual(len(conflicts), 0)


class TestRunBriqWorker(unittest.TestCase):
    def test_default_worker_pass(self):
        group = BriqGroup(
            id="html",
            name="HTML",
            description="Create index.html",
            allowed_paths=["index.html"],
            acceptance=["Create index.html"],
        )
        loop_result = run_briq_worker(group)
        self.assertTrue(loop_result.converged)
        self.assertEqual(loop_result.final_result.status, "PASS")
        self.assertEqual(loop_result.final_result.worker_id, "construqtor_html")

    def test_contract_validating_worker(self):
        group = BriqGroup(id="bad", name="", description="Missing name")
        loop_result = run_briq_worker(
            group,
            build_fn=contract_validating_build_fn,
        )
        # Should fail on first review since name is empty
        self.assertFalse(loop_result.converged)
        self.assertIn(loop_result.final_result.status, ("FAIL_REPAIRABLE", "PASS_WITH_WARNINGS"))


if __name__ == "__main__":
    unittest.main()
