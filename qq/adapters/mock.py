"""
Mock adapter for offline testing of the Qontroller loop — with streaming support.

Supports QQ_MOCK_STREAM_DELAY env var for multi-chunk delayed streaming tests.
"""
from __future__ import annotations

import json
import os
import sys
import time

from .base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities
from ..path_guards import assert_command_cwd_allowed, assert_project_write_allowed, PathPolicyViolation


class MockAdapter(AgentAdapter):
    name = "mock"

    def __init__(self):
        self._review_calls = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_exec_mode=True, supports_tools=True)

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        # Path guard enforcement
        ws_root = spec.workspace_root or spec.repo_root or spec.cd or spec.workdir
        run_root = spec.run_root or ""
        if ws_root and run_root:
            assert_command_cwd_allowed(spec.workdir, ws_root, run_root)
            cd_path = spec.cd or spec.repo_root or spec.workdir
            assert_command_cwd_allowed(cd_path, ws_root, run_root)

        os.makedirs(spec.workdir, exist_ok=True)
        output_path = spec.output_file if os.path.isabs(spec.output_file) else os.path.join(spec.workdir, spec.output_file)
        payload = self._canned_response(spec)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        # Mock construQtor also "implements" something real
        if spec.role == "construqtor":
            main_path = os.path.join(spec.workdir, "main.py")
            if ws_root and run_root:
                assert_project_write_allowed(main_path, ws_root, run_root)
            with open(main_path, "w", encoding="utf-8") as fh:
                fh.write('print("hello from the mock build")\n')

        # Streaming support
        streaming = getattr(spec, 'stream_output', False)
        mock_stdout = ""
        mock_stderr = ""

        if streaming:
            # Check for stream delay env var (for testing live streaming)
            stream_delay = float(os.environ.get("QQ_MOCK_STREAM_DELAY", "0"))

            # Emit simulated output through the sink
            sink = getattr(spec, 'output_sink', None)
            role = spec.role
            call_id = getattr(spec, 'call_id', '')

            # Get multi-chunk simulated output when delay is enabled
            if stream_delay > 0:
                sim = self._simulated_output_delayed(spec)
            else:
                sim = self._simulated_output(spec)

            if sink and sim:
                for stream_name, text in sim:
                    mock_stdout += text if stream_name == "stdout" else ""
                    mock_stderr += text if stream_name == "stderr" else ""
                    try:
                        sink({
                            "role": role,
                            "stream_name": stream_name,
                            "text": text,
                            "call_id": call_id,
                        })
                    except Exception:
                        pass
                    if stream_delay > 0:
                        time.sleep(stream_delay)
        else:
            mock_stdout = "[mock adapter] ok\n"
            mock_stderr = ""

        # Write artifact files if artifact_dir is set
        if spec.artifact_dir:
            os.makedirs(spec.artifact_dir, exist_ok=True)
            # prompt.md
            with open(os.path.join(spec.artifact_dir, "prompt.md"), "w",
                      encoding="utf-8") as fh:
                fh.write(spec.prompt)
            # stdout.txt — use simulated output if streaming, else default
            with open(os.path.join(spec.artifact_dir, "stdout.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(mock_stdout if mock_stdout else "[mock adapter] ok\n")
            # stderr.txt
            with open(os.path.join(spec.artifact_dir, "stderr.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(mock_stderr)
            # result.json
            with open(os.path.join(spec.artifact_dir, "result.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            # metadata.json
            metadata = {
                "role": spec.role,
                "model": spec.model,
                "exit_code": 0,
                "duration_seconds": 0.01,
                "output_path_exists": True,
                "thinking": spec.thinking,
                "call_id": spec.call_id,
                "stream_agent_output": streaming,
                "stream_mode": getattr(spec, 'stream_mode', 'prefixed'),
                "stream_indicator": getattr(spec, 'stream_indicator', 'stream'),
                "stdout_bytes": len(mock_stdout.encode("utf-8")),
                "stderr_bytes": len(mock_stderr.encode("utf-8")),
                "return_code": 0,
                "duration": 0.01,
            }
            with open(os.path.join(spec.artifact_dir, "metadata.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(metadata, fh, indent=2)

        return AgentCallResult(
            spec=spec, exit_code=0,
            stdout=mock_stdout or "[mock adapter] ok",
            stderr=mock_stderr,
            duration_seconds=0.01, output_path_exists=True,
            raw_output_text=json.dumps(payload),
        )

    def _simulated_output(self, spec: AgentCallSpec):
        """Return simulated output lines for streaming mode."""
        if spec.role == "qlarifier":
            return [
                ("stdout", "clarified task ready\n"),
            ]
        if spec.role == "instruqtor":
            return [
                ("stdout", "created 2 briQs across 1 build group\n"),
            ]
        if spec.role == "construqtor":
            return [
                ("stdout", f"mock build cycle {getattr(spec, 'call_id', '?')} wrote files\n"),
            ]
        if spec.role == "inspeqtor":
            return [
                ("stdout", "\033[31mNOT_DONE\033[0m: one issue found\n"),
            ]
        return []

    def _simulated_output_delayed(self, spec: AgentCallSpec):
        """Return multi-chunk simulated output for live-streaming proof tests.

        Each agent produces 3 chunks so we can verify each chunk arrives
        before the agent "finishes" — proving the streaming is live, not
        end-buffered.
        """
        call_id = getattr(spec, 'call_id', '')
        if spec.role == "qlarifier":
            return [
                ("stdout", f"[{call_id}] reading task...\n"),
                ("stdout", f"[{call_id}] analyzing requirements...\n"),
                ("stdout", "clarified task ready\n"),
            ]
        if spec.role == "instruqtor":
            return [
                ("stdout", f"[{call_id}] splitting into briQs...\n"),
                ("stdout", f"[{call_id}] grouping into build groups...\n"),
                ("stdout", "created 2 briQs across 1 build group\n"),
            ]
        if spec.role == "construqtor":
            return [
                ("stdout", f"[{call_id}] starting build...\n"),
                ("stdout", f"[{call_id}] writing files...\n"),
                ("stdout", "mock build cycle ... wrote files\n"),
            ]
        if spec.role == "inspeqtor":
            return [
                ("stdout", f"[{call_id}] reviewing code...\n"),
                ("stdout", f"[{call_id}] checking against task...\n"),
                ("stdout", "\033[31mNOT_DONE\033[0m: one issue found\n"),
            ]
        return []

    def _canned_response(self, spec: AgentCallSpec):
        if spec.role == "qlarifier":
            return {
                "status": "clarified",
                "clarified_task": "(mock) build a tiny CLI hello-world tool",
                "notes_for_instruqtor": "single file, no external deps",
            }
        if spec.role == "instruqtor":
            return {
                "summary": "(mock) one build group, two briqs",
                "build_groups": [{
                    "build_group_id": "bg-core", "name": "core",
                    "description": "core CLI", "parallel_safe": False,
                    "briqs": [
                        {"briq_id": "briq-1", "title": "scaffold",
                         "description": "create entrypoint", "sensitivity": 5},
                        {"briq_id": "briq-2", "title": "hello",
                         "description": "print hello", "sensitivity": 5},
                    ],
                }],
            }
        if spec.role == "construqtor":
            return {"status": "implemented", "files_changed": ["main.py"]}
        if spec.role == "inspeqtor":
            self._review_calls += 1
            if self._review_calls >= 2:
                return {"status": "FULLY_DONE",
                         "summary": "(mock) looks good", "score": 97,
                         "issues": []}
            return {
                "status": "NOT_DONE",
                "score": 68,
                "summary": "(mock) missing hello output",
                "issues": [{
                    "build_group_id": "bg-core", "briq_id": "briq-2",
                    "severity": "blocking",
                    "what_is_wrong": "no output produced",
                    "what_to_fix": "actually print hello",
                    "files": ["main.py"],
                }],
            }
        return {"status": "ok"}
