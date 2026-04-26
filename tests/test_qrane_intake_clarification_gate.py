import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QRANE_DIR = PROJECT_ROOT / "qrane"
sys.path.insert(0, str(QRANE_DIR))

import qrane  # noqa: E402
from lib_qrane import create_manifest, load_manifest  # noqa: E402


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
    def test_non_interactive_not_ready_marks_blocked_waiting_for_input_and_emits_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
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
            self.assertEqual(payload["answers"][0]["answer"], "")

            manifest = load_manifest(workspace)
            self.assertEqual(manifest["lifecycle_state"], "BLOCKED")
            self.assertEqual(manifest["run_status"], "RUN_WAITING_FOR_INPUT")
            self.assertEqual(manifest["current_stage"], "CLARIFICATION")
            self.assertEqual(manifest["execution"]["state"]["stop_reason"], "clarification_waiting_for_input")

    def test_interactive_clarification_success_writes_response_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
            write_not_ready_artifacts(workspace)
            (workspace / "struqture").mkdir(parents=True, exist_ok=True)

            original_can_prompt = qrane.can_prompt_for_clarification
            original_run_agent = qrane.run_agent
            original_record_completion = qrane.record_agent_completion
            original_input = builtins.input

            def fake_run_agent(*args, **kwargs):
                write_ready_artifacts(workspace)
                return True

            try:
                qrane.can_prompt_for_clarification = lambda is_autonomous: True
                qrane.run_agent = fake_run_agent
                qrane.record_agent_completion = lambda *args, **kwargs: {}
                builtins.input = lambda prompt="": "Implement CSV import and normalization CLI with tests."

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
            finally:
                qrane.can_prompt_for_clarification = original_can_prompt
                qrane.run_agent = original_run_agent
                qrane.record_agent_completion = original_record_completion
                builtins.input = original_input

            self.assertEqual(result["outcome"], "ready")
            response_path = workspace / "task" / "clarification-response.v1.json"
            self.assertTrue(response_path.exists())
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "clarification-response.v1")
            self.assertEqual(payload["round"], 1)
            self.assertEqual(len(payload["answers"]), 1)

    def test_interactive_clarification_round_limit_blocks_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
            write_not_ready_artifacts(workspace)
            (workspace / "struqture").mkdir(parents=True, exist_ok=True)

            original_can_prompt = qrane.can_prompt_for_clarification
            original_run_agent = qrane.run_agent
            original_record_completion = qrane.record_agent_completion
            original_input = builtins.input

            def fake_run_agent(*args, **kwargs):
                write_not_ready_artifacts(workspace)
                return True

            try:
                qrane.can_prompt_for_clarification = lambda is_autonomous: True
                qrane.run_agent = fake_run_agent
                qrane.record_agent_completion = lambda *args, **kwargs: {}
                builtins.input = lambda prompt="": "Need more detail"

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
            finally:
                qrane.can_prompt_for_clarification = original_can_prompt
                qrane.run_agent = original_run_agent
                qrane.record_agent_completion = original_record_completion
                builtins.input = original_input

            self.assertEqual(result["outcome"], "blocked")
            self.assertEqual(result["reason"], "clarification_round_limit_reached")
            manifest = load_manifest(workspace)
            self.assertEqual(manifest["lifecycle_state"], "BLOCKED")
            self.assertEqual(manifest["run_status"], "RUN_WAITING_FOR_INPUT")


    def test_existing_template_is_refreshed_for_later_blocked_question_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
            write_not_ready_artifacts(workspace)
            
            # create initial response template manually
            response_path = workspace / "task" / "clarification-response.v1.json"
            response_path.parent.mkdir(parents=True, exist_ok=True)
            initial_payload = {
                "schema_version": "clarification-response.v1",
                "round": 1,
                "answers": [
                    {"question_id": "q-old", "question": "old question", "answer": "old answer"}
                ]
            }
            response_path.write_text(json.dumps(initial_payload), encoding="utf-8")

            # act: handle clarification (it's round 2 because existing round was 1)
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
            
            # assert template is refreshed
            self.assertEqual(result["outcome"], "blocked")
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["round"], 2)
            # Should have q-1 from write_not_ready_artifacts
            self.assertEqual(len(payload["answers"]), 1)
            self.assertEqual(payload["answers"][0]["question_id"], "q-1")

    def test_safe_preservation_of_matching_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create_manifest(workspace)
            write_not_ready_artifacts(workspace)
            
            # create initial response template with matching id
            response_path = workspace / "task" / "clarification-response.v1.json"
            response_path.parent.mkdir(parents=True, exist_ok=True)
            initial_payload = {
                "schema_version": "clarification-response.v1",
                "round": 1,
                "answers": [
                    {"question_id": "q-1", "question": "What specific implementation outcome is required?", "answer": "Some preserved answer"}
                ]
            }
            response_path.write_text(json.dumps(initial_payload), encoding="utf-8")

            # act
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
            
            # assert answer is preserved
            self.assertEqual(result["outcome"], "blocked")
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["round"], 2)
            self.assertEqual(len(payload["answers"]), 1)
            self.assertEqual(payload["answers"][0]["question_id"], "q-1")
            self.assertEqual(payload["answers"][0]["answer"], "Some preserved answer")

if __name__ == "__main__":
    unittest.main()
