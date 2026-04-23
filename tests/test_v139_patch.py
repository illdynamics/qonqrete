# tests/test_v139_patch.py
import unittest
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "qrane"))

from worqer.smoqetester.models import SmoketestResult
from worqer.smoqetester.adapters.python import PythonAdapter
from worqer.lib_ai import _dispatch_openai_compatible
from qrane import get_agent_prefix, Colors

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class TestV139Patch(unittest.TestCase):

    def test_prefix_alignment_logic(self):
        prefix = "uQQ"
        p1 = get_agent_prefix("Qrystallizer", Colors.WHITE, prefix)
        p2 = get_agent_prefix("Qrane", Colors.WHITE, prefix)
        p3 = get_agent_prefix("instruQtor", Colors.WHITE, prefix)
        
        # Check alignment: ⸎ index should be same in stripped text.
        s1 = strip_ansi(p1)
        s2 = strip_ansi(p2)
        s3 = strip_ansi(p3)
        
        idx1 = s1.find("⸎")
        idx2 = s2.find("⸎")
        idx3 = s3.find("⸎")
        
        self.assertEqual(idx1, idx2)
        self.assertEqual(idx2, idx3)
        
        # Verify padding: Qrystallizer is 12 chars, Qrane is 5.
        # get_agent_prefix adds padding + " " before ⸎
        # Qrystallizer: 0 padding + 1 space = 1 space
        # Qrane: 7 padding + 1 space = 8 spaces
        self.assertIn("Qrystallizer』 ⸎", s1)
        self.assertIn("Qrane』        ⸎", s2) # 8 spaces

    def test_openai_token_compatibility(self):
        with patch('worqer.lib_ai._openai_client_for_provider') as mock_client_factory:
            mock_client = MagicMock()
            mock_client_factory.return_value = mock_client
            
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = "result"
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            
            messages = [{"role": "user", "content": "hello"}]
            
            # Test o1 model
            _dispatch_openai_compatible("openai", "o1-mini", messages, 1000, 30)
            args, kwargs = mock_client.chat.completions.create.call_args
            self.assertIn("max_completion_tokens", kwargs)
            self.assertNotIn("max_tokens", kwargs)
            self.assertEqual(kwargs["max_completion_tokens"], 1000)
            
            # Test o3 model
            _dispatch_openai_compatible("openai", "o3-mini", messages, 2000, 30)
            args, kwargs = mock_client.chat.completions.create.call_args
            self.assertIn("max_completion_tokens", kwargs)
            self.assertEqual(kwargs["max_completion_tokens"], 2000)

            # Test gpt-4 model
            _dispatch_openai_compatible("openai", "gpt-4o", messages, 1000, 30)
            args, kwargs = mock_client.chat.completions.create.call_args
            self.assertIn("max_tokens", kwargs)
            self.assertNotIn("max_completion_tokens", kwargs)
            self.assertEqual(kwargs["max_tokens"], 1000)

    def test_python_failure_classification(self):
        adapter = PythonAdapter()
        ctx = MagicMock()
        ctx.qodeyard_path = Path("/tmp/fake_qodeyard")
        
        # Mock manifest check
        with patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'read_text', return_value="fastapi==0.100.0"):
            
            res = SmoketestResult(
                adapter="python",
                name="test",
                status="FAIL",
                executed=True,
                message="failed",
                stderr="ModuleNotFoundError: No module named 'fastapi'"
            )
            
            adapter._classify_failure(res, ctx)
            self.assertEqual(res.failure_kind, "environment_dependency_missing")
            self.assertTrue(res.environment_blocked)
            self.assertEqual(res.missing_module, "fastapi")
            
            # Test undeclared but manifest exists
            with patch.object(Path, 'read_text', return_value="requests"):
                res2 = SmoketestResult(
                    adapter="python",
                    name="test",
                    status="FAIL",
                    executed=True,
                    message="failed",
                    stderr="ModuleNotFoundError: No module named 'fastapi'"
                )
                adapter._classify_failure(res2, ctx)
                self.assertEqual(res2.failure_kind, "dependency_declaration_failures")
                self.assertFalse(res2.environment_blocked)

            # Test no manifest at all
            with patch.object(Path, 'exists', return_value=False):
                res3 = SmoketestResult(
                    adapter="python",
                    name="test",
                    status="FAIL",
                    executed=True,
                    message="failed",
                    stderr="ModuleNotFoundError: No module named 'fastapi'"
                )
                adapter._classify_failure(res3, ctx)
                self.assertEqual(res3.failure_kind, "blocking_code_failures")

if __name__ == '__main__':
    unittest.main()
