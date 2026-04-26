# worqer/qualifier/discovery.py
# ═══════════════════════════════════════════════════════════════════════════════
# External tool discovery.
#
# Resolution order (first hit wins):
#   1. Local node_modules/.bin/<tool>   (under qodeyard or repo root)
#   2. Repo-root node_modules/.bin/<tool>  (for Node tools bundled with QonQrete)
#   3. PATH lookup via shutil.which
#
# Missing tools NEVER raise — callers receive None and decide how to report.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


# Where QonQrete's bundled Node tools land in the container.
# See Dockerfile: global npm installs land under /usr/local/lib/node_modules
# and /usr/local/bin, which is already on PATH. But for dev environments
# without a global install, we also probe the repo's own node_modules/.bin.
_REPO_ROOT_MARKERS = ("worqer", "worqspace", "qonqrete.sh")


def _find_repo_root(start: Path) -> Optional[Path]:
    """Walk upward from `start` looking for QonQrete's repo root markers."""
    cur = start.resolve()
    for _ in range(10):  # bounded
        if all((cur / m).exists() for m in _REPO_ROOT_MARKERS):
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _node_bin_candidates(cwd: Optional[Path]) -> Iterable[Path]:
    """Yield candidate directories that might contain node_modules/.bin."""
    seen: set[Path] = set()
    if cwd:
        cwd = Path(cwd).resolve()
        # Walk up from cwd looking for node_modules/.bin
        cur: Optional[Path] = cwd
        for _ in range(8):
            if cur is None:
                break
            candidate = cur / "node_modules" / ".bin"
            if candidate not in seen:
                seen.add(candidate)
                yield candidate
            if cur.parent == cur:
                break
            cur = cur.parent

    # Also probe the QonQrete repo root itself
    here = Path(__file__).resolve()
    repo = _find_repo_root(here)
    if repo:
        candidate = repo / "node_modules" / ".bin"
        if candidate not in seen:
            seen.add(candidate)
            yield candidate


@lru_cache(maxsize=128)
def _cached_which(name: str) -> Optional[str]:
    return shutil.which(name)


def find_binary(name: str, cwd: Optional[Path] = None) -> Optional[str]:
    """Locate an external binary.

    Returns the absolute path as a string, or None if nothing suitable
    is found. Never raises.
    """
    # 1+2. Local node_modules/.bin under cwd / repo root
    for bin_dir in _node_bin_candidates(cwd):
        candidate = bin_dir / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
        # Some Windows installs use .cmd / .ps1 — we only support POSIX.

    # 3. PATH lookup
    hit = _cached_which(name)
    return hit


def clear_cache() -> None:
    """Clear the which() cache. Useful in tests."""
    _cached_which.cache_clear()


__all__ = ["find_binary", "clear_cache"]
