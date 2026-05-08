import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worqer"))

import contract_harness  # noqa: E402


def _write_workspace(tmp_path: Path) -> tuple[Path, Path]:
    worqspace = tmp_path / "qage_test"
    qodeyard = worqspace / "qodeyard"
    tasq_dir = worqspace / "tasq.d"
    qodeyard.mkdir(parents=True, exist_ok=True)
    tasq_dir.mkdir(parents=True, exist_ok=True)
    return worqspace, qodeyard


def test_detect_harness_class_is_dynamic_contract():
    assert contract_harness.detect_harness_class("anything") == "dynamic_tasq_contract.v2"


def test_build_harness_extracts_exact_required_files(tmp_path):
    worqspace, _ = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `alpha.txt`
- `beta.json`
- `gamma.sh`
No extra files.
"""
    (worqspace / "tasq.d" / "cyqle1_tasq.md").write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace)
    required = harness.get("file_rules", {}).get("required_files", [])
    allowed_only = harness.get("file_rules", {}).get("allowed_only_files", [])

    assert required == ["alpha.txt", "beta.json", "gamma.sh"]
    assert allowed_only == required


def test_strict_scope_forbids_extra_files_and_dependencies(tmp_path):
    worqspace, qodeyard = _write_workspace(tmp_path)
    task_text = """
Required files:
- `main.py`
- `requirements.txt`
- `run.sh`

Include requirements.txt with:
    fastapi
    uvicorn

