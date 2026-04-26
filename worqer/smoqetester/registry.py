# worqer/smoqetester/registry.py
# ═══════════════════════════════════════════════════════════════════════════════
# Extension dispatch + lazy adapter loading for smoqetester.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .base import Adapter


EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ksh": "shell",
    ".js": "js_ts",
    ".jsx": "js_ts",
    ".mjs": "js_ts",
    ".cjs": "js_ts",
    ".ts": "js_ts",
    ".tsx": "js_ts",
    ".html": "html_css",
    ".htm": "html_css",
    ".css": "html_css",
}


def adapter_for_extension(ext: str) -> Optional[str]:
    return EXTENSION_MAP.get(str(ext or "").lower())


def adapter_for_file(file_path: Path) -> Optional[str]:
    return adapter_for_extension(file_path.suffix)


_ADAPTER_CACHE: dict[str, Adapter] = {}


def _load_python() -> Adapter:
    from .adapters.python import PythonAdapter

    return PythonAdapter()


def _load_shell() -> Adapter:
    from .adapters.shell import ShellAdapter

    return ShellAdapter()


def _load_js_ts() -> Adapter:
    from .adapters.js_ts import JsTsAdapter

    return JsTsAdapter()


def _load_html_css() -> Adapter:
    from .adapters.html_css import HtmlCssAdapter

    return HtmlCssAdapter()


_LOADERS: dict[str, Callable[[], Adapter]] = {
    "python": _load_python,
    "shell": _load_shell,
    "js_ts": _load_js_ts,
    "html_css": _load_html_css,
}


def load_adapter(name: str) -> Adapter:
    if name in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[name]
    loader = _LOADERS.get(name)
    if loader is None:
        raise KeyError(f"unknown adapter: {name}")
    adapter = loader()
    _ADAPTER_CACHE[name] = adapter
    return adapter


def register_adapter(name: str, loader: Callable[[], Adapter]) -> None:
    _LOADERS[name] = loader
    _ADAPTER_CACHE.pop(name, None)


def clear_cache() -> None:
    _ADAPTER_CACHE.clear()


def known_adapter_names() -> list[str]:
    return sorted(_LOADERS.keys())


__all__ = [
    "EXTENSION_MAP",
    "adapter_for_extension",
    "adapter_for_file",
    "load_adapter",
    "register_adapter",
    "clear_cache",
    "known_adapter_names",
]
