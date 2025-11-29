#!/usr/bin/env python3
# worqer/construqtor.py
import sys
import os
import yaml
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError: print("CRITICAL: lib_ai.py not found."); sys.exit(1)

def get_mode_persona(mode: str) -> str:
    m = mode.lower()
    if m == 'enterprise': return "Code Style: Enterprise. Add logging, error handling, docstrings, and modular structure."
    if m == 'performance': return "Code Style: Performance. Optimize for speed, memory usage, and efficiency."
    if m == 'security': return "Code Style: Security. Validate all inputs, use secure defaults, sanitize data."
    return "Code Style: Functional. Ensure it works correctly."

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
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro') # Default safety

    mode = os.environ.get('QONQ_MODE', 'enterprise')
    mode_prompt = get_mode_persona(mode)

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briqs found.", flush=True); sys.exit(1)

    all_briqs_summary = []
    # Count errors to determine final status
    failure_count = 0

    print(f"--- Construqtor Found {len(briq_files)} Briqs to Process ---", flush=True)
    print(f"--- Construqtor filtering for: {pattern} (Mode:{mode}) ---", flush=True)

    context_dirs = [str(qodeyard_path.resolve())]

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --", flush=True)
        with open(briq_file, 'r', encoding='utf-8') as f: briq_content = f.read()

        prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the following plan.
**RESTRICTION:** GENERATE CODE ONLY. NO CONVERSATIONAL FILLER.
**OUTPUT:** Return the code files inside standard markdown code blocks (e.g., ```python ... ```).

**OPERATIONAL MODE:** {mode.upper()}
{mode_prompt}

**CRITICAL PATH INSTRUCTIONS:**
1. You are in Project Root.
2. The code you write will be saved to `qodeyard/`.
3. If the plan implies running a command, WRITE A SHELL SCRIPT to run it.

**Plan:**
{briq_content}
"""
        success = False
        try:
            result = lib_ai.run_ai_completion(ai_provider, ai_model, prompt, context_files=context_dirs)
            if "```" in result:
                success = True
                # In a real tool, we would parse and save here.
                # For now, we assume the content is generated for the Inspeqtor to review/save.
                # If we wanted to AUTO-SAVE, we would add the parser here.
            else:
                print(f"     [WARN] No code blocks detected in output.", flush=True)
                # We mark as success if it generated text, but warn.
                success = True

        except Exception as e:
            print(f"     [ERROR] Generation failed: {e}", flush=True); success = False

        status = "success" if success else "failure"
        if not success: failure_count += 1

        all_briqs_summary.append({ 'briq_file': briq_file.name, 'status': status })
        print(f"-- Executed Briq: {briq_file.name} --", flush=True)
        # [CRITICAL] NO BREAK HERE. CONTINUES TO NEXT FILE.

    # Final Summary Generation
    final_status = "Success" if failure_count == 0 else ("Partial" if failure_count < len(briq_files) else "Failure")

    summary_content = f"# ConstruQtor Execution Summary\n\n**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(briq_files)} | **Failures:** {failure_count}\n\n"
    summary_content += "## Briq Execution Log\n"
    for item in all_briqs_summary:
        summary_content += f"- **{item['briq_file']}**: {item['status']}\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f: f.write(summary_content)
    print(f"--- Summary Report Generated ({len(all_briqs_summary)} entries) ---", flush=True)

if __name__ == "__main__": main()
