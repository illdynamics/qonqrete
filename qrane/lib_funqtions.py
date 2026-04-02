# qrane/lib_funqtions.py
"""
Shared utility functions for Qonqrete (Math, Tokens, Formatting).
"""
import os
import math

# --- Token Constants ---
# Costs are per 1M tokens (Input / Output) as of late 2025 estimates
PRICING = {
    # Gemini - RECOMMENDED FOR COST EFFICIENCY
    "gemini-2.5-flash-lite": {"input": 0.10,  "output": 0.40, "char_per_token": 4.0},  # CHEAPEST
    "gemini-2.5-flash":      {"input": 0.30,  "output": 2.50, "char_per_token": 4.0},
    "gemini-2.5-pro":        {"input": 1.25,  "output": 10.00, "char_per_token": 4.0},
    "gemini-2.0-flash":      {"input": 0.10,  "output": 0.40, "char_per_token": 4.0},
    "gemini-1.5-pro":        {"input": 3.50,  "output": 10.50, "char_per_token": 4.0},
    # OpenAI GPT-4.1 series
    "gpt-4.1":               {"input": 2.00,  "output": 8.00,  "char_per_token": 4.0},
    "gpt-4.1-mini":          {"input": 0.40,  "output": 1.60,  "char_per_token": 4.0},
    "gpt-4.1-nano":          {"input": 0.10,  "output": 0.40,  "char_per_token": 4.0},
    # OpenAI GPT-4o series
    "gpt-4o":                {"input": 2.50,  "output": 10.00, "char_per_token": 4.0},
    "gpt-4o-mini":           {"input": 0.15,  "output": 0.60,  "char_per_token": 4.0},
    # Claude
    "claude-3-5-sonnet":     {"input": 3.00,  "output": 15.00, "char_per_token": 3.5},
    "claude-sonnet-4":       {"input": 3.00,  "output": 15.00, "char_per_token": 3.5},
    "claude-opus-4":         {"input": 15.00, "output": 75.00, "char_per_token": 3.5},
    # DeepSeek - VERY CHEAP
    "deepseek-chat":         {"input": 0.14,  "output": 0.28,  "char_per_token": 4.0},
    "deepseek-coder":        {"input": 0.14,  "output": 0.28,  "char_per_token": 4.0},
}

ZERO_COST_PROVIDERS = {"llamacpp", "local"}


def _looks_like_local_model(model: str | None) -> bool:
    if not model:
        return False
    value = str(model).strip().lower()
    return value.endswith('.gguf') or '/.gguf' in value or '.gguf/' in value


def is_zero_cost(provider: str | None = None, model: str | None = None) -> bool:
    provider_lc = (provider or '').strip().lower()
    return provider_lc in ZERO_COST_PROVIDERS or _looks_like_local_model(model)


def estimate_tokens(text: str, model: str = "gemini-2.5-flash-lite") -> int:
    """
    Returns an estimated token count based on character length.
    Fast, local, and accurate enough for estimations.
    """
    if not text:
        return 0
    
    # Get model specifics or default to average (4 chars/token)
    specs = PRICING.get(model, {"char_per_token": 4.0})
    ratio = specs["char_per_token"]
    
    return math.ceil(len(text) / ratio)

def calculate_cost(tokens: int, model: str = "gemini-2.5-flash-lite", is_input: bool = True, provider: str | None = None) -> float:
    """Calculates USD cost for a given token count."""
    if is_zero_cost(provider, model):
        return 0.0
    specs = PRICING.get(model, PRICING["gemini-2.5-flash-lite"])
    price_per_million = specs["input"] if is_input else specs["output"]
    return (tokens / 1_000_000) * price_per_million

def estimate_call_cost(input_text: str, estimated_output_tokens: int, model: str, provider: str | None = None) -> tuple[float, int, int]:
    """
    Estimate cost for an AI call.
    
    Returns:
        (total_cost, input_tokens, output_tokens)
    """
    input_tokens = estimate_tokens(input_text, model)
    input_cost = calculate_cost(input_tokens, model, is_input=True, provider=provider)
    output_cost = calculate_cost(estimated_output_tokens, model, is_input=False, provider=provider)
    return (input_cost + output_cost, input_tokens, estimated_output_tokens)

def format_cost(cost: float) -> str:
    """Formats tiny costs readably (e.g., $0.0004)"""
    if cost < 0.01:
        return f"${cost:.5f}"
    return f"${cost:.2f}"
