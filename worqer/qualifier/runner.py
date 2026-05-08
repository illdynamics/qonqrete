# worqer/qualifier/runner.py
# ═══════════════════════════════════════════════════════════════════════════════
# Qualifier runner — walks the qodeyard (or a caller-supplied scoped subset
# of it), groups files by extension, dispatches to the right adapter, and
# aggregates everything into a single VerificationReport.
#
# Extension-driven + lazy: an adapter is only imported and invoked if at
# least one file with its extension is present in the ACTIVE scope. Pure-
# Python cyqles never touch the shell / JS / HTML adapters.
#
# v2.x adds scope-aware operation via the optional ``changed_files`` kwarg:
#   - ``changed_files=None``  (or empty)  →  full qodeyard scan  (legacy)
#   - ``changed_files=[paths]``           →  scoped to those paths
#
# Scoped semantics are strict:
#   - repo-relative paths, or absolutes under qodeyard, are both accepted
#   - path separators are normalized
#   - duplicates are collapsed while preserving deterministic order
#   - files outside the qodeyard are silently dropped
#   - missing files are silently dropped
#   - files living inside the usual skip dirs (node_modules / .venv / …)
#     are silently dropped — same exclusion set as full-scan discovery
#   - only scoped files that actually match an adapter extension survive
#   - if the scope ends up with at least one usable file, we run scoped —
#     we do NOT expand to a full scan just because only one language was
#     touched
#   - if the scope ends up empty (nothing usable survived the filter) we
#     fall back to a full qodeyard scan, so callers passing a stale or
#     trivially wrong manifest still get meaningful output
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional, Union

from .base import QualifyContext, rel_name, result_error, result_info
from .models import VerificationReport
from .registry import adapter_for_file, load_adapter

# v1.3.10: Unified skip list across construQtor / inspeQtor / Qualifier.
# Single source of truth in worqer/path_hygiene.py — prevents drift.
try:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from path_hygiene import (
        INFRA_DIR_NAMES as _SHARED_INFRA_NAMES,
        is_generated_output_dir as _is_generated_output_dir,
        is_source_junk_file as _is_source_junk_file,
    )
except ImportError:
    _SHARED_INFRA_NAMES = frozenset()

    def _is_generated_output_dir(path: Path) -> bool:
        return path.name == "out" and path.parent.name == "vscode-extension"

    def _is_source_junk_file(path: Path) -> bool:
        return path.name == ".DS_Store" or path.name.startswith("._") or path.suffix == ".pyc"


# Paths inside qodeyard that we skip during file discovery. Generated /
# vendored / VCS content has no business being validated. Used by both
# the full-scan path and the scoped-path filter so the two modes share
# identical exclusion semantics.
#
# v1.3.10: Expanded from the v1.3.9 list (which missed attempts/,
# validation-root/, recovery/, reqap.d/, etc.) and unified with
# path_hygiene.INFRA_DIR_NAMES so all three layers share one source of truth.
_SKIP_DIR_NAMES = _SHARED_INFRA_NAMES | {
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
    "build",
    ".next",
    ".cache",
    ".parcel-cache",
    "coverage",
    "__MACOSX",
    # v1.3.10 additions — qonqrete internals that must NEVER be linted
    "attempts",
    "validation-root",
    "recovery",
    "staging",
    "reqap.d",
    ".qonqrete",
    "qonstructions",
    "struqture",
    "exeq.d",
    "qontext.d",
    "bloq.d",
    "tasq.d",
    "briq.d",
    "qontract.d",
    "qache.d",
    "planning",
    "sqrapyard",
}

