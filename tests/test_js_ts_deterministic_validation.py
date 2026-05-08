from __future__ import annotations

import shutil
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from qualifier.adapters.js_ts import _run_node_check  # noqa: E402
from qualifier.runner import run_verification  # noqa: E402


def _run_js_project(files: dict[str, str]):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")

    patches = (
        mock.patch("qualifier.discovery.find_binary", return_value=None),
        mock.patch("qualifier.adapters.js_ts.find_binary", return_value=None),
    )
    stack = []
    try:
        for patcher in patches:
            stack.append(patcher.__enter__())
        report = run_verification(root, None, "1", {}, changed_files=list(files))
        return td, report
    except Exception:
        td.cleanup()
        raise
    finally:
        for patcher in reversed(patches):
            patcher.__exit__(None, None, None)


def test_valid_js_static_checks_pass_and_report_storage_keys():
    td, report = _run_js_project({
        "app.js": """
            import { helper } from "./helper.js";
            localStorage.setItem("mode", "dark");
            sessionStorage.getItem("mode");
            helper();
        """,
        "helper.js": "export function helper() { return 1; }\n",
    })
    try:
        assert report.errors == 0
        assert any(r.check_type == "js_ts:static" and r.passed for r in report.results)
        storage_rows = [r for r in report.results if r.check_type == "js_ts:storage-keys"]
        assert storage_rows
        assert "localStorage(mode)" in storage_rows[0].message
        assert "sessionStorage(mode)" in storage_rows[0].message
    finally:
        td.cleanup()


def test_js_syntax_error_remains_blocking_when_node_is_available():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bad.js"
        path.write_text("function broken( {\n", encoding="utf-8")
        results = _run_node_check(path, "bad.js", node)
    assert any((not r.passed) and r.severity == "error" for r in results)


def test_merge_conflict_markers_are_blocking():
    td, report = _run_js_project({
        "app.js": "<<<<<<< HEAD\nconst a = 1;\n=======\nconst a = 2;\n>>>>>>> branch\n",
    })
    try:
        assert report.errors >= 1
        assert any("merge conflict" in r.message.lower() for r in report.results)
    finally:
        td.cleanup()


def test_placeholder_content_warns_without_blocking():
    td, report = _run_js_project({"app.js": "// TODO: replace scaffold\nconst ok = 1;\n"})
    try:
        assert report.errors == 0
        assert report.warnings >= 1
        assert any("placeholder" in r.message.lower() for r in report.results)
    finally:
        td.cleanup()


def test_missing_relative_static_import_fails():
    td, report = _run_js_project({"app.js": 'import { x } from "./missing.js";\nx();\n'})
    try:
        assert report.errors >= 1
        assert any("missing local static import" in r.message.lower() for r in report.results)
    finally:
        td.cleanup()


def test_existing_relative_static_import_passes():
    td, report = _run_js_project({
        "app.js": 'import { x } from "./local.js";\nx();\n',
        "local.js": "export const x = () => 1;\n",
    })
    try:
        assert report.errors == 0
        assert not any("missing local static import" in r.message.lower() for r in report.results)
    finally:
        td.cleanup()


def test_bare_package_import_is_not_treated_as_missing_local_file():
    td, report = _run_js_project({"app.js": 'import debounce from "lodash/debounce";\ndebounce(() => {}, 1);\n'})
    try:
        assert report.errors == 0
        assert not any("missing local" in r.message.lower() for r in report.results)
    finally:
        td.cleanup()


def test_missing_literal_dynamic_import_fails():
    td, report = _run_js_project({"app.js": 'async function boot() { await import("./missing.js"); }\n'})
    try:
        assert report.errors >= 1
        assert any("missing local dynamic import" in r.message.lower() for r in report.results)
    finally:
        td.cleanup()
