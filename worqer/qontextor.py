#!/usr/bin/env python3
# worqer/qontextor.py
"""
QonQrete Qontextor - Deterministic Multi-language Context Generator

Default identity:
- deterministic
- structural
- graph-oriented
- lightweight
- offline-safe

Local mode uses shared normalized graph records plus language-specific extractors
for Python, shell, JS/TS, and HTML/CSS. AI mode remains optional for non-local
providers, but the default/local path is structural and does not depend on
embeddings.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from runtime_capabilities import capability_report_json, collect_runtime_capabilities, format_capability_report
from qontextor_extractors.graph import FileContext, GraphEdge, ProjectGraph
from qontextor_extractors.registry import get_extractor_for_file
from qontextor_extractors.utils import (
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DOCS_EXTENSIONS,
    SPECIAL_FILENAMES,
    extract_first_sentence,
    normalize_symbol_aliases,
    relative_display_path,
    resolve_relative_path,
)
from qontextor_extractors import python_extractor as python_extractor_module

# --- AI Mode Imports (Optional) ------------------------------------------------
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lib_ai
    import qompressor
    AI_MODE_AVAILABLE = True
except ImportError:
    AI_MODE_AVAILABLE = False
    lib_ai = None
    qompressor = None


_PROJECT_GRAPH_CACHE: dict[str, ProjectGraph] = {}


# --- Generic helpers -----------------------------------------------------------

def get_qontextor_config() -> dict[str, Any]:
    try:
        with open('config.yaml', 'r', encoding='utf-8') as handle:
            config = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        config = {}
    return config.get('agents', {}).get('qontextor', {})


def get_file_type(file_path: Path) -> str:
    if file_path.suffix.lower() in CODE_EXTENSIONS or file_path.name in SPECIAL_FILENAMES:
        return 'code'
    if file_path.suffix.lower() in DOCS_EXTENSIONS:
        return 'doc'
    if file_path.suffix.lower() in CONFIG_EXTENSIONS:
        return 'config'
    return 'unknown'


def should_process_file(file_path: Path) -> bool:
    return get_file_type(file_path) != 'unknown'


def _generic_context(project_path: Path, file_path: Path) -> FileContext:
    rel = relative_display_path(project_path, file_path)
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as exc:
        return FileContext(file_path=rel, language='text', extractor='generic', error=str(exc))

    file_type = get_file_type(file_path)
    summary = extract_first_sentence(content)
    if not summary:
        if file_type == 'doc':
            summary = f'Documentation/support file: {file_path.name}'
        elif file_type == 'config':
            summary = f'Configuration file: {file_path.name}'
        else:
            summary = f'Support file: {file_path.name}'
    language = 'config' if file_type == 'config' else 'text'
    module = rel
    ctx = FileContext(
        file_path=rel,
        language=language,
        extractor='generic',
        module=module,
        summary=summary,
        file_metadata={'processing_path': 'generic summary'},
        graph_nodes=[
            {'id': f'file:{rel}', 'type': 'file', 'name': rel, 'file_path': rel, 'module': module, 'language': language},
            {'id': f'module:{rel}', 'type': 'module', 'name': rel, 'file_path': rel, 'module': module, 'language': language},
        ],
    )
    return ctx


def _iter_processable_files(project_path: Path) -> Iterable[Path]:
    for file_path in sorted(project_path.rglob('*')):
        if not file_path.is_file():
            continue
        if should_process_file(file_path):
            yield file_path


# --- Project graph orchestration ----------------------------------------------

def build_project_graph(project_path: Path, local_mode: str = 'complex') -> ProjectGraph:
    project_path = project_path.resolve()
    cache_key = f'{project_path}:{local_mode}'
    if cache_key in _PROJECT_GRAPH_CACHE:
        return _PROJECT_GRAPH_CACHE[cache_key]

    graph = ProjectGraph(project_path)
    python_states: dict[Path, Any] = {}

    for file_path in _iter_processable_files(project_path):
        extractor = get_extractor_for_file(file_path)
        if extractor is None:
            ctx = _generic_context(project_path, file_path)
        else:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            ctx = extractor.extract(project_path, file_path, content, local_mode=local_mode)
            if extractor is python_extractor_module.get_extractor():
                analyzer = extractor.get_analyzer(file_path)
                if analyzer is not None:
                    python_states[file_path.resolve()] = analyzer
                    if analyzer.module_name:
                        graph.top_level_by_module[analyzer.module_name].update(analyzer.top_level_symbols)
                    for class_qname, methods in analyzer.class_methods.items():
                        graph.class_methods[class_qname].update(methods)
                    if analyzer.is_package_init and analyzer.module_name:
                        graph.package_inits.add(analyzer.module_name)
        graph.register_context(file_path, ctx)

    for file_path, analyzer in python_states.items():
        file_ctx = graph.contexts[file_path]
        python_extractor_module.finalize_python_file(graph, analyzer, file_ctx)
        graph.register_context(file_path, file_ctx)

    _resolve_internal_assets(graph)
    _resolve_shell_function_calls(graph)
    _resolve_selector_matches(graph)
    _populate_inbound_references(graph)
    _PROJECT_GRAPH_CACHE[cache_key] = graph
    return graph


def _edge_exists(ctx: FileContext, edge_type: str, source: str, target: str) -> bool:
    return any(edge.type == edge_type and edge.source == source and edge.target == target for edge in ctx.relationships)


def _resolve_internal_assets(graph: ProjectGraph) -> None:
    for file_path, ctx in list(graph.contexts.items()):
        if ctx.language != 'html':
            continue
        for edge in ctx.relationships:
            if edge.type != 'links_asset':
                continue
            raw_target = edge.target.removeprefix('asset:')
            resolved = resolve_relative_path(graph.project_path, file_path, raw_target, ['.css', '.scss', '.sass', '.less', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx']) or raw_target
            if resolved and resolved != raw_target:
                edge.metadata['resolved_path'] = resolved
                if resolved in graph.file_to_module:
                    add_dep = graph.file_to_module[resolved]
                else:
                    add_dep = resolved
                if add_dep not in ctx.dependencies:
                    ctx.dependencies.append(add_dep)
        ctx.dependencies = sorted(dict.fromkeys(ctx.dependencies))


def _resolve_shell_function_calls(graph: ProjectGraph) -> None:
    shell_functions_by_file: dict[str, dict[str, str]] = {}
    for ctx in graph.contexts.values():
        if ctx.language != 'shell':
            continue
        functions: dict[str, str] = {}
        for symbol in ctx.symbols:
            if symbol.type == 'shell_function' and symbol.qualified_name:
                functions[symbol.name] = symbol.qualified_name
        shell_functions_by_file[ctx.file_path] = functions

    for ctx in graph.contexts.values():
        if ctx.language != 'shell':
            continue
        sourced_files = [edge.target for edge in ctx.relationships if edge.type == 'sources']
        visible_functions = dict(shell_functions_by_file.get(ctx.file_path, {}))
        for sourced in sourced_files:
            visible_functions.update(shell_functions_by_file.get(sourced, {}))
        for edge in list(ctx.relationships):
            if edge.type != 'invokes_command' or not edge.target.startswith('command:'):
                continue
            name = edge.target.split(':', 1)[1]
            target = visible_functions.get(name)
            if not target:
                continue
            if not _edge_exists(ctx, 'calls', edge.source, target):
                ctx.relationships.append(GraphEdge('calls', edge.source, target, line=edge.line))
                if target not in ctx.dependencies:
                    ctx.dependencies.append(target)
        ctx.dependencies = sorted(dict.fromkeys(ctx.dependencies))
        ctx.relationships.sort(key=lambda e: (e.line or 0, e.type, e.source, e.target))


def _selector_match_targets(graph: ProjectGraph, token: dict[str, str]) -> list[str]:
    kind = token.get('kind')
    value = token.get('value')
    results: list[str] = []
    for node_id, node in graph.node_index.items():
        ntype = node.get('type')
        name = node.get('name')
        if kind == 'id' and ntype == 'html_id' and name == value:
            results.append(node_id)
        elif kind == 'class' and ntype == 'html_class' and name == value:
            results.append(node_id)
        elif kind == 'tag' and ntype == 'html_element' and node.get('metadata', {}).get('tag', name) == value:
            results.append(node_id)
    return sorted(dict.fromkeys(results))


def _resolve_selector_matches(graph: ProjectGraph) -> None:
    for file_path, ctx in list(graph.contexts.items()):
        if ctx.language not in {'javascript', 'typescript', 'css'}:
            continue
        selector_symbols = [symbol for symbol in ctx.symbols if symbol.type == 'selector']
        for symbol in selector_symbols:
            tokens: list[dict[str, str]] = []
            if symbol.metadata.get('simple_tokens'):
                tokens.extend(symbol.metadata['simple_tokens'])
            else:
                value = symbol.metadata.get('selector_value', symbol.name)
                kind = symbol.metadata.get('selector_kind')
                if kind == 'id' or str(value).startswith('#'):
                    tokens.append({'kind': 'id', 'value': str(value).lstrip('#')})
                elif kind == 'class' or str(value).startswith('.'):
                    tokens.append({'kind': 'class', 'value': str(value).lstrip('.')})
                else:
                    bare = re.sub(r'[^A-Za-z0-9_-].*$', '', str(value)).strip()
                    if bare and bare[0].isalpha():
                        tokens.append({'kind': 'tag', 'value': bare})
            for token in tokens:
                for target in _selector_match_targets(graph, token):
                    if not _edge_exists(ctx, 'matches_selector', symbol.qualified_name or symbol.name, target):
                        ctx.relationships.append(GraphEdge('matches_selector', symbol.qualified_name or symbol.name, target, line=symbol.line, metadata={'selector_kind': token.get('kind')}))
                        if target not in symbol.dependencies:
                            symbol.dependencies.append(target)
                        owner_file = graph.node_index.get(target, {}).get('file_path')
                        if owner_file and owner_file != ctx.file_path:
                            if owner_file in graph.file_to_module:
                                ctx.dependencies.append(graph.file_to_module[owner_file])
                            else:
                                ctx.dependencies.append(owner_file)
        ctx.dependencies = sorted(dict.fromkeys(ctx.dependencies))
        for symbol in ctx.symbols:
            symbol.dependencies = sorted(dict.fromkeys(symbol.dependencies))
        ctx.relationships.sort(key=lambda edge: (edge.line or 0, edge.type, edge.source, edge.target))


def _ownership_keys(ctx: FileContext) -> set[str]:
    owned: set[str] = {ctx.file_path}
    if ctx.module:
        owned.add(ctx.module)
    for symbol in ctx.symbols:
        if symbol.qualified_name:
            owned.add(symbol.qualified_name)
    return owned


def _matches_owned(dep: str, owned: str) -> bool:
    return dep == owned or dep.startswith(f'{owned}.') or dep.startswith(f'{owned}::') or dep.startswith(f'{owned}#')


def _populate_inbound_references(graph: ProjectGraph) -> None:
    ownership: dict[str, str] = {}
    for ctx in graph.contexts.values():
        owner_name = ctx.module or ctx.file_path
        for key in _ownership_keys(ctx):
            ownership[key] = owner_name

    reverse: dict[str, set[str]] = defaultdict(set)
    for ctx in graph.contexts.values():
        source = ctx.module or ctx.file_path
        for dep in ctx.dependencies:
            for owned, owner_name in ownership.items():
                if _matches_owned(dep, owned):
                    reverse[owner_name].add(source)

    for ctx in graph.contexts.values():
        inbound = set(reverse.get(ctx.module or ctx.file_path, set()))
        current = ctx.module or ctx.file_path
        inbound.discard(current)
        ctx.inbound_refs = sorted(inbound)


# --- Query / retrieval ---------------------------------------------------------

def _load_qontext_documents(qontext_dir: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if not qontext_dir.exists():
        return documents
    for yaml_file in sorted(qontext_dir.rglob('*.q.yaml')):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as handle:
                data = yaml.safe_load(handle) or {}
            if isinstance(data, dict):
                documents.append(data)
        except Exception as exc:
            print(f'  - [WARN] Failed to load {yaml_file}: {exc}', flush=True)
    return documents


def _score_text_match(query: str, *fields: str) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0
    tokens = [tok for tok in re.split(r'[^a-zA-Z0-9_#:.\/+-]+', q) if tok]
    score = 0.0
    combined = ' '.join(field.lower() for field in fields if field)
    for field in fields:
        field_l = field.lower() if field else ''
        if not field_l:
            continue
        if field_l == q:
            score += 12.0
        elif q in field_l:
            score += 6.0
    for token in tokens:
        if token in combined:
            score += 1.5
    return score


def search_symbols(query: str, qontext_dir: Path, top_k: int = 10) -> list[tuple[float, dict[str, Any]]]:
    results: list[tuple[float, dict[str, Any]]] = []
    for data in _load_qontext_documents(qontext_dir):
        file_path = data.get('file_path', '')
        module = data.get('module', '')
        language = data.get('language', '')
        for symbol in data.get('symbols', []) or []:
            if not isinstance(symbol, dict):
                continue
            metadata_text = ''
            if isinstance(symbol.get('metadata'), dict):
                metadata_text = ' '.join(str(v) for v in symbol['metadata'].values() if isinstance(v, (str, int, float)))
            score = _score_text_match(
                query,
                symbol.get('name', ''),
                symbol.get('qualified_name', ''),
                symbol.get('signature', ''),
                symbol.get('purpose', ''),
                metadata_text,
                module,
                file_path,
                language,
            )
            if score <= 0:
                continue
            results.append((score, {
                'file': file_path,
                'module': module,
                'language': language,
                'name': symbol.get('name', ''),
                'qualified_name': symbol.get('qualified_name', ''),
                'type': symbol.get('type', 'unknown'),
                'purpose': symbol.get('purpose', ''),
                'signature': symbol.get('signature', ''),
                'dependencies': symbol.get('dependencies', []) or [],
            }))
    results.sort(key=lambda item: (-item[0], item[1].get('qualified_name') or item[1].get('name') or ''))
    return results[:top_k]


def find_related_by_verb(verb_pattern: str, qontext_dir: Path) -> list[dict[str, Any]]:
    results = []
    for data in _load_qontext_documents(qontext_dir):
        file_path = data.get('file_path', '')
        for symbol in data.get('symbols', []) or []:
            if not isinstance(symbol, dict):
                continue
            name = symbol.get('name', '')
            if re.match(verb_pattern, name, re.IGNORECASE):
                results.append({
                    'file': file_path,
                    'module': data.get('module'),
                    'language': data.get('language'),
                    'name': name,
                    'qualified_name': symbol.get('qualified_name', ''),
                    'type': symbol.get('type', 'unknown'),
                    'purpose': symbol.get('purpose', ''),
                    'dependencies': symbol.get('dependencies', []) or [],
                })
    return results


def _canonical_aliases(identifier: str) -> set[str]:
    aliases: set[str] = set()
    for alias in normalize_symbol_aliases(identifier):
        aliases.add(alias)
    return aliases


def _match_symbol_aliases(symbol_name: str, symbol_lookup: dict[str, set[str]]) -> set[str]:
    matches: set[str] = set()
    for alias in _canonical_aliases(symbol_name):
        matches.update(symbol_lookup.get(alias, set()))
        for key, canonicals in symbol_lookup.items():
            if alias == key or alias.endswith(key) or key.endswith(alias):
                matches.update(canonicals)
            for canonical in canonicals:
                if canonical.endswith(f'.{alias}') or canonical.endswith(f'::{alias}') or canonical.endswith(f':{alias}'):
                    matches.add(canonical)
    return matches or ({symbol_name} if symbol_name else set())


def analyze_ripple_effect(symbol_name: str, qontext_dir: Path) -> dict[str, Any]:
    result = {'symbol': symbol_name, 'file': None, 'called_by': [], 'calls': [], 'depth_1_impact': [], 'depth_2_impact': []}
    if not qontext_dir.exists():
        return result

    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    symbol_to_file: dict[str, str] = {}
    symbol_lookup: dict[str, set[str]] = defaultdict(set)
    symbol_types: dict[str, str] = {}

    for data in _load_qontext_documents(qontext_dir):
        file_path = data.get('file_path', '')
        module = data.get('module', '')
        if module:
            symbol_to_file[module] = file_path
            for alias in _canonical_aliases(module):
                symbol_lookup[alias].add(module)
            symbol_types[module] = 'module'
        symbol_to_file[file_path] = file_path
        symbol_lookup[file_path].add(file_path)
        symbol_types[file_path] = 'file'

        for symbol in data.get('symbols', []) or []:
            if not isinstance(symbol, dict):
                continue
            qname = symbol.get('qualified_name') or symbol.get('name')
            name = symbol.get('name') or qname
            if not qname:
                continue
            symbol_to_file[qname] = file_path
            for alias in _canonical_aliases(qname) | _canonical_aliases(name):
                symbol_lookup[alias].add(qname)
            symbol_types[qname] = symbol.get('type', '')
            forward.setdefault(qname, set())

        for edge in data.get('relationships', []) or []:
            if not isinstance(edge, dict):
                continue
            if edge.get('type') not in {'calls', 'extends', 'imports', 'implements', 'sources', 'links_asset', 'binds_event', 'matches_selector'}:
                continue
            source = edge.get('source')
            target = edge.get('target')
            if not source or not target:
                continue
            forward[source].add(target)
            reverse[target].add(source)
        if not data.get('relationships'):
            for dep in data.get('dependencies', []) or []:
                if module and dep:
                    forward[module].add(dep)
                    reverse[dep].add(module)

    canonical_targets = _match_symbol_aliases(symbol_name, symbol_lookup)
    direct_callers: set[str] = set()
    direct_callees: set[str] = set()
    depth_1: set[str] = set()
    depth_2: set[str] = set()

    preferred_targets = sorted(canonical_targets, key=lambda item: (symbol_types.get(item) == 'variable', item.count('.'), item))
    for canonical in preferred_targets:
        if result['file'] is None and canonical in symbol_to_file and symbol_types.get(canonical) not in {'variable'}:
            result['file'] = symbol_to_file[canonical]
        direct_callers.update(reverse.get(canonical, set()))
        direct_callees.update(forward.get(canonical, set()))
    if result['file'] is None:
        for canonical in preferred_targets:
            if canonical in symbol_to_file:
                result['file'] = symbol_to_file[canonical]
                break

    for caller in direct_callers:
        if caller in symbol_to_file:
            depth_1.add(symbol_to_file[caller])
        for indirect in reverse.get(caller, set()):
            if indirect in symbol_to_file:
                depth_2.add(symbol_to_file[indirect])

    depth_2 -= depth_1
    if result['file'] in depth_1:
        depth_1.remove(result['file'])
    if result['file'] in depth_2:
        depth_2.remove(result['file'])

    result['called_by'] = sorted(direct_callers)
    result['calls'] = sorted(direct_callees)
    result['depth_1_impact'] = sorted(depth_1)
    result['depth_2_impact'] = sorted(depth_2)
    return result


# --- Local context generation --------------------------------------------------

def get_project_graph(project_path: Path, local_mode: str = 'complex') -> ProjectGraph:
    return build_project_graph(project_path, local_mode=local_mode)


def generate_context_local(file_path: Path, local_mode: str, project_path: Path) -> FileContext:
    graph = get_project_graph(project_path, local_mode=local_mode)
    resolved_path = file_path.resolve()
    if resolved_path in graph.contexts:
        return graph.contexts[resolved_path]
    return _generic_context(project_path, file_path)


# --- AI Mode Logic -------------------------------------------------------------

def generate_qontext_ai(file_path: Path, provider: str, model: str, file_type: str) -> str:
    if not AI_MODE_AVAILABLE:
        return f"file_path: {str(file_path.as_posix())}\nerror: 'AI mode dependencies (lib_ai, qompressor) are not installed.'"

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
        content = handle.read()

    content_to_send = qompressor.compress_file_content(str(file_path), content) if file_type == 'code' else content
    if len(content_to_send) > 100000:
        return f"file_path: {str(file_path.as_posix())}\nerror: 'File is too large to analyze.'"

    prompt = f"""
