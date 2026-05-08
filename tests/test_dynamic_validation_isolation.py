import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worqer"))

import contract_harness  # noqa: E402
import inspeqtor  # noqa: E402


def _mk_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "qage_dynamic"
    qodeyard = root / "qodeyard"
    tasq = root / "tasq.d" / "cyqle1_tasq.md"
    qodeyard.mkdir(parents=True, exist_ok=True)
    tasq.parent.mkdir(parents=True, exist_ok=True)
    return root, qodeyard, tasq


def _write_planning(root: Path, required_files: list[str]):
    planning = root / "planning"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "execution-blueprint.v1.json").write_text("{}", encoding="utf-8")
    (planning / "validation-plan.v1.json").write_text("{}", encoding="utf-8")
    (planning / "completion-criteria.v1.json").write_text(
        json.dumps({"required_files": required_files, "tier": "medium"}),
        encoding="utf-8",
    )
    (planning / "build-groups.v1.json").write_text(
        json.dumps({"items": [{"build_group_id": "bg1", "scope_id": "scope1", "briq_refs": []}], "briq_inventory": []}),
        encoding="utf-8",
    )


def test_no_cross_contamination_between_two_tasks(tmp_path):
    root, qodeyard, tasq = _mk_workspace(tmp_path)

    tasq_a = """
The project must contain exactly these files:
- `a.txt`
- `b.txt`
- `c.txt`
"""
    tasq_b = """
The project must contain exactly these files:
- `x.txt`
- `y.txt`
"""

    tasq.write_text(tasq_a, encoding="utf-8")
    harness_a = contract_harness.build_harness(tasq_a, worqspace_root=root, source_tasq_path=str(tasq))

    tasq.write_text(tasq_b, encoding="utf-8")
    harness_b = contract_harness.build_harness(tasq_b, worqspace_root=root, source_tasq_path=str(tasq))

    assert harness_a["file_rules"]["required_files"] == ["a.txt", "b.txt", "c.txt"]
    assert harness_b["file_rules"]["required_files"] == ["x.txt", "y.txt"]

    (qodeyard / "x.txt").write_text("x", encoding="utf-8")
    (qodeyard / "y.txt").write_text("y", encoding="utf-8")

    result_a = contract_harness.run_harness(qodeyard, harness_a)
    result_b = contract_harness.run_harness(qodeyard, harness_b)

    codes_a = {row.get("code") for row in result_a.get("violations", [])}
    assert "FILE_REQUIRED_MISSING" in codes_a
    assert result_b["passed"] is True


