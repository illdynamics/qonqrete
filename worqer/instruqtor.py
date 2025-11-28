#!/usr/bin/env python3
# worqer/instruqtor.py
import os
import sys
import yaml
import re
from pathlib import Path

# Add local directory to path to import lib_ai
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
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
    pattern = re.compile(r'<briq\s+title=["\'](.*?)["\']\s*>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
    matches = pattern.findall(content)
    return [{'title': m[0].strip(), 'content': m[1].strip()} for m in matches]

def clean_filename_slug(text: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9 ]', '', text)
    slug = "_".join(clean.split()[:6]).lower()
    return slug if slug else "task"

def main() -> None:
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: python instruqtor.py <input_file> <output_dir>\n")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    # Context info
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    tasq_num = os.environ.get('TASQ_NUM', '1')

    if not input_file.exists():
        sys.stderr.write(f"CRITICAL: Task file not found: {input_file}\n")
        sys.exit(1)

    print(f"--- Instruqtor reading: {input_file.name} ---", flush=True)
    with open(input_file, 'r', encoding='utf-8') as f:
        task_content = clean_input_content(f.read())

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except FileNotFoundError: config = {}

    agent_cfg = config.get('agents', {}).get('instruqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o-mini')

    direqtor_prompt = os.environ.get('DIREQTOR_PROMPT', '')
    planner_prompt = f"""
{direqtor_prompt}
You are the 'instruQtor', a senior technical planner.
Your goal is to break down the Input Task into logical, atomic "Briqs" (Units of Work).

**OUTPUT FORMAT RULES:**
You must wrap EVERY unit of work in `<briq>` XML tags.

Example Output:
<briq title="Setup Network">
Explain how to configure...
</briq>

**Input Task:**
{task_content}

**Begin XML Output:**
"""

    try:
        master_plan = lib_ai.run_ai_completion(ai_provider, ai_model, planner_prompt)
    except Exception as e:
        sys.stderr.write(f"Instruqtor Failure: {e}\n")
        sys.exit(1)

    briqs = parse_xml_briqs(master_plan)
    if not briqs:
        print("[WARN] No <briq> tags found. Saving raw output.", flush=True)
        briqs = [{'title': 'Master_Plan_Fallback', 'content': master_plan}]

    print(f"--- Generating {len(briqs)} Briqs for Cycle {cycle_num} using {ai_provider}/{ai_model} ---", flush=True)

    for i, item in enumerate(briqs):
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq{tasq_num}_briq{i:03d}_{step_slug}.md"
        file_path = output_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# {item['title']}\n\n{item['content']}")
        print(f"  - Wrote Briq: {filename}", flush=True)

if __name__ == '__main__':
    main()
