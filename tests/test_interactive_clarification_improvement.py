import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QRANE_DIR = PROJECT_ROOT / ".qonqrete" / "qrane"
sys.path.insert(0, str(QRANE_DIR))

import qrane

# Mocking internal dependencies that are not available in the test environment
qrane.mark_clarification_blocked = MagicMock()
qrane.record_agent_completion = MagicMock()

def write_not_ready_artifacts(workspace: Path, question_id="q-1") -> None:
    task_dir = workspace / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-spec.v1.json").write_text(
        json.dumps(
            {
                "ready": False,
                "status": "NOT_READY",
                "run_id": "test-run",
                "inputs": [
                    {"name": "raw_task", "source_ref": "tasq.d/cyqle1_tasq.md"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "clarification-log.v1.json").write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": question_id,
                        "reason": "Task does not state a concrete implementation action.",
                        "question": "What specific implementation outcome is required?",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

def write_ready_artifacts(workspace: Path) -> None:
    task_dir = workspace / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-spec.v1.json").write_text(
        json.dumps(
            {
                "ready": True,
                "status": "READY",
                "run_id": "test-run",
                "inputs": [
                    {"name": "raw_task", "source_ref": "tasq.d/cyqle1_tasq.md"},
                ],
            }
        ),
        encoding="utf-8",
    )

class TestClarificationImprovement(unittest.TestCase):
    @patch('sys.stdin.isatty', return_value=True)
    @patch('sys.stdout.isatty', return_value=True)
    def test_should_prompt_for_clarification_tty(self, mock_stdout, mock_stdin):
        with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "", "CI": ""}, clear=False):
            self.assertTrue(qrane.should_prompt_for_clarification())

    @patch('sys.stdin.isatty', return_value=True)
    @patch('sys.stdout.isatty', return_value=False)
    def test_should_prompt_for_clarification_stdin_tty_stdout_not_tty(self, mock_stdout, mock_stdin):
        with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "", "CI": ""}, clear=False):
            self.assertFalse(qrane.should_prompt_for_clarification())

    @patch('sys.stdin.isatty', return_value=False)
    @patch('sys.stdout.isatty', return_value=True)
    def test_should_prompt_for_clarification_no_tty(self, mock_stdout, mock_stdin):
        with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "", "CI": ""}, clear=False):
            self.assertFalse(qrane.should_prompt_for_clarification())

    @patch('sys.stdin.isatty', return_value=True)
    @patch('sys.stdout.isatty', return_value=True)
    def test_should_prompt_for_clarification_non_interactive_env(self, mock_stdout, mock_stdin):
        with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "1", "CI": ""}, clear=False):
            self.assertFalse(qrane.should_prompt_for_clarification())

    @patch('sys.stdin.isatty', return_value=True)
    @patch('sys.stdout.isatty', return_value=True)
    def test_should_prompt_for_clarification_force_interactive_env(self, mock_stdout, mock_stdin):
        with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "1", "QONQ_INTERACTIVE_CLARIFICATION": "1"}, clear=False):
            self.assertTrue(qrane.should_prompt_for_clarification())

    @patch('sys.stdin.isatty', return_value=True)
    @patch('sys.stdout.isatty', return_value=True)
    def test_should_prompt_for_clarification_force_non_interactive_flag(self, mock_stdout, mock_stdin):
        with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "", "CI": ""}, clear=False):
            self.assertFalse(qrane.should_prompt_for_clarification(force_non_interactive=True))

    @patch('sys.stdin.isatty', return_value=True)
    def test_handle_intake_clarification_non_interactive_env_pauses_without_prompt(self, mock_stdin):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace)
            with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "1", "CI": ""}, clear=False):
                with patch("builtins.input", side_effect=AssertionError("input() must not be called")):
                    result = qrane.handle_intake_clarification(
                        workspace,
                        prefix="uQQ",
                        is_autonomous=False,
                        config={},
                        cycle=1,
                        qrystallizer_cmd=["python3", "qrystallizer.py"],
                        env=dict(os.environ),
                        qonsole_log_path=workspace / "qonsole.log"
                    )
            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_waiting_for_input")
            response_path = workspace / "task" / "clarification-response.v1.json"
            self.assertTrue(response_path.exists())

    @patch('sys.stdin.isatty', return_value=False)
    def test_handle_intake_clarification_ci_pauses_without_prompt(self, mock_stdin):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace)
            with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "", "CI": "1"}, clear=False):
                with patch("builtins.input", side_effect=AssertionError("input() must not be called")):
                    result = qrane.handle_intake_clarification(
                        workspace,
                        prefix="uQQ",
                        is_autonomous=False,
                        config={},
                        cycle=1,
                        qrystallizer_cmd=["python3", "qrystallizer.py"],
                        env=dict(os.environ),
                        qonsole_log_path=workspace / "qonsole.log"
                    )
            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_waiting_for_input")
            response_path = workspace / "task" / "clarification-response.v1.json"
            self.assertTrue(response_path.exists())

    @patch('sys.stdin.isatty', return_value=True)
    @patch('sys.stdout.isatty', return_value=True)
    @patch('builtins.input', return_value="Detailed requirement")
    @patch('qrane.run_agent', return_value=True)
    @patch('qrane.canonical_run_id', return_value="test-run")
    def test_force_interactive_clarification_overrides_non_interactive_env(self, mock_run_id, mock_run, mock_input, mock_stdout, mock_stdin):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace)

            def side_effect(*args, **kwargs):
                write_ready_artifacts(workspace)
                return True
            mock_run.side_effect = side_effect

            with patch.dict(os.environ, {"QONQ_NON_INTERACTIVE": "1", "CI": ""}, clear=False):
                result = qrane.handle_intake_clarification(
                    workspace,
                    prefix="uQQ",
                    is_autonomous=False,
                    config={},
                    cycle=1,
                    qrystallizer_cmd=["python3", "qrystallizer.py"],
                    env=dict(os.environ),
                    qonsole_log_path=workspace / "qonsole.log",
                    force_interactive=True,
                )

            self.assertEqual(result["outcome"], "ready")

    @patch('qrane.resolve_clarification_prompt_mode', return_value=(True, "test_interactive"))
    @patch('builtins.input', return_value="Test Answer")
    @patch('qrane.run_agent', return_value=True)
    @patch('qrane.canonical_run_id', return_value="test-run")
    def test_handle_intake_clarification_interactive_success(self, mock_run_id, mock_run, mock_input, mock_mode):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace)
            
            # First run: NOT_READY. Rerun should make it READY.
            def side_effect(*args, **kwargs):
                write_ready_artifacts(workspace)
                return True
            mock_run.side_effect = side_effect

            result = qrane.handle_intake_clarification(
                workspace,
                prefix="uQQ",
                is_autonomous=False,
                config={},
                cycle=1,
                qrystallizer_cmd=["python3", "qrystallizer.py"],
                env={},
                qonsole_log_path=workspace / "qonsole.log"
            )

            self.assertEqual(result["outcome"], "ready")
            self.assertEqual(result["status"], "READY")
            
            response_path = workspace / "task" / "clarification-response.v1.json"
            self.assertTrue(response_path.exists())
            data = json.loads(response_path.read_text())
            # Find the answer for q-1
            answer = next(a for a in data["answers"] if a["question_id"] == "q-1")
            self.assertEqual(answer["answer"], "Test Answer")

    @patch('qrane.resolve_clarification_prompt_mode', return_value=(True, "test_interactive"))
    @patch('builtins.input', return_value="Test Answer")
    @patch('qrane.run_agent', return_value=True)
    @patch('qrane.canonical_run_id', return_value="test-run")
    def test_handle_intake_clarification_infinite_loop_protection(self, mock_run_id, mock_run, mock_input, mock_mode):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace, question_id="q-1")
            
            # Qrystallizer keeps returning the same question
            mock_run.return_value = True 

            result = qrane.handle_intake_clarification(
                workspace,
                prefix="uQQ",
                is_autonomous=False,
                config={"agents": {"qrystallizer": {"max_clarification_rounds": 3}}},
                cycle=1,
                qrystallizer_cmd=["python3", "qrystallizer.py"],
                env={},
                qonsole_log_path=workspace / "qonsole.log"
            )

            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_infinite_loop_detected")

    @patch('qrane.resolve_clarification_prompt_mode', return_value=(True, "test_interactive"))
    @patch('builtins.input', return_value="/skip")
    @patch('qrane.canonical_run_id', return_value="test-run")
    def test_skip_is_recorded_and_run_pauses(self, mock_run_id, mock_input, mock_mode):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace, question_id="q-1")

            result = qrane.handle_intake_clarification(
                workspace,
                prefix="uQQ",
                is_autonomous=False,
                config={"agents": {"qrystallizer": {"max_clarification_rounds": 1}}},
                cycle=1,
                qrystallizer_cmd=["python3", "qrystallizer.py"],
                env={},
                qonsole_log_path=workspace / "qonsole.log"
            )

            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_waiting_for_input")
            response_path = workspace / "task" / "clarification-response.v1.json"
            payload = json.loads(response_path.read_text())
            answer = next(a for a in payload["answers"] if a["question_id"] == "q-1")
            self.assertTrue(answer.get("skipped"))
            self.assertEqual(answer.get("answer"), "")

    def test_write_clarification_response_artifact_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            response_path = workspace / "task" / "clarification-response.v1.json"
            response_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Existing answer
            initial_payload = {
                "answers": [
                    {"question_id": "q-old", "answer": "old answer"}
                ]
            }
            response_path.write_text(json.dumps(initial_payload))
            
            qrane.write_clarification_response_artifact(
                workspace,
                run_id="test",
                raw_task_ref="ref",
                round_num=2,
                source="test",
                answers=[{"question_id": "q-new", "answer": "new answer"}]
            )
            
            data = json.loads(response_path.read_text())
            self.assertEqual(len(data["answers"]), 2)
            ids = [a["question_id"] for a in data["answers"]]
            self.assertIn("q-old", ids)
            self.assertIn("q-new", ids)

if __name__ == "__main__":
    unittest.main()
