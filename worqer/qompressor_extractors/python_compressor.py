from __future__ import annotations

import ast
import re
from pathlib import Path

from .base import Compressor
from .common import comment_marker_for_suffix, normalize_blank_lines

KEY_PATTERNS = [
    re.compile(r'next_id', re.IGNORECASE),
    re.compile(r'\bid\s*=', re.IGNORECASE),
    re.compile(r'\[.*\]\s*='),
    re.compile(r'\.append\('),
    re.compile(r'\.update\('),
    re.compile(r'\.insert\('),
    re.compile(r'return\s+'),
]


class PythonCompressor(Compressor):
    name = 'python'
    extensions = ('.py', '.pyi')

    def compress(self, file_path: Path, content: str) -> str:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            self._set_last_metadata(mode='python_passthrough', strategy='fallback', tooling='Python stdlib AST', note='syntax error prevented AST skeletonization')
            return content

        lines = content.splitlines()
        marker = comment_marker_for_suffix(file_path.suffix)

        class Skeletonizer(ast.NodeVisitor):
            def __init__(self) -> None:
                self.keep_intervals: list[tuple[int, int]] = []
                self.insertions: dict[int, list[str]] = {}

            def _keep(self, start: int, end: int) -> None:
                self.keep_intervals.append((start, end))

            def _insert_after(self, line_no: int, values: list[str]) -> None:
                self.insertions.setdefault(line_no, []).extend(values)

            def _is_module_level(self, node: ast.AST) -> bool:
                return getattr(node, 'col_offset', -1) == 0

            def _body_indent(self, node: ast.AST, default: int = 4) -> int:
                body = getattr(node, 'body', []) or []
                if body:
                    first_body = body[0]
                    if hasattr(first_body, 'col_offset'):
                        return max(default, first_body.col_offset)
                return default

            def _first_docstring_expr(self, node: ast.AST):
                body = getattr(node, 'body', []) or []
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    return body[0]
                return None

            def _signature_end(self, node: ast.AST) -> int:
                start = node.lineno
                end = getattr(node, 'end_lineno', node.lineno)
                for idx in range(start - 1, min(end, start + 30)):
                    if idx < len(lines) and lines[idx].rstrip().endswith(':'):
                        return idx + 1
                return node.lineno

            def _keep_decorators_and_signature(self, node: ast.AST) -> int:
                start = getattr(node, 'lineno', 1)
                decorators = getattr(node, 'decorator_list', []) or []
                if decorators:
                    start = decorators[0].lineno
                sig_end = self._signature_end(node)
                self._keep(start, sig_end)
                return sig_end

            def visit_Import(self, node: ast.Import) -> None:
                self._keep(node.lineno, node.end_lineno)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                self._keep(node.lineno, node.end_lineno)

            def visit_Assign(self, node: ast.Assign) -> None:
                if self._is_module_level(node):
                    self._keep(node.lineno, node.end_lineno)

            def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
                if self._is_module_level(node):
                    self._keep(node.lineno, node.end_lineno)

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                sig_end = self._keep_decorators_and_signature(node)
                docstring_expr = self._first_docstring_expr(node)
                if docstring_expr is not None:
                    self._keep(docstring_expr.lineno, docstring_expr.end_lineno)
                interesting = False
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign, ast.ClassDef)):
                        interesting = True
                        self.visit(child)
                if not interesting:
                    indent = ' ' * self._body_indent(node)
                    self._insert_after(sig_end, [indent + marker, indent + 'pass'])

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._process_function(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._process_function(node)

            def _process_function(self, node: ast.AST) -> None:
                sig_end = self._keep_decorators_and_signature(node)
                indent = ' ' * self._body_indent(node)
                docstring_expr = self._first_docstring_expr(node)
                if docstring_expr is not None:
                    self._keep(docstring_expr.lineno, docstring_expr.end_lineno)

                summary = self._summarize(node)
                self._insert_after(sig_end, [
                    indent + f'# summary: {summary}',
                    indent + marker,
                    indent + 'pass',
                ])

            def _summarize(self, node: ast.AST) -> str:
                body_text = ''
                body = getattr(node, 'body', []) or []
                if body:
                    start = body[0].lineno - 1
                    end = getattr(node, 'end_lineno', body[-1].end_lineno)
                    body_text = '\n'.join(lines[start:end])
                calls: list[str] = []
                seen_calls: set[str] = set()
                writes: list[str] = []
                seen_writes: set[str] = set()
                returns: str | None = None
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        try:
                            name = ast.unparse(child.func)
                        except Exception:
                            name = ''
                        if name and len(name) < 50 and name not in seen_calls:
                            calls.append(name)
                            seen_calls.add(name)
                    elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                        for target in targets:
                            try:
                                name = ast.unparse(target)
                            except Exception:
                                name = ''
                            if name and len(name) < 40 and name not in seen_writes:
                                writes.append(name)
                                seen_writes.add(name)
                    elif isinstance(child, ast.Return) and returns is None and getattr(child, 'value', None) is not None:
                        try:
                            returns = ast.unparse(child.value)
                        except Exception:
                            returns = None
                parts: list[str] = []
                if calls:
                    parts.append('calls: ' + ', '.join(calls[:5]))
                if writes:
                    parts.append('writes: ' + ', '.join(writes[:4]))
                if returns:
                    parts.append('returns: ' + returns[:60])
                for pat in KEY_PATTERNS:
                    if pat.search(body_text):
                        parts.append('keeps key mutations/returns')
                        break
                if not parts:
                    parts.append('implementation stripped')
                return '; '.join(parts)

        visitor = Skeletonizer()
        visitor.visit(tree)
        merged = self._merge_intervals(visitor.keep_intervals)
        output: list[str] = []
        current_line = 1
        for start, end in merged:
            current_line = max(current_line, start)
            for ln in range(start, min(end, len(lines)) + 1):
                output.append(lines[ln - 1])
                if ln in visitor.insertions:
                    output.extend(visitor.insertions[ln])
            output.append('')
            current_line = end + 1
        result = normalize_blank_lines('\n'.join(output))
        try:
            ast.parse(result)
            self._set_last_metadata(mode='python_ast', strategy='native', tooling='Python stdlib AST')
            return result
        except SyntaxError:
            self._set_last_metadata(mode='python_passthrough', strategy='fallback', tooling='Python stdlib AST', note='generated skeleton failed round-trip parse validation')
            return content

    def _merge_intervals(self, intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not intervals:
            return []
        intervals = sorted(intervals)
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end + 1:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))
        return merged


def get_compressor() -> Compressor:
    return PythonCompressor()
