"""Tests for the refactored worqer/qualifier/ package.

Coverage:
  - Public API / import surface (import qualifier still works)
  - Registry: extension dispatch, lazy loading, custom registration
  - Runner: file discovery, skip-dirs, adapter aggregation, crash isolation
  - Report aggregation: pass/warn/err tallies, info severity handling, markdown
  - Python adapter: preserves v1.3.0 checks (syntax/imports/skeleton) + Ruff
  - Shell/JS-TS/HTML-CSS adapters: dispatch + missing-tool handling + parsing
  - Backward compat: legacy verification.checks.* toggles still drive Python
"""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import qualifier  # noqa: E402  — the refactored package
from qualifier import registry  # noqa: E402
from qualifier.base import (  # noqa: E402
    Adapter,
    QualifyContext,
    result_error,
    result_info,
    result_pass,
    result_warn,
)
from qualifier.models import (  # noqa: E402
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    VerificationReport,
    VerificationResult,
)
from qualifier.runner import run_verification  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

class _TmpQodeyard:
    """Context manager that creates a qodeyard+qontext pair."""

    def __init__(self):
        self._td = tempfile.TemporaryDirectory()

    def __enter__(self):
        base = Path(self._td.name)
        self.qodeyard = base / "qodeyard"
        self.qontext = base / "qontext.d"
        self.qodeyard.mkdir()
        self.qontext.mkdir()
        return self

    def __exit__(self, *exc):
        self._td.cleanup()

    def write(self, rel: str, content: str) -> Path:
        p = self.qodeyard / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content))
        return p


class _FakeAdapter(Adapter):
    """Test adapter that records calls for assertion."""

    def __init__(self, name="fake", extensions=(".fake",), results=None,
                 preflight_results=None, raises_on_file=None):
        self.name = name
        self.extensions = extensions
        self._results = results or []
        self._preflight = preflight_results or []
        self._raises_on_file = raises_on_file
        self.qualify_calls: list[Path] = []
        self.preflight_calls: int = 0

    def preflight(self, ctx):
        self.preflight_calls += 1
        return list(self._preflight)

    def qualify(self, file_path, ctx):
        self.qualify_calls.append(file_path)
        if self._raises_on_file and file_path.name == self._raises_on_file:
            raise RuntimeError("boom")
        return list(self._results)


@contextlib.contextmanager
def _no_tools():
    """Force find_binary to return None everywhere it is bound.

    Adapters do `from ..discovery import find_binary` which creates a
    fresh binding in the adapter's own namespace. Patching only
    `qualifier.discovery.find_binary` does NOT affect those local
    bindings, so we have to patch every adapter that's currently
    imported too. Adapters that have not been imported yet are simply
    skipped — they'll pick up the discovery-level patch on first import.
    """
    targets = [
        "qualifier.discovery.find_binary",
        "qualifier.adapters.python.find_binary",
        "qualifier.adapters.shell.find_binary",
        "qualifier.adapters.js_ts.find_binary",
        "qualifier.adapters.html_css.find_binary",
    ]
    with contextlib.ExitStack() as stack:
        for target in targets:
            module_name, _, attr = target.rpartition(".")
            mod = sys.modules.get(module_name)
            # Skip adapters that haven't been imported yet — their
            # module doesn't exist in sys.modules, and mock.patch would
            # raise ModuleNotFoundError. When the adapter gets imported
            # later, it pulls find_binary from qualifier.discovery which
            # IS patched, so the adapter sees the stub anyway.
            if mod is None and target != "qualifier.discovery.find_binary":
                continue
            if mod is not None and not hasattr(mod, attr):
                continue
            stack.enter_context(mock.patch(target, return_value=None))
        yield


# ═══════════════════════════════════════════════════════════════════════════
# Public-API surface
# ═══════════════════════════════════════════════════════════════════════════

class PublicApiTests(unittest.TestCase):
    def test_import_qualifier_resolves_to_package(self):
        # The primary backward-compat constraint for InspeQtor
        self.assertTrue(hasattr(qualifier, "run_verification"))
        self.assertTrue(hasattr(qualifier, "VerificationReport"))
        self.assertTrue(hasattr(qualifier, "VerificationResult"))

    def test_verification_report_and_result_are_classes(self):
        self.assertTrue(isinstance(qualifier.VerificationReport, type))
        self.assertTrue(isinstance(qualifier.VerificationResult, type))

    def test_run_verification_is_callable(self):
        self.assertTrue(callable(qualifier.run_verification))

    def test_package_version_present(self):
        self.assertTrue(hasattr(qualifier, "__version__"))
        # Loose sanity — not a strict equality so bumps don't break tests
        self.assertTrue(isinstance(qualifier.__version__, str))
        self.assertTrue(len(qualifier.__version__) > 0)


# ═══════════════════════════════════════════════════════════════════════════
# Models — report aggregation
# ═══════════════════════════════════════════════════════════════════════════

