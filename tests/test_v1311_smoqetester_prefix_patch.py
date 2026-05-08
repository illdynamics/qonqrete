from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worqer"))
sys.path.insert(0, str(ROOT / "qrane"))

from worqer.smoqetester.adapters.python import PythonAdapter  # noqa: E402
from worqer.smoqetester.base import SmoketestContext  # noqa: E402
from worqer.smoqetester.discovery import _path_candidate  # noqa: E402
from worqer.smoqetester.models import SmoketestResult  # noqa: E402
import worqer.smoqetester.python_bootstrap as python_bootstrap  # noqa: E402
from qrane import Colors, get_agent_prefix, normalize_agent_display_line  # noqa: E402


def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


class DiscoveryPathCandidateTests(unittest.TestCase):
    def test_path_candidate_keeps_explicit_symlink_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "system-python"
            target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            target.chmod(0o755)
            launcher = root / "bin" / "python"
            launcher.parent.mkdir(parents=True, exist_ok=True)
            try:
                launcher.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"Symlink creation unsupported: {exc}")

            resolved = _path_candidate(str(launcher), cwd=None)
            self.assertEqual(resolved, str(launcher.absolute()))
            self.assertNotEqual(resolved, str(target.resolve()))

    def test_path_candidate_relative_path_uses_cwd_without_dereference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "venv" / "bin" / "python"
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            exe.chmod(0o755)

            resolved = _path_candidate("venv/bin/python", cwd=root)
            self.assertEqual(resolved, str(exe.absolute()))


class PythonAdapterBindingTests(unittest.TestCase):
    def _ctx(self, qodeyard: Path, **adapter_overrides) -> SmoketestContext:
        adapter_cfg = {
            "command": "python -m pytest -q",
            "auto_unittest_discover": False,
            "auto_cli_help": False,
            "auto_fastapi_probe": False,
        }
        adapter_cfg.update(adapter_overrides)
        return SmoketestContext(
            qodeyard_path=qodeyard,
            cycle_num="1",
            adapter_config=adapter_cfg,
            timeout_seconds=5,
            max_output_chars=200,
        )

    def test_bind_python_command_rebinds_python_family(self):
        adapter = PythonAdapter()
        py_bin = "/tmp/validation-env/bin/python"
        self.assertEqual(
            adapter._bind_python_command(["python", "-m", "pytest"], py_bin),
            [py_bin, "-m", "pytest"],
        )
        self.assertEqual(
            adapter._bind_python_command(["python3.12", "app.py"], py_bin),
            [py_bin, "app.py"],
        )
        self.assertEqual(
            adapter._bind_python_command(["pytest", "-q"], py_bin),
            ["pytest", "-q"],
        )

    def test_project_smoketest_rebinds_configured_python_commands(self):
        adapter = PythonAdapter()
        with tempfile.TemporaryDirectory() as td:
            qodeyard = Path(td)
            app = qodeyard / "app.py"
            app.write_text("print('ok')\n", encoding="utf-8")
            ctx = self._ctx(qodeyard, command="python -m pytest -q")

            captured_command: list[str] = []

            def fake_run_command(*args, **kwargs):
                captured_command[:] = list(args[2])
                return SmoketestResult(
                    adapter="python",
                    name=args[1],
                    status="PASS",
                    executed=True,
                    execution_kind="executed",
                    message="ok",
                    command=" ".join(captured_command),
                )

            with mock.patch.object(PythonAdapter, "_python_bin", return_value=("/tmp/venv/bin/python", None)), \
                mock.patch("worqer.smoqetester.adapters.python.run_command", side_effect=fake_run_command):
                adapter.project_smoketest(ctx, [app])

            self.assertTrue(captured_command)
            self.assertEqual(captured_command[0], "/tmp/venv/bin/python")
            self.assertEqual(captured_command[1:], ["-m", "pytest", "-q"])

    def test_fastapi_probe_command_stays_truthful(self):
        adapter = PythonAdapter()
        with tempfile.TemporaryDirectory() as td:
            qodeyard = Path(td)
            entrypoint = qodeyard / "main.py"
            entrypoint.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
            ctx = self._ctx(qodeyard)
            expected_command = "/tmp/venv/bin/python .qonqrete_fastapi_probe.py"

            with mock.patch("worqer.smoqetester.adapters.python.run_command", return_value=SmoketestResult(
                adapter="python",
                name="python:fastapi_probe",
                status="PASS",
                executed=True,
                execution_kind="process_boot",
                message="ok",
                command=expected_command,
            )):
                res = adapter._run_fastapi_probe(ctx, "/tmp/venv/bin/python", entrypoint, [entrypoint])

            self.assertEqual(res[0].command, expected_command)
            self.assertNotEqual(res[0].command, "python _fastapi_probe.py")

    def test_missing_module_fallback_regex_classifies_probe_errors(self):
        adapter = PythonAdapter()
        with tempfile.TemporaryDirectory() as td:
            qodeyard = Path(td)
            (qodeyard / "requirements.txt").write_text("fastapi==0.110.0\n", encoding="utf-8")
            ctx = self._ctx(qodeyard)
            res = SmoketestResult(
                adapter="python",
                name="python:fastapi_probe",
                status="FAIL",
                executed=True,
                execution_kind="process_boot",
                message="failed",
                stderr="Failed to import FastAPI app: No module named 'fastapi'",
            )

            adapter._classify_failure(res, ctx)
            self.assertEqual(res.missing_module, "fastapi")
            self.assertEqual(res.failure_kind, "environment_dependency_missing")
            self.assertTrue(res.environment_blocked)


