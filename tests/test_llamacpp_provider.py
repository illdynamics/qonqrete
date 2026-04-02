import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

import types

# Provide lightweight stubs for optional provider SDKs so the llama.cpp unit tests
# can import worqer.lib_ai without depending on every cloud SDK being installed.
if 'anthropic' not in sys.modules:
    sys.modules['anthropic'] = types.SimpleNamespace(Anthropic=object)
if 'openai' not in sys.modules:
    class _DummyOpenAIClient:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda *a, **k: None))
            self.models = types.SimpleNamespace(list=lambda *a, **k: [])
    sys.modules['openai'] = types.SimpleNamespace(
        OpenAI=_DummyOpenAIClient,
        APITimeoutError=Exception,
        APIError=Exception,
    )
if 'google' not in sys.modules:
    google_module = types.ModuleType('google')
    generativeai_module = types.ModuleType('google.generativeai')
    google_module.generativeai = generativeai_module
    sys.modules['google'] = google_module
    sys.modules['google.generativeai'] = generativeai_module

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from worqer.lib_ai import _select_llamacpp_model_id
from worqer.lib_provider_config import (
    get_llamacpp_endpoint_candidates,
    normalize_llamacpp_endpoint,
    resolve_agent_provider_options,
)
from worqer.lib_security import (
    MAX_LLAMACPP_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    validate_config,
)


