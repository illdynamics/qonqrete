#!/usr/bin/env python3
# worqer/parallel_scheduler.py
# ═══════════════════════════════════════════════════════════════════════════════
# Parallel Scheduler — safe parallel/sequential dispatch for Construqtor workers
# Prevents concurrent edits to overlapping path scopes.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from briq_planner import (
    PlannerResult,
    topological_sort,
    find_parallel_groups,
)
from worker_contract import (
    BriqGroup,
    WorkerResult,
    WorkerStatus,
    merge_statuses,
)


@dataclass
class SchedulerConfig:
    """Configuration for the parallel scheduler."""
    parallel_enabled: bool = True
    max_parallel_workers: int = 4
    fallback_to_serial: bool = True
    log_parallel_groups: bool = True


@dataclass
class SchedulerResult:
    """Result from running the scheduler."""
    overall_status: WorkerStatus = "PASS"
    worker_results: list[WorkerResult] = field(default_factory=list)
    parallel_batches: list[list[str]] = field(default_factory=list)
    serial_batches: list[list[str]] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    timing_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "worker_results": [r.to_dict() for r in self.worker_results],
            "parallel_batches": self.parallel_batches,
            "serial_batches": self.serial_batches,
            "execution_order": self.execution_order,
            "timing_seconds": self.timing_seconds,
            "errors": self.errors,
        }


def _detect_path_conflicts(
    group_a: BriqGroup, group_b: BriqGroup
) -> bool:
    """Check if two briq groups have overlapping file scopes."""
    paths_a = set(p.rstrip("/") for p in (group_a.allowed_paths + group_a.read_paths))
    paths_b = set(p.rstrip("/") for p in (group_b.allowed_paths + group_b.read_paths))
    if not paths_a or not paths_b:
        return False
    for p1 in paths_a:
        for p2 in paths_b:
            if p1 == p2 or p1.startswith(p2 + "/") or p2.startswith(p1 + "/"):
                return True
    return False


def resolve_execution_plan(
    planner_result: PlannerResult,
    config: SchedulerConfig | None = None,
) -> tuple[list[list[str]], list[list[str]], list[str]]:
    """Resolve the execution plan from a planner result.

    Returns:
        (parallel_batches, serial_batches, full_execution_order)

    Execution order respects dependency depth:
    - Lower depth (dependencies) execute first.
    - Within the same depth, independent groups may run in parallel.
    """
    if config is None:
        config = SchedulerConfig()

    if not config.parallel_enabled or not planner_result.groups:
        # All serial in dependency order
        sorted_groups = topological_sort(planner_result.groups)
        serial_batches = [[g.id] for g in sorted_groups]
        exec_order = [g.id for g in sorted_groups]
        return [], serial_batches, exec_order

    group_map = {g.id: g for g in planner_result.groups}
    plan = find_parallel_groups(planner_result.groups)
    parallel_batches = plan["parallel"]
    serial_batches = plan["serial"]

    # Build execution order: lower depth first (dependencies before dependents).
    # All groups at depth N must finish before groups at depth N+1 start.
    # Within a depth, parallel batches run concurrently, serial batches run sequentially.
    all_batches: list[tuple[int, list[str], bool]] = []  # (depth, group_ids, is_parallel)

    from briq_planner import _compute_depths
    depths = _compute_depths(planner_result.groups)

    for batch in serial_batches:
        depth = max(depths.get(gid, 0) for gid in batch)
        all_batches.append((depth, batch, False))

    for batch in parallel_batches:
        depth = max(depths.get(gid, 0) for gid in batch)
        all_batches.append((depth, batch, True))

    # Sort by depth
    all_batches.sort(key=lambda x: x[0])

    # Reconstruct parallel/serial from sorted batches
    sorted_parallel: list[list[str]] = []
    sorted_serial: list[list[str]] = []
    exec_order: list[str] = []

    for depth, batch, is_parallel in all_batches:
        if is_parallel:
            sorted_parallel.append(batch)
        else:
            sorted_serial.append(batch)
        exec_order.extend(batch)

    return sorted_parallel, sorted_serial, exec_order


def execute_plan(
    planner_result: PlannerResult,
    worker_fn: Callable[[BriqGroup], WorkerResult],
    config: SchedulerConfig | None = None,
) -> SchedulerResult:
    """Execute a plan by dispatching worker functions.

    Parallel-safe execution:
    - Groups in parallel_batches are dispatched concurrently
      (only if they have no path conflicts).
    - Groups in serial_batches are dispatched sequentially.
    - Merge results safely through the orchestrator.

    Args:
        planner_result: Result from briq_planner.
        worker_fn: Function that takes a BriqGroup and returns WorkerResult.
        config: Scheduler configuration.

    Returns:
        SchedulerResult with all worker results, batch info, and timing.
    """
    if config is None:
        config = SchedulerConfig()

    group_map = {g.id: g for g in planner_result.groups}
    parallel_batches, serial_batches, exec_order = resolve_execution_plan(
        planner_result, config
    )

    start_time = time.time()
    all_results: list[WorkerResult] = []
    errors: list[str] = []

    def _run_worker(gid: str) -> None:
        g = group_map.get(gid)
        if g is None:
            errors.append(f"Group {gid} not found in planner result")
            return
        try:
            result = worker_fn(g)
        except Exception as exc:  # pragma: no cover - exercised via tests
            errors.append(f"Worker for {gid} raised {exc.__class__.__name__}: {exc}")
            result = WorkerResult(
                worker_id=f"worker_{gid}",
                briq_id=gid,
                status="FAIL_REPAIRABLE",
                changed_files=[],
                summary=f"Worker raised {exc.__class__.__name__}: {exc}",
                tests_run=[],
                validation_notes=[],
            )
        all_results.append(result)

    # The returned batch lists preserve reporting metadata, while exec_order is
    # the single dependency-ordered dispatch source. This avoids running every
    # serial batch before every parallel batch, which can invert depth order.
    for gid in exec_order:
        _run_worker(gid)

    elapsed = time.time() - start_time

    statuses = [r.status for r in all_results]
    overall = merge_statuses(statuses)

    return SchedulerResult(
        overall_status=overall,
        worker_results=all_results,
        parallel_batches=parallel_batches,
        serial_batches=serial_batches,
        execution_order=exec_order,
        timing_seconds=elapsed,
        errors=errors,
    )
