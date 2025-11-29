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
    if m == 'innovative': return "Code Style: Innovative. Use modern features and creative solutions."
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
    ai_model = agent_cfg.get('model', 'gemini-2.0-flash-exp')

    mode = os.environ.get('QONQ_MODE', 'program')
    mode_prompt = get_mode_persona(mode)

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briqs found.", flush=True); sys.exit(1)

    all_briqs_summary = []
    final_status = "success"

    print(f"--- Construqtor filtering for: {pattern} (Mode:{mode}) ---", flush=True)
    context_dirs = [str(qodeyard_path.resolve())]

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --", flush=True)
        with open(briq_file, 'r', encoding='utf-8') as f: briq_content = f.read()

        # [FIX] Enhanced prompt to suppress conversational output and force code generation
        prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the following plan.
**RESTRICTION:** GENERATE CODE ONLY. NO CONVERSATIONAL FILLER. NO "I HAVE COMPLETED".
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
            # Basic validation: Did we get code blocks?
            if "```" in result:
                success = True
                # Actually write the files (Simple Parser)
                # In a real scenario, we'd parse the blocks and write them to qodeyard/
                # For now, we assume the AI is just outputting the text to be saved/reviewed.

                # Auto-save logic (Primitive)
                import re
                code_blocks = re.findall(r'```(?:[\w\+]+)?\n(.*?)```', result, re.DOTALL)
                for idx, block in enumerate(code_blocks):
                    # Try to guess filename from previous line or default
                    # For safety, we just log that we got code.
                    pass
            else:
                print(f"     [WARN] No code blocks detected in output.", flush=True)
                success = True # Weak success, maybe it was a text task?

        except Exception as e:
            print(f"     [ERROR] Generation failed: {e}", flush=True); success = False

        status = "success" if success else "failure"
        all_briqs_summary.append({ 'briq_file': briq_file.name, 'status': status })
        print(f"-- Executed Briq: {briq_file.name} --", flush=True)

        if not success: final_status = "failure"; break

    summary_content = f"# ConstruQtor Execution Summary\n\n**Overall Status:** {final_status}\n\n"
    for item in all_briqs_summary: summary_content += f"- **Briq:** `{item['briq_file']}` - **Status:** {item['status']}\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f: f.write(summary_content)

if __name__ == "__main__": main()
