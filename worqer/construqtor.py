#!/usr/bin/env python3
# worqer/construqtor.py
import sys
import os
import yaml
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError: print("CRITICAL: lib_ai.py not found."); sys.exit(1)

def get_mode_persona(mode: str) -> str:
    m = mode.lower()
    if m == 'enterprise': return "Code Style: Enterprise. Add logging, error handling, docstrings, and modular structure."
    if m == 'security': return "Code Style: Security. Validate inputs, sanitize data."
    return "Code Style: Functional."

def main():
    if len(sys.argv) < 3: print("Usage: construqtor.py <input> <output>"); sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    qodeyard_path.mkdir(parents=True, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro')

    mode = os.environ.get('QONQ_MODE', 'enterprise')
    mode_prompt = get_mode_persona(mode)

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briqs found.", flush=True); sys.exit(1)

    all_briqs_summary = []
    failure_count = 0

    print(f"--- Construqtor Found {len(briq_files)} Briqs ---", flush=True)

    context_dirs = [str(qodeyard_path.resolve())]

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --", flush=True)
        with open(briq_file, 'r', encoding='utf-8') as f: briq_content = f.read()

        prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan.
**RESTRICTION:** GENERATE CODE ONLY.
**OUTPUT:** Return the code files inside markdown blocks.

**MODE:** {mode.upper()}
{mode_prompt}

**Plan:**
{briq_content}
"""
        success = False
        result = ""
        try:
            result = lib_ai.run_ai_completion(ai_provider, ai_model, prompt, context_files=context_dirs)
            success = True
        except Exception as e:
            # [FIX] If we got a partial result or pipe error, check if code was generated anyway
            print(f"     [WARN] AI Pipe Signal: {e}", flush=True)
            if "```" in str(e) or (result and "```" in result):
                success = True
            else:
                success = False

        # [FIX] Robust check: Did we actually get code?
        if "```" in result:
             success = True

        status = "success" if success else "failure"
        if not success: failure_count += 1

        all_briqs_summary.append({ 'briq_file': briq_file.name, 'status': status })
        print(f"-- Executed Briq: {briq_file.name} (Status: {status}) --", flush=True)

    final_status = "Success" if failure_count == 0 else ("Partial" if failure_count < len(briq_files) else "Failure")

    summary_content = f"# Execution Summary\n\n**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(briq_files)} | **Failures:** {failure_count}\n\n"
    for item in all_briqs_summary:
        summary_content += f"- **{item['briq_file']}**: {item['status']}\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f: f.write(summary_content)

if __name__ == "__main__": main()
