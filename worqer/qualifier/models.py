# worqer/qualifier/models.py
# ═══════════════════════════════════════════════════════════════════════════════
# Qualifier data models
#
# Public API:
#   - VerificationResult  — one normalized check outcome
#   - VerificationReport  — aggregate report for a cycle
#
# These shapes are the stable contract consumed by InspeQtor (see
# worqer/inspeqtor.py — structured verdict + meta-prompt + reqap formatter).
# Adding new adapters must NOT change these shapes; all adapters emit
# `VerificationResult` values into the shared report.
# ═══════════════════════════════════════════════════════════════════════════════
from dataclasses import dataclass, field
from typing import Optional


# Valid severity values. 'info' is new in the refactor and is used for
# non-blocking advisory results (e.g. a tool was not available on PATH).
# 'info' results are displayed in the report but do NOT affect pass/warn/err
# tallies or the overall status — they are observational only.
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


def default_frontend_validation_summary() -> dict:
    return {
        "html_files_checked": 0,
        "css_files_checked": 0,
        "js_files_checked": 0,
        "local_asset_references_checked": 0,
        "blocking_errors": 0,
        "warnings": 0,
        "advisory_findings": 0,
        "validation_coverage_summary": "no_frontend_files_checked",
    }


@dataclass
class VerificationResult:
    """Result of a single verification check.

    Fields are intentionally kept identical to the v1.3.0 monolith so that
    InspeQtor's structured-verdict consumers (check_id="qualification") and
    the reqap formatter continue to work unchanged.
    """

    file_path: str
    # check_type is a short slug describing the check. Historical values are
    # 'syntax' | 'import' | 'signature' | 'call'. New adapters use namespaced
    # slugs like 'python:ruff', 'shell:shellcheck', 'js_ts:biome',
    # 'html_css:html-validate' so that consumers can still group by source.
    check_type: str
    passed: bool
    message: str
    line_number: Optional[int] = None
    severity: str = SEVERITY_ERROR  # 'error' | 'warning' | 'info'


