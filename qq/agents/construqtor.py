"""
construQtor — the implementer.

Speed optimization: Warm context reuse — on repair cycles, the repair
prompt includes a condensed summary of the previous build's context
so the model can "continue" rather than "restart" from scratch.

Receipt path (new):
  Per-call: <run_root>/agents/cycle-XXX/construqtor/receipts/<bg_id>__<call_id>.json
  Aggregate: <run_root>/agents/cycle-XXX/construqtor/construqtor_output.json
"""
from __future__ import annotations

import concurrent.futures
import os
import json
from typing import Dict, List, Optional

from ..adapters.base import AgentAdapter, AgentCallSpec
from ..models import BriQ, BriqStatus, BuildGroup, ClarifiedTask, ReviewIssue, ReviewVerdict
from ..workspaces import WorkspaceManager
from ._jsonio import call_for_json, cleanup_agent_artifacts
from .receipts import (
    agent_receipt_path, per_call_receipt_path, aggregate_receipt_path,
    ensure_dir, write_aggregate_receipt, merge_per_call_receipts,
)

_SYSTEM_PRIMER_TEMPLATE = """You are construQtor, the implementer agent in the Qq
pipeline. You have full read/write access to the files in your current
working directory.

PATH CONTRACT:
- WORKSPACE_ROOT (TARGET_PATH): __WS__
- RUN_ROOT (QonQrete metadata): __RR__
- You must NOT create, edit, or build any files under RUN_ROOT or `.qq`
- RUN_ROOT and `.qq` are QonQrete metadata-only
- If you need to reference state, read it from RUN_ROOT, but do not use RUN_ROOT as your working directory
- Your `cd` directory is WORKSPACE_ROOT — that is where project files live

DO NOT write QonQrete receipt JSON files into the target project workspace.
Write your required JSON receipt only to RECEIPT_PATH.
Project/source files go under TARGET_PATH only.

 Implement the briQs described below for real, by
creating/editing the actual files — you are not writing a description of
the work, you are doing the work.

Do real file edits in the current working directory.
Do not just describe the changes.
Write only a small JSON receipt to the requested output file.
Do not commit — Qq handles that.
Do not write secrets.
Do not write Qq scratch files into the target repo.

MAXIMIZE FIRST-PASS COMPLETENESS: Implement every detail, every feature,
every interactive element, every paragraph of text, every animation, every
form field, every styling detail listed in the briQ. Leave NOTHING for a
repair cycle. A repair cycle = failure. Do the FULL job NOW. This means
ALL text content filled in (no lorem ipsum), ALL CSS effects implemented,
ALL interactive behaviors working, ALL responsive breakpoints handled.
Half-done features cause repair cycles. Full features prevent them.

When repair notes are present on a briQ, they take priority: fix exactly
what they describe before doing anything else.

When you are done, write a short status JSON to the given path (this is
just a status receipt — your real output is the code you wrote in the
workspace itself):
{"status": "implemented", "files_changed": ["...", "..."], "notes": "..."}
"""

_REPAIR_PRIMER_TEMPLATE = """You are construQtor in REPAIR MODE. The inspeQtor has
reviewed your previous work and found specific issues that must be fixed.

PATH CONTRACT:
- WORKSPACE_ROOT (TARGET_PATH): __WS__
- RUN_ROOT (QonQrete metadata): __RR__
- You must NOT create, edit, or build any files under RUN_ROOT or `.qq`
- RUN_ROOT and `.qq` are QonQrete metadata-only
- If you need to reference state, read it from RUN_ROOT, but do not use RUN_ROOT as your working directory
- Your `cd` directory is WORKSPACE_ROOT — that is where project files live

DO NOT write QonQrete receipt JSON files into the target project workspace.
Write your required JSON receipt only to RECEIPT_PATH.

Your ONLY job is to fix the issues listed below — nothing else.

CRITICAL RULES FOR REPAIR MODE:
- Fix ONLY the issues listed under REPAIR NOTES below.
- Do NOT redo, review, refactor, or rewrite any other part of the code.
- Do NOT reimplement the overall briQ from scratch.
- Read the affected files, make the minimal targeted changes, and stop.
- When the listed issues are fixed, write your JSON receipt IMMEDIATELY.
- Do not iterate, do not improve things beyond the listed issues.
- Do not add features, refactor, or change anything not mentioned.

When you are done fixing ONLY the listed repair issues, write:
{"status": "implemented", "files_changed": ["...", "..."], "notes": "..."}
"""

