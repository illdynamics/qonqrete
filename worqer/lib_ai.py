#!/usr/bin/env python3
# worqer/lib_ai.py
"""Central AI abstraction with provider-aware budgeting and audited chunking."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

import anthropic
import google.generativeai as genai
import openai
import yaml

try:
    from worqer.ai_capabilities import load_runtime_config, resolve_model_capabilities
except ImportError:
    from ai_capabilities import load_runtime_config, resolve_model_capabilities

try:
    from worqer.lib_provider_config import is_local_endpoint, resolve_agent_provider_options, resolve_local_provider
except ImportError:
    from lib_provider_config import is_local_endpoint, resolve_agent_provider_options, resolve_local_provider

try:
    from worqer.lib_security import MAX_TIMEOUT_SECONDS
except ImportError:
    from lib_security import MAX_TIMEOUT_SECONDS

try:
    from worqer import qompressor
except ImportError:
    try:
        import qompressor
    except ImportError:
        qompressor = None


DEFAULT_API_TIMEOUT = 300
DEFAULT_MAX_PROMPT_CHARS = 800_000
DEFAULT_MAX_CONTEXT_FILES = 100
DEFAULT_MAX_CHARS_PER_FILE = 150_000
STRING_HARD_LIMIT = 9_500_000
DEFAULT_ACK_TEMPLATE = "ACK CHUNK {index}/{total} HASH {hash}"
DEFAULT_CHUNK_SPLIT_PREFERENCES = ("\n\n", "\n", ". ", "! ", "? ", "; ", ", ")


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
    preload_message: str = ""
    expected_ack: str = ""


@dataclass
class DispatchResult:
    text: str
    response_truncated: bool
    provider_metadata: dict[str, Any]
    preload_acks: list[str] = field(default_factory=list)


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


def _provider_timeout_cap(provider: str) -> int:
    return 900 if (provider or "").lower() in {"llamacpp", "ollama"} else MAX_TIMEOUT_SECONDS


def _clamp_timeout(provider: str, timeout: int | None) -> int:
    resolved = int(timeout or _default_api_timeout())
    return max(1, min(resolved, _provider_timeout_cap(provider)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _estimate_tokens(text: str, chars_per_token: float) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / max(chars_per_token, 1.0)))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return load_runtime_config(config)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _worqspace_root(config: dict[str, Any] | None = None) -> Path:
    env_root = os.environ.get("QONQ_WORKSPACE")
    if env_root:
        return Path(env_root)
    cfg = config or {}
    path = cfg.get("paths", {}).get("worqspace")
    if path:
        return Path(path)
    return _project_root() / "worqspace"


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
    if not ai_cfg.get("include_previous_log", True):
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


def _token_budget(
    config: dict[str, Any],
    caps,
    agent_name: str | None,
    output_tokens: int | None,
    task_type: str | None,
    provider_options: dict[str, Any],
) -> dict[str, int]:
    ai_cfg = config.get("ai_budgeting", {})
    output_cfg = ai_cfg.get("agent_output_tokens", {})
    default_output = output_tokens
    if default_output is None and provider_options.get("max_tokens") is not None:
        default_output = provider_options.get("max_tokens")
    if default_output is None and agent_name:
        default_output = output_cfg.get(agent_name)
    if default_output is None:
        task_defaults = ai_cfg.get("task_output_tokens", {})
        default_output = task_defaults.get(task_type or "", caps.safe_output_tokens)
    if default_output is None:
        default_output = caps.safe_output_tokens

    output_budget = min(int(default_output), int(caps.safe_output_tokens))
    planning_limit = caps.planning_context_limit_tokens or caps.total_context_window or (caps.safe_input_tokens + output_budget)
    max_inline_from_window = max(512, int(planning_limit) - output_budget - 1024)
    input_budget = max(512, min(int(caps.safe_input_tokens), max_inline_from_window))
    return {
        "safe_input_tokens": input_budget,
        "safe_output_tokens": output_budget,
        "planning_context_limit_tokens": int(planning_limit),
    }


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


def _find_split_position(text: str, max_chunk_chars: int) -> int:
    if len(text) <= max_chunk_chars:
        return len(text)
    window = text[:max_chunk_chars]
    min_split = max(1, max_chunk_chars // 3)
    for separator in DEFAULT_CHUNK_SPLIT_PREFERENCES:
        idx = window.rfind(separator)
        if idx >= min_split:
            return idx + len(separator)
    return max_chunk_chars


def _chunk_text(text: str, max_chunk_chars: int) -> list[str]:
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chunk_chars:
            chunks.append(remaining)
            break
        split_at = _find_split_position(remaining, max_chunk_chars)
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    return chunks


def _system_message() -> str:
    return "Follow the user's instructions exactly. Do not omit required provided context."


def _build_preload_message(chunk: ChunkRecord) -> str:
    return (
        "Deterministic preload mode. Store the following chunk faithfully for later use.\n"
        f"Chunk index: {chunk.chunk_index}/{chunk.chunk_total}\n"
        f"Section label: {chunk.section_label}\n"
        f"Section hash: {chunk.section_hash}\n"
        f"Chunk hash: {chunk.chunk_hash}\n"
        "Do not summarize or transform it. Reply with exactly:\n"
        f"{chunk.expected_ack}\n\n"
        "BEGIN CHUNK\n"
        f"{chunk.text}\n"
        "END CHUNK"
    )


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


def _message_token_footprint(messages: list[dict[str, str]], chars_per_token: float) -> int:
    total = 0
    for item in messages:
        total += _estimate_tokens(item.get("role", ""), chars_per_token)
        total += _estimate_tokens(item.get("content", ""), chars_per_token)
        total += 6
    return total


def _build_chunk_records(chunks: list[ChunkRecord]) -> None:
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        chunk.chunk_index = idx
        chunk.chunk_total = total
        chunk.expected_ack = DEFAULT_ACK_TEMPLATE.format(index=idx, total=total, hash=chunk.chunk_hash)
        chunk.preload_message = _build_preload_message(chunk)


def _build_transport_messages(inline_prompt: str, chunks: list[ChunkRecord]) -> tuple[list[dict[str, str]], list[list[dict[str, str]]], dict[str, str]]:
    system = {"role": "system", "content": _system_message()}
    history = [system]
    preload_calls: list[list[dict[str, str]]] = []
    for chunk in chunks:
        preload_user = {"role": "user", "content": chunk.preload_message}
        preload_calls.append(history + [preload_user])
        history = history + [preload_user, {"role": "assistant", "content": chunk.expected_ack}]
    final_user = {"role": "user", "content": _build_final_user_message(inline_prompt, chunks)}
    final_messages = history + [final_user]
    return final_messages, preload_calls, {"system_message": system["content"], "final_user_message": final_user["content"]}


def _validate_conversation_plan(
    inline_prompt: str,
    chunks: list[ChunkRecord],
    chars_per_token: float,
    planning_context_limit_tokens: int,
    final_output_budget: int,
    ack_output_budget: int,
) -> dict[str, Any]:
    final_messages, preload_calls, supporting = _build_transport_messages(inline_prompt, chunks)
    preload_footprints = []
    max_preload = 0
    for idx, messages in enumerate(preload_calls, start=1):
        footprint = _message_token_footprint(messages, chars_per_token) + ack_output_budget
        preload_footprints.append({"step": idx, "messages_token_estimate": footprint})
        max_preload = max(max_preload, footprint)
    final_footprint = _message_token_footprint(final_messages, chars_per_token) + final_output_budget
    fits = final_footprint <= planning_context_limit_tokens and max_preload <= planning_context_limit_tokens
    diagnostics = {
        "planning_context_limit_tokens": planning_context_limit_tokens,
        "ack_output_budget_tokens": ack_output_budget,
        "preload_requests": preload_footprints,
        "max_preload_request_tokens": max_preload,
        "final_conversation_tokens": final_footprint,
        "fits": fits,
        "system_message": supporting["system_message"],
        "final_user_message": supporting["final_user_message"],
    }
    if not fits:
        raise RuntimeError(
            "No-loss chunking plan exceeds the effective planning context limit when full preload history, ACKs, and final request are counted."
        )
    return diagnostics


def _plan_chunks(
    sections: list[PromptSection],
    budgets: dict[str, int],
    chars_per_token: float,
    config: dict[str, Any],
    supports_chunking: bool,
) -> tuple[list[PromptSection], list[ChunkRecord], dict[str, Any]]:
    active_sections = [section for section in sections if not section.omitted]
    active_tokens = sum(section.estimated_tokens for section in active_sections)
    if active_tokens <= budgets["safe_input_tokens"]:
        return sections, [], {"chunking_used": False, "reason": "not_needed"}

    if not supports_chunking or not config.get("ai_budgeting", {}).get("enable_no_loss_chunking", True):
        required = [section.label for section in active_sections if section.required]
        raise RuntimeError(f"Prompt exceeds safe input budget and no-loss chunking is unavailable. Required sections: {required}")

    chunk_target_tokens = min(
        max(512, budgets["safe_input_tokens"] // 2),
        config.get("ai_budgeting", {}).get("chunk_target_input_tokens", max(512, budgets["safe_input_tokens"] // 2)),
    )
    max_preload_chunks = config.get("ai_budgeting", {}).get("max_preload_chunks_per_request", 24)
    max_chunk_chars = max(2000, int(chunk_target_tokens * chars_per_token))
    chunks: list[ChunkRecord] = []
    chunkable_sections = [
        section for section in active_sections
        if section.loss_policy == "chunkable" or (section.required and section.loss_policy == "preserve" and section.estimated_tokens > budgets["safe_input_tokens"] // 2)
    ]
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

    _build_chunk_records(chunks)

    for section in sections:
        if section.chunked:
            section.estimated_tokens = 0

    remaining_active = [section for section in sections if not section.omitted and not section.chunked]
    remaining_tokens = sum(section.estimated_tokens for section in remaining_active)
    if remaining_tokens > budgets["safe_input_tokens"]:
        raise RuntimeError("Inline prompt still exceeds budget after chunk planning.")

    ack_budget = min(64, config.get("ai_budgeting", {}).get("ack_output_budget_tokens", 32))
    footprint = _validate_conversation_plan(
        inline_prompt=_build_inline_prompt(sections),
        chunks=chunks,
        chars_per_token=chars_per_token,
        planning_context_limit_tokens=budgets["planning_context_limit_tokens"],
        final_output_budget=budgets["safe_output_tokens"],
        ack_output_budget=ack_budget,
    )
    return sections, chunks, {
        "chunking_used": True,
        "reason": "required_or_chunkable_sections_preloaded",
        "conversation_footprint": footprint,
    }


def _build_inline_prompt(sections: list[PromptSection]) -> str:
    return "\n\n".join(section.content for section in sections if not section.omitted and not section.chunked).strip()


def _http_json_request(url: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 30, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = None
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=body, method=method, headers=merged_headers)
    with urlrequest.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_model_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    return data if isinstance(data, list) else []


def _model_profile(configured_model: str) -> dict[str, Any]:
    raw = (configured_model or "").strip()
    expanded = os.path.expandvars(raw)
    expanded = os.path.expanduser(expanded)
    candidates = [raw, expanded, os.path.basename(raw), os.path.basename(expanded)]
    return {"raw": raw, "expanded": expanded, "basenames": [item for item in dict.fromkeys(candidates) if item]}


def _llamacpp_aliases(entry: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("id", "root", "parent", "alias"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            aliases.append(value.strip())
    for item in entry.get("aliases", []) or []:
        if isinstance(item, str) and item.strip():
            aliases.append(item.strip())
    return aliases


def _select_llamacpp_model_id(configured_model: str, endpoint: str, timeout: int, api_key: str | None) -> tuple[str, dict[str, Any]]:
    profile = _model_profile(configured_model)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        payload = _http_json_request(f"{endpoint.rstrip('/')}/models", timeout=timeout, headers=headers)
        entries = _extract_model_entries(payload)
    except Exception as exc:
        return configured_model, {"models_preflight_error": str(exc), "configured_model": configured_model}

    if not entries:
        return configured_model, {"models_preflight_empty": True, "configured_model": configured_model}

    raw = profile["raw"]
    expanded = profile["expanded"]
    basenames = {os.path.basename(raw), os.path.basename(expanded)}
    exact_alias_match = None
    basename_match = None
    single_model_match = None
    for entry in entries:
        aliases = _llamacpp_aliases(entry)
        if raw in aliases or expanded in aliases:
            exact_alias_match = entry.get("id") or raw
            break
        if any(os.path.basename(alias) in basenames for alias in aliases):
            basename_match = entry.get("id") or aliases[0]
        if len(entries) == 1 and any(os.path.basename(alias) in basenames for alias in aliases):
            single_model_match = entry.get("id") or aliases[0]
    resolved = exact_alias_match or basename_match or single_model_match or configured_model
    return resolved, {
        "configured_model": configured_model,
        "resolved_model": resolved,
        "server_models": [entry.get("id") for entry in entries if entry.get("id")],
    }


def _discover_ollama_native(native_endpoint: str, timeout: int, model: str) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    try:
        diagnostics["version"] = _http_json_request(f"{native_endpoint.rstrip('/')}/version", timeout=timeout)
    except Exception as exc:
        diagnostics["version_error"] = str(exc)
    try:
        diagnostics["tags"] = _http_json_request(f"{native_endpoint.rstrip('/')}/tags", timeout=timeout)
    except Exception as exc:
        diagnostics["tags_error"] = str(exc)
    try:
        diagnostics["show"] = _http_json_request(f"{native_endpoint.rstrip('/')}/show", method="POST", timeout=timeout, payload={"name": model})
    except Exception as exc:
        diagnostics["show_error"] = str(exc)
    try:
        diagnostics["ps"] = _http_json_request(f"{native_endpoint.rstrip('/')}/ps", timeout=timeout)
    except Exception as exc:
        diagnostics["ps_error"] = str(exc)
    return diagnostics


def _installed_ollama_models(v1_payload: dict[str, Any] | None, native_payload: dict[str, Any] | None) -> list[str]:
    names: list[str] = []
    for entry in _extract_model_entries(v1_payload or {}):
        model_id = entry.get("id")
        if isinstance(model_id, str) and model_id:
            names.append(model_id)
    for entry in (native_payload or {}).get("models", []) or []:
        for key in ("name", "model"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                names.append(value)
    return list(dict.fromkeys(names))


def _normalize_ollama_model_candidates(model: str) -> list[str]:
    value = (model or "").strip()
    if not value:
        return []
    candidates = [value]
    if value.endswith(":latest"):
        candidates.append(value[: -len(":latest")])
    elif ":" not in value:
        candidates.append(f"{value}:latest")
    return list(dict.fromkeys(candidates))


def _select_ollama_model_id(model: str, endpoint: str, native_endpoint: str | None, timeout: int) -> tuple[str, dict[str, Any]]:
    v1_payload = None
    discovery: dict[str, Any] = {}
    try:
        v1_payload = _http_json_request(f"{endpoint.rstrip('/')}/models", timeout=timeout, headers={})
    except Exception as exc:
        discovery["v1_models_error"] = str(exc)

    native_discovery = _discover_ollama_native(native_endpoint, timeout, model) if native_endpoint else {}
    installed = _installed_ollama_models(v1_payload, native_discovery.get("tags"))
    candidates = _normalize_ollama_model_candidates(model)
    lowered_installed = {item.lower(): item for item in installed}

    for candidate in candidates:
        if candidate in installed:
            return candidate, {"configured_model": model, "resolved_model": candidate, "installed_models": installed, "native_discovery": native_discovery, **discovery}
        normalized = lowered_installed.get(candidate.lower())
        if normalized:
            return normalized, {"configured_model": model, "resolved_model": normalized, "installed_models": installed, "native_discovery": native_discovery, **discovery}

    if installed:
        raise RuntimeError(f"Configured Ollama model `{model}` was not found. Installed models: {', '.join(installed[:12])}")
    return model, {"configured_model": model, "resolved_model": model, "installed_models": [], "native_discovery": native_discovery, **discovery}


def _openai_client_for_provider(provider: str, timeout: int):
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
    raise ValueError(f"Provider {provider} does not use OpenAI-compatible dispatch")


def _build_openai_chat_kwargs(
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    request_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": output_tokens,
    }
    request_options = request_options or {}
    if request_options.get("ack_mode"):
        payload["temperature"] = 0
        payload["top_p"] = 1
        payload["max_tokens"] = min(output_tokens, request_options.get("ack_output_budget_tokens", 32))
    return payload


def _dispatch_openai_compatible(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
    request_options: dict[str, Any] | None = None,
) -> DispatchResult:
    client = _openai_client_for_provider(provider, timeout)
    response = client.chat.completions.create(timeout=timeout, **_build_openai_chat_kwargs(model, messages, output_tokens, request_options=request_options))
    choice = response.choices[0]
    text = choice.message.content or ""
    finish_reason = getattr(choice, "finish_reason", None)
    return DispatchResult(
        text=text.strip(),
        response_truncated=(finish_reason == "length"),
        provider_metadata={
            "finish_reason": finish_reason,
            "usage": getattr(response, "usage", None).model_dump() if getattr(response, "usage", None) else None,
        },
    )


def _build_local_openai_request_kwargs(
    provider: str,
    resolved_model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    provider_options: dict[str, Any],
    request_options: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "max_tokens": int(request_options.get("max_tokens", output_tokens) if request_options else output_tokens),
        "temperature": provider_options.get("temperature"),
        "top_p": provider_options.get("top_p"),
        "presence_penalty": provider_options.get("presence_penalty"),
        "frequency_penalty": provider_options.get("frequency_penalty"),
    }
    stop = provider_options.get("stop")
    if stop:
        payload["stop"] = stop
    if request_options and request_options.get("ack_mode"):
        payload["temperature"] = 0
        payload["top_p"] = 1
        payload["max_tokens"] = min(int(payload["max_tokens"]), request_options.get("ack_output_budget_tokens", 32))
    extra_body = {}
    for key in ("top_k", "min_p", "seed", "repeat_penalty", "mirostat", "mirostat_tau", "mirostat_eta", "keep_alive", "think", "reasoning_effort"):
        value = provider_options.get(key)
        if value is not None:
            extra_body[key] = value
    if request_options and request_options.get("ack_mode"):
        extra_body.setdefault("seed", 0)
    if extra_body:
        payload["extra_body"] = extra_body
    return {key: value for key, value in payload.items() if value is not None}


def _dispatch_local_openai_compatible(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
    provider_options: dict[str, Any],
    request_options: dict[str, Any] | None = None,
) -> DispatchResult:
    resolution = resolve_local_provider(provider, config={"providers": {provider: provider_options}})
    endpoint_candidates = provider_options.get("endpoint_candidates") or resolution.endpoint_candidates
    native_endpoint_candidates = provider_options.get("native_endpoint_candidates") or resolution.native_endpoint_candidates
    last_error = None

    for endpoint in endpoint_candidates:
        try:
            if provider == "llamacpp":
                api_key = os.environ.get("LLAMACPP_API_KEY") or "sk-no-key-required"
                resolved_model, discovery = _select_llamacpp_model_id(model, endpoint, timeout, None if api_key == "sk-no-key-required" else api_key)
            else:
                configured_key = provider_options.get("api_key") or os.environ.get("OLLAMA_API_KEY")
                api_key = configured_key or ("ollama" if is_local_endpoint(endpoint) else None)
                if api_key is None:
                    raise ValueError("OLLAMA_API_KEY is required for non-local Ollama endpoints.")
                native_endpoint = (native_endpoint_candidates[0] if native_endpoint_candidates else None)
                resolved_model, discovery = _select_ollama_model_id(model, endpoint, native_endpoint, timeout)

            client = openai.OpenAI(api_key=api_key, base_url=endpoint, timeout=timeout)
            request_kwargs = _build_local_openai_request_kwargs(provider, resolved_model, messages, output_tokens, provider_options, request_options)
            response = client.chat.completions.create(timeout=timeout, **request_kwargs)
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            provider_metadata = {
                "endpoint": endpoint,
                "resolved_model": resolved_model,
                "finish_reason": finish_reason,
                "usage": getattr(response, "usage", None).model_dump() if getattr(response, "usage", None) else None,
                "discovery": discovery,
            }
            if provider == "ollama":
                ps_models = (((discovery.get("native_discovery") or {}).get("ps") or {}).get("models") or [])
                observed_context = None
                for item in ps_models:
                    if item.get("model") in {resolved_model, model}:
                        observed_context = item.get("context_length")
                        break
                provider_metadata["observed_context_length"] = observed_context
            return DispatchResult(
                text=(choice.message.content or "").strip(),
                response_truncated=(finish_reason == "length"),
                provider_metadata=provider_metadata,
            )
        except Exception as exc:
            last_error = exc
            sys.stderr.write(f"\n[WARN] {provider} endpoint failed {endpoint}: {exc}\n")

    attempted = ", ".join(endpoint_candidates)
    raise RuntimeError(f"{provider} request failed for every endpoint candidate: {attempted}. Last error: {last_error}")


def _dispatch_anthropic(
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
) -> DispatchResult:
    client = anthropic.Anthropic(timeout=timeout)
    system = None
    anth_messages = []
    for item in messages:
        if item["role"] == "system":
            system = item["content"] if system is None else f"{system}\n\n{item['content']}"
        else:
            anth_messages.append({"role": item["role"], "content": item["content"]})
    response = client.messages.create(
        model=model,
        max_tokens=output_tokens,
        system=system,
        messages=anth_messages,
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    stop_reason = getattr(response, "stop_reason", None)
    usage = {
        "input_tokens": getattr(getattr(response, "usage", None), "input_tokens", None),
        "output_tokens": getattr(getattr(response, "usage", None), "output_tokens", None),
    }
    return DispatchResult(
        text=text.strip(),
        response_truncated=(stop_reason == "max_tokens"),
        provider_metadata={"stop_reason": stop_reason, "usage": usage},
    )


def _dispatch_gemini(
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int,
) -> DispatchResult:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment.")
    genai.configure(api_key=api_key)
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    history = []
    user_messages = [m for m in messages if m["role"] != "system"]
    for item in user_messages[:-1]:
        role = "model" if item["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [item["content"]]})
    model_client = genai.GenerativeModel(
        model_name=model,
        system_instruction="\n\n".join(system_parts) if system_parts else None,
        generation_config={"max_output_tokens": output_tokens},
    )
    if user_messages:
        chat = model_client.start_chat(history=history)
        response = chat.send_message(user_messages[-1]["content"], request_options={"timeout": timeout})
    else:
        response = model_client.generate_content("", request_options={"timeout": timeout})
    text = getattr(response, "text", "") or ""
    truncated = False
    try:
        finish_reason = response.candidates[0].finish_reason
        truncated = str(finish_reason).endswith("MAX_TOKENS")
    except Exception:
        finish_reason = None
    return DispatchResult(
        text=text.strip(),
        response_truncated=truncated,
        provider_metadata={"finish_reason": str(finish_reason) if finish_reason is not None else None},
    )


def run_ai_messages(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    output_tokens: int,
    timeout: int | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    request_options: dict[str, Any] | None = None,
) -> DispatchResult:
    resolved_timeout = _clamp_timeout(provider, timeout)
    provider_l = provider.lower()
    provider_options = resolve_agent_provider_options(config or {}, agent_name=agent_name, provider=provider_l)
    if provider_options.get("timeout") and timeout is None:
        resolved_timeout = _clamp_timeout(provider, provider_options.get("timeout"))
    try:
        if provider_l in {"openai", "deepseek", "qwen", "openrouter"}:
            return _dispatch_openai_compatible(provider_l, model, messages, output_tokens, resolved_timeout, request_options=request_options)
        if provider_l in {"llamacpp", "ollama"}:
            return _dispatch_local_openai_compatible(provider_l, model, messages, output_tokens, resolved_timeout, provider_options, request_options=request_options)
        if provider_l == "anthropic":
            return _dispatch_anthropic(model, messages, output_tokens, resolved_timeout)
        if provider_l == "gemini":
            return _dispatch_gemini(model, messages, output_tokens, resolved_timeout)
        raise ValueError(f"Unknown AI Provider: {provider}")
    except openai.APITimeoutError as exc:
        raise TimeoutError(f"{provider} API timeout after {resolved_timeout}s") from exc
    except anthropic.APITimeoutError as exc:
        raise TimeoutError(f"{provider} API timeout after {resolved_timeout}s") from exc


def _dispatch_with_chunking(
    provider: str,
    model: str,
    inline_prompt: str,
    chunks: list[ChunkRecord],
    output_tokens: int,
    config: dict[str, Any],
    agent_name: str | None,
    timeout: int | None = None,
) -> tuple[DispatchResult, list[dict[str, Any]]]:
    messages = [{"role": "system", "content": _system_message()}]
    acks: list[str] = []
    retry_log: list[dict[str, Any]] = []
    max_retries = max(0, int(config.get("ai_budgeting", {}).get("preload_ack_max_retries", 2)))
    ack_budget = min(64, config.get("ai_budgeting", {}).get("ack_output_budget_tokens", 32))
    for chunk in chunks:
        preload = {"role": "user", "content": chunk.preload_message}
        attempts = []
        ack_result = None
        for attempt in range(1, max_retries + 2):
            try:
                ack_result = run_ai_messages(
                    provider,
                    model,
                    messages + [preload],
                    output_tokens=ack_budget,
                    timeout=timeout,
                    config=config,
                    agent_name=agent_name,
                    request_options={"ack_mode": True, "ack_output_budget_tokens": ack_budget},
                )
                matched = ack_result.text.strip() == chunk.expected_ack
                attempts.append({"attempt": attempt, "matched": matched, "response": ack_result.text.strip()})
                if matched:
                    break
            except Exception as exc:
                attempts.append({"attempt": attempt, "matched": False, "error": str(exc)})
                ack_result = None
            if attempt >= max_retries + 1:
                break

        retry_log.append({
            "chunk_index": chunk.chunk_index,
            "expected_ack": chunk.expected_ack,
            "attempts": attempts,
            "success": bool(ack_result and ack_result.text.strip() == chunk.expected_ack),
        })
        if not ack_result or ack_result.text.strip() != chunk.expected_ack:
            raise RuntimeError(f"Chunk preload ACK mismatch after bounded retries. Expected `{chunk.expected_ack}`")
        acks.append(ack_result.text.strip())
        messages.append(preload)
        messages.append({"role": "assistant", "content": ack_result.text.strip()})

    final_user = {"role": "user", "content": _build_final_user_message(inline_prompt, chunks)}
    final_result = run_ai_messages(
        provider=provider,
        model=model,
        messages=messages + [final_user],
        output_tokens=output_tokens,
        timeout=timeout,
        config=config,
        agent_name=agent_name,
    )
    final_result.preload_acks = acks
    return final_result, retry_log


def _relative_to_worqspace(path: Path, config: dict[str, Any]) -> str:
    try:
        return str(path.relative_to(_worqspace_root(config)))
    except Exception:
        return str(path)


def _write_audit_sidecars(
    config: dict[str, Any],
    request_hash: str,
    inline_prompt: str,
    chunks: list[ChunkRecord],
    final_user_message: str,
    preload_acks: list[str] | None = None,
) -> dict[str, Any]:
    root = _worqspace_root(config)
    base_dir = root / config.get("ai_budgeting", {}).get("audit_dir", "audit/ai_payloads")
    sidecar_root = base_dir.parent / "ai_payload_sidecars" / request_hash[:20]
    sidecar_root.mkdir(parents=True, exist_ok=True)

    files = []

    def write_file(name: str, content: str) -> str:
        path = sidecar_root / name
        path.write_text(content, encoding="utf-8")
        files.append({"path": _relative_to_worqspace(path, config), "sha256": _sha256_text(content), "char_count": len(content)})
        return str(path)

    write_file("system_message.txt", _system_message())
    write_file("inline_prompt.txt", inline_prompt)
    write_file("final_user_message.txt", final_user_message)
    for chunk in chunks:
        write_file(f"chunk-{chunk.chunk_index:03d}.txt", chunk.text)
        write_file(f"preload-{chunk.chunk_index:03d}.txt", chunk.preload_message)
    for idx, ack in enumerate(preload_acks or [], start=1):
        write_file(f"ack-{idx:03d}.txt", ack)
    return {"directory": _relative_to_worqspace(sidecar_root, config), "files": files}


def _write_audit_record(config: dict[str, Any], agent_name: str | None, payload: dict[str, Any]) -> Path:
    root = _worqspace_root(config)
    audit_dir = root / config.get("ai_budgeting", {}).get("audit_dir", "audit/ai_payloads")
    audit_dir.mkdir(parents=True, exist_ok=True)
    label = _sanitize_name(payload.get("audit_label") or agent_name or "ai-call")
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{label}-{payload['request_hash'][:12]}.json"
    audit_path = audit_dir / filename
    audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
) -> dict[str, Any]:
    capability_provider = provider if provider.lower() != "dry-run" else config.get("ai_budgeting", {}).get("dry_run_provider", "deepseek")
    provider_options = resolve_agent_provider_options(config, agent_name=agent_name, provider=capability_provider)
    caps = resolve_model_capabilities(capability_provider, model, config=config, agent_name=agent_name)
    budgets = _token_budget(config, caps, agent_name, output_tokens, task_type, provider_options)
    sections = _normalize_sections(prompt, context_files, prompt_sections, config, caps, budget_config)
    sections, dropped_sections, summarized_sections = _optimize_sections(sections, budgets["safe_input_tokens"], caps.chars_per_token)
    supports_chunking = caps.supports_multi_message_history and caps.supports_chunk_preload and (allow_chunking is not False)
    sections, chunks, chunk_meta = _plan_chunks(sections, budgets, caps.chars_per_token, config, supports_chunking)
    inline_prompt = _build_inline_prompt(sections)
    inline_tokens = _estimate_tokens(inline_prompt, caps.chars_per_token)
    if inline_tokens > budgets["safe_input_tokens"]:
        raise RuntimeError("Inline prompt exceeds safe input budget after optimization and chunk planning.")

    final_messages, _, supporting = _build_transport_messages(inline_prompt, chunks)
    active_source_files = sorted({path for section in sections for path in section.source_files if not section.omitted})
    request_hash = _sha256_text(inline_prompt + "".join(chunk.chunk_hash for chunk in chunks))
    return {
        "capabilities": caps,
        "capability_provider": capability_provider,
        "provider_options": provider_options,
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
        "final_messages": final_messages,
        "system_message": _system_message(),
        "final_user_message": supporting["final_user_message"],
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
    audit_label: str | None = None,
) -> str:
    context_files = context_files or []
    runtime_config = _load_config(config)
    budget_config = {
        "max_prompt_chars": max_prompt_chars or DEFAULT_MAX_PROMPT_CHARS,
        "max_context_files": max_context_files or DEFAULT_MAX_CONTEXT_FILES,
        "max_chars_per_file": max_chars_per_file or DEFAULT_MAX_CHARS_PER_FILE,
    }

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
    )

    dispatch_result: DispatchResult | None = None
    error_text: str | None = None
    ack_retry_log: list[dict[str, Any]] = []
    resolved_timeout = _clamp_timeout(provider, timeout or plan["provider_options"].get("timeout"))

    audit_payload = {
        "schema_version": "ai-call-metadata.v2",
        "created_at": _utc_now(),
        "provider": provider,
        "model": model,
        "agent_name": agent_name,
        "audit_label": audit_label or agent_name or "ai_call",
        "capabilities": plan["capabilities"].to_dict(),
        "provider_options": {key: value for key, value in plan["provider_options"].items() if key not in {"api_key"}},
        "input_token_estimate": plan["inline_tokens"] + sum(chunk.estimated_tokens for chunk in plan["chunks"]),
        "inline_input_token_estimate": plan["inline_tokens"],
        "output_token_budget": plan["budgets"]["safe_output_tokens"],
        "safe_input_budget": plan["budgets"]["safe_input_tokens"],
        "safe_output_budget": plan["budgets"]["safe_output_tokens"],
        "planning_context_limit_tokens": plan["budgets"]["planning_context_limit_tokens"],
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
        "conversation_budgeting": plan["chunk_meta"].get("conversation_footprint", {
            "planning_context_limit_tokens": plan["budgets"]["planning_context_limit_tokens"],
            "final_conversation_tokens": _message_token_footprint(plan["final_messages"], plan["capabilities"].chars_per_token) + plan["budgets"]["safe_output_tokens"],
        }),
    }

    if len(plan["inline_prompt"]) > STRING_HARD_LIMIT:
        audit_payload["fallback_char_emergency_protection_used"] = True
        error_text = f"Inline prompt still exceeds hard string limit {STRING_HARD_LIMIT} chars."
    else:
        try:
            if provider.lower() == "dry-run":
                dispatch_result = DispatchResult(
                    text="[DRY RUN] request planned without external API call.",
                    response_truncated=False,
                    provider_metadata={"mode": "dry-run"},
                )
            elif plan["chunks"]:
                dispatch_result, ack_retry_log = _dispatch_with_chunking(
                    provider=provider,
                    model=model,
                    inline_prompt=plan["inline_prompt"],
                    chunks=plan["chunks"],
                    output_tokens=plan["budgets"]["safe_output_tokens"],
                    timeout=resolved_timeout,
                    config=runtime_config,
                    agent_name=agent_name,
                )
            else:
                messages = [
                    {"role": "system", "content": _system_message()},
                    {"role": "user", "content": plan["inline_prompt"]},
                ]
                dispatch_result = run_ai_messages(
                    provider=provider,
                    model=model,
                    messages=messages,
                    output_tokens=plan["budgets"]["safe_output_tokens"],
                    timeout=resolved_timeout,
                    config=runtime_config,
                    agent_name=agent_name,
                )
        except Exception as exc:
            error_text = str(exc)
            sys.stderr.write(f"\n[AI ERROR - {provider.upper()}]: {exc}\n")

    preload_acks = dispatch_result.preload_acks if dispatch_result else []
    audit_payload["transport_sidecars"] = _write_audit_sidecars(
        runtime_config,
        plan["request_hash"],
        plan["inline_prompt"],
        plan["chunks"],
        plan["final_user_message"],
        preload_acks=preload_acks,
    )
    audit_payload["preload_ack_retries"] = ack_retry_log

    if dispatch_result is not None:
        audit_payload["response_truncation_detected"] = dispatch_result.response_truncated
        audit_payload["provider_response_metadata"] = dispatch_result.provider_metadata
        audit_payload["preload_acks"] = dispatch_result.preload_acks
    if error_text is not None:
        audit_payload["error"] = error_text

    audit_path = _write_audit_record(runtime_config, agent_name, audit_payload)
    if error_text is not None:
        raise RuntimeError(f"{error_text} | audit={audit_path}")
    return dispatch_result.text


def ai_query(
    prompt: str,
    provider: str,
    model: str,
    context_files: list[str] | None = None,
    timeout: int | None = None,
    agent_name: str | None = None,
    config: dict[str, Any] | None = None,
    output_tokens: int | None = None,
) -> str:
    return run_ai_completion(
        provider=provider,
        model=model,
        prompt=prompt,
        context_files=context_files or [],
        timeout=timeout,
        agent_name=agent_name,
        config=config,
        output_tokens=output_tokens,
    )


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
