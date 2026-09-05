"""Tests for qq.agents._jsonio.call_for_json retry/error classification.

These lock in the fix for the "stream disconnected" failure mode: when the
agent *process* crashes (non-zero exit code), call_for_json must retry the
original prompt with the original timeout (not a halved one), and the final
error must surface the real stderr tail instead of the startup banner.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters.base import AgentCallResult, AgentCallSpec
from qq.agents._jsonio import AgentOutputError, call_for_json


class _RecordingAdapter:
    """Fake adapter that returns a fixed result and records each call's spec."""

    def __init__(self, result: AgentCallResult):
        self.result = result
        self.calls = []

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        self.calls.append(spec)
        return self.result


def _make_result(spec, exit_code, stderr, stdout="", output_exists=False,
                 raw_output=None):
    return AgentCallResult(
        spec=spec,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=0.1,
        output_path_exists=output_exists,
        raw_output_text=raw_output,
    )


class TestConnectionErrorRetry(unittest.TestCase):
    def test_process_failure_retries_original_timeout_and_reports_tail(self):
        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="instruqtor", model="m", prompt="hello",
                workdir=td, output_file=os.path.join(td, "out.json"),
                timeout_seconds=600,
            )
            stderr = (
                "[codeseeq] bridge mode: process\n"
                "[codeseeq] bridge log: /tmp/bridge.log\n"
                "ERROR: stream disconnected before completion: "
                "error sending request for url (http://127.0.0.1:8080/v1/responses)"
            )
            adapter = _RecordingAdapter(
                _make_result(spec, exit_code=-1, stderr=stderr))

            with self.assertRaises(AgentOutputError) as ctx:
                call_for_json(adapter, spec, max_repairs=1)

            # Retried once (2 total calls), with the ORIGINAL timeout retained.
            self.assertEqual(len(adapter.calls), 2)
            self.assertEqual(adapter.calls[1].timeout_seconds, 600)
            # The retry prompt must NOT be the "write only JSON" sharpening.
            self.assertEqual(adapter.calls[1].prompt, "hello")

            err = str(ctx.exception)
            self.assertIn("agent process failed", err)
            self.assertIn("stream disconnected", err)
            # The startup banner (first lines) is no longer the only diagnostic.
            self.assertIn("error sending request", err)

    def test_missing_json_keeps_sharpen_prompt_and_halved_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            spec = AgentCallSpec(
                role="instruqtor", model="m", prompt="hello",
                workdir=td, output_file=os.path.join(td, "out.json"),
                timeout_seconds=600,
            )
            adapter = _RecordingAdapter(
                _make_result(spec, exit_code=0, stderr=""))

            with self.assertRaises(AgentOutputError) as ctx:
                call_for_json(adapter, spec, max_repairs=1)

            self.assertEqual(len(adapter.calls), 2)
            self.assertEqual(adapter.calls[1].timeout_seconds, 300)
            self.assertIn("PREVIOUS ATTEMPT FAILED", adapter.calls[1].prompt)

            err = str(ctx.exception)
            self.assertIn("agent did not write", err)
            self.assertNotIn("agent process failed", err)


if __name__ == "__main__":
    unittest.main()
