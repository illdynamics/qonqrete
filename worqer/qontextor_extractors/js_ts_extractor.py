from __future__ import annotations

from pathlib import Path

from node_tooling import helper_capabilities, run_node_helper

from .base import Extractor
from .graph import FileContext, GraphEdge, SymbolSummary
from .utils import add_unique, infer_purpose_from_name, relative_display_path, resolve_relative_path, strip_js_comments


class JsTsExtractor(Extractor):
    name = 'js_ts_structural'
    extensions = ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx')

    def extract(self, project_path: Path, file_path: Path, content: str, local_mode: str = 'complex') -> FileContext:
        rel = relative_display_path(project_path, file_path)
        language = 'typescript' if file_path.suffix.lower() in {'.ts', '.tsx'} else 'javascript'
        native = self._extract_native(project_path, file_path, rel, content)
        if native is not None:
            return native
        return self._extract_heuristic(project_path, file_path, content)

    def _extract_native(self, project_path: Path, file_path: Path, rel: str, content: str) -> FileContext | None:
        caps = helper_capabilities()
        if not caps.get('typescript'):
            return None
        try:
            data = run_node_helper(
                'extract-js-ts',
                stdin_text=content,
                args=[str(project_path.resolve()), str(file_path.resolve()), rel],
            )
        except Exception:
            return None
        ctx = FileContext(
            file_path=rel,
            language=data.get('language', 'typescript' if file_path.suffix.lower() in {'.ts', '.tsx'} else 'javascript'),
            extractor='js_ts_native',
            module=rel,
            file_metadata={**(data.get('file_metadata') or {}), 'processing_path': 'native TypeScript helper'},
        )
        self._populate_from_native(ctx, rel, data)
        return ctx

    def _populate_from_native(self, ctx: FileContext, rel: str, data: dict) -> None:
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        for symbol_data in data.get('symbols', []) or []:
            name = symbol_data.get('name', '')
            stype = symbol_data.get('type', 'variable')
            purpose = symbol_data.get('purpose') or infer_purpose_from_name(name, stype)[0]
            symbol = SymbolSummary(
                name=name,
                type=stype,
                line=int(symbol_data.get('line') or 0),
                signature=symbol_data.get('signature', name),
                purpose=purpose,
                qualified_name=symbol_data.get('qualified_name'),
                parent=symbol_data.get('parent'),
                decorators=list(symbol_data.get('decorators') or []),
                docstring=symbol_data.get('docstring'),
                metadata=dict(symbol_data.get('metadata') or {}),
            )
            ctx.symbols.append(symbol)
        for edge_data in data.get('relationships', []) or []:
            edge = GraphEdge(
                edge_data.get('type', 'calls'),
                edge_data.get('source', module_node),
                edge_data.get('target', ''),
                line=edge_data.get('line'),
                resolved=edge_data.get('resolved', True),
                metadata=dict(edge_data.get('metadata') or {}),
            )
            if edge.type == 'imports' and edge.target:
                add_unique(ctx.imports, edge.target)
            ctx.relationships.append(edge)
        for symbol in ctx.symbols:
            if symbol.type == 'selector':
                value = symbol.metadata.get('selector_value', symbol.name)
                if value and value not in symbol.dependencies:
                    symbol.dependencies.append(str(value))
        deps = list(ctx.imports)
        deps.extend(edge.target for edge in ctx.relationships if edge.type in {'calls', 'extends', 'implements', 'reads_storage', 'writes_storage'} and edge.target)
        ctx.dependencies = sorted(dict.fromkeys(dep for dep in deps if dep))
        ctx.summary = self._build_summary(rel, ctx)
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': rel, 'language': ctx.language},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': rel, 'language': ctx.language},
        ] + [symbol.as_graph_node(rel, rel, ctx.language or 'javascript') for symbol in ctx.symbols]
        ctx.relationships.sort(key=lambda edge: (edge.line or 0, edge.type, edge.source, edge.target))
        ctx.symbols.sort(key=lambda sym: (sym.line, sym.name))

    def _build_summary(self, rel: str, ctx: FileContext) -> str:
        symbol_types = {symbol.type for symbol in ctx.symbols}
        features = []
        if 'class' in symbol_types:
            features.append('classes')
        if 'function' in symbol_types or 'method' in symbol_types:
            features.append('functions')
        if any(edge.type == 'binds_event' for edge in ctx.relationships):
            features.append('event bindings')
        if any(edge.type in {'reads_storage', 'writes_storage'} for edge in ctx.relationships):
            features.append('storage usage')
        if any(symbol.type == 'selector' for symbol in ctx.symbols):
            features.append('DOM selectors')
        if not features:
            features.append('structural module relationships')
        return f"{ctx.language.title() if ctx.language else 'JS/TS'} file {rel} with native TypeScript AST mapping for {', '.join(features)}."

    # Honest fallback for reduced environments only.
    def _extract_heuristic(self, project_path: Path, file_path: Path, content: str) -> FileContext:
        from .graph import GraphEdge, SymbolSummary
        import re

        rel = relative_display_path(project_path, file_path)
        module = rel
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        language = 'typescript' if file_path.suffix.lower() in {'.ts', '.tsx'} else 'javascript'
        ctx = FileContext(file_path=rel, language=language, extractor='js_ts_fallback', module=module, file_metadata={'processing_path': 'heuristic fallback', 'capability_note': 'native TypeScript helper unavailable'})
        lines = strip_js_comments(content).splitlines()

        import_re = re.compile(r"^\s*import\s+(?P<what>.+?)\s+from\s+['\"](?P<spec>[^'\"]+)['\"]")
        side_re = re.compile(r"^\s*import\s+['\"](?P<spec>[^'\"]+)['\"]")
        func_re = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
        class_re = re.compile(r"^\s*(?:export\s+default\s+|export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)")
        selector_re = re.compile(r"(?:querySelectorAll|querySelector|getElementById|getElementsByClassName)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
        event_re = re.compile(r"\.addEventListener\(\s*['\"]([^'\"]+)['\"]")
        for lineno, raw in enumerate(lines, start=1):
            if import_re.match(raw) or side_re.match(raw):
                spec = (import_re.match(raw) or side_re.match(raw)).group('spec')
                target = resolve_relative_path(project_path, file_path, spec, ['.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx']) or spec
                ctx.relationships.append(GraphEdge('imports', module_node, target, line=lineno))
                add_unique(ctx.imports, target)
            if class_re.match(raw):
                name = class_re.match(raw).group(1)
                qname = f'{rel}::{name}'
                ctx.symbols.append(SymbolSummary(name=name, type='class', line=lineno, signature=raw.strip(), purpose=infer_purpose_from_name(name, 'class')[0], qualified_name=qname))
            if func_re.match(raw):
                name = func_re.match(raw).group(1)
                qname = f'{rel}::{name}'
                ctx.symbols.append(SymbolSummary(name=name, type='function', line=lineno, signature=raw.strip(), purpose=infer_purpose_from_name(name, 'function')[0], qualified_name=qname))
            for selector in selector_re.findall(raw):
                ctx.symbols.append(SymbolSummary(name=selector, type='selector', line=lineno, signature=selector, purpose=infer_purpose_from_name(selector, 'selector')[0], qualified_name=f'{rel}::selector:{lineno}:{selector[:12]}', metadata={'selector_value': selector}))
            for event_name in event_re.findall(raw):
                ctx.relationships.append(GraphEdge('binds_event', module_node, f'event:{event_name}', line=lineno, resolved=False, metadata={'event': event_name}))
            if 'localStorage.' in raw or 'sessionStorage.' in raw:
                edge_type = 'reads_storage' if '.getItem(' in raw or '.key(' in raw else 'writes_storage'
                store = 'localStorage' if 'localStorage.' in raw else 'sessionStorage'
                ctx.relationships.append(GraphEdge(edge_type, module_node, f'storage:{store}', line=lineno))
        ctx.dependencies = sorted(dict.fromkeys(ctx.imports + [edge.target for edge in ctx.relationships if edge.type != 'binds_event']))
        ctx.summary = f'{language.title()} file {rel} analyzed with heuristic fallback because native TypeScript tooling was unavailable.'
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': language},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': language},
        ] + [symbol.as_graph_node(rel, module, language) for symbol in ctx.symbols]
        return ctx


_EXTRACTOR = JsTsExtractor()


def get_extractor() -> JsTsExtractor:
    return _EXTRACTOR
