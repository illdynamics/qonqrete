#!/usr/bin/env python3
# worqer/calqulator.py
import sys, os, re, yaml, json, math
from pathlib import Path

# INTERNAL PRICING & LOGIC (Formerly lib_funqtions.py)
PRICING = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40, "ratio": 4.0},
    "gemini-2.5-flash":      {"input": 0.30, "output": 2.50, "ratio": 4.0},
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

def run_calqulation(briqs_dir: Path, qodeyard_path: Path):
    try:
        with open('config.yaml', 'r') as f: cfg = yaml.safe_load(f) or {}
        # calqulator usually audits the construqtor's model
        provider, model = lib_ai.get_agent_ai_params(cfg, 'construqtor', 'gemini', 'gemini-2.5-flash-lite')
    except:
        model = 'gemini-2.5-flash-lite'

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    briq_files = sorted(briqs_dir.glob(f"cyqle{cycle_num}_*.md"))
    print(f"--- Audit Report ({model}) ---", flush=True)

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
