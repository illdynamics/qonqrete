from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from node_tooling import helper_capabilities
from qompressor_extractors import tree_sitter_fallback


def _language_status(native_available: bool, native_tool: str, fallback: str | None = None) -> dict[str, Any]:
    return {
        'native_available': native_available,
        'active_mode': 'native' if native_available else 'fallback',
        'native_tool': native_tool,
        'fallback': fallback,
    }



def collect_runtime_capabilities() -> dict[str, Any]:
    node_caps = helper_capabilities()
    shfmt_path = shutil.which('shfmt')
    tree_sitter_installed = tree_sitter_fallback.optional_tree_sitter_loaded()
    tree_sitter_reason = tree_sitter_fallback.optional_tree_sitter_unavailable_reason()

    report: dict[str, Any] = {
        'scope': 'current runtime',
        'node_helper': {
            'available': bool(node_caps.get('available')),
            'node_path': node_caps.get('node_path'),
            'helper_script': node_caps.get('helper_script'),
            'helper_script_exists': bool(node_caps.get('helper_script_exists')),
            'repo_node_modules': node_caps.get('repo_node_modules'),
            'repo_node_modules_exists': bool(node_caps.get('repo_node_modules_exists')),
            'global_node_modules': node_caps.get('global_node_modules'),
            'global_node_modules_exists': bool(node_caps.get('global_node_modules_exists')),
            'reason': node_caps.get('reason'),
        },
        'languages': {
            'python': {
                'native_available': True,
                'active_mode': 'native',
                'native_tool': 'Python stdlib AST',
                'fallback': None,
            },
            'shell': {
                **_language_status(bool(shfmt_path), 'shfmt -tojson', 'heuristic shell fallback'),
                'binary': shfmt_path,
            },
            'javascript_typescript': {
                **_language_status(bool(node_caps.get('available') and node_caps.get('typescript')), 'TypeScript Compiler API via repo-shipped Node helper', 'heuristic JS/TS fallback'),
                'helper_available': bool(node_caps.get('available')),
            },
            'html': {
                **_language_status(bool(node_caps.get('available') and node_caps.get('parse5')), 'parse5 via repo-shipped Node helper', 'fallback HTML parser'),
                'helper_available': bool(node_caps.get('available')),
            },
            'css': {
                **_language_status(bool(node_caps.get('available') and node_caps.get('postcss')), 'PostCSS via repo-shipped Node helper', 'fallback CSS parser'),
                'helper_available': bool(node_caps.get('available')),
            },
        },
        'optional_fallbacks': {
            'tree_sitter': {
                'optional': True,
                'installed': bool(tree_sitter_installed),
                'available': bool(tree_sitter_installed),
                'active_mode': 'available' if tree_sitter_installed else 'inactive',
                'install_hint': 'pip install -r requirements-optional-tree-sitter.txt',
                'reason': None if tree_sitter_installed else (tree_sitter_reason or 'tree_sitter_language_pack is not installed in the current runtime'),
            },
        },
        'node_helper_features': {
            'typescript': bool(node_caps.get('typescript')),
            'parse5': bool(node_caps.get('parse5')),
            'postcss': bool(node_caps.get('postcss')),
        },
    }
    return report



def format_capability_report(data: dict[str, Any] | None = None) -> str:
    data = data or collect_runtime_capabilities()
    lines: list[str] = ['QonQrete capability report (current runtime)', '']
    helper = data['node_helper']
    lines.append('Node helper')
    lines.append(f"- available: {'yes' if helper.get('available') else 'no'}")
    lines.append(f"- node executable: {helper.get('node_path') or 'not found'}")
    lines.append(f"- helper script: {helper.get('helper_script')}")
    lines.append(f"- repo-local node_modules: {'present' if helper.get('repo_node_modules_exists') else 'absent'}")
    lines.append(f"- global node_modules: {'present' if helper.get('global_node_modules_exists') else 'absent'}")
    if helper.get('reason'):
        lines.append(f"- note: {helper['reason']}")
    lines.append('')
    lines.append('Language paths')
    for label, info in data['languages'].items():
        pretty = {
            'python': 'Python',
            'shell': 'Shell',
            'javascript_typescript': 'JavaScript / TypeScript',
            'html': 'HTML',
            'css': 'CSS',
        }[label]
        status = 'native' if info.get('native_available') else 'fallback only'
        lines.append(f"- {pretty}: {status} ({info.get('native_tool')})")
        if info.get('fallback'):
            lines.append(f"  fallback: {info['fallback']}")
        if info.get('binary'):
            lines.append(f"  binary: {info['binary']}")
    lines.append('')
    ts = data['optional_fallbacks']['tree_sitter']
    lines.append('Optional Tree-sitter fallback')
    lines.append(f"- installed: {'yes' if ts.get('installed') else 'no'}")
    lines.append(f"- install hint: {ts.get('install_hint')}")
    if ts.get('reason'):
        lines.append(f"- note: {ts['reason']}")
    return '\n'.join(lines)



def capability_report_json(data: dict[str, Any] | None = None) -> str:
    return json.dumps(data or collect_runtime_capabilities(), indent=2, sort_keys=False)
