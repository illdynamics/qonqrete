import unittest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure worqer is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "worqer"))

import lib_ai

class TestV1312Providers(unittest.TestCase):
    def setUp(self):
        self.config = {
            "agents": {
                "test_agent": {
                    "provider": "mlx",
                    "api_base_url": "http://localhost:1234/v1"
                }
            }
        }

    def test_mlx_defaults(self):
        cap = lib_ai.resolve_model_capabilities("mlx", "", config=self.config, agent_name="test_agent")
        self.assertEqual(cap.total_context_window, 16384)
        self.assertEqual(cap.safe_output_tokens, 8192)

    def test_llama_cpp_defaults(self):
        cap = lib_ai.resolve_model_capabilities("llama-cpp", "", config=self.config, agent_name="test_agent")
        self.assertEqual(cap.total_context_window, 8192)
        self.assertEqual(cap.safe_output_tokens, 4096)

    def test_get_agent_ai_params_omitted_model(self):
        # mlx with omitted model
        p, m = lib_ai.get_agent_ai_params(self.config, "test_agent", "openai", "gpt-4o")
        self.assertEqual(p, "mlx")
        self.assertEqual(m, "")

        # openai with omitted model (should get default)
        config_oa = {"agents": {"test_agent": {"provider": "openai"}}}
        p, m = lib_ai.get_agent_ai_params(config_oa, "test_agent", "openai", "gpt-4o")
        self.assertEqual(p, "openai")
        self.assertEqual(m, "gpt-4o")

    @patch('urllib.request.urlopen')
    def test_mlx_dispatch_omits_model(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        lib_ai.run_ai_completion(
            "mlx", "", "prompt", config=self.config, agent_name="test_agent"
        )

        args, _ = mock_urlopen.call_args
        req = args[0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertNotIn('model', payload)
        self.assertEqual(payload['max_tokens'], 8192)

    @patch('urllib.request.urlopen')
    def test_mlx_dispatch_with_model(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        lib_ai.run_ai_completion(
            "mlx", "my-model", "prompt", config=self.config, agent_name="test_agent"
        )

        args, _ = mock_urlopen.call_args
        req = args[0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload['model'], 'my-model')

    @patch('urllib.request.urlopen')
    def test_mlx_no_auth_header(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "hello"}}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {}, clear=True):
            if 'MLX_API_KEY' in os.environ: del os.environ['MLX_API_KEY']
            lib_ai.run_ai_completion(
                "mlx", "", "prompt", config=self.config, agent_name="test_agent"
            )

        args, _ = mock_urlopen.call_args
        req = args[0]
        self.assertNotIn('Authorization', req.headers)

    @patch('urllib.request.urlopen')
    def test_mlx_with_auth_header(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "hello"}}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {"MLX_API_KEY": "secret-key"}):
            lib_ai.run_ai_completion(
                "mlx", "", "prompt", config=self.config, agent_name="test_agent"
            )

        args, _ = mock_urlopen.call_args
        req = args[0]
        # In urllib Request, headers are capitalized in a specific way or available in .headers
        auth_header = req.get_header('Authorization')
        self.assertEqual(auth_header, 'Bearer secret-key')

    @patch('lib_ai._openai_client_for_provider')
    def test_venice_dispatch_with_params(self, mock_client_factory):
        self.config["agents"]["test_agent"] = {
            "provider": "venice",
            "model": "venice-model",
            "venice_parameters": {"foo": "bar"}
        }
        
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "hello"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_factory.return_value = mock_client

        with patch.dict(os.environ, {"VENICE_API_KEY": "v-key"}):
            lib_ai.run_ai_completion(
                "venice", "venice-model", "prompt", config=self.config, agent_name="test_agent"
            )

        args, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs['extra_body'], {"venice_parameters": {"foo": "bar"}})

if __name__ == '__main__':
    unittest.main()
