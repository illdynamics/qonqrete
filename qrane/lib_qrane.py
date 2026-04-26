#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from execution_model import (
    ESTIMATE_MODE_ADVISORY,
    ESTIMATE_MODE_SCHEDULER,
    PASS_BUILD,
    PASS_REPAIR,
    ExecutionLimits,
    ExecutionState,
    normalize_estimate_mode,
    normalize_pass_kind,
)


RUN_MANIFEST_FILE = "run-manifest.v1.json"
AUDIT_DIR = "audit"
AUDIT_TIMELINE_FILE = "timeline.md"
AUDIT_EVENTS_FILE = "events.ndjson"

STAGE_IDS = [
    "INTAKE",
    "CLARIFICATION",
    "CONSTRAINT",
    "PLANNING",
    "ESTIMATION",
    "BUILD",
    "VALIDATION",
    "REALIZATION",
    "INSPECTION",
    "REPAIR",
    "FINALIZE",
]

LIFECYCLE_STATES = [
    "CREATED",
    "READY_FOR_CLARIFICATION",
    "CLARIFYING",
    "BLOCKED",
    "CONSTRAINING",
    "PLANNING",
    "ESTIMATING",
    "AWAITING_GATE",
    "BUILDING",
    "VALIDATING",
    "REALIZING",
    "INSPECTING",
    "REPAIRING",
    "CONTINUABLE",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
    "ABORTED",
]

RUN_STATUSES = [
    "RUN_CREATED",
    "RUN_ACTIVE",
    "RUN_WAITING_FOR_INPUT",
    "RUN_WAITING_FOR_GATE",
    "RUN_REPAIR_PENDING",
    "RUN_COMPLETED",
    "RUN_PARTIAL",
    "RUN_FAILED",
    "RUN_ABORTED",
]

CAPABILITY_MODES = [
    "SIMULATION",
    "EXECUTION",
    "EXECUTION_PREFERRED",
    "MIXED_REASONING_EXECUTION",
]

VALIDATION_EXECUTION_MODES = [
    "NONE",
    "SIMULATED",
    "STATIC_ONLY",
    "EXECUTED",
    "MIXED",
]

EVIDENCE_STATUSES = [
    "EVIDENCE_MISSING",
    "EVIDENCE_PARTIAL",
    "EVIDENCE_COMPLETE",
]

CONFIDENCE_STATUSES = [
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_HIGH",
]

STAGE_ALIAS_MAP = {
    "qrystallizer": "CLARIFICATION",
    "qonstrictor": "CONSTRAINT",
    "instruqtor": "PLANNING",
    "calqulator": "ESTIMATION",
    "construqtor": "BUILD",
    "inspeqtor": "INSPECTION",
    "qualifier": "VALIDATION",
    "qonfirmer": "CONSTRAINT",
    "reqap promotion": "REPAIR",
    "cycle promotion": "REPAIR",
}

SUPPORT_SERVICE_ALIASES = {
    "qontextor": "CONTEXT_SERVICE",
    "qompressor": "SKELETON_SERVICE",
    "qontrabender": "CACHE_SERVICE",
    "qompressor_warmup": "SKELETON_WARMUP",
    "qontextor_initial": "CONTEXT_WARMUP",
    "qontrabender_warmup": "CACHE_WARMUP",
}

