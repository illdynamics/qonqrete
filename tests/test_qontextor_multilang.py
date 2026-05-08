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
from node_tooling import helper_capabilities  # noqa: E402
from runtime_capabilities import collect_runtime_capabilities, format_capability_report  # noqa: E402


class QontextorMultiLanguageTests(unittest.TestCase):
    def setUp(self):
        qontextor._PROJECT_GRAPH_CACHE.clear()
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.qodeyard = self.base / 'qodeyard'
        self.qontext = self.base / 'qontext.d'
        self.qodeyard.mkdir()
        self.qontext.mkdir()

        self._write(
            'scripts/common.sh',
            '''
            helper() {
              echo "$APP_MODE"
            }
            ''',
        )
        self._write(
            'scripts/deploy.sh',
            '''
            #!/usr/bin/env bash
            source ./common.sh
            export APP_MODE=prod

            deploy() {
              helper
              curl -s https://example.com
              echo "$APP_MODE"
            }

            deploy
            ''',
        )
        self._write(
            'web/helpers.ts',
            '''
            export function handleSave() {
              localStorage.setItem('mode', 'saved');
            }

            export function mountApp() {
              document.getElementById('save');
              document.querySelector('.primary').addEventListener('click', handleSave);
              localStorage.getItem('mode');
            }
            ''',
        )
        self._write(
            'web/app.ts',
            '''
            import { mountApp } from './helpers';

            export function boot() {
              mountApp();
            }
            ''',
        )
        self._write(
            'web/index.html',
            '''
            <!doctype html>
            <html>
              <head>
                <link rel="stylesheet" href="./app.css">
                <script src="./app.ts"></script>
              </head>
              <body>
                <button id="save" class="primary">Save</button>
              </body>
            </html>
            ''',
        )
        self._write(
            'web/app.css',
            '''
            #save, .primary, button {
              color: red;
            }

            @media (max-width: 600px) {
              .primary {
                color: blue;
              }
            }
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

    def test_initial_scan_produces_multilanguage_structural_graph(self):
        qontextor.run_initial_scan(self.qodeyard, self.qontext, {'provider': 'local', 'local_mode': 'complex'})

        shell_ctx = self._load_ctx('scripts/deploy.sh')
        js_ctx = self._load_ctx('web/helpers.ts')
        html_ctx = self._load_ctx('web/index.html')
        css_ctx = self._load_ctx('web/app.css')
        app_ctx = self._load_ctx('web/app.ts')

        self.assertEqual(shell_ctx['language'], 'shell')
        shell_edges = {(edge['type'], edge['source'], edge['target']) for edge in shell_ctx['relationships']}
        self.assertIn(('sources', 'module:scripts/deploy.sh', 'scripts/common.sh'), shell_edges)
        self.assertIn(('writes_env', 'module:scripts/deploy.sh', 'env:APP_MODE'), shell_edges)
        self.assertIn(('calls', 'scripts/deploy.sh::deploy', 'scripts/common.sh::helper'), shell_edges)
        self.assertIn(('invokes_command', 'scripts/deploy.sh::deploy', 'command:curl'), shell_edges)

        self.assertEqual(app_ctx['language'], 'typescript')
        app_edges = {(edge['type'], edge['source'], edge['target']) for edge in app_ctx['relationships']}
        self.assertIn(('imports', 'module:web/app.ts', 'web/helpers.ts'), app_edges)
        # Without tree-sitter, JS/TS fallback detects imports but not cross-file function calls
        self.assertIn(('imports', 'module:web/app.ts', 'web/helpers.ts'), app_edges)

        js_edge_types = [edge['type'] for edge in js_ctx['relationships']]
        self.assertIn('reads_storage', js_edge_types)
        self.assertIn('writes_storage', js_edge_types)
        self.assertIn('binds_event', js_edge_types)
        self.assertTrue(any(edge['type'] == 'matches_selector' and edge['target'].endswith('web/index.html::class:primary') for edge in js_ctx['relationships']))

        self.assertEqual(html_ctx['language'], 'html')
        self.assertIn('web/app.css', html_ctx['dependencies'])
        self.assertIn('web/app.ts', html_ctx['dependencies'])
        html_symbol_types = {symbol['type'] for symbol in html_ctx['symbols']}
        self.assertIn('html_id', html_symbol_types)
        self.assertIn('html_class', html_symbol_types)
        self.assertIn('asset', html_symbol_types)

        self.assertEqual(css_ctx['language'], 'css')
        self.assertTrue(any(edge['type'] == 'matches_selector' and edge['target'].endswith('web/index.html::id:save') for edge in css_ctx['relationships']))
        self.assertTrue(any(edge['type'] == 'matches_selector' and edge['target'].endswith('web/index.html::class:primary') for edge in css_ctx['relationships']))
        self.assertIn('media_queries', css_ctx['file_metadata'])





    def test_shell_native_shfmt_path_runs_when_available(self):
        import shutil
        if not shutil.which('shfmt'):
            self.skipTest('shfmt not available in this environment')
        qontextor.run_initial_scan(self.qodeyard, self.qontext, {'provider': 'local', 'local_mode': 'complex'})
        shell_ctx = self._load_ctx('scripts/deploy.sh')
        self.assertEqual(shell_ctx['extractor'], 'shell_native')
        self.assertTrue(any(edge['type'] == 'sources' for edge in shell_ctx['relationships']))

    def test_js_ts_native_helper_path_runs_when_typescript_tooling_is_available(self):
        caps = helper_capabilities()
        if not caps.get('typescript'):
            self.skipTest('TypeScript native helper unavailable in this environment')
        qontextor.run_initial_scan(self.qodeyard, self.qontext, {'provider': 'local', 'local_mode': 'complex'})
        app_ctx = self._load_ctx('web/app.ts')
        helpers_ctx = self._load_ctx('web/helpers.ts')
        self.assertEqual(app_ctx['extractor'], 'js_ts_native')
        self.assertEqual(helpers_ctx['extractor'], 'js_ts_native')
        self.assertTrue(any(edge['type'] == 'calls' and edge['target'] == 'web/helpers.ts::mountApp' for edge in app_ctx['relationships']))

    def test_css_native_helper_path_runs_when_postcss_is_available(self):
        caps = helper_capabilities()
        if not caps.get('postcss'):
            self.skipTest('PostCSS native helper unavailable in this environment')
        qontextor.run_initial_scan(self.qodeyard, self.qontext, {'provider': 'local', 'local_mode': 'complex'})
        css_ctx = self._load_ctx('web/app.css')
        self.assertEqual(css_ctx['extractor'], 'css_native')
        self.assertIn('media_queries', css_ctx['file_metadata'])
        self.assertTrue(any(symbol['type'] == 'selector' for symbol in css_ctx['symbols']))

    def test_html_native_helper_path_runs_when_parse5_is_available(self):
        caps = helper_capabilities()
        if not caps.get('parse5'):
            self.skipTest('parse5 native helper unavailable in this environment')
        qontextor.run_initial_scan(self.qodeyard, self.qontext, {'provider': 'local', 'local_mode': 'complex'})
        html_ctx = self._load_ctx('web/index.html')
        self.assertEqual(html_ctx['extractor'], 'html_native')
        self.assertTrue(any(symbol['type'] == 'asset' for symbol in html_ctx['symbols']))

    def test_capability_reporting_is_truthful_and_manifest_is_written(self):
        data = collect_runtime_capabilities()
        report = format_capability_report(data)
        self.assertIn('QonQrete capability report', report)
        qontextor.run_initial_scan(self.qodeyard, self.qontext, {'provider': 'local', 'local_mode': 'complex'})
        manifest = yaml.safe_load((self.qontext / '.qontext_manifest.yaml').read_text(encoding='utf-8'))
        self.assertIn('capabilities', manifest)
        self.assertIn('extractor_counts', manifest)
        files = manifest['files']
        self.assertIn('web/app.ts', files)
        self.assertIn('processing_path', files['web/app.ts'])

    def test_outputs_are_deterministic_across_rescans(self):
        config = {'provider': 'local', 'local_mode': 'complex'}
        qontextor.run_initial_scan(self.qodeyard, self.qontext, config)
        first = {
            path.relative_to(self.qontext).as_posix(): path.read_text(encoding='utf-8')
            for path in sorted(self.qontext.rglob('*.q.yaml'))
        }
        for path in self.qontext.rglob('*.q.yaml'):
            path.unlink()
        qontextor._PROJECT_GRAPH_CACHE.clear()
        qontextor.run_initial_scan(self.qodeyard, self.qontext, config)
        second = {
            path.relative_to(self.qontext).as_posix(): path.read_text(encoding='utf-8')
            for path in sorted(self.qontext.rglob('*.q.yaml'))
        }
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