Analyze the following file and generate a YAML structure representing deterministic structural context.
Prefer explicit definitions, signatures, and statically visible relationships.

**File Path:** {file_path.as_posix()}
**File Content:**
```
{content_to_send}
```

**YAML Structure Rules:**
1. Root must include `file_path`.
2. Include `summary` for non-code or `symbols` for code.
3. Keep the output grounded and inspectable.
4. Do not invent semantic or embedding-based relationships.
"""
    try:
        raw_result = lib_ai.run_ai_completion(
            provider,
            model,
            prompt,
            prompt_sections=[{
                'label': f'qontextor:{file_path.name}',
                'content': prompt,
                'required': True,
                'loss_policy': 'preserve',
                'section_type': 'context_indexing',
            }],
            agent_name='qontextor',
            task_type='planning',
            output_tokens=1800,
        )
        yaml_match = re.search(r'```yaml\n(.*?)\n```', raw_result, re.DOTALL)
        return yaml_match.group(1) if yaml_match else raw_result
    except Exception as exc:
        return f"file_path: {str(file_path.as_posix())}\nerror: 'Failed to generate context due to an AI error: {exc}'"


def write_qontext_manifest(qontext_path: Path, graph: ProjectGraph | None, config: dict[str, Any]) -> None:
    files: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    if graph is not None:
        for file_path, ctx in sorted(graph.contexts.items(), key=lambda item: item[1].file_path):
            counts[ctx.extractor or 'unknown'] += 1
            files.append({
                'file_path': ctx.file_path,
                'language': ctx.language,
                'extractor': ctx.extractor,
                'processing_path': (ctx.file_metadata or {}).get('processing_path'),
            })
    manifest = {
        'kind': 'qontextor_run_manifest',
        'provider': config.get('provider', 'local'),
        'local_mode': config.get('local_mode', 'complex'),
        'capabilities': collect_runtime_capabilities(),
        'extractor_counts': dict(sorted(counts.items())),
        'files': files,
    }
    (qontext_path / '.qontext_manifest.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False), encoding='utf-8')


# --- Scan orchestration --------------------------------------------------------

def process_file(qodeyard_path: Path, file_path: Path, qontext_path: Path, config: dict[str, Any]) -> None:
    relative_path = file_path.relative_to(qodeyard_path)
    qontext_file = qontext_path / f'{relative_path}.q.yaml'
    qontext_file.parent.mkdir(parents=True, exist_ok=True)

    provider = config.get('provider', 'local')
    model = config.get('model', 'qontextor')
    local_mode = config.get('local_mode', 'complex')

    print(f'     - Qontextualizing: {relative_path} (Mode: {provider}, Detail: {local_mode})', flush=True)

    if provider == 'local':
        context = generate_context_local(file_path, local_mode, qodeyard_path)
        yaml_content = yaml.dump(context.to_dict(), sort_keys=False, default_flow_style=False, indent=2)
    else:
        file_type = get_file_type(file_path)
        yaml_content = generate_qontext_ai(file_path, provider, model, file_type)

    with open(qontext_file, 'w', encoding='utf-8') as handle:
        handle.write(yaml_content)


def run_initial_scan(qodeyard_path: Path, qontext_path: Path, config: dict[str, Any]) -> None:
    print(f'--- Qontextor: Starting initial scan of {qodeyard_path} ---', flush=True)
    local_mode = config.get('local_mode', 'complex')
    graph = None
    if config.get('provider', 'local') == 'local':
        graph = get_project_graph(qodeyard_path, local_mode=local_mode)
    for file_path in _iter_processable_files(qodeyard_path):
        relative_path = file_path.relative_to(qodeyard_path)
        qontext_file = qontext_path / f'{relative_path}.q.yaml'
        if not qontext_file.exists():
            process_file(qodeyard_path, file_path, qontext_path, config)
    write_qontext_manifest(qontext_path, graph, config)
    print('--- Qontextor: Initial scan complete ---', flush=True)


def run_update_scan(summary_path: Path, qodeyard_path: Path, qontext_path: Path, config: dict[str, Any]) -> None:
    print(f'--- Qontextor: Starting update scan based on {summary_path.name} ---', flush=True)
    graph = None
    if not summary_path.exists():
        print('  - Summary file not found. Nothing to update.', flush=True)
        return
    local_mode = config.get('local_mode', 'complex')
    if config.get('provider', 'local') == 'local':
        graph = get_project_graph(qodeyard_path, local_mode=local_mode)
    with open(summary_path, 'r', encoding='utf-8') as handle:
        summary_content = handle.read()
    changed_files = re.findall(r'`([^`]+)`', summary_content)
    if not changed_files:
        print('  - No changed files found in summary. Nothing to update.', flush=True)
        return
    processed_files: set[Path] = set()
    for file_str in changed_files:
        file_path = Path(file_str)
        if file_path.is_absolute():
            try:
                file_path = qodeyard_path / file_path.relative_to(qodeyard_path)
            except ValueError:
                print(f"  - [WARN] Changed file '{file_str}' is outside the qodeyard. Skipping.", flush=True)
                continue
        else:
            file_path = qodeyard_path / file_str
        if file_path in processed_files:
            continue
        processed_files.add(file_path)
        if file_path.exists() and should_process_file(file_path):
            process_file(qodeyard_path, file_path, qontext_path, config)
        else:
            print(f"  - [INFO] Changed file '{file_str}' does not exist or is not processable. Skipping.", flush=True)
    if graph is None and config.get('provider', 'local') == 'local':
        graph = get_project_graph(qodeyard_path, local_mode=local_mode)
    write_qontext_manifest(qontext_path, graph, config)
    print('--- Qontextor: Update scan complete ---', flush=True)


# --- CLI -----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Qontextor - Deterministic multi-language context generator and querier')
    parser.add_argument('input_path', nargs='?', help='The source directory (qodeyard) or summary file for updates.')
    parser.add_argument('output_path', nargs='?', help='The destination for context files (qontext.d).')
    parser.add_argument('--query', help='Perform a structural symbol search for a given term.')
    parser.add_argument('--verb', help='Find symbols matching a verb pattern (e.g., "get_.*").')
    parser.add_argument('--ripple', help='Analyze the ripple effect of changing a symbol.')
    parser.add_argument('--capabilities', action='store_true', help='Print current native/fallback capability report and exit.')
    parser.add_argument('--capabilities-json', action='store_true', help='Print capability report as JSON and exit.')
    args = parser.parse_args()

    if args.capabilities_json:
        print(capability_report_json())
        return
    if args.capabilities:
        print(format_capability_report())
        return

    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / 'qodeyard'
    qontext_path = worqspace_root / 'qontext.d'

    print(f'  - Qontextor running in: {worqspace_root}', flush=True)
    config = get_qontextor_config()
    qontext_path.mkdir(exist_ok=True)

    if not any(qontext_path.iterdir()) and (args.query or args.verb or args.ripple):
        print('  - [INFO] Qontext directory is empty. Running initial scan...', flush=True)
        if qodeyard_path.exists():
            run_initial_scan(qodeyard_path, qontext_path, config)
        else:
            print('  - [ERROR] qodeyard not found. Cannot build context.', flush=True)
            sys.exit(1)

    if args.query:
        print(f"--- Structural Search: '{args.query}' ---", flush=True)
        results = search_symbols(args.query, qontext_path, top_k=10)
        if not results:
            print('No results found.', flush=True)
        else:
            for score, item in results:
                label = item.get('qualified_name') or item.get('name')
                print(f"  [{score:.1f}] {label} ({Path(item['file']).name})", flush=True)
                if item.get('purpose'):
                    print(f"          → {item['purpose']}", flush=True)
                if item.get('dependencies'):
                    preview = ', '.join(item['dependencies'][:3])
                    suffix = '...' if len(item['dependencies']) > 3 else ''
                    print(f"          ⤷ deps: {preview}{suffix}", flush=True)
        sys.exit(0)

    if args.verb:
        print(f"--- Verb Pattern Search: '{args.verb}' ---", flush=True)
        results = find_related_by_verb(args.verb, qontext_path)
        if not results:
            print('No results found.', flush=True)
        else:
            for item in results:
                label = item.get('qualified_name') or item['name']
                print(f"  {label} ({item['type']}) - {Path(item['file']).name}", flush=True)
                print(f"      → {item['purpose']}", flush=True)
                if item['dependencies']:
                    preview = ', '.join(item['dependencies'][:3])
                    suffix = '...' if len(item['dependencies']) > 3 else ''
                    print(f"      ⤷ deps: {preview}{suffix}", flush=True)
        sys.exit(0)

    if args.ripple:
        print(f"--- Ripple Effect Analysis: '{args.ripple}' ---", flush=True)
        ripple = analyze_ripple_effect(args.ripple, qontext_path)
        print(yaml.dump(ripple, sort_keys=False, default_flow_style=False), flush=True)
        sys.exit(0)

    if args.input_path and args.output_path:
        run_initial_scan(Path(args.input_path), Path(args.output_path), config)
        return

    if qodeyard_path.exists():
        run_initial_scan(qodeyard_path, qontext_path, config)
    else:
        print('  - [ERROR] qodeyard not found.', flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
