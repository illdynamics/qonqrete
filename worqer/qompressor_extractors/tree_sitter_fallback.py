from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import comment_marker_for_suffix, normalize_blank_lines, safe_trim, signature_until_block

try:
    from tree_sitter_language_pack import get_parser  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    get_parser = None


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
        if get_parser is None:
            return TreeSitterAvailability(False, 'tree_sitter_language_pack unavailable; install requirements-optional-tree-sitter.txt to enable fallback')
        language = LANGUAGE_MAP.get(file_path.suffix.lower())
        if not language:
            return TreeSitterAvailability(False, 'no mapped tree-sitter language')
        try:
            get_parser(language)
        except Exception as exc:
            return TreeSitterAvailability(False, str(exc))
        return TreeSitterAvailability(True, None)

    def compress(self, file_path: Path, content: str) -> str | None:
        if get_parser is None:
            return None
        language = LANGUAGE_MAP.get(file_path.suffix.lower())
        if not language:
            return None
        try:
            parser = get_parser(language)
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
