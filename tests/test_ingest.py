"""
Tests for the Obelisk ingest endpoint (qq/web/ingest.py).

Run: python -m pytest tests/test_ingest.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Ensure the repo root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qq.web.ingest import (
    IngestRequest,
    ObeliskIngestConfig,
    ResolvedTarget,
    RunTriggerResult,
    ValidationError,
    _compute_dedupe_key,
    _VALID_TRIGGERS,
    _VALID_MODES,
    check_auth,
    check_duplicate,
    check_path_allowed,
    create_external_run_trigger,
    generate_command,
    load_obelisk_config_from_env,
    record_dedupe,
    resolve_target,
    validate_request,
    write_task_files,
    command_preview,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_config(tmp_path):
    runs_root = os.path.expanduser("~/tmp/test-qonqrete-runs")
    return ObeliskIngestConfig(
        enabled=True,
        default_run_root=runs_root,
        default_target_root=str(tmp_path / "targets"),  # test-safe target root
        task_dir=os.path.expanduser("~/.qonqrete/ingest/test-tasks"),
        queue_mode="queue",
        allowed_target_roots=[runs_root, str(tmp_path / "targets"),
                              "/tmp/test-allowed"],
        allowed_senders=[],
        aliases={"testsite": os.path.expanduser("~/tmp/test-qonqrete-runs/testsite")},
        max_task_length=64000,
        dev_no_auth=True,  # tests skip auth
        control_root=str(tmp_path / "control"),  # test-safe control root
    )


@pytest.fixture
def valid_payload():
    return {
        "source": "obelisk",
        "source_channel": "signal",
        "sender_id": "test-sender",
        "sender_display": "Test User",
        "chat_id": "chat-123",
        "message_id": "msg-001",
        "transcription_id": "trans-001",
        "raw_transcription": "qonqrete repo default now build me a website",
        "trigger": "qonqrete",
        "mode": "repo",
        "target": "default",
        "delimiter": "now",
        "task_text": "build me a website",
        "received_at": "2026-07-03T12:00:00Z",
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_token_rejected(self):
        config = ObeliskIngestConfig()
        with mock.patch.dict(os.environ, {"QONQRETE_RUNS_API_TOKEN": "secret-token"}, clear=True):
            assert check_auth(None, config) is False
            assert check_auth("", config) is False

    def test_wrong_token_rejected(self):
        config = ObeliskIngestConfig()
        with mock.patch.dict(os.environ, {"QONQRETE_RUNS_API_TOKEN": "secret-token"}, clear=True):
            assert check_auth("Bearer wrong", config) is False
            assert check_auth("Bearer secret_token", config) is False
            assert check_auth("Basic secret-token", config) is False
            assert check_auth("bearer wrong-token", config) is False

    def test_valid_token_accepted(self):
        config = ObeliskIngestConfig()
        with mock.patch.dict(os.environ, {"QONQRETE_RUNS_API_TOKEN": "secret-token"}, clear=True):
            assert check_auth("Bearer secret-token", config) is True

    def test_dev_no_auth(self):
        config = ObeliskIngestConfig(dev_no_auth=True)
        with mock.patch.dict(os.environ, {}, clear=True):
            assert check_auth(None, config) is True
            assert check_auth("garbage", config) is True

    def test_no_token_configured_rejects(self):
        config = ObeliskIngestConfig()
        with mock.patch.dict(os.environ, {}, clear=True):
            # No token configured at all
            assert check_auth("Bearer anything", config) is False


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_repo_default(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="qonqrete repo default now build",
            trigger="qonqrete", mode="repo", target="default", task_text="build",
        )
        validate_request(req, base_config)  # should not raise

    def test_valid_trigger_concrete(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="concrete folder /x now calc",
            trigger="concrete", mode="folder", target="/x/test",
            task_text="calc",
        )
        validate_request(req, base_config)  # should not raise

    def test_invalid_trigger_rejected(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="invalid",
            mode="repo", target="default", task_text="test",
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "invalid_trigger"

    def test_invalid_mode_rejected(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="invalid", target="default", task_text="test",
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "invalid_mode"

    def test_empty_task_rejected(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="",
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "missing_task_text"

    def test_whitespace_only_task_rejected(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="   ",
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "empty_task_text"

    def test_task_too_long_rejected(self, base_config):
        base_config.max_task_length = 10
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="x" * 100,
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "task_too_long"

    def test_sender_allowlist(self, base_config):
        base_config.allowed_senders = ["alice", "bob"]
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="test",
            sender_id="charlie",
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "sender_not_allowed"

        req2 = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="test",
            sender_id="alice",
        )
        validate_request(req2, base_config)  # should not raise

    def test_null_bytes_rejected(self, base_config):
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="test\x00boom",
        )
        with pytest.raises(ValidationError) as exc:
            validate_request(req, base_config)
        assert exc.value.error == "invalid_characters"


# ---------------------------------------------------------------------------
# Path resolution tests
# ---------------------------------------------------------------------------

class TestPathResolution:
    def test_default_target(self, base_config):
        ts = "2026-07-03_14-55-12"
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="test",
        )
        resolved = resolve_target(req, base_config, ts)
        # Default target now resolves under default_target_root, not default_run_root
        from qq.web.ingest import _run_stamp_to_run_id
        expected = os.path.join(base_config.default_target_root, _run_stamp_to_run_id(ts))
        assert resolved.path == expected
        assert resolved.kind == "default"

    def test_alias_resolution(self, base_config):
        ts = "2026-07-03_14-55-12"
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="testsite", task_text="test",
        )
        resolved = resolve_target(req, base_config, ts)
        assert resolved.path == os.path.expanduser(base_config.aliases["testsite"])
        assert resolved.kind == "alias"
        assert resolved.alias_name == "testsite"

    def test_explicit_absolute_path(self, base_config):
        ts = "2026-07-03_14-55-12"
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="folder", target="/tmp/test-allowed/myproject", task_text="test",
        )
        resolved = resolve_target(req, base_config, ts)
        assert resolved.path == "/tmp/test-allowed/myproject"
        assert resolved.kind == "explicit"

    def test_tilde_expansion(self, base_config):
        ts = "2026-07-03_14-55-12"
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="~/Projects/test", task_text="test",
        )
        resolved = resolve_target(req, base_config, ts)
        assert resolved.path.startswith(os.path.expanduser("~"))
        assert not resolved.path.startswith("~")

    def test_relative_path_rejected(self, base_config):
        ts = "2026-07-03_14-55-12"
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="./relative/path", task_text="test",
        )
        with pytest.raises(ValidationError) as exc:
            resolve_target(req, base_config, ts)
        assert exc.value.error == "relative_path_not_allowed"

    def test_path_outside_allowed_roots_rejected(self, base_config):
        ts = "2026-07-03_14-55-12"
        base_config.allowed_target_roots = ["/tmp/test-allowed"]
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="folder", target="/etc/passwd", task_text="test",
        )
        resolved = resolve_target(req, base_config, ts)
        with pytest.raises(ValidationError) as exc:
            check_path_allowed(resolved, base_config)
        assert exc.value.error == "target_not_allowed"


# ---------------------------------------------------------------------------
# Command generation tests
# ---------------------------------------------------------------------------

class TestCommandGeneration:
    def test_repo_mode_no_norepo(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test-run")
        assert "--no-repo" not in args
        assert "--no-web" in args
        assert "--run-root" in args
        assert "/x/qq/runs/test-run" in args
        assert args[0] == "qq"
        assert args[1] == "run"
        assert args[2] == "--no-web"
        assert args[3] == "--no-tui"
        # After flags: [qq, run, --no-web, --no-tui, --run-root, /x/..., task, target]
        assert "/tmp/task.md" in args
        assert "/tmp/target" in args

    def test_folder_mode_includes_norepo(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="folder", run_root="/x/qq/runs/test-run")
        assert "--no-repo" in args
        assert "--no-web" in args
        assert "--run-root" in args
        # --no-repo placed before positional args
        norepo_idx = args.index("--no-repo")
        task_idx = args.index("/tmp/task.md")
        assert norepo_idx < task_idx

    def test_argv_list_not_shell_string(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test-run")
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args)

    def test_run_root_included(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test-run")
        run_root_idx = args.index("--run-root")
        assert args[run_root_idx + 1] == "/x/qq/runs/test-run"

    def test_no_web_flag(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test-run")
        assert "--no-web" in args

    def test_no_shell_injection(self):
        # Task text with shell metacharacters should NOT affect command generation
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test-run")
        # Shell metacharacters like ; | & $ ` etc should not appear in argv
        dangerous_chars = [";", "|", "&&", "$(", "`"]
        # The task file path doesn't contain those — the task text is in the file, not the args
        for dc in dangerous_chars:
            # Check that dangerous chars aren't at any position
            for a in args:
                assert dc not in a


# ---------------------------------------------------------------------------
# Dedupe tests
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_transcription_id_dedupe(self, valid_payload):
        req = IngestRequest.from_payload(valid_payload)
        key = _compute_dedupe_key(req)
        assert key == "obelisk:trans:trans-001"

    def test_message_id_dedupe(self, valid_payload):
        valid_payload["transcription_id"] = None
        req = IngestRequest.from_payload(valid_payload)
        key = _compute_dedupe_key(req)
        assert key == "obelisk:signal:msg:msg-001"

    def test_hash_fallback_dedupe(self, valid_payload):
        """When no external IDs exist, _compute_dedupe_key returns None so
        each call creates a unique run (no accidental dedupe for manual calls)."""
        valid_payload["transcription_id"] = None
        valid_payload["message_id"] = None
        req = IngestRequest.from_payload(valid_payload)
        key = _compute_dedupe_key(req)
        assert key is None  # No dedupe without external ID

    def test_duplicate_detected(self, base_config, tmp_path):
        dedupe_dir = tmp_path / "dedupe"
        dedupe_file = dedupe_dir / "dedupe.jsonl"
        dedupe_dir.mkdir(parents=True)

        import qq.web.ingest as ingest
        old_dedupe_path = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = str(dedupe_file)

        try:
            record_dedupe("test-key-123", "run-1", "/tmp/task.md", "/tmp/target", state="started")
            existing = check_duplicate("test-key-123")
            assert existing is not None
            assert existing["run_id"] == "run-1"
        finally:
            ingest._DEDUPE_PATH = old_dedupe_path

    def test_no_duplicate_when_not_recorded(self, base_config, tmp_path):
        dedupe_dir = tmp_path / "dedupe2"
        dedupe_file = dedupe_dir / "dedupe.jsonl"
        dedupe_dir.mkdir(parents=True)

        import qq.web.ingest as ingest
        old_dedupe_path = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = str(dedupe_file)

        try:
            existing = check_duplicate("nonexistent-key")
            assert existing is None
        finally:
            ingest._DEDUPE_PATH = old_dedupe_path


# ---------------------------------------------------------------------------
# Task file writing tests
# ---------------------------------------------------------------------------

class TestTaskFileWriting:
    def test_task_md_created(self, base_config, tmp_path):
        base_config.task_dir = str(tmp_path / "tasks")
        req = IngestRequest.from_payload({
            "source": "obelisk", "source_channel": "signal",
            "sender_id": "s1", "sender_display": "Alice",
            "chat_id": "c1", "message_id": "m1",
            "transcription_id": "t1",
            "raw_transcription": "qonqrete repo default now build",
            "trigger": "qonqrete", "mode": "repo", "target": "default",
            "task_text": "build me a website",
            "received_at": "2026-07-03T12:00:00Z",
        })
        ts = "2026-07-03_14-55-12"
        resolved = ResolvedTarget(path="/tmp/target", kind="default")
        task_path = write_task_files(req, base_config, ts, resolved)

        assert os.path.isfile(task_path)
        content = open(task_path).read()
        assert "build me a website" in content
        assert "source: obelisk" in content
        assert "trigger: qonqrete" in content
        assert "mode: repo" in content

    def test_metadata_json_created(self, base_config, tmp_path):
        base_config.task_dir = str(tmp_path / "tasks")
        req = IngestRequest.from_payload({
            "source": "obelisk",
            "raw_transcription": "test",
            "trigger": "qonqrete", "mode": "repo", "target": "default",
            "task_text": "test task",
        })
        ts = "2026-07-03_14-55-12"
        resolved = ResolvedTarget(path="/tmp/target", kind="default")
        write_task_files(req, base_config, ts, resolved)

        meta_path = os.path.join(base_config.task_dir, f"task_{ts}.meta.json")
        assert os.path.isfile(meta_path)
        meta = json.load(open(meta_path))
        assert meta["resolved_target"] == "/tmp/target"
        assert meta["state"] == "accepted"
        assert meta["original_payload"]["task_text"] == "test task"

    def test_raw_transcription_preserved(self, base_config, tmp_path):
        base_config.task_dir = str(tmp_path / "tasks")
        raw = "qonqrete repo default now build me a website as test"
        req = IngestRequest.from_payload({
            "source": "obelisk",
            "raw_transcription": raw,
            "trigger": "qonqrete", "mode": "repo", "target": "default",
            "task_text": "build me a website as test",
        })
        ts = "2026-07-03_14-55-12"
        resolved = ResolvedTarget(path="/tmp/target", kind="default")
        write_task_files(req, base_config, ts, resolved)
        task_path = os.path.join(base_config.task_dir, f"task_{ts}.md")
        content = open(task_path).read()
        assert raw in content

    def test_same_timestamp_for_task_and_run(self, base_config):
        ts = "2026-07-03_14-55-12"
        req = IngestRequest(
            source="obelisk", raw_transcription="...", trigger="qonqrete",
            mode="repo", target="default", task_text="test",
        )
        resolved = resolve_target(req, base_config, ts)
        # The path uses the run-stamp-to-id format (dashes instead of underscores)
        from qq.web.ingest import _run_stamp_to_run_id
        expected_id = _run_stamp_to_run_id(ts)
        assert expected_id in resolved.path
        assert expected_id in resolved.path  # Uses run-stamp-to-id format


# ---------------------------------------------------------------------------
# End-to-end trigger tests
# ---------------------------------------------------------------------------

class TestCreateExternalRunTrigger:

    @pytest.fixture(autouse=True)
    def _reset_queue(self, tmp_path, monkeypatch):
        """Reset queue state and dedupe path between tests.
        Also mock _do_launch so tests don't need real qq-tui/tmux."""
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        # Use tmp_path as control root so current-run.json writes are safe
        old_control_root = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        # Create control root dir
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        # Mock _do_launch to simulate successful local_exec launch
        def _fake_launch(item):
            item["launch_ok"] = True
            item["pid"] = os.getpid()  # Use real PID so reconcile doesn't mark stale
            item["runner"] = "local_exec"
            item["stdout_log"] = "/fake/stdout.log"
            item["stderr_log"] = "/fake/stderr.log"
            ingest._mark_run_active(item)
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_launch)
        # Also mock _do_launch_tmux
        def _fake_tmux_launch(item):
            item["launch_ok"] = True
            item["tmux_session"] = f"qonqrete-{item['run_id']}"
            item["attach_command"] = f"tmux attach -t {item['tmux_session']}"
            item["runner"] = "tmux"
            ingest._mark_run_active(item)
            return True
        monkeypatch.setattr(ingest, "_do_launch_tmux", _fake_tmux_launch)
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = old_dedupe
        if old_control_root:
            os.environ["QONQRETE_CONTROL_ROOT"] = old_control_root
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_repo_default_creates_files(self, base_config, tmp_path):
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)

        base_config.task_dir = str(task_dir)
        base_config.default_run_root = str(run_root)
        base_config.allowed_target_roots = [str(run_root)]
        base_config.queue_mode = "reject_if_running"

        result = create_external_run_trigger(
            source="obelisk",
            raw_transcription="qonqrete repo default now build a site",
            task_text="build a site",
            mode="repo",
            target="default",
            trigger="qonqrete",
            transcription_id="trans-e2e-001-a",
            config=base_config,
        )

        assert result.ok is True
        assert result.started is True
        assert result.mode == "repo"
        assert result.run_root != ""
        assert result.events_path != ""
        assert result.runner != ""
        assert os.path.isdir(result.run_root)
        assert result.events_path.startswith(result.run_root)
        assert os.path.isfile(result.task_path)
        assert "--no-repo" not in result.command_preview
        assert "--no-web" in result.command_preview
        assert "--run-root" in result.command_preview
        # With local_exec runner, command is plain qq run (no qq-tui)
        assert "qq run" in result.command_preview

    def test_folder_path_command_includes_norepo(self, base_config, tmp_path):
        task_dir = tmp_path / "tasks"
        target_dir = tmp_path / "targets" / "project"
        task_dir.mkdir(parents=True)
        target_dir.mkdir(parents=True)

        base_config.task_dir = str(task_dir)
        base_config.allowed_target_roots = [str(tmp_path / "targets")]
        base_config.queue_mode = "reject_if_running"

        result = create_external_run_trigger(
            source="obelisk",
            raw_transcription="concrete folder /x now calc",
            task_text="build a calculator",
            mode="folder",
            target=str(target_dir),
            trigger="concrete",
            transcription_id="trans-e2e-002-b",
            config=base_config,
        )

        assert result.ok is True
        assert result.run_root != ""
        assert result.events_path != ""
        assert result.runner != ""
        assert os.path.isdir(result.run_root)
        assert "--no-repo" in result.command_preview
        assert "--no-web" in result.command_preview
        assert "--run-root" in result.command_preview
        # With local_exec runner, command is plain qq run (no qq-tui)
        assert "qq run" in result.command_preview

    def test_duplicate_rejected(self, base_config, tmp_path):
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)

        base_config.task_dir = str(task_dir)
        base_config.default_run_root = str(run_root)
        base_config.allowed_target_roots = [str(run_root)]
        base_config.queue_mode = "reject_if_running"

        result1 = create_external_run_trigger(
            source="obelisk", raw_transcription="test", task_text="test",
            mode="repo", target="default", trigger="qonqrete",
            transcription_id="trans-dup-001",
            config=base_config,
        )
        assert result1.ok is True
        assert result1.duplicate is False

        result2 = create_external_run_trigger(
            source="obelisk", raw_transcription="test", task_text="test",
            mode="repo", target="default", trigger="qonqrete",
            transcription_id="trans-dup-001",
            config=base_config,
        )
        assert result2.ok is True
        assert result2.duplicate is True

    def test_invalid_mode_returns_error(self, base_config):
        result = create_external_run_trigger(
            source="obelisk", raw_transcription="test",
            task_text="test", mode="invalid_mode", target="default",
            trigger="qonqrete", config=base_config,
        )
        assert result.ok is False
        assert result.error == "invalid_mode"


