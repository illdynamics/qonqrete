from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from qualifier import registry  # noqa: E402
from qualifier.base import Adapter  # noqa: E402
from qualifier.models import VerificationReport  # noqa: E402
from qualifier.runner import run_verification  # noqa: E402
from inspeqtor import build_validation_bundle  # noqa: E402


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _without_frontend_tools():
    return (
        mock.patch("qualifier.discovery.find_binary", return_value=None),
        mock.patch("qualifier.adapters.html_css.find_binary", return_value=None),
        mock.patch("qualifier.adapters.js_ts.find_binary", return_value=None),
    )


def test_frontend_summary_counts_html_css_js_and_local_refs_with_scoped_html_expansion():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "index.html", """
            <!doctype html>
            <html>
              <head><link rel="stylesheet" href="./style.css"></head>
              <body><script src="./app.js"></script></body>
            </html>
        """)
        _write(root, "style.css", "body { color: black; }\n")
        _write(root, "app.js", "localStorage.setItem('mode', 'dark');\n")

        patchers = _without_frontend_tools()
        try:
            for patcher in patchers:
                patcher.__enter__()
            report = run_verification(root, None, "1", {}, changed_files=["index.html"])
        finally:
            for patcher in reversed(patchers):
                patcher.__exit__(None, None, None)

    summary = report.frontend_validation_summary
    assert summary["html_files_checked"] == 1
    assert summary["css_files_checked"] == 1
    assert summary["js_files_checked"] == 1
    assert summary["local_asset_references_checked"] >= 2
    assert report.validation_outcome == "SUCCESS_LOW_COVERAGE"


def test_blocking_frontend_error_cannot_be_success_verified():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "index.html", "<!doctype html><html><body><img src='missing.png'></body></html>")

        patchers = _without_frontend_tools()
        try:
            for patcher in patchers:
                patcher.__enter__()
            report = run_verification(root, None, "1", {})
        finally:
            for patcher in reversed(patchers):
                patcher.__exit__(None, None, None)

    assert report.errors > 0
    assert report.validation_outcome == "FAILED_BLOCKING_VALIDATION"
    assert report.frontend_validation_summary["blocking_errors"] > 0


class _CrashAdapter(Adapter):
    name = "crash"
    extensions = (".boom",)

    def qualify(self, file_path, ctx):
        raise RuntimeError("adapter exploded")


def test_adapter_crash_cannot_be_success_verified():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "bad.boom", "boom\n")

        old_adapter = registry.EXTENSION_MAP.get(".boom")
        registry.EXTENSION_MAP[".boom"] = "crash"
        registry.register_adapter("crash", lambda: _CrashAdapter())
        try:
            report = run_verification(root, None, "1", {})
        finally:
            if old_adapter is None:
                registry.EXTENSION_MAP.pop(".boom", None)
            else:
                registry.EXTENSION_MAP[".boom"] = old_adapter
            registry.clear_cache()

    assert report.validation_outcome == "FAILED_VALIDATION_INFRA"


def test_clean_python_deterministic_validation_is_success_verified():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "app.py", "VALUE = 1\n")
        with mock.patch("qualifier.discovery.find_binary", return_value=None), \
             mock.patch("qualifier.adapters.python.find_binary", return_value=None):
            report = run_verification(root, None, "1", {})

    assert report.errors == 0
    assert report.warnings == 0
    assert report.validation_outcome == "SUCCESS_VERIFIED"


def test_inspeqtor_validation_bundle_includes_frontend_summary_and_outcome():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "qodeyard").mkdir()
        (root / "reqap.d").mkdir()
        report = VerificationReport(cycle_num="1")
        report.files_checked = 2
        report.total_files = 2
        report.validation_outcome = "SUCCESS_LOW_COVERAGE"
        report.frontend_validation_summary = {
            "html_files_checked": 1,
            "css_files_checked": 0,
            "js_files_checked": 1,
            "local_asset_references_checked": 1,
            "blocking_errors": 0,
            "warnings": 0,
            "advisory_findings": 2,
            "validation_coverage_summary": "frontend_static_low_coverage",
        }
        bundle = build_validation_bundle(
            root,
            "1",
            qonfirmer_report=None,
            verification_results=report,
            smoketest_report=None,
            grouped_coherence={
                "status": "PASS",
                "checks": [],
                "issues": [],
                "group_summaries": [],
                "undeclared_changed_files": [],
                "unassigned_briqs": [],
            },
            changed_manifest_files=[],
        )

    assert bundle["validation_outcome"] == "SUCCESS_LOW_COVERAGE"
    assert bundle["frontend_validation_summary"]["html_files_checked"] == 1
    qualification = next(c for c in bundle["checks"] if c["check_id"] == "qualification")
    assert qualification["validation_outcome"] == "SUCCESS_LOW_COVERAGE"
    assert qualification["frontend_validation_summary"]["js_files_checked"] == 1
