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

def load_agent_config(agent_name: str):
    """Reads config to find the active provider and model for a given agent."""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        agent_cfg = cfg.get('agents', {}).get(agent_name, {})
        provider = agent_cfg.get('provider', 'local')
        model = agent_cfg.get('model', 'unknown')
        return provider, model
    except:
        return 'local', 'unknown'

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
    calq_provider, calq_model = load_agent_config('calqulator')
    con_provider, con_model = load_agent_config('construqtor')

    # --- Pre-calculation and Setup ---
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briqs_dir.glob(pattern))

    # Determine dynamic column width for alignment
    max_filename_len = 0
    if briq_files:
        max_filename_len = max(len(f.name) for f in briq_files)
    # Ensure a minimum width for the header
    col_width = max(max_filename_len, len("Briq File")) + 3  # Add padding

    # --- Base Context Cost ---
    bloq_tokens = get_directory_token_size(bloq_path, con_model)
    system_prompt_buffer = 2000
    base_context_tokens = bloq_tokens + system_prompt_buffer

    # --- Print Header ---
    header_line = f"--- CalQulator Audit Report (Provider: {calq_provider}, Model: {calq_model}) ---"
    print(f"\n{header_line}", flush=True)
    print(f"Estimating for ConstruQtor model: {con_model}", flush=True)
    print(f"Base Overhead (Skeletons + Sys): {base_context_tokens:,} tokens", flush=True)
    
    # Dynamic separator line
    separator = "-" * (col_width + 12 + 15 + 4) # col + tokens + cost + separators
    print(separator, flush=True)
    print(f"{'Briq File':<{col_width}} | {'Tokens':<12} | {'Est. Cost':<15}", flush=True)
    print(separator, flush=True)

    if not briq_files:
        print(f"{'No briqs found for this cycle.':<{col_width}} | {'0':<12} | {'$0.00':<15}", flush=True)
        print(separator, flush=True)
        return

    # --- Process Briqs ---
    grand_total_tokens = 0
    for briq_file in briq_files:
        with open(briq_file, 'r', encoding='utf-8') as f:
            content = f.read()

        tokens_for_files = 0
        found_files = re.findall(r'`([^`]+\.[a-z_]+)`', content)
        for fname in set(found_files):
            fpath = qodeyard_path / fname
            if fpath.exists():
                tokens_for_files += get_file_token_size(fpath, con_model)

        task_instruction_tokens = lib.estimate_tokens(content, con_model)
        total_briq_tokens = base_context_tokens + tokens_for_files + task_instruction_tokens
        cost = lib.calculate_cost(total_briq_tokens, con_model, is_input=True)
        grand_total_tokens += total_briq_tokens

        # Annotate File
        header_match = re.match(r"(# .*?)\n", content)
        if header_match:
            header = header_match.group(1)
            if "[Est:" not in header:
                calc_tag = f" [Est: {total_briq_tokens:,} toks | {lib.format_cost(cost)}]"
                annotated_header = header.rstrip() + calc_tag
                annotated_content = content.replace(header, annotated_header, 1)
                with open(briq_file, 'w', encoding='utf-8') as f:
                    f.write(annotated_content)

        # Log Table Row
        print(f"{briq_file.name:<{col_width}} | {total_briq_tokens:<12,} | {lib.format_cost(cost):<15}", flush=True)

    # --- Print Footer ---
    total_cost_formatted = lib.format_cost(lib.calculate_cost(grand_total_tokens, con_model, is_input=True))
    print(separator, flush=True)
    print(f"{'TOTAL CYCLE ESTIMATE':<{col_width}} | {grand_total_tokens:<12,} | {total_cost_formatted:<15}", flush=True)
    print(separator + "\n", flush=True)

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
