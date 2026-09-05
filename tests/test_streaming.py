"""Tests for agent output streaming — CLI args, mock streaming, redaction, deadlock, artifacts."""
import subprocess
import unittest
import sys
import os
import io
import json
import tempfile
import dataclasses
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters.base import AgentCallSpec
from qq.adapters.mock import MockAdapter
from qq.streaming import AgentOutputStreamer, create_streamer
from qq.config import resolve_config
from qq.qontroller import QontrollerConfig, run


class TestCLIArgs(unittest.TestCase):
    """CLI argument parsing for streaming options."""

    def test_stream_agent_output_sets_config(self):
        cfg = resolve_config(dry_run=True, stream_agent_output=True)
        self.assertTrue(cfg.stream_agent_output)

    def test_stream_mode_raw_works(self):
        cfg = resolve_config(dry_run=True, stream_agent_output=True,
                            stream_mode="raw")
        self.assertEqual(cfg.stream_mode, "raw")

    def test_invalid_stream_mode_fails(self):
        with self.assertRaises(ValueError):
            resolve_config(dry_run=True, stream_mode="invalid_mode_xyz")

    def test_show_prompts_sets_config(self):
        cfg = resolve_config(dry_run=True, show_prompts=True)
        self.assertTrue(cfg.show_prompts)

    def test_stream_stderr_defaults_true(self):
        cfg = resolve_config(dry_run=True, stream_agent_output=True)
        self.assertTrue(cfg.stream_stderr)

    def test_stream_agent_output_defaults_true(self):
        cfg = resolve_config(dry_run=True)
        self.assertTrue(cfg.stream_agent_output)


class TestAgentOutputStreamer(unittest.TestCase):
    """Test the streaming renderer/sink."""

    def test_prefixed_mode_includes_role_and_stream(self):
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", sink=buf.append)
        streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                       "text": "hello\n", "call_id": "c1"})
        self.assertEqual(len(buf), 1)
        line = buf[0].get("line", "")
        self.assertIn("[Qlarifier] stdout", line)
        self.assertIn("hello", line)

    def test_raw_mode_no_prefix(self):
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="raw", sink=buf.append,
            agent_color_output="original")
        streamer.emit({"role": "construqtor", "stream_name": "stdout",
                       "text": "raw output\n", "call_id": "c2"})
        line = buf[0].get("line", "")
        self.assertEqual(line, "raw output\n")

    def test_raw_mode_agent_color(self):
        """Raw mode with agent_color_output='agent' wraps output in agent color."""
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="raw", sink=buf.append,
            agent_color_output="agent")
        streamer.emit({"role": "construqtor", "stream_name": "stdout",
                       "text": "raw output\n", "call_id": "c2"})
        line = buf[0].get("line", "")
        # Should have ANSI yellow for construQtor and the raw output
        self.assertIn("raw output", line)
        self.assertIn("\033[33m", line)

    def test_raw_mode_no_agent_color(self):
        """Raw mode with agent_color_output='none' has no color."""
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="raw", sink=buf.append,
            agent_color_output="none")
        streamer.emit({"role": "construqtor", "stream_name": "stdout",
                       "text": "raw output\n", "call_id": "c2"})
        line = buf[0].get("line", "")
        self.assertEqual(line, "raw output\n")

    def test_disabled_streamer_is_noop(self):
        buf = []
        streamer = AgentOutputStreamer(
            enabled=False, mode="prefixed", sink=buf.append)
        streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                       "text": "should not appear\n"})
        self.assertEqual(len(buf), 0)

    def test_stderr_gating(self):
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", stream_stderr=False,
            sink=buf.append)
        streamer.emit({"role": "construqtor", "stream_name": "stdout",
                       "text": "ok\n"})
        streamer.emit({"role": "construqtor", "stream_name": "stderr",
                       "text": "hidden\n"})
        self.assertEqual(len(buf), 1)
        self.assertIn("[construQtor] stdout", buf[0].get("line", ""))

    def test_redaction_in_streamer(self):
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", redact=True, sink=buf.append)
        streamer.emit({"role": "construqtor", "stream_name": "stdout",
                       "text": "DEEPSEEK_API_KEY=sk-secret123\n"})
        line = buf[0].get("line", "")
        self.assertNotIn("sk-secret123", line)
        self.assertIn("ƇΞƝƧØⱤΞƊ", line)

    def test_factory_creates_streamer(self):
        s = create_streamer(enabled=True, mode="raw")
        self.assertTrue(s.enabled)
        self.assertEqual(s.mode, "raw")


