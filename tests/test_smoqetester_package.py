from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worqer"))

from smoqetester.base import Adapter, SmoketestContext  # noqa: E402
from smoqetester.models import SmoketestResult  # noqa: E402
from smoqetester.registry import EXTENSION_MAP, clear_cache, register_adapter  # noqa: E402
from smoqetester.runner import normalize_scoped_files, run_smoketest  # noqa: E402
import smoqetester.registry as smoke_registry  # noqa: E402


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


class _CrashAdapter(Adapter):
    name = "crash"
    extensions = (".crash",)

    def run(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        raise RuntimeError("boom")


class SmoqetesterPackageTests(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def _config(self, **kwargs):
        base = {
            "agents": {
                "inspeqtor": {
                    "smoketest": {
                        "enabled": True,
                        "mode": "scoped",
                        "timeout_seconds": 5,
                        "max_output_chars": 200,
                        "adapters": {
                            "python": {
                                "enabled": True,
                                "command": None,
                                "auto_unittest_discover": False,
                                "auto_cli_help": False,
                            },
                            "shell": {"enabled": True, "command": None},
                            "js_ts": {
                                "enabled": True,
                                "command": None,
                                "allow_script_execution": False,
                                "require_dependencies": True,
                                "auto_tsc_no_emit": True,
                            },
                            "html_css": {"enabled": True, "command": None},
                        },
                    }
                }
            }
        }
        base["agents"]["inspeqtor"]["smoketest"].update(kwargs)
        return base

    def test_normalize_scoped_files_deterministic(self):
        with _TmpRepo() as repo:
            repo.write("b.py", "print('b')\n")
            repo.write("a.py", "print('a')\n")
            scoped = normalize_scoped_files(repo.qodeyard, ["b.py", "a.py"])
            self.assertEqual([item.name for item in scoped], ["a.py", "b.py"])

    def test_scoped_execution_uses_only_relevant_adapter(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            repo.write("script.sh", "echo ok\n")
            calls: list[str] = []
            real_load = smoke_registry.load_adapter

            def _tracking(name: str):
                calls.append(name)
                return real_load(name)

            with mock.patch("smoqetester.runner.load_adapter", side_effect=_tracking):
                report = run_smoketest(
                    repo.qodeyard,
                    "1",
                    self._config(),
                    changed_files=["main.py"],
                )

            self.assertEqual(calls, ["python"])
            self.assertEqual(report.total_files, 1)
            self.assertIn("python", report.adapters_triggered)
            self.assertGreaterEqual(report.static_count, 1)

    def test_preflight_and_per_file_static_smoke_are_recorded(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            report = run_smoketest(repo.qodeyard, "1", self._config(), changed_files=["main.py"])
            results = report.to_dict()["results"]
            names = {item["name"] for item in results}
            self.assertIn("python_runtime", names)
            self.assertIn("python:py_compile", names)
            py_compile = next(item for item in results if item["name"] == "python:py_compile")
            self.assertEqual(py_compile["execution_kind"], "syntax_probe")
            self.assertFalse(py_compile["executed"])

    def test_missing_tools_surface_skip_rows_non_fatal(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            config = self._config(
                adapters={
                    "python": {"enabled": True, "command": ["definitely-missing-smoke-tool"]},
                    "shell": {"enabled": False},
                    "js_ts": {"enabled": False},
                    "html_css": {"enabled": False},
                }
            )
            report = run_smoketest(repo.qodeyard, "1", config, changed_files=["main.py"])
            self.assertEqual(report.failed, 0)
            self.assertEqual(report.errors, 0)
            self.assertGreaterEqual(report.commands_skipped, 1)
            self.assertTrue(any("Missing required tool" in item.message for item in report.results))

    def test_executed_vs_static_classification_is_honest(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            config = self._config(
                adapters={
                    "python": {
                        "enabled": True,
                        "command": [sys.executable, "-c", "print('project smoke ok')"],
                        "auto_unittest_discover": False,
                        "auto_cli_help": False,
                    },
                    "shell": {"enabled": False},
                    "js_ts": {"enabled": False},
                    "html_css": {"enabled": False},
                }
            )
            report = run_smoketest(repo.qodeyard, "1", config, changed_files=["main.py"])
            payload = report.to_dict()
            self.assertGreaterEqual(payload["executed_count"], 1)
            self.assertGreaterEqual(payload["static_count"], 1)
            executed_rows = [item for item in payload["results"] if item["execution_kind"] == "executed" and item["status"] != "SKIP"]
            static_rows = [item for item in payload["results"] if item["execution_kind"] == "static_probe" and item["status"] != "SKIP"]
            self.assertTrue(executed_rows)
            self.assertTrue(static_rows)

    def test_shell_syntax_checks_are_static(self):
        with _TmpRepo() as repo:
            repo.write("script.sh", "echo ok\n")
            config = self._config(
                adapters={
                    "python": {"enabled": False},
                    "shell": {"enabled": True, "command": None},
                    "js_ts": {"enabled": False},
                    "html_css": {"enabled": False},
                }
            )
            report = run_smoketest(repo.qodeyard, "1", config, changed_files=["script.sh"])
            shell_rows = [item.to_dict() for item in report.results if item.adapter == "shell" and item.name == "shell:syntax"]
            self.assertEqual(len(shell_rows), 1)
            self.assertEqual(shell_rows[0]["execution_kind"], "syntax_probe")
            self.assertFalse(shell_rows[0]["executed"])

    def test_scoped_empty_scope_skips_without_full_fallback(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            report = run_smoketest(
                repo.qodeyard,
                "1",
                self._config(),
                changed_files=["missing.py"],
            )
            self.assertEqual(report.executed, 0)
            self.assertTrue(any(item.name == "scope_empty" for item in report.results))

    def test_adapter_crash_isolated_to_error_result(self):
        with _TmpRepo() as repo:
            repo.write("crash.crash", "x\n")
            EXTENSION_MAP[".crash"] = "crash"
            register_adapter("crash", lambda: _CrashAdapter())
            try:
                config = self._config(
                    adapters={
                        "python": {"enabled": False},
                        "shell": {"enabled": False},
                        "js_ts": {"enabled": False},
                        "html_css": {"enabled": False},
                        "crash": {"enabled": True, "command": [sys.executable, "-c", "print('x')"]},
                    }
                )
                config["agents"]["inspeqtor"]["smoketest"]["adapters"]["crash"] = {
                    "enabled": True,
                    "command": [sys.executable, "-c", "print('x')"],
                }
                report = run_smoketest(repo.qodeyard, "1", config, changed_files=["crash.crash"])
            finally:
                EXTENSION_MAP.pop(".crash", None)
            self.assertEqual(report.errors, 1)
            self.assertTrue(any(item.status == "ERROR" for item in report.results))

    def test_report_payload_contains_rich_fields(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            config = self._config(
                adapters={
                    "python": {
                        "enabled": True,
                        "command": [sys.executable, "-c", "print('ok')"],
                        "auto_unittest_discover": False,
                        "auto_cli_help": False,
                    },
                    "shell": {"enabled": False},
                    "js_ts": {"enabled": False},
                    "html_css": {"enabled": False},
                }
            )
            report = run_smoketest(repo.qodeyard, "2", config, changed_files=["main.py"])
            payload = report.to_dict()
            for key in [
                "total_files",
                "files_checked",
                "commands_executed",
                "commands_skipped",
                "executed_count",
                "static_count",
                "warnings",
                "overall_status",
            ]:
                self.assertIn(key, payload)
            self.assertIn("executed", payload)  # backward-compatible alias
            result_payload = payload["results"][0]
            for key in ["execution_kind", "command", "severity", "related_files"]:
                self.assertIn(key, result_payload)

    def test_markdown_output_contains_execution_kind_and_related_files(self):
        with _TmpRepo() as repo:
            repo.write("main.py", "print('ok')\n")
            report = run_smoketest(repo.qodeyard, "2", self._config(), changed_files=["main.py"])
            markdown = report.to_markdown()
            self.assertIn("Smoketest Report - CyQle 2", markdown)
            self.assertIn("execution_kind", markdown)
            self.assertIn("related_files", markdown)


if __name__ == "__main__":
    unittest.main()

