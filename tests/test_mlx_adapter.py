"""Tests for the MLX (Apple Silicon) local OpenAI-compatible provider.

The v2 engine speaks OpenAI-compatible HTTP to a local server that runs the
model separately. MLX models (safetensors, `mlx_lm.server`) are served the
same way llama.cpp serves GGUF — the MlxAdapter is the llama.cpp adapter's
machinery with the MLX server's conventions (default port 8080, model field
omitted so the server uses the model it was started with).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters import get_adapter  # noqa: E402
from qq.adapters import llama_cpp as llama_cpp_mod  # noqa: E402
from qq.adapters.base import AgentCallSpec  # noqa: E402
from qq.adapters.llama_cpp import LlamaCppAdapter  # noqa: E402
from qq.adapters.mlx import MlxAdapter  # noqa: E402
from qq.config import load_providers, resolve_config  # noqa: E402

_DEFAULT = "http://127.0.0.1:8080/v1"


def _spec(model="local", output_file=None, workdir=None):
    return AgentCallSpec(
        role="qlarifier",
        model=model,
        prompt="clarify this",
        workdir=workdir or "/tmp",
        output_file=output_file or "/tmp/mlx-receipt.json",
    )


class TestMlxProviderRegistration(unittest.TestCase):
    def test_registered_in_adapter_registry(self):
        adapter = get_adapter("mlx")
        self.assertIsInstance(adapter, MlxAdapter)
        self.assertIsInstance(adapter, LlamaCppAdapter)
        self.assertEqual(adapter.name, "mlx")

    def test_get_adapter_filters_to_accepted_kwargs(self):
        adapter = get_adapter(
            "mlx",
            endpoint="http://127.0.0.1:7070/v1",
            codeseeq_path="/does/not/exist",  # must be dropped
        )
        self.assertEqual(adapter.endpoint, "http://127.0.0.1:7070/v1")

    def test_provider_manifest_lists_mlx_implemented(self):
        providers = load_providers()
        self.assertIn("mlx", providers)
        pd = providers["mlx"]
        self.assertEqual(pd.status, "implemented")
        self.assertEqual(pd.kind, "api")
        self.assertEqual(pd.default_model, "local")
        self.assertEqual(pd.models, [])

    def test_resolve_config_accepts_mlx_provider(self):
        cfg = resolve_config(provider="mlx")
        self.assertEqual(cfg.provider, "mlx")
        # No model declared for the provider -> per-role default_model used.
        self.assertEqual(cfg.model_qlarifier, "local")
        self.assertEqual(cfg.model_construqtor, "local")

    def test_resolve_config_parses_local_endpoints(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write("provider: mlx\nlocal_endpoints:\n  mlx: http://127.0.0.1:9090/v1\n")
            path = fh.name
        try:
            cfg = resolve_config(qq_path=path)
            self.assertEqual(cfg.local_endpoints.get("mlx"),
                             "http://127.0.0.1:9090/v1")
        finally:
            os.unlink(path)


class TestMlxEndpointConfig(unittest.TestCase):
    def test_default_endpoint_is_mlx_server_port(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = MlxAdapter()
        self.assertEqual(adapter.endpoint, _DEFAULT)

    def test_env_endpoint_override(self):
        with patch.dict(os.environ,
                        {"QQ_MLX_ENDPOINT": "http://192.168.1.20:9999/v1"},
                        clear=True):
            adapter = MlxAdapter()
        self.assertEqual(adapter.endpoint, "http://192.168.1.20:9999/v1")

    def test_explicit_endpoint_kwarg_wins(self):
        with patch.dict(os.environ,
                        {"QQ_MLX_ENDPOINT": "http://env.example:1234/v1"},
                        clear=True):
            adapter = MlxAdapter(endpoint="http://127.0.0.1:8080/v1")
        self.assertEqual(adapter.endpoint, "http://127.0.0.1:8080/v1")

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {"QQ_MLX_API_KEY": "sekret"}, clear=True):
            adapter = MlxAdapter()
        self.assertEqual(adapter.api_key, "sekret")

    def test_no_api_key_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = MlxAdapter()
        self.assertIsNone(adapter.api_key)


class TestMlxModelFieldHandling(unittest.TestCase):
    """mlx_lm.server treats `model` as the id of the model to load — so the
    `local` placeholder must be OMITTED, unlike llama.cpp which ignores it."""

    def test_placeholder_model_is_omitted(self):
        adapter = MlxAdapter(endpoint=_DEFAULT)
        self.assertIsNone(adapter._payload_model(_spec("local")))
        self.assertIsNone(adapter._payload_model(_spec("")))

    def test_explicit_model_id_is_passed_through(self):
        adapter = MlxAdapter(endpoint=_DEFAULT)
        model = "mlx-community/Qwen2.5-7B-Instruct-4bit"
        self.assertEqual(adapter._payload_model(_spec(model)), model)

    def test_llama_flavor_still_sends_placeholder(self):
        """Regression guard: llama.cpp ignores model names, so the existing
        llama-cpp flavor keeps sending `local` exactly as before."""
        adapter = LlamaCppAdapter(endpoint="http://127.0.0.1:8888/v1")
        self.assertEqual(adapter._payload_model(_spec("local")), "local")


class TestMlxCallFlow(unittest.TestCase):
    def test_call_omits_model_field_and_prefixes_mlx(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "receipt.json")
            spec = _spec(model="local", output_file=out, workdir=td)
            adapter = MlxAdapter(endpoint=_DEFAULT)
            captured = {}

            def fake_chat(**kwargs):
                captured["model"] = kwargs["model"]
                captured["endpoint"] = kwargs["endpoint"]
                return json.dumps({"status": "clarified", "clarified_task": "ok"})

            with patch.object(llama_cpp_mod, "_chat_completion",
                              side_effect=fake_chat) as chat:
                result = adapter.call(spec)

            chat.assert_called_once()
            self.assertIsNone(captured["model"])
            self.assertEqual(captured["endpoint"], _DEFAULT)
            self.assertTrue(result.output_path_exists)
            with open(out, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["status"], "clarified")
            self.assertIn("[mlx]", result.stdout)

    def test_call_sends_explicit_model_when_configured(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "receipt.json")
            spec = _spec(model="mlx-community/Qwen2.5-7B-Instruct-4bit",
                         output_file=out, workdir=td)
            adapter = MlxAdapter(endpoint=_DEFAULT)
            captured = {}

            def fake_chat(**kwargs):
                captured["model"] = kwargs["model"]
                return json.dumps({"status": "clarified", "clarified_task": "ok"})

            with patch.object(llama_cpp_mod, "_chat_completion",
                              side_effect=fake_chat):
                adapter.call(spec)
            self.assertEqual(captured["model"],
                             "mlx-community/Qwen2.5-7B-Instruct-4bit")

    def test_capabilities_mirror_llama_flavor(self):
        caps = MlxAdapter(endpoint=_DEFAULT).capabilities()
        self.assertFalse(caps.supports_sessions)
        self.assertFalse(caps.supports_tools)
        self.assertFalse(caps.supports_thinking_mode)
        self.assertTrue(caps.supports_exec_mode)
        self.assertTrue(caps.safe_in_container)

    def test_error_text_names_mlx_env_var(self):
        with patch.object(llama_cpp_mod, "_is_wsl", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                llama_cpp_mod._chat_completion(
                    endpoint="http://127.0.0.1:1/v1",
                    api_key=None,
                    model=None,
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=None,
                    top_p=None,
                    timeout=2,
                    label="mlx",
                    server_name="MLX server",
                    endpoint_env="QQ_MLX_ENDPOINT",
                    server_binary="mlx_lm.server",
                )
        msg = str(ctx.exception)
        self.assertIn("Could not reach mlx endpoint", msg)
        self.assertIn("Is MLX server running? Check QQ_MLX_ENDPOINT", msg)
        self.assertNotIn("WSL", msg)


if __name__ == "__main__":
    unittest.main()