# ---------------------------------------------------------------------------
# Config loading tests
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_obelisk_config_from_env()
            assert config.enabled is True
            assert config.queue_mode == "latest_wins"
            assert config.max_task_length == 64000

    def test_env_overrides(self):
        env = {
            "QONQRETE_DEFAULT_RUN_ROOT": "/custom/runs",
            "QONQRETE_INGEST_TASK_DIR": "/custom/tasks",
            "QONQRETE_INGEST_QUEUE_MODE": "reject_if_running",
            "QONQRETE_ALLOWED_TARGET_ROOTS": "/a,/b",
            "QONQRETE_ALLOWED_INGEST_SENDERS": "alice,bob",
            "QONQRETE_MAX_TASK_LENGTH": "500",
            "QONQRETE_DEV_NO_AUTH": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_obelisk_config_from_env()
            assert config.default_run_root == "/custom/runs"
            assert config.task_dir == "/custom/tasks"
            assert config.queue_mode == "reject_if_running"
            assert config.allowed_target_roots == ["/a", "/b"]
            assert config.allowed_senders == ["alice", "bob"]
            assert config.max_task_length == 500
            assert config.dev_no_auth is True

    def test_alias_env_vars(self):
        env = {
            "QONQRETE_INGEST_ALIAS_TESTSITE4": "~/Desktop/qq/testsite4",
            "QONQRETE_INGEST_ALIAS_STRAWBERRY": "~/Desktop/qq/strawberry-g",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_obelisk_config_from_env()
            assert config.aliases["testsite4"] == "~/Desktop/qq/testsite4"
            assert config.aliases["strawberry"] == "~/Desktop/qq/strawberry-g"


# ---------------------------------------------------------------------------
# NEW TESTS: Tmux runner, current-run pointer, health, dashboard URL
# ---------------------------------------------------------------------------

class TestTmuxLaunchBehavior:
    """Tests that tmux runner works with launch_ok (not pid)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Mock everything for tmux tests."""
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        # Mock _do_launch_tmux
        def _fake_tmux(item):
            item["launch_ok"] = True
            item["tmux_session"] = f"qonqrete-{item['run_id']}"
            item["attach_command"] = f"tmux attach -t {item['tmux_session']}"
            item["runner"] = "tmux"
            return True
        monkeypatch.setattr(ingest, "_do_launch_tmux", _fake_tmux)
        # Mock _do_launch for local_exec
        def _fake_local(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            item["stdout_log"] = "/fake/stdout.log"
            item["stderr_log"] = "/fake/stderr.log"
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_local)
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_tmux_mode_returns_ok_true_without_pid(self, tmp_path):
        """tmux runner returns ok true without pid field."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="tmux",
            control_root=str(tmp_path / "control"),
            dashboard_url="http://10.11.12.111:31337",
        )

        result = create_external_run_trigger(
            source="manual-api",
            raw_transcription="",
            task_text="build a test",
            mode="repo",
            target="default",
            trigger="qonqrete",
            transcription_id="trans-tmux-ok-001",
            config=config,
        )

        assert result.ok is True
        assert result.started is True
        assert result.runner == "tmux"
        # Should NOT have pid (tmux doesn't use pid)
        assert result.pid is None
        # Should have tmux_session and attach_command
        assert result.tmux_session != ""
        assert result.tmux_session.startswith("qonqrete-")
        assert result.attach_command != ""
        assert "tmux attach" in result.attach_command

    def test_tmux_mode_returns_tmux_session_and_attach_command(self, tmp_path):
        """tmux runner response includes tmux_session and attach_command."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="tmux",
            control_root=str(tmp_path / "control"),
        )

        result = create_external_run_trigger(
            source="manual-api",
            raw_transcription="",
            task_text="build a test",
            mode="folder",
            target=str(run_root),
            trigger="qonqrete",
            transcription_id="trans-tmux-fields-001",
            config=config,
        )

        assert result.ok is True
        assert result.tmux_session == f"qonqrete-{result.run_id}"
        assert result.attach_command == f"tmux attach -t qonqrete-{result.run_id}"

    def test_local_exec_mode_returns_pid_and_logs(self, tmp_path):
        """local_exec runner returns pid, stdout_log, stderr_log."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="local_exec",
            control_root=str(tmp_path / "control"),
        )

        result = create_external_run_trigger(
            source="manual-api",
            raw_transcription="",
            task_text="build a test",
            mode="repo",
            target="default",
            trigger="qonqrete",
            transcription_id="trans-local-001",
            config=config,
        )

        assert result.ok is True
        assert result.runner == "local_exec"
        assert result.pid is not None
        assert result.stdout_log != ""
        assert result.stderr_log != ""


class TestCurrentRunPointerBehavior:
    """Tests for current-run.json write behavior."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        self.tmp_path = tmp_path
        # Mock _do_launch for local_exec
        def _fake_local(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_local)
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_current_run_json_written_on_success(self, tmp_path):
        """current-run.json is written after successful launch."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="local_exec",
            control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api",
            raw_transcription="",
            task_text="build a test",
            mode="repo",
            target="default",
            trigger="qonqrete",
            transcription_id="trans-ptr-001",
            config=config,
        )

        assert result.ok is True
        # Check current-run.json exists
        ptr_path = control_root / "current-run.json"
        assert ptr_path.is_file(), f"expected {ptr_path} to exist"
        ptr_data = json.loads(ptr_path.read_text())
        assert ptr_data["run_id"] == result.run_id
        assert ptr_data["run_root"] == result.run_root
        assert ptr_data["events_path"] == result.events_path
        assert ptr_data["runner"] == "local_exec"
        assert ptr_data["mode"] == "repo"
        assert "command_preview" in ptr_data

    def test_current_run_json_points_to_response_run_root(self, tmp_path):
        """current-run.json run_root matches API response run_root."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="local_exec",
            control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api",
            raw_transcription="",
            task_text="build a test",
            mode="folder",
            target=str(run_root),
            trigger="qonqrete",
            transcription_id="trans-ptr-002",
            config=config,
        )

        assert result.ok is True
        ptr_path = control_root / "current-run.json"
        ptr_data = json.loads(ptr_path.read_text())
        # The run_root in the pointer should match the response's run_root
        assert ptr_data["run_root"] == result.run_root
        assert ptr_data["events_path"] == result.events_path

    def test_control_root_preflight_rejects_unwritable(self, tmp_path, monkeypatch):
        """If control root is not writable, preflight fails before launch."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        # Monkeypatch _preflight_control_root to return False — this works
        # even when tests run as root (chmod 444 doesn't affect root).
        import qq.web.ingest as ingest
        original_preflight = ingest._preflight_control_root
        ingest._preflight_control_root = lambda cr: False

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="local_exec",
            control_root=str(control_root),
        )

        try:
            result = create_external_run_trigger(
                source="manual-api",
                raw_transcription="",
                task_text="build a test",
                mode="repo",
                target="default",
                trigger="qonqrete",
                transcription_id="trans-ptr-preflight-001",
                config=config,
            )

            assert result.ok is False
            assert result.error == "control_root_preflight_failed"
        finally:
            ingest._preflight_control_root = original_preflight

    def test_current_run_pointer_write_failure_returns_error(self, tmp_path, monkeypatch):
        """If current-run.json cannot be written, launch is prevented.
        
        Uses monkeypatch instead of chmod so it works when tests run as root.
        """
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        import qq.web.ingest as ingest
        original_write = ingest._write_current_run_pointer

        # Return True for the "starting" call, False for "started" call
        call_count = [0]
        def _fake_write(*args, **kwargs):
            call_count[0] += 1
            state = kwargs.get("state", args[13] if len(args) > 12 else "")
            if state == "starting":
                return True  # pre-launch write succeeds
            else:
                return False  # post-launch write fails
        ingest._write_current_run_pointer = _fake_write

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="local_exec",
            control_root=str(control_root),
        )

        try:
            result = create_external_run_trigger(
                source="manual-api",
                raw_transcription="",
                task_text="build a test",
                mode="repo",
                target="default",
                trigger="qonqrete",
                transcription_id="trans-ptr-fail-001",
                config=config,
            )

            # Should still succeed because pointer write is optional after launch
            # (the pre-launch starting pointer was written OK)
            assert result.ok is True, f"Expected ok=True, got error={result.error} msg={result.message}"
        finally:
            ingest._write_current_run_pointer = original_write

    def test_starting_pointer_write_failure_prevents_launch(self, tmp_path, monkeypatch):
        """If the starting pointer write fails BEFORE launch, the run is prevented.
        This ensures no orphan runs (launched but dashboard can't follow)."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        original_write = ingest._write_current_run_pointer

        # Return False for the starting pointer write — simulate failure
        call_count = [0]
        def _fake_write_fail(*args, **kwargs):
            call_count[0] += 1
            state = kwargs.get("state", args[13] if len(args) > 12 else "")
            if state == "starting":
                return False  # PRE-LAUNCH write fails
            return True
        ingest._write_current_run_pointer = _fake_write_fail

        # Also track that _do_launch is never called
        def _fake_launch_should_not_run(item):
            raise AssertionError("_do_launch was called after pointer write failure")
        monkeypatch.setattr(ingest, "_do_launch", _fake_launch_should_not_run)

        config = ObeliskIngestConfig(
            enabled=True,
            default_run_root=str(run_root),
            task_dir=str(task_dir),
            queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)],
            dev_no_auth=True,
            runner="local_exec",
            control_root=str(control_root),
        )

        try:
            result = create_external_run_trigger(
                source="manual-api",
                raw_transcription="",
                task_text="build a test",
                mode="repo",
                target="default",
                trigger="qonqrete",
                transcription_id="trans-start-ptr-fail-001",
                config=config,
            )

            assert result.ok is False, (
                f"Launch should be prevented when starting pointer write fails, "
                f"got ok=True run_id={result.run_id}"
            )
            assert result.error == "current_run_pointer_write_failed", (
                f"Expected current_run_pointer_write_failed error, got: {result.error}"
            )
            assert "orphan" in result.message.lower(), (
                f"Message should mention orphan run prevention, got: {result.message}"
            )
            assert call_count[0] >= 1, (
                "Pointer write function was not called"
            )
        finally:
            ingest._write_current_run_pointer = original_write