def _build_system_primer(workspace_root: str = "", run_root: str = "") -> str:
    """Return the system primer with actual workspace/run root paths interpolated."""
    ws = workspace_root or "the target directory passed to `qq run <task> <target>`"
    rr = run_root or "QonQrete internal metadata directory (NOT your working directory)"
    return _SYSTEM_PRIMER_TEMPLATE.replace("__WS__", ws).replace("__RR__", rr)


def _build_repair_primer(workspace_root: str = "", run_root: str = "") -> str:
    """Return the repair primer with actual workspace/run root paths interpolated."""
    ws = workspace_root or "the target directory passed to `qq run <task> <target>`"
    rr = run_root or "QonQrete internal metadata directory (NOT your working directory)"
    return _REPAIR_PRIMER_TEMPLATE.replace("__WS__", ws).replace("__RR__", rr)




# ---------------------------------------------------------------------------
# Post-agent scan for forbidden project deliverables
# ---------------------------------------------------------------------------
from ..path_guards import scan_for_forbidden_bool as _scan_for_forbidden
from ..path_guards import scan_for_forbidden_deliverables as _scan_for_deliverables
from ..path_guards import cleanup_forbidden_deliverables as _cleanup_forbidden
from ..path_guards import move_qonqrete_metadata_out_of_target as _sweep_target
from ..sandbox import SandboxUnavailable, SandboxPolicyViolation

# Module-level cache: maps build_group_id -> last build context dict
_last_build_context: Dict[str, dict] = {}


def reset_last_build_context() -> None:
    """Reset the module-level build context cache. Used in test teardown."""
    _last_build_context.clear()



def _has_repair_only(briqs: List[BriQ]) -> bool:
    """True if every briQ is either already DONE/verified or has repair
    notes, and at least one briQ actually has repair notes pending."""
    if not briqs:
        return False
    all_done_or_repair = all(
        b.status in (BriqStatus.DONE, BriqStatus.NEEDS_REPAIR, BriqStatus.AWAITING_REVIEW)
        for b in briqs
    )
    any_repair = any(b.repair_notes for b in briqs)
    return all_done_or_repair and any_repair


def _build_prompt(clarified: ClarifiedTask, group: BuildGroup,
                  briqs: List[BriQ],
                  sibling_info: list = None,
                  workspace_root: str = "",
                  run_root: str = "",
                  receipt_path: str = "") -> str:
    if _has_repair_only(briqs):
        return _build_repair_prompt(clarified, group, briqs, sibling_info, workspace_root, run_root, receipt_path)
    return _build_full_prompt(clarified, group, briqs, sibling_info, workspace_root, run_root, receipt_path)


def _build_full_prompt(clarified: ClarifiedTask, group: BuildGroup,
                       briqs: List[BriQ],
                       sibling_info: list = None,
                       workspace_root: str = "",
                       run_root: str = "",
                       receipt_path: str = "") -> str:
    briq_lines = []
    for b in briqs:
        line = f"- [{b.id}] {b.title}: {b.description}"
        if b.repair_notes:
            line += "\n  REPAIR NOTES: " + " | ".join(b.repair_notes)
        if b.expected_files:
            line += f"\n  Expected files: {', '.join(b.expected_files)}"
        briq_lines.append(line)

    # Build sibling awareness notice
    sibling_section = ""
    if sibling_info and len(sibling_info) > 0:
        sibling_lines = [
            "",
            "## IMPORTANT - Parallel Build Awareness",
            "These build groups are being built IN PARALLEL right now. ",
            "Do NOT create, modify, or depend on files that belong to them. ",
            "Stay strictly within your own expected_files. ",
            "Do NOT try to spin up / start any application - testing is done ",
            "by the qontroller after ALL groups finish.",
        ]
        for sib in sibling_info:
            sibling_lines.append(
                f"- **{sib['group_name']}** ({sib['group_id']}): "
                f"working on {', '.join(sib['briqs'])}"
            )
            if sib.get('expected_files'):
                sibling_lines.append(
                    f"  Their files (DO NOT TOUCH): "
                    f"{', '.join(sib['expected_files'])}"
                )
        sibling_lines.append("")
        sibling_section = "\n".join(sibling_lines) + "\n"

    receipt_line = f"RECEIPT_PATH: {receipt_path}\nWrite your status JSON to: {receipt_path}\n"
    prompt = (
        f"{_build_system_primer(workspace_root, run_root)}\n{sibling_section}\n"
        f"{receipt_line}\n"
        f"## Overall clarified task\n{clarified.clarified_text}\n\n"
        f"## Build group: {group.name}\n{group.description}\n\n"
        f"## BriQs in this group\n" + "\n".join(briq_lines) + "\n"
    )
    _last_build_context[group.id] = {
        "clarified_text": clarified.clarified_text,
        "group_name": group.name,
        "group_description": group.description,
        "briqs": [
            {"id": b.id, "title": b.title, "description": b.description}
            for b in briqs
        ],
    }
    return prompt


