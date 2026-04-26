from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

from .base import Compressor


EXTENSION_MAP: dict[str, str] = {
    '.py': 'python_compressor',
    '.pyi': 'python_compressor',
    '.sh': 'shell_compressor',
    '.bash': 'shell_compressor',
    '.zsh': 'shell_compressor',
    '.ksh': 'shell_compressor',
    '.js': 'js_ts_compressor',
    '.jsx': 'js_ts_compressor',
    '.mjs': 'js_ts_compressor',
    '.cjs': 'js_ts_compressor',
    '.ts': 'js_ts_compressor',
    '.tsx': 'js_ts_compressor',
    '.html': 'html_css_compressor',
    '.htm': 'html_css_compressor',
    '.css': 'html_css_compressor',
    '.scss': 'html_css_compressor',
    '.sass': 'html_css_compressor',
    '.less': 'html_css_compressor',
}

_LOADED: dict[str, Compressor] = {}


def compressor_for_extension(ext: str) -> Optional[str]:
    return EXTENSION_MAP.get(ext.lower())


def get_compressor(name: str) -> Compressor:
    if name in _LOADED:
        return _LOADED[name]
    module = importlib.import_module(f'qompressor_extractors.{name}')
    compressor = module.get_compressor()
    _LOADED[name] = compressor
    return compressor


def get_compressor_for_file(file_path: Path) -> Optional[Compressor]:
    name = compressor_for_extension(file_path.suffix.lower())
    if not name:
        return None
    return get_compressor(name)
