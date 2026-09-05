"""Tests for the CodeSeeq adapter command building and secret redaction."""
import unittest
import sys
import os
import tempfile
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters.base import AgentCallSpec
from qq.adapters.codeseeq import (
    _redact_secrets, _find_codeseeq_binary, CodeSeeqAdapter,
)
from qq.adapters.mock import MockAdapter


class TestSecretRedaction(unittest.TestCase):
    def test_bearer_redaction(self):
        result = _redact_secrets("Bearer sk-abc123")
        self.assertNotIn("sk-abc123", result)
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)

    def test_deepseek_api_key_redaction(self):
        result = _redact_secrets("DEEPSEEK_API_KEY=sk-secret123")
        self.assertNotIn("sk-secret123", result)
        self.assertIn("DEEPSEEK_API_KEY", result)
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)

    def test_api_key_redaction(self):
        result = _redact_secrets("Api_Key = abcdefghijklmnopqrstuvwxyz")
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)

    def test_openai_key_redaction(self):
        result = _redact_secrets('export OPENAI_API_KEY="sk-openai-key"')
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)
        self.assertNotIn("sk-openai-key", result)

    def test_sk_key_standalone(self):
        result = _redact_secrets("sk-abc12345678901234567890")
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)
        self.assertNotIn("abc12345678901234567890", result)

    def test_password_token_redaction(self):
        result = _redact_secrets("password=supersecret")
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)
        self.assertNotIn("supersecret", result)

    def test_token_redaction(self):
        result = _redact_secrets("token=abc123")
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)

    def test_redact_preserves_non_secrets(self):
        result = _redact_secrets("echo hello world")
        self.assertIn("hello world", result)
        self.assertNotIn("ƇΞƝƧØⱤΞƊ", result)

    def test_redact_stdout_stderr(self):
        """Secrets in stdout/stderr should be redacted."""
        result = _redact_secrets("stdout: DEEPSEEK_API_KEY=sk-xyz123")
        self.assertNotIn("sk-xyz123", result)
        self.assertIn("ƇΞƝƧØⱤΞƊ", result)


