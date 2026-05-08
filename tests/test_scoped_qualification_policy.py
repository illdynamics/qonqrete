import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import construqtor  # noqa: E402
from qualifier.models import VerificationResult  # noqa: E402


def test_scoped_qualification_demotes_advisory_html_lint_errors():
    with tempfile.TemporaryDirectory(prefix="qonq_scoped_policy_") as td:
        worqspace_root = Path(td)
        qodeyard = worqspace_root / "qodeyard"
        qodeyard.mkdir(parents=True, exist_ok=True)
        (worqspace_root / "config.yaml").write_text(
            "verification:\n  enabled: true\n",
            encoding="utf-8",
        )
        (qodeyard / "index.html").write_text("<!doctype html><html><body></body></html>\n", encoding="utf-8")
        report = SimpleNamespace(
            files_checked=1,
            results=[
                VerificationResult(
                    file_path="index.html",
                    check_type="html_css:html-validate",
                    passed=False,
                    message='no-redundant-for: Redundant "for" attribute',
                    line_number=8,
                    severity="error",
                )
            ],
        )
        with mock.patch("qualifier.run_verification", return_value=report):
            res = construqtor.run_scoped_qualification(
                ["index.html"],
                qodeyard,
                worqspace_root,
                cycle_label="policy-advisory",
            )
        assert res["passed"] is True
        assert res["syntax_errors"] == []
        assert any("advisory_quality" in row for row in res.get("import_warnings", []))
        assert any("html_css:html-validate" in row for row in res.get("advisory_quality_issues", []))


def test_scoped_qualification_keeps_shell_syntax_failures_hard():
    with tempfile.TemporaryDirectory(prefix="qonq_scoped_policy_") as td:
        worqspace_root = Path(td)
        qodeyard = worqspace_root / "qodeyard"
        qodeyard.mkdir(parents=True, exist_ok=True)
        (worqspace_root / "config.yaml").write_text(
            "verification:\n  enabled: true\n",
            encoding="utf-8",
        )
        (qodeyard / "broken.sh").write_text("#!/bin/sh\necho \"unterminated\n", encoding="utf-8")
        report = SimpleNamespace(
            files_checked=1,
            results=[
                VerificationResult(
                    file_path="broken.sh",
                    check_type="shell:syntax",
                    passed=False,
                    message="Syntax error: Unterminated quoted string",
                    line_number=2,
                    severity="error",
                )
            ],
        )
        with mock.patch("qualifier.run_verification", return_value=report):
            res = construqtor.run_scoped_qualification(
                ["broken.sh"],
                qodeyard,
                worqspace_root,
                cycle_label="policy-hard",
            )
        assert res["passed"] is False
        assert any("shell:syntax" in row for row in res["syntax_errors"])
