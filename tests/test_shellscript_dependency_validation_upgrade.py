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
from smoqetester.adapters.shell import ShellAdapter  # noqa: E402
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


def _write_shell_dependency_fixture(root: Path, run_sh_text: str, requirements: str = "alpha_pkg\nbeta_pkg\n") -> dict:
    main_py = root / "service.py"
    req = root / "requirements.txt"
    run_sh = root / "run.sh"

    main_py.write_text(
        "\n".join(
            [
                "import os",
                "",
                "def main() -> None:",
                "    port = os.environ.get('PORT', '8000')",
                "    print(f'listening on {port}')",
                "",
                "if __name__ == '__main__':",
                "    main()",
            ]
        ),
        encoding="utf-8",
    )
    req.write_text(requirements, encoding="utf-8")
    run_sh.write_text(run_sh_text, encoding="utf-8")
    run_sh.chmod(0o755)
    return {
        "harness_id": "generic_contract.v1",
        "required_files": ["service.py", "requirements.txt", "run.sh"],
        "dependency_checks": {
            "required_packages": ["alpha_pkg", "beta_pkg"]
        },
        "shellscript_checks": [
            {
                "file": "run.sh",
                "command_policy": {
                    "exact_command_required": "python service.py --port $PORT",
                    "allow_wrapper": False,
                    "allowed_boilerplate": ["set", "export"],
                },
            }
        ]
    }


def test_regression_missing_port_value_in_run_sh_is_contract_fail():
    errors = validate_run_sh_contract(
        "python service.py --port\n",
        {"exact_command_required": "python service.py --port $PORT", "allow_wrapper": False},
    )
    assert any("must include exact command" in msg.lower() for msg in errors)


def test_regression_hardcoded_port_in_run_sh_is_contract_fail():
    errors = validate_run_sh_contract(
        "python service.py --port 8000\n",
        {
            "exact_command_required": "python service.py --port $PORT",
            "allow_wrapper": False,
            "forbid_literal_values": ["8000"],
        },
    )
    assert any("forbidden literal values present" in msg.lower() or "must include exact command" in msg.lower() for msg in errors)


def test_regression_hardcoded_port_assignment_forbidden_in_exact_mode():
    errors = validate_run_sh_contract(
        "#!/bin/sh\nexport PORT=8000\npython service.py --port $PORT\n",
        {
            "allowed_commands": ["python service.py --port $PORT"],
            "required_variables": ["PORT"],
            "forbid_literal_values": ["8000"],
        },
    )
    assert any("forbidden literal values present" in msg.lower() for msg in errors)


def test_regression_exact_mode_rejects_port_wrapper_extraction_logic():
    errors = validate_run_sh_contract(
        "#!/bin/sh\nPORT=$(python -c \"print(9000)\")\npython service.py --port $PORT\n",
        {"exact_command_required": "python service.py --port $PORT", "allow_wrapper": False},
    )
    assert any("only allowed boilerplate and the exact launcher command are permitted" in msg for msg in errors)


def test_regression_wrong_uvicorn_target_is_contract_fail():
    errors = validate_run_sh_contract(
        "python wrong.py --port $PORT\n",
        {"allowed_commands": ["python service.py --port $PORT"]},
    )
    assert any("allowed command set" in msg for msg in errors)


def test_shellscript_syntax_error_is_classified():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        harness = _write_shell_dependency_fixture(
            root,
            "#!/bin/sh\nif then\n  echo broken\nfi\n",
        )
        result = contract_harness.run_harness(root, harness, apply_fixes=False)
        assert result["passed"] is False
        assert result["verdict_classification"] == "FAIL: deterministic contract validation failed"
        assert any(v["rule_id"] == "SHELLSCRIPT_COMMAND_MISMATCH" for v in result["violations"])


def test_missing_dependency_from_requirements_is_fail_dependency_not_declared():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        harness = _write_shell_dependency_fixture(
            root,
            "#!/bin/sh\nset -eu\npython service.py --port $PORT\n",
            requirements="beta_pkg\n",
        )
        result = contract_harness.run_harness(root, harness, apply_fixes=False)
        assert result["passed"] is False
        assert result["verdict_classification"] == "FAIL: deterministic contract validation failed"
        assert any(v["rule_id"] == "DEPENDENCY_MISSING_DECLARATION" for v in result["violations"])


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


