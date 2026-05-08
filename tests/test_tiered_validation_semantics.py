from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

import construqtor
import inspeqtor


def _validation_result(*, passed: bool, error: str = "") -> dict:
    return {
        "passed": passed,
        "syntax_errors": [] if passed else [error or "synthetic syntax failure"],
        "constraint_errors": [],
        "import_warnings": [],
        "files_checked": 1,
    }


def test_l1_invalid_python_syntax_fails_immediately_after_file_write(tmp_path: Path) -> None:
    qodeyard = tmp_path / "qodeyard"
    qodeyard.mkdir()
    (qodeyard / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    result = construqtor.run_local_validation(["bad.py"], qodeyard)

    assert result["passed"] is False
    assert result["syntax_errors"]
    assert "SyntaxError" in result["syntax_errors"][0]


def test_incomplete_batch_missing_sibling_import_stays_file_local(tmp_path: Path) -> None:
    qodeyard = tmp_path / "qodeyard"
    qodeyard.mkdir()
    (qodeyard / "app.py").write_text("from app_helper import value\nprint(value)\n", encoding="utf-8")

    result = construqtor.run_local_validation(["app.py"], qodeyard)

    assert result["passed"] is True
    assert result["syntax_errors"] == []
    assert result["constraint_errors"] == []


def test_l3_changed_set_validation_runs_after_sibling_batch_closes(tmp_path: Path) -> None:
    worqspace = tmp_path / "worqspace"
    qodeyard = worqspace / "qodeyard"
    qodeyard.mkdir(parents=True)
    validation_root = worqspace / "validation-root"
    calls: list[list[str]] = []

    def fake_validation(files, *_args, **_kwargs):
        calls.append(list(files))
        return _validation_result(passed=True)

    with mock.patch("construqtor.run_scoped_qualification", side_effect=fake_validation), mock.patch(
        "construqtor.lib_ai.run_ai_completion",
        return_value={
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "app.py", "content": "from app_helper import value\nprint(value)\n"}),
                    }
                },
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "app_helper.py", "content": "value = 42\n"}),
                    }
                },
            ]
        },
    ):
        _, meta = construqtor._run_direct_coding_loop(
            "provider",
            "model",
            "prompt",
            [],
            [],
            validation_root,
            qodeyard,
            worqspace,
            {},
            return_meta=True,
        )

    assert calls == [["app.py", "app_helper.py"]]
    assert meta["validated_batches"][0]["status"] == "PASS"


def test_l0_path_traversal_is_rejected_before_write_regardless_of_batch_state(tmp_path: Path) -> None:
    validation_root = tmp_path / "validation-root"
    validation_root.mkdir()

    with pytest.raises(Exception):
        construqtor._write_text(validation_root / ".." / "escape.py", "x = 1\n", jail=validation_root)

    assert not (tmp_path / "escape.py").exists()


def test_scoped_qonfirmer_runs_after_changed_set_checkpoint(tmp_path: Path, monkeypatch) -> None:
    worqspace = tmp_path / "worqspace"
    qodeyard = worqspace / "qodeyard"
    qodeyard.mkdir(parents=True)
    (qodeyard / "app.py").write_text("print('ok')\n", encoding="utf-8")
    calls: list[str] = []

    def fake_scoped(*_args, **_kwargs):
        calls.append("scoped")
        return _validation_result(passed=True)

    class FakeReport:
        passed = True
        violations: list[dict] = []

        def to_json(self) -> dict:
            return {"status": "PASS", "violations": []}

    class FakeQonfirmer:
        @staticmethod
        def run_qonfirmer_for_files(*_args, **_kwargs):
            calls.append("qonfirmer")
            return FakeReport()

    monkeypatch.setattr(construqtor, "run_scoped_qualification", fake_scoped)
    monkeypatch.setattr(construqtor, "collect_scope_validation_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(construqtor, "qonfirmer", FakeQonfirmer)

    state = construqtor._evaluate_repair_scope_state(
        worqspace,
        qodeyard,
        repair_targets=["app.py"],
        validation_scope_files=["app.py"],
        is_contract_relevant=True,
        contract_data={"invariants": {"forbidden_imports": ["uuid"]}},
        build_group=None,
        repair_plan_payload={},
    )

    assert calls == ["scoped", "qonfirmer"]
    assert state["passed"] is True


def test_full_qonfirmer_runs_at_stage_final_gate() -> None:
    source = Path(inspeqtor.__file__).read_text(encoding="utf-8")

    assert "STAGE 0: Qonfirmer" in source
    assert "qonfirmer.run_qonfirmer(contract, qodeyard_path)" in source


def test_batch_level_failure_requests_repair_for_cumulative_batch_not_only_last_file(tmp_path: Path, monkeypatch) -> None:
    worqspace = tmp_path / "worqspace"
    qodeyard = worqspace / "qodeyard"
    qodeyard.mkdir(parents=True)
    validation_root = worqspace / "validation-root"

    monkeypatch.setenv("QONQ_DIRECT_MAX_TOOL_ITERATIONS", "1")
    with mock.patch("construqtor.run_scoped_qualification", return_value=_validation_result(passed=False, error="batch failed")), mock.patch(
        "construqtor.lib_ai.run_ai_completion",
        return_value={
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "app.py", "content": "from app_helper import value\nprint(value)\n"}),
                    }
                },
                {
                    "function": {
                        "name": "write_file_direct",
                        "arguments": json.dumps({"path": "app_helper.py", "content": "value = 42\n"}),
                    }
                },
            ]
        },
    ):
        _, meta = construqtor._run_direct_coding_loop(
            "provider",
            "model",
            "prompt",
            [],
            [],
            validation_root,
            qodeyard,
            worqspace,
            {},
            return_meta=True,
        )

    assert meta["validated_batches"][0]["status"] == "FAIL"
    assert meta["validated_batches"][0]["batch_files"] == ["app.py", "app_helper.py"]
    assert meta["validated_batches"][0]["cumulative_files"] == ["app.py", "app_helper.py"]
    assert meta["last_failed_batch"] == ["app.py", "app_helper.py"]
