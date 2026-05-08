import os
import sys
import tempfile
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORQER_DIR = ROOT / "worqer"
sys.path.insert(0, str(WORQER_DIR))

import inspeqtor  # noqa: E402


class InspeqtorResilienceTests(unittest.TestCase):
    def test_build_validation_bundle_captures_execution_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qodeyard").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            grouped = {
                "status": "PASS",
                "checks": [],
                "issues": [],
                "group_summaries": [],
                "touched_scope_ids": [],
                "touched_group_files": [],
                "undeclared_changed_files": [],
                "unassigned_briqs": [],
            }
            old_env = {
                "QONQ_GLOBAL_ITERATION_INDEX": os.environ.get("QONQ_GLOBAL_ITERATION_INDEX"),
                "QONQ_PASS_KIND": os.environ.get("QONQ_PASS_KIND"),
                "QONQ_BUILD_PASS_INDEX": os.environ.get("QONQ_BUILD_PASS_INDEX"),
                "QONQ_REPAIR_PASS_INDEX": os.environ.get("QONQ_REPAIR_PASS_INDEX"),
                "QONQ_REPAIRING_BUILD_PASS_INDEX": os.environ.get("QONQ_REPAIRING_BUILD_PASS_INDEX"),
                "QONQ_CYCLE_ESTIMATE_MODE": os.environ.get("QONQ_CYCLE_ESTIMATE_MODE"),
                "QONQ_ESTIMATED_BUILD_PASSES": os.environ.get("QONQ_ESTIMATED_BUILD_PASSES"),
                "QONQ_SCHEDULED_BUILD_PASS_TARGET": os.environ.get("QONQ_SCHEDULED_BUILD_PASS_TARGET"),
            }
            os.environ["QONQ_GLOBAL_ITERATION_INDEX"] = "9"
            os.environ["QONQ_PASS_KIND"] = "repair"
            os.environ["QONQ_BUILD_PASS_INDEX"] = "3"
            os.environ["QONQ_REPAIR_PASS_INDEX"] = "2"
            os.environ["QONQ_REPAIRING_BUILD_PASS_INDEX"] = "3"
            os.environ["QONQ_CYCLE_ESTIMATE_MODE"] = "scheduler"
            os.environ["QONQ_ESTIMATED_BUILD_PASSES"] = "5"
            os.environ["QONQ_SCHEDULED_BUILD_PASS_TARGET"] = "4"
            try:
                bundle = inspeqtor.build_validation_bundle(
                    root,
                    "1",
                    None,
                    None,
                    None,
                    grouped,
                    [],
                )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

            self.assertEqual(bundle["global_iteration_index"], 9)
            self.assertEqual(bundle["pass_kind"], "repair")
            self.assertEqual(bundle["build_pass_index"], 3)
            self.assertEqual(bundle["repair_pass_index"], 2)
            self.assertEqual(bundle["repairing_build_pass_index"], 3)
            self.assertEqual(bundle["cycle_estimate_mode"], "scheduler")
            self.assertEqual(bundle["estimated_build_passes"], 5)
            self.assertEqual(bundle["scheduled_build_pass_target"], 4)

    def test_merge_briq_changed_files_snapshots_targets_from_qodeyard(self):
        with tempfile.TemporaryDirectory() as tmp:
            qodeyard = Path(tmp) / "qodeyard"
            (qodeyard / "src").mkdir(parents=True, exist_ok=True)
            (qodeyard / "src" / "app.js").write_text("export const ok = true;\n", encoding="utf-8")
            merged = inspeqtor.merge_briq_changed_files(
                [],
                qodeyard,
                ["src/app.js"],
                fallback_limit=3,
            )
            self.assertIn(("src/app.js", "export const ok = true;\n"), merged)

    def test_build_inspection_verdict_marks_degraded_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "completion-criteria.v1.json").write_text("{}", encoding="utf-8")
            (root / "planning" / "build-groups.v1.json").write_text("{\"items\":[],\"briq_inventory\":[]}", encoding="utf-8")
            validation_bundle = {
                "status": "PASS",
                "issues": [],
                "validation_execution_mode": "STATIC_ONLY",
            }
            realization_bundle = {
                "confidence": "CONFIDENCE_MEDIUM",
                "evidence_status": "EVIDENCE_PARTIAL",
                "capability_mode": "MIXED_REASONING_EXECUTION",
                "scope_summary": {
                    "touched_scopes": ["scope.one"],
                    "undeclared_touched_scopes": [],
                },
                "unknowns": [],
            }
            inspection_input = {"status": "READY", "required_inputs": {}}
            failures = [{"substep": "tactical_review", "recoverable": True, "error": "timeout"}]
            verdict = inspeqtor.build_inspection_verdict(
                root,
                "1",
                "[SUCCESS]",
                validation_bundle,
                realization_bundle,
                inspection_input,
                [],
                [],
                inspection_substep_failures=failures,
            )
            self.assertEqual(verdict["inspection_integrity"], "DEGRADED")
            self.assertEqual(len(verdict["inspection_substep_failures"]), 1)
            self.assertTrue(any(item.get("source") == "inspection_runtime" for item in verdict["issues"]))

    def test_default_repair_plan_keeps_same_run_when_briqs_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "briq.d" / "cyqle1_feature.md").write_text("# briq\n", encoding="utf-8")
            plan = inspeqtor.default_repair_plan(
                root,
                "1",
                {"completion_assessment": "Repair needed."},
                "repair plan fallback",
            )
            self.assertTrue(plan["same_run_repair_eligible"])
            self.assertEqual(plan["next_lifecycle_transition"], "REPAIRING")
            self.assertIn("cyqle1_feature.md", plan["target_briq_files"])
            self.assertIn("repair_escalation", plan)
            self.assertTrue(plan["repair_escalation"].get("enabled", False))

    def test_build_repair_plan_keeps_same_run_for_file_level_deterministic_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-main",
                                "briq_refs": ["briq-001"],
                                "scope_id": "scope-main",
                                "component_refs": ["api"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-001"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_main.md").write_text(
                "Briq-Ref: briq-001\n# main briq\n",
                encoding="utf-8",
            )

            inspection_verdict = {
                "status": "FAILURE",
                "issues": [
                    {
                        "issue_id": "deterministic-001",
                        "severity": "error",
                        "source": "smoketest",
                        "file": "run.sh",
                        "summary": "POST /users failed with 422 due to query params instead of JSON body.",
                    }
                ],
                "completion_criteria_results": [],
                "completion_assessment": "Deterministic runtime mismatch.",
            }
            validation_bundle = {
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "file": "run.sh",
                        "files": ["main.py", "run.sh"],
                    }
                ],
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
            }
            grouped = {
                "group_summaries": [],
                "status": "FAIL",
                "checks": [],
                "issues": [],
                "undeclared_changed_files": [],
            }

            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {},
                grouped,
                [],
            )
            self.assertTrue(plan["same_run_repair_eligible"])
            self.assertEqual(plan["continuation_strategy"], "same_run")
            self.assertIn("cyqle1_main.md", plan["target_briq_files"])
            self.assertIn("run.sh", plan["target_files"])

    def test_build_repair_plan_uses_planned_file_ownership_for_runtime_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-main",
                                "briq_refs": ["briq-001"],
                                "scope_id": "scope-main",
                                "component_refs": ["api"],
                                "primary_files": ["main.py"],
                                "target_files": ["main.py", "app.post"],
                            },
                            {
                                "build_group_id": "bg-launch",
                                "briq_refs": ["briq-002"],
                                "scope_id": "scope-launch",
                                "component_refs": ["launch"],
                                "primary_files": ["requirements.txt"],
                                "target_files": ["requirements.txt", "run.sh"],
                            },
                        ],
                        "briq_inventory": [{"briq_ref": "briq-001"}, {"briq_ref": "briq-002"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_main.md").write_text("Briq-Ref: briq-001\n", encoding="utf-8")
            (root / "briq.d" / "cyqle1_launch.md").write_text("Briq-Ref: briq-002\n", encoding="utf-8")

            inspection_verdict = {
                "status": "FAILURE",
                "issues": [
                    {
                        "issue_id": "deterministic-001",
                        "severity": "error",
                        "source": "smoketest",
                        "file": "run.sh",
                        "summary": "POST /users failed with 422 due to missing body id.",
                    }
                ],
                "completion_criteria_results": [],
                "completion_assessment": "Deterministic runtime mismatch.",
            }
            validation_bundle = {
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "file": "run.sh",
                        "files": ["main.py", "run.sh"],
                    }
                ],
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
            }
            grouped = {
                "group_summaries": [],
                "status": "FAIL",
                "checks": [],
                "issues": [],
                "undeclared_changed_files": [],
            }

            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {},
                grouped,
                [],
            )
            self.assertIn("bg-main", plan["target_build_groups"])
            self.assertIn("bg-launch", plan["target_build_groups"])
            self.assertIn("cyqle1_main.md", plan["target_briq_files"])
            self.assertIn("cyqle1_launch.md", plan["target_briq_files"])

    def test_build_repair_plan_same_fix_signature_ignores_cycle_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "verdict").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-main",
                                "briq_refs": ["briq-001"],
                                "scope_id": "scope-main",
                                "component_refs": ["api"],
                                "primary_files": ["main.py"],
                                "target_files": ["main.py"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-001"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_main.md").write_text("Briq-Ref: briq-001\n", encoding="utf-8")
            (root / "briq.d" / "cyqle2_main.md").write_text("Briq-Ref: briq-001\n", encoding="utf-8")

            inspection_verdict = {
                "status": "FAILURE",
                "issues": [
                    {
                        "issue_id": "deterministic-001",
                        "severity": "error",
                        "source": "smoketest",
                        "file": "main.py",
                        "summary": "POST /users failed with 422 due to missing body id.",
                    }
                ],
                "completion_criteria_results": [],
                "completion_assessment": "Deterministic runtime mismatch.",
            }
            validation_bundle = {
                "issues": [{"severity": "error", "source": "smoketest", "file": "main.py", "files": ["main.py"]}],
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
            }
            grouped = {
                "group_summaries": [],
                "status": "FAIL",
                "checks": [],
                "issues": [],
                "undeclared_changed_files": [],
            }

            first = inspeqtor.build_repair_plan(root, "1", inspection_verdict, validation_bundle, {}, grouped, [])
            (root / "verdict" / "repair-plan.v1.json").write_text(json.dumps(first), encoding="utf-8")
            second = inspeqtor.build_repair_plan(root, "2", inspection_verdict, validation_bundle, {}, grouped, [])
            self.assertEqual(first["repair_signature"], second["repair_signature"])
            self.assertEqual(second["same_fix_repeat_count"], 2)

    def test_build_repair_plan_infers_main_py_from_run_sh_smoketest_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard" / "run.sh").write_text(
                "#!/usr/bin/env bash\npython -m uvicorn main:app --reload --port $PORT\n",
                encoding="utf-8",
            )
            (root / "qodeyard" / "main.py").write_text(
                "from fastapi import FastAPI\napp = FastAPI()\n",
                encoding="utf-8",
            )
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-main",
                                "briq_refs": ["briq-001"],
                                "scope_id": "scope-main",
                                "component_refs": ["api"],
                                "primary_files": ["main.py"],
                                "target_files": ["main.py"],
                            },
                            {
                                "build_group_id": "bg-launch",
                                "briq_refs": ["briq-002"],
                                "scope_id": "scope-launch",
                                "component_refs": ["launch"],
                                "primary_files": ["run.sh"],
                                "target_files": ["run.sh"],
                            },
                        ],
                        "briq_inventory": [{"briq_ref": "briq-001"}, {"briq_ref": "briq-002"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_main.md").write_text("Briq-Ref: briq-001\n", encoding="utf-8")
            (root / "briq.d" / "cyqle1_launch.md").write_text("Briq-Ref: briq-002\n", encoding="utf-8")

            inspection_verdict = {
                "status": "FAILURE",
                "issues": [
                    {
                        "issue_id": "deterministic-001",
                        "severity": "error",
                        "source": "smoketest",
                        "file": "run.sh",
                        "summary": "POST /users failed: status=422 body=...",
                    }
                ],
                "completion_criteria_results": [],
                "completion_assessment": "Deterministic runtime mismatch.",
            }
            validation_bundle = {
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "file": "run.sh",
                        "files": ["run.sh"],
                        "related_files": ["run.sh"],
                        "check_type": "shell:run_sh_behavior",
                        "command": "/usr/bin/bash run.sh",
                    }
                ],
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
            }
            grouped = {
                "group_summaries": [],
                "status": "FAIL",
                "checks": [],
                "issues": [],
                "undeclared_changed_files": [],
            }

            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {},
                grouped,
                [],
            )
            self.assertIn("main.py", plan["target_files"])
            self.assertIn("bg-main", plan["target_build_groups"])
            self.assertIn("cyqle1_main.md", plan["target_briq_files"])

    def test_detect_validation_execution_mode_matrix(self):
        smoke_none = {"executed_count": 0, "static_count": 0}
        smoke_static = {"executed_count": 0, "static_count": 2}
        smoke_executed = {"executed_count": 1, "static_count": 0}
        self.assertEqual(
            inspeqtor.detect_validation_execution_mode(None, None, smoke_none),
            "NONE",
        )
        self.assertEqual(
            inspeqtor.detect_validation_execution_mode({"ok": True}, None, smoke_static),
            "STATIC_ONLY",  # static deterministic checks remain static-only
        )
        self.assertEqual(
            inspeqtor.detect_validation_execution_mode(None, None, smoke_static),
            "STATIC_ONLY",
        )
        self.assertEqual(
            inspeqtor.detect_validation_execution_mode(None, None, smoke_executed),
            "EXECUTED",
        )
        self.assertEqual(
            inspeqtor.detect_validation_execution_mode({"ok": True}, None, smoke_executed),
            "MIXED",
        )

    def test_validation_bundle_integrates_smoketest_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qodeyard").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard" / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "reqap.d" / "cyqle1").mkdir(parents=True, exist_ok=True)
            (root / "reqap.d" / "cyqle1" / "cyqle1_smoketest.v1.json").write_text("{}", encoding="utf-8")
            grouped = {
                "status": "PASS",
                "checks": [],
                "issues": [],
                "group_summaries": [],
                "touched_scope_ids": [],
                "touched_group_files": [],
                "undeclared_changed_files": [],
                "unassigned_briqs": [],
            }
            smoke_report = {
                "enabled": True,
                "mode": "scoped",
                "overall_status": "FAIL",
                "executed_count": 1,
                "static_count": 0,
                "commands_executed": 1,
                "commands_skipped": 0,
                "failed": 1,
                "warnings": 0,
                "errors": 0,
                "skipped": 0,
                "adapters_triggered": ["python"],
                "results": [
                    {
                        "adapter": "python",
                        "name": "python:command",
                        "status": "FAIL",
                        "executed": True,
                        "execution_kind": "executed",
                        "message": "pytest failed",
                        "file": "app.py",
                        "files": ["app.py"],
                        "related_files": ["app.py", "utils.py"],
                        "scope": "scope.api",
                        "command": "python -m pytest -q",
                        "severity": "error",
                        "exit_code": 1,
                    }
                ],
            }
            bundle = inspeqtor.build_validation_bundle(
                root,
                "1",
                None,
                None,
                smoke_report,
                grouped,
                ["app.py"],
            )
            self.assertEqual(bundle["validation_execution_mode"], "EXECUTED")
            smoke_checks = [item for item in bundle["checks"] if item.get("check_id") == "smoketest"]
            self.assertEqual(len(smoke_checks), 1)
            smoke_issues = [item for item in bundle["issues"] if item.get("source") == "smoketest"]
            self.assertEqual(len(smoke_issues), 1)
            self.assertEqual(smoke_issues[0]["related_files"], ["app.py", "utils.py"])
            self.assertEqual(smoke_issues[0]["execution_kind"], "executed")
            self.assertEqual(smoke_issues[0]["command"], "python -m pytest -q")
            self.assertIn("reqap.d/cyqle1/cyqle1_smoketest.v1.json", bundle["evidence_refs"])

    def test_realization_bundle_uses_smoketest_behavior_when_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(json.dumps({"items": []}), encoding="utf-8")
            validation_bundle = {
                "status": "PASS",
                "validation_execution_mode": "EXECUTED",
                "checks": [{"check_id": "smoketest", "status": "PASS"}],
                "coverage": {"non_python_files": []},
                "smoketest": {
                    "executed_count": 1,
                    "static_count": 1,
                    "results": [
                        {
                            "adapter": "python",
                            "name": "python:command",
                            "status": "PASS",
                            "execution_kind": "executed",
                            "related_files": ["app.py"],
                        },
                        {
                            "adapter": "python",
                            "name": "python:py_compile",
                            "status": "PASS",
                            "execution_kind": "static",
                            "related_files": ["app.py"],
                        }
                    ],
                },
            }
            grouped = {
                "group_summaries": [],
                "undeclared_changed_files": [],
                "touched_scope_ids": [],
            }
            bundle = inspeqtor.build_realization_bundle(
                root,
                "1",
                validation_bundle,
                validation_bundle.get("smoketest"),
                grouped,
                [],
                [],
            )
            ids = [item.get("behavior_id") for item in bundle["behavioral_reality"]["observed_behaviors"]]
            self.assertTrue(any(str(item).startswith("smoketest:") for item in ids))
            unresolved = [item.get("behavior_id") for item in bundle["behavioral_reality"]["unverified_behaviors"]]
            self.assertNotIn("project_test_runner", unresolved)

    def test_repair_plan_targets_related_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "briq.d" / "cyqle1_api.md").write_text("Briq-Ref: BRIQ-API\n", encoding="utf-8")
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "group.api",
                                "scope_id": "scope.api",
                                "component_refs": ["component.api"],
                                "briq_refs": ["BRIQ-API"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "BRIQ-API"}],
                    }
                ),
                encoding="utf-8",
            )
            grouped = {
                "group_summaries": [
                    {
                        "build_group_id": "group.api",
                        "scope_id": "scope.api",
                        "planned_components": ["component.api"],
                        "changed_files": ["src/api.py"],
                        "reported_files": ["src/api.py"],
                        "status": "PASS",
                    }
                ],
                "undeclared_changed_files": [],
            }
            validation_bundle = {
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
                "issues": [
                    {
                        "source": "smoketest",
                        "severity": "error",
                        "message": "Smoke failed",
                        "related_files": ["src/api.py"],
                        "files": ["src/api.py"],
                    }
                ],
            }
            inspection_verdict = {"completion_assessment": "Repair required."}
            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {"scope_summary": {}},
                grouped,
                [],
            )
            self.assertIn("group.api", plan["target_build_groups"])
            self.assertIn("scope.api", plan["target_scopes"])
            self.assertIn("cyqle1_api.md", plan["target_briq_files"])

    def test_repair_plan_carries_deterministic_issue_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "briq.d" / "cyqle1_ui.md").write_text("Briq-Ref: BRIQ-UI\n", encoding="utf-8")
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "group.ui",
                                "scope_id": "scope.ui",
                                "component_refs": ["component.ui"],
                                "briq_refs": ["BRIQ-UI"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "BRIQ-UI"}],
                    }
                ),
                encoding="utf-8",
            )
            grouped = {
                "group_summaries": [
                    {
                        "build_group_id": "group.ui",
                        "scope_id": "scope.ui",
                        "planned_components": ["component.ui"],
                        "changed_files": ["index.html", "app.js"],
                        "reported_files": ["index.html", "app.js"],
                        "status": "PARTIAL",
                    }
                ],
                "undeclared_changed_files": [],
            }
            validation_bundle = {"checks": [], "issues": []}
            inspection_verdict = {
                "completion_assessment": "Repair required.",
                "issues": [
                    {
                        "issue_id": "deterministic-001",
                        "summary": "JavaScript references missing DOM ids: chat-section, join-section in app.js and index.html",
                        "severity": "error",
                        "source": "frontend_contract",
                    }
                ],
            }
            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {"scope_summary": {}},
                grouped,
                [],
            )
            self.assertIn("group.ui", plan["target_build_groups"])
            self.assertIn("cyqle1_ui.md", plan["target_briq_files"])
            self.assertTrue(
                any(action.startswith("resolve deterministic issue: JavaScript references missing DOM ids") for action in plan["required_actions"])
            )

    def test_passed_file_lock_state_locks_run_sh_when_main_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qodeyard").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard" / "main.py").write_text("print('bad')\n", encoding="utf-8")
            (root / "qodeyard" / "run.sh").write_text(
                "python -m uvicorn main:app --reload --port $PORT\n",
                encoding="utf-8",
            )
            criteria = [
                {
                    "criterion": "Required deliverable files exist in qodeyard.",
                    "status": "PASS",
                    "basis": {
                        "required_files": ["main.py", "run.sh"],
                        "missing_required_files": [],
                    },
                }
            ]
            validation_bundle = {
                "issues": [
                    {
                        "severity": "error",
                        "failure_kind": "code_behavior_mismatch",
                        "file": "main.py",
                        "message": "POST /users still requires id",
                    }
                ]
            }
            state = inspeqtor.build_passed_file_lock_state(
                root,
                "1",
                validation_bundle,
                criteria,
                ["main.py", "run.sh"],
            )
            self.assertIn("run.sh", state["locked_files"])
            self.assertIn("main.py", state["hard_failure_files"])
            file_rows = {item["path"]: item for item in state["files"]}
            self.assertEqual(file_rows["run.sh"]["status"], "PASS")
            self.assertEqual(file_rows["main.py"]["status"], "FAIL")

    def test_passed_file_lock_state_infers_runtime_source_from_run_sh_behavior_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qodeyard" / "__pycache__").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard" / "main.py").write_text("print('bad')\n", encoding="utf-8")
            (root / "qodeyard" / "run.sh").write_text(
                "#!/bin/sh\npython -m uvicorn main:app --reload --port $PORT\n",
                encoding="utf-8",
            )
            (root / "qodeyard" / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"noise")
            criteria = [
                {
                    "criterion": "Required deliverable files exist in qodeyard.",
                    "status": "PASS",
                    "basis": {
                        "required_files": ["main.py", "run.sh"],
                        "missing_required_files": [],
                    },
                }
            ]
            validation_bundle = {
                "issues": [],
                "smoketest": {
                    "results": [
                        {
                            "adapter": "shell",
                            "name": "shell:run_sh_behavior",
                            "status": "FAIL",
                            "severity": "error",
                            "execution_kind": "http_probe",
                            "failure_kind": "code_behavior_mismatch",
                            "file": "run.sh",
                            "files": ["run.sh"],
                            "related_files": ["run.sh"],
                            "command": "/bin/sh run.sh",
                            "message": "POST /users unexpected fields",
                        }
                    ]
                },
            }

            state = inspeqtor.build_passed_file_lock_state(
                root,
                "1",
                validation_bundle,
                criteria,
                ["main.py", "run.sh"],
            )

            self.assertIn("main.py", state["hard_failure_files"])
            self.assertIn("run.sh", state["hard_failure_files"])
            self.assertNotIn("run.sh", state["locked_files"])
            self.assertNotIn("__pycache__/main.cpython-311.pyc", state["locked_files"])
            file_rows = {item["path"]: item for item in state["files"]}
            self.assertEqual(file_rows["main.py"]["status"], "FAIL")
            self.assertEqual(file_rows["run.sh"]["status"], "FAIL")
            self.assertNotIn("__pycache__/main.cpython-311.pyc", file_rows)

    def test_repair_plan_excludes_locked_file_not_in_new_hard_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "verdict").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-api",
                                "scope_id": "scope-api",
                                "component_refs": ["component-api"],
                                "briq_refs": ["briq-api"],
                                "target_files": ["main.py", "run.sh"],
                                "primary_files": ["main.py", "run.sh"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-api"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_api.md").write_text("Briq-Ref: briq-api\n", encoding="utf-8")
            lock_payload = {
                "schema_version": "passed-file-locks.v1",
                "files": [
                    {"path": "run.sh", "locked": True, "content_sha256": "abc"},
                    {"path": "main.py", "locked": False, "content_sha256": "def"},
                ],
                "locked_files": ["run.sh"],
                "hard_failure_files": ["main.py"],
                "unlocked_files": [],
            }
            (root / "verdict" / "passed-file-locks.v1.json").write_text(
                json.dumps(lock_payload),
                encoding="utf-8",
            )
            inspection_verdict = {
                "completion_assessment": "Repair required.",
                "completion_criteria_results": [],
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "summary": "POST /users failed",
                        "file": "main.py",
                    }
                ],
            }
            validation_bundle = {
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "file": "main.py",
                        "files": ["main.py", "run.sh"],
                    }
                ],
            }
            grouped = {
                "group_summaries": [
                    {
                        "build_group_id": "bg-api",
                        "scope_id": "scope-api",
                        "status": "FAIL",
                        "changed_files": ["main.py", "run.sh"],
                        "reported_files": ["main.py", "run.sh"],
                    }
                ],
                "undeclared_changed_files": [],
            }
            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {},
                grouped,
                [],
            )
            self.assertIn("main.py", plan["target_files"])
            self.assertNotIn("run.sh", plan["target_files"])
            excluded = {item["path"] for item in plan.get("locked_files_excluded", [])}
            self.assertIn("run.sh", excluded)

    def test_repair_plan_can_reinclude_locked_file_when_file_itself_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "verdict").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-launch",
                                "scope_id": "scope-launch",
                                "component_refs": ["component-launch"],
                                "briq_refs": ["briq-launch"],
                                "target_files": ["run.sh"],
                                "primary_files": ["run.sh"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-launch"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_launch.md").write_text("Briq-Ref: briq-launch\n", encoding="utf-8")
            lock_payload = {
                "schema_version": "passed-file-locks.v1",
                "files": [{"path": "run.sh", "locked": True, "content_sha256": "abc"}],
                "locked_files": ["run.sh"],
                "hard_failure_files": ["run.sh"],
                "unlocked_files": [{"path": "run.sh", "reason": "hard_failure_now_implicates_file"}],
            }
            (root / "verdict" / "passed-file-locks.v1.json").write_text(
                json.dumps(lock_payload),
                encoding="utf-8",
            )
            inspection_verdict = {
                "completion_assessment": "Repair required.",
                "completion_criteria_results": [],
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "summary": "run.sh missing --port value",
                        "file": "run.sh",
                    }
                ],
            }
            validation_bundle = {
                "checks": [{"check_id": "smoketest", "status": "FAIL"}],
                "issues": [
                    {
                        "severity": "error",
                        "source": "smoketest",
                        "failure_kind": "shellscript_contract_mismatch",
                        "file": "run.sh",
                        "files": ["run.sh"],
                    }
                ],
            }
            grouped = {
                "group_summaries": [
                    {
                        "build_group_id": "bg-launch",
                        "scope_id": "scope-launch",
                        "status": "FAIL",
                        "changed_files": ["run.sh"],
                        "reported_files": ["run.sh"],
                    }
                ],
                "undeclared_changed_files": [],
            }
            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {},
                grouped,
                [],
            )
            self.assertIn("run.sh", plan["target_files"])
            excluded = {item["path"] for item in plan.get("locked_files_excluded", [])}
            self.assertNotIn("run.sh", excluded)

    def test_frontend_repair_plan_keeps_locked_html_css_out_of_app_js_fix_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "verdict").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-web",
                                "scope_id": "scope-web",
                                "component_refs": ["component-web"],
                                "briq_refs": ["briq-web"],
                                "target_files": ["index.html", "styles.css", "app.js"],
                                "primary_files": ["index.html", "styles.css", "app.js"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-web"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_web.md").write_text("Briq-Ref: briq-web\n", encoding="utf-8")
            (root / "verdict" / "passed-file-locks.v1.json").write_text(
                json.dumps(
                    {
                        "schema_version": "passed-file-locks.v1",
                        "files": [
                            {"path": "index.html", "locked": True},
                            {"path": "styles.css", "locked": True},
                            {"path": "app.js", "locked": False},
                        ],
                        "locked_files": ["index.html", "styles.css"],
                        "hard_failure_files": ["app.js"],
                        "unlocked_files": [],
                    }
                ),
                encoding="utf-8",
            )
            inspection_verdict = {
                "completion_assessment": "Repair required.",
                "completion_criteria_results": [],
                "issues": [
                    {
                        "severity": "error",
                        "source": "frontend_contract",
                        "summary": "app.js uses wrong localStorage key",
                        "file": "app.js",
                    }
                ],
            }
            validation_bundle = {
                "checks": [{"check_id": "group_scope_integration", "status": "FAIL"}],
                "issues": [
                    {
                        "severity": "error",
                        "source": "frontend_contract",
                        "file": "app.js",
                        "files": ["app.js", "index.html", "styles.css"],
                    }
                ],
            }
            grouped = {
                "group_summaries": [
                    {
                        "build_group_id": "bg-web",
                        "scope_id": "scope-web",
                        "status": "FAIL",
                        "changed_files": ["index.html", "styles.css", "app.js"],
                        "reported_files": ["index.html", "styles.css", "app.js"],
                    }
                ],
                "undeclared_changed_files": [],
            }
            plan = inspeqtor.build_repair_plan(
                root,
                "1",
                inspection_verdict,
                validation_bundle,
                {},
                grouped,
                [],
            )
            self.assertIn("app.js", plan["target_files"])
            self.assertNotIn("index.html", plan["target_files"])
            self.assertNotIn("styles.css", plan["target_files"])

    def test_lock_state_detects_locked_file_content_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qodeyard").mkdir(parents=True, exist_ok=True)
            (root / "qodeyard" / "run.sh").write_text(
                "python -m uvicorn main:app --reload --port $PORT\n",
                encoding="utf-8",
            )
            criteria = [
                {
                    "criterion": "Required deliverable files exist in qodeyard.",
                    "status": "PASS",
                    "basis": {
                        "required_files": ["run.sh"],
                        "missing_required_files": [],
                    },
                }
            ]
            first = inspeqtor.build_passed_file_lock_state(
                root,
                "1",
                {"issues": []},
                criteria,
                ["run.sh"],
            )
            (root / "verdict").mkdir(parents=True, exist_ok=True)
            (root / "verdict" / "passed-file-locks.v1.json").write_text(
                json.dumps(first),
                encoding="utf-8",
            )
            (root / "qodeyard" / "run.sh").write_text(
                "PORT=$(python -c \"from main import PORT; print(PORT)\")\npython -m uvicorn main:app --reload --port \"$PORT\"\n",
                encoding="utf-8",
            )
            second = inspeqtor.build_passed_file_lock_state(
                root,
                "2",
                {"issues": []},
                criteria,
                ["run.sh"],
            )
            self.assertTrue(second["repair_scope_violations"])
            self.assertEqual(second["repair_scope_violations"][0]["path"], "run.sh")


if __name__ == "__main__":
    unittest.main()