def test_fastapi_transitively_covers_pydantic_in_dependency_gate():
    with tempfile.TemporaryDirectory() as td:
        qodeyard = Path(td)
        (qodeyard / "main.py").write_text(
            "\n".join(
                [
                    "from fastapi import FastAPI",
                    "from pydantic import BaseModel",
                    "app = FastAPI()",
                    "class User(BaseModel):",
                    "    id: int",
                ]
            ),
            encoding="utf-8",
        )
        (qodeyard / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
        cfg = _smoke_config()
        with mock.patch(
            "smoqetester.dependency_gate.provision_validation_env",
            return_value=("/usr/bin/python3", None),
        ):
            report = run_smoketest(qodeyard, "1", cfg, changed_files=["main.py", "requirements.txt"])

        declaration_rows = [
            row.to_dict()
            for row in report.results
            if row.adapter == "dependency_gate" and row.name == "dependency_gate:python_declarations"
        ]
        assert declaration_rows == []


def test_api_behavior_pass_not_enough_when_run_sh_contract_fails():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        harness = _write_shell_dependency_fixture(
            root,
            "#!/bin/sh\nset -eu\npython service.py --port\n",
        )
        result = contract_harness.run_harness(root, harness, apply_fixes=False)
        assert result["passed"] is False
        assert result["verdict_classification"] == "FAIL: deterministic contract validation failed"
        assert any(v["rule_id"] == "SHELLSCRIPT_COMMAND_MISMATCH" for v in result["violations"])


def test_shell_fastapi_contract_probe_uses_task_valid_user_payloads_and_hides_password():
    adapter = ShellAdapter()
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, url: str, payload: dict | None = None, timeout: float = 2.0):
        del timeout
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return 200, {"status": "healthy"}, '{"status":"healthy"}'
        if method == "POST" and url.endswith("/users"):
            assert payload is not None
            assert 3 <= len(payload["username"]) <= 20
            assert len(payload["password"]) >= 6
            assert "@" in payload["email"]
            user_id = 1 if payload["username"] == "alice" else 2
            body = {"id": user_id, "username": payload["username"], "email": payload["email"]}
            return 201, body, json.dumps(body)
        if method == "GET" and url.endswith("/users"):
            return 200, [{"id": 1}, {"id": 2}], '[{"id":1},{"id":2}]'
        if method == "GET" and url.endswith("/users/1"):
            return 200, {"id": 1, "username": "alice", "email": "alice@example.com"}, '{"id":1}'
        if method == "GET" and url.endswith("/users/999"):
            return 404, {"detail": "User not found"}, '{"detail":"User not found"}'
        raise AssertionError(f"Unexpected request: {method} {url}")

    adapter._http_json_request = fake_request  # type: ignore[method-assign]

    assert adapter._exercise_fastapi_contract("http://example.test") is None
    posted_payloads = [payload for method, _, payload in calls if method == "POST"]
    assert [payload["username"] for payload in posted_payloads if payload] == ["alice", "bravo"]


def test_http_contract_harness_orders_user_update_before_delete():
    task = """
Create a FastAPI REST API.
- requirements.txt
- run.sh: python -m uvicorn main:app --reload --port $PORT
- GET /health -> {"status": "healthy"}
- POST /users -> creates a user
- GET /users -> list users
- GET /users/{user_id} -> one user or 404
- DELETE /users/{user_id} -> deletes user or 404
- PUT /users/{user_id} -> accepts partial update and returns user or 404
Validation:
- username must be 3-20 characters
- password must be at least 6 characters
"""
    harness = contract_harness.build_harness(task)
    checks = harness.get("runtime_checks") or []
    assert checks
    probes = checks[0].get("probes") or []
    order = [(probe["method"], probe["path"]) for probe in probes]

    assert order.index(("POST", "/users")) < order.index(("PUT", "/users/1"))
    assert order.index(("PUT", "/users/1")) < order.index(("DELETE", "/users/1"))


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


def test_harness_pass_does_not_override_failing_validation_bundle():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "planning").mkdir(parents=True, exist_ok=True)
        (root / "qodeyard").mkdir(parents=True, exist_ok=True)
        (root / "qontract.d").mkdir(parents=True, exist_ok=True)
        (root / "planning" / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
        (root / "planning" / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
        (root / "planning" / "completion-criteria.v1.json").write_text(json.dumps({"required_files": []}), encoding="utf-8")
        (root / "planning" / "build-groups.v1.json").write_text(
            json.dumps({"items": [{"build_group_id": "bg1", "scope_id": "scope1", "briq_refs": []}], "briq_inventory": []}),
            encoding="utf-8",
        )
        (root / "qontract.d" / "harness-result.v1.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "verdict_classification": "PASS",
                    "completion_override": {"allowed": True},
                    "violations": [],
                }
            ),
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
                        "message": "Dependency not declared: requests",
                        "failure_kind": "dependency_not_declared",
                        "file": "requirements.txt",
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
        assert verdict["repair_required"] is True


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
