# qrane/lib_funqtions.py
"""
Shared utility functions for Qonqrete (Math, Tokens, Formatting).
"""
import os
import math

# --- Token Constants ---
# Costs are per 1M tokens (Input / Output) as of late 2024/2025 estimates
PRICING = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30, "char_per_token": 4.0},
    "gemini-1.5-pro":   {"input": 3.50,  "output": 10.50, "char_per_token": 4.0},
    "gpt-4o":           {"input": 2.50,  "output": 10.00, "char_per_token": 4.0},
    "gpt-4o-mini":      {"input": 0.15,  "output": 0.60,  "char_per_token": 4.0},
    "claude-3-5-sonnet":{"input": 3.00,  "output": 15.00, "char_per_token": 3.5},
    "deepseek-chat":    {"input": 0.14,  "output": 0.28,  "char_per_token": 4.0}, # Example pricing
    "qwen-turbo":       {"input": 0.1,   "output": 0.2,   "char_per_token": 3.8},
}

def estimate_tokens(text: str, model: str = "qwen-turbo") -> int:
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

def calculate_cost(tokens: int, model: str = "qwen-turbo", is_input: bool = True) -> float:
    """Calculates USD cost for a given token count."""
    specs = PRICING.get(model, PRICING["qwen-turbo"])
    price_per_million = specs["input"] if is_input else specs["output"]
    return (tokens / 1_000_000) * price_per_million

def format_cost(cost: float) -> str:
    """Formats tiny costs readably (e.g., $0.0004)"""
    if cost < 0.01:
        return f"${cost:.5f}"
    return f"${cost:.2f}"
