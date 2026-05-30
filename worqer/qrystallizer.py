#!/usr/bin/env python3
"""Canonical front-door intake for QonQrete Phase 1 demo readiness."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "task-spec.v1"
CLARIFICATION_SCHEMA_VERSION = "clarification-log.v1"
CLARIFICATION_RESPONSE_SCHEMA_VERSION = "clarification-response.v1"
DEFAULT_QRYSTALLIZER_PROVIDER = "venice"
DEFAULT_QRYSTALLIZER_MODEL = "deepseek-v3.2"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
except Exception:
    lib_ai = None

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


def canonical_run_id(workspace_root: Path) -> str:
    for env_key in ("QONQ_RUN_ID", "QONQ_RUN_NAME", "QONSTRUCTION_NAME"):
        raw = str(os.environ.get(env_key, "")).strip()
        if raw:
            return Path(raw).name
    name = str(workspace_root.name).strip()
    return name or "run-unknown"


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_runtime_config(workspace_root: Path) -> dict:
    config_path = workspace_root / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def resolve_qrystallizer_ai_binding(config: dict) -> dict:
    provider = DEFAULT_QRYSTALLIZER_PROVIDER
    model = DEFAULT_QRYSTALLIZER_MODEL
    capabilities = {}
    source = "defaults"
    if isinstance(config, dict):
        source = "runtime_config"
        if lib_ai is not None and hasattr(lib_ai, "get_agent_ai_params"):
            provider, model = lib_ai.get_agent_ai_params(
                config,
                "qrystallizer",
                DEFAULT_QRYSTALLIZER_PROVIDER,
                DEFAULT_QRYSTALLIZER_MODEL,
            )
            if hasattr(lib_ai, "resolve_model_capabilities"):
                try:
                    cap = lib_ai.resolve_model_capabilities(
                        provider,
                        model,
                        config=config,
                        agent_name="qrystallizer",
                    )
                    capabilities = {
                        "total_context_window": int(getattr(cap, "total_context_window", 0) or 0),
                        "safe_input_tokens": int(getattr(cap, "safe_input_tokens", 0) or 0),
                        "safe_output_tokens": int(getattr(cap, "safe_output_tokens", 0) or 0),
                    }
                except Exception:
                    capabilities = {}
        else:
            agent_cfg = ((config.get("agents", {}) or {}).get("qrystallizer", {}) or {})
            provider = str(agent_cfg.get("provider", provider) or provider).strip() or provider
            model = str(agent_cfg.get("model", model) or model).strip() or model
    return {
        "agent": "qrystallizer",
        "provider": provider,
        "model": model,
        "source": source,
        "capabilities": capabilities,
    }


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


def detect_blocking_gaps(raw_task_text: str, clarified_task_text: str, goal: str, *, answers_supplied: bool) -> list[dict]:
    gaps: list[dict] = []
    stripped = clarified_task_text.strip()
    
    # Gap detection logic
    if len(stripped) < 40:
        gaps.append(
            {
                "gap_id": "gap-task-too-thin",
                "impact": "high",
                "reason": "Task is too short to clarify reliable build intent.",
                "question": "What concrete change should QonQrete implement in the repository?",
            }
        )

    if not any(re.search(rf"\b{verb}\b", clarified_task_text, re.IGNORECASE) for verb in ACTION_VERBS):
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
        if pattern.search(raw_task_text) and not answers_supplied:
            gaps.append(
                {
                    "gap_id": "gap-vague-placeholder",
                    "impact": "high",
                    "reason": reason,
                    "question": "Which unresolved placeholder should be treated as the real requirement?",
                }
            )

    # Semantic deduplication: if we have "too thin" or "no goal", they often cover "missing action".
    # We want distinct high-impact questions.
    deduped: list[dict] = []
    seen_questions: set[str] = set()
    seen_ids: set[str] = set()
    
    for gap in gaps:
        q_text = gap["question"].strip().lower()
        g_id = gap["gap_id"]
        if q_text in seen_questions or g_id in seen_ids:
            continue
        
        # Priority: if we already have a 'task-too-thin' or 'vague-placeholder', 
        # it usually makes 'missing-action' and 'no-goal' redundant for the first round.
        if (g_id == "gap-missing-action" or g_id == "gap-no-goal") and ("gap-task-too-thin" in seen_ids or "gap-vague-placeholder" in seen_ids):
            continue

        seen_questions.add(q_text)
        seen_ids.add(g_id)
        deduped.append(gap)
        
    deduped.sort(key=lambda item: (0 if "placeholder" in str(item.get("reason", "")).lower() else 1))
    return deduped


def _synthesize_clarified_goal(raw_goal: str, answers: list[dict]) -> tuple[str, str, str]:
    """Derive a stable, high-quality goal from clarification answers.
    Returns: (goal, provenance, status)
    """
    if not answers:
        return raw_goal, "raw_task", "unresolved"
    
    # If we have answers, the first substantial answer is often the best goal.
    valid_answers = [a["answer"].strip() for a in answers if len(a.get("answer", "")) > 10]
    if not valid_answers:
        return raw_goal, "raw_task", "unresolved"
        
    # Pick the most descriptive answer (often the first one for vague tasks)
    best_candidate = valid_answers[0]
    
    # Clean up common prefixes
    best_candidate = re.sub(r"^(the goal is to|implement|create|add|fix)\s+", "", best_candidate, flags=re.IGNORECASE)
    
    # Capitalize first letter while preserving the rest (to keep acronyms like CSV)
    if best_candidate:
        best_candidate = best_candidate[0].upper() + best_candidate[1:]
    
    return best_candidate[:160], "clarification_answers", "resolved"


def _build_clarified_task_body(raw_task_text: str, answers: list[dict]) -> str:
    """Construct a canonical clarified task block for downstream consumption."""
    if not answers:
        return raw_task_text
        
    lines = ["# Clarified Task Requirement", ""]
    lines.append("## Clarification Answers")
    for answer in answers:
        q = answer.get("question") or answer.get("question_id") or "Question"
        lines.append(f"### {q}")
        lines.append(answer.get("answer", ""))
        lines.append("")
        
    lines.append("---")
    lines.append("## Original Raw Task Reference")
    lines.append(raw_task_text.strip())
    
    return "\n".join(lines)


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


def load_clarification_response(path: Path, run_id: str) -> dict:
    payload = load_json(path)
    if not payload:
        return {
            "supplied": False,
            "response_ref": None,
            "round": 0,
            "source": None,
            "answers": [],
            "warnings": [],
        }
    warnings: list[str] = []
    if payload.get("schema_version") != CLARIFICATION_RESPONSE_SCHEMA_VERSION:
        warnings.append("Clarification response schema version is not recognized; parsing best effort.")
    payload_run_id = payload.get("run_id")
    if payload_run_id and payload_run_id != run_id:
        warnings.append("Clarification response run_id does not match current run; parsing best effort.")
    answers: list[dict] = []
    for item in payload.get("answers", []):
        if not isinstance(item, dict):
            continue
        answer_text = str(item.get("answer", "")).strip()
        if not answer_text:
            continue
        answers.append(
            {
                "question_id": str(item.get("question_id", "")).strip() or None,
                "question": str(item.get("question", "")).strip() or None,
                "answer": answer_text,
            }
        )
    return {
        "supplied": bool(answers),
        "response_ref": str(path),
        "round": int(payload.get("round", 0) or 0),
        "source": payload.get("source"),
        "answers": answers,
        "warnings": warnings,
    }


def build_task_spec(
    run_id: str,
    input_path: Path,
    task_text: str,
    clarification_response: dict | None = None,
    ai_binding: dict | None = None,
) -> tuple[dict, dict]:
    clarification_response = clarification_response or {
        "supplied": False,
        "response_ref": None,
        "round": 0,
        "source": None,
        "answers": [],
        "warnings": [],
    }
    
    answers = clarification_response.get("answers", [])
    answers_supplied = bool(clarification_response.get("supplied"))
    
    # Internal goal extraction from text (legacy/fallback)
    raw_goal = extract_goal(task_text)
    
    # Primary goal synthesis
    if answers_supplied:
        goal, goal_source, clarified_goal_status = _synthesize_clarified_goal(raw_goal, answers)
    else:
        goal = raw_goal
        goal_source = "raw_task"
        clarified_goal_status = "unresolved"
        
    clarified_task_body = _build_clarified_task_body(task_text, answers)
    
    constraints = extract_constraints(clarified_task_body)
    assumptions = capture_assumptions(clarified_task_body)
    
    blocking_gaps = detect_blocking_gaps(
        task_text,
        clarified_task_body,
        goal,
        answers_supplied=answers_supplied,
    )
    
    non_blocking_unknowns = capture_non_blocking_unknowns(clarified_task_body)
    ready = not blocking_gaps
    
    clarification_questions = [
        {
            "question_id": f"q-{index + 1}",
            "impact": gap["impact"],
            "reason": gap["reason"],
            "default_assumption": gap.get("suggested_answer", ""),
            "question": gap["question"],
        }
        for index, gap in enumerate(blocking_gaps)
    ]

    summary = (
        "READY: task clarified with explicit assumptions and bounded unknowns."
        if ready
        else f"NOT_READY: {len(blocking_gaps)} high-impact clarification blocker(s) remain."
    )
    effective_ai_binding = {
        "agent": "qrystallizer",
        "provider": str((ai_binding or {}).get("provider") or DEFAULT_QRYSTALLIZER_PROVIDER),
        "model": str((ai_binding or {}).get("model") or DEFAULT_QRYSTALLIZER_MODEL),
        "source": str((ai_binding or {}).get("source") or "defaults"),
    }
    caps = (ai_binding or {}).get("capabilities")
    if isinstance(caps, dict) and caps:
        effective_ai_binding["capabilities"] = caps

    task_spec = {
        "schema_version": SCHEMA_VERSION,
        "task_spec_id": f"{run_id}-task-spec",
        "run_id": run_id,
        "status": "READY" if ready else "NOT_READY",
        "goal": goal,
        "goal_source": goal_source,
        "clarified_goal_status": clarified_goal_status,
        "clarified_goal": goal if goal_source == "clarification_answers" else None,
        "clarification_answers": answers,
        "clarified_task_body": clarified_task_body,
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
        "clarification_answers_supplied": bool(clarification_response.get("supplied")),
        "clarification_round": int(clarification_response.get("round", 0) or 0),
        "ready_after_clarification": bool(ready and clarification_response.get("supplied")),
        "still_blocked_after_clarification": bool((not ready) and clarification_response.get("supplied")),
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "clarification_summary": summary,
        "ai_binding": effective_ai_binding,
    }
    if clarification_response.get("response_ref"):
        task_spec["clarification_response_ref"] = str(clarification_response["response_ref"])
    if clarification_response.get("source"):
        task_spec["clarification_response_source"] = clarification_response["source"]

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
        "clarification_answers_supplied": bool(clarification_response.get("supplied")),
        "clarification_round": int(clarification_response.get("round", 0) or 0),
        "answers": clarification_response.get("answers", []),
        "ready_after_clarification": bool(ready and clarification_response.get("supplied")),
        "still_blocked_after_clarification": bool((not ready) and clarification_response.get("supplied")),
        "assumptions": assumptions,
        "blocking_gaps": blocking_gaps,
        "non_blocking_unknowns": non_blocking_unknowns,
        "ai_binding": effective_ai_binding,
    }
    if clarification_response.get("response_ref"):
        clarification_log["clarification_response_ref"] = str(clarification_response["response_ref"])
    if clarification_response.get("source"):
        clarification_log["clarification_response_source"] = clarification_response["source"]
    if clarification_response.get("warnings"):
        clarification_log["clarification_response_warnings"] = clarification_response["warnings"]

    return task_spec, clarification_log


def render_summary(task_spec: dict, clarification_log: dict, raw_task_path: Path) -> str:
    lines = [
        "# Qrystallizer Intake Summary",
        "",
        f"- Status: {task_spec['status']}",
        f"- Goal: {task_spec['goal']}",
        f"- Raw Task: `{raw_task_path}`",
        f"- AI Binding: `{task_spec.get('ai_binding', {}).get('provider', DEFAULT_QRYSTALLIZER_PROVIDER)}` / `{task_spec.get('ai_binding', {}).get('model', DEFAULT_QRYSTALLIZER_MODEL)}`",
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
    if clarification_log.get("answers"):
        lines.extend(["", "## Clarification Answers"])
        for item in clarification_log["answers"]:
            question_id = item.get("question_id") or "unlabeled"
            lines.append(f"- {question_id}: {item.get('answer', '')}")
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
    run_id = canonical_run_id(workspace_root)

    print("[Qrystallizer] --- Clarifying task ---", flush=True)
    raw_task = load_text(input_path)
    runtime_config = load_runtime_config(workspace_root)
    ai_binding = resolve_qrystallizer_ai_binding(runtime_config)
    response_path = workspace_root / "task" / "clarification-response.v1.json"
    clarification_response = load_clarification_response(response_path, run_id)
    # Auto-enhancement: use AI to improve task quality before gap detection.
    # Skip when QONQ_DONT_ENHANCE_TASQ=1 (--dont-enhance-tasq / -E flag).
    dont_enhance = os.environ.get("QONQ_DONT_ENHANCE_TASQ", "").strip() == "1"
    if not dont_enhance and len(raw_task.strip()) < 2000:
        from . import lib_ai as _lib_ai
        try:
            enhancement_prompt = (
                "Enhance the following task description for an AI code generation system. "
                "Add missing details, clarify ambiguous requirements, and structure the task "
                "into clear sections (Goal, Context, Acceptance Criteria, Notes). "
                "Preserve ALL original requirements. Do NOT add new requirements.\n\n"
                f"Original task:\n{raw_task}"
            )
            enhanced = _lib_ai.ai_completion(
                provider=ai_binding["provider"],
                model=ai_binding["model"],
                prompt=enhancement_prompt,
                max_tokens=2000,
                task_type="task_enhancement",
            )
            if enhanced and len(enhanced.strip()) > len(raw_task.strip()) * 0.5:
                raw_task = enhanced.strip()
                print("[Qrystallizer] Task enhanced via AI.", flush=True)
        except Exception:
            pass  # Enhancement is best-effort; fall through to original task

    print("[Qrystallizer] Qrystallizer: checking gaps", flush=True)
    print(
        f"[Qrystallizer] AI binding provider={ai_binding['provider']} model={ai_binding['model']}",
        flush=True,
    )
    task_spec, clarification_log = build_task_spec(
        run_id,
        input_path,
        raw_task,
        clarification_response=clarification_response,
        ai_binding=ai_binding,
    )

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
    print(f"[Qrystallizer] Clarification answers supplied: {len(clarification_response.get('answers', []))}", flush=True)
    print(f"[Qrystallizer] Assumptions logged: {len(task_spec['assumptions'])}", flush=True)
    print(f"[Qrystallizer] Blocking gaps: {len(task_spec['blocking_gaps'])}", flush=True)
    print("[Qrystallizer] Wrote Task Spec", flush=True)
    print(f"[Qrystallizer] Wrote Task Spec: {task_spec_path}", flush=True)
    print(f"[Qrystallizer] Wrote Clarification Log: {clarification_log_path}", flush=True)


if __name__ == "__main__":
    main()