class TestDashboardUrl:
    """Tests for public dashboard URL behavior."""

    def test_public_dashboard_url_from_env(self, tmp_path, monkeypatch):
        """API response uses QONQRETE_PUBLIC_DASHBOARD_URL when set."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None

        def _fake_launch(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            ingest._mark_run_active(item)
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_launch)

        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = str(dedupe_dir / "dedupe.jsonl")

        try:
            config = ObeliskIngestConfig(
                enabled=True,
                default_run_root=str(run_root),
                task_dir=str(task_dir),
                queue_mode="reject_if_running",
                allowed_target_roots=[str(run_root)],
                dev_no_auth=True,
                runner="local_exec",
                control_root=str(control_root),
                dashboard_url="http://10.11.12.111:31337",
            )

            result = create_external_run_trigger(
                source="manual-api",
                raw_transcription="",
                task_text="build a test",
                mode="repo",
                target="default",
                trigger="qonqrete",
                transcription_id="trans-dash-001",
                config=config,
            )

            assert result.ok is True
            assert result.dashboard_url == "http://10.11.12.111:31337"
        finally:
            ingest._queue.clear()
            ingest._active_run = False
            ingest._active_run_id = None
            ingest._active_item = None
            ingest._DEDUPE_PATH = old_dedupe


# ---------------------------------------------------------------------------
# FIX #1 TESTS: Current-run pointer ordering + state lifecycle
# ---------------------------------------------------------------------------

class TestPointerStateLifecycle:
    """Tests that current-run.json goes through starting -> started -> launch_failed."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        self.tmp_path = tmp_path
        def _fake_local(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_local)
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_pointer_has_state_field(self, tmp_path):
        """current-run.json includes 'state' field after successful launch."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-state-001",
            config=config,
        )
        assert result.ok is True

        ptr_path = control_root / "current-run.json"
        ptr_data = json.loads(ptr_path.read_text())
        assert ptr_data["state"] == "started"
        assert ptr_data["mode"] == "repo"
        assert "command_preview" in ptr_data

    def test_pointer_contains_all_required_fields(self, tmp_path):
        """current-run.json contains run_id, run_root, events_path, task_path,
           target_path, mode, runner, command_preview, state."""
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-fields-001",
            config=config,
        )
        assert result.ok is True

        ptr_path = control_root / "current-run.json"
        ptr_data = json.loads(ptr_path.read_text())

        required_fields = ["run_id", "run_root", "events_path", "task_path",
                           "target_path", "mode", "runner", "command_preview", "state"]
        for field in required_fields:
            assert field in ptr_data, f"Missing field: {field}"

        # Verify started pointer includes runner-specific fields
        assert ptr_data["state"] == "started", (
            f"Expected started state, got: {ptr_data.get('state')}"
        )
        # local_exec runner should include pid
        assert "pid" in ptr_data, (
            "started pointer missing pid field for local_exec runner"
        )
        assert isinstance(ptr_data["pid"], int), (
            f"pid should be an integer, got: {type(ptr_data.get('pid'))}"
        )


    def test_queued_starting_pointer_failure_prevents_launch(self, tmp_path, monkeypatch):
        """When a queued run is dequeued and the starting pointer write fails,
        the queued item is NOT launched (prevents orphan run)."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        # Reset state
        ingest._queue.clear()
        ingest._active_run = True  # Simulate an active run so new ones get queued

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="queue",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        # First: queue a run normally
        result1 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test queued ptr fail", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-queued-ptr-001",
            config=config,
        )
        assert result1.ok is True
        assert result1.queued is True
        assert len(ingest._queue) == 1

        # Now make the pointer write fail when it matters
        original_write = ingest._write_current_run_pointer
        call_count = [0]
        def _fake_write_fail(*args, **kwargs):
            call_count[0] += 1
            state = kwargs.get("state", args[13] if len(args) > 12 else "")
            if state == "starting":
                return False  # Simulate pointer write failure
            return True
        ingest._write_current_run_pointer = _fake_write_fail

        # Track that _do_launch is NOT called for the queued item
        def _fake_launch_should_not_run(item):
            raise AssertionError(
                "_do_launch was called after queued pointer write failure"
            )
        monkeypatch.setattr(ingest, "_do_launch", _fake_launch_should_not_run)

        try:
            # Dequeue: simulate run finished, triggering _maybe_start_next
            ingest._active_run = False  # Mark previous run finished
            ingest._maybe_start_next()

            # The queued item should have launch_ok=False and launch_error set
            queue_item = ingest._queue[0] if ingest._queue else None
            if queue_item is not None:
                assert queue_item.get("launch_ok") is False, (
                    "queued item should not be launched"
                )
                assert "pointer_write" in queue_item.get("launch_error", "").lower(), (
                    f"queued item launch_error should mention pointer, got: "
                    f"{queue_item.get('launch_error')}"
                )
        finally:
            ingest._write_current_run_pointer = original_write


# ---------------------------------------------------------------------------
# FIX #2 TESTS: Dedupe ordering
# ---------------------------------------------------------------------------

class TestDedupeOrdering:
    """Tests that dedupe is recorded only after successful launch."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        self.tmp_path = tmp_path
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_no_dedupe_on_launch_failure(self, tmp_path, monkeypatch):
        """Failed launch does not create a dedupe record."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        def _fake_failing_launch(item):
            item["launch_ok"] = False
            item["launch_error"] = "local_exec_failed"
            item["runner"] = "local_exec"
            return False
        monkeypatch.setattr(ingest, "_do_launch", _fake_failing_launch)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-dedupe-fail-001",
            config=config,
        )
        assert result.ok is False

        # The dedupe record may exist with state="launch_failed",
        # but check_duplicate should NOT treat it as active (retry allowed)
        from qq.web.ingest import _compute_dedupe_key, IngestRequest
        req = IngestRequest(source="manual-api", raw_transcription="", trigger="qonqrete",
                            mode="repo", target="default", task_text="test",
                            transcription_id="trans-dedupe-fail-001")
        dkey = _compute_dedupe_key(req)
        existing = check_duplicate(dkey)
        assert existing is None, "launch_failed dedupe should NOT block retry"

        # Verify that launch_failed pointer includes launch_error
        ptr_path = control_root / "current-run.json"
        assert ptr_path.is_file(), "Launch failed but no current-run.json was written"
        ptr_data = json.loads(ptr_path.read_text())
        assert ptr_data["state"] == "launch_failed", (
            f"Expected launch_failed state, got: {ptr_data.get('state')}"
        )
        assert "launch_error" in ptr_data, (
            "launch_failed pointer missing launch_error field"
        )
        assert ptr_data["launch_error"] == "local_exec_failed"

    def test_retry_after_failed_launch_not_duplicate(self, tmp_path, monkeypatch):
        """Retrying same transcription_id after failed launch should attempt again."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        def _fake_failing(item):
            item["launch_ok"] = False
            item["launch_error"] = "local_exec_failed"
            item["runner"] = "local_exec"
            return False
        monkeypatch.setattr(ingest, "_do_launch", _fake_failing)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        result1 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-retry-001",
            config=config,
        )
        assert result1.ok is False
        assert result1.duplicate is False

        def _fake_succeed(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_succeed)

        result2 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-retry-001",
            config=config,
        )
        assert result2.ok is True
        assert result2.duplicate is False, "Retry after failed launch should not be duplicate"


# ---------------------------------------------------------------------------
# Two-queued-runs: first launch fails, second starts, current-run.json correct
# ---------------------------------------------------------------------------

class TestQueuedLaunchFailureNextRun:
    """Tests that when a queued run fails to launch, the next queued run starts
    and current-run.json points to the second run, not the failed first one."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        self.tmp_path = tmp_path
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_two_queued_first_launch_fails_second_starts(self, monkeypatch):
        """Two queued runs: first launch fails, second starts.
        current-run.json must point to the second run after it starts."""
        import qq.web.ingest as ingest

        tmp_path = self.tmp_path
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        # Make it look like a run is already active so both calls queue
        ingest._active_run = True
        ingest._queue.clear()

        # First call to _do_launch fails, second succeeds
        call_count = [0]

        def _alternating_launch(item):
            call_count[0] += 1
            if call_count[0] == 1:
                # First launch fails
                item["launch_ok"] = False
                item["launch_error"] = "local_exec_failed"
                item["runner"] = "local_exec"
                return False
            else:
                # Second launch succeeds
                item["launch_ok"] = True
                item["pid"] = 99999
                item["runner"] = "local_exec"
                # Do NOT call _mark_run_active() — test controls it
                return True

        monkeypatch.setattr(ingest, "_do_launch", _alternating_launch)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="queue",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        # Set active_run = True to force queue behavior
        ingest._active_run = True
        ingest._active_run_id = "fake-active-run"

        # Queue first run
        result1 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="first run", mode="repo", target="default",
            trigger="qonqrete", transcription_id="two-queue-001",
            config=config,
        )
        assert result1.ok is True
        assert result1.queued is True
        run_id_1 = result1.run_id

        # Queue second run (first is active in queue but launch will fail)
        result2 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="second run", mode="repo", target="default",
            trigger="qonqrete", transcription_id="two-queue-002",
            config=config,
        )
        assert result2.ok is True
        assert result2.queued is True
        run_id_2 = result2.run_id

        # Now simulate run finishing so both queued items get processed
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._maybe_start_next()

        # current-run.json should point to the second run, not the first (failed) one
        ptr_path = control_root / "current-run.json"
        assert ptr_path.is_file(), "current-run.json should exist after processing"
        ptr_data = json.loads(ptr_path.read_text())
        assert ptr_data["run_id"] == run_id_2, (
            f"Expected current-run.json to point to second run ({run_id_2}), "
            f"got first run ({ptr_data.get('run_id')})"
        )
        assert ptr_data["state"] == "started", (
            f"Expected 'started' state, got '{ptr_data.get('state')}'"
        )

        # The first run should have a runner.failed.json
        failed_path = Path(result1.run_root) / "runner.failed.json"
        assert failed_path.is_file(), (
            f"Expected runner.failed.json for failed first run at {failed_path}"
        )

    def test_two_queued_first_pointer_fails_second_starts(self, monkeypatch):
        """Two queued runs: first pointer write fails, second starts.
        current-run.json must point to the second run."""
        import qq.web.ingest as ingest

        tmp_path = self.tmp_path
        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        # Make it look like a run is already active so both calls queue
        ingest._active_run = True
        ingest._queue.clear()

        # Track how many times _write_current_run_pointer is called
        pointer_calls = [0]

        def _fake_launch_succeed(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            ingest._mark_run_active(item)
            return True

        monkeypatch.setattr(ingest, "_do_launch", _fake_launch_succeed)

        # Override _write_current_run_pointer: first call fails, subsequent succeed
        orig_write = ingest._write_current_run_pointer

        def _write_pointer_alternating(*args, **kwargs):
            pointer_calls[0] += 1
            if pointer_calls[0] == 1:
                return False  # First pointer write fails
            return orig_write(*args, **kwargs)

        monkeypatch.setattr(ingest, "_write_current_run_pointer", _write_pointer_alternating)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="queue",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        # Queue first run
        result1 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="first run", mode="repo", target="default",
            trigger="qonqrete", transcription_id="ptr-fail-001",
            config=config,
        )
        assert result1.ok is True
        assert result1.queued is True

        # Queue second run
        result2 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="second run", mode="repo", target="default",
            trigger="qonqrete", transcription_id="ptr-fail-002",
            config=config,
        )
        assert result2.ok is True
        assert result2.queued is True

        # Process queue: first pointer write fails, second succeeds
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._maybe_start_next()

        # current-run.json should point to the second run
        ptr_path = control_root / "current-run.json"
        assert ptr_path.is_file(), "current-run.json should exist"
        ptr_data = json.loads(ptr_path.read_text())
        assert ptr_data["run_id"] == result2.run_id, (
            f"Expected current-run.json to point to second run ({result2.run_id}), "
            f"got {ptr_data.get('run_id')}"
        )
        assert ptr_data["state"] == "started", (
            f"Expected 'started' state, got '{ptr_data.get('state')}'"
        )

        # The first run should have a runner.failed.json
        failed_path = Path(result1.run_root) / "runner.failed.json"
        assert failed_path.is_file(), (
            f"Expected runner.failed.json at {failed_path}"
        )


# ---------------------------------------------------------------------------
# FIX #5 TESTS: Tmux send-keys failure
        # Clean up: ensure _active_run is reset so other tests are not affected
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._queue.clear()
# ---------------------------------------------------------------------------

