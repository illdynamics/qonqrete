from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import types
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))
sys.path.insert(0, str(PROJECT_ROOT / 'qrane'))

import context_bundle  # noqa: E402
import construqtor  # noqa: E402
import lib_ai  # noqa: E402
import qontextor  # noqa: E402
import qontrabender  # noqa: E402
import qrane  # noqa: E402


class ContextBundleFidelityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.qodeyard = self.base / 'qodeyard'
        self.bloq = self.base / 'bloq.d'
        self.qontext = self.base / 'qontext.d'
        self.qache = self.base / 'qache.d'
        self.qodeyard.mkdir(parents=True, exist_ok=True)
        self.bloq.mkdir(parents=True, exist_ok=True)
        self.qontext.mkdir(parents=True, exist_ok=True)
        self.qache.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write(self, root: Path, rel: str, content: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + '\n', encoding='utf-8')
        return path

    def test_repair_targets_full_with_all_context_tools_enabled(self) -> None:
        self._write(self.qodeyard, 'pkg/target.py', 'def do_work():\n    return 1')
        self._write(self.qodeyard, 'pkg/neighbor.py', 'def helper():\n    return 2')
        self._write(self.bloq, 'pkg/neighbor.py', '# QONQ_FIDELITY: skeleton\ndef helper(): ...')
        qctx_target = self.qontext / 'pkg/target.py.q.yaml'
        qctx_target.parent.mkdir(parents=True, exist_ok=True)
        qctx_target.write_text(
            yaml.safe_dump({'file_path': 'pkg/target.py', 'dependencies': ['pkg/neighbor.py'], 'inbound_refs': []}),
            encoding='utf-8',
        )
        qctx_neighbor = self.qontext / 'pkg/neighbor.py.q.yaml'
        qctx_neighbor.parent.mkdir(parents=True, exist_ok=True)
        qctx_neighbor.write_text(
            yaml.safe_dump({'file_path': 'pkg/neighbor.py', 'dependencies': [], 'inbound_refs': ['pkg/target.py']}),
            encoding='utf-8',
        )

        bundle = context_bundle.build_context_bundle(
            qodeyard_path=self.qodeyard,
            bloq_path=self.bloq,
            qontext_path=self.qontext,
            editable_targets=['pkg/target.py'],
            repair_targets=['pkg/target.py'],
            use_qompressor=True,
            use_qontextor=True,
            context_strategy='repair_truth',
            max_neighbor_full_chars=200000,
            max_full_neighbors=10,
            max_indirect=10,
        )
        context_bundle.validate_bundle_invariants(
            bundle=bundle,
            qodeyard_path=self.qodeyard,
            repair_targets=['pkg/target.py'],
        )

        target_items = [item for item in bundle if item.rel_path == 'pkg/target.py']
        self.assertTrue(target_items)
        self.assertTrue(any(item.source == 'qodeyard' for item in target_items))
        self.assertTrue(any(item.fidelity == context_bundle.FULL_HOTSET for item in target_items))

    def test_qompressor_never_replaces_global_qodeyard_context(self) -> None:
        self._write(self.qodeyard, 'main.py', 'def run():\n    return 42')
        self._write(self.qodeyard, 'big_dep.py', 'x = 1\n' * 80000)
        self._write(self.bloq, 'big_dep.py', '# QONQ_FIDELITY: skeleton\ndef run(): ...')
        (self.qontext / 'main.py.q.yaml').write_text(
            yaml.safe_dump({'file_path': 'main.py', 'dependencies': ['big_dep.py'], 'inbound_refs': []}),
            encoding='utf-8',
        )
        (self.qontext / 'big_dep.py.q.yaml').write_text(
            yaml.safe_dump({'file_path': 'big_dep.py', 'dependencies': [], 'inbound_refs': ['main.py']}),
            encoding='utf-8',
        )

        bundle = context_bundle.build_context_bundle(
            qodeyard_path=self.qodeyard,
            bloq_path=self.bloq,
            qontext_path=self.qontext,
            editable_targets=['main.py'],
            repair_targets=['main.py'],
            use_qompressor=True,
            use_qontextor=True,
            context_strategy='repair_truth',
            max_neighbor_full_chars=100,
            max_full_neighbors=1,
            max_indirect=10,
        )
        main_items = [item for item in bundle if item.rel_path == 'main.py']
        self.assertTrue(main_items)
        self.assertTrue(all(item.source == 'qodeyard' for item in main_items if item.editable))

        sections = context_bundle.build_bundle_prompt_sections(bundle=bundle, qache_dir=self.qache)
        structural = '\n'.join(s['content'] for s in sections if s['section_type'] == 'structural_context')
        editable = '\n'.join(s['content'] for s in sections if s['section_type'] == 'full_editable_context')
        self.assertIn('STRUCTURAL CONTEXT', structural)
        self.assertIn('FULL EDITABLE CONTEXT', editable)
        self.assertIn('main.py', editable)
        self.assertNotIn('big_dep.py\nSOURCE: qodeyard\nFIDELITY: full_hotset', editable)

    def test_qontextor_selects_neighbors_not_source_replacement(self) -> None:
        self._write(self.qodeyard, 'a.py', 'from b import f\n\ndef a():\n    return f()')
        self._write(self.qodeyard, 'b.py', 'def f():\n    return 1')
        (self.qontext / 'a.py.q.yaml').write_text(
            yaml.safe_dump({'file_path': 'a.py', 'dependencies': ['b.py'], 'inbound_refs': []}),
            encoding='utf-8',
        )
        (self.qontext / 'b.py.q.yaml').write_text(
            yaml.safe_dump({'file_path': 'b.py', 'dependencies': [], 'inbound_refs': ['a.py']}),
            encoding='utf-8',
        )

        bundle = context_bundle.build_context_bundle(
            qodeyard_path=self.qodeyard,
            bloq_path=self.bloq,
            qontext_path=self.qontext,
            editable_targets=['a.py'],
            repair_targets=[],
            use_qompressor=True,
            use_qontextor=True,
            context_strategy='hybrid_fidelity',
            max_neighbor_full_chars=200000,
            max_full_neighbors=10,
            max_indirect=10,
        )

        a_item = next(item for item in bundle if item.rel_path == 'a.py')
        self.assertEqual(a_item.fidelity, context_bundle.FULL_HOTSET)
        self.assertTrue(a_item.editable)
        b_items = [item for item in bundle if item.rel_path == 'b.py']
        self.assertTrue(b_items)
        self.assertTrue(any(item.fidelity == context_bundle.FULL_NEIGHBOR for item in b_items))
        self.assertTrue(all(not item.editable for item in b_items))


class QontrabenderProviderAwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.qodeyard = self.base / 'qodeyard'
        self.bloq = self.base / 'bloq.d'
        self.qontext = self.base / 'qontext.d'
        self.qache = self.base / 'qache.d'
        for p in (self.qodeyard, self.bloq, self.qontext, self.qache):
            p.mkdir(parents=True, exist_ok=True)

        (self.qodeyard / 'app.py').write_text('def run():\n    return 1\n', encoding='utf-8')
        (self.bloq / 'app.py').write_text('# QONQ_FIDELITY: skeleton\ndef run(): ...\n', encoding='utf-8')
        (self.qontext / 'app.py.q.yaml').write_text(
            yaml.safe_dump({'file_path': 'app.py', 'dependencies': [], 'inbound_refs': []}),
            encoding='utf-8',
        )
        (self.base / 'config.yaml').write_text(
            yaml.safe_dump(
                {
                    'agents': {
                        'construqtor': {'provider': 'deepseek', 'model': 'deepseek-chat'},
                        'qontrabender': {
                            'provider_cache': {
                                'enabled': True,
                                'gemini_explicit_enabled': True,
                                'anthropic_cache_control_enabled': True,
                                'openai_stable_prefix_enabled': True,
                                'deepseek_stable_prefix_enabled': True,
                            }
                        },
                    },
                    'options': {
                        'use_qompressor': True,
                        'use_qontextor': True,
                        'use_qontrabender': True,
                    },
                },
                sort_keys=False,
            ),
            encoding='utf-8',
        )

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_qontrabender_runs_non_gemini_local_bundle(self) -> None:
        qb = qontrabender.Qontrabender(
            self.base,
            mode='local_smart',
            qodeyard_path=self.qodeyard,
            bloq_path=self.bloq,
            qontext_path=self.qontext,
            qache_path=self.qache,
        )
        with patch.dict(
            os.environ,
            {
                'QONQ_CONSTRUQTOR_PROVIDER': 'deepseek',
                'QONQ_CONSTRUQTOR_MODEL': 'deepseek-chat',
                'QONQ_PASS_KIND': 'build',
                'QONQ_REPAIR_MODE': '0',
                'CYCLE_NUM': '1',
            },
            clear=False,
        ):
            ok, backend = qontrabender._run_provider_aware_pipeline_bundle(qb)

        self.assertTrue(ok)
        self.assertEqual(backend, 'stable_prefix_auto')
        self.assertTrue((self.qache / 'cached_payload.txt').exists())
        self.assertTrue((self.qache / 'hotset_payload.txt').exists())
        self.assertTrue((self.qache / 'context_bundle_manifest.json').exists())
        self.assertFalse((self.qache / 'provider_cache.json').exists())
        manifest = json.loads((self.qache / 'context_bundle_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['provider'], 'deepseek')
        self.assertEqual(manifest['model'], 'deepseek-chat')
        self.assertEqual(manifest['cache_backend'], 'stable_prefix_auto')
        self.assertIn('cache_backend_reason', manifest)
        self.assertIn('source_hashes', manifest)

    def test_qontrabender_gemini_explicit_not_faked_for_gemini(self) -> None:
        cfg = {
            'enabled': True,
            'gemini_explicit_enabled': True,
            'anthropic_cache_control_enabled': True,
            'openai_stable_prefix_enabled': True,
            'deepseek_stable_prefix_enabled': True,
        }
        self.assertEqual(context_bundle.resolve_qontrabender_cache_backend(provider='gemini', provider_cache_cfg=cfg), 'stable_prefix_auto')
        self.assertNotEqual(context_bundle.resolve_qontrabender_cache_backend(provider='deepseek', provider_cache_cfg=cfg), 'gemini_explicit')
        self.assertNotEqual(context_bundle.resolve_qontrabender_cache_backend(provider='openai', provider_cache_cfg=cfg), 'gemini_explicit')
        self.assertNotEqual(context_bundle.resolve_qontrabender_cache_backend(provider='anthropic', provider_cache_cfg=cfg), 'gemini_explicit')

    def test_qrane_does_not_skip_qontrabender_for_non_gemini(self) -> None:
        should_skip = qrane.should_skip_agent(
            name='qontrabender',
            use_qompressor=True,
            use_qontextor=True,
            use_qontrabender=True,
            is_repair_pass=False,
            construqtor_provider='deepseek',
        )
        self.assertFalse(should_skip)


class ProviderCacheDispatchTests(unittest.TestCase):
    def test_anthropic_cache_control_layout(self) -> None:
        captured: dict[str, object] = {}

        class FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                response = types.SimpleNamespace()
                response.stop_reason = 'end_turn'
                response.content = [types.SimpleNamespace(type='text', text='ok')]
                response.usage = types.SimpleNamespace(input_tokens=10, output_tokens=4, cache_read_input_tokens=6)
                return response

        class FakeClient:
            def __init__(self, timeout=None):
                self.messages = FakeMessages()

        fake_mod = types.SimpleNamespace(Anthropic=FakeClient, APITimeoutError=RuntimeError)
        with patch.object(lib_ai, '_import_anthropic', return_value=fake_mod):
            res = lib_ai._dispatch_anthropic(
                model='claude-sonnet-4',
                messages=[
                    {'role': 'system', 'content': 'base system rules'},
                    {'role': 'user', 'content': 'volatile hotset text'},
                ],
                output_tokens=128,
                timeout=10,
                stream_callback=False,
                cache_envelope={
                    'backend': 'anthropic_cache_control',
                    'stable_prefix': 'stable payload block',
                    'anthropic_cache_control': {'enabled': True, 'ttl_minutes': 60},
                },
            )

        self.assertEqual(res.text, 'ok')
        self.assertIsInstance(captured.get('system'), list)
        first_block = captured['system'][0]
        self.assertEqual(first_block.get('type'), 'text')
        self.assertEqual(first_block.get('text'), 'stable payload block')
        self.assertIn('cache_control', first_block)
        self.assertEqual(first_block['cache_control'].get('type'), 'ephemeral')
        self.assertEqual(captured['messages'][0]['content'], 'volatile hotset text')

    def test_openai_deepseek_stable_prefix_ordering(self) -> None:
        s1 = [
            lib_ai.PromptSection(label='core', content='SYSTEM\n', section_type='instructions'),
            lib_ai.PromptSection(label='stable', content='CACHED\n', section_type='cached_stable_context'),
            lib_ai.PromptSection(label='hotset', content='HOTSET A\n', section_type='hotset_payload'),
        ]
        s2 = [
            lib_ai.PromptSection(label='core', content='SYSTEM\n', section_type='instructions'),
            lib_ai.PromptSection(label='stable', content='CACHED\n', section_type='cached_stable_context'),
            lib_ai.PromptSection(label='hotset', content='HOTSET B\n', section_type='hotset_payload'),
        ]
        p1 = lib_ai._stable_prefix_from_sections(s1)
        p2 = lib_ai._stable_prefix_from_sections(s2)
        self.assertEqual(p1, p2)

        captured: dict[str, object] = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                message = types.SimpleNamespace(content='ok', tool_calls=None)
                choice = types.SimpleNamespace(message=message, finish_reason='stop')
                usage = types.SimpleNamespace(model_dump=lambda: {'prompt_tokens': 1, 'completion_tokens': 1})
                return types.SimpleNamespace(choices=[choice], usage=usage)

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeClient:
            def __init__(self):
                self.chat = FakeChat()

        with patch.object(lib_ai, '_openai_client_for_provider', return_value=FakeClient()):
            lib_ai._dispatch_openai_compatible(
                provider='deepseek',
                model='deepseek-chat',
                messages=[{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}],
                output_tokens=64,
                timeout=10,
                stream_callback=False,
                cache_envelope={'prompt_cache_key': 'must_not_be_used_for_deepseek'},
            )
        self.assertNotIn('prompt_cache_key', captured)


class QontextorAndWritebackGuardsTests(unittest.TestCase):
    def test_qontextor_regenerates_changed_qontext(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qodeyard = base / 'qodeyard'
            qontext = base / 'qontext.d'
            qodeyard.mkdir(parents=True, exist_ok=True)
            qontext.mkdir(parents=True, exist_ok=True)
            src = qodeyard / 'mod.py'
            src.write_text('def f():\n    return 1\n', encoding='utf-8')

            qontextor.run_initial_scan(qodeyard, qontext, {'provider': 'local', 'local_mode': 'complex'})
            first = (qontext / 'mod.py.q.yaml').read_text(encoding='utf-8')
            src.write_text('def f():\n    return 2\n\ndef g():\n    return f()\n', encoding='utf-8')
            qontextor.run_initial_scan(qodeyard, qontext, {'provider': 'local', 'local_mode': 'complex'})
            second = (qontext / 'mod.py.q.yaml').read_text(encoding='utf-8')

            self.assertNotEqual(first, second)
            self.assertIn('g', second)

    def test_qontextor_stale_delete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qodeyard = base / 'qodeyard'
            qontext = base / 'qontext.d'
            qodeyard.mkdir(parents=True, exist_ok=True)
            qontext.mkdir(parents=True, exist_ok=True)
            src = qodeyard / 'mod.py'
            src.write_text('def f():\n    return 1\n', encoding='utf-8')

            qontextor._PROJECT_GRAPH_CACHE.clear()
            qontextor.run_initial_scan(qodeyard, qontext, {'provider': 'local', 'local_mode': 'complex'})
            self.assertTrue((qontext / 'mod.py.q.yaml').exists())

            src.unlink()
            summary = base / 'changed.md'
            summary.write_text('Changed: `mod.py`\n', encoding='utf-8')
            qontextor._PROJECT_GRAPH_CACHE.clear()
            qontextor.run_update_scan(summary, qodeyard, qontext, {'provider': 'local', 'local_mode': 'complex'})
            self.assertFalse((qontext / 'mod.py.q.yaml').exists())

    def test_qontextor_related_files_cli(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qodeyard = base / 'qodeyard'
            qontext = base / 'qontext.d'
            qodeyard.mkdir(parents=True, exist_ok=True)
            qontext.mkdir(parents=True, exist_ok=True)
            (qodeyard / 'a.py').write_text('from b import f\n\ndef a():\n    return f()\n', encoding='utf-8')
            (qodeyard / 'b.py').write_text('def f():\n    return 1\n', encoding='utf-8')
            qontextor.run_initial_scan(qodeyard, qontext, {'provider': 'local', 'local_mode': 'complex'})
            proc = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / 'worqer' / 'qontextor.py'), 'related', '--files', 'a.py', '--depth', '2', '--json'],
                cwd=base,
                env={**os.environ, 'PYTHONPATH': str(PROJECT_ROOT / 'worqer')},
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(proc.stdout)
            self.assertIn('direct_dependencies', payload)
            self.assertIn('b.py', payload['direct_dependencies'])

    def test_skeleton_writeback_guard_still_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            qodeyard = Path(td)
            payload = """
```foo.py
# QONQ_FIDELITY: skeleton
# QONQ_DO_NOT_WRITE_BACK: true
print('x')
```
"""
            files = construqtor._extract_ai_output_files(payload, qodeyard)
            self.assertEqual(files, {})


if __name__ == '__main__':
    unittest.main()