SUBSTAGE_ALIASES = {
    "Qonfirmer": "CONSTRAINT",
    "Qualification": "VALIDATION",
    "Per-Briq Tactical Reviews": "INSPECTION",
    "Global Meta-Review": "INSPECTION",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel_path(root: Path, path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except Exception:
        try:
            return str(p.relative_to(root))
        except Exception:
            return str(p)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_assessment(text: str) -> str | None:
    match = re.search(r"Assessment:.*?(SUCCESS|PARTIAL|FAILURE)", text, re.IGNORECASE | re.DOTALL)
    return match.group(1).upper() if match else None


def _looks_like_rel_file_token(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    if len(token) > 512:
        return False
    if token.startswith(("/", "~")):
        return False
    if ":" in token:
        # Keep parser scoped to repo-relative file hints only.
        return False
    if re.search(r"\s", token):
        return False
    if not re.fullmatch(r"[A-Za-z0-9._/\-]+", token):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)+", token):
        return False
    parts = token.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    basename = parts[-1]
    if basename in {"Dockerfile", "Makefile", "Procfile"}:
        return True
    return "." in basename


def parse_changed_files(markdown_text: str) -> list[str]:
    candidates = re.findall(r"`([^`]+)`", markdown_text or "")
    parsed = [item.strip() for item in candidates if _looks_like_rel_file_token(item)]
    return sorted(set(parsed))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _normalize_smoketest_kind(value: Any, executed_flag: bool = False) -> str:
    raw = str(value or "").strip().lower()
    # Support all valid granular kinds
    if raw in {
        "static_probe", "syntax_probe", "process_boot",
        "http_probe", "ws_probe", "browser_probe", "executed"
    }:
        return raw
    # Legacy fallbacks
    if raw == "static": return "static_probe"
    return "executed" if bool(executed_flag) else "static_probe"


def _smoketest_counts_from_payload(payload: dict[str, Any]) -> tuple[int, int]:
    executed_count = _int_or_none(payload.get("executed_count"))
    if executed_count is None:
        executed_count = _int_or_none(payload.get("executed"))
    static_count = _int_or_none(payload.get("static_count"))
    
    # v1.3.8: Also pull granular counts if present
    syntax_count = _int_or_none(payload.get("syntax_count"))
    boot_count = _int_or_none(payload.get("boot_count"))
    http_count = _int_or_none(payload.get("http_count"))
    ws_count = _int_or_none(payload.get("ws_count"))
    browser_count = _int_or_none(payload.get("browser_count"))

    results = payload.get("results") if isinstance(payload.get("results"), list) else []

    derived_executed = 0
    derived_static = 0
    derived_syntax = 0
    derived_boot = 0
    derived_http = 0
    derived_ws = 0
    derived_browser = 0

    for item in results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).upper()
        if status == "SKIP":
            continue
        
        kind = _normalize_smoketest_kind(item.get("execution_kind"), bool(item.get("executed", False)))
        
        if kind == "static_probe":
            derived_static += 1
        elif kind == "syntax_probe":
            derived_syntax += 1
        elif kind == "process_boot":
            derived_boot += 1
        elif kind == "http_probe":
            derived_http += 1
        elif kind == "ws_probe":
            derived_ws += 1
        elif kind == "browser_probe":
            derived_browser += 1
        elif kind == "executed":
            derived_executed += 1

    # Aggregate executed-ish kinds for high-level flags
    total_executed = (
        (executed_count or derived_executed) + 
        (boot_count or derived_boot) + 
        (http_count or derived_http) + 
        (ws_count or derived_ws) + 
        (browser_count or derived_browser)
    )
    total_static = (
        (static_count or derived_static) + 
        (syntax_count or derived_syntax)
    )

    return max(0, total_executed), max(0, total_static)


def _smoketest_counts_from_markdown(markdown_text: str) -> tuple[int, int]:
    text = markdown_text or ""
    executed_count = None
    static_count = None

    patterns = [
        r"^\s*-\s*Executed Count:\s*(\d+)\s*$",
        r"^\s*-\s*Executed:\s*(\d+)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            executed_count = int(match.group(1))
            break
    static_match = re.search(r"^\s*-\s*Static Count:\s*(\d+)\s*$", text, re.MULTILINE | re.IGNORECASE)
    if static_match:
        static_count = int(static_match.group(1))

    if executed_count is None:
        executed_count = len(re.findall(r"\(executed=yes\)", text, re.IGNORECASE))
    if static_count is None:
        static_count = len(re.findall(r"execution_kind=static", text, re.IGNORECASE))

    return max(0, int(executed_count or 0)), max(0, int(static_count or 0))


def _fallback_smoketest_evidence(workspace_root: Path) -> tuple[int, int, bool]:
    reqap_dir = workspace_root / "reqap.d"
    executed_total = 0
    static_total = 0
    has_artifact = False

    for json_path in sorted(reqap_dir.glob("cyqle*/cyqle*_smoketest.v1.json")):
        payload = read_json(json_path)
        if not payload:
            continue
        has_artifact = True
        executed_count, static_count = _smoketest_counts_from_payload(payload)
        executed_total += executed_count
        static_total += static_count

    for md_path in sorted(reqap_dir.glob("cyqle*/cyqle*_smoketest.md")):
        has_artifact = True
        executed_count, static_count = _smoketest_counts_from_markdown(read_text(md_path))
        executed_total += executed_count
        static_total += static_count

    return executed_total, static_total, has_artifact


def determine_validation_mode(workspace_root: Path) -> str:
    validation_bundle = read_json(workspace_root / "validation" / "validation-bundle.v1.json")
    if validation_bundle:
        mode = str(validation_bundle.get("validation_execution_mode") or "").upper()
        if mode in VALIDATION_EXECUTION_MODES:
            return mode
    reqap_dir = workspace_root / "reqap.d"
    has_qonfirmer = any(reqap_dir.glob("cyqle*_qonfirmer.json")) or any(reqap_dir.glob("cyqle*_qonfirmer.md"))
    has_verification = any(reqap_dir.glob("cyqle*/cyqle*_verification.md"))
    smoke_executed, smoke_static, has_smoketest = _fallback_smoketest_evidence(workspace_root)
    has_static = has_qonfirmer or has_verification or smoke_static > 0
    has_executed = smoke_executed > 0
    if has_static and has_executed:
        return "MIXED"
    if has_executed:
        return "EXECUTED"
    if has_static:
        return "STATIC_ONLY"
    if has_smoketest:
        # Smoketest artifacts exist but provide no executed/static evidence.
        return "NONE"
    return "NONE"


def determine_evidence_status(workspace_root: Path) -> str:
    has_build = any(workspace_root.glob("exeq.d/cyqle*_summary.md")) and any(workspace_root.glob("exeq.d/cyqle*_changed.md"))
    validation_bundle = read_json(workspace_root / "validation" / "validation-bundle.v1.json")
    realization_bundle = read_json(workspace_root / "realization" / "realization-bundle.v1.json")
    inspection_verdict = read_json(workspace_root / "verdict" / "inspection-verdict.v1.json")
    has_validation = bool(validation_bundle) or determine_validation_mode(workspace_root) != "NONE"
    has_inspection = bool(inspection_verdict) or any(workspace_root.glob("reqap.d/cyqle*_reqap.md"))
    has_realization = bool(realization_bundle)
    if realization_bundle:
        status = realization_bundle.get("evidence_status")
        if status in {"EVIDENCE_MISSING", "EVIDENCE_PARTIAL", "EVIDENCE_COMPLETE"}:
            return status
    if has_build and has_validation and has_inspection and has_realization:
        return "EVIDENCE_COMPLETE"
    if has_build or has_validation or has_inspection or has_realization:
        return "EVIDENCE_PARTIAL"
    return "EVIDENCE_MISSING"


def determine_confidence_status(workspace_root: Path) -> str:
    realization_bundle = read_json(workspace_root / "realization" / "realization-bundle.v1.json")
    if realization_bundle:
        confidence = realization_bundle.get("confidence")
        if confidence in CONFIDENCE_STATUSES:
            return confidence
    validation_mode = determine_validation_mode(workspace_root)
    if validation_mode == "NONE":
        return "CONFIDENCE_LOW"
    if validation_mode == "STATIC_ONLY":
        return "CONFIDENCE_MEDIUM"
    return "CONFIDENCE_HIGH"


def manifest_path(workspace_root: Path) -> Path:
    return workspace_root / RUN_MANIFEST_FILE


def ensure_audit_files(workspace_root: Path) -> tuple[Path, Path]:
    audit_dir = workspace_root / AUDIT_DIR
    audit_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = audit_dir / AUDIT_TIMELINE_FILE
    events_path = audit_dir / AUDIT_EVENTS_FILE
    if not timeline_path.exists():
        timeline_path.write_text(
            "# Run Audit Timeline\n\n"
            "| Time (UTC) | Event | Canonical Stage | Agent | Details |\n"
            "| --- | --- | --- | --- | --- |\n",
            encoding="utf-8",
        )
    if not events_path.exists():
        events_path.write_text("", encoding="utf-8")
    return timeline_path, events_path


def load_manifest(workspace_root: Path) -> dict[str, Any]:
    path = manifest_path(workspace_root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return create_manifest(workspace_root)


def save_manifest(workspace_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["updated_at"] = now_utc()
    manifest_path(workspace_root).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def append_audit_event(
    workspace_root: Path,
    event_type: str,
    canonical_stage_id: str | None,
    agent_name: str | None,
    detail: str,
    payload: dict[str, Any] | None = None,
) -> None:
    timeline_path, events_path = ensure_audit_files(workspace_root)
    timestamp = now_utc()
    line = f"| {timestamp} | {event_type} | {canonical_stage_id or '-'} | {agent_name or '-'} | {detail.replace('|', '/')} |\n"
    with timeline_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    event = {
        "timestamp": timestamp,
        "event_type": event_type,
        "canonical_stage_id": canonical_stage_id,
        "agent_name": agent_name,
        "detail": detail,
    }
    if payload:
        event["payload"] = payload
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _int_or(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except Exception:
        return default


def execution_metadata_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    state = state or {}
    pass_kind = normalize_pass_kind(state.get("pass_kind", PASS_BUILD))
    build_pass_index = _int_or(state.get("build_pass_index"), 0) or 0
    repairing_build_pass_index = _int_or(state.get("repairing_build_pass_index"), None)
    if pass_kind == PASS_REPAIR and repairing_build_pass_index is None:
        repairing_build_pass_index = build_pass_index or None
    return {
        "global_iteration_index": _int_or(state.get("global_iteration_index"), 0) or 0,
        "pass_kind": pass_kind,
        "build_pass_index": build_pass_index,
        "repair_pass_index": _int_or(state.get("repair_pass_index"), 0) or 0,
        "repairing_build_pass_index": repairing_build_pass_index,
        "cycle_estimate_mode": normalize_estimate_mode(state.get("cycle_estimate_mode", ESTIMATE_MODE_ADVISORY)),
        "estimated_build_passes": _int_or(state.get("estimated_build_passes"), None),
        "scheduled_build_pass_target": _int_or(state.get("scheduled_build_pass_target"), None),
    }


def execution_metadata_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    execution = ensure_execution_block(manifest)
    return execution_metadata_from_state(execution.get("state") or {})


def execution_metadata_for_workspace(workspace_root: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path(workspace_root))
    state = (((manifest or {}).get("execution") or {}).get("state") or {})
    return execution_metadata_from_state(state)


def resolve_repo_sync_mode() -> str:
    raw_mode = str(os.environ.get("QONQ_REPO_SYNC_MODE", "sync_to_repo_root") or "").strip().lower()
    if raw_mode in {"no_sync", "no-sync", "nosync", "off", "disabled", "false", "0"}:
        return "no_sync"
    return "sync_to_repo_root"


def _build_resume_execution(prior_manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not prior_manifest:
        return None
    execution = prior_manifest.get("execution") or {}
    if not execution:
        return None
    state = execution.get("state") or {}
    return {
        "global_iteration_index": _int_or(state.get("global_iteration_index"), 0) or 0,
        "pass_kind": normalize_pass_kind(state.get("pass_kind", PASS_BUILD)),
        "build_pass_index": _int_or(state.get("build_pass_index"), 0) or 0,
        "repair_pass_index": _int_or(state.get("repair_pass_index"), 0) or 0,
        "repairing_build_pass_index": _int_or(state.get("repairing_build_pass_index"), None),
        "cycle_estimate_mode": normalize_estimate_mode(state.get("cycle_estimate_mode", ESTIMATE_MODE_ADVISORY)),
        "estimated_build_passes": _int_or(state.get("estimated_build_passes"), None),
        "scheduled_build_pass_target": _int_or(state.get("scheduled_build_pass_target"), None),
        "pending_next_pass_kind": normalize_pass_kind(state.get("pending_next_pass_kind")) if state.get("pending_next_pass_kind") else None,
        "pending_repairing_build_pass_index": _int_or(state.get("pending_repairing_build_pass_index"), None),
        "stop_reason": state.get("stop_reason"),
        "prior_run_status": prior_manifest.get("run_status"),
        "prior_lifecycle_state": prior_manifest.get("lifecycle_state"),
        "prior_current_stage": prior_manifest.get("current_stage"),
    }


def _default_execution_block(prior_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    resumed = _build_resume_execution(prior_manifest)
    state = resumed or {
        "global_iteration_index": 0,
        "pass_kind": PASS_BUILD,
        "build_pass_index": 0,
        "repair_pass_index": 0,
        "repairing_build_pass_index": None,
        "cycle_estimate_mode": ESTIMATE_MODE_ADVISORY,
        "estimated_build_passes": None,
        "scheduled_build_pass_target": None,
        "pending_next_pass_kind": None,
        "pending_repairing_build_pass_index": None,
        "stop_reason": None,
    }
    limits = ((prior_manifest or {}).get("execution") or {}).get("limits") or {
        "max_total_iterations": None,
        "max_build_passes": None,
        "max_attempts_per_build_pass": None,
    }
    return {
        "schema_version": "execution-semantics.v1",
        "folder_iteration_semantics": "cyqle{N} maps to global_iteration_index, not build_pass_index",
        "state": state,
        "limits": limits,
        "resume_state": resumed,
    }


def ensure_execution_block(manifest: dict[str, Any]) -> dict[str, Any]:
    execution = manifest.setdefault("execution", _default_execution_block())
    execution.setdefault("schema_version", "execution-semantics.v1")
    execution.setdefault("folder_iteration_semantics", "cyqle{N} maps to global_iteration_index, not build_pass_index")
    execution.setdefault("limits", {})
    state = execution.setdefault("state", {})
    state.setdefault("global_iteration_index", 0)
    state.setdefault("pass_kind", PASS_BUILD)
    state.setdefault("build_pass_index", 0)
    state.setdefault("repair_pass_index", 0)
    state.setdefault("repairing_build_pass_index", None)
    state.setdefault("cycle_estimate_mode", ESTIMATE_MODE_ADVISORY)
    state.setdefault("estimated_build_passes", None)
    state.setdefault("scheduled_build_pass_target", None)
    state.setdefault("pending_next_pass_kind", None)
    state.setdefault("pending_repairing_build_pass_index", None)
    state.setdefault("stop_reason", None)
    return execution


def set_execution_config(workspace_root: Path, limits: ExecutionLimits, cycle_estimate_mode: str) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    execution = ensure_execution_block(manifest)
    execution["limits"] = {
        "max_total_iterations": limits.max_total_iterations,
        "max_build_passes": limits.max_build_passes,
        "max_attempts_per_build_pass": limits.max_attempts_per_build_pass,
    }
    execution["state"]["cycle_estimate_mode"] = normalize_estimate_mode(cycle_estimate_mode)
    save_manifest(workspace_root, manifest)
    return manifest


def update_execution_planning(workspace_root: Path, estimated_build_passes: int | None = None, scheduled_build_pass_target: int | None = None) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    execution = ensure_execution_block(manifest)
    state = execution["state"]
    if estimated_build_passes is not None:
        state["estimated_build_passes"] = _int_or(estimated_build_passes, None)
    if scheduled_build_pass_target is not None:
        state["scheduled_build_pass_target"] = _int_or(scheduled_build_pass_target, None)
    save_manifest(workspace_root, manifest)
    return manifest


def record_pass_state(
    workspace_root: Path,
    *,
    global_iteration_index: int,
    pass_kind: str,
    build_pass_index: int,
    repair_pass_index: int,
    repairing_build_pass_index: int | None = None,
    cycle_estimate_mode: str = ESTIMATE_MODE_ADVISORY,
    estimated_build_passes: int | None = None,
    scheduled_build_pass_target: int | None = None,
    pending_next_pass_kind: str | None = None,
    pending_repairing_build_pass_index: int | None = None,
    stop_reason: str | None = None,
    event_type: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    execution = ensure_execution_block(manifest)
    state = execution["state"]
    state.update({
        "global_iteration_index": int(global_iteration_index),
        "pass_kind": normalize_pass_kind(pass_kind),
        "build_pass_index": int(build_pass_index),
        "repair_pass_index": int(repair_pass_index),
        "repairing_build_pass_index": _int_or(repairing_build_pass_index, None),
        "cycle_estimate_mode": normalize_estimate_mode(cycle_estimate_mode),
        "estimated_build_passes": _int_or(estimated_build_passes, None),
        "scheduled_build_pass_target": _int_or(scheduled_build_pass_target, None),
        "pending_next_pass_kind": normalize_pass_kind(pending_next_pass_kind) if pending_next_pass_kind else None,
        "pending_repairing_build_pass_index": _int_or(pending_repairing_build_pass_index, None),
        "stop_reason": stop_reason,
    })
    save_manifest(workspace_root, manifest)
    if event_type and detail:
        append_audit_event(
            workspace_root,
            event_type,
            "REPAIR" if normalize_pass_kind(pass_kind) == PASS_REPAIR else "BUILD",
            None,
            detail,
            {"execution": state.copy()},
        )
    return manifest


def base_manifest(workspace_root: Path, prior_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    run_id = workspace_root.name
    resumed_from_qage = os.environ.get("QONQ_RESUMED_FROM_QAGE")
    run_kind = os.environ.get("QONQ_RUN_KIND", "run")
    repo_sync_mode = resolve_repo_sync_mode()
    canonical_state_root = str(workspace_root)
    raw_task_rel = rel_path(workspace_root, workspace_root / "tasq.d" / "cyqle1_tasq.md")
    manifest = {
        "schema_version": "run-manifest.v1",
        "run_id": run_id,
        "manifest_kind": "canonical_run_manifest_bridge",
        "current_stage": "INTAKE",
        "lifecycle_state": "CREATED",
        "run_status": "RUN_CREATED",
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "validation_execution_mode": "NONE",
        "evidence_status": "EVIDENCE_MISSING",
        "confidence_status": "CONFIDENCE_LOW",
        "lineage": {
            "run_kind": run_kind,
            "resumed_from_qage": resumed_from_qage,
            "repo_sync_mode": repo_sync_mode,
        },
        "compatibility": {
            "partial_write_model": "SCOPED_STAGED_ATOMIC_ATTEMPTS",
            "partial_write_disclosure": "ConstruQtor stages scoped attempt writes, validates against an overlay workspace, and commits atomically with snapshot-based recovery metadata.",
            "continuation_model": "EXPLICIT_REPAIR_PLAN_CANONICAL",
            "canonical_manifest_authority": True,
            "canonical_state_root": canonical_state_root,
            "canonical_state_model": "RUN_ROOT_NATIVE",
        },
        "registry": {
            "stage_ids": STAGE_IDS,
            "lifecycle_states": LIFECYCLE_STATES,
            "run_statuses": RUN_STATUSES,
            "capability_modes": CAPABILITY_MODES,
            "validation_execution_modes": VALIDATION_EXECUTION_MODES,
            "evidence_statuses": EVIDENCE_STATUSES,
            "confidence_statuses": CONFIDENCE_STATUSES,
            "stage_alias_map": STAGE_ALIAS_MAP,
            "support_service_aliases": SUPPORT_SERVICE_ALIASES,
            "substage_aliases": SUBSTAGE_ALIASES,
            "pass_kinds": [PASS_BUILD, PASS_REPAIR],
            "cycle_estimate_modes": [ESTIMATE_MODE_ADVISORY, ESTIMATE_MODE_SCHEDULER],
        },
        "task": {
            "raw_input_path": raw_task_rel,
            "current_cycle_task_path": raw_task_rel,
            "task_spec_path": rel_path(workspace_root, workspace_root / "task" / "task-spec.v1.json"),
            "clarification_log_path": rel_path(workspace_root, workspace_root / "task" / "clarification-log.v1.json"),
            "clarification_response_path": rel_path(workspace_root, workspace_root / "task" / "clarification-response.v1.json"),
            "qonstrictor_result_path": rel_path(workspace_root, workspace_root / "qontract.d" / "qonstrictor-result.v1.json"),
        },
        "artifacts": {
            "run_manifest": RUN_MANIFEST_FILE,
            "audit_summary": f"{AUDIT_DIR}/{AUDIT_TIMELINE_FILE}",
            "audit_events": f"{AUDIT_DIR}/{AUDIT_EVENTS_FILE}",
            "cache_manifest": rel_path(workspace_root, workspace_root / "qache.d" / "manifest.json"),
            "task_spec": rel_path(workspace_root, workspace_root / "task" / "task-spec.v1.json"),
            "clarification_log": rel_path(workspace_root, workspace_root / "task" / "clarification-log.v1.json"),
            "clarification_response": rel_path(workspace_root, workspace_root / "task" / "clarification-response.v1.json"),
            "qonstrictor_result": rel_path(workspace_root, workspace_root / "qontract.d" / "qonstrictor-result.v1.json"),
            "repair_plan": rel_path(workspace_root, workspace_root / "verdict" / "repair-plan.v1.json"),
            "continuation_metadata": rel_path(workspace_root, workspace_root / "continuation" / "continuation-metadata.v1.json"),
            "build_attempts_root": rel_path(workspace_root, workspace_root / "build" / "attempts"),
        },
        "directories": {
            "qage_root": ".",
            "tasq_dir": rel_path(workspace_root, workspace_root / "tasq.d"),
            "briq_dir": rel_path(workspace_root, workspace_root / "briq.d"),
            "qodeyard_dir": rel_path(workspace_root, workspace_root / "qodeyard"),
            "exeq_dir": rel_path(workspace_root, workspace_root / "exeq.d"),
            "reqap_dir": rel_path(workspace_root, workspace_root / "reqap.d"),
            "qontract_dir": rel_path(workspace_root, workspace_root / "qontract.d"),
            "qontext_dir": rel_path(workspace_root, workspace_root / "qontext.d"),
            "bloq_dir": rel_path(workspace_root, workspace_root / "bloq.d"),
            "qache_dir": rel_path(workspace_root, workspace_root / "qache.d"),
        },
        "stages": [],
        "support_services": [],
        "execution": _default_execution_block(prior_manifest),
        "terminal": {
            "final_verdict": None,
            "completed_at": None,
        },
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    return manifest


def create_manifest(workspace_root: Path) -> dict[str, Any]:
    workspace_root.mkdir(parents=True, exist_ok=True)
    ensure_audit_files(workspace_root)
    prior_manifest = None
    if os.environ.get("QONQ_RUN_KIND") == "resume":
        prior_manifest = read_json(manifest_path(workspace_root))
    manifest = base_manifest(workspace_root, prior_manifest=prior_manifest)
    write_task_intake_bridge(workspace_root)
    manifest["artifacts"]["task_input_bridge"] = rel_path(workspace_root, workspace_root / "task" / "task-intake-bridge.v1.json")
    append_audit_event(
        workspace_root,
        "manifest_created",
        "INTAKE",
        os.environ.get("QONQ_RUN_KIND", "run"),
        "Canonical run manifest bridge created at intake.",
        {"run_id": manifest["run_id"]},
    )
    return save_manifest(workspace_root, manifest)


def ensure_stage_record(manifest: dict[str, Any], stage_id: str, cycle: int | None, agent_name: str | None) -> dict[str, Any]:
    for record in manifest["stages"]:
        if record["stage_id"] == stage_id and record.get("cycle") == cycle and record.get("agent_name") == agent_name:
            return record
    record = {
        "stage_id": stage_id,
        "agent_name": agent_name,
        "cycle": cycle,
        "status": "pending",
        "started_at": None,
        "ended_at": None,
        "artifacts": [],
        "notes": [],
    }
    manifest["stages"].append(record)
    return record


def append_unique(values: list[Any], item: Any) -> None:
    if item is None:
        return
    if item not in values:
        values.append(item)


def start_stage(workspace_root: Path, stage_id: str, agent_name: str | None, cycle: int | None, detail: str) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    execution = ensure_execution_block(manifest)
    record = ensure_stage_record(manifest, stage_id, cycle, agent_name)
    record["status"] = "in_progress"
    record["started_at"] = record["started_at"] or now_utc()
    manifest["current_stage"] = stage_id
    manifest["run_status"] = "RUN_ACTIVE"
    lifecycle_map = {
        "INTAKE": "READY_FOR_CLARIFICATION",
        "CLARIFICATION": "CLARIFYING",
        "CONSTRAINT": "CONSTRAINING",
        "PLANNING": "PLANNING",
        "ESTIMATION": "ESTIMATING",
        "BUILD": "BUILDING",
        "VALIDATION": "VALIDATING",
        "REALIZATION": "REALIZING",
        "INSPECTION": "INSPECTING",
        "REPAIR": "REPAIRING",
        "FINALIZE": "COMPLETED",
    }
    manifest["lifecycle_state"] = lifecycle_map.get(stage_id, manifest["lifecycle_state"])
    append_audit_event(workspace_root, "stage_started", stage_id, agent_name, detail, {"cycle": cycle, "execution": execution.get("state", {}).copy()})
    return save_manifest(workspace_root, manifest)


def complete_stage(
    workspace_root: Path,
    stage_id: str,
    agent_name: str | None,
    cycle: int | None,
    artifacts: list[str] | None = None,
    notes: list[str] | None = None,
    success: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    execution = ensure_execution_block(manifest)
    record = ensure_stage_record(manifest, stage_id, cycle, agent_name)
    record["status"] = "completed" if success else "failed"
    record["ended_at"] = now_utc()
    for artifact in artifacts or []:
        append_unique(record["artifacts"], artifact)
    for note in notes or []:
        append_unique(record["notes"], note)
    manifest["validation_execution_mode"] = determine_validation_mode(workspace_root)
    manifest["evidence_status"] = determine_evidence_status(workspace_root)
    manifest["confidence_status"] = determine_confidence_status(workspace_root)
    append_audit_event(
        workspace_root,
        "stage_completed" if success else "stage_failed",
        stage_id,
        agent_name,
        f"{stage_id} completed with {len(artifacts or [])} linked artifacts.",
        {"cycle": cycle, "artifacts": artifacts or [], "notes": notes or [], "execution": execution.get("state", {}).copy()},
    )
    return save_manifest(workspace_root, manifest)


def mark_clarification_blocked(
    workspace_root: Path,
    *,
    detail: str,
    stop_reason: str,
    questions: list[dict[str, Any]] | None = None,
    cycle: int | None = None,
    source: str = "qrane",
) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    execution = ensure_execution_block(manifest)
    state = execution.setdefault("state", {})
    state["pending_next_pass_kind"] = None
    state["pending_repairing_build_pass_index"] = None
    state["stop_reason"] = stop_reason
    manifest["current_stage"] = "CLARIFICATION"
    manifest["lifecycle_state"] = "BLOCKED"
    manifest["run_status"] = "RUN_WAITING_FOR_INPUT"

    clarification_cycle = cycle
    if clarification_cycle is None:
        clarification_cycle = _int_or(state.get("global_iteration_index"), 1) or 1
    record = ensure_stage_record(manifest, "CLARIFICATION", clarification_cycle, "qrystallizer")
    append_unique(record["notes"], detail)
    if stop_reason:
        append_unique(record["notes"], f"stop_reason={stop_reason}")
    if questions:
        append_unique(record["notes"], f"clarification_questions={len(questions)}")
    save_manifest(workspace_root, manifest)
    append_audit_event(
        workspace_root,
        "clarification_blocked",
        "CLARIFICATION",
        source,
        detail,
        {
            "cycle": clarification_cycle,
            "stop_reason": stop_reason,
            "question_count": len(questions or []),
            "question_ids": [q.get("question_id") for q in (questions or []) if isinstance(q, dict)],
            "execution": state.copy(),
        },
    )
    return load_manifest(workspace_root)


def record_support_service(
    workspace_root: Path,
    agent_name: str,
    cycle: int | None,
    artifacts: list[str] | None = None,
    notes: list[str] | None = None,
    success: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    service_record = {
        "service_id": SUPPORT_SERVICE_ALIASES.get(agent_name, "SUPPORT_SERVICE"),
        "agent_name": agent_name,
        "cycle": cycle,
        "status": "completed" if success else "failed",
        "recorded_at": now_utc(),
        "artifacts": artifacts or [],
        "notes": notes or [],
    }
    manifest["support_services"].append(service_record)
    append_audit_event(
        workspace_root,
        "support_service_recorded",
        None,
        agent_name,
        f"Support service {agent_name} recorded.",
        service_record,
    )
    return save_manifest(workspace_root, manifest)


def write_json(root: Path, relative_path: str, payload: dict[str, Any]) -> str:
    dest = root / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return relative_path


def write_task_intake_bridge(workspace_root: Path) -> str:
    raw_task = workspace_root / "tasq.d" / "cyqle1_tasq.md"
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "task-intake-bridge.v1",
        "generated_at": now_utc(),
        "input_path": rel_path(workspace_root, raw_task),
        "run_id": workspace_root.name,
        "run_kind": os.environ.get("QONQ_RUN_KIND", "run"),
        "resumed_from_qage": os.environ.get("QONQ_RESUMED_FROM_QAGE"),
        "repo_sync_mode": resolve_repo_sync_mode(),
        **execution_meta,
        "notes": [
            "Raw tasq intake remains immutable source evidence.",
            "Canonical Qrystallizer output now owns clarified task readiness and assumption capture.",
        ],
    }
    return write_json(workspace_root, "task/task-intake-bridge.v1.json", payload)


def write_planning_bridge(workspace_root: Path, cycle: int) -> str:
    briq_files = sorted(rel_path(workspace_root, p) for p in (workspace_root / "briq.d").glob(f"cyqle{cycle}_*.md"))
    qontract_json = workspace_root / "qontract.d" / "qontract.json"
    qontract_md = workspace_root / "qontract.d" / "qontract.md"
    task_spec = workspace_root / "task" / "task-spec.v1.json"
    qonstrictor_result = workspace_root / "qontract.d" / "qonstrictor-result.v1.json"
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "planning-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "stage_agent": "instruqtor",
        "canonical_stage_id": "PLANNING",
        **execution_meta,
        "task_spec_ref": rel_path(workspace_root, task_spec) if task_spec.exists() else None,
        "qonstrictor_result_ref": rel_path(workspace_root, qonstrictor_result) if qonstrictor_result.exists() else None,
        "briq_files": briq_files,
        "briq_count": len(briq_files),
        "structured_artifacts": {
            "execution_blueprint": "planning/execution-blueprint.v1.json" if (workspace_root / "planning" / "execution-blueprint.v1.json").exists() else None,
            "architecture_foundation": "planning/architecture-foundation.md" if (workspace_root / "planning" / "architecture-foundation.md").exists() else None,
            "dependency_contract": "planning/dependency-interaction-contract.v1.json" if (workspace_root / "planning" / "dependency-interaction-contract.v1.json").exists() else None,
            "component_contracts": "planning/component-contracts.v1.json" if (workspace_root / "planning" / "component-contracts.v1.json").exists() else None,
            "validation_plan": "planning/validation-plan.v1.json" if (workspace_root / "planning" / "validation-plan.v1.json").exists() else None,
            "completion_criteria": "planning/completion-criteria.v1.json" if (workspace_root / "planning" / "completion-criteria.v1.json").exists() else None,
            "build_groups": "planning/build-groups.v1.json" if (workspace_root / "planning" / "build-groups.v1.json").exists() else None,
            "estimation_basis": "planning/estimation-basis.v1.json" if (workspace_root / "planning" / "estimation-basis.v1.json").exists() else None,
        },
        "contract_artifacts": {
            "qontract_json": rel_path(workspace_root, qontract_json) if qontract_json.exists() else None,
            "qontract_md": rel_path(workspace_root, qontract_md) if qontract_md.exists() else None,
        },
    }
    return write_json(workspace_root, "planning/planning-bridge.v1.json", payload)


def write_estimation_bridge(workspace_root: Path, cycle: int) -> str:
    briq_dir = workspace_root / "briq.d"
    estimated_briqs = []
    for briq in sorted(briq_dir.glob(f"cyqle{cycle}_*.md")):
        content = read_text(briq)
        match = re.search(r"\[Est:\s*([^\]]+)\]", content)
        estimated_briqs.append(
            {
                "path": rel_path(workspace_root, briq),
                "estimate_annotation": match.group(1) if match else None,
            }
        )
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "estimation-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "stage_agent": "calqulator",
        "canonical_stage_id": "ESTIMATION",
        **execution_meta,
        "estimated_briqs": estimated_briqs,
        "estimated_count": len(estimated_briqs),
        "estimate_artifact": "estimation/estimate.v1.json" if (workspace_root / "estimation" / "estimate.v1.json").exists() else None,
    }
    return write_json(workspace_root, "estimation/estimation-bridge.v1.json", payload)


def _parse_utc_iso_to_epoch(value: str | None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except Exception:
        return None


def _collect_stage_wall_clock_totals(workspace_root: Path) -> dict[str, float]:
    manifest = load_manifest(workspace_root)
    totals: dict[str, float] = {}
    for record in manifest.get("stages", []) or []:
        stage_id = str(record.get("stage_id") or "").strip()
        if not stage_id:
            continue
        started = _parse_utc_iso_to_epoch(record.get("started_at"))
        ended = _parse_utc_iso_to_epoch(record.get("ended_at"))
        if started is None or ended is None:
            continue
        duration = max(0.0, ended - started)
        totals[stage_id] = float(totals.get(stage_id, 0.0) + duration)
    return {k: round(v, 3) for k, v in sorted(totals.items())}


def _collect_build_attempt_metrics(workspace_root: Path) -> dict[str, Any]:
    attempts_root = workspace_root / "build" / "attempts"
    totals = {
        "attempt_count": 0,
        "ai_call_count": 0,
        "tool_iteration_count": 0,
        "validation_duration_sec": 0.0,
        "retry_sleep_duration_sec": 0.0,
        "attempt_duration_sec": 0.0,
        "stream_fallback_count": 0,
    }
    per_briq_ai_calls: dict[str, int] = {}
    if not attempts_root.exists():
        return {"totals": totals, "per_briq_ai_call_count": per_briq_ai_calls}

    for manifest_file in sorted(attempts_root.glob("*/attempt-manifest.v1.json")):
        payload = read_json(manifest_file)
        if not payload:
            continue
        totals["attempt_count"] += 1
        attempt_context = payload.get("attempt_context") if isinstance(payload.get("attempt_context"), dict) else {}
        metrics = attempt_context.get("metrics") if isinstance(attempt_context.get("metrics"), dict) else {}
        totals["ai_call_count"] += int(metrics.get("ai_call_count", 0) or 0)
        totals["tool_iteration_count"] += int(metrics.get("tool_iteration_count", 0) or 0)
        totals["validation_duration_sec"] += float(metrics.get("validation_duration_sec", 0.0) or 0.0)
        totals["retry_sleep_duration_sec"] += float(metrics.get("retry_sleep_duration_sec", 0.0) or 0.0)
        totals["attempt_duration_sec"] += float(metrics.get("attempt_duration_sec", 0.0) or 0.0)
        totals["stream_fallback_count"] += int(metrics.get("stream_fallback_count", 0) or 0)
        briq_name = str(attempt_context.get("briq_name") or "").strip()
        if briq_name:
            per_briq_ai_calls[briq_name] = int(per_briq_ai_calls.get(briq_name, 0) + int(metrics.get("ai_call_count", 0) or 0))

    rounded_totals = {
        "attempt_count": int(totals["attempt_count"]),
        "ai_call_count": int(totals["ai_call_count"]),
        "tool_iteration_count": int(totals["tool_iteration_count"]),
        "validation_duration_sec": round(float(totals["validation_duration_sec"]), 3),
        "retry_sleep_duration_sec": round(float(totals["retry_sleep_duration_sec"]), 3),
        "attempt_duration_sec": round(float(totals["attempt_duration_sec"]), 3),
        "stream_fallback_count": int(totals["stream_fallback_count"]),
    }
    return {
        "totals": rounded_totals,
        "per_briq_ai_call_count": dict(sorted(per_briq_ai_calls.items())),
    }


def write_build_bridge(workspace_root: Path, cycle: int) -> str:
    summary_path = workspace_root / "exeq.d" / f"cyqle{cycle}_summary.md"
    changed_path = workspace_root / "exeq.d" / f"cyqle{cycle}_changed.md"
    summary = read_text(summary_path)
    status_match = re.search(r"\*\*Overall Status:\*\*\s*([A-Za-z]+)", summary)
    per_briq_dir = workspace_root / "exeq.d" / f"cyqle{cycle}"
    group_reports = [
        read_json(path)
        for path in sorted((workspace_root / "build" / "groups").glob("*/build-report.v1.json"))
    ] if (workspace_root / "build" / "groups").exists() else []
    write_modes = sorted({
        report.get("write_strategy")
        for report in group_reports
        if report.get("write_strategy")
    })
    recovery_policies = sorted({
        report.get("recovery_policy")
        for report in group_reports
        if report.get("recovery_policy")
    })
    execution_backends = [
        report.get("execution_backend")
        for report in group_reports
        if report.get("execution_backend")
    ]
    attempt_metrics = _collect_build_attempt_metrics(workspace_root)
    stage_wall_clock_totals = _collect_stage_wall_clock_totals(workspace_root)
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "build-output-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "stage_agent": "construqtor",
        "canonical_stage_id": "BUILD",
        **execution_meta,
        "build_status": status_match.group(1).upper() if status_match else None,
        "summary_path": rel_path(workspace_root, summary_path) if summary_path.exists() else None,
        "changed_manifest_path": rel_path(workspace_root, changed_path) if changed_path.exists() else None,
        "per_briq_exeq_dir": rel_path(workspace_root, per_briq_dir) if per_briq_dir.exists() else None,
        "group_reports": sorted(
            rel_path(workspace_root, path)
            for path in (workspace_root / "build" / "groups").glob("*/build-report.v1.json")
        ) if (workspace_root / "build" / "groups").exists() else [],
        "group_changed_scope_manifests": sorted(
            rel_path(workspace_root, path)
            for path in (workspace_root / "build" / "groups").glob("*/changed-files.v1.json")
        ) if (workspace_root / "build" / "groups").exists() else [],
        "write_strategy": write_modes[0] if len(write_modes) == 1 else ("mixed" if write_modes else "unknown"),
        "write_strategy_disclosure": "Build groups disclose scoped staged or atomic attempt writes and snapshot-based recovery metadata.",
        "recovery_policies": recovery_policies,
        "execution_backends": execution_backends,
        "attempt_metrics": attempt_metrics,
        "stage_wall_clock_totals_sec": stage_wall_clock_totals,
    }
    return write_json(workspace_root, "build/build-output-bridge.v1.json", payload)


def write_validation_bridge(workspace_root: Path, cycle: int) -> str:
    canonical_path = workspace_root / "validation" / "validation-bundle.v1.json"
    if canonical_path.exists():
        return "validation/validation-bundle.v1.json"
    reqap_dir = workspace_root / "reqap.d"
    qonfirmer_md = reqap_dir / f"cyqle{cycle}_qonfirmer.md"
    qonfirmer_json = reqap_dir / f"cyqle{cycle}_qonfirmer.json"
    verification_md = reqap_dir / f"cyqle{cycle}" / f"cyqle{cycle}_verification.md"
    smoketest_md = reqap_dir / f"cyqle{cycle}" / f"cyqle{cycle}_smoketest.md"
    smoketest_json = reqap_dir / f"cyqle{cycle}" / f"cyqle{cycle}_smoketest.v1.json"
    verification_text = read_text(verification_md)
    verification_status_match = re.search(r"\*\*Status:\*\*\s*([A-Z]+)", verification_text)
    execution_meta = execution_metadata_for_workspace(workspace_root)
    validation_mode = determine_validation_mode(workspace_root)
    validation_sources = [
        {"agent_name": "Qonfirmer", "canonical_stage_id": "CONSTRAINT"},
        {"agent_name": "Qualification", "canonical_stage_id": "VALIDATION"},
    ]
    if smoketest_md.exists() or smoketest_json.exists():
        validation_sources.append({"agent_name": "smoQetester", "canonical_stage_id": "VALIDATION"})
    capability_notes = [
        "Validation remains Python-skewed in the current engine.",
    ]
    if validation_mode in {"EXECUTED", "MIXED"}:
        capability_notes.append("Executed smoketest evidence is present in the current validation boundary.")
    elif validation_mode == "STATIC_ONLY":
        capability_notes.append("Smoketest evidence is static-only in the current validation boundary.")
    else:
        capability_notes.append("No executed smoketest evidence was observed for this cycle.")
    payload = {
        "schema_version": "validation-bundle.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "canonical_stage_id": "VALIDATION",
        **execution_meta,
        "sources": validation_sources,
        "validation_execution_mode": validation_mode,
        "capability_disclosure": {
            "deterministic_validation_strength": "PYTHON_CENTRIC_STATIC_VALIDATION",
            "notes": capability_notes,
        },
        "artifacts": {
            "qonfirmer_markdown": rel_path(workspace_root, qonfirmer_md) if qonfirmer_md.exists() else None,
            "qonfirmer_json": rel_path(workspace_root, qonfirmer_json) if qonfirmer_json.exists() else None,
            "verification_markdown": rel_path(workspace_root, verification_md) if verification_md.exists() else None,
            "smoketest_markdown": rel_path(workspace_root, smoketest_md) if smoketest_md.exists() else None,
            "smoketest_json": rel_path(workspace_root, smoketest_json) if smoketest_json.exists() else None,
        },
        "qonfirmer_present": qonfirmer_md.exists() or qonfirmer_json.exists(),
        "verification_status": verification_status_match.group(1) if verification_status_match else None,
    }
    return write_json(workspace_root, "validation/validation-bundle.v1.json", payload)


def write_qonstrictor_bridge(workspace_root: Path) -> str | None:
    qonstrictor_result_path = workspace_root / "qontract.d" / "qonstrictor-result.v1.json"
    if not qonstrictor_result_path.exists():
        return None
    qonstrictor_markdown_path = workspace_root / "qontract.d" / "qonstrictor-result.v1.md"
    task_spec_path = workspace_root / "task" / "task-spec.v1.json"
    task_spec = read_json(task_spec_path)
    qonstrictor_result = read_json(qonstrictor_result_path)
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "qonstrictor-bridge.v1",
        "generated_at": now_utc(),
        "canonical_stage_id": "CONSTRAINT",
        "stage_agent": "qonstrictor",
        **execution_meta,
        "task_spec_ref": rel_path(workspace_root, task_spec_path) if task_spec_path.exists() else None,
        "qonstrictor_result_ref": rel_path(workspace_root, qonstrictor_result_path),
        "status": qonstrictor_result.get("status"),
        "task_ready": task_spec.get("ready"),
    }
    if qonstrictor_markdown_path.exists():
        payload["qonstrictor_markdown_ref"] = rel_path(workspace_root, qonstrictor_markdown_path)
    return write_json(workspace_root, "qontract.d/qonstrictor-bridge.v1.json", payload)


def write_realization_bridge(workspace_root: Path, cycle: int) -> str:
    canonical_path = workspace_root / "realization" / "realization-bundle.v1.json"
    if canonical_path.exists():
        return "realization/realization-bundle.v1.json"
    changed_path = workspace_root / "exeq.d" / f"cyqle{cycle}_changed.md"
    summary_path = workspace_root / "exeq.d" / f"cyqle{cycle}_summary.md"
    changed_text = read_text(changed_path)
    changed_files = parse_changed_files(changed_text)
    changed_scope_manifests = sorted(
        rel_path(workspace_root, path)
        for path in (workspace_root / "build" / "groups").glob("*/changed-files.v1.json")
    ) if (workspace_root / "build" / "groups").exists() else []
    validation_mode = determine_validation_mode(workspace_root)
    recovery_refs = []
    attempt_refs = []
    for manifest_ref in changed_scope_manifests:
        manifest_payload = read_json(workspace_root / manifest_ref)
        recovery_refs.extend(manifest_payload.get("recovery_refs", []))
        attempt_refs.extend(manifest_payload.get("attempt_manifest_refs", []))
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "realization-bundle.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "canonical_stage_id": "REALIZATION",
        **execution_meta,
        "sources": {
            "changed_manifest": rel_path(workspace_root, changed_path) if changed_path.exists() else None,
            "execution_summary": rel_path(workspace_root, summary_path) if summary_path.exists() else None,
        },
        "structural_reality": {
            "changed_files": changed_files,
            "changed_file_count": len(changed_files),
            "grouped_scope_manifests": changed_scope_manifests,
            "recovery_refs": sorted(set(recovery_refs)),
            "attempt_manifest_refs": sorted(set(attempt_refs)),
        },
        "behavioral_reality": {
            "validation_execution_mode": validation_mode,
            "executed_test_runner_present": validation_mode in {"EXECUTED", "MIXED"},
        },
        "evidence_reality": {
            "evidence_status": determine_evidence_status(workspace_root),
            "direct_observation_paths": [
                rel_path(workspace_root, changed_path) if changed_path.exists() else None,
                rel_path(workspace_root, summary_path) if summary_path.exists() else None,
            ],
            "unknowns": [
                "No dedicated realization stage exists yet in the current engine.",
                "Realization bridge fallback provides limited smoke detail when canonical realization artifacts are missing.",
            ],
        },
    }
    return write_json(workspace_root, "realization/realization-bundle.v1.json", payload)


def write_inspection_bridge(workspace_root: Path, cycle: int) -> str:
    canonical_path = workspace_root / "verdict" / "inspection-verdict.v1.json"
    if canonical_path.exists():
        return "verdict/inspection-verdict.v1.json"
    reqap_path = workspace_root / "reqap.d" / f"cyqle{cycle}_reqap.md"
    reqap_text = read_text(reqap_path)
    execution_meta = execution_metadata_for_workspace(workspace_root)
    payload = {
        "schema_version": "inspection-verdict-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "stage_agent": "inspeqtor",
        "canonical_stage_id": "INSPECTION",
        **execution_meta,
        "assessment": parse_assessment(reqap_text),
        "reqap_path": rel_path(workspace_root, reqap_path) if reqap_path.exists() else None,
    }
    return write_json(workspace_root, "verdict/inspection-verdict-bridge.v1.json", payload)


def collect_agent_artifacts(workspace_root: Path, agent_name: str, cycle: int) -> tuple[list[str], list[str]]:
    artifacts: list[str] = []
    notes: list[str] = []
    if agent_name == "qrystallizer":
        tasq_path = workspace_root / "tasq.d" / f"cyqle{cycle}_tasq.md"
        if tasq_path.exists():
            append_unique(artifacts, rel_path(workspace_root, tasq_path))
        for rel_candidate in [
            "task/task-intake-bridge.v1.json",
            "task/task-spec.v1.json",
            "task/clarification-log.v1.json",
            "task/clarification-response.v1.json",
            "task/clarification-summary.md",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
        notes.append("Canonical Qrystallizer intake ran without mutating the canonical task input.")
    elif agent_name == "qonstrictor":
        bridge_path = write_qonstrictor_bridge(workspace_root)
        if bridge_path:
            append_unique(artifacts, bridge_path)
        for rel_candidate in [
            "qontract.d/qonstrictor-result.v1.json",
            "qontract.d/qonstrictor-result.v1.md",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif agent_name == "instruqtor":
        append_unique(artifacts, write_planning_bridge(workspace_root, cycle))
        for rel_candidate in [
            "planning/execution-blueprint.v1.json",
            "planning/execution-blueprint.md",
            "planning/architecture-foundation.md",
            "planning/dependency-interaction-contract.v1.json",
            "planning/dependency-interaction-contract.md",
            "planning/component-contracts.v1.json",
            "planning/component-contracts.md",
            "planning/validation-plan.v1.json",
            "planning/validation-plan.md",
            "planning/completion-criteria.v1.json",
            "planning/completion-criteria.md",
            "planning/build-groups.v1.json",
            "planning/estimation-basis.v1.json",
            # v1.3.13: Six-Shooter Qontract support
            "qontract.d/six-shooter-manifest.v1.json",
            "qontract.d/00-current-state.md",
            "qontract.d/01-execution-plan.md",
            "qontract.d/02-hard-ruleset.md",
            "qontract.d/03-migration-bridge.md",
            "qontract.d/04-contracts.md",
            "qontract.d/05-target-state.md",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
        for briq in sorted((workspace_root / "briq.d").glob(f"cyqle{cycle}_*.md")):
            append_unique(artifacts, rel_path(workspace_root, briq))
        for contract_artifact in ["qontract.d/qontract.json", "qontract.d/qontract.md"]:
            if (workspace_root / contract_artifact).exists():
                append_unique(artifacts, contract_artifact)
    elif agent_name == "calqulator":
        append_unique(artifacts, write_estimation_bridge(workspace_root, cycle))
        for rel_candidate in ["estimation/estimate.v1.json", "estimation/estimate.md"]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif agent_name == "construqtor":
        append_unique(artifacts, write_build_bridge(workspace_root, cycle))
        append_unique(artifacts, write_realization_bridge(workspace_root, cycle))
        for rel_candidate in [
            f"exeq.d/cyqle{cycle}_summary.md",
            f"exeq.d/cyqle{cycle}_changed.md",
            f"exeq.d/cyqle{cycle}",
            "build/groups",
            "build/attempts",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif agent_name == "inspeqtor":
        append_unique(artifacts, write_validation_bridge(workspace_root, cycle))
        append_unique(artifacts, write_realization_bridge(workspace_root, cycle))
        append_unique(artifacts, write_inspection_bridge(workspace_root, cycle))
        for rel_candidate in [
            "validation/validation-bundle.v1.json",
            "validation/validation-summary.md",
            "realization/realization-bundle.v1.json",
            "realization/realization-summary.md",
            "verdict/inspection-input.v1.json",
            "verdict/inspection-runtime.v1.json",
            "verdict/inspection-verdict.v1.json",
            "verdict/inspection-verdict.md",
            "verdict/repair-plan.v1.json",
            "verdict/repair-plan.md",
            "continuation/continuation-metadata.v1.json",
            f"reqap.d/cyqle{cycle}_reqap.md",
            f"reqap.d/cyqle{cycle}_qonfirmer.md",
            f"reqap.d/cyqle{cycle}_qonfirmer.json",
            f"reqap.d/cyqle{cycle}/cyqle{cycle}_verification.md",
            f"reqap.d/cyqle{cycle}/cyqle{cycle}_smoketest.md",
            f"reqap.d/cyqle{cycle}/cyqle{cycle}_smoketest.v1.json",
            f"reqap.d/cyqle{cycle}",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif agent_name == "qontextor":
        if (workspace_root / "qontext.d").exists():
            append_unique(artifacts, "qontext.d")
    elif agent_name == "qompressor":
        if (workspace_root / "bloq.d").exists():
            append_unique(artifacts, "bloq.d")
    elif agent_name == "qontrabender":
        if (workspace_root / "qache.d").exists():
            append_unique(artifacts, "qache.d")
        if (workspace_root / "qache.d" / "manifest.json").exists():
            append_unique(artifacts, "qache.d/manifest.json")
            notes.append("Cache manifest linked as supplementary evidence; canonical run manifest remains authoritative.")
    return artifacts, notes


def sync_artifact_slots(workspace_root: Path) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    slots = manifest.setdefault("artifacts", {})
    bridge_candidates = {
        "task_input_bridge": "task/task-intake-bridge.v1.json",
        "task_spec": "task/task-spec.v1.json",
        "clarification_log": "task/clarification-log.v1.json",
        "clarification_response": "task/clarification-response.v1.json",
        "clarification_summary": "task/clarification-summary.md",
        "qonstrictor_result": "qontract.d/qonstrictor-result.v1.json",
        "qonstrictor_output": "qontract.d/qonstrictor-bridge.v1.json",
        "planning_output": "planning/planning-bridge.v1.json",
        "execution_blueprint": "planning/execution-blueprint.v1.json",
        "architecture_foundation": "planning/architecture-foundation.md",
        "dependency_contract": "planning/dependency-interaction-contract.v1.json",
        "component_contracts": "planning/component-contracts.v1.json",
        "validation_plan": "planning/validation-plan.v1.json",
        "completion_criteria": "planning/completion-criteria.v1.json",
        "build_groups": "planning/build-groups.v1.json",
        "estimation_output": "estimation/estimation-bridge.v1.json",
        "estimate_artifact": "estimation/estimate.v1.json",
        "build_output": "build/build-output-bridge.v1.json",
        "build_attempts_root": "build/attempts",
        "validation_output": "validation/validation-bundle.v1.json",
        "realization_output": "realization/realization-bundle.v1.json",
        "inspection_input": "verdict/inspection-input.v1.json",
        "inspection_runtime": "verdict/inspection-runtime.v1.json",
        "inspection_output": "verdict/inspection-verdict.v1.json",
        "inspection_output_bridge": "verdict/inspection-verdict-bridge.v1.json",
        "repair_plan": "verdict/repair-plan.v1.json",
        "continuation_metadata": "continuation/continuation-metadata.v1.json",
        "cache_manifest": "qache.d/manifest.json",
        "six_shooter_manifest": "qontract.d/six-shooter-manifest.v1.json",
    }
    for slot, rel_candidate in bridge_candidates.items():
        if (workspace_root / rel_candidate).exists():
            slots[slot] = rel_candidate
    save_manifest(workspace_root, manifest)
    return manifest


def record_agent_completion(workspace_root: Path, agent_name: str, cycle: int, success: bool = True) -> dict[str, Any]:
    canonical_stage = STAGE_ALIAS_MAP.get(agent_name)
    artifacts, notes = collect_agent_artifacts(workspace_root, agent_name, cycle)
    if agent_name == "inspeqtor":
        validation_artifacts = [
            path for path in artifacts
            if path.startswith("validation/")
            or path.endswith("_qonfirmer.md")
            or path.endswith("_qonfirmer.json")
            or path.endswith("_verification.md")
            or path.endswith("_smoketest.md")
            or path.endswith("_smoketest.v1.json")
        ]
        realization_artifacts = [path for path in artifacts if path.startswith("realization/")]
        if validation_artifacts:
            complete_stage(
                workspace_root,
                "VALIDATION",
                "inspeqtor:validation",
                cycle,
                artifacts=validation_artifacts,
                notes=["Validation artifacts were produced inside the inspeqtor runtime boundary."],
                success=success,
            )
        if realization_artifacts:
            complete_stage(
                workspace_root,
                "REALIZATION",
                "inspeqtor:realization",
                cycle,
                artifacts=realization_artifacts,
                notes=["Realization artifacts were produced inside the inspeqtor runtime boundary."],
                success=success,
            )
    if canonical_stage:
        complete_stage(workspace_root, canonical_stage, agent_name, cycle, artifacts=artifacts, notes=notes, success=success)
    else:
        record_support_service(workspace_root, agent_name, cycle, artifacts=artifacts, notes=notes, success=success)
    manifest = sync_artifact_slots(workspace_root)
    if agent_name == "inspeqtor":
        inspection_path = workspace_root / "verdict" / "inspection-verdict.v1.json"
        if not inspection_path.exists():
            inspection_path = workspace_root / "verdict" / "inspection-verdict-bridge.v1.json"
        if inspection_path.exists():
            verdict = json.loads(inspection_path.read_text(encoding="utf-8"))
            assessment = verdict.get("status") or verdict.get("assessment")
            if assessment == "SUCCESS":
                manifest["terminal"]["final_verdict"] = "SUCCESS"
                manifest["compatibility"]["continuation_model"] = "EXPLICIT_REPAIR_PLAN_CANONICAL"
            elif assessment in {"PARTIAL", "FAILURE"}:
                manifest["terminal"]["final_verdict"] = assessment
            if verdict.get("repair_required"):
                manifest["run_status"] = "RUN_REPAIR_PENDING"
                manifest["lifecycle_state"] = "CONTINUABLE"
                manifest["compatibility"]["continuation_model"] = "EXPLICIT_REPAIR_PLAN_CANONICAL"
            save_manifest(workspace_root, manifest)
    return manifest



def finalize_manifest(workspace_root: Path, run_outcome: str, detail: str) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    outcome_map = {
        "completed": ("COMPLETED", "RUN_COMPLETED"),
        "partial": ("PARTIAL", "RUN_PARTIAL"),
        "blocked": ("BLOCKED", "RUN_WAITING_FOR_INPUT"),
        "failed": ("FAILED", "RUN_FAILED"),
        "aborted": ("ABORTED", "RUN_ABORTED"),
    }
    lifecycle_state, run_status = outcome_map.get(run_outcome, ("FAILED", "RUN_FAILED"))
    manifest["current_stage"] = "FINALIZE"
    manifest["lifecycle_state"] = lifecycle_state
    manifest["run_status"] = run_status
    manifest["validation_execution_mode"] = determine_validation_mode(workspace_root)
    manifest["evidence_status"] = determine_evidence_status(workspace_root)
    manifest["confidence_status"] = determine_confidence_status(workspace_root)
    manifest["terminal"]["completed_at"] = now_utc()
    if manifest["terminal"]["final_verdict"] is None:
        manifest["terminal"]["final_verdict"] = lifecycle_state
    save_manifest(workspace_root, manifest)
    complete_stage(workspace_root, "FINALIZE", None, None, artifacts=[], notes=[detail], success=run_outcome != "failed")
    append_audit_event(workspace_root, "run_finalized", "FINALIZE", None, detail, {"outcome": run_outcome, "execution": ensure_execution_block(manifest).get("state", {}).copy()})
    return load_manifest(workspace_root)


def cli() -> int:
    parser = argparse.ArgumentParser(description="QonQrete manifest bridge helpers")
    parser.add_argument("command", choices=["init", "start-stage", "complete-agent", "record-support", "finalize"])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--stage")
    parser.add_argument("--agent-name")
    parser.add_argument("--cycle", type=int)
    parser.add_argument("--detail", default="")
    parser.add_argument("--outcome", default="completed")
    args = parser.parse_args()

    workspace_root = Path(args.workspace)
    if args.command == "init":
        create_manifest(workspace_root)
    elif args.command == "start-stage":
        if not args.stage:
            raise SystemExit("--stage is required for start-stage")
        start_stage(workspace_root, args.stage, args.agent_name, args.cycle, args.detail or "Stage started.")
    elif args.command == "complete-agent":
        if not args.agent_name:
            raise SystemExit("--agent-name is required for complete-agent")
        record_agent_completion(workspace_root, args.agent_name, args.cycle or 1)
    elif args.command == "record-support":
        if not args.agent_name:
            raise SystemExit("--agent-name is required for record-support")
        record_support_service(workspace_root, args.agent_name, args.cycle, notes=[args.detail] if args.detail else [])
    elif args.command == "finalize":
        finalize_manifest(workspace_root, args.outcome, args.detail or "Run finalized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