class TestMockStreaming(unittest.TestCase):
    """Mock adapter should emit simulated output when streaming is enabled."""

    def test_mock_streaming_emits_output(self):
        adapter = MockAdapter()
        sink_calls = []

        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="construqtor", model="mock", prompt="test",
                workdir=td, output_file="output.json",
                stream_output=True, stream_mode="prefixed",
                stream_stderr=True, output_sink=sink_calls.append,
            )
            result = adapter.call(spec)
            self.assertEqual(result.exit_code, 0)

        self.assertGreater(len(sink_calls), 0)
        texts = [c.get("text", "") for c in sink_calls]
        combined = "".join(texts)
        self.assertIn("mock build", combined.lower())

    def test_mock_no_streaming_no_sink_calls(self):
        adapter = MockAdapter()
        sink_calls = []

        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="construqtor", model="mock", prompt="test",
                workdir=td, output_file="output.json",
                stream_output=False, output_sink=sink_calls.append,
            )
            adapter.call(spec)

        self.assertEqual(len(sink_calls), 0)

    def test_mock_qlarifier_stream_output(self):
        adapter = MockAdapter()
        sink_calls = []

        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="qlarifier", model="mock", prompt="test",
                workdir=td, output_file="output.json",
                stream_output=True, output_sink=sink_calls.append,
            )
            result = adapter.call(spec)
            self.assertEqual(result.exit_code, 0)

        texts = [c.get("text", "") for c in sink_calls]
        combined = "".join(texts)
        self.assertIn("clarified task ready", combined.lower())

    def test_mock_instruqtor_stream_output(self):
        adapter = MockAdapter()
        sink_calls = []

        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="instruqtor", model="mock", prompt="test",
                workdir=td, output_file="output.json",
                stream_output=True, output_sink=sink_calls.append,
            )
            adapter.call(spec)

        texts = [c.get("text", "") for c in sink_calls]
        combined = "".join(texts)
        self.assertIn("briqs", combined.lower())

    def test_mock_inspeqtor_stream_output(self):
        adapter = MockAdapter()
        sink_calls = []

        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="inspeqtor", model="mock", prompt="test",
                workdir=td, output_file="output.json",
                stream_output=True, output_sink=sink_calls.append,
            )
            adapter.call(spec)

        texts = [c.get("text", "") for c in sink_calls]
        combined = "".join(texts)
        self.assertIn("NOT_DONE", combined)


class TestCodeSeeqStreamingCommand(unittest.TestCase):
    """Test CodeSeeqAdapter streaming command building with mocked Popen."""

    def test_streaming_uses_popen_not_run(self):
        from qq.adapters.codeseeq import CodeSeeqAdapter

        adapter = CodeSeeqAdapter(codeseeq_path="/fake/codeseeq")

        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                stream_output=True, stream_mode="prefixed",
                stream_stderr=True,
                artifact_dir=os.path.join(td, "artifacts"),
                call_id="call-0001",
            )

            mock_proc = MagicMock()
            mock_proc.stdout = io.StringIO("mock stdout line\n")
            mock_proc.stderr = io.StringIO("mock stderr line\n")
            mock_proc.wait.return_value = 0

            with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
                result = adapter.call(spec)

                mock_popen.assert_called_once()
                args, kwargs = mock_popen.call_args
                cmd = args[0]
                self.assertIn("/fake/codeseeq", cmd)
                self.assertIn("run", cmd)
                self.assertIn("-f", cmd)
                self.assertIn("--model", cmd)
                self.assertIn("deepseek-v4-flash", cmd)

                self.assertEqual(kwargs.get("cwd"), td)
                self.assertEqual(kwargs.get("stdout"), subprocess.PIPE)
                self.assertEqual(kwargs.get("stderr"), subprocess.PIPE)
                self.assertTrue(kwargs.get("text"))
                self.assertEqual(kwargs.get("bufsize"), 1)

                self.assertEqual(result.exit_code, 0)

    def test_batch_path_uses_run_when_no_streaming(self):
        from qq.adapters.codeseeq import CodeSeeqAdapter

        adapter = CodeSeeqAdapter(codeseeq_path="/fake/codeseeq")

        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                stream_output=False,
            )

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="ok", stderr="")
                adapter.call(spec)
                mock_run.assert_called_once()