class PythonBootstrapCacheTests(unittest.TestCase):
    def _setup_repo(self, root: Path) -> tuple[Path, Path]:
        worqspace = root / "worqspace"
        qodeyard = root / "qodeyard"
        qodeyard.mkdir(parents=True, exist_ok=True)
        (qodeyard / "requirements.txt").write_text("fastapi==0.110.0\n", encoding="utf-8")
        return worqspace, qodeyard

    def test_manifest_hash_is_runtime_salted(self):
        with tempfile.TemporaryDirectory() as td:
            _, qodeyard = self._setup_repo(Path(td))
            with mock.patch.object(python_bootstrap.sys, "version", "3.11.9"), \
                mock.patch.object(python_bootstrap.sys, "platform", "linux"):
                h1 = python_bootstrap.get_manifest_hash(qodeyard)
            with mock.patch.object(python_bootstrap.sys, "version", "3.12.3"), \
                mock.patch.object(python_bootstrap.sys, "platform", "linux"):
                h2 = python_bootstrap.get_manifest_hash(qodeyard)
            with mock.patch.object(python_bootstrap.sys, "version", "3.12.3"), \
                mock.patch.object(python_bootstrap.sys, "platform", "darwin"):
                h3 = python_bootstrap.get_manifest_hash(qodeyard)

            self.assertIsNotNone(h1)
            self.assertNotEqual(h1, h2)
            self.assertNotEqual(h2, h3)

    def test_cache_reuse_requires_completion_sentinel(self):
        with tempfile.TemporaryDirectory() as td:
            worqspace, qodeyard = self._setup_repo(Path(td))
            cache_key = python_bootstrap.get_manifest_hash(qodeyard)
            self.assertIsNotNone(cache_key)
            venv_dir = worqspace / ".validation-env-cache" / "python" / str(cache_key)
            venv_python = venv_dir / "bin" / "python"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            venv_python.chmod(0o755)

            calls: list[list[str]] = []

            def fake_run(argv, **kwargs):
                calls.append([str(item) for item in argv])
                if len(argv) >= 3 and argv[1] == "-m" and argv[2] == "venv":
                    venv_python.parent.mkdir(parents=True, exist_ok=True)
                    venv_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    venv_python.chmod(0o755)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with mock.patch("worqer.smoqetester.python_bootstrap.subprocess.run", side_effect=fake_run):
                python_bin, err = python_bootstrap.provision_validation_env(worqspace, qodeyard)

            self.assertIsNone(err)
            self.assertEqual(python_bin, str(venv_python))
            self.assertTrue((venv_dir / ".bootstrap_complete").exists())
            self.assertGreaterEqual(len(calls), 2)

    def test_cache_reuse_with_sentinel_skips_rebootstrap(self):
        with tempfile.TemporaryDirectory() as td:
            worqspace, qodeyard = self._setup_repo(Path(td))
            cache_key = python_bootstrap.get_manifest_hash(qodeyard)
            self.assertIsNotNone(cache_key)
            venv_dir = worqspace / ".validation-env-cache" / "python" / str(cache_key)
            venv_python = venv_dir / "bin" / "python"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            venv_python.chmod(0o755)
            (venv_dir / ".bootstrap_complete").write_text("ok\n", encoding="utf-8")

            with mock.patch("worqer.smoqetester.python_bootstrap.subprocess.run") as mock_run:
                python_bin, err = python_bootstrap.provision_validation_env(worqspace, qodeyard)

            self.assertIsNone(err)
            self.assertEqual(python_bin, str(venv_python))
            mock_run.assert_not_called()

    def test_bootstrap_failure_cleans_partial_cache(self):
        with tempfile.TemporaryDirectory() as td:
            worqspace, qodeyard = self._setup_repo(Path(td))
            cache_key = python_bootstrap.get_manifest_hash(qodeyard)
            self.assertIsNotNone(cache_key)
            venv_dir = worqspace / ".validation-env-cache" / "python" / str(cache_key)
            venv_python = venv_dir / "bin" / "python"

            call_count = {"n": 0}

            def fake_run(argv, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    venv_python.parent.mkdir(parents=True, exist_ok=True)
                    venv_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=argv,
                    output="pip failed",
                    stderr="boom",
                )

            with mock.patch("worqer.smoqetester.python_bootstrap.subprocess.run", side_effect=fake_run):
                python_bin, err = python_bootstrap.provision_validation_env(worqspace, qodeyard)

            self.assertIsNone(python_bin)
            self.assertIsNotNone(err)
            self.assertFalse(venv_dir.exists())


