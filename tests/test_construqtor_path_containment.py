import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import construqtor  # noqa: E402


class ConstruqtorPathContainmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="construqtor_path_containment_")
        self.workspace = Path(self._tmp)
        self.qodeyard = self.workspace / "qodeyard"
        self.qodeyard.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_safe_relative_file_is_accepted(self):
        payload = "```python:main.py\nprint('ok')\n```"
        files = construqtor._extract_ai_output_files(payload, self.qodeyard)
        self.assertIn("main.py", files)

    def test_parent_traversal_is_rejected(self):
        payload = "```python:../escape.py\nprint('bad')\n```"
        files = construqtor._extract_ai_output_files(payload, self.qodeyard)
        self.assertNotIn("../escape.py", files)
        self.assertEqual(files, {})

    def test_sibling_prefix_escape_is_rejected(self):
        outside = self.workspace / "qodeyard_evil" / "bad.py"
        payload = f"```python:{outside}\nprint('bad')\n```"
        files = construqtor._extract_ai_output_files(payload, self.qodeyard)
        self.assertEqual(files, {})

    def test_symlink_escape_is_rejected_without_crash(self):
        outside_dir = self.workspace / "outside"
        outside_dir.mkdir(parents=True, exist_ok=True)
        link_path = self.qodeyard / "link"
        try:
            os.symlink(outside_dir, link_path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable in this environment")

        payload = "```python:link/escape.py\nprint('bad')\n```"
        files = construqtor._extract_ai_output_files(payload, self.qodeyard)
        self.assertEqual(files, {})


if __name__ == "__main__":
    unittest.main()
