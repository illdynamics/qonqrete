from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .base import Compressor
from .common import comment_marker_for_suffix, normalize_blank_lines, relative_indent, safe_trim

FUNC_START_RE = re.compile(r'^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\))?\s*\{\s*$')
SOURCE_RE = re.compile(r'^\s*(?:source|\.)\s+(.+)$')
EXPORT_RE = re.compile(r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)\s*(=.*)?$')
ASSIGN_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
SET_RE = re.compile(r'^\s*(?:set\s+-|set\s+-o|shopt\b|IFS=)')
ENV_READ_RE = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?')
CONTROL_RE = re.compile(r'^\s*(if|elif|else|fi|for|while|until|do|done|case|esac|select)\b')
COMMENT_RE = re.compile(r'^\s*#')

BUILTINS = {
    'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do', 'done', 'case', 'esac', 'function', 'local', 'declare',
    'export', 'readonly', 'unset', 'return', 'shift', 'break', 'continue', 'source', '.', 'test', '[', '[[', 'echo', 'printf',
}


class ShellCompressor(Compressor):
    name = 'shell'
    extensions = ('.sh', '.bash', '.zsh', '.ksh')

    def compress(self, file_path: Path, content: str) -> str:
        native = self._compress_with_shfmt(file_path, content)
        if native:
            self._set_last_metadata(mode='shell_native', strategy='native', tooling='shfmt -tojson')
            return native
        self._set_last_metadata(mode='shell_fallback', strategy='fallback', tooling='heuristic shell compressor', note='shfmt unavailable or failed')
        return self._compress_pythonic(file_path, content)

    def _compress_with_shfmt(self, file_path: Path, content: str) -> str | None:
        shfmt = shutil.which('shfmt')
        if not shfmt:
            return None
        try:
            proc = subprocess.run(
                [shfmt, '-filename', file_path.name, '-tojson'],
                input=content,
                text=True,
                capture_output=True,
                check=True,
            )
            ast_json = json.loads(proc.stdout)
        except Exception:
            return None

        lines = content.splitlines()
        marker = comment_marker_for_suffix(file_path.suffix)
        output: list[str] = []
        if lines and lines[0].startswith('#!'):
            output.append(lines[0])
        for line in lines[1:8]:
            if COMMENT_RE.match(line) or SET_RE.match(line):
                output.append(line)
        for stmt in ast_json.get('Stmts', []):
            node = stmt.get('Cmd') or {}
            rendered = self._render_shfmt_stmt(node, marker)
            if rendered:
                output.extend(rendered)
                output.append('')
        return normalize_blank_lines('\n'.join(output)) or self._compress_pythonic(file_path, content)

    def _render_shfmt_stmt(self, node: dict, marker: str) -> list[str]:
        typ = node.get('Type')
        if typ == 'FuncDecl':
            name = node.get('Name', {}).get('Value', 'function')
            lines = [f'{name}() {{']
            body = node.get('Body', {}).get('Stmts', [])
            summary = self._summarize_stmt_block(body)
            lines.append(f'  # summary: {summary}')
            lines.append(f'  {marker}')
            lines.append('}')
            return lines
        if typ == 'CallExpr':
            args = node.get('Args', [])
            rendered = ' '.join(arg.get('Parts', [{}])[0].get('Value', '') for arg in args if arg.get('Parts'))
            if rendered:
                return [rendered]
        return []

    def _summarize_stmt_block(self, statements: list[dict]) -> str:
        commands: list[str] = []
        for stmt in statements:
            node = stmt.get('Cmd') or {}
            if node.get('Type') == 'CallExpr':
                args = node.get('Args', [])
                if args and args[0].get('Parts'):
                    value = args[0]['Parts'][0].get('Value', '')
                    if value and value not in BUILTINS and value not in commands:
                        commands.append(value)
        if commands:
            return 'invokes: ' + ', '.join(commands[:5])
        return 'implementation stripped'

    def _compress_pythonic(self, file_path: Path, content: str) -> str:
        lines = content.splitlines()
        output: list[str] = []
        marker = comment_marker_for_suffix(file_path.suffix)
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped:
                index += 1
                continue
            if index == 0 and line.startswith('#!'):
                output.append(line)
                index += 1
                continue
            if COMMENT_RE.match(line) or SET_RE.match(line):
                output.append(line)
                index += 1
                continue
            if SOURCE_RE.match(line) or EXPORT_RE.match(line):
                output.append(line)
                index += 1
                continue
            assign_match = ASSIGN_RE.match(line)
            if assign_match and assign_match.group(1).isupper():
                output.append(line)
                index += 1
                continue
            func_match = FUNC_START_RE.match(line)
            if func_match:
                end_index, block_lines = self._collect_brace_block(lines, index)
                output.extend(self._render_function_block(block_lines, marker))
                output.append('')
                index = end_index + 1
                continue
            if CONTROL_RE.match(line):
                output.append(line)
                index += 1
                continue
            if self._looks_like_command(stripped):
                output.append(line)
                index += 1
                continue
            index += 1
        return normalize_blank_lines('\n'.join(output))

    def _collect_brace_block(self, lines: list[str], start_index: int) -> tuple[int, list[str]]:
        depth = 0
        block: list[str] = []
        end = start_index
        for idx in range(start_index, len(lines)):
            line = lines[idx]
            block.append(line)
            depth += line.count('{')
            depth -= line.count('}')
            end = idx
            if idx > start_index and depth <= 0:
                break
        return end, block

    def _render_function_block(self, block_lines: list[str], marker: str) -> list[str]:
        header = block_lines[0].rstrip()
        indent = relative_indent(block_lines[0]) + '  '
        summary = self._summarize_shell_block(block_lines[1:-1])
        return [
            header,
            indent + f'# summary: {summary}',
            indent + marker,
            block_lines[-1].rstrip() if block_lines else '}',
        ]

    def _summarize_shell_block(self, body_lines: list[str]) -> str:
        commands: list[str] = []
        reads: list[str] = []
        writes: list[str] = []
        sources: list[str] = []
        for line in body_lines:
            stripped = line.strip()
            if not stripped or COMMENT_RE.match(line):
                continue
            source_match = SOURCE_RE.match(line)
            if source_match:
                target = safe_trim(source_match.group(1), 40)
                if target not in sources:
                    sources.append(target)
            export_match = EXPORT_RE.match(line)
            if export_match:
                name = export_match.group(1)
                if name not in writes:
                    writes.append(name)
            assign_match = ASSIGN_RE.match(line)
            if assign_match and assign_match.group(1).isupper() and assign_match.group(1) not in writes:
                writes.append(assign_match.group(1))
            for env in ENV_READ_RE.findall(line):
                if env not in reads:
                    reads.append(env)
            command = self._extract_command(stripped)
            if command and command not in commands:
                commands.append(command)
        parts: list[str] = []
        if commands:
            parts.append('invokes: ' + ', '.join(commands[:5]))
        if sources:
            parts.append('sources: ' + ', '.join(sources[:3]))
        if reads:
            parts.append('reads env: ' + ', '.join(reads[:5]))
        if writes:
            parts.append('writes env: ' + ', '.join(writes[:5]))
        if not parts:
            parts.append('implementation stripped')
        return '; '.join(parts)

    def _extract_command(self, stripped: str) -> str | None:
        if stripped.startswith(('if ', 'elif ', 'while ', 'for ', 'until ', 'case ', 'do', 'done', 'fi', 'esac')):
            return None
        try:
            tokens = shlex.split(stripped, comments=True, posix=True)
        except Exception:
            tokens = stripped.split()
        if not tokens:
            return None
        token0 = tokens[0]
        if '=' in token0 and not token0.startswith(('>', '<')):
            if len(tokens) == 1:
                return None
            token0 = tokens[1]
        return token0 if token0 not in BUILTINS else None

    def _looks_like_command(self, stripped: str) -> bool:
        return self._extract_command(stripped) is not None


def get_compressor() -> Compressor:
    return ShellCompressor()