class TestArtifactPreservation(unittest.TestCase):
    """Artifacts must still exist after streaming calls."""

    def test_mock_streaming_preserves_artifact_files(self):
        adapter = MockAdapter()

        with tempfile.TemporaryDirectory() as td:
            arts_dir = os.path.join(td, "artifacts")
            spec = AgentCallSpec(
                role="construqtor", model="mock", prompt="test prompt",
                workdir=td, output_file="output.json",
                stream_output=True, output_sink=lambda x: None,
                artifact_dir=arts_dir, call_id="call-0001",
            )
            adapter.call(spec)

            for fname in ("prompt.md", "stdout.txt", "stderr.txt",
                          "result.json", "metadata.json"):
                fpath = os.path.join(arts_dir, fname)
                self.assertTrue(os.path.exists(fpath),
                                f"Missing artifact: {fname}")

            with open(os.path.join(arts_dir, "stdout.txt")) as f:
                content = f.read()
            self.assertGreater(len(content), 0)

            with open(os.path.join(arts_dir, "metadata.json")) as f:
                meta = json.load(f)
            self.assertIn("stream_agent_output", meta)
            self.assertIn("stream_mode", meta)
            self.assertIn("stdout_bytes", meta)
            self.assertIn("stderr_bytes", meta)

    def test_mock_no_streaming_preserves_artifact_files(self):
        """Quiet mode (no streaming) still writes all artifacts."""
        adapter = MockAdapter()

        with tempfile.TemporaryDirectory() as td:
            arts_dir = os.path.join(td, "artifacts")
            spec = AgentCallSpec(
                role="construqtor", model="mock", prompt="test prompt",
                workdir=td, output_file="output.json",
                stream_output=False,
                artifact_dir=arts_dir, call_id="call-0001",
            )
            adapter.call(spec)

            for fname in ("prompt.md", "stdout.txt", "stderr.txt",
                          "result.json", "metadata.json"):
                fpath = os.path.join(arts_dir, fname)
                self.assertTrue(os.path.exists(fpath),
                                f"Missing artifact: {fname}")


class TestDeadlockPrevention(unittest.TestCase):
    """Both stdout and stderr must be read concurrently."""

    def test_both_streams_read(self):
        """When Popen produces both stdout and stderr, both should be captured."""
        from qq.adapters.codeseeq import CodeSeeqAdapter

        adapter = CodeSeeqAdapter(codeseeq_path="/fake/codeseeq")

        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            arts_dir = os.path.join(td, "artifacts")
            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                stream_output=True,
                artifact_dir=arts_dir,
                call_id="call-dl-1",
            )

            mock_proc = MagicMock()
            mock_proc.stdout = io.StringIO("line1\nline2\nline3\n")
            mock_proc.stderr = io.StringIO("err1\nerr2\n")
            mock_proc.wait.return_value = 0
            mock_proc.returncode = 0

            import subprocess
            with patch("subprocess.Popen", return_value=mock_proc):
                result = adapter.call(spec)

            self.assertIn("line1", result.stdout)
            self.assertIn("line2", result.stdout)
            self.assertIn("err1", result.stderr)

    def test_long_output_no_deadlock(self):
        """Large outputs on both streams should not deadlock."""
        from qq.adapters.codeseeq import CodeSeeqAdapter

        adapter = CodeSeeqAdapter(codeseeq_path="/fake/codeseeq")

        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            big_stdout = "".join(f"line{i}\n" for i in range(1000))
            big_stderr = "".join(f"err{i}\n" for i in range(500))

            arts_dir = os.path.join(td, "artifacts")
            spec2 = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                stream_output=True,
                artifact_dir=arts_dir,
                call_id="call-dl-2",
            )

            mock_proc = MagicMock()
            mock_proc.stdout = io.StringIO(big_stdout)
            mock_proc.stderr = io.StringIO(big_stderr)
            mock_proc.wait.return_value = 0
            mock_proc.returncode = 0

            with patch("subprocess.Popen", return_value=mock_proc):
                result = adapter.call(spec2)

            self.assertEqual(len(result.stdout.splitlines()), 1000)
            self.assertEqual(len(result.stderr.splitlines()), 500)


