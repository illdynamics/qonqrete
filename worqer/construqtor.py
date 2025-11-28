#!/usr/bin/env python3
# worqer/construqtor.py
import sys
import os
import yaml
from pathlib import Path

# Add local directory to path to import lib_ai
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
except ImportError:
    print("CRITICAL: lib_ai.py not found in worqer/ directory.")
    sys.exit(1)

def main():
    if len(sys.argv) < 3:
        print("Usage: construqtor.py <input_briq_dir> <output_summary_file>")
        sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    worqspace_root = briq_dir.parent
    qodeyard_path = worqspace_root / "qodeyard"
    qodeyard_path.mkdir(parents=True, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except FileNotFoundError: config = {}

    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-2.0-flash-exp')

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briq files found matching {pattern}")
        sys.exit(1)

    all_briqs_summary = []
    final_status = "success"

    print(f"--- Construqtor filtering for: {pattern} using {ai_provider}/{ai_model} ---")

    context_dirs = [str(qodeyard_path.resolve())]

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --")

        with open(briq_file, 'r', encoding='utf-8') as f:
            briq_content = f.read()

        prompt = f"""You are the 'construQtor'. Execute this plan.

**CRITICAL PATH INSTRUCTIONS:**
1. You are in Project Root.
2. WRITE ALL CODE to `qodeyard/`.
3. Do NOT write to `./`.

**Plan:**
{briq_content}
"""
        success = False
        try:
            result = lib_ai.run_ai_completion(ai_provider, ai_model, prompt, context_files=context_dirs)
            if result:
                success = True
            else:
                success = False
        except Exception as e:
            print(f"     [ERROR] Execution failed: {e}")
            success = False

        status = "success" if success else "failure"
        all_briqs_summary.append({ 'briq_file': briq_file.name, 'status': status })
        print(f"-- Executed Briq: {briq_file.name} --")

        if not success:
            final_status = "failure"
            break

    summary_content = f"# ConstruQtor Execution Summary\n\n**Overall Status:** {final_status}\n\n"
    for item in all_briqs_summary:
        summary_content += f"- **Briq:** `{item['briq_file']}` - **Status:** {item['status']}\n"

    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)

if __name__ == "__main__":
    main()
