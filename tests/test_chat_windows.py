"""Regression tests for the browser chat UI on Windows.

Covers the two root causes that broke `qq chat` builds for Windows users:
  1. The repo root was embedded raw into a JavaScript string literal.
     Windows paths like C:\\Users\\... were decoded as JS escape sequences
     (\\U -> U, \\m -> m, ...) and the default destination directory came out
     corrupted (C:Usersmate...).
  2. Chat-triggered runs exec'd the Rust TUI cockpit, which (a) tried to
     parse the YAML qq config as TOML and (b) aborted because the chat worker
     subprocess has no interactive TTY. The spawned command must therefore be
     headless (--no-tui) and keep task/destination as separate argv entries
     so Windows paths survive.
"""
import html
import http.client
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.chat import _Handler, _render_chat_html, build_chat_run_command  # noqa: E402


class TestChatHtmlWindowsPaths(unittest.TestCase):
    def test_windows_root_backslashes_survive_rendering(self):
        root = r"C:\Users\mate\qonqrete"
        page = _render_chat_html(root)
        # The path must appear verbatim in the hidden input attribute.
        self.assertIn('id="root-hint" value="C:\\Users\\mate\\qonqrete"', page)
        # It must NOT be embedded raw in the JS string literal anymore.
        self.assertNotIn("rootHint='C:", page)
        self.assertNotIn("rootHint=\\\"C:", page)

    def test_posix_root_rendering_unchanged(self):
        page = _render_chat_html("/Users/wicked/gitje/qonqrete")
        self.assertIn('id="root-hint" value="/Users/wicked/gitje/qonqrete"', page)

    def test_js_reads_root_from_hidden_input(self):
        page = _render_chat_html(r"C:\Users\mate\qonqrete")
        self.assertIn("getElementById('root-hint').value", page)
        self.assertIn("d.value=rootHint+'/runs/qonqrete-run-'", page)

    def test_html_escaping_keeps_attribute_safe(self):
        root = '/tmp/path with "quotes" & <angle>'
        page = _render_chat_html(root)
        expected = html.escape(root, quote=True)
        self.assertIn('id="root-hint" value="%s"' % expected, page)


class TestChatBuildCommand(unittest.TestCase):
    def test_run_is_headless_and_keeps_paths_separate(self):
        task = r"C:\Users\mate\project\.qonqrete-chat-task-123.md"
        dest = r"C:\Users\mate\project"
        cmd = build_chat_run_command(task, dest)
        self.assertIn("--no-tui", cmd)
        # task + destination are discrete argv entries (no shell quoting), so
        # Windows backslashes and spaces are passed to the child intact.
        self.assertIn(task, cmd)
        self.assertIn(dest, cmd)
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1:4], ["-m", "qq", "run"])

    def test_optional_args_forwarded(self):
        cmd = build_chat_run_command("t.md", "d", config_path="qq.yaml",
                                     web_port=31337)
        self.assertIn("--config", cmd)
        self.assertIn("qq.yaml", cmd)
        self.assertIn("--web-port", cmd)
        self.assertIn("31337", cmd)


class TestChatHttpPage(unittest.TestCase):
    """Serve the actual chat page and assert the Windows root survives HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="qq-chat-test-")
        # Point the server at the repo so /asset/squid etc. resolve; we only
        # GET "/" though.
        cls.repo = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

        class Server(ThreadingHTTPServer):
            allow_reuse_address = True

        cls.srv = Server(("127.0.0.1", 0), _Handler)
        cls.srv.repo_root = os.path.abspath(cls.repo)
        cls.srv.root = r"C:\Users\mate\qonqrete"  # simulate a Windows server root
        cls.srv.provider = None
        cls.srv.config_path = None
        cls.srv.web_port = None
        cls.srv.runs = {}
        cls.srv.lock = threading.RLock()
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=5)

    def test_index_serves_verbatim_windows_root(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
        finally:
            conn.close()
        self.assertEqual(resp.status, 200)
        self.assertIn('id="root-hint" value="C:\\Users\\mate\\qonqrete"', body)
        self.assertNotIn("rootHint='C:", body)


if __name__ == "__main__":
    unittest.main()
