from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

from .base import Extractor


EXTENSION_MAP: dict[str, str] = {
    '.py': 'python_extractor',
    '.pyi': 'python_extractor',
    '.sh': 'shell_extractor',
    '.bash': 'shell_extractor',
    '.zsh': 'shell_extractor',
    '.ksh': 'shell_extractor',
    '.js': 'js_ts_extractor',
    '.jsx': 'js_ts_extractor',
    '.mjs': 'js_ts_extractor',
    '.cjs': 'js_ts_extractor',
    '.ts': 'js_ts_extractor',
    '.tsx': 'js_ts_extractor',
    '.html': 'html_css_extractor',
    '.htm': 'html_css_extractor',
    '.css': 'html_css_extractor',
    '.scss': 'html_css_extractor',
    '.sass': 'html_css_extractor',
    '.less': 'html_css_extractor',
}

_LOADED: dict[str, Extractor] = {}


def extractor_for_extension(ext: str) -> Optional[str]:
    return EXTENSION_MAP.get(ext.lower())


def get_extractor(name: str) -> Extractor:
    if name in _LOADED:
        return _LOADED[name]
    module = importlib.import_module(f'qontextor_extractors.{name}')
    extractor = module.get_extractor()
    _LOADED[name] = extractor
    return extractor


def get_extractor_for_file(file_path: Path) -> Optional[Extractor]:
    name = extractor_for_extension(file_path.suffix.lower())
    if not name:
        return None
    return get_extractor(name)
