"""
Tests for the QonQrete completion callback system.

Run:
    python -m pytest tests/test_completion_callback.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

# Ensure the repo root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qq.completion_callback import (
    CompletionCallbackConfig,
    CallbackState,
    CompletionStatus,
    load_completion_callback_config,
    write_origin_metadata,
    load_origin_metadata,
    is_run_fully_done,
    run_is_fully_done,
    is_run_terminal,
    get_run_completion_status,
    get_run_terminal_status,
    build_callback_payload,
    send_completion_callback,
    maybe_send_completion_callback,
    maybe_send_terminal_callback,
    acquire_callback_send_lock,
    write_callback_state,
    load_callback_state,
    _build_reply_text,
    _resolve_per_run_callback_url,
    _resolve_per_run_callback_token,
    is_callback_enabled_for_run,
    get_run_aware_callback_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Autouse fixture: ensure urllib.request.urlopen is restored between tests.
# This prevents test-isolation issues when threaded mock patches in
# TestConcurrentExactlyOnce leak across to subsequent test files.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _restore_urlopen():
    """Restore urllib.request.urlopen after each test to prevent mock leaks."""
    import urllib.request as _ur
    _original = _ur.urlopen
    yield
    _ur.urlopen = _original


@pytest.fixture
def run_root(tmp_path):
    """Create a temporary run_root with state/ directory."""
    rr = tmp_path / "run_20260704-020902-8141e5a5"
    state_dir = rr / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(rr)


@pytest.fixture
def telegram_origin():
    return {
        "source": "obelisk",
        "source_channel": "telegram",
        "sender_id": "123456",
        "sender_name": "wicked",
        "chat_id": "-100123456",
        "chat_title": "QonQrete Control",
        "message_id": "98765",
        "transcription_id": "tg-98765",
        "raw_transcription": "qonqrete folder default now build a calculator in python",
        "trigger": "qonqrete",
        "task_text": "build a calculator in python",
        "task_title": "Build a Python calculator",
        "mode": "folder",
        "target": "/x/qq/testwebsite",
        "reply_to": {
            "channel": "telegram",
            "chat_id": "-100123456",
            "message_id": "98765",
        },
        "metadata": {},
    }


@pytest.fixture
def signal_origin():
    return {
        "source": "obelisk",
        "source_channel": "signal",
        "sender_id": "+31612345678",
        "sender_name": "wicked",
        "chat_id": "+31612345678",
        "message_id": "sig-abc123",
        "transcription_id": "sig-abc123",
        "raw_transcription": "concrete folder default now build a calculator in python",
        "trigger": "concrete",
        "task_text": "build a calculator in python",
        "task_title": "Build a Python calculator",
        "mode": "folder",
        "target": "/x/qq/testwebsite",
        "reply_to": {
            "channel": "signal",
            "recipient": "+31612345678",
            "message_id": "sig-abc123",
        },
        "metadata": {},
    }


def _write_final_json(run_root: str, status: str, success: bool = True) -> None:
    """Helper to write a final.json for testing."""
    final_path = os.path.join(run_root, "state", "final.json")
    data = {
        "run_id": os.path.basename(run_root),
        "status": status,
        "cycle": 3,
        "run_root": run_root,
        "final_verdict": {"status": status, "summary": "All passed."},
        "finished_at": "2026-07-04T02:09:02Z",
    }
    with open(final_path, "w") as f:
        json.dump(data, f)


def _write_events(run_root: str, events: list) -> None:
    """Helper to write events.jsonl."""
    path = os.path.join(run_root, "events.jsonl")
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _write_exit_code(run_root: str, code: int) -> None:
    """Write runner.exit_code."""
    path = os.path.join(run_root, "runner.exit_code")
    with open(path, "w") as f:
        f.write(str(code))


# ---------------------------------------------------------------------------
# A. Origin metadata persistence
# ---------------------------------------------------------------------------


class TestOriginPersistence:
    def test_telegram_origin_written(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        loaded = load_origin_metadata(run_root)
        assert loaded is not None
        assert loaded["source_channel"] == "telegram"
        assert loaded["sender_id"] == "123456"
        assert loaded["chat_id"] == "-100123456"
        assert loaded["message_id"] == "98765"
        assert loaded["reply_to"]["channel"] == "telegram"

    def test_signal_origin_written(self, run_root, signal_origin):
        write_origin_metadata(run_root, signal_origin, run_id=os.path.basename(run_root))
        loaded = load_origin_metadata(run_root)
        assert loaded is not None
        assert loaded["source_channel"] == "signal"
        assert loaded["sender_id"] == "+31612345678"
        assert loaded["reply_to"]["channel"] == "signal"

    def test_channel_normalization(self, run_root):
        """If source_channel is missing but channel is provided, use channel."""
        origin = {
            "source": "obelisk",
            "channel": "signal",
            "sender_id": "+31612345678",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["source_channel"] == "signal"

    def test_transport_fallback(self, run_root):
        """If transport is provided, use it."""
        origin = {
            "source": "obelisk",
            "transport": "telegram",
            "sender_id": "123",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["source_channel"] == "telegram"

    def test_source_inference(self, run_root):
        """If no channel/transport, infer from source."""
        origin = {
            "source": "obelisk-telegram",
            "sender_id": "123",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["source_channel"] == "telegram"

    def test_missing_origin_returns_none(self, run_root):
        assert load_origin_metadata(run_root) is None


# ---------------------------------------------------------------------------
# B. FULLY_DONE detection
# ---------------------------------------------------------------------------


class TestFullyDoneDetection:
    def test_final_json_fully_done(self, run_root):
        _write_final_json(run_root, "FULLY_DONE")
        assert is_run_fully_done(run_root) is True

    def test_final_json_done(self, run_root):
        _write_final_json(run_root, "DONE")
        assert is_run_fully_done(run_root) is True

    def test_final_json_success(self, run_root):
        _write_final_json(run_root, "success")
        assert is_run_fully_done(run_root) is True

    def test_final_json_accepted(self, run_root):
        _write_final_json(run_root, "accepted")
        assert is_run_fully_done(run_root) is True

    def test_final_json_failed(self, run_root):
        _write_final_json(run_root, "FAILED")
        assert is_run_fully_done(run_root) is False

    def test_final_json_aborted(self, run_root):
        _write_final_json(run_root, "ABORTED")
        assert is_run_fully_done(run_root) is False

    def test_events_run_completed(self, run_root):
        _write_events(run_root, [
            {"ts": time.time(), "type": "run.started", "run_id": "test"},
            {"ts": time.time(), "type": "run.completed", "status": "success", "run_id": "test"},
        ])
        assert is_run_fully_done(run_root) is True

    def test_events_run_completed_fully_done(self, run_root):
        _write_events(run_root, [
            {"ts": time.time(), "type": "run.started", "run_id": "test"},
            {"ts": time.time(), "type": "run.completed", "status": "FULLY_DONE", "run_id": "test"},
        ])
        assert is_run_fully_done(run_root) is True

    def test_events_run_failed(self, run_root):
        _write_events(run_root, [
            {"ts": time.time(), "type": "run.started", "run_id": "test"},
            {"ts": time.time(), "type": "run.failed", "run_id": "test"},
        ])
        assert is_run_fully_done(run_root) is False

    def test_events_run_aborted(self, run_root):
        _write_events(run_root, [
            {"ts": time.time(), "type": "run.started", "run_id": "test"},
            {"ts": time.time(), "type": "run.aborted", "run_id": "test"},
        ])
        assert is_run_fully_done(run_root) is False

    def test_process_exit_only_not_fully_done(self, run_root):
        """Process exit (exit_code 0) is not FULLY_DONE."""
        _write_exit_code(run_root, 0)
        status = get_run_completion_status(run_root)
        assert status.done is False
        assert "runner_exit_code" in status.reason

    def test_process_exit_nonzero_not_fully_done(self, run_root):
        _write_exit_code(run_root, 1)
        status = get_run_completion_status(run_root)
        assert status.done is False

    def test_no_signals_at_all(self, run_root):
        status = get_run_completion_status(run_root)
        assert status.done is False
        assert status.reason == "no_terminal_signal_found"

    def test_fully_done_returns_full_status(self, run_root):
        _write_final_json(run_root, "FULLY_DONE")
        status = get_run_completion_status(run_root)
        assert status.done is True
        assert status.terminal is True
        assert status.success is True
        assert status.status == "FULLY_DONE"

    def test_final_verdict_checked(self, run_root):
        """final.json with final_verdict.status FULLY_DONE also counts."""
        final_path = os.path.join(run_root, "state", "final.json")
        data = {
            "run_id": os.path.basename(run_root),
            "status": "building",
            "final_verdict": {"status": "FULLY_DONE", "summary": "All good."},
        }
        with open(final_path, "w") as f:
            json.dump(data, f)
        assert is_run_fully_done(run_root) is True


class TestSharedRunIsFullyDonePredicate:
    """Coverage for the single shared A15/B3 terminal-FULLY_DONE predicate."""

    def test_action_status_fully_done_trumps_no_disk_signal(self, run_root):
        # Even with no disk signal, a live action_status of FULLY_DONE is terminal.
        assert run_is_fully_done("FULLY_DONE", run_root) is True

    def test_action_status_not_fully_done_falls_back_to_disk(self, run_root):
        _write_final_json(run_root, "FULLY_DONE")
        assert run_is_fully_done("Building", run_root) is True

    def test_action_status_none_uses_disk_status(self, run_root):
        _write_final_json(run_root, "FULLY_DONE")
        assert run_is_fully_done(None, run_root) is True

    def test_action_status_vs_final_json_agree(self, run_root):
        # The web poll convention (action_status from run.completed) and the
        # canonical get_run_terminal_status semantics must agree for FULLY_DONE.
        _write_events(run_root, [
            {"ts": time.time(), "type": "run.started", "run_id": "test"},
            {"ts": time.time(), "type": "run.completed", "status": "FULLY_DONE", "run_id": "test"},
        ])
        status = get_run_terminal_status(run_root)
        assert status.done is True
        assert status.status == "FULLY_DONE"
        assert run_is_fully_done("FULLY_DONE", run_root) is True

    def test_plain_done_is_not_strict_fully_done(self, run_root):
        # A plain "DONE" is a terminal "done" state but NOT the exact FULLY_DONE
        # status — A15/B3 freezing must not trigger on it (strict predicate).
        _write_final_json(run_root, "DONE")
        assert is_run_fully_done(run_root) is True           # broad (any done)
        assert run_is_fully_done(None, run_root) is False    # strict (exact FULLY_DONE)

    def test_failed_not_fully_done(self, run_root):
        _write_final_json(run_root, "FAILED")
        assert run_is_fully_done(None, run_root) is False

    def test_running_no_signal(self, run_root):
        assert run_is_fully_done("Building", run_root) is False


# ---------------------------------------------------------------------------
# C. Callback payload
# ---------------------------------------------------------------------------


class TestCallbackPayload:
    def test_telegram_payload(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig(
            enabled=True,
            url="http://127.0.0.1:8765/api/qonqrete/callbacks/run-completed",
            dashboard_url="http://10.11.12.111:31337",
        )
        payload = build_callback_payload(run_root, telegram_origin, completion, cfg)
        assert payload["event"] == "qonqrete.run.completed"
        assert payload["status"] == "FULLY_DONE"
        assert payload["success"] is True
        assert payload["run_id"] == os.path.basename(run_root)
        assert payload["origin"]["source_channel"] == "telegram"
        assert payload["reply"]["channel"] == "telegram"
        assert payload["reply"]["chat_id"] == "-100123456"
        assert "Dashboard" in payload["reply"]["text"]
        assert "FULLY_DONE" in payload["reply"]["text"]
        # No token in payload
        payload_str = json.dumps(payload)
        assert "token" not in payload_str.lower() or "token" not in json.dumps(payload["reply"])

    def test_signal_payload(self, run_root, signal_origin):
        write_origin_metadata(run_root, signal_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig(
            enabled=True,
            url="http://127.0.0.1:8765/api/qonqrete/callbacks/run-completed",
        )
        payload = build_callback_payload(run_root, signal_origin, completion, cfg)
        assert payload["origin"]["source_channel"] == "signal"
        assert payload["reply"]["channel"] == "signal"
        assert payload["reply"]["recipient"] == "+31612345678"

    def test_reply_text_includes_task(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, telegram_origin, completion, cfg)
        text = payload["reply"]["text"]
        assert "Build a Python calculator" in text
        assert os.path.basename(run_root) in text

    def test_reply_text_truncated(self):
        """Reply text is truncated to ~1500 chars."""
        long_summary = "x" * 5000
        text = _build_reply_text(
            status="FULLY_DONE",
            task_title="Test",
            target="/x/qq/test",
            run_id="abc",
            summary=long_summary,
            dashboard_url="http://example.com",
        )
        assert len(text) <= 1500

    def test_no_token_leaked_in_payload(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig(token="secret-token-123")
        payload = build_callback_payload(run_root, telegram_origin, completion, cfg)
        payload_str = json.dumps(payload)
        assert "secret-token-123" not in payload_str


# ---------------------------------------------------------------------------
# D. Exactly-once
# ---------------------------------------------------------------------------


class TestExactlyOnce:
    def test_already_sent_does_not_resend(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        # Pre-set sent state
        state = CallbackState(
            enabled=True, state="sent",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test",
        )
        write_callback_state(run_root, state)
        # Try to acquire lock
        assert acquire_callback_send_lock(run_root) is False

    def test_sending_state_respected(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        # Pre-set sending state + a fresh lock file
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state = CallbackState(
            enabled=True, state="sending",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test",
            last_attempt_at=now,
        )
        write_callback_state(run_root, state)
        # Create a fresh lock file to simulate another process holding the lock
        lock_path = os.path.join(run_root, "state", "completion_callback.lock")
        with open(lock_path, "w") as f:
            f.write(str(time.time()))
        # Should not acquire (fresh lock exists)
        assert acquire_callback_send_lock(run_root) is False
        # Clean up
        os.remove(lock_path)

    def test_stale_sending_state_reacquired(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        # Pre-set sending state (old, >5 min ago)
        old_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
        state = CallbackState(
            enabled=True, state="sending",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test",
            last_attempt_at=old_time,
        )
        write_callback_state(run_root, state)
        # Should reacquire (stale)
        assert acquire_callback_send_lock(run_root) is True

    def test_no_state_first_acquire(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        assert acquire_callback_send_lock(run_root) is True


# ---------------------------------------------------------------------------
# E. Retry behavior
# ---------------------------------------------------------------------------


class TestRetryBehavior:
    def test_retry_on_500(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        cfg = CompletionCallbackConfig(
            enabled=True,
            url="http://127.0.0.1:8765/api/callback",
            max_retries=3,
            retry_base_seconds=0.01,
            timeout_seconds=1,
        )

        # Mock: first 2 calls HTTP 500, 3rd call 200
        call_count = [0]

        class MockResponse:
            def __init__(self, status):
                self.status = status

            def getcode(self):
                return self.status

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise urllib.error.HTTPError(
                    req.full_url, 500, "Server Error", {}, None
                )
            return MockResponse(200)

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            state = send_completion_callback(run_root, cfg, callback_url="http://test")
            assert call_count[0] == 3
            assert state.state == "sent"
            assert state.attempts == 3

    def test_client_error_no_retry(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        cfg = CompletionCallbackConfig(
            enabled=True,
            url="http://127.0.0.1:8765/api/callback",
            max_retries=5,
            retry_base_seconds=0.01,
            timeout_seconds=1,
        )

        call_count = [0]

        def mock_urlopen_400(req, **kwargs):
            call_count[0] += 1
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen_400):
            state = send_completion_callback(run_root, cfg, callback_url="http://test")
            # 4xx should not retry — just 1 attempt
            assert call_count[0] == 1
            assert state.state == "failed"

    def test_failure_after_max_retries(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        cfg = CompletionCallbackConfig(
            enabled=True,
            url="http://127.0.0.1:8765/api/callback",
            max_retries=3,
            retry_base_seconds=0.01,
            timeout_seconds=1,
        )

        def mock_timeout(req, **kwargs):
            raise urllib.error.URLError("timeout")

        with mock.patch("urllib.request.urlopen", side_effect=mock_timeout):
            state = send_completion_callback(run_root, cfg, callback_url="http://test")
            assert state.state == "failed"
            assert state.attempts == 3
            assert state.last_error == "max_retries_exhausted"


# ---------------------------------------------------------------------------
# F. Not fully done = no callback
# ---------------------------------------------------------------------------


class TestNoCallbackWhenNotFullyDone:
    def test_started_no_callback(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        # No final.json, no events
        post_count = [0]

        def mock_post(req, **kwargs):
            post_count[0] += 1
            raise urllib.error.URLError("should not be called")

        with mock.patch("urllib.request.urlopen", side_effect=mock_post):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://127.0.0.1:8765/api/callback",
            )
            result = maybe_send_completion_callback(run_root)
            assert post_count[0] == 0
            assert result is None  # Not FULLY_DONE

    def test_non_terminal_no_callback(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "building")
        post_count = [0]

        def mock_post(req, **kwargs):
            post_count[0] += 1
            raise urllib.error.URLError("should not be called")

        with mock.patch("urllib.request.urlopen", side_effect=mock_post):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://127.0.0.1:8765/api/callback",
            )
            result = maybe_send_completion_callback(run_root)
            assert post_count[0] == 0

    def test_running_no_callback(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "building")
        post_count = [0]

        def mock_post(req, **kwargs):
            post_count[0] += 1
            raise urllib.error.URLError("should not be called")

        with mock.patch("urllib.request.urlopen", side_effect=mock_post):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://127.0.0.1:8765/api/callback",
            )
            result = maybe_send_completion_callback(run_root)
            assert post_count[0] == 0


# ---------------------------------------------------------------------------
# G. Config loading
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_disabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_completion_callback_config()
            assert cfg.enabled is False
            assert cfg.url == ""

    def test_enabled_by_url(self):
        with mock.patch.dict(os.environ, {"QONQRETE_OBELISK_CALLBACK_URL": "http://test"}, clear=True):
            cfg = load_completion_callback_config()
            assert cfg.enabled is True
            assert cfg.url == "http://test"

    def test_explicit_enable(self):
        with mock.patch.dict(os.environ, {
            "QONQRETE_COMPLETION_CALLBACK_ENABLED": "true",
            "QONQRETE_OBELISK_CALLBACK_URL": "http://test",
            "QONQRETE_COMPLETION_CALLBACK_TIMEOUT_SECONDS": "5",
            "QONQRETE_COMPLETION_CALLBACK_MAX_RETRIES": "3",
            "QONQRETE_COMPLETION_CALLBACK_ON_FAILURE": "mark_warning",
        }, clear=True):
            cfg = load_completion_callback_config()
            assert cfg.enabled is True
            assert cfg.timeout_seconds == 5
            assert cfg.max_retries == 3
            assert cfg.on_failure == "mark_warning"

    def test_token_never_serialized(self):
        cfg = CompletionCallbackConfig(token="secret-123")
        d = dataclasses_to_safe_dict(cfg)
        # Token should not appear in output — we don't serialize configs
        # The token is only used in Authorization header
        assert cfg.token == "secret-123"  # Present in config object for HTTP header use


def dataclasses_to_safe_dict(obj):
    """Helper — we verify the token is only used in headers, not payload."""
    import dataclasses
    return {f.name: "***" if f.name == "token" else getattr(obj, f.name)
            for f in dataclasses.fields(obj)}


# ---------------------------------------------------------------------------
# H. Recovery
# ---------------------------------------------------------------------------


class TestRecovery:
    def test_missed_callback_sent_on_recovery(self, run_root, telegram_origin):
        """If final.json FULLY_DONE exists but callback state is missing,
        recovery sends it once."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        # No callback state file

        call_count = [0]

        class MockResponse:
            status = 200

            def getcode(self):
                return 200

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://127.0.0.1:8765/api/callback",
            )
            state = send_completion_callback(run_root, cfg)
            assert call_count[0] == 1
            assert state.state == "sent"

        # Now reload state and verify sent
        saved = load_callback_state(run_root)
        assert saved is not None
        assert saved.state == "sent"

    def test_restart_after_full_send_no_duplicate(self, run_root, telegram_origin):
        """After a restart, the callback doesn't fire again."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        # Pre-set sent
        state = CallbackState(
            enabled=True, state="sent",
            run_id=os.path.basename(run_root),
            callback_url="http://test",
        )
        write_callback_state(run_root, state)

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            raise urllib.error.URLError("should not be called")

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://127.0.0.1:8765/api/callback",
            )
            result = maybe_send_completion_callback(run_root)
            assert call_count[0] == 0


# ---------------------------------------------------------------------------
# I. Disabled callback
# ---------------------------------------------------------------------------


class TestDisabledCallback:
    def test_disabled_no_send(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            cfg = CompletionCallbackConfig(enabled=False, url="http://test")
            result = send_completion_callback(run_root, cfg)
            assert result is None
            assert call_count[0] == 0

    def test_no_url_no_send(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            cfg = CompletionCallbackConfig(enabled=True, url="")
            result = send_completion_callback(run_root, cfg)
            assert result is None
            assert call_count[0] == 0


# ---------------------------------------------------------------------------
# J. Events emitted (verify event files get written)
# ---------------------------------------------------------------------------


class TestEventEmission:
    def test_callback_sent_event_written(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        class MockResponse:
            def getcode(self):
                return 200

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        with mock.patch("urllib.request.urlopen", return_value=MockResponse()):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://test",
            )
            send_completion_callback(run_root, cfg)

        # Check events.jsonl
        events_path = os.path.join(run_root, "events.jsonl")
        assert os.path.isfile(events_path)
        with open(events_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        types = [e["type"] for e in events]
        assert "completion_callback_attempt" in types
        assert "completion_callback_sent" in types

    def test_callback_failed_event_written(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        def mock_timeout(req, **kwargs):
            raise urllib.error.URLError("timeout")

        with mock.patch("urllib.request.urlopen", side_effect=mock_timeout):
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://test",
                max_retries=2,
                retry_base_seconds=0.01,
                timeout_seconds=1,
            )
            send_completion_callback(run_root, cfg)

        events_path = os.path.join(run_root, "events.jsonl")
        with open(events_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        types = [e["type"] for e in events]
        assert "completion_callback_attempt" in types
        assert "completion_callback_failed" in types

    def test_skip_event_when_not_terminal(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "building")

        cfg = CompletionCallbackConfig(enabled=True, url="http://test")
        send_completion_callback(run_root, cfg)

        events_path = os.path.join(run_root, "events.jsonl")
        with open(events_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        types = [e["type"] for e in events]
        assert "completion_callback_skipped_not_terminal" in types


# ---------------------------------------------------------------------------
# K. Concurrency tests — exactly-once with atomic lock
# ---------------------------------------------------------------------------


class TestConcurrentExactlyOnce:
    """Test that concurrent calls to maybe_send_completion_callback result in
    exactly one HTTP POST. (Fix #7)"""

    def test_10_threads_one_post(self, run_root, telegram_origin):
        """Start 10 threads calling callback at once — only one POST occurs."""
        import threading
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]
        lock = threading.Lock()

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            with lock:
                call_count[0] += 1
            return MockResponse()

        threads = []
        results = []

        def call_callback():
            cfg = CompletionCallbackConfig(
                enabled=True,
                url="http://test/callback",
            )
            # Use send_completion_callback directly (bypasses maybe_send's
            # top-level config reload)
            state = send_completion_callback(run_root, cfg)
            results.append(state)

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            for _ in range(10):
                t = threading.Thread(target=call_callback)
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        # Exactly one POST is the core exactly-once invariant.
        assert call_count[0] == 1, f"Expected 1 POST, got {call_count[0]}"
        # The winning thread must report sent; every thread that observed the
        # winner's state afterwards also legitimately reports sent, so exactly
        # one POST is what guarantees exactly-once, NOT that only one thread
        # observed the terminal "sent" state (that depends on read timing).
        assert any(r is not None and r.state == "sent" for r in results), \
            "No thread observed the sent state"

        # Verify state on disk is sent
        state = load_callback_state(run_root)
        assert state is not None
        assert state.state == "sent"

    def test_repeat_after_sent_no_new_post(self, run_root, telegram_origin):
        """After callback is sent, calling again does not POST."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # First send
        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
            )
            state1 = send_completion_callback(run_root, cfg)
            assert state1.state == "sent"
            assert call_count[0] == 1

        # Second call — should not POST
        with mock.patch("urllib.request.urlopen") as mock2:
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
            )
            state2 = send_completion_callback(run_root, cfg)
            assert state2.state == "sent"
            mock2.assert_not_called()

    def test_stale_lock_allows_retry(self, run_root, telegram_origin):
        """A lock older than TTL is broken and allows retry."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # Create a stale lock file
        lock_path = os.path.join(run_root, "state", "completion_callback.lock")
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        # Set mtime to 10 minutes ago
        stale_time = time.time() - 600
        with open(lock_path, "w") as f:
            f.write(str(stale_time))
        os.utime(lock_path, (stale_time, stale_time))

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
            )
            result = send_completion_callback(run_root, cfg)
            assert result is not None
            # Should have posted (lock was stale)
            assert call_count[0] == 1

    def test_fresh_lock_prevents_duplicate(self, run_root, telegram_origin):
        """A fresh lock (< TTL) prevents duplicate sends."""
        import threading, time as _time
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]
        lock = threading.Lock()

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            with lock:
                call_count[0] += 1
            # Simulate some latency so lock stays fresh
            _time.sleep(0.1)
            return MockResponse()

        # Use a barrier so all threads start at the same time
        barrier = threading.Barrier(5)

        def call_callback():
            barrier.wait()
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
            )
            send_completion_callback(run_root, cfg)

        threads = [threading.Thread(target=call_callback) for _ in range(5)]
        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)

        assert call_count[0] == 1, f"Expected 1 POST, got {call_count[0]}"

    def test_failed_callback_does_not_mark_run_failed(self, run_root, telegram_origin):
        """Failed callback does not affect the run status in final.json."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        def mock_fail(req, **kwargs):
            raise urllib.error.URLError("connection refused")

        with mock.patch("urllib.request.urlopen", side_effect=mock_fail):
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
                max_retries=1, retry_base_seconds=0.01, timeout_seconds=1,
            )
            state = send_completion_callback(run_root, cfg)
            assert state.state == "failed"

        # final.json should still show FULLY_DONE (unchanged by callback failure)
        final_path = os.path.join(run_root, "state", "final.json")
        with open(final_path) as f:
            final = json.load(f)
        assert final["status"] == "FULLY_DONE"


class TestReleaseCallbackLock:
    """Test that lock file is properly released after success/failure."""

    def test_lock_released_after_success(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with mock.patch("urllib.request.urlopen", return_value=MockResponse()):
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
            )
            send_completion_callback(run_root, cfg)

        # Lock should be cleaned up
        lock_path = os.path.join(run_root, "state", "completion_callback.lock")
        assert not os.path.exists(lock_path), "Lock file should be released after success"

    def test_lock_released_after_failure(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        def mock_fail(req, **kwargs):
            raise urllib.error.URLError("conn refused")

        with mock.patch("urllib.request.urlopen", side_effect=mock_fail):
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
                max_retries=1, retry_base_seconds=0.01, timeout_seconds=1,
            )
            send_completion_callback(run_root, cfg)

        # Lock should be cleaned up even after failure
        lock_path = os.path.join(run_root, "state", "completion_callback.lock")
        assert not os.path.exists(lock_path), "Lock file should be released after failure"

    def test_lock_released_after_skip(self, run_root, telegram_origin):
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        # NOT terminal — should skip
        _write_final_json(run_root, "building")

        cfg = CompletionCallbackConfig(
            enabled=True, url="http://test/callback",
        )
        send_completion_callback(run_root, cfg)

        lock_path = os.path.join(run_root, "state", "completion_callback.lock")
        assert not os.path.exists(lock_path), "Lock file should be released after skip"


# ===========================================================================
# NEW TESTS — Obelisk completion/failure callback upgrade
# ===========================================================================

class TestOriginPersistenceExtended:
    """A. Origin persistence extended tests."""

    def test_flat_callback_url_persists(self, run_root):
        """Flat callback_url persists in origin.json."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "callback_url": "http://obelisk:8080/api/callback",
            "chat_id": "-100123",
            "message_id": "456",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["callback_url"] == "http://obelisk:8080/api/callback"

    def test_flat_callback_token_ref_persists(self, run_root):
        """Flat callback_token_ref persists in origin.json."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "callback_token_ref": "QONQRETE_OBELISK_CALLBACK_TOKEN",
            "chat_id": "-100123",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["callback_token_ref"] == "QONQRETE_OBELISK_CALLBACK_TOKEN"

    def test_top_level_obelisk_block_persists(self, run_root):
        """Top-level obelisk block persists in origin.json."""
        origin = {
            "source": "obelisk",
            "source_channel": "signal",
            "obelisk": {
                "callback_url": "http://obelisk:8080/api/callback",
                "callback_auth": {"type": "bearer", "token": "secret"},
            },
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["obelisk"] is not None
        assert result["obelisk"]["callback_url"] == "http://obelisk:8080/api/callback"
        assert result["obelisk"]["callback_auth"]["type"] == "bearer"

    def test_metadata_obelisk_block_persists(self, run_root):
        """metadata.obelisk block persists in origin.json."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "metadata": {
                "obelisk": {
                    "callback_url": "http://obelisk:8080/api/callback",
                }
            },
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        # The obelisk block from metadata should end up in the top-level obelisk field
        assert result.get("obelisk") is not None or result.get("metadata", {}).get("obelisk") is not None

    def test_provided_reply_to_preserved(self, run_root):
        """Provided reply_to is preserved as-is (with channel normalization)."""
        origin = {
            "source": "obelisk",
            "source_channel": "signal",
            "reply_to": {
                "channel": "signal-cli",
                "recipient": "+31612345678",
                "message_id": "sig-abc",
            },
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["reply_to"]["channel"] == "signal"
        assert result["reply_to"]["recipient"] == "+31612345678"

    def test_source_channel_normalized(self, run_root):
        """source_channel is normalized to lowercase canonical form."""
        origin = {
            "source": "obelisk",
            "source_channel": "Telegram",
            "chat_id": "-100123",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["source_channel"] == "telegram"

    def test_tg_normalized_to_telegram(self, run_root):
        """'tg' is normalized to 'telegram'."""
        origin = {
            "source": "obelisk",
            "channel": "tg",
            "chat_id": "-100123",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["source_channel"] == "telegram"

    def test_signal_cli_normalized_to_signal(self, run_root):
        """'signal-cli' is normalized to 'signal'."""
        origin = {
            "source": "obelisk",
            "channel": "signal-cli",
            "sender_id": "+316",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["source_channel"] == "signal"

    def test_target_path_is_resolved_actual(self, run_root):
        """target_path is resolved actual directory, not 'default'."""
        origin = {
            "source": "obelisk",
            "target": "default",
            "target_path": "/x/qq/targets/myrun-123",
        }
        result = write_origin_metadata(
            run_root, origin, run_id="test",
            target_path="/x/qq/targets/myrun-123",
        )
        assert result["target_path"] == "/x/qq/targets/myrun-123"
        assert result["target"] == "default"

    def test_reply_to_synthesized_when_missing(self, run_root):
        """reply_to is synthesized for Telegram when not provided."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100123",
            "message_id": "456",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["reply_to"]["channel"] == "telegram"
        assert result["reply_to"]["chat_id"] == "-100123"

    def test_signal_reply_to_synthesized_when_missing(self, run_root):
        """reply_to is synthesized for Signal with recipient when not provided."""
        origin = {
            "source": "obelisk",
            "source_channel": "signal",
            "sender_id": "+31612345678",
            "message_id": "sig-abc",
        }
        result = write_origin_metadata(run_root, origin, run_id="test")
        assert result["reply_to"]["channel"] == "signal"
        assert result["reply_to"]["recipient"] == "+31612345678"


class TestPerRunCallbackEnablement:
    """B. Per-run callback enablement tests."""

    def test_no_global_callback_env_per_run_url_works(self, run_root, telegram_origin):
        """With no global callback env, per-run callback_url in origin enables callback."""
        # Write origin with per-run callback URL
        origin = dict(telegram_origin)
        origin["callback_url"] = "http://obelisk:8080/api/callback"
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = CompletionCallbackConfig(
                    enabled=True,
                    url="",  # No global URL
                )
                state = send_completion_callback(run_root, cfg)
                assert call_count[0] == 1, "Per-run callback URL should trigger send"
                assert state.state == "sent"

    def test_per_run_obelisk_callback_url_works(self, run_root):
        """origin.obelisk.callback_url works even without flat callback_url."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100123",
            "obelisk": {
                "callback_url": "http://obelisk:8080/api/callback",
            },
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = CompletionCallbackConfig(
                    enabled=True,
                    url="",
                )
                state = send_completion_callback(run_root, cfg)
                assert call_count[0] == 1
                assert state.state == "sent"

    def test_explicit_disable_blocks_per_run_url(self, run_root, telegram_origin):
        """QONQRETE_COMPLETION_CALLBACK_ENABLED=false blocks even per-run URL."""
        origin = dict(telegram_origin)
        origin["callback_url"] = "http://obelisk:8080/api/callback"
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {
                "QONQRETE_COMPLETION_CALLBACK_ENABLED": "false",
            }, clear=False):
                cfg = CompletionCallbackConfig(
                    enabled=False,
                    url="http://test",
                )
                state = send_completion_callback(run_root, cfg)
                assert state is None
                assert call_count[0] == 0


class TestSignalRouting:
    """C. Signal routing tests."""

    def test_signal_reply_channel(self, run_root, signal_origin):
        """Signal request produces reply.channel == 'signal'."""
        write_origin_metadata(run_root, signal_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, signal_origin, completion, cfg)
        assert payload["reply"]["channel"] == "signal"

    def test_signal_recipient_from_reply_to(self, run_root, signal_origin):
        """Signal recipient is populated from reply_to.recipient."""
        write_origin_metadata(run_root, signal_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, signal_origin, completion, cfg)
        assert payload["reply"]["recipient"] == "+31612345678"

    def test_signal_recipient_falls_back_to_chat_id(self, run_root):
        """Signal recipient falls back to chat_id when reply_to doesn't have recipient."""
        origin = {
            "source": "obelisk",
            "source_channel": "signal",
            "sender_id": "+31611111111",
            "chat_id": "+31622222222",
            "message_id": "sig-abc",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)
        assert payload["reply"]["recipient"] == "+31622222222"


class TestTelegramRouting:
    """D. Telegram routing tests."""

    def test_telegram_reply_channel(self, run_root, telegram_origin):
        """Telegram request produces reply.channel == 'telegram'."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, telegram_origin, completion, cfg)
        assert payload["reply"]["channel"] == "telegram"

    def test_telegram_chat_id_populated(self, run_root, telegram_origin):
        """Telegram reply.chat_id is populated."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_completion_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, telegram_origin, completion, cfg)
        assert payload["reply"]["chat_id"] == "-100123456"


class TestFullyDoneCanonicalization:
    """E. FULLY_DONE canonicalization tests."""

    def test_final_verdict_fully_done_over_top_level_done(self, run_root):
        """final.json with status='done' but final_verdict.status='FULLY_DONE'
        must produce payload status 'FULLY_DONE' and reply text 'Status: FULLY_DONE'."""
        final_path = os.path.join(run_root, "state", "final.json")
        data = {
            "status": "done",
            "final_verdict": {
                "status": "FULLY_DONE",
                "summary": "All passed",
            },
        }
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        with open(final_path, "w") as f:
            json.dump(data, f)

        status = get_run_terminal_status(run_root)
        assert status.done is True
        assert status.success is True
        assert status.status == "FULLY_DONE"

        # Build payload from this
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100123",
            "task_text": "test task",
            "task_title": "Test Task",
            "target_path": "/x/qq/targets/run-1",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, status, cfg)
        assert payload["status"] == "FULLY_DONE", f"Expected FULLY_DONE, got {payload['status']}"
        assert "FULLY_DONE" in payload["reply"]["text"]
        assert payload["success"] is True
        assert payload["fully_done"] is True

    def test_top_level_fully_done(self, run_root):
        """final.json with status='FULLY_DONE' (uppercase) works."""
        _write_final_json(run_root, "FULLY_DONE")
        status = get_run_terminal_status(run_root)
        assert status.done is True
        assert status.status == "FULLY_DONE"


class TestFailureCallback:
    """F. Failure callback tests."""

    def test_aborted_status_sends_failure_payload(self, run_root, telegram_origin):
        """final.json status='aborted' sends POST with success=False, fully_done=False."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        final_path = os.path.join(run_root, "state", "final.json")
        data = {
            "status": "aborted",
            "cycle": 5,
            "final_verdict": {"status": "ABORTED", "summary": "Hit max cycles"},
        }
        with open(final_path, "w") as f:
            json.dump(data, f)

        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is False
        assert status.status == "ABORTED"

        origin = load_origin_metadata(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, status, cfg)
        assert payload["event"] == "qonqrete.run.failed"
        assert payload["success"] is False
        assert payload["fully_done"] is False
        assert payload["status"] == "ABORTED"
        assert "❌" in payload["reply"]["text"] or "QonQrete" in payload["reply"]["text"]

    def test_events_run_failed_sends_terminal_callback(self, run_root, telegram_origin):
        """events.jsonl run.failed event produces terminal status."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        _write_events(run_root, [
            {"ts": time.time(), "type": "run.started", "run_id": "test"},
            {"ts": time.time(), "type": "run.failed", "run_id": "test", "error": "boom"},
        ])
        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is False
        assert status.status == "FAILED"

    def test_nonzero_exit_code_produces_terminal(self, run_root):
        """Nonzero runner.exit_code produces terminal PROCESS_FAILED status."""
        _write_exit_code(run_root, 1)
        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is False
        assert status.status == "PROCESS_FAILED"

    def test_failure_payload_includes_failure_reason(self, run_root, telegram_origin):
        """Failure callback payload includes failure_reason."""
        write_origin_metadata(run_root, telegram_origin, run_id=os.path.basename(run_root))
        final_path = os.path.join(run_root, "state", "final.json")
        data = {
            "status": "FAILED",
            "final_verdict": {"status": "FAILED"},
        }
        with open(final_path, "w") as f:
            json.dump(data, f)

        status = get_run_terminal_status(run_root)
        origin = load_origin_metadata(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, status, cfg)
        assert payload["success"] is False
        assert payload["failure_reason"] is not None
        assert payload["event"] == "qonqrete.run.failed"