def test_allowed_only_files_reject_extra(tmp_path):
    root, qodeyard, tasq = _mk_workspace(tmp_path)
    task_text = """
The project must contain exactly these files:
- `alpha.txt`
- `beta.txt`
No extra files.
"""
    tasq.write_text(task_text, encoding="utf-8")
    harness = contract_harness.build_harness(task_text, worqspace_root=root, source_tasq_path=str(tasq))

    (qodeyard / "alpha.txt").write_text("a", encoding="utf-8")
    (qodeyard / "beta.txt").write_text("b", encoding="utf-8")
    (qodeyard / "extra.txt").write_text("x", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    codes = {row.get("code") for row in result.get("violations", [])}

    assert result["passed"] is False
    assert "FILE_EXTRA_PRESENT" in codes
    assert "DELIVERABLE_SET_MISMATCH" in codes


def test_shellscript_required_vs_not_required(tmp_path):
    root, qodeyard, tasq = _mk_workspace(tmp_path)

    task_shell = """
Project must contain exactly these files:
- `launch.sh`
launch exactly this command: sh app.sh
"""
    tasq.write_text(task_shell, encoding="utf-8")
    harness_shell = contract_harness.build_harness(task_shell, worqspace_root=root, source_tasq_path=str(tasq))

    result_missing = contract_harness.run_harness(qodeyard, harness_shell)
    codes_missing = {row.get("code") for row in result_missing.get("violations", [])}
    assert "SHELLSCRIPT_REQUIRED_MISSING" in codes_missing

    task_no_shell = """
Project must contain exactly these files:
- `index.html`
- `app.js`
- `styles.css`
No extra files.
"""
    tasq.write_text(task_no_shell, encoding="utf-8")
    harness_no_shell = contract_harness.build_harness(task_no_shell, worqspace_root=root, source_tasq_path=str(tasq))

    (qodeyard / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (qodeyard / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (qodeyard / "styles.css").write_text("body{}", encoding="utf-8")
    (qodeyard / "launch.sh").write_text("echo hi", encoding="utf-8")

    result_extra = contract_harness.run_harness(qodeyard, harness_no_shell)
    codes_extra = {row.get("code") for row in result_extra.get("violations", [])}
    assert "FILE_EXTRA_PRESENT" in codes_extra


def test_runtime_entrypoint_ambiguity_is_blocked(tmp_path):
    root, qodeyard, tasq = _mk_workspace(tmp_path)
    task_text = """
Project must contain exactly these files:
- `one.html`
- `two.html`
- `app.js`
- `styles.css`
"""
    tasq.write_text(task_text, encoding="utf-8")
    harness = contract_harness.build_harness(task_text, worqspace_root=root, source_tasq_path=str(tasq))

    for name in ["one.html", "two.html"]:
        (qodeyard / name).write_text("<html><body>x</body></html>", encoding="utf-8")
    (qodeyard / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (qodeyard / "styles.css").write_text("body{}", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    codes = {row.get("code") for row in result.get("violations", [])}

    assert "RUNTIME_ENTRYPOINT_AMBIGUOUS" in codes


def test_cli_runtime_contract_is_used(tmp_path):
    root, qodeyard, tasq = _mk_workspace(tmp_path)
    task_text = "Project must contain exactly these files: `tool.py`"
    tasq.write_text(task_text, encoding="utf-8")
    harness = contract_harness.build_harness(task_text, worqspace_root=root, source_tasq_path=str(tasq))

    harness["runtime_checks"] = [
        {
            "runtime_type": "cli_command",
            "required": True,
            "commands": [
                {
                    "command": "python3 tool.py",
                    "expected_exit": 0,
                    "stdout_regex": "HELLO_CLI",
                }
            ],
        }
    ]
    harness["task_identity"]["contract_hash"] = contract_harness._compute_contract_hash(harness)  # type: ignore[attr-defined]

    (qodeyard / "tool.py").write_text("print('HELLO_CLI')\n", encoding="utf-8")

    result = contract_harness.run_harness(qodeyard, harness)
    assert result["passed"] is True


def test_completion_gate_rejects_deterministic_failures(tmp_path):
    root, _, _ = _mk_workspace(tmp_path)
    _write_planning(root, ["index.html", "styles.css", "app.js"])

    verdict = inspeqtor.build_inspection_verdict(
        worqspace_root=root,
        cycle_num="1",
        overall_assessment="SUCCESS",
        validation_bundle={
            "status": "PASS",
            "issues": [
                {
                    "severity": "error",
                    "source": "contract_harness",
                    "message": "required runtime unsupported",
                    "check_type": "RUNTIME_TYPE_UNSUPPORTED",
                    "failure_kind": "runtime_type_unsupported",
                    "file": "index.html",
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

    assert verdict["hard_gate_status"] == "FAIL"
    assert verdict["task_completed"] is False
    assert verdict["repair_required"] is True
    assert verdict["status"] in {"FAILURE", "ENVIRONMENT_BLOCKED"}


def test_contract_identity_uses_explicit_run_id_env(tmp_path, monkeypatch):
    root, qodeyard, tasq = _mk_workspace(tmp_path)
    monkeypatch.setenv("QONQ_RUN_ID", "qage_test_identity_001")
    task_text = """
The project must contain exactly these files:
- `main.txt`
"""
    tasq.write_text(task_text, encoding="utf-8")
    harness = contract_harness.build_harness(task_text, worqspace_root=root, source_tasq_path=str(tasq))
    assert harness["task_identity"]["qage_id"] == "qage_test_identity_001"

    (qodeyard / "main.txt").write_text("ok", encoding="utf-8")
    result = contract_harness.run_harness(qodeyard, harness)
    assert result["artifact_identity"]["qage_id"] == "qage_test_identity_001"
    codes = {row.get("code") for row in result.get("violations", [])}
    assert "CONTRACT_QAGE_ID_MISMATCH" not in codes
