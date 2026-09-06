"""
LlamaCpp adapter — OpenAI-compatible HTTP backend for local llama.cpp servers.

Routes all agent calls to a local llama.cpp (or any OpenAI-compatible) server
via the /v1/chat/completions endpoint. The server manages its own loaded model;
QonQrete does NOT specify a model name — the field is set to "local" which
llama.cpp ignores, using whatever model is currently loaded.

Default endpoint: http://127.0.0.1:8888/v1
Override via:
  - QQ_LLAMA_CPP_ENDPOINT env var
  - llama_cpp_endpoint= kwarg to LlamaCppAdapter()

No API key is required for local servers. Set QQ_LLAMA_CPP_API_KEY if your
llama.cpp server is behind an auth proxy.

WSL / Windows interop
---------------------
When ``qq`` runs inside Windows Subsystem for Linux (WSL2) while llama.cpp
runs as a native Windows process, the default ``127.0.0.1:8888`` endpoint is
NOT reachable: WSL2 is its own lightweight VM, so loopback traffic never
leaves it (the classic ``[Errno 111] Connection refused``). This adapter
detects WSL and, when the loopback endpoint refuses connections, transparently
retries the same host/port against the Windows host through the WSL NAT
gateway (the IP WSL auto-writes into ``/etc/resolv.conf`` / the default
route). The first working endpoint is cached for the rest of the process, so
every role call after the first uses it directly.

For the auto-detection to succeed the Windows llama-server must accept
non-loopback connections: start it with ``--host 0.0.0.0``, e.g.
``llama-server -m model.gguf --host 0.0.0.0 --port 8888``, and allow it
through Windows Firewall for the WSL virtual adapter.

Order of preference for WSL users:
  1. Run llama-server inside WSL. 127.0.0.1 then just works, and Windows can
     still reach it via ``localhost:8888`` (WSL2 forwards Windows localhost
     into WSL automatically).
  2. Let this adapter auto-detect the Windows host (requires ``--host
     0.0.0.0`` on the Windows llama-server).
  3. Set ``QQ_LLAMA_CPP_ENDPOINT=http://<windows-host-ip>:8888/v1`` manually.
``QQ_WSL_HOST_IP`` may optionally seed/override the auto-detected
Windows-host IPs (comma/space separated).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional
from urllib.parse import urlsplit, urlunsplit

from .base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_ENDPOINT = "http://127.0.0.1:8888/v1"
_CONNECT_TIMEOUT = 30   # seconds for initial connection
_STREAM_TIMEOUT = 1800  # seconds for the full completion (matches codeseeq default)


# ---------------------------------------------------------------------------
# WSL / Windows-host interop helpers
# ---------------------------------------------------------------------------
# Under WSL2 default NAT networking the Windows host is the WSL gateway: WSL
# auto-generates /etc/resolv.conf with the gateway as "nameserver", and `ip
# route` shows it as "default via <gw>". Either source gives us an IP that
# can reach Windows-host services (llama-server) from inside WSL.
_PROBE_TIMEOUT = 1.0  # seconds per TCP probe


def _is_wsl() -> bool:
    """Return True when this Python process runs under Windows Subsystem for Linux."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    return "microsoft" in _read_text_file("/proc/version").lower()


