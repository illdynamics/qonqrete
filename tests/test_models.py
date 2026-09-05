"""Unit tests for models: safe IDs, verdict parsing, plan validation."""
import unittest
import sys
import os
import tempfile
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.models import (
    BriqStatus, Plan, ReviewVerdict, ReviewIssue,
    slugify_id, BuildGroup, BriQ
)


class TestSafeIDs(unittest.TestCase):
    def test_slugify_id_normal(self):
        self.assertEqual(slugify_id("bg-core"), "bg-core")
        self.assertEqual(slugify_id("briq-1"), "briq-1")

    def test_slugify_id_with_spaces(self):
        safe = slugify_id("build group one")
        self.assertNotIn(" ", safe)
        self.assertTrue(safe.startswith("build-group"))

    def test_slugify_id_traversal(self):
        safe = slugify_id("../../etc/passwd")
        self.assertNotIn("..", safe)
        self.assertFalse(safe.startswith("."))
        self.assertFalse(safe.startswith("/"))

    def test_slugify_id_shell_chars(self):
        safe = slugify_id("bg; rm -rf /")
        self.assertNotIn(";", safe)
        self.assertNotIn(" ", safe)

    def test_slugify_id_unicode(self):
        safe = slugify_id("briQ-über")
        self.assertNotIn("über", safe)
        self.assertIn("b", safe.lower())

    def test_slugify_id_double_dots(self):
        safe = slugify_id("a..b")
        self.assertNotIn("..", safe)

    def test_slugify_id_lock(self):
        safe = slugify_id("branch.lock")
        self.assertNotIn(".lock", safe)

    def test_slugify_id_leading_dot(self):
        safe = slugify_id(".hidden")
        self.assertFalse(safe.startswith("."))

    def test_slugify_id_trailing_slash(self):
        safe = slugify_id("path/")
        self.assertFalse(safe.endswith("/"))
        self.assertFalse(safe.endswith("-"))

    def test_slugify_id_leading_slash(self):
        safe = slugify_id("/absolute/path")
        self.assertFalse(safe.startswith("/"))

    def test_slugify_id_double_slashes(self):
        safe = slugify_id("a//b")
        self.assertNotIn("//", safe)
        self.assertNotIn("..", safe)

    def test_slugify_id_backslashes(self):
        safe = slugify_id("a\\b")
        self.assertNotIn("\\", safe)

    def test_slugify_id_whitespace_only(self):
        safe = slugify_id("   ")
        self.assertTrue(len(safe) > 0)
        self.assertNotIn(" ", safe)

    def test_slugify_id_at_sign(self):
        safe = slugify_id("ref@{1}")
        self.assertNotIn("@{", safe)

    def test_slugify_id_shell_metachar(self):
        safe = slugify_id("foo`bar`")
        self.assertNotIn("`", safe)

    def test_safe_branch_name_valid(self):
        from qq.workspaces import safe_branch_name
        branch = safe_branch_name("run-1", "bg-core", 3)
        self.assertTrue(branch.startswith("qq/run-1/"))
        self.assertIn("/cycle-3", branch)
        self.assertNotIn(" ", branch)

    def test_safe_branch_name_traversal(self):
        from qq.workspaces import safe_branch_name
        branch = safe_branch_name("run-1", "../../etc", 0)
        self.assertNotIn("..", branch)
        self.assertFalse(branch.startswith("/"))


