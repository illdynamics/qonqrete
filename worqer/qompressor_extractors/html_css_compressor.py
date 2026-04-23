from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

from node_tooling import helper_capabilities, run_node_helper

from .base import Compressor
from .common import comment_marker_for_suffix, normalize_blank_lines, safe_trim

VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
TEXT_TAGS = {'title', 'button', 'label', 'legend', 'option', 'textarea', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}


class HtmlSkeletonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.depth = 0
        self._inline_skip_tags: list[str] = []

    def handle_decl(self, decl: str) -> None:
        self.lines.append(f'<!{decl}>')

    def handle_comment(self, data: str) -> None:
        text = safe_trim(data, 100)
        if text:
            self.lines.append(self._indent() + f'<!-- {text} -->')

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        rendered = self._render_start_tag(tag, attrs)
        self.lines.append(self._indent() + rendered)
        if tag in {'script', 'style'}:
            self._inline_skip_tags.append(tag)
        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        rendered = self._render_start_tag(tag, attrs, self_closing=True)
        self.lines.append(self._indent() + rendered)

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID_TAGS:
            self.depth = max(0, self.depth - 1)
            self.lines.append(self._indent() + f'</{tag}>')
        if self._inline_skip_tags and self._inline_skip_tags[-1] == tag:
            self._inline_skip_tags.pop()

    def handle_data(self, data: str) -> None:
        text = safe_trim(data, 80)
        if not text:
            return
        if self._inline_skip_tags:
            self.lines.append(self._indent() + '<!-- inline content stripped by Qompressor -->')
            return
        if getattr(self, 'lasttag', None) in TEXT_TAGS:
            self.lines.append(self._indent() + html.escape(text))

    def _render_start_tag(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool = False) -> str:
        keep_order = ['id', 'class', 'name', 'type', 'role', 'method', 'action', 'href', 'src', 'rel', 'for', 'value', 'placeholder']
        kept: list[str] = []
        attr_map = {k: v for k, v in attrs}
        for key in keep_order:
            if key in attr_map and attr_map[key] not in (None, ''):
                kept.append(f'{key}="{html.escape(attr_map[key], quote=True)}"')
        for key, value in attrs:
            if key.startswith('data-') and value not in (None, ''):
                kept.append(f'{key}="{html.escape(value, quote=True)}"')
        joined = (' ' + ' '.join(dict.fromkeys(kept))) if kept else ''
        closing = ' />' if self_closing or tag in VOID_TAGS else '>'
        return f'<{tag}{joined}{closing}'

    def _indent(self) -> str:
        return '  ' * self.depth


