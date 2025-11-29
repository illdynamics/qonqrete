#!/usr/bin/env python3
# worqer/inspeqtor.py
import os
import sys
import yaml
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError: sys.exit(1)

def main() -> None:
    if len(sys.argv) != 3: sys.exit(1)

    summary_path = Path(sys.argv[1])
    reqap_path = Path(sys.argv[2])
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    qodeyard_path = Path(os.getcwd()) / 'qodeyard'

    print(f"Checking cyQle {cycle_num} codebase", flush=True)

    try:
        with open(summary_path, 'r', encoding='utf-8') as f: summary_content = f.read()
    except: summary_content = "Summary not found."

    try:
        with open('config.yaml', 'r') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('inspeqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o')

    # Gather Code Context (Safe Limit)
    context_str = f"## ConstruQtor's Report\n{summary_content}\n\n## Artifacts\n"
    total_chars = 0
    MAX_CHARS = 300000 # ~75k tokens, safe for GPT-4o

    if qodeyard_path.is_dir():
        for root, _, files in os.walk(qodeyard_path):
            for name in files:
                if total_chars > MAX_CHARS: break
                fpath = os.path.join(root, name)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        context_str += f"\n### File: `{name}`\n```\n{content}\n```\n"
                        total_chars += len(content)
                except: pass

    reviewer_prompt = f"""
You are the 'inspeQtor'.
**TASK:** Review the generated code.
**OUTPUT:** Strict Markdown reQap.

**Context:**
{context_str[:MAX_CHARS]}

**Assessment:**
"""

    try:
        # [FIX] This will now use stdin via lib_ai, avoiding Argument list too long
        content = lib_ai.run_ai_completion(ai_provider, ai_model, reviewer_prompt)

        os.makedirs(reqap_path.parent, exist_ok=True)
        with open(reqap_path, 'w', encoding='utf-8') as f: f.write(content)
        print(f"reQap written to {reqap_path}", flush=True)

    except Exception as e:
        print(f"Inspeqtor Failure: {e}", flush=True)
        # Create a fallback reqap so the cycle doesn't crash hard
        with open(reqap_path, 'w') as f: f.write(f"Assessment: Partial\nError: {e}")

if __name__ == '__main__':
    main()
