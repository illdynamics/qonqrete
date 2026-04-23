from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .base import Extractor
from .graph import FileContext, GraphEdge, SymbolSummary
from .utils import add_unique, infer_purpose_from_name, relative_display_path, resolve_relative_path, strip_shell_comments

_ENV_READ_PATTERN = re.compile(r'\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))')
_EXPORT_PATTERN = re.compile(r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
_ASSIGN_PATTERN = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
_FUNCTION_PATTERNS = [
    re.compile(r'^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\))?\s*\{'),
    re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{'),
]


class ShellExtractor(Extractor):
    name = 'shell_structural'
    extensions = ('.sh', '.bash', '.zsh', '.ksh')

    def extract(self, project_path: Path, file_path: Path, content: str, local_mode: str = 'complex') -> FileContext:
        native = self._extract_with_shfmt(project_path, file_path, content)
        if native is not None:
            return native
        return self._extract_fallback(project_path, file_path, content)

    def _extract_with_shfmt(self, project_path: Path, file_path: Path, content: str) -> FileContext | None:
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
                timeout=30,
            )
            ast_json = json.loads(proc.stdout)
        except Exception:
            return None

        rel = relative_display_path(project_path, file_path)
        module = rel
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        ctx = FileContext(
            file_path=rel,
            language='shell',
            extractor='shell_native',
            module=module,
            file_metadata={'entrypoint': content.startswith('#!'), 'native_ast': 'shfmt -tojson', 'processing_path': 'native shfmt AST'},
        )

        functions: dict[str, str] = {}
        command_nodes: set[str] = set()
        env_nodes: set[str] = set()

        def first_value(word: dict) -> str:
            parts = word.get('Parts') or []
            values: list[str] = []
            for part in parts:
                value = part.get('Value')
                if value:
                    values.append(str(value))
            return ''.join(values)

        def scan_stmt_list(statements: list[dict], current_source: str) -> None:
            for stmt in statements or []:
                cmd = stmt.get('Cmd') or stmt
                walk_cmd(cmd, current_source)

        def walk_cmd(cmd: dict, current_source: str) -> None:
            typ = cmd.get('Type')
            if typ == 'FuncDecl':
                name = (cmd.get('Name') or {}).get('Value') or 'function'
                qname = f'{rel}::{name}'
                functions[name] = qname
                ctx.symbols.append(SymbolSummary(
                    name=name,
                    type='shell_function',
                    line=0,
                    signature=f'{name}() {{',
                    purpose=infer_purpose_from_name(name, 'function')[0],
                    qualified_name=qname,
                ))
                ctx.relationships.append(GraphEdge('exports', module_node, qname))
                body = (cmd.get('Body') or {}).get('Stmts') or []
                scan_stmt_list(body, qname)
                return
            if typ == 'CallExpr':
                args = cmd.get('Args') or []
                words = [first_value(arg) for arg in args]
                words = [word for word in words if word]
                if not words:
                    return
                head = words[0]
                if head in {'source', '.'} and len(words) > 1:
                    target = resolve_relative_path(project_path, file_path, words[1], ['.sh', '.bash', '.zsh', '.ksh']) or words[1]
                    ctx.relationships.append(GraphEdge('sources', current_source, target, resolved=target != words[1] or target.endswith(('.sh', '.bash', '.zsh', '.ksh'))))
                    add_unique(ctx.imports, target)
                    add_unique(ctx.dependencies, target)
                    return
                if head == 'export' and len(words) > 1:
                    for item in words[1:]:
                        env_name = item.split('=', 1)[0]
                        if env_name:
                            env_nodes.add(env_name)
                            ctx.relationships.append(GraphEdge('writes_env', current_source, f'env:{env_name}'))
                    return
                if head in functions:
                    target = functions[head]
                    ctx.relationships.append(GraphEdge('calls', current_source, target))
                    add_unique(ctx.dependencies, target)
                else:
                    command_nodes.add(head)
                    ctx.relationships.append(GraphEdge('invokes_command', current_source, f'command:{head}'))
                for word in words[1:]:
                    for env_a, env_b in _ENV_READ_PATTERN.findall(word):
                        env_name = env_a or env_b
                        if env_name:
                            env_nodes.add(env_name)
                            ctx.relationships.append(GraphEdge('reads_env', current_source, f'env:{env_name}'))
                return
            for key in ('Stmts', 'Items', 'Then', 'Else', 'Do'):
                value = cmd.get(key)
                if isinstance(value, list):
                    scan_stmt_list(value, current_source)
            for key, value in cmd.items():
                if isinstance(value, dict):
                    walk_cmd(value, current_source)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and 'Type' in item:
                            walk_cmd(item, current_source)

        scan_stmt_list(ast_json.get('Stmts') or [], module_node)

        for lineno, raw in enumerate(strip_shell_comments(content).splitlines(), start=1):
            export_match = _EXPORT_PATTERN.match(raw)
            if export_match:
                env_name = export_match.group(1)
                env_nodes.add(env_name)
                if not any(edge.type == 'writes_env' and edge.target == f'env:{env_name}' for edge in ctx.relationships):
                    ctx.relationships.append(GraphEdge('writes_env', module_node, f'env:{env_name}', line=lineno))
            else:
                assign_match = _ASSIGN_PATTERN.match(raw)
                if assign_match and assign_match.group(1).isupper():
                    env_name = assign_match.group(1)
                    env_nodes.add(env_name)
                    if not any(edge.type == 'writes_env' and edge.target == f'env:{env_name}' for edge in ctx.relationships):
                        ctx.relationships.append(GraphEdge('writes_env', module_node, f'env:{env_name}', line=lineno))
            for env_a, env_b in _ENV_READ_PATTERN.findall(raw):
                env_name = env_a or env_b
                if env_name:
                    env_nodes.add(env_name)
                    if not any(edge.type == 'reads_env' and edge.target == f'env:{env_name}' and (edge.line == lineno or edge.line is None) for edge in ctx.relationships):
                        ctx.relationships.append(GraphEdge('reads_env', module_node, f'env:{env_name}', line=lineno))

        for cmd in sorted(command_nodes):
            ctx.symbols.append(SymbolSummary(name=cmd, type='command', line=0, signature=cmd, purpose=f'External command {cmd} is invoked by this shell file.', qualified_name=f'command:{cmd}', metadata={'kind': 'external_command'}))
        for env in sorted(env_nodes):
            ctx.symbols.append(SymbolSummary(name=env, type='env_var', line=0, signature=env, purpose=f'Environment variable {env} is used by this shell file.', qualified_name=f'env:{env}'))

        ctx.imports = sorted(dict.fromkeys(ctx.imports))
        ctx.dependencies = sorted(dict.fromkeys(ctx.dependencies + ctx.imports + [edge.target for edge in ctx.relationships if edge.type in {'calls', 'invokes_command'}]))
        ctx.summary = self._build_summary(rel, ctx, native=True)
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': 'shell'},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': 'shell'},
        ] + [symbol.as_graph_node(rel, module, 'shell') for symbol in ctx.symbols]
        ctx.relationships.sort(key=lambda edge: (edge.line or 0, edge.type, edge.source, edge.target))
        ctx.symbols.sort(key=lambda sym: (sym.line, sym.name))
        return ctx

    def _extract_fallback(self, project_path: Path, file_path: Path, content: str) -> FileContext:
        rel = relative_display_path(project_path, file_path)
        module = rel
        file_node = f'file:{rel}'
        module_node = f'module:{rel}'
        ctx = FileContext(file_path=rel, language='shell', extractor='shell_fallback', module=module, file_metadata={'entrypoint': content.startswith('#!'), 'processing_path': 'heuristic shell fallback', 'capability_note': 'shfmt unavailable or failed'})
        lines = strip_shell_comments(content).splitlines()
        functions: dict[str, str] = {}
        command_nodes: set[str] = set()
        env_nodes: set[str] = set()
        current_source = module_node

        for lineno, raw in enumerate(lines, start=1):
            for pattern in _FUNCTION_PATTERNS:
                match = pattern.match(raw)
                if match:
                    name = match.group(1)
                    qname = f'{rel}::{name}'
                    functions[name] = qname
                    current_source = qname
                    ctx.symbols.append(SymbolSummary(name=name, type='shell_function', line=lineno, signature=raw.strip(), purpose=infer_purpose_from_name(name, 'function')[0], qualified_name=qname))
                    ctx.relationships.append(GraphEdge('exports', module_node, qname, line=lineno))
            stripped = raw.strip()
            if stripped.startswith(('source ', '. ')):
                target_raw = stripped.split(maxsplit=1)[1].strip()
                target = resolve_relative_path(project_path, file_path, target_raw, ['.sh', '.bash', '.zsh', '.ksh']) or target_raw
                ctx.relationships.append(GraphEdge('sources', current_source, target, line=lineno))
                add_unique(ctx.imports, target)
                add_unique(ctx.dependencies, target)
            export_match = _EXPORT_PATTERN.match(raw)
            if export_match:
                env_name = export_match.group(1)
                env_nodes.add(env_name)
                ctx.relationships.append(GraphEdge('writes_env', current_source, f'env:{env_name}', line=lineno))
            else:
                assign_match = _ASSIGN_PATTERN.match(raw)
                if assign_match and assign_match.group(1).isupper():
                    env_name = assign_match.group(1)
                    env_nodes.add(env_name)
                    ctx.relationships.append(GraphEdge('writes_env', current_source, f'env:{env_name}', line=lineno))
            for env_a, env_b in _ENV_READ_PATTERN.findall(raw):
                env_name = env_a or env_b
                if env_name:
                    env_nodes.add(env_name)
                    ctx.relationships.append(GraphEdge('reads_env', current_source, f'env:{env_name}', line=lineno))
            if stripped and not stripped.startswith('#') and not stripped.endswith('{') and stripped not in {'}', 'fi', 'done', 'esac'}:
                cmd = stripped.split()[0]
                if cmd in functions:
                    ctx.relationships.append(GraphEdge('calls', current_source, functions[cmd], line=lineno))
                elif cmd not in {'if', 'then', 'else', 'elif', 'for', 'while', 'do', 'case', 'function', 'export'}:
                    command_nodes.add(cmd)
                    ctx.relationships.append(GraphEdge('invokes_command', current_source, f'command:{cmd}', line=lineno))
        for cmd in sorted(command_nodes):
            ctx.symbols.append(SymbolSummary(name=cmd, type='command', line=0, signature=cmd, purpose=f'External command {cmd} is invoked by this shell file.', qualified_name=f'command:{cmd}', metadata={'kind': 'external_command'}))
        for env in sorted(env_nodes):
            ctx.symbols.append(SymbolSummary(name=env, type='env_var', line=0, signature=env, purpose=f'Environment variable {env} is used by this shell file.', qualified_name=f'env:{env}'))
        ctx.imports = sorted(dict.fromkeys(ctx.imports))
        ctx.dependencies = sorted(dict.fromkeys(ctx.dependencies + ctx.imports + [edge.target for edge in ctx.relationships if edge.type in {'calls', 'invokes_command'}]))
        ctx.summary = self._build_summary(rel, ctx, native=False)
        ctx.graph_nodes = [
            {'id': file_node, 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': 'shell'},
            {'id': module_node, 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': 'shell'},
        ] + [symbol.as_graph_node(rel, module, 'shell') for symbol in ctx.symbols]
        ctx.relationships.sort(key=lambda edge: (edge.line or 0, edge.type, edge.source, edge.target))
        ctx.symbols.sort(key=lambda sym: (sym.line, sym.name))
        return ctx

    def _build_summary(self, rel: str, ctx: FileContext, native: bool) -> str:
        function_count = sum(1 for s in ctx.symbols if s.type == 'shell_function')
        command_count = sum(1 for s in ctx.symbols if s.type == 'command')
        basis = 'native shfmt AST' if native else 'heuristic fallback'
        return f'Shell file {rel} defines {function_count} function(s) and invokes {command_count} command(s) using {basis} mapping.'


_EXTRACTOR = ShellExtractor()


def get_extractor() -> ShellExtractor:
    return _EXTRACTOR