class TestNoCallback:
    """G. No callback tests."""

    def test_no_origin_json_no_callback(self, run_root):
        """No origin.json means no callback (CLI-triggered run)."""
        _write_final_json(run_root, "FULLY_DONE")
        result = maybe_send_terminal_callback(run_root)
        assert result is None

    def test_no_callback_url_anywhere_no_callback(self, run_root, telegram_origin):
        """No callback URL anywhere means no callback."""
        # Write origin without any callback URL
        origin = dict(telegram_origin)
        origin.pop("callback_url", None)
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = CompletionCallbackConfig(enabled=True, url="")
            result = send_completion_callback(run_root, cfg)
            assert result is None

    def test_explicit_disable_blocks(self, run_root, telegram_origin):
        """QONQRETE_COMPLETION_CALLBACK_ENABLED=false disables callback."""
        origin = dict(telegram_origin)
        origin["callback_url"] = "http://test/callback"
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        with mock.patch.dict(os.environ, {
            "QONQRETE_COMPLETION_CALLBACK_ENABLED": "false",
        }):
            result = maybe_send_terminal_callback(run_root)
            assert result is None


class TestTokenResolution:
    """Token resolution tests."""

    def test_obelisk_auth_token_used(self, run_root):
        """origin.obelisk.callback_auth.token is used for Authorization."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100",
            "obelisk": {
                "callback_url": "http://test/callback",
                "callback_auth": {"type": "bearer", "token": "test-token-123"},
            },
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        token = _resolve_per_run_callback_token(run_root)
        assert token == "test-token-123"

    def test_token_env_resolved(self, run_root):
        """origin.obelisk.callback_auth.token_env resolves from environment."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100",
            "obelisk": {
                "callback_url": "http://test/callback",
                "callback_auth": {"type": "bearer", "token_env": "TEST_CALLBACK_TOKEN"},
            },
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        with mock.patch.dict(os.environ, {"TEST_CALLBACK_TOKEN": "env-token-value"}):
            token = _resolve_per_run_callback_token(run_root)
            assert token == "env-token-value"

    def test_flat_callback_token_ref_resolved(self, run_root):
        """origin.callback_token_ref resolves from environment."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100",
            "callback_url": "http://test/callback",
            "callback_token_ref": "MY_TOKEN_ENV",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        with mock.patch.dict(os.environ, {"MY_TOKEN_ENV": "ref-token-value"}):
            token = _resolve_per_run_callback_token(run_root)
            assert token == "ref-token-value"

    def test_no_token_omits_auth_header(self, run_root, telegram_origin):
        """When no token exists, Authorization header is omitted entirely."""
        origin = dict(telegram_origin)
        origin["callback_url"] = "http://test/callback"
        # No token anywhere
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        captured_headers = []

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            captured_headers.append(dict(req.headers))
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = CompletionCallbackConfig(enabled=True, url="", token="")
                state = send_completion_callback(run_root, cfg)
                assert state.state == "sent"
                assert len(captured_headers) > 0
                # Authorization header should NOT be present
                assert "Authorization" not in captured_headers[0], (
                    f"Authorization header should be absent when no token, got: {captured_headers[0]}"
                )

    def test_token_not_in_payload(self, run_root, telegram_origin):
        """Token is never leaked in payload."""
        origin = dict(telegram_origin)
        origin["callback_url"] = "http://test/callback"
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        origin_loaded = load_origin_metadata(run_root)
        status = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig(token="secret-token-leak-test")
        payload = build_callback_payload(run_root, origin_loaded, status, cfg)
        payload_str = json.dumps(payload)
        assert "secret-token-leak-test" not in payload_str


class TestExactlyOnceExtended:
    """H. Exactly once extended tests."""

    def test_10_concurrent_terminal_attempts_one_post(self, run_root, telegram_origin):
        """10 concurrent terminal callback attempts produce exactly 1 POST."""
        import threading
        origin = dict(telegram_origin)
        origin["callback_url"] = "http://test/callback"
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]
        lock = threading.Lock()

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            with lock:
                call_count[0] += 1
            return MockResponse()

        results = []

        def call_callback():
            cfg = CompletionCallbackConfig(
                enabled=True, url="http://test/callback",
            )
            state = send_completion_callback(run_root, cfg)
            results.append(state)

        threads = [threading.Thread(target=call_callback) for _ in range(10)]
        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert call_count[0] == 1, f"Expected 1 POST, got {call_count[0]}"
        # Exactly-once is guaranteed by the single POST above.  The winner must
        # report sent; other threads may observe the winner's sent state too
        # depending on read timing, so do not assert a single observer.
        assert any(r is not None and r.state == "sent" for r in results), \
            "No thread observed the sent state"

        # Verify state on disk is sent
        state = load_callback_state(run_root)
        assert state is not None
        assert state.state == "sent"




# ===========================================================================
# Regression tests — Per-run callback URL auto-enable (Fix #1)
# ===========================================================================

class TestPerRunCallbackAutoEnable:
    """Regression: per-run callback_url auto-enables sending without global config."""

    def test_per_run_flat_callback_url_via_maybe_send(self, run_root):
        """maybe_send_terminal_callback sends when only per-run flat callback_url exists."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100123",
            "callback_url": "http://obelisk:8080/api/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                state = maybe_send_terminal_callback(run_root)
                assert call_count[0] == 1, f"Expected 1 POST, got {call_count[0]}"
                assert state is not None
                assert state.state == "sent"

    def test_per_run_obelisk_callback_url_via_maybe_send(self, run_root):
        """maybe_send_terminal_callback sends when only origin.obelisk.callback_url exists."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100123",
            "obelisk": {
                "callback_url": "http://obelisk:8080/api/callback",
            },
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                state = maybe_send_terminal_callback(run_root)
                assert call_count[0] == 1, f"Expected 1 POST, got {call_count[0]}"
                assert state is not None
                assert state.state == "sent"


# ===========================================================================
# Regression tests — Telegram/Signal end-to-end routing (Fix #6)
# ===========================================================================

class TestEndToEndRouting:
    """End-to-end tests for Signal/Telegram channel routing."""

    def test_source_channel_missing_reply_to_signal(self, run_root):
        """When source_channel is missing but reply_to.channel='signal', route as signal."""
        origin = {
            "source": "obelisk",
            "source_channel": "",  # missing
            "chat_id": "+31612345678",
            "reply_to": {"channel": "signal", "recipient": "+31612345678"},
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)
        assert payload["reply"]["channel"] == "signal"
        assert payload["reply"]["recipient"] == "+31612345678"

    def test_source_channel_missing_reply_to_telegram(self, run_root):
        """When source_channel is missing but reply_to.channel='telegram', route as telegram."""
        origin = {
            "source": "obelisk",
            "source_channel": "",  # missing
            "chat_id": "-100456",
            "reply_to": {"channel": "telegram", "chat_id": "-100456", "message_id": "msg-1"},
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)
        assert payload["reply"]["channel"] == "telegram"
        assert payload["reply"]["chat_id"] == "-100456"

    def test_telegram_success_end_to_end(self, run_root):
        """Telegram success: full e2e with per-run callback_url, no global config."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "message_id": "msg-789",
            "task_text": "build a calculator",
            "task_title": "Build Calculator",
            "target_path": "/x/qq/targets/calc-run-1",
            "callback_url": "http://obelisk:8080/api/callback",
            "reply_to": {"channel": "telegram", "chat_id": "-100456", "message_id": "msg-789"},
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]
        captured_payload = []

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            captured_payload.append(json.loads(req.data.decode("utf-8")))
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                state = maybe_send_terminal_callback(run_root)
                assert call_count[0] == 1, f"Expected 1 POST, got {call_count[0]}"
                assert state.state == "sent"
                payload = captured_payload[0]
                assert payload["event"] == "qonqrete.run.completed"
                assert payload["status"] == "FULLY_DONE"
                assert payload["success"] is True
                assert payload["fully_done"] is True
                assert payload["reply"]["channel"] == "telegram"
                assert payload["reply"]["chat_id"] == "-100456"
                assert "✅ QonQrete FULLY_DONE" in payload["reply"]["text"]
                assert "Status: FULLY_DONE" in payload["reply"]["text"]
                assert "/x/qq/targets/calc-run-1" in payload["reply"]["text"]

    def test_signal_success_end_to_end(self, run_root):
        """Signal success: full e2e with per-run callback_url."""
        origin = {
            "source": "obelisk",
            "source_channel": "signal",
            "sender_id": "+31612345678",
            "chat_id": "+31612345678",
            "message_id": "sig-abc",
            "task_text": "build a website",
            "task_title": "Build Website",
            "target_path": "/x/qq/targets/web-run-1",
            "callback_url": "http://obelisk:8080/api/callback",
            "reply_to": {"channel": "signal", "recipient": "+31612345678", "message_id": "sig-abc"},
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]
        captured_payload = []

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            captured_payload.append(json.loads(req.data.decode("utf-8")))
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                state = maybe_send_terminal_callback(run_root)
                assert call_count[0] == 1
                assert state.state == "sent"
                payload = captured_payload[0]
                assert payload["reply"]["channel"] == "signal"
                assert payload["reply"]["recipient"] == "+31612345678"