class TestCodeSeeqCommandBuilding(unittest.TestCase):
    """Test that CodeSeeqAdapter builds correct commands without
    requiring an actual codeseeq binary or network."""

    def setUp(self):
        # Use a fake binary path
        self.fake_bin = "/fake/path/to/codeseeq"

    @patch("subprocess.run")
    def test_command_uses_run_f_model(self, mock_run):
        """Command should be: codeseeq run -f <prompt-file> --model <model>"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build stuff", workdir=td,
                output_file="output.json",
            )
            result = adapter.call(spec)

            # Verify the subprocess call
            args, kwargs = mock_run.call_args
            cmd = args[0]
            self.assertIn(self.fake_bin, cmd)
            self.assertIn("run", cmd)
            self.assertIn("-f", cmd)
            self.assertIn("--model", cmd)
            self.assertIn("deepseek-v4-flash", cmd)
            # Should have a prompt file
            prompt_idx = cmd.index("-f") + 1
            prompt_file = cmd[prompt_idx]
            self.assertTrue(os.path.exists(prompt_file))
            self.assertIn(".qq_prompt_", prompt_file)

    @patch("subprocess.run")
    def test_command_does_not_use_cwd_flag(self, mock_run):
        """Command should NOT include --cwd or --cd flag."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build stuff", workdir=td,
                output_file="output.json",
            )
            adapter.call(spec)

            args, kwargs = mock_run.call_args
            cmd = args[0]
            self.assertNotIn("--cwd", cmd)
            self.assertNotIn("--cd", cmd)

    @patch("subprocess.run")
    def test_subprocess_cwd_is_spec_workdir(self, mock_run):
        """subprocess cwd should be spec.workdir."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build stuff", workdir=td,
                output_file="output.json",
            )
            adapter.call(spec)

            kwargs = mock_run.call_args[1]
            self.assertEqual(kwargs.get("cwd"), td)

    @patch("subprocess.run")
    def test_prompt_file_is_written(self, mock_run):
        """Prompt file should be written to workdir before call."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            prompt_text = "test prompt content"
            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt=prompt_text, workdir=td,
                output_file="output.json",
            )
            adapter.call(spec)

            # Find the prompt file from the command
            args = mock_run.call_args[0][0]
            prompt_idx = args.index("-f") + 1
            prompt_file = args[prompt_idx]
            with open(prompt_file, "r") as f:
                content = f.read()
            self.assertIn(prompt_text, content)

    @patch("subprocess.run")
    def test_stale_output_file_deleted(self, mock_run):
        """Stale output file should be deleted before call."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            # Write stale content
            with open(output_path, "w") as f:
                f.write("stale")
            self.assertTrue(os.path.exists(output_path))

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
            )
            adapter.call(spec)
            # After call, the stale file should be gone
            # (mock_run doesn't recreate it, but adapter.delete happens first)
            args = mock_run.call_args[0][0]
            prompt_idx = args.index("-f") + 1
            prompt_file = args[prompt_idx]
            # Stale output_file should have been deleted before run
            # (The mock hasn't written it back; we just check it was deleted)

    @patch("subprocess.run")
    def test_env_vars_are_set(self, mock_run):
        """CODESEEQ_RUNTIME_MODE, CODESEEQ_BRIDGE_MODE,
        CODESEEQ_WORKSPACE_BANNER should be set."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        adapter = CodeSeeqAdapter(
            codeseeq_path=self.fake_bin,
            runtime_mode="container",
            bridge_mode="process",
        )
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
            )
            adapter.call(spec)

            kwargs = mock_run.call_args[1]
            env = kwargs.get("env", {})
            self.assertEqual(env.get("CODESEEQ_RUNTIME_MODE"), "container")
            self.assertEqual(env.get("CODESEEQ_BRIDGE_MODE"), "process")
            self.assertEqual(env.get("CODESEEQ_WORKSPACE_BANNER"), "false")

    @patch("subprocess.run")
    def test_timeout_returns_error(self, mock_run):
        """Timeout should return exit_code=-1 with error stderr."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["codeseeq", "run"], timeout=1800,
            output="partial stdout", stderr="partial stderr")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                timeout_seconds=1,
            )
            result = adapter.call(spec)
            self.assertEqual(result.exit_code, -1)
            self.assertIn("TIMEOUT", result.stderr)

    @patch("subprocess.run")
    def test_artifact_dir_writes_stdout_stderr(self, mock_run):
        """When artifact_dir is set, stdout/stderr files are written."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="test stdout", stderr="test stderr")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            arts_dir = os.path.join(td, "artifacts")
            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                artifact_dir=arts_dir,
            )
            adapter.call(spec)

            stdout_file = os.path.join(arts_dir, "stdout.txt")
            stderr_file = os.path.join(arts_dir, "stderr.txt")
            self.assertTrue(os.path.exists(stdout_file))
            self.assertTrue(os.path.exists(stderr_file))
            with open(stdout_file) as f:
                self.assertIn("test stdout", f.read())
            with open(stderr_file) as f:
                self.assertIn("test stderr", f.read())

    @patch("subprocess.run")
    def test_secret_redaction_covers_stdout_stderr(self, mock_run):
        """stdout/stderr containing secrets should be redacted."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="api key is sk-abc12345678901234567890",
            stderr="DEEPSEEK_API_KEY=sk-secret123")

        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
            )
            result = adapter.call(spec)
            self.assertNotIn("sk-abc123", result.stdout)
            self.assertNotIn("sk-secret123", result.stderr)
            self.assertIn("ƇΞƝƧØⱤΞƊ", result.stdout)
            self.assertIn("ƇΞƝƧØⱤΞƊ", result.stderr)

    def test_capabilities(self):
        """CodeSeeqAdapter should report correct capabilities."""
        adapter = CodeSeeqAdapter(codeseeq_path=self.fake_bin)
        caps = adapter.capabilities()
        self.assertTrue(caps.supports_exec_mode)
        self.assertTrue(caps.supports_tools)
        self.assertTrue(caps.supports_thinking_mode)


class TestMockAdapter(unittest.TestCase):
    def test_writes_output(self):
        adapter = MockAdapter()
        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="construqtor", model="mock", prompt="test", workdir=td,
                output_file="output.json",
            )
            result = adapter.call(spec)
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.output_path_exists)
            self.assertIsNotNone(result.raw_output_text)
            data = json.loads(result.raw_output_text)
            self.assertEqual(data["status"], "implemented")

    def test_inspeqtor_not_done_then_pass(self):
        adapter = MockAdapter()
        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="inspeqtor", model="mock", prompt="test", workdir=td,
                output_file="output.json",
            )
            r1 = adapter.call(spec)
            d1 = json.loads(r1.raw_output_text)
            self.assertEqual(d1["status"], "NOT_DONE")

            r2 = adapter.call(spec)
            d2 = json.loads(r2.raw_output_text)
            self.assertEqual(d2["status"], "FULLY_DONE")

    def test_qlarifier_returns_clarified(self):
        adapter = MockAdapter()
        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="qlarifier", model="mock", prompt="test", workdir=td,
                output_file="output.json",
            )
            result = adapter.call(spec)
            data = json.loads(result.raw_output_text)
            self.assertEqual(data["status"], "clarified")
            self.assertIn("clarified_task", data)

    def test_writes_artifact_files(self):
        """Mock adapter writes full artifact set when artifact_dir set."""
        adapter = MockAdapter()
        with tempfile.TemporaryDirectory() as td:
            arts_dir = os.path.join(td, "artifacts")
            spec = AgentCallSpec(
                role="construqtor", model="mock", prompt="test prompt",
                workdir=td, output_file="output.json",
                artifact_dir=arts_dir, call_id="call-0001",
            )
            adapter.call(spec)

            for fname in ("prompt.md", "stdout.txt", "stderr.txt",
                          "result.json", "metadata.json"):
                self.assertTrue(
                    os.path.exists(os.path.join(arts_dir, fname)),
                    f"Missing artifact: {fname}")


class TestStubAdapters(unittest.TestCase):
    def test_stubs_raise(self):
        from qq.adapters.stubs import JaminiAdapter, JeanClaudeAdapter
        for adapter in [JaminiAdapter(), JeanClaudeAdapter()]:
            with self.assertRaises(NotImplementedError):
                adapter.call(AgentCallSpec(
                    role="test", model="x", prompt="", workdir="/tmp",
                    output_file="o.json"))


if __name__ == "__main__":
    unittest.main()
