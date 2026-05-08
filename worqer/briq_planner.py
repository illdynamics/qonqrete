#!/usr/bin/env python3
# worqer/briq_planner.py
# ═══════════════════════════════════════════════════════════════════════════════
# Briq Planner — dependency-aware task decomposition
# Breaks a task into structured briq groups with dependency and
# parallel-safety metadata. Model-agnostic.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from worker_contract import BriqGroup, WorkerStatus, validate_worker_status


# ── Planner result ────────────────────────────────────────────────────────
@dataclass
class PlannerResult:
    status: WorkerStatus = "PASS"
    groups: list[BriqGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "groups": [g.to_dict() for g in self.groups],
            "warnings": self.warnings,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlannerResult:
        return cls(
            status=validate_worker_status(data.get("status", "PASS")),
            groups=[BriqGroup.from_dict(g) for g in data.get("groups", [])],
            warnings=data.get("warnings", []),
            errors=data.get("errors", []),
        )


# ── Dependency graph utilities ────────────────────────────────────────────
def topological_sort(groups: list[BriqGroup]) -> list[BriqGroup]:
    """Topological sort of briq groups by depends_on.
    Returns groups in dependency order (dependencies first).
    Raises ValueError on cycle.
    """
    group_map = {g.id: g for g in groups}
    visited: set[str] = set()
    in_stack: set[str] = set()
    order: list[BriqGroup] = []

    def _visit(gid: str) -> None:
        if gid in in_stack:
            deps = [g.id for g in order] if order else []
            raise ValueError(f"Circular dependency detected involving briq '{gid}'. Current order: {deps}")
        if gid in visited:
            return
        visited.add(gid)
        in_stack.add(gid)
        g = group_map.get(gid)
        if g:
            for dep in g.depends_on:
                if dep in group_map:
                    _visit(dep)
                # missing dep is a warning, not a hard error
        in_stack.discard(gid)
        if g:
            order.append(g)

    for g in groups:
        if g.id not in visited:
            _visit(g.id)

    return order


def find_parallel_groups(groups: list[BriqGroup]) -> dict[str, list[list[str]]]:
    """Find which briq groups can run in parallel vs serial.

    Returns:
        {"parallel": [[...group ids per parallel batch...]],
         "serial": [[...group ids per serial batch...]]}

    Rules:
    - Groups with no dependency on each other AND no overlapping allowed_paths
      can run in parallel.
    - Groups with dependencies must run serially (dependency first).
    - Groups with overlapping path scopes cannot run in parallel (merge conflict
      prevention).
    """
    sorted_groups = topological_sort(groups)
    group_map = {g.id: g for g in sorted_groups}

    # Build a dependency index: for each group, all groups it transitively depends on
    def _transitive_deps(gid: str, seen: set[str] | None = None) -> set[str]:
        if seen is None:
            seen = set()
        deps: set[str] = set()
        g = group_map.get(gid)
        if g:
            for dep in g.depends_on:
                if dep not in seen and dep in group_map:
                    seen.add(dep)
                    deps.add(dep)
                    deps.update(_transitive_deps(dep, seen))
        return deps

    transitive_deps: dict[str, set[str]] = {}
    for g in sorted_groups:
        transitive_deps[g.id] = _transitive_deps(g.id)

    # Path scope sets for conflict detection
    def _path_scope(g: BriqGroup) -> set[str]:
        return set(p.rstrip("/") for p in (g.allowed_paths + g.read_paths))

    path_scopes = {g.id: _path_scope(g) for g in sorted_groups}

    # Check if two groups have overlapping path scopes
    def _paths_overlap(gid1: str, gid2: str) -> bool:
        s1 = path_scopes.get(gid1, set())
        s2 = path_scopes.get(gid2, set())
        if not s1 or not s2:
            return False  # no scope = no conflict
        # Overlap if any path in one is a prefix of any path in the other
        for p1 in s1:
            for p2 in s2:
                if p1 == p2 or p1.startswith(p2 + "/") or p2.startswith(p1 + "/"):
                    return True
        return False

    # Batch by layers: all groups at the same dependency depth can be parallel
    # if they don't have overlapping path scopes.
    def _dependency_depth(gid: str) -> int:
        deps = transitive_deps.get(gid, set())
        if not deps:
            return 0
        return 1 + max((_dependency_depth(d) for d in deps), default=0)

    depth_groups: dict[int, list[str]] = {}
    for g in sorted_groups:
        d = _dependency_depth(g.id)
        depth_groups.setdefault(d, []).append(g.id)

    parallel_batches: list[list[str]] = []
    serial_batches: list[list[str]] = []

    for depth in sorted(depth_groups.keys()):
        batch_ids = depth_groups[depth]
        if len(batch_ids) <= 1:
            # Single group at this depth => serial batch
            serial_batches.append(batch_ids)
            continue

        # Try to parallelize: group non-conflicting groups together
        used: set[str] = set()
        for gid in batch_ids:
            if gid in used:
                continue
            # Find all groups that can run in parallel with this one
            parallel_group = [gid]
            used.add(gid)
            for other in batch_ids:
                if other not in used:
                    g = group_map.get(other)
                    if g and g.parallel_safe:
                        # Check no path conflict with already-assigned group members
                        conflict = False
                        for member in parallel_group:
                            if _paths_overlap(member, other):
                                conflict = True
                                break
                        if not conflict:
                            parallel_group.append(other)
                            used.add(other)
            if len(parallel_group) > 1:
                parallel_batches.append(parallel_group)
            else:
                serial_batches.append(parallel_group)

    return {"parallel": parallel_batches, "serial": serial_batches}


# ── Planner (task → briq groups) ─────────────────────────────────────────
def plan_from_task_file(task_path: str | Path) -> PlannerResult:
    """Parse a task file and produce a planned briq group breakdown.

    This is a heuristic planner. For production use, Instruqtor generates
    the full briq breakdown. This function provides a fallback for
    simple/medium tasks where AI-based planning is not available.
    """
    task_path = Path(task_path)
    if not task_path.exists():
        return PlannerResult(
            status="FAIL_REPAIRABLE",
            errors=[f"Task file not found: {task_path}"],
        )

    task_text = task_path.read_text(encoding="utf-8")
    return _plan_from_text(task_text, task_path.name)


def _plan_from_text(task_text: str, source_name: str = "task") -> PlannerResult:
    """Heuristic planner: parse a task markdown into briq groups."""
    groups: list[BriqGroup] = []
    warnings: list[str] = []

    lines = task_text.splitlines()

    # Detect file requirements from task
    file_refs: list[str] = []
    in_code_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        # Match file references like `file.py`, `file.css`, `file.html`
        for m in re.finditer(r'`([^\s]+\.\w+)`', line):
            file_refs.append(m.group(1))

    # Group files by type
    html_files = [f for f in file_refs if f.endswith((".html", ".htm"))]
    css_files = [f for f in file_refs if f.endswith(".css")]
    js_files = [f for f in file_refs if f.endswith((".js", ".jsx", ".ts", ".tsx"))]
    py_files = [f for f in file_refs if f.endswith(".py")]
    other_files = [f for f in file_refs if f not in html_files + css_files + js_files + py_files]

    # Create briq groups
    if html_files:
        groups.append(BriqGroup(
            id="html_structure",
            name="HTML Structure",
            description="Create HTML markup for the application",
            depends_on=[],
            allowed_paths=html_files,
            read_paths=[source_name],
            acceptance=[f"Create {', '.join(html_files)} with proper structure"],
            parallel_safe=True,
        ))

    if css_files:
        deps = []
        if html_files:
            deps.append("html_structure")
        groups.append(BriqGroup(
            id="css_styling",
            name="CSS Styling",
            description="Create CSS stylesheets for the application",
            depends_on=deps,
            allowed_paths=css_files,
            read_paths=[source_name] + html_files,
            acceptance=[f"Create {', '.join(css_files)} with proper styling"],
            parallel_safe=not bool(deps),
        ))

    if js_files:
        deps = []
        if html_files:
            deps.append("html_structure")
        groups.append(BriqGroup(
            id="js_logic",
            name="JavaScript Logic",
            description="Create JavaScript logic for the application",
            depends_on=deps,
            allowed_paths=js_files,
            read_paths=[source_name] + html_files + css_files,
            acceptance=[f"Create {', '.join(js_files)} with proper logic"],
            parallel_safe=not bool(deps),
        ))

    if py_files:
        deps = []
        if html_files:
            deps.append("html_structure")
        groups.append(BriqGroup(
            id="python_backend",
            name="Python Backend",
            description="Create Python backend files",
            depends_on=deps,
            allowed_paths=py_files,
            read_paths=[source_name],
            acceptance=[f"Create {', '.join(py_files)} with proper implementation"],
            parallel_safe=not bool(deps),
        ))

    if other_files:
        groups.append(BriqGroup(
            id="config_and_support",
            name="Config and Support Files",
            description="Create configuration and support files",
            depends_on=[],
            allowed_paths=other_files,
            read_paths=[source_name],
            acceptance=[f"Create {', '.join(other_files)}"],
            parallel_safe=True,
        ))

    if not groups:
        # Fallback: if no file refs found, create a single monolithic group
        groups.append(BriqGroup(
            id="main_implementation",
            name="Main Implementation",
            description="Complete implementation from task",
            depends_on=[],
            allowed_paths=["."],
            read_paths=[source_name],
            acceptance=["Implement the task as specified"],
            parallel_safe=False,
        ))
        warnings.append("No file references found; using monolithic group")

    # Run topological sort to validate
    try:
        topological_sort(groups)
    except ValueError as e:
        return PlannerResult(
            status="FAIL_REPAIRABLE",
            groups=groups,
            errors=[str(e)],
            warnings=warnings + ["Dependency cycle detected"],
        )

    return PlannerResult(
        status="PASS",
        groups=groups,
        warnings=warnings,
    )


def plan_to_json(result: PlannerResult, indent: int = 2) -> str:
    """Serialize a PlannerResult to JSON."""
    return json.dumps(result.to_dict(), indent=indent)


def _compute_depths(groups: list[BriqGroup]) -> dict[str, int]:
    """Compute dependency depth for each briq group.
    
    Depth 0 = no dependencies.
    Depth N = depends on at least one group at depth N-1.
    """
    group_map = {g.id: g for g in groups}
    depths: dict[str, int] = {}

    def _depth(gid: str, seen: set[str] | None = None) -> int:
        if gid in depths:
            return depths[gid]
        if seen is None:
            seen = set()
        if gid in seen:
            return 0  # cycle protection
        seen.add(gid)
        g = group_map.get(gid)
        if not g or not g.depends_on:
            depths[gid] = 0
            return 0
        max_dep = 0
        for dep in g.depends_on:
            if dep in group_map:
                d = _depth(dep, seen)
                max_dep = max(max_dep, d + 1)
        depths[gid] = max_dep
        return max_dep

    for g in groups:
        _depth(g.id)

    return depths
