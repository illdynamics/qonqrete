from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import construqtor  # noqa: E402
import sqrewdriver_controller  # noqa: E402
from execution_model import ExecutionLimits, ExecutionState  # noqa: E402


class SqrewdriverControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="qonq_sqrewdriver_")
        self.workspace = Path(self._tmp)
        for rel in ("qodeyard", "verdict", "validation", "realization", "planning", "briq.d", "reqap.d"):
            (self.workspace / rel).mkdir(parents=True, exist_ok=True)
        (self.workspace / "briq.d" / "cyqle1_001.md").write_text(
            "Briq-Ref: briq-001\nTarget-Files: alpha.txt\n",
            encoding="utf-8",
        )
        (self.workspace / "realization" / "realization-bundle.v1.json").write_text(
            json.dumps({"status": "EVIDENCE_PARTIAL"}),
            encoding="utf-8",
        )
        (self.workspace / "reqap.d" / "cyqle1_reqap.md").write_text("review notes\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_json(self, rel: str, payload: dict) -> None:
        path = self.workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _state(self, *, repair_pass_index: int = 0) -> ExecutionState:
        return ExecutionState(
            global_iteration_index=1,
            pass_kind="build",
            build_pass_index=1,
            repair_pass_index=repair_pass_index,
        )

    def _limits(self, *, repairs: int = 2) -> ExecutionLimits:
        return ExecutionLimits(max_total_iterations=4, max_build_passes=2, max_attempts_per_build_pass=repairs)

    def _config(self) -> dict:
        return {
            "sqrewdriver": {
                "enabled": True,
                "write_repair_brief": True,
                "include_validation_issue_limit": 50,
                "include_reqap_excerpt_chars": 12000,
                "include_prior_attempts": True,
            }
        }

    def test_success_verdict_stops(self) -> None:
        (self.workspace / "qodeyard" / "foo.txt").write_text("ok\n", encoding="utf-8")
        self._write_json("planning/completion-criteria.v1.json", {"required_files": ["foo.txt"]})
        self._write_json("validation/validation-bundle.v1.json", {"status": "PASS", "issues": [], "checks": []})
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "SUCCESS",
                "task_completed": True,
                "hard_gate_status": "PASS",
                "repair_needed": False,
                "inspection_integrity": "COMPLETE",
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(),
            limits=self._limits(),
            config=self._config(),
        )

        self.assertEqual(decision.action, "STOP")

    def test_success_after_repair_restores_canonical_repair_plan(self) -> None:
        (self.workspace / "qodeyard" / "foo.txt").write_text("ok\n", encoding="utf-8")
        self._write_json("planning/completion-criteria.v1.json", {"required_files": ["foo.txt"]})
        self._write_json("validation/validation-bundle.v1.json", {"status": "PASS", "issues": [], "checks": []})
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "SUCCESS",
                "task_completed": True,
                "hard_gate_status": "PASS",
                "repair_needed": False,
                "inspection_integrity": "COMPLETE",
            },
        )
        self._write_json(
            "verdict/sqrewdriver-last-repair-plan.v1.json",
            {
                "schema_version": "repair-plan.v1",
                "required_actions": ["preserve the bounded repair audit trail"],
                "target_files": ["foo.txt"],
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(),
            limits=self._limits(),
            config=self._config(),
        )

        restored_plan = self.workspace / "verdict" / "repair-plan.v1.json"
        self.assertEqual(decision.action, "STOP")
        self.assertTrue(restored_plan.exists())
        restored = json.loads(restored_plan.read_text(encoding="utf-8"))
        self.assertTrue(restored["sqrewdriver_restored_after_success"])
        self.assertIn("preserve the bounded repair audit trail", restored["required_actions"])

    def test_failure_verdict_repairs_and_writes_brief(self) -> None:
        self._write_json("planning/completion-criteria.v1.json", {"required_files": ["alpha.txt"]})
        self._write_json(
            "validation/validation-bundle.v1.json",
            {
                "status": "FAIL",
                "checks": [{"check_id": "generic-contract", "status": "FAIL", "summary": "alpha must be complete"}],
                "issues": [
                    {
                        "source": "validation",
                        "severity": "error",
                        "file": "alpha.txt",
                        "message": "alpha output is incomplete",
                        "check_type": "GENERIC_CHECK",
                    }
                ],
            },
        )
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "FAILURE",
                "task_completed": False,
                "hard_gate_status": "FAIL",
                "repair_needed": True,
                "repair_required": True,
                "unresolved_issues": ["alpha output is incomplete"],
            },
        )
        self._write_json(
            "verdict/repair-plan.v1.json",
            {
                "required_actions": ["complete alpha output"],
                "target_files": ["alpha.txt"],
                "validation_scope_files": ["alpha.txt"],
                "allowed_edit_paths": ["alpha.txt"],
                "locked_file_paths": ["locked.txt"],
                "target_briq_files": ["cyqle1_001.md"],
                "issue_fingerprints": [{"fingerprint": "validation::alpha"}],
                "evidence_refs": ["validation/validation-bundle.v1.json"],
                "same_run_repair_eligible": True,
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(),
            limits=self._limits(),
            config=self._config(),
        )

        self.assertEqual(decision.action, "REPAIR")
        brief_path = self.workspace / "verdict" / "sqrewdriver-repair-brief.v1.md"
        self.assertTrue(brief_path.exists())
        brief = brief_path.read_text(encoding="utf-8")
        self.assertIn("complete alpha output", brief)
        self.assertIn("alpha.txt", brief)
        self.assertIn("locked.txt", brief)
        self.assertIn("alpha output is incomplete", brief)

    def test_repair_scope_drops_placeholder_paths(self) -> None:
        self._write_json(
            "validation/validation-bundle.v1.json",
            {
                "issues": [
                    {
                        "source": "validation",
                        "severity": "error",
                        "file": "alpha.txt",
                        "message": "alpha output is incomplete",
                    }
                ],
            },
        )
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "FAILURE",
                "task_completed": False,
                "hard_gate_status": "FAIL",
                "repair_needed": True,
            },
        )
        self._write_json(
            "verdict/repair-plan.v1.json",
            {
                "required_actions": ["complete alpha output"],
                "target_files": ["alpha.txt", "none", "n/a"],
                "allowed_edit_paths": ["alpha.txt", "null"],
                "locked_file_paths": ["not applicable"],
                "target_briq_files": ["cyqle1_001.md"],
                "same_run_repair_eligible": True,
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(),
            limits=self._limits(),
            config=self._config(),
        )

        self.assertEqual(decision.action, "REPAIR")
        plan = json.loads((self.workspace / "verdict" / "repair-plan.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["target_files"], ["alpha.txt"])
        self.assertEqual(plan["allowed_edit_paths"], ["alpha.txt"])
        self.assertEqual(plan["locked_file_paths"], [])
        brief = (self.workspace / "verdict" / "sqrewdriver-repair-brief.v1.md").read_text(encoding="utf-8")
        self.assertIn("alpha.txt", brief)
        brief_json = json.loads((self.workspace / "verdict" / "sqrewdriver-repair-brief.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(brief_json["repair_scope"]["target_files"], ["alpha.txt"])
        self.assertEqual(brief_json["repair_scope"]["allowed_edit_paths"], ["alpha.txt"])
        self.assertEqual(brief_json["repair_scope"]["locked_file_paths"], [])

    def test_partial_or_degraded_verdict_repairs_when_repair_needed(self) -> None:
        self._write_json("validation/validation-bundle.v1.json", {"issues": []})
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "PARTIAL",
                "task_completed": False,
                "hard_gate_status": "FAIL",
                "repair_needed": True,
                "inspection_integrity": "DEGRADED",
            },
        )
        self._write_json(
            "verdict/repair-plan.v1.json",
            {
                "required_actions": ["resolve partial inspection"],
                "target_files": ["alpha.txt"],
                "allowed_edit_paths": ["alpha.txt"],
                "target_briq_files": ["cyqle1_001.md"],
                "same_run_repair_eligible": True,
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(),
            limits=self._limits(),
            config=self._config(),
        )

        self.assertEqual(decision.action, "REPAIR")

    def test_cap_hit_stops_partial(self) -> None:
        self._write_json("validation/validation-bundle.v1.json", {"issues": []})
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "FAILURE",
                "task_completed": False,
                "hard_gate_status": "FAIL",
                "repair_needed": True,
            },
        )
        self._write_json(
            "verdict/repair-plan.v1.json",
            {
                "required_actions": ["fix bounded failure"],
                "target_briq_files": ["cyqle1_001.md"],
                "same_run_repair_eligible": True,
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(repair_pass_index=2),
            limits=self._limits(repairs=2),
            config=self._config(),
        )

        self.assertEqual(decision.action, "STOP_PARTIAL")
        self.assertIn("repair_cap_hit", decision.reason)
        self.assertNotIn("hard_gate_success", decision.reason)
        self.assertFalse((self.workspace / "verdict" / "sqrewdriver-repair-brief.v1.md").exists())

    def test_missing_required_file_refuses_stop(self) -> None:
        self._write_json("planning/completion-criteria.v1.json", {"required_files": ["foo.txt"]})
        self._write_json("validation/validation-bundle.v1.json", {"issues": [], "checks": []})
        self._write_json(
            "verdict/inspection-verdict.v1.json",
            {
                "status": "SUCCESS",
                "task_completed": True,
                "hard_gate_status": "PASS",
                "repair_needed": False,
            },
        )

        decision = sqrewdriver_controller.evaluate_after_inspection(
            self.workspace,
            cycle=1,
            execution_state=self._state(),
            limits=self._limits(),
            config=self._config(),
        )

        self.assertEqual(decision.action, "REPAIR")
        self.assertIn("missing_required_files", decision.summary["failure_reasons"][0])

    def test_no_task_specific_literals_in_controller_or_tests(self) -> None:
        forbidden = [
            "tasq-" + "small",
            "tasq-" + "medium",
            "Fast" + "API",
            "uvi" + "corn",
            "rec" + "ipe",
            "local" + "Storage",
        ]
        paths = [
            PROJECT_ROOT / "qrane" / "sqrewdriver_controller.py",
            Path(__file__),
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for item in forbidden:
                self.assertNotIn(item, text)

    def test_construqtor_loads_sqrewdriver_brief_in_repair_context(self) -> None:
        repair_plan = self.workspace / "verdict" / "repair-plan.v1.json"
        repair_plan.write_text(
            json.dumps(
                {
                    "repair_pass_index": 1,
                    "repair_reason_summary": "bounded repair",
                    "required_actions": ["fix alpha"],
                    "target_briq_files": ["cyqle1_001.md"],
                    "locked_file_paths": ["locked.txt"],
                }
            ),
            encoding="utf-8",
        )
        brief = self.workspace / "verdict" / "sqrewdriver-repair-brief.v1.md"
        brief.write_text("Brief says fix only alpha evidence.\n", encoding="utf-8")

        with patch.dict(
            os.environ,
            {
                "QONQ_REPAIR_MODE": "1",
                "QONQ_REPAIR_PLAN_PATH": str(repair_plan),
                "QONQ_SQREWDRIVER_REPAIR_BRIEF_PATH": str(brief),
            },
            clear=False,
        ):
            context = construqtor.load_repair_context(self.workspace)

        self.assertIn("SQREWDRIVER REPAIR BRIEF (HIGH PRIORITY)", context)
        self.assertIn("Brief says fix only alpha evidence.", context)
        self.assertIn("STRUCTURED SCOPE AUTHORITY", context)


if __name__ == "__main__":
    unittest.main()
