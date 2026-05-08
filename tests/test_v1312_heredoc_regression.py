import unittest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure worqer is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "worqer"))

import construqtor

class TestV1312HeredocRegression(unittest.TestCase):
    def setUp(self):
        self.worqspace_root = Path("/tmp/qonq_test_heredoc")
        self.worqspace_root.mkdir(parents=True, exist_ok=True)
        self.qodeyard = self.worqspace_root / "qodeyard"
        self.qodeyard.mkdir(parents=True, exist_ok=True)
        
    def tearDown(self):
        import shutil
        if self.worqspace_root.exists():
            shutil.rmtree(self.worqspace_root)

    def test_heredoc_prompt(self):
        p_heredoc = construqtor._build_core_prompt('heredoc', 'tree', 'program', 'p')
        self.assertIn("markdown code blocks", p_heredoc)
        self.assertIn("language:path/to/file.ext", p_heredoc)
        self.assertIn("GENERATE ONLY THE FILE BLOCKS", p_heredoc)
        self.assertNotIn("write_file_direct", p_heredoc)

    def test_heredoc_extraction(self):
        fake_response = """
Here is the code you asked for:
```python:qodeyard/main.py
print("hello world")
```
Some trailing text.
"""
        extracted = construqtor._extract_ai_output_files(fake_response, self.qodeyard)
        self.assertIn("main.py", extracted)
        self.assertEqual(extracted["main.py"], 'print("hello world")')

    def test_heredoc_extraction_no_qodeyard_prefix(self):
        fake_response = """
```javascript:index.js
console.log('hi');
```
"""
        extracted = construqtor._extract_ai_output_files(fake_response, self.qodeyard)
        self.assertIn("index.js", extracted)
        self.assertEqual(extracted["index.js"], "console.log('hi');")

    @patch('construqtor.lib_ai.run_ai_completion')
    @patch('construqtor.run_scoped_qualification')
    def test_heredoc_interleaved_process(self, mock_val, mock_ai):
        mock_val.return_value = {'passed': True, 'files_checked': 1, 'syntax_errors': [], 'constraint_errors': [], 'import_warnings': []}
        mock_ai.return_value = "```python:qodeyard/script.py\npass\n```"
        
        briq_file = self.worqspace_root / "briq.md"
        briq_file.write_text("Contract-Relevant: no\nTarget: `script.py`")
        
        exeq_dir = self.worqspace_root / "exeq"
        exeq_dir.mkdir(exist_ok=True)
        
        retry_config = {'enabled': False, 'max_attempts': 1, 'retry_delay': 0}
        interleaved_config = {'local_validation': False, 'ai_quick_review': False, 'retry_on_review_fail': False}
        write_strategy_config = {'mode': 'staged_atomic_per_attempt', 'coding_mode': 'heredoc', 'recovery_policy': 'snapshot'}
        
        with patch('builtins.print'):
            res = construqtor.process_briq_interleaved(
                briq_file, self.qodeyard, self.worqspace_root, exeq_dir, [], 'tree', 'program', 'prompt',
                'prov', 'mod', retry_config, interleaved_config, write_strategy_config=write_strategy_config
            )
            
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['coding_mode'], 'heredoc')
        self.assertIn('script.py', res['written_files'])

if __name__ == '__main__':
    unittest.main()
