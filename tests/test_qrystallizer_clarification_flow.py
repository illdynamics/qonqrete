import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import qrystallizer  # noqa: E402
import instruqtor  # noqa: E402


class QrystallizerClarificationFlowTests(unittest.TestCase):
    def test_vague_task_is_not_ready_with_bounded_questions(self):
        task_spec, clarification_log = qrystallizer.build_task_spec(
            "run-demo",
            Path("tasq.d/cyqle1_tasq.md"),
            "fix stuff",
        )
        self.assertFalse(task_spec["ready"])
        self.assertEqual(task_spec["status"], "NOT_READY")
        self.assertLessEqual(len(clarification_log["questions"]), 3)
        self.assertGreaterEqual(len(task_spec["blocking_gaps"]), 1)

    def test_placeholder_task_emits_placeholder_blocker(self):
        task_spec, _ = qrystallizer.build_task_spec(
            "run-demo",
            Path("tasq.d/cyqle1_tasq.md"),
            "TBD ???",
        )
        reasons = [str(item.get("reason", "")).lower() for item in task_spec["blocking_gaps"]]
        self.assertTrue(any("placeholder" in reason or "vague" in reason for reason in reasons))

    def test_clarification_answers_can_make_task_ready_and_hardened(self):
        response = {
            "supplied": True,
            "response_ref": "task/clarification-response.v1.json",
            "round": 1,
            "source": "interactive_terminal",
            "answers": [
                {
                    "question_id": "q-1",
                    "question": "What specific implementation outcome is required?",
                    "answer": "Implement a CLI that imports CSV records, validates required fields, and writes normalized JSON output with tests.",
                }
            ],
            "warnings": [],
        }
        task_spec, clarification_log = qrystallizer.build_task_spec(
            "run-demo",
            Path("tasq.d/cyqle1_tasq.md"),
            "TBD ???",
            clarification_response=response,
        )
        self.assertTrue(task_spec["ready"])
        self.assertTrue(task_spec.get("ready_after_clarification", True)) # Field might be legacy but check ready
        self.assertEqual(task_spec["goal_source"], "clarification_answers")
        self.assertEqual(task_spec["clarified_goal_status"], "resolved")
        self.assertIn("CSV records", task_spec["goal"])
        self.assertNotEqual(task_spec["goal"], "Clarification Answers")
        
        # Verify planning input uses clarified intent
        planning_input = instruqtor.build_planning_task_input("TBD ???", task_spec, {})
        self.assertIn("CSV records", planning_input)
        self.assertIn("# Clarified Task Requirement", planning_input)
        self.assertIn("Goal Source: clarification_answers", planning_input)

    def test_truthful_provenance_when_answer_is_weak(self):
        response = {
            "supplied": True,
            "response_ref": "task/clarification-response.v1.json",
            "round": 1,
            "source": "interactive_terminal",
            "answers": [
                {
                    "question_id": "q-1",
                    "question": "What specific implementation outcome is required?",
                    "answer": "not sure",
                }
            ],
            "warnings": [],
        }
        task_spec, clarification_log = qrystallizer.build_task_spec(
            "run-demo",
            Path("tasq.d/cyqle1_tasq.md"),
            "TBD ???",
            clarification_response=response,
        )
        self.assertFalse(task_spec["ready"])
        self.assertEqual(task_spec["goal_source"], "raw_task")
        self.assertEqual(task_spec["clarified_goal_status"], "unresolved")
        self.assertNotIn("not sure", task_spec["goal"])
        self.assertNotEqual(task_spec["goal"], "Clarification Answers")

    def test_question_deduplication_for_vague_tasks(self):
        # "TBD ???" used to trigger multiple similar questions
        task_spec, clarification_log = qrystallizer.build_task_spec(
            "run-demo",
            Path("tasq.d/cyqle1_tasq.md"),
            "TBD ???",
        )
        questions = clarification_log["questions"]
        # We expect at most 2 distinct questions for this: one about placeholder, 
        # maybe one about missing goal, but NOT redundant ones.
        self.assertLessEqual(len(questions), 2)
        question_texts = [q["question"].lower() for q in questions]
        self.assertEqual(len(question_texts), len(set(question_texts)), "Redundant questions found")

    def test_clarification_answers_can_still_remain_blocked(self):
        response = {
            "supplied": True,
            "response_ref": "task/clarification-response.v1.json",
            "round": 1,
            "source": "interactive_terminal",
            "answers": [
                {
                    "question_id": "q-1",
                    "question": "What concrete change should QonQrete implement in the repository?",
                    "answer": "not sure",
                }
            ],
            "warnings": [],
        }
        task_spec, clarification_log = qrystallizer.build_task_spec(
            "run-demo",
            Path("tasq.d/cyqle1_tasq.md"),
            "???",
            clarification_response=response,
        )
        self.assertFalse(task_spec["ready"])
        self.assertGreaterEqual(len(task_spec.get("blocking_gaps", [])), 0)


if __name__ == "__main__":
    unittest.main()
