"""Tests for WSL / Windows-host interop in the llama-cpp adapter.

Verifies the auto-discovery that lets a qq process running inside WSL2 reach
a llama-server that runs as a native Windows process (loopback is a separate
VM under WSL2, so 127.0.0.1 alone can never reach the Windows host).
"""
import os
import sys
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.adapters import llama_cpp as mod  # noqa: E402
from qq.adapters.llama_cpp import (  # noqa: E402
    LlamaCppAdapter,
    _default_gateway_ips,
    _endpoint_candidates,
    _host_is_loopback,
    _is_wsl,
    _nameserver_ips,
    _replace_host,
    _wsl_windows_host_ips,
)

RESOLV_WSL = "nameserver 172.24.64.1\nnameserver 127.0.0.53\nsearch example.com\n"
IP_ROUTE_WSL = (
    "default via 172.24.64.1 dev eth0 proto kernel\n"
    "172.24.64.0/20 dev eth0 proto kernel scope link src 172.24.80.1\n"
)


@contextmanager
def _wsl_context():
    """Fake a WSL2 session with a 172.24.64.1 NAT gateway."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(mod, "_is_wsl", return_value=True))
        stack.enter_context(patch.object(mod, "_read_text_file",
                                         return_value=RESOLV_WSL))
        stack.enter_context(patch.object(mod, "_run_ip_route",
                                         return_value=IP_ROUTE_WSL))
        yield


def _make_wsl_adapter(endpoint="http://127.0.0.1:8888/v1"):
    """Build an adapter as if __init__ ran inside WSL2 (gateway 172.24.64.1)."""
    with _wsl_context():
        return LlamaCppAdapter(endpoint=endpoint)


class TestWslDetection(unittest.TestCase):
    def test_detects_wsl_via_env(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            self.assertTrue(_is_wsl())

    def test_detects_wsl_via_proc_version(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": ""}):
            with patch.object(mod, "_read_text_file",
                              return_value="Linux version 5.15.153.1-microsoft-standard-WSL2 (gcc)"):
                self.assertTrue(_is_wsl())

    def test_not_wsl_when_no_signals(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": ""}):
            with patch.object(mod, "_read_text_file", return_value=""):
                self.assertFalse(_is_wsl())


class TestHostDiscoveryParsers(unittest.TestCase):
    def test_nameserver_ips_skips_stub_and_ipv6(self):
        self.assertEqual(_nameserver_ips(RESOLV_WSL), ["172.24.64.1"])

    def test_nameserver_ips_empty(self):
        self.assertEqual(_nameserver_ips(""), [])

    def test_default_gateway_ips(self):
        self.assertEqual(_default_gateway_ips(IP_ROUTE_WSL), ["172.24.64.1"])

    def test_default_gateway_ignores_non_default_routes(self):
        self.assertEqual(_default_gateway_ips("172.24.0.0/20 dev eth0\n"), [])

    def test_windows_host_ips_dedup_and_env_override(self):
        with _wsl_context():
            with patch.dict(os.environ, {"QQ_WSL_HOST_IP": "10.0.0.2, 10.0.0.3"}):
                self.assertEqual(
                    _wsl_windows_host_ips(),
                    ["172.24.64.1", "10.0.0.2", "10.0.0.3"],
                )


class TestEndpointHelpers(unittest.TestCase):
    def test_host_is_loopback(self):
        self.assertTrue(_host_is_loopback("http://127.0.0.1:8888/v1"))
        self.assertTrue(_host_is_loopback("http://localhost:8888/v1"))
        self.assertFalse(_host_is_loopback("http://192.168.1.5:8888/v1"))
        self.assertFalse(_host_is_loopback("http://172.24.64.1:8888/v1"))

    def test_replace_host_keeps_port_and_path(self):
        self.assertEqual(
            _replace_host("http://127.0.0.1:8888/v1", "172.24.64.1"),
            "http://172.24.64.1:8888/v1",
        )

    def test_replace_host_without_port(self):
        self.assertEqual(
            _replace_host("http://127.0.0.1/v1", "172.24.64.1"),
            "http://172.24.64.1/v1",
        )

    def test_replace_host_leaves_ipv6_alone(self):
        url = "http://[::1]:8888/v1"
        self.assertEqual(_replace_host(url, "172.24.64.1"), url)

    def test_replace_host_preserves_scheme(self):
        self.assertEqual(
            _replace_host("https://127.0.0.1:8443/v1", "172.24.64.1"),
            "https://172.24.64.1:8443/v1",
        )

    def test_candidates_appended_only_on_wsl_loopback(self):
        with _wsl_context():
            self.assertEqual(
                _endpoint_candidates("http://127.0.0.1:8888/v1"),
                ["http://127.0.0.1:8888/v1",
                 "http://172.24.64.1:8888/v1"],
            )

    def test_non_loopback_endpoint_gets_no_wsl_candidates(self):
        with _wsl_context():
            self.assertEqual(
                _endpoint_candidates("http://192.168.1.5:8888/v1"),
                ["http://192.168.1.5:8888/v1"],
            )

    def test_no_candidates_outside_wsl(self):
        with patch.object(mod, "_is_wsl", return_value=False):
            self.assertEqual(
                _endpoint_candidates("http://127.0.0.1:8888/v1"),
                ["http://127.0.0.1:8888/v1"],
            )


class TestEffectiveEndpoint(unittest.TestCase):
    """The adapter falls back to the Windows host only inside WSL, and only
    when the loopback endpoint refuses connections."""

    def test_falls_back_to_windows_host_when_loopback_refused(self):
        with _wsl_context():
            adapter = _make_wsl_adapter()
            self.assertEqual(adapter._candidates,
                             ["http://127.0.0.1:8888/v1",
                              "http://172.24.64.1:8888/v1"])
            with patch.object(mod, "_port_open",
                              side_effect=[False, True]) as probe:
                self.assertEqual(adapter._effective_endpoint(),
                                 "http://172.24.64.1:8888/v1")
                self.assertEqual(adapter._resolved_endpoint,
                                 "http://172.24.64.1:8888/v1")
                # Cached: a second call must not probe again.
                self.assertEqual(adapter._effective_endpoint(),
                                 "http://172.24.64.1:8888/v1")
                self.assertEqual(probe.call_count, 2)

    def test_keeps_loopback_when_server_runs_inside_wsl(self):
        with _wsl_context():
            adapter = _make_wsl_adapter()
            with patch.object(mod, "_port_open", return_value=True) as probe:
                self.assertEqual(adapter._effective_endpoint(),
                                 "http://127.0.0.1:8888/v1")
                self.assertEqual(probe.call_count, 1)

    def test_keeps_primary_when_nothing_is_reachable(self):
        with _wsl_context():
            adapter = _make_wsl_adapter()
            with patch.object(mod, "_port_open", return_value=False) as probe:
                self.assertEqual(adapter._effective_endpoint(),
                                 "http://127.0.0.1:8888/v1")
                # 1 primary + 1 WSL candidate probed, then canonical kept.
                self.assertEqual(probe.call_count, 2)

    def test_outside_wsl_endpoint_never_probes(self):
        with patch.object(mod, "_is_wsl", return_value=False):
            adapter = LlamaCppAdapter(endpoint="http://127.0.0.1:8888/v1")
        with patch.object(mod, "_port_open",
                          side_effect=AssertionError("must not probe outside WSL")):
            self.assertEqual(adapter._effective_endpoint(),
                             "http://127.0.0.1:8888/v1")
            self.assertEqual(adapter._resolved_endpoint,
                             "http://127.0.0.1:8888/v1")


class TestErrorMessageWslHint(unittest.TestCase):
    def test_wsl_hint_included_on_connection_error(self):
        with patch.object(mod, "_is_wsl", return_value=True):
            with self.assertRaises(RuntimeError) as ctx:
                mod._chat_completion(
                    endpoint="http://127.0.0.1:1/v1",
                    api_key=None,
                    model="local",
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=None,
                    top_p=None,
                    timeout=2,
                )
        msg = str(ctx.exception)
        self.assertIn("Could not reach llama-cpp endpoint", msg)
        self.assertIn("WSL", msg)
        self.assertIn("QQ_LLAMA_CPP_ENDPOINT", msg)

    def test_no_wsl_hint_outside_wsl(self):
        with patch.object(mod, "_is_wsl", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                mod._chat_completion(
                    endpoint="http://127.0.0.1:1/v1",
                    api_key=None,
                    model="local",
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=None,
                    top_p=None,
                    timeout=2,
                )
        self.assertNotIn("WSL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
