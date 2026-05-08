from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
import json
import time

try:
    from execution_model import (
        ExecutionLimits,
        ExecutionState,
        decide_post_inspection,
        repair_cap_reached,
        total_iteration_cap_reached,
    )
except ImportError:  # pragma: no cover - package import fallback
    from .execution_model import (  # type: ignore
        ExecutionLimits,
        ExecutionState,
        decide_post_inspection,
        repair_cap_reached,
        total_iteration_cap_reached,
    )


REPAIR_BRIEF_MD = Path("verdict") / "sqrewdriver-repair-brief.v1.md"
REPAIR_BRIEF_JSON = Path("verdict") / "sqrewdriver-repair-brief.v1.json"
REPAIR_PLAN = Path("verdict") / "repair-plan.v1.json"
LAST_REPAIR_PLAN = Path("verdict") / "sqrewdriver-last-repair-plan.v1.json"
INSPECTION_VERDICT = Path("verdict") / "inspection-verdict.v1.json"
VALIDATION_BUNDLE = Path("validation") / "validation-bundle.v1.json"
REALIZATION_BUNDLE = Path("realization") / "realization-bundle.v1.json"
COMPLETION_CRITERIA = Path("planning") / "completion-criteria.v1.json"

STALE_FAILURE_CODES = {
    "CONTRACT_TASK_HASH_MISMATCH",
    "CONTRACT_QAGE_ID_MISMATCH",
    "CONTRACT_STALE_ARTIFACT",
    "VALIDATION_PLAN_STALE",
    "HARNESS_RESULT_STALE",
    "REPAIR_HISTORY_STALE",
    "STALE_ARTIFACT_INVALIDATED",
    "CONTRACT_UNRELATED_DEFAULTS_DETECTED",
}


@dataclass
class SqrewdriverDecision:
    action: Literal["STOP", "REPAIR", "STOP_PARTIAL"]
    reason: str
    repair_prompt_path: str | None = None
    repair_plan_path: str | None = None
    summary: dict = field(default_factory=dict)


def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
    except Exception:
        pass
    return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "pass", "success"}


