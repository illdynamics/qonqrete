import unittest
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure qrane is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "qrane"))

import qrane

class TestV1312QraneValidation(unittest.TestCase):
    def test_check_api_keys_missing_base_url(self):
        config = {
            "agents": {
                "test_agent": {
                    "provider": "mlx"
                    # missing api_base_url
                }
            }
        }
        
        with patch('sys.exit') as mock_exit, patch('builtins.print') as mock_print:
            qrane.check_api_keys(config, "[Qrane] ")
            mock_exit.assert_called_with(1)
            # Check that it complained about api_base_url
            msgs = [call.args[0] for call in mock_print.call_args_list]
            self.assertTrue(any("lack 'api_base_url'" in m for m in msgs))

    def test_check_api_keys_with_base_url(self):
        config = {
            "agents": {
                "test_agent": {
                    "provider": "mlx",
                    "api_base_url": "http://localhost:1234"
                }
            }
        }
        
        with patch('sys.exit') as mock_exit, patch('builtins.print') as mock_print:
            qrane.check_api_keys(config, "[Qrane] ")
            mock_exit.assert_not_called()

    def test_check_api_keys_venice_required(self):
        config = {
            "agents": {
                "test_agent": {
                    "provider": "venice"
                }
            }
        }
        
        with patch.dict(os.environ, {}, clear=True):
            if 'VENICE_API_KEY' in os.environ: del os.environ['VENICE_API_KEY']
            with patch('builtins.print') as mock_print, patch('sys.exit') as mock_exit:
                qrane.check_api_keys(config, "[Qrane] ")
                mock_exit.assert_called_with(1)
                msgs = [call.args[0] for call in mock_print.call_args_list]
                self.assertTrue(any("VENICE_API_KEY" in m for m in msgs))

if __name__ == '__main__':
    unittest.main()
