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


UNSUPPORTED_OLLAMA_OPTION_KEYS = {"use_native_transport", "enable_responses_api"}
BOOLEAN_OPTION_KEYS = {
    "use_native_discovery",
    "use_native_metadata",
    "think",
}
NUMERIC_OPTION_KEYS = {
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
    "mirostat",
    "mirostat_tau",
    "mirostat_eta",
    "planning_context_limit_tokens",
}


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


def _same_endpoint_host(lhs: str | None, rhs: str | None) -> bool:
    if not lhs or not rhs:
        return False
    left = urlparse(lhs if "://" in lhs else f"http://{lhs}")
    right = urlparse(rhs if "://" in rhs else f"http://{rhs}")
    return (
        (left.scheme or "http").lower() == (right.scheme or "http").lower()
        and (left.hostname or "").lower() == (right.hostname or "").lower()
        and (left.port or (443 if left.scheme == "https" else 80)) == (right.port or (443 if right.scheme == "https" else 80))
    )


def paired_ollama_native_endpoint(endpoint: str | None, native_endpoint_candidates: list[str] | None = None) -> str | None:
    derived = normalize_ollama_native_endpoint(endpoint)
    for candidate in native_endpoint_candidates or []:
        if _same_endpoint_host(candidate, endpoint):
            return candidate
    return derived


def _is_valid_http_endpoint(value: str) -> tuple[bool, str | None]:
    normalized = value.strip()
    if not normalized:
        return False, "must not be empty"
    if "://" not in normalized:
        normalized = f"http://{normalized}"
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        return False, "must use http:// or https://"
    if not parsed.netloc:
        return False, "must include a hostname"
    if parsed.username or parsed.password:
        return False, "must not embed credentials in the URL"
    return True, None


def _validate_endpoint_option(errors: list[str], path: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"{path} must be a string HTTP endpoint")
        return
    ok, detail = _is_valid_http_endpoint(value)
    if not ok:
        errors.append(f"{path} {detail}")


def _validate_timeout_option(errors: list[str], path: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 900:
        errors.append(f"{path} must be an integer between 1 and 900")


def _validate_planning_limit(errors: list[str], path: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 512:
        errors.append(f"{path} must be an integer >= 512")


def _validate_stop_option(errors: list[str], path: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{path} must be a list of strings")


def _validate_provider_option_types(errors: list[str], provider: str, base_path: str, options: dict[str, Any]) -> None:
    allowed_keys = PROVIDER_OPTION_KEYS.get(provider, set())
    for key, value in options.items():
        path = f"{base_path}.{key}"
        if provider == "ollama" and key in UNSUPPORTED_OLLAMA_OPTION_KEYS:
            errors.append(f"{path} is not supported yet; remove it from config")
            continue
        if key in {"endpoint", "native_endpoint"}:
            _validate_endpoint_option(errors, path, value)
            continue
        if key == "timeout":
            _validate_timeout_option(errors, path, value)
            continue
        if key == "planning_context_limit_tokens":
            _validate_planning_limit(errors, path, value)
            continue
        if key == "stop":
            _validate_stop_option(errors, path, value)
            continue
        if key in BOOLEAN_OPTION_KEYS:
            if value is not None and not isinstance(value, bool):
                errors.append(f"{path} must be a boolean")
            continue
        if key in NUMERIC_OPTION_KEYS:
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                errors.append(f"{path} must be numeric")
            continue
        if key in allowed_keys:
            if value is not None and key in {"keep_alive", "reasoning_effort", "api_key"} and not isinstance(value, str):
                errors.append(f"{path} must be a string")


def validate_provider_config(config: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(config, dict):
        return errors

    providers_cfg = config.get("providers", {}) or {}
    for provider in ("llamacpp", "ollama"):
        provider_cfg = providers_cfg.get(provider, {}) or {}
        if not isinstance(provider_cfg, dict):
            errors.append(f"providers.{provider} must be an object")
            continue
        _validate_provider_option_types(errors, provider, f"providers.{provider}", provider_cfg)
        if provider == "ollama":
            if provider_cfg.get("native_endpoint") and provider_cfg.get("endpoint"):
                if not _same_endpoint_host(
                    normalize_ollama_native_endpoint(provider_cfg.get("native_endpoint")),
                    normalize_ollama_endpoint(provider_cfg.get("endpoint")),
                ):
                    errors.append("providers.ollama.native_endpoint must point at the same host as providers.ollama.endpoint")
            if provider_cfg.get("use_native_metadata") and provider_cfg.get("use_native_discovery") is False:
                errors.append("providers.ollama.use_native_metadata requires providers.ollama.use_native_discovery=true")

    for agent_name, agent_cfg in (config.get("agents", {}) or {}).items():
        if not isinstance(agent_cfg, dict):
            continue
        provider = str(agent_cfg.get("provider", "")).lower()
        if provider not in PROVIDER_OPTION_KEYS:
            continue
        _validate_provider_option_types(errors, provider, f"agents.{agent_name}", agent_cfg)
        if provider == "ollama":
            if agent_cfg.get("native_endpoint") and agent_cfg.get("endpoint"):
                if not _same_endpoint_host(
                    normalize_ollama_native_endpoint(agent_cfg.get("native_endpoint")),
                    normalize_ollama_endpoint(agent_cfg.get("endpoint")),
                ):
                    errors.append(f"agents.{agent_name}.native_endpoint must point at the same host as agents.{agent_name}.endpoint")
            if agent_cfg.get("use_native_metadata") and agent_cfg.get("use_native_discovery") is False:
                errors.append(f"agents.{agent_name}.use_native_metadata requires agents.{agent_name}.use_native_discovery=true")

    return errors


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


def reorder_endpoint_candidates(
    provider_options: dict[str, Any],
    preferred_endpoint: str | None,
) -> dict[str, Any]:
    """Return provider options with the preferred endpoint moved to the front."""
    if not preferred_endpoint:
        return dict(provider_options or {})
    reordered = dict(provider_options or {})
    endpoint_candidates = list(reordered.get("endpoint_candidates", []) or [])
    if preferred_endpoint in endpoint_candidates:
        endpoint_candidates = [preferred_endpoint] + [item for item in endpoint_candidates if item != preferred_endpoint]
        reordered["endpoint_candidates"] = endpoint_candidates
        reordered["endpoint"] = preferred_endpoint
    if reordered.get("native_endpoint_candidates"):
        native_candidates = list(reordered.get("native_endpoint_candidates", []) or [])
        preferred_native = paired_ollama_native_endpoint(preferred_endpoint, native_candidates)
        if preferred_native and preferred_native in native_candidates:
            reordered["native_endpoint_candidates"] = [preferred_native] + [item for item in native_candidates if item != preferred_native]
            reordered["native_endpoint"] = preferred_native
    return reordered
