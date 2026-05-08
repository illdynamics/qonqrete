#!/usr/bin/env python3
"""Tests for worker_contract.py — worker result contract validation."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from worker_contract import (
    WorkerResult,
    SelfReview,
    BriqGroup,
    SqrewdriverResult,
    SqrewdriverFinding,
    InspeqtorResult,
    InspeqtorFinding,
    OrchestratorRunResult,
    validate_worker_status,
    worker_status_from_bool,
    merge_statuses,
)


class TestWorkerResult(unittest.TestCase):
    def test_success_result(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS",
            changed_files=["index.html"],
            summary="Created index.html",
            self_review=SelfReview(issues_found=[], fixes_applied=[], remaining_risks=[]),
            tests_run=["test_html.sh"],
            validation_notes=["Valid OK"],
        )
        self.assertTrue(r.is_success())
        self.assertFalse(r.is_failure())

    def test_failure_result(self):
        r = WorkerResult(worker_id="w1", briq_id="b1", status="FAIL_REBUILD_REQUIRED")
        self.assertFalse(r.is_success())
        self.assertTrue(r.is_failure())

    def test_to_dict_and_from_dict(self):
        r = WorkerResult(
            worker_id="w1",
            briq_id="b1",
            status="PASS_WITH_WARNINGS",
            changed_files=["a.txt", "b.txt"],
            summary="Done",
            self_review=SelfReview(
                issues_found=["missing test"],
                fixes_applied=["added test"],
                remaining_risks=["coverage gap"],
            ),
            tests_run=["pytest"],
            validation_notes=["reviewed"],
        )
        d = r.to_dict()
        r2 = WorkerResult.from_dict(d)
        self.assertEqual(r2.worker_id, "w1")
        self.assertEqual(r2.briq_id, "b1")
        self.assertEqual(r2.status, "PASS_WITH_WARNINGS")
        self.assertEqual(r2.changed_files, ["a.txt", "b.txt"])
        self.assertIsNotNone(r2.self_review)
        if r2.self_review:
            self.assertEqual(r2.self_review.issues_found, ["missing test"])
            self.assertEqual(r2.self_review.remaining_risks, ["coverage gap"])

    def test_status_validation(self):
        self.assertEqual(validate_worker_status("PASS"), "PASS")
        self.assertEqual(validate_worker_status("FAIL_REPAIRABLE"), "FAIL_REPAIRABLE")
        self.assertEqual(validate_worker_status("INVALID"), "FAIL_REBUILD_REQUIRED")
        self.assertEqual(validate_worker_status("pass"), "PASS")
        self.assertEqual(validate_worker_status(""), "FAIL_REBUILD_REQUIRED")

    def test_status_from_bool(self):
        self.assertEqual(worker_status_from_bool(True), "PASS")
        self.assertEqual(worker_status_from_bool(False), "FAIL_REPAIRABLE")


class TestMergeStatuses(unittest.TestCase):
    def test_all_pass(self):
        self.assertEqual(merge_statuses(["PASS", "PASS"]), "PASS")

    def test_worst_wins(self):
        self.assertEqual(merge_statuses(["PASS", "FAIL_REBUILD_REQUIRED"]), "FAIL_REBUILD_REQUIRED")
        self.assertEqual(merge_statuses(["PASS_WITH_WARNINGS", "FAIL_REPAIRABLE"]), "FAIL_REPAIRABLE")
        self.assertEqual(merge_statuses(["BLOCKED", "PASS"]), "BLOCKED")

    def test_empty_list(self):
        self.assertEqual(merge_statuses([]), "PASS")


class TestBriqGroupSerialization(unittest.TestCase):
    def test_to_dict(self):
        g = BriqGroup(id="x", name="X", description="desc", depends_on=["y"],
                      allowed_paths=["src/"], read_paths=["docs/"],
                      acceptance=["a"], parallel_safe=False)
        d = g.to_dict()
        self.assertEqual(d["id"], "x")
        self.assertFalse(d["parallel_safe"])

    def test_from_dict(self):
        d = {"id": "g1", "name": "G1", "description": "", "depends_on": [],
             "allowed_paths": [], "read_paths": [], "acceptance": [],
             "parallel_safe": True}
        g = BriqGroup.from_dict(d)
        self.assertEqual(g.id, "g1")
        self.assertTrue(g.parallel_safe)


class TestSqrewdriverResult(unittest.TestCase):
    def test_roundtrip(self):
        r = SqrewdriverResult(
            status="FAIL_REPAIRABLE",
            findings=[
                SqrewdriverFinding(source="test", file="a.txt", message="broken",
                                   severity="error", repair_suggestion="fix it")
            ],
            repair_suggestions=["fix a.txt"],
            commands_run=["pytest"],
        )
        d = r.to_dict()
        r2 = SqrewdriverResult.from_dict(d)
        self.assertEqual(r2.status, "FAIL_REPAIRABLE")
        self.assertEqual(len(r2.findings), 1)
        self.assertEqual(r2.findings[0].file, "a.txt")
        self.assertEqual(r2.repair_suggestions, ["fix a.txt"])


class TestInspeqtorResult(unittest.TestCase):
    def test_roundtrip(self):
        r = InspeqtorResult(
            status="PASS_WITH_WARNINGS",
            findings=[
                InspeqtorFinding(check_id="sec", severity="warning",
                                 message="hardcoded key", file="config.py",
                                 required_action="use env var")
            ],
            acceptance_checked=["req1"],
            security_issues=["key in config.py"],
        )
        d = r.to_dict()
        r2 = InspeqtorResult.from_dict(d)
        self.assertEqual(r2.status, "PASS_WITH_WARNINGS")
        self.assertEqual(len(r2.findings), 1)
        self.assertEqual(r2.findings[0].check_id, "sec")
        self.assertEqual(r2.acceptance_checked, ["req1"])


class TestOrchestratorRunResult(unittest.TestCase):
    def test_to_dict(self):
        r = OrchestratorRunResult(
            overall_status="PASS",
            planner_status="PASS",
            worker_results=[
                WorkerResult(worker_id="w1", briq_id="b1", status="PASS")
            ],
            sqrewdriver_result=SqrewdriverResult(status="PASS"),
            inspeqtor_result=InspeqtorResult(status="PASS"),
            parallel_groups=[["b1"]],
            serial_groups=[],
        )
        d = r.to_dict()
        self.assertEqual(d["overall_status"], "PASS")
        self.assertEqual(len(d["worker_results"]), 1)
        self.assertIsNotNone(d["sqrewdriver_result"])
        self.assertIsNotNone(d["inspeqtor_result"])


if __name__ == "__main__":
    unittest.main()
