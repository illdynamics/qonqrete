"""Validation verdict semantics: prevent false-success on incomplete validation."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

SUCCESS_VERIFIED = "SUCCESS_VERIFIED"
SUCCESS_LOW_COVERAGE = "SUCCESS_LOW_COVERAGE"
PARTIAL_VALIDATION_DEGRADED = "PARTIAL_VALIDATION_DEGRADED"
FAILED_VALIDATION_INFRA = "FAILED_VALIDATION_INFRA"
FAILED_BLOCKING_VALIDATION = "FAILED_BLOCKING_VALIDATION"
FAILED_BROWSER_E2E = "FAILED_BROWSER_E2E"
FAILED_ACCEPTANCE_CONTRACT = "FAILED_ACCEPTANCE_CONTRACT"

@dataclass
class ValidationVerdict:
    status: str = SUCCESS_VERIFIED
    reasons: list[str] = field(default_factory=list)
    html_files_checked: int = 0
    css_files_checked: int = 0
    js_files_checked: int = 0
    local_asset_references_checked: int = 0
    browser_tests_run: bool = False
    browser_tests_passed: int = 0
    browser_tests_failed: int = 0
    blocking_errors: int = 0
    warnings: int = 0
    advisory_findings: int = 0
    validation_coverage_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "reasons": self.reasons,
            "html_files_checked": self.html_files_checked,
            "css_files_checked": self.css_files_checked,
            "js_files_checked": self.js_files_checked,
            "browser_tests_run": self.browser_tests_run,
            "browser_tests_passed": self.browser_tests_passed,
            "browser_tests_failed": self.browser_tests_failed,
            "blocking_errors": self.blocking_errors,
            "warnings": self.warnings,
            "advisory_findings": self.advisory_findings,
        }

    @property
    def is_success(self) -> bool:
        return self.status in {SUCCESS_VERIFIED, SUCCESS_LOW_COVERAGE}

    @property
    def is_failure(self) -> bool:
        return self.status.startswith("FAILED_")


def resolve_verdict(
    *,
    qualifier_results: list[dict] | None = None,
    smoke_results: dict | None = None,
    browser_required: bool = False,
    browser_available: bool = False,
    browser_ran: bool = False,
    browser_failures: int = 0,
    qualifier_errors: int = 0,
    qualifier_warnings: int = 0,
    html_checked: int = 0,
    css_checked: int = 0,
    js_checked: int = 0,
    contract_present: bool = False,
    infra_crashed: bool = False,
) -> ValidationVerdict:
    """Resolve honest validation verdict.

    Priority: infra crash > blocking errors > contract missing > browser unavailable > browser failed > verified > low coverage.
    """
    verdict = ValidationVerdict()
    verdict.html_files_checked = html_checked
    verdict.css_files_checked = css_checked
    verdict.js_files_checked = js_checked
    verdict.blocking_errors = qualifier_errors
    verdict.warnings = qualifier_warnings
    verdict.browser_tests_run = browser_ran

    # Rule 1: Infra crash (explicit flag)
    if infra_crashed:
        verdict.status = FAILED_VALIDATION_INFRA
        verdict.reasons.append("Validation infrastructure crashed")
        return verdict

    # Rule 2: Blocking deterministic errors ALWAYS win
    if qualifier_errors > 0:
        verdict.status = FAILED_BLOCKING_VALIDATION
        verdict.reasons.append(f"Blocking deterministic validation errors: {qualifier_errors}")
        return verdict

    # Rule 3: Contract required but missing
    if browser_required and not contract_present:
        verdict.status = FAILED_ACCEPTANCE_CONTRACT
        verdict.reasons.append("Browser validation required but no acceptance contract found")
        return verdict

    # Rule 4: Browser required but unavailable
    if browser_required and not browser_available:
        verdict.status = PARTIAL_VALIDATION_DEGRADED
        verdict.reasons.append(
            "Browser validation required but Playwright not installed. "
            "Install: pip install playwright && python3 -m playwright install chromium"
        )
        return verdict

    # Rule 5: Browser required and failed
    if browser_required and browser_ran and browser_failures > 0:
        verdict.status = FAILED_BROWSER_E2E
        verdict.browser_tests_failed = browser_failures
        verdict.reasons.append(f"Browser E2E tests failed: {browser_failures} failure(s)")
        return verdict

    # Rule 6: Browser ran and passed
    if browser_ran and browser_failures == 0:
        verdict.status = SUCCESS_VERIFIED
        verdict.browser_tests_passed = 1
        verdict.reasons.append("All validation layers passed including browser E2E")
        return verdict

    # Rule 7: Deterministic clean (no browser requirement)
    if qualifier_errors == 0 and qualifier_warnings == 0:
        verdict.status = SUCCESS_VERIFIED
        verdict.reasons.append("Deterministic validation clean")
        return verdict

    # Rule 8: Warnings only, no blocking errors
    if qualifier_warnings > 0 and qualifier_errors == 0:
        verdict.status = SUCCESS_LOW_COVERAGE
        verdict.reasons.append(f"Warnings present ({qualifier_warnings}) but no blocking errors")
        return verdict

    verdict.status = PARTIAL_VALIDATION_DEGRADED
    verdict.reasons.append("Validation coverage incomplete")
    return verdict


__all__ = [
    "SUCCESS_VERIFIED", "SUCCESS_LOW_COVERAGE", "PARTIAL_VALIDATION_DEGRADED",
    "FAILED_VALIDATION_INFRA", "FAILED_BLOCKING_VALIDATION",
    "FAILED_BROWSER_E2E", "FAILED_ACCEPTANCE_CONTRACT",
    "ValidationVerdict", "resolve_verdict",
]