class TestSecretRedactionInStreaming(unittest.TestCase):
    """Terminal output must be redacted, artifacts may keep raw content."""

    def test_stream_sink_redacted(self):
        """Output sent to streamer (via AgentOutputStreamer) should have secrets redacted."""
        from qq.adapters.codeseeq import CodeSeeqAdapter
        from qq.streaming import AgentOutputStreamer

        sink_calls = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", redact=True, sink=sink_calls.append)

        adapter = CodeSeeqAdapter(codeseeq_path="/fake/codeseeq")

        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "output.json")
            with open(output_path, "w") as f:
                json.dump({"status": "ok"}, f)

            arts_dir = os.path.join(td, "artifacts")
            spec = AgentCallSpec(
                role="construqtor", model="deepseek-v4-flash",
                prompt="build", workdir=td,
                output_file="output.json",
                stream_output=True, output_sink=streamer.emit,
                artifact_dir=arts_dir,
                call_id="call-redact-1",
            )

            mock_proc = MagicMock()
            mock_proc.stdout = io.StringIO(
                "DEEPSEEK_API_KEY=sk-secret123\n"
                "Bearer sk-abcdef1234567890\n"
                "password=supersecret\n"
            )
            mock_proc.stderr = io.StringIO("")
            mock_proc.wait.return_value = 0
            mock_proc.returncode = 0

            with patch("subprocess.Popen", return_value=mock_proc):
                adapter.call(spec)

            sink_texts = [c.get("line", "") for c in sink_calls]
            sink_combined = "".join(sink_texts)
            self.assertNotIn("sk-secret123", sink_combined)
            self.assertNotIn("sk-abcdef1234567890", sink_combined)
            self.assertNotIn("supersecret", sink_combined)
            self.assertIn("ƇΞƝƧØⱤΞƊ", sink_combined)

    def test_streamer_redacts_all_secret_types(self):
        """Test AgentOutputStreamer redacts all secret patterns."""
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", redact=True, sink=buf.append)

        test_cases = [
            ("DEEPSEEK_API_KEY=sk-secret123\n", "sk-secret123"),
            ("OPENAI_API_KEY=sk-openai-key\n", "sk-openai-key"),
            ("Bearer sk-abcdef1234567890\n", "sk-abcdef1234567890"),
            ("password=supersecret\n", "supersecret"),
            ("token=abc123def\n", "abc123def"),
            ("Api_Key=hunter2\n", "hunter2"),
            ("SECRET=mysecret\n", "mysecret"),
        ]

        for text, secret in test_cases:
            buf.clear()
            streamer.emit({
                "role": "construqtor", "stream_name": "stdout",
                "text": text,
            })
            line = buf[0].get("line", "")
            self.assertNotIn(secret, line,
                            f"Secret '{secret}' not redacted in '{line}'")
            self.assertIn("ƇΞƝƧØⱤΞƊ", line,
                         f"ƇΞƝƧØⱤΞƊ missing for '{text}'")

    def test_non_secret_text_preserved(self):
        """Normal output should not be redacted."""
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", redact=True, sink=buf.append)
        streamer.emit({
            "role": "construqtor", "stream_name": "stdout",
            "text": "echo hello world\n",
        })
        line = buf[0].get("line", "")
        self.assertIn("hello world", line)
        self.assertNotIn("ƇΞƝƧØⱤΞƊ", line)


