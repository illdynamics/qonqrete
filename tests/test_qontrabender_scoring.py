import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import qontrabender  # noqa: E402


class QontrabenderScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="qontrabender_scoring_")
        self.workspace = Path(self._tmp)
        (self.workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
        (self.workspace / "qontext.d").mkdir(parents=True, exist_ok=True)
        self.bender = qontrabender.Qontrabender(self.workspace)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_python_docstring_detection_with_ast(self):
        documented = (
            '"""module doc"""\n'
            "class Service:\n"
            '    """class doc"""\n'
            "    def run(self):\n"
            '        """method doc"""\n'
            "        return True\n"
        )
        undocumented = (
            "class Service:\n"
            "    def run(self):\n"
            "        return True\n"
        )
        self.assertTrue(self.bender._has_docstrings(documented, ".py"))
        self.assertFalse(self.bender._has_docstrings(undocumented, ".py"))

    def test_inbound_refs_are_loaded_and_affect_core_score(self):
        qctx_file = self.workspace / "qontext.d" / "app.py.q.yaml"
        qctx_file.write_text(
            yaml.safe_dump(
                {
                    "symbols": [{"name": "app", "dependencies": ["db.py"]}],
                    "inbound_refs": ["svc.py", "router.py", "worker.py"],
                }
            ),
            encoding="utf-8",
        )

        intel = self.bender._load_qontext_intelligence("app.py")
        self.assertEqual(intel.get("inbound_refs"), 3)
        self.assertTrue(intel.get("has_qontext"))

        with_refs = self.bender._calculate_core_score(
            {
                "dependency_count": intel["dependency_count"],
                "symbol_count": intel["symbol_count"],
                "inbound_refs": intel["inbound_refs"],
                "has_docstrings": False,
            }
        )
        without_refs = self.bender._calculate_core_score(
            {
                "dependency_count": intel["dependency_count"],
                "symbol_count": intel["symbol_count"],
                "inbound_refs": 0,
                "has_docstrings": False,
            }
        )
        self.assertGreater(with_refs, without_refs)

    def test_missing_qontext_does_not_fake_inbound_refs(self):
        intel = self.bender._load_qontext_intelligence("missing.py")
        self.assertEqual(intel.get("inbound_refs"), 0)
        self.assertFalse(intel.get("has_qontext"))


if __name__ == "__main__":
    unittest.main()