def _read_text_file(path: str) -> str:
    """Read a small text file best-effort; empty string on any failure."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _run_ip_route() -> str:
    """Return ``ip route`` output best-effort; empty string on any failure."""
    try:
        proc = subprocess.run(
            ["ip", "route"], capture_output=True, text=True, timeout=3
        )
        return proc.stdout or ""
    except Exception:
        return ""


def _nameserver_ips(resolv_conf: str) -> List[str]:
    """Extract dotted-quad nameserver entries from /etc/resolv.conf content."""
    ips: List[str] = []
    for line in resolv_conf.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            ip = parts[1].strip()
            # Skip the systemd-resolved stub and IPv6 forms — we want the
            # real gateway address WSL2 publishes for the Windows host.
            if ip and not ip.startswith(("127.", "::")) and ip not in ips:
                ips.append(ip)
    return ips


def _default_gateway_ips(ip_route: str) -> List[str]:
    """Extract ``default via <gw>`` gateways from ``ip route`` output."""
    ips: List[str] = []
    for line in ip_route.splitlines():
        parts = line.split()
        if not parts or parts[0] != "default" or "via" not in parts:
            continue
        try:
            gw = parts[parts.index("via") + 1]
        except (ValueError, IndexError):
            continue
        if gw and gw not in ips:
            ips.append(gw)
    return ips


def _wsl_windows_host_ips() -> List[str]:
    """Best-effort list of Windows-host IPs reachable from this WSL session.

    Sources, in order: /etc/resolv.conf nameserver, ``ip route`` default
    gateway, and the optional ``QQ_WSL_HOST_IP`` env override. Candidates are
    probed later with a short TCP connect, so stale/misleading entries simply
    fail fast and the next one is tried.
    """
    ips: List[str] = []
    for ip in _nameserver_ips(_read_text_file("/etc/resolv.conf")):
        if ip not in ips:
            ips.append(ip)
    for ip in _default_gateway_ips(_run_ip_route()):
        if ip not in ips:
            ips.append(ip)
    extra = os.environ.get("QQ_WSL_HOST_IP", "").strip()
    for ip in extra.replace(",", " ").split():
        if ip and ip not in ips:
            ips.append(ip)
    return ips


def _host_is_loopback(endpoint: str) -> bool:
    """True when *endpoint* targets the local machine (localhost/127.x/::1)."""
    host = (urlsplit(endpoint).hostname or "").lower()
    return host in ("localhost", "::1") or host.startswith("127.")


def _replace_host(endpoint: str, new_host: str) -> str:
    """Return *endpoint* with only its hostname swapped for *new_host*.

    Scheme, port and path are preserved, e.g.
    ``http://127.0.0.1:8888/v1`` + ``172.24.64.1`` ->
    ``http://172.24.64.1:8888/v1``.
    """
    parts = urlsplit(endpoint)
    netloc = parts.netloc
    prefix = ""
    if "@" in netloc:
        prefix, _, netloc = netloc.rpartition("@")
        prefix += "@"
    if netloc.startswith("["):
        return endpoint  # IPv6 literal — leave untouched
    if ":" in netloc:
        host, _, port = netloc.rpartition(":")
        netloc = f"{new_host}:{port}" if port.isdigit() else new_host
    else:
        netloc = new_host
    return urlunsplit((parts.scheme, prefix + netloc, parts.path,
                       parts.query, parts.fragment))


def _port_open(host: str, port: int, timeout: float = _PROBE_TIMEOUT) -> bool:
    """True when a TCP connection to host:port succeeds within *timeout*."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _endpoint_candidates(endpoint: str) -> List[str]:
    """Return ``[endpoint]`` plus, on WSL with a loopback endpoint, the
    Windows-host variants of the same endpoint.

    Outside WSL (macOS / native Windows / plain Linux) the returned list has
    exactly one entry, so existing behavior is unchanged.
    """
    base = endpoint.rstrip("/")
    candidates = [base]
    if _is_wsl() and _host_is_loopback(base):
        for ip in _wsl_windows_host_ips():
            alt = _replace_host(base, ip)
            if alt != base and alt not in candidates:
                candidates.append(alt)
    return candidates


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------
def _system_prompt_for_role(role: str) -> str:
    """Return a concise system prompt scoped to each QonQrete agent role."""
    base = (
        "You are an autonomous coding agent inside QonQrete. "
        "You must respond ONLY with a single valid JSON object — no markdown, "
        "no code fences, no preamble, no commentary. "
        "Write the JSON directly to the output file path given in the user message."
    )
    role_hints = {
        "qlarifier": (
            " Your role is Qlarifier: parse the task, resolve ambiguities, "
            "and emit a clarified_task JSON with keys: status, clarified_task, "
            "notes_for_instruqtor."
        ),
        "instruqtor": (
            " Your role is instruQtor: decompose the clarified task into build_groups "
            "containing briQs. Emit JSON with keys: summary, build_groups."
        ),
        "construqtor": (
            " Your role is construQtor: implement exactly the briQs assigned. "
            "Write all files. Emit JSON with keys: status, files_changed."
        ),
        "inspeqtor": (
            " Your role is inspeQtor: review the implementation against the original "
            "task. Emit JSON with keys: status (FULLY_DONE or NOT_DONE), summary, "
            "score (0-100), issues."
        ),
    }
    return base + role_hints.get(role, "")


