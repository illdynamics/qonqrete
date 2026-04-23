# worqer/path_hygiene.py
# ═══════════════════════════════════════════════════════════════════════════════
# v1.3.10 — Qodeyard hygiene: single source of truth for what qualifies as
# "user source code" vs "qonqrete infrastructure/artifact" inside a worqspace.
#
# Motivation: in v1.3.9 the AI would occasionally emit whole file trees that
# mirrored the qage's internal structure (build/attempts/..., reqap.d/...,
# validation-root/..., etc.) because the prompt context showed the tree.
# The construQtor then happily wrote those files into qodeyard as if they
# were user code, producing exponential nesting like:
#   qodeyard/<proj>/build/attempts/<id>/validation-root/<proj>/reqap.d/cyqleN/...
#
# The Qualifier runner partially protected itself via a skip-dir list, but
# individual adapters (python.py, js_ts.py) did raw rglob() and happily
# linted those nested pollution dirs. And `shutil.copytree(qodeyard,
# validation_root)` in stage_attempt_files snapshotted the whole polluted
# tree on every attempt.
#
# This module centralises:
#   - INFRA_DIR_NAMES      — directory names that must NEVER appear inside a
#                            qodeyard and must never be discovered during
#                            validation / qualification scans
#   - INFRA_PATH_MARKERS   — substring markers that identify qonqrete-emitted
#                            artifact files the AI must never be writing
#                            (qonfirmer.json, _reqap.md, verification.md, etc.)
#   - is_infra_path()      — predicate for "looks like leaked infra"
#   - is_cwd_inside_qodeyard() — guard so agents fail loud if they were
#                            launched with cwd drifted into qodeyard/<sub>/…
#                            instead of at the qage/worqspace root
#   - iter_source_files()  — shared safe walker that respects the skip list
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


# Directories that are *qonqrete infrastructure* and must never be treated
# as user source. Any of these appearing inside a qodeyard is pollution.
# Also used as discovery-walk skip set.
INFRA_DIR_NAMES: frozenset[str] = frozenset({
    # build artifacts & attempt snapshots (the big offenders)
    "build",
    "attempts",
    "validation-root",
    "recovery",
    "staging",
    # review / report artifacts
    "reqap.d",
    "reqap_d",
    # qage-level qonqrete state
    ".qonqrete",
    "qonstructions",
    "sqrapyard",
    "struqture",
    "exeq.d",
    "exeq_d",
    "qontext.d",
    "qontext_d",
    "bloq.d",
    "bloq_d",
    "tasq.d",
    "tasq_d",
    "briq.d",
    "briq_d",
    "qontract.d",
    "qontract_d",
    "qache.d",
    "qache_d",
    "planning",
    # generic noise
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    ".next",
    ".cache",
    ".parcel-cache",
    "coverage",
    "__MACOSX",
})


# Filename / path-fragment markers that identify qonqrete artifact files.
# If an AI-emitted filename contains any of these, it is rejected outright
# — user code never legitimately has these names.
INFRA_PATH_MARKERS: tuple[str, ...] = (
    "attempt-manifest.v1.json",
    "run-manifest.v1.json",
    "build-output-bridge.v1.json",
    "validation/validation-bundle.v1.json",
    "realization/realization-bundle.v1.json",
    "verdict/inspection-input.v1.json",
    "verdict/inspection-verdict.v1.json",
    "verdict/inspection-runtime.v1.json",
    "verdict/repair-plan.v1.json",
    "_qonfirmer.json",
    "_qonfirmer.md",
    "_reqap.md",
    "_verification.md",
    "_smoketest.md",
    "_smoketest.v1.json",
    "recovery-metadata.v1.json",
    "component-contracts.v1.json",
    "build-groups.v1.json",
)


# Prefixes that identify transient qage directories (name pattern: qage_<ts>)
_TRANSIENT_PREFIXES: tuple[str, ...] = ("qage_",)


def _as_parts(rel: Path | str) -> tuple[str, ...]:
    if isinstance(rel, str):
        # normalise separators
        return tuple(p for p in rel.replace("\\", "/").split("/") if p and p != ".")
    return rel.parts