@dataclass
class VerificationReport:
    """Complete verification report for a cycle."""

    cycle_num: str
    total_files: int = 0
    files_checked: int = 0
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    results: list = field(default_factory=list)

    # New in the refactor — which adapter names ran during this report.
    # Used by to_markdown() to generate an accurate per-adapter summary
    # and to surface missing-tool diagnostics. Never relied on by inspeqtor.
    adapters_triggered: list = field(default_factory=list)

    # Normalized Phase 1 validation metadata. overall_status remains the
    # backward-compatible SUCCESS/PARTIAL/FAILURE tri-state; these fields let
    # callers distinguish verified success from degraded/static coverage.
    frontend_validation_summary: dict = field(
        default_factory=default_frontend_validation_summary
    )
    validation_outcome: str = "SUCCESS_LOW_COVERAGE"

    @property
    def overall_status(self) -> str:
        if self.errors > 0:
            return "FAILURE"
        if self.warnings > 0:
            return "PARTIAL"
        return "SUCCESS"

    def add_result(self, result: VerificationResult) -> None:
        self.results.append(result)
        # 'info' severity is observational only — it does not contribute
        # to pass/warn/err tallies or to overall_status. This lets adapters
        # surface tool-availability diagnostics without poisoning the status.
        if result.severity == SEVERITY_INFO:
            return
        if result.passed:
            self.passed += 1
        elif result.severity == SEVERITY_WARNING:
            self.warnings += 1
        else:
            self.errors += 1

    def to_markdown(self) -> str:
        """Generate markdown report.

        Output shape is compatible with the v1.3.0 monolith's markdown:
        - Header block with status + tallies
        - Errors section (grouped)
        - Warnings section (grouped)
        - File summary table — now language-aware, built from the check_types
          actually observed rather than a hard-coded Syntax/Imports pair.
        """
        md = f"# Qualification Report - CyQle {self.cycle_num}\n\n"
        md += f"**Status:** {self.overall_status}\n"
        md += f"**Files:** {self.files_checked}/{self.total_files}\n"
        md += (
            f"**Results:** ✅ {self.passed} passed "
            f"| ⚠️ {self.warnings} warnings "
            f"| ❌ {self.errors} errors\n"
        )
        if self.adapters_triggered:
            md += f"**Adapters:** {', '.join(sorted(self.adapters_triggered))}\n"
        md += "\n"

        # Errors first (error severity, not passed)
        errors = [
            r for r in self.results
            if not r.passed and r.severity == SEVERITY_ERROR
        ]
        if errors:
            md += "## ❌ Errors\n\n"
            for r in errors:
                line_info = f" (line {r.line_number})" if r.line_number else ""
                md += (
                    f"- **{r.file_path}**{line_info}: "
                    f"[{r.check_type}] {r.message}\n"
                )
            md += "\n"

        # Warnings
        warnings = [
            r for r in self.results
            if not r.passed and r.severity == SEVERITY_WARNING
        ]
        if warnings:
            md += "## ⚠️ Warnings\n\n"
            for r in warnings:
                line_info = f" (line {r.line_number})" if r.line_number else ""
                md += (
                    f"- **{r.file_path}**{line_info}: "
                    f"[{r.check_type}] {r.message}\n"
                )
            md += "\n"

        # Info (new — missing tool diagnostics, etc.)
        infos = [r for r in self.results if r.severity == SEVERITY_INFO]
        if infos:
            md += "## ℹ️ Info\n\n"
            for r in infos:
                md += f"- **{r.file_path}**: [{r.check_type}] {r.message}\n"
            md += "\n"

        # File summary — adapter-aware. Columns are the distinct check_types
        # we observed, but collapsed to their top-level namespace so the
        # table stays readable when there are many sub-checks.
        md += self._render_file_summary_table()
        return md

    # ─── helpers ────────────────────────────────────────────────────────────

    def _render_file_summary_table(self) -> str:
        """Render a per-file summary grouped by check_type namespace.

        Namespace is the part before ':' in check_type ('python:ruff' ->
        'python'). For legacy bare check_types ('syntax', 'import',
        'signature', 'call') we keep them as-is to preserve v1.3.0 columns
        when only Python ran.
        """
        by_file: dict[str, list[VerificationResult]] = {}
        for r in self.results:
            if r.severity == SEVERITY_INFO and r.file_path == "-":
                # Skip run-level info rows from the per-file table.
                continue
            by_file.setdefault(r.file_path, []).append(r)

        if not by_file:
            return "## File Summary\n\n_No files checked._\n"

        def ns(check_type: str) -> str:
            return check_type.split(":", 1)[0] if ":" in check_type else check_type

        # Collect all columns that appeared anywhere
        all_cols = sorted({ns(r.check_type) for rs in by_file.values() for r in rs})

        md = "## File Summary\n\n"
        header = "| File | " + " | ".join(all_cols) + " | Overall |\n"
        sep = "|------|" + "|".join(["--------"] * len(all_cols)) + "|--------|\n"
        md += header
        md += sep

        for file_path, results in sorted(by_file.items()):
            cells = []
            file_has_error = False
            file_has_warning = False
            file_has_info_only = False
            for col in all_cols:
                col_results = [r for r in results if ns(r.check_type) == col]
                if not col_results:
                    cells.append("—")
                    continue
                has_err = any(
                    (not r.passed) and r.severity == SEVERITY_ERROR
                    for r in col_results
                )
                has_warn = any(
                    (not r.passed) and r.severity == SEVERITY_WARNING
                    for r in col_results
                )
                has_info = any(r.severity == SEVERITY_INFO for r in col_results)
                if has_err:
                    cells.append("❌")
                    file_has_error = True
                elif has_warn:
                    cells.append("⚠️")
                    file_has_warning = True
                elif has_info:
                    cells.append("ℹ️")
                    file_has_info_only = True
                else:
                    cells.append("✅")
            if file_has_error:
                overall = "❌"
            elif file_has_warning:
                overall = "⚠️"
            elif file_has_info_only:
                overall = "ℹ️"
            else:
                overall = "✅"
            md += f"| `{file_path}` | " + " | ".join(cells) + f" | {overall} |\n"

        return md
