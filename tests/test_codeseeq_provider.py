from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))
sys.path.insert(0, str(PROJECT_ROOT / "qrane"))

import context_bundle  # noqa: E402
import construqtor  # noqa: E402
import contract_harness  # noqa: E402
import lib_ai  # noqa: E402
import qrane  # noqa: E402


def test_codeseeq_capability_resolution() -> None:
    cap = lib_ai.resolve_model_capabilities("codeseeq", "deepseek-v4-flash", config={})
    assert cap.total_context_window == 1000000
    assert cap.safe_output_tokens == 384000
    assert cap.supports_chunk_preload is False


def test_codeseeq_dispatch_command_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="diagnostic\n")

    monkeypatch.setenv("QONQ_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(lib_ai, "_find_codeseeq_binary", lambda *_args, **_kwargs: Path("/fake/codeseeq"))
    monkeypatch.setattr(lib_ai.subprocess, "run", fake_run)

    text = lib_ai.run_ai_completion(
        "codeseeq",
        "deepseek-v4-flash",
        "hello",
        config={},
        agent_name="construqtor",
        stream_callback=False,
    )

    assert text == "ok"
    argv = captured["argv"]
    assert argv[:5] == ["/fake/codeseeq", "-m", "deepseek-v4-flash", "-y", "run"]
    assert "hello" in argv[5]
    kwargs = captured["kwargs"]
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["capture_output"] is True


def test_codeseeq_large_prompt_file_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return types.SimpleNamespace(returncode=0, stdout="file ok", stderr="")

    messages = [{"role": "user", "content": "large prompt content"}]
    monkeypatch.setenv("QONQ_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("QONQ_CODESEEQ_INLINE_MAX_CHARS", "10")
    monkeypatch.setattr(lib_ai, "_find_codeseeq_binary", lambda *_args, **_kwargs: Path("/fake/codeseeq"))
    monkeypatch.setattr(lib_ai.subprocess, "run", fake_run)

    result = lib_ai.run_ai_messages(
        "codeseeq",
        "deepseek-v4-flash",
        messages,
        output_tokens=42,
        timeout=5,
        config={},
        agent_name="instruqtor",
        stream_callback=False,
    )

    assert result.text == "file ok"
    argv = captured["argv"]
    assert argv[:6] == ["/fake/codeseeq", "-m", "deepseek-v4-flash", "-y", "run", "-f"]
    prompt_file = Path(argv[6])
    assert prompt_file.exists()
    expected = lib_ai._codeseeq_prompt_from_messages(messages, output_tokens=42, agent_name="instruqtor")
    assert prompt_file.read_text(encoding="utf-8") == expected


def test_codeseeq_nonzero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(argv, **kwargs):
        return types.SimpleNamespace(returncode=1, stdout="bad stdout", stderr="bad stderr")

    monkeypatch.setenv("QONQ_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(lib_ai, "_find_codeseeq_binary", lambda *_args, **_kwargs: Path("/fake/codeseeq"))
    monkeypatch.setattr(lib_ai.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc:
        lib_ai.run_ai_messages(
            "codeseeq",
            "deepseek-v4-flash",
            [{"role": "user", "content": "hello"}],
            output_tokens=42,
            timeout=5,
            config={},
            stream_callback=False,
        )

    msg = str(exc.value)
    assert "bad stderr" in msg
    assert "bad stdout" in msg
    assert "deepseek-v4-flash" in msg


def test_codeseeq_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 3, output="partial stdout", stderr="partial stderr")

    monkeypatch.setenv("QONQ_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(lib_ai, "_find_codeseeq_binary", lambda *_args, **_kwargs: Path("/fake/codeseeq"))
    monkeypatch.setattr(lib_ai.subprocess, "run", fake_run)

    with pytest.raises(lib_ai.TimeoutError) as exc:
        lib_ai.run_ai_messages(
            "codeseeq",
            "deepseek-v4-flash",
            [{"role": "user", "content": "hello"}],
            output_tokens=42,
            timeout=3,
            config={},
            stream_callback=False,
        )

    assert "timeout after 3s" in str(exc.value)
    assert "partial stderr" in str(exc.value)


def test_codeseeq_tools_unsupported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QONQ_WORKSPACE", str(tmp_path))

    with pytest.raises(RuntimeError) as exc:
        lib_ai.run_ai_messages(
            "codeseeq",
            "deepseek-v4-flash",
            [{"role": "user", "content": "hello"}],
            output_tokens=42,
            timeout=3,
            tools=[{"type": "function", "function": {"name": "x"}}],
            config={},
            stream_callback=False,
        )

    assert "does not support QonQrete-level tool_calls yet" in str(exc.value)


def test_qrane_codeseeq_requires_deepseek_api_key(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    config = {"agents": {"construqtor": {"provider": "codeseeq", "model": "deepseek-v4-flash"}}}
    exits: list[int] = []
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(qrane.sys, "exit", lambda code=0: exits.append(code))

    qrane.check_api_keys(config, "[Qrane] ")

    out = capsys.readouterr().out
    assert exits and exits[0] == 1
    assert "DEEPSEEK_API_KEY" in out


def test_qontrabender_codeseeq_cache_backend() -> None:
    cfg = {"enabled": True, "deepseek_stable_prefix_enabled": True}
    assert (
        context_bundle.resolve_qontrabender_cache_backend(
            provider="codeseeq",
            provider_cache_cfg=cfg,
        )
        == "stable_prefix_auto"
    )


def test_construqtor_codeseeq_backend_detection() -> None:
    backend = construqtor.detect_execution_backend("codeseeq", "deepseek-v4-flash")
    assert backend["backend_kind"] == "codex_style_scoped_execution_engine"
    assert backend["backend_family"] == "codeseeq"


def test_construqtor_codeseeq_forces_non_tool_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QONQ_CODING_MODE", raising=False)
    strategy = construqtor.get_write_strategy_config(
        {"agents": {"construqtor": {"provider": "codeseeq", "coding_mode": "hybrid"}}}
    )
    assert strategy["requested_coding_mode"] == "hybrid"
    assert strategy["coding_mode"] == "heredoc"
    assert strategy["codeseeq_cli_forced_heredoc"] is True


def test_construqtor_harness_prompt_includes_http_status_and_shell_policy(tmp_path: Path) -> None:
    worqspace = tmp_path / "qage_test"
    tasq_dir = worqspace / "tasq.d"
    tasq_dir.mkdir(parents=True)
    task_text = """
Create a FastAPI REST API.
- POST /users
- GET /users
Add run.sh to launch exectly this uvicorn command: python -m uvicorn main:app --reload --port $PORT
"""
    tasq_path = tasq_dir / "cyqle1_tasq.md"
    tasq_path.write_text(task_text, encoding="utf-8")
    harness = contract_harness.build_harness(task_text, worqspace_root=worqspace, source_tasq_path=str(tasq_path))
    contract_harness.write_harness(worqspace, harness)

    rendered = construqtor.build_harness_prompt_context(worqspace, ["main.py", "run.sh"])

    assert "POST `/users` must return HTTP 201" in rendered
    assert "status_code=201" in rendered
    assert "Use this launcher command exactly: `python -m uvicorn main:app --reload --port $PORT`" in rendered
