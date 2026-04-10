#!/usr/bin/env python3
"""Canonical pre-plan Guard stage for Phase 1 demo readiness."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_constraint(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(".")


def evaluate_guard(task_spec: dict) -> dict:
    goal = task_spec.get("goal", "")
    constraints = [normalize_constraint(item) for item in task_spec.get("constraints", []) if str(item).strip()]
    assumptions = task_spec.get("assumptions", [])
    violations: list[dict] = []
    warnings: list[dict] = []

    if not task_spec.get("ready"):
        violations.append(
            {
                "rule_id": "TASK_SPEC_NOT_READY",
                "severity": "error",
                "message": "Task Spec is NOT_READY. Planning is blocked until high-impact clarification blockers are resolved.",
            }
        )

    combined_text = " ".join([goal] + constraints)
    prohibited_fail_patterns = [
        (r"\brm\s+-rf\b", "Destructive shell deletion is not allowed at intake."),
        (r"\bexfiltrat", "Tasks requesting secret or data exfiltration are blocked."),
    ]
    review_patterns = [
        (r"\bdeploy(?:ment)?\b", "Task mentions deployment; runtime safety constraints remain in force."),
        (r"\bproduction\b", "Task mentions production scope; validate environment assumptions downstream."),
        (r"\bsecret|credential|token\b", "Task may touch secrets or credentials; preserve existing secret handling."),
    ]

    for pattern, message in prohibited_fail_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            violations.append({"rule_id": "PROHIBITED_SCOPE", "severity": "error", "message": message})

    for pattern, message in review_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            warnings.append({"rule_id": "REVIEW_SCOPE", "severity": "warning", "message": message})

    if assumptions:
        warnings.append(
            {
                "rule_id": "ASSUMPTION_CARRY_FORWARD",
                "severity": "warning",
                "message": "Planning must honor logged assumptions and must not replace them with hidden reinterpretation.",
            }
        )

    effective_constraints = []
    for item in constraints:
        if item not in effective_constraints:
            effective_constraints.append(item)

    for item in [
        "Execution must remain within the clarified goal and declared constraints.",
        "Only clarification may ask user questions; no mid-run questioning is allowed after readiness acceptance.",
        "If ambiguity remains after start, use logged assumptions or fail explicitly.",
        "Do not silently redesign architecture or completion criteria during planning or build.",
    ]:
        normalized = normalize_constraint(item)
        if normalized not in effective_constraints:
            effective_constraints.append(normalized)

    status = "FAIL" if violations else ("REVIEW" if warnings else "PASS")
    return {
        "status": status,
        "violations": violations,
        "warnings": warnings,
        "effective_constraints": effective_constraints,
        "policy_refs": [
            "docs/02-project-hard-ruleset.md",
            "docs/03-project-migration-compound.md",
            "docs/04-project-qonscience-connections.md",
        ],
        "next_stage": "PLANNING" if status in {"PASS", "REVIEW"} else "STOP",
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# Guard Result",
        "",
        f"**Status:** {result['status']}",
        f"**Next Stage:** {result['next_stage']}",
        "",
        "## Effective Constraints",
    ]
    for item in result["effective_constraints"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Violations"])
    if result["violations"]:
        for item in result["violations"]:
            lines.append(f"- {item['rule_id']}: {item['message']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings"])
    if result["warnings"]:
        for item in result["warnings"]:
            lines.append(f"- {item['rule_id']}: {item['message']}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 3:
        print("[Guard] Usage: guard.py <task_spec_path> <guard_result_path>", flush=True)
        sys.exit(1)

    task_spec_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    if not task_spec_path.exists():
        print(f"[Guard] ERROR: Task Spec not found: {task_spec_path}", flush=True)
        sys.exit(1)

    workspace_root = Path(os.environ.get("QONQ_WORKSPACE", output_path.resolve().parents[1] if output_path.parent.name == "guard" else output_path.parent))
    run_id = os.environ.get("QONQ_LEGACY_QAGE_ID") or workspace_root.name

    task_spec = load_json(task_spec_path)
    result = evaluate_guard(task_spec)
    payload = {
        "schema_version": "guard-result.v1",
        "guard_result_id": f"{run_id}-guard-result",
        "run_id": run_id,
        "generated_at": now_utc(),
        **result,
    }

    markdown_path = output_path.with_suffix(".md")
    write_json(output_path, payload)
    write_text(markdown_path, render_markdown(payload))

    print(f"[Guard] Status: {payload['status']}", flush=True)
    print(f"[Guard] Violations: {len(payload['violations'])}", flush=True)
    print(f"[Guard] Warnings: {len(payload['warnings'])}", flush=True)
    print(f"[Guard] Wrote Guard Result: {output_path}", flush=True)

    if payload["status"] == "FAIL":
        sys.exit(2)


if __name__ == "__main__":
    main()