class PythonTestDiscoveryHeuristicsTests(unittest.TestCase):
    def _ctx(self, qodeyard: Path) -> SmoketestContext:
        return SmoketestContext(
            qodeyard_path=qodeyard,
            cycle_num="1",
            adapter_config={},
            timeout_seconds=5,
            max_output_chars=200,
        )

    def test_unittest_discovery_heuristics_accept_expected_patterns(self):
        adapter = PythonAdapter()
        with tempfile.TemporaryDirectory() as td:
            qodeyard = Path(td)
            (qodeyard / "tests").mkdir(parents=True, exist_ok=True)
            self.assertTrue(adapter._tests_plausibly_exist(self._ctx(qodeyard)))

            (qodeyard / "tests").rmdir()
            (qodeyard / "test_api.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
            self.assertTrue(adapter._tests_plausibly_exist(self._ctx(qodeyard)))

            (qodeyard / "test_api.py").unlink()
            (qodeyard / "api_test.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
            self.assertTrue(adapter._tests_plausibly_exist(self._ctx(qodeyard)))

    def test_unittest_discovery_heuristics_reject_broad_and_manual_junk(self):
        adapter = PythonAdapter()
        with tempfile.TemporaryDirectory() as td:
            qodeyard = Path(td)
            (qodeyard / "testhelper.py").write_text("print('helper')\n", encoding="utf-8")
            self.assertFalse(adapter._tests_plausibly_exist(self._ctx(qodeyard)))

            (qodeyard / "manual_test.py").write_text("print('manual')\n", encoding="utf-8")
            self.assertFalse(adapter._tests_plausibly_exist(self._ctx(qodeyard)))


class QranePrefixRoutingTests(unittest.TestCase):
    def _prefixes(self):
        prefix = "uQQ"
        return {
            "agent": get_agent_prefix("inspeqtor", Colors.WHITE, prefix),
            "qualifier": get_agent_prefix("Qualifier", Colors.GREEN, prefix),
            "qonfirmer": get_agent_prefix("qonfirmer", Colors.MAGENTA, prefix),
            "smoqetester": get_agent_prefix("smoqetester", Colors.C, prefix),
        }

    def test_normalization_routes_qonfirmer_markers(self):
        p = self._prefixes()
        row = normalize_agent_display_line(
            "[Qonfirmer] PASS",
            agent_name="inspeqtor",
            agent_prefix=p["agent"],
            qualifier_prefix=p["qualifier"],
            qonfirmer_prefix=p["qonfirmer"],
            smoqetester_prefix=p["smoqetester"],
        )
        self.assertIsNotNone(row)
        self.assertEqual(row[0], p["qonfirmer"])
        self.assertEqual(row[1], "PASS")

        row2 = normalize_agent_display_line(
            "Qonfirmer: FAIL",
            agent_name="inspeqtor",
            agent_prefix=p["agent"],
            qualifier_prefix=p["qualifier"],
            qonfirmer_prefix=p["qonfirmer"],
            smoqetester_prefix=p["smoqetester"],
        )
        self.assertIsNotNone(row2)
        self.assertEqual(row2[0], p["qonfirmer"])
        self.assertEqual(row2[1], "FAIL")

    def test_normalization_routes_smoqetester_markers_case_variants(self):
        p = self._prefixes()
        for line in (
            "[smoQetester] Running scoped smoketest...",
            "[smoqetester] PASS",
            "smoQetester: Report: reqap.d/cyqle1/cyqle1_smoketest.md",
            "smoqetester: FAIL",
        ):
            with self.subTest(line=line):
                row = normalize_agent_display_line(
                    line,
                    agent_name="inspeqtor",
                    agent_prefix=p["agent"],
                    qualifier_prefix=p["qualifier"],
                    qonfirmer_prefix=p["qonfirmer"],
                    smoqetester_prefix=p["smoqetester"],
                )
                self.assertIsNotNone(row)
                self.assertEqual(row[0], p["smoqetester"])

    def test_prefix_alignment_major_agents_and_shell_template(self):
        prefix = "uQQ"
        majors = [
            get_agent_prefix("Qrane", Colors.WHITE, prefix),
            get_agent_prefix("Construqtor", Colors.C, prefix),
            get_agent_prefix("Qualifier", Colors.GREEN, prefix),
            get_agent_prefix("qonfirmer", Colors.MAGENTA, prefix),
            get_agent_prefix("smoqetester", Colors.C, prefix),
        ]
        indices = {strip_ansi(item).find("⸎") for item in majors}
        self.assertEqual(len(indices), 1)

        shell_text = (ROOT / "qonqrete.sh").read_text(encoding="utf-8")
        self.assertIn("AGENT_BASELINE_WIDTH=12", shell_text)
        self.assertIn('QRANE_LABEL="Qrane"', shell_text)
        self.assertIn('PREFIX_TPL="${B}〘{PREFIX}〙『${W}${QRANE_LABEL}${B}』${PADDING} ⸎ ${R}"', shell_text)

        shell_prefix_plain = f"〘{prefix}〙『Qrane』{' ' * (12 - len('Qrane'))} ⸎ "
        python_prefix_plain = strip_ansi(get_agent_prefix("Qrane", Colors.WHITE, prefix))
        self.assertEqual(shell_prefix_plain.find("⸎"), python_prefix_plain.find("⸎"))


if __name__ == "__main__":
    unittest.main()