class ReportAggregationTests(unittest.TestCase):
    def test_pass_increments_passed_counter(self):
        rep = VerificationReport(cycle_num="1")
        rep.add_result(result_pass("a.py", "syntax", "OK"))
        self.assertEqual(rep.passed, 1)
        self.assertEqual(rep.warnings, 0)
        self.assertEqual(rep.errors, 0)

    def test_warning_increments_warnings_counter(self):
        rep = VerificationReport(cycle_num="1")
        rep.add_result(result_warn("a.py", "import", "missing", line_number=3))
        self.assertEqual(rep.warnings, 1)
        self.assertEqual(rep.passed, 0)
        self.assertEqual(rep.errors, 0)

    def test_error_increments_errors_counter(self):
        rep = VerificationReport(cycle_num="1")
        rep.add_result(result_error("a.py", "syntax", "bad"))
        self.assertEqual(rep.errors, 1)

    def test_info_severity_does_not_count(self):
        rep = VerificationReport(cycle_num="1")
        rep.add_result(result_info("-", "python:ruff", "ruff missing"))
        self.assertEqual(rep.passed, 0)
        self.assertEqual(rep.warnings, 0)
        self.assertEqual(rep.errors, 0)
        # But it IS recorded for display
        self.assertEqual(len(rep.results), 1)

    def test_overall_status_transitions(self):
        rep = VerificationReport(cycle_num="1")
        self.assertEqual(rep.overall_status, "SUCCESS")
        rep.add_result(result_warn("a.py", "x", "m"))
        self.assertEqual(rep.overall_status, "PARTIAL")
        rep.add_result(result_error("a.py", "x", "m"))
        self.assertEqual(rep.overall_status, "FAILURE")

    def test_to_markdown_contains_expected_sections(self):
        rep = VerificationReport(cycle_num="3")
        rep.adapters_triggered.append("python")
        rep.adapters_triggered.append("shell")
        rep.files_checked = 2
        rep.total_files = 2
        rep.add_result(result_pass("ok.py", "syntax", "OK"))
        rep.add_result(result_error("bad.py", "syntax", "oops", line_number=1))
        rep.add_result(result_warn("bad.py", "import", "no mod", line_number=2))
        rep.add_result(result_info("-", "python:ruff", "ruff missing"))

        md = rep.to_markdown()
        self.assertIn("CyQle 3", md)
        self.assertIn("## ❌ Errors", md)
        self.assertIn("## ⚠️ Warnings", md)
        self.assertIn("## ℹ️ Info", md)
        self.assertIn("## File Summary", md)
        self.assertIn("python, shell", md)
        self.assertIn("bad.py", md)

    def test_markdown_renders_with_no_files(self):
        rep = VerificationReport(cycle_num="0")
        md = rep.to_markdown()
        self.assertIn("SUCCESS", md)
        self.assertIn("No files checked", md)

    def test_file_summary_shows_info_only_rows(self):
        rep = VerificationReport(cycle_num="4")
        rep.files_checked = 1
        rep.total_files = 1
        rep.add_result(result_info(
            "ui/app.js",
            "js_ts:summary",
            "Adapter matched this file, but no file-level checks ran because required tool(s) were unavailable.",
        ))
        md = rep.to_markdown()
        self.assertIn("`ui/app.js`", md)
        self.assertIn("ℹ️", md)


# ═══════════════════════════════════════════════════════════════════════════
# Registry — extension dispatch + lazy loading
# ═══════════════════════════════════════════════════════════════════════════

class RegistryDispatchTests(unittest.TestCase):
    def test_known_extensions_map_to_expected_adapters(self):
        cases = {
            ".py": "python",
            ".pyi": "python",
            ".sh": "shell",
            ".bash": "shell",
            ".js": "js_ts",
            ".ts": "js_ts",
            ".tsx": "js_ts",
            ".jsx": "js_ts",
            ".mjs": "js_ts",
            ".cjs": "js_ts",
            ".html": "html_css",
            ".htm": "html_css",
            ".css": "html_css",
        }
        for ext, expected in cases.items():
            with self.subTest(ext=ext):
                self.assertEqual(registry.adapter_for_extension(ext), expected)

    def test_unknown_extensions_return_none(self):
        self.assertIsNone(registry.adapter_for_extension(".md"))
        self.assertIsNone(registry.adapter_for_extension(".txt"))
        self.assertIsNone(registry.adapter_for_extension(".bin"))
        self.assertIsNone(registry.adapter_for_extension(".scss"))
        self.assertIsNone(registry.adapter_for_extension(".sass"))
        self.assertIsNone(registry.adapter_for_extension(".less"))

    def test_adapter_for_file_respects_suffix_case(self):
        # Extensions are matched case-insensitively
        self.assertEqual(registry.adapter_for_file(Path("A.PY")), "python")
        self.assertEqual(registry.adapter_for_file(Path("X.TsX")), "js_ts")

    def test_load_adapter_caches_instances(self):
        registry.clear_cache()
        first = registry.load_adapter("python")
        second = registry.load_adapter("python")
        self.assertIs(first, second)

    def test_load_unknown_adapter_raises(self):
        with self.assertRaises(KeyError):
            registry.load_adapter("does_not_exist")

    def test_register_adapter_allows_custom_extension_adapter(self):
        registry.clear_cache()
        fake = _FakeAdapter(name="xyz")
        registry.register_adapter("xyz", lambda: fake)
        loaded = registry.load_adapter("xyz")
        self.assertIs(loaded, fake)
        self.assertIn("xyz", registry.known_adapter_names())


# ═══════════════════════════════════════════════════════════════════════════
# Runner — discovery, skip-dirs, aggregation, crash isolation
# ═══════════════════════════════════════════════════════════════════════════

class RunnerTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_runner_skips_unhandled_files(self):
        with _TmpQodeyard() as q:
            q.write("README.md", "# hi\n")
            q.write("data.json", "{}")
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
            self.assertEqual(rep.total_files, 0)
            self.assertEqual(rep.overall_status, "SUCCESS")

    def test_runner_skips_noise_directories(self):
        with _TmpQodeyard() as q:
            q.write("src/a.py", "x = 1\n")
            # These should NOT be walked
            q.write("node_modules/pkg/b.py", "raise SyntaxError\n")
            q.write("__pycache__/c.py", "still:broken(\n")
            q.write(".venv/lib/d.py", "boom(\n")
            # Force the python adapter without ruff to avoid external tool
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
            self.assertEqual(rep.total_files, 1)

    def test_runner_dispatches_by_extension_with_fake_adapter(self):
        registry.clear_cache()
        fake = _FakeAdapter(
            name="fake",
            extensions=(".fake",),
            results=[result_pass("x.fake", "fake:check", "ok")],
        )
        registry.EXTENSION_MAP[".fake"] = "fake"
        registry.register_adapter("fake", lambda: fake)
        try:
            with _TmpQodeyard() as q:
                q.write("one.fake", "data")
                q.write("two.fake", "data")
                q.write("ignore.unknown", "data")
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
            self.assertEqual(fake.preflight_calls, 1)
            self.assertEqual(len(fake.qualify_calls), 2)
            self.assertEqual(rep.total_files, 2)
            self.assertEqual(rep.files_checked, 2)
            self.assertEqual(rep.passed, 2)
            self.assertIn("fake", rep.adapters_triggered)
        finally:
            del registry.EXTENSION_MAP[".fake"]

    def test_runner_isolates_adapter_crashes(self):
        registry.clear_cache()
        fake = _FakeAdapter(
            name="crashy",
            extensions=(".crashy",),
            results=[result_pass("x.crashy", "crashy", "ok")],
            raises_on_file="boom.crashy",
        )
        registry.EXTENSION_MAP[".crashy"] = "crashy"
        registry.register_adapter("crashy", lambda: fake)
        try:
            with _TmpQodeyard() as q:
                q.write("good.crashy", "a")
                q.write("boom.crashy", "b")
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
            # Both files were attempted
            self.assertEqual(rep.files_checked, 2)
            # One error from the crash, one pass from the good file
            self.assertEqual(rep.errors, 1)
            self.assertEqual(rep.passed, 1)
            # Crash is tagged with :crash check_type
            crash_results = [
                r for r in rep.results if r.check_type.endswith(":crash")
            ]
            self.assertEqual(len(crash_results), 1)
            self.assertIn("boom", crash_results[0].message.lower())
        finally:
            del registry.EXTENSION_MAP[".crashy"]

    def test_runner_does_not_follow_symlinks(self):
        # We don't follow symlinks — avoids infinite loops and cross-FS reads
        with _TmpQodeyard() as q:
            q.write("real/a.py", "x = 1\n")
            # Create a symlink loop
            try:
                (q.qodeyard / "loop").symlink_to(q.qodeyard)
            except OSError:
                self.skipTest("symlink creation not supported")
            with _no_tools():
                # If symlinks were followed, this would never terminate
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
            self.assertEqual(rep.total_files, 1)


