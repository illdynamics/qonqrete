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
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional, Callable

from .base import AgentAdapter, AgentCallResult, AgentCallSpec, Capabilities


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_ENDPOINT = "http://127.0.0.1:8888/v1"
_CONNECT_TIMEOUT = 30   # seconds for initial connection
_STREAM_TIMEOUT = 1800  # seconds for the full completion (matches codeseeq default)


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
        raise RuntimeError(
            f"Could not reach llama-cpp endpoint {url}: {exc.reason}. "
            "Is llama.cpp running? Check QQ_LLAMA_CPP_ENDPOINT."
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

        _emit(f"[llama-cpp] {role} → {self.endpoint}/chat/completions\n")

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
                endpoint=self.endpoint,
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