def has_infra_segment(rel: Path | str) -> bool:
    """True if any path component is an infra dir name or qage_* directory."""
    for part in _as_parts(rel):
        if part in INFRA_DIR_NAMES:
            return True
        if any(part.startswith(pref) for pref in _TRANSIENT_PREFIXES):
            return True
    return False


def has_infra_marker(rel: Path | str) -> bool:
    """True if the path contains any filename fragment matching a known
    qonqrete artifact marker."""
    s = str(rel).replace("\\", "/")
    return any(marker in s for marker in INFRA_PATH_MARKERS)


def is_infra_path(rel: Path | str) -> bool:
    """Unified predicate: infra dir anywhere in path OR infra filename marker.
    Use this when deciding whether to reject an AI-emitted filename, skip a
    file during validation discovery, or exclude a path from a copy."""
    return has_infra_segment(rel) or has_infra_marker(rel)


def strip_project_prefix(rel: str, project_names: Iterable[str]) -> str:
    """If `rel`'s first path component matches any of `project_names`,
    strip it. This handles the case where the AI emits
    `test-small/main.py` because it thinks the project lives in a
    subfolder with the run's qonstruction name.

    Returns the possibly-modified relative path string."""
    rel_norm = rel.replace("\\", "/").lstrip("/")
    head, _, tail = rel_norm.partition("/")
    if not tail:
        return rel_norm
    for name in project_names:
        if name and head == name:
            return tail
    return rel_norm


def is_cwd_inside_qodeyard(cwd: Path | None = None) -> Path | None:
    """If the current working directory is resolved to be *inside* a
    `qodeyard/` directory (i.e. some ancestor is named 'qodeyard'),
    return that ancestor. Otherwise return None.

    This is used as a fail-loud guard in agent main()s — if cwd has
    drifted into qodeyard/<sub>/… the agent's notion of worqspace_root
    is wrong and it would write infrastructure files into qodeyard.
    """
    root = (cwd or Path.cwd()).resolve()
    for ancestor in [root, *root.parents]:
        if ancestor.name == "qodeyard":
            return ancestor
    return None


def assert_cwd_outside_qodeyard(agent_name: str = "agent") -> None:
    """Raise RuntimeError with a clear message if cwd has drifted into
    qodeyard/. Call early from agent entrypoints."""
    hit = is_cwd_inside_qodeyard()
    if hit is not None:
        raise RuntimeError(
            f"[{agent_name}] cwd drifted into qodeyard (ancestor: {hit}). "
            f"Refusing to run — worqspace_root would be misresolved and "
            f"infrastructure files (build/, attempts/, reqap.d/, "
            f"validation-root/) would be written inside qodeyard. "
            f"Ensure the launcher sets cwd to the qage/worqspace root, "
            f"NOT any subfolder within qodeyard."
        )


def iter_source_files(root: Path, extra_skip: Iterable[str] = ()) -> Iterable[Path]:
    """Yield files under `root`, pruning INFRA_DIR_NAMES + any extra
    skip names, and silently dropping symlinks (avoids bind-mount loops)."""
    extra = set(extra_skip)
    skip = INFRA_DIR_NAMES | extra
    if not root.exists():
        return
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            name = entry.name
            if entry.is_dir():
                if name in skip:
                    continue
                if any(name.startswith(pref) for pref in _TRANSIENT_PREFIXES):
                    continue
                stack.append(entry)
            elif entry.is_file():
                yield entry


def safe_rglob(root: Path, pattern: str) -> Iterable[Path]:
    """Drop-in replacement for `root.rglob(pattern)` that skips infra dirs.

    Use this instead of `Path.rglob` anywhere the search is supposed to
    cover 'user source under qodeyard'. It avoids scanning build/,
    attempts/, validation-root/, reqap.d/, etc."""
    # Delegate to iter_source_files for the walk, then fnmatch the pattern
    import fnmatch
    for f in iter_source_files(root):
        # Match against the name (pattern semantics users expect from rglob)
        if fnmatch.fnmatch(f.name, pattern):
            yield f


# Back-compat alias used by qualifier/runner.py
_SKIP_DIR_NAMES = INFRA_DIR_NAMES
