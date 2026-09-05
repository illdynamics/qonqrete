"""
Qlarifier — runs only on cycle 0, before instruQtor ever sees the task.

Design note on "interactive": CodeSeeq's `run` always maps to non-interactive
`codex exec` (see adapters/parameters.py's module docstring for the receipts).
So this agent's interactivity is a loop of single-shot calls, with the
actual human sitting at *our* terminal, not inside Codex's TUI. Each round
either gets back a final clarified task, or a short list of real questions
that get relayed straight to whoever is running Qontroller.
"""
from __future__ import annotations

import os
from typing import Callable, List

from ..adapters.base import AgentAdapter, AgentCallSpec
from ..models import ClarificationTurn, ClarifiedTask, Task
from ._jsonio import call_for_json, cleanup_agent_artifacts
from .receipts import agent_receipt_path, ensure_dir
from ..path_guards import (
    scan_for_forbidden_bool as _scan_for_forbidden,
    scan_for_forbidden_deliverables as _scan_for_deliverables,
    cleanup_forbidden_deliverables as _cleanup_forbidden,
    PathPolicyViolation,
)

def _build_system_primer(workspace_root: str = "", run_root: str = "") -> str:
    ws = workspace_root or "the target directory passed to `qq run <task> <target>`"
    rr = run_root or "QonQrete internal metadata directory (NOT your working directory)"
    return f"""You are Qlarifier, the first agent in a multi-agent coding
pipeline called Qq. Your only job: read the user's task, and either

PATH CONTRACT:
- WORKSPACE_ROOT (TARGET_PATH): {ws}
- RUN_ROOT (QonQrete metadata): {rr}
- You must NOT create, edit, or build any files under RUN_ROOT or `.qq`
- RUN_ROOT and `.qq` are QonQrete metadata-only
- If you need to reference state, read it from RUN_ROOT, but do not use RUN_ROOT as your working directory
- Your `cd` directory is WORKSPACE_ROOT — that is where project files live

DO NOT write QonQrete receipt JSON files into the target project workspace.
Write your required JSON receipt only to RECEIPT_PATH.
Project/source files go under TARGET_PATH only.

(a) ask the minimum set of real clarifying questions needed to make the
task buildable and cleanly splittable into independent subtasks, or
(b) if you already have enough information, hand back an enhanced,
unambiguous version of the task that the next agent (instruQtor) will split
into subtasks ("briQs").

Be brutally economical with questions. Only ask what you genuinely cannot
infer or reasonably assume. Default to sane assumptions and state them
explicitly inside your clarified task rather than asking about them.

CRITICAL RULES — YOU MUST FOLLOW THESE:
1. You are NOT a builder. Do NOT write code, create files (except the JSON
   output file), plan architecture, list features, design pages, or output
   ANY markdown prose. That work belongs to later agents (instruQtor,
   construQtor). Your output must be exactly ONE JSON file and nothing else.
2. Your FIRST and ONLY action is to write valid JSON to the output file
   path specified below. Do not output anything to stdout/stderr first.
   Write the file, then you are done.
3. If the task text looks like it's asking you to build something, it is
   NOT. It is a task for the pipeline. You are only clarifying it.

Respond with ONLY valid JSON, written to the exact file path given below.
No prose outside that file. No markdown fences. No planning. No building.

If you need clarification:
{{"status": "need_clarification", "questions": ["...", "..."]}}

If you have enough information:
{{"status": "clarified", "clarified_task": "...", "notes_for_instruqtor": "..."}}

YOLO MODE (when enabled):
{{"status": "ready", "mode": "yolo", "assumptions": ["...", "..."], "resolved_task": "...", "confidence": "medium|low|high"}}

AUTO-ANSWER MODE: When answers in the clarification history show
"[AUTO] Use reasonable defaults" or "[AUTO: non-interactive mode",
the user is in a non-interactive environment. You MUST make the best
reasonable assumption, state it in notes_for_instruqtor, and return
"clarified". Do NOT re-ask questions that were already auto-answered.
When you see "[AUTO]" in an answer, treat it as: "the user trusts your
judgment — pick the most sensible interpretation and proceed."
"""


