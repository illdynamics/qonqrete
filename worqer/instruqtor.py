#!/usr/bin/env python3
# worqer/instruqtor.py
import os
import sys
import yaml
import re
from pathlib import Path

# Add local directory to path to import lib_ai
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

def clean_input_content(text: str) -> str:
    text = text.replace('\u200b', '').replace('\ufeff', '')
    text = text.replace('\xa0', ' ')
    text = re.sub(r'^\s*[●•]\s*', '- ', text, flags=re.MULTILINE)
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    return text

def parse_xml_briqs(content: str) -> list[dict]:
    # 1. Try Strict Match (attributes)
    pattern_strict = re.compile(r'<briq\s+title=["\'](.*?)["\']\s*>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
    matches = pattern_strict.findall(content)

    results = [{'title': m[0].strip(), 'content': m[1].strip()} for m in matches]

    # 2. If Strict failed or returned nothing, try Loose Match (no attributes)
    if not results:
        pattern_loose = re.compile(r'<briq>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
        loose_matches = pattern_loose.findall(content)
        for i, m in enumerate(loose_matches):
            # Generate a title if missing
            results.append({'title': f'Step_{i+1}_Instruction', 'content': m.strip()})

    return results

def clean_filename_slug(text: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9 ]', '', text)
    slug = "_".join(clean.split()[:6]).lower()
    return slug if slug else "task"

# 0-9 Sensitivity Map
def get_sensitivity_rules(level: int) -> str:
    if level >= 9:
        return "SENSITIVITY 9 (MONOLITHIC): Create EXACTLY ONE <briq>. Do NOT split the task. Keep it all together."
    elif level >= 7:
        return "SENSITIVITY 7-8 (COARSE): Split only by MAJOR phases (e.g., Setup, Core Logic, Visualization)."
    elif level >= 5:
        return "SENSITIVITY 5-6 (BALANCED): Create one briq per logical component."
    elif level >= 3:
        return "SENSITIVITY 3-4 (DETAILED): Create a briq for every distinct function or sub-task."
    else:
        return "SENSITIVITY 0-2 (ATOMIC): Maximum granularity. Every requirement gets its own briq."

# Mode Persona Map
def get_mode_persona(mode: str) -> str:
    m = mode.lower()
    if m == 'enterprise': return "Focus: Enterprise-grade reliability, logging, metrics, documentation."
    if m == 'performance': return "Focus: Speed, efficiency, low resource usage, optimization."
    if m == 'security': return "Focus: Input validation, secure defaults, no secrets in code."
    if m == 'innovative': return "Focus: Creative features, modern patterns, 'wow' factor."
    return "Focus: Functional correctness. Make it work."

def main() -> None:
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: python instruqtor.py <input_file> <output_dir>\n"); sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    tasq_num = os.environ.get('TASQ_NUM', '1')

    if not input_file.exists():
        sys.stderr.write(f"CRITICAL: Task file not found: {input_file}\n"); sys.exit(1)

    print(f"--- Instruqtor reading: {input_file.name} ---", flush=True)
    with open(input_file, 'r', encoding='utf-8') as f: task_content = clean_input_content(f.read())

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except FileNotFoundError: config = {}

    agent_cfg = config.get('agents', {}).get('instruqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o-mini')

    try: sensitivity = int(os.environ.get('QONQ_SENSITIVITY', 5))
    except: sensitivity = 5
    mode = os.environ.get('QONQ_MODE', 'program')

    sens_prompt = get_sensitivity_rules(sensitivity)
    mode_prompt = get_mode_persona(mode)

    direqtor_prompt = os.environ.get('DIREQTOR_PROMPT', '')
    planner_prompt = f"""
{direqtor_prompt}
You are the 'instruQtor', a senior technical planner.
**OPERATIONAL MODE:** {mode.upper()}
{mode_prompt}

Your goal is to break down the Input Task into logical, atomic "Briqs" (Units of Work).

**OUTPUT FORMAT RULES:**
1. Use the format: `<briq title="Short Descriptive Title"> ... detailed instructions ... </briq>`
2. **DO NOT SUMMARIZE.** You must carry over ALL technical details, regex patterns, constraints, and logic mappings from the Input Task into the relevant Briq.
3. If the input contains code snippets or specific data structures, they MUST appear in the Briq that implements them.
4. Each Briq should be self-contained enough for a developer to execute without seeing the full original file if possible.

**GRANULARITY RULES:**
{sens_prompt}

**Input Task:**
{task_content}

**Begin XML Output:**
"""

    try:
        master_plan = lib_ai.run_ai_completion(ai_provider, ai_model, planner_prompt)
    except Exception as e:
        sys.stderr.write(f"Instruqtor Failure: {e}\n"); sys.exit(1)

    briqs = parse_xml_briqs(master_plan)

    # Fallback only if regex totally fails
    if not briqs:
        if sensitivity >= 8:
             print("[INFO] High Sensitivity or Parsing Fail: Wrapping content as one Briq.", flush=True)
             briqs = [{'title': 'Execute_Full_Task', 'content': task_content}]
        else:
             print("[WARN] No <briq> tags found. Saving raw output.", flush=True)
             briqs = [{'title': 'Master_Plan_Fallback', 'content': master_plan}]

    print(f"--- Generating {len(briqs)} Briqs (Sens:{sensitivity}, Mode:{mode}) ---", flush=True)

    for i, item in enumerate(briqs):
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq{tasq_num}_briq{i:03d}_{step_slug}.md"
        file_path = output_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# {item['title']}\n\n{item['content']}")
        print(f"  - Wrote Briq: {filename}", flush=True)

if __name__ == '__main__':
    main()
