#!/usr/bin/env python3
# worqer/calqulator.py
import sys
import os
import re
import yaml
from pathlib import Path

# Ensure we can import from the qrane directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from qrane import lib_funqtions as lib
except ImportError:
    print("CRITICAL: Could not import lib_funqtions.py from qrane.", flush=True)
    sys.exit(1)

def load_config():
    """Reads config to find the active provider and model for construqtor."""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        construqtor_cfg = cfg.get('agents', {}).get('construqtor', {})
        provider = construqtor_cfg.get('provider', 'gemini')
        model = construqtor_cfg.get('model', 'gemini-2.5-flash')
        return provider, model
    except:
        return 'gemini', 'gemini-2.5-flash'

def get_directory_token_size(path: Path, model: str) -> int:
    """Calculates total tokens for all files in a directory (recursive)."""
    total_chars = 0
    if not path.exists():
        return 0

    for root, _, files in os.walk(path):
        for file in files:
            try:
                with open(Path(root) / file, 'r', encoding='utf-8', errors='ignore') as f:
                    total_chars += len(f.read())
            except:
                pass

    return lib.estimate_tokens(" " * total_chars, model)

def get_file_token_size(file_path: Path, model: str) -> int:
    """Calculates total tokens for a single file."""
    if not file_path.exists():
        return 0
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return lib.estimate_tokens(f.read(), model)
    except:
        return 0

def run_calqulation(briqs_dir: Path, qodeyard_path: Path, bloq_path: Path):
    """
    Finds all relevant briq files, calculates costs, annotates them,
    and prints a detailed ledger to stdout/logs.
    """
    provider, model = load_config()

    # 1. Base Context Cost
    bloq_tokens = get_directory_token_size(bloq_path, model)
    system_prompt_buffer = 2000
    base_context_tokens = bloq_tokens + system_prompt_buffer

    # --- START LOG TABLE ---
    print(f"\n--- 🧮 CalQulator Audit Report (Provider: {provider}, Model: {model}) ---", flush=True)
    print(f"Base Overhead (Skeletons + Sys): {base_context_tokens:,} tokens", flush=True)
    print("-" * 85, flush=True)
    print(f"{'Briq File':<45} | {'Tokens':<12} | {'Est. Cost':<12}", flush=True)
    print("-" * 85, flush=True)

    # 2. Process Briqs
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briqs_dir.glob(pattern))

    if not briq_files:
        print(f"{'No briqs found for this cycle.':<45} | {'0':<12} | {'$0.00'}", flush=True)
        return

    grand_total_tokens = 0

    for briq_file in briq_files:
        with open(briq_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Calculate Deep Read cost (full files mentioned)
        tokens_for_files = 0
        found_files = re.findall(r'`([^`]+\.[a-z_]+)`', content)
        for fname in set(found_files):
            fpath = qodeyard_path / fname
            if fpath.exists():
                tokens_for_files += get_file_token_size(fpath, model)

        # Total for this briq
        task_instruction_tokens = lib.estimate_tokens(content, model)
        total_briq_tokens = base_context_tokens + tokens_for_files + task_instruction_tokens
        cost = lib.calculate_cost(total_briq_tokens, model, is_input=True)
        grand_total_tokens += total_briq_tokens

        # Annotate File
        header_match = re.match(r"(# .*?)\n", content)
        if header_match:
            header = header_match.group(1)
            # Avoid double tagging if re-running
            if "[Est:" not in header:
                calc_tag = f" [Est: {total_briq_tokens:,} toks | {lib.format_cost(cost)}]"
                annotated_header = header.rstrip() + calc_tag
                annotated_content = content.replace(header, annotated_header, 1)
                with open(briq_file, 'w', encoding='utf-8') as f:
                    f.write(annotated_content)

        # Log Table Row
        print(f"{briq_file.name:<45} | {total_briq_tokens:<12,} | {lib.format_cost(cost):<12}", flush=True)

    # --- END LOG TABLE ---
    total_cost_formatted = lib.format_cost(lib.calculate_cost(grand_total_tokens, model, is_input=True))
    print("-" * 85, flush=True)
    print(f"{'TOTAL CYCLE ESTIMATE':<45} | {grand_total_tokens:<12,} | {total_cost_formatted:<12}", flush=True)
    print("-" * 85 + "\n", flush=True)

def main():
    if len(sys.argv) != 3:
        # Default fallback for testing
        print("Usage: calqulator.py <briq_dir> <dummy>", flush=True)
        sys.exit(1)

    briqs_dir = Path(sys.argv[1])
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    bloq_path = worqspace_root / "bloq.d"

    run_calqulation(briqs_dir, qodeyard_path, bloq_path)

if __name__ == "__main__":
    main()