# ---------------------------------------------------------------------------
# HTTP helper — stdlib only, no external deps
# ---------------------------------------------------------------------------
def _chat_completion(
    endpoint: str,
    api_key: Optional[str],
    model: str,
    messages: list,
    temperature: Optional[float],
    top_p: Optional[float],
    timeout: int = _STREAM_TIMEOUT,
) -> str:
    """POST to /chat/completions and return the assistant message content."""
    url = endpoint.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(
            f"llama-cpp endpoint returned HTTP {exc.code}: {body_text}"
        ) from exc
    except urllib.error.URLError as exc:
        hint = ""
        if _is_wsl():
            hint = (
                " Running qq under WSL cannot reach a llama-server that "
                "listens only on the Windows host's 127.0.0.1. Fix: run "
                "llama-server inside WSL (recommended), or on Windows bind it "
                "with --host 0.0.0.0 and let QonQrete auto-detect it, or set "
                "QQ_LLAMA_CPP_ENDPOINT=http://<windows-host-ip>:8888/v1."
            )
        raise RuntimeError(
            f"Could not reach llama-cpp endpoint {url}: {exc.reason}. "
            "Is llama.cpp running? Check QQ_LLAMA_CPP_ENDPOINT." + hint
        ) from exc

    try:
        resp_json = json.loads(body)
        return resp_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Unexpected response from llama-cpp endpoint: {body[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class LlamaCppAdapter(AgentAdapter):
    """OpenAI-compatible adapter targeting a local llama.cpp server.

    The server is assumed to already have a model loaded. QonQrete sends
    model="local" (or whatever default_model is set to in providers.yaml),
    which llama.cpp ignores — it always uses its currently loaded model.
    """

    name = "llama-cpp"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        event_log_cb: Optional[Callable] = None,
    ):
        self.endpoint = (
            endpoint
            or os.environ.get("QQ_LLAMA_CPP_ENDPOINT")
            or _DEFAULT_ENDPOINT
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("QQ_LLAMA_CPP_API_KEY") or None
        self._output_event_log = event_log_cb
        self._candidates = _endpoint_candidates(self.endpoint)
        self._resolved_endpoint: Optional[str] = None

    def _effective_endpoint(self) -> str:
        """Return the first reachable endpoint for this process.

        Outside WSL (or when only the configured candidate exists) the
        configured endpoint is returned untouched — zero behavior change on
        macOS / native Windows / plain Linux. Inside WSL the loopback
        candidate is probed first; if nothing listens there (the typical
        "llama-server runs on the Windows host" layout), each Windows-host
        candidate from ``_wsl_windows_host_ips()`` is probed and the first
        open one is cached for every later role call.
        """
        if self._resolved_endpoint is not None:
            return self._resolved_endpoint
        if not _is_wsl() or len(self._candidates) == 1:
            self._resolved_endpoint = self.endpoint
            return self._resolved_endpoint

        def _host_port(url: str):
            p = urlsplit(url)
            return p.hostname or "", p.port or (443 if p.scheme == "https" else 80)

        host, port = _host_port(self.endpoint)
        if _port_open(host, port):
            self._resolved_endpoint = self.endpoint
            return self._resolved_endpoint
        for cand in self._candidates[1:]:
            host, port = _host_port(cand)
            if _port_open(host, port):
                self._resolved_endpoint = cand
                return cand
        # Nothing reachable — keep the canonical URL so the error that
        # surfaces later names exactly what the user configured.
        self._resolved_endpoint = self.endpoint
        return self._resolved_endpoint

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_sessions=False,
            supports_interactive_tui=False,
            supports_exec_mode=True,
            supports_tools=False,   # llama.cpp has no native tool-use protocol
            supports_thinking_mode=False,
            requires_host_mode=False,
            safe_in_container=True,
        )

    def call(self, spec: AgentCallSpec) -> AgentCallResult:
        os.makedirs(spec.workdir, exist_ok=True)
        output_path = (
            spec.output_file
            if os.path.isabs(spec.output_file)
            else os.path.join(spec.workdir, spec.output_file)
        )
        if os.path.exists(output_path):
            os.remove(output_path)

        sink = getattr(spec, "output_sink", None)
        role = spec.role
        call_id = getattr(spec, "call_id", "")

        def _emit(text: str) -> None:
            chunk = {"role": role, "stream_name": "stdout", "text": text, "call_id": call_id}
            if sink:
                try:
                    sink(chunk)
                except Exception:
                    pass
            if self._output_event_log:
                try:
                    self._output_event_log(chunk)
                except Exception:
                    pass

        endpoint = self._effective_endpoint()
        _emit(f"[llama-cpp] {role} → {endpoint}/chat/completions\n")
        if endpoint != self.endpoint:
            _emit(
                "[llama-cpp] WSL: llama-server not reachable on loopback "
                f"({self.endpoint}) — using Windows-host endpoint {endpoint}\n"
            )

        system_msg = _system_prompt_for_role(role)
        # Inject the output file path into the user prompt so the model knows
        # where to write — mirrors what the CodeSeeq adapter does via the CLI.
        augmented_prompt = (
            spec.prompt
            + f"\n\n---\nWrite your JSON response to: {output_path}\n"
            "Respond with ONLY the raw JSON object, nothing else."
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": augmented_prompt},
        ]

        start = time.time()
        stdout = ""
        stderr = ""
        exit_code = 0
        raw_output = None
        exists = False

        try:
            content = _chat_completion(
                endpoint=endpoint,
                api_key=self.api_key,
                model=spec.model or "local",
                messages=messages,
                temperature=spec.temperature,
                top_p=spec.top_p,
                timeout=spec.timeout_seconds or _STREAM_TIMEOUT,
            )

            # Strip markdown fences if the model wrapped the JSON anyway
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                # drop first fence line and last fence line
                inner = lines[1:] if lines[0].startswith("```") else lines
                if inner and inner[-1].strip() == "```":
                    inner = inner[:-1]
                cleaned = "\n".join(inner).strip()

            # Write the output file ourselves (the model can't literally write
            # files — we extract the JSON from its response and write it)
            try:
                parsed = json.loads(cleaned)
                with open(output_path, "w", encoding="utf-8") as fh:
                    json.dump(parsed, fh, indent=2)
                exists = True
                raw_output = json.dumps(parsed, indent=2)
                stdout = f"[llama-cpp] {role} completed — output written to {output_path}\n"
                _emit(stdout)
            except json.JSONDecodeError as exc:
                stderr = (
                    f"[llama-cpp] WARNING: model response was not valid JSON: {exc}\n"
                    f"Raw response (first 500 chars): {cleaned[:500]}\n"
                )
                _emit(stderr)
                # Write the raw text anyway so the caller can inspect it
                with open(output_path, "w", encoding="utf-8") as fh:
                    fh.write(cleaned)
                exists = True
                raw_output = cleaned
                exit_code = 1

        except RuntimeError as exc:
            stderr = f"[llama-cpp] ERROR: {exc}\n"
            _emit(stderr)
            exit_code = 1

        duration = time.time() - start

        # Write artifacts
        arts_dir = getattr(spec, "artifact_dir", "")
        if arts_dir:
            os.makedirs(arts_dir, exist_ok=True)
            for fname, content_str in [("stdout.txt", stdout), ("stderr.txt", stderr)]:
                with open(os.path.join(arts_dir, fname), "w", encoding="utf-8") as fh:
                    fh.write(content_str)
            if raw_output:
                with open(os.path.join(arts_dir, "result.json"), "w", encoding="utf-8") as fh:
                    fh.write(raw_output)

        return AgentCallResult(
            spec=spec,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            output_path_exists=exists,
            raw_output_text=raw_output,
        )