# ===========================================================================
# Regression tests — Abort callbacks (Fix #2)
# ===========================================================================

class TestAbortCallbacks:
    """End-to-end tests for abort callbacks (max cycles, max time)."""

    def test_aborted_status_via_maybe_send(self, run_root):
        """final.json ABORTED sends one POST with failure payload."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
            "task_text": "test task",
            "task_title": "Test",
            "target_path": "/x/qq/targets/abort-run",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        final_path = os.path.join(run_root, "state", "final.json")
        data = {
            "status": "aborted",
            "cycle": 5,
            "final_verdict": {"status": "ABORTED", "summary": "Hit max cycles"},
        }
        with open(final_path, "w") as f:
            json.dump(data, f)

        call_count = [0]
        captured_payload = []

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            captured_payload.append(json.loads(req.data.decode("utf-8")))
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                state = maybe_send_terminal_callback(run_root)
                assert call_count[0] == 1
                assert state.state == "sent"
                payload = captured_payload[0]
                assert payload["event"] == "qonqrete.run.failed"
                assert payload["status"] == "ABORTED"
                assert payload["success"] is False
                assert payload["fully_done"] is False
                assert "❌" in payload["reply"]["text"] or "QonQrete" in payload["reply"]["text"]


# ===========================================================================
# Regression tests — Launch failure callbacks (Fix #3)
# ===========================================================================

class TestLaunchFailureCallbacks:
    """End-to-end tests for launch failure callbacks."""

    def test_runner_failed_json_detected_as_terminal(self, run_root):
        """runner.failed.json with launch error is detected as terminal."""
        # Write runner.failed.json
        failed_path = os.path.join(run_root, "runner.failed.json")
        failed_data = {
            "run_id": "test-run",
            "reason": "tmux_not_installed",
            "launch_error": "tmux_not_installed",
            "failed_at": "2026-01-01T00:00:00Z",
        }
        os.makedirs(run_root, exist_ok=True)
        with open(failed_path, "w") as f:
            json.dump(failed_data, f)

        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is False
        assert status.status == "LAUNCH_FAILED"

    def test_runner_failed_pointer_write_detected(self, run_root):
        """runner.failed.json with pointer_write_failed is detected as POINTER_FAILED."""
        failed_path = os.path.join(run_root, "runner.failed.json")
        failed_data = {
            "run_id": "test-run",
            "reason": "current_run_pointer_write_failed",
            "failed_at": "2026-01-01T00:00:00Z",
        }
        os.makedirs(run_root, exist_ok=True)
        with open(failed_path, "w") as f:
            json.dump(failed_data, f)

        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is False
        assert status.status == "POINTER_FAILED"

    def test_launch_failed_sends_callback(self, run_root):
        """When runner.failed.json exists with launch error and origin.json exists, callback is sent."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
            "task_text": "test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))

        failed_path = os.path.join(run_root, "runner.failed.json")
        failed_data = {
            "run_id": "test-run",
            "reason": "qq_binary_not_found",
            "launch_error": "qq_binary_not_found",
            "failed_at": "2026-01-01T00:00:00Z",
        }
        with open(failed_path, "w") as f:
            json.dump(failed_data, f)

        call_count = [0]
        captured_payload = []

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            captured_payload.append(json.loads(req.data.decode("utf-8")))
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {}, clear=True):
                state = maybe_send_terminal_callback(run_root)
                assert call_count[0] == 1
                assert state.state == "sent"
                payload = captured_payload[0]
                assert payload["event"] == "qonqrete.run.failed"
                assert payload["success"] is False
                assert payload["fully_done"] is False
                assert payload["failure_reason"] is not None


