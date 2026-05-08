#!/usr/bin/env python3
# worqer/lib_ai.py
"""Central AI abstraction with provider-aware budgeting and audited chunking."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


try:
    from worqer import qompressor
except ImportError:
    try:
        import qompressor
    except ImportError:
        qompressor = None

try:
    from worqer.lib_loqal import safe_write_file
except ImportError:
    try:
        from lib_loqal import safe_write_file
    except ImportError:
        safe_write_file = None


DEFAULT_API_TIMEOUT = 600
DEFAULT_MAX_PROMPT_CHARS = 800_000
DEFAULT_MAX_CONTEXT_FILES = 100
DEFAULT_MAX_CHARS_PER_FILE = 150_000
STRING_HARD_LIMIT = 9_500_000
DEFAULT_ACK_TEMPLATE = "ACK CHUNK {index}/{total} HASH {hash}"
MAX_TIMEOUT_SECONDS = 300

VOLATILE_SECTION_TYPES = {
    "full_editable_context",
    "task",
    "repair_context",
    "hotset_payload",
    "previous_log",
    "user_prompt",
}

# ─────────────────────────────────────────────────────────────────────────────
# v1.3.13: STREAMING SUPPORT
# ─────────────────────────────────────────────────────────────────────────────
# Prior to v1.3.13 every dispatcher blocked on the full response before any
# output was visible. That meant InstruQtor/ConstruQtor/InspeQtor would appear
# to "hang" for 30-120+ seconds with no sign of progress while the model was
# in fact generating tokens. From v1.3.13 onward every dispatcher supports
# incremental streaming. When enabled (default) token deltas are written to
# stderr in real time so users see the model thinking. The accumulated text
# and the final DispatchResult shape are preserved exactly so downstream
# parsers, audit records, chunk ACK matching and tool-call handling are all
# unchanged. Tool-call streaming is enabled only for providers where delta
# reassembly is implemented (OpenAI-compatible paths in this module) and can
# be disabled globally via QONQ_STREAM_TOOLS=0.
# ─────────────────────────────────────────────────────────────────────────────


def _streaming_enabled() -> bool:
    """Return True unless QONQ_STREAMING is explicitly set to a falsey value."""
    val = os.environ.get("QONQ_STREAMING", "1").strip().lower()
    return val not in ("0", "false", "no", "off", "")


def _default_stream_callback(agent_name: str | None = None):
    """Build a default stderr-writing stream callback.

    Writes token deltas to stderr with flush on every write so the user can
    observe the model generating in real time. Returns a tuple of
    (callback, finalizer). The finalizer should be called once at end of
    stream to emit the terminating newline.
    """
    state = {
        "agent": agent_name or "ai",
        "buffer": "",
        "max_line_chars": max(20, int(os.environ.get("QONQ_STREAM_LINE_CHARS", "60"))),
    }

    def _emit_ready_lines(force: bool = False) -> None:
        buffer = state["buffer"]
        if not buffer:
            return
        
        # v1.3.13: Use smaller chunks for "live" feel
        stream_line_chars = state["max_line_chars"]
        
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            try:
                sys.stderr.write(f"[stream:{state['agent']}] {line}\n")
                sys.stderr.flush()
            except Exception:
                pass
        
        # Aggressively emit long lines in chunks even without newline
        while len(buffer) >= stream_line_chars:
            line = buffer[:stream_line_chars]
            buffer = buffer[stream_line_chars:]
            try:
                sys.stderr.write(f"[stream:{state['agent']}] {line}\n")
                sys.stderr.flush()
            except Exception:
                pass
        
        if force and buffer:
            try:
                sys.stderr.write(f"[stream:{state['agent']}] {buffer}\n")
                sys.stderr.flush()
            except Exception:
                pass
            buffer = ""
        
        state["buffer"] = buffer

    def _cb(delta: str) -> None:
        if not delta:
            return
        state["buffer"] += str(delta)
        _emit_ready_lines(force=False)

    def _finalize() -> None:
        _emit_ready_lines(force=True)

    return _cb, _finalize


def _tool_streaming_enabled() -> bool:
    val = os.environ.get("QONQ_STREAM_TOOLS", "1").strip().lower()
    return val not in ("0", "false", "no", "off", "")


def _resolve_stream_callback(
    stream_callback,
    agent_name: str | None,
    tools,
    *,
    allow_tool_streaming: bool = False,
    telemetry_callback=None,
    telemetry_finalize=None,
):
    """Decide whether to stream, and return (callback, finalizer).

    Priority:
      1. Explicit stream_callback=False or tools present without explicit
         provider support -> no streaming.
      2. Callable provided -> use it (finalizer is a no-op).
      3. None + streaming enabled -> default stderr callback.
      4. None + streaming disabled -> no streaming.
    """
    def _wrap_handlers(cb, finalize_cb):
        if cb is None:
            return None, (telemetry_finalize or (lambda: None))

        def _wrapped_cb(delta):
            if telemetry_callback is not None:
                try:
                    telemetry_callback(delta)
                except Exception:
                    pass
            cb(delta)

        def _wrapped_finalize():
            try:
                finalize_cb()
            finally:
                if telemetry_finalize is not None:
                    try:
                        telemetry_finalize()
                    except Exception:
                        pass

        return _wrapped_cb, _wrapped_finalize

    if stream_callback is False:
        return None, lambda: None
    if tools and not (allow_tool_streaming and _tool_streaming_enabled()):
        return None, lambda: None
    if callable(stream_callback):
        return _wrap_handlers(stream_callback, lambda: None)
    if stream_callback is None and _streaming_enabled():
        default_cb, default_finalize = _default_stream_callback(agent_name)
        return _wrap_handlers(default_cb, default_finalize)
    return None, lambda: None


def _coerce_stream_tool_delta(raw: Any) -> dict[str, Any]:
    """Normalize a streamed tool-call delta object into a plain dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        try:
            dumped = raw.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    out: dict[str, Any] = {}
    for key in ("index", "id", "type", "function"):
        value = getattr(raw, key, None)
        if value is None:
            continue
        if key == "function":
            if isinstance(value, dict):
                out[key] = dict(value)
            else:
                fn_data: dict[str, Any] = {}
                fn_name = getattr(value, "name", None)
                fn_args = getattr(value, "arguments", None)
                if fn_name is not None:
                    fn_data["name"] = fn_name
                if fn_args is not None:
                    fn_data["arguments"] = fn_args
                if fn_data:
                    out[key] = fn_data
        else:
            out[key] = value
    return out


def _accumulate_stream_tool_calls(tool_state: dict[int, dict[str, Any]], delta_tool_calls: Any) -> None:
    """Reassemble streamed tool-call fragments into OpenAI-compatible objects."""
    if not delta_tool_calls:
        return
    if not isinstance(delta_tool_calls, list):
        delta_tool_calls = [delta_tool_calls]
    for raw_item in delta_tool_calls:
        item = _coerce_stream_tool_delta(raw_item)
        if not item:
            continue
        try:
            idx = int(item.get("index", len(tool_state)))
        except Exception:
            idx = len(tool_state)
        entry = tool_state.setdefault(
            idx,
            {
                "id": item.get("id") or f"call_stream_{idx}",
                "type": item.get("type") or "function",
                "function": {"name": "", "arguments": ""},
            },
        )
        if item.get("id"):
            entry["id"] = item["id"]
        if item.get("type"):
            entry["type"] = item["type"]
        function = item.get("function") or {}
        if not isinstance(function, dict):
            function = {}
        fn_name = function.get("name")
        if isinstance(fn_name, str) and fn_name:
            if not entry["function"]["name"]:
                entry["function"]["name"] = fn_name
            elif fn_name != entry["function"]["name"] and not entry["function"]["name"].endswith(fn_name):
                entry["function"]["name"] += fn_name
        fn_args = function.get("arguments")
        if fn_args is not None:
            entry["function"]["arguments"] += str(fn_args)


