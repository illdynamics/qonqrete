from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worqer"))
sys.path.insert(0, str(ROOT / "qrane"))

import contract_harness  # noqa: E402
import inspeqtor  # noqa: E402
from shellscript_validation import validate_run_sh_contract  # noqa: E402
from smoqetester.runner import run_smoketest  # noqa: E402


def _smoke_config() -> dict:
    return {
        "agents": {
            "inspeqtor": {
                "smoketest": {
                    "enabled": True,
                    "mode": "scoped",
                    "timeout_seconds": 6,
                    "max_output_chars": 800,
                    "dependency_gate": {"enabled": True},
                    "adapters": {
                        "python": {"enabled": False},
                        "shell": {"enabled": False},
                        "js_ts": {"enabled": False},
                        "html_css": {"enabled": False},
                    },
                }
            }
        }
    }


def _write_fastapi_fixture(root: Path, run_sh_text: str, requirements: str = "fastapi\nuvicorn\n") -> dict:
    main_py = root / "main.py"
    req = root / "requirements.txt"
    run_sh = root / "run.sh"

    main_py.write_text(
        "\n".join(
            [
                "PORT = 8000",
                "from fastapi import FastAPI, HTTPException",
                "from pydantic import BaseModel",
                "",
                "app = FastAPI()",
                "",
                "class User(BaseModel):",
                "    id: int",
                "    username: str",
                "    email: str",
                "    password: str",
                "",
                "users = []",
                "next_id = 1",
                "",
                "# Run with:",
                "# uvicorn main:app --reload --port $PORT",
                "",
                "@app.get('/health')",
                "def health():",
                "    return {'status': 'healthy'}",
                "",
                "@app.post('/users')",
                "def create_user(payload: dict):",
                "    global next_id",
                "    user = {'id': next_id, 'username': payload['username'], 'email': payload['email'], 'password': payload['password']}",
                "    users.append(user)",
                "    next_id += 1",
                "    return user",
                "",
                "@app.get('/users')",
                "def list_users():",
                "    return users",
                "",
                "@app.get('/users/{user_id}')",
                "def get_user(user_id: int):",
                "    for item in users:",
                "        if item['id'] == user_id:",
                "            return item",
                "    raise HTTPException(status_code=404, detail='not found')",
            ]
        ),
        encoding="utf-8",
    )
    req.write_text(requirements, encoding="utf-8")
    run_sh.write_text(run_sh_text, encoding="utf-8")
    run_sh.chmod(0o755)
    return {"harness_id": "fastapi_users_memory_api.v1", "required_files": ["main.py", "requirements.txt", "run.sh"]}


def test_regression_missing_port_value_in_run_sh_is_contract_fail():
    errors = validate_run_sh_contract(
        "python -m uvicorn main:app --reload --port\n",
        "exact_variable_port",
    )
    assert any("missing value after --port" in msg for msg in errors)


def test_regression_hardcoded_port_in_run_sh_is_contract_fail():
    errors = validate_run_sh_contract(
        "python -m uvicorn main:app --reload --port 8000\n",
        "exact_variable_port",
    )
    assert any("hardcoded port" in msg.lower() or "must launch exactly" in msg.lower() for msg in errors)


def test_regression_wrong_uvicorn_target_is_contract_fail():
    errors = validate_run_sh_contract(
        "python -m uvicorn app:app --reload --port $PORT\n",
        "port_variable",
    )
    assert any("main:app" in msg for msg in errors)


def test_shellscript_syntax_error_is_classified():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        harness = _write_fastapi_fixture(
            root,
            "#!/bin/sh\nif then\n  echo broken\nfi\n",
        )
        result = contract_harness.run_harness(root, harness, apply_fixes=False)
        assert result["passed"] is False
        assert result["verdict_classification"] == "FAIL: shellscript syntax error"
        assert any(v["rule_id"] == "FAIL_SHELLSCRIPT_SYNTAX" for v in result["violations"])


def test_missing_dependency_from_requirements_is_fail_dependency_not_declared():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        harness = _write_fastapi_fixture(
            root,
            "#!/bin/sh\nset -eu\npython -m uvicorn main:app --reload --port \"$PORT\"\n",
            requirements="uvicorn\n",
        )
        result = contract_harness.run_harness(root, harness, apply_fixes=False)
        assert result["passed"] is False
        assert result["verdict_classification"] == "FAIL: dependency not declared"
        assert any(v["rule_id"] == "FAIL_DEPENDENCY_DECLARATION" for v in result["violations"])


