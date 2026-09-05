"""
inspeQtor — the brutally honest reviewer. Passes show as green FULLY_DONE;
failures as red NOT_DONE. Reviews the integrated result in the main repo
tree against the clarified task and decides, full stop, whether the work
is actually done.

The only passing status string is "FULLY_DONE". Qontroller checks for that
exact token and nothing else counts as done, on purpose — it's a
deliberately weird, unmistakable token specifically so a model can't "kind
of" pass by hedging with something that sounds like agreement.

Receipt path (new):
  Per-call: <run_root>/agents/cycle-XXX/inspeqtor/receipts/<bg_id>__<call_id>.json
  Aggregate: <run_root>/agents/cycle-XXX/inspeqtor/inspeqtor_output.json
"""
from __future__ import annotations

import os
import uuid
from typing import List, Optional

from ..adapters.base import AgentAdapter, AgentCallSpec
from ..path_guards import PathPolicyViolation
from ..models import BuildGroup, ClarifiedTask, ReviewVerdict
from ..workspaces import WorkspaceManager
from ._jsonio import call_for_json, cleanup_agent_artifacts
from .receipts import (
    per_call_receipt_path, aggregate_receipt_path,
    ensure_dir, write_aggregate_receipt,
)
from ..path_guards import scan_for_forbidden_bool as _scan_for_forbidden

_SYSTEM_PRIMER_TEMPLATE = """You are inspeQtor, the reviewer agent in the Qq
pipeline. You are a brutally honest, strict reviewer. Your job is not to be

PATH CONTRACT:
- WORKSPACE_ROOT (TARGET_PATH): __WS__
- RUN_ROOT (QonQrete metadata): __RR__
- You must NOT create, edit, or build any files under RUN_ROOT or `.qq`
- RUN_ROOT and `.qq` are QonQrete metadata-only
- If you need to reference state, read it from RUN_ROOT, but do not use RUN_ROOT as your working directory
- Your `cd` directory is WORKSPACE_ROOT — that is where project files live

DO NOT write QonQrete receipt JSON files into the target project workspace.
Write your required JSON receipt only to RECEIPT_PATH.
Inspect TARGET_PATH. Write your inspection JSON only to RECEIPT_PATH.

encouraging — it is to find every real gap between what was asked for and
what was actually built. Read the files in your working directory yourself;
do not take the implementer's word for anything.

If, and only if, the work genuinely and completely satisfies the clarified
task, respond with status "FULLY_DONE". Any other situation — even
one small thing wrong, missing, half-done, or merely claimed-but-unverified
— is NOT_DONE, with a specific, actionable issue for every gap you find.
Vague issues ("improve error handling") are not acceptable: say exactly
which file/behavior is wrong and exactly what would fix it.

CRITICAL RULES FOR SUBSEQUENT REVIEW CYCLES:
- If a Previous Reviews section is present, you are reviewing the SAME task
  that you reviewed before. This is a HOT START — use your prior knowledge.
- Check whether issues from previous cycles have actually been FIXED.
- If an old issue is fixed, do NOT report it again.
- If an old issue persists, report it again and note which cycle it first
  appeared in (e.g., "[PERSISTENT from cycle 1] ...").
- If the score trend is improving, acknowledge progress but stay strict.
- A score of 95+ with zero blocking issues = FULLY_DONE.

Respond with ONLY valid JSON written to the given path:
{
  "status": "FULLY_DONE" | "NOT_DONE",
  "score": 0-100,
  "summary": "...",
  "issues": [
    {"build_group_id": "...", "briq_id": "...", "severity": "blocking"|"minor",
     "what_is_wrong": "...", "what_to_fix": "...", "files": ["..."]}
  ]
}

CRITICAL — use the EXACT build_group_id and briq_id values shown below.
Do NOT invent your own IDs, do NOT use group names or briQ titles as IDs.
The orchestrator can only map issues to the correct briQs if you use the
exact IDs provided in the Build Groups section.

Score is your honest 0-100 assessment of how close the work is to done:
  - 95-100: genuinely ready, everything works, no issues → FULLY_DONE
  - 70-94: mostly works but has non-blocking gaps → NOT_DONE
  - 40-69: significant gaps, several things broken → NOT_DONE
  - 0-39: barely started or fundamentally broken → NOT_DONE
"""



def _build_system_primer(workspace_root: str = "", run_root: str = "") -> str:
    """Return the system primer with actual workspace/run root paths interpolated."""
    ws = workspace_root or "the target directory passed to `qq run <task> <target>`"
    rr = run_root or "QonQrete internal metadata directory (NOT your working directory)"
    return _SYSTEM_PRIMER_TEMPLATE.replace("__WS__", ws).replace("__RR__", rr)

