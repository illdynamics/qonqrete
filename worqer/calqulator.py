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
    """Reads config to find the active model for construqtor."""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        return cfg.get('agents', {}).get('construqtor', {}).get('model', 'gemini-2.5-flash')
    except:
        return 'gemini-2.5-flash'

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
    Finds all relevant briq files in a directory, calculates the cost for each,
    and overwrites them with the annotated content.
    """
    model = load_config()
    print(f"--- CalQulator: Estimating costs for model '{model}' ---", flush=True)
    
    # 1. Base Context Cost (System Prompt + Bloq.d Skeletons)
    bloq_tokens = get_directory_token_size(bloq_path, model)
    system_prompt_buffer = 2000 # Estimate for construqtor's system instructions
    base_context_tokens = bloq_tokens + system_prompt_buffer
    
    print(f"  - Base Context (Skeletons + Sys Prompt): {base_context_tokens:,} tokens", flush=True)

    # 2. Find and Process Briq files for the current cycle
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briqs_dir.glob(pattern))

    if not briq_files:
        print(f"  - No briq files found for cycle {cycle_num}. Nothing to calqulate.", flush=True)
        return

    grand_total_tokens = 0
    for briq_file in briq_files:
        with open(briq_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find mentioned files to add their full content cost from qodeyard
        tokens_for_files = 0
        found_files = re.findall(r'`([^`]+\.[a-z_]+)`', content)
        
        # Deduplicate and sum tokens for mentioned files
        for fname in set(found_files):
            fpath = qodeyard_path / fname
            if fpath.exists():
                tokens_for_files += get_file_token_size(fpath, model)
        
        # Total tokens for this specific briq task
        task_instruction_tokens = lib.estimate_tokens(content, model)
        total_briq_tokens = base_context_tokens + tokens_for_files + task_instruction_tokens
        cost = lib.calculate_cost(total_briq_tokens, model, is_input=True)
        grand_total_tokens += total_briq_tokens
        
        # Annotate the briq file
        header_match = re.match(r"(# .*?)\n", content)
        if header_match:
            header = header_match.group(1)
            calc_tag = f" [Est: {total_briq_tokens:,} toks | {lib.format_cost(cost)}]"
            annotated_header = header.rstrip() + calc_tag
            annotated_content = content.replace(header, annotated_header, 1)
            
            with open(briq_file, 'w', encoding='utf-8') as f:
                f.write(annotated_content)
            
            print(f"  - Annotated {briq_file.name}: {total_briq_tokens:,} tokens", flush=True)

    total_cost_formatted = lib.format_cost(lib.calculate_cost(grand_total_tokens, model, is_input=True))
    print(f"--- CalQulator: Total estimated run cost: {total_cost_formatted} ({grand_total_tokens:,} tokens) ---", flush=True)

def main():
    if len(sys.argv) != 3:
        print("Usage: calqulator.py <input_briq_dir> <dummy_output>", flush=True)
        sys.exit(1)
        
    briqs_dir = Path(sys.argv[1])
    
    # Agents run from the worqspace root
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    bloq_path = worqspace_root / "bloq.d"
    
    run_calqulation(briqs_dir, qodeyard_path, bloq_path)

if __name__ == "__main__":
    main()