class LlamacppProviderTests(unittest.TestCase):
    def test_normalize_llamacpp_endpoint_appends_v1_once(self):
        self.assertEqual(
            normalize_llamacpp_endpoint('host.docker.internal:8080'),
            'http://host.docker.internal:8080/v1',
        )
        self.assertEqual(
            normalize_llamacpp_endpoint('http://host.docker.internal:8080/'),
            'http://host.docker.internal:8080/v1',
        )
        self.assertEqual(
            normalize_llamacpp_endpoint('http://host.docker.internal:8080/v1/'),
            'http://host.docker.internal:8080/v1',
        )

    def test_endpoint_candidates_order_prefers_agent_then_provider_then_env_then_fallbacks(self):
        config = {
            'providers': {'llamacpp': {'endpoint': 'provider.example:8080'}},
            'agents': {'construqtor': {'provider': 'llamacpp', 'endpoint': 'agent.example:8080'}},
        }
        with mock.patch.dict(os.environ, {
            'LLAMACPP_ENDPOINT': 'env-one.example:8080',
            'QONQ_LLAMACPP_ENDPOINT': 'env-two.example:8080',
        }, clear=False):
            candidates = get_llamacpp_endpoint_candidates(config, 'construqtor')

        self.assertEqual(
            candidates[:4],
            [
                'http://agent.example:8080/v1',
                'http://provider.example:8080/v1',
                'http://env-one.example:8080/v1',
                'http://env-two.example:8080/v1',
            ],
        )
        self.assertIn('http://host.docker.internal:8080/v1', candidates)
        self.assertIn('http://host.containers.internal:8080/v1', candidates)
        self.assertIn('http://localhost:8080/v1', candidates)

    def test_resolve_agent_provider_options_merges_llamacpp_defaults_and_overrides(self):
        config = {
            'providers': {
                'llamacpp': {
                    'endpoint': 'http://host.docker.internal:8080',
                    'timeout': 900,
                    'temperature': 0.2,
                    'top_p': 0.9,
                }
            },
            'agents': {
                'construqtor': {
                    'provider': 'llamacpp',
                    'model': '/Users/test/model.gguf',
                    'temperature': 0.15,
                    'max_tokens': 12000,
                }
            },
        }
        options = resolve_agent_provider_options(config, 'construqtor')
        self.assertEqual(options['provider'], 'llamacpp')
        self.assertEqual(options['model'], '/Users/test/model.gguf')
        self.assertEqual(options['endpoint'], 'http://host.docker.internal:8080')
        self.assertEqual(options['timeout'], 900)
        self.assertEqual(options['temperature'], 0.15)
        self.assertEqual(options['top_p'], 0.9)
        self.assertEqual(options['max_tokens'], 12000)
        self.assertEqual(options['endpoint_candidates'][0], 'http://host.docker.internal:8080/v1')

    def test_validate_config_accepts_shipped_llamacpp_timeout(self):
        config = yaml.safe_load((REPO_ROOT / 'worqspace' / 'config.yaml').read_text())
        errors = validate_config(config)
        self.assertEqual(errors, [])

    def test_validate_config_allows_llamacpp_timeout_but_rejects_cloud_timeout_above_default_cap(self):
        ok_config = {
            'providers': {'llamacpp': {'timeout': MAX_LLAMACPP_TIMEOUT_SECONDS}},
            'agents': {
                'construqtor': {
                    'provider': 'llamacpp',
                    'model': '/Users/test/model.gguf',
                    'timeout': MAX_LLAMACPP_TIMEOUT_SECONDS,
                }
            },
        }
        self.assertEqual(validate_config(ok_config), [])

        bad_cloud_config = {
            'agents': {
                'construqtor': {
                    'provider': 'openai',
                    'model': 'gpt-4.1-mini',
                    'timeout': MAX_TIMEOUT_SECONDS + 1,
                }
            },
        }
        errors = validate_config(bad_cloud_config)
        self.assertTrue(any('agents.construqtor.timeout' in err for err in errors))

    @mock.patch('worqer.lib_ai._fetch_llamacpp_models')
    def test_model_id_selection_exact_absolute_path(self, mock_fetch):
        model_id = '/Users/name/Qoding/ai/model.gguf'
        mock_fetch.return_value = [{'id': model_id}]
        resolved = _select_llamacpp_model_id(model_id, 'http://host.docker.internal:8080/v1', 30, 'sk-no-key-required')
        self.assertEqual(resolved, model_id)

    @mock.patch('worqer.lib_ai._fetch_llamacpp_models')
    def test_model_id_selection_matches_basename(self, mock_fetch):
        mock_fetch.return_value = [{'id': '/Users/name/Qoding/ai/model.gguf'}]
        resolved = _select_llamacpp_model_id('model.gguf', 'http://host.docker.internal:8080/v1', 30, 'sk-no-key-required')
        self.assertEqual(resolved, '/Users/name/Qoding/ai/model.gguf')

    @mock.patch('worqer.lib_ai._fetch_llamacpp_models')
    def test_model_id_selection_matches_alias(self, mock_fetch):
        mock_fetch.return_value = [{'id': 'server-model', 'aliases': ['qwen-local']}]
        resolved = _select_llamacpp_model_id('qwen-local', 'http://host.docker.internal:8080/v1', 30, 'sk-no-key-required')
        self.assertEqual(resolved, 'server-model')

    @mock.patch('worqer.lib_ai._fetch_llamacpp_models', side_effect=RuntimeError('boom'))
    def test_model_id_selection_preserves_raw_tilde_path_when_preflight_fails(self, _mock_fetch):
        configured = '~/Qoding/ai/model.gguf'
        resolved = _select_llamacpp_model_id(configured, 'http://host.docker.internal:8080/v1', 30, 'sk-no-key-required')
        self.assertEqual(resolved, configured)

    @mock.patch('worqer.lib_ai._fetch_llamacpp_models')
    def test_model_id_selection_uses_server_path_for_tilde_config_when_basename_matches(self, mock_fetch):
        mock_fetch.return_value = [{'id': '/Users/name/Qoding/ai/model.gguf'}]
        resolved = _select_llamacpp_model_id('~/Qoding/ai/model.gguf', 'http://host.docker.internal:8080/v1', 30, 'sk-no-key-required')
        self.assertEqual(resolved, '/Users/name/Qoding/ai/model.gguf')


if __name__ == '__main__':
    unittest.main()
