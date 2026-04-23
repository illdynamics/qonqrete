"""Tests for the v1.3.5 smoqetester honesty patch.

These tests encode the truthfulness contract that static validation evidence
(syntax/compile/parse checks) MUST NOT masquerade as executed smoke evidence,
regardless of whether a subprocess was used to perform the check.

Prior-session-compatible: these tests live alongside test_smoqetester_package.py
and do not modify or replace existing test behavior.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worqer"))
sys.path.insert(0, str(ROOT / "qrane"))

from smoqetester.base import (  # noqa: E402
    classify_command_execution_kind,
    collect_commands,
    normalize_execution_kind_value,
)
from smoqetester.models import (  # noqa: E402
    EXECUTION_KIND_EXECUTED,
    EXECUTION_KIND_STATIC,
    EXECUTION_KIND_SYNTAX,
    SmoketestReport,
    SmoketestResult,
)
from smoqetester.registry import clear_cache  # noqa: E402
from smoqetester.runner import run_smoketest  # noqa: E402


class _TmpRepo:
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()

    def __enter__(self):
        self.root = Path(self._td.name)
        self.qodeyard = self.root / "qodeyard"
        self.qodeyard.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc):
        self._td.cleanup()

    def write(self, rel: str, content: str) -> Path:
        path = self.qodeyard / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


def _config(**kwargs):
    base = {
        "agents": {
            "inspeqtor": {
                "smoketest": {
                    "enabled": True,
                    "mode": "scoped",
                    "timeout_seconds": 5,
                    "max_output_chars": 200,
                    "adapters": {
                        "python": {"enabled": False},
                        "shell": {"enabled": False},
                        "js_ts": {"enabled": False},
                        "html_css": {"enabled": False},
                    },
                }
            }
        }
    }
    base["agents"]["inspeqtor"]["smoketest"].update(kwargs)
    return base


# ═════════════════════════════════════════════════════════════════════════════
# Issue B — Adapter classification logic honesty
# ═════════════════════════════════════════════════════════════════════════════
class ClassifierHonestyTests(unittest.TestCase):
    """Prove classify_command_execution_kind never overclaims executed."""

    def test_py_compile_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["python", "-m", "py_compile", "foo.py"]),
            EXECUTION_KIND_SYNTAX,
        )

    def test_python3_py_compile_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["python3", "-m", "py_compile", "foo.py"]),
            EXECUTION_KIND_SYNTAX,
        )

    def test_bash_dash_n_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["bash", "-n", "script.sh"]),
            EXECUTION_KIND_SYNTAX,
        )

    def test_sh_dash_n_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["sh", "-n", "script.sh"]),
            EXECUTION_KIND_SYNTAX,
        )

    def test_node_check_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["node", "--check", "app.js"]),
            EXECUTION_KIND_SYNTAX,
        )

    def test_tsc_no_emit_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["tsc", "--noEmit"]),
            EXECUTION_KIND_STATIC,
        )

    def test_tsc_without_no_emit_is_still_static(self):
        """A tsc build pass is not runtime smoke — it is a type/compile check."""
        self.assertEqual(
            classify_command_execution_kind(["tsc"]),
            EXECUTION_KIND_STATIC,
        )
        self.assertEqual(
            classify_command_execution_kind(["tsc", "--pretty", "false"]),
            EXECUTION_KIND_STATIC,
        )

    def test_known_static_linters_and_formatters_are_static(self):
        for tool in ("eslint", "flake8", "mypy", "ruff", "shellcheck", "black", "prettier"):
            with self.subTest(tool=tool):
                self.assertEqual(
                    classify_command_execution_kind([tool, "some-file"]),
                    EXECUTION_KIND_STATIC,
                )

    def test_unittest_discover_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["python", "-m", "unittest", "discover"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_pytest_module_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["python", "-m", "pytest"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_python_cli_help_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["python", "cli.py", "--help"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_node_running_a_script_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["node", "server.js"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_npm_run_smoke_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["npm", "run", "smoke"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_npm_test_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["npm", "test"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_npm_run_build_is_static(self):
        """Build compiles assets — it does not exercise runtime business logic."""
        self.assertEqual(
            classify_command_execution_kind(["npm", "run", "build"]),
            EXECUTION_KIND_STATIC,
        )

    def test_npm_run_lint_is_static(self):
        self.assertEqual(
            classify_command_execution_kind(["npm", "run", "lint"]),
            EXECUTION_KIND_STATIC,
        )

    def test_pnpm_run_smoke_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["pnpm", "run", "smoke"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_yarn_smoke_is_executed(self):
        self.assertEqual(
            classify_command_execution_kind(["yarn", "smoke"]),
            EXECUTION_KIND_EXECUTED,
        )

    def test_yarn_install_is_static(self):
        """Package-management verbs don't exercise runtime logic."""
        self.assertEqual(
            classify_command_execution_kind(["yarn", "install"]),
            EXECUTION_KIND_STATIC,
        )

    def test_unknown_tool_defaults_to_static(self):
        """Conservative fallback: subprocess running is not evidence of execution."""
        for command in (
            ["some-random-tool", "--flag"],
            ["my-custom-script", "arg"],
            ["/bin/totally-unknown", "x"],
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    classify_command_execution_kind(command),
                    EXECUTION_KIND_STATIC,
                )

    def test_empty_command_is_static(self):
        self.assertEqual(classify_command_execution_kind([]), EXECUTION_KIND_STATIC)

    def test_unknown_python_m_module_is_static(self):
        """Unknown `-m` module is conservative: we can't prove it runs app logic."""
        self.assertEqual(
            classify_command_execution_kind(["python", "-m", "black"]),
            EXECUTION_KIND_STATIC,
        )