class TestPlanParsing(unittest.TestCase):
    def test_from_agent_json_builds_briqs_and_groups(self):
        data = {
            "summary": "test plan",
            "build_groups": [{
                "build_group_id": "bg-1", "name": "core",
                "description": "core stuff",
                "parallel_safe": True,
                "briqs": [
                    {"briq_id": "briq-1", "title": "a", "description": "do a"},
                    {"briq_id": "briq-2", "title": "b", "description": "do b"},
                ],
            }],
        }
        plan = Plan.from_agent_json("ctask-1", data)
        self.assertEqual(len(plan.briqs), 2)
        self.assertEqual(len(plan.build_groups), 1)
        bg = plan.build_groups["bg-1"]
        self.assertTrue(bg.parallel_safe)
        self.assertEqual(set(bg.briq_ids), {"briq-1", "briq-2"})
        self.assertEqual(plan.briqs["briq-1"].status, BriqStatus.PENDING)

    def test_generates_missing_ids(self):
        data = {
            "summary": "no ids",
            "build_groups": [{
                "name": "core",
                "briqs": [{"title": "thing", "description": "do thing"}],
            }],
        }
        plan = Plan.from_agent_json("ctask-1", data)
        self.assertEqual(len(plan.briqs), 1)
        self.assertEqual(len(plan.build_groups), 1)
        bg = list(plan.build_groups.values())[0]
        self.assertTrue(bg.id.startswith("bg-"))
        briq = list(plan.briqs.values())[0]
        self.assertTrue(briq.id.startswith("briq-"))
        self.assertEqual(briq.build_group_id, bg.id)

    def test_dedup_ids(self):
        data = {
            "summary": "dup ids",
            "build_groups": [
                {"build_group_id": "bg-1",
                 "briqs": [{"briq_id": "briq-1", "title": "a"}]},
                {"build_group_id": "bg-1",
                 "briqs": [{"briq_id": "briq-1", "title": "b"}]},
            ],
        }
        plan = Plan.from_agent_json("ctask-1", data)
        self.assertEqual(len(plan.build_groups), 2)
        bg_ids = list(plan.build_groups.keys())
        self.assertNotEqual(bg_ids[0], bg_ids[1])
        self.assertEqual(len(plan.briqs), 2)
        briq_ids = list(plan.briqs.keys())
        self.assertNotEqual(briq_ids[0], briq_ids[1])

    def test_sensitivity_clamped(self):
        data = {
            "build_groups": [{
                "build_group_id": "bg-1",
                "briqs": [
                    {"briq_id": "briq-1", "title": "a", "sensitivity": 42},
                    {"briq_id": "briq-2", "title": "b", "sensitivity": -5},
                ],
            }],
        }
        plan = Plan.from_agent_json("ctask-1", data)
        self.assertEqual(plan.briqs["briq-1"].sensitivity, 16)
        self.assertEqual(plan.briqs["briq-2"].sensitivity, 0)

    def test_plan_validation(self):
        data = {
            "build_groups": [
                {"build_group_id": "bg-1",
                 "briqs": [{"briq_id": "briq-1", "title": "a"}]},
                {"build_group_id": "bg-2", "briqs": []},
            ],
        }
        plan = Plan.from_agent_json("ctask-1", data)
        issues = plan.validate()
        self.assertEqual(len(issues), 0)

    def test_plan_validation_dup_briq(self):
        data = {
            "build_groups": [
                {"build_group_id": "bg-1",
                 "briqs": [{"briq_id": "briq-1", "title": "a"}]},
                {"build_group_id": "bg-2",
                 "briqs": [{"briq_id": "briq-1", "title": "b"}]},
            ],
        }
        plan = Plan.from_agent_json("ctask-1", data)
        issues = plan.validate()
        self.assertEqual(len(issues), 0)


class TestReviewVerdict(unittest.TestCase):
    def test_passed_only_on_exact_token(self):
        self.assertTrue(ReviewVerdict(status="FULLY_DONE").passed)
        self.assertFalse(ReviewVerdict(status="imhappyaboutitnow").passed)
        self.assertTrue(ReviewVerdict(status="FULLY_DONE ").passed)
        self.assertFalse(ReviewVerdict(status="NOT_DONE").passed)
        self.assertFalse(ReviewVerdict(
            status="I think it's mostly fine").passed)
        self.assertFalse(ReviewVerdict(
            status="almost FULLY_DONE").passed)
        self.assertFalse(ReviewVerdict(
            status="NOT_FULLY_DONE").passed)
        self.assertFalse(ReviewVerdict(status="").passed)

    def test_not_done_no_issues_synthesizes(self):
        verdict = ReviewVerdict.from_agent_json(1, {
            "status": "NOT_DONE",
            "summary": "The code is broken",
            "issues": [],
        })
        self.assertFalse(verdict.passed)
        self.assertEqual(len(verdict.issues), 1)
        self.assertEqual(verdict.issues[0].severity, "blocking")
        self.assertIn("broken", verdict.issues[0].what_is_wrong)

    def test_not_done_with_issues_preserved(self):
        verdict = ReviewVerdict.from_agent_json(1, {
            "status": "NOT_DONE",
            "summary": "needs work",
            "issues": [{
                "build_group_id": "bg-1", "severity": "blocking",
                "what_is_wrong": "bad", "what_to_fix": "fix it",
            }],
        })
        self.assertEqual(len(verdict.issues), 1)
        self.assertEqual(verdict.issues[0].what_is_wrong, "bad")

    def test_pass_with_issues_still_passes(self):
        verdict = ReviewVerdict.from_agent_json(1, {
            "status": "FULLY_DONE",
            "summary": "perfect",
            "issues": [{"build_group_id": "bg-1", "severity": "minor",
                        "what_is_wrong": "nit", "what_to_fix": "ignore"}],
        })
        self.assertTrue(verdict.passed)


if __name__ == "__main__":
    unittest.main()