# ═══════════════════════════════════════════════════════════════════════════
# Python adapter — preserves v1.3.0 checks + adds Ruff
# ═══════════════════════════════════════════════════════════════════════════

class PythonAdapterTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()
        # Force all external tools missing so ruff never runs, regardless of
        # whether ruff is installed in the test environment. Helper patches
        # find_binary in the adapter's LOCAL namespace (which is where the
        # call actually resolves) in addition to qualifier.discovery.
        self._no_tools = _no_tools()
        self._no_tools.__enter__()

    def tearDown(self):
        self._no_tools.__exit__(None, None, None)
        registry.clear_cache()

    def test_valid_python_passes_syntax_and_imports(self):
        with _TmpQodeyard() as q:
            q.write("good.py", "def hello():\n    return 42\n")
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertEqual(rep.errors, 0)
        syntax_results = [r for r in rep.results if r.check_type == "syntax"]
        self.assertTrue(all(r.passed for r in syntax_results))

    def test_broken_python_flagged_as_syntax_error(self):
        with _TmpQodeyard() as q:
            q.write("bad.py", "def oops(\n    pass\n")
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertEqual(rep.overall_status, "FAILURE")
        self.assertGreaterEqual(rep.errors, 1)
        self.assertTrue(any(
            r.check_type == "syntax" and not r.passed
            for r in rep.results
        ))

    def test_missing_local_import_produces_warning(self):
        with _TmpQodeyard() as q:
            q.write(
                "main.py",
                "from src.utils.missing import thing\n"
                "print(thing)\n",
            )
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
        warn_results = [
            r for r in rep.results
            if r.check_type == "import" and r.severity == SEVERITY_WARNING
        ]
        self.assertTrue(
            len(warn_results) >= 1,
            f"Expected at least one import warning, got {rep.results}",
        )

    def test_stdlib_import_is_not_flagged(self):
        with _TmpQodeyard() as q:
            q.write("m.py", "import os\nimport json\nfrom pathlib import Path\n")
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertEqual(rep.errors, 0)
        self.assertEqual(rep.warnings, 0)

    def test_legacy_syntax_toggle_disables_syntax_check(self):
        config = {"verification": {"checks": {"syntax": False}}}
        with _TmpQodeyard() as q:
            q.write("bad.py", "def oops(\n    pass\n")
            rep = run_verification(q.qodeyard, q.qontext, "1", config)
        # With syntax disabled, the broken file generates NO syntax error row
        syntax_rows = [r for r in rep.results if r.check_type == "syntax"]
        self.assertEqual(len(syntax_rows), 0)

    def test_legacy_imports_toggle_disables_import_check(self):
        config = {"verification": {"checks": {"imports": False}}}
        with _TmpQodeyard() as q:
            q.write(
                "main.py",
                "from src.utils.missing import thing\n",
            )
            rep = run_verification(q.qodeyard, q.qontext, "1", config)
        import_rows = [r for r in rep.results if r.check_type == "import"]
        self.assertEqual(len(import_rows), 0)

    def test_skeleton_mismatch_flagged_when_qontext_present(self):
        with _TmpQodeyard() as q:
            q.write("m.py", "def existing():\n    pass\n")
            qctx_file = q.qontext / "m.py.q.yaml"
            qctx_file.write_text(
                "symbols:\n"
                "  - name: existing\n"
                "    type: function\n"
                "  - name: ghost\n"
                "    type: function\n"
            )
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
        sig_warns = [
            r for r in rep.results
            if r.check_type == "signature" and r.severity == SEVERITY_WARNING
        ]
        self.assertEqual(len(sig_warns), 1)
        self.assertIn("ghost", sig_warns[0].message)

    def test_ruff_preflight_info_when_missing(self):
        with _TmpQodeyard() as q:
            q.write("m.py", "x = 1\n")
            rep = run_verification(q.qodeyard, q.qontext, "1", {})
        ruff_infos = [
            r for r in rep.results
            if r.check_type == "python:ruff" and r.severity == SEVERITY_INFO
        ]
        self.assertEqual(len(ruff_infos), 1)


class PythonAdapterRuffTests(unittest.TestCase):
    """Ruff behaviour via subprocess mocking — no actual ruff needed."""

    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_ruff_diagnostics_are_normalized(self):
        from qualifier.adapters import python as pymod

        with _TmpQodeyard() as q:
            fpath = q.write("m.py", "x = 1\n")

            # Pretend ruff is on PATH, and make it emit one JSON violation
            ruff_payload = json.dumps([{
                "code": "F841",
                "message": "Local variable `x` is assigned to but never used",
                "location": {"row": 1, "column": 1},
            }])
            fake_completed = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=ruff_payload, stderr="",
            )

            with mock.patch(
                "qualifier.adapters.python.find_binary",
                return_value="/usr/bin/ruff",
            ), mock.patch(
                "qualifier.adapters.python.subprocess.run",
                return_value=fake_completed,
            ):
                results = pymod._run_ruff(fpath, "m.py", "/usr/bin/ruff")

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed)
        self.assertEqual(results[0].check_type, "python:ruff")
        self.assertEqual(results[0].severity, SEVERITY_WARNING)
        self.assertIn("F841", results[0].message)
        self.assertEqual(results[0].line_number, 1)

    def test_ruff_clean_run_returns_pass(self):
        from qualifier.adapters import python as pymod
        with _TmpQodeyard() as q:
            fpath = q.write("m.py", "x = 1\n")
            fake_completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch(
                "qualifier.adapters.python.subprocess.run",
                return_value=fake_completed,
            ):
                results = pymod._run_ruff(fpath, "m.py", "/usr/bin/ruff")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed)