_HTML_EXTS = {".html", ".htm"}
_CSS_EXTS = {".css"}
_JS_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
_FRONTEND_EXTS = _HTML_EXTS | _CSS_EXTS | _JS_EXTS
_HTML_REF_PATTERN = re.compile(
    r"""(?:src|href)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_CSS_URL_PATTERN = re.compile(r"""url\(([^)]+)\)""", re.IGNORECASE)
_JS_IMPORT_REF_PATTERN = re.compile(
    r"""
    ^\s*import\s+(?:[^'"]*?\s+from\s*)?["'](?P<import>[^"']+)["']
    |
    ^\s*export\s+[^'"]*?\s+from\s*["'](?P<export>[^"']+)["']
    |
    \brequire\s*\(\s*["'](?P<require>[^"']+)["']\s*\)
    |
    \bimport\s*\(\s*["'](?P<dynamic>[^"']+)["']\s*\)
    """,
    re.MULTILINE | re.VERBOSE,
)
_REMOTE_REF_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _iter_source_files(root: Path) -> Iterable[Path]:
    """Yield source files under root, skipping known noise dirs."""
    if not root.exists():
        return
    # We walk manually so we can prune skip dirs cheaply.
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                # Don't follow symlinks — avoids infinite loops and
                # reading host FS trees that were bind-mounted in.
                continue
            if entry.is_dir():
                if entry.name in _SKIP_DIR_NAMES:
                    continue
                if _is_generated_output_dir(entry):
                    continue
                stack.append(entry)
            elif entry.is_file():
                if _is_source_junk_file(entry):
                    continue
                yield entry


def _group_files_by_adapter(root: Path) -> dict[str, list[Path]]:
    """Scan `root` once and bucket handled files by adapter name."""
    buckets: dict[str, list[Path]] = {}
    for f in _iter_source_files(root):
        adapter_name = adapter_for_file(f)
        if adapter_name is None:
            continue
        buckets.setdefault(adapter_name, []).append(f)
    # Stable order for deterministic reports
    for name in buckets:
        buckets[name].sort()
    return buckets


# ─── scoped-mode helpers ────────────────────────────────────────────────────

def _path_has_skip_segment(rel: Path) -> bool:
    """True if any path component is in the skip-dir exclusion set."""
    return any(part in _SKIP_DIR_NAMES for part in rel.parts)


def normalize_scoped_files(
    qodeyard_path: Path,
    changed_files: Optional[Iterable[Union[str, Path]]],
) -> list[Path]:
    """Normalize a caller-supplied scope manifest into usable file Paths.

    Rules (all applied in order, all silent — nothing raises):
      1. ``None`` / empty iterable → ``[]``
      2. each entry becomes a ``Path``; relative entries are resolved
         against ``qodeyard_path``; path separators are normalized by
         ``Path`` construction
      3. entries that don't sit under the resolved qodeyard root are
         dropped (no traversal out)
      4. entries that don't exist on disk are dropped
      5. entries whose relative path contains any skip-dir segment are
         dropped
      6. duplicates (same resolved path) are collapsed
      7. the surviving list is sorted for deterministic downstream
         ordering — scoped runs must not flap based on caller ordering

    Returns an empty list if nothing usable survives. Callers can use
    that signal to decide between scoped and full-scan modes.
    """
    if not changed_files:
        return []

    try:
        qodeyard_resolved = qodeyard_path.resolve()
    except OSError:
        qodeyard_resolved = qodeyard_path

    seen: set[Path] = set()
    ordered: list[Path] = []
    for raw in changed_files:
        if raw is None:
            continue
        try:
            candidate = Path(raw) if isinstance(raw, Path) else Path(str(raw))
        except (TypeError, ValueError):
            continue

        if not candidate.is_absolute():
            candidate = qodeyard_path / candidate

        try:
            resolved = candidate.resolve()
        except OSError:
            continue

        # Must live under the qodeyard — no jailbreaks.
        try:
            rel = resolved.relative_to(qodeyard_resolved)
        except ValueError:
            continue

        if _path_has_skip_segment(rel):
            continue

        if not resolved.is_file():
            # Silently drop missing / directory-typed / special-FS entries.
            continue

        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)

    ordered.sort()
    return ordered


def _group_scoped_files_by_adapter(
    scoped_files: list[Path],
) -> dict[str, list[Path]]:
    """Bucket an already-normalized scope list by adapter.

    Files whose extension has no registered adapter are silently
    dropped. Output is sorted per-bucket for determinism, matching
    full-scan output shape exactly.
    """
    buckets: dict[str, list[Path]] = {}
    for f in scoped_files:
        adapter_name = adapter_for_file(f)
        if adapter_name is None:
            continue
        buckets.setdefault(adapter_name, []).append(f)
    for name in buckets:
        buckets[name].sort()
    return buckets


def _clean_ref(raw: str) -> str:
    value = str(raw or "").strip().strip("\"'")
    value = value.split("#", 1)[0]
    value = value.split("?", 1)[0]
    return value


def _is_local_ref(ref: str) -> bool:
    if not ref:
        return False
    if ref.startswith("#") or ref.startswith("//"):
        return False
    if _REMOTE_REF_PATTERN.match(ref):
        return False
    return True


def _frontend_files_from_buckets(buckets: dict[str, list[Path]]) -> list[Path]:
    files: list[Path] = []
    for bucket_files in buckets.values():
        for file_path in bucket_files:
            if file_path.suffix.lower() in _FRONTEND_EXTS:
                files.append(file_path)
    return files


def _count_local_asset_references(frontend_files: Iterable[Path]) -> int:
    count = 0
    for file_path in frontend_files:
        ext = file_path.suffix.lower()
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        refs: list[str] = []
        if ext in _HTML_EXTS:
            refs.extend(match.group(1) for match in _HTML_REF_PATTERN.finditer(text))
        elif ext in _CSS_EXTS:
            refs.extend(match.group(1) for match in _CSS_URL_PATTERN.finditer(text))
        elif ext in _JS_EXTS:
            for match in _JS_IMPORT_REF_PATTERN.finditer(text):
                spec = next((v for v in match.groupdict().values() if v), "")
                if spec.startswith("./") or spec.startswith("../"):
                    refs.append(spec)
        count += sum(1 for ref in refs if _is_local_ref(_clean_ref(ref)))
    return count


def _expand_scoped_frontend_references(
    qodeyard_path: Path,
    scoped_files: list[Path],
) -> list[Path]:
    """Include local JS/CSS files referenced by scoped HTML files.

    A frontend repair often touches only index.html while the behavioral
    surface lives in linked browser JS/CSS. Keeping this expansion scoped
    preserves fast validation while avoiding an HTML-only coverage blind spot.
    """
    try:
        qodeyard_resolved = qodeyard_path.resolve()
    except OSError:
        qodeyard_resolved = qodeyard_path

    expanded = list(scoped_files)
    seen = {p.resolve() for p in expanded}
    for html_file in scoped_files:
        if html_file.suffix.lower() not in _HTML_EXTS:
            continue
        try:
            text = html_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in _HTML_REF_PATTERN.finditer(text):
            cleaned = _clean_ref(match.group(1))
            if not _is_local_ref(cleaned):
                continue
            candidate = (html_file.parent / cleaned).resolve()
            if candidate.suffix.lower() not in (_CSS_EXTS | _JS_EXTS):
                continue
            try:
                rel = candidate.relative_to(qodeyard_resolved)
            except ValueError:
                continue
            if _path_has_skip_segment(rel) or not candidate.is_file():
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            expanded.append(candidate)
    expanded.sort()
    return expanded


def _has_validation_infra_failure(report: VerificationReport) -> bool:
    infra_markers = (":loader", ":preflight", ":crash")
    return any(
        (not result.passed)
        and result.severity == "error"
        and any(marker in result.check_type for marker in infra_markers)
        for result in report.results
    )


def _has_low_coverage_frontend_results(report: VerificationReport) -> bool:
    weak_markers = (
        "html_css:html-fallback",
        "html_css:css-fallback",
        "js_ts:node-check",
    )
    for result in report.results:
        if result.check_type.startswith(("html_css:", "js_ts:")):
            message = str(result.message or "").lower()
            if result.check_type in weak_markers or "degraded" in message:
                return True
            if result.severity == "info" and (
                "not found" in message or "skipped" in message
            ):
                return True
    return False


def _finalize_report_metadata(
    report: VerificationReport,
    buckets: dict[str, list[Path]],
) -> None:
    frontend_files = _frontend_files_from_buckets(buckets)
    frontend_results = [
        result for result in report.results
        if result.check_type.startswith(("html_css:", "js_ts:"))
    ]
    blocking_errors = sum(
        1 for result in frontend_results
        if (not result.passed) and result.severity == "error"
    )
    warnings = sum(
        1 for result in frontend_results
        if (not result.passed) and result.severity == "warning"
    )
    advisory = sum(
        1 for result in frontend_results
        if result.severity == "info"
    )
    low_frontend_coverage = _has_low_coverage_frontend_results(report)

    if not frontend_files:
        coverage_summary = "no_frontend_files_checked"
    elif blocking_errors:
        coverage_summary = "frontend_blocking_errors_detected"
    elif low_frontend_coverage:
        coverage_summary = "frontend_static_low_coverage"
    else:
        coverage_summary = "frontend_required_validation_passed"

    report.frontend_validation_summary = {
        "html_files_checked": sum(1 for p in frontend_files if p.suffix.lower() in _HTML_EXTS),
        "css_files_checked": sum(1 for p in frontend_files if p.suffix.lower() in _CSS_EXTS),
        "js_files_checked": sum(1 for p in frontend_files if p.suffix.lower() in _JS_EXTS),
        "local_asset_references_checked": _count_local_asset_references(frontend_files),
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "advisory_findings": advisory,
        "validation_coverage_summary": coverage_summary,
    }

    if _has_validation_infra_failure(report):
        report.validation_outcome = "FAILED_VALIDATION_INFRA"
    elif report.errors > 0:
        report.validation_outcome = "FAILED_BLOCKING_VALIDATION"
    elif report.warnings > 0:
        report.validation_outcome = "PARTIAL_VALIDATION_DEGRADED"
    elif frontend_files and low_frontend_coverage:
        report.validation_outcome = "SUCCESS_LOW_COVERAGE"
    elif report.files_checked == 0:
        report.validation_outcome = "SUCCESS_LOW_COVERAGE"
    else:
        report.validation_outcome = "SUCCESS_VERIFIED"


def run_verification(
    qodeyard_path: Path,
    qontext_path: Optional[Path],
    cycle_num: str,
    config: dict,
    changed_files: Optional[Iterable[Union[str, Path]]] = None,
    tier: str = "low",
) -> VerificationReport:
    """Run all verification checks on the qodeyard.

    Backwards-compatible: existing 4-positional callers (``qodeyard_path,
    qontext_path, cycle_num, config``) continue to work unchanged and
    trigger a full scan. Passing ``changed_files`` enables scoped mode —
    see module docstring for the exact semantics.

    Args:
      qodeyard_path: root of the source tree to qualify.
      qontext_path:  optional qontext directory (consumed by the Python
                     adapter's skeleton-match check). May be ``None``.
      cycle_num:     opaque label stamped into the report; used by the
                     markdown renderer only.
      config:        raw full-config dict (the real config tree, NOT a
                     flattened agent-only copy). Adapters read their own
                     sections off it — missing keys are tolerated.
      changed_files: optional iterable of repo-relative (or qodeyard-
                     absolute) paths. When provided and non-empty and
                     at least one entry survives normalization, the
                     runner operates in SCOPED mode: only those files
                     are qualified, and only adapters that actually
                     match at least one scoped file are loaded.
      tier:          Task tier (low, medium, high) for severity gating.
    """
    qodeyard_path = Path(qodeyard_path)
    if qontext_path is not None:
        qontext_path = Path(qontext_path)

    report = VerificationReport(cycle_num=str(cycle_num))

    # Legacy per-check toggles live under verification.checks.*
    checks_config = (config or {}).get("verification", {}).get("checks", {}) or {}
    ctx = QualifyContext(
        qodeyard_path=qodeyard_path,
        qontext_path=qontext_path,
        config=config or {},
        python_checks=dict(checks_config),
        tier=str(tier).lower(),
    )

    # ── Phase 1: decide scoped vs full, then scan ───────────────────────
    scoped = normalize_scoped_files(qodeyard_path, changed_files)
    if scoped:
        scoped = _expand_scoped_frontend_references(qodeyard_path, scoped)
    scoped_mode = bool(scoped)

    if scoped_mode:
        buckets = _group_scoped_files_by_adapter(scoped)
        # If the caller gave us a scope but NOTHING in it matched any
        # known adapter, fall back to full-scan so we don't silently
        # produce an empty "SUCCESS" report. This fallback is the only
        # case where scoped intent yields a full scan — see module docs.
        if not buckets:
            scoped_mode = False
            buckets = _group_files_by_adapter(qodeyard_path)
    else:
        buckets = _group_files_by_adapter(qodeyard_path)

    total_handled = sum(len(v) for v in buckets.values())
    report.total_files = total_handled

    if not buckets:
        mode_label = "scoped" if scoped_mode else "full"
        _finalize_report_metadata(report, buckets)
        print(
            f"[Qualifier] No handled source files found "
            f"({mode_label} scan).",
            flush=True,
        )
        print(
            f"[Qualifier] Verification complete: {report.overall_status}",
            flush=True,
        )
        return report

    adapter_summary = ", ".join(
        f"{k}={len(v)}" for k, v in sorted(buckets.items())
    )
    scope_tag = (
        f"scoped({len(scoped)})" if scoped_mode else "full-scan"
    )
    print(
        f"[Qualifier] Dispatching [{scope_tag}]: {adapter_summary} "
        f"(total {total_handled} files)",
        flush=True,
    )

    # ── Phase 2: per-adapter preflight + qualify ────────────────────────
    for adapter_name in sorted(buckets.keys()):
        files = buckets[adapter_name]
        try:
            adapter = load_adapter(adapter_name)
        except Exception as exc:
            # Registry/loader blew up — record it and move on.
            report.add_result(result_error(
                file_path="-",
                check_type=f"{adapter_name}:loader",
                message=f"Adapter failed to load: {exc}",
            ))
            continue

        report.adapters_triggered.append(adapter.name)

        # Preflight: tool discovery diagnostics, etc.
        adapter_preflight_results = []
        try:
            adapter_preflight_results = list(adapter.preflight(ctx) or [])
            for r in adapter_preflight_results:
                report.add_result(r)
        except Exception as exc:
            report.add_result(result_error(
                file_path="-",
                check_type=f"{adapter_name}:preflight",
                message=f"Preflight crashed: {exc}",
            ))

        missing_tool_checks = [
            r.check_type
            for r in adapter_preflight_results
            if r.severity == "info" and r.file_path == "-"
        ]

        # Per-file qualification
        for fp in files:
            report.files_checked += 1
            rel = rel_name(fp, qodeyard_path)
            try:
                results = adapter.qualify(fp, ctx) or []
            except Exception as exc:
                results = [result_error(
                    file_path=rel,
                    check_type=f"{adapter_name}:crash",
                    message=f"Adapter crashed: {exc}",
                )]

            already_has_file_row = any(r.file_path == rel for r in report.results)
            if not results and not already_has_file_row:
                if missing_tool_checks:
                    results = [result_info(
                        file_path=rel,
                        check_type=f"{adapter_name}:summary",
                        message=(
                            "Adapter matched this file, but no file-level checks ran "
                            "because required tool(s) were unavailable: "
                            + ", ".join(sorted(missing_tool_checks))
                        ),
                    )]
                else:
                    results = [result_info(
                        file_path=rel,
                        check_type=f"{adapter_name}:summary",
                        message=(
                            "Adapter matched this file, but emitted no file-level "
                            "diagnostics."
                        ),
                    )]
            for r in results:
                report.add_result(r)

    _finalize_report_metadata(report, buckets)
    print(
        f"[Qualifier] Verification complete: {report.overall_status}",
        flush=True,
    )
    print(
        f"        ✅ {report.passed} | "
        f"⚠️ {report.warnings} | "
        f"❌ {report.errors}",
        flush=True,
    )
    return report


__all__ = ["run_verification", "normalize_scoped_files"]
