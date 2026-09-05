"""
instruQtor — splits a clarified task into briQs grouped into build groups.

The briQ-sensitivity scale (0-16):
  0 = Auto (instruQtor decides optimal granularity)
  1-16 = Manual (higher = more/smaller briQs)
The scale is salvaged from QonQrete v1's worqer/instruqtor.py, because it was
always a genuinely good idea — one dial instead of arguing with prompt wording
every time you want coarser or finer decomposition. Setting it to 0 (the new
default) gives instruQtor full authority to determine the optimal decomposition.
The build-group concept is also salvaged from v1 (it already had
`build_group_id` there); it just lived buried inside a much bigger file than it
needed to be.
"""
from __future__ import annotations

import os
from ..adapters.base import AgentAdapter, AgentCallSpec
from ..models import ClarifiedTask, Plan
from ._jsonio import call_for_json, cleanup_agent_artifacts
from .receipts import agent_receipt_path, ensure_dir
from ..path_guards import scan_for_forbidden_bool as _scan_for_forbidden, PathPolicyViolation

BRIQ_SENSITIVITY_SCALE = {
    0: "Auto (instruQtor decides optimal granularity)", 1: "Tiny split (2 briqs)", 2: "Very broad (2-3 briqs)",
    3: "Broad (3-4 briqs)", 4: "Feature-level (4-6 briqs)", 5: "Balanced (5-7 briqs)",
    6: "Detailed (6-9 briqs)", 7: "High (8-12 briqs)", 8: "Very high (10-15 briqs)",
    9: "Atomic-ish (12-18 briqs)", 10: "Ultra (15-22 briqs)", 11: "Mega (18-28 briqs)",
    12: "Hyper (22-36 briqs)", 13: "Extreme (28-48 briqs)", 14: "Maximum (36-64 briqs)",
    15: "Insane (48-84 briqs)", 16: "QQ MAX (64-120 briqs)",
}

_SYSTEM_PRIMER_TEMPLATE = """You are instruQtor, the planning agent in the Qq
pipeline. You receive an already-clarified task. Split it into "briQs"

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

(small, independently describable units of work) and group briQs that
belong to the same component/feature into "build groups". Two briQs belong
in the same build group when they touch the same files/component and should
be built together; otherwise keep them in separate groups so they can run
in parallel later.

Mark build_groups `parallel_safe: true` UNLESS they explicitly share the
exact same files (e.g., both need to edit App.svelte or app.css). Different
components (.svelte files) never conflict. Default to parallel. In a modern
component-based project, most groups should be parallel_safe: true. Only
groups that genuinely touch the same exact files should be sequential.
When in doubt, mark it TRUE — parallel is faster and an auto-detector
will verify safety after planning.

Assign each briQ a sensitivity score (0-16) reflecting how much authority
the implementer has to reuse/diverge/expand on your description.

When the target granularity is "Auto (instruQtor decides optimal granularity)",
YOU choose the optimal number and size of briQs based on the task complexity:
- Simple tasks: fewer, coarser briQs (1-4)
- Moderate tasks: balanced decomposition (5-10)
- Complex multi-component tasks: finer decomposition (10-20+)
- Very large system-level tasks: as many briQs as you truly need
The goal is the BEST RESULT — split enough that each unit is buildable and
reviewable, but no more than necessary.

For each briQ, include ALL implementation details: exact text content,
exact color values, exact CSS effects, exact form fields, exact interactive
behaviors. Vagueness in briQs causes repair cycles — precision prevents them.
The implementer cannot guess what you meant; spell out every requirement.

Respond with ONLY valid JSON written to the given path, shaped exactly like:
{
  "summary": "...",
  "build_groups": [
    {
      "build_group_id": "bg-...", "name": "...", "description": "...",
      "parallel_safe": false,
      "briqs": [
        {"briq_id": "briq-...", "title": "...", "description": "...",
         "sensitivity": 5, "depends_on": [], "expected_files": ["..."]}
      ]
    }
  ]
}
"""



def _build_system_primer(workspace_root: str = "", run_root: str = "") -> str:
    """Return the system primer with actual workspace/run root paths interpolated."""
    ws = workspace_root or "the target directory passed to `qq run <task> <target>`"
    rr = run_root or "QonQrete internal metadata directory (NOT your working directory)"
    return _SYSTEM_PRIMER_TEMPLATE.replace("__WS__", ws).replace("__RR__", rr)

def run_instruqtor(
    adapter: AgentAdapter, clarified: ClarifiedTask, workdir: str, model: str,
    briq_sensitivity: int = 5, event_log=None, thinking: bool = True,
    reasoning_effort: str = "",

    run_root: str = "",
    workspace_root: str = "",
    stream_config: dict = None,
) -> Plan:
    if not (0 <= briq_sensitivity <= 16):
        briq_sensitivity = max(0, min(16, briq_sensitivity))
    sensitivity_label = BRIQ_SENSITIVITY_SCALE.get(briq_sensitivity, "Balanced")

    # Canonical receipt path for InstruQtor (new: instruqtor_output.json)
    receipt_path = str(agent_receipt_path(run_root, 0, "instruqtor")) if run_root else ""
    if receipt_path:
        ensure_dir(agent_receipt_path(run_root, 0, "instruqtor").parent)

    prompt = (
        f"{_build_system_primer(workspace_root or workdir, run_root)}\n\n"
        f"RECEIPT_PATH: {receipt_path}\n"
        f"Write your JSON to: {receipt_path}\n\n"
        f"Target granularity: {briq_sensitivity} — {sensitivity_label}\n\n"
        f"## Clarified task\n{clarified.clarified_text}\n\n"
        f"## Notes from Qlarifier\n{clarified.notes_for_instruqtor}\n"
    )
    if briq_sensitivity == 0:
        prompt += (
            "\n## CRITICAL: Granularity Mode = AUTO\n"
            "You have full authority to determine the optimal number of briQs.\n"
            "Analyze the task and choose the decomposition that will produce the\n"
            "best end result. Do not ask yourself what a human would prefer —\n"
            "choose what YOU think is architecturally optimal.\n"
        )
    actual_cwd = workspace_root or workdir
    spec = AgentCallSpec(
        role="instruqtor", model=model, prompt=prompt, workdir=actual_cwd,
        output_file=receipt_path if receipt_path else "instruqtor_output.json",
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        sandbox="danger-full-access", approval="never",
        cd=actual_cwd, repo_root=actual_cwd,
        workspace_root=actual_cwd, run_root=run_root,
    )
    data, _ = call_for_json(adapter, spec, event_log=event_log,
                            run_root=run_root, cycle=0,
                            stream_config=stream_config or {})
    cleanup_agent_artifacts(spec)

    # Post-agent scan for forbidden project deliverables.
    if run_root:
        violation = _scan_for_forbidden(
            run_root, workspace_root or workdir,
            agent="instruqtor",
            cycle=0, event_log=event_log)
        if violation:
            if event_log:
                event_log.emit("path_policy_violation_detected",
                               agent="instruqtor", cycle=0,
                               severity="warning")
            import sys as _sys
            _sys.stderr.write(
                "[qq] WARNING: instruQtor wrote project files under "
                "QonQrete metadata. This is non-fatal for instruQtor.\n")
            _sys.stderr.flush()
    return Plan.from_agent_json(clarified.id, data)