def _finalize_stream_tool_calls(tool_state: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    if not tool_state:
        return []
    finalized: list[dict[str, Any]] = []
    for idx in sorted(tool_state):
        item = tool_state[idx]
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        finalized.append(
            {
                "id": item.get("id") or f"call_stream_{idx}",
                "type": item.get("type") or "function",
                "function": {
                    "name": str(fn.get("name") or ""),
                    "arguments": str(fn.get("arguments") or ""),
                },
            }
        )
    return finalized


class TimeoutError(Exception):
    pass


@dataclass
class PromptSection:
    label: str
    content: str
    required: bool = False
    loss_policy: str = "preserve"  # preserve | droppable | summarizable | chunkable
    section_type: str = "text"
    source_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_tokens: int = 0
    omitted: bool = False
    summarized: bool = False
    chunked: bool = False
    omit_reason: str | None = None
    summary_reason: str | None = None
    original_tokens: int = 0
    original_chars: int = 0
    hash: str = ""


@dataclass
class ChunkRecord:
    chunk_index: int
    chunk_total: int
    section_label: str
    section_hash: str
    chunk_hash: str
    estimated_tokens: int
    text: str


@dataclass
class DispatchResult:
    text: str
    response_truncated: bool
    provider_metadata: dict[str, Any]
    preload_acks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelCapabilities:
    provider: str
    model_pattern: str
    safe_input_tokens: int
    safe_output_tokens: int
    total_context_window: int | None
    chars_per_token: float
    supports_multi_message_history: bool
    supports_chunk_preload: bool
    supports_system_messages: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityResolution:
    base: ModelCapabilities
    effective: ModelCapabilities
    applied_overrides: list[dict[str, Any]]
    warnings: list[str]


DEFAULT_CAPABILITY = ModelCapabilities(
    provider="default",
    model_pattern="*",
    safe_input_tokens=12000,
    safe_output_tokens=2000,
    total_context_window=16000,
    chars_per_token=4.0,
    supports_multi_message_history=True,
    supports_chunk_preload=False,
    supports_system_messages=True,
)


CAPABILITY_TABLE: tuple[ModelCapabilities, ...] = (
    ModelCapabilities("openai", "gpt-4.1*", 90000, 8000, 128000, 4.0, True, True, True),
    ModelCapabilities("openai", "gpt-4o*", 90000, 8000, 128000, 4.0, True, True, True),
    ModelCapabilities("gemini", "gemini-2.5-pro*", 120000, 8192, 128000, 4.0, True, True, True),
    ModelCapabilities("gemini", "gemini-2.5-flash*", 80000, 8192, 100000, 4.0, True, True, True),
    ModelCapabilities("gemini", "gemini-2.0-flash*", 50000, 4096, 64000, 4.0, True, True, True),
    ModelCapabilities("anthropic", "claude-sonnet-4*", 100000, 8192, 128000, 3.5, True, True, True),
    ModelCapabilities("anthropic", "claude-3-5-sonnet*", 80000, 8192, 100000, 3.5, True, True, True),
    ModelCapabilities("anthropic", "claude-opus-4*", 100000, 8192, 128000, 3.5, True, True, True),
    ModelCapabilities("deepseek", "deepseek-reasoner*", 32000, 8192, 48000, 4.0, True, True, True),
    ModelCapabilities("deepseek", "deepseek-chat*", 32000, 8192, 48000, 4.0, True, True, True),
    ModelCapabilities("deepseek", "deepseek-coder*", 32000, 8192, 48000, 4.0, True, True, True),
    ModelCapabilities("qwen", "qwen*", 32000, 4096, 48000, 4.0, True, True, True),
    ModelCapabilities("openrouter", "*", 32000, 4096, 48000, 4.0, True, True, True),
    # v1.3.12: mlx and llama-cpp providers (local / LAN OpenAI-compatible runtimes).
    # "model" is OPTIONAL. External runtime decides the actual model if omitted.
    ModelCapabilities("mlx", "*", 8192, 8192, 16384, 4.0, True, True, True),
    ModelCapabilities("llama-cpp", "*", 4096, 4096, 8192, 4.0, True, True, True),
    # v1.3.12: venice provider (Venice API, OpenAI-compatible). The user sets
    # a REAL Venice model ID in `model`. Defaults are generous; per-agent
    # context_window / max_tokens may override for specific models.
    ModelCapabilities("venice", "qwen3-coder-480b-a35b-instruct-turbo", 120000, 8192, 128000, 4.0, True, True, True),
    ModelCapabilities("venice", "*", 80000, 8192, 100000, 4.0, True, True, True),
    ModelCapabilities("codeseeq", "deepseek-v4-flash", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek-v4-flash-thinking", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek-v4-pro", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek-v4-pro-thinking", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek@deepseek-v4-flash", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek@deepseek-v4-flash-thinking", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek@deepseek-v4-pro", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "deepseek@deepseek-v4-pro-thinking", 616000, 384000, 1000000, 3.33, True, False, True),
    ModelCapabilities("codeseeq", "*", 616000, 384000, 1000000, 3.33, True, False, True),
)


def _config_path_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    module_dir = here.parent
    project_root = module_dir.parent

    roots: list[Path] = []
    env_workspace = os.environ.get("QONQ_WORKSPACE", "").strip()
    if env_workspace:
        roots.append(Path(env_workspace))

    roots.extend([
        Path.cwd(),
        module_dir,
        project_root,
    ])

    candidates: list[Path] = []
    seen: set[Path] = set()

    for root in roots:
        for candidate in (
            root / "config.yaml",
            root / "worqspace" / "config.yaml",
        ):
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(candidate)

    return candidates


def load_runtime_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    for path in _config_path_candidates():
        if not path.exists():
            continue
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(loaded, dict):
            return loaded
        if loaded is None:
            return {}
    return {}


def _lookup_base_capabilities(provider: str, model: str) -> ModelCapabilities:
    provider_l = (provider or "default").lower()
    model_l = (model or "").lower()
    for entry in CAPABILITY_TABLE:
        if entry.provider == provider_l and fnmatch.fnmatch(model_l, entry.model_pattern.lower()):
            return entry
    for entry in CAPABILITY_TABLE:
        if entry.provider == provider_l and entry.model_pattern == "*":
            return entry
    return ModelCapabilities(
        provider=provider_l,
        model_pattern=model or "*",
        safe_input_tokens=DEFAULT_CAPABILITY.safe_input_tokens,
        safe_output_tokens=DEFAULT_CAPABILITY.safe_output_tokens,
        total_context_window=DEFAULT_CAPABILITY.total_context_window,
        chars_per_token=DEFAULT_CAPABILITY.chars_per_token,
        supports_multi_message_history=DEFAULT_CAPABILITY.supports_multi_message_history,
        supports_chunk_preload=DEFAULT_CAPABILITY.supports_chunk_preload,
        supports_system_messages=DEFAULT_CAPABILITY.supports_system_messages,
    )


_CAPABILITY_NUMERIC_LIMIT_FIELDS = {
    "safe_input_tokens",
    "safe_output_tokens",
    "total_context_window",
}


def _apply_capability_override(cap: ModelCapabilities, override: dict[str, Any]) -> ModelCapabilities:
    if not override:
        return cap
    payload = cap.to_dict()
    payload.update({key: value for key, value in override.items() if key in payload and value is not None})
    return ModelCapabilities(**payload)


def _apply_capability_override_with_audit(
    cap: ModelCapabilities,
    override: dict[str, Any],
    *,
    base_cap: ModelCapabilities,
    source: str,
    trusted: bool,
    applied_overrides: list[dict[str, Any]],
    warnings: list[str],
) -> ModelCapabilities:
    if not override:
        return cap

    payload = cap.to_dict()
    requested: dict[str, Any] = {}
    effective: dict[str, Any] = {}
    for key, raw_value in override.items():
        if key not in payload or raw_value is None:
            continue
        requested[key] = raw_value
        value = raw_value

        if key in _CAPABILITY_NUMERIC_LIMIT_FIELDS:
            try:
                requested_int = int(raw_value)
                base_value = getattr(base_cap, key)
                base_int = int(base_value) if base_value is not None else None
            except (TypeError, ValueError):
                continue

            if requested_int <= 0:
                warnings.append(f"{source}.{key} ignored because it is not positive: {raw_value!r}")
                continue
            if base_int is not None and requested_int > base_int and not trusted:
                value = base_int
                warnings.append(
                    f"{source}.{key}={requested_int} exceeds base capability {base_int}; "
                    "capped because trust_provider_context_overrides is not true"
                )
            else:
                value = requested_int

        payload[key] = value
        effective[key] = value

    if requested:
        applied_overrides.append({
            "source": source,
            "trusted": bool(trusted),
            "requested": requested,
            "effective": effective,
        })

    return ModelCapabilities(**payload)


def _get_agent_config(config: dict[str, Any] | None, agent_name: str | None) -> dict[str, Any]:
    """v1.3.12: fetch per-agent config block from runtime config."""
    if not agent_name or not isinstance(config, dict):
        return {}
    agents_cfg = config.get("agents", {})
    if not isinstance(agents_cfg, dict):
        return {}
    block = agents_cfg.get(agent_name, {})
    return block if isinstance(block, dict) else {}


def _agent_capability_override(agent_cfg: dict[str, Any]) -> dict[str, Any]:
    """v1.3.12: translate per-agent context_window / max_tokens into capability overrides.

    - context_window sets total_context_window
    - max_tokens sets safe_output_tokens
    - safe_input_tokens is derived as (context_window - max_tokens) with a small
      headroom and a 2000-token floor, but only when both are provided; otherwise
      existing capability values are preserved.
    """
    if not agent_cfg:
        return {}
    override: dict[str, Any] = {}
    ctx = agent_cfg.get("context_window")
    max_tok = agent_cfg.get("max_tokens")
    try:
        ctx_int = int(ctx) if ctx is not None else None
    except (TypeError, ValueError):
        ctx_int = None
    try:
        max_tok_int = int(max_tok) if max_tok is not None else None
    except (TypeError, ValueError):
        max_tok_int = None
    if ctx_int is not None and ctx_int > 0:
        override["total_context_window"] = ctx_int
    if max_tok_int is not None and max_tok_int > 0:
        override["safe_output_tokens"] = max_tok_int
    if ctx_int is not None and max_tok_int is not None and ctx_int > max_tok_int:
        headroom = 512
        override["safe_input_tokens"] = max(2000, ctx_int - max_tok_int - headroom)
    return override


def get_agent_ai_params(config: dict[str, Any], agent_name: str, default_provider: str, default_model: str) -> tuple[str, str]:
    """v1.3.12: Fetch provider and model with proper optional-model semantics.
    
    If provider is mlx or llama-cpp and model is omitted in config, returns (provider, "").
    Otherwise, returns (provider, model) with provided defaults.
    """
    agent_cfg = _get_agent_config(config, agent_name)
    provider = str(agent_cfg.get("provider", default_provider) or default_provider).strip()
    
    # If provider is local/LAN, model is truly optional.
    if provider.lower() in {"mlx", "llama-cpp"}:
        model = str(agent_cfg.get("model", "") or "").strip()
        return provider, model
    
    model = str(agent_cfg.get("model", default_model) or default_model).strip()
    if not model:
        model = str(default_model or "").strip()
    return provider, model


def resolve_model_capability_details(
    provider: str,
    model: str,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
) -> CapabilityResolution:
    runtime_config = load_runtime_config(config)
    base_cap = _lookup_base_capabilities(provider, model)
    cap = base_cap
    applied_overrides: list[dict[str, Any]] = []
    warnings: list[str] = []

    ai_budget = runtime_config.get("ai_budgeting", {})
    provider_overrides = ai_budget.get("providers", {}).get((provider or "").lower(), {})
    trust_provider_overrides = bool(
        ai_budget.get("trust_provider_context_overrides", False)
        or (provider_overrides or {}).get("trust_provider_context_overrides", False)
        or (provider_overrides or {}).get("trust_context_overrides", False)
    )
    if provider_overrides:
        cap = _apply_capability_override_with_audit(
            cap,
            provider_overrides.get("defaults", {}),
            base_cap=base_cap,
            source=f"providers.{(provider or '').lower()}.defaults",
            trusted=trust_provider_overrides,
            applied_overrides=applied_overrides,
            warnings=warnings,
        )
        for pattern, override in provider_overrides.get("models", {}).items():
            if fnmatch.fnmatch((model or "").lower(), pattern.lower()):
                cap = _apply_capability_override_with_audit(
                    cap,
                    override,
                    base_cap=base_cap,
                    source=f"providers.{(provider or '').lower()}.models.{pattern}",
                    trusted=trust_provider_overrides or bool((override or {}).get("trust_provider_context_overrides", False)),
                    applied_overrides=applied_overrides,
                    warnings=warnings,
                )

    # v1.3.12: per-agent context_window / max_tokens override takes priority.
    agent_cfg = _get_agent_config(runtime_config, agent_name)
    agent_override = _agent_capability_override(agent_cfg)
    if agent_override:
        cap = _apply_capability_override_with_audit(
            cap,
            agent_override,
            base_cap=base_cap,
            source=f"agents.{agent_name}",
            trusted=bool(agent_cfg.get("trust_provider_context_overrides", False)),
            applied_overrides=applied_overrides,
            warnings=warnings,
        )

    return CapabilityResolution(
        base=base_cap,
        effective=cap,
        applied_overrides=applied_overrides,
        warnings=warnings,
    )


def resolve_model_capabilities(provider: str, model: str, config: dict[str, Any] | None = None, agent_name: str | None = None) -> ModelCapabilities:
    return resolve_model_capability_details(provider, model, config=config, agent_name=agent_name).effective


def _default_api_timeout() -> int:
    raw = os.environ.get("QONQ_AI_TIMEOUT", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if 0 < parsed <= MAX_TIMEOUT_SECONDS * 4:
                return parsed
        except ValueError:
            pass
    return DEFAULT_API_TIMEOUT


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _estimate_tokens(text: str, chars_per_token: float) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / max(chars_per_token, 1.0)))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()




def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _worqspace_root(config: dict[str, Any] | None = None) -> Path:
    env_root = os.environ.get("QONQ_WORKSPACE", "").strip()
    if env_root:
        return Path(env_root)

    cfg = config or {}
    path_cfg = cfg.get("paths", {})
    for key in ("worqspace", "workspace", "root"):
        path = path_cfg.get(key)
        if path:
            return Path(path)

    for candidate in _config_path_candidates():
        if candidate.exists():
            return candidate.parent

    return _project_root() / "worqspace"


def _prompt_char_count(prompt: str, prompt_sections: list[dict[str, Any]] | None) -> int:
    if prompt_sections:
        return sum(len(str(section.get("content", ""))) for section in prompt_sections)
    return len(prompt)


def _stable_prefix_from_sections(sections: list["PromptSection"]) -> str:
    stable_parts: list[str] = []
    for section in sections:
        if section.omitted:
            continue
        if section.section_type in VOLATILE_SECTION_TYPES:
            break
        stable_parts.append(section.content)
    return "".join(stable_parts).strip()


def _provider_cache_config(config: dict[str, Any], agent_name: str | None) -> dict[str, Any]:
    agent_cfg = _get_agent_config(config, agent_name)
    qontrabender_cfg = (config.get("agents", {}) or {}).get("qontrabender", {}) if isinstance(config, dict) else {}
    out: dict[str, Any] = {}
    for src in (
        qontrabender_cfg.get("provider_cache"),
        agent_cfg.get("provider_cache"),
        (config.get("provider_cache") if isinstance(config, dict) else None),
    ):
        if isinstance(src, dict):
            out.update(src)
    return out


def _render_prompt_cache_key(template: str, *, config: dict[str, Any], stable_prefix: str) -> str:
    root = _worqspace_root(config)
    qage_id = root.name
    context_hash = _sha256_text(stable_prefix)[:16]
    try:
        return template.format(qage_id=qage_id, context_hash=context_hash)
    except Exception:
        return ""


