#!/usr/bin/env python3
# worqer/inspeqtor.py
import os
import sys
import yaml
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError: sys.exit(1)

def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: inspeqtor.py <summary_path> <changed_files_path> <reqap_output_path>", flush=True)
        sys.exit(1)

    summary_path = Path(sys.argv[1])
    changed_files_path = Path(sys.argv[2])
    reqap_path = Path(sys.argv[3])
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    qontext_path = worqspace_root / "qontext.d"

    print(f"Checking cyQle {cycle_num} codebase", flush=True)

    try:
        with open(summary_path, 'r', encoding='utf-8') as f: summary_content = f.read()
    except Exception as e:
        summary_content = f"Summary not found or could not be read: {e}"

    try:
        with open(changed_files_path, 'r', encoding='utf-8') as f: changed_files_content = f.read()
    except Exception as e:
        changed_files_content = f"Changed files summary not found or could not be read: {e}"

    try:
        with open('config.yaml', 'r') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('inspeqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o')

    # --- Step 1: Gather all architectural context ---
    all_qontext_files = []
    if qontext_path.is_dir():
        for root, _, files in os.walk(qontext_path):
            for file in files:
                if file.endswith('.q.yaml'):
                    all_qontext_files.append(str(Path(root) / file))
    
    # --- Step 2: Get the new code for changed files from the dedicated summary ---
    changed_code_context = ""
    # The changed_files_content IS the list of changed files
    changed_files = re.findall(r'`([^`]+)`', changed_files_content)
    
    if changed_files:
        changed_code_context += "\n## Changed Code Artifacts (for review)\n"
        for file_str in set(changed_files):
            file_path = qodeyard_path / file_str
            if file_path.is_file():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    changed_code_context += f"\n### File: `{file_str}`\n```\n{content}\n```\n"
                except Exception as e:
                    changed_code_context += f"\n### File: `{file_str}`\nCould not read file: {e}\n"
            else:
                changed_code_context += f"\n### File: `{file_str}`\nFile not found in qodeyard.\n"
    else:
        changed_code_context = "\n_No changed code artifacts were listed for review._\n"

    # --- Step 3: Build the final prompt ---
    reviewer_prompt = f"""
You are the 'inspeQtor', a senior software quality engineer performing a code review.

**YOUR TASK:**
Your goal is to determine if the recent code changes are complete, correct, and consistent with the existing project architecture. You will be given three sources of information:
1.  **The ConstruQtor's Report:** A summary of the work that was supposed to be done.
2.  **The Architectural Context:** A series of YAML files (`.q.yaml`) describing the entire codebase *before* the changes were made.
3.  **The Changed Code:** The actual source code of the files that were modified in this cycle.

**REVIEW CRITERIA (Your thought process):**
1.  **Correctness:** Does the new code seem logically correct and free of obvious bugs?
2.  **Completeness:** Did the `construQtor` fully implement the tasks described in its report?
3.  **Consistency:** This is the most important part. Compare the new code against the architectural context. Did the changes introduce any inconsistencies? For example, if a function signature was changed, were all calls to it in other files (which you can find in the architectural context) also updated? If not, that is a FAILURE.

**OUTPUT FORMAT (Strict Markdown):**
1.  **Assessment:** Must be one of: [SUCCESS], [PARTIAL], or [FAILURE].
    - `[SUCCESS]` means the changes are correct, complete, and fully consistent.
    - `[PARTIAL]` means the changes are mostly correct but have minor issues or missed a small part of the task.
    - `[FAILURE]` means the code is incorrect, incomplete, or, most importantly, creates inconsistencies with the rest of the codebase.
2.  **Summary:** A brief (2-3 sentences) summary of your assessment. Justify your decision by referencing the code and the context.
3.  **Suggestions:** A bulleted list of specific, actionable suggestions for the next cycle. If the assessment is a FAILURE, these suggestions must explain what needs to be fixed.

**INPUTS FOR YOUR REVIEW:**

## 1. ConstruQtor's Report
{summary_content}

## 2. Changed Code Artifacts
{changed_code_context}

---
*The full architectural context (`.q.yaml` files) has been provided in the background.*
---

**Begin Review:**
"""

    try:
        content = lib_ai.run_ai_completion(ai_provider, ai_model, reviewer_prompt, context_files=all_qontext_files)

        os.makedirs(reqap_path.parent, exist_ok=True)
        with open(reqap_path, 'w', encoding='utf-8') as f: f.write(content)
        print(f"reQap written to {reqap_path}", flush=True)
    except Exception as e:
        print(f"Inspeqtor Failure: {e}", flush=True)
        # Create a fallback reqap so the cycle doesn't crash hard
        with open(reqap_path, 'w', encoding='utf-8') as f:
            f.write(f"Assessment: [FAILURE]\n\n**Summary**\n\nThe Inspeqtor agent failed to execute due to a critical error: {e}\n\n**Suggestions**\n- Check the console logs for the `inspeqtor` agent to diagnose the root cause.")

if __name__ == '__main__':
    main()
