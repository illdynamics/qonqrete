import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))

import inspeqtor  # noqa: E402
import instruqtor  # noqa: E402
import qonfirmer  # noqa: E402
import qrane  # noqa: E402
from execution_model import ExecutionLimits  # noqa: E402


class MediumBigBlockerFixTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="qonq_v1314_")
        self.workspace = Path(self._tmp)
        (self.workspace / "planning").mkdir(parents=True, exist_ok=True)
        (self.workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
        self._prev_retry_env = os.environ.get("QONQ_RETRY_MAX_ATTEMPTS")
        os.environ.pop("QONQ_RETRY_MAX_ATTEMPTS", None)

    def tearDown(self):
        if self._prev_retry_env is None:
            os.environ.pop("QONQ_RETRY_MAX_ATTEMPTS", None)
        else:
            os.environ["QONQ_RETRY_MAX_ATTEMPTS"] = self._prev_retry_env
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_resolve_agent_ai_params_fallback_without_helper_symbol(self):
        config = {"agents": {"instruqtor": {"provider": "deepseek", "model": "deepseek-chat"}}}
        with mock.patch.object(instruqtor.lib_ai, "get_agent_ai_params", new=None):
            provider, model = instruqtor.resolve_agent_ai_params(config, "instruqtor", "openai", "gpt-4o")
        self.assertEqual(provider, "deepseek")
        self.assertEqual(model, "deepseek-chat")

    def test_compute_auto_repair_budget_is_bounded(self):
        plan_payload = {"estimation_basis": {"complexity": "high", "target_briqs": 30}}
        config = {
            "retry": {"hard_cap_max_attempts": 5},
            "repair": {"hard_cap_max_attempts_per_build_pass": 2, "auto_repair_amount": True},
        }
        budget = instruqtor.compute_auto_repair_budget(
            config=config,
            plan_payload=plan_payload,
            sensitivity=9,
            required_files=["a.py", "b.py", "c.py"],
        )
        self.assertEqual(budget["tier"], "high")
        self.assertEqual(budget["retry_max_attempts"], 4)
        self.assertEqual(budget["repair_max_attempts_per_build_pass"], 2)
        self.assertEqual(budget["caps"]["retry_max_attempts"], 5)
        self.assertEqual(budget["caps"]["repair_max_attempts_per_build_pass"], 2)

    def test_apply_auto_repair_budget_uses_recommendation_and_respects_explicit_overrides(self):
        (self.workspace / "planning" / "estimation-basis.v1.json").write_text(
            json.dumps(
                {
                    "estimation_basis": {
                        "auto_repair_budget": {
                            "enabled": True,
                            "tier": "medium",
                            "retry_max_attempts": 3,
                            "repair_max_attempts_per_build_pass": 2,
                            "caps": {
                                "retry_max_attempts": 6,
                                "repair_max_attempts_per_build_pass": 3,
                            },
                            "source": "test_budget",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        limits = ExecutionLimits(max_total_iterations=4, max_build_passes=4, max_attempts_per_build_pass=0)
        cfg_defaults = {
            "retry": {"max_attempts": 4},
            "repair": {"max_attempts_per_build_pass": 2, "auto_repair_amount": True},
        }
        details = qrane.apply_auto_repair_budget_if_enabled(self.workspace, cfg_defaults, limits, prefix="")
        self.assertTrue(details["applied"])
        self.assertEqual(details["effective_retry_max_attempts"], 3)
        self.assertEqual(details["effective_repair_max_attempts_per_build_pass"], 2)
        self.assertEqual(os.environ.get("QONQ_RETRY_MAX_ATTEMPTS"), "3")
        self.assertEqual(limits.max_attempts_per_build_pass, 2)

        limits2 = ExecutionLimits(max_total_iterations=4, max_build_passes=4, max_attempts_per_build_pass=0)
        cfg_explicit = {
            "retry": {"max_attempts": 5},
            "repair": {"max_attempts_per_build_pass": 3, "auto_repair_amount": True},
        }
        details2 = qrane.apply_auto_repair_budget_if_enabled(self.workspace, cfg_explicit, limits2, prefix="")
        self.assertEqual(details2["effective_retry_max_attempts"], 5)
        self.assertEqual(details2["effective_repair_max_attempts_per_build_pass"], 3)
        self.assertEqual(limits2.max_attempts_per_build_pass, 3)

    def test_extract_briq_file_targets_parses_required_file_sections(self):
        briq = """
Implement recipe planner.
Project must contain exactly these files:
- index.html
- styles.css
- app.js
"""
        targets = inspeqtor.extract_briq_file_targets(briq)
        self.assertEqual(set(targets), {"index.html", "styles.css", "app.js"})

    def test_instruqtor_extract_target_files_handles_qodeyard_prefixed_paths(self):
        briq = """
Create /qodeyard/requirements.txt with dependencies.
Create /qodeyard/run.sh as startup script.
Keep main.py as the app module.
"""
        targets = instruqtor.extract_target_files_from_briq(briq)
        self.assertIn("requirements.txt", targets)
        self.assertIn("run.sh", targets)
        self.assertIn("main.py", targets)

    def test_extract_briq_file_targets_parses_required_files_yaml(self):
        briq = """
required-files:
  - index.html
  - styles.css
  - app.js
"""
        targets = inspeqtor.extract_briq_file_targets(briq)
        self.assertEqual(set(targets), {"index.html", "styles.css", "app.js"})

    def test_instruqtor_primary_file_inference_avoids_cross_file_reference_churn(self):
        briq = (
            "Create the index.html file with all required UI sections. "
            "Wire up placeholder event handlers in app.js."
        )
        targets = instruqtor.extract_target_files_from_briq(briq)
        self.assertEqual(targets[0], "index.html")
        self.assertIn("app.js", targets)
        primary = instruqtor.extract_primary_files_from_briq(briq, targets)
        self.assertEqual(primary, ["index.html"])

    def test_frontend_contract_handlers_are_task_driven(self):
        (self.workspace / "qodeyard" / "index.html").write_text(
            '<!doctype html><button id="btn"></button>',
            encoding="utf-8",
        )
        (self.workspace / "qodeyard" / "app.js").write_text(
            "document.getElementById('btn').addEventListener('click', () => {});\n",
            encoding="utf-8",
        )
        (self.workspace / "task").mkdir(parents=True, exist_ok=True)
        (self.workspace / "task" / "task-spec.v1.json").write_text(
            json.dumps({"required_handler_markers": ["handle_submit"]}),
            encoding="utf-8",
        )
        issues = inspeqtor.evaluate_frontend_contracts(self.workspace)
        self.assertTrue(any("handle_submit" in issue.get("message", "") for issue in issues))

    def test_qonfirmer_scoped_endpoint_check_ignores_non_routing_file(self):
        util_file = self.workspace / "qodeyard" / "utils.py"
        util_file.write_text("def helper():\n    return 1\n", encoding="utf-8")
        contract = {"invariants": {"required_endpoints": [{"method": "get", "path": "/health"}]}}
        report = qonfirmer.run_qonfirmer_for_files(contract, self.workspace / "qodeyard", ["utils.py"])
        self.assertTrue(report.passed)
        self.assertEqual(report.violations, [])

    def test_inspection_verdict_enforces_exact_required_file_set_when_task_demands_it(self):
        (self.workspace / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (self.workspace / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (self.workspace / "planning" / "completion-criteria.v1.json").write_text(
            json.dumps({"required_files": ["index.html", "styles.css", "app.js"]}),
            encoding="utf-8",
        )
        (self.workspace / "planning" / "build-groups.v1.json").write_text(
            json.dumps({"briq_inventory": [], "items": []}),
            encoding="utf-8",
        )
        (self.workspace / "task").mkdir(parents=True, exist_ok=True)
        (self.workspace / "task" / "task-spec.v1.json").write_text(
            json.dumps({"clarified_task_body": "The project must contain exactly these files: index.html, styles.css, app.js"}),
            encoding="utf-8",
        )
        (self.workspace / "qodeyard" / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
        (self.workspace / "qodeyard" / "styles.css").write_text("body{}\n", encoding="utf-8")
        (self.workspace / "qodeyard" / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
        (self.workspace / "qodeyard" / "test.txt").write_text("extra\n", encoding="utf-8")

        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=self.workspace,
            cycle_num="1",
            overall_assessment="SUCCESS",
            validation_bundle={"status": "PASS", "issues": []},
            realization_bundle={
                "scope_summary": {"touched_scopes": ["scope-a"], "undeclared_touched_scopes": []},
                "confidence": "CONFIDENCE_HIGH",
                "unknowns": [],
                "evidence_status": "EVIDENCE_COMPLETE",
            },
            inspection_input={"status": "READY", "required_inputs": {}},
            cross_briq_warnings=[],
            failed_briq_suggestions=[],
        )
        exact_row = next(
            row for row in verdict["completion_criteria_results"]
            if row["criterion"] == "Required file set is exact (no undeclared extra deliverable files)."
        )
        self.assertEqual(exact_row["status"], "FAIL")
        self.assertIn("test.txt", exact_row["basis"]["extra_files"])
        self.assertNotEqual(verdict["status"], "SUCCESS")

    def test_repair_plan_includes_repair_escalation_recommendation(self):
        (self.workspace / "briq.d").mkdir(parents=True, exist_ok=True)
        (self.workspace / "briq.d" / "cyqle1_task.md").write_text(
            "Briq-Ref: briq-001\nBuild-Group: bg-core\n",
            encoding="utf-8",
        )
        (self.workspace / "planning" / "build-groups.v1.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "build_group_id": "bg-core",
                            "scope_id": "scope-core",
                            "component_refs": ["component-core"],
                            "briq_refs": ["briq-001"],
                        }
                    ],
                    "briq_inventory": [{"briq_ref": "briq-001"}],
                }
            ),
            encoding="utf-8",
        )
        plan = inspeqtor.build_repair_plan(
            worqspace_root=self.workspace,
            cycle_num="1",
            inspection_verdict={
                "completion_assessment": "Deterministic code defects block completion and require bounded repair.",
                "issues": [{"summary": "deterministic issue in app.js"}],
            },
            validation_bundle={
                "issues": [{"failure_kind": "blocking_code_failures", "severity": "error", "file": "app.js"}],
                "checks": [{"check_id": "qonfirmer", "status": "FAIL"}],
            },
            realization_bundle={},
            grouped_coherence={
                "group_summaries": [
                    {
                        "build_group_id": "bg-core",
                        "status": "FAIL",
                        "changed_files": ["app.js"],
                        "reported_files": ["app.js"],
                    }
                ],
                "undeclared_changed_files": [],
            },
            failed_briq_suggestions=[],
        )
        escalation = plan.get("repair_escalation", {})
        self.assertTrue(escalation.get("enabled", False))
        self.assertEqual(escalation.get("recommended_failure_class"), "exact_validator_violation")
        self.assertGreaterEqual(int(escalation.get("recommended_start_level", 0)), 3)


if __name__ == "__main__":
    unittest.main()
