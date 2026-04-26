from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, Optional


VERB_PATTERNS = {
    r'^(get|fetch|load|read|retrieve|find|lookup|query|select|obtain|pull)': 'Retrieves',
    r'^(set|update|modify|patch|change|alter|edit|adjust|revise)': 'Updates',
    r'^(is|has|can|should|will|does|check|verify|validate|test|assert|ensure)': 'Checks',
    r'^(create|make|build|generate|new|init|initialize|construct|spawn)': 'Creates',
    r'^(delete|remove|destroy|drop|clear|purge|erase|wipe|discard)': 'Removes',
    r'^(parse|convert|transform|translate|map|decode|encode|serialize)': 'Transforms',
    r'^(send|emit|dispatch|publish|broadcast|notify|post|transmit|push)': 'Sends',
    r'^(receive|handle|process|consume|accept|on_|listen|respond|react)': 'Handles',
    r'^(save|store|persist|write|commit|flush|dump|export|backup)': 'Saves',
    r'^(render|display|show|draw|present|format|print|output|visualize)': 'Renders',
    r'^(start|begin|open|launch|run|execute|invoke|trigger|activate)': 'Starts',
    r'^(stop|end|close|terminate|shutdown|halt|abort|kill|finish)': 'Stops',
    r'^(add|append|insert|push|enqueue|register|attach|include)': 'Adds',
    r'^(count|measure|calculate|compute|sum|avg|total|aggregate|tally)': 'Calculates',
}
SPECIAL_METHODS = {
    '__init__': 'Initializes a new instance.',
    '__str__': 'Returns a string representation.',
    '__repr__': 'Returns a debugging representation.',
    '__len__': 'Returns the length or size.',
    '__iter__': 'Returns an iterator.',
    '__getitem__': 'Gets an item by key or index.',
}


DOCS_EXTENSIONS = {'.md', '.txt', '.rst'}
CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.xml'}
SPECIAL_FILENAMES = {
    'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.gitignore', '.dockerignore',
    'Makefile', 'Jenkinsfile', 'Vagrantfile'
}
CODE_EXTENSIONS = {
    '.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx',
    '.sh', '.bash', '.zsh', '.ksh', '.html', '.htm', '.css', '.scss', '.sass', '.less'
}


def add_unique(values: list[str], item: Optional[str]) -> None:
    if item and item not in values:
        values.append(item)


def relative_display_path(base_path: Path, file_path: Path) -> str:
    try:
        return file_path.resolve().relative_to(base_path.resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()


def path_to_module_str(base_path: Path, file_path: Path) -> str:
    try:
        relative_path = file_path.resolve().relative_to(base_path.resolve())
    except ValueError:
        return file_path.stem
    without_suffix = relative_path.with_suffix('')
    parts = list(without_suffix.parts)
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts) if parts else file_path.stem


def resolve_relative_import(module_name: str, is_package_init: bool, target_module: str | None, level: int) -> str:
    if level <= 0:
        return target_module or ''
    parts = module_name.split('.') if module_name else []
    if not is_package_init and parts:
        parts = parts[:-1]
    if level > 1:
        trim = min(len(parts), level - 1)
        parts = parts[:-trim] if trim else parts
    if target_module:
        parts.extend(target_module.split('.'))
    return '.'.join([part for part in parts if part])


def extract_first_sentence(text: Optional[str]) -> str:
    if not text:
        return ""
    match = re.split(r'(?<=[.!?])\s+', text.strip())
    return match[0] if match else text.strip()


def infer_purpose_from_name(name: str, stype: str) -> tuple[str, float]:
    if name in SPECIAL_METHODS:
        return SPECIAL_METHODS[name], 0.95
    words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|$)|\d+', name)
    words = [w.lower() for w in words]
    if not words:
        return f"Defines {name}.", 0.3
    verb = words[0]
    for pattern, action in VERB_PATTERNS.items():
        if re.match(pattern, verb):
            remainder = " ".join(words[1:]).strip()
            return f"{action} {remainder}.".replace(' .', '.').strip(), 0.7
    if stype == 'class':
        return f"Defines the {name} type.", 0.5
    if stype in {'selector', 'html_id', 'html_class'}:
        return f"UI selector or linkage for {name}.", 0.5
    if stype == 'command':
        return f"Invokes the {name} command.", 0.5
    if stype == 'env_var':
        return f"Reads or writes environment variable {name}.", 0.5
    return f"Logic for {name}.", 0.4


def safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def resolve_relative_path(project_path: Path, file_path: Path, specifier: str, candidates: Iterable[str]) -> Optional[str]:
    spec = (specifier or '').strip()
    if not spec or spec.startswith(('http://', 'https://', '//', 'data:')):
        return spec or None
    base = file_path.parent
    candidate_paths: list[Path] = []
    spec_path = Path(spec)
    if spec.startswith('/'):
        spec_path = project_path / spec.lstrip('/')
        candidate_paths.append(spec_path)
    else:
        candidate_paths.append((base / spec).resolve())
        candidate_paths.append((project_path / spec).resolve())
    raw_candidates = list(candidate_paths)
    for path in raw_candidates:
        if path.suffix:
            candidate_paths.append(path)
        else:
            for suffix in candidates:
                candidate_paths.append(path.with_suffix(suffix))
            candidate_paths.append(path / '__init__.py')
            candidate_paths.append(path / 'index.js')
            candidate_paths.append(path / 'index.ts')
            candidate_paths.append(path / 'index.tsx')
            candidate_paths.append(path / 'index.jsx')
            candidate_paths.append(path / 'index.css')
    seen: set[str] = set()
    for candidate in candidate_paths:
        key = candidate.as_posix()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.resolve().relative_to(project_path.resolve()).as_posix()
            except Exception:
                return candidate.as_posix()
    return spec


def strip_js_comments(text: str) -> str:
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//.*', '', text)
    return text


def strip_css_comments(text: str) -> str:
    return re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)


def strip_shell_comments(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        if raw.lstrip().startswith('#'):
            lines.append('')
        else:
            lines.append(re.sub(r'\s+#.*$', '', raw))
    return '\n'.join(lines)


def normalize_symbol_aliases(*parts: str) -> list[str]:
    aliases: set[str] = set()
    for part in parts:
        if not part:
            continue
        aliases.add(part)
        fragments = re.split(r'[:.#/]+', part)
        for frag in fragments:
            if frag:
                aliases.add(frag)
    return sorted(aliases)
