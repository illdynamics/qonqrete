import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = PROJECT_ROOT / "_test_runtime"
TMP_ROOT.mkdir(exist_ok=True)
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import construqtor  # noqa: E402
import inspeqtor  # noqa: E402
from integration_checks import build_issue_fingerprint_entries, collect_scope_validation_issues  # noqa: E402


class RepairSystemHardeningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="qonq_v1319_", dir=str(TMP_ROOT)))
        self.workspace = self._tmp
        (self.workspace / "qodeyard").mkdir(parents=True, exist_ok=True)
        (self.workspace / "planning").mkdir(parents=True, exist_ok=True)
        (self.workspace / "build" / "groups" / "bg-app").mkdir(parents=True, exist_ok=True)
        (self.workspace / "briq.d").mkdir(parents=True, exist_ok=True)
        (self.workspace / "task").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, rel: str, body: str):
        path = self.workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def _write_build_groups(self):
        (self.workspace / "planning" / "build-groups.v1.json").write_text(
            json.dumps(
                {
                    "briq_inventory": [
                        {
                            "briq_ref": "briq-001",
                            "target_files": ["main.py", "routes/chat_routes.py", "store.py", "file_routes.py"],
                            "primary_deliverables": ["main.py", "routes/chat_routes.py", "store.py"],
                        }
                    ],
                    "items": [
                        {
                            "build_group_id": "bg-app",
                            "scope_id": "scope-app",
                            "briq_refs": ["briq-001"],
                            "component_refs": ["cmp-app"],
                            "target_files": ["main.py", "routes/chat_routes.py", "store.py", "file_routes.py"],
                            "primary_files": ["main.py", "routes/chat_routes.py", "store.py"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.workspace / "build" / "groups" / "bg-app" / "changed-files.v1.json").write_text(
            json.dumps(
                {
                    "changed_files": [
                        {"path": "main.py", "in_intended_scope": True},
                        {"path": "routes/chat_routes.py", "in_intended_scope": True},
                        {"path": "store.py", "in_intended_scope": True},
                        {"path": "file_routes.py", "in_intended_scope": True},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.workspace / "build" / "groups" / "bg-app" / "build-report.v1.json").write_text(
            json.dumps({"files": ["main.py", "routes/chat_routes.py", "store.py", "file_routes.py"]}),
            encoding="utf-8",
        )
        (self.workspace / "briq.d" / "cyqle1_tasq1_briq001.md").write_text(
            "Briq-Ref: briq-001\nBuild-Group: bg-app\nTarget-Files: main.py routes/chat_routes.py store.py file_routes.py\n",
            encoding="utf-8",
        )

    def test_build_repair_plan_backfills_scope_and_issue_fingerprints(self):
        self._write_build_groups()
        inspection_verdict = {
            "completion_assessment": "Need repair",
            "issues": [],
            "completion_criteria_results": [],
        }
        validation_bundle = {
            "status": "FAIL",
            "checks": [{"check_id": "group_scope_integration", "status": "FAIL"}],
            "issues": [
                {
                    "source": "validation",
                    "severity": "error",
                    "message": "main.py does not include_router any route modules",
                    "build_group_id": "bg-app",
                    "scope": "scope-app",
                }
            ],
        }
        grouped_coherence = {
            "group_summaries": [
                {
                    "build_group_id": "bg-app",
                    "scope_id": "scope-app",
                    "status": "FAIL",
                    "changed_files": ["main.py", "routes/chat_routes.py"],
                    "reported_files": ["main.py", "routes/chat_routes.py", "store.py", "file_routes.py"],
                }
            ],
            "undeclared_changed_files": [],
            "unassigned_briqs": [],
        }
        plan = inspeqtor.build_repair_plan(
            self.workspace,
            "1",
            inspection_verdict,
            validation_bundle,
            {},
            grouped_coherence,
            [],
        )
        self.assertIn("bg-app", plan["target_build_groups"])
        self.assertIn("main.py", plan["target_files"])
        self.assertIn("routes/chat_routes.py", plan["allowed_edit_paths"])
        self.assertTrue(plan["issue_fingerprints"])
        self.assertIn("main.py", plan["validation_scope_files"])

    def test_merge_briq_changed_files_includes_group_scope_snapshots(self):
        self._write("qodeyard/main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
        self._write("qodeyard/routes/chat_routes.py", "from fastapi import APIRouter\nrouter = APIRouter()\n")
        merged = inspeqtor.merge_briq_changed_files(
            [("main.py", "from fastapi import FastAPI\n")],
            self.workspace / "qodeyard",
            ["main.py"],
            fallback_limit=3,
            scope_files=["main.py", "routes/chat_routes.py"],
        )
        merged_names = [name for name, _ in merged]
        self.assertIn("routes/chat_routes.py", merged_names)

    def test_collect_scope_validation_issues_catches_medium_frontend_breaks(self):
        self._write(
            "task/task-spec.v1.json",
            json.dumps(
                {
                    "task_body": """
Use localStorage and exactly these keys:
- qonqrete-recipe-planner-recipes
- qonqrete-recipe-planner-plan
Monday\nTuesday\nWednesday\nThursday\nFriday\nSaturday\nSunday
"""
                }
            ),
        )
        self._write(
            "qodeyard/index.html",
            '<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body><div id="recipe-list"></div><script src="script.js"></script></body></html>',
        )
        self._write(
            "qodeyard/app.js",
            "document.getElementById('category-filter');\nlocalStorage.setItem('wrong-key', 'x');\n",
        )
        self._write("qodeyard/styles.css", "body{}\n")
        issues = collect_scope_validation_issues(self.workspace, scope_files=["index.html", "app.js", "styles.css"])
        messages = "\n".join(issue.get("message", "") for issue in issues)
        self.assertIn("Missing local HTML references: script.js", messages)
        self.assertIn("JavaScript references missing DOM ids: category-filter", messages)
        self.assertIn("missing required localStorage keys", messages)
        self.assertIn("undeclared localStorage keys: wrong-key", messages)

    def test_collect_scope_validation_issues_accepts_direct_localstorage_literals(self):
        self._write(
            "task/task-spec.v1.json",
            json.dumps(
                {
                    "task_body": """
Use localStorage and exactly these keys:
- qonqrete-recipe-planner-recipes
- qonqrete-recipe-planner-plan
"""
                }
            ),
        )
        self._write(
            "qodeyard/index.html",
            '<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body>'
            '<div id="recipe-list"></div><script src="app.js"></script></body></html>',
        )
        self._write(
            "qodeyard/app.js",
            "document.addEventListener('DOMContentLoaded', () => {});\n"
            "document.getElementById('recipe-list');\n"
            "localStorage.getItem('qonqrete-recipe-planner-recipes');\n"
            "localStorage.setItem('qonqrete-recipe-planner-plan', 'x');\n",
        )
        self._write("qodeyard/styles.css", "body{}\n")
        issues = collect_scope_validation_issues(self.workspace, scope_files=["index.html", "app.js", "styles.css"])
        messages = "\n".join(issue.get("message", "") for issue in issues)
        self.assertNotIn("missing required localStorage keys", messages)
        self.assertNotIn("uses undeclared localStorage keys", messages)

    def test_collect_scope_validation_issues_accepts_const_and_object_indirection(self):
        self._write(
            "task/task-spec.v1.json",
            json.dumps(
                {
                    "task_body": """
Use localStorage and exactly these keys:
- qonqrete-recipe-planner-recipes
- qonqrete-recipe-planner-plan
"""
                }
            ),
        )
        self._write(
            "qodeyard/index.html",
            '<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body>'
            '<div id="recipe-list"></div><div id="plan-list"></div><script src="app.js"></script></body></html>',
        )
        self._write(
            "qodeyard/app.js",
            "const RECIPES_KEY = 'qonqrete-recipe-planner-recipes';\n"
            "const PLAN_KEY = 'qonqrete-recipe-planner-plan';\n"
            "const RECIPES_ALIAS = RECIPES_KEY;\n"
            "const STORAGE_KEYS = { recipes: RECIPES_ALIAS, plan: PLAN_KEY };\n"
            "document.addEventListener('DOMContentLoaded', () => {});\n"
            "document.getElementById('recipe-list');\n"
            "document.getElementById('plan-list');\n"
            "localStorage.getItem(STORAGE_KEYS.recipes);\n"
            "localStorage.setItem(STORAGE_KEYS.plan, 'x');\n",
        )
        self._write("qodeyard/styles.css", "body{}\n")
        issues = collect_scope_validation_issues(self.workspace, scope_files=["index.html", "app.js", "styles.css"])
        messages = "\n".join(issue.get("message", "") for issue in issues)
        self.assertNotIn("missing required localStorage keys", messages)
        self.assertNotIn("uses undeclared localStorage keys", messages)

    def test_collect_scope_validation_issues_catches_fastapi_integration_breaks(self):
        self._write("task/task-spec.v1.json", json.dumps({"task_body": "Uploads must use storage/uploads exactly."}))
        self._write("qodeyard/main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
        self._write("qodeyard/routes/chat_routes.py", "from store import manager\nfrom fastapi import APIRouter\nrouter = APIRouter()\n")
        self._write("qodeyard/store.py", "class Store:\n    pass\n")
        self._write("qodeyard/file_routes.py", 'UPLOAD_DIR = "uploads"\n')
        issues = collect_scope_validation_issues(
            self.workspace,
            scope_files=["main.py", "routes/chat_routes.py", "store.py", "file_routes.py"],
        )
        messages = "\n".join(issue.get("message", "") for issue in issues)
        self.assertIn("main.py does not include_router any route modules", messages)
        self.assertIn("imports missing local symbols from store.py: manager", messages)
        self.assertIn("uses uploads path but not required storage/uploads path", messages)

    def test_evaluate_repair_scope_state_keeps_open_fingerprints_open(self):
        self._write(
            "task/task-spec.v1.json",
            json.dumps({"task_body": "Use localStorage and exactly these keys:\n- qonqrete-recipe-planner-recipes\n- qonqrete-recipe-planner-plan"}),
        )
        self._write("qodeyard/index.html", '<!doctype html><html><body><script src="script.js"></script></body></html>')
        self._write("qodeyard/app.js", "document.getElementById('missing-id');")
        issues = collect_scope_validation_issues(self.workspace, scope_files=["index.html", "app.js"])
        plan = {"issue_fingerprints": build_issue_fingerprint_entries(issues)}
        state = construqtor._evaluate_repair_scope_state(
            self.workspace,
            self.workspace / "qodeyard",
            repair_targets=["index.html", "app.js"],
            validation_scope_files=["index.html", "app.js"],
            is_contract_relevant=False,
            contract_data=None,
            build_group="bg-web",
            repair_plan_payload=plan,
        )
        self.assertFalse(state["passed"])
        self.assertTrue(state["open_fingerprints"])


if __name__ == "__main__":
    unittest.main()