def run_inspeqtor(
    adapter: AgentAdapter, clarified: ClarifiedTask, groups: List[BuildGroup],
    workspaces: WorkspaceManager, repo_root: str, model: str,
    cycle: int, run_root: str, event_log=None, thinking: bool = True,
    reasoning_effort: str = "",

    workspace_root: str = "",
    stream_config: dict = None,
    plan=None,
    verdict_history: Optional[List[ReviewVerdict]] = None,
    group_suffix: str = "",
) -> ReviewVerdict:
    # Build detailed group+briQ block
    group_lines = []
    for g in groups:
        group_lines.append(
            f"### Group: {g.name}\n"
            f"  build_group_id: {g.id}\n"
            f"  description: {g.description}\n"
            f"  parallel_safe: {g.parallel_safe}"
        )
        if plan and g.id in plan.build_groups:
            for bid in plan.build_groups[g.id].briq_ids:
                if bid in plan.briqs:
                    b = plan.briqs[bid]
                    notes = ""
                    if b.repair_notes:
                        notes = f" [REPAIR: {'; '.join(b.repair_notes)}]"
                    group_lines.append(
                        f"  - briq_id: {b.id} | title: {b.title} | "
                        f"description: {b.description} | "
                        f"status: {b.status.value}{notes}"
                    )
    group_block = "\n".join(group_lines)

    # Build previous reviews context
    previous_reviews_block = ""
    if verdict_history:
        prev_lines = []
        for i, v in enumerate(verdict_history, 1):
            prev_lines.append(
                f"### Cycle {v.cycle} — {v.status} (score: {v.score})\n"
                f"Summary: {v.summary}\n"
                f"Issues found ({len(v.issues)}):"
            )
            for j, issue in enumerate(v.issues, 1):
                prev_lines.append(
                    f"  {j}. [{issue.severity}] {issue.what_is_wrong}\n"
                    f"     → Fix: {issue.what_to_fix}\n"
                    f"     Files: {', '.join(issue.files) if issue.files else 'N/A'}"
                )
        if prev_lines:
            scores = [v.score for v in verdict_history]
            trend = " → ".join(str(s) for s in scores)
            direction = (
                "IMPROVING" if len(scores) >= 2 and scores[-1] > scores[-2]
                else "STABLE" if len(scores) >= 2 and scores[-1] == scores[-2]
                else "DECLINING" if len(scores) >= 2 and scores[-1] < scores[-2]
                else "FIRST REVIEW"
            )
            previous_reviews_block = (
                f"## PREVIOUS REVIEWS (hot start — you reviewed this before)\n"
                f"Score trend: {trend} ({direction})\n\n"
                + "\n".join(prev_lines)
                + "\n\nIMPORTANT: Check whether the issues above have been"
                " fixed. Don't re-report fixed issues. Do report persistent ones."
            )

    # Canonical receipt path
    call_id = f"call-{uuid.uuid4().hex[:8]}"
    if run_root:
        # Use group_suffix to distinguish per-group parallel reviews
        if group_suffix:
            # Per-group inspeQtor: use per-call receipt
            bg_id = group_suffix.lstrip("_")
            receipt_path = str(per_call_receipt_path(run_root, cycle, "inspeqtor", bg_id, call_id))
        else:
            # Single/full-cycle inspeQtor
            receipt_path = str(per_call_receipt_path(run_root, cycle, "inspeqtor", "full-cycle", call_id))
        ensure_dir(os.path.dirname(receipt_path))
        # Also ensure aggregate dir exists
        agg_path = aggregate_receipt_path(run_root, cycle, "inspeqtor")
        ensure_dir(agg_path.parent)
    else:
        receipt_path = f"inspeqtor_output{group_suffix}.json"

    actual_cwd = workspace_root or repo_root

    prompt = (
        f"{_build_system_primer(actual_cwd, run_root)}\n\n"
        f"RECEIPT_PATH: {receipt_path}\n"
        f"Write your JSON to: {receipt_path}\n\n"
        f"## Clarified task\n{clarified.clarified_text}\n\n"
        f"## Build groups delivered this cycle\n{group_block}\n\n"
        f"Review cycle: {cycle}\n"
    )
    if previous_reviews_block:
        prompt += f"\n{previous_reviews_block}\n"

    spec = AgentCallSpec(
        role="inspeqtor", model=model, prompt=prompt, workdir=actual_cwd,
        output_file=receipt_path, thinking=thinking,
        reasoning_effort=reasoning_effort,
        sandbox="danger-full-access", approval="never",
        cd=actual_cwd, repo_root=actual_cwd,
        workspace_root=actual_cwd, run_root=run_root,
    )
    data, _ = call_for_json(adapter, spec, event_log=event_log,
                            run_root=run_root, cycle=cycle,
                            stream_config=stream_config or {})
    cleanup_agent_artifacts(spec)

    # Merge per-call receipt into aggregate (thread-safe)
    if run_root:
        try:
            per_call_receipt = {
                "build_group_id": bg_id if group_suffix else "",
                "call_id": call_id,
                "status": data.get("status", "NOT_DONE"),
                "score": data.get("score", 0),
                "issues": data.get("issues", []),
                "notes": data.get("summary", ""),
                "raw_receipt": data,
            }
            agg_path = aggregate_receipt_path(run_root, cycle, "inspeqtor")
            write_aggregate_receipt(agg_path, [per_call_receipt], "inspeqtor", cycle)
        except Exception:
            pass

    # Post-agent scan
    if run_root:
        violation = _scan_for_forbidden(
            run_root, actual_cwd,
            agent="inspeqtor",
            build_group_id=",".join(g.id for g in groups),
            cycle=cycle, event_log=event_log)
        if violation:
            if event_log:
                event_log.emit("path_policy_violation_detected",
                               agent="inspeqtor", cycle=cycle,
                               severity="warning")
            import sys as _sys
            _sys.stderr.write(
                "[qq] WARNING: inspeQtor wrote project files under "
                "QonQrete metadata. This is non-fatal for inspeQtor.\n")
            _sys.stderr.flush()
    return ReviewVerdict.from_agent_json(cycle, data)
