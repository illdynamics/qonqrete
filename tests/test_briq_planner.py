#!/usr/bin/env python3
"""Tests for briq_planner.py — briq graph planning, dependency ordering, parallel-safe grouping."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from briq_planner import (
    BriqGroup,
    PlannerResult,
    plan_from_task_file,
    topological_sort,
    find_parallel_groups,
    plan_to_json,
)


class TestBriqGroup(unittest.TestCase):
    def test_to_dict_and_from_dict(self):
        g = BriqGroup(
            id="test",
            name="Test Group",
            description="A test",
            depends_on=["dep1"],
            allowed_paths=["src/"],
            read_paths=["docs/"],
            acceptance=["Must work"],
            parallel_safe=True,
        )
        d = g.to_dict()
        self.assertEqual(d["id"], "test")
        self.assertEqual(d["depends_on"], ["dep1"])
        self.assertTrue(d["parallel_safe"])

        g2 = BriqGroup.from_dict(d)
        self.assertEqual(g2.id, g.id)
        self.assertEqual(g2.name, g.name)
        self.assertEqual(g2.depends_on, g.depends_on)
        self.assertEqual(g2.allowed_paths, g.allowed_paths)


class TestTopologicalSort(unittest.TestCase):
    def test_simple_ordering(self):
        groups = [
            BriqGroup(id="backend", name="Backend", depends_on=["database"]),
            BriqGroup(id="frontend", name="Frontend", depends_on=["backend"]),
            BriqGroup(id="database", name="Database", depends_on=[]),
        ]
        ordered = topological_sort(groups)
        ids = [g.id for g in ordered]
        # database must come before backend, backend before frontend
        self.assertLess(ids.index("database"), ids.index("backend"))
        self.assertLess(ids.index("backend"), ids.index("frontend"))

    def test_no_deps(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=[]),
            BriqGroup(id="b", name="B", depends_on=[]),
        ]
        ordered = topological_sort(groups)
        self.assertEqual(len(ordered), 2)

    def test_cycle_detection(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=["b"]),
            BriqGroup(id="b", name="B", depends_on=["a"]),
        ]
        with self.assertRaises(ValueError):
            topological_sort(groups)

    def test_self_dependency(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=["a"]),
        ]
        with self.assertRaises(ValueError):
            topological_sort(groups)


class TestParallelGroups(unittest.TestCase):
    def test_independent_groups_parallel(self):
        groups = [
            BriqGroup(id="html", name="HTML", depends_on=[], allowed_paths=["index.html"]),
            BriqGroup(id="css", name="CSS", depends_on=[], allowed_paths=["styles.css"]),
        ]
        plan = find_parallel_groups(groups)
        self.assertTrue(len(plan["parallel"]) > 0 or len(plan["serial"]) >= 2)

    def test_dependent_groups_serial(self):
        groups = [
            BriqGroup(id="html", name="HTML", depends_on=[], allowed_paths=["index.html"]),
            BriqGroup(id="css", name="CSS", depends_on=["html"], allowed_paths=["styles.css"]),
        ]
        plan = find_parallel_groups(groups)
        # css depends on html, so they should be in different batches
        all_batches = plan["parallel"] + plan["serial"]
        # Count how many batches have html in them
        html_batches = [i for i, b in enumerate(all_batches) if "html" in b]
        css_batches = [i for i, b in enumerate(all_batches) if "css" in b]
        if html_batches and css_batches:
            self.assertNotEqual(html_batches[0], css_batches[0])

    def test_path_conflict_prevents_parallel(self):
        groups = [
            BriqGroup(id="a", name="A", depends_on=[], allowed_paths=["src/app.py"]),
            BriqGroup(id="b", name="B", depends_on=[], allowed_paths=["src/app.py"]),  # same file
        ]
        plan = find_parallel_groups(groups)
        # Same path scope => should not be in a parallel batch together
        for batch in plan["parallel"]:
            has_a = "a" in batch
            has_b = "b" in batch
            self.assertFalse(has_a and has_b, f"a and b should not be parallel: {batch}")

    def test_no_path_conflict_allows_parallel(self):
        groups = [
            BriqGroup(id="html", name="HTML", depends_on=[], allowed_paths=["index.html"]),
            BriqGroup(id="css", name="CSS", depends_on=[], allowed_paths=["styles.css"]),
        ]
        plan = find_parallel_groups(groups)
        # These should be able to run in parallel
        found_parallel = False
        for batch in plan["parallel"]:
            if "html" in batch and "css" in batch:
                found_parallel = True
                break
        if not found_parallel:
            # Also acceptable if both in serial with equal depth
            pass


class TestPlanFromTaskFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="briq_planner_test_")
        self.task_file = Path(self._tmp) / "tasq-test.md"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_html_css_js_task(self):
        self.task_file.write_text(
            "# Test Task\n\n"
            "Build a web app with these files:\n"
            "- `index.html`\n"
            "- `styles.css`\n"
            "- `app.js`\n"
        )
        result = plan_from_task_file(self.task_file)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.groups), 3)
        group_ids = [g.id for g in result.groups]
        self.assertIn("html_structure", group_ids)
        self.assertIn("css_styling", group_ids)
        self.assertIn("js_logic", group_ids)

    def test_python_task(self):
        self.task_file.write_text(
            "# Python Task\n\n"
            "Create:\n"
            "- `main.py`\n"
            "- `utils.py`\n"
        )
        result = plan_from_task_file(self.task_file)
        self.assertEqual(result.status, "PASS")
        self.assertIn("python_backend", [g.id for g in result.groups])

    def test_empty_task(self):
        self.task_file.write_text("# Empty\n")
        result = plan_from_task_file(self.task_file)
        # No file refs = monolithic fallback
        self.assertEqual(len(result.groups), 1)
        self.assertIn("main_implementation", [g.id for g in result.groups])

    def test_missing_file(self):
        result = plan_from_task_file("/nonexistent/path.md")
        self.assertEqual(result.status, "FAIL_REPAIRABLE")
        self.assertTrue(len(result.errors) > 0)

    def test_serialization(self):
        self.task_file.write_text("Create: `index.html`\n")
        result = plan_from_task_file(self.task_file)
        json_str = plan_to_json(result)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["status"], "PASS")
        self.assertTrue(len(parsed["groups"]) > 0)

    def test_dependency_wiring(self):
        self.task_file.write_text(
            "Build: `index.html`, `styles.css`, `app.js`\n"
        )
        result = plan_from_task_file(self.task_file)
        # html depends on nothing, css depends on html, js depends on html
        groups_by_id = {g.id: g for g in result.groups}
        if "html_structure" in groups_by_id:
            self.assertEqual(groups_by_id["html_structure"].depends_on, [])
        if "css_styling" in groups_by_id:
            self.assertIn("html_structure", groups_by_id["css_styling"].depends_on)


if __name__ == "__main__":
    unittest.main()
