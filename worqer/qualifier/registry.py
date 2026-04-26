# worqer/qualifier/registry.py
# ═══════════════════════════════════════════════════════════════════════════════
# Adapter registry + extension dispatch.
#
# Core principle: extension-driven, lazy-loaded. Adapter modules are NOT
# imported until a file with their extension is actually encountered.
# That keeps the cold path cheap — a pure-Python cyqle never imports
# the shell / JS / HTML adapters.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .base import Adapter


# File-extension -> adapter name dispatch table. Lowercase, with dot.
EXTENSION_MAP: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",
    # Shell
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ksh": "shell",
    # JavaScript / TypeScript
    ".js": "js_ts",
    ".jsx": "js_ts",
    ".mjs": "js_ts",
    ".cjs": "js_ts",
    ".ts": "js_ts",
    ".tsx": "js_ts",
    # HTML / CSS (truthful shipped scope: HTML + plain CSS only)
    ".html": "html_css",
    ".htm": "html_css",
    ".css": "html_css",
}


def adapter_for_extension(ext: str) -> Optional[str]:
    """Return adapter name for a file extension, or None if unhandled."""
    return EXTENSION_MAP.get(ext.lower())


def adapter_for_file(file_path: Path) -> Optional[str]:
    """Return adapter name for a file path, or None if unhandled."""
    return adapter_for_extension(file_path.suffix)


# ─── lazy adapter loader ───────────────────────────────────────────────────

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
    """Load (and cache) an adapter by name. Raises KeyError if unknown."""
    if name in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[name]
    loader = _LOADERS.get(name)
    if loader is None:
        raise KeyError(f"unknown adapter: {name}")
    adapter = loader()
    _ADAPTER_CACHE[name] = adapter
    return adapter


def register_adapter(name: str, loader: Callable[[], Adapter]) -> None:
    """Register a custom adapter loader. Primarily for tests and extensions."""
    _LOADERS[name] = loader
    _ADAPTER_CACHE.pop(name, None)


def clear_cache() -> None:
    """Clear adapter cache. Primarily for tests."""
    _ADAPTER_CACHE.clear()


def known_adapter_names() -> list[str]:
    """All registered adapter names (loaded or not)."""
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
