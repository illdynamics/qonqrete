from __future__ import annotations

import importlib
import importlib.abc
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'worqer'))


def _clear_modules(prefixes: list[str]) -> None:
    for name in list(sys.modules.keys()):
        if any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes):
            sys.modules.pop(name, None)


class _BlockingTreeSitterFinder(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.attempts = 0

    def find_spec(self, fullname, path, target=None):  # type: ignore[override]
        if fullname == 'tree_sitter_language_pack':
            self.attempts += 1
            raise ImportError('blocked tree_sitter_language_pack import for test')
        return None


class TreeSitterLazyImportRegressionTests(unittest.TestCase):
    def test_importing_qompressor_and_lib_ai_does_not_load_optional_tree_sitter(self) -> None:
        finder = _BlockingTreeSitterFinder()
        sys.meta_path.insert(0, finder)
        try:
            _clear_modules(['qompressor', 'lib_ai', 'runtime_capabilities', 'qompressor_extractors', 'tree_sitter_language_pack'])
            importlib.import_module('qompressor')
            importlib.import_module('lib_ai')
            self.assertEqual(finder.attempts, 0)
        finally:
            if finder in sys.meta_path:
                sys.meta_path.remove(finder)
            _clear_modules(['qompressor', 'lib_ai', 'runtime_capabilities', 'qompressor_extractors', 'tree_sitter_language_pack'])

    def test_availability_degrades_cleanly_and_failed_import_is_cached(self) -> None:
        finder = _BlockingTreeSitterFinder()
        sys.meta_path.insert(0, finder)
        try:
            _clear_modules(['qompressor_extractors', 'tree_sitter_language_pack'])
            fallback_mod = importlib.import_module('qompressor_extractors.tree_sitter_fallback')
            fallback_mod._reset_loader_cache_for_tests()

            fallback = fallback_mod.TreeSitterFallback()
            first = fallback.availability(Path('sample.rb'))
            second = fallback.availability(Path('sample.rb'))
            compressed = fallback.compress(Path('sample.rb'), 'class User\nend\n')

            self.assertFalse(first.available)
            self.assertFalse(second.available)
            self.assertIn('tree_sitter_language_pack unavailable', first.reason or '')
            self.assertIsNone(compressed)
            self.assertEqual(finder.attempts, 1)
        finally:
            if finder in sys.meta_path:
                sys.meta_path.remove(finder)
            _clear_modules(['qompressor_extractors', 'tree_sitter_language_pack'])


if __name__ == '__main__':
    unittest.main()
