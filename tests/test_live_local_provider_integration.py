import os
import sys
import tempfile
import unittest
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import lib_ai  # noqa: E402


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@unittest.skipUnless(_env_enabled("QONQ_LIVE_LLAMACPP_TESTS"), "set QONQ_LIVE_LLAMACPP_TESTS=1")
class LiveLlamacppIntegrationTest(unittest.TestCase):
    provider = "llamacpp"
    endpoint = os.environ.get("LLAMACPP_ENDPOINT", "http://localhost:8080/v1")
    model = os.environ.get("QONQ_LLAMACPP_LIVE_MODEL") or os.environ.get("LLAMACPP_MODEL")

    @classmethod
    def setUpClass(cls):
        if not cls.model:
            raise unittest.SkipTest("set QONQ_LLAMACPP_LIVE_MODEL or LLAMACPP_MODEL")

    def test_models_preflight_and_reconciliation(self):
        resolved, meta = lib_ai._select_llamacpp_model_id(self.model, self.endpoint, 30, os.environ.get("LLAMACPP_API_KEY"))
        self.assertTrue(resolved)
        self.assertIn("configured_model", meta)

    def test_simple_chat_completion(self):
        result = lib_ai.run_ai_messages(
            provider=self.provider,
            model=self.model,
            messages=[{"role": "system", "content": "Reply with exactly OK."}, {"role": "user", "content": "OK"}],
            output_tokens=16,
            timeout=120,
            config={"providers": {"llamacpp": {"endpoint": self.endpoint, "timeout": 120}}},
        )
        self.assertTrue(result.text)

    def test_chunked_request_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            os.environ["QONQ_WORKSPACE"] = str(workspace)
            try:
                response = lib_ai.run_ai_completion(
                    provider=self.provider,
                    model=self.model,
                    prompt="core prompt",
                    prompt_sections=[
                        {"label": "instructions", "content": "Reply with exactly CHUNKED_OK.", "required": True, "loss_policy": "preserve"},
                        {"label": "large_context", "content": "A" * 24000, "required": True, "loss_policy": "chunkable"},
                    ],
                    config={
                        "providers": {"llamacpp": {"endpoint": self.endpoint, "timeout": 180, "planning_context_limit_tokens": 8192}},
                        "ai_budgeting": {
                            "chunk_target_input_tokens": 1024,
                            "max_preload_chunks_per_request": 64,
                            "providers": {
                                "llamacpp": {
                                    "defaults": {
                                        "safe_input_tokens": 2048,
                                        "safe_output_tokens": 256,
                                        "total_context_window": 8192,
                                        "planning_context_limit_tokens": 8192,
                                        "supports_multi_message_history": True,
                                        "supports_chunk_preload": True,
                                    }
                                }
                            },
                        },
                    },
                    output_tokens=32,
                )
                self.assertTrue(response)
            except RuntimeError as exc:
                message = str(exc)
                self.assertIn("audit=", message)
                audit_path = Path(message.split("audit=", 1)[1].strip())
                payload = json.loads(audit_path.read_text(encoding="utf-8"))
                self.assertTrue(payload["chunking_used"])
                self.assertGreater(payload["number_of_chunks"], 0)
                self.assertIn(payload["chunk_transport"]["failure_boundary"]["stage"], {"preload_ack", "final_generation"})


@unittest.skipUnless(_env_enabled("QONQ_LIVE_OLLAMA_TESTS"), "set QONQ_LIVE_OLLAMA_TESTS=1")
class LiveOllamaIntegrationTest(unittest.TestCase):
    provider = "ollama"
    endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434/v1")
    native_endpoint = os.environ.get("OLLAMA_NATIVE_ENDPOINT", "http://localhost:11434/api")
    model = os.environ.get("QONQ_OLLAMA_LIVE_MODEL") or os.environ.get("OLLAMA_MODEL")

    @classmethod
    def setUpClass(cls):
        if not cls.model:
            raise unittest.SkipTest("set QONQ_OLLAMA_LIVE_MODEL or OLLAMA_MODEL")

    def test_native_and_v1_preflight(self):
        self.assertIn("data", lib_ai._http_json_request(f"{self.endpoint.rstrip('/')}/models", timeout=30))
        self.assertIn("version", lib_ai._http_json_request(f"{self.native_endpoint.rstrip('/')}/version", timeout=30))
        self.assertIn("models", lib_ai._http_json_request(f"{self.native_endpoint.rstrip('/')}/tags", timeout=30))
        self.assertIsInstance(
            lib_ai._http_json_request(f"{self.native_endpoint.rstrip('/')}/show", method="POST", timeout=30, payload={"name": self.model}),
            dict,
        )
        self.assertIn("models", lib_ai._http_json_request(f"{self.native_endpoint.rstrip('/')}/ps", timeout=30))

    def test_simple_chat_completion(self):
        result = lib_ai.run_ai_messages(
            provider=self.provider,
            model=self.model,
            messages=[{"role": "system", "content": "Reply with exactly OK."}, {"role": "user", "content": "OK"}],
            output_tokens=16,
            timeout=120,
            config={"providers": {"ollama": {"endpoint": self.endpoint, "native_endpoint": self.native_endpoint, "timeout": 120}}},
        )
        self.assertTrue(result.text)

    def test_chunked_request_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "worqspace"
            workspace.mkdir(parents=True, exist_ok=True)
            os.environ["QONQ_WORKSPACE"] = str(workspace)
            try:
                response = lib_ai.run_ai_completion(
                    provider=self.provider,
                    model=self.model,
                    prompt="core prompt",
                    prompt_sections=[
                        {"label": "instructions", "content": "Reply with exactly CHUNKED_OK.", "required": True, "loss_policy": "preserve"},
                        {"label": "large_context", "content": "A" * 24000, "required": True, "loss_policy": "chunkable"},
                    ],
                    config={
                        "providers": {
                            "ollama": {
                                "endpoint": self.endpoint,
                                "native_endpoint": self.native_endpoint,
                                "timeout": 180,
                                "planning_context_limit_tokens": 8192,
                                "use_native_discovery": True,
                                "use_native_metadata": True,
                            }
                        },
                        "ai_budgeting": {
                            "chunk_target_input_tokens": 1024,
                            "max_preload_chunks_per_request": 64,
                            "providers": {
                                "ollama": {
                                    "defaults": {
                                        "safe_input_tokens": 2048,
                                        "safe_output_tokens": 256,
                                        "total_context_window": 8192,
                                        "planning_context_limit_tokens": 8192,
                                        "supports_multi_message_history": True,
                                        "supports_chunk_preload": True,
                                    }
                                }
                            },
                        },
                    },
                    output_tokens=32,
                )
                self.assertTrue(response)
            except RuntimeError as exc:
                message = str(exc)
                self.assertIn("audit=", message)
                audit_path = Path(message.split("audit=", 1)[1].strip())
                payload = json.loads(audit_path.read_text(encoding="utf-8"))
                self.assertTrue(payload["chunking_used"])
                self.assertGreater(payload["number_of_chunks"], 0)
                self.assertIn(payload["chunk_transport"]["failure_boundary"]["stage"], {"preload_ack", "final_generation"})


if __name__ == "__main__":
    unittest.main()
