from __future__ import annotations

import ast
import builtins
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .base import Extractor
from .graph import FileContext, GraphEdge, ProjectGraph, SymbolSummary
from .utils import (
    add_unique,
    extract_first_sentence,
    infer_purpose_from_name,
    path_to_module_str,
    relative_display_path,
    resolve_relative_import,
    safe_unparse,
)

BUILTIN_NAMES = set(dir(builtins))


@dataclass
class PendingRelationship:
    type: str
    source: str
    node: ast.AST
    line: int
    class_context: Optional[str] = None


class PythonModuleAnalyzer(ast.NodeVisitor):
    def __init__(self, project_path: Path, file_path: Path, source_code: str, local_mode: str = 'complex'):
        self.project_path = project_path.resolve()
        self.file_path = file_path.resolve()
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.local_mode = local_mode
        self.relative_path = relative_display_path(self.project_path, self.file_path)
        self.module_name = path_to_module_str(self.project_path, self.file_path)
        self.is_package_init = self.file_path.name == '__init__.py'

        self.symbols: list[SymbolSummary] = []
        self.symbol_lookup: dict[str, SymbolSummary] = {}
        self.relationships: list[GraphEdge] = []
        self.pending_relationships: list[PendingRelationship] = []
        self.import_aliases: dict[str, str] = {}
        self.top_level_symbols: dict[str, str] = {}
        self.class_methods: dict[str, dict[str, str]] = defaultdict(dict)
        self.current_symbol_stack: list[str] = []
        self.current_class_stack: list[str] = []
        self.file_node_id = f"file:{self.relative_path}"
        self.module_node_id = self.module_name or self.relative_path.replace('/', '.')
        self.module_docstring: Optional[str] = None

    def analyze(self) -> FileContext:
        try:
            tree = ast.parse(self.source_code)
        except SyntaxError as exc:
            return FileContext(
                file_path=self.relative_path,
                module=self.module_name,
                language='python',
                extractor='python_ast',
                error=f"AST Parse Error (SyntaxError): {exc}",
            )
        except Exception as exc:
            return FileContext(
                file_path=self.relative_path,
                module=self.module_name,
                language='python',
                extractor='python_ast',
                error=f"Analysis Error ({type(exc).__name__}): {exc}",
            )

        self.module_docstring = ast.get_docstring(tree)
        self.visit(tree)

        file_ctx = FileContext(
            file_path=self.relative_path,
            module=self.module_name,
            language='python',
            extractor='python_ast',
            symbols=self.symbols,
            imports=sorted(dict.fromkeys(self.import_aliases.values())),
            relationships=list(self.relationships),
            file_metadata={
                'local_mode': self.local_mode,
                'is_package_init': self.is_package_init,
            },
        )
        file_ctx.summary = extract_first_sentence(self.module_docstring) or build_module_summary(file_ctx)
        file_ctx.graph_nodes = self._build_graph_nodes(file_ctx)
        return file_ctx

    def _build_graph_nodes(self, file_ctx: FileContext) -> list[dict[str, Any]]:
        nodes = [
            {
                'id': self.file_node_id,
                'type': 'file',
                'name': self.relative_path,
                'file_path': self.relative_path,
                'module': self.module_name,
                'language': 'python',
            },
            {
                'id': self.module_node_id,
                'type': 'module',
                'name': self.module_name,
                'file_path': self.relative_path,
                'module': self.module_name,
                'language': 'python',
            },
        ]
        for symbol in file_ctx.symbols:
            nodes.append(symbol.as_graph_node(self.relative_path, self.module_name, 'python'))
        return nodes

    def _current_symbol(self) -> str:
        return self.current_symbol_stack[-1] if self.current_symbol_stack else self.module_node_id

    def _current_class(self) -> Optional[str]:
        return self.current_class_stack[-1] if self.current_class_stack else None

    def _register_symbol(self, symbol: SymbolSummary) -> None:
        self.symbols.append(symbol)
        if symbol.qualified_name:
            self.symbol_lookup[symbol.qualified_name] = symbol
        if symbol.parent is None and symbol.name not in self.top_level_symbols:
            self.top_level_symbols[symbol.name] = symbol.qualified_name or symbol.name
        if symbol.type == 'method' and symbol.parent:
            self.class_methods[symbol.parent][symbol.name] = symbol.qualified_name or symbol.name

    def _build_qualified_name(self, name: str) -> str:
        if self.current_symbol_stack:
            return f"{self.current_symbol_stack[-1]}.{name}"
        return f"{self.module_node_id}.{name}" if self.module_node_id else name

    def _get_signature(self, node: ast.AST) -> str:
        start = getattr(node, 'lineno', None)
        end = getattr(node, 'end_lineno', None)
        if not start or not end:
            return safe_unparse(node)[:200]
        for idx in range(start - 1, min(end, start + 20)):
            if idx < len(self.lines) and self.lines[idx].strip().endswith(':'):
                return " ".join(self.lines[start - 1:idx + 1]).strip().rstrip(':')
        return self.lines[start - 1].strip() if start - 1 < len(self.lines) else safe_unparse(node)[:200]

    def _is_useful_constant(self, name: str, value: ast.AST | None) -> bool:
        if not name or name.startswith('__'):
            return False
        if not re.match(r'^[A-Z][A-Z0-9_]*$', name):
            return False
        if value is None:
            return True
        return isinstance(value, (ast.Constant, ast.Tuple, ast.List, ast.Dict, ast.Set, ast.UnaryOp))

    def _record_env_edge(self, relation_type: str, env_name: str | None, line: int) -> None:
        env_target = f"env:{env_name or '*'}"
        source = self._current_symbol()
        self.relationships.append(GraphEdge(type=relation_type, source=source, target=env_target, line=line))
        symbol = self.symbol_lookup.get(source)
        if symbol is not None and env_name:
            if relation_type == 'reads_env':
                add_unique(symbol.reads_env, env_name)
            elif relation_type == 'writes_env':
                add_unique(symbol.writes_env, env_name)

    def _env_name_from_arg(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _resolve_env_mapping_name(self, node: ast.AST) -> Optional[str]:
        text = safe_unparse(node)
        if text in {'os.environ', 'environ'}:
            return 'os.environ'
        if isinstance(node, ast.Name):
            target = self.import_aliases.get(node.id)
            if target == 'os.environ':
                return 'os.environ'
        return None

    def _record_pending_call(self, node: ast.Call) -> None:
        self.pending_relationships.append(PendingRelationship(
            type='calls',
            source=self._current_symbol(),
            node=node.func,
            line=node.lineno,
            class_context=self._current_class(),
        ))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split('.')[0]
            target = alias.name
            self.import_aliases[local_name] = target
            symbol = SymbolSummary(
                name=local_name,
                type='variable',
                line=node.lineno,
                signature=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ''),
                purpose=f"Imports {target}.",
                qualified_name=f"{self.module_node_id}.{local_name}",
                dependencies=[target],
                metadata={'import': True},
            )
            self._register_symbol(symbol)
            self.relationships.append(GraphEdge(type='imports', source=self.module_node_id, target=target, line=node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = resolve_relative_import(self.module_name, self.is_package_init, node.module, node.level)
        for alias in node.names:
            local_name = alias.asname or alias.name
            target = f"{module}.{alias.name}" if module and alias.name != '*' else (f"{module}.*" if module else alias.name)
            self.import_aliases[local_name] = target
            symbol = SymbolSummary(
                name=local_name,
                type='variable',
                line=node.lineno,
                signature=(f"from {'.' * node.level}{node.module or ''} import {alias.name}" + (f" as {alias.asname}" if alias.asname else '')),
                purpose=f"Imports {alias.name} from {module or '.'}.",
                qualified_name=f"{self.module_node_id}.{local_name}",
                dependencies=[target],
                metadata={'import': True},
            )
            self._register_symbol(symbol)
            self.relationships.append(GraphEdge(type='imports', source=self.module_node_id, target=target, line=node.lineno))

    def visit_Assign(self, node: ast.Assign) -> None:
        self._handle_assignment(node.targets, node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        targets = [node.target]
        self._handle_assignment(targets, node.value, node.lineno)
        self.generic_visit(node)

    def _handle_assignment(self, targets: list[ast.AST], value: ast.AST | None, line: int) -> None:
        for target in targets:
            self._handle_env_store(target, line)
            if not self.current_class_stack and not self.current_symbol_stack and isinstance(target, ast.Name):
                if self._is_useful_constant(target.id, value):
                    qname = self._build_qualified_name(target.id)
                    value_repr = safe_unparse(value)[:120] if value is not None else ''
                    self._register_symbol(SymbolSummary(
                        name=target.id,
                        type='variable',
                        line=line,
                        signature=f"{target.id} = {value_repr}".strip(),
                        purpose=f"Module constant {target.id}.",
                        qualified_name=qname,
                        metadata={'constant': True},
                    ))

    def _handle_env_store(self, target: ast.AST, line: int) -> None:
        if isinstance(target, ast.Subscript) and self._resolve_env_mapping_name(target.value):
            env_name = getattr(target, 'slice', None)
            self._record_env_edge('writes_env', self._env_name_from_arg(env_name), line)
        elif isinstance(target, ast.Name) and target.id.isupper() and self.current_symbol_stack:
            # no-op: preserve deterministic honesty, uppercase locals are not env writes
            return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        doc = ast.get_docstring(node)
        qualified_name = self._build_qualified_name(node.name)
        decorators = [safe_unparse(d) for d in node.decorator_list if safe_unparse(d)]
        symbol = SymbolSummary(
            name=node.name,
            type='class',
            line=node.lineno,
            signature=self._get_signature(node).replace('class ', '', 1),
            purpose=extract_first_sentence(doc) or infer_purpose_from_name(node.name, 'class')[0],
            qualified_name=qualified_name,
            parent=self.current_symbol_stack[-1] if self.current_symbol_stack else None,
            decorators=decorators,
            docstring=extract_first_sentence(doc),
        )
        self._register_symbol(symbol)
        for base in node.bases:
            self.pending_relationships.append(PendingRelationship(
                type='extends',
                source=qualified_name,
                node=base,
                line=node.lineno,
                class_context=qualified_name,
            ))
        self.current_symbol_stack.append(qualified_name)
        self.current_class_stack.append(qualified_name)
        self.generic_visit(node)
        self.current_class_stack.pop()
        self.current_symbol_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_function(node)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        stype = 'method' if self.current_class_stack else 'function'
        doc = ast.get_docstring(node)
        qualified_name = self._build_qualified_name(node.name)
        decorators = [safe_unparse(d) for d in node.decorator_list if safe_unparse(d)]
        signature = self._get_signature(node)
        if stype == 'function':
            signature = signature.replace('def ', '', 1).replace('async def ', '', 1)
        symbol = SymbolSummary(
            name=node.name,
            type=stype,
            line=node.lineno,
            signature=signature,
            purpose=extract_first_sentence(doc) or infer_purpose_from_name(node.name, stype)[0],
            qualified_name=qualified_name,
            parent=self.current_class_stack[-1] if self.current_class_stack else (self.current_symbol_stack[-1] if self.current_symbol_stack else None),
            decorators=decorators,
            docstring=extract_first_sentence(doc),
            metadata={'async': isinstance(node, ast.AsyncFunctionDef)},
        )
        self._register_symbol(symbol)
        self.current_symbol_stack.append(qualified_name)
        self.generic_visit(node)
        self.current_symbol_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        env_kind = self._resolve_env_call(node)
        if env_kind:
            relation_type, env_name = env_kind
            self._record_env_edge(relation_type, env_name, node.lineno)
        else:
            self._record_pending_call(node)
        self.generic_visit(node)

    def _resolve_env_call(self, node: ast.Call) -> tuple[str, Optional[str]] | None:
        func_text = safe_unparse(node.func)
        if func_text in {'os.getenv', 'getenv'}:
            env_name = self._env_name_from_arg(node.args[0]) if node.args else None
            return ('reads_env', env_name)
        if func_text in {'os.putenv', 'os.unsetenv'}:
            env_name = self._env_name_from_arg(node.args[0]) if node.args else None
            return ('writes_env', env_name)
        if func_text in {'os.environ.get', 'environ.get'}:
            env_name = self._env_name_from_arg(node.args[0]) if node.args else None
            return ('reads_env', env_name)
        if func_text in {'os.environ.setdefault', 'environ.setdefault'}:
            env_name = self._env_name_from_arg(node.args[0]) if node.args else None
            return ('writes_env', env_name)
        if isinstance(node.func, ast.Attribute) and self._resolve_env_mapping_name(node.func.value):
            if node.func.attr == 'get':
                env_name = self._env_name_from_arg(node.args[0]) if node.args else None
                return ('reads_env', env_name)
            if node.func.attr == 'setdefault':
                env_name = self._env_name_from_arg(node.args[0]) if node.args else None
                return ('writes_env', env_name)
        return None

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, ast.Load) and self._resolve_env_mapping_name(node.value):
            self._record_env_edge('reads_env', self._env_name_from_arg(node.slice), node.lineno)
        self.generic_visit(node)


def build_module_summary(file_ctx: FileContext) -> str:
    counts = defaultdict(int)
    for symbol in file_ctx.symbols:
        if symbol.metadata.get('import'):
            continue
        counts[symbol.type] += 1
    parts: list[str] = []
    if counts.get('class'):
        parts.append(f"{counts['class']} class{'es' if counts['class'] != 1 else ''}")
    if counts.get('function'):
        parts.append(f"{counts['function']} function{'s' if counts['function'] != 1 else ''}")
    if counts.get('method'):
        parts.append(f"{counts['method']} method{'s' if counts['method'] != 1 else ''}")
    if counts.get('variable'):
        parts.append(f"{counts['variable']} constant{'s' if counts['variable'] != 1 else ''}")
    if not parts:
        return f"Python module {file_ctx.module or file_ctx.file_path}."
    return f"Python module {file_ctx.module or file_ctx.file_path} defines " + ', '.join(parts) + '.'


def _resolve_reference(graph: ProjectGraph, analyzer: PythonModuleAnalyzer, node: ast.AST, class_context: Optional[str]) -> tuple[str, bool]:
    if isinstance(node, ast.Name):
        name = node.id
        if name in analyzer.import_aliases:
            return analyzer.import_aliases[name], True
        local_top = graph.top_level_by_module.get(analyzer.module_name, {}).get(name)
        if local_top:
            return local_top, True
        if class_context and name in graph.class_methods.get(class_context, {}):
            return graph.class_methods[class_context][name], True
        if name in BUILTIN_NAMES:
            return f"builtin:{name}", False
        return name, False

    if isinstance(node, ast.Attribute):
        base_target, base_resolved = _resolve_reference(graph, analyzer, node.value, class_context)
        attr = node.attr
        if isinstance(node.value, ast.Name) and node.value.id in {'self', 'cls'} and class_context:
            method_target = graph.class_methods.get(class_context, {}).get(attr)
            if method_target:
                return method_target, True
            candidate = f"{class_context}.{attr}"
            return candidate, candidate in graph.symbols_by_qname
        if base_resolved:
            candidate = f"{base_target}.{attr}"
            if candidate in graph.symbols_by_qname:
                return candidate, True
            if base_target in graph.modules or base_target in graph.package_inits or base_target in analyzer.import_aliases.values():
                return candidate, True
            return candidate, False
        return f"{base_target}.{attr}" if base_target else safe_unparse(node), False

    if isinstance(node, ast.Call):
        return _resolve_reference(graph, analyzer, node.func, class_context)
    if isinstance(node, ast.Subscript):
        return safe_unparse(node), False
    raw = safe_unparse(node)
    return raw, False


def finalize_python_file(graph: ProjectGraph, analyzer: PythonModuleAnalyzer, file_ctx: FileContext) -> None:
    for edge in list(file_ctx.relationships):
        if edge.resolved and edge.type in {'calls', 'imports', 'extends', 'implements'}:
            add_unique(file_ctx.dependencies, edge.target)
            symbol = analyzer.symbol_lookup.get(edge.source)
            if symbol is not None:
                add_unique(symbol.dependencies, edge.target)

    for pending in analyzer.pending_relationships:
        target, resolved = _resolve_reference(graph, analyzer, pending.node, pending.class_context)
        if not target:
            continue
        file_ctx.relationships.append(GraphEdge(
            type=pending.type,
            source=pending.source,
            target=target,
            line=pending.line,
            resolved=resolved,
        ))
        if resolved and pending.type in {'calls', 'imports', 'extends', 'implements'}:
            add_unique(file_ctx.dependencies, target)
            symbol = analyzer.symbol_lookup.get(pending.source)
            if symbol is not None:
                add_unique(symbol.dependencies, target)

    file_ctx.imports = sorted(dict.fromkeys(file_ctx.imports))
    file_ctx.dependencies = sorted(dict.fromkeys(file_ctx.dependencies))
    for symbol in file_ctx.symbols:
        symbol.dependencies = sorted(dict.fromkeys(symbol.dependencies))
    file_ctx.relationships.sort(key=lambda edge: (edge.line or 0, edge.type, edge.source, edge.target))
    file_ctx.graph_nodes = analyzer._build_graph_nodes(file_ctx)


class PythonExtractor(Extractor):
    name = 'python_ast'
    extensions = ('.py', '.pyi')

    def __init__(self) -> None:
        self._analyzers: dict[Path, PythonModuleAnalyzer] = {}

    def extract(self, project_path: Path, file_path: Path, content: str, local_mode: str = 'complex') -> FileContext:
        analyzer = PythonModuleAnalyzer(project_path, file_path, content, local_mode=local_mode)
        ctx = analyzer.analyze()
        self._analyzers[file_path.resolve()] = analyzer
        return ctx

    def get_analyzer(self, file_path: Path) -> Optional[PythonModuleAnalyzer]:
        return self._analyzers.get(file_path.resolve())


_EXTRACTOR = PythonExtractor()


def get_extractor() -> PythonExtractor:
    return _EXTRACTOR
