#!/usr/bin/env python3
# worqer/inspeqtor.py
import os
import sys
import yaml
from pathlib import Path

# Add local directory to path to import lib_ai
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
except ImportError:
    print("CRITICAL: lib_ai.py not found in worqer/ directory.")
    sys.exit(1)

def get_mode_persona(mode: str) -> str:
    m = mode.lower()
    if m == 'enterprise': return "Critique Focus: Maintainability, Logging, Metrics, Structure."
    if m == 'performance': return "Critique Focus: Speed, O(n) complexity, Memory leaks."
    if m == 'security': return "Critique Focus: OWASP Top 10, Sanitization, Auth."
    if m == 'innovative': return "Critique Focus: Creativity, feature completeness."
    return "Critique Focus: Does it work?"

def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: inspeqtor.py <input_summary_file> <output_reqap_file>")
        sys.exit(1)

    summary_path = Path(sys.argv[1])
    reqap_path = Path(sys.argv[2])
    cycle_num = os.environ.get('CYCLE_NUM', '1')

    # Assume CWD is workspace root
    worqspace_dir = Path(os.getcwd())
    qodeyard_path = worqspace_dir / 'qodeyard'

    print(f"Checking {summary_path.name} (current cyqle summary)", flush=True)
    print(f"Checking cyQle {cycle_num} codebase", flush=True)

    try:
        # [FIXED] Syntax error resolved
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary_content = f.read()
    except FileNotFoundError:
        print(f"CRITICAL: Summary file not found at {summary_path}", flush=True); sys.exit(1)

    try:
        with open('config.yaml', 'r') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('inspeqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o')

    mode = os.environ.get('QONQ_MODE', 'program')
    mode_prompt = get_mode_persona(mode)

    context_str = f"## ConstruQtor's Report\n{summary_content}\n\n## Generated Artifacts\n"
    if qodeyard_path.is_dir():
        for root, _, files in os.walk(qodeyard_path):
            for name in files:
                fpath = os.path.join(root, name)
                rel_path = os.path.relpath(fpath, qodeyard_path)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        context_str += f"\n### File: `{rel_path}`\n```\n{f.read()}\n```\n"
                except: pass

    reviewer_prompt = f"""
You are the 'inspeQtor', a senior code reviewer.
**OPERATIONAL MODE:** {mode.upper()}
{mode_prompt}

**Output Format (Strict Markdown):**
1. **Assessment:** `Success`, `Partial`, or `Failure` (First line).
2. **Summary:** Brief findings.
3. **Suggestions:** Bulleted list of improvements.

**Context:**
{context_str}

**Begin Review:**
"""

    try:
        content = lib_ai.run_ai_completion(ai_provider, ai_model, reviewer_prompt)
        content = content.replace("```markdown", "").replace("```", "").strip()

        os.makedirs(reqap_path.parent, exist_ok=True)
        with open(reqap_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"reQap written to {reqap_path}", flush=True)

    except Exception as e:
        print(f"Inspeqtor Failure: {e}", flush=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