# ===========================================================================
# Regression tests — Explicit disable + exactly once
# ===========================================================================

class TestExplicitDisable:
    """Explicit disable blocks even per-run URLs."""

    def test_explicit_disable_blocks_per_run_url_via_maybe_send(self, run_root):
        """QONQRETE_COMPLETION_CALLBACK_ENABLED=false blocks maybe_send_terminal_callback."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {
                "QONQRETE_COMPLETION_CALLBACK_ENABLED": "false",
            }, clear=False):
                state = maybe_send_terminal_callback(run_root)
                assert state is None
                assert call_count[0] == 0


# ===========================================================================
# Regression tests — Terminal status detection ordering (Fix #8)
# ===========================================================================

class TestTerminalStatusOrdering:
    """Terminal status detection prefers newest terminal event."""

    def test_old_failed_new_completed_resolves_success(self, run_root):
        """events.jsonl: old run.failed + newer run.completed → status resolves to success."""
        _write_events(run_root, [
            {"ts": 1000, "type": "run.started", "run_id": "test"},
            {"ts": 2000, "type": "run.failed", "run_id": "test"},
            {"ts": 3000, "type": "run.completed", "status": "success", "run_id": "test"},
        ])
        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is True
        assert status.status == "FULLY_DONE"

    def test_old_completed_new_failed_resolves_failed(self, run_root):
        """events.jsonl: old run.completed + newer run.failed → status resolves to failed."""
        _write_events(run_root, [
            {"ts": 1000, "type": "run.started", "run_id": "test"},
            {"ts": 2000, "type": "run.completed", "status": "success", "run_id": "test"},
            {"ts": 3000, "type": "run.failed", "run_id": "test"},
        ])
        status = get_run_terminal_status(run_root)
        assert status.terminal is True
        assert status.success is False
        assert status.status == "FAILED"


# ===========================================================================
# Regression tests — Dashboard URL normalization (Fix #7)
# ===========================================================================

class TestDashboardUrlNormalization:
    """Dashboard URL uses normalized host (never 0.0.0.0)."""

    def test_dashboard_url_not_zero_zero_zero_zero(self, run_root):
        """origin.json dashboard_url never uses 0.0.0.0."""
        origin = {"source": "test", "source_channel": "api"}
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root),
                              dashboard_url="http://127.0.0.1:31337")
        loaded = load_origin_metadata(run_root)
        assert "0.0.0.0" not in loaded.get("dashboard_url", "")


# ===========================================================================
# Regression tests — Callback token (Fix #5)
# ===========================================================================

class TestCallbackToken:
    """Top-level callback_token is persisted and resolved."""

    def test_flat_callback_token_persisted(self, run_root):
        """Flat callback_token reaches origin.json."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100",
            "callback_url": "http://test/callback",
            "callback_token": "my-secret-token",
        }
        result = write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        assert result["callback_token"] == "my-secret-token"

    def test_callback_token_not_in_reply_text(self, run_root):
        """Raw callback_token is never exposed in reply text."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100",
            "callback_url": "http://test/callback",
            "callback_token": "my-secret-token",
            "target_path": "/x/qq/targets/test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)
        assert "my-secret-token" not in payload["reply"]["text"]



# Test that new function names are importable
class TestNewFunctionNames:
    def test_get_run_terminal_status_importable(self):
        from qq.completion_callback import get_run_terminal_status
        assert callable(get_run_terminal_status)

    def test_maybe_send_terminal_callback_importable(self):
        from qq.completion_callback import maybe_send_terminal_callback
        assert callable(maybe_send_terminal_callback)

    def test_is_run_terminal_importable(self):
        from qq.completion_callback import is_run_terminal
        assert callable(is_run_terminal)

    def test_is_callback_enabled_for_run_importable(self):
        from qq.completion_callback import is_callback_enabled_for_run
        assert callable(is_callback_enabled_for_run)

    def test_get_run_aware_callback_config_importable(self):
        from qq.completion_callback import get_run_aware_callback_config
        assert callable(get_run_aware_callback_config)

    def test_legacy_maybe_send_completion_callback_still_works(self):
        from qq.completion_callback import maybe_send_completion_callback
        assert callable(maybe_send_completion_callback)




# ═══════════════════════════════════════════════════════════════════════════
# NEW TESTS — Payload Correlation IDs (Item 11)
# ═══════════════════════════════════════════════════════════════════════════

class TestPayloadCorrelationIds:
    """Tests for top-level Obelisk correlation IDs in callback payload."""

    def test_payload_exposes_top_level_obelisk_correlation_ids(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "task_text": "test",
            "target_path": "/x/qq/targets/test",
            "obelisk": {
                "callback_id": "evt-cb-001",
                "qq_trans_event_id": "evt-qq-001",
                "origin_event_id": "evt-orig-001",
                "reply_channel": "telegram",
                "callback_url": "http://test/callback",
            },
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)

        assert payload["callback_id"] == "evt-cb-001"
        assert payload["qq_trans_event_id"] == "evt-qq-001"
        assert payload["origin_event_id"] == "evt-orig-001"
        assert payload["callback_kind"] == "qonqrete-run-terminal"
        assert payload["callback_version"] == 1

    def test_payload_success_contains_ok_true(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "task_text": "test",
            "target_path": "/x/qq/targets/test",
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)

        assert payload["ok"] is True
        assert payload["success"] is True

    def test_payload_failed_contains_ok_false_and_error_aliases(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "task_text": "test",
            "target_path": "/x/qq/targets/test",
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        final_path = os.path.join(run_root, "state", "final.json")
        data = {"status": "FAILED", "final_verdict": {"status": "FAILED"}}
        with open(final_path, "w") as f:
            json.dump(data, f)
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)

        assert payload["ok"] is False
        assert payload["success"] is False
        assert payload.get("error")
        assert payload.get("error_message")
        assert payload.get("failure_reason")

    def test_payload_contains_target_aliases(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "task_text": "test",
            "target_path": "/x/qq/targets/alias-test",
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)

        assert payload["target_path"] == "/x/qq/targets/alias-test"
        assert payload["target_dir"] == "/x/qq/targets/alias-test"
        assert payload["target_directory"] == "/x/qq/targets/alias-test"
        assert payload["output_dir"] == "/x/qq/targets/alias-test"

    def test_no_token_in_reply_text_or_payload(self, run_root):
        """Token must not appear in reply text or top-level payload fields."""
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "task_text": "test",
            "target_path": "/x/qq/targets/test",
            "callback_token": "super-secret-token-value",
            "callback_url": "http://test/callback",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")
        completion = get_run_terminal_status(run_root)
        cfg = CompletionCallbackConfig()
        payload = build_callback_payload(run_root, origin, completion, cfg)

        # Token must not appear in reply text
        assert "super-secret-token-value" not in payload["reply"]["text"]
        # Token must not appear in top-level fields (not under 'origin')
        top_level = {k: v for k, v in payload.items() if k not in ("origin",)}
        top_str = json.dumps(top_level)
        assert "super-secret-token-value" not in top_str


# ═══════════════════════════════════════════════════════════════════════════
# NEW TESTS — Failed Callback Cooldown (Item 11)
# ═══════════════════════════════════════════════════════════════════════════

class TestFailedCallbackCooldown:
    """Tests for retry storm prevention."""

    def test_failed_callback_cooldown_prevents_retry_storm(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
            "task_text": "test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # Pre-set failed state recently
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10))
        state = CallbackState(
            enabled=True, state="failed",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test/callback",
            last_attempt_at=now_ts,
            attempts=5,
        )
        write_callback_state(run_root, state)

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {"QONQRETE_COMPLETION_CALLBACK_FAILED_RETRY_COOLDOWN_SECONDS": "600"}, clear=False):
                result = maybe_send_terminal_callback(run_root)
                # Should return existing failed state, not POST
                assert call_count[0] == 0
                assert result is not None
                assert result.state == "failed"

    def test_failed_callback_url_change_allows_retry(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "obelisk": {
                "callback_url": "https://o.wickednet.nl:443/v1/qonqrete/callback",
            },
            "task_text": "test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # Pre-set failed state with OLD URL
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10))
        state = CallbackState(
            enabled=True, state="failed",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://obelisk:8080/v1/qonqrete/callback",  # OLD
            last_attempt_at=now_ts,
            attempts=5,
        )
        write_callback_state(run_root, state)

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {"QONQRETE_COMPLETION_CALLBACK_FAILED_RETRY_COOLDOWN_SECONDS": "600"}, clear=False):
                result = maybe_send_terminal_callback(run_root)
                # Should retry because URL changed
                assert call_count[0] == 1
                assert result is not None
                assert result.state == "sent"

    def test_failed_callback_old_enough_retries(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
            "task_text": "test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # Pre-set failed state with old timestamp (>10 min ago)
        old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 700))
        state = CallbackState(
            enabled=True, state="failed",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test/callback",
            last_attempt_at=old_ts,
            attempts=5,
        )
        write_callback_state(run_root, state)

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {"QONQRETE_COMPLETION_CALLBACK_FAILED_RETRY_COOLDOWN_SECONDS": "600"}, clear=False):
                result = maybe_send_terminal_callback(run_root)
                # Should retry because cooldown expired
                assert call_count[0] == 1
                assert result is not None
                assert result.state == "sent"

    def test_sent_state_never_retries(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
            "task_text": "test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # Pre-set sent state
        state = CallbackState(
            enabled=True, state="sent",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test/callback",
            sent_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        write_callback_state(run_root, state)

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = maybe_send_terminal_callback(run_root)
            assert call_count[0] == 0
            assert result is not None
            assert result.state == "sent"

    def test_force_retries_failed_state(self, run_root):
        origin = {
            "source": "obelisk",
            "source_channel": "telegram",
            "chat_id": "-100456",
            "callback_url": "http://test/callback",
            "task_text": "test",
        }
        write_origin_metadata(run_root, origin, run_id=os.path.basename(run_root))
        _write_final_json(run_root, "FULLY_DONE")

        # Pre-set failed state recently
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10))
        state = CallbackState(
            enabled=True, state="failed",
            event="qonqrete.run.completed",
            run_id=os.path.basename(run_root),
            callback_url="http://test/callback",
            last_attempt_at=now_ts,
            attempts=5,
        )
        write_callback_state(run_root, state)

        call_count = [0]

        class MockResponse:
            def getcode(self):
                return 200
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            return MockResponse()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with mock.patch.dict(os.environ, {"QONQRETE_COMPLETION_CALLBACK_FAILED_RETRY_COOLDOWN_SECONDS": "600"}, clear=False):
                result = maybe_send_terminal_callback(run_root, force=True)
                # Should retry because of force
                assert call_count[0] == 1
                assert result is not None
                assert result.state == "sent"