def _build_repair_prompt(clarified: ClarifiedTask, group: BuildGroup,
                         briqs: List[BriQ],
                         sibling_info: list = None,
                         workspace_root: str = "",
                         run_root: str = "",
                         receipt_path: str = "") -> str:
    """Build a repair-only prompt."""
    repair_lines = []
    for b in briqs:
        if b.repair_notes:
            repair_lines.append(
                f"### BriQ: {b.title} ({b.id})\n"
                + "\n".join(f"- {note}" for note in b.repair_notes)
            )
    if not repair_lines:
        return _build_full_prompt(clarified, group, briqs, sibling_info, workspace_root, run_root, receipt_path)

    warm_context = ""
    prev_ctx = _last_build_context.get(group.id)
    if prev_ctx:
        warm_lines = [
            "## WARM CONTEXT — Previous build summary (for continuity)",
            f"**Task**: {prev_ctx['clarified_text'][:500]}",
            f"**Group**: {prev_ctx['group_name']} — {prev_ctx['group_description']}",
            "**Previously built briQs in this group**:",
        ]
        for bq in prev_ctx["briqs"]:
            warm_lines.append(f"  - [{bq['id']}] {bq['title']}: {bq['description']}")
        warm_lines.append("")
        warm_lines.append(
            "These files already exist from previous builds. The code is in the"
            " workspace. Fix ONLY the repair issues below — do not rebuild from"
            " scratch, do not touch files that aren't mentioned in repair notes."
        )
        warm_lines.append("")
        warm_context = "\n".join(warm_lines)

    sibling_repair = ""
    if sibling_info and len(sibling_info) > 0:
        sibling_lines = [
            "",
            "## IMPORTANT - Parallel Build Awareness (repair mode)",
            "These build groups are being built/fixed IN PARALLEL right now. ",
            "Do NOT create, modify, or depend on files that belong to them. ",
            "Stay strictly within your own files. ",
            "Do NOT try to spin up / start any application.",
        ]
        for sib in sibling_info:
            sibling_lines.append(
                f"- **{sib['group_name']}** ({sib['group_id']}): "
                f"working on {', '.join(sib['briqs'])}"
            )
            if sib.get('expected_files'):
                sibling_lines.append(
                    f"  Their files (DO NOT TOUCH): "
                    f"{', '.join(sib['expected_files'])}"
                )
        sibling_lines.append("")
        sibling_repair = "\n".join(sibling_lines) + "\n"

    receipt_line = f"RECEIPT_PATH: {receipt_path}\nWrite your status JSON to: {receipt_path}\n"
    prompt = (
        f"{_build_repair_primer(workspace_root, run_root)}\n{sibling_repair}\n"
        f"{receipt_line}\n"
        f"{warm_context}"
        f"## Context: Build group '{group.name}'\n"
        f"These files already exist and are complete except for the issues"
        f" listed below. Fix ONLY these issues.\n\n"
        f"## REPAIR ISSUES (fix only these — nothing else)\n\n"
        + "\n\n".join(repair_lines) + "\n\n"
        "---\n"
        "REMINDER: You are in REPAIR MODE. Fix the issues above, then "
        "write your JSON receipt and STOP. Do not redo the entire briQ."
        " Do not iterate. The inspeQtor will check your fixes next.\n"
    )
    return prompt


