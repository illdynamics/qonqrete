#!/usr/bin/env python3
"""Provider/model capability registry for conservative AI budgeting."""

from __future__ import annotations

import fnmatch
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from worqer.lib_provider_config import get_provider_config_block, resolve_agent_provider_options
except ImportError:
    from lib_provider_config import get_provider_config_block, resolve_agent_provider_options


@dataclass(frozen=True)
class ModelCapabilities:
    provider: str
    model_pattern: str
    safe_input_tokens: int
    safe_output_tokens: int
    total_context_window: int | None
    planning_context_limit_tokens: int | None
    chars_per_token: float
    supports_multi_message_history: bool
    supports_chunk_preload: bool
    supports_system_messages: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CAPABILITY = ModelCapabilities(
    provider="default",
    model_pattern="*",
    safe_input_tokens=12000,
    safe_output_tokens=2000,
    total_context_window=16000,
    planning_context_limit_tokens=16000,
    chars_per_token=4.0,
    supports_multi_message_history=True,
    supports_chunk_preload=False,
    supports_system_messages=True,
)


CAPABILITY_TABLE: tuple[ModelCapabilities, ...] = (
    ModelCapabilities("openai", "gpt-4.1*", 90000, 8000, 128000, 128000, 4.0, True, True, True),
    ModelCapabilities("openai", "gpt-4o*", 90000, 8000, 128000, 128000, 4.0, True, True, True),
    ModelCapabilities("gemini", "gemini-2.5-pro*", 120000, 8192, 128000, 128000, 4.0, True, True, True),
    ModelCapabilities("gemini", "gemini-2.5-flash*", 80000, 8192, 100000, 100000, 4.0, True, True, True),
    ModelCapabilities("gemini", "gemini-2.0-flash*", 50000, 4096, 64000, 64000, 4.0, True, True, True),
    ModelCapabilities("anthropic", "claude-sonnet-4*", 100000, 8192, 128000, 128000, 3.5, True, True, True),
    ModelCapabilities("anthropic", "claude-3-5-sonnet*", 80000, 8192, 100000, 100000, 3.5, True, True, True),
    ModelCapabilities("anthropic", "claude-opus-4*", 100000, 8192, 128000, 128000, 3.5, True, True, True),
    ModelCapabilities("deepseek", "deepseek-reasoner*", 32000, 8192, 48000, 48000, 4.0, True, True, True),
    ModelCapabilities("deepseek", "deepseek-chat*", 32000, 8192, 48000, 48000, 4.0, True, True, True),
    ModelCapabilities("deepseek", "deepseek-coder*", 32000, 8192, 48000, 48000, 4.0, True, True, True),
    ModelCapabilities("qwen", "qwen*", 32000, 4096, 48000, 48000, 4.0, True, True, True),
    ModelCapabilities("openrouter", "*", 32000, 4096, 48000, 48000, 4.0, True, True, True),
    ModelCapabilities("llamacpp", "*", 24000, 4096, 32768, 32768, 4.0, True, True, True),
    ModelCapabilities("ollama", "*", 24000, 4096, 32768, 32768, 4.0, True, True, True),
)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _config_path_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    project_root = here.parent.parent
    return [
        project_root / "worqspace" / "config.yaml",
        Path.cwd() / "worqspace" / "config.yaml",
    ]


def load_runtime_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    for path in _config_path_candidates():
        if path.exists():
            try:
                return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
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
    return ModelCapabilities(provider_l, model or "*", **{
        key: value for key, value in DEFAULT_CAPABILITY.to_dict().items()
        if key not in {"provider", "model_pattern"}
    })


def _apply_override(cap: ModelCapabilities, override: dict[str, Any]) -> ModelCapabilities:
    if not override:
        return cap
    payload = cap.to_dict()
    payload.update({key: value for key, value in override.items() if key in payload and value is not None})
    if payload.get("planning_context_limit_tokens") is None and payload.get("total_context_window") is not None:
        payload["planning_context_limit_tokens"] = payload["total_context_window"]
    if payload.get("total_context_window") is None and payload.get("planning_context_limit_tokens") is not None:
        payload["total_context_window"] = payload["planning_context_limit_tokens"]
    return ModelCapabilities(**payload)


def resolve_model_capabilities(
    provider: str,
    model: str,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
    agent_config: dict[str, Any] | None = None,
) -> ModelCapabilities:
    runtime_config = load_runtime_config(config)
    cap = _lookup_base_capabilities(provider, model)

    ai_budget = runtime_config.get("ai_budgeting", {})
    provider_overrides = ai_budget.get("providers", {}).get((provider or "").lower(), {})
    if provider_overrides:
        cap = _apply_override(cap, provider_overrides.get("defaults", {}))
        for pattern, override in provider_overrides.get("models", {}).items():
            if fnmatch.fnmatch((model or "").lower(), pattern.lower()):
                cap = _apply_override(cap, override)

    provider_config_block = get_provider_config_block(runtime_config, provider)
    cap = _apply_override(cap, {
        "planning_context_limit_tokens": provider_config_block.get("planning_context_limit_tokens"),
        "safe_output_tokens": provider_config_block.get("max_tokens"),
    })

    resolved_agent_cfg = dict(agent_config or {})
    if agent_name and not resolved_agent_cfg:
        resolved_agent_cfg = dict(runtime_config.get("agents", {}).get(agent_name, {}) or {})
    cap = _apply_override(cap, {
        "planning_context_limit_tokens": resolved_agent_cfg.get("planning_context_limit_tokens"),
        "safe_output_tokens": resolved_agent_cfg.get("max_tokens"),
    })

    provider_options = resolve_agent_provider_options(runtime_config, agent_name=agent_name, provider=provider, agent_config=resolved_agent_cfg)
    cap = _apply_override(cap, {
        "planning_context_limit_tokens": provider_options.get("planning_context_limit_tokens"),
        "safe_output_tokens": provider_options.get("max_tokens"),
    })
    return cap


def chars_per_token_for_model(
    model: str,
    provider: str | None = None,
    config: dict[str, Any] | None = None,
    agent_name: str | None = None,
) -> float:
    cap = resolve_model_capabilities(provider or "default", model, config=config, agent_name=agent_name)
    return cap.chars_per_token
