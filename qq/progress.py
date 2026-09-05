"""
Canonical progress calculator for QonQrete.

Implements a phase-aware, multi-layer progress system:
- accepted_pct: Only work accepted by inspeQtor.
- working_pct: Provisional/momentum progress including built-but-not-yet-reviewed.
- displayed_pct: What the UI shows (working_pct while active, accepted_pct at FULLY_DONE).
- inspeqtor_quality_pct: Separated quality/confidence score.
- confidence: provisional | reviewed | final | failed | repairing

Phase weights:
  Clarification/Qlarifier:  5%
  Planning/instruQtor:     15%
  Build + review loop:     75%
  Finalization:             5%

Group lifecycle scores map statuses to 0.0..1.0 contribution.
construQtor completion = ready for Review, not Done.
inspeQtor acceptance = Done.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Phase weights (constants, configurable)
# ---------------------------------------------------------------------------
PHASE_WEIGHTS = {
    "clarification": 5.0,
    "planning": 15.0,
    "build_review": 75.0,
    "finalization": 5.0,
}


# ---------------------------------------------------------------------------
# Lifecycle score mapping: status → lifecycle_score
# ---------------------------------------------------------------------------
def _lifecycle_score(
    status: str,
    briq_completion_ratio: Optional[float] = None,
    repair_completion_ratio: Optional[float] = None,
) -> float:
    """Map group status to a lifecycle_score in 0.0..1.0.

    Args:
        status: Group status string.
        briq_completion_ratio: 0.0..1.0 fraction of briQs completed (for building).
        repair_completion_ratio: 0.0..1.0 fraction of repair done (for repairing).
    """
    if status is None:
        return 0.0

    s = status.lower().strip()

    # planned / not started
    if s in ("planned", "queued", "not_started", "pending"):
        return 0.00

    # building / in progress
    if s in ("building", "running", "in_progress", "constructing",
             "picked_up", "active", "writing", "testing", "constructing"):
        ratio = briq_completion_ratio if briq_completion_ratio is not None else 0.35
        return 0.10 + 0.50 * max(0.0, min(1.0, ratio))

    # built / ready for review
    if s in ("built", "build_complete", "ready_for_review", "pending_review",
             "build_done"):
        return 0.70

    # reviewing / inspecting
    if s in ("reviewing", "inspecting", "validation", "qa", "validating",
             "review_needed", "validating_in_progress", "inspection",
             "needs_review"):
        return 0.80

    # repair needed
    if s in ("repair_needed", "needs_repair", "failed_review",
             "failed_validation", "validation_failed", "failed"):
        return 0.65

    # repairing
    if s in ("repairing", "fixing", "adjusting"):
        ratio = repair_completion_ratio if repair_completion_ratio is not None else 0.72
        return 0.70 + 0.10 * max(0.0, min(1.0, ratio))

    # ready for re-review
    if s in ("ready_for_re_review"):
        return 0.82

    # accepted / done
    if s in ("accepted", "passed_review", "done", "complete", "fully_done",
             "success", "completed", "merged", "finalized", "valid_done",
             "pass"):
        return 1.00

    # Unknown status → 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Progress snapshot output shape
# ---------------------------------------------------------------------------
@dataclass
class ProgressGroup:
    id: str = ""
    name: str = ""
    status: str = ""
    weight_pct: float = 0.0
    normalized_weight_pct: float = 0.0
    lifecycle_score: float = 0.0
    working_contribution_pct: float = 0.0
    accepted_contribution_pct: float = 0.0
    confidence: str = "provisional"


@dataclass
class ProgressComponents:
    clarification_pct: float = 0.0
    planning_pct: float = 0.0
    build_review_working_pct: float = 0.0
    build_review_accepted_pct: float = 0.0
    finalization_pct: float = 0.0


@dataclass
class ProgressSnapshot:
    accepted_pct: float = 0.0
    working_pct: float = 0.0
    displayed_pct: float = 0.0
    inspeqtor_quality_pct: Optional[float] = None
    quality_confidence: str = "unknown"
    confidence: str = "provisional"
    phase: str = "clarification"
    source: str = "hybrid_group_lifecycle"
    components: ProgressComponents = field(default_factory=ProgressComponents)
    groups: List[ProgressGroup] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict matching the read-model spec."""
        return {
            "accepted_pct": round(self.accepted_pct, 1),
            "working_pct": round(self.working_pct, 1),
            "displayed_pct": round(self.displayed_pct, 1),
            "progress_pct": round(self.displayed_pct, 1),  # backward compat
            "inspeqtor_quality_pct": (
                round(self.inspeqtor_quality_pct, 1)
                if self.inspeqtor_quality_pct is not None
                else None
            ),
            "quality_confidence": self.quality_confidence,
            "confidence": self.confidence,
            "phase": self.phase,
            "source": self.source,
            "components": {
                "clarification_pct": round(self.components.clarification_pct, 1),
                "planning_pct": round(self.components.planning_pct, 1),
                "build_review_working_pct": round(self.components.build_review_working_pct, 1),
                "build_review_accepted_pct": round(self.components.build_review_accepted_pct, 1),
                "finalization_pct": round(self.components.finalization_pct, 1),
            },
            "groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "status": g.status,
                    "weight_pct": round(g.weight_pct, 1),
                    "normalized_weight_pct": round(g.normalized_weight_pct, 1),
                    "lifecycle_score": round(g.lifecycle_score, 3),
                    "working_contribution_pct": round(g.working_contribution_pct, 2),
                    "accepted_contribution_pct": round(g.accepted_contribution_pct, 2),
                    "confidence": g.confidence,
                }
                for g in self.groups
            ],
        }


