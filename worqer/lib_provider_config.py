#!/usr/bin/env python3
"""Shared provider option resolution for remote and local HTTP LLM providers."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


ZERO_COST_PROVIDERS = {"local", "llamacpp", "ollama"}
REQUIRED_API_KEY_ENV_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "QWEN_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

LLAMACPP_OPTION_KEYS = {
    "endpoint",
    "timeout",
    "max_tokens",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "seed",
    "repeat_penalty",
    "presence_penalty",
    "frequency_penalty",
    "stop",
    "mirostat",
    "mirostat_tau",
    "mirostat_eta",
    "planning_context_limit_tokens",
}

OLLAMA_OPTION_KEYS = {
    "endpoint",
    "native_endpoint",
    "timeout",
    "max_tokens",
    "temperature",
    "top_p",
    "seed",
    "presence_penalty",
    "frequency_penalty",
    "stop",
    "use_native_discovery",
    "use_native_metadata",
    "use_native_transport",
    "enable_responses_api",
    "keep_alive",
    "think",
    "reasoning_effort",
    "api_key",
    "planning_context_limit_tokens",
}

PROVIDER_OPTION_KEYS = {
    "llamacpp": LLAMACPP_OPTION_KEYS,
    "ollama": OLLAMA_OPTION_KEYS,
}

DEFAULT_PROVIDER_OPTIONS: dict[str, dict[str, Any]] = {
    "llamacpp": {
        "timeout": 900,
        "max_tokens": 8192,
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.05,
        "seed": -1,
        "repeat_penalty": 1.05,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "stop": [],
        "planning_context_limit_tokens": None,
    },
    "ollama": {
        "timeout": 900,
        "max_tokens": 8192,
        "temperature": 0.2,
        "top_p": 0.9,
        "seed": None,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "stop": [],
        "use_native_discovery": True,
        "use_native_metadata": True,
        "use_native_transport": False,
        "enable_responses_api": False,
        "keep_alive": "10m",
        "think": False,
        "reasoning_effort": None,
        "api_key": None,
        "planning_context_limit_tokens": None,
    },
}


@dataclass(frozen=True)
class LocalProviderResolution:
    provider: str
    options: dict[str, Any]
    endpoint_candidates: list[str]
    native_endpoint_candidates: list[str]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_provider_defaults(provider: str) -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_PROVIDER_OPTIONS.get((provider or "").lower(), {}))


def is_zero_cost_provider(provider: str | None) -> bool:
    return (provider or "").lower() in ZERO_COST_PROVIDERS


def required_api_key_env(provider: str | None) -> str | None:
    return REQUIRED_API_KEY_ENV_BY_PROVIDER.get((provider or "").lower())


def is_local_endpoint(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    hostname = (parsed.hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal", "host.containers.internal"}


def normalize_endpoint_for_suffix(endpoint: str | None, suffix: str) -> str | None:
    if endpoint is None:
        return None
    value = str(endpoint).strip()
    if not value:
        return None
    if "://" not in value:
        value = f"http://{value}"
    value = value.rstrip("/")
    if value.endswith(suffix):
        return value
    if value.endswith("/v1") and suffix == "/api":
        value = value[: -len("/v1")]
    if value.endswith("/api") and suffix == "/v1":
        value = value[: -len("/api")]
    return f"{value}{suffix}"


def normalize_llamacpp_endpoint(endpoint: str | None) -> str | None:
    return normalize_endpoint_for_suffix(endpoint, "/v1")


def normalize_ollama_endpoint(endpoint: str | None) -> str | None:
    return normalize_endpoint_for_suffix(endpoint, "/v1")


def normalize_ollama_native_endpoint(endpoint: str | None) -> str | None:
    return normalize_endpoint_for_suffix(endpoint, "/api")


def _dedupe_keep_order(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_candidates(values: list[str | None], normalizer) -> list[str]:
    return _dedupe_keep_order([normalizer(value) for value in values if value is not None])


def get_provider_config_block(config: dict[str, Any] | None, provider: str) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    return dict(config.get("providers", {}).get((provider or "").lower(), {}) or {})


def resolve_agent_provider_options(
    config: dict[str, Any] | None,
    agent_name: str | None = None,
    provider: str | None = None,
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    resolved_agent_cfg = dict(agent_config or {})
    if agent_name and not resolved_agent_cfg:
        resolved_agent_cfg = dict(config.get("agents", {}).get(agent_name, {}) or {})
    provider_name = (provider or resolved_agent_cfg.get("provider") or "").lower()
    defaults = get_provider_defaults(provider_name)
    option_keys = PROVIDER_OPTION_KEYS.get(provider_name, set())
    provider_block = get_provider_config_block(config, provider_name)

    merged: dict[str, Any] = dict(defaults)
    for source in (provider_block, resolved_agent_cfg):
        for key, value in source.items():
            if key in option_keys and value is not None:
                merged[key] = copy.deepcopy(value)

    if provider_name == "llamacpp":
        endpoint_candidates = _normalize_candidates([
            resolved_agent_cfg.get("endpoint"),
            provider_block.get("endpoint"),
            os.environ.get("LLAMACPP_ENDPOINT"),
            os.environ.get("QONQ_LLAMACPP_ENDPOINT"),
            "http://host.docker.internal:8080/v1",
            "http://host.containers.internal:8080/v1",
            "http://localhost:8080/v1",
        ], normalize_llamacpp_endpoint)
        merged["endpoint"] = normalize_llamacpp_endpoint(merged.get("endpoint")) or (endpoint_candidates[0] if endpoint_candidates else None)
        merged["endpoint_candidates"] = endpoint_candidates
        return merged

    if provider_name == "ollama":
        endpoint_candidates = _normalize_candidates([
            resolved_agent_cfg.get("endpoint"),
            provider_block.get("endpoint"),
            os.environ.get("OLLAMA_ENDPOINT"),
            os.environ.get("QONQ_OLLAMA_ENDPOINT"),
            "http://host.docker.internal:11434/v1",
            "http://host.containers.internal:11434/v1",
            "http://localhost:11434/v1",
        ], normalize_ollama_endpoint)
        primary_native = resolved_agent_cfg.get("native_endpoint") or provider_block.get("native_endpoint")
        derived_native = normalize_ollama_native_endpoint(endpoint_candidates[0]) if endpoint_candidates else None
        native_endpoint_candidates = _normalize_candidates([
            primary_native,
            os.environ.get("OLLAMA_NATIVE_ENDPOINT"),
            os.environ.get("QONQ_OLLAMA_NATIVE_ENDPOINT"),
            derived_native,
            "http://host.docker.internal:11434/api",
            "http://host.containers.internal:11434/api",
            "http://localhost:11434/api",
        ], normalize_ollama_native_endpoint)
        merged["endpoint"] = normalize_ollama_endpoint(merged.get("endpoint")) or (endpoint_candidates[0] if endpoint_candidates else None)
        merged["native_endpoint"] = normalize_ollama_native_endpoint(merged.get("native_endpoint")) or (native_endpoint_candidates[0] if native_endpoint_candidates else None)
        merged["endpoint_candidates"] = endpoint_candidates
        merged["native_endpoint_candidates"] = native_endpoint_candidates
        return merged

    return merged


def resolve_local_provider(provider: str, config: dict[str, Any] | None, agent_name: str | None = None, agent_config: dict[str, Any] | None = None) -> LocalProviderResolution:
    options = resolve_agent_provider_options(config=config, agent_name=agent_name, provider=provider, agent_config=agent_config)
    return LocalProviderResolution(
        provider=(provider or "").lower(),
        options=options,
        endpoint_candidates=list(options.get("endpoint_candidates", [])),
        native_endpoint_candidates=list(options.get("native_endpoint_candidates", [])),
    )
