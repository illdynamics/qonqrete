from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import comment_marker_for_suffix, normalize_blank_lines, safe_trim, signature_until_block

# Test hook and runtime cache. Keep `get_parser` as a module global so existing
# tests can patch it directly without importing the optional package.
get_parser = None
_get_parser_load_attempted = False
_get_parser_load_error: str | None = None


def _load_get_parser():
    """Lazily load the optional tree-sitter parser factory once."""
    global get_parser, _get_parser_load_attempted, _get_parser_load_error

    if get_parser is not None:
        return get_parser
    if _get_parser_load_attempted:
        return None

    _get_parser_load_attempted = True
    try:
        module = importlib.import_module('tree_sitter_language_pack')
        loaded = getattr(module, 'get_parser', None)
        if loaded is None:
            _get_parser_load_error = 'tree_sitter_language_pack missing get_parser'
            return None
        get_parser = loaded
        _get_parser_load_error = None
        return get_parser
    except Exception as exc:  # pragma: no cover - exercised via regression tests
        _get_parser_load_error = str(exc) or exc.__class__.__name__
        return None


def _tree_sitter_unavailable_reason() -> str:
    if _get_parser_load_error:
        return f"tree_sitter_language_pack unavailable: {_get_parser_load_error}"
    return 'tree_sitter_language_pack unavailable; install requirements-optional-tree-sitter.txt to enable fallback'


def optional_tree_sitter_loaded() -> bool:
    """Return True when the optional tree-sitter parser factory can be loaded."""
    return _load_get_parser() is not None


def optional_tree_sitter_unavailable_reason() -> str | None:
    """Return the current unavailability reason, loading lazily if needed."""
    if _load_get_parser() is not None:
        return None
    return _tree_sitter_unavailable_reason()


def _reset_loader_cache_for_tests() -> None:
    """Test helper to reset lazy-loader cache state."""
    global get_parser, _get_parser_load_attempted, _get_parser_load_error
    get_parser = None
    _get_parser_load_attempted = False
    _get_parser_load_error = None


LANGUAGE_MAP = {
    '.rb': 'ruby',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.c': 'c',
    '.h': 'c',
    '.hpp': 'cpp',
    '.cpp': 'cpp',
    '.cc': 'cpp',
    '.php': 'php',
    '.lua': 'lua',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.kts': 'kotlin',
    '.scala': 'scala',
    '.pl': 'perl',
}

STRUCTURAL_TYPES = {
    'class', 'class_declaration', 'class_definition', 'module', 'module_definition', 'namespace_definition',
    'function_definition', 'function_declaration', 'method_definition', 'method_declaration', 'constructor_declaration',
    'interface_declaration', 'enum_declaration', 'struct_item', 'trait_item', 'impl_item', 'impl_declaration',
    'import_declaration', 'package_clause', 'use_declaration', 'include', 'include_directive',
}


@dataclass
class TreeSitterAvailability:
    available: bool
    reason: str | None = None


class TreeSitterFallback:
    def availability(self, file_path: Path) -> TreeSitterAvailability:
        parser_factory = _load_get_parser()
        if parser_factory is None:
            return TreeSitterAvailability(False, _tree_sitter_unavailable_reason())
        language = LANGUAGE_MAP.get(file_path.suffix.lower())
        if not language:
            return TreeSitterAvailability(False, 'no mapped tree-sitter language')
        try:
            parser_factory(language)
        except Exception as exc:
            return TreeSitterAvailability(False, f"tree_sitter_language_pack unavailable: {str(exc) or exc.__class__.__name__}")
        return TreeSitterAvailability(True, None)

    def compress(self, file_path: Path, content: str) -> str | None:
        parser_factory = _load_get_parser()
        if parser_factory is None:
            return None
        language = LANGUAGE_MAP.get(file_path.suffix.lower())
        if not language:
            return None
        try:
            parser = parser_factory(language)
        except Exception:
            return None
        try:
            tree = parser.parse(content.encode('utf-8', errors='ignore'))
        except Exception:
            return None
        return self._render_tree(tree.root_node, content, file_path)

    def _render_tree(self, root_node: Any, content: str, file_path: Path) -> str:
        marker = comment_marker_for_suffix(file_path.suffix)
        lines = content.splitlines()
        out: list[str] = []
        for child in getattr(root_node, 'children', []):
            rendered = self._render_node(child, lines, marker)
            if rendered:
                out.extend(rendered)
                out.append('')
        return normalize_blank_lines('\n'.join(out))

    def _render_node(self, node: Any, lines: list[str], marker: str) -> list[str]:
        node_type = getattr(node, 'type', '')
        if node_type not in STRUCTURAL_TYPES and 'function' not in node_type and 'class' not in node_type and 'import' not in node_type and 'module' not in node_type:
            return []
        start_line = getattr(node, 'start_point', (0, 0))[0]
        end_line = getattr(node, 'end_point', (start_line, 0))[0]
        block = lines[start_line:end_line + 1]
        if not block:
            return []
        header = signature_until_block(self._first_signature(block))
        indent = re.match(r'^\s*', block[0]).group(0) + '  '
        summary = self._summarize(node, block)
        closing = self._closing_line(block)
        if '{' in ''.join(block[:3]) or node_type.endswith(('definition', 'declaration', 'item')):
            return [header, indent + f'// summary: {summary}', indent + marker, closing]
        return [safe_trim(' '.join(line.strip() for line in block if line.strip()), 140)]

    def _first_signature(self, block: list[str]) -> str:
        collected: list[str] = []
        for line in block[:12]:
            collected.append(line.strip())
            if '{' in line or line.strip().endswith(('do', ':')):
                break
        return ' '.join(collected)

    def _closing_line(self, block: list[str]) -> str:
        for line in reversed(block):
            stripped = line.strip()
            if stripped in {'}', 'end'} or stripped.startswith('end'):
                return line.rstrip()
        return '}'

    def _summarize(self, node: Any, block: list[str]) -> str:
        node_type = getattr(node, 'type', 'node')
        names = []
        for child in getattr(node, 'children', []):
            ctype = getattr(child, 'type', '')
            if 'identifier' in ctype or ctype == 'name' or ctype.endswith('_name'):
                snippet = safe_trim(' '.join(line.strip() for line in block[:2]), 80)
                if snippet and snippet not in names:
                    names.append(snippet)
                    break
        parts = [f'{node_type} skeleton']
        if names:
            parts.append('signature: ' + names[0])
        return '; '.join(parts)


def fallback_compress(file_path: Path, content: str) -> str | None:
    return TreeSitterFallback().compress(file_path, content)
