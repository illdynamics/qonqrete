# worqer/smoqetester/discovery.py
# ═══════════════════════════════════════════════════════════════════════════════
# External binary discovery for smoketest adapters.
# Local node_modules/.bin paths are preferred over PATH where applicable.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


_REPO_ROOT_MARKERS = ("worqer", "worqspace", "qonqrete.sh")


def _find_repo_root(start: Path) -> Optional[Path]:
    cur = start.resolve()
    for _ in range(10):
        if all((cur / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _node_bin_candidates(cwd: Optional[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    if cwd:
        cur = Path(cwd).resolve()
        for _ in range(8):
            candidate = cur / "node_modules" / ".bin"
            if candidate not in seen:
                seen.add(candidate)
                yield candidate
            if cur.parent == cur:
                break
            cur = cur.parent

    repo = _find_repo_root(Path(__file__).resolve())
    if repo:
        candidate = repo / "node_modules" / ".bin"
        if candidate not in seen:
            seen.add(candidate)
            yield candidate


@lru_cache(maxsize=128)
def _cached_which(name: str) -> Optional[str]:
    return shutil.which(name)


def _path_candidate(name: str, cwd: Optional[Path]) -> Optional[str]:
    if not name or "/" not in name:
        return None

    candidate = Path(name)
    if not candidate.is_absolute() and cwd is not None:
        candidate = Path(cwd) / candidate

    try:
        absolute = candidate.absolute()
    except OSError:
        return None

    if absolute.exists() and os.access(absolute, os.X_OK):
        return str(absolute)
    return None


def find_binary(name: str, cwd: Optional[Path] = None) -> Optional[str]:
    """Resolve an executable path, returning None when missing."""
    path_hit = _path_candidate(name, cwd)
    if path_hit:
        return path_hit

    if "/" in str(name):
        return None

    for bin_dir in _node_bin_candidates(cwd):
        candidate = bin_dir / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    return _cached_which(name)


def clear_cache() -> None:
    _cached_which.cache_clear()


__all__ = ["find_binary", "clear_cache"]