class TestQuietModeUnchanged(unittest.TestCase):
    """Without --stream-agent-output, normal Qq status output remains concise."""

    def test_quiet_mode_no_streaming(self):
        tmp = tempfile.mkdtemp(prefix="qq_quiet_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                briq_sensitivity=5, max_cycles=60,
                stream_agent_output=False,
            )
            adapter = MockAdapter()
            events = []
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
                on_event=lambda msg: events.append(msg),
            )
            self.assertEqual(state.status.value, "done")

            status_events = [e for e in events]
            self.assertGreater(len(status_events), 0)
            for e in status_events:
                self.assertTrue(
                    isinstance(e, str) and len(e) > 0,
                    f"Event should be a string: {e}"
                )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestStreamingDryRunEndToEnd(unittest.TestCase):
    """Full dry-run with streaming enabled via direct run() invocation."""

    def test_streaming_dry_run_reaches_done(self):
        tmp = tempfile.mkdtemp(prefix="qq_stream_dr_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                briq_sensitivity=5, max_cycles=60,
                stream_agent_output=True,
                stream_mode="prefixed",
                stream_stderr=True,
            )
            adapter = MockAdapter()
            events = []
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
                on_event=lambda msg: events.append(msg),
            )
            self.assertEqual(state.status.value, "done")

            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as f:
                log_events = [json.loads(line) for line in f if line.strip()]

            config_loaded = [e for e in log_events if e["type"] == "config.loaded"]
            self.assertEqual(len(config_loaded), 1)
            self.assertTrue(config_loaded[0].get("stream_agent_output"))

            finished = [e for e in log_events if e["type"] == "agent.call.finished"]
            self.assertGreater(len(finished), 0)
            for fe in finished:
                self.assertIn("stdout_bytes", fe)
                self.assertIn("streamed", fe)

            agents_dir = os.path.join(config.run_root, "agents")
            self.assertTrue(os.path.isdir(agents_dir))

            call_dirs = []
            for root, dnames, fnames in os.walk(agents_dir):
                for d in dnames:
                    if d.startswith("call-"):
                        call_dirs.append(os.path.join(root, d))
            self.assertGreater(len(call_dirs), 0)

            for cd in call_dirs:
                for fname in ("prompt.md", "stdout.txt", "stderr.txt",
                             "result.json", "metadata.json"):
                    self.assertTrue(
                        os.path.exists(os.path.join(cd, fname)),
                        f"Missing {fname} in {cd}")

        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestQontrollerConfigStreaming(unittest.TestCase):
    """QontrollerConfig streaming fields."""

    def test_streaming_fields_default_false(self):
        c = QontrollerConfig(
            repo_root="/tmp", run_root="/tmp/runs/t",
            model_qlarifier="m", model_instruqtor="m",
            model_construqtor="m", model_inspeqtor="m",
        )
        self.assertFalse(c.stream_agent_output)
        self.assertEqual(c.stream_mode, "prefixed")
        self.assertTrue(c.stream_stderr)
        self.assertFalse(c.show_prompts)

    def test_streaming_fields_set(self):
        c = QontrollerConfig(
            repo_root="/tmp", run_root="/tmp/runs/t",
            model_qlarifier="m", model_instruqtor="m",
            model_construqtor="m", model_inspeqtor="m",
            stream_agent_output=True,
            stream_mode="raw",
            stream_stderr=False,
            show_prompts=True,
        )
        self.assertTrue(c.stream_agent_output)
        self.assertEqual(c.stream_mode, "raw")
        self.assertFalse(c.stream_stderr)
        self.assertTrue(c.show_prompts)


class TestAgentCallSpecStreaming(unittest.TestCase):
    """AgentCallSpec streaming fields."""

    def test_streaming_fields_on_spec(self):
        spec = AgentCallSpec(
            role="construqtor", model="m", prompt="p",
            workdir="/tmp", output_file="o.json",
            stream_output=True, stream_mode="raw",
            stream_stderr=False,
        )
        self.assertTrue(spec.stream_output)
        self.assertEqual(spec.stream_mode, "raw")
        self.assertFalse(spec.stream_stderr)

    def test_default_no_streaming(self):
        spec = AgentCallSpec(
            role="construqtor", model="m", prompt="p",
            workdir="/tmp", output_file="o.json",
        )
        self.assertFalse(spec.stream_output)
        self.assertIsNone(spec.output_sink)


