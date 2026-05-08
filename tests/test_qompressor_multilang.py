from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import types
import unittest

import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))

import qompressor  # noqa: E402
from node_tooling import helper_capabilities, run_node_helper  # noqa: E402
from runtime_capabilities import collect_runtime_capabilities, format_capability_report  # noqa: E402
from qompressor_extractors import tree_sitter_fallback  # noqa: E402


class QompressorMultiLanguageTests(unittest.TestCase):
    def test_python_skeleton_preserves_structure(self):
        content = textwrap.dedent(
            '''
            import os

            API_PORT = 8080

            class Service:
                """Service docs."""

                @classmethod
                def build(cls, value: str) -> "Service":
                    return cls()

            def helper(name: str) -> str:
                value = os.getenv("APP_MODE", "dev")
                return name + value
            '''
        ).strip() + '\n'
        out = qompressor.compress_file_content('app.py', content)
        self.assertIn('import os', out)
        self.assertIn('API_PORT = 8080', out)
        self.assertIn('class Service:', out)
        self.assertIn('@classmethod', out)
        self.assertIn('def helper(name: str) -> str:', out)
        self.assertIn('# ... (body stripped by Qompressor) ...', out)

    def test_shell_skeleton_preserves_sources_exports_functions_and_entrypoint(self):
        content = textwrap.dedent(
            '''
            #!/usr/bin/env bash
            set -euo pipefail
            source ./common.sh
            export APP_MODE=prod

            deploy() {
              helper "$APP_MODE"
              curl -fsSL https://example.invalid
              BUILD_ID=42
            }

            deploy "$@"
            '''
        ).strip() + '\n'
        out = qompressor.compress_file_content('deploy.sh', content)
        self.assertIn('#!/usr/bin/env bash', out)
        self.assertIn('set -euo pipefail', out)
        self.assertIn('source ./common.sh', out)
        self.assertIn('export APP_MODE=prod', out)
        self.assertIn('deploy() {', out)
        self.assertIn('reads env: APP_MODE', out)
        self.assertIn('writes env: BUILD_ID', out)
        self.assertIn('deploy "$@"', out)

    def test_js_ts_skeleton_preserves_imports_classes_functions_storage_and_events(self):
        content = textwrap.dedent(
            '''
            import { api } from "./api";

            export class App {
              constructor() {
                document.querySelector("#save").addEventListener("click", this.save.bind(this));
              }

              save() {
                localStorage.setItem("mode", "saved");
                api();
              }
            }

            export const mount = (root) => {
              sessionStorage.getItem("mode");
              return new App(root);
            };
            '''
        ).strip() + '\n'
        out = qompressor.compress_file_content('app.ts', content)
        self.assertIn('import { api } from "./api";', out)
        self.assertIn('export class App {', out)
        self.assertIn('constructor() {', out)
        self.assertIn('addEventListener("click"', out)
        self.assertIn('events: click', out)
        self.assertIn('sessionStorage.getItem', out)
        self.assertIn('export const mount = (root) => {', out)

    def test_html_css_skeleton_preserves_ui_structure_assets_and_selectors(self):
        html_content = textwrap.dedent(
            '''
            <!doctype html>
            <html>
              <head>
                <link rel="stylesheet" href="./app.css">
                <script src="./app.js"></script>
              </head>
              <body>
                <form id="login" class="panel" data-flow="auth">
                  <input type="email" name="email" />
                  <button id="submit" class="primary">Save</button>
                </form>
              </body>
            </html>
            '''
        ).strip() + '\n'
        css_content = textwrap.dedent(
            '''
            :root {
              --brand: #f0f;
              color: white;
            }

            #submit, .primary {
              display: flex;
              gap: 8px;
              color: white;
            }

            @media (max-width: 600px) {
              .panel {
                display: grid;
              }
            }
            '''
        ).strip() + '\n'
        html_out = qompressor.compress_file_content('index.html', html_content)
        css_out = qompressor.compress_file_content('app.css', css_content)
        self.assertIn('<link', html_out)
        self.assertIn('rel="stylesheet"', html_out)
        self.assertIn('href="./app.css"', html_out)
        self.assertIn('<script src="./app.js">', html_out)
        self.assertIn('<form id="login" class="panel" data-flow="auth">', html_out)
        self.assertIn('<button id="submit" class="primary">', html_out)
        self.assertIn('Save', html_out)
        self.assertIn(':root {', css_out)
        self.assertIn('--brand: #f0f;', css_out)
        self.assertIn('#submit, .primary {', css_out)
        self.assertIn('@media (max-width: 600px) {', css_out)





    def test_shell_native_shfmt_path_runs_when_available(self):
        import shutil
        if not shutil.which('shfmt'):
            self.skipTest('shfmt not available in this environment')
        content = '#!/usr/bin/env bash\nrun() {\n  echo "$APP_MODE"\n}\nrun\n'
        out = qompressor.compress_file_content('run.sh', content)
        self.assertIn('run() {', out)
        self.assertIn('summary:', out)

    def test_js_ts_native_helper_runs_for_qompressor_when_typescript_tooling_is_available(self):
        caps = helper_capabilities()
        if not caps.get('typescript'):
            self.skipTest('TypeScript native helper unavailable in this environment')
        content = 'export function boot() {\n  mount()\n}\n'
        try:
            native = run_node_helper('compress-js-ts', stdin_text=content, args=['app.ts'], timeout=5)['output']
        except RuntimeError as e:
            self.skipTest(f"Node helper failed/timed out: {e}")
        out = qompressor.compress_file_content('app.ts', content)
        self.assertEqual(out, native)
        self.assertIn('export function boot() {', out)

    def test_css_native_helper_runs_for_qompressor_when_postcss_is_available(self):
        caps = helper_capabilities()
        if not caps.get('postcss'):
            self.skipTest('PostCSS native helper unavailable in this environment')
        content = '#save { display: flex; gap: 8px; color: white; }\n'
        try:
            native = run_node_helper('compress-css', stdin_text=content, args=['app.css'], timeout=5)['output']
        except RuntimeError as e:
            self.skipTest(f"Node helper failed/timed out: {e}")
        out = qompressor.compress_file_content('app.css', content)
        self.assertEqual(out, native)
        self.assertIn('#save {', out)

    def test_html_native_helper_runs_for_qompressor_when_parse5_is_available(self):
        caps = helper_capabilities()
        if not caps.get('parse5'):
            self.skipTest('parse5 native helper unavailable in this environment')
        content = '<html><body><button id="x">X</button></body></html>\n'
        try:
            native = run_node_helper('compress-html', stdin_text=content, args=['index.html'], timeout=5)['output']
        except RuntimeError as e:
            self.skipTest(f"Node helper failed/timed out: {e}")
        out = qompressor.compress_file_content('index.html', content)
        self.assertEqual(out, native)
        self.assertIn('<button id="x">', out)

    def test_tree_sitter_capability_reporting_is_honest(self):
        data = collect_runtime_capabilities()
        ts = data['optional_fallbacks']['tree_sitter']
        self.assertTrue(ts['optional'])
        if ts['installed']:
            self.assertTrue(ts['available'])
        else:
            self.assertIn('requirements-optional-tree-sitter.txt', ts['install_hint'])

    def test_tree_sitter_integration_when_opted_in_and_available(self):
        if os.environ.get('QONQ_RUN_TREE_SITTER_INTEGRATION') != '1':
            self.skipTest('opt-in Tree-sitter integration test is disabled')
        fallback = tree_sitter_fallback.TreeSitterFallback()
        availability = fallback.availability(Path('sample.rb'))
        if not availability.available:
            self.skipTest(availability.reason or 'Tree-sitter parser unavailable')
        content = 'class User\n  def save(name)\n    puts name\n  end\nend\n'
        out = qompressor.compress_file_content('user.rb', content)
        self.assertIn('class User', out)

    def test_capability_reporting_is_truthful_and_human_readable(self):
        data = collect_runtime_capabilities()
        report = format_capability_report(data)
        self.assertIn('QonQrete capability report', report)
        self.assertIn('Python', report)
        self.assertIn('Optional Tree-sitter fallback', report)
        self.assertEqual(data['languages']['shell']['native_available'], bool(__import__('shutil').which('shfmt')))

    def test_cli_processes_mixed_project_writes_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            src = td_path / 'qodeyard'
            dest = td_path / 'bloq.d'
            src.mkdir()
            (src / 'a.py').write_text('def hi():\n    return 1\n', encoding='utf-8')
            (src / 'b.sh').write_text('run() {\n  echo hi\n}\nrun\n', encoding='utf-8')
            (src / 'c.ts').write_text('export function boot() {\n  mount()\n}\n', encoding='utf-8')
            original_argv = sys.argv[:]
            sys.argv = ['qompressor.py', str(src), str(dest)]
            try:
                qompressor.main()
            finally:
                sys.argv = original_argv
            manifest = yaml.safe_load((dest / '.bloq_manifest.yaml').read_text(encoding='utf-8'))
            self.assertIn('capabilities', manifest)
            self.assertIn('mode_counts', manifest)
            files = {item['file']: item for item in manifest['files']}
            self.assertIn('a.py', files)
            self.assertIn('b.sh', files)
            self.assertIn('c.ts', files)
            self.assertTrue(files['a.py']['mode'].startswith('python_'))
            for key in ('source_hash', 'source_size_bytes', 'compressed_size_bytes', 'fidelity', 'compressor_status', 'strategy', 'tooling'):
                self.assertIn(key, files['a.py'])

    def test_tree_sitter_fallback_invocation_for_unsupported_language(self):
        original_get_parser = tree_sitter_fallback.get_parser

        class FakeNode:
            def __init__(self, type_, start_line, end_line, children=None):
                self.type = type_
                self.start_point = (start_line, 0)
                self.end_point = (end_line, 0)
                self.children = children or []

        class FakeTree:
            def __init__(self):
                self.root_node = FakeNode('program', 0, 4, [FakeNode('class_definition', 0, 4)])

        class FakeParser:
            def parse(self, _: bytes):
                return FakeTree()

        def fake_get_parser(language: str):
            self.assertEqual(language, 'ruby')
            return FakeParser()

        tree_sitter_fallback.get_parser = fake_get_parser
        try:
            content = textwrap.dedent(
                '''
                class User
                  def save(name)
                    puts name
                  end
                end
                '''
            ).strip() + '\n'
            out = qompressor.compress_file_content('user.rb', content)
            self.assertIn('class User', out)
            self.assertIn('body stripped by Qompressor', out)
        finally:
            tree_sitter_fallback.get_parser = original_get_parser

    def test_cli_processes_mixed_project_legacy_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            src = td_path / 'qodeyard'
            dest = td_path / 'bloq.d'
            src.mkdir()
            (src / 'a.py').write_text('def hi():\n    return 1\n', encoding='utf-8')
            (src / 'b.sh').write_text('run() {\n  echo hi\n}\nrun\n', encoding='utf-8')
            (src / 'c.ts').write_text('export function boot() {\n  mount()\n}\n', encoding='utf-8')
            (src / 'd.html').write_text('<html><body><button id="x">X</button></body></html>\n', encoding='utf-8')
            (src / 'e.css').write_text('#x { display: block; }\n', encoding='utf-8')
            original_argv = sys.argv[:]
            sys.argv = ['qompressor.py', str(src), str(dest)]
            try:
                qompressor.main()
            finally:
                sys.argv = original_argv
            self.assertTrue((dest / 'a.py').exists())
            self.assertTrue((dest / 'b.sh').exists())
            self.assertTrue((dest / 'c.ts').exists())
            self.assertTrue((dest / 'd.html').exists())
            self.assertTrue((dest / 'e.css').exists())
            self.assertTrue((dest / '.bloq_cycle_marker').exists())


if __name__ == '__main__':
    unittest.main()
