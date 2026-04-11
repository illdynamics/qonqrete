import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))
sys.path.insert(0, str(PROJECT_ROOT))

import lib_ai  # noqa: E402
import lib_provider_config  # noqa: E402
import qrane.qrane as qrane_runtime  # noqa: E402
from ai_capabilities import resolve_model_capabilities  # noqa: E402
from lib_security import validate_config  # noqa: E402


class LocalProviderIntegrationTest(unittest.TestCase):
    def test_provider_enum_acceptance(self):
        self.assertEqual(validate_config({"agents": {"builder": {"provider": "llamacpp", "timeout": 900}}}), [])
        self.assertEqual(validate_config({"agents": {"builder": {"provider": "ollama", "timeout": 900}}}), [])

    def test_llamacpp_endpoint_normalization_and_fallback_order(self):
        with mock.patch.dict("os.environ", {"LLAMACPP_ENDPOINT": "host.containers.internal:9000"}, clear=False):
            options = lib_provider_config.resolve_agent_provider_options(
                config={
                    "providers": {"llamacpp": {"endpoint": "localhost:8080", "timeout": 900}},
                    "agents": {"builder": {"provider": "llamacpp", "endpoint": "host.docker.internal:8081"}},
                },
                agent_name="builder",
                provider="llamacpp",
            )
        self.assertEqual(options["endpoint_candidates"][0], "http://host.docker.internal:8081/v1")
        self.assertEqual(options["endpoint_candidates"][1], "http://localhost:8080/v1")
        self.assertEqual(options["endpoint_candidates"][2], "http://host.containers.internal:9000/v1")

    @mock.patch("lib_ai._http_json_request")
    def test_llamacpp_models_reconcile_exact_and_basename(self, mock_request):
        mock_request.return_value = {
            "data": [
                {"id": "/models/qwen.gguf", "root": "/models/qwen.gguf"},
                {"id": "other-model", "alias": "other"},
            ]
        }
        resolved, meta = lib_ai._select_llamacpp_model_id("/models/qwen.gguf", "http://localhost:8080/v1", 30, None)
        self.assertEqual(resolved, "/models/qwen.gguf")
        self.assertIn("/models/qwen.gguf", meta["server_models"])

        resolved, _ = lib_ai._select_llamacpp_model_id("qwen.gguf", "http://localhost:8080/v1", 30, None)
        self.assertEqual(resolved, "/models/qwen.gguf")

    @mock.patch("lib_ai._http_json_request")
    def test_llamacpp_models_reconcile_alias_root_parent(self, mock_request):
        mock_request.return_value = {
            "data": [
                {"id": "qwen-local", "root": "/srv/qwen.gguf", "parent": "/srv", "alias": "qwen"},
            ]
        }
        resolved, _ = lib_ai._select_llamacpp_model_id("qwen", "http://localhost:8080/v1", 30, None)
        self.assertEqual(resolved, "qwen-local")

    @mock.patch("lib_ai._http_json_request", side_effect=RuntimeError("boom"))
    def test_llamacpp_models_failure_falls_back_to_raw_model(self, _mock_request):
        resolved, meta = lib_ai._select_llamacpp_model_id("raw-model", "http://localhost:8080/v1", 30, None)
        self.assertEqual(resolved, "raw-model")
        self.assertIn("models_preflight_error", meta)

    def test_ollama_endpoint_normalization_and_native_derivation(self):
        options = lib_provider_config.resolve_agent_provider_options(
            config={"providers": {"ollama": {"endpoint": "localhost:11434"}}},
            provider="ollama",
        )
        self.assertEqual(options["endpoint"], "http://localhost:11434/v1")
        self.assertEqual(options["native_endpoint"], "http://localhost:11434/api")

    @mock.patch("lib_ai._http_json_request")
    def test_ollama_native_discovery_flags_change_runtime_behavior(self, mock_request):
        calls = []

        def fake_request(url, *args, **kwargs):
            calls.append(url)
            if url.endswith("/v1/models"):
                return {"data": [{"id": "qwen3:14b"}]}
            if url.endswith("/api/version"):
                return {"version": "0.13.3"}
            if url.endswith("/api/tags"):
                return {"models": [{"name": "qwen3:14b"}]}
            if url.endswith("/api/show"):
                return {"details": {"family": "qwen3"}}
            if url.endswith("/api/ps"):
                return {"models": [{"model": "qwen3:14b", "context_length": 16384}]}
            raise AssertionError(url)

        mock_request.side_effect = fake_request

        resolved, meta = lib_ai._select_ollama_model_id(
            "qwen3:14b",
            "http://localhost:11434/v1",
            "http://localhost:11434/api",
            30,
            use_native_discovery=False,
            use_native_metadata=True,
        )
        self.assertEqual(resolved, "qwen3:14b")
        self.assertEqual(meta["native_discovery"], {})
        self.assertEqual(calls, ["http://localhost:11434/v1/models"])

        calls.clear()
        resolved, meta = lib_ai._select_ollama_model_id(
            "qwen3:14b",
            "http://localhost:11434/v1",
            "http://localhost:11434/api",
            30,
            use_native_discovery=True,
            use_native_metadata=False,
        )
        self.assertEqual(resolved, "qwen3:14b")
        self.assertIn("version", meta["native_discovery"])
        self.assertIn("tags", meta["native_discovery"])
        self.assertNotIn("show", meta["native_discovery"])
        self.assertNotIn("ps", meta["native_discovery"])
        self.assertEqual(
            calls,
            [
                "http://localhost:11434/v1/models",
                "http://localhost:11434/api/version",
                "http://localhost:11434/api/tags",
            ],
        )

    @mock.patch("lib_ai._http_json_request")
    def test_ollama_model_resolution_and_missing_model_diagnostic(self, mock_request):
        def fake_request(url, *args, **kwargs):
            if url.endswith("/v1/models"):
                return {"data": [{"id": "qwen3:14b"}, {"id": "qwen3:8b"}]}
            if url.endswith("/api/version"):
                return {"version": "0.13.3"}
            if url.endswith("/api/tags"):
                return {"models": [{"name": "qwen3:14b"}, {"name": "qwen3:8b"}]}
            if url.endswith("/api/show"):
                return {"details": {"family": "qwen3"}}
            if url.endswith("/api/ps"):
                return {"models": [{"model": "qwen3:14b", "context_length": 16384}]}
            raise AssertionError(url)

        mock_request.side_effect = fake_request
        resolved, meta = lib_ai._select_ollama_model_id("qwen3:14b", "http://localhost:11434/v1", "http://localhost:11434/api", 30)
        self.assertEqual(resolved, "qwen3:14b")
        self.assertEqual(meta["native_discovery"]["ps"]["models"][0]["context_length"], 16384)

        with self.assertRaises(RuntimeError) as raised:
            lib_ai._select_ollama_model_id("missing-model", "http://localhost:11434/v1", "http://localhost:11434/api", 30)
        self.assertIn("Installed models", str(raised.exception))

    def test_planning_context_override_merge_rules(self):
        config = {
            "providers": {"llamacpp": {"planning_context_limit_tokens": 16000, "max_tokens": 2048}},
            "agents": {"builder": {"provider": "llamacpp", "planning_context_limit_tokens": 12000}},
        }
        caps = resolve_model_capabilities("llamacpp", "model.gguf", config=config, agent_name="builder")
        self.assertEqual(caps.planning_context_limit_tokens, 12000)

    def test_runtime_config_loader_prefers_active_qage_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "config.yaml").write_text(
                "providers:\n  llamacpp:\n    planning_context_limit_tokens: 16384\n    max_tokens: 2048\n"
                "agents:\n  builder:\n    provider: llamacpp\n",
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {"QONQ_WORKSPACE": str(workspace)}, clear=False):
                caps = resolve_model_capabilities("llamacpp", "model.gguf", agent_name="builder")
        self.assertEqual(caps.planning_context_limit_tokens, 16384)
        self.assertEqual(caps.safe_output_tokens, 2048)

    def test_check_api_keys_skips_local_http_providers(self):
        config = {"agents": {"builder": {"provider": "llamacpp"}, "reviewer": {"provider": "ollama"}}}
        qrane_runtime.check_api_keys(config, "[TEST]")

    def test_ack_retry_logic_is_bounded_and_strict(self):
        chunk = lib_ai.ChunkRecord(
            chunk_index=1,
            chunk_total=1,
            section_label="req",
            section_hash="sectionhash",
            chunk_hash="chunkhash",
            estimated_tokens=10,
            text="payload",
        )
        lib_ai._build_chunk_records([chunk])
        calls = []

        def fake_run(provider, model, messages, output_tokens, timeout=None, config=None, agent_name=None, request_options=None):
            calls.append({"messages": messages, "request_options": request_options})
            if len(calls) == 1:
                return lib_ai.DispatchResult("WRONG", False, {})
            if len(calls) == 2:
                return lib_ai.DispatchResult(chunk.expected_ack, False, {})
            return lib_ai.DispatchResult("final answer", False, {})

        with mock.patch("lib_ai.run_ai_messages", side_effect=fake_run):
            result, retry_log = lib_ai._dispatch_with_chunking(
                provider="llamacpp",
                model="model.gguf",
                inline_prompt="do work",
                chunks=[chunk],
                output_tokens=128,
                config={"ai_budgeting": {"preload_ack_max_retries": 2}},
                agent_name="builder",
                timeout=30,
            )

        self.assertEqual(result.text, "final answer")
        self.assertEqual(len(retry_log[0]["attempts"]), 2)
        self.assertTrue(retry_log[0]["success"])
        self.assertTrue(calls[0]["request_options"]["ack_mode"])

    def test_ollama_fallback_pairs_native_endpoint_with_current_host(self):
        seen_pairs = []

        def fake_select(model, endpoint, native_endpoint, timeout, **kwargs):
            seen_pairs.append((endpoint, native_endpoint))
            raise RuntimeError(f"boom at {endpoint}")

        provider_options = {
            "endpoint_candidates": [
                "http://bad-host:11434/v1",
                "http://good-host:11434/v1",
            ],
            "native_endpoint_candidates": [
                "http://good-host:11434/api",
                "http://bad-host:11434/api",
            ],
            "api_key": "ollama",
            "use_native_discovery": True,
            "use_native_metadata": True,
        }

        with mock.patch("lib_ai._select_ollama_model_id", side_effect=fake_select):
            with self.assertRaises(RuntimeError) as raised:
                lib_ai._dispatch_local_openai_compatible(
                    provider="ollama",
                    model="qwen3:14b",
                    messages=[{"role": "user", "content": "hello"}],
                    output_tokens=64,
                    timeout=30,
                    provider_options=provider_options,
                )

        self.assertEqual(
            seen_pairs,
            [
                ("http://bad-host:11434/v1", "http://bad-host:11434/api"),
                ("http://good-host:11434/v1", "http://good-host:11434/api"),
            ],
        )
        self.assertIn("openai=http://bad-host:11434/v1, native=http://bad-host:11434/api", str(raised.exception))
        self.assertIn("openai=http://good-host:11434/v1, native=http://good-host:11434/api", str(raised.exception))

    def test_validate_config_rejects_invalid_local_provider_config(self):
        errors = validate_config(
            {
                "providers": {
                    "llamacpp": {
                        "endpoint": 123,
                        "timeout": "slow",
                        "planning_context_limit_tokens": 128,
                    },
                    "ollama": {
                        "endpoint": "notaurl:://bad",
                        "native_endpoint": "http://other-host:11434/api",
                        "use_native_discovery": "yes",
                        "use_native_metadata": True,
                        "use_native_transport": True,
                    },
                },
                "agents": {
                    "builder": {
                        "provider": "ollama",
                        "endpoint": "http://localhost:11434/v1",
                        "native_endpoint": "http://127.0.0.1:11434/api",
                        "enable_responses_api": True,
                    }
                },
            }
        )
        joined = "\n".join(errors)
        self.assertIn("providers.llamacpp.endpoint must be a string HTTP endpoint", joined)
        self.assertIn("providers.llamacpp.timeout must be an integer between 1 and 900", joined)
        self.assertIn("providers.llamacpp.planning_context_limit_tokens must be an integer >= 512", joined)
        self.assertIn("providers.ollama.endpoint must use http:// or https://", joined)
        self.assertIn("providers.ollama.native_endpoint must point at the same host as providers.ollama.endpoint", joined)
        self.assertIn("providers.ollama.use_native_discovery must be a boolean", joined)
        self.assertIn("providers.ollama.use_native_transport is not supported yet; remove it from config", joined)
        self.assertIn("agents.builder.enable_responses_api is not supported yet; remove it from config", joined)


if __name__ == "__main__":
    unittest.main()
