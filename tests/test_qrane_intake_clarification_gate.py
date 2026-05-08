import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QRANE_DIR = PROJECT_ROOT / ".qonqrete" / "qrane"
sys.path.insert(0, str(QRANE_DIR))

import qrane

def write_not_ready_artifacts(workspace: Path) -> None:
    task_dir = workspace / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-spec.v1.json").write_text(
        json.dumps(
            {
                "ready": False,
                "status": "NOT_READY",
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
                        "question_id": "q-1",
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
                "inputs": [
                    {"name": "raw_task", "source_ref": "tasq.d/cyqle1_tasq.md"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "clarification-log.v1.json").write_text(
        json.dumps({"questions": []}),
        encoding="utf-8",
    )


class IntakeClarificationGateTests(unittest.TestCase):
    @patch('qrane.resolve_clarification_prompt_mode', return_value=(False, "test_non_interactive"))
    @patch('builtins.input', side_effect=AssertionError("input() should not be called in non-interactive mode"))
    def test_non_interactive_not_ready_marks_blocked_waiting_for_input_and_emits_template(self, mock_input, mock_mode):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            # create_manifest and other lib_qrane functions are mocked
            qrane.mark_clarification_blocked = MagicMock()
            write_not_ready_artifacts(workspace)

            result = qrane.handle_intake_clarification(
                workspace,
                prefix="aQQ",
                is_autonomous=True,
                config={},
                cycle=1,
                qrystallizer_cmd=["python3", "qrystallizer.py"],
                env={},
                qonsole_log_path=workspace / "struqture" / "qonsole_qrystallizer.log",
            )

            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_waiting_for_input")
            
            # Verify template artifact
            template_path = workspace / "task" / "clarification-response.v1.json"
            self.assertTrue(template_path.exists())
            payload = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "clarification-response.v1")
            self.assertEqual(payload["source"], "template")
            self.assertGreater(len(payload["answers"]), 0)

    @patch('qrane.resolve_clarification_prompt_mode', return_value=(True, "test_interactive"))
    @patch('qrane.run_agent', return_value=True)
    @patch('qrane.record_agent_completion', return_value=None)
    @patch('qrane.canonical_run_id', return_value="test-run")
    @patch('builtins.input', return_value="Implement CSV import.")
    def test_interactive_clarification_success_writes_response_and_continues(self, mock_input, mock_run_id, mock_record, mock_run, mock_mode):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            write_not_ready_artifacts(workspace)
            (workspace / "struqture").mkdir(parents=True, exist_ok=True)

            # First run: NOT_READY. Rerun should make it READY.
            def fake_run_agent(*args, **kwargs):
                write_ready_artifacts(workspace)
                return True
            mock_run.side_effect = fake_run_agent

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

            self.assertEqual(result["outcome"], "ready")
            response_path = workspace / "task" / "clarification-response.v1.json"
            self.assertTrue(response_path.exists())
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["round"], 1)

    @patch('qrane.resolve_clarification_prompt_mode', return_value=(True, "test_interactive"))
    @patch('qrane.run_agent', return_value=True)
    @patch('qrane.record_agent_completion', return_value=None)
    @patch('qrane.canonical_run_id', return_value="test-run")
    @patch('builtins.input', return_value="Still vague.")
    def test_interactive_clarification_round_limit_blocks_cleanly(self, mock_input, mock_run_id, mock_record, mock_run, mock_mode):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            qrane.mark_clarification_blocked = MagicMock()
            write_not_ready_artifacts(workspace)
            (workspace / "struqture").mkdir(parents=True, exist_ok=True)

            result = qrane.handle_intake_clarification(
                workspace,
                prefix="uQQ",
                is_autonomous=False,
                config={"agents": {"qrystallizer": {"max_clarification_rounds": 1}}},
                cycle=1,
                qrystallizer_cmd=["python3", "qrystallizer.py"],
                env={},
                qonsole_log_path=workspace / "struqture" / "qonsole_qrystallizer.log",
            )

            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_round_limit_reached")

if __name__ == "__main__":
    unittest.main()