# ═════════════════════════════════════════════════════════════════════════════
# Issue H — Config-driven execution_kind override
# ═════════════════════════════════════════════════════════════════════════════
class ConfigExecutionKindOverrideTests(unittest.TestCase):
    def test_normalize_execution_kind_value(self):
        self.assertEqual(normalize_execution_kind_value("static_probe"), "static_probe")
        self.assertEqual(normalize_execution_kind_value("EXECUTED"), "executed")
        self.assertEqual(normalize_execution_kind_value(" Static "), "static_probe")
        self.assertIsNone(normalize_execution_kind_value(None))
        self.assertIsNone(normalize_execution_kind_value(""))
        self.assertIsNone(normalize_execution_kind_value("auto"))
        self.assertIsNone(normalize_execution_kind_value("bogus"))

    def test_collect_commands_respects_adapter_default_override(self):
        commands = collect_commands("xx", {
            "command": "python -c 'print(1)'",
            "execution_kind": "static_probe",
        })
        self.assertEqual(len(commands), 1)
        _, argv, kind = commands[0]
        self.assertEqual(argv, ["python", "-c", "print(1)"])
        self.assertEqual(kind, "static_probe")

    def test_collect_commands_structured_entry_override_wins(self):
        commands = collect_commands("xx", {
            "commands": [
                {"command": "npm run smoke", "execution_kind": "executed"},
                {"command": "npm run build", "execution_kind": "static_probe"},
                "python -m py_compile foo.py",  # legacy scalar, no override
            ],
            "execution_kind": "auto",  # adapter default = infer
        })
        self.assertEqual(len(commands), 3)
        self.assertEqual(commands[0][2], "executed")
        self.assertEqual(commands[1][2], "static_probe")
        # Scalar entry with no override inherits adapter default (auto => None).
        self.assertIsNone(commands[2][2])

    def test_collect_commands_no_override_means_inference(self):
        commands = collect_commands("xx", {"command": "python -m py_compile foo.py"})
        self.assertEqual(len(commands), 1)
        self.assertIsNone(commands[0][2])

    def test_collect_commands_per_file_execution_kind_legacy_alias(self):
        commands = collect_commands("xx", {
            "command": "some-tool",
            "per_file_execution_kind": "static_probe",
        })
        self.assertEqual(commands[0][2], "static_probe")

    def test_config_override_forces_executed_on_custom_runtime_command(self):
        """A user who knows their script exercises runtime logic can say so."""
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            cfg = _config(adapters={
                "python": {
                    "enabled": True,
                    "command": [sys.executable, "-c", "print('runtime')"],
                    "execution_kind": "executed",
                    "auto_unittest_discover": False,
                    "auto_cli_help": False,
                },
                "shell": {"enabled": False},
                "js_ts": {"enabled": False},
                "html_css": {"enabled": False},
            })
            clear_cache()
            report = run_smoketest(repo.qodeyard, "1", cfg, changed_files=["main.py"])
            payload = report.to_dict()
            # The explicitly-executed user command contributes 1 executed.
            self.assertGreaterEqual(payload["executed_count"], 1)
            # The implicit py_compile is still static.
            self.assertGreaterEqual(payload["static_count"], 1)

    def test_config_override_forces_static_on_runtime_looking_command(self):
        """Conservative operator can downgrade an ambiguous command to static."""
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            cfg = _config(adapters={
                "python": {
                    "enabled": True,
                    # `python -c '...'` would infer to executed, but operator overrides.
                    "command": [sys.executable, "-c", "print('not really runtime')"],
                    "execution_kind": "static_probe",
                    "auto_unittest_discover": False,
                    "auto_cli_help": False,
                },
                "shell": {"enabled": False},
                "js_ts": {"enabled": False},
                "html_css": {"enabled": False},
            })
            clear_cache()
            report = run_smoketest(repo.qodeyard, "1", cfg, changed_files=["main.py"])
            payload = report.to_dict()
            # Config override wins: no executed evidence, only static/syntax.
            self.assertEqual(payload["executed_count"], 0)
            self.assertTrue(payload["has_static_evidence"])
            self.assertGreaterEqual(payload["static_count"], 1)
            self.assertEqual(payload.get("syntax_count"), 1)
            self.assertFalse(payload["has_executed_evidence"])


