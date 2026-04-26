# worqer/smoqetester/models.py
# ═══════════════════════════════════════════════════════════════════════════════
# Data models for deterministic smoketest reporting.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"
STATUS_ERROR = "ERROR"
EXECUTION_KIND_STATIC = "static_probe"
EXECUTION_KIND_SYNTAX = "syntax_probe"
EXECUTION_KIND_PROCESS_BOOT = "process_boot"
EXECUTION_KIND_HTTP = "http_probe"
EXECUTION_KIND_WS = "ws_probe"
EXECUTION_KIND_BROWSER = "browser_probe"
EXECUTION_KIND_EXECUTED = "executed"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

_VALID_STATUSES = {STATUS_PASS, STATUS_FAIL, STATUS_SKIP, STATUS_ERROR}

_VALID_EXECUTION_KINDS = {
    EXECUTION_KIND_STATIC,
    EXECUTION_KIND_SYNTAX,
    EXECUTION_KIND_PROCESS_BOOT,
    EXECUTION_KIND_HTTP,
    EXECUTION_KIND_WS,
    EXECUTION_KIND_BROWSER,
    EXECUTION_KIND_EXECUTED,
}
_VALID_SEVERITIES = {SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR}


@dataclass
class SmoketestResult:
    """One normalized smoketest check outcome."""

    adapter: str
    name: str
    status: str
    executed: bool
    message: str
    execution_kind: str = EXECUTION_KIND_STATIC
    file: Optional[str] = None
    files: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    scope: Optional[str] = None
    command: str = ""
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    severity: str = SEVERITY_INFO
    stdout: str = ""
    stderr: str = ""
    failure_kind: Optional[str] = None
    missing_module: Optional[str] = None
    environment_blocked: bool = False

    def normalized_status(self) -> str:
        raw = str(self.status or "").strip().upper()
        if raw in _VALID_STATUSES:
            return raw
        return STATUS_ERROR

    def normalized_execution_kind(self) -> str:
        raw = str(self.execution_kind or "").strip().lower()
        if raw in _VALID_EXECUTION_KINDS:
            return raw
        return EXECUTION_KIND_EXECUTED if bool(self.executed) else EXECUTION_KIND_STATIC

    def normalized_severity(self) -> str:
        raw = str(self.severity or "").strip().lower()
        if raw in _VALID_SEVERITIES:
            return raw
        status = self.normalized_status()
        if status in {STATUS_FAIL, STATUS_ERROR}:
            return SEVERITY_ERROR
        return SEVERITY_INFO

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "name": self.name,
            "status": self.normalized_status(),
            "executed": bool(self.executed),
            "execution_kind": self.normalized_execution_kind(),
            "message": self.message,
            "file": self.file,
            "files": list(self.files or []),
            "related_files": list(self.related_files or []),
            "scope": self.scope,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "severity": self.normalized_severity(),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "failure_kind": self.failure_kind,
            "missing_module": self.missing_module,
            "environment_blocked": bool(self.environment_blocked),
        }


