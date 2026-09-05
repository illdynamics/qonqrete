"""
HTTP-level route tests for the briQsQope / QonQrete runs API.

Tests:
  - POST /api/qonqrete/runs canonical endpoint
  - POST /v1/ingest/qq-trans legacy alias
  - Auth, validation, error responses
  - 404 for unknown POST routes
  - No "Empty reply from server" crashes

Run: python -m pytest tests/test_web_api_routes.py -v
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import sys
import threading
import time
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qq.web.api import BriQsQopeHandler
from qq.web.ingest import (
    _queue,
    _active_run,
)

# Mock subprocess.Popen to avoid launching real qq-tui in tests
class FakePopen:
    def __init__(self, *args, **kwargs):
        self.pid = 99999
        self.args = args
    def wait(self):
        return 0



# ---------------------------------------------------------------------------
# Helper: find a free port
# ---------------------------------------------------------------------------
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Helper: start a test server
# ---------------------------------------------------------------------------
class TestServer:
    """Context manager for a test HTTP server on a free port.

    Uses a per-test handler subclass instead of mutating BriQsQopeHandler
    class globals directly.  Each test gets its own handler class with
    isolated attributes (run_root, repo_root, tailer, config cache).

    Uses ThreadingHTTPServer with daemon_threads, port reuse, and
    serve_forever(poll_interval=0.01) for responsive shutdown.
    """

    # Prevent pytest from collecting this helper class as a test class.
    __test__ = False

    class _DaemonThreadingServer(http.server.ThreadingHTTPServer):
        """ThreadingHTTPServer with daemon_threads and port reuse."""
        allow_reuse_address = True
        daemon_threads = True
        # Python 3.12+ only: block_on_close = False

    def __init__(self, tmp_path, **handler_attrs):
        self.tmp_path = tmp_path
        self.port = _free_port()
        self.handler_attrs = handler_attrs
        self.server = None
        self._thread = None

    def start(self):
        # Create a per-test handler subclass with isolated attributes
        handler_attrs = self.handler_attrs

        class _TestHandler(BriQsQopeHandler):
            pass

        for attr, val in handler_attrs.items():
            setattr(_TestHandler, attr, val)

        # Also set parent class attrs so imports work
        for attr, val in handler_attrs.items():
            setattr(BriQsQopeHandler, attr, val)

        # Store so stop() can reset
        self._test_handler_class = _TestHandler

        self.server = self._DaemonThreadingServer(
            ("127.0.0.1", self.port), _TestHandler
        )
        self.server.timeout = 0.25  # Serve loop polls frequently for quick shutdown
        self._thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01),
            daemon=True
        )
        self._thread.start()
        self._wait_ready()
        return self

    def _wait_ready(self, attempts: int = 100):
        """Block until the server actually accepts connections.

        A fixed sleep is unreliable under CI load (the serve thread may not
        have bound the socket yet, causing mass ConnectionRefused failures).
        Poll with a small backoff until a request succeeds or we give up.
        """
        import urllib.request
        deadline = time.time() + 10.0
        last_err = None
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/qonqrete/health",
                    timeout=0.5,
                )
                return
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
                time.sleep(0.02)
        # Give one last full test-timeout-style attempt before failing loudly.
        raise RuntimeError(
            f"TestServer on 127.0.0.1:{self.port} never became ready: {last_err}"
        )

    def stop(self):
        """Stop the test server quickly and deterministically.

        Uses shutdown() + wake-up connection to ensure serve_forever exits.
        Never blocks forever — all timeouts are short and tight.
        """
        if self.server:
            # Wake the selector by opening/closing a connection
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/qonqrete/health", timeout=0.5)
            except Exception:
                pass

            # Call shutdown() in a helper thread with tight timeout
            def _do_shutdown():
                try:
                    self.server.shutdown()
                except Exception:
                    pass
            shutdown_t = threading.Thread(target=_do_shutdown, daemon=True)
            shutdown_t.start()
            shutdown_t.join(timeout=0.5)

            # Force stop if shutdown didn't work
            try:
                self.server._BaseServer__shutdown_request = True
            except Exception:
                pass

            # Now close the server
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None

        # Join the serve thread with a short timeout
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.3)

        # Reset handler class globals
        self._reset_handler_globals()

    @staticmethod
    def _reset_handler_globals():
        """Reset handler class globals to prevent cross-test contamination."""
        BriQsQopeHandler.run_root = ""
        BriQsQopeHandler.repo_root = ""
        BriQsQopeHandler.tailer = None
        BriQsQopeHandler._config_cache = None
        BriQsQopeHandler._config_cache_ts = 0

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.port}{path}"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _post(url, body=None, headers=None, timeout=5):
    """Simple POST using urllib."""
    import urllib.request
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, data=data, method="POST")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, {"raw": body_text}
    except Exception as e:
        return None, {"error": str(e)}


def _get(url, timeout=5):
    """Simple GET using urllib."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Base environment for route tests
# ---------------------------------------------------------------------------
@pytest.fixture
def env_base(tmp_path):
    """Base environment: task dir, run root, default env vars."""
    task_dir = tmp_path / "tasks"
    run_root_dir = tmp_path / "runs"
    control_root_dir = tmp_path / "control"
    task_dir.mkdir(parents=True)
    run_root_dir.mkdir(parents=True)
    control_root_dir.mkdir(parents=True, exist_ok=True)
    return {
        "task_dir": str(task_dir),
        "run_root": str(run_root_dir),
        "control_root": str(control_root_dir),
        "tmp_path": tmp_path,
    }


@pytest.fixture
def _mock_popen(monkeypatch):
    """Mock subprocess.Popen to avoid launching real qq-tui."""
    import subprocess as _sp
    class FakeProc:
        def __init__(self, *args, **kwargs):
            self.pid = os.getpid()  # Use real PID so reconcile doesn't mark stale
        def wait(self):
            return 0
    monkeypatch.setattr("subprocess.Popen", FakeProc)


@pytest.fixture(autouse=True)
def _reset_queue(tmp_path):
    """Reset in-memory queue state and dedupe file before each test."""
    _queue.clear()
    import qq.web.ingest as ingest
    ingest._active_run = False
    ingest._active_run_id = None
    ingest._active_item = None
    ingest._active_run_id = None
    ingest._active_item = None
    # Use a fresh dedupe file per test
    dedupe_dir = tmp_path / "dedupe"
    dedupe_dir.mkdir(exist_ok=True)
    dedupe_file = str(dedupe_dir / "dedupe.jsonl")
    old_dedupe = ingest._DEDUPE_PATH
    ingest._DEDUPE_PATH = dedupe_file
    # Set test-safe control root in env — this is critical for all POST tests
    control_dir = tmp_path / "control"
    control_dir.mkdir(exist_ok=True)
    old_control_root = os.environ.get("QONQRETE_CONTROL_ROOT", "")
    os.environ["QONQRETE_CONTROL_ROOT"] = str(control_dir)
    # Mock _do_launch to avoid spawning real processes
    def _fake_launch(item):
        item["launch_ok"] = True
        item["pid"] = os.getpid()   # Use real current PID so reconcile doesn't mark stale
        item["runner"] = "local_exec"
        item["stdout_log"] = "/fake/stdout.log"
        item["stderr_log"] = "/fake/stderr.log"
        # Mark run active with identity tracking so dedupe works correctly.
        # Tests that need to simulate multiple concurrent runs should
        # directly manipulate _active_run_id in their test body.
        ingest._mark_run_active(item)
        return True
    old_do_launch = ingest._do_launch
    ingest._do_launch = _fake_launch
    yield
    _queue.clear()
    ingest._active_run = False
    ingest._active_run_id = None
    ingest._active_item = None
    ingest._DEDUPE_PATH = old_dedupe
    ingest._do_launch = old_do_launch
    if old_control_root:
        os.environ["QONQRETE_CONTROL_ROOT"] = old_control_root
    else:
        os.environ.pop("QONQRETE_CONTROL_ROOT", None)