def run_construqtor_for_group(
    adapter: AgentAdapter, clarified: ClarifiedTask,
    group: BuildGroup, briqs: List[BriQ],
    workspaces: WorkspaceManager, model: str,
    cycle: int, event_log=None, thinking: bool = False,
    reasoning_effort: str = "",
    sandbox: str = "danger-full-access",
    approval: str = "never",
    run_root: str = "",
    workspace_root: str = "",
    stream_config: dict = None,
    sibling_info: list = None,
) -> Dict:
    workdir = workspaces.repo_root
    if event_log:
        event_log.emit("workspace.created",
                       build_group_id=group.id, cycle=cycle)

    pending_briqs = [b for b in briqs if b.status not in (BriqStatus.DONE, BriqStatus.AWAITING_REVIEW)]

    if not pending_briqs:
        if event_log:
            event_log.emit("construqtor.skipped",
                           build_group_id=group.id, cycle=cycle,
                           reason="all_briqs_already_done")
        return {"status": "skipped", "files_changed": [],
                "notes": "All briQs already DONE or awaiting review — nothing to build."}

    ws_root = workspace_root or workspaces.repo_root

    # Canonical receipt paths
    call_id = f"call-{__import__('uuid').uuid4().hex[:8]}"
    if run_root:
        per_call_path = str(per_call_receipt_path(run_root, cycle, "construqtor", group.id, call_id))
        ensure_dir(per_call_receipt_path(run_root, cycle, "construqtor", group.id, call_id).parent)
        # Also ensure aggregate dir exists
        agg_path = aggregate_receipt_path(run_root, cycle, "construqtor")
        ensure_dir(agg_path.parent)
    else:
        per_call_path = "construqtor_output.json"

    prompt = _build_prompt(clarified, group, pending_briqs, sibling_info,
                           workspace_root=ws_root, run_root=run_root,
                           receipt_path=per_call_path)
    spec = AgentCallSpec(
        role="construqtor", model=model, prompt=prompt,
        workdir=ws_root, output_file=per_call_path,
        thinking=thinking, reasoning_effort=reasoning_effort,
        sandbox=sandbox, approval=approval,
        cd=ws_root, repo_root=ws_root,
        workspace_root=ws_root, run_root=run_root,
    )
    # Track which briQs were being worked on
    worked_briqs = list(pending_briqs)
    for b in worked_briqs:
        b.status = BriqStatus.IN_PROGRESS
        b.attempts += 1
        if event_log:
            event_log.emit("briq.status_changed",
                           briq_id=b.id, status="in_progress",
                           build_group_id=group.id, cycle=cycle)

    try:
        data, _ = call_for_json(adapter, spec, event_log=event_log,
                            run_root=run_root, cycle=cycle,
                            stream_config=stream_config or {})
        cleanup_agent_artifacts(spec)
    except (SandboxUnavailable, SandboxPolicyViolation) as e:
        cleanup_agent_artifacts(spec)
        for b in worked_briqs:
            b.status = BriqStatus.FAILED
            if event_log:
                event_log.emit("briq.status_changed",
                               briq_id=b.id, status="failed",
                               build_group_id=group.id, cycle=cycle,
                               reason="sandbox_unavailable_or_policy")
        workspaces.commit_direct(
            f"qq: construQtor FAILED on {group.name} (cycle {cycle}) — "
            f"sandbox: {e}"
        )
        if event_log:
            event_log.emit("build_group.failed",
                           build_group_id=group.id, cycle=cycle,
                           reason="sandbox_unavailable",
                           status="failed")
        return {
            "status": "failed",
            "error": str(e),
            "files_changed": [],
            "notes": f"construQtor sandbox failure: {e}",
        }

    for b in worked_briqs:
        b.status = BriqStatus.AWAITING_REVIEW
        b.repair_notes = []
        if event_log:
            event_log.emit("briq.status_changed",
                           briq_id=b.id, status="awaiting_review",
                           build_group_id=group.id, cycle=cycle)

    # Merge per-call receipt into aggregate (thread-safe with file locking)
    if run_root:
        try:
            per_call_receipt = {
                "build_group_id": group.id,
                "build_group_name": group.name,
                "call_id": call_id,
                "status": data.get("status", "implemented"),
                "files_changed": data.get("files_changed", []),
                "notes": data.get("notes", ""),
                "raw_receipt": data,
            }
            agg_path = aggregate_receipt_path(run_root, cycle, "construqtor")
            write_aggregate_receipt(agg_path, [per_call_receipt], "construqtor", cycle)
        except Exception:
            pass  # Non-fatal: receipt merging failure should not crash the build

    # Move any QonQrete metadata JSON out of the target workspace BEFORE committing
    if run_root and workspace_root:
        _sweep_target(run_root, ws_root, event_log=event_log, cycle=cycle)

    workspaces.commit_direct(
        f"qq: construqtor pass on {group.name} (cycle {cycle})"
    )

    # Post-agent scan
    if run_root:
        violations_list = _scan_for_deliverables(
            run_root, workspaces.repo_root,
            agent="construqtor",
            build_group_id=group.id, cycle=cycle, event_log=event_log)
        if violations_list:
            removed = _cleanup_forbidden(violations_list)
            if event_log:
                event_log.emit("path_policy_violation_cleanup",
                               agent="construqtor",
                               build_group_id=group.id,
                               cycle=cycle,
                               violations_count=len(violations_list),
                               removed_count=removed)
            for b in worked_briqs:
                b.status = BriqStatus.FAILED
                if event_log:
                    event_log.emit("briq.status_changed",
                                   briq_id=b.id, status="failed",
                                   build_group_id=group.id, cycle=cycle,
                                   reason="path_policy_violation")
            workspaces.commit_direct(
                f"qq: construQtor FAILED on {group.name} (cycle {cycle}) — path_policy_violation"
            )
            if event_log:
                event_log.emit("build_group.failed",
                               build_group_id=group.id, cycle=cycle,
                               reason="path_policy_violation",
                               status="failed")
            return {
                "status": "failed",
                "error": "path_policy_violation",
                "files_changed": [],
                "notes": "Agent wrote project deliverables under QonQrete metadata.",
            }

    if event_log:
        event_log.emit("workspace.committed",
                       build_group_id=group.id, cycle=cycle)

    return data


