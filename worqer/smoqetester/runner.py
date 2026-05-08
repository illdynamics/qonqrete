# worqer/smoqetester/runner.py
# ═══════════════════════════════════════════════════════════════════════════════
# Scope-aware smoketest runner with lazy adapter loading.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

from .base import Adapter, SmoketestContext, rel_name, truncate_output
from .dependency_gate import run_dependency_gate
from .models import STATUS_ERROR, SmoketestReport, SmoketestResult, EXECUTION_KIND_STATIC
from .registry import adapter_for_file, load_adapter

try:
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


def _path_has_skip_segment(rel: Path) -> bool:
    """True if any path component is in the skip-dir exclusion set."""
    return any(part in _SKIP_DIR_NAMES for part in rel.parts)


def _iter_source_files(root: Path) -> Iterable[Path]:
    """Yield source files under root, skipping known noise dirs."""
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


def normalize_scoped_files(
    qodeyard_path: Path,
    changed_files: Optional[Iterable[Union[str, Path]]],
) -> list[Path]:
    """Normalize a caller-supplied scope manifest into usable file Paths."""
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

        try:
            rel = resolved.relative_to(qodeyard_resolved)
        except ValueError:
            continue

        if _path_has_skip_segment(rel):
            continue
        if not resolved.is_file():
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)

    ordered.sort()
    return ordered


def _group_files_by_adapter(files: list[Path]) -> dict[str, list[Path]]:
    buckets: dict[str, list[Path]] = {}
    for file_path in files:
        adapter_name = adapter_for_file(file_path)
        if adapter_name is None:
            continue
        buckets.setdefault(adapter_name, []).append(file_path)
    for adapter_name in buckets:
        buckets[adapter_name].sort()
    return buckets


def _normalize_smoke_config(config: dict | None) -> dict:
    root = dict(_DEFAULT_SMOKE_CONFIG)
    full = config or {}
    smoke = (
        (full.get("agents") or {})
        .get("inspeqtor", {})
        .get("smoketest", {})
    )
    if isinstance(smoke, dict):
        for k, v in smoke.items():
            if k in root:
                root[k] = v
    return root


_DEFAULT_SMOKE_CONFIG = {
    "enabled": True,
    "mode": "scoped",
    "timeout_seconds": 60,
    "max_output_chars": 8000,
    "adapters": {},
}

_DEFAULT_ADAPTER_CONFIG = {
    "enabled": True,
}


def _append_report_result(report: SmoketestReport, result: SmoketestResult, max_chars: int) -> None:
    result.stdout = truncate_output(result.stdout, max_chars)
    result.stderr = truncate_output(result.stderr, max_chars)
    report.add_result(result)