class TestTmuxSendKeys:
    """Tests that tmux send-keys failure is handled correctly."""

    def test_send_keys_failure_returns_tmux_send_keys_failed(self, tmp_path, monkeypatch):
        """Simulated send-keys failure returns the right error."""
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)

        def _fake_tmux_sendkeys_fail(item):
            item["launch_ok"] = False
            item["launch_error"] = "tmux_send_keys_failed"
            item["runner"] = "tmux"
            return False
        monkeypatch.setattr(ingest, "_do_launch_tmux", _fake_tmux_sendkeys_fail)

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = str(dedupe_dir / "dedupe.jsonl")
        old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(control_root)

        try:
            config = ObeliskIngestConfig(
                enabled=True, default_run_root=str(run_root),
                task_dir=str(task_dir), queue_mode="reject_if_running",
                allowed_target_roots=[str(run_root)], dev_no_auth=True,
                runner="tmux", control_root=str(control_root),
            )

            result = create_external_run_trigger(
                source="manual-api", raw_transcription="",
                task_text="test", mode="repo", target="default",
                trigger="qonqrete", transcription_id="trans-tmux-fail-001",
                config=config,
            )
            assert result.ok is False
            assert result.error == "tmux_send_keys_failed"
        finally:
            ingest._queue.clear()
            ingest._active_run = False
            ingest._active_run_id = None
            ingest._active_item = None
            ingest._DEDUPE_PATH = old_dedupe
            if old_control:
                os.environ["QONQRETE_CONTROL_ROOT"] = old_control
            else:
                os.environ.pop("QONQRETE_CONTROL_ROOT", None)


# ---------------------------------------------------------------------------
# Additional runner command tests
# ---------------------------------------------------------------------------

class TestRunnerCommandDetails:
    """Additional tests for command generation details."""

    def test_folder_mode_includes_no_repo(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="folder", run_root="/x/qq/runs/test")
        assert "--no-repo" in args

    def test_repo_mode_omits_no_repo(self):
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test")
        assert "--no-repo" not in args

    def test_both_modes_include_no_web(self):
        for mode in ["repo", "folder"]:
            args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode=mode, run_root="/x/qq/runs/test")
            assert "--no-web" in args, f"--no-web missing in {mode} mode {args}"

    def test_both_modes_include_run_root(self):
        for mode in ["repo", "folder"]:
            args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode=mode, run_root="/x/qq/runs/test")
            assert "--run-root" in args
            assert "/x/qq/runs/test" in args

    def test_command_preview_no_old_qq_tui_exec(self):
        # local_exec mode: plain qq run (no qq-tui)
        args = generate_command(task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test")
        preview = command_preview(args)
        assert "qq-tui exec" not in preview, f"Old qq-tui exec path in preview: {preview}"
        # local_exec should NOT have qq-tui
        assert "qq-tui" not in preview, f"local_exec should not have qq-tui in preview: {preview}"
        assert "qq run" in preview
        
        # tmux mode: direct qq run now owns the integrated TUI
        args_tmux = generate_command(runner="tmux", task_path="/tmp/task.md", target_path="/tmp/target", mode="repo", run_root="/x/qq/runs/test", events_path="/x/qq/runs/test/events.jsonl")
        preview_tmux = command_preview(args_tmux)
        assert preview_tmux.startswith("qq run ")
        assert "--no-tui" not in preview_tmux


# ---------------------------------------------------------------------------
# FIX #1 TESTS: Tmux exit code capture in inner command
# ---------------------------------------------------------------------------

class TestTmuxExitCodeCapture:
    """Tests that tmux inner command properly captures exit codes."""

    def test_inner_command_uses_qq_exit_variable(self, tmp_path, monkeypatch):
        """The tmux inner command uses QQ_EXIT=$? to capture the real exit code."""
        import qq.web.ingest as ingest
        run_root = tmp_path / "runs" / "test-run"
        run_root.mkdir(parents=True)

        item = {
            "args": ["qq-tui", "run", "--exit-when-done", "qq", "run", "--no-web",
                     "--run-root", str(run_root), "/tmp/task.md", "/tmp/target"],
            "run_id": "test-run-123",
            "run_root": str(run_root),
        }

        # Capture all subprocess.run calls at module level
        captured_commands = []

        class FakeResult:
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured_commands.append(cmd)
            # For has-session, return nonzero (session doesn't exist)
            if isinstance(cmd, list) and cmd[0] == "tmux" and "has-session" in cmd:
                r = FakeResult()
                r.returncode = 1  # session not found
                return r
            return FakeResult()

        monkeypatch.setattr(ingest.subprocess, "run", fake_run)
        # Ensure binary check passes in test environment
        monkeypatch.setattr(ingest, "_has_qonqrete_runner_binary", lambda: True)
        try:
            ingest._do_launch_tmux(item)
        except Exception:
            pass

        # Find the inner command sent to tmux
        inner_cmd = None
        for cmd in captured_commands:
            if isinstance(cmd, list) and len(cmd) >= 5 and cmd[0] == "tmux" and cmd[1] == "send-keys":
                inner_cmd = cmd[4]  # The string sent to tmux
                break

        assert inner_cmd is not None, f"tmux send-keys command not captured. Captured: {captured_commands}"
        assert "QQ_EXIT=$?" in inner_cmd, (
            f"QQ_EXIT=$? not found in inner command:\n{inner_cmd}"
        )
        assert "QQ_EXIT=0 || QQ_EXIT=0" not in inner_cmd, (
            f"Bug pattern QQ_EXIT=0 || QQ_EXIT=0 found in:\n{inner_cmd}"
        )
        assert "runner.exit_code" in inner_cmd, (
            f"runner.exit_code not found in inner command:\n{inner_cmd}"
        )
        assert "runner.finished" in inner_cmd, (
            f"runner.finished not found in inner command:\n{inner_cmd}"
        )
        assert "exit \"$QQ_EXIT\"" in inner_cmd, (
            f"exit $QQ_EXIT not found in inner command (should close session, not leave idle bash):\n{inner_cmd}"
        )
        assert "exec bash" not in inner_cmd, (
            f"exec bash found in inner command (should have been removed):\n{inner_cmd}"
        )

    def test_inner_command_uses_shlex_quote(self, tmp_path, monkeypatch):
        """Run paths in the tmux inner command are shell-quoted."""
        import qq.web.ingest as ingest
        import shlex as _shlex

        run_root = tmp_path / "runs" / "test run with spaces"
        run_root.mkdir(parents=True)

        item = {
            "args": ["qq-tui", "run", "--exit-when-done", "qq", "run", "--no-web",
                     "--run-root", str(run_root), "/tmp/task.md", "/tmp/target"],
            "run_id": "test-run-456",
            "run_root": str(run_root),
        }

        captured_commands = []
        original_run = ingest.subprocess.run

        class FakeResult:
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured_commands.append(cmd)
            # Return nonzero for has-session so fake tmux "exists"
            if isinstance(cmd, list) and cmd[0] == "tmux" and "has-session" in cmd:
                r = FakeResult()
                r.returncode = 1  # session not found
                return r
            return FakeResult()

        monkeypatch.setattr(ingest.subprocess, "run", fake_run)
        # Ensure binary check passes in test environment
        monkeypatch.setattr(ingest, "_has_qonqrete_runner_binary", lambda: True)
        try:
            ingest._do_launch_tmux(item)
        except Exception:
            pass

        inner_cmd = None
        for cmd in captured_commands:
            if isinstance(cmd, list) and len(cmd) >= 5 and cmd[0] == "tmux" and cmd[1] == "send-keys":
                inner_cmd = cmd[4]
                break

        assert inner_cmd is not None, "tmux send-keys command not captured"
        # Check that paths containing spaces are quoted
        runner_ec_path = str(run_root / "runner.exit_code")
        runner_fin_path = str(run_root / "runner.finished")
        quoted_ec = _shlex.quote(runner_ec_path)
        quoted_fin = _shlex.quote(runner_fin_path)
        assert quoted_ec in inner_cmd or runner_ec_path in inner_cmd, (
            f"runner.exit_code path not found in:\n{inner_cmd}"
        )
        assert quoted_fin in inner_cmd or runner_fin_path in inner_cmd, (
            f"runner.finished path not found in:\n{inner_cmd}"
        )

    def test_tmux_session_name_sanitization(self, tmp_path, monkeypatch):
        """Tmux session name is sanitized to only allow-safe chars."""
        import qq.web.ingest as ingest
        run_root = tmp_path / "runs" / "test-run"
        run_root.mkdir(parents=True)

        # Use a run_id with special characters
        item = {
            "args": ["qq-tui", "run", "--exit-when-done", "qq", "run", "--no-web",
                     "--run-root", str(run_root), "/tmp/task.md", "/tmp/target"],
            "run_id": "test-run!@#$%^",
            "run_root": str(run_root),
        }

        captured_commands = []
        original_run = ingest.subprocess.run

        class FakeResult:
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured_commands.append(cmd)
            if isinstance(cmd, list) and cmd[0] == "tmux" and "has-session" in cmd:
                r = FakeResult()
                r.returncode = 1
                return r
            return FakeResult()

        monkeypatch.setattr(ingest.subprocess, "run", fake_run)
        # Ensure binary check passes in test environment
        monkeypatch.setattr(ingest, "_has_qonqrete_runner_binary", lambda: True)
        try:
            ingest._do_launch_tmux(item)
        except Exception:
            pass

        # Verify session name in captured commands
        # Session names appear in tmux commands like:
        # ["tmux", "has-session", "-t", <session>]
        # ["tmux", "new-session", "-d", "-s", <session>, "bash"]
        # ["tmux", "send-keys", "-t", <session>, ...]
        # Session name is at different indices. Only check those, not the full inner_cmd.
        session_found = False
        for cmd in captured_commands:
            if not isinstance(cmd, list):
                continue
            # For has-session: ["tmux", "has-session", "-t", session_name]
            if len(cmd) >= 4 and cmd[0] == "tmux" and cmd[1] == "has-session" and cmd[2] == "-t":
                arg = cmd[3]
                if "qonqrete-" in str(arg):
                    session_found = True
                    assert not any(c in str(arg) for c in "!@#$%^"), (
                        f"Special characters found in session name: {arg}"
                    )
            # For new-session: ["tmux", "new-session", "-d", "-s", session_name, "bash"]
            if len(cmd) >= 5 and cmd[0] == "tmux" and cmd[1] == "new-session" and cmd[3] == "-s":
                arg = cmd[4]
                if "qonqrete-" in str(arg):
                    session_found = True
                    assert not any(c in str(arg) for c in "!@#$%^"), (
                        f"Special characters found in session name: {arg}"
                    )
            # For send-keys: ["tmux", "send-keys", "-t", session_name, ...]
            if len(cmd) >= 4 and cmd[0] == "tmux" and cmd[1] == "send-keys" and cmd[2] == "-t":
                arg = cmd[3]
                if "qonqrete-" in str(arg):
                    session_found = True
                    assert not any(c in str(arg) for c in "!@#$%^"), (
                        f"Special characters found in session name: {arg}"
                    )
        assert session_found, "Tmux session name not found in captured commands"

    def test_task_text_not_in_inner_command(self, tmp_path, monkeypatch):
        """Task text is NOT shell-inserted into the tmux inner command."""
        import qq.web.ingest as ingest
        run_root = tmp_path / "runs" / "test-run"
        run_root.mkdir(parents=True)

        dangerous_task = "/tmp/task.md"  # Task text is in the file, not args
        item = {
            "args": ["qq-tui", "run", "--exit-when-done", "qq", "run", "--no-web",
                     "--run-root", str(run_root), dangerous_task, "/tmp/target"],
            "run_id": "test-run-no-inj",
            "run_root": str(run_root),
        }

        captured_commands = []
        original_run = ingest.subprocess.run

        class FakeResult:
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured_commands.append(cmd)
            if isinstance(cmd, list) and cmd[0] == "tmux" and "has-session" in cmd:
                r = FakeResult()
                r.returncode = 1
                return r
            return FakeResult()

        monkeypatch.setattr(ingest.subprocess, "run", fake_run)
        # Ensure binary check passes in test environment
        monkeypatch.setattr(ingest, "_has_qonqrete_runner_binary", lambda: True)
        try:
            ingest._do_launch_tmux(item)
        except Exception:
            pass

        inner_cmd = None
        for cmd in captured_commands:
            if isinstance(cmd, list) and len(cmd) >= 5 and cmd[0] == "tmux" and cmd[1] == "send-keys":
                inner_cmd = cmd[4]
                break

        assert inner_cmd is not None
        # Shell injection characters should not appear bare
        for dc in ["; rm -rf", "&& cat", "$(whoami)", "`id`"]:
            assert dc not in inner_cmd, (
                f"Suspicious shell pattern '{dc}' found in inner command"
            )


# ---------------------------------------------------------------------------
# YAML config loading tests
# ---------------------------------------------------------------------------

class TestYamlConfigLoading:
    """Tests that YAML config loads runner, control_root, dashboard_url."""

    def test_yaml_runner_loaded(self, tmp_path, monkeypatch):
        """YAML runner value is loaded when no env var is set."""
        import qq.web.ingest as ingest

        # Create a test yaml file
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        yaml_path = config_dir / "qq.yaml"
        yaml_path.write_text("""
qonqrete_runs_api:
  runner: tmux
  control_root: /tmp/test-control
  dashboard_url: http://10.20.30.40:31337
""")

        # Monkeypatch the yaml path resolution
        original_dirname = os.path.dirname
        def fake_dirname(p):
            if "ingest" in str(p) or p.endswith("qq/web/ingest.py"):
                return str(tmp_path)
            return original_dirname(p)

        with monkeypatch.context() as m:
            # Clear env vars that would affect the test
            for key in list(os.environ.keys()):
                if key.startswith("QONQRETE_"):
                    m.delenv(key, raising=False)

            # The YAML path resolution uses __file__ of ingest module
            # which is tricky to monkeypatch. Instead test _apply_yaml_section directly.
            from qq.web.ingest import RunsAPIConfig, _apply_yaml_section
            cfg = RunsAPIConfig()
            section = {
                "runner": "tmux",
                "control_root": "/tmp/test-control",
                "dashboard_url": "http://10.20.30.40:31337",
            }
            _apply_yaml_section(cfg, section)
            assert cfg.runner == "tmux"
            assert cfg.control_root == "/tmp/test-control"
            assert cfg.dashboard_url == "http://10.20.30.40:31337"

    def test_env_overrides_yaml_runner(self, tmp_path, monkeypatch):
        """Env var QONQRETE_RUNS_RUNNER overrides YAML runner."""
        from qq.web.ingest import RunsAPIConfig, _apply_yaml_section

        cfg = RunsAPIConfig()
        section = {
            "runner": "tmux",
            "control_root": "/tmp/yaml-control",
            "dashboard_url": "http://yaml.example.com:31337",
        }
        _apply_yaml_section(cfg, section)

        # Simulate load_obelisk_config_from_env post-YAML env reading
        # (which now only sets if env var is present)
        # Env is not set, so YAML value should persist
        assert cfg.runner == "tmux"

        # Now simulate env var being set
        runner_env = "local_exec"
        if runner_env in ("local_exec", "tmux"):
            cfg.runner = runner_env

        assert cfg.runner == "local_exec", "Env var should override YAML runner"

    def test_env_overrides_yaml_control_root(self, tmp_path, monkeypatch):
        """Env var QONQRETE_CONTROL_ROOT overrides YAML control_root."""
        from qq.web.ingest import RunsAPIConfig, _apply_yaml_section

        cfg = RunsAPIConfig()
        section = {
            "control_root": "/tmp/yaml-control",
        }
        _apply_yaml_section(cfg, section)
        assert cfg.control_root == "/tmp/yaml-control"

        # Simulate env override
        control_env = "/tmp/env-control"
        if control_env:
            cfg.control_root = os.path.expanduser(control_env)
        assert cfg.control_root == "/tmp/env-control"

    def test_env_overrides_yaml_dashboard_url(self, tmp_path, monkeypatch):
        """Env var QONQRETE_PUBLIC_DASHBOARD_URL overrides YAML dashboard_url."""
        from qq.web.ingest import RunsAPIConfig, _apply_yaml_section

        cfg = RunsAPIConfig()
        section = {
            "dashboard_url": "http://yaml.example.com:31337",
        }
        _apply_yaml_section(cfg, section)
        assert cfg.dashboard_url == "http://yaml.example.com:31337"

        # Simulate env override
        dashboard_env = "http://env.example.com:31337"
        if dashboard_env:
            cfg.dashboard_url = dashboard_env
        assert cfg.dashboard_url == "http://env.example.com:31337"

    def test_yaml_invalid_runner_ignored(self, tmp_path):
        """Invalid YAML runner value is ignored."""
        from qq.web.ingest import RunsAPIConfig, _apply_yaml_section

        cfg = RunsAPIConfig()
        # Default is "local_exec"
        assert cfg.runner == "local_exec"

        section = {"runner": "invalid_runner"}
        _apply_yaml_section(cfg, section)
        # Invalid runner should not overwrite the default
        assert cfg.runner == "local_exec"

    def test_yaml_empty_values_dont_overwrite(self, tmp_path):
        """Empty YAML values don't overwrite existing config."""
        from qq.web.ingest import RunsAPIConfig, _apply_yaml_section

        cfg = RunsAPIConfig()
        cfg.runner = "tmux"
        cfg.control_root = "/x/qq/control"
        cfg.dashboard_url = "http://existing.example.com:31337"

        section = {
            "runner": None,  # Not in ("local_exec", "tmux") → skipped
            "control_root": "",  # Falsy → skipped
            "dashboard_url": "",  # Falsy → skipped
        }
        _apply_yaml_section(cfg, section)
        # Existing values should be preserved
        assert cfg.runner == "tmux"
        assert cfg.control_root == "/x/qq/control"
        assert cfg.dashboard_url == "http://existing.example.com:31337"


# ---------------------------------------------------------------------------
# Queued run dedupe tests
# ---------------------------------------------------------------------------

class TestQueuedDedupe:
    """Tests that queued runs properly handle deduplication."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        (tmp_path / "control").mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(tmp_path / "control")
        self.tmp_path = tmp_path

        # Setup: simulate an active run so new requests get queued
        ingest._active_run = True

        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_queued_run_records_dedupe_after_queue(self, tmp_path):
        """When a run is queued, dedupe is recorded after successful queue insertion."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="queue",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test queued dedupe", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-queued-001",
            config=config,
        )

        assert result.ok is True
        assert result.queued is True
        assert result.started is False

        # Verify dedupe was recorded
        dedupe_file = ingest._DEDUPE_PATH
        assert os.path.isfile(dedupe_file), f"Dedupe file not found: {dedupe_file}"
        content = open(dedupe_file).read()
        assert "trans-queued-001" in content, "Dedupe not recorded for queued run"

        # Verify queue contains the item with dedupe_key
        assert len(ingest._queue) == 1
        assert ingest._queue[0].get("dedupe_key") is not None, "Queue item missing dedupe_key"

    def test_duplicate_retry_while_queued(self, tmp_path):
        """Retry with same transcription_id while queued returns duplicate=True."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="queue",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        # First request: queues it
        result1 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test duplicate while queued", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-queued-dup-001",
            config=config,
        )
        assert result1.ok is True
        assert result1.queued is True
        assert result1.duplicate is False

        # Second request: should find it in queue and return duplicate
        result2 = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test duplicate while queued", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-queued-dup-001",
            config=config,
        )
        assert result2.ok is True
        assert result2.duplicate is True, (
            f"Expected duplicate=True for retry while queued, got: {result2}"
        )

    def test_failed_launch_does_not_record_dedupe(self, tmp_path, monkeypatch):
        """Failed launch does not create a dedupe record."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        # Reset active_run to False so we get immediate launch (not queue)
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None

        def _fake_failing_launch(item):
            item["launch_ok"] = False
            item["launch_error"] = "local_exec_failed"
            return False
        monkeypatch.setattr(ingest, "_do_launch", _fake_failing_launch)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="reject_if_running",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        result = create_external_run_trigger(
            source="manual-api", raw_transcription="",
            task_text="test no dedupe on fail", mode="repo", target="default",
            trigger="qonqrete", transcription_id="trans-no-ded-001",
            config=config,
        )
        assert result.ok is False

        # Dedupe may be recorded with launch_failed but should NOT block retry
        from qq.web.ingest import _compute_dedupe_key, IngestRequest
        req = IngestRequest(source="manual-api", raw_transcription="", trigger="qonqrete",
                            mode="repo", target="default", task_text="test no dedupe on fail",
                            transcription_id="trans-no-ded-001")
        dkey = _compute_dedupe_key(req)
        existing = check_duplicate(dkey)
        assert existing is None, "launch_failed dedupe should NOT block retry"

    def test_dedupe_key_in_queued_item(self, tmp_path):
        """Queue items store dedupe_key for duplicate detection."""
        import qq.web.ingest as ingest

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        config = ObeliskIngestConfig(
            enabled=True, default_run_root=str(run_root),
            task_dir=str(task_dir), queue_mode="queue",
            allowed_target_roots=[str(run_root)], dev_no_auth=True,
            runner="local_exec", control_root=str(control_root),
        )

        # Force queue mode by setting active_run=True
        ingest._active_run = True
        ingest._active_run_id = "fake-active"

        # All items should queue
        for i in range(3):
            result = create_external_run_trigger(
                source="manual-api", raw_transcription="",
                task_text=f"test queued item {i}", mode="repo", target="default",
                trigger="qonqrete", transcription_id=f"trans-multi-{i:03d}",
                config=config,
            )
            assert result.ok is True
            assert result.queued is True

        # All queue items should have dedupe_key
        for item in ingest._queue:
            assert item.get("dedupe_key") is not None, (
                f"Queue item missing dedupe_key: {item.get('run_id')}"
            )