def _build_cache_envelope(
    *,
    provider: str,
    config: dict[str, Any],
    agent_name: str | None,
    sections: list["PromptSection"],
    qache_dir: str | None = None,
) -> dict[str, Any]:
    provider_l = str(provider or "").strip().lower()
    stable_prefix = _stable_prefix_from_sections(sections)
    cfg = _provider_cache_config(config, agent_name)
    cache_enabled = str(cfg.get("enabled", "true")).strip().lower() not in {"0", "false", "no", "off"}
    if not cache_enabled:
        return {"backend": "disabled", "stable_prefix": stable_prefix}

    backend = "local_only"

    # Read qache.d manifest to align backend with Qontrabender
    qache_manifest_backend: str | None = None
    if qache_dir:
        manifest_path = Path(qache_dir) / "context_bundle_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("schema_version") == "context_bundle_manifest.v1":
                    qache_manifest_backend = str(manifest.get("cache_backend") or "").strip() or None
            except Exception:
                pass

    if qache_manifest_backend:
        backend = qache_manifest_backend
    elif provider_l in {"openai", "deepseek", "qwen", "openrouter", "venice", "codeseeq"}:
        backend = "stable_prefix_auto"
    elif provider_l in {"anthropic"}:
        if str(cfg.get("anthropic_cache_control_enabled", "true")).strip().lower() in {"0", "false", "no", "off"}:
            backend = "stable_prefix_auto"
        else:
            backend = "anthropic_cache_control"
    elif provider_l in {"gemini", "google"}:
        # Default to stable_prefix_auto; gemini_explicit only if manifest says so
        backend = "stable_prefix_auto"

    if provider_l in {"gemini", "google"} and backend == "gemini_explicit":
        # Safe fallback path: this codebase does not have a verified Gemini
        # CachedContent dispatch implementation, so never fake explicit cache use.
        backend = "stable_prefix_auto"

    envelope: dict[str, Any] = {
        "backend": backend,
        "stable_prefix": stable_prefix,
    }

    template = str(cfg.get("prompt_cache_key_template") or "").strip()
    openai_prompt_cache_enabled = str(cfg.get("openai_prompt_cache_key_enabled", "false")).strip().lower() in {"1", "true", "yes", "on"}
    if provider_l == "openai" and openai_prompt_cache_enabled and template and stable_prefix:
        key = _render_prompt_cache_key(template, config=config, stable_prefix=stable_prefix)
        if key:
            envelope["prompt_cache_key"] = key

    anth_cache_enabled = str(cfg.get("anthropic_cache_control_enabled", "true")).strip().lower() not in {"0", "false", "no", "off"}
    if provider_l == "anthropic" and anth_cache_enabled and stable_prefix:
        ttl_minutes = cfg.get("cache_ttl_minutes")
        try:
            ttl_minutes_int = int(ttl_minutes) if ttl_minutes is not None else 0
        except Exception:
            ttl_minutes_int = 0
        envelope["anthropic_cache_control"] = {"enabled": True, "ttl_minutes": ttl_minutes_int}

    return envelope


def _resolve_path_within_root(root: Path, configured_path: str) -> Path:
    root_resolved = root.resolve()
    candidate = Path(configured_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root_resolved / candidate).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise RuntimeError(f"Configured path escapes worqspace root: {configured_path}") from exc
    return resolved


def _sanitize_name(value: str) -> str:
    keep = []
    for char in value.lower():
        keep.append(char if char.isalnum() or char in {"-", "_"} else "-")
    return "".join(keep).strip("-") or "call"


def _read_text_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        sys.stderr.write(f"\n[WARN] Could not read context file {path}: {exc}\n")
        return None


def _summarize_text_block(content: str, max_lines: int = 120, max_chars: int = 12000) -> str:
    lines = [line for line in content.splitlines() if line.strip()]
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... [omitted {len(content.splitlines()) - max_lines} lines after summary cap]"]
    summarized = "\n".join(lines)
    if len(summarized) > max_chars:
        summarized = summarized[:max_chars] + "\n... [omitted after summary char cap]"
    return summarized


def _sanitize_previous_log(content: str) -> str:
    """Redact likely secrets and user-specific local path segments from prior logs."""
    if not content:
        return content

    redacted = content

    redacted = re.sub(
        r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?im)\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY|ACCESS_KEY|AUTH)\b\s*[:=]\s*)(['\"]?)([^'\"\s]+)(\2)",
        r"\1\2[REDACTED]\4",
        redacted,
    )
    redacted = re.sub(
        r"(?im)\b((?:openai|anthropic|deepseek|qwen|openrouter|venice|gemini|google)[-_ ]?api[-_ ]?key\s*[:=]\s*)(['\"]?)([^'\"\s]+)(\2)",
        r"\1\2[REDACTED]\4",
        redacted,
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9]{16,}\b", "[REDACTED]", redacted)
    redacted = re.sub(r"\bAIza[0-9A-Za-z\-_]{20,}\b", "[REDACTED]", redacted)

    # Preserve path shape while avoiding username leakage.
    redacted = re.sub(r"/Users/[^/\s]+/", "/Users/[REDACTED]/", redacted)
    redacted = re.sub(r"/home/[^/\s]+/", "/home/[REDACTED]/", redacted)
    redacted = re.sub(r"([A-Za-z]:\\Users\\)[^\\\s]+\\", r"\1[REDACTED]\\", redacted)
    return redacted


def _maybe_compress_context(path: str, content: str) -> tuple[str, str | None]:
    if qompressor is None:
        return content, None
    try:
        compressed = qompressor.compress_file_content(path, content)
    except Exception:
        return content, None
    if compressed and len(compressed) + 64 < len(content):
        return compressed, "qompressor"
    return content, None


def _build_context_section(
    fpath: str,
    content: str,
    chars_per_token: float,
    per_file_limit: int,
    summarize_before_chunking: bool,
) -> PromptSection:
    source_name = os.path.basename(fpath)
    payload = content
    summary_reason = None
    if summarize_before_chunking:
        compressed, compression_kind = _maybe_compress_context(fpath, content)
        if compression_kind:
            payload = compressed
            summary_reason = compression_kind
        elif len(content) > per_file_limit:
            payload = _summarize_text_block(content, max_chars=min(per_file_limit, 12000))
            summary_reason = "heuristic_summary"
    label = f"context:{source_name}"
    block = f"\nFile: {fpath}\n```\n{payload}\n```\n"
    section = PromptSection(
        label=label,
        content=block,
        required=False,
        loss_policy="summarizable",
        section_type="context_file",
        source_files=[fpath],
        metadata={"path": fpath},
        summarized=summary_reason is not None,
        summary_reason=summary_reason,
    )
    section.original_chars = len(content)
    section.original_tokens = _estimate_tokens(content, chars_per_token)
    section.estimated_tokens = _estimate_tokens(section.content, chars_per_token)
    section.hash = _sha256_text(content)
    return section


def _previous_log_section(config: dict[str, Any], chars_per_token: float) -> PromptSection | None:
    ai_cfg = config.get("ai_budgeting", {})
    include_override = os.environ.get("QONQ_INCLUDE_PREVIOUS_LOG")
    if include_override is not None:
        normalized = include_override.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return None
        if normalized not in {"1", "true", "yes", "on"}:
            if not ai_cfg.get("include_previous_log", False):
                return None
    elif not ai_cfg.get("include_previous_log", False):
        return None
    prev_log_path = os.environ.get("QONQ_PREVIOUS_LOG")
    if not prev_log_path:
        return None
    path = Path(prev_log_path)
    if not path.exists():
        return None
    content = _read_text_file(path)
    if not content:
        return None
    max_chars = ai_cfg.get("previous_log_max_chars", 12000)
    if len(content) > max_chars:
        content = content[-max_chars:]
    content = _sanitize_previous_log(content)
    section = PromptSection(
        label="previous_log",
        content=f"\n--- PREVIOUS AGENT LOG (OPTIONAL REPAIR CONTEXT) ---\n{content}\n",
        required=False,
        loss_policy="droppable",
        section_type="previous_log",
        source_files=[str(path)],
    )
    section.original_chars = len(content)
    section.original_tokens = _estimate_tokens(content, chars_per_token)
    section.estimated_tokens = _estimate_tokens(section.content, chars_per_token)
    section.hash = _sha256_text(content)
    return section


def _normalize_sections(
    prompt: str,
    context_files: list[str],
    prompt_sections: list[dict[str, Any]] | None,
    config: dict[str, Any],
    caps,
    budget_config: dict[str, Any],
    include_previous_log: bool | None = None,
) -> list[PromptSection]:
    sections: list[PromptSection] = []

    if prompt_sections:
        for raw in prompt_sections:
            content = raw.get("content", "")
            section = PromptSection(
                label=raw.get("label", "section"),
                content=content,
                required=bool(raw.get("required", False)),
                loss_policy=raw.get("loss_policy", "preserve"),
                section_type=raw.get("section_type", "text"),
                source_files=list(raw.get("source_files", [])),
                metadata=dict(raw.get("metadata", {})),
            )
            section.original_chars = len(content)
            section.original_tokens = _estimate_tokens(content, caps.chars_per_token)
            section.estimated_tokens = section.original_tokens
            section.hash = _sha256_text(content)
            sections.append(section)

        # Avoid duplicate prompt-weighting when callers already passed prompt
        # through explicit prompt_sections (common in InspeQtor review paths).
        if prompt and str(prompt).strip():
            prompt_hash = _sha256_text(prompt)
            prompt_already_present = any(section.hash == prompt_hash for section in sections)
            if not prompt_already_present:
                base = PromptSection(
                    label="supplemental_prompt",
                    content=prompt,
                    required=True,
                    loss_policy="preserve",
                    section_type="user_prompt",
                )
                base.original_chars = len(prompt)
                base.original_tokens = _estimate_tokens(prompt, caps.chars_per_token)
                base.estimated_tokens = base.original_tokens
                base.hash = prompt_hash
                sections.append(base)
    else:
        base = PromptSection(
            label="core_prompt",
            content=prompt,
            required=True,
            loss_policy="preserve",
            section_type="base_prompt",
        )
        base.original_chars = len(prompt)
        base.original_tokens = _estimate_tokens(prompt, caps.chars_per_token)
        base.estimated_tokens = base.original_tokens
        base.hash = _sha256_text(prompt)
        sections.append(base)

    prev_log = None
    if include_previous_log is None:
        prev_log = _previous_log_section(config, caps.chars_per_token)
    elif include_previous_log:
        prev_log = _previous_log_section(config, caps.chars_per_token)
    if prev_log is not None:
        sections.append(prev_log)

    per_file_limit = budget_config["max_chars_per_file"]
    summarize_before_chunking = config.get("ai_budgeting", {}).get("summarize_optional_sections", True)
    for fpath in context_files[: budget_config["max_context_files"]]:
        path = Path(fpath)
        if not path.exists() or path.is_dir():
            continue
        content = _read_text_file(path)
        if not content:
            continue
        section = _build_context_section(
            fpath=fpath,
            content=content,
            chars_per_token=caps.chars_per_token,
            per_file_limit=per_file_limit,
            summarize_before_chunking=summarize_before_chunking,
        )
        sections.append(section)

    return sections


def _token_budget(config: dict[str, Any], caps, agent_name: str | None, output_tokens: int | None, task_type: str | None) -> dict[str, int]:
    ai_cfg = config.get("ai_budgeting", {})
    provider_cfg = ai_cfg.get("agent_output_tokens", {})
    default_output = output_tokens
    if default_output is None and agent_name:
        default_output = provider_cfg.get(agent_name)
    if default_output is None:
        task_defaults = ai_cfg.get("task_output_tokens", {})
        default_output = task_defaults.get(task_type or "", caps.safe_output_tokens)
    if default_output is None:
        default_output = caps.safe_output_tokens

    output_budget = min(int(default_output), caps.safe_output_tokens)
    input_budget = max(2000, int(caps.safe_input_tokens))
    return {"safe_input_tokens": input_budget, "safe_output_tokens": output_budget}


def _section_breakdown(sections: list[PromptSection]) -> list[dict[str, Any]]:
    items = []
    for section in sections:
        payload = asdict(section)
        payload.pop("content", None)
        items.append(payload)
    return items


def _optimize_sections(sections: list[PromptSection], input_budget: int, chars_per_token: float) -> tuple[list[PromptSection], list[dict[str, Any]], list[dict[str, Any]]]:
    dropped: list[dict[str, Any]] = []
    summarized: list[dict[str, Any]] = []

    def total_tokens() -> int:
        return sum(section.estimated_tokens for section in sections if not section.omitted)

    if total_tokens() <= input_budget:
        return sections, dropped, summarized

    for section in sections:
        if section.loss_policy == "droppable" and not section.required and not section.omitted:
            section.omitted = True
            section.omit_reason = "dropped_for_budget"
            dropped.append({"label": section.label, "reason": section.omit_reason, "estimated_tokens": section.estimated_tokens})
            if total_tokens() <= input_budget:
                return sections, dropped, summarized

    for section in sections:
        if section.loss_policy == "summarizable" and not section.required and not section.omitted and not section.summarized:
            summarized_content = _summarize_text_block(section.content)
            if len(summarized_content) < len(section.content):
                section.content = summarized_content
                section.summarized = True
                section.summary_reason = section.summary_reason or "budget_summary"
                section.estimated_tokens = _estimate_tokens(section.content, chars_per_token)
                summarized.append({"label": section.label, "reason": section.summary_reason, "estimated_tokens": section.estimated_tokens})
                if total_tokens() <= input_budget:
                    return sections, dropped, summarized

    for section in sections:
        if section.loss_policy == "summarizable" and not section.required and not section.omitted:
            section.omitted = True
            section.omit_reason = "omitted_after_summary_budget_failure"
            dropped.append({"label": section.label, "reason": section.omit_reason, "estimated_tokens": section.estimated_tokens})
            if total_tokens() <= input_budget:
                return sections, dropped, summarized

    return sections, dropped, summarized


def _chunk_text(text: str, max_chunk_chars: int) -> list[str]:
    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + max_chunk_chars)
        chunks.append(text[cursor:end])
        cursor = end
    return chunks


