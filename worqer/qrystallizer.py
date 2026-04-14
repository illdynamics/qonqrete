#!/usr/bin/env python3
"""Canonical front-door intake for QonQrete Phase 1 demo readiness."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "task-spec.v1"
CLARIFICATION_SCHEMA_VERSION = "clarification-log.v1"

ACTION_VERBS = {
    "add",
    "adjust",
    "build",
    "change",
    "clean",
    "create",
    "debug",
    "document",
    "enforce",
    "fix",
    "implement",
    "improve",
    "introduce",
    "make",
    "migrate",
    "move",
    "refactor",
    "replace",
    "separate",
    "stabilize",
    "tighten",
    "update",
    "wire",
}

HIGH_IMPACT_UNKNOWN_PATTERNS = [
    (re.compile(r"\b(?:tbd|todo|placeholder|decide later)\b", re.IGNORECASE), "Task contains unresolved placeholders that define core build intent."),
    (re.compile(r"\?\?\?"), "Task contains unresolved placeholder markers."),
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_constraint(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip(" -*\t"))
    return cleaned.rstrip(".")


def extract_goal(task_text: str) -> str:
    for line in task_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
            if stripped:
                return stripped
        if len(stripped) > 20:
            return stripped
    return task_text.strip()[:160]


def extract_constraints(task_text: str) -> list[str]:
    constraints: list[str] = []
    in_constraint_section = False
    current_depth = 0
    header_pattern = re.compile(r"^(#+)\s+(.*)$")
    for line in task_text.splitlines():
        header_match = header_pattern.match(line)
        if header_match:
            current_depth = len(header_match.group(1))
            title = header_match.group(2).strip().lower()
            in_constraint_section = any(token in title for token in ("rule", "constraint", "must", "do not", "non-negotiable"))
            continue
        if in_constraint_section:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ")):
                constraints.append(normalize_constraint(stripped))
                continue
            if re.match(r"^\d+\.\s+", stripped):
                constraints.append(normalize_constraint(re.sub(r"^\d+\.\s+", "", stripped)))

    imperative_pattern = re.compile(r"^\s*[-*]\s+.*\b(?:must|never|always|do not|required|forbidden)\b.*$", re.IGNORECASE | re.MULTILINE)
    for match in imperative_pattern.findall(task_text):
        normalized = normalize_constraint(match)
        if normalized not in constraints:
            constraints.append(normalized)

    return constraints[:12]


def detect_blocking_gaps(task_text: str, goal: str) -> list[dict]:
    gaps: list[dict] = []
    stripped = task_text.strip()
    if len(stripped) < 40:
        gaps.append(
            {
                "gap_id": "gap-task-too-thin",
                "impact": "high",
                "reason": "Task is too short to clarify reliable build intent.",
                "question": "What concrete change should QonQrete implement in the repository?",
            }
        )

    if not any(re.search(rf"\b{verb}\b", task_text, re.IGNORECASE) for verb in ACTION_VERBS):
        gaps.append(
            {
                "gap_id": "gap-missing-action",
                "impact": "high",
                "reason": "Task does not state a concrete implementation action.",
                "question": "What specific implementation outcome is required?",
            }
        )

    if len(goal.strip()) < 12:
        gaps.append(
            {
                "gap_id": "gap-no-goal",
                "impact": "high",
                "reason": "No stable implementation goal could be extracted from the task.",
                "question": "What is the primary goal of this run?",
            }
        )

    for pattern, reason in HIGH_IMPACT_UNKNOWN_PATTERNS:
        if pattern.search(task_text):
            gaps.append(
                {
                    "gap_id": f"gap-pattern-{len(gaps) + 1}",
                    "impact": "high",
                    "reason": reason,
                    "question": "Which unresolved placeholder should be treated as the real requirement?",
                }
            )

    deduped: list[dict] = []
    seen: set[str] = set()
    for gap in gaps:
        if gap["reason"] in seen:
            continue
        seen.add(gap["reason"])
        deduped.append(gap)
    return deduped[:3]


def capture_assumptions(task_text: str) -> list[dict]:
    assumptions = [
        {
            "assumption_id": "asm-preserve-existing",
            "statement": "Preserve existing repository behavior unless the task explicitly requires a behavior change.",
            "basis": "Demo-safe default when requirements do not request broad redesign.",
            "source": "system-default",
        },
        {
            "assumption_id": "asm-follow-repo-patterns",
            "statement": "Prefer existing repository patterns and naming over introducing new architecture during intake.",
            "basis": "Repo-local consistency is safer than speculative redesign in this phase.",
            "source": "system-default",
        },
    ]

    if not re.search(r"\b(?:dependency|dependencies|package|library|sdk|framework)\b", task_text, re.IGNORECASE):
        assumptions.append(
            {
                "assumption_id": "asm-no-new-deps",
                "statement": "Avoid introducing new external dependencies unless later stages find them explicitly required by the task.",
                "basis": "The task does not request dependency expansion.",
                "source": "system-default",
            }
        )

    return assumptions[:4]


def capture_non_blocking_unknowns(task_text: str) -> list[str]:
    unknowns: list[str] = []
    if not re.search(r"\b(?:test|validation|verify|py_compile|lint)\b", task_text, re.IGNORECASE):
        unknowns.append("Validation depth is not specified in the task and will follow repository/runtime defaults.")
    if not re.search(r"\b(?:ui|cli|api|backend|frontend|docs?)\b", task_text, re.IGNORECASE):
        unknowns.append("The exact affected surface area is not fully named and will be derived from repository context.")
    return unknowns[:3]


def build_task_spec(run_id: str, input_path: Path, task_text: str) -> tuple[dict, dict]:
    goal = extract_goal(task_text)
    constraints = extract_constraints(task_text)
    assumptions = capture_assumptions(task_text)
    blocking_gaps = detect_blocking_gaps(task_text, goal)
    non_blocking_unknowns = capture_non_blocking_unknowns(task_text)
    ready = not blocking_gaps
    clarification_questions = [
        {
            "question_id": f"q-{index + 1}",
            "impact": gap["impact"],
            "reason": gap["reason"],
            "question": gap["question"],
        }
        for index, gap in enumerate(blocking_gaps)
    ]

    summary = (
        "READY: task clarified with explicit assumptions and bounded unknowns."
        if ready
        else f"NOT_READY: {len(blocking_gaps)} high-impact clarification blocker(s) remain."
    )

    task_spec = {
        "schema_version": SCHEMA_VERSION,
        "task_spec_id": f"{run_id}-task-spec",
        "run_id": run_id,
        "status": "READY" if ready else "NOT_READY",
        "goal": goal,
        "inputs": [
            {
                "name": "raw_task",
                "type": "markdown",
                "source_ref": str(input_path),
            }
        ],
        "constraints": constraints
        + [
            "Only clarification may ask the user questions.",
            "No user questioning is allowed after readiness is accepted.",
        ],
        "assumptions": assumptions,
        "blocking_gaps": blocking_gaps,
        "non_blocking_unknowns": non_blocking_unknowns,
        "ready": ready,
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "clarification_summary": summary,
    }

    clarification_log = {
        "schema_version": CLARIFICATION_SCHEMA_VERSION,
        "run_id": run_id,
        "task_spec_id": task_spec["task_spec_id"],
        "generated_at": now_utc(),
        "readiness_status": task_spec["status"],
        "question_policy": {
            "bounded_questions_only": True,
            "max_high_impact_questions": 3,
            "no_mid_run_questioning_after_ready": True,
        },
        "questions": clarification_questions,
        "assumptions": assumptions,
        "blocking_gaps": blocking_gaps,
        "non_blocking_unknowns": non_blocking_unknowns,
    }

    return task_spec, clarification_log


def render_summary(task_spec: dict, clarification_log: dict, raw_task_path: Path) -> str:
    lines = [
        "# Qrystallizer Intake Summary",
        "",
        f"- Status: {task_spec['status']}",
        f"- Goal: {task_spec['goal']}",
        f"- Raw Task: `{raw_task_path}`",
        "",
        "## Constraints",
    ]
    for item in task_spec["constraints"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Assumptions"])
    for item in clarification_log["assumptions"]:
        lines.append(f"- {item['statement']} ({item['basis']})")
    if clarification_log["blocking_gaps"]:
        lines.extend(["", "## Blocking Gaps"])
        for item in clarification_log["blocking_gaps"]:
            lines.append(f"- {item['reason']}")
    if clarification_log["questions"]:
        lines.extend(["", "## Clarification Questions"])
        for item in clarification_log["questions"]:
            lines.append(f"- {item['question']}")
    if clarification_log["non_blocking_unknowns"]:
        lines.extend(["", "## Non-Blocking Unknowns"])
        for item in clarification_log["non_blocking_unknowns"]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("[Qrystallizer] Usage: qrystallizer.py <tasq_path> [compat_output_path]", flush=True)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path
    if not input_path.exists():
        print(f"[Qrystallizer] ERROR: task input not found: {input_path}", flush=True)
        sys.exit(1)

    workspace_root = Path(os.environ.get("QONQ_WORKSPACE", input_path.resolve().parents[1] if input_path.parent.name == "tasq.d" else input_path.parent))
    run_id = os.environ.get("QONQ_LEGACY_QAGE_ID") or workspace_root.name

    raw_task = load_text(input_path)
    task_spec, clarification_log = build_task_spec(run_id, input_path, raw_task)

    task_dir = workspace_root / "task"
    task_spec_path = task_dir / "task-spec.v1.json"
    clarification_log_path = task_dir / "clarification-log.v1.json"
    summary_path = task_dir / "clarification-summary.md"

    write_json(task_spec_path, task_spec)
    write_json(clarification_log_path, clarification_log)
    write_text(summary_path, render_summary(task_spec, clarification_log, input_path))

    if output_path != input_path and not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(input_path, output_path)

    print(f"[Qrystallizer] Intake authority active for: {input_path.name}", flush=True)
    print(f"[Qrystallizer] Goal: {task_spec['goal']}", flush=True)
    print(f"[Qrystallizer] Readiness: {task_spec['status']}", flush=True)
    print(f"[Qrystallizer] Assumptions logged: {len(task_spec['assumptions'])}", flush=True)
    print(f"[Qrystallizer] Blocking gaps: {len(task_spec['blocking_gaps'])}", flush=True)
    print(f"[Qrystallizer] Wrote Task Spec: {task_spec_path}", flush=True)
    print(f"[Qrystallizer] Wrote Clarification Log: {clarification_log_path}", flush=True)


if __name__ == "__main__":
    main()