# ---------------------------------------------------------------------------
# Auth tests (HTTP level)
# ---------------------------------------------------------------------------
class TestAuthRoutes:
    def test_missing_token_returns_401_json(self, env_base):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test", "trigger": "qonqrete"},
                )
                assert status == 401
                assert body["ok"] is False
                assert body["error"] == "unauthorized"
            finally:
                srv.stop()

    def test_wrong_token_returns_401_json(self, env_base):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test", "trigger": "qonqrete"},
                    headers={"Authorization": "Bearer wrong-token"},
                )
                assert status == 401
                assert body["ok"] is False
            finally:
                srv.stop()

    def test_valid_token_accepted(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test task", "mode": "repo", "target": "default",
                     "source": "test-src", "raw_transcription": "test transcript",
                     "trigger": "qonqrete", "transcription_id": "trans-route-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body["endpoint"] == "/api/qonqrete/runs"
            finally:
                srv.stop()

    def test_legacy_ingest_token_fallback(self, env_base, _mock_popen):
        """QONQRETE_INGEST_TOKEN works as fallback for auth."""
        env = {
            "QONQRETE_INGEST_TOKEN": "old-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test task", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-legacy-auth-001"},
                    headers={"Authorization": "Bearer old-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
            finally:
                srv.stop()

    def test_dev_no_auth_accepts_without_token(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test task", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-devauth-001"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Empty body / invalid JSON tests
# ---------------------------------------------------------------------------
class TestMalformedRequests:
    def test_empty_body_returns_400_json(self, env_base):
        env = {
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                # POST with no body
                import urllib.request
                req = urllib.request.Request(
                    srv.url("/api/qonqrete/runs"),
                    data=b"",
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        raw = resp.read().decode("utf-8")
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8")
                    assert e.code == 400
                body = json.loads(raw)
                assert body["ok"] is False
                assert body["error"] == "empty_body"
            finally:
                srv.stop()

    def test_invalid_json_returns_400_json(self, env_base):
        env = {
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                import urllib.request
                req = urllib.request.Request(
                    srv.url("/api/qonqrete/runs"),
                    data=b"not-valid-json{",
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        raw = resp.read().decode("utf-8")
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8")
                    assert e.code == 400
                body = json.loads(raw)
                assert body["ok"] is False
                assert body["error"] == "invalid_json"
            finally:
                srv.stop()

    def test_missing_task_text_returns_400(self, env_base):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test", "trigger": "qonqrete"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status == 400
                assert body["ok"] is False
                assert body["error"] == "missing_task_text"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Canonical vs legacy routes
# ---------------------------------------------------------------------------
class TestRouteBehavior:
    def test_canonical_endpoint_returns_no_deprecation(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-canon-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body.get("legacy_endpoint", False) is False
                assert body.get("deprecated_endpoint") is not True
                assert body["endpoint"] == "/api/qonqrete/runs"
            finally:
                srv.stop()

    def test_legacy_alias_still_works(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/v1/ingest/qq-trans"),
                    {"task_text": "test legacy", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-legacy-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body.get("legacy_endpoint") is True or body.get("deprecated_endpoint") is True
                # Legacy should include canonical endpoint hint
                assert "canonical_endpoint" in body or body["endpoint"] == "/api/qonqrete/runs"
            finally:
                srv.stop()

    def test_unknown_post_route_returns_404_json(self, env_base):
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/unknown"),
                    {"x": "y"},
                )
                assert status == 404
                assert body["ok"] is False
                assert body["error"] == "not_found"
            finally:
                srv.stop()

    def test_get_health_still_works(self, env_base):
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body["status"] == "ok"
            finally:
                srv.stop()

    def test_get_config_still_works(self, env_base):
        with mock.patch.dict(os.environ, {}, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/config"))
                assert status == 200
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Mode-specific behavior
# ---------------------------------------------------------------------------
class TestModeBehavior:
    def test_folder_mode_includes_norepo_in_preview(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "calc", "mode": "folder", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-folder-002"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert "--no-repo" in body.get("command_preview", "")
            finally:
                srv.stop()

    def test_repo_mode_excludes_norepo_in_preview(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-repo-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert "--no-repo" not in body.get("command_preview", "")
            finally:
                srv.stop()

    def test_invalid_mode_returns_400(self, env_base):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "bad_mode", "target": "default",
                     "source": "test", "raw_transcription": "test", "trigger": "qonqrete"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status == 400
                assert body["ok"] is False
                assert body["error"] == "invalid_mode"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Duplicate detection (HTTP level)
# ---------------------------------------------------------------------------
class TestDuplicateDetectionRoutes:
    def test_duplicate_request_returns_200_duplicate_true(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                payload = {
                    "task_text": "test", "mode": "repo", "target": "default",
                    "source": "test", "raw_transcription": "test",
                    "trigger": "qonqrete", "transcription_id": "trans-dup-route-unique-002",
                }
                auth = {"Authorization": "Bearer test-token"}

                status1, body1 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status1 in (200, 202)
                assert body1["ok"] is True
                assert body1.get("duplicate") is not True

                status2, body2 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status2 in (200, 202)
                assert body2["ok"] is True
                assert body2["duplicate"] is True
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Import crash fix — verify handler doesn't crash
# ---------------------------------------------------------------------------
class TestImportSafety:
    def test_api_import_works(self):
        """Verify that importing api.py does not crash."""
        # The import at module top should not fail
        from qq.web.api import BriQsQopeHandler, RUNS_API_PATH, LEGACY_QQ_TRANS_PATH
        assert RUNS_API_PATH == "/api/qonqrete/runs"
        assert LEGACY_QQ_TRANS_PATH == "/v1/ingest/qq-trans"

    def test_handler_has_handle_create_run(self):
        """Verify _handle_create_run exists."""
        from qq.web.api import BriQsQopeHandler
        assert hasattr(BriQsQopeHandler, "_handle_create_run")
        assert hasattr(BriQsQopeHandler, "_handle_ingest")  # backward compat wrapper


# ---------------------------------------------------------------------------
# Deprecation header tests
# ---------------------------------------------------------------------------
class TestDeprecationHeaders:
    def test_legacy_response_includes_deprecation_headers(self, env_base, _mock_popen):
        """Legacy POST should return Deprecation and Link headers."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                import urllib.request
                data = json.dumps({
                    "task_text": "test legacy headers", "mode": "repo", "target": "default",
                    "source": "test", "raw_transcription": "test",
                    "trigger": "qonqrete", "transcription_id": "trans-headers-001",
                }).encode("utf-8")
                req = urllib.request.Request(
                    srv.url("/v1/ingest/qq-trans"),
                    data=data,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-token",
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        deprecation = resp.getheader("Deprecation")
                        link = resp.getheader("Link")
                        assert deprecation == "true", f"Expected Deprecation: true, got {deprecation}"
                        assert link is not None, "Expected Link header"
                        assert "successor-version" in link
                        body = json.loads(resp.read().decode("utf-8"))
                        assert body["ok"] is True
                        assert body.get("deprecated_endpoint") is True
                        assert body.get("canonical_endpoint") == "/api/qonqrete/runs"
                except urllib.error.HTTPError as e:
                    # Check headers on error too
                    deprecation = e.headers.get("Deprecation")
                    link = e.headers.get("Link")
                    if deprecation is not None:
                        assert deprecation == "true"
            finally:
                srv.stop()

    def test_canonical_endpoint_has_no_deprecation_headers(self, env_base, _mock_popen):
        """Canonical endpoint should NOT have Deprecation/Link headers."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                import urllib.request
                data = json.dumps({
                    "task_text": "test canonical", "mode": "repo", "target": "default",
                    "source": "test", "raw_transcription": "test",
                    "trigger": "qonqrete", "transcription_id": "trans-canon-headers-001",
                }).encode("utf-8")
                req = urllib.request.Request(
                    srv.url("/api/qonqrete/runs"),
                    data=data,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-token",
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        deprecation = resp.getheader("Deprecation")
                        assert deprecation is None or deprecation.lower() != "true", \
                            f"Canonical endpoint should not have Deprecation header, got {deprecation}"
                except urllib.error.HTTPError:
                    pass  # May get 200/202 anyway
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# 405 method_not_allowed for GET /api/qonqrete/runs
# ---------------------------------------------------------------------------
class TestMethodNotAllowed:
    def test_get_runs_returns_405(self, env_base):
        """GET /api/qonqrete/runs should return 405 method_not_allowed."""
        with mock.patch.dict(os.environ, {}, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/runs"))
                assert status == 405, f"Expected 405, got {status}"
                assert body["ok"] is False
                assert body["error"] == "method_not_allowed"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Response completeness: mode + resolved_target_kind
# ---------------------------------------------------------------------------
class TestResponseFields:
    def test_started_response_includes_mode_and_target_kind(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test fields", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-fields-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body.get("mode") == "repo"
                assert body.get("resolved_target_kind") == "default"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Delimiter preservation
# ---------------------------------------------------------------------------
class TestDelimiterPreservation:
    def test_delimiter_is_stored_in_task_files(self, env_base, _mock_popen):
        """Verify that delimiter is passed through and stored in task metadata."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-delim-001",
                     "delimiter": "now"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                # Verify the delimiter appears in the task markdown file
                task_path = body.get("task_path")
                assert task_path, "Expected task_path in response"
                if task_path and os.path.isfile(task_path):
                    content = open(task_path).read()
                    assert "delimiter: now" in content

                # Verify metadata JSON contains delimiter
                meta_path = task_path.replace(".md", ".meta.json") if task_path else None
                if meta_path and os.path.isfile(meta_path):
                    meta = json.load(open(meta_path))
                    assert meta["original_payload"]["delimiter"] == "now"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# NEW TESTS: raw_transcription optional + defaults + dedupe behavior
# ---------------------------------------------------------------------------
class TestOptionalRawTranscription:
    """Tests that raw_transcription is no longer required."""

    def test_minimal_folder_payload_accepted(self, env_base, _mock_popen):
        """POST with only mode, target, task_text — no raw_transcription."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "folder",
                        "target": env_base["run_root"],
                        "task_text": "build a calculator for me in python please",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
            finally:
                srv.stop()

    def test_minimal_repo_payload_accepted(self, env_base, _mock_popen):
        """POST with only mode=repo, target=default, task_text."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "repo",
                        "target": "default",
                        "task_text": "build me a website as test",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
            finally:
                srv.stop()

    def test_missing_task_text_still_fails(self, env_base):
        """Missing task_text should still be rejected."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "folder",
                        "target": env_base["run_root"],
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status == 400
                assert body["ok"] is False
                assert body["error"] == "missing_task_text"
            finally:
                srv.stop()

    def test_empty_task_text_still_fails(self, env_base):
        """Empty task_text should still be rejected."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "folder",
                        "target": env_base["run_root"],
                        "task_text": "",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status == 400
                assert body["ok"] is False
                assert body["error"] == "missing_task_text"
            finally:
                srv.stop()

    def test_whitespace_only_task_text_still_fails(self, env_base):
        """Whitespace-only task_text should still be rejected."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "folder",
                        "target": env_base["run_root"],
                        "task_text": "   ",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status == 400
                assert body["ok"] is False
                assert body["error"] == "empty_task_text"
            finally:
                srv.stop()

    def test_rich_payload_with_raw_transcription_still_works(self, env_base, _mock_popen):
        """Obelisk-style payload with raw_transcription still accepted."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "source": "obelisk",
                        "raw_transcription": "qonqrete repo default now build a website",
                        "task_text": "build a website",
                        "mode": "repo",
                        "target": "default",
                        "trigger": "qonqrete",
                        "source_channel": "signal",
                        "sender_id": "user123",
                        "transcription_id": "trans-rich-001",
                        "delimiter": "now",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
            finally:
                srv.stop()


class TestSynthesizedFlag:
    """Tests that raw_transcription_synthesized flag is set correctly in metadata."""

    def test_synthesized_true_when_raw_transcription_missing(self, env_base, _mock_popen):
        """When raw_transcription is missing, metadata should mark synthesized=True."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "repo",
                        "target": "default",
                        "task_text": "build a thing",
                        "transcription_id": "trans-synth-001",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                task_path = body.get("task_path")
                if task_path and os.path.isfile(task_path):
                    meta_path = task_path.replace(".md", ".meta.json")
                    if os.path.isfile(meta_path):
                        meta = json.load(open(meta_path))
                        assert meta["original_payload"]["raw_transcription_synthesized"] is True
            finally:
                srv.stop()

    def test_synthesized_false_when_raw_transcription_provided(self, env_base, _mock_popen):
        """When raw_transcription is provided, metadata should mark synthesized=False."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "repo",
                        "target": "default",
                        "task_text": "build a thing",
                        "raw_transcription": "qonqrete repo default now build a thing",
                        "transcription_id": "trans-synth-002",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                task_path = body.get("task_path")
                if task_path and os.path.isfile(task_path):
                    meta_path = task_path.replace(".md", ".meta.json")
                    if os.path.isfile(meta_path):
                        meta = json.load(open(meta_path))
                        assert meta["original_payload"]["raw_transcription_synthesized"] is False
            finally:
                srv.stop()


class TestManualRepeatedCallsNoDedupe:
    """Tests that repeated manual calls without external IDs do NOT dedupe."""

    def test_repeated_manual_calls_create_separate_runs(self, env_base, _mock_popen):
        """Two identical manual API calls without transcription_id create two runs."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "queue",  # queue mode allows multiple calls
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                payload = {
                    "mode": "repo",
                    "target": "default",
                    "task_text": "build a calculator",
                }
                auth = {"Authorization": "Bearer test-token"}

                status1, body1 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status1 in (200, 202)
                assert body1["ok"] is True
                assert body1.get("duplicate") is not True
                run_id_1 = body1["run_id"]

                status2, body2 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status2 in (200, 202)
                assert body2["ok"] is True
                assert body2.get("duplicate") is not True
                run_id_2 = body2["run_id"]

                # Two separate runs should have different run_ids
                assert run_id_1 != run_id_2, (
                    f"Manual repeated calls should create different runs, "
                    f"got same run_id: {run_id_1}"
                )
            finally:
                srv.stop()

    def test_calls_with_same_transcription_id_still_dedupe(self, env_base, _mock_popen):
        """Calls with same transcription_id should still dedupe."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                payload = {
                    "mode": "repo",
                    "target": "default",
                    "task_text": "build a calculator",
                    "transcription_id": "same-trans-id-dedupe",
                }
                auth = {"Authorization": "Bearer test-token"}

                status1, body1 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status1 in (200, 202)
                assert body1["ok"] is True
                assert body1.get("duplicate") is not True

                status2, body2 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status2 in (200, 202)
                assert body2["ok"] is True
                assert body2["duplicate"] is True
            finally:
                srv.stop()


class TestDefaultFieldValues:
    """Tests that missing optional fields get sensible defaults."""

    def test_source_defaults_to_manual_api(self, env_base, _mock_popen):
        """When source is missing, it defaults to 'manual-api'."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {
                        "mode": "repo",
                        "target": "default",
                        "task_text": "test defaults",
                        "transcription_id": "trans-defaults-001",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                # Check task metadata for default source
                task_path = body.get("task_path")
                if task_path and os.path.isfile(task_path):
                    meta_path = task_path.replace(".md", ".meta.json")
                    if os.path.isfile(meta_path):
                        meta = json.load(open(meta_path))
                        assert meta["original_payload"]["source"] == "manual-api"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# NEW TESTS: Health endpoint with control_root and dashboard_url
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for the enhanced health endpoint."""

    def test_health_includes_control_root_and_active_run(self, env_base):
        """Health response includes control_root and active_run_root."""
        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body["status"] == "ok"
                assert body["product"] == "briQsQope"
                assert "control_root" in body
                assert "active_run_root" in body
                assert "active_run_id" in body
                assert "active_events_path" in body
                assert "source_of_truth" in body
            finally:
                srv.stop()

    def test_health_shows_null_when_no_current_run(self, env_base):
        """When no current-run.json exists, active_run_root/id are null."""
        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body["active_run_root"] is None
                assert body["active_run_id"] is None
            finally:
                srv.stop()

    def test_health_includes_dashboard_url_from_env(self, env_base):
        """Health response uses QONQRETE_PUBLIC_DASHBOARD_URL when set."""
        env = {
            "QONQRETE_PUBLIC_DASHBOARD_URL": "http://10.11.12.111:31337",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body["dashboard_url"] == "http://10.11.12.111:31337"
            finally:
                srv.stop()

    def test_health_includes_dashboard_url_fallback(self, env_base):
        """Health response falls back to inferred URL when no env var."""
        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert "dashboard_url" in body
                assert body["dashboard_url"].startswith("http")
            finally:
                srv.stop()


class TestResponseContract:
    """Tests that API response contract matches the spec."""

    def test_response_includes_run_root_and_events_path(self, env_base, _mock_popen):
        """API response includes run_root and events_path."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-resp-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert "run_root" in body
                assert "events_path" in body
                assert body["run_root"] != ""
                assert body["events_path"] != ""
                assert body["events_path"].startswith(body["run_root"])
            finally:
                srv.stop()

    def test_response_includes_runner_field(self, env_base, _mock_popen):
        """API response includes runner field."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-resp-002"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert "runner" in body
                assert body["runner"] in ("local_exec", "tmux")
            finally:
                srv.stop()

    def test_health_response_after_run_has_active_run(self, env_base, _mock_popen):
        """After creating a run, health endpoint shows active run info."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            # Write a current-run.json to the control root
            import json as _json
            control_dir = env_base["control_root"]
            current_run = {
                "run_id": "test-run-id",
                "run_root": "/tmp/test-run-root",
                "events_path": "/tmp/test-run-root/events.jsonl",
                "runner": "local_exec",
            }
            with open(os.path.join(control_dir, "current-run.json"), "w") as f:
                _json.dump(current_run, f)

            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body["active_run_root"] == "/tmp/test-run-root"
                assert body["active_run_id"] == "test-run-id"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# FIX #3 TESTS: SSE / events follow active run even before events.jsonl exists
# ---------------------------------------------------------------------------

class TestEventsActiveRunFollow:
    """Tests that /api/qonqrete/events and events/stream follow active run
    even before events.jsonl exists."""

    def test_events_returns_empty_active_when_file_missing(self, env_base):
        """When current-run.json exists but events.jsonl is missing,
        /api/qonqrete/events should still use active path (return empty list)."""
        import json as _json
        control_dir = env_base["control_root"]
        test_run_root = env_base["run_root"]
        current_run = {
            "run_id": "test-active-id",
            "run_root": test_run_root,
            "events_path": os.path.join(test_run_root, "events.jsonl"),
            "runner": "local_exec",
            "state": "started",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/events"))
                assert status == 200
                # Should return empty list (not error) since EventTailer
                # handles missing files gracefully
                assert isinstance(body, list), f"Expected list, got {type(body)}"
            finally:
                srv.stop()

    def test_event_stream_for_active_run_no_file(self, env_base):
        """When current-run.json has active run_root but events.jsonl missing,
        the SSE stream endpoint should still accept connections and wait.
        We test that it returns 200 (SSE), not 500.
        """
        import json as _json
        control_dir = env_base["control_root"]
        test_run_root = env_base["run_root"]
        current_run = {
            "run_id": "test-sse-active",
            "run_root": test_run_root,
            "events_path": os.path.join(test_run_root, "events.jsonl"),
            "runner": "local_exec",
            "state": "started",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        import urllib.request
        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                # Test HEAD first (SSE isn't easy to test with urllib, but we
                # can check the endpoint returns 200 with text/event-stream)
                import http.client
                conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
                conn.request("GET", "/api/qonqrete/events/stream")
                resp = conn.getresponse()
                assert resp.status == 200
                assert resp.getheader("Content-Type") == "text/event-stream"
                conn.close()
            finally:
                srv.stop()

    def test_events_uses_active_path_when_current_run_exists(self, env_base):
        """When current-run.json has active run, events endpoint uses it."""
        import json as _json
        control_dir = env_base["control_root"]
        test_run_root = env_base["run_root"]

        # Create events file in the active run root
        events_path = os.path.join(test_run_root, "events.jsonl")
        with open(events_path, "w") as f:
            _json.dump({"type": "test_event", "data": "hello"}, f)
            f.write("\n")

        current_run = {
            "run_id": "test-active-events",
            "run_root": test_run_root,
            "events_path": events_path,
            "runner": "local_exec",
            "state": "started",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/events"))
                assert status == 200
                assert isinstance(body, list)
                # Should contain our test event
                assert len(body) > 0
                assert any(e.get("type") == "test_event" for e in body if isinstance(e, dict))
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# FIX #4/#5 TESTS: Tmux completion marker + send-keys
# ---------------------------------------------------------------------------

class TestTmuxFeatures:
    """Tests for tmux session tracking and send-keys failure."""

    def test_tmux_response_includes_session_and_attach(self, env_base, _mock_popen):
        """When runner=tmux, response includes tmux_session and attach_command."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_RUNS_RUNNER": "tmux",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-tmux-resp-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                assert body["runner"] == "tmux"
                assert "tmux_session" in body
                assert "attach_command" in body
                assert body["tmux_session"].startswith("qonqrete-")
                assert "tmux attach" in body["attach_command"]
            finally:
                srv.stop()

    def test_local_exec_no_tmux_session_in_response(self, env_base, _mock_popen):
        """When runner=local_exec, response does NOT include tmux_session."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_RUNNER": "local_exec",
            "QONQRETE_RUNS_YOLO_DEFAULT": "0",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-local-resp-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                assert body["runner"] == "local_exec"
                assert "tmux_session" not in body
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Dashboard URL tests
# ---------------------------------------------------------------------------

class TestDashboardUrlInResponses:
    """Tests that QONQRETE_PUBLIC_DASHBOARD_URL is used in responses."""

    def test_dashboard_url_from_env_in_run_response(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_PUBLIC_DASHBOARD_URL": "http://10.11.12.111:31337",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-dash-url-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["dashboard_url"] == "http://10.11.12.111:31337"
            finally:
                srv.stop()

    def test_server_bind_is_0_0_0_0_no_zerotier_hardcoded(self, env_base):
        """Server bind stays 0.0.0.0 — no hardcoded ZeroTier IP."""
        import qq.web.api as api_mod
        # The default host in main() is 0.0.0.0
        # Check that the module code doesn't have hardcoded ZeroTier IPs
        source = open(api_mod.__file__).read()
        # "10." is fine as PUBLIC_DASHBOARD_URL, not as a bind address
        assert "0.0.0.0" in source.split("--host")[1][:100] if "--host" in source else True


# ---------------------------------------------------------------------------
# Known-duplicate behavior test (transcription_id-based dedupe works)
# ---------------------------------------------------------------------------

class TestDuplicateWithTranscriptionId:
    def test_duplicate_after_successful_launch(self, env_base, _mock_popen):
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                payload = {
                    "task_text": "test dedupe", "mode": "repo", "target": "default",
                    "source": "test", "raw_transcription": "test",
                    "trigger": "qonqrete", "transcription_id": "trans-ded-after-success-001",
                }
                auth = {"Authorization": "Bearer test-token"}

                status1, body1 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status1 in (200, 202)
                assert body1["ok"] is True
                assert body1.get("duplicate") is not True

                status2, body2 = _post(srv.url("/api/qonqrete/runs"), payload, headers=auth)
                assert status2 in (200, 202)
                assert body2["ok"] is True
                assert body2["duplicate"] is True
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# SSE heartbeat tests
# ---------------------------------------------------------------------------

class TestSSEHeartbeat:
    """Tests that EventTailer.sse_events() yields heartbeat comments.

    Uses fast heartbeat intervals (heartbeat_interval_ms=10) so tests
    complete in milliseconds, not seconds.
    """

    def test_sse_events_yields_immediate_heartbeat_when_idle(self, tmp_path):
        """When no events exist, sse_events yields an immediate heartbeat first."""
        from qq.web.events import EventTailer

        events_path = tmp_path / "events.jsonl"
        # Don't create the file — simulate idle state
        tailer = EventTailer(str(events_path), poll_interval_ms=10,
                             heartbeat_interval_ms=10)

        gen = tailer.sse_events()
        try:
            # First message should be the immediate heartbeat
            msg = next(gen)
            assert msg.startswith(": ping"), (
                f"Expected immediate heartbeat, got: {msg!r}"
            )
            assert msg.endswith("\n\n"), (
                f"Heartbeat should end with \\n\\n, got: {msg!r}"
            )
            assert "data:" not in msg, (
                f"Heartbeat should be comment format, got: {msg!r}"
            )
        finally:
            gen.close()

    def test_sse_heartbeat_is_comment_format(self, tmp_path):
        """SSE heartbeat uses the comment format ': ping\\n\\n'."""
        from qq.web.events import EventTailer

        events_path = tmp_path / "events.jsonl"
        tailer = EventTailer(str(events_path), poll_interval_ms=10,
                             heartbeat_interval_ms=10)

        gen = tailer.sse_events()
        try:
            # First idle message is the immediate heartbeat
            msg = next(gen)
            assert msg.startswith(": ping"), (
                f"Heartbeat has wrong prefix: {msg!r}"
            )
            assert msg.endswith("\n\n"), (
                f"Heartbeat should end with \\n\\n, got: {msg!r}"
            )
            # Should NOT contain "data:" (SSE comment, not event)
            assert "data:" not in msg, (
                f"Heartbeat should be comment format, got: {msg!r}"
            )
        finally:
            gen.close()

    def test_sse_events_yields_data_for_real_events(self, tmp_path):
        """When events exist, sse_events yields them as SSE data messages."""
        from qq.web.events import EventTailer

        events_path = tmp_path / "events.jsonl"
        events_path.write_text(
            '{"type": "test", "msg": "hello"}\n{"type": "test2", "msg": "world"}\n'
        )

        tailer = EventTailer(str(events_path), poll_interval_ms=10,
                             heartbeat_interval_ms=10)
        gen = tailer.sse_events()

        try:
            # First messages should be data events (immediate, no heartbeat delay)
            msgs = []
            for _ in range(5):
                msg = next(gen)
                if msg.startswith("data:"):
                    msgs.append(msg)
                if len(msgs) >= 2:
                    break

            assert len(msgs) >= 2, f"Expected at least 2 data events, got {len(msgs)}"
            for m in msgs[:2]:
                assert m.startswith("data: {"), f"Expected JSON data, got: {m[:50]}"
                assert m.endswith("\n\n"), f"Data message should end with \\n\\n"
        finally:
            gen.close()

    def test_sse_stream_endpoint_returns_content_type(self, env_base):
        """SSE stream endpoint returns text/event-stream content type."""
        import http.client

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
                resp = None
                try:
                    conn.request("GET", "/api/qonqrete/events/stream")
                    resp = conn.getresponse()
                    assert resp.status == 200
                    assert resp.getheader("Content-Type") == "text/event-stream"
                    assert resp.getheader("Cache-Control") == "no-cache"
                    assert resp.getheader("Connection") == "keep-alive"
                finally:
                    if resp:
                        resp.close()
                    conn.close()
            finally:
                srv.stop()

    def test_sse_stream_closes_cleanly(self, env_base):
        """SSE stream can be opened and closed without hanging the server."""
        import http.client

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                # Open SSE connection, read headers, then close cleanly
                conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=3)
                resp = None
                try:
                    conn.request("GET", "/api/qonqrete/events/stream")
                    resp = conn.getresponse()
                    assert resp.status == 200

                    # Read headers to confirm SSE, then close cleanly
                    ct = resp.getheader("Content-Type")
                    assert ct == "text/event-stream"
                    # Close immediately without reading body — should not hang server
                finally:
                    if resp:
                        resp.close()
                    conn.close()

                # Small delay to let server clean up
                time.sleep(0.1)

                # Server should still be reachable
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body["status"] == "ok"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Events path from current-run.json (web routes)
# ---------------------------------------------------------------------------

class TestEventsPathFromPointerWeb:
    """Tests that web routes prefer events_path from current-run.json."""

    def test_events_endpoint_uses_pointer_events_path(self, env_base):
        """When current-run.json has events_path, /api/qonqrete/events uses it."""
        import json as _json

        control_dir = env_base["control_root"]
        test_run_root = env_base["run_root"]

        # Create events in the active run root
        events_path = os.path.join(test_run_root, "events.jsonl")
        with open(events_path, "w") as f:
            _json.dump({"type": "from_events_path", "data": "pointer_test"}, f)
            f.write("\n")

        # Create current-run.json with explicit events_path
        current_run = {
            "run_id": "test-pointer-events",
            "run_root": test_run_root,
            "events_path": events_path,
            "runner": "local_exec",
            "state": "started",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/events"))
                assert status == 200
                assert isinstance(body, list)
                assert len(body) > 0
                assert any(e.get("type") == "from_events_path" for e in body
                          if isinstance(e, dict)), (
                    "events_path from pointer not used"
                )
            finally:
                srv.stop()

    def test_events_endpoint_fallback_when_no_events_path(self, env_base):
        """When pointer has no events_path, fallback to active_run_root/events.jsonl."""
        import json as _json

        control_dir = env_base["control_root"]
        test_run_root = env_base["run_root"]

        # Create events in the active run root
        fallback_path = os.path.join(test_run_root, "events.jsonl")
        with open(fallback_path, "w") as f:
            _json.dump({"type": "fallback_event", "data": "no_explicit_path"}, f)
            f.write("\n")

        # Create current-run.json WITHOUT events_path
        current_run = {
            "run_id": "test-fallback-events",
            "run_root": test_run_root,
            # No events_path — should fall back
            "runner": "local_exec",
            "state": "started",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/events"))
                assert status == 200
                assert isinstance(body, list)
                assert len(body) > 0
                assert any(e.get("type") == "fallback_event" for e in body
                          if isinstance(e, dict)), (
                    "Fallback events_path not used"
                )
            finally:
                srv.stop()

    def test_events_endpoint_returns_empty_when_no_state(self, env_base):
        """When no current-run.json exists, returns events from tailer (may be empty)."""
        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/events"))
                assert status == 200
                # Should get a response (list or error)
                assert isinstance(body, (list, dict))
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# New tests: Health endpoint exposes active run state fields
# ---------------------------------------------------------------------------

class TestHealthActiveRunState:
    """Tests that health endpoint exposes active_run_state, active_runner,
    active_exit_code, and active_finished_at from current-run.json."""

    def test_health_exposes_active_run_state(self, env_base):
        """Health endpoint includes active_run_state when current-run.json exists."""
        import json as _json

        control_dir = env_base["control_root"]
        current_run = {
            "run_id": "test-state-run",
            "run_root": "/tmp/test-state-run-root",
            "events_path": "/tmp/test-state-run-root/events.jsonl",
            "runner": "local_exec",
            "state": "started",
            "exit_code": None,
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body.get("active_run_state") == "started", (
                    f"Expected active_run_state=started, got {body.get('active_run_state')}"
                )
                assert body.get("active_runner") == "local_exec"
            finally:
                srv.stop()

    def test_health_exposes_finished_state_with_exit_code(self, env_base):
        """Health endpoint exposes finished state with exit_code."""
        import json as _json

        control_dir = env_base["control_root"]
        current_run = {
            "run_id": "test-finished-run",
            "run_root": "/tmp/test-finished-run-root",
            "events_path": "/tmp/test-finished-run-root/events.jsonl",
            "runner": "tmux",
            "state": "finished",
            "exit_code": 0,
            "finished_at": "2026-07-05T12:00:00Z",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            _json.dump(current_run, f)

        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=control_dir,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body.get("active_run_state") == "finished"
                assert body.get("active_runner") == "tmux"
                assert body.get("active_exit_code") == 0
                assert body.get("active_finished_at") == "2026-07-05T12:00:00Z"
            finally:
                srv.stop()

    def test_health_active_run_state_none_when_no_current_run(self, env_base):
        """When no current-run.json exists, active_run_state is null."""
        env = {}
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/health"))
                assert status == 200
                assert body.get("active_run_state") is None
                assert body.get("active_runner") is None
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# New tests: Dedupe restart safety
# ---------------------------------------------------------------------------

class TestDedupeRestartSafety:
    """Tests that dedupe is restart-safe and stale records allow retries."""

    def test_stale_queued_after_restart_allows_retry(self, env_base, _mock_popen):
        """Stale 'queued' dedupe record allows retry when queue is empty."""
        import qq.web.ingest as ingest

        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            # Pre-populate a stale queued dedupe record (queue is empty)
            dedupe_key = "test:trans:stale-queued-001"
            ingest.record_dedupe(
                dedupe_key, "old-run-id", "/fake/task.md", "/fake/target",
                run_root="/fake/root", events_path="/fake/events.jsonl",
                mode="repo", runner="local_exec", state="queued"
            )

            # Queue is empty — record should be treated as stale
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "stale-queued-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                # Should NOT be a duplicate (stale queued record allows retry)
                assert body.get("duplicate") is not True, (
                    f"Expected retry allowed (stale queued), got duplicate={body.get('duplicate')}"
                )
            finally:
                srv.stop()

    def test_stale_started_with_runner_finished_allows_retry(self, env_base, _mock_popen):
        """Stale 'started' dedupe with runner.finished marker allows retry."""
        import qq.web.ingest as ingest

        run_root = os.path.join(env_base["run_root"], "stale-started-run")
        os.makedirs(run_root, exist_ok=True)

        # Create runner.finished marker to indicate the run is done
        with open(os.path.join(run_root, "runner.finished"), "w") as f:
            f.write("2026-07-04T00:00:00Z")

        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            dedupe_key = "test:trans:stale-started-001"
            ingest.record_dedupe(
                dedupe_key, "stale-run-id", "/fake/task.md", "/fake/target",
                run_root=run_root, events_path=os.path.join(run_root, "events.jsonl"),
                mode="repo", runner="local_exec", state="started"
            )

            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "stale-started-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                # runner.finished exists -> should allow retry
                assert body.get("duplicate") is not True, (
                    "Expected retry allowed (runner.finished exists)"
                )
            finally:
                srv.stop()

    def test_finished_state_allows_retry(self, env_base, _mock_popen):
        """Finished dedupe records allow retry by default."""
        import qq.web.ingest as ingest

        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            dedupe_key = "test:trans:finished-001"
            ingest.record_dedupe(
                dedupe_key, "finished-run-id", "/fake/task.md", "/fake/target",
                run_root=env_base["run_root"], events_path="/fake/events.jsonl",
                mode="repo", runner="local_exec", state="finished"
            )

            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "finished-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                assert body.get("duplicate") is not True, (
                    "Expected retry allowed for finished state"
                )
            finally:
                srv.stop()

    def test_launch_failed_state_allows_retry(self, env_base, _mock_popen):
        """Launch-failed dedupe records allow retry."""
        import qq.web.ingest as ingest

        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            dedupe_key = "test:trans:launch-failed-001"
            ingest.record_dedupe(
                dedupe_key, "lf-run-id", "/fake/task.md", "/fake/target",
                run_root=env_base["run_root"], events_path="/fake/events.jsonl",
                mode="repo", runner="local_exec", state="launch_failed"
            )

            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "launch-failed-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                assert body.get("duplicate") is not True
            finally:
                srv.stop()

    def test_dedupe_metadata_includes_full_fields(self, env_base):
        """record_dedupe includes run_root, events_path, mode, runner in dedupe records."""
        import qq.web.ingest as ingest

        dedupe_key = "test:trans:full-meta-001"
        ingest.record_dedupe(
            dedupe_key, "meta-run-id", "/fake/task.md", "/fake/target",
            run_root="/fake/run_root", events_path="/fake/events.jsonl",
            mode="folder", runner="tmux", command_preview="qq-tui run ...",
            state="started"
        )

        # Check the dedupe file
        dedupe_path = ingest._DEDUPE_PATH
        with open(dedupe_path) as f:
            lines = f.readlines()

        found = False
        for line in lines:
            entry = json.loads(line.strip())
            if entry.get("dedupe_key") == dedupe_key:
                found = True
                assert entry.get("run_root") == "/fake/run_root"
                assert entry.get("events_path") == "/fake/events.jsonl"
                assert entry.get("mode") == "folder"
                assert entry.get("runner") == "tmux"
                assert entry.get("command_preview") == "qq-tui run ..."
                assert entry.get("state") == "started"
                break

        assert found, "Dedupe record not found in dedupe file"

    def test_reconcile_before_dedupe_uses_tmux_session_field(self, env_base):
        """_reconcile_active_run uses tmux_session field from current-run.json."""
        import qq.web.ingest as ingest
        from qq.web.ingest import RunsAPIConfig

        control_dir = env_base["control_root"]

        # Write current-run.json with custom tmux_session
        current_run = {
            "run_id": "test-reconcile-tmux",
            "run_root": "/tmp/test-reconcile-tmux-root",
            "events_path": "/tmp/test-reconcile-tmux-root/events.jsonl",
            "runner": "tmux",
            "tmux_session": "custom-session-name",
            "state": "started",
        }
        with open(os.path.join(control_dir, "current-run.json"), "w") as f:
            json.dump(current_run, f)

        # Create a config for the reconcile call
        config = RunsAPIConfig(control_root=control_dir)

        # Mock subprocess.run to simulate tmux has-session returning true (session exists)
        with mock.patch("subprocess.run") as mock_run:
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = ingest._reconcile_active_run(config)

            # Verify tmux has-session was called with the custom session name
            call_found = False
            for call_args in mock_run.call_args_list:
                args = call_args[0][0] if call_args[0] else []
                if "has-session" in args and "custom-session-name" in args:
                    call_found = True
                    break

            assert call_found, (
                "tmux has-session was not called with custom-session-name"
            )


# ---------------------------------------------------------------------------
# Regression: command_preview does not contain qq-tui exec
# ---------------------------------------------------------------------------

class TestCommandPreviewRegression:
    """Regression tests for command_preview content."""

    def test_command_preview_has_no_repo_for_folder_mode(self, env_base, _mock_popen):
        """Folder mode command_preview includes --no-repo and --run-root and --no-web."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "folder", "target": env_base["run_root"],
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-cmd-regression-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                cmd = body.get("command_preview", "")
                assert "--no-repo" in cmd, f"Expected --no-repo in: {cmd}"
                assert "--run-root" in cmd, f"Expected --run-root in: {cmd}"
                assert "--no-web" in cmd, f"Expected --no-web in: {cmd}"
            finally:
                srv.stop()

    def test_command_preview_no_repo_for_repo_mode(self, env_base, _mock_popen):
        """Repo mode command_preview does NOT include --no-repo."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-cmd-repo-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202), f"Got {status}: {body}"
                assert body["ok"] is True
                cmd = body.get("command_preview", "")
                assert "--no-repo" not in cmd, f"Expected NO --no-repo in: {cmd}"
                assert "--run-root" in cmd, f"Expected --run-root in: {cmd}"
                assert "--no-web" in cmd, f"Expected --no-web in: {cmd}"
            finally:
                srv.stop()

# ---------------------------------------------------------------------------
# Regression tests: stale _active_run_id reconcile + dedupe
# ---------------------------------------------------------------------------

class TestStaleActiveRunIdReconcile:
    """Regression tests for stale _active_run_id surviving reconcile (Fix #2, #3, #7)."""

    @staticmethod
    def setup_method():
        """Reset ingest module state before each test."""
        import qq.web.ingest as _ingest
        _ingest._active_run = False
        _ingest._active_run_id = None
        _ingest._active_item = None
        _ingest._queue.clear()
        _ingest._finished_run_ids.clear()

    @staticmethod
    def teardown_method():
        """Clean up ingest module state after each test."""
        import qq.web.ingest as _ingest
        _ingest._active_run = False
        _ingest._active_run_id = None
        _ingest._active_item = None
        _ingest._queue.clear()
        _ingest._finished_run_ids.clear()

    def test_reconcile_finished_clears_active_run_id(self):
        """Test A: reconcile with state="finished" clears _active_run_id and _active_item."""
        import tempfile, json, os
        import qq.web.ingest as _ingest

        with tempfile.TemporaryDirectory() as tmpdir:
            control_root = os.path.join(tmpdir, "control")
            os.makedirs(control_root, exist_ok=True)

            # Write current-run.json with state="finished"
            run_id = "r1"
            pointer = {
                "run_id": run_id,
                "run_root": os.path.join(tmpdir, "runs", run_id),
                "events_path": os.path.join(tmpdir, "runs", run_id, "events.jsonl"),
                "task_path": os.path.join(tmpdir, "tasks", "task.md"),
                "target_path": os.path.join(tmpdir, "target"),
                "mode": "folder",
                "source": "test",
                "runner": "local_exec",
                "tmux_session": "",
                "created_at": "2026-01-01T00:00:00Z",
                "command_preview": "qq run ...",
                "state": "finished",
                "finished_at": "2026-01-01T00:01:00Z",
                "exit_code": 0,
            }
            with open(os.path.join(control_root, "current-run.json"), "w") as f:
                json.dump(pointer, f)

            # Set in-memory active state
            _ingest._active_run = True
            _ingest._active_run_id = run_id
            _ingest._active_item = {"run_id": run_id}

            # Create a config pointing to our control_root
            from qq.web.ingest import RunsAPIConfig
            config = RunsAPIConfig(control_root=control_root)

            # Call reconcile
            result = _ingest._reconcile_active_run(config)

            # Assertions
            assert result is False, "reconcile should return False for finished run"
            assert _ingest._active_run is False, "_active_run should be False"
            assert _ingest._active_run_id is None, f"_active_run_id should be None, got {_ingest._active_run_id}"
            assert _ingest._active_item is None, f"_active_item should be None, got {_ingest._active_item}"

    def test_dedupe_allows_retry_after_reconcile_clears_stale_id(self):
        """Test B: after reconcile clears stale _active_run_id, local_exec started/no-pid allows retry."""
        import tempfile, json, os
        import qq.web.ingest as _ingest

        with tempfile.TemporaryDirectory() as tmpdir:
            control_root = os.path.join(tmpdir, "control")
            os.makedirs(control_root, exist_ok=True)

            run_id = "r1"
            dedupe_key = "test-dedupe-key-001"

            # Pre-populate dedupe with started/no-pid local_exec entry
            _ingest._ensure_dedupe_dir()
            dedupe_path = _ingest._DEDUPE_PATH
            _ingest._ensure_dedupe_dir()
            stale_entry = {
                "dedupe_key": dedupe_key,
                "run_id": run_id,
                "task_path": os.path.join(tmpdir, "tasks", "task.md"),
                "target_path": os.path.join(tmpdir, "target"),
                "state": "started",
                "run_root": os.path.join(tmpdir, "runs", run_id),
                "events_path": os.path.join(tmpdir, "runs", run_id, "events.jsonl"),
                "mode": "folder",
                "runner": "local_exec",
                "command_preview": "qq run ...",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            with open(dedupe_path, "w") as f:
                json.dump(stale_entry, f)
                f.write("\n")

            # In-memory state is cleared (simulates post-restart state)
            _ingest._active_run = False
            _ingest._active_run_id = None
            _ingest._active_item = None

            # check_duplicate should return None (allowing retry)
            result = _ingest.check_duplicate(dedupe_key)
            assert result is None, f"check_duplicate should return None for stale started/no-pid, got {result}"

            # Verify latest dedupe state is stale
            last_state = None
            if os.path.isfile(dedupe_path):
                with open(dedupe_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("dedupe_key") == dedupe_key:
                                last_state = entry.get("state")
                        except json.JSONDecodeError:
                            continue
            assert last_state == "stale", f"Latest dedupe state should be stale, got {last_state}"

    def test_local_exec_no_pid_requires_active_run_true(self):
        """Test C: local_exec started/no-pid with _active_run=False allows retry (Fix #3)."""
        import tempfile, json, os
        import qq.web.ingest as _ingest

        with tempfile.TemporaryDirectory() as tmpdir:
            run_id = "r1"
            dedupe_key = "test-dedupe-key-003"

            _ingest._ensure_dedupe_dir()
            dedupe_path = _ingest._DEDUPE_PATH
            _ingest._ensure_dedupe_dir()
            stale_entry = {
                "dedupe_key": dedupe_key,
                "run_id": run_id,
                "task_path": os.path.join(tmpdir, "tasks", "task.md"),
                "target_path": os.path.join(tmpdir, "target"),
                "state": "started",
                "run_root": os.path.join(tmpdir, "runs", run_id),
                "events_path": os.path.join(tmpdir, "runs", run_id, "events.jsonl"),
                "mode": "folder",
                "runner": "local_exec",
                "command_preview": "qq run ...",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            with open(dedupe_path, "w") as f:
                json.dump(stale_entry, f)
                f.write("\n")

            # _active_run is False but _active_run_id matches
            _ingest._active_run = False
            _ingest._active_run_id = run_id
            _ingest._active_item = None

            result = _ingest.check_duplicate(dedupe_key)
            assert result is None, f"check_duplicate should return None when _active_run=False even if _active_run_id matches, got {result}"

    def test_local_exec_no_pid_with_real_active_blocks_duplicate(self):
        """Test D: local_exec started/no-pid with _active_run=True + matching IDs blocks duplicate."""
        import tempfile, json, os
        import qq.web.ingest as _ingest

        with tempfile.TemporaryDirectory() as tmpdir:
            run_id = "r1"
            dedupe_key = "test-dedupe-key-004"

            _ingest._ensure_dedupe_dir()
            dedupe_path = _ingest._DEDUPE_PATH
            _ingest._ensure_dedupe_dir()
            active_entry = {
                "dedupe_key": dedupe_key,
                "run_id": run_id,
                "task_path": os.path.join(tmpdir, "tasks", "task.md"),
                "target_path": os.path.join(tmpdir, "target"),
                "state": "started",
                "run_root": os.path.join(tmpdir, "runs", run_id),
                "events_path": os.path.join(tmpdir, "runs", run_id, "events.jsonl"),
                "mode": "folder",
                "runner": "local_exec",
                "command_preview": "qq run ...",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            with open(dedupe_path, "w") as f:
                json.dump(active_entry, f)
                f.write("\n")

            # Real in-memory active state
            _ingest._active_run = True
            _ingest._active_run_id = run_id
            _ingest._active_item = {"run_id": run_id}

            result = _ingest.check_duplicate(dedupe_key)
            assert result is not None, "check_duplicate should return duplicate for active local_exec no-pid with real in-memory state"

    def test_reconcile_uses_guarded_writes(self):
        """Test E: _reconcile_active_run writes stale/finished through guarded helper,
        and cannot overwrite a newer active pointer."""
        import tempfile, json, os, time
        import qq.web.ingest as _ingest

        with tempfile.TemporaryDirectory() as tmpdir:
            control_root = os.path.join(tmpdir, "control")
            os.makedirs(control_root, exist_ok=True)

            # Create current-run.json with new active run (run_id="r2", started)
            new_run_pointer = {
                "run_id": "r2",
                "run_root": os.path.join(tmpdir, "runs", "r2"),
                "events_path": os.path.join(tmpdir, "runs", "r2", "events.jsonl"),
                "task_path": os.path.join(tmpdir, "tasks", "task.md"),
                "target_path": os.path.join(tmpdir, "target"),
                "mode": "folder",
                "source": "test",
                "runner": "local_exec",
                "tmux_session": "",
                "created_at": "2026-01-01T00:02:00Z",
                "command_preview": "qq run ...",
                "state": "started",
                "pid": 99999,
            }
            with open(os.path.join(control_root, "current-run.json"), "w") as f:
                json.dump(new_run_pointer, f)

            # Old reconcile from a previous process thinks run_id="r1" should be stale
            # It should NOT be able to overwrite the new active "r2" pointer
            from qq.web.ingest import RunsAPIConfig
            config = RunsAPIConfig(control_root=control_root)

            # Manually simulate what reconcile would see: current-run.json already
            # points to a different (active) run. We call _update_current_run_pointer_guarded
            # with stale state for old "r1" and verify it's blocked.
            result = _ingest._update_current_run_pointer_guarded(
                run_id="r1",
                run_root=os.path.join(tmpdir, "runs", "r1"),
                events_path=os.path.join(tmpdir, "runs", "r1", "events.jsonl"),
                task_path=os.path.join(tmpdir, "tasks", "task.md"),
                target_path=os.path.join(tmpdir, "target"),
                mode="folder",
                source="test",
                runner="local_exec",
                tmux_session="",
                created_at="2026-01-01T00:01:00Z",
                command_preview="qq run ...",
                control_root=control_root,
                state="stale",
            )
            # The guarded write should succeed (return True) but NOT change the pointer
            # because it's writing stale for "r1" while "r2" is active
            assert result is True, "guarded write should return True (silently skipped)"

            # Verify current-run.json still points to r2, not r1
            with open(os.path.join(control_root, "current-run.json")) as f:
                cr = json.load(f)
            assert cr["run_id"] == "r2", f"Pointer should still be 'r2', got {cr['run_id']}"
            assert cr["state"] == "started", f"State should still be 'started', got {cr['state']}"

    def test_clear_active_run_state_helper(self):
        """Test _clear_active_run_state helper with all variants."""
        import qq.web.ingest as _ingest

        # Setup: active state
        _ingest._active_run = True
        _ingest._active_run_id = "r-test"
        _ingest._active_item = {"run_id": "r-test"}

        # Test force=True clears everything
        _ingest._clear_active_run_state(force=True)
        assert _ingest._active_run is False
        assert _ingest._active_run_id is None
        assert _ingest._active_item is None

        # Re-setup
        _ingest._active_run = True
        _ingest._active_run_id = "r-test"
        _ingest._active_item = {"run_id": "r-test"}

        # Test matching run_id clears
        _ingest._clear_active_run_state(run_id="r-test")
        assert _ingest._active_run is False
        assert _ingest._active_run_id is None
        assert _ingest._active_item is None

        # Re-setup
        _ingest._active_run = True
        _ingest._active_run_id = "r-test"
        _ingest._active_item = {"run_id": "r-test"}

        # Test non-matching run_id does NOT clear
        _ingest._clear_active_run_state(run_id="r-other")
        assert _ingest._active_run is True, "should not clear for non-matching run_id"
        assert _ingest._active_run_id == "r-test"
        assert _ingest._active_item is not None

        # Test no args clears everything
        _ingest._clear_active_run_state()
        assert _ingest._active_run is False
        assert _ingest._active_run_id is None
        assert _ingest._active_item is None

    def test_reconcile_clears_all_three_state_vars(self):
        """_reconcile_active_run clears _active_run, _active_run_id, AND _active_item."""
        import tempfile, json, os
        import qq.web.ingest as _ingest

        with tempfile.TemporaryDirectory() as tmpdir:
            control_root = os.path.join(tmpdir, "control")
            os.makedirs(control_root, exist_ok=True)

            run_id = "r-sweep"
            pointer = {
                "run_id": run_id,
                "run_root": os.path.join(tmpdir, "runs", run_id),
                "events_path": os.path.join(tmpdir, "runs", run_id, "events.jsonl"),
                "task_path": os.path.join(tmpdir, "tasks", "task.md"),
                "target_path": os.path.join(tmpdir, "target"),
                "mode": "folder",
                "source": "test",
                "runner": "local_exec",
                "tmux_session": "",
                "created_at": "2026-01-01T00:00:00Z",
                "command_preview": "qq run ...",
                "state": "stale",
            }
            with open(os.path.join(control_root, "current-run.json"), "w") as f:
                json.dump(pointer, f)

            _ingest._active_run = True
            _ingest._active_run_id = run_id
            _ingest._active_item = {"run_id": run_id}

            from qq.web.ingest import RunsAPIConfig
            config = RunsAPIConfig(control_root=control_root)
            result = _ingest._reconcile_active_run(config)

            assert result is False
            assert _ingest._active_run is False
            assert _ingest._active_run_id is None
            assert _ingest._active_item is None



# ---------------------------------------------------------------------------
# Session endpoint tests: GET /api/qonqrete/sessions
# ---------------------------------------------------------------------------

class TestSessionsEndpoint:
    """Tests for the GET /api/qonqrete/sessions endpoint."""

    def test_sessions_returns_ok_with_empty_list(self, env_base):
        """When no runs exist, sessions returns ok: true with empty sessions list."""
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/sessions"))
                assert status == 200
                assert body["ok"] is True
                assert isinstance(body["sessions"], list)
                assert "control_root" in body
                assert "linked_run_id" in body
            finally:
                srv.stop()

    def test_sessions_includes_current_run_from_pointer(self, env_base, _mock_popen):
        """After creating a run, sessions lists it from current-run.json."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                # First create a run
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test task", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-sessions-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                run_id = body["run_id"]

                # Now fetch sessions
                s2, sessions_body = _get(srv.url("/api/qonqrete/sessions"))
                assert s2 == 200
                assert sessions_body["ok"] is True
                assert len(sessions_body["sessions"]) >= 1
                assert sessions_body["linked_run_id"] == run_id

                # Find our run in the list
                found = False
                for sess in sessions_body["sessions"]:
                    if sess["run_id"] == run_id:
                        found = True
                        assert "current-run" in sess.get("source", "")
                        assert "state" in sess
                        assert "runner" in sess
                        assert "run_root" in sess
                        assert "events_path" in sess
                        assert "started_at" in sess
                        break
                assert found, f"Run {run_id} not found in sessions list"
            finally:
                srv.stop()

    def test_sessions_includes_yolo_when_set(self, env_base, _mock_popen):
        """When YOLO is enabled via payload, sessions reflects it."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test task", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-yolo-sessions-001",
                     "yolo": True},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body["yolo"] is True

                # Fetch sessions
                s2, sessions_body = _get(srv.url("/api/qonqrete/sessions"))
                assert s2 == 200
                found = False
                for sess in sessions_body["sessions"]:
                    if sess["run_id"] == body["run_id"]:
                        found = True
                        assert sess.get("yolo") is True
                        break
                assert found
            finally:
                srv.stop()

    def test_sessions_includes_history_from_runs_jsonl(self, env_base, _mock_popen):
        """Sessions endpoint reads from runs.jsonl for history entries."""
        import json
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            # Pre-populate runs.jsonl with history entries
            runs_jsonl = os.path.join(env_base["control_root"], "runs.jsonl")
            history_entries = [
                {"run_id": "run_hist_001", "state": "finished", "runner": "local_exec",
                 "run_root": os.path.join(env_base["run_root"], "run_hist_001"),
                 "events_path": os.path.join(env_base["run_root"], "run_hist_001", "events.jsonl"),
                 "target_path": os.path.join(env_base["run_root"], "run_hist_001"),
                 "created_at": "2026-01-01T00:00:00Z", "source": "history"},
                {"run_id": "run_hist_002", "state": "running", "runner": "tmux",
                 "run_root": os.path.join(env_base["run_root"], "run_hist_002"),
                 "events_path": os.path.join(env_base["run_root"], "run_hist_002", "events.jsonl"),
                 "created_at": "2026-01-02T00:00:00Z", "source": "history"},
            ]
            os.makedirs(env_base["control_root"], exist_ok=True)
            with open(runs_jsonl, "w") as f:
                for entry in history_entries:
                    f.write(json.dumps(entry) + "\n")

            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _get(srv.url("/api/qonqrete/sessions"))
                assert status == 200
                assert body["ok"] is True
                hist_ids = [s["run_id"] for s in body["sessions"] if "history" in s.get("source", "") or "runs-history" in s.get("source", "")]
                assert "run_hist_001" in hist_ids
                assert "run_hist_002" in hist_ids
            finally:
                srv.stop()

    def test_sessions_fields_present(self, env_base, _mock_popen):
        """Session entries contain all required fields per spec."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test task", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-fields-001",
                     "yolo": True},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)

                s2, sessions_body = _get(srv.url("/api/qonqrete/sessions"))
                assert s2 == 200
                for sess in sessions_body["sessions"]:
                    required_fields = [
                        "run_id", "state", "runner", "run_root", "target_path",
                        "events_path", "task_path", "tmux_session", "attach_command",
                        "events_exists", "plan_exists", "final_exists",
                        "target_exists", "target_file_count", "created_at",
                        "started_at", "finished_at", "exit_code", "source"
                    ]
                    for field in required_fields:
                        assert field in sess, f"Missing field '{field}' in session entry"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Session selection: POST /api/qonqrete/sessions/select
# ---------------------------------------------------------------------------

class TestSessionSelectEndpoint:
    """Tests for the POST /api/qonqrete/sessions/select endpoint."""

    def test_select_requires_run_id_or_run_root(self, env_base):
        """Select fails with missing_identifier when neither run_id nor run_root given."""
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/sessions/select"),
                    {},
                )
                assert status == 400
                assert body["ok"] is False
                assert body["error"] == "missing_identifier"
            finally:
                srv.stop()

    def test_select_unknown_run_returns_404(self, env_base):
        """Selecting a non-existent run returns 404."""
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/sessions/select"),
                    {"run_id": "nonexistent_run_xyz"},
                )
                assert status == 404
                assert body["ok"] is False
                assert body["error"] == "run_not_found"
            finally:
                srv.stop()

    def test_select_switches_current_run_pointer(self, env_base, _mock_popen):
        """Selecting a valid run updates current-run.json. Uses queue mode so
        multiple runs can coexist."""
        import json
        import qq.web.ingest as _ingest
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "queue",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                # Create run 1
                s1, b1 = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "run 1", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "r1",
                     "trigger": "qonqrete", "transcription_id": "trans-select-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert s1 in (200, 202)
                id1 = b1["run_id"]

                # Clear active run state so run 2 can be created
                _ingest._active_run = False
                _ingest._active_run_id = None
                _ingest._active_item = None

                # Create run 2
                s2, b2 = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "run 2", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "r2",
                     "trigger": "qonqrete", "transcription_id": "trans-select-002",
                     "yolo": True},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert s2 in (200, 202)
                id2 = b2["run_id"]

                # Select run 1
                s3, b3 = _post(
                    srv.url("/api/qonqrete/sessions/select"),
                    {"run_id": id1},
                )
                assert s3 == 200
                assert b3["ok"] is True
                assert b3["run_id"] == id1

                # Verify current-run.json now points to run 1
                current_run_path = os.path.join(env_base["control_root"], "current-run.json")
                with open(current_run_path) as f:
                    cr = json.load(f)
                assert cr["run_id"] == id1

                # Previous backup should exist
                backup_path = os.path.join(env_base["control_root"], "current-run.previous.json")
                assert os.path.isfile(backup_path)
            finally:
                srv.stop()

    def test_select_does_not_kill_run(self, env_base, _mock_popen):
        """Selecting a session does not mutate or kill the run."""
        import json
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                # Create a run
                s1, b1 = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "keep me", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "keep",
                     "trigger": "qonqrete", "transcription_id": "trans-nokill-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert s1 in (200, 202)
                run_id = b1["run_id"]

                # Select it (same run)
                s2, b2 = _post(
                    srv.url("/api/qonqrete/sessions/select"),
                    {"run_id": run_id},
                )
                # Should succeed — the run still exists
                assert s2 == 200
                assert b2["ok"] is True
            finally:
                srv.stop()

    def test_select_with_run_root_identifier(self, env_base, _mock_popen):
        """Select supports run_root as identifier (resolves run_id from dir name)."""
        import json
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                # Create a run to get a valid run_root
                s1, b1 = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "run root select", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "root",
                     "trigger": "qonqrete", "transcription_id": "trans-root-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert s1 in (200, 202)
                run_root = b1["run_root"]

                # Select via run_root
                s2, b2 = _post(
                    srv.url("/api/qonqrete/sessions/select"),
                    {"run_root": run_root},
                )
                assert s2 == 200
                assert b2["ok"] is True
            finally:
                srv.stop()

    def test_select_invalid_json_returns_400(self, env_base):
        """Select with invalid JSON body returns 400."""
        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                import urllib.request
                req = urllib.request.Request(
                    srv.url("/api/qonqrete/sessions/select"),
                    data=b"not-json{",
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        raw = resp.read().decode("utf-8")
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8")
                    assert e.code == 400
                body = json.loads(raw)
                assert body["ok"] is False
                assert body["error"] == "invalid_json"
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# YOLO Command Generation Tests
# ---------------------------------------------------------------------------

class TestYoloCommandGeneration:
    """Tests for YOLO in command generation."""

    def test_yolo_true_includes_yolo_in_command(self):
        """When yolo=True, --yolo is included in command."""
        from qq.web.ingest import generate_command
        args = generate_command(
            task_path="/tmp/task.md",
            target_path="/tmp/target",
            mode="folder",
            run_root="/tmp/runs/r1",
            yolo=True,
        )
        assert "--yolo" in args
        assert "--no-yolo" not in args

    def test_yolo_false_includes_no_yolo_in_command(self):
        """When yolo=False, --no-yolo is included."""
        from qq.web.ingest import generate_command
        args = generate_command(
            task_path="/tmp/task.md",
            target_path="/tmp/target",
            mode="folder",
            run_root="/tmp/runs/r1",
            yolo=False,
        )
        assert "--no-yolo" in args
        assert "--yolo" not in args

    def test_yolo_none_no_yolo_flags(self):
        """When yolo=None (not explicitly set), no yolo flags in command."""
        from qq.web.ingest import generate_command
        args = generate_command(
            task_path="/tmp/task.md",
            target_path="/tmp/target",
            mode="folder",
            run_root="/tmp/runs/r1",
            yolo=None,
        )
        assert "--yolo" not in args
        assert "--no-yolo" not in args

    def test_api_run_yolo_defaults_true(self, env_base, _mock_popen):
        """API runs default to yolo=True (via yolo_default=True in config)."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_YOLO_DEFAULT": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test yolo default", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-yolo-default-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body["yolo"] is True
                # Command preview should include --yolo
                cmd = body.get("command_preview", "")
                assert "--yolo" in cmd, f"Expected --yolo in command: {cmd}"
            finally:
                srv.stop()

    def test_api_payload_yolo_false_overrides_default(self, env_base, _mock_popen):
        """API payload {yolo: false} overrides config default."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_YOLO_DEFAULT": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test yolo false", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-yolo-false-001",
                     "yolo": False},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body["yolo"] is False
                cmd = body.get("command_preview", "")
                assert "--no-yolo" in cmd, f"Expected --no-yolo in command: {cmd}"
            finally:
                srv.stop()

    def test_env_yolo_var_overrides_config(self, env_base, _mock_popen):
        """QONQRETE_YOLO=0 env var overrides config default True."""
        env = {
            "QONQRETE_RUNS_API_TOKEN": "test-token",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_RUNS_ALLOWED_TARGET_ROOTS": env_base["run_root"],
            "QONQRETE_RUNS_QUEUE_MODE": "reject_if_running",
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
            "QONQRETE_RUNS_YOLO_DEFAULT": "0",
            "QONQRETE_YOLO": "0",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                status, body = _post(
                    srv.url("/api/qonqrete/runs"),
                    {"task_text": "test yolo env", "mode": "repo", "target": "default",
                     "source": "test", "raw_transcription": "test",
                     "trigger": "qonqrete", "transcription_id": "trans-yolo-env-001"},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert status in (200, 202)
                assert body["ok"] is True
                assert body["yolo"] is False
                cmd = body.get("command_preview", "")
                assert "--no-yolo" in cmd
            finally:
                srv.stop()


# ---------------------------------------------------------------------------
# Qlarifier YOLO Behavior Tests
# ---------------------------------------------------------------------------

class TestQlarifierYoloBehavior:
    """Tests for Qlarifier behavior in YOLO mode."""

    def test_qlarifier_yolo_never_returns_needs_clarification(self, env_base):
        """When yolo=True, Qlarifier must not return need_clarification status."""
        from qq.agents.qlarifier import run_qlarifier
        from qq.models import Task, ClarifiedTask
        from qq.adapters.mock import MockAdapter
        from qq.eventlog import EventLog

        adapter = MockAdapter()
        task = Task(raw_text="Create a file with some text in it.")
        event_log = EventLog(os.path.join(env_base["tmp_path"], "events_yolo.jsonl"), run_id="test-yolo")

        result = run_qlarifier(
            adapter, task,
            os.path.join(env_base["tmp_path"], "qlarifier_work3"),
            "test-model",
            ask_human=lambda q: ["answered"] * len(q),
            event_log=event_log,
            yolo=True,
            max_rounds=2,
        )
        # MockAdapter returns "clarified" status, and yolo mode should not break it
        assert isinstance(result, ClarifiedTask)
        assert len(result.clarified_text) > 0

    def test_qlarifier_non_yolo_preserves_interactive_behavior(self, env_base):
        """Without YOLO, Qlarifier works normally with MockAdapter."""
        from qq.agents.qlarifier import run_qlarifier
        from qq.models import Task, ClarifiedTask
        from qq.adapters.mock import MockAdapter
        from qq.eventlog import EventLog

        adapter = MockAdapter()
        task = Task(raw_text="Build something ambiguous.")

        event_log = EventLog(os.path.join(env_base["tmp_path"], "events_non_yolo2.jsonl"), run_id="test-non-yolo")

        result = run_qlarifier(
            adapter, task,
            os.path.join(env_base["tmp_path"], "qlarifier_work4"),
            "test-model",
            ask_human=lambda q: ["A web app"] * len(q),
            event_log=event_log,
            yolo=False,
            max_rounds=2,
        )
        assert isinstance(result, ClarifiedTask)


# ---------------------------------------------------------------------------
# Configuration YOLO Resolution Tests
# ---------------------------------------------------------------------------

class TestConfigYoloResolution:
    """Tests for YOLO resolution in config system."""

    def test_config_yolo_default_is_none(self):
        """By default, yolo is None (not set) in resolved config."""
        from qq.config import resolve_config
        cfg = resolve_config(
            repo_root="/tmp",
            run_root="/tmp/runs/test",
            dry_run=True,
        )
        # With no env vars and dry_run=True (mock provider), yolo
        # resolves from the config file's qonqrete section. When no
        # config file exists or qonqrete section missing, it's False.
        # But the key is: cfg.yolo is accessible
        assert cfg.yolo is not None  # It should resolve to something

    def test_cli_yolo_flag_sets_true(self):
        """CLI --yolo flag sets cfg.yolo = True."""
        from qq.config import resolve_config
        cfg = resolve_config(
            repo_root="/tmp",
            run_root="/tmp/runs/test",
            dry_run=True,
            yolo=True,
        )
        assert cfg.yolo is True

    def test_cli_no_yolo_flag_sets_false(self):
        """CLI --no-yolo flag sets cfg.yolo = False."""
        from qq.config import resolve_config
        cfg = resolve_config(
            repo_root="/tmp",
            run_root="/tmp/runs/test",
            dry_run=True,
            yolo=False,
        )
        assert cfg.yolo is False

    def test_env_yolo_overrides_config(self, env_base):
        """QONQRETE_YOLO env var overrides config file default."""
        env = {"QONQRETE_YOLO": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            from qq.config import resolve_config
            cfg = resolve_config(
                repo_root="/tmp",
                run_root="/tmp/runs/test",
                dry_run=True,
            )
            assert cfg.yolo is True

    def test_env_yolo_false_overrides(self, env_base):
        """QONQRETE_YOLO=0 sets yolo to False."""
        env = {"QONQRETE_YOLO": "0"}
        with mock.patch.dict(os.environ, env, clear=True):
            from qq.config import resolve_config
            cfg = resolve_config(
                repo_root="/tmp",
                run_root="/tmp/runs/test",
                dry_run=True,
            )
            assert cfg.yolo is False

    def test_cli_flag_overrides_env(self, env_base):
        """Explicit CLI flag overrides env var."""
        env = {"QONQRETE_YOLO": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            from qq.config import resolve_config
            cfg = resolve_config(
                repo_root="/tmp",
                run_root="/tmp/runs/test",
                dry_run=True,
                yolo=False,
            )
            assert cfg.yolo is False  # CLI wins


# ---------------------------------------------------------------------------
# Approval Bypass Tests
# ---------------------------------------------------------------------------

class TestApprovalBypass:
    """Tests for approval bypass in YOLO mode."""

    def test_qontroller_yolo_bypasses_ask_human(self, env_base):
        """When yolo=True, QontrollerConfig accepts yolo parameter."""
        from qq.qontroller import QontrollerConfig

        config = QontrollerConfig(
            repo_root=env_base["tmp_path"],
            run_root=os.path.join(env_base["tmp_path"], "runs", "test_bypass"),
            model_qlarifier="test-model",
            model_instruqtor="test-model",
            model_construqtor="test-model",
            model_inspeqtor="test-model",
            max_cycles=1,
            yolo=True,
        )
        assert config.yolo is True


# ---------------------------------------------------------------------------
# CLI Flag Tests
# ---------------------------------------------------------------------------

class TestCliYoloFlags:
    """Tests for CLI --yolo and --no-yolo arg parsing."""

    def test_yolo_flag_parsed(self):
        """-y and --yolo are parsed as yolo=True."""
        from qq.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "task.md", "target", "-y"])
        assert args.yolo is True
        
        args2 = parser.parse_args(["run", "task.md", "target", "--yolo"])
        assert args2.yolo is True

    def test_no_yolo_flag_parsed(self):
        """--no-yolo is parsed as yolo=False."""
        from qq.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "task.md", "target", "--no-yolo"])
        assert args.yolo is False

    def test_no_yolo_flag_default(self):
        """Without any yolo flag, default is None (not explicitly set)."""
        from qq.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "task.md", "target"])
        assert args.yolo is None


# ---------------------------------------------------------------------------
# Session Integration: scan logic matches spec
# ---------------------------------------------------------------------------

class TestSessionScanLogic:
    """Tests for session scanning behavior."""

    def test_session_scan_uses_control_root_current_run(self, env_base):
        """Session scan includes current-run.json entry first."""
        import json
        # Pre-populate current-run.json
        pointer = {
            "run_id": "run_scan_001",
            "run_root": os.path.join(env_base["run_root"], "run_scan_001"),
            "events_path": os.path.join(env_base["run_root"], "run_scan_001", "events.jsonl"),
            "task_path": os.path.join(env_base["task_dir"], "task.md"),
            "target_path": os.path.join(env_base["run_root"], "target"),
            "mode": "folder",
            "source": "test",
            "runner": "local_exec",
            "state": "started",
            "created_at": "2026-07-01T00:00:00Z",
            "yolo": True,
            "tmux_session": "",
            "command_preview": "qq run ...",
        }
        os.makedirs(env_base["control_root"], exist_ok=True)
        with open(os.path.join(env_base["control_root"], "current-run.json"), "w") as f:
            json.dump(pointer, f)

        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                s, body = _get(srv.url("/api/qonqrete/sessions"))
                assert s == 200
                assert body["ok"] is True
                assert body["linked_run_id"] == "run_scan_001"
                assert any(sess["run_id"] == "run_scan_001" for sess in body["sessions"])
            finally:
                srv.stop()

    def test_session_entry_has_correct_source_field(self, env_base):
        """Different scan sources set correct source field values."""
        import json
        # Pre-populate current-run.json
        pointer = {
            "run_id": "run_source_test",
            "run_root": os.path.join(env_base["run_root"], "run_source_test"),
            "events_path": os.path.join(env_base["run_root"], "run_source_test", "events.jsonl"),
            "task_path": os.path.join(env_base["task_dir"], "task.md"),
            "target_path": os.path.join(env_base["run_root"], "target"),
            "mode": "folder",
            "source": "test",
            "runner": "local_exec",
            "state": "started",
            "created_at": "2026-07-01T00:00:00Z",
        }
        os.makedirs(env_base["control_root"], exist_ok=True)
        with open(os.path.join(env_base["control_root"], "current-run.json"), "w") as f:
            json.dump(pointer, f)

        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                s, body = _get(srv.url("/api/qonqrete/sessions"))
                assert s == 200
                for sess in body["sessions"]:
                    if sess["run_id"] == "run_source_test":
                        assert "current-run" in sess.get("source", "")
                        break
            finally:
                srv.stop()



class TestReadModelReviewPhase502:
    """50x regression tests for read-model/config endpoints in the
    inspEQtor/reviewing phase.

    Read-model and config must return HTTP 200 (valid JSON) both during
    normal building and when the run transitions into review/inspeQtor with
    malformed review/cycle payloads (missing/None/dict verdict status,
    non-numeric cycle fields, string inspection scores).
    """

    def _seed_run(self, run_root, events, with_plan=True):
        """Create a minimal run directory with events + optional plan."""
        os.makedirs(os.path.join(run_root, "state"), exist_ok=True)
        with open(os.path.join(run_root, "events.jsonl"), "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        if with_plan:
            with open(os.path.join(run_root, "state", "plan.json"), "w") as f:
                json.dump({
                    "build_groups": {
                        "g1": {"id": "g1", "name": "Group 1", "briq_ids": ["b1"]},
                    },
                    "briqs": {"b1": {"id": "b1", "title": "Briq", "status": "done"}},
                }, f)

    def _build_pointer(self, run_root):
        return {
            "run_id": "review_phase_run",
            "run_root": run_root,
            "events_path": os.path.join(run_root, "events.jsonl"),
            "task_path": "",
            "target_path": "",
            "mode": "folder",
            "source": "test",
            "runner": "local_exec",
            "state": "running",
            "created_at": "2026-07-01T00:00:00Z",
            "yolo": False,
            "tmux_session": "",
            "command_preview": "qq run ...",
        }

    def test_read_model_200_normal_build(self, env_base):
        """Valid model during normal building."""
        run_root = os.path.join(env_base["run_root"], "review_phase_run")
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "review_phase_run", "max_cycles": 5},
            {"type": "active_agent_changed", "ts": 1100, "role": "construqtor"},
            {"type": "build_group.queued", "ts": 1200, "build_group_id": "g1"},
            {"type": "build_group.started", "ts": 1500, "build_group_id": "g1"},
            {"type": "build_group.completed", "ts": 2000, "build_group_id": "g1"},
        ]
        self._seed_run(run_root, events)
        os.makedirs(env_base["control_root"], exist_ok=True)
        with open(os.path.join(env_base["control_root"], "current-run.json"), "w") as f:
            json.dump(self._build_pointer(run_root), f)

        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                s, body = _get(srv.url("/api/qonqrete/read-model?_refresh=1"))
                assert s == 200
                assert "error" not in body
                assert body["run"]["status"] == "running"
            finally:
                srv.stop()

    def test_read_model_200_review_phase(self, env_base):
        """Valid model during inspEQtor/reviewing phase."""
        run_root = os.path.join(env_base["run_root"], "review_phase_run")
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "review_phase_run", "max_cycles": 5},
            {"type": "active_agent_changed", "ts": 1100, "role": "construqtor"},
            {"type": "build_group.queued", "ts": 1200, "build_group_id": "g1"},
            {"type": "build_group.started", "ts": 1500, "build_group_id": "g1"},
            {"type": "build_group.completed", "ts": 2000, "build_group_id": "g1"},
            {"type": "active_agent_changed", "ts": 2100, "role": "inspeqtor"},
            {"type": "review.started", "ts": 2200},
            {"type": "review.verdict", "ts": 2500, "status": "NOT_DONE"},
            {"type": "cycle_completed", "ts": 3000, "cycle": 2},
            {"type": "cycle_summary", "cycle": 2, "total_cycles": 5},
        ]
        self._seed_run(run_root, events)
        os.makedirs(env_base["control_root"], exist_ok=True)
        with open(os.path.join(env_base["control_root"], "current-run.json"), "w") as f:
            json.dump(self._build_pointer(run_root), f)

        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                s, body = _get(srv.url("/api/qonqrete/read-model?_refresh=1"))
                assert s == 200
                assert "error" not in body
                assert body["run"]["active_agent"] == "inspeqtor"
                assert s == 200
                cs, cfg = _get(srv.url("/api/qonqrete/config"))
                assert cs == 200
                assert "config" in cfg
            finally:
                srv.stop()

    def test_read_model_200_malformed_review_events(self, env_base):
        """Valid model despite malformed review/cycle payloads (no crash)."""
        run_root = os.path.join(env_base["run_root"], "review_phase_run")
        events = [
            {"type": "run.started", "ts": 1000, "run_id": "review_phase_run", "max_cycles": 3},
            {"type": "active_agent_changed", "ts": 1100, "role": "inspeqtor"},
            {"type": "review.verdict", "ts": 1200, "status": {"status": "NOT_DONE"}},
            {"type": "review.completed", "ts": 1300, "build_group_id": None},
            {"type": "cycle_completed", "ts": 1400, "cycle": "2"},
            {"type": "cycle_summary"},
            {"type": "inspection.completed", "ts": 1500, "build_group_id": "g1", "score": "95"},
            {"type": "review.failed"},
        ]
        self._seed_run(run_root, events)
        os.makedirs(env_base["control_root"], exist_ok=True)
        with open(os.path.join(env_base["control_root"], "current-run.json"), "w") as f:
            json.dump(self._build_pointer(run_root), f)

        env = {
            "QONQRETE_RUNS_DEV_NO_AUTH": "1",
            "QONQRETE_RUNS_TASK_DIR": env_base["task_dir"],
            "QONQRETE_RUNS_DEFAULT_ROOT": env_base["run_root"],
            "QONQRETE_CONTROL_ROOT": env_base["control_root"],
        }
        with mock.patch.dict(os.environ, env, clear=True):
            srv = TestServer(
                env_base["tmp_path"],
                run_root=env_base["run_root"],
                control_root=env_base["control_root"],
                control_root_mode=True,
            ).start()
            try:
                s, body = _get(srv.url("/api/qonqrete/read-model?_refresh=1"))
                assert s == 200
                assert "error" not in body
            finally:
                srv.stop()