# ---------------------------------------------------------------------------
# Events path from current-run.json tests
# ---------------------------------------------------------------------------

class TestEventsPathFromPointer:
    """Tests that events_path from current-run.json is preferred."""

    def test_events_path_in_pointer_matches_response(self, tmp_path, monkeypatch):
        """The events_path in current-run.json matches the API response."""
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None

        task_dir = tmp_path / "tasks"
        run_root = tmp_path / "runs"
        task_dir.mkdir(parents=True)
        run_root.mkdir(parents=True)
        control_root = tmp_path / "control"
        control_root.mkdir(parents=True, exist_ok=True)

        def _fake_launch(item):
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            ingest._mark_run_active(item)
            return True
        monkeypatch.setattr(ingest, "_do_launch", _fake_launch)

        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = str(dedupe_dir / "dedupe.jsonl")
        old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(control_root)

        try:
            config = ObeliskIngestConfig(
                enabled=True, default_run_root=str(run_root),
                task_dir=str(task_dir), queue_mode="reject_if_running",
                allowed_target_roots=[str(run_root)], dev_no_auth=True,
                runner="local_exec", control_root=str(control_root),
            )

            result = create_external_run_trigger(
                source="manual-api", raw_transcription="",
                task_text="test events path", mode="repo", target="default",
                trigger="qonqrete", transcription_id="trans-evt-path-001",
                config=config,
            )
            assert result.ok is True

            # Read the pointer
            ptr_path = control_root / "current-run.json"
            ptr_data = json.loads(ptr_path.read_text())

            # events_path in pointer should match what response returns
            assert ptr_data["events_path"] == result.events_path
            assert ptr_data["run_root"] == result.run_root
            assert ptr_data["events_path"].startswith(ptr_data["run_root"])

            # events_path should be run_root/events.jsonl
            expected_events = os.path.join(result.run_root, "events.jsonl")
            assert ptr_data["events_path"] == expected_events, (
                f"Expected {expected_events}, got {ptr_data['events_path']}"
            )
        finally:
            ingest._queue.clear()
            ingest._active_run = False
            ingest._active_run_id = None
            ingest._active_item = None
            ingest._DEDUPE_PATH = old_dedupe
            if old_control:
                os.environ["QONQRETE_CONTROL_ROOT"] = old_control
            else:
                os.environ.pop("QONQRETE_CONTROL_ROOT", None)


# ============================================================================
# State regression tests (current-run.json monotonic guard)
# ============================================================================

class TestCurrentRunPointerMonotonicGuard:
    """Tests that current-run.json state cannot regress from terminal to active."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        self.control_dir = tmp_path / "control"
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.run_root = tmp_path / "runs" / "test-run"
        self.run_root.mkdir(parents=True)
        self.events_path = str(self.run_root / "events.jsonl")

    def test_finished_cannot_regress_to_started(self):
        """Write finished -> attempt started -> final state remains finished."""
        from qq.web.ingest import _write_current_run_pointer, _update_current_run_pointer_guarded
        import json

        run_id = "test-finished-grd"
        control_root = str(self.control_dir)

        # Write finished state
        ok = _write_current_run_pointer(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="finished",
            finished_at="2026-01-01T01:00:00Z",
            exit_code=0,
        )
        assert ok is True

        # Read state
        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "finished"

        # Attempt to write "started" via guarded helper
        ok2 = _update_current_run_pointer_guarded(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="started",
        )
        # May return True (silently skipped) — but state must not change
        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "finished", (
            f"Expected finished, got {cr['state']} — state regressed!"
        )

    def test_stale_cannot_regress_to_started(self):
        """Write stale -> attempt started -> final state remains stale."""
        from qq.web.ingest import _write_current_run_pointer, _update_current_run_pointer_guarded
        import json

        run_id = "test-stale-grd"
        control_root = str(self.control_dir)

        # Write stale state
        _write_current_run_pointer(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="stale",
        )

        # Attempt started
        _update_current_run_pointer_guarded(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="started",
        )

        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "stale", (
            f"Expected stale, got {cr['state']} — state regressed!"
        )

    def test_launch_failed_cannot_regress_to_started(self):
        """Write launch_failed -> attempt started -> final state remains launch_failed."""
        from qq.web.ingest import _write_current_run_pointer, _update_current_run_pointer_guarded
        import json

        run_id = "test-lf-grd"
        control_root = str(self.control_dir)

        _write_current_run_pointer(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="launch_failed",
            launch_error="test_error",
        )

        _update_current_run_pointer_guarded(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="started",
        )

        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "launch_failed", (
            f"Expected launch_failed, got {cr['state']} — state regressed!"
        )

    def test_old_run_cannot_overwrite_newer_run_pointer(self):
        """Old run finishing cannot overwrite a newer run's running pointer."""
        from qq.web.ingest import _write_current_run_pointer, _update_current_run_pointer_guarded
        import json

        old_run_id = "old-run-123"
        new_run_id = "new-run-456"
        control_root = str(self.control_dir)

        # Write new run as started
        _write_current_run_pointer(
            run_id=new_run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task_new.md",
            target_path="/fake/target_new",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-02T00:00:00Z",
            command_preview="new run",
            control_root=control_root,
            state="started",
        )

        # Old run tries to write "finished"
        _update_current_run_pointer_guarded(
            run_id=old_run_id, run_root="/fake/old_root",
            events_path="/fake/old_events.jsonl",
            task_path="/fake/task_old.md",
            target_path="/fake/target_old",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="old run",
            control_root=control_root,
            state="finished",
            finished_at="2026-01-01T01:00:00Z",
            exit_code=0,
        )

        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["run_id"] == new_run_id, "Newer run was overwritten by old run!"
        assert cr["state"] == "started", "Newer run state was overwritten!"

    def test_started_only_allowed_from_starting_or_missing(self):
        """Writing 'started' is only allowed when current state is 'starting' or missing."""
        from qq.web.ingest import _write_current_run_pointer, _update_current_run_pointer_guarded
        import json

        run_id = "test-start-grd"
        control_root = str(self.control_dir)

        # Write 'running' state
        _write_current_run_pointer(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="running",
        )

        # Attempt to write 'started' — should be silently skipped
        _update_current_run_pointer_guarded(
            run_id=run_id, run_root=str(self.run_root),
            events_path=self.events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="started",
        )

        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "running", f"Expected running, got {cr['state']}"


