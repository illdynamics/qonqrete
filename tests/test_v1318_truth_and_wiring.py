import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))

import inspeqtor  # noqa: E402
import lib_ai  # noqa: E402
import qrystallizer  # noqa: E402


class TruthAndWiringRegressionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="qonq_v1318_")
        self.workspace = Path(self._tmp)
        (self.workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
        (self.workspace / "planning").mkdir(parents=True, exist_ok=True)
        (self.workspace / "build" / "groups" / "bg-web").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_common_planning(self):
        (self.workspace / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (self.workspace / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (self.workspace / "planning" / "completion-criteria.v1.json").write_text(
            json.dumps({"required_files": ["index.html", "styles.css", "app.js"]}),
            encoding="utf-8",
        )
        (self.workspace / "planning" / "build-groups.v1.json").write_text(
            json.dumps(
                {
                    "briq_inventory": [{"briq_ref": "briq-001"}],
                    "items": [
                        {
                            "build_group_id": "bg-web",
                            "scope_id": "scope-web",
                            "briq_refs": ["briq-001"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.workspace / "build" / "groups" / "bg-web" / "changed-files.v1.json").write_text(
            json.dumps(
                {
                    "changed_files": [
                        {"path": "index.html", "change_type": "modified_or_created", "in_intended_scope": True},
                        {"path": "styles.css", "change_type": "modified_or_created", "in_intended_scope": True},
                        {"path": "app.js", "change_type": "modified_or_created", "in_intended_scope": True},
                    ]
                }
            ),
            encoding="utf-8",
        )
        for rel, body in {
            "index.html": "<!doctype html><html><body><main id=\"app\"></main><script src=\"app.js\"></script></body></html>\n",
            "styles.css": "body { font-family: sans-serif; }\n",
            "app.js": "document.getElementById('app').textContent = 'ok';\n",
        }.items():
            (self.workspace / "qodeyard" / rel).write_text(body, encoding="utf-8")

    def test_realization_bundle_counts_http_probe_as_executed_evidence(self):
        self._write_common_planning()
        validation_bundle = {
            "status": "PASS",
            "validation_execution_mode": "MIXED",
            "coverage": {"python_files": [], "non_python_files": []},
            "checks": [{"check_id": "smoketest", "status": "PASS"}],
        }
        grouped = {
            "group_summaries": [
                {
                    "build_group_id": "bg-web",
                    "scope_id": "scope-web",
                    "changed_files": ["index.html", "styles.css", "app.js"],
                    "reported_files": ["index.html", "styles.css", "app.js"],
                    "write_strategy": "staged_atomic_per_attempt",
                }
            ],
            "undeclared_changed_files": [],
            "touched_scope_ids": ["scope-web"],
        }
        smoke_report = {
            "enabled": True,
            "overall_status": "PASS",
            "results": [
                {
                    "adapter": "html_css",
                    "name": "html:http_probe",
                    "status": "PASS",
                    "executed": True,
                    "execution_kind": "http_probe",
                    "related_files": ["index.html", "app.js"],
                }
            ],
        }
        bundle = inspeqtor.build_realization_bundle(
            self.workspace,
            "1",
            validation_bundle,
            smoke_report,
            grouped,
            ["index.html", "styles.css", "app.js"],
            [],
        )
        self.assertEqual(bundle["evidence_status"], "EVIDENCE_COMPLETE")
        observed_ids = {item["behavior_id"] for item in bundle["behavioral_reality"]["observed_behaviors"]}
        self.assertIn("smoketest:html_css:html:http_probe", observed_ids)

    def test_realization_bundle_allows_warnings_only_validation_to_complete(self):
        self._write_common_planning()
        validation_bundle = {
            "status": "PARTIAL",
            "validation_execution_mode": "MIXED",
            "coverage": {"python_files": ["main.py"], "non_python_files": []},
            "checks": [{"check_id": "qualification", "status": "PARTIAL"}],
            "issues": [
                {
                    "severity": "warning",
                    "message": "shfmt suggests formatting changes",
                }
            ],
        }
        grouped = {
            "group_summaries": [
                {
                    "build_group_id": "bg-web",
                    "scope_id": "scope-web",
                    "changed_files": ["index.html", "styles.css", "app.js"],
                    "reported_files": ["index.html", "styles.css", "app.js"],
                    "write_strategy": "staged_atomic_per_attempt",
                }
            ],
            "undeclared_changed_files": [],
            "touched_scope_ids": ["scope-web"],
        }
        smoke_report = {
            "enabled": True,
            "overall_status": "PASS",
            "results": [
                {
                    "adapter": "python",
                    "name": "python:fastapi_boot",
                    "status": "PASS",
                    "executed": True,
                    "execution_kind": "process_boot",
                    "related_files": ["main.py"],
                }
            ],
        }
        bundle = inspeqtor.build_realization_bundle(
            self.workspace,
            "1",
            validation_bundle,
            smoke_report,
            grouped,
            ["index.html", "styles.css", "app.js"],
            [],
        )
        self.assertEqual(bundle["evidence_status"], "EVIDENCE_COMPLETE")

    def test_inspection_verdict_marks_success_with_limited_coverage_when_hard_gates_pass(self):
        self._write_common_planning()
        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=self.workspace,
            cycle_num="1",
            overall_assessment="SUCCESS",
            validation_bundle={"status": "PASS", "issues": [], "validation_execution_mode": "STATIC_ONLY"},
            realization_bundle={
                "scope_summary": {"touched_scopes": ["scope-web"], "undeclared_touched_scopes": []},
                "confidence": "CONFIDENCE_MEDIUM",
                "unknowns": [],
                "evidence_status": "EVIDENCE_PARTIAL",
            },
            inspection_input={"status": "READY", "required_inputs": {}},
            cross_briq_warnings=[],
            failed_briq_suggestions=[],
        )
        self.assertEqual(verdict["status"], "SUCCESS")
        self.assertTrue(verdict["task_completed"])
        self.assertEqual(verdict["task_outcome"], "PASS")
        self.assertEqual(verdict["hard_gate_status"], "PASS")
        self.assertEqual(verdict["validation_coverage"], "LIMITED")
        self.assertFalse(verdict["repair_required"])

    def test_audit_payload_records_resolved_provider_and_model(self):
        old_workspace = os.environ.get("QONQ_WORKSPACE")
        try:
            os.environ["QONQ_WORKSPACE"] = str(self.workspace)
            response = lib_ai.run_ai_completion(
                provider="dry-run",
                model="qwen3-coder-480b-a35b-instruct-turbo",
                prompt="tiny",
                prompt_sections=[
                    {
                        "label": "core",
                        "content": "hello",
                        "required": True,
                        "loss_policy": "preserve",
                    }
                ],
                agent_name="inspeqtor",
            )
            self.assertIn("[DRY RUN]", response)
            audits = sorted((self.workspace / "audit" / "ai_payloads").glob("*.json"))
            self.assertTrue(audits)
            payload = json.loads(audits[-1].read_text(encoding="utf-8"))
            self.assertEqual(payload["resolved_provider"], "dry-run")
            self.assertEqual(payload["resolved_model"], "qwen3-coder-480b-a35b-instruct-turbo")
        finally:
            if old_workspace is None:
                os.environ.pop("QONQ_WORKSPACE", None)
            else:
                os.environ["QONQ_WORKSPACE"] = old_workspace

    def test_primary_agent_bindings_resolve_to_venice_deepseek_v32(self):
        config = {
            "agents": {
                "qrystallizer": {"provider": "venice", "model": "deepseek-v3.2"},
                "instruqtor": {"provider": "venice", "model": "deepseek-v3.2"},
                "construqtor": {"provider": "venice", "model": "deepseek-v3.2"},
                "inspeqtor": {"provider": "venice", "model": "deepseek-v3.2"},
            }
        }
        binding = qrystallizer.resolve_qrystallizer_ai_binding(config)
        self.assertEqual((binding["provider"], binding["model"]), ("venice", "deepseek-v3.2"))
        for agent in ("instruqtor", "construqtor", "inspeqtor"):
            self.assertEqual(
                lib_ai.get_agent_ai_params(config, agent, "openai", "gpt-4o"),
                ("venice", "deepseek-v3.2"),
            )

    def test_batched_review_prompt_marks_authoritative_truncation_metadata(self):
        prompt = inspeqtor.build_batched_review_prompt(
            [
                {
                    "name": "cyqle1_briq001",
                    "content": "Implement app.js",
                    "changed": [("app.js", "x" * 9001)],
                }
            ],
            six_shooter_context=None,
        )
        self.assertIn("evidence=authoritative_final_file", prompt)
        self.assertIn("snippet_truncated=true", prompt)
        self.assertIn("snippet_truncated=true` means prompt clipping only", prompt)

    def test_default_binding_fallbacks_use_deepseek_v32(self):
        binding = qrystallizer.resolve_qrystallizer_ai_binding({})
        self.assertEqual(binding["provider"], "venice")
        self.assertEqual(binding["model"], "deepseek-v3.2")
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.yaml"
            cfg_path.write_text("agents: {}\n", encoding="utf-8")
            loaded = inspeqtor.load_inspeqtor_config(cfg_path)
            self.assertEqual(loaded["provider"], "venice")
            self.assertEqual(loaded["model"], "deepseek-v3.2")

    def test_normalize_review_result_clears_stale_truncation_claims(self):
        assessment, summary, issues = inspeqtor.normalize_review_result(
            "[FAILURE]",
            "app.js appears truncated and incomplete.",
            "- app.js appears truncated and incomplete.",
            [("app.js", "const ok = true;\nconsole.log(ok);\n")],
        )
        self.assertEqual(assessment, "[SUCCESS]")
        self.assertIn("Deterministic qodeyard evidence confirmed", summary)
        self.assertEqual(issues, "None")

    def test_verdict_prefers_deterministic_success_over_advisory_briq_failures(self):
        self._write_common_planning()
        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=self.workspace,
            cycle_num="1",
            overall_assessment="[FAILURE]",
            validation_bundle={"status": "PASS", "issues": [], "validation_execution_mode": "MIXED"},
            realization_bundle={
                "scope_summary": {"touched_scopes": ["scope-web"], "undeclared_touched_scopes": []},
                "confidence": "CONFIDENCE_HIGH",
                "unknowns": [],
                "evidence_status": "EVIDENCE_COMPLETE",
            },
            inspection_input={"status": "READY", "required_inputs": {}},
            cross_briq_warnings=[],
            failed_briq_suggestions=[
                {"briq": "briq-001", "assessment": "[FAILURE]", "suggestions": "stale concern"}
            ],
        )
        self.assertEqual(verdict["status"], "SUCCESS")
        briq_issues = [item for item in verdict["issues"] if item.get("source") == "briq_review"]
        self.assertTrue(briq_issues)
        self.assertTrue(all(item.get("severity") == "info" for item in briq_issues))
        self.assertEqual(verdict["unresolved_issues"], [])


if __name__ == "__main__":
    unittest.main()
