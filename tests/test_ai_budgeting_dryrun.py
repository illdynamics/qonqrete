import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import lib_ai  # noqa: E402
import instruqtor  # noqa: E402
import construqtor  # noqa: E402


class AIBudgetingDryRunTest(unittest.TestCase):
    def _ack_from_preload_message(self, preload_message: str) -> str:
        marker = "Reply with exactly:\n"
        tail = preload_message.split(marker, 1)[1]
        return tail.split("\n", 1)[0].strip()

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

    def test_preload_failure_still_persists_partial_transport_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            os.environ["QONQ_WORKSPACE"] = str(workspace)
            call_count = {"value": 0}

            def fake_run_ai_messages(provider, model, messages, output_tokens, timeout=None, config=None, agent_name=None, request_options=None):
                call_count["value"] += 1
                preload_message = messages[-1]["content"]
                expected_ack = self._ack_from_preload_message(preload_message)
                if call_count["value"] == 1:
                    return lib_ai.DispatchResult(expected_ack, False, {"mode": "ack"})
                return lib_ai.DispatchResult("WRONG", False, {"mode": "ack"})

            with mock.patch("lib_ai.run_ai_messages", side_effect=fake_run_ai_messages):
                with self.assertRaises(RuntimeError) as raised:
                    lib_ai.run_ai_completion(
                        provider="llamacpp",
                        model="model.gguf",
                        prompt="core prompt",
                        prompt_sections=[
                            {
                                "label": "required_large_task",
                                "content": "TASK\n" + ("A" * 200000),
                                "required": True,
                                "loss_policy": "chunkable",
                            }
                        ],
                        agent_name="builder",
                        config={
                            "ai_budgeting": {
                                "chunk_target_input_tokens": 12000,
                                "providers": {
                                    "llamacpp": {
                                        "defaults": {
                                            "safe_input_tokens": 24000,
                                            "safe_output_tokens": 4096,
                                            "total_context_window": 320000,
                                            "planning_context_limit_tokens": 320000,
                                            "supports_multi_message_history": True,
                                            "supports_chunk_preload": True,
                                        }
                                    }
                                },
                            }
                        },
                    )

            self.assertIn("audit=", str(raised.exception))
            audit_path = Path(str(raised.exception).split("audit=", 1)[1].strip())
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["chunk_transport"]["failure_boundary"]["stage"], "preload_ack")
            self.assertEqual(len(payload["preload_acks"]), 1)
            self.assertEqual(len(payload["chunk_transport"]["transmitted_chunks"]), 1)
            self.assertTrue(payload["chunk_transport"]["preload_history_preserved"][0]["ack_succeeded"])
            self.assertFalse(payload["chunk_transport"]["preload_history_preserved"][1]["ack_succeeded"])
            self.assertTrue(payload["chunk_transport"]["transmitted_chunks"][0]["chunk_sidecar"]["path"].endswith("chunk-001.txt"))
            self.assertTrue(payload["chunk_transport"]["transmitted_chunks"][0]["ack_sidecar"]["path"].endswith("ack-001.txt"))

    def test_final_generation_failure_preserves_completed_preload_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            os.environ["QONQ_WORKSPACE"] = str(workspace)
            preload_calls = {"count": 0}

            def fake_run_ai_messages(provider, model, messages, output_tokens, timeout=None, config=None, agent_name=None, request_options=None):
                if request_options and request_options.get("ack_mode"):
                    preload_calls["count"] += 1
                    return lib_ai.DispatchResult(self._ack_from_preload_message(messages[-1]["content"]), False, {"mode": "ack"})
                raise RuntimeError("final generation boom")

            with mock.patch("lib_ai.run_ai_messages", side_effect=fake_run_ai_messages):
                with self.assertRaises(RuntimeError) as raised:
                    lib_ai.run_ai_completion(
                        provider="llamacpp",
                        model="model.gguf",
                        prompt="core prompt",
                        prompt_sections=[
                            {
                                "label": "required_large_task",
                                "content": "TASK\n" + ("A" * 200000),
                                "required": True,
                                "loss_policy": "chunkable",
                            }
                        ],
                        agent_name="builder",
                        config={
                            "ai_budgeting": {
                                "chunk_target_input_tokens": 12000,
                                "providers": {
                                    "llamacpp": {
                                        "defaults": {
                                            "safe_input_tokens": 24000,
                                            "safe_output_tokens": 4096,
                                            "total_context_window": 320000,
                                            "planning_context_limit_tokens": 320000,
                                            "supports_multi_message_history": True,
                                            "supports_chunk_preload": True,
                                        }
                                    }
                                },
                            }
                        },
                    )

            audit_path = Path(str(raised.exception).split("audit=", 1)[1].strip())
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["chunk_transport"]["failure_boundary"]["stage"], "final_generation")
            self.assertEqual(len(payload["preload_acks"]), preload_calls["count"])
            self.assertEqual(len(payload["chunk_transport"]["transmitted_chunks"]), preload_calls["count"])
            self.assertTrue(all(item["ack_succeeded"] for item in payload["chunk_transport"]["preload_history_preserved"]))
            self.assertIn("final generation boom", payload["error"])

    def test_planning_parser_salvages_json_and_markdown_shapes(self):
        json_briqs, json_mode = instruqtor.parse_briqs(
            '[{"title":"Backend","objective":"Build API endpoints"},{"title":"Run Script","objective":"Add launch script"}]'
        )
        self.assertEqual(json_mode, "json")
        self.assertEqual(len(json_briqs), 2)

        markdown_briqs, markdown_mode = instruqtor.parse_briqs(
            "1. Backend\\n- Build main.py with FastAPI endpoints\\n2. Run Script\\n- Add run.sh and requirements.txt"
        )
        self.assertEqual(markdown_mode, "markdown")
        self.assertEqual(len(markdown_briqs), 2)

    def test_construqtor_context_fallback_prefers_implementation_files(self):
        all_context_files = [
            "/tmp/qontext/main.py.q.yaml",
            "/tmp/qontext/requirements.txt.q.yaml",
            "/tmp/bloq/12-chunking-perfection-llamacpp-ollama-report.md",
            "/tmp/bloq/llamacpp_provider_design_for_qonqrete.md",
            "/tmp/bloq/main.py",
            "/tmp/bloq/requirements.txt",
            "/tmp/bloq/run.sh",
            "/tmp/bloq/tasq-small.md",
        ]

        selected = construqtor.select_briq_context_files(all_context_files, [], Path("/tmp/qontext"))

        self.assertEqual(selected, [
            "/tmp/bloq/main.py",
            "/tmp/bloq/requirements.txt",
            "/tmp/bloq/run.sh",
        ])


if __name__ == "__main__":
    unittest.main()
