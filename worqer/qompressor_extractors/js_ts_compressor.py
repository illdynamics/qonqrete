from __future__ import annotations

import re
from pathlib import Path

from node_tooling import helper_capabilities, run_node_helper

from .base import Compressor
from .common import comment_marker_for_suffix, normalize_blank_lines, safe_trim

IMPORT_EXPORT_RE = re.compile(r'^\s*(?:import|export)\b')
FUNC_START_RE = re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(')
CLASS_START_RE = re.compile(r'^\s*(?:export\s+default\s+|export\s+)?class\s+[A-Za-z_$][\w$]*')
INTERFACE_START_RE = re.compile(r'^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)')
TYPE_START_RE = re.compile(r'^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=')
ENUM_START_RE = re.compile(r'^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)')
ARROW_START_RE = re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?.*=>\s*\{')
OBJ_START_RE = re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\{\s*$')
SIMPLE_CONST_RE = re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^\n;]+);?\s*$')
METHOD_RE = re.compile(r'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+|get\s+|set\s+)*(?:#?[A-Za-z_$][\w$]*|constructor)\s*\([^;]*\)\s*(?::\s*[^=\{]+)?\s*\{\s*$')
FIELD_RE = re.compile(r'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)?[#A-Za-z_$][\w$]*\s*(?::\s*[^=;]+)?(?:\s*=\s*[^;]+)?;\s*$')
COMMENT_RE = re.compile(r'^\s*(?://|/\*|\*)')
SELECTOR_RE = re.compile(r'(?:querySelector|querySelectorAll|getElementById|getElementsByClassName)\s*\(([^\)]+)\)')
EVENT_RE = re.compile(r'\.addEventListener\s*\(\s*["\']([^"\']+)["\']')
STORAGE_READ_RE = re.compile(r'\b(?:window\.)?(?:localStorage|sessionStorage)\.(?:getItem|key)\s*\(')
STORAGE_WRITE_RE = re.compile(r'\b(?:window\.)?(?:localStorage|sessionStorage)\.(?:setItem|removeItem|clear)\s*\(')


class JsTsCompressor(Compressor):
    name = 'js_ts'
    extensions = ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx')

    def compress(self, file_path: Path, content: str) -> str:
        if helper_capabilities().get('typescript'):
            try:
                data = run_node_helper('compress-js-ts', stdin_text=content, args=[str(file_path)])
                output = data.get('output', '')
                if output.strip():
                    self._set_last_metadata(mode='js_ts_native', strategy='native', tooling='TypeScript Compiler API via Node helper')
                    return output
            except Exception as exc:
                self._set_last_metadata(mode='js_ts_fallback', strategy='fallback', tooling='heuristic JS/TS compressor', note=f'native TypeScript helper failed: {exc}')
                return self._compress_fallback(content, file_path)
        self._set_last_metadata(mode='js_ts_fallback', strategy='fallback', tooling='heuristic JS/TS compressor', note='native TypeScript helper unavailable')
        return self._compress_fallback(content, file_path)

    def _compress_fallback(self, content: str, file_path: Path) -> str:
        lines = content.splitlines()
        out: list[str] = []
        idx = 0
        marker = comment_marker_for_suffix(file_path.suffix)
        while idx < len(lines):
            line = lines[idx]
            stripped = line.strip()
            if not stripped:
                idx += 1
                continue
            if COMMENT_RE.match(line):
                out.append(line)
                idx += 1
                continue
            if IMPORT_EXPORT_RE.match(line):
                block_end = self._collect_until_semicolon(lines, idx)
                out.extend(lines[idx:block_end + 1])
                out.append('')
                idx = block_end + 1
                continue
            if FUNC_START_RE.match(line) or ARROW_START_RE.match(line):
                end, block = self._collect_brace_block(lines, idx)
                out.extend(self._render_function(block, marker))
                out.append('')
                idx = end + 1
                continue
            if CLASS_START_RE.match(line):
                end, block = self._collect_brace_block(lines, idx)
                out.extend(self._render_class(block, marker))
                out.append('')
                idx = end + 1
                continue
            if INTERFACE_START_RE.match(line) or ENUM_START_RE.match(line):
                end, block = self._collect_brace_block(lines, idx)
                out.extend(block)
                out.append('')
                idx = end + 1
                continue
            if TYPE_START_RE.match(line):
                end, block = self._collect_type_block(lines, idx)
                out.extend(block)
                out.append('')
                idx = end + 1
                continue
            simple_const = SIMPLE_CONST_RE.match(line)
            if simple_const and len(stripped) < 140:
                out.append(line)
                idx += 1
                continue
            if OBJ_START_RE.match(line):
                end, block = self._collect_brace_block(lines, idx)
                out.extend(self._render_object(block, marker))
                out.append('')
                idx = end + 1
                continue
            idx += 1
        return normalize_blank_lines('\n'.join(out))

    def _collect_until_semicolon(self, lines: list[str], start: int) -> int:
        for idx in range(start, min(len(lines), start + 30)):
            if ';' in lines[idx]:
                return idx
        return start

    def _collect_type_block(self, lines: list[str], start: int) -> tuple[int, list[str]]:
        if '{' not in lines[start]:
            end = self._collect_until_semicolon(lines, start)
            return end, lines[start:end + 1]
        return self._collect_brace_block(lines, start)

    def _collect_brace_block(self, lines: list[str], start: int) -> tuple[int, list[str]]:
        depth = 0
        seen_brace = False
        block: list[str] = []
        for idx in range(start, len(lines)):
            line = lines[idx]
            block.append(line)
            clean = self._strip_strings_and_comments(line)
            depth += clean.count('{')
            depth -= clean.count('}')
            if '{' in clean:
                seen_brace = True
            if seen_brace and depth <= 0:
                return idx, block
        return len(lines) - 1, block

    def _strip_strings_and_comments(self, line: str) -> str:
        line = re.sub(r'//.*$', '', line)
        line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        line = re.sub(r"'(?:\\.|[^'\\])*'", "''", line)
        line = re.sub(r'`(?:\\.|[^`\\])*`', '``', line)
        return line

    def _render_function(self, block: list[str], marker: str) -> list[str]:
        header_lines = self._header_lines(block)
        indent = self._body_indent(block)
        summary = self._summarize(block)
        closing = self._closing_line(block)
        return header_lines + [indent + f'// summary: {summary}', indent + marker, closing]

    def _render_class(self, block: list[str], marker: str) -> list[str]:
        out = self._header_lines(block)
        class_indent = self._body_indent(block)
        members = self._extract_class_members(block[1:-1], class_indent, marker)
        if members:
            out.extend(members)
        else:
            out.append(class_indent + '// summary: implementation stripped')
            out.append(class_indent + marker)
        out.append(self._closing_line(block))
        return out

    def _render_object(self, block: list[str], marker: str) -> list[str]:
        header = self._header_lines(block)
        indent = self._body_indent(block)
        keys: list[str] = []
        for line in block[1:-1]:
            stripped = line.strip().rstrip(',')
            if not stripped or stripped.startswith('//'):
                continue
            m = re.match(r'([A-Za-z_$][\w$-]*|["\'][^"\']+["\'])\s*:', stripped)
            if m:
                keys.append(safe_trim(m.group(1), 40))
        summary = 'keys: ' + ', '.join(keys[:8]) if keys else 'object/config stripped'
        return header + [indent + f'// summary: {summary}', indent + marker, self._closing_line(block)]

    def _header_lines(self, block: list[str]) -> list[str]:
        collected: list[str] = []
        for line in block:
            collected.append(line.rstrip())
            if '{' in self._strip_strings_and_comments(line):
                break
        return collected

    def _closing_line(self, block: list[str]) -> str:
        return block[-1].rstrip() if block else '}'

    def _body_indent(self, block: list[str]) -> str:
        if len(block) > 1:
            line = block[1]
            return line[: len(line) - len(line.lstrip())] or '  '
        line = block[0]
        return (line[: len(line) - len(line.lstrip())] + '  ') or '  '

    def _extract_class_members(self, lines: list[str], base_indent: str, marker: str) -> list[str]:
        out: list[str] = []
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            stripped = line.strip()
            if not stripped:
                idx += 1
                continue
            if COMMENT_RE.match(line):
                out.append(line.rstrip())
                idx += 1
                continue
            if FIELD_RE.match(line):
                out.append(line.rstrip())
                idx += 1
                continue
            if METHOD_RE.match(line):
                end, block = self._collect_brace_block(lines, idx)
                header = self._header_lines(block)
                summary = self._summarize(block)
                out.extend(header)
                out.append(self._body_indent(block) + f'// summary: {summary}')
                out.append(self._body_indent(block) + marker)
                out.append(self._closing_line(block))
                out.append('')
                idx = end + 1
                continue
            idx += 1
        return out

    def _summarize(self, block: list[str]) -> str:
        text = '\n'.join(block)
        selectors = []
        for match in SELECTOR_RE.findall(text):
            value = safeTrim(match.strip().strip('"\''), 40)
            if value not in selectors:
                selectors.append(value)
        events = []
        for event in EVENT_RE.findall(text):
            if event not in events:
                events.append(event)
        storage: list[str] = []
        if STORAGE_READ_RE.search(text):
            storage.append('reads storage')
        if STORAGE_WRITE_RE.search(text):
            storage.append('writes storage')
        calls = []
        for call in re.findall(r'\b([A-Za-z_$][\w$]*)\s*\(', text):
            if call not in {'if', 'for', 'while', 'switch', 'catch', 'function'} and call not in calls:
                calls.append(call)
        parts: list[str] = []
        if calls:
            parts.append('calls: ' + ', '.join(calls[:6]))
        if selectors:
            parts.append('selectors: ' + ', '.join(selectors[:4]))
        if events:
            parts.append('events: ' + ', '.join(events[:4]))
        if storage:
            parts.extend(storage)
        if not parts:
            parts.append('implementation stripped')
        return '; '.join(parts)


def get_compressor() -> Compressor:
    return JsTsCompressor()


def safeTrim(text: str, max_len: int) -> str:
    value = safe_trim(text, max_len)
    return value
