import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QRANE_DIR = PROJECT_ROOT / ".qonqrete" / "qrane"
sys.path.insert(0, str(QRANE_DIR))

import qrane  # noqa: E402


class _TTY:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def _write_not_ready(workspace: Path, question_id: str = "q-1") -> None:
    task_dir = workspace / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-spec.v1.json").write_text(
        json.dumps(
            {
                "ready": False,
                "status": "NOT_READY",
                "run_id": "run-test",
                "inputs": [{"name": "raw_task", "source_ref": "tasq.d/cyqle1_tasq.md"}],
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
                        "question": "What should be implemented?",
                        "reason": "Need concrete outcome.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


class ClarificationModeControlTests(unittest.TestCase):
    def test_force_non_interactive_wins_over_force_interactive(self):
        enabled, reason = qrane.resolve_clarification_prompt_mode(
            force_interactive=True,
            force_non_interactive=True,
            env={"QONQ_INTERACTIVE_CLARIFICATION": "1"},
            stdin_stream=_TTY(True),
            stdout_stream=_TTY(True),
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "forced_non_interactive")

    def test_force_interactive_requires_tty(self):
        enabled, reason = qrane.resolve_clarification_prompt_mode(
            force_interactive=True,
            env={},
            stdin_stream=_TTY(True),
            stdout_stream=_TTY(False),
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "forced_interactive_requires_tty")

    def test_ci_and_non_interactive_default_to_file_pause(self):
        enabled, reason = qrane.resolve_clarification_prompt_mode(
            env={"CI": "1"},
            stdin_stream=_TTY(True),
            stdout_stream=_TTY(True),
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "ci")

        enabled, reason = qrane.resolve_clarification_prompt_mode(
            env={"QONQ_NON_INTERACTIVE": "1"},
            stdin_stream=_TTY(True),
            stdout_stream=_TTY(True),
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "env_non_interactive")

    def test_normal_tty_defaults_to_interactive(self):
        enabled, reason = qrane.resolve_clarification_prompt_mode(
            env={},
            stdin_stream=_TTY(True),
            stdout_stream=_TTY(True),
        )
        self.assertTrue(enabled)
        self.assertEqual(reason, "interactive_stdio_tty")

    def test_no_tty_defaults_to_non_interactive(self):
        enabled, reason = qrane.resolve_clarification_prompt_mode(
            env={},
            stdin_stream=_TTY(False),
            stdout_stream=_TTY(True),
        )
        self.assertFalse(enabled)
        self.assertEqual(reason, "stdin_not_tty")

    def test_prompt_abort_raises_clean_exception(self):
        with mock.patch("builtins.input", return_value="/abort"):
            with self.assertRaises(qrane.ClarificationPromptAborted):
                qrane.prompt_for_clarification_answers(
                    "uQQ",
                    [{"question_id": "q-1", "question": "Need detail"}],
                )

    def test_response_artifact_merges_answers(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            task_dir = workspace / "task"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "clarification-response.v1.json").write_text(
                json.dumps(
                    {
                        "schema_version": "clarification-response.v1",
                        "answers": [
                            {"question_id": "q-1", "question": "A?", "answer": "old"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            qrane.write_clarification_response_artifact(
                workspace,
                run_id="run-test",
                raw_task_ref="tasq.d/cyqle1_tasq.md",
                round_num=2,
                source="interactive_terminal",
                answers=[
                    {"question_id": "q-1", "question": "A?", "answer": "new"},
                    {"question_id": "q-2", "question": "B?", "answer": "added"},
                ],
            )
            payload = json.loads((task_dir / "clarification-response.v1.json").read_text(encoding="utf-8"))
            by_id = {item["question_id"]: item for item in payload["answers"]}
            self.assertEqual(by_id["q-1"]["answer"], "new")
            self.assertEqual(by_id["q-2"]["answer"], "added")

    def test_same_question_loop_protection_blocks_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / "struqture").mkdir(parents=True, exist_ok=True)
            _write_not_ready(workspace, question_id="q-1")
            qrane.mark_clarification_blocked = mock.MagicMock()

            with mock.patch("builtins.input", return_value="Need CSV import"):
                with mock.patch("qrane.resolve_clarification_prompt_mode", return_value=(True, "test")):
                    with mock.patch("qrane.run_agent", return_value=True):
                        with mock.patch("qrane.record_agent_completion", return_value=None):
                            result = qrane.handle_intake_clarification(
                                workspace,
                                prefix="uQQ",
                                is_autonomous=False,
                                config={"agents": {"qrystallizer": {"max_clarification_rounds": 2}}},
                                cycle=1,
                                qrystallizer_cmd=["python3", "qrystallizer.py"],
                                env={},
                                qonsole_log_path=workspace / "struqture" / "qonsole_qrystallizer.log",
                            )
            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_infinite_loop_detected")


if __name__ == "__main__":
    unittest.main()
