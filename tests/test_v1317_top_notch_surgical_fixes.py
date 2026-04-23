import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))

import construqtor  # noqa: E402
import inspeqtor  # noqa: E402
import instruqtor  # noqa: E402
import lib_ai  # noqa: E402
import lib_qrane  # noqa: E402
import qrane  # noqa: E402
import qrystallizer  # noqa: E402


class LibQraneFixTests(unittest.TestCase):
    def test_parse_changed_files_filters_non_path_backticks(self):
        changed_md = (
            "- `app/main.py`\n"
            "- `mode:hybrid`\n"
            "- `scope-id`\n"
            "- `0.00002`\n"
            "- `Dockerfile`\n"
            "- `styles.css`\n"
        )
        parsed = lib_qrane.parse_changed_files(changed_md)
        self.assertIn("app/main.py", parsed)
        self.assertIn("styles.css", parsed)
        self.assertIn("Dockerfile", parsed)
        self.assertNotIn("mode:hybrid", parsed)
        self.assertNotIn("scope-id", parsed)
        self.assertNotIn("0.00002", parsed)

    def test_determine_evidence_status_returns_complete_when_artifacts_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "exeq.d").mkdir(parents=True, exist_ok=True)
            (root / "validation").mkdir(parents=True, exist_ok=True)
            (root / "verdict").mkdir(parents=True, exist_ok=True)
            (root / "realization").mkdir(parents=True, exist_ok=True)
            (root / "reqap.d").mkdir(parents=True, exist_ok=True)

            (root / "exeq.d" / "cyqle1_summary.md").write_text("summary\n", encoding="utf-8")
            (root / "exeq.d" / "cyqle1_changed.md").write_text("`app.py`\n", encoding="utf-8")
            (root / "validation" / "validation-bundle.v1.json").write_text(
                json.dumps({"status": "PASS"}), encoding="utf-8"
            )
            (root / "verdict" / "inspection-verdict.v1.json").write_text(
                json.dumps({"status": "SUCCESS"}), encoding="utf-8"
            )
            (root / "realization" / "realization-bundle.v1.json").write_text(
                json.dumps({"status": "PASS"}), encoding="utf-8"
            )

            self.assertEqual(lib_qrane.determine_evidence_status(root), "EVIDENCE_COMPLETE")


class LibAiWiringFixTests(unittest.TestCase):
    def test_get_agent_ai_params_defaults_blank_venice_model(self):
        config = {"agents": {"instruqtor": {"provider": "venice", "model": ""}}}
        provider, model = lib_ai.get_agent_ai_params(
            config,
            "instruqtor",
            "venice",
            "qwen3-coder-480b-a35b-instruct-turbo",
        )
        self.assertEqual(provider, "venice")
        self.assertEqual(model, "qwen3-coder-480b-a35b-instruct-turbo")

    def test_dispatch_openai_compatible_rejects_blank_venice_model(self):
        with self.assertRaises(ValueError):
            lib_ai._dispatch_openai_compatible(  # noqa: SLF001
                provider="venice",
                model="",
                messages=[{"role": "user", "content": "hello"}],
                output_tokens=16,
                timeout=5,
                tools=None,
                config={},
                agent_name="instruqtor",
            )


class QraneProviderDefaultFixTests(unittest.TestCase):
    def test_resolve_construqtor_provider_defaults_to_venice(self):
        self.assertEqual(qrane.resolve_construqtor_provider({}), "venice")
        self.assertEqual(
            qrane.resolve_construqtor_provider({"construqtor": {"provider": "VENICE"}}),
            "venice",
        )


