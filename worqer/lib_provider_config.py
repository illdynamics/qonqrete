#!/usr/bin/env python3
# worqer/lib_provider_config.py
"""Small helpers for provider/runtime option resolution."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

ZERO_COST_PROVIDERS = {"llamacpp"}

LLAMACPP_OPTION_KEYS = [
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
]

DEFAULT_PROVIDER_OPTIONS = {
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
    }
}

LLAMACPP_ENDPOINT_ENV_KEYS = [
    "LLAMACPP_ENDPOINT",
    "QONQ_LLAMACPP_ENDPOINT",
]

LLAMACPP_FALLBACK_ENDPOINTS = [
    "http://host.docker.internal:8080/v1",
    "http://host.containers.internal:8080/v1",
    "http://localhost:8080/v1",
]


def is_zero_cost_provider(provider: str | None) -> bool:
    return (provider or "").strip().lower() in ZERO_COST_PROVIDERS


def normalize_llamacpp_endpoint(endpoint: str | None) -> str | None:
    if endpoint is None:
        return None

    value = str(endpoint).strip()
    if not value:
        return None

    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"

    value = value.rstrip("/")
    if not value.endswith("/v1"):
        value = f"{value}/v1"
    return value


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def get_llamacpp_endpoint_candidates(config: dict[str, Any] | None, agent_name: str) -> list[str]:
    config = config or {}
    agents = config.get("agents", {}) or {}
    providers = config.get("providers", {}) or {}

    agent_cfg = agents.get(agent_name, {}) or {}
    provider_cfg = providers.get("llamacpp", {}) or {}

    raw_values: list[str] = []

    for value in [
        agent_cfg.get("endpoint"),
        provider_cfg.get("endpoint"),
        *[os.environ.get(env_key) for env_key in LLAMACPP_ENDPOINT_ENV_KEYS],
        *LLAMACPP_FALLBACK_ENDPOINTS,
    ]:
        normalized = normalize_llamacpp_endpoint(value)
        if normalized:
            raw_values.append(normalized)

    return _unique_preserve_order(raw_values)


def resolve_agent_provider_options(config: dict[str, Any] | None, agent_name: str) -> dict[str, Any]:
    config = config or {}
    agents = config.get("agents", {}) or {}
    providers = config.get("providers", {}) or {}

    agent_cfg = deepcopy(agents.get(agent_name, {}) or {})
    provider_name = str(agent_cfg.get("provider", "openai")).strip().lower()
    provider_cfg = deepcopy(providers.get(provider_name, {}) or {})

    resolved: dict[str, Any] = {
        "provider": provider_name,
        "model": agent_cfg.get("model"),
    }

    timeout = agent_cfg.get("timeout", provider_cfg.get("timeout"))
    if timeout is not None:
        resolved["timeout"] = timeout

    if provider_name == "llamacpp":
        merged = deepcopy(DEFAULT_PROVIDER_OPTIONS["llamacpp"])
        for key in LLAMACPP_OPTION_KEYS:
            if key in provider_cfg:
                merged[key] = deepcopy(provider_cfg[key])
            if key in agent_cfg:
                merged[key] = deepcopy(agent_cfg[key])

        endpoint_candidates = get_llamacpp_endpoint_candidates(config, agent_name)
        resolved.update(merged)
        resolved["endpoint_candidates"] = endpoint_candidates
        resolved["endpoint"] = merged.get("endpoint") or (endpoint_candidates[0] if endpoint_candidates else None)

    return resolved
