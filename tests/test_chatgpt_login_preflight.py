"""Regression tests for the chatgpt provider login preflight.

Covers the scenario reported as `mv /qq/codeseeq /qq/qonqrete/.codeseeq`:
QonQrete must never need (or suggest) relocating a codeseeq home into the
project.  Instead it reuses an existing `codeseeq login` wherever it lives
(project `.codeseeq`, `$CODEX_HOME` / `$CODESEEQ_HOST_CODEX_HOME`, or
`~/.codeseeq`) and, when no sign-in exists at all, it pins the new login to
the project-scoped home via `CODESEEQ_HOST_CODEX_HOME` so the session lands
in exactly the place every later run will look.
"""
import unittest
import sys
import os
import tempfile
import json
import io
import contextlib
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


class _FakeStdin:
    def __init__(self, isatty_value):
        self._isatty = isatty_value

    def isatty(self):
        return self._isatty


def _make_cfg(ws, *, provider="chatgpt"):
    return SimpleNamespace(
        provider=provider,
        model_qlarifier="gpt-5.5",
        model_instruqtor="gpt-5.5",
        model_construqtor="gpt-5.5",
        model_inspeqtor="gpt-5.5",
        repo_root=ws,
        run_root="",
        codeseeq_bin="/fake/path/to/codeseeq",
    )