# ═══════════════════════════════════════════════════════════════════════════
# Shell adapter — sh/bash -n + shellcheck + shfmt via subprocess mocks
# ═══════════════════════════════════════════════════════════════════════════

class ShellAdapterTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_shell_adapter_flags_syntax_error(self):
        # /bin/sh is always present on POSIX systems; this runs for real
        with _TmpQodeyard() as q:
            q.write("bad.sh", "#!/bin/sh\nif then fi\n")
            # Force other shell tools missing
            def _fb(name, cwd=None):
                return "/bin/sh" if name == "sh" else None
            with mock.patch(
                "qualifier.adapters.shell.find_binary", side_effect=_fb,
            ):
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertGreaterEqual(rep.errors, 1)
        syntax_errs = [
            r for r in rep.results
            if r.check_type == "shell:syntax" and not r.passed
        ]
        self.assertEqual(len(syntax_errs), 1)

    def test_shell_adapter_passes_valid_script(self):
        with _TmpQodeyard() as q:
            q.write("ok.sh", "#!/bin/sh\necho hello\n")
            def _fb(name, cwd=None):
                return "/bin/sh" if name == "sh" else None
            with mock.patch(
                "qualifier.adapters.shell.find_binary", side_effect=_fb,
            ):
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        syntax_rows = [r for r in rep.results if r.check_type == "shell:syntax"]
        self.assertTrue(all(r.passed for r in syntax_rows))

    def test_shell_shebang_detection_picks_bash(self):
        from qualifier.adapters.shell import _pick_shell_mode
        with _TmpQodeyard() as q:
            f = q.write("b.sh", "#!/usr/bin/env bash\necho $BASH_VERSION\n")
            self.assertEqual(_pick_shell_mode(f), "bash")

    def test_shell_shebang_default_is_sh(self):
        from qualifier.adapters.shell import _pick_shell_mode
        with _TmpQodeyard() as q:
            f = q.write("x.sh", "echo hi\n")  # no shebang
            self.assertEqual(_pick_shell_mode(f), "sh")

    def test_shell_extension_overrides_shebang(self):
        from qualifier.adapters.shell import _pick_shell_mode
        with _TmpQodeyard() as q:
            f = q.write("x.bash", "echo hi\n")
            self.assertEqual(_pick_shell_mode(f), "bash")

    def test_shellcheck_json_parsed_into_normalized_results(self):
        from qualifier.adapters.shell import _run_shellcheck
        with _TmpQodeyard() as q:
            f = q.write("x.sh", "#!/bin/sh\necho hi\n")
            payload = json.dumps([
                {
                    "level": "error",
                    "code": 2086,
                    "message": "Double quote to prevent globbing",
                    "line": 2,
                },
                {
                    "level": "warning",
                    "code": 2034,
                    "message": "Variable appears unused",
                    "line": 3,
                },
            ])
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.shell.subprocess.run",
                return_value=fake,
            ):
                results = _run_shellcheck(f, "x.sh", "/usr/bin/shellcheck")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].severity, SEVERITY_ERROR)
        self.assertIn("SC2086", results[0].message)
        self.assertEqual(results[1].severity, SEVERITY_WARNING)
        self.assertIn("SC2034", results[1].message)


# ═══════════════════════════════════════════════════════════════════════════
# JS/TS adapter — Biome + tsc
# ═══════════════════════════════════════════════════════════════════════════

class JsTsAdapterTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_js_ts_dispatch_happens_for_js_files(self):
        with _TmpQodeyard() as q:
            q.write("app.js", "const x = 1;\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertIn("js_ts", rep.adapters_triggered)
        # Missing biome → info row
        infos = [r for r in rep.results if r.check_type == "js_ts:biome"]
        self.assertEqual(len(infos), 1)

    def test_tsc_info_only_appears_when_ts_project_exists(self):
        # With no .ts files and no tsconfig.json, tsc shouldn't be complained about
        with _TmpQodeyard() as q:
            q.write("app.js", "const x = 1;\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        tsc_rows = [r for r in rep.results if r.check_type == "js_ts:tsc"]
        self.assertEqual(len(tsc_rows), 0)

    def test_tsc_info_appears_when_ts_files_present(self):
        with _TmpQodeyard() as q:
            q.write("app.ts", "const x: number = 1;\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        tsc_rows = [r for r in rep.results if r.check_type == "js_ts:tsc"]
        self.assertEqual(len(tsc_rows), 1)
        self.assertEqual(tsc_rows[0].severity, SEVERITY_INFO)

    def test_biome_diagnostic_parsed_from_json(self):
        from qualifier.adapters.js_ts import _run_biome
        with _TmpQodeyard() as q:
            f = q.write("a.js", "const x = 1;\n")
            payload = json.dumps({
                "diagnostics": [{
                    "severity": "warning",
                    "category": "lint/correctness",
                    "description": "unused variable",
                    "location": {
                        "span": {"start": {"line": 1}},
                    },
                }],
            })
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.js_ts.subprocess.run",
                return_value=fake,
            ):
                results = _run_biome(f, "a.js", "/usr/bin/biome")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, SEVERITY_WARNING)
        self.assertIn("lint/correctness", results[0].message)

    def test_biome_style_and_format_errors_are_downgraded_to_warning(self):
        from qualifier.adapters.js_ts import _run_biome
        with _TmpQodeyard() as q:
            f = q.write("a.js", "let x = 1;\n")
            payload = json.dumps({
                "diagnostics": [
                    {
                        "severity": "error",
                        "category": "format",
                        "description": "Formatter would have printed the following content:",
                        "location": {"span": {"start": {"line": 1}}},
                    },
                    {
                        "severity": "error",
                        "category": "lint/style/useConst",
                        "description": "This let declares a variable that is only assigned once.",
                        "location": {"span": {"start": {"line": 1}}},
                    },
                    {
                        "severity": "error",
                        "category": "lint/complexity/noForEach",
                        "description": "Prefer for...of instead of forEach.",
                        "location": {"span": {"start": {"line": 2}}},
                    },
                ],
            })
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.js_ts.subprocess.run",
                return_value=fake,
            ):
                results = _run_biome(f, "a.js", "/usr/bin/biome")
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.severity == SEVERITY_WARNING for r in results))

    def test_biome_non_style_errors_remain_blocking(self):
        from qualifier.adapters.js_ts import _run_biome
        with _TmpQodeyard() as q:
            f = q.write("a.js", "const x = obj.hasOwnProperty('a');\n")
            payload = json.dumps({
                "diagnostics": [{
                    "severity": "error",
                    "category": "lint/suspicious/noPrototypeBuiltins",
                    "description": "Do not access Object.prototype method 'hasOwnProperty' from target object.",
                    "location": {"span": {"start": {"line": 1}}},
                }],
            })
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.js_ts.subprocess.run",
                return_value=fake,
            ):
                results = _run_biome(f, "a.js", "/usr/bin/biome")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, SEVERITY_ERROR)
        self.assertIn("lint/suspicious/noPrototypeBuiltins", results[0].message)