# ═════════════════════════════════════════════════════════════════════════════
# Issues D & E — Aggregate report + validation bundle honesty
# ═════════════════════════════════════════════════════════════════════════════
class ReportAndBundleHonestyTests(unittest.TestCase):
    def test_report_payload_has_evidence_flags(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            cfg = _config(adapters={
                "python": {
                    "enabled": True,
                    "command": None,
                    "auto_unittest_discover": False,
                    "auto_cli_help": False,
                },
                "shell": {"enabled": False},
                "js_ts": {"enabled": False},
                "html_css": {"enabled": False},
            })
            clear_cache()
            report = run_smoketest(repo.qodeyard, "7", cfg, changed_files=["main.py"])
            payload = report.to_dict()
            for key in (
                "has_executed_evidence",
                "has_static_evidence",
                "validation_mode_contribution",
                "executed_count",
                "static_count",
            ):
                self.assertIn(key, payload)
            # py_compile ran; no executed commands configured => static-only.
            self.assertFalse(payload["has_executed_evidence"])
            self.assertTrue(payload["has_static_evidence"])
            self.assertEqual(payload["validation_mode_contribution"], "static-only")

    def test_markdown_discloses_evidence_flags(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            cfg = _config(adapters={
                "python": {"enabled": True, "command": None, "auto_unittest_discover": False, "auto_cli_help": False},
                "shell": {"enabled": False},
                "js_ts": {"enabled": False},
                "html_css": {"enabled": False},
            })
            clear_cache()
            report = run_smoketest(repo.qodeyard, "9", cfg, changed_files=["main.py"])
            md = report.to_markdown()
            self.assertIn("Has Executed Evidence:", md)
            self.assertIn("Has Static Evidence:", md)
            self.assertIn("Validation Mode Contribution:", md)

    def test_validation_mode_contribution_for_empty_report(self):
        # Disabled smoke => enabled-false result => no evidence => "none".
        report = SmoketestReport(cycle_num="1", mode="scoped", enabled=False)
        self.assertEqual(report.validation_mode_contribution, "none")

    def test_validation_mode_contribution_mixed(self):
        report = SmoketestReport(cycle_num="1", mode="scoped", enabled=True)
        report.add_result(SmoketestResult(
            adapter="python", name="python:py_compile", status="PASS",
            executed=False, execution_kind="static_probe", message="ok",
        ))
        report.add_result(SmoketestResult(
            adapter="python", name="python:unittest_discover", status="PASS",
            executed=True, execution_kind="executed", message="ok",
        ))
        self.assertEqual(report.validation_mode_contribution, "mixed")
        self.assertTrue(report.has_executed_evidence)
        self.assertTrue(report.has_static_evidence)

    def test_static_check_does_not_count_as_executed_in_report(self):
        """Regression guard: a subprocess-based static check must stay static."""
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            # Default python adapter uses py_compile, which is static.
            cfg = _config(adapters={
                "python": {"enabled": True, "command": None, "auto_unittest_discover": False, "auto_cli_help": False},
                "shell": {"enabled": False},
                "js_ts": {"enabled": False},
                "html_css": {"enabled": False},
            })
            clear_cache()
            report = run_smoketest(repo.qodeyard, "1", cfg, changed_files=["main.py"])
            payload = report.to_dict()
            # py_compile ran successfully as a subprocess, but it is still STATIC (syntax_probe).
            py_compile_row = next(
                row for row in payload["results"] if row["name"] == "python:py_compile"
            )
            self.assertEqual(py_compile_row["status"], "PASS")
            self.assertEqual(py_compile_row["execution_kind"], "syntax_probe")
            self.assertFalse(py_compile_row["executed"])
            self.assertEqual(payload["executed_count"], 0)


# ═════════════════════════════════════════════════════════════════════════════
# Issues F & G — inspeqtor aggregation + qrane fallback honesty
# ═════════════════════════════════════════════════════════════════════════════
class InspeqtorAggregationTests(unittest.TestCase):
    """Validation-mode aggregation reflects actual evidence, not process usage."""

    def setUp(self):
        # Ensure inspeqtor is importable from the worqer path.
        # (Already inserted above, but we re-import here for test isolation.)
        if "inspeqtor" in sys.modules:
            importlib.reload(sys.modules["inspeqtor"])
        self.inspeqtor = importlib.import_module("inspeqtor")

    def test_detect_mode_static_only_when_smoke_is_static_only(self):
        smoke = {
            "results": [
                {"status": "PASS", "execution_kind": "static_probe", "executed": False},
                {"status": "PASS", "execution_kind": "static_probe", "executed": False},
            ],
            "executed_count": 0,
            "static_count": 2,
        }
        mode = self.inspeqtor.detect_validation_execution_mode(None, None, smoke)
        self.assertEqual(mode, "STATIC_ONLY")

    def test_detect_mode_executed_when_only_executed_evidence(self):
        smoke = {
            "results": [
                {"status": "PASS", "execution_kind": "executed", "executed": True},
            ],
            "executed_count": 1,
            "static_count": 0,
        }
        mode = self.inspeqtor.detect_validation_execution_mode(None, None, smoke)
        self.assertEqual(mode, "EXECUTED")

    def test_detect_mode_mixed_when_both_kinds_of_evidence(self):
        smoke = {
            "results": [
                {"status": "PASS", "execution_kind": "static_probe", "executed": False},
                {"status": "PASS", "execution_kind": "executed", "executed": True},
            ],
            "executed_count": 1,
            "static_count": 1,
        }
        mode = self.inspeqtor.detect_validation_execution_mode(None, None, smoke)
        self.assertEqual(mode, "MIXED")

    def test_detect_mode_none_when_no_evidence_at_all(self):
        smoke = {"results": [], "executed_count": 0, "static_count": 0}
        mode = self.inspeqtor.detect_validation_execution_mode(None, None, smoke)
        self.assertEqual(mode, "NONE")

    def test_summarize_counts_includes_evidence_booleans(self):
        smoke = {
            "results": [
                {"status": "PASS", "execution_kind": "static_probe", "executed": False},
            ],
        }
        counts = self.inspeqtor.summarize_smoketest_counts(smoke)
        self.assertEqual(counts["executed_count"], 0)
        self.assertEqual(counts["static_count"], 1)
        self.assertFalse(counts["has_executed_evidence"])
        self.assertTrue(counts["has_static_evidence"])

    def test_summarize_counts_ignores_skip_status(self):
        smoke = {
            "results": [
                {"status": "SKIP", "execution_kind": "executed", "executed": False},
                {"status": "SKIP", "execution_kind": "static_probe", "executed": False},
            ],
        }
        counts = self.inspeqtor.summarize_smoketest_counts(smoke)
        self.assertEqual(counts["executed_count"], 0)
        self.assertEqual(counts["static_count"], 0)
        self.assertFalse(counts["has_executed_evidence"])
        self.assertFalse(counts["has_static_evidence"])


class QraneFallbackHonestyTests(unittest.TestCase):
    """qrane lib fallback must not overclaim EXECUTED based on artifact presence."""

    def setUp(self):
        if "lib_qrane" in sys.modules:
            importlib.reload(sys.modules["lib_qrane"])
        self.lib_qrane = importlib.import_module("lib_qrane")

    def _write_smoke_artifacts(self, workspace: Path, cycle: str, payload: dict) -> None:
        cycle_dir = workspace / "reqap.d" / f"cyqle{cycle}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        (cycle_dir / f"cyqle{cycle}_smoketest.v1.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_fallback_static_only_smoke_does_not_overclaim_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._write_smoke_artifacts(workspace, "1", {
                "executed_count": 0,
                "static_count": 4,
                "results": [
                    {"status": "PASS", "execution_kind": "static_probe", "executed": False},
                ] * 4,
            })
            mode = self.lib_qrane.determine_validation_mode(workspace)
            # There is smoke evidence but none of it is executed.
            self.assertEqual(mode, "STATIC_ONLY")

    def test_fallback_artifact_presence_alone_is_not_executed(self):
        """Smoke JSON exists with zero evidence => NONE, never EXECUTED."""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._write_smoke_artifacts(workspace, "1", {
                "executed_count": 0,
                "static_count": 0,
                "results": [],
            })
            mode = self.lib_qrane.determine_validation_mode(workspace)
            self.assertEqual(mode, "NONE")

    def test_fallback_genuine_executed_smoke_yields_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._write_smoke_artifacts(workspace, "1", {
                "executed_count": 2,
                "static_count": 0,
                "results": [
                    {"status": "PASS", "execution_kind": "executed", "executed": True},
                    {"status": "PASS", "execution_kind": "executed", "executed": True},
                ],
            })
            mode = self.lib_qrane.determine_validation_mode(workspace)
            self.assertEqual(mode, "EXECUTED")

    def test_fallback_mixed_smoke_yields_mixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._write_smoke_artifacts(workspace, "1", {
                "executed_count": 1,
                "static_count": 1,
                "results": [
                    {"status": "PASS", "execution_kind": "static_probe", "executed": False},
                    {"status": "PASS", "execution_kind": "executed", "executed": True},
                ],
            })
            mode = self.lib_qrane.determine_validation_mode(workspace)
            self.assertEqual(mode, "MIXED")


if __name__ == "__main__":
    unittest.main()