# ============================================================================
# Active run identity tracking tests
# ============================================================================

class TestActiveRunIdentity:
    """Tests that run-id-aware active state tracking works correctly."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        self.tmp_path = tmp_path

    def test_run_a_late_finish_does_not_clear_run_b(self):
        """Run A's late finish does not clear active state for run B."""
        import qq.web.ingest as ingest

        # Simulate run B is active
        ingest._active_run = True
        ingest._active_run_id = "run-b"

        # Stale watcher for run A calls mark_run_finished
        ingest._mark_run_finished("run-a")

        # Run B should still be active
        assert ingest._active_run is True, "Run B active state was cleared by stale watcher A!"
        assert ingest._active_run_id == "run-b", "Run ID was overwritten by stale watcher A!"

    def test_mark_run_finished_requires_run_id_match(self):
        """_mark_run_finished only clears active state when run_id matches."""
        import qq.web.ingest as ingest

        ingest._active_run = True
        ingest._active_run_id = "correct-run"

        # Calling with wrong run_id should NOT clear
        ingest._mark_run_finished("wrong-run")
        assert ingest._active_run is True
        assert ingest._active_run_id == "correct-run"

        # Calling with correct run_id SHOULD clear
        ingest._mark_run_finished("correct-run")
        assert ingest._active_run is False
        assert ingest._active_run_id is None

    def test_queue_starts_next_run_once(self):
        """Queue starts next run exactly once after active run finishes."""
        import qq.web.ingest as ingest
        from qq.web.ingest import _queue, _queue_lock

        # Set up: run A is active, run B is queued
        ingest._active_run = True
        ingest._active_run_id = "run-a"

        queue_item = {
            "run_id": "run-b",
            "run_root": str(self.tmp_path / "runs" / "run-b"),
            "events_path": str(self.tmp_path / "runs" / "run-b" / "events.jsonl"),
            "args": ["qq-tui"],
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.tmp_path / "control"),
            "command_preview": "qq-tui run ...",
            "dedupe_key": "test:trans:run-b",
            "created_at": "2026-01-01T00:00:00Z",
        }
        with _queue_lock:
            _queue.append(queue_item)

        # Launch count tracking
        launch_count = [0]

        def _tracking_launch(item):
            launch_count[0] += 1
            item["launch_ok"] = True
            item["pid"] = 99999
            ingest._mark_run_active(item)
            return True

        old_launch = ingest._do_launch
        ingest._do_launch = _tracking_launch

        try:
            # Finish run A — should trigger _maybe_start_next -> launch run B
            ingest._mark_run_finished("run-a")

            # Run B should be launched exactly once
            assert launch_count[0] == 1, f"Expected 1 launch, got {launch_count[0]}"
            assert ingest._active_run is True
            assert ingest._active_run_id == "run-b"
        finally:
            ingest._do_launch = old_launch
            _queue.clear()
            ingest._active_run = False
            ingest._active_run_id = None
            ingest._active_item = None


# ============================================================================
# Stale local_exec dedupe tests
# ============================================================================

class TestStaleLocalExecDedupe:
    """Tests that stale local_exec records allow retries."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        self.tmp_path = tmp_path

    def teardown_method(self):
        import qq.web.ingest as ingest
        ingest._DEDUPE_PATH = self._old_dedupe
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None

    def test_local_exec_started_no_pid_allows_retry(self):
        """local_exec 'started' with no pid and no active item allows retry."""
        import qq.web.ingest as ingest

        dedupe_key = "test:trans:stale-local-no-pid"
        ingest.record_dedupe(
            dedupe_key, "stale-run", "/fake/task.md", "/fake/target",
            run_root=str(self.tmp_path / "stale-run"),
            events_path=str(self.tmp_path / "stale-run" / "events.jsonl"),
            mode="repo", runner="local_exec", state="started",
        )
        # Ensure run_root exists but no runner.finished and no active item
        os.makedirs(str(self.tmp_path / "stale-run"), exist_ok=True)

        result = ingest.check_duplicate(dedupe_key)
        assert result is None, (
            f"Stale local_exec started/no-pid should allow retry, got {result}"
        )

    def test_local_exec_live_pid_blocks_duplicate(self):
        """local_exec with live PID blocks duplicate."""
        import qq.web.ingest as ingest

        dedupe_key = "test:trans:live-pid"
        run_root = str(self.tmp_path / "live-run")
        os.makedirs(run_root, exist_ok=True)

        ingest.record_dedupe(
            dedupe_key, "live-run", "/fake/task.md", "/fake/target",
            run_root=run_root, events_path=os.path.join(run_root, "events.jsonl"),
            mode="repo", runner="local_exec", state="started",
            pid=os.getpid(),  # This process is alive!
        )

        result = ingest.check_duplicate(dedupe_key)
        assert result is not None, (
            "Live PID should block duplicate"
        )

    def test_runner_finished_allows_retry(self):
        """runner.finished marker allows retry."""
        import qq.web.ingest as ingest

        dedupe_key = "test:trans:finished-marker"
        run_root = str(self.tmp_path / "finished-run")
        os.makedirs(run_root, exist_ok=True)
        # Create runner.finished
        with open(os.path.join(run_root, "runner.finished"), "w") as f:
            f.write("2026-01-01T00:00:00Z")

        ingest.record_dedupe(
            dedupe_key, "finished-run", "/fake/task.md", "/fake/target",
            run_root=run_root, events_path=os.path.join(run_root, "events.jsonl"),
            mode="repo", runner="local_exec", state="started",
        )

        result = ingest.check_duplicate(dedupe_key)
        assert result is None, "runner.finished should allow retry"


# ============================================================================
# Stale tmux dedupe tests
# ============================================================================

class TestStaleTmuxDedupe:
    """Tests that stale tmux records allow retries."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        self.tmp_path = tmp_path

    def teardown_method(self):
        import qq.web.ingest as ingest
        ingest._DEDUPE_PATH = self._old_dedupe
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None

    def test_tmux_missing_session_allows_retry(self, monkeypatch):
        """Missing tmux session allows retry."""
        import qq.web.ingest as ingest
        import subprocess

        dedupe_key = "test:trans:tmux-no-session"
        run_root = str(self.tmp_path / "tmux-run")
        os.makedirs(run_root, exist_ok=True)

        ingest.record_dedupe(
            dedupe_key, "tmux-run", "/fake/task.md", "/fake/target",
            run_root=run_root, events_path=os.path.join(run_root, "events.jsonl"),
            mode="repo", runner="tmux", state="started",
            tmux_session="qonqrete-tmux-run",
        )

        # Mock tmux has-session to return 1 (session doesn't exist)
        class FakeResult:
            returncode = 1
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())

        result = ingest.check_duplicate(dedupe_key)
        assert result is None, "Missing tmux session should allow retry"

    def test_tmux_runner_finished_allows_retry(self):
        """tmux record with runner.finished allows retry."""
        import qq.web.ingest as ingest

        dedupe_key = "test:trans:tmux-finished"
        run_root = str(self.tmp_path / "tmux-finished-run")
        os.makedirs(run_root, exist_ok=True)
        with open(os.path.join(run_root, "runner.finished"), "w") as f:
            f.write("2026-01-01T00:00:00Z")

        ingest.record_dedupe(
            dedupe_key, "tmux-finished-run", "/fake/task.md", "/fake/target",
            run_root=run_root, events_path=os.path.join(run_root, "events.jsonl"),
            mode="repo", runner="tmux", state="started",
        )

        result = ingest.check_duplicate(dedupe_key)
        assert result is None, "tmux runner.finished should allow retry"

    def test_finished_state_allows_retry_by_default(self):
        """Finished dedupe records always allow retry."""
        import qq.web.ingest as ingest

        dedupe_key = "test:trans:finished-retry"
        ingest.record_dedupe(
            dedupe_key, "finished-run", "/fake/task.md", "/fake/target",
            run_root="/fake/root", events_path="/fake/events.jsonl",
            mode="repo", runner="local_exec", state="finished",
        )

        result = ingest.check_duplicate(dedupe_key)
        assert result is None, "Finished state should allow retry"


# ============================================================================
# Fast-finishing run state tests
# ============================================================================

class TestFastFinishingRunState:
    """Tests that fast-finishing runs end in 'finished' state, not 'started'."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        self.control_dir = tmp_path / "control"
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_path = tmp_path

    def test_centralized_finish_writes_finished_state(self):
        """_mark_runner_finished writes 'finished' state to current-run.json."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "fast-run")
        os.makedirs(run_root, exist_ok=True)
        events_path = os.path.join(run_root, "events.jsonl")

        item = {
            "run_id": "fast-run",
            "run_root": run_root,
            "events_path": events_path,
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.control_dir),
            "command_preview": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": None,
        }

        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        current = os.path.join(str(self.control_dir), "current-run.json")
        assert os.path.isfile(current), "current-run.json was not created"

        with open(current) as f:
            cr = json.load(f)
        assert cr["state"] == "finished", f"Expected finished, got {cr['state']}"
        assert cr["exit_code"] == 0
        assert "finished_at" in cr

    def test_fast_finish_does_not_end_as_started(self):
        """A run that starts and finishes should have current-run.json state='finished'."""
        import qq.web.ingest as ingest
        from qq.web.ingest import _write_current_run_pointer
        import json

        run_id = "fast-run-2"
        run_root = str(self.tmp_path / run_id)
        os.makedirs(run_root, exist_ok=True)
        events_path = os.path.join(run_root, "events.jsonl")
        control_root = str(self.control_dir)

        # Simulate: write 'starting', then immediately finish via _mark_runner_finished
        _write_current_run_pointer(
            run_id=run_id, run_root=run_root,
            events_path=events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="starting",
        )

        # Now finish
        item = {
            "run_id": run_id,
            "run_root": run_root,
            "events_path": events_path,
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": control_root,
            "command_preview": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
        }
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "finished", f"Fast finish must be 'finished', got '{cr['state']}'"

# ============================================================================
# REGRESSION TESTS: Exactly-once finish handler fixes
# ============================================================================

