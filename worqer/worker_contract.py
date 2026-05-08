#!/usr/bin/env python3
# worqer/worker_contract.py
# ═══════════════════════════════════════════════════════════════════════════════
# Worker Contract — typed structures for Construqtor briq workers
# Model-agnostic, JSON-compatible contracts for the QonQrete swarm.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Literal


# ── Status types ──────────────────────────────────────────────────────────
WorkerStatus = Literal[
    "PASS",
    "PASS_WITH_WARNINGS",
    "FAIL_REPAIRABLE",
    "FAIL_REBUILD_REQUIRED",
    "BLOCKED",
]

VALID_STATUSES: frozenset[str] = frozenset({
    "PASS",
    "PASS_WITH_WARNINGS",
    "FAIL_REPAIRABLE",
    "FAIL_REBUILD_REQUIRED",
    "BLOCKED",
})


# ── Briq group spec (output of planner, input to workers) ─────────────────
@dataclass
class BriqGroup:
    """A single briq group in the dependency/parallelism graph."""
    id: str
    name: str
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    read_paths: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    parallel_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BriqGroup:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Worker result contract ────────────────────────────────────────────────
@dataclass
class SelfReview:
    issues_found: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    remaining_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelfReview:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WorkerResult:
    """Structured result from a Construqtor worker."""
    worker_id: str
    briq_id: str
    status: WorkerStatus = "PASS"
    changed_files: list[str] = field(default_factory=list)
    summary: str = ""
    self_review: SelfReview | None = None
    tests_run: list[str] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "worker_id": self.worker_id,
            "briq_id": self.briq_id,
            "status": self.status,
            "changed_files": self.changed_files,
            "summary": self.summary,
            "tests_run": self.tests_run,
            "validation_notes": self.validation_notes,
        }
        if self.self_review is not None:
            d["self_review"] = self.self_review.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerResult:
        sr = data.get("self_review")
        self_review = SelfReview.from_dict(sr) if isinstance(sr, dict) else None
        return cls(
            worker_id=data.get("worker_id", ""),
            briq_id=data.get("briq_id", ""),
            status=data.get("status", "PASS"),
            changed_files=data.get("changed_files", []),
            summary=data.get("summary", ""),
            self_review=self_review,
            tests_run=data.get("tests_run", []),
            validation_notes=data.get("validation_notes", []),
        )

    def is_success(self) -> bool:
        return self.status in ("PASS", "PASS_WITH_WARNINGS")

    def is_failure(self) -> bool:
        return self.status in ("FAIL_REPAIRABLE", "FAIL_REBUILD_REQUIRED", "BLOCKED")


# ── Sqrewdriver validation result ─────────────────────────────────────────
@dataclass
class SqrewdriverFinding:
    source: str = ""
    file: str = ""
    message: str = ""
    severity: Literal["info", "warning", "error"] = "info"
    repair_suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SqrewdriverFinding:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SqrewdriverResult:
    status: WorkerStatus = "PASS"
    findings: list[SqrewdriverFinding] = field(default_factory=list)
    repair_suggestions: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "repair_suggestions": self.repair_suggestions,
            "commands_run": self.commands_run,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SqrewdriverResult:
        return cls(
            status=data.get("status", "PASS"),
            findings=[SqrewdriverFinding.from_dict(f) for f in data.get("findings", [])],
            repair_suggestions=data.get("repair_suggestions", []),
            commands_run=data.get("commands_run", []),
        )


# ── Inspeqtor validation result ───────────────────────────────────────────
@dataclass
class InspeqtorFinding:
    check_id: str = ""
    severity: Literal["info", "warning", "error", "critical"] = "info"
    message: str = ""
    file: str = ""
    required_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InspeqtorFinding:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class InspeqtorResult:
    status: WorkerStatus = "PASS"
    findings: list[InspeqtorFinding] = field(default_factory=list)
    acceptance_checked: list[str] = field(default_factory=list)
    security_issues: list[str] = field(default_factory=list)
    consistency_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "acceptance_checked": self.acceptance_checked,
            "security_issues": self.security_issues,
            "consistency_issues": self.consistency_issues,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InspeqtorResult:
        return cls(
            status=data.get("status", "PASS"),
            findings=[InspeqtorFinding.from_dict(f) for f in data.get("findings", [])],
            acceptance_checked=data.get("acceptance_checked", []),
            security_issues=data.get("security_issues", []),
            consistency_issues=data.get("consistency_issues", []),
        )


# ── Orchestrator run result ───────────────────────────────────────────────
@dataclass
class OrchestratorRunResult:
    """Top-level result from a full Codeseeq orchestration run."""
    overall_status: WorkerStatus = "PASS"
    planner_status: WorkerStatus = "PASS"
    worker_results: list[WorkerResult] = field(default_factory=list)
    sqrewdriver_result: SqrewdriverResult | None = None
    inspeqtor_result: InspeqtorResult | None = None
    parallel_groups: list[list[str]] = field(default_factory=list)
    serial_groups: list[list[str]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "planner_status": self.planner_status,
            "worker_results": [w.to_dict() for w in self.worker_results],
            "sqrewdriver_result": self.sqrewdriver_result.to_dict() if self.sqrewdriver_result else None,
            "inspeqtor_result": self.inspeqtor_result.to_dict() if self.inspeqtor_result else None,
            "parallel_groups": self.parallel_groups,
            "serial_groups": self.serial_groups,
            "validation_errors": self.validation_errors,
        }


# ── Helpers ───────────────────────────────────────────────────────────────
def validate_worker_status(value: str) -> WorkerStatus:
    """Validate and normalize a status string."""
    v = value.strip().upper()
    if v in VALID_STATUSES:
        return v  # type: ignore
    return "FAIL_REBUILD_REQUIRED"


def worker_status_from_bool(ok: bool) -> WorkerStatus:
    return "PASS" if ok else "FAIL_REPAIRABLE"


def merge_statuses(statuses: list[WorkerStatus]) -> WorkerStatus:
    """Merge multiple statuses: worst wins."""
    severity = ["PASS", "PASS_WITH_WARNINGS", "FAIL_REPAIRABLE", "FAIL_REBUILD_REQUIRED", "BLOCKED"]
    max_idx = 0
    for s in statuses:
        try:
            idx = severity.index(s)
            if idx > max_idx:
                max_idx = idx
        except ValueError:
            max_idx = max(max_idx, 3)  # FAIL_REBUILD_REQUIRED for unknown
    return severity[max_idx]  # type: ignore
