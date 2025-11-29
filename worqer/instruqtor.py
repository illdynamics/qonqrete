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
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    return text

def parse_xml_briqs(content: str) -> list[dict]:
    # Robust parsing that handles potential AI formatting glitches
    pattern_strict = re.compile(r'<briq\s+title=["\'](.*?)["\']\s*>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
    matches = pattern_strict.findall(content)
    results = [{'title': m[0].strip(), 'content': m[1].strip()} for m in matches]

    if not results:
        # Fallback: Try to find briqs without attributes
        pattern_loose = re.compile(r'<briq>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
        loose_matches = pattern_loose.findall(content)
        for i, m in enumerate(loose_matches):
            # Extract first line as title if possible
            lines = m.strip().split('\n')
            title = lines[0].strip() if lines else f"Task_{i+1}"
            content_body = "\n".join(lines[1:]) if len(lines) > 1 else m.strip()
            results.append({'title': title, 'content': content_body})

    return results

def clean_filename_slug(text: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9 ]', '', text)
    slug = "_".join(clean.split()[:8]).lower() # Increased slug length for better filenames
    return slug if slug else "task"

def main() -> None:
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: python instruqtor.py <input_file> <output_dir>\n"); sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    cycle_num = os.environ.get('CYCLE_NUM', '1')

    if not input_file.exists():
        sys.stderr.write(f"CRITICAL: Task file not found: {input_file}\n"); sys.exit(1)

    print(f"--- InstruQtor (Architect Mode) analyzing: {input_file.name} ---", flush=True)
    with open(input_file, 'r', encoding='utf-8') as f: task_content = clean_input_content(f.read())

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except FileNotFoundError: config = {}

    agent_cfg = config.get('agents', {}).get('instruqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o') # Recommend a smart model for architecture

    mode = os.environ.get('QONQ_MODE', 'program')

    # --- THE ARCHITECT PROMPT ---
    # This prompt is engineered to force the AI to behave like a Lead Developer/Architect
    # It focuses on deriving concrete code tasks from abstract descriptions.

    planner_prompt = f"""
You are the **Principal Software Architect** of a high-performance engineering team.
**OPERATIONAL MODE:** {mode.upper()}

**INPUT:** A Technical Specification or Whitepaper.
**YOUR GOAL:** Deconstruct this document into a **CONCRETE, FILE-BY-FILE BUILD PLAN**.

**ARCHITECTURAL DIRECTIVES:**
1.  **INFER THE STRUCTURE:** If the input is a report (e.g., "Analysis of X"), you must deduce the code required to *build* X.
2.  **FILE-CENTRIC PLANNING:** Do not give vague instructions like "Implement networking." You must specify: "Create `network_manager.py` with class `ConnectionHandler`."
3.  **DEPENDENCY FIRST:** Ensure early Briqs handle setup (`requirements.txt`, `setup.sh`, config files) before logic.
4.  **COMPLETENESS:** If the report mentions a feature (e.g., "Jittered Beaconing"), you MUST create a Briq to implement the logic for it.

**OUTPUT FORMAT (STRICT XML):**
You must output a series of `<briq>` tags. Each tag represents a **Unit of Work** for a developer.

Format:
<briq title="00_Setup_Environment">
- Create `requirements.txt` with dependencies: [list derived from report]
- Create `config.yaml` with fields: [list derived from report]
</briq>

<briq title="01_Core_Logic_Module">
- Create file `src/core.py`.
- Implement class `Engine`.
- Add methods corresponding to [specific section of report].
</briq>

... continue for ALL components ...

**INPUT DOCUMENT:**
{task_content}

**BEGIN ARCHITECTURAL BREAKDOWN:**
"""

    try:
        # Pass empty list for context_files as we are analyzing the input spec primarily
        master_plan = lib_ai.run_ai_completion(ai_provider, ai_model, planner_prompt)
    except Exception as e:
        sys.stderr.write(f"Instruqtor Architecture Failure: {e}\n"); sys.exit(1)

    briqs = parse_xml_briqs(master_plan)

    if not briqs:
        print("[WARN] Architect failed to produce valid XML. Dumping raw output as single task.", flush=True)
        briqs = [{'title': 'Master_Plan_Fallback', 'content': master_plan}]

    print(f"--- Architect generated {len(briqs)} Build Phases ---", flush=True)

    for i, item in enumerate(briqs):
        # Use simple numbering to ensure Construqtor runs them in order
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq1_briq{i:03d}_{step_slug}.md"
        file_path = output_dir / filename

        with open(file_path, 'w', encoding='utf-8') as f:
            # Wrap content in a robust prompt for the Construqtor
            f.write(f"# {item['title']}\n\n**ARCHITECT'S INSTRUCTION:**\n{item['content']}")

        print(f"  - [Plan] {filename}", flush=True)

if __name__ == '__main__':
    main()
