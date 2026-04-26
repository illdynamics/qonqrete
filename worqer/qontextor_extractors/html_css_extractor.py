from __future__ import annotations

from pathlib import Path

from node_tooling import helper_capabilities, run_node_helper

from .base import Extractor
from .graph import FileContext, GraphEdge, SymbolSummary
from .utils import add_unique, infer_purpose_from_name, relative_display_path, strip_css_comments


class HtmlCssExtractor(Extractor):
    name = 'html_css_structural'
    extensions = ('.html', '.htm', '.css', '.scss', '.sass', '.less')

    def extract(self, project_path: Path, file_path: Path, content: str, local_mode: str = 'complex') -> FileContext:
        rel = relative_display_path(project_path, file_path)
        suffix = file_path.suffix.lower()
        if suffix in {'.html', '.htm'}:
            native = self._extract_html_native(project_path, file_path, rel, content)
            if native is not None:
                return native
            return self._extract_html_fallback(project_path, file_path, content)
        native = self._extract_css_native(project_path, file_path, rel, content)
        if native is not None:
            return native
        return self._extract_css_fallback(project_path, file_path, content)

    def _extract_html_native(self, project_path: Path, file_path: Path, rel: str, content: str) -> FileContext | None:
        if not helper_capabilities().get('parse5'):
            return None
        try:
            data = run_node_helper('extract-html', stdin_text=content, args=[str(project_path.resolve()), str(file_path.resolve()), rel])
        except Exception:
            return None
        return self._ctx_from_native(rel, 'html', 'html_native', data)

    def _extract_css_native(self, project_path: Path, file_path: Path, rel: str, content: str) -> FileContext | None:
        if not helper_capabilities().get('postcss'):
            return None
        try:
            data = run_node_helper('extract-css', stdin_text=content, args=[str(project_path.resolve()), str(file_path.resolve()), rel])
        except Exception:
            return None
        return self._ctx_from_native(rel, 'css', 'css_native', data)

    def _ctx_from_native(self, rel: str, language: str, extractor_name: str, data: dict) -> FileContext:
        module = rel
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        file_metadata = dict(data.get('file_metadata') or {})
        file_metadata.setdefault('processing_path', 'native parse5 helper' if language == 'html' else 'native PostCSS helper')
        ctx = FileContext(file_path=rel, language=language, extractor=extractor_name, module=module, file_metadata=file_metadata)
        for symbol_data in data.get('symbols', []) or []:
            name = symbol_data.get('name', '')
            stype = symbol_data.get('type', 'variable')
            ctx.symbols.append(SymbolSummary(
                name=name,
                type=stype,
                line=int(symbol_data.get('line') or 0),
                signature=symbol_data.get('signature', name),
                purpose=symbol_data.get('purpose') or infer_purpose_from_name(name, stype)[0],
                qualified_name=symbol_data.get('qualified_name'),
                parent=symbol_data.get('parent'),
                metadata=dict(symbol_data.get('metadata') or {}),
            ))
        for edge_data in data.get('relationships', []) or []:
            edge = GraphEdge(
                edge_data.get('type', 'links_asset'),
                edge_data.get('source', module_node),
                edge_data.get('target', ''),
                line=edge_data.get('line'),
                resolved=edge_data.get('resolved', True),
                metadata=dict(edge_data.get('metadata') or {}),
            )
            ctx.relationships.append(edge)
            if edge.type == 'imports':
                add_unique(ctx.imports, edge.target)
        if language == 'html':
            for edge in ctx.relationships:
                if edge.type == 'links_asset':
                    resolved = edge.metadata.get('resolved_path') or edge.target.removeprefix('asset:')
                    add_unique(ctx.dependencies, resolved)
        else:
            ctx.dependencies = sorted(dict.fromkeys(list(data.get('imports') and [item['target'] for item in data['imports']] or []) + [edge.target for edge in ctx.relationships if edge.type == 'imports']))
        ctx.summary = self._build_summary(rel, ctx)
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': language},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': language},
        ] + [symbol.as_graph_node(rel, module, language) for symbol in ctx.symbols]
        ctx.relationships.sort(key=lambda edge: (edge.line or 0, edge.type, edge.source, edge.target))
        ctx.symbols.sort(key=lambda sym: (sym.line, sym.name))
        return ctx

    def _build_summary(self, rel: str, ctx: FileContext) -> str:
        if ctx.language == 'html':
            assets = sum(1 for s in ctx.symbols if s.type == 'asset')
            return f'HTML file {rel} with native structural parsing for UI elements, ids/classes, and {assets} linked asset(s).'
        selectors = sum(1 for s in ctx.symbols if s.type == 'selector')
        media = len(ctx.file_metadata.get('media_queries') or [])
        return f'CSS file {rel} with native PostCSS parsing for {selectors} selector(s) and {media} media querie(s).'

    def _extract_html_fallback(self, project_path: Path, file_path: Path, content: str) -> FileContext:
        from html.parser import HTMLParser
        import html

        rel = relative_display_path(project_path, file_path)
        module = rel
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        ctx = FileContext(file_path=rel, language='html', extractor='html_fallback', module=module, file_metadata={'processing_path': 'fallback HTML parser', 'capability_note': 'native parse5 helper unavailable'})

        class Parser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                lineno = self.getpos()[0]
                ctx.symbols.append(SymbolSummary(name=tag, type='html_element', line=lineno, signature=f'<{tag}>', purpose=infer_purpose_from_name(tag, 'html_element')[0], qualified_name=f'{rel}::element:{lineno}:{tag}', metadata={'tag': tag}))
                amap = dict(attrs)
                if amap.get('id'):
                    ctx.symbols.append(SymbolSummary(name=amap['id'], type='html_id', line=lineno, signature=f"#{amap['id']}", purpose=infer_purpose_from_name(amap['id'], 'html_id')[0], qualified_name=f'{rel}::id:{amap["id"]}', metadata={'tag': tag}))
                for klass in (amap.get('class') or '').split():
                    ctx.symbols.append(SymbolSummary(name=klass, type='html_class', line=lineno, signature=f'.{klass}', purpose=infer_purpose_from_name(klass, 'html_class')[0], qualified_name=f'{rel}::class:{klass}', metadata={'tag': tag}))
                raw = amap.get('href') or amap.get('src')
                if raw and tag in {'link', 'script'}:
                    ctx.symbols.append(SymbolSummary(name=raw, type='asset', line=lineno, signature=raw, purpose=f'Linked asset {raw}.', qualified_name=f'asset:{raw}', metadata={'tag': tag}))
                    ctx.relationships.append(GraphEdge('links_asset', module_node, f'asset:{raw}', line=lineno))
                    ctx.dependencies.append(raw)

        parser = Parser(convert_charrefs=True)
        parser.feed(content)
        parser.close()
        ctx.dependencies = sorted(dict.fromkeys(ctx.dependencies))
        ctx.summary = f'HTML file {rel} analyzed with fallback parser because native parse5 tooling was unavailable.'
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': 'html'},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': 'html'},
        ] + [symbol.as_graph_node(rel, module, 'html') for symbol in ctx.symbols]
        return ctx

    def _extract_css_fallback(self, project_path: Path, file_path: Path, content: str) -> FileContext:
        import re

        rel = relative_display_path(project_path, file_path)
        module = rel
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        ctx = FileContext(file_path=rel, language='css', extractor='css_fallback', module=module, file_metadata={'processing_path': 'fallback CSS parser', 'capability_note': 'native PostCSS helper unavailable'})
        text = strip_css_comments(content)
        for match in re.finditer(r'([^{}]+)\{', text):
            selector_blob = match.group(1).strip()
            line = text[:match.start()].count('\n') + 1
            if selector_blob.startswith('@media'):
                ctx.file_metadata.setdefault('media_queries', []).append(selector_blob.removeprefix('@media').strip())
                continue
            for idx, selector in enumerate(part.strip() for part in selector_blob.split(',') if part.strip()):
                ctx.symbols.append(SymbolSummary(name=selector, type='selector', line=line, signature=selector, purpose=infer_purpose_from_name(selector, 'selector')[0], qualified_name=f'{rel}::selector:{line}:{idx}', metadata={'selector_value': selector}))
        ctx.summary = f'CSS file {rel} analyzed with fallback parser because native PostCSS tooling was unavailable.'
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': 'css'},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': 'css'},
        ] + [symbol.as_graph_node(rel, module, 'css') for symbol in ctx.symbols]
        return ctx


_EXTRACTOR = HtmlCssExtractor()


def get_extractor() -> HtmlCssExtractor:
    return _EXTRACTOR
