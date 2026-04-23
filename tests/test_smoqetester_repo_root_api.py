from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


class RepoRootSmoqetesterApiTests(unittest.TestCase):
    def test_repo_root_import_smoqetester_shim_exports_api(self):
        sys.path.insert(0, str(REPO_ROOT))
        try:
            module = importlib.import_module("smoqetester")
        finally:
            if str(REPO_ROOT) in sys.path:
                sys.path.remove(str(REPO_ROOT))
        self.assertTrue(hasattr(module, "run_smoketest"))
        self.assertTrue(hasattr(module, "SmoketestReport"))

    def test_repo_root_module_execution_for_worqer_smoqetester(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qodeyard = root / "qodeyard"
            qodeyard.mkdir(parents=True, exist_ok=True)
            (qodeyard / "main.py").write_text("print('ok')\n", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text(
                "agents:\n"
                "  inspeqtor:\n"
                "    smoketest:\n"
                "      enabled: false\n",
                encoding="utf-8",
            )

            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "worqer.smoqetester",
                    str(qodeyard),
                    "--cycle",
                    "1",
                    "--config",
                    str(config_path),
                    "--json",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertIn("\"overall_status\"", proc.stdout)

    def test_repo_root_module_execution_for_smoqetester_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qodeyard = root / "qodeyard"
            qodeyard.mkdir(parents=True, exist_ok=True)
            (qodeyard / "main.py").write_text("print('ok')\n", encoding="utf-8")

            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT / "worqer")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "smoqetester",
                    str(qodeyard),
                    "--cycle",
                    "1",
                    "--json",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertIn("\"cycle\"", proc.stdout)


if __name__ == "__main__":
    unittest.main()