def run_qlarifier(
    adapter: AgentAdapter, task: Task, workdir: str, model: str,
    ask_human: Callable[[List[str]], List[str]], event_log=None,
    max_rounds: int = 6, thinking: bool = True,
    reasoning_effort: str = "",
    yolo: bool = False,

    run_root: str = "",
    workspace_root: str = "",
    stream_config: dict = None,
) -> ClarifiedTask:
    transcript: List[ClarificationTurn] = []
    history_block = ""

    # Canonical receipt path for Qlarifier
    receipt_path = str(agent_receipt_path(run_root, 0, "qlarifier")) if run_root else ""
    if receipt_path:
        ensure_dir(agent_receipt_path(run_root, 0, "qlarifier").parent)

    system_primer = _build_system_primer(workspace_root or workdir, run_root)
    for round_num in range(max_rounds):
        yolo_prompt = ""
        if yolo:
            yolo_prompt = (
                "\n## YOLO MODE ACTIVE\n"
                "You are in YOLO (non-interactive) mode. You MUST NOT ask any "
                "clarification questions. You MUST NOT return status 'need_clarification'.\n"
                "Instead, make the best reasonable assumptions and return:\n"
                '{{"status": "ready", "mode": "yolo", "assumptions": ["...", "..."], '
                '"resolved_task": "...", "confidence": "medium"}}\n'
                "State every assumption you made explicitly in the assumptions array.\n"
                "Choose the most sensible defaults for any ambiguous parts.\n"
            )
        prompt = (
            f"{system_primer}\n\n"
            f"RECEIPT_PATH: {receipt_path}\n"
            f"Write your JSON receipt to: {receipt_path}\n\n"
            f"REMINDER: Your ONLY job is clarification. Do NOT build, plan, "
            f"or output anything except the JSON file.\n\n"
            f"{yolo_prompt}"
            f"## Original task\n{task.raw_text}\n\n"
            f"## Clarification so far\n{history_block or '(none yet)'}\n"
        )
        actual_cwd = workspace_root or workdir
        spec = AgentCallSpec(
            role="qlarifier", model=model, prompt=prompt, workdir=actual_cwd,
            output_file=receipt_path if receipt_path else "qlarifier_output.json",
            thinking=thinking,
            sandbox="danger-full-access", approval="never",
            reasoning_effort=reasoning_effort,
            cd=actual_cwd, repo_root=actual_cwd,
            workspace_root=actual_cwd, run_root=run_root,
        )
        data, _ = call_for_json(adapter, spec, event_log=event_log,
                                run_root=run_root, cycle=0,
                                stream_config=stream_config)

        if data.get("status") == "need_clarification":
            questions = data.get("questions") or ["(no question text returned)"]
            if yolo:
                if round_num >= 1:
                    if event_log:
                        event_log.emit("clarifier.assumption",
                                       mode="yolo",
                                       assumptions=[f"Fallback: bypassed question after retry: {q}" for q in questions],
                                       original_questions=questions,
                                       fallback=True)
                        event_log.emit("approval.bypassed",
                                       reason="yolo_fallback_enabled",
                                       stage="clarifier")
                    assumptions_text = "; ".join(
                        f"Assuming {q}" for q in questions
                    )
                    fallback_task = f"{task.raw_text}\n\n[YOLO Assumptions: {assumptions_text}]"
                    return ClarifiedTask(
                        source_task_id=task.id,
                        clarified_text=fallback_task,
                        notes_for_instruqtor=f"YOLO fallback after {round_num+1} clarification attempts. Assumptions: {assumptions_text}",
                        transcript=transcript,
                    )
                
                if event_log:
                    event_log.emit("clarifier.assumption",
                                   mode="yolo",
                                   assumptions=[f"Bypassed question: {q}" for q in questions],
                                   original_questions=questions)
                    event_log.emit("approval.bypassed",
                                   reason="yolo_enabled",
                                   stage="clarifier")
                history_block += "".join(
                    f"Q: {q}\nA: [YOLO: making best assumption, proceeding automatically]\n"
                    for q in questions
                )
                continue
            answers = ask_human(questions)
            transcript.append(ClarificationTurn(questions=questions, answers=answers))
            all_auto = all(
                (a or "").startswith("[AUTO]") or (a or "").strip() == ""
                for a in answers
            )
            if all_auto:
                history_block += "".join(
                    f"Q: {q}\nA: [AUTO: non-interactive mode — make your best assumption and proceed]\n"
                    for q in questions
                )
                if round_num >= 2 and any(
                    "[AUTO]" in (a or "") or (a or "").strip() == ""
                    for a in answers
                ):
                    history_block += (
                        "\n*** SYSTEM: You have asked questions for 2+ rounds in non-interactive mode. "
                        "You MUST now make your best assumptions and return status 'clarified'. "
                        "Do NOT ask any more questions — the user cannot answer them. ***\n"
                    )
            else:
                history_block += "".join(f"Q: {q}\nA: {a}\n" for q, a in zip(questions, answers))
            if event_log:
                event_log.emit("clarification.questioned", round=round_num,
                                questions=questions, answers=answers)
            continue

        # Not "need_clarification"
        if data.get("status") == "ready":
            assumptions = data.get("assumptions", [])
            resolved_task = data.get("resolved_task", task.raw_text)
            confidence = data.get("confidence", "medium")
            if event_log:
                event_log.emit("clarifier.assumption",
                               mode="yolo",
                               assumptions=assumptions,
                               resolved_task=resolved_task,
                               confidence=confidence)
            data["status"] = "clarified"
            data["clarified_task"] = resolved_task
            data["notes_for_instruqtor"] = "Assumptions: " + "; ".join(assumptions[:3])

        cleanup_agent_artifacts(spec)

        # Post-agent scan for forbidden project deliverables.
        if run_root:
            violations_list = _scan_for_deliverables(
                run_root, workspace_root or workdir,
                agent="qlarifier",
                cycle=0, event_log=event_log)
            if violations_list:
                removed = _cleanup_forbidden(violations_list)
                if event_log:
                    event_log.emit("path_policy_violation_detected",
                                   agent="qlarifier", cycle=0,
                                   violations_count=len(violations_list),
                                   removed_count=removed,
                                   severity="warning")
                import sys as _sys
                _sys.stderr.write(
                    f"[qq] WARNING: Qlarifier wrote {len(violations_list)} "
                    f"project file(s) under QonQrete metadata. "
                    f"Cleaned up {removed} file(s). "
                    f"This is non-fatal for qlarifier.\n")
                _sys.stderr.flush()
        return ClarifiedTask.from_agent_json(task.id, data, transcript)

    # Safety valve
    return ClarifiedTask(
        source_task_id=task.id,
        clarified_text=task.raw_text,
        notes_for_instruqtor=(
            "Qlarifier exhausted max_rounds without converging on a final "
            "clarified task; passing the raw task through unmodified."
        ),
        transcript=transcript,
    )
