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
                config={
                    "ai_budgeting": {
                        "dry_run_provider": "deepseek",
                        "providers": {
                            "deepseek": {
                                "defaults": {
                                    "safe_input_tokens": 32000,
                                    "safe_output_tokens": 6000,
                                    "total_context_window": 320000,
                                    "planning_context_limit_tokens": 320000,
                                    "supports_multi_message_history": True,
                                    "supports_chunk_preload": True,
                                }
                            }
                        }
                    }
                },
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
            self.assertIn("transport_sidecars", payload)
            sidecar_dir = workspace / payload["transport_sidecars"]["directory"]
            self.assertTrue(sidecar_dir.exists())
            self.assertTrue(any(path.name.startswith("chunk-") for path in sidecar_dir.iterdir()))

    def test_aggregate_history_limit_failure_is_loud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            os.environ["QONQ_WORKSPACE"] = str(workspace)

            with self.assertRaises(RuntimeError) as raised:
                lib_ai.run_ai_completion(
                    provider="dry-run",
                    model="deepseek-chat",
                    prompt="core prompt",
                    prompt_sections=[
                        {
                            "label": "required_large_task",
                            "content": "TASK\n" + ("A" * 120000),
                            "required": True,
                            "loss_policy": "chunkable",
                        }
                    ],
                    agent_name="test-agent",
                    task_type="code_generation",
                    config={
                        "ai_budgeting": {
                            "dry_run_provider": "deepseek",
                            "providers": {
                                "deepseek": {
                                    "defaults": {
                                        "safe_input_tokens": 16000,
                                        "safe_output_tokens": 2000,
                                        "total_context_window": 22000,
                                        "planning_context_limit_tokens": 22000,
                                        "supports_multi_message_history": True,
                                        "supports_chunk_preload": True,
                                    }
                                }
                            }
                        }
                    },
                )

            self.assertIn("effective planning context limit", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
