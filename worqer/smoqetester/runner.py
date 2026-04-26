# worqer/smoqetester/runner.py
# ═══════════════════════════════════════════════════════════════════════════════
# Scope-aware smoketest runner with lazy adapter loading.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

from .base import Adapter, SmoketestContext, rel_name, truncate_output
from .models import STATUS_ERROR, SmoketestReport, SmoketestResult
from .registry import adapter_for_file, load_adapter


_SKIP_DIR_NAMES = {
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
}

_DEFAULT_SMOKE_CONFIG = {
    "enabled": False,
    "mode": "scoped",
    "timeout_seconds": 45,
    "max_output_chars": 800,
}

_DEFAULT_ADAPTER_CONFIG = {
    "enabled": True,
    "command": None,
    "commands": None,
    "append_changed_files": False,
    "allow_script_execution": False,
    "require_dependencies": True,
    "auto_tsc_no_emit": True,
    "auto_unittest_discover": True,
    "auto_cli_help": False,
}


def _iter_source_files(root: Path) -> Iterable[Path]:
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
                stack.append(entry)
            elif entry.is_file():
                yield entry


def _path_has_skip_segment(rel: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in rel.parts)


def normalize_scoped_files(
    qodeyard_path: Path,
    changed_files: Optional[Iterable[Union[str, Path]]],
) -> list[Path]:
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
    ) or {}

    root["enabled"] = bool(smoke.get("enabled", root["enabled"]))
    mode = str(smoke.get("mode", root["mode"]) or root["mode"]).strip().lower()
    root["mode"] = mode if mode in {"scoped", "full"} else "scoped"

    try:
        root["timeout_seconds"] = max(1, int(smoke.get("timeout_seconds", root["timeout_seconds"])))
    except Exception:
        root["timeout_seconds"] = _DEFAULT_SMOKE_CONFIG["timeout_seconds"]

    try:
        root["max_output_chars"] = max(64, int(smoke.get("max_output_chars", root["max_output_chars"])))
    except Exception:
        root["max_output_chars"] = _DEFAULT_SMOKE_CONFIG["max_output_chars"]

    adapters_cfg = smoke.get("adapters") if isinstance(smoke.get("adapters"), dict) else {}
    root["adapters"] = {}
    adapter_names = set(["python", "shell", "js_ts", "html_css"])
    adapter_names.update(adapters_cfg.keys())
    for adapter_name in sorted(adapter_names):
        merged = dict(_DEFAULT_ADAPTER_CONFIG)
        adapter_payload = adapters_cfg.get(adapter_name)
        if isinstance(adapter_payload, dict):
            merged.update(adapter_payload)
        merged["enabled"] = bool(merged.get("enabled", True))
        root["adapters"][adapter_name] = merged

    return root


def _append_report_result(report: SmoketestReport, result: SmoketestResult, max_chars: int) -> None:
    result.stdout = truncate_output(result.stdout or "", max_chars)
    result.stderr = truncate_output(result.stderr or "", max_chars)
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
            # No explicit scope input was provided; run full inventory deterministically.
            report.mode = "full"

    buckets = _group_files_by_adapter(active_files)
    report.total_files = len(active_files)
    if not buckets:
        report.add_result(SmoketestResult(
            adapter="smoketest",
            name="no_supported_files",
            status="SKIP",
            executed=False,
            execution_kind="static",
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
                execution_kind="static",
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
                execution_kind="static",
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
                execution_kind="static",
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
                    execution_kind="static",
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
                execution_kind="static",
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
                    execution_kind="static",
                    message=f"File smoketest crashed for {rel_name(file_path, qodeyard_path)}: {exc}",
                    file=rel_name(file_path, qodeyard_path),
                    files=[rel_name(file_path, qodeyard_path)],
                    related_files=sorted(set(related)),
                )]
            for item in file_results:
                _append_report_result(report, item, smoke_config["max_output_chars"])

    return report


__all__ = ["run_smoketest", "normalize_scoped_files"]