No additional frameworks.
Only implement what is explicitly described in this task.
If something is not specified, do not invent it.
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    required = harness.get("file_rules", {}).get("required_files", [])
    allowed_only = harness.get("file_rules", {}).get("allowed_only_files", [])
    dependency_rules = harness.get("dependency_rules", {})

    assert allowed_only == required
    assert dependency_rules["required_dependencies"] == ["fastapi", "uvicorn"]
    assert dependency_rules["allow_unspecified_dependencies"] is False

    (qodeyard / "main.py").write_text("PORT = 8000\n", encoding="utf-8")
    (qodeyard / "requirements.txt").write_text("fastapi\nuvicorn\nhttpx\npytest\n", encoding="utf-8")
    (qodeyard / "run.sh").write_text("python -m uvicorn main:app --reload --port $PORT\n", encoding="utf-8")
    (qodeyard / "test_api.py").write_text("def test_extra(): pass\n", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    codes = {row.get("code") for row in result.get("violations", [])}

    assert result["passed"] is False
    assert "FILE_EXTRA_PRESENT" in codes
    assert "DEPENDENCY_EXTRA_DECLARATION" in codes


def test_run_harness_missing_required_file(tmp_path):
    worqspace, qodeyard = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `a.txt`
- `b.txt`
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    (qodeyard / "a.txt").write_text("ok", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    codes = {row.get("code") for row in result.get("violations", [])}

    assert result["passed"] is False
    assert "FILE_REQUIRED_MISSING" in codes


def test_task_hash_mismatch_marks_stale_artifact(tmp_path):
    worqspace, qodeyard = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `main.txt`
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    (qodeyard / "main.txt").write_text("ok", encoding="utf-8")

    # mutate source tasq after contract generation
    tasq_path.write_text(task_text + "\n- `unexpected.txt`\n", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    codes = {row.get("code") for row in result.get("violations", [])}

    assert "CONTRACT_TASK_HASH_MISMATCH" in codes
    assert "STALE_ARTIFACT_INVALIDATED" in codes


def test_static_app_runtime_uses_contract_entrypoint(tmp_path):
    worqspace, qodeyard = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `home.html`
- `bundle.js`
- `styles.css`
main title: `Demo App`
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))

    (qodeyard / "home.html").write_text(
        """<!doctype html><html><body><h1>Demo App</h1><script src=\"bundle.js\"></script></body></html>""",
        encoding="utf-8",
    )
    (qodeyard / "bundle.js").write_text("console.log('ok');", encoding="utf-8")
    (qodeyard / "styles.css").write_text("body { color: black; }", encoding="utf-8")

    # Ensure runtime check points at the contract-derived html file.
    runtime_checks = harness.get("runtime_checks", [])
    static_rows = [row for row in runtime_checks if row.get("runtime_type") == "static_browser_app"]
    assert static_rows
    assert static_rows[0].get("entrypoint") == "home.html"

    result = contract_harness.run_harness(qodeyard, harness)
    assert result["passed"] is True


def test_static_app_hints_accept_semantic_containers_and_storage_constants(tmp_path):
    worqspace, qodeyard = _write_workspace(tmp_path)
    harness = {
        "schema_version": "dynamic_tasq_contract.v2",
        "task_identity": {"qage_id": worqspace.name},
        "file_rules": {
            "required_files": ["index.html", "styles.css", "app.js"],
            "forbidden_files": [],
            "allowed_only_files": ["index.html", "styles.css", "app.js"],
            "exclude_hidden_from_deliverables": True,
            "exclude_system_artifacts": True,
        },
        "dependency_rules": {},
        "shellscript_checks": [],
        "runtime_checks": [],
        "static_checks": [
            {
                "type": "html_required_controls",
                "file": "index.html",
                "controls": ["form", "grid"],
                "required": True,
            },
            {
                "type": "storage_keys_exact",
                "files": ["app.js"],
                "keys": ["example-recipes", "example-plan"],
                "exact": True,
            },
        ],
    }
    (qodeyard / "index.html").write_text(
        """<!doctype html><html><body>
        <form id="recipe-form"><input id="name"><button>Add</button></form>
        <section id="recipe-grid"></section>
        <script src="app.js"></script>
        </body></html>""",
        encoding="utf-8",
    )
    (qodeyard / "app.js").write_text(
        """
        const RECIPES_KEY = 'example-recipes';
        const PLAN_KEY = 'example-plan';
        localStorage.getItem(RECIPES_KEY);
        localStorage.setItem(PLAN_KEY, JSON.stringify({}));
        """,
        encoding="utf-8",
    )
    (qodeyard / "styles.css").write_text("body { color: black; }", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    assert result["passed"] is True


def test_build_harness_does_not_promote_forbidden_file_mentions(tmp_path):
    worqspace, _ = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `index.html`
- `styles.css`
- `app.js`

Do not add `main.py`.
Do not include `run.sh`.
No extra files.
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    required = harness.get("file_rules", {}).get("required_files", [])

    assert required == ["app.js", "index.html", "styles.css"]


def test_build_harness_recognizes_misspelled_exact_launch_command(tmp_path):
    worqspace, _ = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `run.sh`
Add a script run.sh that is a shellscript to launch exectly this uvicorn command: python -m uvicorn main:app --reload --port $PORT
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    checks = harness.get("shellscript_checks", [])

    assert checks
    assert checks[0]["command_policy"]["allow_wrapper"] is False
    assert checks[0]["command_policy"]["exact_command_required"] == "python -m uvicorn main:app --reload --port $PORT"


def test_build_harness_strips_parenthetical_after_exact_launch_command(tmp_path):
    worqspace, _ = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `run.sh`
Add a script run.sh that is a shellscript to launch exectly this uvicorn command: python -m uvicorn main:app --reload --port $PORT (same port value as we use for the application)
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    checks = harness.get("shellscript_checks", [])

    assert checks
    assert checks[0]["command_policy"]["exact_command_required"] == "python -m uvicorn main:app --reload --port $PORT"


def test_http_runtime_uses_run_sh_even_when_exact_launch_command_present(tmp_path):
    worqspace, _ = _write_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `main.py`
- `run.sh`

- GET /health
- POST /users

Add a script run.sh that is a shellscript to launch exectly this uvicorn command: python -m uvicorn main:app --reload --port $PORT (same port value as we use for the application)
"""
    tasq_path = worqspace / "tasq.d" / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")

    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))

    runtime = [row for row in harness.get("runtime_checks", []) if row.get("runtime_type") == "http_service"]
    assert runtime
    assert runtime[0]["launch_command"] == "sh run.sh"
