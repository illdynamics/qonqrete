import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))

import inspeqtor
import construqtor
import qrane
from execution_model import ExecutionState, ExecutionLimits

class RepairStrategyOverhaulTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="qonq_overhaul_")
        self.workspace = Path(self._tmp)
        (self.workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
        (self.workspace / "planning").mkdir(parents=True, exist_ok=True)
        (self.workspace / "briq.d").mkdir(parents=True, exist_ok=True)
        (self.workspace / "exeq.d").mkdir(parents=True, exist_ok=True)
        (self.workspace / "reqap.d").mkdir(parents=True, exist_ok=True)
        (self.workspace / "qontract.d").mkdir(parents=True, exist_ok=True)
        
        # Mock some essentials
        (self.workspace / "config.yaml").write_text("{}", encoding="utf-8")
        for f in ["execution-blueprint.v1.json", "validation-plan.v1.json", "completion-criteria.v1.json", "build-groups.v1.json"]:
            (self.workspace / "planning" / f).write_text("{}", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_repair_inversion_mapping(self):
        # Level 1 should be Surgical
        lvl = inspeqtor.recommend_repair_start_level_for_failure_class("collateral_churn_overrewrite")
        self.assertEqual(lvl, 1)
        # Level 4 should be Broad
        lvl = inspeqtor.recommend_repair_start_level_for_failure_class("broad_task_shape_miss")
        self.assertEqual(lvl, 4)

    def test_stale_invalidation_fingerprint(self):
        file_path = self.workspace / "qodeyard" / "app.js"
        file_path.write_text("original content", encoding="utf-8")
        
        from inspeqtor import sha256_file
        old_hash = sha256_file(file_path)
        
        # Issue reported on old hash
        validation_bundle = {
            "status": "PASS",
            "issues": [
                {
                    "severity": "error",
                    "file": "app.js",
                    "file_hash": old_hash,
                    "message": "Logic missing"
                }
            ]
        }
        
        # Change file
        file_path.write_text("updated content", encoding="utf-8")
        
        # Verdict should invalidate the issue
        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=self.workspace,
            cycle_num="1",
            overall_assessment="SUCCESS",
            validation_bundle=validation_bundle,
            realization_bundle={"scope_summary": {"touched_scopes": ["a"]}},
            inspection_input={"status": "READY"},
            cross_briq_warnings=[],
            failed_briq_suggestions=[]
        )
        
        # Issue should be INVALIDATED
        issue = verdict["issues"][0]
        self.assertEqual(issue.get("status"), "INVALIDATED")
        
        # And since it's the only error, verdict status should be SUCCESS (or PASS)
        # wait, build_inspection_verdict determines SUCCESS based on overall_assessment if no errors
        self.assertEqual(verdict["status"], "SUCCESS")

    def test_repair_plan_targeting_propagation(self):
        # Setup criteria failure
        verdict = {
            "status": "FAIL",
            "completion_criteria_results": [
                {
                    "criterion": "Required deliverables exist",
                    "status": "FAIL",
                    "basis": {
                        "missing_required_files": ["missing.py"]
                    }
                }
            ]
        }
        validation_bundle = {
            "issues": [
                {
                    "severity": "error",
                    "file": "error.py",
                    "message": "Syntax error"
                }
            ]
        }
        
        # Write some briqs to globs find them
        (self.workspace / "briq.d" / "cyqle1_001.md").write_text("Briq-Ref: briq-001\n", encoding="utf-8")
        
        plan = inspeqtor.build_repair_plan(
            self.workspace, "1", verdict, validation_bundle, 
            {"group_summaries": []}, {}, []
        )
        
        self.assertIn("missing.py", plan["target_files"])
        self.assertIn("error.py", plan["target_files"])
        self.assertIn("Required deliverables exist", plan["target_criteria_ids"])

if __name__ == "__main__":
    unittest.main()