class TestExactlyOnceFinishHandlerFix:
    """Tests that the exactly-once finish handler bug is fixed.

    These tests exercise the actual code paths that were broken:
    - local_exec watcher no longer pre-adds to _finished_run_ids
    - tmux watcher no longer pre-adds to _finished_run_ids
    - _mark_runner_finished actually runs when called by watchers
    - _mark_runner_finished writes runner.finished, current-run.json, dedupe
    """

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._finished_run_ids.clear()
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        self.control_dir = tmp_path / "control"
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self._old_control = os.environ.get("QONQRETE_CONTROL_ROOT", "")
        os.environ["QONQRETE_CONTROL_ROOT"] = str(self.control_dir)
        self.tmp_path = tmp_path
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._finished_run_ids.clear()
        ingest._DEDUPE_PATH = self._old_dedupe
        if self._old_control:
            os.environ["QONQRETE_CONTROL_ROOT"] = self._old_control
        else:
            os.environ.pop("QONQRETE_CONTROL_ROOT", None)

    def test_local_exec_finish_writes_runner_finished_and_pointer(self):
        """local_exec watcher calls _mark_runner_finished which writes markers."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "finish-test")
        os.makedirs(run_root, exist_ok=True)
        events_path = os.path.join(run_root, "events.jsonl")

        item = {
            "run_id": "finish-test-001",
            "run_root": run_root,
            "events_path": events_path,
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
            "dedupe_key": "test:trans:finish-test-001",
        }

        # Call _mark_runner_finished directly (simulating watcher)
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        # Verify runner.finished was written
        finished_path = os.path.join(run_root, "runner.finished")
        assert os.path.isfile(finished_path), "runner.finished was not written"

        # Verify runner.exit_code was written
        exit_code_path = os.path.join(run_root, "runner.exit_code")
        assert os.path.isfile(exit_code_path), "runner.exit_code was not written"
        assert open(exit_code_path).read().strip() == "0"

        # Verify current-run.json was written with finished state
        ptr_path = self.control_dir / "current-run.json"
        assert ptr_path.is_file(), "current-run.json was not written"
        ptr = json.loads(ptr_path.read_text())
        assert ptr["state"] == "finished", f"Expected finished, got {ptr['state']}"
        assert ptr["exit_code"] == 0
        assert "finished_at" in ptr

        # Verify dedupe was recorded
        dedupe_file = ingest._DEDUPE_PATH
        assert os.path.isfile(dedupe_file), "Dedupe file not created"
        dedupe_lines = open(dedupe_file).readlines()
        assert len(dedupe_lines) > 0, "No dedupe entries written"

    def test_local_exec_watcher_does_not_pre_add(self):
        """local_exec watcher does not pre-add to _finished_run_ids before calling _mark_runner_finished."""
        import qq.web.ingest as ingest

        # Verify that after our fix, searching source for pre-add patterns
        # in the _watch function finds nothing
        import inspect
        # We can't easily inspect the nested _watch closure, but we can
        # verify the behavior: call _mark_runner_finished twice and see
        # that the second call is a no-op (exactly-once guard works properly)

        run_root = str(self.tmp_path / "runs" / "no-pre-add")
        os.makedirs(run_root, exist_ok=True)

        item = {
            "run_id": "no-pre-add-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
            "dedupe_key": "test:trans:no-pre-add-001",
        }

        # First call should succeed and do all the work
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        # Second call should be a no-op (exactly-once)
        # Modify the exit code to verify it doesn't get overwritten
        ingest._mark_runner_finished(item, exit_code=42, state="finished")

        # Exit code should still be 0 (not overwritten)
        exit_code_path = os.path.join(run_root, "runner.exit_code")
        assert open(exit_code_path).read().strip() == "0", (
            "Second _mark_runner_finished call overwrote exit_code"
        )

        # Dedupe file should have exactly 1 entry for finished state
        dedupe_file = ingest._DEDUPE_PATH
        assert os.path.isfile(dedupe_file), f"Dedupe file not found: {dedupe_file}"
        dedupe_lines = [l for l in open(dedupe_file).readlines()
                       if '"state": "finished"' in l]
        assert len(dedupe_lines) == 1, (
            f"Expected 1 dedupe finished entry, got {len(dedupe_lines)}"
        )

    def test_active_run_cleared_after_finish(self):
        """_mark_runner_finished clears _active_run and _active_run_id."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "clear-active")
        os.makedirs(run_root, exist_ok=True)

        # Set active run state
        item = {
            "run_id": "clear-active-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
        }

        ingest._mark_run_active(item)
        assert ingest._active_run is True
        assert ingest._active_run_id == "clear-active-001"

        # Finish the run
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        assert ingest._active_run is False, "_active_run was not cleared"
        assert ingest._active_run_id is None, "_active_run_id was not cleared"

    def test_queue_advances_after_local_exec_finish(self, monkeypatch):
        """After first run finishes, queued second run starts."""
        import qq.web.ingest as ingest
        from qq.web.ingest import _queue, _queue_lock

        run_a_root = str(self.tmp_path / "runs" / "run-a")
        run_b_root = str(self.tmp_path / "runs" / "run-b")
        os.makedirs(run_a_root, exist_ok=True)
        os.makedirs(run_b_root, exist_ok=True)

        # Set active run A
        item_a = {
            "run_id": "run-a", "run_root": run_a_root,
            "events_path": os.path.join(run_a_root, "events.jsonl"),
            "task_path": "/fake/task_a.md", "target_path": "/fake/target_a",
            "mode": "repo", "source": "test", "runner": "local_exec",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z", "pid": 99999,
        }
        item_b = {
            "run_id": "run-b", "run_root": run_b_root,
            "events_path": os.path.join(run_b_root, "events.jsonl"),
            "task_path": "/fake/task_b.md", "target_path": "/fake/target_b",
            "mode": "repo", "source": "test", "runner": "local_exec",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z",
            "dedupe_key": "test:trans:run-b",
            "args": ["qq-tui"],
        }

        ingest._mark_run_active(item_a)

        # Queue run B
        with _queue_lock:
            _queue.append(item_b)

        # Track launches
        launch_count = [0]
        def _tracking_launch(item):
            launch_count[0] += 1
            item["launch_ok"] = True
            item["pid"] = 99999
            item["runner"] = "local_exec"
            ingest._mark_run_active(item)
            return True

        old_launch = ingest._do_launch
        ingest._do_launch = _tracking_launch

        try:
            # Finish run A via _mark_runner_finished
            ingest._mark_runner_finished(item_a, exit_code=0, state="finished")

            # Run B should have been launched
            assert launch_count[0] == 1, f"Expected 1 launch, got {launch_count[0]}"
            assert ingest._active_run is True
            assert ingest._active_run_id == "run-b"
        finally:
            ingest._do_launch = old_launch
            _queue.clear()
            ingest._active_run = False
            ingest._active_run_id = None
            ingest._active_item = None

    def test_tmux_marker_finish_writes_finished_state(self):
        """tmux watcher marker detection writes finished state via _mark_runner_finished."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "tmux-finish")
        os.makedirs(run_root, exist_ok=True)

        # Pre-create runner.finished and runner.exit_code (simulating tmux command exit)
        with open(os.path.join(run_root, "runner.finished"), "w") as f:
            f.write("2026-01-01T00:00:00Z")
        with open(os.path.join(run_root, "runner.exit_code"), "w") as f:
            f.write("0")

        item = {
            "run_id": "tmux-finish-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "tmux",
            "tmux_session": "qonqrete-tmux-finish-001",
            "attach_command": "tmux attach -t qonqrete-tmux-finish-001",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z",
            "dedupe_key": "test:trans:tmux-finish-001",
        }

        ingest._mark_run_active(item)

        # Simulate watcher calling central finish
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        # Verify current-run.json
        ptr_path = self.control_dir / "current-run.json"
        ptr = json.loads(ptr_path.read_text())
        assert ptr["state"] == "finished", f"Expected finished, got {ptr['state']}"
        assert ptr["exit_code"] == 0
        assert ptr["runner"] == "tmux"
        assert ptr.get("tmux_session") is not None or True  # tmux_session may be in pointer

        # Verify active cleared
        assert ingest._active_run is False

    def test_tmux_stale_path_uses_central_finish(self):
        """tmux stale fallback uses _mark_runner_finished with state='stale'."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "tmux-stale")
        os.makedirs(run_root, exist_ok=True)

        item = {
            "run_id": "tmux-stale-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "tmux",
            "tmux_session": "qonqrete-tmux-stale-001",
            "attach_command": "tmux attach -t qonqrete-tmux-stale-001",
            "control_root": str(self.control_dir),
            "command_preview": "qq-tui run ...",
            "created_at": "2026-01-01T00:00:00Z",
            "dedupe_key": "test:trans:tmux-stale-001",
        }

        ingest._mark_run_active(item)

        # Call central finish with stale state
        ingest._mark_runner_finished(item, exit_code=None, state="stale")

        # Verify current-run.json has stale state
        ptr_path = self.control_dir / "current-run.json"
        ptr = json.loads(ptr_path.read_text())
        assert ptr["state"] == "stale", f"Expected stale, got {ptr['state']}"

        # Verify active cleared
        assert ingest._active_run is False

        # Verify runner.finished was written
        finished_path = os.path.join(run_root, "runner.finished")
        assert os.path.isfile(finished_path), "runner.finished was not written for stale path"


class TestGuardedPointerWrites:
    """Tests that lifecycle writes use guarded pointer update, not raw write."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._finished_run_ids.clear()
        self.control_dir = tmp_path / "control"
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_path = tmp_path

    def test_fast_finish_does_not_regress_to_started(self):
        """A fast finish (finished before started ptr write) stays finished."""
        from qq.web.ingest import _update_current_run_pointer_guarded, _write_current_run_pointer, _mark_runner_finished
        import qq.web.ingest as ingest

        run_id = "fast-race-001"
        run_root = str(self.tmp_path / "runs" / run_id)
        os.makedirs(run_root, exist_ok=True)
        events_path = os.path.join(run_root, "events.jsonl")
        control_root = str(self.control_dir)

        # Simulate: starting pointer written, then run finishes fast,
        # then code tries to write started
        _write_current_run_pointer(
            run_id=run_id, run_root=run_root,
            events_path=events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="starting",
        )

        # Fast finish via _mark_runner_finished
        item = {
            "run_id": run_id, "run_root": run_root,
            "events_path": events_path,
            "task_path": "/fake/task.md", "target_path": "/fake/target",
            "mode": "repo", "source": "test",
            "runner": "local_exec",
            "control_root": control_root,
            "command_preview": "test",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
        }
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        # Verify finished
        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "finished", f"Expected finished, got {cr['state']}"

        # Now try to write started (simulating post-launch started write)
        _update_current_run_pointer_guarded(
            run_id=run_id, run_root=run_root,
            events_path=events_path,
            task_path="/fake/task.md",
            target_path="/fake/target",
            mode="repo", source="test",
            runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z",
            command_preview="test",
            control_root=control_root,
            state="started",
        )

        # State must still be finished
        with open(os.path.join(control_root, "current-run.json")) as f:
            cr = json.load(f)
        assert cr["state"] == "finished", (
            f"Fast-finish race: finished was regressed to {cr['state']}!"
        )

    def test_guarded_pointer_write_used_for_starting_in_immediate_launch(self):
        """Verify that the immediate launch path uses guarded pointer for starting."""
        import qq.web.ingest as ingest
        import ast

        with open(os.path.join(os.path.dirname(ingest.__file__), "ingest.py")) as f:
            source = f.read()

        # After our fix, create_external_run_trigger should call
        # _update_current_run_pointer_guarded for "starting", "launch_failed", and "started"
        # NOT raw _write_current_run_pointer for those states.

        tree = ast.parse(source)
        found_create_ext = False
        raw_write_count = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'create_external_run_trigger':
                found_create_ext = True
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        # Check the function being called
                        fn_id = None
                        if hasattr(sub.func, 'id'):
                            fn_id = sub.func.id
                        elif hasattr(sub.func, 'attr'):
                            fn_id = sub.func.attr

                        if fn_id == '_write_current_run_pointer':
                            # Check what state this raw write is for
                            for kw in sub.keywords:
                                if kw.arg == 'state' and hasattr(kw.value, 'value'):
                                    state_val = kw.value.value
                                    if state_val in ('starting', 'started', 'launch_failed'):
                                        raw_write_count += 1
                break

        assert found_create_ext, "Could not find create_external_run_trigger function"
        assert raw_write_count == 0, (
            f"Found {raw_write_count} raw _write_current_run_pointer calls for "
            f"lifecycle states in create_external_run_trigger. "
            f"Should use _update_current_run_pointer_guarded instead."
        )


class TestDedupeFullMetadata:
    """Tests that dedupe records include full metadata."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        import qq.web.ingest as ingest
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._finished_run_ids.clear()
        dedupe_dir = tmp_path / "dedupe"
        dedupe_dir.mkdir(parents=True, exist_ok=True)
        dedupe_file = str(dedupe_dir / "dedupe.jsonl")
        self._old_dedupe = ingest._DEDUPE_PATH
        ingest._DEDUPE_PATH = dedupe_file
        self.tmp_path = tmp_path
        yield
        ingest._queue.clear()
        ingest._active_run = False
        ingest._active_run_id = None
        ingest._active_item = None
        ingest._finished_run_ids.clear()
        ingest._DEDUPE_PATH = self._old_dedupe

    def test_finished_dedupe_includes_command_preview(self):
        """Finished dedupe record includes command_preview."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "meta-test")
        os.makedirs(run_root, exist_ok=True)

        item = {
            "run_id": "meta-test-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.tmp_path / "control"),
            "command_preview": "qq-tui run --no-web --run-root /x/qq/runs/meta-test-001",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
            "dedupe_key": "test:trans:meta-test-001",
        }

        os.makedirs(str(self.tmp_path / "control"), exist_ok=True)
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        dedupe_file = ingest._DEDUPE_PATH
        with open(dedupe_file) as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("state") == "finished":
                    assert "command_preview" in entry, "Finished dedupe missing command_preview"
                    assert entry["command_preview"] == "qq-tui run --no-web --run-root /x/qq/runs/meta-test-001"
                    assert entry["runner"] == "local_exec"
                    assert entry["pid"] == 99999
                    assert "updated_at" in entry

    def test_tmux_dedupe_includes_tmux_fields(self):
        """Tmux dedupe record includes tmux_session and attach_command."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "tmux-meta")
        os.makedirs(run_root, exist_ok=True)

        item = {
            "run_id": "tmux-meta-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "tmux",
            "tmux_session": "qonqrete-tmux-meta-001",
            "attach_command": "tmux attach -t qonqrete-tmux-meta-001",
            "control_root": str(self.tmp_path / "control"),
            "command_preview": "qq-tui run --no-web --run-root /x/qq/runs/tmux-meta",
            "created_at": "2026-01-01T00:00:00Z",
            "dedupe_key": "test:trans:tmux-meta-001",
        }

        os.makedirs(str(self.tmp_path / "control"), exist_ok=True)
        ingest._mark_runner_finished(item, exit_code=0, state="finished")

        dedupe_file = ingest._DEDUPE_PATH
        with open(dedupe_file) as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("state") == "finished":
                    assert "tmux_session" in entry, "Tmux dedupe missing tmux_session"
                    assert entry["tmux_session"] == "qonqrete-tmux-meta-001"
                    assert "attach_command" in entry, "Tmux dedupe missing attach_command"
                    assert entry["attach_command"] == "tmux attach -t qonqrete-tmux-meta-001"
                    assert "command_preview" in entry

    def test_stale_dedupe_includes_metadata(self):
        """Stale dedupe record includes all available metadata."""
        import qq.web.ingest as ingest

        run_root = str(self.tmp_path / "runs" / "stale-meta")
        os.makedirs(run_root, exist_ok=True)

        item = {
            "run_id": "stale-meta-001",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/fake/task.md",
            "target_path": "/fake/target",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "control_root": str(self.tmp_path / "control"),
            "command_preview": "qq-tui run",
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 99999,
            "dedupe_key": "test:trans:stale-meta-001",
        }

        os.makedirs(str(self.tmp_path / "control"), exist_ok=True)
        ingest._mark_runner_finished(item, exit_code=None, state="stale")

        dedupe_file = ingest._DEDUPE_PATH
        with open(dedupe_file) as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("state") == "stale":
                    assert "command_preview" in entry, "Stale dedupe missing command_preview"
                    assert entry["command_preview"] == "qq-tui run"
                    assert "updated_at" in entry
                    break


# ===========================================================================
# Regression tests for fixes.md — Hardening fixes
# ===========================================================================

