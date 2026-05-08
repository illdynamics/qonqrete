from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT_MARKERS = ("worqer", "worqspace", "qonqrete.sh")
_HELPER_REL = Path('worqer/node_helpers/multilang_native.cjs')


@lru_cache(maxsize=1)
def repo_root() -> Path:
    cur = Path(__file__).resolve().parent
    for _ in range(12):
        if all((cur / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def helper_script() -> Path:
    return (repo_root() / _HELPER_REL).resolve()


@lru_cache(maxsize=1)
def find_node() -> Optional[str]:
    return shutil.which('node')


@lru_cache(maxsize=1)
def repo_node_modules_path() -> Path:
    return (repo_root() / 'node_modules').resolve()


@lru_cache(maxsize=1)
def global_node_modules_path() -> Optional[str]:
    npm = shutil.which('npm')
    if not npm:
        return None
    try:
        proc = subprocess.run([npm, 'root', '-g'], text=True, capture_output=True, check=True, timeout=10)
        value = proc.stdout.strip()
        return value or None
    except Exception:
        return None


@lru_cache(maxsize=1)
def helper_capabilities() -> dict[str, Any]:
    node = find_node()
    script = helper_script()
    repo_modules = repo_node_modules_path()
    global_modules = global_node_modules_path()
    base: dict[str, Any] = {
        'available': False,
        'typescript': False,
        'postcss': False,
        'parse5': False,
        'node_path': node,
        'helper_script': str(script),
        'helper_script_exists': script.exists(),
        'repo_node_modules': str(repo_modules),
        'repo_node_modules_exists': repo_modules.exists(),
        'global_node_modules': global_modules,
        'global_node_modules_exists': bool(global_modules and Path(global_modules).exists()),
    }
    if not node or not script.exists():
        base['reason'] = 'node helper unavailable'
        return base
    try:
        payload = run_node_helper('capabilities')
    except Exception as exc:
        base['reason'] = str(exc)
        return base
    result = dict(base)
    result.update(payload)
    result['available'] = bool(payload.get('available', True))
    result.setdefault('reason', None)
    return result



def _node_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = os.environ.copy()
    node_paths: list[str] = []
    repo_modules = repo_node_modules_path()
    if repo_modules.exists():
        node_paths.append(str(repo_modules))
    global_modules = global_node_modules_path()
    if global_modules:
        node_paths.append(global_modules)
    existing = env.get('NODE_PATH')
    if existing:
        node_paths.append(existing)
    if node_paths:
        env['NODE_PATH'] = os.pathsep.join(dict.fromkeys(node_paths))
    if extra:
        env.update(extra)
    return env



def run_node_helper(command: str, *, stdin_text: Optional[str] = None, args: Optional[list[str]] = None, timeout: int = 15) -> dict[str, Any]:
    node = find_node()
    script = helper_script()
    if not node:
        raise RuntimeError('node executable not found')
    if not script.exists():
        raise RuntimeError(f'node helper script not found: {script}')
    try:
        proc = subprocess.run(
            [node, str(script), command] + (args or []),
            input=stdin_text,
            text=True,
            capture_output=True,
            env=_node_env(),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'node helper timed out after {timeout} seconds') from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or '').strip()
        raise RuntimeError(stderr or f'node helper failed with exit code {proc.returncode}')
    try:
        return json.loads(proc.stdout or '{}')
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'node helper returned invalid JSON: {exc}') from exc



def clear_tooling_caches() -> None:
    for func in (repo_root, helper_script, find_node, repo_node_modules_path, global_node_modules_path, helper_capabilities):
        func.cache_clear()