# ---------------------------------------------------------------------------
# Normalize weights
# ---------------------------------------------------------------------------
def _normalize_weights(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure groups have normalized_weight_pct summing to 100.

    Uses explicit progress_weight_pct if available; falls back to equal weights.
    Returns groups with normalized_weight_pct set.
    """
    if not groups:
        return groups

    weights = []
    for g in groups:
        w = g.get("progress_weight_pct")
        if isinstance(w, (int, float)) and w > 0:
            weights.append(w)
        else:
            weights.append(None)

    has_any = any(w is not None for w in weights)

    if has_any:
        # Fill missing with 0, then normalize
        raw = [w if w is not None else 0.0 for w in weights]
        total = sum(raw)
        if total > 0:
            for g, w in zip(groups, raw):
                g["normalized_weight_pct"] = round(w * 100.0 / total, 2)
        else:
            for g in groups:
                g["normalized_weight_pct"] = 0.0
    else:
        n = len(groups)
        if n > 0:
            eq = round(100.0 / n, 2)
            for g in groups:
                g["normalized_weight_pct"] = eq
        else:
            for g in groups:
                g["normalized_weight_pct"] = 0.0

    return groups


# ---------------------------------------------------------------------------
# Phase detection
# ---------------------------------------------------------------------------
def _detect_phase(
    groups: List[Dict[str, Any]],
    active_agent: str,
    final_verdict: Optional[str],
    run_status: str,
) -> str:
    """Determine current phase from run state."""
    if final_verdict == "FULLY_DONE":
        return "finalization"
    if run_status in ("done", "aborted", "failed"):
        return "finalization"

    role = (active_agent or "").lower()
    if role in ("qlarifier", "clarifier"):
        return "clarification"
    if role in ("instruqtor", "instructor"):
        return "planning"
    if role in ("construqtor", "constructor"):
        return "building"
    if role in ("inspeqtor", "inspector"):
        return "building"  # reviewing is part of build_review

    # Fallback: use group statuses
    if not groups:
        return "clarification"

    all_accepted = all(
        _lifecycle_score(g.get("status", "")) >= 1.0 for g in groups
    )
    if all_accepted:
        return "finalization"

    any_building = any(
        g.get("status", "") in ("building", "in_progress", "picked_up",
                                "built", "build_complete")
        for g in groups
    )
    any_review = any(
        g.get("status", "") in ("reviewing", "validating", "inspection",
                                "review_needed", "needs_review")
        for g in groups
    )
    if any_building or any_review:
        return "building"

    return "clarification"


# ---------------------------------------------------------------------------
# Bounding helpers
# ---------------------------------------------------------------------------
def _clamp(val: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, val))


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------
def calculate_progress(
    groups: List[Dict[str, Any]],
    active_agent: str = "",
    final_verdict: Optional[str] = None,
    run_status: str = "running",
    inspeqtor_score: Optional[float] = None,
    phase_weights: Optional[Dict[str, float]] = None,
    clarification_complete: bool = False,
    planning_complete: bool = False,
    finalization_complete: bool = False,
) -> ProgressSnapshot:
    """Calculate canonical multi-layer progress.

    Args:
        groups: List of build group dicts from plan, each with:
            - id, title/name, status
            - progress_weight_pct (optional)
            - briqs list with statuses
        active_agent: Current active agent role.
        final_verdict: FULLY_DONE, BLOCKED, FAILED, or None.
        run_status: running, done, aborted, failed.
        inspeqtor_score: Latest inspeQtor quality score 0..100.
        phase_weights: Override phase weight constants.
        clarification_complete: Qlarifier phase is done.
        planning_complete: instruQtor phase is done.
        finalization_complete: Run is FULLY_DONE.

    Returns:
        ProgressSnapshot with all layers.
    """
    pw = phase_weights or PHASE_WEIGHTS

    # Normalize group weights
    groups = _normalize_weights(groups)

    # Detect phase
    phase = _detect_phase(groups, active_agent, final_verdict, run_status)

    # Infer phase completions
    is_fully_done = final_verdict == "FULLY_DONE"
    if is_fully_done:
        clarification_complete = True
        planning_complete = True
        finalization_complete = True
        # At FULLY_DONE, all groups are considered accepted
        for g in groups:
            g["status"] = "done"
    else:
        # Heuristic phase completion detection
        role = (active_agent or "").lower()
        if role not in ("qlarifier", "clarifier"):
            clarification_complete = True
        if role not in ("qlarifier", "clarifier", "instruqtor", "instructor"):
            planning_complete = True

        # If we have groups, phases preceding build are done
        if groups:
            clarification_complete = True
            planning_complete = True

    # Compute per-group lifecycle contributions
    progress_groups: List[ProgressGroup] = []
    build_review_working_ratio = 0.0
    build_review_accepted_ratio = 0.0

    for g in groups:
        gid = g.get("id", "")
        gname = g.get("title") or g.get("name", gid)
        gstatus = g.get("status", "planned")
        norm_weight = g.get("normalized_weight_pct", 0.0)
        orig_weight = g.get("progress_weight_pct", norm_weight)

        # Compute briq completion ratio
        briqs = g.get("briqs", [])
        briq_ratio = None
        repair_ratio = None
        if briqs:
            total = len(briqs)
            done = sum(
                1 for b in briqs
                if b.get("status") in ("done", "completed", "valid_done",
                                       "fully_done", "success", "merged")
            )
            briq_ratio = done / total if total > 0 else 0.0
            # Repair ratio: count briqs with repair status
            repairing = sum(
                1 for b in briqs
                if b.get("status") in ("repairing", "needs_repair",
                                       "fixing", "adjusting")
            )
            repaired = sum(
                1 for b in briqs
                if b.get("status") in ("done", "completed", "valid_done",
                                       "fully_done", "success", "merged",
                                       "ready_for_review", "build_complete",
                                       "built")
            )
            repair_ratio = repaired / total if total > 0 else 0.0

        # Lifecycle score
        ls = _lifecycle_score(gstatus, briq_ratio, repair_ratio)

        # Confidence per group
        if ls >= 1.0:
            conf = "final"
        elif ls >= 0.70:
            conf = "reviewed"
        elif ls >= 0.10:
            conf = "provisional"
        elif ls > 0:
            conf = "repairing"
        else:
            conf = "provisional"

        # Working contribution = normalized_weight * lifecycle_score / 100
        wc = (norm_weight * ls) / 100.0

        # Accepted contribution = normalized_weight / 100 only if fully accepted
        ac = norm_weight / 100.0 if ls >= 1.0 else 0.0

        progress_groups.append(ProgressGroup(
            id=gid,
            name=gname,
            status=gstatus,
            weight_pct=orig_weight if isinstance(orig_weight, (int, float)) else norm_weight,
            normalized_weight_pct=norm_weight,
            lifecycle_score=ls,
            working_contribution_pct=round(norm_weight * ls, 2),
            accepted_contribution_pct=round(norm_weight if ls >= 1.0 else 0.0, 2),
            confidence=conf,
        ))

        build_review_working_ratio += wc
        build_review_accepted_ratio += ac

    # Clamp ratios
    build_review_working_ratio = _clamp(build_review_working_ratio, 0.0, 1.0)
    build_review_accepted_ratio = _clamp(build_review_accepted_ratio, 0.0, 1.0)

    # Compute components
    cla_pct = pw["clarification"] if clarification_complete else 0.0
    pln_pct = pw["planning"] if planning_complete else 0.0
    fin_pct = pw["finalization"] if finalization_complete else 0.0

    # Build/review components scaled by phase weight
    br_weight = pw["build_review"]
    br_working_pct = br_weight * build_review_working_ratio
    br_accepted_pct = br_weight * build_review_accepted_ratio

    # Overall
    working_pct = cla_pct + pln_pct + br_working_pct + fin_pct
    accepted_pct = cla_pct + pln_pct + br_accepted_pct + fin_pct

    # Clamp
    working_pct = _clamp(working_pct)
    accepted_pct = _clamp(accepted_pct)

    # Displayed
    if is_fully_done:
        displayed_pct = 100.0
    elif run_status in ("failed", "aborted"):
        displayed_pct = _clamp(working_pct)
    else:
        displayed_pct = _clamp(working_pct)

    # Confidence
    if is_fully_done:
        overall_confidence = "final"
    elif run_status == "failed":
        overall_confidence = "failed"
    elif run_status == "aborted":
        overall_confidence = "provisional"
    else:
        # Based on progress_groups
        if all(g.lifecycle_score >= 0.70 for g in progress_groups) if progress_groups else False:
            overall_confidence = "reviewed"
        else:
            overall_confidence = "provisional"

    # InspeQtor quality
    quality = None
    quality_conf = "unknown"
    if inspeqtor_score is not None and isinstance(inspeqtor_score, (int, float)):
        quality = _clamp(float(inspeqtor_score))
        if quality >= 80:
            quality_conf = "high"
        elif quality >= 50:
            quality_conf = "medium"
        else:
            quality_conf = "low"

    return ProgressSnapshot(
        accepted_pct=accepted_pct,
        working_pct=working_pct,
        displayed_pct=displayed_pct,
        inspeqtor_quality_pct=quality,
        quality_confidence=quality_conf,
        confidence=overall_confidence,
        phase=phase,
        source="hybrid_group_lifecycle",
        components=ProgressComponents(
            clarification_pct=cla_pct,
            planning_pct=pln_pct,
            build_review_working_pct=br_working_pct,
            build_review_accepted_pct=br_accepted_pct,
            finalization_pct=fin_pct,
        ),
        groups=progress_groups,
    )


# ---------------------------------------------------------------------------
# Convenience: compute from read-model dict
# ---------------------------------------------------------------------------
def calculate_from_read_model(model: Dict[str, Any]) -> ProgressSnapshot:
    """Compute progress directly from a read-model dict."""
    groups = model.get("build_groups", [])
    run = model.get("run", {})
    metrics = model.get("metrics", {})

    active_agent = run.get("active_agent", "")
    final_verdict = run.get("final_verdict")
    run_status = run.get("status", "running")
    inspeqtor_score = metrics.get("latest_inspeqtor_score")

    # Ensure groups have the normalized weights from the read model
    for g in groups:
        if "normalized_weight_pct" not in g and "progress_weight_pct" in g:
            # Use raw weight; calculate_progress will normalize
            pass

    return calculate_progress(
        groups=groups,
        active_agent=active_agent,
        final_verdict=final_verdict,
        run_status=run_status,
        inspeqtor_score=inspeqtor_score,
    )