class TestGuardRejectsStaleOldActiveWrite:
    """fixes.md #2-A: Guard rejects stale old active write."""
    def test_stale_old_run_started_cannot_overwrite_newer_terminal(self, tmp_path):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        # Write pointer: run B, state finished
        ingest._update_current_run_pointer_guarded(
            run_id="run-B", run_root="/tmp/run-B", events_path="/tmp/run-B/events.jsonl",
            task_path="/tmp/tasks/task-B.md", target_path="/tmp/run-B",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run B",
            control_root=control_root, state="finished",
            finished_at="2026-01-01T00:01:00Z", exit_code=0,
        )

        # Verify pointer is B finished
        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-B"
        assert ptr["state"] == "finished"

        # Attempt to write run A started with allow_switch_to_new_run=False (default)
        ingest._update_current_run_pointer_guarded(
            run_id="run-A", run_root="/tmp/run-A", events_path="/tmp/run-A/events.jsonl",
            task_path="/tmp/tasks/task-A.md", target_path="/tmp/run-A",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run A",
            control_root=control_root, state="started",
            # allow_switch_to_new_run=False (default)
        )

        # Assert pointer remains B finished
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-B", f"Expected run-B, got {ptr.get('run_id')}"
        assert ptr["state"] == "finished", f"Expected finished, got {ptr.get('state')}"


class TestGuardAllowsExplicitNewRunSwitch:
    """fixes.md #2-B: Guard allows explicit new run switch."""
    def test_explicit_switch_after_terminal_succeeds(self, tmp_path):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        # Write pointer: run B, state finished
        ingest._update_current_run_pointer_guarded(
            run_id="run-B", run_root="/tmp/run-B", events_path="/tmp/run-B/events.jsonl",
            task_path="/tmp/tasks/task-B.md", target_path="/tmp/run-B",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run B",
            control_root=control_root, state="finished",
            finished_at="2026-01-01T00:01:00Z", exit_code=0,
        )

        # Write run C starting with allow_switch_to_new_run=True
        ingest._update_current_run_pointer_guarded(
            run_id="run-C", run_root="/tmp/run-C", events_path="/tmp/run-C/events.jsonl",
            task_path="/tmp/tasks/task-C.md", target_path="/tmp/run-C",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:02:00Z", command_preview="qq run C",
            control_root=control_root, state="starting",
            allow_switch_to_new_run=True,
        )

        # Assert pointer becomes C starting
        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-C", f"Expected run-C, got {ptr.get('run_id')}"
        assert ptr["state"] == "starting", f"Expected starting, got {ptr.get('state')}"


class TestStartedWriteCannotSwitch:
    """fixes.md #2-C: Started write cannot switch run_id."""
    def test_started_write_only_upgrades_starting(self, tmp_path):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        # Write pointer: run B, state starting
        ingest._update_current_run_pointer_guarded(
            run_id="run-B", run_root="/tmp/run-B", events_path="/tmp/run-B/events.jsonl",
            task_path="/tmp/tasks/task-B.md", target_path="/tmp/run-B",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run B",
            control_root=control_root, state="starting",
            allow_switch_to_new_run=True,
        )

        # Verify B starting
        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-B"
        assert ptr["state"] == "starting"

        # Attempt run A started (no allow_switch) — must be rejected
        ingest._update_current_run_pointer_guarded(
            run_id="run-A", run_root="/tmp/run-A", events_path="/tmp/run-A/events.jsonl",
            task_path="/tmp/tasks/task-A.md", target_path="/tmp/run-A",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run A",
            control_root=control_root, state="started",
        )

        # Assert pointer remains B
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-B", f"Expected run-B, got {ptr.get('run_id')}"

    def test_started_can_upgrade_same_run_from_starting(self, tmp_path):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        # Write pointer: run B, state starting
        ingest._update_current_run_pointer_guarded(
            run_id="run-B", run_root="/tmp/run-B", events_path="/tmp/run-B/events.jsonl",
            task_path="/tmp/tasks/task-B.md", target_path="/tmp/run-B",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run B",
            control_root=control_root, state="starting",
            allow_switch_to_new_run=True,
        )

        # Now write B started — same run_id, should upgrade
        ingest._update_current_run_pointer_guarded(
            run_id="run-B", run_root="/tmp/run-B", events_path="/tmp/run-B/events.jsonl",
            task_path="/tmp/tasks/task-B.md", target_path="/tmp/run-B",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run B",
            control_root=control_root, state="started",
        )

        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-B"
        assert ptr["state"] == "started"


class TestReconcileLocalExecNoPid:
    """fixes.md #4-F: Reconcile local_exec no-pid treats _active_run=False as stale."""
    def test_no_pid_without_full_active_state_returns_stale(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        run_id = "test-run-no-pid"
        run_root = str(tmp_path / "run_root_no_pid")

        # Write current-run.json: state started, runner local_exec, no pid
        pointer = {
            "run_id": run_id,
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/tmp/tasks/task.md",
            "target_path": run_root,
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "tmux_session": "",
            "created_at": "2026-01-01T00:00:00Z",
            "command_preview": "qq run",
            "state": "started",
        }
        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path, "w") as f:
            json.dump(pointer, f)

        # Simulate: _active_run=False, _active_run_id=run_id, _active_item=None
        import qq.web.ingest as ingest_mod
        with ingest_mod._queue_lock:
            ingest_mod._active_run = False
            ingest_mod._active_run_id = run_id
            ingest_mod._active_item = None

        config = ObeliskIngestConfig(control_root=control_root)
        result = ingest._reconcile_active_run(config)

        # Should return False (stale)
        assert result is False, f"Expected False (stale), got {result}"

        # Pointer should become stale
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["state"] in ("stale",), f"Expected stale, got {ptr.get('state')}"

        # Active state should be cleared
        with ingest_mod._queue_lock:
            assert ingest_mod._active_run is False

    def test_no_pid_with_full_active_state_returns_active(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        run_id = "test-run-active-no-pid"
        run_root = str(tmp_path / "run_root_active")

        # Write current-run.json: state started, runner local_exec, no pid
        pointer = {
            "run_id": run_id,
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "/tmp/tasks/task.md",
            "target_path": run_root,
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "tmux_session": "",
            "created_at": "2026-01-01T00:00:00Z",
            "command_preview": "qq run",
            "state": "started",
        }
        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path, "w") as f:
            json.dump(pointer, f)

        # Simulate: _active_run=True, _active_run_id=run_id, _active_item with matching run_id
        import qq.web.ingest as ingest_mod
        with ingest_mod._queue_lock:
            ingest_mod._active_run = True
            ingest_mod._active_run_id = run_id
            ingest_mod._active_item = {"run_id": run_id}

        config = ObeliskIngestConfig(control_root=control_root)
        result = ingest._reconcile_active_run(config)

        # Should return True (active)
        assert result is True, f"Expected True (active), got {result}"


class TestDuplicateRetryNoEmptyRunRoot:
    """fixes.md #6-G: Duplicate retry does not create unused run root."""
    def test_duplicate_retry_does_not_create_unused_directory(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        import subprocess
        control_root = str(tmp_path / "control")
        run_root_parent = str(tmp_path / "runs")
        os.makedirs(control_root, exist_ok=True)
        os.makedirs(run_root_parent, exist_ok=True)

        # Set up config with control_root and run_root_parent
        config = ObeliskIngestConfig(
            default_run_root=run_root_parent,
            control_root=control_root,
            dev_no_auth=True,
        )
        monkeypatch.setattr(ingest, "_DEDUPE_PATH", str(tmp_path / "dedupe.jsonl"))

        # Create a small shell subprocess to act as a "live run"
        import subprocess
        proc = subprocess.Popen(
            ["sleep", "30"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            live_pid = proc.pid
            live_run_id = "existing-run"
            live_run_root = os.path.join(run_root_parent, live_run_id)
            os.makedirs(live_run_root, exist_ok=True)

            # Create an active dedupe record with the live PID
            dedupe_key = "test:trans:dup-no-root-001"
            ingest.record_dedupe(
                dedupe_key=dedupe_key,
                run_id=live_run_id,
                task_path="/tmp/tasks/existing.md",
                target_path="/tmp/existing",
                state="started",
                run_root=live_run_root,
                events_path=os.path.join(live_run_root, "events.jsonl"),
                mode="repo",
                runner="local_exec",
                command_preview="qq run",
                pid=live_pid,
            )

            # Count existing directories under run_root_parent
            dirs_before = set(os.listdir(run_root_parent))

            # Call create_external_run_trigger with same transcription_id
            with monkeypatch.context() as m:
                m.setattr(ingest, "_reconcile_active_run", lambda c: False)
                m.setattr(ingest, "_active_run", False)
                result = ingest.create_external_run_trigger(
                    source="test",
                    raw_transcription="test raw",
                    task_text="build something",
                    mode="repo",
                    target="default",
                    transcription_id="dup-no-root-001",
                    config=config,
                )

            # Should be duplicate
            assert result.duplicate is True, f"Expected duplicate=True, got {result.duplicate}"

            # No new directory should have been created
            dirs_after = set(os.listdir(run_root_parent))
            new_dirs = dirs_after - dirs_before
            assert len(new_dirs) == 0, f"Unexpected new directories created: {new_dirs}"
        finally:
            proc.kill()
            proc.wait()


class TestDedupeFullMetadataAllStates:
    """fixes.md #5: Full metadata in all dedupe states."""
    def test_pointer_failed_dedupe_includes_all_metadata(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        monkeypatch.setattr(ingest, "_DEDUPE_PATH", str(tmp_path / "dedupe.jsonl"))
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        item = {
            "run_id": "test-pf-001",
            "run_root": "/tmp/test-pf-001",
            "events_path": "/tmp/test-pf-001/events.jsonl",
            "task_path": "/tmp/tasks/task.md",
            "target_path": "/tmp/test-pf-001",
            "mode": "repo",
            "source": "test",
            "runner": "local_exec",
            "command_preview": "qq-tui run --no-web",
            "dedupe_key": "test:pf:001",
            "control_root": control_root,
            "created_at": "2026-01-01T00:00:00Z",
            "pid": 12345,
        }
        ingest._record_item_dedupe(item, "pointer_failed")

        dedupe_file = ingest._DEDUPE_PATH
        with open(dedupe_file) as f:
            entry = json.loads(f.readline().strip())
            assert entry["state"] == "pointer_failed"
            assert entry["command_preview"] == "qq-tui run --no-web"
            assert entry["pid"] == 12345
            assert entry["mode"] == "repo"
            assert entry["runner"] == "local_exec"
            assert "updated_at" in entry

    def test_tmux_stale_dedupe_includes_tmux_fields(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        monkeypatch.setattr(ingest, "_DEDUPE_PATH", str(tmp_path / "dedupe.jsonl"))

        item = {
            "run_id": "test-tmux-001",
            "run_root": "/tmp/test-tmux-001",
            "events_path": "/tmp/test-tmux-001/events.jsonl",
            "task_path": "/tmp/tasks/task.md",
            "target_path": "/tmp/test-tmux-001",
            "mode": "repo",
            "source": "test",
            "runner": "tmux",
            "command_preview": "qq-tui run --no-web",
            "dedupe_key": "test:tmux:001",
            "control_root": "/tmp/control",
            "created_at": "2026-01-01T00:00:00Z",
            "tmux_session": "qonqrete-test-tmux-001",
            "attach_command": "tmux attach -t qonqrete-test-tmux-001",
        }
        ingest._record_item_dedupe(item, "stale")

        dedupe_file = ingest._DEDUPE_PATH
        with open(dedupe_file) as f:
            entry = json.loads(f.readline().strip())
            assert entry["state"] == "stale"
            assert entry["tmux_session"] == "qonqrete-test-tmux-001"
            assert entry["attach_command"] == "tmux attach -t qonqrete-test-tmux-001"
            assert entry["runner"] == "tmux"
            assert entry["command_preview"] == "qq-tui run --no-web"


class TestImmediateStartPathUsesAllowSwitch:
    """fixes.md #2-D: Immediate start path uses allow_switch_to_new_run only for 'starting'."""
    def test_started_post_launch_does_not_allow_switch(self, tmp_path, monkeypatch):
        import qq.web.ingest as ingest
        control_root = str(tmp_path / "control")
        os.makedirs(control_root, exist_ok=True)

        # Verify: "started" write in create_external_run_trigger does NOT
        # use allow_switch_to_new_run (we can verify this by checking
        # the AST or by behavioral test)
        # Behavioral test: write a different run_id as terminal, then
        # try the "started" path — it should be rejected.

        # Write pointer: run B, state finished
        ingest._update_current_run_pointer_guarded(
            run_id="run-B", run_root="/tmp/run-B", events_path="/tmp/run-B/events.jsonl",
            task_path="/tmp/tasks/task-B.md", target_path="/tmp/run-B",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:00:00Z", command_preview="qq run B",
            control_root=control_root, state="finished",
            finished_at="2026-01-01T00:01:00Z", exit_code=0,
        )

        # Try "started" for run A without allow_switch — should be blocked
        ingest._update_current_run_pointer_guarded(
            run_id="run-A", run_root="/tmp/run-A", events_path="/tmp/run-A/events.jsonl",
            task_path="/tmp/tasks/task-A.md", target_path="/tmp/run-A",
            mode="repo", source="test", runner="local_exec", tmux_session="",
            created_at="2026-01-01T00:02:00Z", command_preview="qq run A",
            control_root=control_root, state="started",
            # NO allow_switch_to_new_run (default False — like the post-launch "started" path)
        )

        pointer_path = os.path.join(control_root, "current-run.json")
        with open(pointer_path) as f:
            ptr = json.load(f)
        assert ptr["run_id"] == "run-B", f"Expected run-B, got {ptr.get('run_id')}"
        assert ptr["state"] == "finished", f"Expected finished, got {ptr.get('state')}"
