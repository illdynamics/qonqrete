import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))

lib_ai_stub = types.ModuleType('lib_ai')
lib_ai_stub.run_ai_completion = lambda *args, **kwargs: '{"sensitivity": 5, "confidence": "medium", "rationale": ["stub"]}'
sys.modules.setdefault('lib_ai', lib_ai_stub)

import instruqtor  # noqa: E402


class InstruqtorPlanningResilienceTests(unittest.TestCase):
    def test_extract_required_files_from_task_detects_plain_and_backtick_paths(self):
        task = """
Project must contain exactly these files:
- main.py
- run.sh
- requirements.txt

Also include `app.js`.
"""
        required = instruqtor.extract_required_files_from_task(task)
        self.assertIn("main.py", required)
        self.assertIn("run.sh", required)
        self.assertIn("requirements.txt", required)
        self.assertIn("app.js", required)

    def test_extract_required_files_from_task_parses_required_files_yaml_list(self):
        task = """
required-files:
  - index.html
  - styles.css
  - app.js
"""
        required = instruqtor.extract_required_files_from_task(task)
        self.assertEqual(required, ["index.html", "styles.css", "app.js"])

    def test_parse_json_payload_repairs_truncated_object(self):
        payload = instruqtor.parse_json_payload('{"architecture_foundation": {"summary": "ok"}, "execution_blueprint": {"summary": "plan"}', expected='object')
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload['architecture_foundation']['summary'], 'ok')
        self.assertEqual(payload['execution_blueprint']['summary'], 'plan')

    def test_main_uses_deterministic_fallback_when_structured_plan_fails(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / 'worqspace'
            (workspace / 'task').mkdir(parents=True, exist_ok=True)
            (workspace / 'qontract.d').mkdir(parents=True, exist_ok=True)
            output_dir = workspace / 'briq.d'
            output_dir.mkdir(parents=True, exist_ok=True)
            input_file = workspace / 'tasq.md'
            input_file.write_text('# Goal\nBuild a recipe planner.\n', encoding='utf-8')
            (workspace / 'task' / 'task-spec.v1.json').write_text(json.dumps({'goal': 'Build a recipe planner.'}), encoding='utf-8')
            (workspace / 'qontract.d' / 'qonstrictor-result.v1.json').write_text(json.dumps({'status': 'REVIEW', 'effective_constraints': ['Stay within scope.']}), encoding='utf-8')

            sample_briqs = [
                {'title': 'Create_HTML', 'content': 'make html'},
                {'title': 'Create_JS', 'content': 'make js'},
            ]

            orig_paginated = instruqtor.generate_briqs_paginated
            orig_enforcement = instruqtor.generate_briqs_with_enforcement
            orig_structured = instruqtor.generate_structured_plan
            try:
                instruqtor.generate_briqs_paginated = lambda **kwargs: sample_briqs
                instruqtor.generate_briqs_with_enforcement = lambda **kwargs: sample_briqs
                instruqtor.generate_structured_plan = lambda **kwargs: (_ for _ in ()).throw(ValueError('forced parse fail'))

                os.chdir(PROJECT_ROOT)
                os.environ['QONQ_WORKSPACE'] = str(workspace)
                os.environ['CYCLE_NUM'] = '1'
                sys.argv = ['instruqtor.py', str(input_file), str(output_dir)]
                instruqtor.main()
            finally:
                instruqtor.generate_briqs_paginated = orig_paginated
                instruqtor.generate_briqs_with_enforcement = orig_enforcement
                instruqtor.generate_structured_plan = orig_structured
                os.chdir(original_cwd)
                os.environ.pop('QONQ_WORKSPACE', None)
                os.environ.pop('CYCLE_NUM', None)

            self.assertTrue((workspace / 'planning' / 'build-groups.v1.json').exists())
            written = sorted(output_dir.glob('*.md'))
            self.assertEqual(len(written), 2)
            self.assertIn('Grouped Scope Contract', written[0].read_text(encoding='utf-8'))

    def test_main_small_scope_skips_structured_plan_ai_fast_path(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / 'worqspace'
            (workspace / 'task').mkdir(parents=True, exist_ok=True)
            (workspace / 'qontract.d').mkdir(parents=True, exist_ok=True)
            output_dir = workspace / 'briq.d'
            output_dir.mkdir(parents=True, exist_ok=True)
            input_file = workspace / 'tasq.md'
            input_file.write_text('# Goal\nBuild a tiny API with main.py and run.sh.\n', encoding='utf-8')
            (workspace / 'task' / 'task-spec.v1.json').write_text(json.dumps({'goal': 'Build a tiny API.'}), encoding='utf-8')
            (workspace / 'qontract.d' / 'qonstrictor-result.v1.json').write_text(json.dumps({'status': 'REVIEW'}), encoding='utf-8')

            sample_briqs = [
                {'title': 'Create_Main', 'content': 'create main.py'},
                {'title': 'Create_Run', 'content': 'create run.sh'},
            ]
            structured_calls = {"count": 0}

            def _unexpected_structured_call(**kwargs):
                structured_calls["count"] += 1
                return {}

            orig_paginated = instruqtor.generate_briqs_paginated
            orig_enforcement = instruqtor.generate_briqs_with_enforcement
            orig_structured = instruqtor.generate_structured_plan
            try:
                instruqtor.generate_briqs_paginated = lambda **kwargs: sample_briqs
                instruqtor.generate_briqs_with_enforcement = lambda **kwargs: sample_briqs
                instruqtor.generate_structured_plan = _unexpected_structured_call

                os.chdir(PROJECT_ROOT)
                os.environ['QONQ_WORKSPACE'] = str(workspace)
                os.environ['CYCLE_NUM'] = '1'
                os.environ.pop('QONQ_FORCE_STRUCTURED_PLAN', None)
                sys.argv = ['instruqtor.py', str(input_file), str(output_dir)]
                instruqtor.main()
            finally:
                instruqtor.generate_briqs_paginated = orig_paginated
                instruqtor.generate_briqs_with_enforcement = orig_enforcement
                instruqtor.generate_structured_plan = orig_structured
                os.chdir(original_cwd)
                os.environ.pop('QONQ_WORKSPACE', None)
                os.environ.pop('CYCLE_NUM', None)

            self.assertEqual(structured_calls["count"], 0)
            completion = json.loads((workspace / 'planning' / 'completion-criteria.v1.json').read_text(encoding='utf-8'))
            self.assertIn("run.sh", completion.get("required_files", []))


if __name__ == '__main__':
    unittest.main()
