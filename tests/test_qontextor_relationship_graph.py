from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))

import qontextor  # noqa: E402


class QontextorRelationshipGraphTests(unittest.TestCase):
    def setUp(self):
        qontextor._PROJECT_GRAPH_CACHE.clear()
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.qodeyard = self.base / 'qodeyard'
        self.qontext = self.base / 'qontext.d'
        self.qodeyard.mkdir()
        self.qontext.mkdir()

        self._write(
            'pkg/__init__.py',
            '''
            """Package init."""
            ''',
        )
        self._write(
            'pkg/base.py',
            '''
            class Base:
                def ping(self) -> str:
                    return "pong"
            ''',
        )
        self._write(
            'pkg/helpers.py',
            '''
            import os
            from pkg.base import Base

            APP_MODE = "dev"

            def env_reader() -> str | None:
                return os.getenv("API_KEY")

            def env_writer() -> None:
                os.environ["MODE"] = APP_MODE

            class Derived(Base):
                def do(self):
                    return env_reader()

                def use_import(self):
                    return self.do()
            ''',
        )
        self._write(
            'pkg/entry.py',
            '''
            from pkg.helpers import Derived, env_reader

            def main():
                worker = Derived()
                env_reader()
                return worker
            ''',
        )

    def tearDown(self):
        self._td.cleanup()
        qontextor._PROJECT_GRAPH_CACHE.clear()

    def _write(self, rel: str, content: str) -> Path:
        path = self.qodeyard / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + '\n', encoding='utf-8')
        return path

    def _load_ctx(self, rel: str) -> dict:
        path = self.qontext / f'{rel}.q.yaml'
        self.assertTrue(path.exists(), f'missing qontext file: {path}')
        return yaml.safe_load(path.read_text(encoding='utf-8'))

    def test_initial_scan_produces_structural_relationship_graph(self):
        qontextor.run_initial_scan(
            self.qodeyard,
            self.qontext,
            {'provider': 'local', 'local_mode': 'complex'},
        )

        helpers = self._load_ctx('pkg/helpers.py')
        entry = self._load_ctx('pkg/entry.py')

        self.assertEqual(helpers['module'], 'pkg.helpers')
        self.assertIn('pkg.base.Base', helpers['dependencies'])
        self.assertIn('pkg.helpers.env_reader', helpers['dependencies'])
        self.assertIn('pkg.entry', helpers['inbound_refs'])

        symbols = {item['qualified_name']: item for item in helpers['symbols']}
        self.assertIn('pkg.helpers.APP_MODE', symbols)
        self.assertEqual(symbols['pkg.helpers.env_reader']['reads_env'], ['API_KEY'])
        self.assertEqual(symbols['pkg.helpers.env_writer']['writes_env'], ['MODE'])

        edges = {(edge['type'], edge['source'], edge['target']) for edge in helpers['relationships']}
        self.assertIn(('extends', 'pkg.helpers.Derived', 'pkg.base.Base'), edges)
        self.assertIn(('calls', 'pkg.helpers.Derived.do', 'pkg.helpers.env_reader'), edges)
        self.assertIn(('calls', 'pkg.helpers.Derived.use_import', 'pkg.helpers.Derived.do'), edges)
        self.assertIn(('reads_env', 'pkg.helpers.env_reader', 'env:API_KEY'), edges)
        self.assertIn(('writes_env', 'pkg.helpers.env_writer', 'env:MODE'), edges)

        entry_edges = {(edge['type'], edge['source'], edge['target']) for edge in entry['relationships']}
        self.assertIn(('calls', 'pkg.entry.main', 'pkg.helpers.Derived'), entry_edges)
        self.assertIn(('calls', 'pkg.entry.main', 'pkg.helpers.env_reader'), entry_edges)

    def test_search_and_ripple_use_structural_data_without_embeddings(self):
        qontextor.run_initial_scan(
            self.qodeyard,
            self.qontext,
            {'provider': 'local', 'local_mode': 'complex'},
        )

        search_results = qontextor.search_symbols('env reader', self.qontext, top_k=5)
        labels = [item['qualified_name'] for _, item in search_results]
        self.assertIn('pkg.helpers.env_reader', labels)

        ripple = qontextor.analyze_ripple_effect('env_reader', self.qontext)
        self.assertIn('pkg.helpers.Derived.do', ripple['called_by'])
        self.assertIn('pkg.entry.main', ripple['called_by'])
        self.assertTrue(any(path.endswith('pkg/entry.py') for path in ripple['depth_1_impact']))


if __name__ == '__main__':
    unittest.main()
