import unittest
import sys
from pathlib import Path

# Ensure worqer is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "worqer"))

import lib_ai

class TestV1313VenicePropagation(unittest.TestCase):
    def setUp(self):
        self.config = {
            "agents": {
                "qrystallizer": {
                    "provider": "venice",
                    "model": "qwen3-coder-480b-a35b-instruct-turbo"
                },
                "instruqtor": {
                    "provider": "venice",
                    "model": "qwen3-coder-480b-a35b-instruct-turbo"
                }
            }
        }

    def test_venice_capability_matching(self):
        # Test specific 480B model
        cap = lib_ai.resolve_model_capabilities("venice", "qwen3-coder-480b-a35b-instruct-turbo", config=self.config, agent_name="instruqtor")
        self.assertEqual(cap.total_context_window, 128000)
        self.assertEqual(cap.safe_input_tokens, 120000)

        # Test generic venice model
        cap_gen = lib_ai.resolve_model_capabilities("venice", "other-model", config=self.config, agent_name="instruqtor")
        self.assertEqual(cap_gen.total_context_window, 100000)

    def test_venice_blank_model_uses_default_at_param_resolution(self):
        config = {
            "agents": {
                "instruqtor": {
                    "provider": "venice",
                    "model": "",
                }
            }
        }
        provider, model = lib_ai.get_agent_ai_params(
            config,
            "instruqtor",
            "venice",
            "qwen3-coder-480b-a35b-instruct-turbo",
        )
        self.assertEqual(provider, "venice")
        self.assertEqual(model, "qwen3-coder-480b-a35b-instruct-turbo")

    def test_venice_dispatch_requires_nonempty_model(self):
        with self.assertRaises(RuntimeError) as exc:
            lib_ai.run_ai_completion(
                "venice",
                "",
                "prompt",
                config=self.config,
                agent_name="instruqtor",
            )
        self.assertIn("requires a non-empty model", str(exc.exception))

if __name__ == '__main__':
    unittest.main()