def _plan_chunks(
    sections: list[PromptSection],
    input_budget: int,
    chars_per_token: float,
    config: dict[str, Any],
    supports_chunking: bool,
) -> tuple[list[PromptSection], list[ChunkRecord], dict[str, Any]]:
    active_sections = [section for section in sections if not section.omitted]
    active_tokens = sum(section.estimated_tokens for section in active_sections)
    if active_tokens <= input_budget:
        return sections, [], {"chunking_used": False, "reason": "not_needed"}

    if not supports_chunking or not config.get("ai_budgeting", {}).get("enable_no_loss_chunking", True):
        required = [section.label for section in active_sections if section.required]
        raise RuntimeError(f"Prompt exceeds safe input budget and no-loss chunking is unavailable. Required sections: {required}")

    chunk_target_tokens = min(
        max(2000, input_budget // 2),
        config.get("ai_budgeting", {}).get("chunk_target_input_tokens", max(2000, input_budget // 2)),
    )
    max_preload_chunks = config.get("ai_budgeting", {}).get("max_preload_chunks_per_request", 24)
    max_chunk_chars = max(4000, int(chunk_target_tokens * chars_per_token))

    chunks: list[ChunkRecord] = []
    chunkable_sections = [section for section in active_sections if section.loss_policy == "chunkable" or (section.required and section.loss_policy == "preserve" and section.estimated_tokens > input_budget // 2)]
    if not chunkable_sections:
        raise RuntimeError("Prompt exceeds safe input budget but no sections are eligible for chunking.")

    for section in chunkable_sections:
        section.chunked = True
        split_texts = _chunk_text(section.content, max_chunk_chars)
        for text in split_texts:
            chunks.append(ChunkRecord(
                chunk_index=0,
                chunk_total=0,
                section_label=section.label,
                section_hash=section.hash,
                chunk_hash=_sha256_text(text),
                estimated_tokens=_estimate_tokens(text, chars_per_token),
                text=text,
            ))

    if len(chunks) > max_preload_chunks:
        raise RuntimeError(f"Chunk plan requires {len(chunks)} preload chunks which exceeds configured cap {max_preload_chunks}.")

    for idx, chunk in enumerate(chunks, start=1):
        chunk.chunk_index = idx
        chunk.chunk_total = len(chunks)

    for section in sections:
        if section.chunked:
            section.estimated_tokens = 0

    remaining_active = [section for section in sections if not section.omitted and not section.chunked]
    remaining_tokens = sum(section.estimated_tokens for section in remaining_active)
    if remaining_tokens > input_budget:
        raise RuntimeError("Inline prompt still exceeds budget after chunk planning.")

    return sections, chunks, {"chunking_used": True, "reason": "required_or_chunkable_sections_preloaded"}


def _build_inline_prompt(sections: list[PromptSection]) -> str:
    return "\n\n".join(section.content for section in sections if not section.omitted and not section.chunked).strip()


def _system_message() -> str:
    return "Follow the user's instructions exactly. Do not omit required provided context."


def _normalize_ack_response(text: str) -> str:
    """Strip <think> blocks and whitespace to normalize ACK replies.
    
    v1.3.13: Hardened normalization. Strips complete <think> blocks,
    removes unclosed <think> tags, and trims whitespace.
    """
    if not text:
        return ""
    import re
    # Remove complete <think>...</think> blocks (case-insensitive, dotall)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # If a stray <think> remains, it might be unclosed. We'll strip the tag itself 
    # and any leading whitespace, but keep the rest to see if the ACK followed.
    text = re.sub(r"<think>", "", text, flags=re.IGNORECASE)
    # Also strip any leading reasoning if the model didn't use tags but prefixed
    # the response with "Thought:" or similar common prefixes
    text = re.sub(r"^(?:thought|reasoning|analysis|explanation):\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    return text.strip()


def _build_preload_messages(chunks: list[ChunkRecord]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for chunk in chunks:
        ack = DEFAULT_ACK_TEMPLATE.format(index=chunk.chunk_index, total=chunk.chunk_total, hash=chunk.chunk_hash)
        preload = (
            "Store the following chunk faithfully for later use.\n"
            f"Chunk index: {chunk.chunk_index}/{chunk.chunk_total}\n"
            f"Section label: {chunk.section_label}\n"
            f"Section hash: {chunk.section_hash}\n"
            f"Chunk hash: {chunk.chunk_hash}\n"
            "CRITICAL: Do not summarize or transform this chunk. Do not think out loud. "
            "Do NOT emit <think> tags. Do NOT include reasoning, explanation, or extra text. "
            "Reply with EXACTLY the following line and NOTHING ELSE:\n"
            f"{ack}\n\n"
            "BEGIN CHUNK\n"
            f"{chunk.text}\n"
            "END CHUNK"
        )
        messages.append({"role": "user", "content": preload})
    return messages


def _build_final_user_message(inline_prompt: str, chunks: list[ChunkRecord]) -> str:
    if not chunks:
        return inline_prompt
    manifest_lines = [
        "The full request includes preloaded chunked context. Use every preloaded chunk exactly as stored.",
        "Chunk manifest:",
    ]
    for chunk in chunks:
        manifest_lines.append(
            f"- {chunk.chunk_index}/{chunk.chunk_total} | section={chunk.section_label} | section_hash={chunk.section_hash} | chunk_hash={chunk.chunk_hash}"
        )
    manifest_lines.append("")
    if inline_prompt:
        manifest_lines.append(inline_prompt)
    return "\n".join(manifest_lines).strip()



def _import_openai():
    try:
        import openai
    except ImportError as exc:
        raise RuntimeError("openai package is required for OpenAI-compatible providers.") from exc
    return openai


def _import_anthropic():
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package is required for Anthropic provider.") from exc
    return anthropic


def _anthropic_usage_to_dict(usage_obj: Any) -> dict[str, Any]:
    if usage_obj is None:
        return {}
    out = {
        "input_tokens": getattr(usage_obj, "input_tokens", None),
        "output_tokens": getattr(usage_obj, "output_tokens", None),
    }
    for key in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "input_tokens_cache_creation",
        "input_tokens_cache_read",
    ):
        value = getattr(usage_obj, key, None)
        if value is not None:
            out[key] = value
    return out


def _import_genai():
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai package is required for Gemini provider.") from exc
    return genai

def _openai_client_for_provider(provider: str, timeout: int, config: dict[str, Any] | None = None, agent_name: str | None = None, model: str | None = None):
    openai = _import_openai()
    provider_l = provider.lower()
    if provider_l == "openai":
        return openai.OpenAI(timeout=timeout)
    if provider_l == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment.")
        return openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=timeout)
    if provider_l == "qwen":
        api_key = os.environ.get("QWEN_API_KEY")
        if not api_key:
            raise ValueError("QWEN_API_KEY not found in environment.")
        return openai.OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=timeout)
    if provider_l == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment.")
        return openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=timeout)
    # v1.3.12: venice provider (Venice API, OpenAI-compatible).
    if provider_l == "venice":
        api_key = os.environ.get("VENICE_API_KEY")
        if not api_key:
            raise ValueError(
                "VENICE_API_KEY not found in environment. "
                "Venice requires a dedicated key; it does NOT fall back to OPENAI_API_KEY."
            )
        agent_cfg = _get_agent_config(config, agent_name)
        base_url = agent_cfg.get("api_base_url") or agent_cfg.get("base_url") or "https://api.venice.ai/api/v1"
        return openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    
    # Fallback for unknown or 'prov' providers (allows tests to mock the client)
    try:
        api_key = os.environ.get("OPENAI_API_KEY") or "sk-dummy-key-for-tests"
        return openai.OpenAI(api_key=api_key, timeout=timeout)
    except Exception:
        raise ValueError(f"Provider {provider} does not use OpenAI-compatible dispatch")


def _path_if_executable(path: Path) -> Path | None:
    try:
        if path.exists() and path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
    except Exception:
        return None
    return None


def _configured_cli_candidates(configured_path: str, config: dict[str, Any] | None) -> list[Path]:
    raw = str(configured_path or "").strip()
    if not raw:
        return []
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        return [expanded]

    bases = [
        Path.cwd(),
        _worqspace_root(config),
        _project_root(),
        _project_root().parent,
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        try:
            candidate = (base / expanded).resolve()
        except Exception:
            candidate = base / expanded
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates


def _find_codeseeq_binary(config: dict[str, Any] | None = None, agent_name: str | None = None) -> Path:
    runtime_config = load_runtime_config(config)
    agent_cfg = _get_agent_config(runtime_config, agent_name)
    checked: list[str] = []

    for key in ("codeseeq_path", "cli_path"):
        raw = str(agent_cfg.get(key) or "").strip()
        if not raw:
            continue
        for candidate in _configured_cli_candidates(raw, runtime_config):
            checked.append(f"agents.{agent_name or '<agent>'}.{key}={candidate}")
            resolved = _path_if_executable(candidate)
            if resolved is not None:
                return resolved

    env_bin = os.environ.get("QONQ_CODESEEQ_BIN", "").strip()
    if env_bin:
        for candidate in _configured_cli_candidates(env_bin, runtime_config):
            checked.append(f"QONQ_CODESEEQ_BIN={candidate}")
            resolved = _path_if_executable(candidate)
            if resolved is not None:
                return resolved

    path_bin = shutil.which("codeseeq")
    if path_bin:
        candidate = Path(path_bin)
        checked.append(f"PATH={candidate}")
        resolved = _path_if_executable(candidate)
        if resolved is not None:
            return resolved

    for candidate in (
        _project_root().parent / "codeseeq" / "codeseeq",
        Path("/usr/local/bin/codeseeq"),
    ):
        checked.append(str(candidate))
        resolved = _path_if_executable(candidate)
        if resolved is not None:
            return resolved

    raise RuntimeError(
        "provider: codeseeq requires CodeSeeq CLI to be executable from the QonQrete runtime. "
        "Set agents.<name>.codeseeq_path, agents.<name>.cli_path, QONQ_CODESEEQ_BIN, put codeseeq on PATH, "
        "or run from a repo layout with sibling ./codeseeq/codeseeq. Checked: "
        + "; ".join(checked)
    )


def _codeseeq_stderr_preview(text: str, limit: int = 2000) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "... [truncated]"


def _codeseeq_prompt_from_messages(
    messages: list[dict[str, Any]],
    *,
    output_tokens: int,
    agent_name: str | None,
) -> str:
    parts = [
        "# QonQrete Agent Request",
        "",
        "This is a QonQrete agent request routed through CodeSeeq.",
        "Return only the requested agent output. Do not add wrapper commentary, CLI diagnostics, or explanations about CodeSeeq.",
        f"Agent: {agent_name or 'unknown'}",
        f"Requested output token budget: {output_tokens}",
        "",
        "## Messages",
    ]

    for index, item in enumerate(messages, start=1):
        role = str(item.get("role") or "user").strip().lower() or "user"
        content = item.get("content", "")
        if not isinstance(content, str):
            try:
                content = json.dumps(content, sort_keys=True, ensure_ascii=False)
            except Exception:
                content = str(content)
        extras = {
            key: value
            for key, value in item.items()
            if key not in {"role", "content"} and value is not None
        }
        parts.extend([
            "",
            f"### Message {index}",
            f"ROLE: {role}",
        ])
        if extras:
            parts.append("METADATA:")
            parts.append(json.dumps(extras, sort_keys=True, ensure_ascii=False))
        parts.extend([
            "CONTENT:",
            content,
        ])

    parts.extend([
        "",
        "## Output",
        "Produce the final QonQrete agent output now.",
    ])
    return "\n".join(parts)


def _codeseeq_inline_max_chars() -> int:
    raw = os.environ.get("QONQ_CODESEEQ_INLINE_MAX_CHARS", "120000").strip()
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except ValueError:
        pass
    return 120000


def _codeseeq_temp_prompt_path(config: dict[str, Any], prompt: str) -> Path:
    root = _worqspace_root(config)
    temp_dir = _resolve_path_within_root(root, "audit/tmp/codeseeq")
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".md",
        prefix="codeseeq-prompt-",
        dir=temp_dir,
        delete=False,
    ) as handle:
        handle.write(prompt)
        handle.flush()
        path = Path(handle.name)
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return path


def _dispatch_codeseeq_cli(
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    output_tokens: int,
    timeout: int,
    tools: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    *,
    cache_envelope: dict[str, Any] | None = None,
) -> DispatchResult:
    if tools is not None:
        raise RuntimeError(
            "codeseeq provider does not support QonQrete-level tool_calls yet; "
            "use a non-tool path or implement tool translation."
        )

    runtime_config = load_runtime_config(config)
    command_path = Path(_find_codeseeq_binary(runtime_config, agent_name))
    cwd = _worqspace_root(runtime_config)
    if not cwd.exists():
        raise RuntimeError(f"codeseeq provider cwd does not exist: {cwd}")

    prompt = _codeseeq_prompt_from_messages(messages, output_tokens=output_tokens, agent_name=agent_name)
    file_mode = len(prompt) > _codeseeq_inline_max_chars()
    prompt_file: Path | None = None
    if file_mode:
        prompt_file = _codeseeq_temp_prompt_path(runtime_config, prompt)
        argv = [str(command_path), "-m", model, "-y", "run", "-f", str(prompt_file)]
    else:
        argv = [str(command_path), "-m", model, "-y", "run", prompt]

    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_preview = _codeseeq_stderr_preview(getattr(exc, "stderr", "") or "")
        stdout_preview = _codeseeq_stderr_preview(getattr(exc, "stdout", "") or "")
        raise TimeoutError(
            f"codeseeq CLI timeout after {timeout}s "
            f"(model={model}, cwd={cwd}, command_path={command_path}, "
            f"stdout_preview={stdout_preview!r}, stderr_preview={stderr_preview!r})"
        ) from exc

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    stderr_preview = _codeseeq_stderr_preview(stderr)
    stdout_preview = _codeseeq_stderr_preview(stdout)

    metadata = {
        "provider": "codeseeq",
        "model": model,
        "command_path": str(command_path),
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stderr_preview": stderr_preview,
        "streamed": False,
        "cli_provider": True,
        "prompt_file_used": bool(file_mode),
        "prompt_file": str(prompt_file) if prompt_file else None,
        "cache_backend": (cache_envelope or {}).get("backend") if isinstance(cache_envelope, dict) else None,
    }

    if completed.returncode != 0:
        raise RuntimeError(
            "codeseeq CLI dispatch failed "
            f"(exit_code={completed.returncode}, model={model}, cwd={cwd}, command_path={command_path}, "
            f"stderr_preview={stderr_preview!r}, stdout_preview={stdout_preview!r})"
        )

    return DispatchResult(
        text=stdout.strip(),
        response_truncated=False,
        provider_metadata=metadata,
    )


def _dispatch_openai_compatible(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
    tools: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    *,
    allow_tool_streaming: bool = False,
    cache_envelope: dict[str, Any] | None = None,
    telemetry_stream_hook=None,
    telemetry_stream_finalize=None,
) -> DispatchResult:
    provider_l = provider.lower()

    # v1.3.17: Venice model selection must be explicit at config/parameter
    # resolution time. Keep dispatch strict so hidden runtime fallbacks cannot
    # mask wiring drift.
    if provider_l == "venice" and not str(model or "").strip():
        raise ValueError(
            "Venice dispatch requires a non-empty model. "
            "Set agents.<name>.model explicitly (recommended: deepseek-v3.2)."
        )

    # v1.3.12: For mlx and llama-cpp, use direct HTTP requests to ensure true
    # model omission and true unauthenticated behavior when no key is present.
    if provider_l in {"mlx", "llama-cpp"}:
        return _dispatch_local_openai_compatible(
            provider_l,
            model,
            messages,
            output_tokens,
            timeout,
            tools,
            config,
            agent_name,
            stream_callback=stream_callback,
            allow_tool_streaming=allow_tool_streaming,
            telemetry_stream_hook=telemetry_stream_hook,
            telemetry_stream_finalize=telemetry_stream_finalize,
        )

    client = _openai_client_for_provider(provider, timeout, config=config, agent_name=agent_name, model=model)

    params = {
        "model": model,
        "messages": messages,
        "timeout": timeout,
    }
    if provider_l == "openai" and isinstance(cache_envelope, dict):
        prompt_cache_key = str(cache_envelope.get("prompt_cache_key") or "").strip()
        if prompt_cache_key:
            params["prompt_cache_key"] = prompt_cache_key
    
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"

    model_l = model.lower()
    # v1.3.9: OpenAI o1/o3/o5 models require max_completion_tokens instead of max_tokens
    if provider_l == "openai" and (
        model_l.startswith("o1") or 
        model_l.startswith("o3") or 
        model_l.startswith("gpt-5") or
        "o1-" in model_l or 
        "o3-" in model_l
    ):
        params["max_completion_tokens"] = output_tokens
    else:
        params["max_tokens"] = output_tokens

    # v1.3.12: venice_parameters pass-through.
    if provider_l == "venice":
        agent_cfg = _get_agent_config(config, agent_name)
        venice_params = agent_cfg.get("venice_parameters")
        if isinstance(venice_params, dict) and venice_params:
            params["extra_body"] = {"venice_parameters": dict(venice_params)}

    # v1.3.13+: Streaming path. For OpenAI-compatible providers we support
    # tool-call delta reassembly, so tools can stream safely when enabled.
    stream_cb, finalize_stream = _resolve_stream_callback(
        stream_callback,
        agent_name,
        tools,
        allow_tool_streaming=allow_tool_streaming,
        telemetry_callback=telemetry_stream_hook,
        telemetry_finalize=telemetry_stream_finalize,
    )

    if stream_cb is not None:
        params["stream"] = True
        # Ask for usage in the final chunk (OpenAI + most compatibles support this).
        params["stream_options"] = {"include_usage": True}
        try:
            stream = client.chat.completions.create(**params)
        except Exception:
            finalize_stream()
            raise

        # Some mocked/testing clients may return a normal response object even
        # when stream=True. Fall back gracefully instead of crashing on
        # non-iterable stream objects.
        if hasattr(stream, "choices"):
            finalize_stream()
            choice = stream.choices[0]
            tool_calls = getattr(choice.message, "tool_calls", None)
            text = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", None)
            usage_obj = getattr(stream, "usage", None)
            normalized_tool_calls = None
            if tool_calls:
                normalized_tool_calls = [
                    t.model_dump() if hasattr(t, "model_dump") else t
                    for t in tool_calls
                ]
            return DispatchResult(
                text=text.strip(),
                response_truncated=(finish_reason == "length"),
                provider_metadata={
                    "finish_reason": finish_reason,
                    "usage": usage_obj.model_dump() if (usage_obj is not None and hasattr(usage_obj, "model_dump")) else usage_obj,
                    "tool_calls": normalized_tool_calls,
                    "streamed": False,
                },
            )

        text_parts: list[str] = []
        finish_reason: str | None = None
        usage_obj = None
        tool_state: dict[int, dict[str, Any]] = {}
        try:
            for event in stream:
                # Some compatibles (e.g. Venice) emit heartbeat events with no choices.
                choices = getattr(event, "choices", None) or []
                if choices:
                    choice = choices[0]
                    delta = getattr(choice, "delta", None)
                    if delta is not None:
                        piece = getattr(delta, "content", None)
                        if piece:
                            text_parts.append(piece)
                            try:
                                stream_cb(piece)
                            except Exception:
                                pass
                        delta_tool_calls = getattr(delta, "tool_calls", None)
                        if delta_tool_calls:
                            _accumulate_stream_tool_calls(tool_state, delta_tool_calls)
                    fr = getattr(choice, "finish_reason", None)
                    if fr:
                        finish_reason = fr
                ev_usage = getattr(event, "usage", None)
                if ev_usage is not None:
                    usage_obj = ev_usage
        finally:
            finalize_stream()

        text = "".join(text_parts)
        streamed_tool_calls = _finalize_stream_tool_calls(tool_state)
        return DispatchResult(
            text=text.strip(),
            response_truncated=(finish_reason == "length"),
            provider_metadata={
                "finish_reason": finish_reason,
                "usage": usage_obj.model_dump() if (usage_obj is not None and hasattr(usage_obj, "model_dump")) else usage_obj,
                "tool_calls": streamed_tool_calls if streamed_tool_calls else None,
                "streamed": True,
            },
        )

    # Non-streaming (legacy) path — preserved byte-for-byte for tools/tool-calls.
    response = client.chat.completions.create(**params)
    choice = response.choices[0]
    
    tool_calls = getattr(choice.message, "tool_calls", None)
    text = choice.message.content or ""
    
    finish_reason = getattr(choice, "finish_reason", None)
    return DispatchResult(
        text=text.strip(),
        response_truncated=(finish_reason == "length"),
        provider_metadata={
            "finish_reason": finish_reason,
            "usage": getattr(response, "usage", None).model_dump() if getattr(response, "usage", None) else None,
            "tool_calls": [t.model_dump() for t in tool_calls] if tool_calls else None,
        },
    )


def _dispatch_local_openai_compatible(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
    tools: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    *,
    allow_tool_streaming: bool = False,
    telemetry_stream_hook=None,
    telemetry_stream_finalize=None,
) -> DispatchResult:
    """v1.3.12: Direct HTTP dispatch for mlx/llama-cpp to preserve model omission and no-auth.

    v1.3.13: Added SSE streaming support. When streaming is active we read the
    response body line-by-line and parse `data: {...}` events in the OpenAI
    SSE format, forwarding content deltas to the stream callback.
    """
    import urllib.request
    import urllib.error
    
    agent_cfg = _get_agent_config(config, agent_name)
    base_url = agent_cfg.get("api_base_url") or agent_cfg.get("base_url")
    if not base_url:
        raise ValueError(
            f"{provider} provider requires 'api_base_url' in config.yaml under "
            f"agents.{agent_name or '<agent>'} (e.g. http://localhost:8080/v1)."
        )
    
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/chat/completions"):
        url = f"{base_url}/chat/completions"
    else:
        url = base_url

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("MLX_API_KEY") if provider == "mlx" else os.environ.get("LLAMA_CPP_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "messages": messages,
        "max_tokens": output_tokens,
    }
    if model:
        payload["model"] = model
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # v1.3.13+: local OpenAI-compatible runtimes can stream tool-call deltas.
    stream_cb, finalize_stream = _resolve_stream_callback(
        stream_callback,
        agent_name,
        tools,
        allow_tool_streaming=allow_tool_streaming,
        telemetry_callback=telemetry_stream_hook,
        telemetry_finalize=telemetry_stream_finalize,
    )

    if stream_cb is not None:
        payload["stream"] = True
        headers["Accept"] = "text/event-stream"

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    if stream_cb is None:
        # Legacy blocking path — preserved exactly.
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_msg = exc.read().decode("utf-8")
            raise RuntimeError(f"Local AI dispatch failed ({provider} @ {url}) with status {exc.code}: {err_msg}")
        except Exception as exc:
            raise RuntimeError(f"Local AI dispatch failed ({provider} @ {url}): {exc}")

        choice = res_data.get("choices", [{}])[0]
        message = choice.get("message", {})
        text = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        finish_reason = choice.get("finish_reason")

        return DispatchResult(
            text=text.strip(),
            response_truncated=(finish_reason == "length"),
            provider_metadata={
                "finish_reason": finish_reason,
                "usage": res_data.get("usage"),
                "tool_calls": tool_calls,
            },
        )

    # v1.3.13: SSE streaming path.
    text_parts: list[str] = []
    finish_reason: str | None = None
    usage_obj = None
    tool_state: dict[int, dict[str, Any]] = {}
    try:
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            err_msg = exc.read().decode("utf-8")
            raise RuntimeError(f"Local AI dispatch failed ({provider} @ {url}) with status {exc.code}: {err_msg}")
        except Exception as exc:
            raise RuntimeError(f"Local AI dispatch failed ({provider} @ {url}): {exc}")

        try:
            content_type = ""
            try:
                content_type = str(resp.headers.get("Content-Type", "")).lower()
            except Exception:
                content_type = ""

            if "text/event-stream" not in content_type:
                # Runtime ignored stream=true and returned one-shot JSON.
                body = resp.read()
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception:
                    payload = {}
                choice = (payload.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = (message.get("content") or "").strip()
                tool_calls = message.get("tool_calls")
                finish_reason = choice.get("finish_reason")
                return DispatchResult(
                    text=text,
                    response_truncated=(finish_reason == "length"),
                    provider_metadata={
                        "finish_reason": finish_reason,
                        "usage": payload.get("usage"),
                        "tool_calls": tool_calls,
                        "streamed": False,
                    },
                )

            for raw_line in resp:
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                except Exception:
                    continue
                if not line or not line.startswith("data:"):
                    continue
                payload_txt = line[5:].strip()
                if payload_txt == "[DONE]":
                    break
                try:
                    event = json.loads(payload_txt)
                except Exception:
                    continue
                choices = event.get("choices") or []
                if choices:
                    choice0 = choices[0]
                    delta = choice0.get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        text_parts.append(piece)
                        try:
                            stream_cb(piece)
                        except Exception:
                            pass
                    
                    # v1.3.13: Support tool call streaming visibility
                    delta_tool_calls = delta.get("tool_calls")
                    if delta_tool_calls:
                        _accumulate_stream_tool_calls(tool_state, delta_tool_calls)
                        # Emit tool argument fragments to stream_cb so user sees progress
                        for dtc in delta_tool_calls:
                            dfn = dtc.get("function")
                            if dfn and dfn.get("arguments"):
                                try:
                                    stream_cb(dfn.get("arguments"))
                                except Exception:
                                    pass
                    
                    fr = choice0.get("finish_reason")
                    if fr:
                        finish_reason = fr
                if event.get("usage"):
                    usage_obj = event.get("usage")
        finally:
            try:
                resp.close()
            except Exception:
                pass
    finally:
        finalize_stream()

    text = "".join(text_parts)
    streamed_tool_calls = _finalize_stream_tool_calls(tool_state)
    return DispatchResult(
        text=text.strip(),
        response_truncated=(finish_reason == "length"),
        provider_metadata={
            "finish_reason": finish_reason,
            "usage": usage_obj,
            "tool_calls": streamed_tool_calls if streamed_tool_calls else None,
            "streamed": True,
        },
    )


def _dispatch_anthropic(
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
    tools: list[dict[str, Any]] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    *,
    allow_tool_streaming: bool = False,
    cache_envelope: dict[str, Any] | None = None,
    telemetry_stream_hook=None,
    telemetry_stream_finalize=None,
) -> DispatchResult:
    anthropic = _import_anthropic()
    try:
        client = anthropic.Anthropic(timeout=timeout)
        system_parts: list[str] = []
        anth_messages = []
        for item in messages:
            if item["role"] == "system":
                system_parts.append(item["content"])
            else:
                anth_messages.append({"role": item["role"], "content": item["content"]})

        system_payload: str | list[dict[str, Any]] | None = None
        system_joined = "\n\n".join([part for part in system_parts if part]).strip()
        stable_prefix = ""
        cache_control_cfg: dict[str, Any] = {}
        if isinstance(cache_envelope, dict):
            stable_prefix = str(cache_envelope.get("stable_prefix") or "").strip()
            cache_control_cfg = cache_envelope.get("anthropic_cache_control") or {}
        if cache_control_cfg.get("enabled") and stable_prefix:
            cache_control: dict[str, Any] = {"type": "ephemeral"}
            ttl_minutes = int(cache_control_cfg.get("ttl_minutes") or 0)
            if ttl_minutes == 60:
                cache_control["ttl"] = "1h"
            system_blocks: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": stable_prefix,
                    "cache_control": cache_control,
                }
            ]
            if system_joined:
                system_blocks.append({"type": "text", "text": system_joined})
            system_payload = system_blocks
        elif system_joined:
            system_payload = system_joined

        params = {
            "model": model,
            "max_tokens": output_tokens,
            "messages": anth_messages,
        }
        if system_payload is not None:
            params["system"] = system_payload
        if tools:
            params["tools"] = tools

        # v1.3.13: Streaming path (tool_use aware). We still only stream the
        # text deltas to the callback, and accumulate tool_use blocks for the
        # final DispatchResult so tool-calling semantics are preserved.
        stream_cb, finalize_stream = _resolve_stream_callback(
            stream_callback,
            agent_name,
            tools=tools,
            allow_tool_streaming=allow_tool_streaming,
            telemetry_callback=telemetry_stream_hook,
            telemetry_finalize=telemetry_stream_finalize,
        )

        if stream_cb is not None:
            text_parts: list[str] = []
            tool_calls_map: dict[str, dict] = {}
            stop_reason = None
            input_tokens = None
            output_tokens_used = None
            last_usage_obj = None
            try:
                with client.messages.stream(**params) as stream:
                    for event in stream:
                        etype = getattr(event, "type", "")
                        if etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta is None:
                                continue
                            piece = getattr(delta, "text", None)
                            if piece:
                                text_parts.append(piece)
                                try:
                                    stream_cb(piece)
                                except Exception:
                                    pass
                            
                            # v1.3.13: Anthropic tool use streaming
                            partial_json = getattr(delta, "partial_json", None)
                            if partial_json:
                                if event.index in tool_calls_map:
                                    tool_calls_map[event.index]["function"]["arguments"] += partial_json
                                try:
                                    stream_cb(partial_json)
                                except Exception:
                                    pass
                        elif etype == "content_block_start":
                            block = getattr(event, "content_block", None)
                            if block and getattr(block, "type", "") == "tool_use":
                                tool_calls_map[event.index] = {
                                    "id": block.id,
                                    "type": "function",
                                    "function": {"name": block.name, "arguments": ""},
                                }
                        elif etype == "message_delta":
                            delta = getattr(event, "delta", None)
                            sr = getattr(delta, "stop_reason", None) if delta is not None else None
                            if sr:
                                stop_reason = sr
                            usage = getattr(event, "usage", None)
                            if usage is not None:
                                last_usage_obj = usage
                                output_tokens_used = getattr(usage, "output_tokens", output_tokens_used)
                        elif etype == "message_start":
                            msg = getattr(event, "message", None)
                            usage = getattr(msg, "usage", None) if msg is not None else None
                            if usage is not None:
                                last_usage_obj = usage
                                input_tokens = getattr(usage, "input_tokens", input_tokens)
                                output_tokens_used = getattr(usage, "output_tokens", output_tokens_used)
            finally:
                finalize_stream()

            # Finalize Anthropic tool calls
            final_tool_calls = []
            if tool_calls_map:
                for tid, call in tool_calls_map.items():
                    final_tool_calls.append(call)

            text = "".join(text_parts)
            return DispatchResult(
                text=text.strip(),
                response_truncated=(stop_reason == "max_tokens"),
                provider_metadata={
                    "stop_reason": stop_reason,
                    "usage": (
                        _anthropic_usage_to_dict(last_usage_obj)
                        if last_usage_obj is not None
                        else {"input_tokens": input_tokens, "output_tokens": output_tokens_used}
                    ),
                    "tool_calls": final_tool_calls if final_tool_calls else None,
                    "streamed": True,
                },
            )

        # Legacy blocking path — preserved for tools and for streaming-disabled.
        response = client.messages.create(**params)
        
        text_parts = []
        tool_calls = []
        for block in response.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", "") == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input)
                    }
                })

        text = "".join(text_parts)
        stop_reason = getattr(response, "stop_reason", None)
        usage = _anthropic_usage_to_dict(getattr(response, "usage", None))
        return DispatchResult(
            text=text.strip(),
            response_truncated=(stop_reason == "max_tokens"),
            provider_metadata={
                "stop_reason": stop_reason, 
                "usage": usage,
                "tool_calls": tool_calls if tool_calls else None
            },
        )
    except anthropic.APITimeoutError as exc:
        raise TimeoutError(f"anthropic API timeout after {timeout}s") from exc