class TestEnsureChatgptLogin(unittest.TestCase):
    def setUp(self):
        # Isolate HOME and drop ambient CODEX_HOME state so a real
        # `codeseeq login` on the developer machine cannot leak into the test.
        self._home_ctx = tempfile.TemporaryDirectory()
        self.home = self._home_ctx.name
        env_patch = patch.dict(os.environ, {"HOME": self.home}, clear=False)
        self._env_patch = env_patch
        env_patch.start()
        os.environ.pop("CODEX_HOME", None)
        os.environ.pop("CODESEEQ_HOST_CODEX_HOME", None)

    def tearDown(self):
        self._env_patch.stop()
        self._home_ctx.cleanup()

    def test_reuses_existing_user_level_login_without_relaunch(self):
        """A sign-in that already exists at ~/.codeseeq is reused: QonQrete
        must NOT trigger another login and must NOT advise moving folders."""
        from qq.cli import _ensure_chatgpt_login

        login_home = os.path.join(self.home, ".codeseeq")
        os.makedirs(login_home, exist_ok=True)
        with open(os.path.join(login_home, "auth.json"), "w") as f:
            json.dump({"tokens": {"access_token": "x"}}, f)

        with tempfile.TemporaryDirectory() as ws, \
             patch("sys.stdin", _FakeStdin(True)), \
             patch("qq.cli.subprocess.call") as mock_call, \
             patch("qq.cli._find_codeseeq_binary",
                   return_value="/fake/path/to/codeseeq"):
            rc = _ensure_chatgpt_login(_make_cfg(ws))
            self.assertEqual(rc, 0)
            mock_call.assert_not_called()

    def test_reuses_login_from_non_dot_container_style_home_env(self):
        """Regression: an existing codeseeq home mounted at a non-dot
        container path (e.g. CODESEEQ_HOST_CODEX_HOME=/qq/codeseeq) must be
        found and reused - no `mv /qq/codeseeq <project>/.codeseeq` needed."""
        from qq.cli import _ensure_chatgpt_login

        # The workspace lives in a container-ish parent (like /qq/qonqrete).
        with tempfile.TemporaryDirectory() as parent:
            ws = os.path.join(parent, "qonqrete")
            os.makedirs(ws, exist_ok=True)
            container_home = os.path.join(parent, "codeseeq")
            os.makedirs(container_home, exist_ok=True)
            with open(os.path.join(container_home, "auth.json"), "w") as f:
                f.write("{}")
            with patch.dict(os.environ,
                            {"CODESEEQ_HOST_CODEX_HOME": container_home},
                            clear=False), \
                 patch("sys.stdin", _FakeStdin(True)), \
                 patch("qq.cli.subprocess.call") as mock_call, \
                 patch("qq.cli._find_codeseeq_binary",
                       return_value="/fake/path/to/codeseeq"):
                rc = _ensure_chatgpt_login(_make_cfg(ws))
                self.assertEqual(rc, 0)
                mock_call.assert_not_called()

    def test_pins_new_login_to_project_home_when_none_exists(self):
        """When there is genuinely no sign-in, `codeseeq login` must be
        launched with CODESEEQ_HOST_CODEX_HOME pinned to <repo>/.codeseeq so
        the session is created in the single canonical place QonQrete reuses
        (this is what makes folder relocation both unnecessary and wrong)."""
        from qq.cli import _ensure_chatgpt_login

        with tempfile.TemporaryDirectory() as ws:
            err = io.StringIO()

            def _fake_login(cmd, **kwargs):
                # Simulate codeseeq login writing the session into the
                # pinned host codeseeq home (cwd/.codeseeq).
                home = kwargs.get("env", {}).get(
                    "CODESEEQ_HOST_CODEX_HOME")
                self.assertTrue(home)
                os.makedirs(home, exist_ok=True)
                with open(os.path.join(home, "auth.json"), "w") as f:
                    f.write("{}")
                return 0

            with contextlib.redirect_stderr(err), \
                 patch("sys.stdin", _FakeStdin(True)), \
                 patch("qq.cli.subprocess.call",
                       side_effect=_fake_login) as mock_call, \
                 patch("qq.cli._find_codeseeq_binary",
                       return_value="/fake/path/to/codeseeq"):
                rc = _ensure_chatgpt_login(_make_cfg(ws))

            self.assertEqual(rc, 0)
            mock_call.assert_called_once()
            call = mock_call.call_args
            self.assertEqual(call[0][0], ["/fake/path/to/codeseeq", "login"])
            self.assertEqual(call[1]["cwd"], os.path.abspath(ws))
            env = call[1]["env"]
            expected_home = os.path.join(os.path.abspath(ws), ".codeseeq")
            self.assertEqual(env.get("CODESEEQ_HOST_CODEX_HOME"),
                             expected_home)
            self.assertEqual(
                env.get("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES"), "true")
            self.assertEqual(env.get("CODESEEQ_RUNTIME_MODE"), "host")
            self.assertTrue(os.path.isfile(
                os.path.join(expected_home, "auth.json")))
            # No line of the output may instruct the user to run a `mv`
            # relocation command for a codeseeq home.
            self.assertFalse(any(
                line.strip().startswith("mv ")
                for line in err.getvalue().splitlines()))

    def test_non_interactive_run_fails_fast_without_relocation_advice(self):
        from qq.cli import _ensure_chatgpt_login

        with tempfile.TemporaryDirectory() as ws:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), \
                 patch("sys.stdin", _FakeStdin(False)), \
                 patch("qq.cli.subprocess.call") as mock_call, \
                 patch("qq.cli._find_codeseeq_binary",
                       return_value="/fake/path/to/codeseeq"):
                rc = _ensure_chatgpt_login(_make_cfg(ws))
            self.assertEqual(rc, 2)
            mock_call.assert_not_called()
            # The failure hint must warn against (never instruct) relocation.
            self.assertIn("Do NOT move", err.getvalue())
            self.assertFalse(any(
                line.strip().startswith("mv ")
                for line in err.getvalue().splitlines()))

    def test_noop_for_other_providers(self):
        from qq.cli import _ensure_chatgpt_login

        with tempfile.TemporaryDirectory() as ws, \
             patch("qq.cli.subprocess.call") as mock_call:
            rc = _ensure_chatgpt_login(_make_cfg(ws, provider="codeseeq"))
            self.assertEqual(rc, 0)
            mock_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