@dataclass
class SmoketestReport:
    """Aggregate smoketest report for one cycle."""

    cycle_num: str
    mode: str
    enabled: bool
    total_files: int = 0
    files_checked: int = 0
    results: list[SmoketestResult] = field(default_factory=list)
    adapters_triggered: list[str] = field(default_factory=list)
    commands_executed: int = 0
    commands_skipped: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    executed_count: int = 0
    static_count: int = 0
    syntax_count: int = 0
    boot_count: int = 0
    http_count: int = 0
    ws_count: int = 0
    browser_count: int = 0
    _files_seen: set[str] = field(default_factory=set, init=False, repr=False)

    @property
    def overall_status(self) -> str:
        if self.failed > 0 or self.errors > 0:
            return "FAIL"
        if self.warnings > 0:
            return "PARTIAL"
        if self.enabled and (self.executed_count + self.static_count + self.syntax_count + self.boot_count + self.http_count + self.ws_count + self.browser_count == 0):
            return "PARTIAL"
        if self.commands_skipped > 0:
            return "PARTIAL"
        return "PASS"

    @property
    def executed(self) -> int:
        """Backward-compatible alias for legacy callers.
        Now includes all forms of runtime activity.
        """
        return self.executed_count + self.boot_count + self.http_count + self.ws_count + self.browser_count

    @property
    def has_executed_evidence(self) -> bool:
        """True when this cycle produced at least one genuine executed result.

        A subprocess running successfully is NOT enough; the result must have
        an execution_kind that exercises runtime behavior and not be a SKIP.
        """
        return self.executed > 0

    @property
    def has_static_evidence(self) -> bool:
        """True when this cycle produced at least one non-skipped static or syntax result."""
        return self.static_count > 0 or self.syntax_count > 0

    @property
    def validation_mode_contribution(self) -> str:
        """How this smoketest report alone would vote on validation mode.

        - "none":        no evidence at all (disabled, empty scope, all skipped)
        - "static-only": only static-kind evidence observed
        - "executed":    only executed-kind evidence observed
        - "mixed":       both static and executed evidence observed
        """
        if self.has_executed_evidence and self.has_static_evidence:
            return "mixed"
        if self.has_executed_evidence:
            return "executed"
        if self.has_static_evidence:
            return "static-only"
        return "none"

    def add_result(self, result: SmoketestResult) -> None:
        self.results.append(result)
        status = result.normalized_status()
        kind = result.normalized_execution_kind()
        severity = result.normalized_severity()
        if result.command:
            if status == STATUS_SKIP:
                self.commands_skipped += 1
            elif result.duration_ms is not None or status in {STATUS_PASS, STATUS_FAIL, STATUS_ERROR}:
                self.commands_executed += 1
        if status != STATUS_SKIP:
            if kind == EXECUTION_KIND_EXECUTED:
                self.executed_count += 1
            elif kind == EXECUTION_KIND_PROCESS_BOOT:
                self.boot_count += 1
            elif kind == EXECUTION_KIND_HTTP:
                self.http_count += 1
            elif kind == EXECUTION_KIND_WS:
                self.ws_count += 1
            elif kind == EXECUTION_KIND_BROWSER:
                self.browser_count += 1
            elif kind == EXECUTION_KIND_SYNTAX:
                self.syntax_count += 1
            elif kind == EXECUTION_KIND_STATIC:
                self.static_count += 1
        if status == STATUS_PASS:
            self.passed += 1
        elif status == STATUS_FAIL:
            self.failed += 1
        elif status == STATUS_SKIP:
            self.skipped += 1
        else:
            self.errors += 1
        if severity == SEVERITY_WARNING:
            self.warnings += 1

        candidate_files: list[str] = []
        if result.file:
            candidate_files.append(result.file)
        candidate_files.extend(result.files or [])
        candidate_files.extend(result.related_files or [])
        for item in candidate_files:
            normalized = str(item or "").strip()
            if normalized:
                self._files_seen.add(normalized)
        self.files_checked = len(self._files_seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": str(self.cycle_num),
            "mode": self.mode,
            "enabled": bool(self.enabled),
            "overall_status": self.overall_status,
            "total_files": int(self.total_files),
            "files_checked": int(self.files_checked),
            "commands_executed": int(self.commands_executed),
            "commands_skipped": int(self.commands_skipped),
            "passed": self.passed,
            "warnings": self.warnings,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "executed_count": self.executed_count,
            "static_count": self.static_count,
            "syntax_count": self.syntax_count,
            "boot_count": self.boot_count,
            "http_count": self.http_count,
            "ws_count": self.ws_count,
            "browser_count": self.browser_count,
            "executed": self.executed,  # Backward-compatible key.
            "has_executed_evidence": self.has_executed_evidence,
            "has_static_evidence": self.has_static_evidence,
            "validation_mode_contribution": self.validation_mode_contribution,
            "adapters_triggered": sorted(set(self.adapters_triggered)),
            "results": [item.to_dict() for item in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Smoketest Report - CyQle {self.cycle_num}",
            "",
            f"- Enabled: {'yes' if self.enabled else 'no'}",
            f"- Mode: {self.mode}",
            f"- Overall Status: {self.overall_status}",
            f"- Validation Mode Contribution: {self.validation_mode_contribution}",
            f"- Total Files: {self.total_files}",
            f"- Files Checked: {self.files_checked}",
            f"- Commands Executed: {self.commands_executed}",
            f"- Commands Skipped: {self.commands_skipped}",
            f"- Executed (Runtime): {self.executed}",
            f"- Static/Syntax: {self.static_count + self.syntax_count}",
            f"- Has Executed Evidence: {'yes' if self.has_executed_evidence else 'no'}",
            f"- Has Static Evidence: {'yes' if self.has_static_evidence else 'no'}",
            f"- Passed: {self.passed}",
            f"- Warnings: {self.warnings}",
            f"- Failed: {self.failed}",
            f"- Skipped: {self.skipped}",
            f"- Errors: {self.errors}",
            f"- Adapters: {', '.join(sorted(set(self.adapters_triggered))) if self.adapters_triggered else 'None'}",
            "",
            "## Results",
        ]
        if not self.results:
            lines.append("- None")
            lines.append("")
            return "\n".join(lines)

        for result in self.results:
            status = result.normalized_status()
            lines.append(
                f"- [{status}] {result.adapter}:{result.name} "
                f"(execution_kind={result.normalized_execution_kind()}, "
                f"executed={'yes' if result.executed else 'no'}, "
                f"severity={result.normalized_severity()}) - {result.message}"
            )
            if result.file:
                lines.append(f"  - file: `{result.file}`")
            if result.files:
                lines.append("  - files: " + ", ".join(f"`{item}`" for item in result.files))
            if result.related_files:
                lines.append("  - related_files: " + ", ".join(f"`{item}`" for item in result.related_files))
            if result.scope:
                lines.append(f"  - scope: `{result.scope}`")
            if result.command:
                lines.append(f"  - command: `{result.command}`")
            if result.exit_code is not None:
                lines.append(f"  - exit_code: {result.exit_code}")
            if result.duration_ms is not None:
                lines.append(f"  - duration_ms: {result.duration_ms}")
            if result.stdout:
                lines.append("  - stdout:")
                lines.append("```text")
                lines.append(result.stdout)
                lines.append("```")
            if result.stderr:
                lines.append("  - stderr:")
                lines.append("```text")
                lines.append(result.stderr)
                lines.append("```")

        lines.append("")
        return "\n".join(lines)


__all__ = [
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_SKIP",
    "STATUS_ERROR",
    "EXECUTION_KIND_STATIC",
    "EXECUTION_KIND_SYNTAX",
    "EXECUTION_KIND_PROCESS_BOOT",
    "EXECUTION_KIND_HTTP",
    "EXECUTION_KIND_WS",
    "EXECUTION_KIND_BROWSER",
    "EXECUTION_KIND_EXECUTED",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SEVERITY_ERROR",
    "SmoketestResult",
    "SmoketestReport",
]
