import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import lib_ai  # noqa: E402


class AIBudgetingDryRunTest(unittest.TestCase):
    def _run_large_chunkable_request(self, workspace: Path, config=None):
        return lib_ai.run_ai_completion(
            provider="dry-run",
            model="deepseek-chat",
            prompt="core prompt",
            prompt_sections=[
                {
                    "label": "core",
                    "content": "Implement the task.",
                    "required": True,
                    "loss_policy": "preserve",
                },
                {
                    "label": "required_large_task",
                    "content": "TASK\n" + ("A" * 180000),
                    "required": True,
                    "loss_policy": "chunkable",
                },
            ],
            agent_name="test-agent",
            task_type="code_generation",
            config=config,
        )

    def _latest_audit(self, workspace: Path) -> dict:
        audits = sorted((workspace / "audit" / "ai_payloads").glob("*.json"))
        self.assertTrue(audits, "expected audit artifact to be written")
        return json.loads(audits[-1].read_text(encoding="utf-8"))

    def test_oversized_request_uses_chunking_and_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            old_workspace = os.environ.get("QONQ_WORKSPACE")
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)

                context_path = workspace / "large_context.py"
                context_path.write_text("def helper():\n    pass\n" * 8000, encoding="utf-8")

                response = lib_ai.run_ai_completion(
                    provider="dry-run",
                    model="deepseek-chat",
                    prompt="core prompt",
                    context_files=[str(context_path)],
                    prompt_sections=[
                        {
                            "label": "core_instructions",
                            "content": "Implement exactly what follows.",
                            "required": True,
                            "loss_policy": "preserve",
                        },
                        {
                            "label": "required_large_task",
                            "content": "TASK\n" + ("A" * 180000),
                            "required": True,
                            "loss_policy": "chunkable",
                        },
                        {
                            "label": "optional_structure",
                            "content": "\n".join(f"node_{idx}" for idx in range(5000)),
                            "required": False,
                            "loss_policy": "droppable",
                        },
                    ],
                    agent_name="test-agent",
                    task_type="code_generation",
                    config={"ai_budgeting": {"providers": {"deepseek": {"models": {"deepseek-chat": {"safe_input_tokens": 10000, "total_context_window": 15000}}}}}},
                )

                self.assertIn("[DRY RUN]", response)

                audit_dir = workspace / "audit" / "ai_payloads"
                audits = sorted(audit_dir.glob("*.json"))
                self.assertTrue(audits, "expected audit artifact to be written")
                payload = json.loads(audits[-1].read_text(encoding="utf-8"))
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace

            self.assertTrue(payload["chunking_used"])
            self.assertGreater(payload["number_of_chunks"], 0)
            self.assertTrue(any(item["label"] == "optional_structure" for item in payload["dropped_optional_sections"]))
            sections = {item["label"]: item for item in payload["sections"]}
            self.assertTrue(sections["required_large_task"]["chunked"])
            self.assertFalse(sections["required_large_task"]["omitted"])

    def test_default_config_absurd_provider_override_is_capped_and_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)

            old_workspace = os.environ.get("QONQ_WORKSPACE")
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)
                self._run_large_chunkable_request(workspace, config=None)
                payload = self._latest_audit(workspace)
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace

            self.assertLessEqual(payload["safe_input_budget"], 32000)
            self.assertTrue(payload["chunking_used"])
            self.assertGreater(payload["number_of_chunks"], 0)
            self.assertIn("base_capabilities", payload)
            self.assertIn("effective_capabilities", payload)
            self.assertTrue(payload["capability_warnings"])
            self.assertTrue(any("capped" in warning for warning in payload["capability_warnings"]))

    def test_absurd_override_without_trust_is_capped_and_warned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            old_workspace = os.environ.get("QONQ_WORKSPACE")
            config = {
                "ai_budgeting": {
                    "dry_run_provider": "deepseek",
                    "enable_no_loss_chunking": True,
                    "providers": {
                        "deepseek": {
                            "defaults": {
                                "safe_input_tokens": 616000,
                                "safe_output_tokens": 384000,
                                "total_context_window": 1000000,
                                "supports_multi_message_history": True,
                                "supports_chunk_preload": True,
                            }
                        }
                    },
                }
            }
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)
                self._run_large_chunkable_request(workspace, config=config)
                payload = self._latest_audit(workspace)
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace

            self.assertEqual(payload["safe_input_budget"], 32000)
            self.assertTrue(payload["chunking_used"])
            self.assertTrue(payload["capability_warnings"])
            self.assertTrue(payload["applied_capability_overrides"])
            self.assertFalse(payload["applied_capability_overrides"][0]["trusted"])

    def test_trusted_absurd_override_is_explicit_and_visible_in_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            old_workspace = os.environ.get("QONQ_WORKSPACE")
            config = {
                "ai_budgeting": {
                    "dry_run_provider": "deepseek",
                    "trust_provider_context_overrides": True,
                    "enable_no_loss_chunking": True,
                    "providers": {
                        "deepseek": {
                            "defaults": {
                                "safe_input_tokens": 616000,
                                "safe_output_tokens": 384000,
                                "total_context_window": 1000000,
                                "supports_multi_message_history": True,
                                "supports_chunk_preload": True,
                            }
                        }
                    },
                }
            }
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)
                self._run_large_chunkable_request(workspace, config=config)
                payload = self._latest_audit(workspace)
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace

            self.assertEqual(payload["safe_input_budget"], 616000)
            self.assertFalse(payload["chunking_used"])
            self.assertEqual(payload["number_of_chunks"], 0)
            self.assertTrue(payload["applied_capability_overrides"][0]["trusted"])
            self.assertFalse(payload["capability_warnings"])

    def test_previous_log_inclusion_can_be_attempt_gated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            prev_log = workspace / "previous.log"
            prev_log.write_text("prior attempt diagnostics\n", encoding="utf-8")

            old_workspace = os.environ.get("QONQ_WORKSPACE")
            old_prev_log = os.environ.get("QONQ_PREVIOUS_LOG")
            old_include_override = os.environ.get("QONQ_INCLUDE_PREVIOUS_LOG")
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)
                os.environ["QONQ_PREVIOUS_LOG"] = str(prev_log)

                os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = "0"
                lib_ai.run_ai_completion(
                    provider="dry-run",
                    model="deepseek-chat",
                    prompt="",
                    prompt_sections=[{
                        "label": "core",
                        "content": "core instructions",
                        "required": True,
                        "loss_policy": "preserve",
                    }],
                    agent_name="test-agent",
                    task_type="code_generation",
                )
                audits = sorted((workspace / "audit" / "ai_payloads").glob("*.json"))
                self.assertTrue(audits, "expected audit artifact to be written")
                payload = json.loads(audits[-1].read_text(encoding="utf-8"))
                labels = {item["label"] for item in payload["sections"]}
                self.assertNotIn("previous_log", labels)

                os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = "1"
                lib_ai.run_ai_completion(
                    provider="dry-run",
                    model="deepseek-chat",
                    prompt="",
                    prompt_sections=[{
                        "label": "core",
                        "content": "core instructions",
                        "required": True,
                        "loss_policy": "preserve",
                    }],
                    agent_name="test-agent",
                    task_type="code_generation",
                )
                audits = sorted((workspace / "audit" / "ai_payloads").glob("*.json"))
                payload = json.loads(audits[-1].read_text(encoding="utf-8"))
                labels = {item["label"] for item in payload["sections"]}
                self.assertIn("previous_log", labels)
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace
                if old_prev_log is None:
                    os.environ.pop("QONQ_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_PREVIOUS_LOG"] = old_prev_log
                if old_include_override is None:
                    os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = old_include_override

    def test_explicit_previous_log_disable_and_prompt_dedup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            prev_log = workspace / "previous.log"
            prev_log.write_text("prior diagnostics\n", encoding="utf-8")

            old_workspace = os.environ.get("QONQ_WORKSPACE")
            old_prev_log = os.environ.get("QONQ_PREVIOUS_LOG")
            old_include_override = os.environ.get("QONQ_INCLUDE_PREVIOUS_LOG")
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)
                os.environ["QONQ_PREVIOUS_LOG"] = str(prev_log)
                os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = "1"
                prompt = "core instructions"
                lib_ai.run_ai_completion(
                    provider="dry-run",
                    model="deepseek-chat",
                    prompt=prompt,
                    prompt_sections=[{
                        "label": "core",
                        "content": prompt,
                        "required": True,
                        "loss_policy": "preserve",
                    }],
                    include_previous_log=False,
                    agent_name="test-agent",
                    task_type="review",
                )
                audits = sorted((workspace / "audit" / "ai_payloads").glob("*.json"))
                self.assertTrue(audits, "expected audit artifact to be written")
                payload = json.loads(audits[-1].read_text(encoding="utf-8"))
                labels = [item["label"] for item in payload["sections"]]
                self.assertNotIn("previous_log", labels)
                self.assertEqual(labels.count("supplemental_prompt"), 0)
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace
                if old_prev_log is None:
                    os.environ.pop("QONQ_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_PREVIOUS_LOG"] = old_prev_log
                if old_include_override is None:
                    os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = old_include_override

    def test_previous_log_default_excludes_when_not_opted_in(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            prev_log = workspace / "previous.log"
            prev_log.write_text("OPENAI_API_KEY=sk-very-secret\n", encoding="utf-8")

            old_workspace = os.environ.get("QONQ_WORKSPACE")
            old_prev_log = os.environ.get("QONQ_PREVIOUS_LOG")
            old_include_override = os.environ.get("QONQ_INCLUDE_PREVIOUS_LOG")
            try:
                os.environ["QONQ_WORKSPACE"] = str(workspace)
                os.environ["QONQ_PREVIOUS_LOG"] = str(prev_log)
                os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                lib_ai.run_ai_completion(
                    provider="dry-run",
                    model="deepseek-chat",
                    prompt="",
                    prompt_sections=[{
                        "label": "core",
                        "content": "core instructions",
                        "required": True,
                        "loss_policy": "preserve",
                    }],
                    config={},
                    agent_name="test-agent",
                    task_type="code_generation",
                )
                audits = sorted((workspace / "audit" / "ai_payloads").glob("*.json"))
                self.assertTrue(audits, "expected audit artifact to be written")
                payload = json.loads(audits[-1].read_text(encoding="utf-8"))
                labels = {item["label"] for item in payload["sections"]}
                self.assertNotIn("previous_log", labels)
            finally:
                if old_workspace is None:
                    os.environ.pop("QONQ_WORKSPACE", None)
                else:
                    os.environ["QONQ_WORKSPACE"] = old_workspace
                if old_prev_log is None:
                    os.environ.pop("QONQ_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_PREVIOUS_LOG"] = old_prev_log
                if old_include_override is None:
                    os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = old_include_override

    def test_previous_log_opt_in_includes_sanitized_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            prev_log = workspace / "previous.log"
            prev_log.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=sk-verysecret1234567890",
                        "Authorization: Bearer super-secret-token-12345",
                        "Path: /Users/alice/private/project/file.py",
                    ]
                ),
                encoding="utf-8",
            )

            old_prev_log = os.environ.get("QONQ_PREVIOUS_LOG")
            old_include_override = os.environ.get("QONQ_INCLUDE_PREVIOUS_LOG")
            try:
                os.environ["QONQ_PREVIOUS_LOG"] = str(prev_log)
                os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                section = lib_ai._previous_log_section(  # pylint: disable=protected-access
                    {"ai_budgeting": {"include_previous_log": True, "previous_log_max_chars": 12000}},
                    chars_per_token=4.0,
                )
                self.assertIsNotNone(section)
                self.assertIn("[REDACTED]", section.content)
                self.assertNotIn("sk-verysecret1234567890", section.content)
                self.assertNotIn("super-secret-token-12345", section.content)
                self.assertNotIn("/Users/alice/", section.content)
            finally:
                if old_prev_log is None:
                    os.environ.pop("QONQ_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_PREVIOUS_LOG"] = old_prev_log
                if old_include_override is None:
                    os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = old_include_override


if __name__ == "__main__":
    unittest.main()