def test_registry_unavailable_is_environment_blocked_in_dependency_gate():
    with tempfile.TemporaryDirectory() as td:
        qodeyard = Path(td)
        (qodeyard / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        (qodeyard / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
        cfg = _smoke_config()
        with mock.patch(
            "smoqetester.dependency_gate.provision_validation_env",
            return_value=(None, "Temporary failure in name resolution"),
        ):
            report = run_smoketest(qodeyard, "1", cfg, changed_files=["main.py", "requirements.txt"])
        rows = [row.to_dict() for row in report.results if row.adapter == "dependency_gate" and row.name == "dependency_gate:python_provision"]
        assert rows
        assert rows[0]["failure_kind"] == "package_registry_unavailable"
        assert rows[0]["environment_blocked"] is True


def test_missing_package_manager_is_environment_blocked():
    with tempfile.TemporaryDirectory() as td:
        qodeyard = Path(td)
        (qodeyard / "package.json").write_text(
            json.dumps({"name": "x", "version": "1.0.0", "dependencies": {"left-pad": "1.3.0"}}),
            encoding="utf-8",
        )
        (qodeyard / "app.js").write_text("import leftPad from 'left-pad';\nconsole.log(leftPad('a', 2));\n", encoding="utf-8")
        cfg = _smoke_config()
        with mock.patch(
            "smoqetester.dependency_gate.find_binary",
            side_effect=lambda name, cwd=None: None,
        ):
            report = run_smoketest(qodeyard, "1", cfg, changed_files=["app.js", "package.json"])
        rows = [row.to_dict() for row in report.results if row.adapter == "dependency_gate" and row.name == "dependency_gate:node_install"]
        assert rows
        assert rows[0]["failure_kind"] == "unavailable_external_tool"
        assert rows[0]["environment_blocked"] is True


def test_api_behavior_pass_not_enough_when_run_sh_contract_fails():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        harness = _write_fastapi_fixture(
            root,
            "#!/bin/sh\nset -eu\npython -m uvicorn main:app --reload --port\n",
        )
        result = contract_harness.run_harness(root, harness, apply_fixes=False)
        assert result["passed"] is False
        assert result["verdict_classification"] == "FAIL: shellscript contract mismatch"
        assert any(v["rule_id"] == "FAIL_SHELLSCRIPT_CONTRACT" for v in result["violations"])


def test_inspection_verdict_classifies_shellscript_contract_failures():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "planning").mkdir(parents=True, exist_ok=True)
        (root / "qodeyard").mkdir(parents=True, exist_ok=True)
        (root / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (root / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (root / "planning" / "completion-criteria.v1.json").write_text(json.dumps({"required_files": []}), encoding="utf-8")
        (root / "planning" / "build-groups.v1.json").write_text(
            json.dumps({"items": [{"build_group_id": "bg1", "scope_id": "scope1", "briq_refs": []}], "briq_inventory": []}),
            encoding="utf-8",
        )
        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=root,
            cycle_num="1",
            overall_assessment="SUCCESS",
            validation_bundle={
                "status": "FAIL",
                "issues": [
                    {
                        "severity": "error",
                        "message": "run.sh contract mismatch",
                        "failure_kind": "shellscript_contract_mismatch",
                        "file": "run.sh",
                    }
                ],
                "validation_execution_mode": "MIXED",
            },
            realization_bundle={
                "scope_summary": {"touched_scopes": ["scope1"], "undeclared_touched_scopes": []},
                "confidence": "CONFIDENCE_HIGH",
                "unknowns": [],
                "evidence_status": "EVIDENCE_PARTIAL",
                "capability_mode": "MIXED_REASONING_EXECUTION",
            },
            inspection_input={"status": "READY", "required_inputs": {}},
            cross_briq_warnings=[],
            failed_briq_suggestions=[],
        )
        assert verdict["status"] == "FAILURE"
        assert verdict["verdict_classification"] == "FAIL: shellscript contract mismatch"


def test_inspection_verdict_classifies_registry_blockers_as_environment_blocked():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "planning").mkdir(parents=True, exist_ok=True)
        (root / "qodeyard").mkdir(parents=True, exist_ok=True)
        (root / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (root / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (root / "planning" / "completion-criteria.v1.json").write_text(json.dumps({"required_files": []}), encoding="utf-8")
        (root / "planning" / "build-groups.v1.json").write_text(
            json.dumps({"items": [{"build_group_id": "bg1", "scope_id": "scope1", "briq_refs": []}], "briq_inventory": []}),
            encoding="utf-8",
        )
        verdict = inspeqtor.build_inspection_verdict(
            worqspace_root=root,
            cycle_num="1",
            overall_assessment="SUCCESS",
            validation_bundle={
                "status": "FAIL",
                "issues": [
                    {
                        "severity": "error",
                        "message": "network unavailable",
                        "failure_kind": "package_registry_unavailable",
                        "file": "requirements.txt",
                        "environment_blocked": True,
                    }
                ],
                "validation_execution_mode": "MIXED",
            },
            realization_bundle={
                "scope_summary": {"touched_scopes": ["scope1"], "undeclared_touched_scopes": []},
                "confidence": "CONFIDENCE_HIGH",
                "unknowns": [],
                "evidence_status": "EVIDENCE_PARTIAL",
                "capability_mode": "MIXED_REASONING_EXECUTION",
            },
            inspection_input={"status": "READY", "required_inputs": {}},
            cross_briq_warnings=[],
            failed_briq_suggestions=[],
        )
        assert verdict["status"] == "ENVIRONMENT_BLOCKED"
        assert verdict["verdict_classification"] == "ENVIRONMENT_BLOCKED: package registry unavailable"
