import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import inspeqtor  # noqa: E402


class CompletionRequiredFilesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="qonq_req_files_")
        self.workspace = Path(self._tmp)
        (self.workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
        (self.workspace / "planning").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_planning_files(self, required_files):
        (self.workspace / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (self.workspace / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (self.workspace / "planning" / "completion-criteria.v1.json").write_text(
            json.dumps(
                {
                    "summary": "Test criteria",
                    "required_files": required_files,
                }
            ),
            encoding="utf-8",
        )
        (self.workspace / "planning" / "build-groups.v1.json").write_text(
            json.dumps(
                {
                    "briq_inventory": [{"briq_ref": "briq-001"}],
                    "items": [{"briq_refs": ["briq-001"]}],
                }
            ),
            encoding="utf-8",
        )

    def test_missing_required_file_forces_non_success_verdict(self):
        (self.workspace / "qodeyard" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        self._write_planning_files(["main.py", "run.sh"])

        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=self.workspace,
            cycle_num="1",
            overall_assessment="SUCCESS",
            validation_bundle={"status": "PASS", "issues": []},
            realization_bundle={
                "scope_summary": {"touched_scopes": ["scope-a"], "undeclared_touched_scopes": []},
                "confidence": "CONFIDENCE_HIGH",
                "unknowns": [],
            },
            inspection_input={"status": "READY", "required_inputs": {}},
            cross_briq_warnings=[],
            failed_briq_suggestions=[],
        )

        req_file_criterion = next(
            item
            for item in verdict["completion_criteria_results"]
            if item["criterion"] == "Required deliverable files exist in qodeyard."
        )
        self.assertEqual(req_file_criterion["status"], "FAIL")
        self.assertIn("run.sh", req_file_criterion["basis"]["missing_required_files"])
        self.assertNotEqual(verdict["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
