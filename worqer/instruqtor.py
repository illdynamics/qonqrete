#!/usr/bin/env python3
# worqer/instruqtor.py
import os
import sys
import yaml
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

def clean_input_content(text: str) -> str:
    text = text.replace('\u200b', '').replace('\ufeff', '')
    text = text.replace('\xa0', ' ')
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    return text

def parse_xml_briqs(content: str) -> list[dict]:
    # Robust parsing that handles potential AI formatting glitches
    pattern_strict = re.compile(r'<briq\s+title=["\'](.*?)["\']\s*>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
    matches = pattern_strict.findall(content)
    results = [{'title': m[0].strip(), 'content': m[1].strip()} for m in matches]

    if not results:
        pattern_loose = re.compile(r'<briq>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
        loose_matches = pattern_loose.findall(content)
        for i, m in enumerate(loose_matches):
            lines = m.strip().split('\n')
            title = lines[0].strip() if lines else f"Task_{i+1}"
            content_body = "\n".join(lines[1:]) if len(lines) > 1 else m.strip()
            results.append({'title': title, 'content': content_body})
    return results

def clean_filename_slug(text: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9 ]', '', text)
    slug = "_".join(clean.split()[:8]).lower()
    return slug if slug else "task"

def get_sensitivity_prompt(level: int) -> str:
    if level == 0:
        return """
**CRITICAL GRANULARITY RULE (LEVEL 0 - ATOMIC):**
1. **ONE FILE PER BRIQ:** You are FORBIDDEN from creating multiple files in a single Briq.
2. **EXPLODE MODULES:** If the report mentions "Network Module", you must create separate Briqs for: `network_core.py`, `network_utils.py`, `network_listener.py`, `network_config.py`.
3. **MANDATORY BOILERPLATE:** You MUST include Briqs for `logger.py`, `exceptions.py`, `constants.py`, and `config_loader.py`.
4. **SCALE:** For a large report, I expect 30-60 Briqs. Do not summarize.
"""
    elif level <= 5:
        return "Create one Briq per logical component."
    else:
        return "Group related tasks into major phases."

def main() -> None:
    if len(sys.argv) != 3: sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    cycle_num = os.environ.get('CYCLE_NUM', '1')

    print(f"--- Architect analyzing: {input_file.name} ---", flush=True)
    with open(input_file, 'r', encoding='utf-8') as f: task_content = clean_input_content(f.read())

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('instruqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o')

    mode = os.environ.get('QONQ_MODE', 'enterprise')
    try: sensitivity = int(os.environ.get('QONQ_SENSITIVITY', 5))
    except: sensitivity = 5

    sens_prompt = get_sensitivity_prompt(sensitivity)

    planner_prompt = f"""
You are the **Principal Software Architect** operating in **ATOMIC BREAKDOWN MODE**.
**OPERATIONAL MODE:** {mode.upper()}

**INPUT:** A Technical Specification.
**YOUR GOAL:** Explode this document into a massive list of tiny, single-file development tasks.

{sens_prompt}

**ARCHITECTURAL DIRECTIVES:**
1.  **INFER THE STRUCTURE:** Deduce every necessary class, utility, and config file.
2.  **IGNORE FLUFF:** Ignore "Executive Summaries". Focus purely on technical implementation.
3.  **SETUP FIRST:** Briq 00-05 should be Project Structure, Gitignore, Requirements, Configs, Loggers.
4.  **IMPLEMENTATION:** Create separate files for every feature mentioned.

**OUTPUT FORMAT (STRICT XML):**
<briq title="000_Project_Root_Setup">
- Create `requirements.txt`
</briq>
...

**INPUT DOCUMENT:**
{task_content}

**BEGIN ATOMIC BREAKDOWN:**
"""

    master_plan = ""
    try:
        master_plan = lib_ai.run_ai_completion(ai_provider, ai_model, planner_prompt)
    except Exception as e:
        # [FIX] If the AI failed but we captured output (partial stream), check if it's usable.
        print(f"[WARN] AI Stream Signal: {e}", flush=True)
        # If the failure was just the pipe closing at the end, lib_ai might have printed it
        # but raised an error. In a real streaming scenario, we rely on what was captured.
        # Since lib_ai returns the string, if it crashes it usually returns nothing via return.
        # But if the crash happens inside lib_ai it raises.
        # We can't easily recover the string unless lib_ai returns it partially.
        # Given the new lib_ai fix, this catch block is just a safety net.
        sys.stderr.write(f"Instruqtor Failure: {e}\n")
        # Proceed only if we have a way to recover logic (omitted for simplicity, relying on lib_ai fix)
        sys.exit(1)

    briqs = parse_xml_briqs(master_plan)

    if not briqs:
        print("[WARN] Architect failed to produce valid XML. Generating raw output.", flush=True)
        briqs = [{'title': 'Master_Plan_Fallback', 'content': master_plan}]

    print(f"--- Architect Generating {len(briqs)} Build Phases (Sens:{sensitivity}) ---", flush=True)

    for i, item in enumerate(briqs):
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq1_briq{i:03d}_{step_slug}.md"
        file_path = output_dir / filename

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# {item['title']}\n\n**ARCHITECT'S INSTRUCTION:**\n{item['content']}")

        print(f"  - Wrote [Plan] {filename}", flush=True)

if __name__ == '__main__':
    main()