def run_construqtor(
    adapter: AgentAdapter, clarified: ClarifiedTask,
    groups: List[BuildGroup],
    briqs_by_group: Dict[str, List[BriQ]],
    workspaces: WorkspaceManager,
    model: str, cycle: int, event_log=None,
    thinking: bool = False, max_parallel: int = 8,
    reasoning_effort: str = "",
    run_root: str = "",
    workspace_root: str = "",
    stream_config: dict = None,
) -> Dict[str, Dict]:
    """Build all groups (used for backward compat / batch mode)."""
    results: Dict[str, Dict] = {}

    parallel_groups = [g for g in groups if g.parallel_safe]
    sequential_groups = [g for g in groups if not g.parallel_safe]

    for g in sequential_groups:
        try:
            results[g.id] = run_construqtor_for_group(
                adapter, clarified, g,
                briqs_by_group.get(g.id, []), workspaces,
                model, cycle, event_log, thinking,
                reasoning_effort=reasoning_effort,
                run_root=run_root,
                workspace_root=workspace_root,
                stream_config=stream_config,
            )
        except Exception as exc:
            results[g.id] = {
                "status": "failed", "error": str(exc)}

    if parallel_groups:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_parallel) as pool:
            futures = {
                pool.submit(
                    run_construqtor_for_group, adapter, clarified,
                    g, briqs_by_group.get(g.id, []), workspaces,
                    model, cycle, event_log, thinking,
                    reasoning_effort=reasoning_effort,
                    run_root=run_root,
                    workspace_root=workspace_root,
                    stream_config=stream_config,
                ): g
                for g in parallel_groups
            }
            for fut in concurrent.futures.as_completed(futures):
                g = futures[fut]
                try:
                    results[g.id] = fut.result()
                except Exception as exc:
                    results[g.id] = {
                        "status": "failed", "error": str(exc)}

    return results
