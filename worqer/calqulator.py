#!/usr/bin/env python3
# worqer/calqulator.py
import math
import os
import re
import sys
from pathlib import Path

import yaml

try:
    import lib_ai  # type: ignore
except Exception:  # pragma: no cover - runtime fallback path
    lib_ai = None

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-2.5-flash-lite"

# INTERNAL PRICING & LOGIC (Formerly lib_funqtions.py)
PRICING = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40, "ratio": 4.0},
    "gemini-2.5-flash":      {"input": 0.30, "output": 2.50, "ratio": 4.0},
    "deepseek-v4-flash":          {"input": 0.20, "output": 0.60, "ratio": 4.0},
    "deepseek-v4-flash-thinking": {"input": 0.20, "output": 0.60, "ratio": 4.0},
    "deepseek-v4-pro":            {"input": 0.80, "output": 2.40, "ratio": 4.0},
    "deepseek-v4-pro-thinking":   {"input": 0.80, "output": 2.40, "ratio": 4.0},
    # Legacy
    "deepseek-chat":         {"input": 0.14, "output": 0.28, "ratio": 4.0},
}

def estimate_tokens(text: str, model: str) -> int:
    ratio = PRICING.get(model, PRICING["gemini-2.5-flash-lite"])["ratio"]
    return math.ceil(len(text or "") / ratio)

def calculate_cost(tokens: int, model: str, is_input: bool = True) -> float:
    specs = PRICING.get(model, PRICING["gemini-2.5-flash-lite"])
    rate = specs["input"] if is_input else specs["output"]
    return (tokens / 1_000_000) * rate

def format_cost(cost: float) -> str:
    return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"

def _manual_agent_ai_params(config: dict, agent_name: str, default_provider: str, default_model: str) -> tuple[str, str]:
    agents = config.get("agents", {}) if isinstance(config, dict) else {}
    agent_cfg = agents.get(agent_name, {}) if isinstance(agents, dict) else {}
    provider = str(agent_cfg.get("provider", default_provider) or default_provider).strip()
    model = str(agent_cfg.get("model", default_model) or default_model).strip()
    return provider, model

def _get_agent_ai_params(config: dict, agent_name: str, default_provider: str, default_model: str) -> tuple[str, str]:
    if lib_ai is not None and hasattr(lib_ai, "get_agent_ai_params"):
        try:
            return lib_ai.get_agent_ai_params(config, agent_name, default_provider, default_model)
        except Exception:
            pass
    return _manual_agent_ai_params(config, agent_name, default_provider, default_model)

def resolve_calqulator_target(config: dict | None) -> tuple[str, str]:
    cfg = config if isinstance(config, dict) else {}
    provider, model = _get_agent_ai_params(cfg, "calqulator", DEFAULT_PROVIDER, DEFAULT_MODEL)
    provider = str(provider or "").strip().lower()
    model = str(model or "").strip()

    # Backward compatibility: legacy configs used a local placeholder pair
    # (`provider: local`, `model: calqulator`). In that case, preserve the
    # previous "audit construqtor settings" behavior.
    if provider in {"", "local"} or model.lower() in {"", "calqulator"}:
        provider, model = _get_agent_ai_params(cfg, "construqtor", DEFAULT_PROVIDER, DEFAULT_MODEL)
        provider = str(provider or "").strip().lower()
        model = str(model or "").strip()

    if not provider:
        provider = DEFAULT_PROVIDER
    if not model:
        model = DEFAULT_MODEL
    return provider, model

def run_calqulation(briqs_dir: Path, qodeyard_path: Path):
    del qodeyard_path  # Kept in signature for API stability.

    cfg = {}
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}
    provider, model = resolve_calqulator_target(cfg)

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    briq_files = sorted(briqs_dir.glob(f"cyqle{cycle_num}_*.md"))
    print(f"--- Audit Report ({provider}/{model}) ---", flush=True)

    for briq_file in briq_files:
        content = briq_file.read_text(encoding='utf-8')
        tokens = estimate_tokens(content, model)
        cost = calculate_cost(tokens, model)

        # Annotate header if missing
        header_match = re.match(r"(# .*?)\n", content)
        if header_match and "[Est:" not in header_match.group(1):
            tag = f" [Est: {tokens:,} toks | {format_cost(cost)}]"
            briq_file.write_text(content.replace(header_match.group(1), header_match.group(1).rstrip() + tag, 1))

        print(f"{briq_file.name:<20} | {tokens:<8,} | {format_cost(cost)}", flush=True)

if __name__ == "__main__":
    run_calqulation(Path(sys.argv[1]), Path(os.getcwd()) / "qodeyard")