def _dispatch_gemini(
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
    tools: list[dict[str, Any]] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    *,
    allow_tool_streaming: bool = False,
    telemetry_stream_hook=None,
    telemetry_stream_finalize=None,
    cache_envelope: dict[str, Any] | None = None,
) -> DispatchResult:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment.")
    genai = _import_genai()
    genai.configure(api_key=api_key)
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    history = []
    user_messages = [m for m in messages if m["role"] != "system"]
    for item in user_messages[:-1]:
        role = "model" if item["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [item["content"]]})
    
    gemini_tools = None
    if tools:
        gemini_tools = []
        for t in tools:
            if t.get("type") == "function":
                gemini_tools.append(t["function"])

    # Qontrabender provider-aware cache. Safe fallback only: this runtime does
    # not wire Gemini CachedContent into the SDK call, so explicit cache is not
    # claimed or faked here.
    if isinstance(cache_envelope, dict) and cache_envelope.get("backend") == "gemini_explicit":
        if agent_name in ("construqtor",):
            import sys as _sys
            _sys.stderr.write(
                "[Qontrabender] Gemini explicit cache requested but no real SDK-backed "
                "CachedContent dispatch is implemented; falling back to stable_prefix_auto.\n"
            )
        cache_envelope = {"backend": "stable_prefix_auto", "stable_prefix": cache_envelope.get("stable_prefix", "")}

    model_client = genai.GenerativeModel(
        model_name=model,
        system_instruction="\n\n".join(system_parts) if system_parts else None,
        generation_config={"max_output_tokens": output_tokens},
        tools=gemini_tools,
    )

    # v1.3.13: Streaming path. Gemini streams via stream=True which yields
    # response chunks; each chunk's .text is a delta. Tools path stays
    # blocking because function_call reassembly happens on full response.
    stream_cb, finalize_stream = _resolve_stream_callback(
        stream_callback,
        agent_name,
        tools,
        allow_tool_streaming=allow_tool_streaming,
        telemetry_callback=telemetry_stream_hook,
        telemetry_finalize=telemetry_stream_finalize,
    )

    if stream_cb is not None and not tools:
        text_parts: list[str] = []
        finish_reason = None
        try:
            if user_messages:
                chat = model_client.start_chat(history=history)
                stream = chat.send_message(
                    user_messages[-1]["content"],
                    stream=True,
                    request_options={"timeout": timeout},
                )
            else:
                stream = model_client.generate_content(
                    "",
                    stream=True,
                    request_options={"timeout": timeout},
                )
            try:
                for chunk in stream:
                    piece = None
                    try:
                        piece = chunk.text
                    except Exception:
                        # Some chunks carry only metadata, no text.
                        piece = None
                    if piece:
                        text_parts.append(piece)
                        try:
                            stream_cb(piece)
                        except Exception:
                            pass
                    try:
                        candidates = getattr(chunk, "candidates", None) or []
                        if candidates:
                            fr = getattr(candidates[0], "finish_reason", None)
                            if fr is not None:
                                finish_reason = fr
                    except Exception:
                        pass
            finally:
                try:
                    stream.resolve()
                except Exception:
                    pass
        finally:
            finalize_stream()

        text = "".join(text_parts)
        truncated = str(finish_reason).endswith("MAX_TOKENS") if finish_reason is not None else False
        return DispatchResult(
            text=text.strip(),
            response_truncated=truncated,
            provider_metadata={
                "finish_reason": str(finish_reason) if finish_reason is not None else None,
                "tool_calls": None,
                "streamed": True,
            },
        )

    # Legacy blocking path — preserved for tools / streaming-disabled.
    if user_messages:
        chat = model_client.start_chat(history=history)
        response = chat.send_message(user_messages[-1]["content"], request_options={"timeout": timeout})
    else:
        response = model_client.generate_content("", request_options={"timeout": timeout})
    
    tool_calls = []
    text = ""
    try:
        for part in response.candidates[0].content.parts:
            if part.text:
                text += part.text
            if part.function_call:
                tool_calls.append({
                    "id": f"call_{_sha256_text(part.function_call.name)[:8]}",
                    "type": "function",
                    "function": {
                        "name": part.function_call.name,
                        "arguments": json.dumps(dict(part.function_call.args))
                    }
                })
    except Exception:
        pass

    truncated = False
    try:
        finish_reason = response.candidates[0].finish_reason
        truncated = str(finish_reason).endswith("MAX_TOKENS")
    except Exception:
        finish_reason = None
    return DispatchResult(
        text=text.strip(),
        response_truncated=truncated,
        provider_metadata={
            "finish_reason": str(finish_reason) if finish_reason is not None else None,
            "tool_calls": tool_calls if tool_calls else None
        },
    )


def run_ai_messages(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    allow_tool_streaming: bool = False,
    cache_envelope: dict[str, Any] | None = None,
    telemetry_stream_hook=None,
    telemetry_stream_finalize=None,
) -> DispatchResult:
    resolved_timeout = timeout or _default_api_timeout()
    provider_l = provider.lower()
    if provider_l == "codeseeq":
        return _dispatch_codeseeq_cli(
            provider_l,
            model,
            messages,
            output_tokens,
            resolved_timeout,
            tools=tools,
            config=config,
            agent_name=agent_name,
            stream_callback=stream_callback,
            cache_envelope=cache_envelope,
        )
    # v1.3.12: mlx, llama-cpp, and venice added to OpenAI-compatible dispatch.
    if provider_l in {"openai", "deepseek", "qwen", "openrouter", "mlx", "llama-cpp", "venice"}:
        try:
            return _dispatch_openai_compatible(
                provider_l,
                model,
                messages,
                output_tokens,
                resolved_timeout,
                tools=tools,
                config=config,
                agent_name=agent_name,
                stream_callback=stream_callback,
                allow_tool_streaming=allow_tool_streaming,
                cache_envelope=cache_envelope,
                telemetry_stream_hook=telemetry_stream_hook,
                telemetry_stream_finalize=telemetry_stream_finalize,
            )
        except Exception as exc:
            # Preserve the original dispatch failure even when the optional
            # openai package is unavailable in this environment. Only remap
            # provider timeout failures to TimeoutError.
            if exc.__class__.__name__ == "APITimeoutError":
                raise TimeoutError(f"{provider} API timeout after {resolved_timeout}s") from exc
            raise
    if provider_l == "anthropic":
        return _dispatch_anthropic(
            model,
            messages,
            output_tokens,
            resolved_timeout,
            tools=tools,
            agent_name=agent_name,
            stream_callback=stream_callback,
            allow_tool_streaming=allow_tool_streaming,
            cache_envelope=cache_envelope,
            telemetry_stream_hook=telemetry_stream_hook,
            telemetry_stream_finalize=telemetry_stream_finalize,
        )
    if provider_l == "gemini":
        return _dispatch_gemini(
            model,
            messages,
            output_tokens,
            resolved_timeout,
            tools=tools,
            agent_name=agent_name,
            stream_callback=stream_callback,
            allow_tool_streaming=allow_tool_streaming,
            cache_envelope=cache_envelope,
            telemetry_stream_hook=telemetry_stream_hook,
            telemetry_stream_finalize=telemetry_stream_finalize,
        )
    if provider_l == "dry-run":
        return DispatchResult(
            text="[DRY RUN] request planned without external API call.",
            response_truncated=False,
            provider_metadata={"mode": "dry-run"},
        )
    
    # v1.4.0: Fallback to OpenAI compatible for all other providers (including 'prov' in tests).
    return _dispatch_openai_compatible(
        provider,
        model,
        messages,
        output_tokens,
        resolved_timeout,
        tools=tools,
        config=config,
        agent_name=agent_name,
        stream_callback=stream_callback,
        allow_tool_streaming=allow_tool_streaming,
        cache_envelope=cache_envelope,
        telemetry_stream_hook=telemetry_stream_hook,
        telemetry_stream_finalize=telemetry_stream_finalize,
    )


def _dispatch_with_chunking(
    provider: str,
    model: str,
    inline_prompt: str,
    chunks: list[ChunkRecord],
    output_tokens: int,
    timeout: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    stream_callback=None,
    *,
    allow_tool_streaming: bool = False,
    cache_envelope: dict[str, Any] | None = None,
    telemetry_stream_hook=None,
    telemetry_stream_finalize=None,
) -> DispatchResult:
    messages = [{"role": "system", "content": _system_message()}]
    acks: list[str] = []
    ack_round_trips: list[float] = []
    
    # v1.3.13: Use a slightly higher ACK budget (512) for models that might 
    # ignore no-think instructions and emit a few tokens of reasoning.
    ack_output_tokens = int(os.environ.get("QONQ_ACK_TOKEN_BUDGET", "512"))

    for preload in _build_preload_messages(chunks):
        expected = DEFAULT_ACK_TEMPLATE.format(
            index=chunks[len(acks)].chunk_index,
            total=chunks[len(acks)].chunk_total,
            hash=chunks[len(acks)].chunk_hash,
        )
        
        # Dispatch with a single retry if the ACK is malformed
        ack_received = False
        last_norm = ""
        last_raw = ""
        
        for attempt in range(1, 3):
            preload_messages = messages + [preload]
            if attempt > 1:
                # v1.3.13: If retrying, add a firm reminder
                preload_messages.append({
                    "role": "user", 
                    "content": f"ERROR: Your previous response was malformed. YOU MUST REPLY WITH ONLY THE EXACT ACK LINE: {expected}"
                })
            
            # v1.3.13: Preload ACK calls are FORCE-blocking (stream_callback=False).
            ack_started_at = time.time()
            ack_result = run_ai_messages(
                provider,
                model,
                preload_messages,
                output_tokens=ack_output_tokens,
                timeout=timeout,
                config=config,
                agent_name=agent_name,
                stream_callback=False,
                allow_tool_streaming=False,
                cache_envelope=cache_envelope,
            )
            ack_round_trips.append(max(0.0, time.time() - ack_started_at))
            
            last_raw = ack_result.text
            last_norm = _normalize_ack_response(last_raw)
            
            if last_norm == expected:
                ack_received = True
                break
            else:
                print(f"     [Chunk] ⚠️ Malformed ACK (attempt {attempt}): expected '{expected}', got '{last_norm or last_raw[:50]}...'", flush=True)

        if not ack_received:
            raise RuntimeError(
                f"Chunk preload ACK mismatch after {attempt} attempts. Expected `{expected}`. "
                f"Got (normalized) `{last_norm}`. Raw response preview: `{last_raw[:100]}...`"
            )
            
        acks.append(last_norm)
        messages.append(preload)
        messages.append({"role": "assistant", "content": last_norm})

    final_user = {"role": "user", "content": _build_final_user_message(inline_prompt, chunks)}
    # The final call is the expensive one and is where streaming gives the
    # biggest perceived-latency win, so we DO pass through stream_callback.
    final_result = run_ai_messages(
        provider,
        model,
        messages + [final_user],
        output_tokens=output_tokens,
        timeout=timeout,
        tools=tools,
        config=config,
        agent_name=agent_name,
        stream_callback=stream_callback,
        allow_tool_streaming=allow_tool_streaming,
        cache_envelope=cache_envelope,
        telemetry_stream_hook=telemetry_stream_hook,
        telemetry_stream_finalize=telemetry_stream_finalize,
    )
    final_result.preload_acks = acks
    provider_meta = dict(final_result.provider_metadata or {})
    provider_meta["chunk_preload_round_trip_count"] = len(ack_round_trips)
    provider_meta["chunk_preload_round_trips_sec"] = ack_round_trips
    provider_meta["chunk_preload_total_wait_sec"] = float(sum(ack_round_trips))
    final_result.provider_metadata = provider_meta
    return final_result


def _write_audit_record(config: dict[str, Any], agent_name: str | None, payload: dict[str, Any]) -> Path:
    root = _worqspace_root(config)
    configured_dir = config.get("ai_budgeting", {}).get("audit_dir", "audit/ai_payloads")
    if (
        not os.environ.get("QONQ_WORKSPACE", "").strip()
        and (os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)
        and configured_dir == "audit/ai_payloads"
    ):
        root = Path(tempfile.gettempdir()) / "qonqrete-pytest-audit" / _sanitize_name(_project_root().name)
        configured_dir = "audit/ai_payloads"
    audit_dir = _resolve_path_within_root(root, configured_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    label = _sanitize_name(payload.get("audit_label") or agent_name or "ai-call")
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{label}-{payload['request_hash'][:12]}.json"
    audit_path = audit_dir / filename
    audit_content = json.dumps(payload, indent=2) + "\n"
    if safe_write_file is not None:
        safe_write_file(audit_path, audit_content, jail=root)
    else:
        audit_path.write_text(audit_content, encoding="utf-8")
    return audit_path


def _prepare_request_plan(
    provider: str,
    model: str,
    prompt: str,
    context_files: list[str],
    prompt_sections: list[dict[str, Any]] | None,
    config: dict[str, Any],
    budget_config: dict[str, Any],
    agent_name: str | None,
    output_tokens: int | None,
    task_type: str | None,
    allow_chunking: bool | None,
    include_previous_log: bool | None = None,
) -> dict[str, Any]:
    capability_provider = provider if provider.lower() != "dry-run" else config.get("ai_budgeting", {}).get("dry_run_provider", "deepseek")
    capability_resolution = resolve_model_capability_details(capability_provider, model, config=config, agent_name=agent_name)
    caps = capability_resolution.effective
    budgets = _token_budget(config, caps, agent_name, output_tokens, task_type)
    sections = _normalize_sections(
        prompt,
        context_files,
        prompt_sections,
        config,
        caps,
        budget_config,
        include_previous_log=include_previous_log,
    )
    sections, dropped_sections, summarized_sections = _optimize_sections(sections, budgets["safe_input_tokens"], caps.chars_per_token)
    supports_chunking = caps.supports_multi_message_history and caps.supports_chunk_preload and (allow_chunking is not False)
    sections, chunks, chunk_meta = _plan_chunks(sections, budgets["safe_input_tokens"], caps.chars_per_token, config, supports_chunking)
    inline_prompt = _build_inline_prompt(sections)
    inline_tokens = _estimate_tokens(inline_prompt, caps.chars_per_token)
    if inline_tokens > budgets["safe_input_tokens"]:
        raise RuntimeError("Inline prompt exceeds safe input budget after optimization and chunk planning.")

    active_source_files = sorted({path for section in sections for path in section.source_files if not section.omitted})
    request_hash = _sha256_text(inline_prompt + "".join(chunk.chunk_hash for chunk in chunks))
    return {
        "capabilities": caps,
        "base_capabilities": capability_resolution.base,
        "applied_capability_overrides": capability_resolution.applied_overrides,
        "capability_warnings": capability_resolution.warnings,
        "capability_provider": capability_provider,
        "budgets": budgets,
        "sections": sections,
        "dropped_sections": dropped_sections,
        "summarized_sections": summarized_sections,
        "chunks": chunks,
        "chunk_meta": chunk_meta,
        "inline_prompt": inline_prompt,
        "inline_tokens": inline_tokens,
        "active_source_files": active_source_files,
        "request_hash": request_hash,
    }


def run_ai_completion(
    provider: str,
    model: str,
    prompt: str,
    context_files: list[str] | None = None,
    max_prompt_chars: int | None = None,
    max_context_files: int | None = None,
    max_chars_per_file: int | None = None,
    timeout: int | None = None,
    prompt_sections: list[dict[str, Any]] | None = None,
    agent_name: str | None = None,
    config: dict[str, Any] | None = None,
    output_tokens: int | None = None,
    task_type: str | None = None,
    allow_chunking: bool | None = None,
    allow_tool_streaming: bool = False,
    audit_label: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    include_previous_log: bool | None = None,
    stream_callback=None,
) -> str | dict[str, Any]:
    context_files = context_files or []
    runtime_config = load_runtime_config(config)
    budget_config = {
        "max_prompt_chars": max_prompt_chars or DEFAULT_MAX_PROMPT_CHARS,
        "max_context_files": max_context_files or DEFAULT_MAX_CONTEXT_FILES,
        "max_chars_per_file": max_chars_per_file or DEFAULT_MAX_CHARS_PER_FILE,
    }

    prompt_char_count = _prompt_char_count(prompt, prompt_sections)
    if prompt_char_count > budget_config["max_prompt_chars"]:
        raise RuntimeError(
            f"Prompt content exceeds max_prompt_chars {budget_config['max_prompt_chars']} "
            f"(got {prompt_char_count})."
        )

    plan = _prepare_request_plan(
        provider=provider,
        model=model,
        prompt=prompt,
        context_files=context_files,
        prompt_sections=prompt_sections,
        config=runtime_config,
        budget_config=budget_config,
        agent_name=agent_name,
        output_tokens=output_tokens,
        task_type=task_type,
        allow_chunking=allow_chunking,
        include_previous_log=include_previous_log,
    )
    qache_dir_path: str | None = None
    candidates = []
    if runtime_config.get("qage_root"):
        candidates.append(Path(str(runtime_config["qage_root"])) / "qache.d")
    if runtime_config.get("worqspace_root"):
        candidates.append(Path(str(runtime_config["worqspace_root"])) / "qache.d")
    candidates.append(_worqspace_root(runtime_config) / "qache.d")
    if os.environ.get("QONQ_WORKSPACE"):
        candidates.append(Path(os.environ["QONQ_WORKSPACE"]) / "qache.d")

    for candidate in candidates:
        if candidate.exists():
            qache_dir_path = str(candidate)
            break

    cache_envelope = _build_cache_envelope(
        provider=provider,
        config=runtime_config,
        agent_name=agent_name,
        sections=plan["sections"],
        qache_dir=qache_dir_path,
    )

    dispatch_result: DispatchResult | None = None
    error_text: str | None = None
    resolved_timeout = timeout or _default_api_timeout()

    audit_payload = {
        "schema_version": "ai-call-metadata.v1",
        "created_at": _utc_now(),
        "provider": provider,
        "model": model,
        "resolved_provider": provider,
        "resolved_model": model,
        "agent_name": agent_name,
        "audit_label": audit_label or agent_name or "ai_call",
        "capabilities": plan["capabilities"].to_dict(),
        "base_capabilities": plan["base_capabilities"].to_dict(),
        "applied_capability_overrides": plan["applied_capability_overrides"],
        "effective_capabilities": plan["capabilities"].to_dict(),
        "capability_warnings": plan["capability_warnings"],
        "input_token_estimate": plan["inline_tokens"] + sum(chunk.estimated_tokens for chunk in plan["chunks"]),
        "inline_input_token_estimate": plan["inline_tokens"],
        "output_token_budget": plan["budgets"]["safe_output_tokens"],
        "safe_input_budget": plan["budgets"]["safe_input_tokens"],
        "safe_output_budget": plan["budgets"]["safe_output_tokens"],
        "chunking_used": bool(plan["chunks"]),
        "number_of_chunks": len(plan["chunks"]),
        "chunk_manifest": [
            {
                "chunk_index": chunk.chunk_index,
                "chunk_total": chunk.chunk_total,
                "section_label": chunk.section_label,
                "section_hash": chunk.section_hash,
                "chunk_hash": chunk.chunk_hash,
                "estimated_tokens": chunk.estimated_tokens,
                "char_count": len(chunk.text),
            }
            for chunk in plan["chunks"]
        ],
        "sections": _section_breakdown(plan["sections"]),
        "dropped_optional_sections": plan["dropped_sections"],
        "summarized_sections": plan["summarized_sections"],
        "source_files_included": plan["active_source_files"],
        "fallback_char_emergency_protection_used": False,
        "response_truncation_detected": False,
        "request_hash": plan["request_hash"],
        "tools_offered": tools is not None,
        "allow_tool_streaming_requested": bool(allow_tool_streaming),
        "include_previous_log_requested": include_previous_log,
        "cache_envelope": {
            "backend": cache_envelope.get("backend"),
            "stable_prefix_chars": len(str(cache_envelope.get("stable_prefix") or "")),
            "prompt_cache_key_used": bool(cache_envelope.get("prompt_cache_key")),
            "anthropic_cache_control": bool((cache_envelope.get("anthropic_cache_control") or {}).get("enabled")),
        },
    }
    progress_tag = agent_name or "ai"

    if len(plan["inline_prompt"]) > STRING_HARD_LIMIT:
        audit_payload["fallback_char_emergency_protection_used"] = True
        error_text = f"Inline prompt still exceeds hard string limit {STRING_HARD_LIMIT} chars."
    else:
        try:
            try:
                sys.stderr.write(
                    f"[AI:{progress_tag}] Request sent "
                    f"(provider={provider}, model={model}, chunks={len(plan['chunks'])}, "
                    f"tools={'yes' if tools else 'no'})\n"
                )
                sys.stderr.flush()
            except Exception:
                pass

            time_started = time.time()
            audit_payload["request_sent_timestamp"] = time_started
            first_token_time = [None]
            first_visible_relay_time = [None]

            def telemetry_stream_hook(delta):
                if not delta:
                    return
                now = time.time()
                if first_token_time[0] is None:
                    first_token_time[0] = now
                    audit_payload["first_token_timestamp"] = now
                    audit_payload["time_to_first_token_sec"] = now - time_started
                if first_visible_relay_time[0] is None:
                    first_visible_relay_time[0] = now
                    audit_payload["first_visible_relay_timestamp"] = now
                    audit_payload["time_to_first_visible_relay_sec"] = now - time_started

            if provider.lower() == "dry-run":
                dispatch_result = DispatchResult(
                    text="[DRY RUN] request planned without external API call.",
                    response_truncated=False,
                    provider_metadata={"mode": "dry-run"},
                )
            elif plan["chunks"]:
                dispatch_result = _dispatch_with_chunking(
                    provider=provider,
                    model=model,
                    inline_prompt=plan["inline_prompt"],
                    chunks=plan["chunks"],
                    output_tokens=plan["budgets"]["safe_output_tokens"],
                    timeout=resolved_timeout,
                    tools=tools,
                    config=runtime_config,
                    agent_name=agent_name,
                    stream_callback=stream_callback,
                    allow_tool_streaming=allow_tool_streaming,
                    cache_envelope=cache_envelope,
                    telemetry_stream_hook=telemetry_stream_hook if stream_callback is not False else None,
                )
            else:
                user_prompt = plan["inline_prompt"]
                if (
                    str(provider or "").strip().lower() == "anthropic"
                    and str(cache_envelope.get("backend") or "").strip() == "anthropic_cache_control"
                ):
                    stable_prefix = str(cache_envelope.get("stable_prefix") or "")
                    if stable_prefix and user_prompt.startswith(stable_prefix):
                        user_prompt = user_prompt[len(stable_prefix):].lstrip()
                        if not user_prompt:
                            user_prompt = "Continue with the task using the cached stable context and produce the requested output."
                messages = [
                    {"role": "system", "content": _system_message()},
                    {"role": "user", "content": user_prompt},
                ]
                dispatch_result = run_ai_messages(
                    provider=provider,
                    model=model,
                    messages=messages,
                    output_tokens=plan["budgets"]["safe_output_tokens"],
                    timeout=resolved_timeout,
                    tools=tools,
                    config=runtime_config,
                    agent_name=agent_name,
                    stream_callback=stream_callback,
                    allow_tool_streaming=allow_tool_streaming,
                    cache_envelope=cache_envelope,
                    telemetry_stream_hook=telemetry_stream_hook if stream_callback is not False else None,
                )
            if dispatch_result is not None:
                time_finished = time.time()
                audit_payload["response_complete_timestamp"] = time_finished
                audit_payload["total_provider_wait_sec"] = time_finished - time_started
                provider_meta = dispatch_result.provider_metadata or {}
                tool_calls = provider_meta.get("tool_calls") if isinstance(provider_meta, dict) else None
                if isinstance(provider_meta, dict):
                    usage_payload = provider_meta.get("usage")
                    if isinstance(usage_payload, dict):
                        audit_payload["provider_cache_token_metadata"] = {
                            key: value
                            for key, value in usage_payload.items()
                            if "cache" in str(key).lower() or "cached" in str(key).lower()
                        }
                if isinstance(provider_meta, dict):
                    preload_count = int(provider_meta.get("chunk_preload_round_trip_count", 0) or 0)
                    preload_total_wait = float(provider_meta.get("chunk_preload_total_wait_sec", 0.0) or 0.0)
                else:
                    preload_count = 0
                    preload_total_wait = 0.0
                audit_payload["chunk_preload_round_trip_count"] = preload_count
                audit_payload["chunk_preload_total_wait_sec"] = preload_total_wait
                try:
                    sys.stderr.write(
                        f"[AI:{progress_tag}] Response received "
                        f"(streamed={'yes' if provider_meta.get('streamed') else 'no'}, "
                        f"tool_calls={len(tool_calls or [])}, "
                        f"truncated={'yes' if dispatch_result.response_truncated else 'no'})\n"
                    )
                    sys.stderr.flush()
                except Exception:
                    pass
        except Exception as exc:
            error_text = str(exc)
            sys.stderr.write(f"\n[AI ERROR - {provider.upper()}]: {exc}\n")

    if dispatch_result is not None:
        audit_payload["response_truncation_detected"] = dispatch_result.response_truncated
        audit_payload["provider_response_metadata"] = dispatch_result.provider_metadata
        audit_payload["preload_acks"] = dispatch_result.preload_acks
        if "chunk_preload_round_trip_count" not in audit_payload:
            audit_payload["chunk_preload_round_trip_count"] = len(dispatch_result.preload_acks or [])
        if "chunk_preload_total_wait_sec" not in audit_payload:
            audit_payload["chunk_preload_total_wait_sec"] = 0.0
    if error_text is not None:
        audit_payload["error"] = error_text

    audit_path = _write_audit_record(runtime_config, agent_name, audit_payload)
    if error_text is not None:
        raise RuntimeError(f"{error_text} | audit={audit_path}")
    
    if tools:
        return {
            "text": dispatch_result.text,
            "tool_calls": dispatch_result.provider_metadata.get("tool_calls"),
            "audit_path": audit_path,
            "truncated": bool(dispatch_result.response_truncated),
            "provider_metadata": dispatch_result.provider_metadata or {},
        }

    return dispatch_result.text


def filter_context_by_relevance(
    all_context_files: list[str],
    changed_files: list[str],
    qontext_path: str,
    max_neighbors: int = 2,
) -> list[str]:
    relevant_files = set()
    changed_basenames = {Path(f).stem for f in changed_files}
    changed_stems = {Path(f).stem.replace(".q", "") for f in changed_files}

    qontext_lookup = {}
    for ctx_file in all_context_files:
        if ctx_file.endswith(".q.yaml"):
            basename = Path(ctx_file).name
            source_name = basename.replace(".q.yaml", "")
            qontext_lookup[source_name] = ctx_file

    for changed in changed_files:
        changed_basename = Path(changed).name
        if changed_basename in qontext_lookup:
            relevant_files.add(qontext_lookup[changed_basename])

    deps_to_check = set()
    for ctx_file in list(relevant_files):
        try:
            with open(ctx_file, "r", encoding="utf-8") as f:
                ctx_data = yaml.safe_load(f) or {}
            deps = ctx_data.get("dependencies", [])
            if isinstance(deps, list):
                for dep in deps:
                    if isinstance(dep, str):
                        deps_to_check.add(dep.split(".")[-1])
        except Exception:
            pass

    if max_neighbors > 1:
        for changed_basename in changed_basenames | changed_stems:
            for source_name, ctx_file in qontext_lookup.items():
                if changed_basename and changed_basename in source_name:
                    relevant_files.add(ctx_file)

    for dep in deps_to_check:
        for source_name, ctx_file in qontext_lookup.items():
            if dep in source_name or source_name.startswith(dep):
                relevant_files.add(ctx_file)

    return list(relevant_files)