class HtmlCssCompressor(Compressor):
    name = 'html_css'
    extensions = ('.html', '.htm', '.css', '.scss', '.sass', '.less')

    def compress(self, file_path: Path, content: str) -> str:
        suffix = file_path.suffix.lower()
        if suffix in {'.html', '.htm'}:
            if helper_capabilities().get('parse5'):
                try:
                    data = run_node_helper('compress-html', stdin_text=content, args=[str(file_path)])
                    output = data.get('output', '')
                    if output.strip():
                        self._set_last_metadata(mode='html_native', strategy='native', tooling='parse5 via Node helper')
                        return output
                except Exception as exc:
                    self._set_last_metadata(mode='html_fallback', strategy='fallback', tooling='fallback HTML parser', note=f'native parse5 helper failed: {exc}')
                    return self._compress_html_fallback(content)
            self._set_last_metadata(mode='html_fallback', strategy='fallback', tooling='fallback HTML parser', note='native parse5 helper unavailable')
            return self._compress_html_fallback(content)
        if helper_capabilities().get('postcss'):
            try:
                data = run_node_helper('compress-css', stdin_text=content, args=[str(file_path)])
                output = data.get('output', '')
                if output.strip():
                    self._set_last_metadata(mode='css_native', strategy='native', tooling='PostCSS via Node helper')
                    return output
            except Exception as exc:
                self._set_last_metadata(mode='css_fallback', strategy='fallback', tooling='fallback CSS parser', note=f'native PostCSS helper failed: {exc}')
                return self._compress_css_fallback(file_path, content)
        self._set_last_metadata(mode='css_fallback', strategy='fallback', tooling='fallback CSS parser', note='native PostCSS helper unavailable')
        return self._compress_css_fallback(file_path, content)

    def _compress_html_fallback(self, content: str) -> str:
        parser = HtmlSkeletonParser()
        parser.feed(content)
        parser.close()
        return normalize_blank_lines('\n'.join(parser.lines))

    def _compress_css_fallback(self, file_path: Path, content: str) -> str:
        text = re.sub(r'/\*.*?\*/', lambda m: '' if '\n' not in m.group(0) else '\n', content, flags=re.S)
        text = re.sub(r'//.*$', '', text, flags=re.M)
        marker = comment_marker_for_suffix(file_path.suffix)
        out: list[str] = []
        idx = 0
        length = len(text)
        while idx < length:
            while idx < length and text[idx].isspace():
                idx += 1
            if idx >= length:
                break
            if text.startswith('@import', idx):
                end = text.find(';', idx)
                if end == -1:
                    end = length - 1
                out.append(text[idx:end + 1].strip())
                out.append('')
                idx = end + 1
                continue
            if text.startswith('@media', idx):
                end, block = self._collect_css_block(text, idx)
                out.extend(self._render_media_block(block, marker))
                out.append('')
                idx = end
                continue
            if '{' in text[idx:]:
                end, block = self._collect_css_block(text, idx)
                out.extend(self._render_rule_block(block, marker))
                out.append('')
                idx = end
                continue
            break
        return normalize_blank_lines('\n'.join(out))

    def _collect_css_block(self, text: str, start: int) -> tuple[int, str]:
        depth = 0
        in_quote: str | None = None
        idx = start
        while idx < len(text):
            ch = text[idx]
            if in_quote:
                if ch == in_quote and text[idx - 1] != '\\':
                    in_quote = None
            else:
                if ch in {'"', "'"}:
                    in_quote = ch
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return idx + 1, text[start:idx + 1]
            idx += 1
        return len(text), text[start:]

    def _render_media_block(self, block: str, marker: str) -> list[str]:
        header, body = block.split('{', 1)
        inner = body.rsplit('}', 1)[0]
        out = [header.strip() + ' {']
        for selector, props in self._first_level_selectors(inner):
            out.append(f'  {selector} {{')
            for line in self._interesting_css_properties(props, indent='    '):
                out.append(line)
            out.append(f'    {marker}')
            out.append('  }')
            out.append('')
        out.append('}')
        return out

    def _render_rule_block(self, block: str, marker: str) -> list[str]:
        selector, body = block.split('{', 1)
        props = body.rsplit('}', 1)[0]
        out = [selector.strip() + ' {']
        interesting = self._interesting_css_properties(props, indent='  ')
        if interesting:
            out.extend(interesting)
        out.append(f'  {marker}')
        out.append('}')
        return out

    def _first_level_selectors(self, inner: str) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        idx = 0
        while idx < len(inner):
            while idx < len(inner) and inner[idx].isspace():
                idx += 1
            if idx >= len(inner):
                break
            end, block = self._collect_css_block(inner, idx)
            if '{' not in block:
                break
            selector, body = block.split('{', 1)
            items.append((selector.strip(), body.rsplit('}', 1)[0]))
            idx = end
        return items

    def _interesting_css_properties(self, body: str, indent: str) -> list[str]:
        lines: list[str] = []
        for raw in body.split(';'):
            line = raw.strip()
            if not line or ':' not in line:
                continue
            name, value = [part.strip() for part in line.split(':', 1)]
            if name.startswith('--'):
                lines.append(f'{indent}{name}: {safe_trim(value, 70)};')
            elif name in {'display', 'position', 'grid-template-columns', 'grid-template-areas', 'grid-area', 'flex', 'flex-direction', 'gap', 'width', 'height', 'min-height', 'max-width', 'font', 'font-size', 'font-weight', 'color', 'background', 'background-color', 'animation', 'transition'}:
                lines.append(f'{indent}{name}: {safe_trim(value, 70)};')
        return lines[:12]


def get_compressor() -> Compressor:
    return HtmlCssCompressor()
