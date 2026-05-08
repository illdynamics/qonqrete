
import os
import sys
import tempfile
import unittest
import json
import hashlib
from pathlib import Path

# Setup paths to import worqer modules
ROOT = Path(__file__).resolve().parents[1]
WORQER_DIR = ROOT / "worqer"
sys.path.insert(0, str(WORQER_DIR))

import inspeqtor
import construqtor
import shellscript_validation

class SelectiveRepairAndFinishTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.qodeyard = self.root / "qodeyard"
        self.qodeyard.mkdir(parents=True, exist_ok=True)
        (self.root / "verdict").mkdir(parents=True, exist_ok=True)
        (self.root / "planning").mkdir(parents=True, exist_ok=True)
        (self.root / "task").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_lock_all_passing_existing_files(self):
        """Test that any existing file with no hard failures is locked, even if not required."""
        # Create a file not in required_files
        (self.qodeyard / "extra.py").write_text("print('extra')\n")
        
        validation_bundle = {
            "status": "PASS",
            "issues": []
        }
        criteria_results = []
        required_files = ["main.py"] # main.py is missing
        
        lock_state = inspeqtor.build_passed_file_lock_state(
            self.root,
            "1",
            validation_bundle,
            criteria_results,
            required_files
        )
        
        locked_paths = {f["path"] for f in lock_state["files"] if f["locked"]}
        
        # Current behavior (before fix): extra.py is NOT locked
        # Desired behavior: extra.py IS locked
        self.assertIn("extra.py", locked_paths, "Existing file without failures should be locked")
        
        # main.py should NOT be locked because it's missing (status FAIL)
        self.assertNotIn("main.py", locked_paths)

    def test_finish_when_hard_gates_pass_with_soft_warnings(self):
        """Test that verdict is SUCCESS if only soft warnings exist."""
        validation_bundle = {
            "status": "FAIL", # Validator might say FAIL due to warnings
            "issues": [
                {
                    "severity": "warning",
                    "message": "shellcheck: use double quotes",
                    "file": "run.sh",
                    "source": "smoketest",
                    "check_type": "shellcheck"
                }
            ]
        }
        
        # Setup minimal planning artifacts
        (self.root / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (self.root / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (self.root / "planning" / "completion-criteria.v1.json").write_text("{}", encoding="utf-8")
        (self.root / "planning" / "build-groups.v1.json").write_text("{\"items\":[],\"briq_inventory\":[]}", encoding="utf-8")
        
        verdict = inspeqtor.build_inspection_verdict(
            self.root,
            "1",
            "OK",
            validation_bundle,
            {"evidence_status": "EVIDENCE_PARTIAL"},
            {"status": "READY"},
            [],
            []
        )
        
        self.assertEqual(verdict["status"], "SUCCESS")
        self.assertEqual(verdict["repair_needed"], False)

    def test_run_sh_exact_contract(self):
        """Test that wrapper commands are rejected under strict exact-command policy."""
        clever_run_sh = """#!/bin/bash
PORT=$(python -c "print(8000)")
python service.py --port $PORT
"""
        errors = shellscript_validation.validate_run_sh_contract(
            clever_run_sh,
            {
                "exact_command_required": "python service.py --port $PORT",
                "allow_wrapper": False,
                "allowed_boilerplate": ["set", "export"],
            },
        )
        self.assertTrue(any("only allowed boilerplate" in e for e in errors))

    def test_locked_file_preservation_during_repair(self):
        """Test that construqtor blocks edits to locked files."""
        lock_scope = {
            "locked_paths": ["run.sh"],
            "unlocked_paths": [],
            "hard_failure_paths": []
        }
        
        extracted_files = {
            "main.py": "print('fixed')\n",
            "run.sh": "python -m uvicorn main:app --port 9000\n" # Violating change
        }
        
        filtered, violations = construqtor._filter_locked_file_edits(
            extracted_files,
            lock_scope=lock_scope
        )
        
        self.assertIn("run.sh", violations)
        self.assertNotIn("run.sh", filtered)
        self.assertIn("main.py", filtered)

if __name__ == "__main__":
    unittest.main()