# ═══════════════════════════════════════════════════════════════════════════
# HTML/CSS adapter — html-validate + stylelint
# ═══════════════════════════════════════════════════════════════════════════

class SummaryConsistencyTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_every_processed_file_appears_in_markdown_summary_even_when_tools_missing(self):
        with _TmpQodeyard() as q:
            q.write("pkg/mod.py", "x = 1\n")
            q.write("scripts/run.sh", "#!/bin/sh\necho hi\n")
            q.write("web/app.js", "const x = 1;\n")
            q.write("web/index.html", "<!doctype html><html></html>\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})

        md = rep.to_markdown()
        self.assertEqual(rep.files_checked, 4)
        self.assertEqual(rep.total_files, 4)
        for rel in ["pkg/mod.py", "scripts/run.sh", "web/app.js", "web/index.html"]:
            self.assertIn(f"`{rel}`", md)
        self.assertIn("js_ts:summary", md)
        self.assertIn("html_css:html-validate", md)


class HtmlCssAdapterTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_html_css_support_scope_is_html_and_plain_css_only(self):
        from qualifier.adapters.html_css import HtmlCssAdapter

        adapter = HtmlCssAdapter()
        self.assertEqual(adapter.extensions, (".html", ".htm", ".css"))
        self.assertIsNone(registry.adapter_for_extension(".scss"))
        self.assertIsNone(registry.adapter_for_extension(".sass"))
        self.assertIsNone(registry.adapter_for_extension(".less"))

    def test_preprocessor_files_are_not_claimed_as_supported(self):
        with _TmpQodeyard() as q:
            q.write("styles/app.scss", "$x: red; .a { color: $x; }\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertEqual(rep.total_files, 0)
        self.assertEqual(rep.files_checked, 0)
        self.assertNotIn("html_css", rep.adapters_triggered)

    def test_html_css_dispatch_for_both_html_and_css(self):
        with _TmpQodeyard() as q:
            q.write("index.html", "<!doctype html><html></html>\n")
            q.write("style.css", "body { color: red; }\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
        self.assertIn("html_css", rep.adapters_triggered)
        self.assertEqual(rep.total_files, 2)
        infos = [r for r in rep.results if r.severity == SEVERITY_INFO]
        # Expect one info per missing tool (html-validate + stylelint)
        kinds = {r.check_type for r in infos}
        self.assertIn("html_css:html-validate", kinds)
        self.assertIn("html_css:stylelint", kinds)

    def test_html_validate_json_parsed(self):
        from qualifier.adapters.html_css import _run_html_validate
        with _TmpQodeyard() as q:
            f = q.write("i.html", "<html></html>\n")
            payload = json.dumps([{
                "filePath": str(f),
                "messages": [
                    {
                        "severity": 2,
                        "ruleId": "element-required-content",
                        "message": "<html> is missing required children",
                        "line": 1,
                        "column": 1,
                    },
                    {
                        "severity": 1,
                        "ruleId": "long-title",
                        "message": "Title is too long",
                        "line": 2,
                    },
                ],
            }])
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.html_css.subprocess.run",
                return_value=fake,
            ):
                results = _run_html_validate(
                    f, "i.html", "/usr/bin/html-validate",
                )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].severity, SEVERITY_ERROR)
        self.assertEqual(results[1].severity, SEVERITY_WARNING)

    def test_stylelint_json_parsed(self):
        from qualifier.adapters.html_css import _run_stylelint
        with _TmpQodeyard() as q:
            f = q.write("s.css", "body { color: red; }\n")
            payload = json.dumps([{
                "source": str(f),
                "warnings": [{
                    "line": 1,
                    "severity": "error",
                    "rule": "color-no-invalid-hex",
                    "text": "Invalid hex color",
                }],
                "parseErrors": [],
            }])
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.html_css.subprocess.run",
                return_value=fake,
            ):
                results = _run_stylelint(f, "s.css", "/usr/bin/stylelint")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, SEVERITY_WARNING)
        self.assertIn("color-no-invalid-hex", results[0].message)

    def test_stylelint_parse_errors_remain_blocking(self):
        from qualifier.adapters.html_css import _run_stylelint
        with _TmpQodeyard() as q:
            f = q.write("broken.css", "body { color: red;\n")
            payload = json.dumps([{
                "source": str(f),
                "warnings": [],
                "parseErrors": [{
                    "line": 1,
                    "text": "Unclosed block",
                }],
            }])
            fake = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr="",
            )
            with mock.patch(
                "qualifier.adapters.html_css.subprocess.run",
                return_value=fake,
            ):
                results = _run_stylelint(f, "broken.css", "/usr/bin/stylelint")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].severity, SEVERITY_ERROR)
        self.assertIn("parse", results[0].message)


# ═══════════════════════════════════════════════════════════════════════════
# Discovery
# ═══════════════════════════════════════════════════════════════════════════