class QrystallizerWiringFixTests(unittest.TestCase):
    def test_qrystallizer_ai_binding_is_recorded_in_task_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            config = {
                "agents": {
                    "qrystallizer": {
                        "provider": "venice",
                        "model": "qwen3-coder-480b-a35b-instruct-turbo",
                    }
                }
            }
            (workspace / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
            binding = qrystallizer.resolve_qrystallizer_ai_binding(config)
            task_spec, clarification_log = qrystallizer.build_task_spec(
                "run-demo",
                workspace / "tasq.md",
                "Implement a tiny feature.",
                ai_binding=binding,
            )
            self.assertEqual(task_spec["ai_binding"]["provider"], "venice")
            self.assertEqual(
                task_spec["ai_binding"]["model"],
                "qwen3-coder-480b-a35b-instruct-turbo",
            )
            self.assertEqual(clarification_log["ai_binding"]["provider"], "venice")


class InstruqtorConfigPathFixTests(unittest.TestCase):
    def test_instruqtor_main_reads_workspace_config_not_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            workspace = tmp / "workspace"
            decoy = tmp / "decoy"
            output_dir = workspace / "output"
            workspace.mkdir(parents=True, exist_ok=True)
            decoy.mkdir(parents=True, exist_ok=True)
            (workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
            (workspace / "tasq.md").write_text("Build app.py", encoding="utf-8")
            (workspace / "config.yaml").write_text(
                "agents:\n  instruqtor:\n    provider: venice\n    model: qwen3-coder-480b-a35b-instruct-turbo\n",
                encoding="utf-8",
            )
            (decoy / "config.yaml").write_text(
                "agents:\n  instruqtor:\n    provider: deepseek\n    model: deepseek-chat\n",
                encoding="utf-8",
            )

            captured = {}

            def _fake_generate(**kwargs):
                captured["ai_provider"] = kwargs.get("ai_provider")
                captured["ai_model"] = kwargs.get("ai_model")
                return [{"title": "Briq 1", "objective": "obj", "content": "content"}]

            orig_cwd = os.getcwd()
            try:
                os.chdir(decoy)
                with mock.patch.dict(os.environ, {"QONQ_WORKSPACE": str(workspace)}, clear=False):
                    with mock.patch.object(sys, "argv", ["instruqtor.py", str(workspace / "tasq.md"), str(output_dir)]):
                        with mock.patch("instruqtor.generate_briqs_with_enforcement", side_effect=_fake_generate):
                            with mock.patch("instruqtor.generate_briqs_paginated", return_value=[]):
                                instruqtor.main()
            finally:
                os.chdir(orig_cwd)

            self.assertEqual(captured.get("ai_provider"), "venice")
            self.assertEqual(captured.get("ai_model"), "qwen3-coder-480b-a35b-instruct-turbo")


class ConstruqtorFixTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.qodeyard = self.root / "qodeyard"
        self.exeq = self.root / "exeq.d"
        self.qodeyard.mkdir(parents=True, exist_ok=True)
        self.exeq.mkdir(parents=True, exist_ok=True)
        self.retry = {"enabled": True, "max_attempts": 1, "retry_delay": 0}
        self.interleaved = {"local_validation": True, "ai_quick_review": False, "retry_on_review_fail": False}
        self.write_strategy = {
            "mode": "staged_atomic_per_attempt",
            "coding_mode": "direct",
            "recovery_policy": "snapshot",
            "hybrid_policy": construqtor.DEFAULT_WRITE_STRATEGY["hybrid_policy"],
        }

    def tearDown(self):
        self._tmp.cleanup()

    def test_heartbeat_does_not_emit_still_working_chatter(self):
        heartbeat = construqtor.Heartbeat("Working", interval=0)

        def _sleep(_seconds):
            heartbeat.stop_event.set()

        with mock.patch("construqtor.time.sleep", side_effect=_sleep):
            with mock.patch("builtins.print") as mock_print:
                heartbeat._run()
        mock_print.assert_not_called()

    def _write_briq(self, name: str, body: str) -> Path:
        briq = self.root / name
        briq.write_text(body, encoding="utf-8")
        return briq

    @mock.patch("construqtor.run_scoped_qualification")
    @mock.patch("construqtor._run_direct_coding_loop")
    def test_direct_mode_passes_allowed_paths_to_direct_loop(self, mock_direct_loop, mock_qualification):
        mock_qualification.return_value = {
            "passed": True,
            "syntax_errors": [],
            "constraint_errors": [],
            "import_warnings": [],
            "files_checked": 1,
        }
        mock_direct_loop.return_value = (
            {"app.py": "print('ok')\n"},
            {"iterations": 1, "ai_call_count": 1, "tool_calls_seen": 1, "parse_failures": 0, "apply_errors": 0},
        )
        briq = self._write_briq(
            "cyqle1_allowed_paths.md",
            "Contract-Relevant: no\nTarget-Files: app.py\nPrimary-Deliverables: app.py\n\nImplement app.py\n",
        )

        with mock.patch("builtins.print"):
            result = construqtor.process_briq_interleaved(
                briq,
                self.qodeyard,
                self.root,
                self.exeq,
                [],
                "tree",
                "program",
                "prompt",
                "venice",
                "qwen3-coder-480b-a35b-instruct-turbo",
                self.retry,
                self.interleaved,
                write_strategy_config=self.write_strategy,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_direct_loop.call_args.kwargs.get("allowed_paths"), {"app.py"})

    @mock.patch("construqtor.run_scoped_qualification")
    @mock.patch("construqtor._run_direct_coding_loop")
    def test_noop_success_requires_validation_proof(self, mock_direct_loop, mock_qualification):
        (self.qodeyard / "app.py").write_text("print('existing')\n", encoding="utf-8")
        mock_direct_loop.return_value = (
            {},
            {"iterations": 1, "ai_call_count": 1, "tool_calls_seen": 0, "parse_failures": 0, "apply_errors": 0},
        )
        mock_qualification.return_value = {
            "passed": False,
            "syntax_errors": ["app.py: [python:syntax] broken"],
            "constraint_errors": [],
            "import_warnings": [],
            "files_checked": 1,
        }
        briq = self._write_briq(
            "cyqle1_noop_validation.md",
            "Contract-Relevant: no\nTarget-Files: app.py\nPrimary-Deliverables: app.py\n\nKeep app.py correct.\n",
        )

        with mock.patch("builtins.print"):
            result = construqtor.process_briq_interleaved(
                briq,
                self.qodeyard,
                self.root,
                self.exeq,
                [],
                "tree",
                "program",
                "prompt",
                "venice",
                "qwen3-coder-480b-a35b-instruct-turbo",
                self.retry,
                self.interleaved,
                write_strategy_config=self.write_strategy,
            )

        self.assertEqual(result["status"], "failure")
        self.assertIn("No-op not allowed: existing target files fail scoped validation", result.get("error", ""))

    @mock.patch("construqtor._run_direct_coding_loop")
    @mock.patch("construqtor.run_scoped_qualification")
    def test_level0_repair_gate_uses_scoped_qualification(self, mock_qualification, mock_direct_loop):
        (self.qodeyard / "app.py").write_text("print('existing')\n", encoding="utf-8")
        mock_qualification.return_value = {
            "passed": True,
            "syntax_errors": [],
            "constraint_errors": [],
            "import_warnings": [],
            "files_checked": 1,
        }
        mock_direct_loop.return_value = (
            {"app.py": "print('new')\n"},
            {"iterations": 1, "ai_call_count": 1, "tool_calls_seen": 1, "parse_failures": 0, "apply_errors": 0},
        )
        briq = self._write_briq(
            "cyqle1_l0_gate.md",
            "Contract-Relevant: no\nTarget-Files: app.py\nPrimary-Deliverables: app.py\n\nRepair app.py\n",
        )

        with mock.patch.dict(os.environ, {"QONQ_REPAIR_MODE": "1"}, clear=False):
            with mock.patch("builtins.print"):
                result = construqtor.process_briq_interleaved(
                    briq,
                    self.qodeyard,
                    self.root,
                    self.exeq,
                    [],
                    "tree",
                    "program",
                    "prompt",
                    "venice",
                    "qwen3-coder-480b-a35b-instruct-turbo",
                    self.retry,
                    self.interleaved,
                    write_strategy_config=self.write_strategy,
                )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["attempts"], 0)
        self.assertTrue(mock_qualification.called)
        self.assertFalse(mock_direct_loop.called)

    def test_run_sh_policy_resolves_exact_literal_from_task_contract(self):
        task_dir = self.root / "task"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task-spec.v1.json").write_text(
            json.dumps(
                {
                    "clarified_task_body": (
                        "run.sh\n\nMust launch exactly:\n\n"
                        "python -m uvicorn main:app --reload --port 8000\n"
                    )
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            construqtor.resolve_run_sh_port_policy(self.root),
            "exact_literal_8000",
        )

    def test_run_sh_exact_literal_policy_accepts_exact_command(self):
        errors = construqtor.validate_run_sh_constraints(
            "#!/bin/bash\npython -m uvicorn main:app --reload --port 8000\n",
            "exact_literal_8000",
        )
        self.assertEqual(errors, [])

    def test_run_sh_exact_literal_policy_rejects_port_variable_variant(self):
        errors = construqtor.validate_run_sh_constraints(
            "#!/bin/bash\npython -m uvicorn main:app --reload --port $PORT\n",
            "exact_literal_8000",
        )
        self.assertTrue(any("must launch exactly" in e for e in errors))

    def test_detect_serialized_code_artifact_flags_blob(self):
        blob_file = self.qodeyard / "main.py"
        blob_file.write_text(
            "['line1\\nline2\\nline3', 'line4\\nline5\\nline6', 'line7\\nline8\\nline9']",
            encoding="utf-8",
        )
        message = construqtor.detect_serialized_code_artifact(blob_file)
        self.assertIsNotNone(message)
        self.assertIn("serialized code blob", message or "")

    def test_run_local_validation_fails_serialized_code_blob(self):
        blob_file = self.qodeyard / "main.py"
        blob_file.write_text(
            "['x\\ny\\nz', 'a\\nb\\nc', 'd\\ne\\nf', 'g\\nh\\ni', 'j\\nk\\nl']",
            encoding="utf-8",
        )
        report = construqtor.run_local_validation(["main.py"], self.qodeyard)
        self.assertFalse(report["passed"])
        self.assertTrue(
            any("serialized code blob" in entry for entry in report.get("syntax_errors", []))
        )


class InspeqtorFixTests(unittest.TestCase):
    def test_success_assessment_normalizes_bracketed_status(self):
        self.assertTrue(inspeqtor.is_success_assessment("[SUCCESS]"))
        self.assertTrue(inspeqtor.is_success_assessment("SUCCESS"))
        self.assertFalse(inspeqtor.is_success_assessment("PASS"))
        self.assertFalse(inspeqtor.is_success_assessment("[FAILURE]"))

    def test_enforce_briq_suggestions_for_repair_only_in_normal_mode(self):
        suggestions = [{"briq": "briq-001", "assessment": "[FAILURE]", "suggestions": "fix it"}]
        self.assertEqual(
            inspeqtor.enforce_briq_suggestions_for_repair("normal", suggestions),
            suggestions,
        )
        self.assertEqual(
            inspeqtor.enforce_briq_suggestions_for_repair("report_only", suggestions),
            [],
        )

    def test_should_run_report_only_briq_reviews_defaults_to_false(self):
        self.assertFalse(inspeqtor.should_run_report_only_briq_reviews({}))
        config_true = {"agents": {"inspeqtor": {"report_only_briq_reviews": True}}}
        self.assertTrue(inspeqtor.should_run_report_only_briq_reviews(config_true))

    def test_should_run_report_only_briq_reviews_env_override(self):
        with mock.patch.dict(os.environ, {"QONQ_INSPEQTOR_REPORT_ONLY_BRIQ_REVIEWS": "1"}, clear=False):
            self.assertTrue(inspeqtor.should_run_report_only_briq_reviews({}))
        with mock.patch.dict(os.environ, {"QONQ_INSPEQTOR_REPORT_ONLY_BRIQ_REVIEWS": "0"}, clear=False):
            self.assertFalse(inspeqtor.should_run_report_only_briq_reviews({"agents": {"inspeqtor": {"report_only_briq_reviews": True}}}))

    def test_repair_plan_uses_deterministic_authority_over_briq_review_noise(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "briq.d").mkdir(parents=True, exist_ok=True)
            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-a",
                                "briq_refs": ["briq-001"],
                                "scope_id": "scope-a",
                                "component_refs": ["component-a"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-001"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "briq.d" / "cyqle1_tasq1_briq001.md").write_text(
                "Briq-Ref: briq-001\n\nBody\n",
                encoding="utf-8",
            )
            inspection_verdict = {
                "issues": [
                    {
                        "issue_id": "deterministic-001",
                        "summary": "Command failed (exit 1)",
                        "severity": "error",
                        "source": "smoketest",
                    },
                    {
                        "issue_id": "briq-review-001",
                        "summary": "briq-001 [FAILURE]: missing implementation",
                        "severity": "error",
                        "source": "briq_review",
                        "briq_ref": "briq-001",
                    },
                ],
                "completion_criteria_results": [],
                "completion_assessment": "Deterministic code defects block completion.",
            }
            validation_bundle = {
                "issues": [
                    {"severity": "warning", "file": "a.py", "scope": "bg-a"},
                ],
                "checks": [],
            }
            realization_bundle = {}
            grouped_coherence = {
                "group_summaries": [
                    {
                        "build_group_id": "bg-a",
                        "status": "FAIL",
                        "changed_files": ["a.py"],
                        "reported_files": ["a.py"],
                    }
                ],
                "undeclared_changed_files": [],
            }
            failed_briq_suggestions = [
                {"briq": "briq-001", "assessment": "[FAILURE]", "suggestions": "missing implementation"}
            ]

            with mock.patch.dict(
                os.environ,
                {
                    "QONQ_GLOBAL_ITERATION_INDEX": "1",
                    "QONQ_BUILD_PASS_INDEX": "1",
                    "QONQ_REPAIR_PASS_INDEX": "0",
                },
                clear=False,
            ):
                plan = inspeqtor.build_repair_plan(
                    root,
                    "1",
                    inspection_verdict,
                    validation_bundle,
                    realization_bundle,
                    grouped_coherence,
                    failed_briq_suggestions,
                )

            self.assertNotIn("bg-a", plan.get("target_build_groups", []))
            self.assertNotIn(
                "address failed or partial briq findings for the targeted build groups",
                plan.get("required_actions", []),
            )

    def test_grouped_coherence_does_not_fail_when_both_attempt_lineages_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "planning").mkdir(parents=True, exist_ok=True)
            (root / "build" / "groups" / "bg-a").mkdir(parents=True, exist_ok=True)

            (root / "planning" / "build-groups.v1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "build_group_id": "bg-a",
                                "scope_id": "scope-a",
                                "component_refs": ["component-a"],
                                "briq_refs": ["briq-001"],
                            }
                        ],
                        "briq_inventory": [{"briq_ref": "briq-001"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "planning" / "component-contracts.v1.json").write_text(
                json.dumps({"items": [{"component_id": "component-a"}]}),
                encoding="utf-8",
            )
            (root / "build" / "groups" / "bg-a" / "build-report.v1.json").write_text(
                json.dumps(
                    {
                        "build_group_id": "bg-a",
                        "files": ["a.py"],
                        "component_ids": ["component-a"],
                        "write_strategy": "staged_atomic_per_attempt",
                        "build_attempt_ids": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "build" / "groups" / "bg-a" / "changed-files.v1.json").write_text(
                json.dumps(
                    {
                        "build_group_id": "bg-a",
                        "changed_files": [{"path": "a.py"}],
                        "build_attempt_ids": [],
                        "recovery_refs": [],
                    }
                ),
                encoding="utf-8",
            )

            grouped = inspeqtor.evaluate_grouped_coherence(root, "1", ["a.py"])
            messages = [issue.get("message", "") for issue in grouped.get("issues", [])]
            self.assertFalse(any("Attempt lineage mismatch" in msg for msg in messages))
            self.assertIn(grouped.get("status"), {"PASS", "PARTIAL"})


if __name__ == "__main__":
    unittest.main()
