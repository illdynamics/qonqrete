#!/usr/bin/env python3
# worqer/inspeqtor.py
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError: sys.exit(1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Inspeqtor Agent")
    parser.add_argument("input_file", help="Path to the input summary file.")
    parser.add_argument("output_file", help="Path to save the output reQap file.")
    parser.add_argument("--provider", required=True, help="AI provider to use.")
    parser.add_argument("--model", required=True, help="AI model to use.")
    args = parser.parse_args()

    summary_path = Path(args.input_file)
    reqap_path = Path(args.output_file)
    ai_provider = args.provider
    ai_model = args.model

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    qodeyard_path = Path(os.getcwd()) / 'qodeyard'

    print(f"Checking cyQle {cycle_num} codebase", flush=True)

    try:
        with open(summary_path, 'r', encoding='utf-8') as f: summary_content = f.read()
    except FileNotFoundError:
        summary_content = f"Summary file not found at: {summary_path}"
    except Exception as e:
        summary_content = f"Could not read summary file: {e}"

    # Gather Code Context (Safe Limit)
    context_str = f"## ConstruQtor's Report\n{summary_content}\n\n## Artifacts\n"
    total_chars = 0
    MAX_CHARS = 300000 # ~75k tokens, safe for GPT-4o

    if qodeyard_path.is_dir():
        for root, _, files in os.walk(qodeyard_path):
            if total_chars > MAX_CHARS: break
            for name in files:
                if total_chars > MAX_CHARS: break
                fpath = os.path.join(root, name)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        context_str += f"\n### File: `{name}`\n```\n{content}\n```\n"
                        total_chars += len(content)
                except Exception as e:
                    context_str += f"\n### File: `{name}`\n```\n[Could not read file: {e}]\n```\n"


    reviewer_prompt = f"""
You are the 'inspeQtor'.
**TASK:** Review the generated code.
**OUTPUT:** Strict Markdown reQap.
1. Assessment: Success/Partial/Failure
2. Summary
3. Suggestions

**Context:**
{context_str[:MAX_CHARS]}

**Begin Review:**
"""

    try:
        content = lib_ai.run_ai_completion(ai_provider, ai_model, reviewer_prompt)

        os.makedirs(reqap_path.parent, exist_ok=True)
        with open(reqap_path, 'w', encoding='utf-8') as f: f.write(content)
        print(f"reQap written to {reqap_path}", flush=True)

    except Exception as e:
        sys.stderr.write(f"CRITICAL: Inspeqtor AI call failed: {e}\n")
        # Do not create a fallback, let the orchestrator know we failed.
        sys.exit(1)

if __name__ == '__main__':
    main()