def _falsey(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if value is None:
        return False
    return str(value).strip().lower() in {"0", "false", "no", "off", "none", "pass", "success"}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_rel_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if text.lower() in {
        "none",
        "null",
        "n/a",
        "na",
        "not applicable",
        "no file",
        "no files",
    }:
        return ""
    if text.startswith("qodeyard/"):
        text = text[len("qodeyard/") :]
    while text.startswith("./"):
        text = text[2:]
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def _normalize_paths(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _as_list(values):
        if isinstance(item, dict):
            item = item.get("path") or item.get("file")
        rel = _clean_rel_path(item)
        if rel and rel not in seen:
            seen.add(rel)
            result.append(rel)
    return result


def _required_files(completion_criteria: dict) -> list[str]:
    return _normalize_paths((completion_criteria or {}).get("required_files"))


def _missing_required_files(workspace_root: Path, completion_criteria: dict) -> list[str]:
    missing: list[str] = []
    for rel in _required_files(completion_criteria):
        if not (workspace_root / "qodeyard" / rel).is_file():
            missing.append(rel)
    return missing


def _issue_summary(issue: dict) -> str:
    for key in ("summary", "message", "reason", "check_id", "code", "failure_kind"):
        text = str(issue.get(key) or "").strip()
        if text:
            return " ".join(text.split())
    return "unspecified validation issue"


def _issue_file_hints(issue: dict) -> list[str]:
    files: list[str] = []
    for key in ("file", "files", "related_files", "path", "paths"):
        files.extend(_normalize_paths(issue.get(key)))
    return sorted(set(files))


def _issue_is_invalidated(issue: dict) -> bool:
    return _upper(issue.get("status")) == "INVALIDATED"


def _current_hard_validation_failures(validation_bundle: dict) -> list[dict]:
    failures: list[dict] = []
    for issue in (validation_bundle or {}).get("issues", []) or []:
        if not isinstance(issue, dict) or _issue_is_invalidated(issue):
            continue
        severity = str(issue.get("severity") or "").strip().lower()
        if severity == "error":
            failures.append(issue)

    for check in (validation_bundle or {}).get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        status = _upper(check.get("status"))
        if status in {"FAIL", "FAILURE", "ERROR"}:
            failures.append(
                {
                    "source": "validation_check",
                    "severity": "error",
                    "check_type": check.get("check_id") or check.get("name"),
                    "summary": check.get("summary")
                    or check.get("message")
                    or f"Validation check failed: {check.get('check_id') or check.get('name') or 'unknown'}",
                    "files": check.get("files") or check.get("target_files") or [],
                }
            )
    return failures


def _stale_artifact_failures(*payloads: dict) -> list[dict]:
    stale: list[dict] = []
    for payload in payloads:
        for issue in (payload or {}).get("issues", []) or []:
            if not isinstance(issue, dict) or _issue_is_invalidated(issue):
                continue
            code = _upper(issue.get("check_type") or issue.get("failure_kind") or issue.get("code"))
            source = str(issue.get("source") or "").strip().lower()
            message = str(issue.get("message") or issue.get("summary") or "").strip().lower()
            is_stale = (
                bool(issue.get("stale", False))
                or code in STALE_FAILURE_CODES
                or (source in {"contract_harness", "validation_artifact", "task_artifact"} and "stale" in message)
            )
            severity = str(issue.get("severity") or "").strip().lower()
            if is_stale and severity in {"", "error", "failure"}:
                stale.append(issue)
    return stale


def _inspection_degraded_requires_repair(verdict: dict) -> bool:
    if _upper((verdict or {}).get("inspection_integrity")) != "DEGRADED":
        return False
    if _repair_requested(verdict):
        return True
    if _upper(verdict.get("hard_gate_status")) != "PASS":
        return True
    if _upper(verdict.get("status")) not in {"SUCCESS", "PASS"}:
        return True
    for item in verdict.get("inspection_substep_failures", []) or []:
        if isinstance(item, dict) and not bool(item.get("recoverable", True)):
            return True
    return False


def _repair_requested(verdict: dict) -> bool:
    if "repair_needed" in verdict:
        return _truthy(verdict.get("repair_needed"))
    if "repair_required" in verdict:
        return _truthy(verdict.get("repair_required"))
    return False


def _repair_not_requested(verdict: dict) -> bool:
    if "repair_needed" in verdict:
        return _falsey(verdict.get("repair_needed"))
    if "repair_required" in verdict:
        return _falsey(verdict.get("repair_required"))
    return False


def is_success_verdict(
    verdict: dict,
    validation_bundle: dict,
    completion_criteria: dict,
    workspace_root: Path,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    verdict = verdict or {}
    validation_bundle = validation_bundle or {}
    completion_criteria = completion_criteria or {}

    if not verdict:
        return False, ["inspection_verdict_missing"]

    status = _upper(verdict.get("status") or verdict.get("assessment"))
    hard_gate_status = _upper(verdict.get("hard_gate_status"))
    task_completed = _truthy(verdict.get("task_completed"))

    success_status = status in {"SUCCESS", "PASS"}
    task_completed_with_gate = task_completed and hard_gate_status == "PASS"
    if not (success_status or task_completed_with_gate):
        reasons.append(f"verdict_not_success:{status or 'UNKNOWN'}")

    if hard_gate_status != "PASS":
        reasons.append(f"hard_gate_not_pass:{hard_gate_status or 'UNKNOWN'}")

    if not _repair_not_requested(verdict):
        reasons.append("repair_requested_or_ambiguous")

    missing_required = _missing_required_files(workspace_root, completion_criteria)
    if missing_required:
        reasons.append("missing_required_files:" + ",".join(missing_required))

    hard_failures = _current_hard_validation_failures(validation_bundle)
    if hard_failures:
        reasons.append(f"current_hard_validation_failures:{len(hard_failures)}")

    stale_failures = _stale_artifact_failures(validation_bundle, verdict)
    if stale_failures:
        reasons.append(f"stale_artifact_failures:{len(stale_failures)}")

    if _inspection_degraded_requires_repair(verdict):
        reasons.append("inspection_degraded_requires_repair")

    return not reasons, reasons


def _failure_summary(
    *,
    failure_reasons: list[str],
    verdict: dict,
    validation_bundle: dict,
    completion_criteria: dict,
    workspace_root: Path,
    issue_limit: int,
) -> dict:
    hard_failures = _current_hard_validation_failures(validation_bundle)
    stale_failures = _stale_artifact_failures(validation_bundle, verdict)
    missing_required = _missing_required_files(workspace_root, completion_criteria)
    validation_issues = []
    for issue in (validation_bundle or {}).get("issues", []) or []:
        if isinstance(issue, dict) and not _issue_is_invalidated(issue):
            validation_issues.append(issue)
    return {
        "failure_reasons": failure_reasons,
        "missing_required_files": missing_required,
        "hard_validation_failure_count": len(hard_failures),
        "stale_artifact_failure_count": len(stale_failures),
        "hard_failure_files": sorted(
            set(
                _normalize_paths((verdict or {}).get("hard_failure_files"))
                + [
                    path
                    for issue in hard_failures
                    for path in _issue_file_hints(issue)
                ]
            )
        ),
        "issues": [
            {
                "summary": _issue_summary(issue),
                "source": issue.get("source"),
                "severity": issue.get("severity"),
                "check_type": issue.get("check_type") or issue.get("code") or issue.get("failure_kind"),
                "files": _issue_file_hints(issue),
                "stale": bool(issue.get("stale", False)),
            }
            for issue in validation_issues[: max(0, issue_limit)]
        ],
    }


def _read_reqap_excerpt(workspace_root: Path, cycle: int, config: dict) -> str:
    limit = int(((config or {}).get("sqrewdriver") or {}).get("include_reqap_excerpt_chars") or 12000)
    candidates = [workspace_root / "reqap.d" / f"cyqle{cycle}_reqap.md"]
    candidates.extend(sorted((workspace_root / "reqap.d").glob("cyqle*_reqap.md"), reverse=True))
    for path in candidates:
        try:
            if path.exists():
                text = path.read_text(encoding="utf-8")
                if len(text) > limit:
                    return text[:limit].rstrip() + "\n[truncated]"
                return text
        except Exception:
            continue
    return ""


def _prior_attempts(repair_plan: dict, config: dict) -> list[dict]:
    sq_cfg = ((config or {}).get("sqrewdriver") or {})
    if not bool(sq_cfg.get("include_prior_attempts", True)):
        return []
    escalation = repair_plan.get("repair_escalation") if isinstance(repair_plan.get("repair_escalation"), dict) else {}
    attempts = escalation.get("prior_attempt_records") or repair_plan.get("prior_attempts") or []
    return [item for item in attempts if isinstance(item, dict)]


def _fallback_target_files(
    validation_bundle: dict,
    completion_criteria: dict,
    verdict: dict,
) -> list[str]:
    paths: set[str] = set(_missing_required_files(Path("."), {}))
    paths.update(_required_files(completion_criteria))
    paths.update(_normalize_paths((verdict or {}).get("hard_failure_files")))
    for issue in (validation_bundle or {}).get("issues", []) or []:
        if isinstance(issue, dict):
            paths.update(_issue_file_hints(issue))
    return sorted(path for path in paths if path)


def _cycle_briq_files(workspace_root: Path, cycle: int) -> list[str]:
    briq_dir = workspace_root / "briq.d"
    names = [path.name for path in sorted(briq_dir.glob(f"cyqle{cycle}_*.md"))]
    if names:
        return names
    return [path.name for path in sorted(briq_dir.glob("*.md"))]


def _ensure_repair_plan(
    workspace_root: Path,
    *,
    cycle: int,
    verdict: dict,
    repair_plan: dict,
    validation_bundle: dict,
    completion_criteria: dict,
    failure_summary: dict,
) -> dict:
    plan = dict(repair_plan or {})
    target_files = _normalize_paths(plan.get("target_files") or plan.get("allowed_edit_paths"))
    if not target_files:
        target_files = _fallback_target_files(validation_bundle, completion_criteria, verdict)

    target_briq_files = [
        str(item).strip()
        for item in (plan.get("target_briq_files") or [])
        if str(item or "").strip()
    ]
    if not target_briq_files:
        target_briq_files = _cycle_briq_files(workspace_root, cycle)

    validation_scope_files = _normalize_paths(plan.get("validation_scope_files") or target_files)
    allowed_edit_paths = _normalize_paths(plan.get("allowed_edit_paths") or target_files)
    locked_paths = _normalize_paths(plan.get("locked_file_paths") or plan.get("locked_files"))
    hard_failure_files = _normalize_paths(plan.get("hard_failure_files") or failure_summary.get("hard_failure_files"))
    unlocked_paths = _normalize_paths(plan.get("unlocked_file_paths"))
    allowed_edit_paths = [
        rel
        for rel in allowed_edit_paths
        if rel not in locked_paths or rel in unlocked_paths or rel in hard_failure_files
    ]
    if not allowed_edit_paths and target_files:
        allowed_edit_paths = [
            rel
            for rel in target_files
            if rel not in locked_paths or rel in unlocked_paths or rel in hard_failure_files
        ]

    plan.setdefault("schema_version", "repair-plan.v1")
    plan.setdefault("source_verdict_ref", str(INSPECTION_VERDICT))
    plan.setdefault("source_cycle", cycle)
    plan.setdefault("repair_reason_summary", (verdict or {}).get("completion_assessment") or "Artifact-gated inspection failed; bounded repair is required.")
    plan["target_files"] = target_files
    plan["validation_scope_files"] = validation_scope_files
    plan["allowed_edit_paths"] = allowed_edit_paths
    plan["locked_file_paths"] = locked_paths
    plan["unlocked_file_paths"] = unlocked_paths
    plan["hard_failure_files"] = hard_failure_files
    plan["target_briq_files"] = target_briq_files
    plan.setdefault("required_actions", [])
    if not plan["required_actions"]:
        plan["required_actions"] = [
            "resolve the evidence-linked inspection and validation failures",
            "re-run validation, realization, and inspection after repair",
        ]
    plan.setdefault("repair_constraints", [])
    for constraint in [
        "no scope expansion",
        "do not modify locked files unless explicitly unlocked",
        "repair only evidence-linked failures",
    ]:
        if constraint not in plan["repair_constraints"]:
            plan["repair_constraints"].append(constraint)
    plan["same_run_repair_eligible"] = bool(target_briq_files)
    plan["continuation_strategy"] = "same_run" if target_briq_files else "linked_continuation"
    plan["next_lifecycle_transition"] = "REPAIRING" if target_briq_files else "CONTINUABLE"
    plan.setdefault("evidence_refs", [])
    for ref in [str(VALIDATION_BUNDLE), str(REALIZATION_BUNDLE), str(INSPECTION_VERDICT)]:
        if ref not in plan["evidence_refs"]:
            plan["evidence_refs"].append(ref)
    plan["sqrewdriver_repair_brief_ref"] = str(REPAIR_BRIEF_MD)
    plan["sqrewdriver_repair_brief_json_ref"] = str(REPAIR_BRIEF_JSON)
    plan["sqrewdriver_augmented_at"] = now_utc()
    _write_json(workspace_root / REPAIR_PLAN, plan)
    _write_json(workspace_root / LAST_REPAIR_PLAN, plan)
    return plan


def _restore_last_repair_plan_if_missing(workspace_root: Path) -> str | None:
    canonical = workspace_root / REPAIR_PLAN
    if canonical.exists():
        return str(canonical.resolve())
    last_plan = _load_json(workspace_root / LAST_REPAIR_PLAN)
    if not last_plan:
        return None
    restored = dict(last_plan)
    restored.setdefault("schema_version", "repair-plan.v1")
    restored["sqrewdriver_restored_after_success"] = True
    restored["sqrewdriver_restored_at"] = now_utc()
    _write_json(canonical, restored)
    return str(canonical.resolve())


def _markdown_list(values: Any, empty: str = "- None") -> str:
    items = [str(item).strip() for item in _as_list(values) if str(item).strip()]
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _markdown_json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```"


def build_repair_prompt(
    workspace_root: Path,
    *,
    cycle: int,
    inspection_verdict: dict,
    repair_plan: dict,
    validation_bundle: dict,
    realization_bundle: dict,
    reqap_text: str,
    prior_attempts: list[dict],
    config: dict,
) -> str:
    sq_cfg = ((config or {}).get("sqrewdriver") or {})
    issue_limit = int(sq_cfg.get("include_validation_issue_limit") or 50)
    completion_criteria = _load_json(workspace_root / COMPLETION_CRITERIA)
    success, failure_reasons = is_success_verdict(
        inspection_verdict,
        validation_bundle,
        completion_criteria,
        workspace_root,
    )
    summary = _failure_summary(
        failure_reasons=failure_reasons if not success else [],
        verdict=inspection_verdict,
        validation_bundle=validation_bundle,
        completion_criteria=completion_criteria,
        workspace_root=workspace_root,
        issue_limit=issue_limit,
    )
    repair_needed = inspection_verdict.get("repair_needed", inspection_verdict.get("repair_required"))
    lines = [
        "# Sqrewdriver Repair Brief",
        "",
        "QonQrete-native inspection-to-repair controller output.",
        "",
        "## Stop Gate",
        f"- Cycle: {cycle}",
        f"- Inspection verdict status: {_upper(inspection_verdict.get('status')) or 'UNKNOWN'}",
        f"- Hard gate status: {_upper(inspection_verdict.get('hard_gate_status')) or 'UNKNOWN'}",
        f"- task_completed: {bool(_truthy(inspection_verdict.get('task_completed')))}",
        f"- repair_needed / repair_required: {bool(_truthy(repair_needed))}",
        f"- inspection_integrity: {_upper(inspection_verdict.get('inspection_integrity')) or 'UNKNOWN'}",
        "",
        "## Failure Summary",
        _markdown_json_block(summary),
        "",
        "## Required Actions",
        _markdown_list(repair_plan.get("required_actions")),
        "",
        "## Target Files",
        _markdown_list(repair_plan.get("target_files")),
        "",
        "## Validation Scope Files",
        _markdown_list(repair_plan.get("validation_scope_files")),
        "",
        "## Allowed Edit Paths",
        _markdown_list(repair_plan.get("allowed_edit_paths")),
        "",
        "## Locked File Paths",
        _markdown_list(repair_plan.get("locked_file_paths")),
        "",
        "## Hard Failure Files",
        _markdown_list(repair_plan.get("hard_failure_files") or summary.get("hard_failure_files")),
        "",
        "## Issue Fingerprints",
        _markdown_json_block(repair_plan.get("issue_fingerprints") or []),
        "",
        "## Evidence References",
        _markdown_list(repair_plan.get("evidence_refs")),
        "",
        "## Unresolved Issues",
        _markdown_list(inspection_verdict.get("unresolved_issues")),
        "",
        "## Relevant Validation Bundle Issues",
        _markdown_json_block(summary.get("issues") or []),
        "",
        "## Prior Attempts",
        _markdown_json_block(prior_attempts or []),
        "",
        "## Relevant ReQap Excerpt",
        reqap_text.strip() or "No reqap excerpt was available.",
        "",
        "## Repair Instruction",
        "Do not broaden scope. Do not rewrite locked files. Fix only the evidence-linked failures unless the repair plan explicitly allows more.",
        "",
    ]
    return "\n".join(lines)


def _write_repair_brief(
    workspace_root: Path,
    *,
    cycle: int,
    prompt: str,
    verdict: dict,
    repair_plan: dict,
    failure_reasons: list[str],
    validation_bundle: dict,
    completion_criteria: dict,
) -> tuple[Path, Path]:
    md_path = workspace_root / REPAIR_BRIEF_MD
    json_path = workspace_root / REPAIR_BRIEF_JSON
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(prompt, encoding="utf-8")
    payload = {
        "schema_version": "sqrewdriver-repair-brief.v1",
        "cycle": cycle,
        "status": "REPAIR_BRIEF_READY",
        "source_verdict_ref": str(INSPECTION_VERDICT),
        "repair_plan_ref": str(REPAIR_PLAN),
        "markdown_ref": str(REPAIR_BRIEF_MD),
        "failure_reasons": failure_reasons,
        "decision_inputs": {
            "inspection_status": verdict.get("status"),
            "hard_gate_status": verdict.get("hard_gate_status"),
            "task_completed": verdict.get("task_completed"),
            "repair_needed": verdict.get("repair_needed"),
            "repair_required": verdict.get("repair_required"),
        },
        "repair_scope": {
            "target_files": repair_plan.get("target_files", []),
            "validation_scope_files": repair_plan.get("validation_scope_files", []),
            "allowed_edit_paths": repair_plan.get("allowed_edit_paths", []),
            "locked_file_paths": repair_plan.get("locked_file_paths", []),
            "hard_failure_files": repair_plan.get("hard_failure_files", []),
        },
        "failure_summary": _failure_summary(
            failure_reasons=failure_reasons,
            verdict=verdict,
            validation_bundle=validation_bundle,
            completion_criteria=completion_criteria,
            workspace_root=workspace_root,
            issue_limit=50,
        ),
        "created_at": now_utc(),
    }
    _write_json(json_path, payload)
    return md_path, json_path


def _max_repair_loops(limits: ExecutionLimits, config: dict) -> int:
    sq_cfg = ((config or {}).get("sqrewdriver") or {})
    raw = sq_cfg.get("max_repair_loops_per_build_pass")
    if raw is None:
        return int(limits.max_attempts_per_build_pass)
    try:
        return max(0, int(raw))
    except Exception:
        return int(limits.max_attempts_per_build_pass)


def _cap_reason(state: ExecutionState, limits: ExecutionLimits, config: dict, legacy_reason: str | None = None) -> str | None:
    max_repair = _max_repair_loops(limits, config)
    if total_iteration_cap_reached(state, limits):
        return f"total_iteration_cap_hit: global_iteration_index={state.global_iteration_index} max_total_iterations={limits.max_total_iterations}"
    if state.repair_pass_index >= max_repair:
        return f"repair_cap_hit: repair_pass_index={state.repair_pass_index} max_repair_loops_per_build_pass={max_repair}"
    if legacy_reason in {"same_fix_repeat_cap_hit", "repair_cap_hit", "total_iteration_cap_hit"}:
        return legacy_reason
    return None


def _sqrewdriver_enabled(config: dict) -> bool:
    sq_cfg = ((config or {}).get("sqrewdriver") or {})
    if "enabled" not in sq_cfg:
        return True
    return bool(sq_cfg.get("enabled"))


def evaluate_after_inspection(
    workspace_root: Path,
    *,
    cycle: int,
    execution_state: ExecutionState,
    limits: ExecutionLimits,
    config: dict,
) -> SqrewdriverDecision:
    if not _sqrewdriver_enabled(config):
        return SqrewdriverDecision("STOP_PARTIAL", "sqrewdriver_disabled")

    verdict = _load_json(workspace_root / INSPECTION_VERDICT)
    repair_plan = _load_json(workspace_root / REPAIR_PLAN)
    validation_bundle = _load_json(workspace_root / VALIDATION_BUNDLE)
    realization_bundle = _load_json(workspace_root / REALIZATION_BUNDLE)
    completion_criteria = _load_json(workspace_root / COMPLETION_CRITERIA)

    if not verdict:
        return SqrewdriverDecision(
            "STOP_PARTIAL",
            "inspection_verdict_missing: cannot evaluate completion or build evidence-linked repair",
            summary={"missing_artifact": str(INSPECTION_VERDICT)},
        )

    success, failure_reasons = is_success_verdict(
        verdict,
        validation_bundle,
        completion_criteria,
        workspace_root,
    )
    legacy_decision = decide_post_inspection(execution_state, limits, verdict, repair_plan)
    summary = {
        "inspection_status": verdict.get("status"),
        "hard_gate_status": verdict.get("hard_gate_status"),
        "task_completed": verdict.get("task_completed"),
        "repair_needed": verdict.get("repair_needed"),
        "repair_required": verdict.get("repair_required"),
        "failure_reasons": failure_reasons,
        "legacy_decision": {
            "action": legacy_decision.action,
            "reason": legacy_decision.reason,
        },
    }

    if success:
        restored_plan_path = _restore_last_repair_plan_if_missing(workspace_root)
        if restored_plan_path:
            summary["restored_repair_plan_path"] = restored_plan_path
        return SqrewdriverDecision(
            "STOP",
            "hard_gate_success",
            repair_plan_path=restored_plan_path,
            summary=summary,
        )

    cap = _cap_reason(execution_state, limits, config, legacy_decision.reason)
    if cap:
        return SqrewdriverDecision(
            "STOP_PARTIAL",
            f"{cap}; current_verdict={verdict.get('status', 'UNKNOWN')} hard_gate={verdict.get('hard_gate_status', 'UNKNOWN')}",
            summary=summary,
        )

    issue_limit = int((((config or {}).get("sqrewdriver") or {}).get("include_validation_issue_limit")) or 50)
    failure_summary = _failure_summary(
        failure_reasons=failure_reasons,
        verdict=verdict,
        validation_bundle=validation_bundle,
        completion_criteria=completion_criteria,
        workspace_root=workspace_root,
        issue_limit=issue_limit,
    )
    repair_plan = _ensure_repair_plan(
        workspace_root,
        cycle=cycle,
        verdict=verdict,
        repair_plan=repair_plan,
        validation_bundle=validation_bundle,
        completion_criteria=completion_criteria,
        failure_summary=failure_summary,
    )

    if not repair_plan.get("same_run_repair_eligible"):
        return SqrewdriverDecision(
            "STOP_PARTIAL",
            f"repair_plan_has_no_same_run_targets; current_verdict={verdict.get('status', 'UNKNOWN')} hard_gate={verdict.get('hard_gate_status', 'UNKNOWN')}",
            repair_plan_path=str((workspace_root / REPAIR_PLAN).resolve()),
            summary=summary,
        )

    prompt = build_repair_prompt(
        workspace_root,
        cycle=cycle,
        inspection_verdict=verdict,
        repair_plan=repair_plan,
        validation_bundle=validation_bundle,
        realization_bundle=realization_bundle,
        reqap_text=_read_reqap_excerpt(workspace_root, cycle, config),
        prior_attempts=_prior_attempts(repair_plan, config),
        config=config,
    )

    if bool((((config or {}).get("sqrewdriver") or {}).get("write_repair_brief", True))):
        md_path, _ = _write_repair_brief(
            workspace_root,
            cycle=cycle,
            prompt=prompt,
            verdict=verdict,
            repair_plan=repair_plan,
            failure_reasons=failure_reasons,
            validation_bundle=validation_bundle,
            completion_criteria=completion_criteria,
        )
        repair_prompt_path = str(md_path.resolve())
    else:
        repair_prompt_path = None

    return SqrewdriverDecision(
        "REPAIR",
        "artifact_gates_failed_repair_brief_ready",
        repair_prompt_path=repair_prompt_path,
        repair_plan_path=str((workspace_root / REPAIR_PLAN).resolve()),
        summary=summary,
    )
