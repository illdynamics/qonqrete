#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_MANIFEST_FILE = "run-manifest.v1.json"
AUDIT_DIR = "audit"
AUDIT_TIMELINE_FILE = "timeline.md"
AUDIT_EVENTS_FILE = "events.ndjson"

STAGE_IDS = [
    "INTAKE",
    "CLARIFICATION",
    "GUARD",
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
    "GUARDING",
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
    "tasqleveler": "CLARIFICATION",
    "qrystallizer": "CLARIFICATION",
    "guard": "GUARD",
    "instruqtor": "PLANNING",
    "calqulator": "ESTIMATION",
    "construqtor": "BUILD",
    "inspeqtor": "INSPECTION",
    "LoQal Verification": "VALIDATION",
    "QontractGuard": "GUARD",
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

LEGACY_SUBSTAGE_ALIASES = {
    "QontractGuard": "GUARD",
    "LoQal Verification": "VALIDATION",
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


def parse_changed_files(markdown_text: str) -> list[str]:
    return sorted(set(re.findall(r"`([^`]+)`", markdown_text)))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def determine_validation_mode(workspace_root: Path) -> str:
    reqap_dir = workspace_root / "reqap.d"
    has_guard = any(reqap_dir.glob("cyqle*_qontract_guard.json")) or any(reqap_dir.glob("cyqle*_qontract_guard.md"))
    has_verification = any(reqap_dir.glob("cyqle*/cyqle*_verification.md"))
    if has_guard or has_verification:
        return "STATIC_ONLY"
    return "NONE"


def determine_evidence_status(workspace_root: Path) -> str:
    has_build = any(workspace_root.glob("exeq.d/cyqle*_summary.md")) and any(workspace_root.glob("exeq.d/cyqle*_changed.md"))
    has_validation = determine_validation_mode(workspace_root) != "NONE"
    has_inspection = any(workspace_root.glob("reqap.d/cyqle*_reqap.md"))
    has_realization = (workspace_root / "realization" / "realization-bundle.v1.json").exists()
    if has_build and has_validation and has_inspection and has_realization:
        return "EVIDENCE_COMPLETE"
    if has_build or has_validation or has_inspection:
        return "EVIDENCE_PARTIAL"
    return "EVIDENCE_MISSING"


def determine_confidence_status(workspace_root: Path) -> str:
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
            "| Time (UTC) | Event | Canonical Stage | Legacy Alias | Details |\n"
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
    legacy_alias: str | None,
    detail: str,
    payload: dict[str, Any] | None = None,
) -> None:
    timeline_path, events_path = ensure_audit_files(workspace_root)
    timestamp = now_utc()
    line = f"| {timestamp} | {event_type} | {canonical_stage_id or '-'} | {legacy_alias or '-'} | {detail.replace('|', '/')} |\n"
    with timeline_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    event = {
        "timestamp": timestamp,
        "event_type": event_type,
        "canonical_stage_id": canonical_stage_id,
        "legacy_alias": legacy_alias,
        "detail": detail,
    }
    if payload:
        event["payload"] = payload
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def base_manifest(workspace_root: Path) -> dict[str, Any]:
    legacy_qage_id = os.environ.get("QONQ_LEGACY_QAGE_ID") or workspace_root.name
    resumed_from_qage = os.environ.get("QONQ_RESUMED_FROM_QAGE")
    run_kind = os.environ.get("QONQ_RUN_KIND", "run")
    raw_task_rel = rel_path(workspace_root, workspace_root / "tasq.d" / "cyqle1_tasq.md")
    manifest = {
        "schema_version": "run-manifest.v1",
        "run_id": legacy_qage_id,
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
            "legacy_qage_id": legacy_qage_id,
            "resumed_from_qage": resumed_from_qage,
        },
        "compatibility": {
            "partial_write_model": "SCOPED_STAGED_ATOMIC_ATTEMPTS",
            "partial_write_disclosure": "ConstruQtor stages scoped attempt writes, validates against an overlay workspace, and commits atomically with snapshot-based recovery metadata.",
            "continuation_model": "EXPLICIT_REPAIR_PLAN_CANONICAL_WITH_LEGACY_COMPATIBILITY_GATE",
            "canonical_manifest_authority": True,
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
            "legacy_substage_aliases": LEGACY_SUBSTAGE_ALIASES,
        },
        "task": {
            "raw_input_path": raw_task_rel,
            "current_cycle_task_path": raw_task_rel,
            "task_spec_path": rel_path(workspace_root, workspace_root / "task" / "task-spec.v1.json"),
            "clarification_log_path": rel_path(workspace_root, workspace_root / "task" / "clarification-log.v1.json"),
            "guard_result_path": rel_path(workspace_root, workspace_root / "guard" / "guard-result.v1.json"),
        },
        "artifacts": {
            "run_manifest": RUN_MANIFEST_FILE,
            "audit_summary": f"{AUDIT_DIR}/{AUDIT_TIMELINE_FILE}",
            "audit_events": f"{AUDIT_DIR}/{AUDIT_EVENTS_FILE}",
            "cache_manifest": rel_path(workspace_root, workspace_root / "qache.d" / "manifest.json"),
            "task_spec": rel_path(workspace_root, workspace_root / "task" / "task-spec.v1.json"),
            "clarification_log": rel_path(workspace_root, workspace_root / "task" / "clarification-log.v1.json"),
            "guard_result": rel_path(workspace_root, workspace_root / "guard" / "guard-result.v1.json"),
            "repair_plan": rel_path(workspace_root, workspace_root / "verdict" / "repair-plan.v1.json"),
            "continuation_metadata": rel_path(workspace_root, workspace_root / "continuation" / "continuation-metadata.v1.json"),
            "build_attempts_root": rel_path(workspace_root, workspace_root / "build" / "attempts"),
        },
        "legacy_links": {
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
    manifest = base_manifest(workspace_root)
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


def ensure_stage_record(manifest: dict[str, Any], stage_id: str, cycle: int | None, legacy_alias: str | None) -> dict[str, Any]:
    for record in manifest["stages"]:
        if record["stage_id"] == stage_id and record.get("cycle") == cycle and record.get("legacy_alias") == legacy_alias:
            return record
    record = {
        "stage_id": stage_id,
        "legacy_alias": legacy_alias,
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


def start_stage(workspace_root: Path, stage_id: str, legacy_alias: str | None, cycle: int | None, detail: str) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    record = ensure_stage_record(manifest, stage_id, cycle, legacy_alias)
    record["status"] = "in_progress"
    record["started_at"] = record["started_at"] or now_utc()
    manifest["current_stage"] = stage_id
    manifest["run_status"] = "RUN_ACTIVE"
    lifecycle_map = {
        "INTAKE": "READY_FOR_CLARIFICATION",
        "CLARIFICATION": "CLARIFYING",
        "GUARD": "GUARDING",
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
    append_audit_event(workspace_root, "stage_started", stage_id, legacy_alias, detail, {"cycle": cycle})
    return save_manifest(workspace_root, manifest)


def complete_stage(
    workspace_root: Path,
    stage_id: str,
    legacy_alias: str | None,
    cycle: int | None,
    artifacts: list[str] | None = None,
    notes: list[str] | None = None,
    success: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    record = ensure_stage_record(manifest, stage_id, cycle, legacy_alias)
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
        legacy_alias,
        f"{stage_id} completed with {len(artifacts or [])} linked artifacts.",
        {"cycle": cycle, "artifacts": artifacts or [], "notes": notes or []},
    )
    return save_manifest(workspace_root, manifest)


def record_support_service(
    workspace_root: Path,
    legacy_alias: str,
    cycle: int | None,
    artifacts: list[str] | None = None,
    notes: list[str] | None = None,
    success: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    service_record = {
        "service_id": SUPPORT_SERVICE_ALIASES.get(legacy_alias, "SUPPORT_SERVICE"),
        "legacy_alias": legacy_alias,
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
        legacy_alias,
        f"Support service {legacy_alias} recorded.",
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
    payload = {
        "schema_version": "task-intake-bridge.v1",
        "generated_at": now_utc(),
        "legacy_input_path": rel_path(workspace_root, raw_task),
        "legacy_qage_id": os.environ.get("QONQ_LEGACY_QAGE_ID") or workspace_root.name,
        "run_kind": os.environ.get("QONQ_RUN_KIND", "run"),
        "resumed_from_qage": os.environ.get("QONQ_RESUMED_FROM_QAGE"),
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
    guard_result = workspace_root / "guard" / "guard-result.v1.json"
    payload = {
        "schema_version": "planning-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "legacy_stage_alias": "instruqtor",
        "canonical_stage_id": "PLANNING",
        "task_spec_ref": rel_path(workspace_root, task_spec) if task_spec.exists() else None,
        "guard_result_ref": rel_path(workspace_root, guard_result) if guard_result.exists() else None,
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
    payload = {
        "schema_version": "estimation-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "legacy_stage_alias": "calqulator",
        "canonical_stage_id": "ESTIMATION",
        "estimated_briqs": estimated_briqs,
        "estimated_count": len(estimated_briqs),
        "estimate_artifact": "estimation/estimate.v1.json" if (workspace_root / "estimation" / "estimate.v1.json").exists() else None,
    }
    return write_json(workspace_root, "estimation/estimation-bridge.v1.json", payload)


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
    payload = {
        "schema_version": "build-output-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "legacy_stage_alias": "construqtor",
        "canonical_stage_id": "BUILD",
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
    }
    return write_json(workspace_root, "build/build-output-bridge.v1.json", payload)


def write_validation_bridge(workspace_root: Path, cycle: int) -> str:
    canonical_path = workspace_root / "validation" / "validation-bundle.v1.json"
    if canonical_path.exists():
        return "validation/validation-bundle.v1.json"
    reqap_dir = workspace_root / "reqap.d"
    guard_md = reqap_dir / f"cyqle{cycle}_qontract_guard.md"
    guard_json = reqap_dir / f"cyqle{cycle}_qontract_guard.json"
    verification_md = reqap_dir / f"cyqle{cycle}" / f"cyqle{cycle}_verification.md"
    verification_text = read_text(verification_md)
    verification_status_match = re.search(r"\*\*Status:\*\*\s*([A-Z]+)", verification_text)
    payload = {
        "schema_version": "validation-bundle.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "canonical_stage_id": "VALIDATION",
        "legacy_sources": [
            {"legacy_alias": "QontractGuard", "canonical_stage_id": "GUARD"},
            {"legacy_alias": "LoQal Verification", "canonical_stage_id": "VALIDATION"},
        ],
        "validation_execution_mode": determine_validation_mode(workspace_root),
        "capability_disclosure": {
            "deterministic_validation_strength": "PYTHON_CENTRIC_STATIC_VALIDATION",
            "notes": [
                "Validation remains Python-skewed in the current engine.",
                "Executed project test runs are not yet a canonical runtime stage.",
            ],
        },
        "artifacts": {
            "guard_markdown": rel_path(workspace_root, guard_md) if guard_md.exists() else None,
            "guard_json": rel_path(workspace_root, guard_json) if guard_json.exists() else None,
            "verification_markdown": rel_path(workspace_root, verification_md) if verification_md.exists() else None,
        },
        "guard_present": guard_md.exists() or guard_json.exists(),
        "verification_status": verification_status_match.group(1) if verification_status_match else None,
    }
    return write_json(workspace_root, "validation/validation-bundle.v1.json", payload)


def write_guard_bridge(workspace_root: Path) -> str | None:
    guard_result_path = workspace_root / "guard" / "guard-result.v1.json"
    if not guard_result_path.exists():
        return None
    guard_markdown_path = workspace_root / "guard" / "guard-result.v1.md"
    task_spec_path = workspace_root / "task" / "task-spec.v1.json"
    task_spec = read_json(task_spec_path)
    guard_result = read_json(guard_result_path)
    payload = {
        "schema_version": "guard-bridge.v1",
        "generated_at": now_utc(),
        "canonical_stage_id": "GUARD",
        "legacy_stage_alias": "guard",
        "task_spec_ref": rel_path(workspace_root, task_spec_path) if task_spec_path.exists() else None,
        "guard_result_ref": rel_path(workspace_root, guard_result_path),
        "status": guard_result.get("status"),
        "task_ready": task_spec.get("ready"),
    }
    if guard_markdown_path.exists():
        payload["guard_markdown_ref"] = rel_path(workspace_root, guard_markdown_path)
    return write_json(workspace_root, "guard/guard-bridge.v1.json", payload)


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
    recovery_refs = []
    attempt_refs = []
    for manifest_ref in changed_scope_manifests:
        manifest_payload = read_json(workspace_root / manifest_ref)
        recovery_refs.extend(manifest_payload.get("recovery_refs", []))
        attempt_refs.extend(manifest_payload.get("attempt_manifest_refs", []))
    payload = {
        "schema_version": "realization-bundle.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "canonical_stage_id": "REALIZATION",
        "legacy_sources": {
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
            "validation_execution_mode": determine_validation_mode(workspace_root),
            "executed_test_runner_present": False,
        },
        "evidence_reality": {
            "evidence_status": determine_evidence_status(workspace_root),
            "direct_observation_paths": [
                rel_path(workspace_root, changed_path) if changed_path.exists() else None,
                rel_path(workspace_root, summary_path) if summary_path.exists() else None,
            ],
            "unknowns": [
                "No dedicated realization stage exists yet in the legacy engine.",
                "No general project test runner is wired into the current core pipeline.",
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
    payload = {
        "schema_version": "inspection-verdict-bridge.v1",
        "generated_at": now_utc(),
        "cycle": cycle,
        "legacy_stage_alias": "inspeqtor",
        "canonical_stage_id": "INSPECTION",
        "assessment": parse_assessment(reqap_text),
        "legacy_reqap_path": rel_path(workspace_root, reqap_path) if reqap_path.exists() else None,
    }
    return write_json(workspace_root, "verdict/inspection-verdict-bridge.v1.json", payload)


def collect_agent_artifacts(workspace_root: Path, legacy_alias: str, cycle: int) -> tuple[list[str], list[str]]:
    artifacts: list[str] = []
    notes: list[str] = []
    if legacy_alias == "tasqleveler":
        tasq_path = workspace_root / "tasq.d" / f"cyqle{cycle}_tasq.md"
        if tasq_path.exists():
            append_unique(artifacts, rel_path(workspace_root, tasq_path))
        for rel_candidate in [
            "task/task-intake-bridge.v1.json",
            "task/task-spec.v1.json",
            "task/clarification-log.v1.json",
            "task/clarification-summary.md",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
        notes.append("Legacy tasqleveler alias now wraps canonical Qrystallizer intake without mutating tasq in place.")
    elif legacy_alias == "guard":
        bridge_path = write_guard_bridge(workspace_root)
        if bridge_path:
            append_unique(artifacts, bridge_path)
        for rel_candidate in [
            "guard/guard-result.v1.json",
            "guard/guard-result.v1.md",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif legacy_alias == "instruqtor":
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
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
        for briq in sorted((workspace_root / "briq.d").glob(f"cyqle{cycle}_*.md")):
            append_unique(artifacts, rel_path(workspace_root, briq))
        for contract_artifact in ["qontract.d/qontract.json", "qontract.d/qontract.md"]:
            if (workspace_root / contract_artifact).exists():
                append_unique(artifacts, contract_artifact)
    elif legacy_alias == "calqulator":
        append_unique(artifacts, write_estimation_bridge(workspace_root, cycle))
        for rel_candidate in ["estimation/estimate.v1.json", "estimation/estimate.md"]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif legacy_alias == "construqtor":
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
    elif legacy_alias == "inspeqtor":
        append_unique(artifacts, write_validation_bridge(workspace_root, cycle))
        append_unique(artifacts, write_realization_bridge(workspace_root, cycle))
        append_unique(artifacts, write_inspection_bridge(workspace_root, cycle))
        for rel_candidate in [
            "validation/validation-bundle.v1.json",
            "validation/validation-summary.md",
            "realization/realization-bundle.v1.json",
            "realization/realization-summary.md",
            "verdict/inspection-input.v1.json",
            "verdict/inspection-verdict.v1.json",
            "verdict/inspection-verdict.md",
            "verdict/repair-plan.v1.json",
            "verdict/repair-plan.md",
            "continuation/continuation-metadata.v1.json",
            f"reqap.d/cyqle{cycle}_reqap.md",
            f"reqap.d/cyqle{cycle}_qontract_guard.md",
            f"reqap.d/cyqle{cycle}_qontract_guard.json",
            f"reqap.d/cyqle{cycle}/cyqle{cycle}_verification.md",
            f"reqap.d/cyqle{cycle}",
        ]:
            if (workspace_root / rel_candidate).exists():
                append_unique(artifacts, rel_candidate)
    elif legacy_alias == "qontextor":
        if (workspace_root / "qontext.d").exists():
            append_unique(artifacts, "qontext.d")
    elif legacy_alias == "qompressor":
        if (workspace_root / "bloq.d").exists():
            append_unique(artifacts, "bloq.d")
    elif legacy_alias == "qontrabender":
        if (workspace_root / "qache.d").exists():
            append_unique(artifacts, "qache.d")
        if (workspace_root / "qache.d" / "manifest.json").exists():
            append_unique(artifacts, "qache.d/manifest.json")
            notes.append("Cache manifest linked as legacy evidence only; canonical run manifest remains authoritative.")
    return artifacts, notes


def sync_artifact_slots(workspace_root: Path) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    slots = manifest.setdefault("artifacts", {})
    bridge_candidates = {
        "task_input_bridge": "task/task-intake-bridge.v1.json",
        "task_spec": "task/task-spec.v1.json",
        "clarification_log": "task/clarification-log.v1.json",
        "clarification_summary": "task/clarification-summary.md",
        "guard_result": "guard/guard-result.v1.json",
        "guard_output": "guard/guard-bridge.v1.json",
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
        "inspection_output": "verdict/inspection-verdict.v1.json",
        "inspection_output_bridge": "verdict/inspection-verdict-bridge.v1.json",
        "repair_plan": "verdict/repair-plan.v1.json",
        "continuation_metadata": "continuation/continuation-metadata.v1.json",
        "cache_manifest": "qache.d/manifest.json",
    }
    for slot, rel_candidate in bridge_candidates.items():
        if (workspace_root / rel_candidate).exists():
            slots[slot] = rel_candidate
    save_manifest(workspace_root, manifest)
    return manifest


def record_agent_completion(workspace_root: Path, legacy_alias: str, cycle: int, success: bool = True) -> dict[str, Any]:
    canonical_stage = STAGE_ALIAS_MAP.get(legacy_alias)
    artifacts, notes = collect_agent_artifacts(workspace_root, legacy_alias, cycle)
    if canonical_stage:
        complete_stage(workspace_root, canonical_stage, legacy_alias, cycle, artifacts=artifacts, notes=notes, success=success)
    else:
        record_support_service(workspace_root, legacy_alias, cycle, artifacts=artifacts, notes=notes, success=success)
    manifest = sync_artifact_slots(workspace_root)
    if legacy_alias == "inspeqtor":
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


def record_cycle_promotion(workspace_root: Path, cycle: int, destination: str) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    payload = {
        "cycle": cycle,
        "destination": destination,
        "legacy_alias": "reqap promotion",
        "canonical_stage_id": "REPAIR",
    }
    append_audit_event(
        workspace_root,
        "legacy_cycle_promotion",
        "REPAIR",
        "reqap promotion",
        "Legacy reqap-to-next-tasq promotion recorded for compatibility.",
        payload,
    )
    manifest.setdefault("continuation", []).append(payload)
    manifest["compatibility"]["continuation_model"] = "LEGACY_CYCLE_PROMOTION_COMPATIBILITY"
    return save_manifest(workspace_root, manifest)


def finalize_manifest(workspace_root: Path, run_outcome: str, detail: str) -> dict[str, Any]:
    manifest = load_manifest(workspace_root)
    outcome_map = {
        "completed": ("COMPLETED", "RUN_COMPLETED"),
        "partial": ("PARTIAL", "RUN_PARTIAL"),
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
    append_audit_event(workspace_root, "run_finalized", "FINALIZE", None, detail, {"outcome": run_outcome})
    return load_manifest(workspace_root)


def cli() -> int:
    parser = argparse.ArgumentParser(description="QonQrete manifest bridge helpers")
    parser.add_argument("command", choices=["init", "start-stage", "complete-agent", "record-support", "record-promotion", "finalize"])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--stage")
    parser.add_argument("--legacy-alias")
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
        start_stage(workspace_root, args.stage, args.legacy_alias, args.cycle, args.detail or "Stage started.")
    elif args.command == "complete-agent":
        if not args.legacy_alias:
            raise SystemExit("--legacy-alias is required for complete-agent")
        record_agent_completion(workspace_root, args.legacy_alias, args.cycle or 1)
    elif args.command == "record-support":
        if not args.legacy_alias:
            raise SystemExit("--legacy-alias is required for record-support")
        record_support_service(workspace_root, args.legacy_alias, args.cycle, notes=[args.detail] if args.detail else [])
    elif args.command == "record-promotion":
        record_cycle_promotion(workspace_root, args.cycle or 1, args.detail)
    elif args.command == "finalize":
        finalize_manifest(workspace_root, args.outcome, args.detail or "Run finalized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
