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
    def test_oversized_request_uses_chunking_and_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
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
            )

            self.assertIn("[DRY RUN]", response)

            audit_dir = workspace / "audit" / "ai_payloads"
            audits = sorted(audit_dir.glob("*.json"))
            self.assertTrue(audits, "expected audit artifact to be written")
            payload = json.loads(audits[-1].read_text(encoding="utf-8"))

            self.assertTrue(payload["chunking_used"])
            self.assertGreater(payload["number_of_chunks"], 0)
            self.assertTrue(any(item["label"] == "optional_structure" for item in payload["dropped_optional_sections"]))
            sections = {item["label"]: item for item in payload["sections"]}
            self.assertTrue(sections["required_large_task"]["chunked"])
            self.assertFalse(sections["required_large_task"]["omitted"])

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


if __name__ == "__main__":
    unittest.main()