def run_smoketest(
    qodeyard_path: Path,
    cycle_num: str,
    config: dict,
    changed_files: Optional[Iterable[Union[str, Path]]] = None,
) -> SmoketestReport:
    qodeyard_path = Path(qodeyard_path)
    smoke_config = _normalize_smoke_config(config)

    report = SmoketestReport(
        cycle_num=str(cycle_num),
        mode=smoke_config["mode"],
        enabled=bool(smoke_config["enabled"]),
    )

    if not report.enabled:
        report.add_result(SmoketestResult(
            adapter="smoketest",
            name="disabled",
            status="SKIP",
            executed=False,
            message="Smoketest disabled by config.",
        ))
        return report

    active_files: list[Path]
    if smoke_config["mode"] == "scoped" and changed_files is not None:
        active_files = normalize_scoped_files(qodeyard_path, changed_files)
        if not active_files:
            report.add_result(SmoketestResult(
                adapter="smoketest",
                name="scope_empty",
                status="SKIP",
                executed=False,
                message="Scoped smoketest skipped because no runnable files survived scope filtering.",
            ))
            return report
    else:
        active_files = sorted(_iter_source_files(qodeyard_path))
        if smoke_config["mode"] == "scoped":
            report.mode = "full"

    buckets = _group_files_by_adapter(active_files)
    report.total_files = len(active_files)

    if bool((smoke_config.get("dependency_gate") or {}).get("enabled", True)):
        dep_ctx = SmoketestContext(
            qodeyard_path=qodeyard_path,
            cycle_num=str(cycle_num),
            config=config or {},
            smoke_config=smoke_config,
            adapter_config={},
            mode=report.mode,
            timeout_seconds=smoke_config["timeout_seconds"],
            max_output_chars=smoke_config["max_output_chars"],
        )
        try:
            dep_results = run_dependency_gate(dep_ctx, active_files) or []
        except Exception as exc:
            dep_results = [SmoketestResult(
                adapter="dependency_gate",
                name="dependency_gate:crash",
                status=STATUS_ERROR,
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message=f"Dependency gate crashed: {exc}",
            )]
        for item in dep_results:
            _append_report_result(report, item, smoke_config["max_output_chars"])

    if not buckets:
        report.add_result(SmoketestResult(
            adapter="smoketest",
            name="no_supported_files",
            status="SKIP",
            executed=False,
            execution_kind=EXECUTION_KIND_STATIC,
            message="No supported files found for smoketest adapters.",
        ))
        return report

    for adapter_name in sorted(buckets.keys()):
        scope_files = buckets[adapter_name]
        adapter_config = smoke_config["adapters"].get(adapter_name, dict(_DEFAULT_ADAPTER_CONFIG))
        related = [rel_name(item, qodeyard_path) for item in scope_files]

        if not adapter_config.get("enabled", True):
            report.add_result(SmoketestResult(
                adapter=adapter_name,
                name="adapter_disabled",
                status="SKIP",
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message="Adapter disabled by config.",
                related_files=sorted(set(related)),
            ))
            continue

        try:
            adapter = load_adapter(adapter_name)
        except Exception as exc:
            report.add_result(SmoketestResult(
                adapter=adapter_name,
                name="loader",
                status=STATUS_ERROR,
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message=f"Adapter failed to load: {exc}",
                related_files=sorted(set(related)),
            ))
            continue

        report.adapters_triggered.append(adapter.name)
        ctx = SmoketestContext(
            qodeyard_path=qodeyard_path,
            cycle_num=str(cycle_num),
            config=config or {},
            smoke_config=smoke_config,
            adapter_config=adapter_config,
            mode=report.mode,
            timeout_seconds=smoke_config["timeout_seconds"],
            max_output_chars=smoke_config["max_output_chars"],
        )

        try:
            preflight_results = adapter.preflight(ctx, scope_files) or []
        except Exception as exc:
            preflight_results = [SmoketestResult(
                adapter=adapter_name,
                name="preflight",
                status=STATUS_ERROR,
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message=f"Preflight crashed: {exc}",
                related_files=sorted(set(related)),
            )]
        for item in preflight_results:
            _append_report_result(report, item, smoke_config["max_output_chars"])

        legacy_run_only = (
            adapter.__class__.run is not Adapter.run
            and adapter.__class__.project_smoketest is Adapter.project_smoketest
            and adapter.__class__.file_smoketest is Adapter.file_smoketest
        )
        if legacy_run_only:
            try:
                adapter_results = adapter.run(ctx, scope_files) or []
            except Exception as exc:
                adapter_results = [SmoketestResult(
                    adapter=adapter_name,
                    name="runner",
                    status=STATUS_ERROR,
                    executed=False,
                    execution_kind=EXECUTION_KIND_STATIC,
                    message=f"Adapter crashed: {exc}",
                    related_files=sorted(set(related)),
                )]
            for item in adapter_results:
                _append_report_result(report, item, smoke_config["max_output_chars"])
            continue

        try:
            project_results = adapter.project_smoketest(ctx, scope_files) or []
        except Exception as exc:
            project_results = [SmoketestResult(
                adapter=adapter_name,
                name="project_smoketest",
                status=STATUS_ERROR,
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message=f"Project smoketest crashed: {exc}",
                related_files=sorted(set(related)),
            )]
        for item in project_results:
            _append_report_result(report, item, smoke_config["max_output_chars"])

        for file_path in scope_files:
            try:
                file_results = adapter.file_smoketest(ctx, file_path, scope_files) or []
            except Exception as exc:
                file_results = [SmoketestResult(
                    adapter=adapter_name,
                    name="file_smoketest",
                    status=STATUS_ERROR,
                    executed=False,
                    execution_kind=EXECUTION_KIND_STATIC,
                    message=f"File smoketest crashed for {rel_name(file_path, qodeyard_path)}: {exc}",
                    file=rel_name(file_path, qodeyard_path),
                    files=[rel_name(file_path, qodeyard_path)],
                    related_files=sorted(set(related)),
                )]
            for item in file_results:
                _append_report_result(report, item, smoke_config["max_output_chars"])

    return report


__all__ = ["run_smoketest", "normalize_scoped_files"]