class TestQlarifierStreamingProof(unittest.TestCase):
    """Prove Qlarifier streaming works end-to-end — terminal output + event log,
    using direct run() invocation instead of CLI subprocess."""

    def test_all_agents_stream_in_dry_run(self):
        """Full dry-run with --stream-agent-output must show streaming output
        for all four agents: qlarifier, instruqtor, construqtor, inspeqtor.
        Proved via event log inspection (streamed=true on all agent.call.finished
        events) and agent.output.started events."""
        import shutil
        tmp = tempfile.mkdtemp(prefix="qq_stream_proof_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                briq_sensitivity=5, max_cycles=10,
                stream_agent_output=True,
                stream_mode="prefixed",
                stream_stderr=True,
            )
            adapter = MockAdapter()

            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
            )

            self.assertEqual(state.status.value, "done")

            # Check event log
            events_path = os.path.join(config.run_root, "events.jsonl")
            self.assertTrue(os.path.exists(events_path))

            with open(events_path) as f:
                log_events = [json.loads(line) for line in f if line.strip()]

            # Verify each role is marked streamed
            for role in ("qlarifier", "instruqtor", "construqtor", "inspeqtor"):
                role_finished = [
                    e for e in log_events
                    if e["type"] == "agent.call.finished"
                    and e.get("role") == role
                ]
                self.assertGreater(len(role_finished), 0,
                                   f"No finished event for {role}")
                for fe in role_finished:
                    self.assertTrue(fe.get("streamed"),
                                    f"{role} not marked streamed: {fe}")

            # Verify agent.output.started emitted for qlarifier
            qlarifier_started = [
                e for e in log_events
                if e["type"] == "agent.output.started"
                and e.get("role") == "qlarifier"
            ]
            self.assertGreater(len(qlarifier_started), 0,
                               "No agent.output.started event for qlarifier")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_qlarifier_status_before_stream(self):
        """Qlarifier status line should appear before qlarifier streamed output,
        tested via direct run() invocation with event-log inspection."""
        import shutil
        tmp = tempfile.mkdtemp(prefix="qq_order_")
        try:
            config = QontrollerConfig(
                repo_root=tmp,
                run_root=os.path.join(tmp, ".qq", "runs", "test"),
                model_qlarifier="mock", model_instruqtor="mock",
                model_construqtor="mock", model_inspeqtor="mock",
                briq_sensitivity=5, max_cycles=10,
                stream_agent_output=True,
                stream_mode="prefixed",
                stream_stderr=True,
            )
            adapter = MockAdapter()

            events = []
            state = run(
                "build a thing", adapter, config,
                ask_human=lambda qs: ["n/a"] * len(qs),
                on_event=lambda msg: events.append(msg),
            )
            self.assertEqual(state.status.value, "done")

            # Events should contain Qlarifier status line
            status_events = [e for e in events if isinstance(e, str)]
            qlarifier_status = [e for e in status_events if "Qlarifier" in e]
            self.assertGreater(len(qlarifier_status), 0,
                               "Missing Qlarifier status line in events")

            # Check event log ordering: config.loaded before agent.output.started
            events_path = os.path.join(config.run_root, "events.jsonl")
            with open(events_path) as f:
                log_events = [json.loads(line) for line in f if line.strip()]

            # Find indices
            config_idx = None
            qlarifier_output_idx = None
            for i, e in enumerate(log_events):
                if e["type"] == "config.loaded":
                    config_idx = i
                if e["type"] == "agent.output.started" and e.get("role") == "qlarifier":
                    qlarifier_output_idx = i

            self.assertIsNotNone(config_idx, "config.loaded not found")
            self.assertIsNotNone(qlarifier_output_idx,
                                 "agent.output.started for qlarifier not found")
            self.assertLess(config_idx, qlarifier_output_idx,
                            "config.loaded must appear before agent.output.started")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestStreamIndicator(unittest.TestCase):
    """Stream indicator modes: stream, spinner, none."""

    def test_default_indicator_is_stream(self):
        """Default prefixed mode still includes [Qlarifier] stdout."""
        cfg = resolve_config(dry_run=True, stream_agent_output=True)
        self.assertEqual(cfg.stream_indicator, "stream")

        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", indicator="stream",
            sink=buf.append)
        streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                       "text": "hello\n", "call_id": "c1"})
        line = buf[0].get("line", "")
        self.assertIn("[Qlarifier] stdout", line)

    def test_spinner_indicator_shows_spinner_frame(self):
        """Spinner mode shows a braille spinner frame instead of stdout/stderr."""
        cfg = resolve_config(dry_run=True, stream_agent_output=True,
                            stream_indicator="spinner")
        self.assertEqual(cfg.stream_indicator, "spinner")

        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", indicator="spinner",
            sink=buf.append)
        streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                       "text": "hello\n", "call_id": "c1"})
        line = buf[0].get("line", "")
        # Should contain role label
        self.assertIn("[Qlarifier]", line)
        # Should contain a spinner frame character (braille)
        from qq.streaming import _SPINNER_FRAMES
        has_spinner = any(frame in line for frame in _SPINNER_FRAMES)
        self.assertTrue(has_spinner, f"No spinner frame found in: {line!r}")
        # Should NOT contain literal "stdout" after the prefix
        prefix_end = line.index("]") + 1
        after_prefix = line[prefix_end:].strip()
        self.assertNotIn("stdout", after_prefix.split("hello")[0])

    def test_spinner_advances_per_chunk(self):
        """Spinner must advance frame per emitted chunk."""
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", indicator="spinner",
            sink=buf.append)
        for i in range(3):
            streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                           "text": f"line{i}\n", "call_id": "c1"})
        self.assertEqual(len(buf), 3)
        # Extract spinner frames
        from qq.streaming import _SPINNER_FRAMES
        frames_seen = []
        for item in buf:
            line = item.get("line", "")
            for frame in _SPINNER_FRAMES:
                if frame in line:
                    frames_seen.append(frame)
                    break
        self.assertEqual(len(frames_seen), 3,
                         f"Expected 3 spinner frames, got {frames_seen}")
        # Frames should advance (not all the same)
        self.assertFalse(all(f == frames_seen[0] for f in frames_seen),
                         f"All frames identical: {frames_seen}")

    def test_spinner_per_stream_independent(self):
        """Spinner state is per (role, stream_name, call_id), so concurrent
        streams don't share a broken frame counter."""
        # Reset global spinner state to isolate this test
        import qq.streaming
        qq.streaming._spinner_state.clear()

        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", indicator="spinner",
            sink=buf.append)

        # stdout line
        streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                       "text": "out1\n", "call_id": "c1"})
        # stderr line — different stream, should use its own counter
        streamer.emit({"role": "qlarifier", "stream_name": "stderr",
                       "text": "err1\n", "call_id": "c1"})

        self.assertEqual(len(buf), 2)
        line_out = buf[0].get("line", "")
        line_err = buf[1].get("line", "")

        from qq.streaming import _SPINNER_FRAMES
        # Both should show the first spinner frame since they are different streams
        self.assertIn(_SPINNER_FRAMES[0], line_out,
                      f"Expected first frame in stdout: {line_out!r}")
        self.assertIn(_SPINNER_FRAMES[0], line_err,
                      f"Expected first frame in stderr: {line_err!r}")

    def test_none_indicator_shows_only_role(self):
        """none indicator shows only [Qlarifier] without stream or spinner."""
        cfg = resolve_config(dry_run=True, stream_agent_output=True,
                            stream_indicator="none")
        self.assertEqual(cfg.stream_indicator, "none")

        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="prefixed", indicator="none",
            sink=buf.append)
        streamer.emit({"role": "qlarifier", "stream_name": "stdout",
                       "text": "hello\n", "call_id": "c1"})
        line = buf[0].get("line", "")
        self.assertIn("[Qlarifier]", line)
        self.assertIn("hello", line)
        # After the prefix, should not have "stdout" or spinner
        prefix_end = line.index("]") + 1
        after_prefix = line[prefix_end:].strip()
        self.assertNotIn("stdout", after_prefix.split("hello")[0])
        self.assertNotIn("stderr", after_prefix.split("hello")[0])

    def test_raw_mode_ignores_indicator(self):
        """Raw mode ignores spinner indicator and stays raw."""
        buf = []
        streamer = AgentOutputStreamer(
            enabled=True, mode="raw", indicator="spinner",
            sink=buf.append, agent_color_output="original")