class DiscoveryTests(unittest.TestCase):
    def test_find_binary_returns_none_for_missing_tool(self):
        from qualifier.discovery import find_binary, clear_cache
        clear_cache()
        self.assertIsNone(find_binary("definitely-not-a-real-binary-xyz123"))

    def test_find_binary_finds_common_path_tool(self):
        from qualifier.discovery import find_binary, clear_cache
        clear_cache()
        # `sh` must exist on any system that can run this test
        sh = find_binary("sh")
        self.assertIsNotNone(sh)
        self.assertTrue(Path(sh).exists())

    def test_find_binary_prefers_local_node_modules(self):
        from qualifier.discovery import find_binary, clear_cache
        clear_cache()
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True)
            fake = bin_dir / "my-fake-linter"
            fake.write_text("#!/bin/sh\necho hi\n")
            fake.chmod(0o755)
            found = find_binary("my-fake-linter", cwd=Path(td))
            self.assertIsNotNone(found)
            self.assertTrue(Path(found).samefile(fake))


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end: extension-driven auto-dispatch, no config toggles
# ═══════════════════════════════════════════════════════════════════════════

class EndToEndTests(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_pure_python_project_does_not_load_other_adapters(self):
        """Lazy-loading guarantee: .py-only cyqle never imports shell/js/html modules."""
        # Purge adapter submodules so we can detect imports
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("qualifier.adapters."):
                del sys.modules[mod_name]
        registry.clear_cache()

        with _TmpQodeyard() as q:
            q.write("m.py", "x = 1\n")
            with _no_tools():
                run_verification(q.qodeyard, q.qontext, "1", {})

        self.assertIn("qualifier.adapters.python", sys.modules)
        self.assertNotIn("qualifier.adapters.shell", sys.modules)
        self.assertNotIn("qualifier.adapters.js_ts", sys.modules)
        self.assertNotIn("qualifier.adapters.html_css", sys.modules)

    def test_mixed_project_loads_all_four_adapters(self):
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("qualifier.adapters."):
                del sys.modules[mod_name]
        registry.clear_cache()

        with _TmpQodeyard() as q:
            q.write("m.py", "x = 1\n")
            q.write("s.sh", "#!/bin/sh\necho hi\n")
            q.write("a.js", "const x = 1;\n")
            q.write("i.html", "<html></html>\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})

        self.assertIn("qualifier.adapters.python", sys.modules)
        self.assertIn("qualifier.adapters.shell", sys.modules)
        self.assertIn("qualifier.adapters.js_ts", sys.modules)
        self.assertIn("qualifier.adapters.html_css", sys.modules)
        self.assertEqual(
            sorted(rep.adapters_triggered),
            ["html_css", "js_ts", "python", "shell"],
        )


# ═══════════════════════════════════════════════════════════════════════════
# v2.x: Scoped verification (changed_files=) — backwards compat + semantics
# ═══════════════════════════════════════════════════════════════════════════

from qualifier.runner import normalize_scoped_files  # noqa: E402


class NormalizeScopedFilesTests(unittest.TestCase):
    """Unit tests for the scope-normalization helper."""

    def test_none_returns_empty_list(self):
        with _TmpQodeyard() as q:
            self.assertEqual(normalize_scoped_files(q.qodeyard, None), [])

    def test_empty_iterable_returns_empty_list(self):
        with _TmpQodeyard() as q:
            self.assertEqual(normalize_scoped_files(q.qodeyard, []), [])

    def test_accepts_relative_paths(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("pkg/b.py", "y = 2\n")
            result = normalize_scoped_files(q.qodeyard, ["a.py", "pkg/b.py"])
            names = sorted(p.name for p in result)
            self.assertEqual(names, ["a.py", "b.py"])
            # All resolved paths must exist under qodeyard
            for p in result:
                self.assertTrue(p.is_file())

    def test_accepts_absolute_paths_under_qodeyard(self):
        with _TmpQodeyard() as q:
            p = q.write("a.py", "x = 1\n")
            result = normalize_scoped_files(q.qodeyard, [str(p.resolve())])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "a.py")

    def test_drops_paths_outside_qodeyard(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            # Try to escape upward
            escaping = str(q.qodeyard.parent / "outside.py")
            Path(escaping).write_text("nope\n", encoding="utf-8")
            try:
                result = normalize_scoped_files(
                    q.qodeyard, ["a.py", escaping, "../outside.py"]
                )
            finally:
                try:
                    Path(escaping).unlink()
                except OSError:
                    pass
            self.assertEqual([p.name for p in result], ["a.py"])

    def test_silently_drops_missing_files(self):
        with _TmpQodeyard() as q:
            q.write("real.py", "x = 1\n")
            result = normalize_scoped_files(
                q.qodeyard, ["real.py", "ghost.py", "nope/missing.js"]
            )
            self.assertEqual([p.name for p in result], ["real.py"])

    def test_drops_skip_dir_entries(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("node_modules/pkg/b.js", "const x = 1;\n")
            q.write("__pycache__/c.py", "still:broken(\n")
            q.write(".venv/d.py", "boom\n")
            result = normalize_scoped_files(
                q.qodeyard,
                [
                    "a.py",
                    "node_modules/pkg/b.js",
                    "__pycache__/c.py",
                    ".venv/d.py",
                ],
            )
            self.assertEqual([p.name for p in result], ["a.py"])

    def test_deduplicates_and_sorts_deterministically(self):
        with _TmpQodeyard() as q:
            q.write("z.py", "x = 1\n")
            q.write("a.py", "x = 1\n")
            q.write("m.py", "x = 1\n")
            # Provide in non-sorted, with dup
            result1 = normalize_scoped_files(
                q.qodeyard, ["z.py", "a.py", "m.py", "a.py"]
            )
            result2 = normalize_scoped_files(
                q.qodeyard, ["m.py", "a.py", "z.py"]
            )
            # Same sorted output regardless of input order / dups
            self.assertEqual([p.name for p in result1], ["a.py", "m.py", "z.py"])
            self.assertEqual([p.name for p in result2], ["a.py", "m.py", "z.py"])

    def test_tolerates_none_and_weird_entries(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            # Mixed noise — None, empty string, integer-ish; must not crash
            result = normalize_scoped_files(
                q.qodeyard, ["a.py", None, "", "ghost.py"]
            )
            self.assertEqual([p.name for p in result], ["a.py"])

    def test_directories_are_dropped(self):
        with _TmpQodeyard() as q:
            q.write("pkg/a.py", "x = 1\n")
            # Pass a directory, not a file
            result = normalize_scoped_files(q.qodeyard, ["pkg"])
            self.assertEqual(result, [])


class ScopedRunVerificationTests(unittest.TestCase):
    """Integration tests for run_verification(..., changed_files=...)."""

    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_four_arg_positional_call_still_works(self):
        """Primary back-compat guarantee — InspeQtor calls positionally."""
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {})
            self.assertEqual(rep.total_files, 1)
            self.assertEqual(rep.files_checked, 1)

    def test_five_arg_positional_call_still_works(self):
        """5-arg positional also allowed for callers that want it."""
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.py", "y = 2\n")
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", {}, ["a.py"])
            # Only 1 file — we scoped down
            self.assertEqual(rep.total_files, 1)
            self.assertEqual(rep.files_checked, 1)

    def test_kwarg_changed_files_call_works(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.py", "y = 2\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard, q.qontext, "1", {}, changed_files=["a.py"]
                )
            self.assertEqual(rep.total_files, 1)
            self.assertEqual(rep.files_checked, 1)

    def test_none_changed_files_falls_back_to_full_scan(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.py", "y = 2\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard, q.qontext, "1", {}, changed_files=None
                )
            self.assertEqual(rep.total_files, 2)

    def test_empty_changed_files_falls_back_to_full_scan(self):
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.py", "y = 2\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard, q.qontext, "1", {}, changed_files=[]
                )
            self.assertEqual(rep.total_files, 2)

    def test_scoped_run_only_loads_relevant_adapter(self):
        """Pure-Python scope must NOT load shell/js/html adapters even when
        the qodeyard happens to contain shell/js/html files."""
        # Purge adapter submodules so we can detect imports
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("qualifier.adapters."):
                del sys.modules[mod_name]
        registry.clear_cache()

        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.sh", "#!/bin/sh\necho hi\n")
            q.write("c.js", "const x = 1;\n")
            q.write("d.html", "<html></html>\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard, q.qontext, "1", {}, changed_files=["a.py"]
                )

        # Only Python adapter should have been imported
        self.assertIn("qualifier.adapters.python", sys.modules)
        self.assertNotIn("qualifier.adapters.shell", sys.modules)
        self.assertNotIn("qualifier.adapters.js_ts", sys.modules)
        self.assertNotIn("qualifier.adapters.html_css", sys.modules)
        # Scope tracked correctly
        self.assertEqual(rep.adapters_triggered, ["python"])
        self.assertEqual(rep.total_files, 1)
        self.assertEqual(rep.files_checked, 1)

    def test_scoped_run_does_not_expand_when_scope_matches_single_ecosystem(self):
        """Scoped mode must NOT fall back to full scan just because the
        scope only matches one language — that's the whole point."""
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("unused1.py", "y = 2\n")
            q.write("unused2.sh", "#!/bin/sh\necho hi\n")
            q.write("unused3.js", "const x = 1;\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard, q.qontext, "1", {}, changed_files=["a.py"]
                )
            # Only a.py was in scope — unused* must NOT be counted
            self.assertEqual(rep.total_files, 1)
            self.assertEqual(rep.files_checked, 1)

    def test_scoped_missing_files_do_not_crash(self):
        """Caller passes a stale manifest — we cope silently."""
        with _TmpQodeyard() as q:
            q.write("real.py", "x = 1\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard,
                    q.qontext,
                    "1",
                    {},
                    changed_files=[
                        "real.py",
                        "ghost_never_existed.py",
                        "also_missing/nope.js",
                    ],
                )
            # Only the real file was processed
            self.assertEqual(rep.total_files, 1)
            self.assertEqual(rep.files_checked, 1)

    def test_scoped_all_unusable_falls_back_to_full_scan(self):
        """If scope has zero usable files, we full-scan (documented behaviour)."""
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.py", "y = 2\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard,
                    q.qontext,
                    "1",
                    {},
                    changed_files=[
                        "ghost.py",
                        "also_ghost.js",
                        "not_a_real_file.sh",
                    ],
                )
            # All three files missing → fallback to full-scan → both real .py picked up
            self.assertEqual(rep.total_files, 2)

    def test_scoped_skip_dir_files_are_excluded(self):
        """Same exclusion set as full-scan — scope doesn't sneak noise back in."""
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("node_modules/pkg/noise.js", "const x = 1;\n")
            q.write("__pycache__/c.py", "still:broken(\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard,
                    q.qontext,
                    "1",
                    {},
                    changed_files=[
                        "a.py",
                        "node_modules/pkg/noise.js",
                        "__pycache__/c.py",
                    ],
                )
            self.assertEqual(rep.total_files, 1)

    def test_scoped_report_total_files_reflects_scope_not_repo(self):
        """total_files must reflect handled files in the active scope only."""
        with _TmpQodeyard() as q:
            for i in range(10):
                q.write(f"mod_{i}.py", "x = 1\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard,
                    q.qontext,
                    "1",
                    {},
                    changed_files=["mod_0.py", "mod_1.py"],
                )
            # Only 2 scoped — NOT 10 from the repo
            self.assertEqual(rep.total_files, 2)
            self.assertEqual(rep.files_checked, 2)

    def test_scoped_markdown_is_stable(self):
        """Markdown renders and doesn't mention files outside scope."""
        with _TmpQodeyard() as q:
            q.write("a.py", "x = 1\n")
            q.write("b.py", "y = 2\n")
            q.write("c.py", "z = 3\n")
            with _no_tools():
                rep = run_verification(
                    q.qodeyard, q.qontext, "1", {}, changed_files=["a.py"]
                )
            md = rep.to_markdown()
            self.assertIn("a.py", md)
            self.assertNotIn("b.py", md)
            self.assertNotIn("c.py", md)


class ScopedVerificationConfigPlumbingTests(unittest.TestCase):
    """The v2.x fix: real verification.checks.* config must survive into
    the qualifier, even under scoped mode. If it doesn't, the Python
    adapter's legacy per-check toggles silently stop working.
    """

    def setUp(self):
        registry.clear_cache()

    def tearDown(self):
        registry.clear_cache()

    def test_verification_checks_config_reaches_python_adapter_scoped(self):
        """With syntax=False toggle in config, broken Python must NOT fail
        — proving the config actually threaded through scoped mode."""
        with _TmpQodeyard() as q:
            q.write("broken.py", "def(:\n")
            config = {
                "verification": {
                    "checks": {
                        "syntax": False,
                        "imports": False,
                        "skeleton_match": False,
                    }
                }
            }
            with _no_tools():
                rep = run_verification(
                    q.qodeyard,
                    q.qontext,
                    "1",
                    config,
                    changed_files=["broken.py"],
                )
            # With syntax=False, broken.py should not produce a syntax error
            syntax_errors = [
                r for r in rep.results
                if (not r.passed) and "syntax" in r.check_type.lower()
                and r.severity == "error"
            ]
            self.assertEqual(
                syntax_errors, [],
                "syntax=False toggle was dropped — config did not reach adapter",
            )

    def test_verification_checks_config_reaches_python_adapter_fullscan(self):
        """Same config plumbing must work for the legacy full-scan path too."""
        with _TmpQodeyard() as q:
            q.write("broken.py", "def(:\n")
            config = {
                "verification": {
                    "checks": {
                        "syntax": False,
                        "imports": False,
                        "skeleton_match": False,
                    }
                }
            }
            with _no_tools():
                rep = run_verification(q.qodeyard, q.qontext, "1", config)
            syntax_errors = [
                r for r in rep.results
                if (not r.passed) and "syntax" in r.check_type.lower()
                and r.severity == "error"
            ]
            self.assertEqual(syntax_errors, [])


class ConstruqtorScopedQualifierReuseTests(unittest.TestCase):
    """v2.x: ConstruQtor's interleaved validation now reuses the real
    qualifier package. That means JS/TS/HTML/CSS/shell failures that the
    old narrow run_local_validation silently ignored now actually surface."""

    def setUp(self):
        registry.clear_cache()
        # Make `construqtor` importable; it lives under worqer/
        worqer_dir = PROJECT_ROOT / "worqer"
        if str(worqer_dir) not in sys.path:
            sys.path.insert(0, str(worqer_dir))

    def tearDown(self):
        registry.clear_cache()

    def test_run_scoped_qualification_exists_and_is_callable(self):
        # Imported lazily because construqtor has heavy deps (lib_ai etc)
        try:
            import construqtor  # noqa: F401
        except SystemExit:
            self.skipTest("construqtor module gated on missing lib_ai")
        except ImportError:
            self.skipTest("construqtor not importable in this env")
        self.assertTrue(hasattr(construqtor, "run_scoped_qualification"))
        self.assertTrue(callable(construqtor.run_scoped_qualification))

    def test_legacy_run_local_validation_still_exists(self):
        """Back-compat guarantee: we did NOT delete the old function."""
        try:
            import construqtor  # noqa: F401
        except (SystemExit, ImportError):
            self.skipTest("construqtor not importable in this env")
        self.assertTrue(hasattr(construqtor, "run_local_validation"))
        self.assertTrue(callable(construqtor.run_local_validation))

    def test_scoped_qualifier_surfaces_shell_syntax_errors(self):
        """Shell errors used to be caught by the narrow validator too
        (via `sh -n`), but the new shim routes them through the shell
        adapter. Prove they still surface as syntax_errors so the retry
        directive can include them."""
        try:
            import construqtor
        except (SystemExit, ImportError):
            self.skipTest("construqtor not importable in this env")

        # Only meaningful if `sh` is actually available on PATH — otherwise
        # the shell adapter emits a 'no shell binary' warning, not a
        # syntax error.
        import shutil as _shutil
        if _shutil.which("sh") is None:
            self.skipTest("sh not on PATH")

        with _TmpQodeyard() as q:
            # Unterminated quoted string — a reliable sh -n failure.
            q.write("broken.sh", '#!/bin/sh\necho "unterminated\n')
            # Drop a minimal config.yaml next to qodeyard so load_config
            # picks up SOME config without erroring.
            worqspace_root = q.qodeyard.parent
            (worqspace_root / "config.yaml").write_text(
                "verification:\n  enabled: true\n  checks:\n    syntax: true\n",
                encoding="utf-8",
            )
            # NOTE: no _no_tools() here — we WANT the real shell available.
            result = construqtor.run_scoped_qualification(
                ["broken.sh"],
                q.qodeyard,
                worqspace_root,
                cycle_label="test-scoped",
            )
        # Shape of legacy dict is preserved
        self.assertIn("passed", result)
        self.assertIn("syntax_errors", result)
        self.assertIn("constraint_errors", result)
        self.assertIn("import_warnings", result)
        self.assertIn("files_checked", result)
        # sh -n via the shell adapter should flag the unterminated quote.
        # This is the PR's smoking gun — the OLD run_local_validation
        # would have caught this too, but that path is narrow. The point
        # here is: the new shim also catches it, via the qualifier.
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("broken.sh" in err for err in result["syntax_errors"]),
            f"expected shell syntax error in {result['syntax_errors']}",
        )

    def test_scoped_qualifier_surfaces_js_failures_new_coverage(self):
        """This is coverage the OLD run_local_validation never had — JS
        files were silently ignored. Now they route through the js_ts
        adapter. Proving that the reuse actually broadens coverage."""
        try:
            import construqtor
        except (SystemExit, ImportError):
            self.skipTest("construqtor not importable in this env")

        with _TmpQodeyard() as q:
            q.write("ok.js", "const x = 1;\n")
            worqspace_root = q.qodeyard.parent
            (worqspace_root / "config.yaml").write_text(
                "verification:\n  enabled: true\n", encoding="utf-8"
            )
            # Use _no_tools so we don't depend on biome/tsc being installed.
            # The adapter will still load and be invoked — that's the
            # point. With no tools, the file is still 'files_checked'
            # and gets an info row, not an error.
            with _no_tools():
                result = construqtor.run_scoped_qualification(
                    ["ok.js"],
                    q.qodeyard,
                    worqspace_root,
                    cycle_label="test-scoped-js",
                )
        # The OLD run_local_validation would have files_checked=0 for .js.
        # The new shim routes it through the js_ts adapter, so at minimum
        # the file gets counted.
        self.assertEqual(result["files_checked"], 1)
        # Passes (no real errors) — but more importantly, the coverage
        # expanded past the old py/sh/json/yaml/toml-only fence.
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
