from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))

import qonfirmer  # noqa: E402


class QonfirmerFullRunRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix='qonfirmer_full_run_')
        self.workspace = Path(self._tmp)
        self.qodeyard = self.workspace / 'qodeyard'
        self.qodeyard.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_full_run_flags_forbidden_import_and_counts_files(self) -> None:
        (self.qodeyard / 'main.py').write_text(
            'import uuid\n\n'
            'def make_id():\n'
            '    return str(uuid.uuid4())\n',
            encoding='utf-8',
        )
        contract = {'invariants': {'forbidden_imports': ['uuid']}}

        report = qonfirmer.run_qonfirmer(contract, self.qodeyard)

        self.assertFalse(report.passed)
        self.assertGreater(report.files_checked, 0)
        self.assertGreater(len(report.violations), 0)
        self.assertTrue(any(v.rule == 'forbidden_import' for v in report.violations))

    def test_full_run_passes_when_contract_is_satisfied(self) -> None:
        (self.qodeyard / 'main.py').write_text(
            'import os\n\n'
            'def env_name() -> str:\n'
            '    return os.getenv("APP_ENV", "dev")\n',
            encoding='utf-8',
        )
        contract = {'invariants': {'forbidden_imports': ['uuid']}}

        report = qonfirmer.run_qonfirmer(contract, self.qodeyard)

        self.assertTrue(report.passed)
        self.assertGreater(report.files_checked, 0)
        self.assertEqual(report.violations, [])

    def test_scoped_run_still_enforces_forbidden_imports(self) -> None:
        (self.qodeyard / 'bad.py').write_text(
            'import uuid\n'
            'def bad() -> str:\n'
            '    return str(uuid.uuid4())\n',
            encoding='utf-8',
        )
        (self.qodeyard / 'ok.py').write_text(
            'import os\n'
            'def ok() -> str:\n'
            '    return os.getenv("X", "y")\n',
            encoding='utf-8',
        )
        contract = {'invariants': {'forbidden_imports': ['uuid']}}

        report = qonfirmer.run_qonfirmer_for_files(contract, self.qodeyard, ['bad.py'])

        self.assertFalse(report.passed)
        self.assertGreater(report.files_checked, 0)
        self.assertTrue(any(v.rule == 'forbidden_import' for v in report.violations))


if __name__ == '__main__':
    unittest.main()
