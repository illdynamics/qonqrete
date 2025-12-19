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
    """Converts a title into a readable, lowercase, underscore-separated slug."""
    # Add underscore before uppercase letters (for PascalCase/camelCase)
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
    
    # Replace non-alphanumeric characters with underscores
    s3 = re.sub(r'\W+', '_', s2)
    
    # Collapse multiple underscores into one
    s4 = re.sub(r'_+', '_', s3)
    
    # Remove leading/trailing underscores and lowercase
    slug = s4.strip('_').lower()
    
    # Limit length to avoid excessively long filenames
    return "_".join(slug.split('_')[:8]) if slug else "task"

def get_sensitivity_prompt(level: int) -> str:
    prompts = {
        0: "**CRITICAL RULE (LEVEL 0 - ATOMIC):** Deconstruct the project into the maximum number of granular tasks possible. Target **50 or more** briqs. Deconstruct every single class, function, helper, and configuration file into its own briq. No grouping is permitted.",
        1: "**CRITICAL RULE (LEVEL 1 - VERY HIGH GRANULARITY):** Break down the project into **30-40** briqs. Each major class and module should be a separate briq.",
        2: "**CRITICAL RULE (LEVEL 2 - HIGH GRANULARITY):** Break down the project into **20-30** briqs. Group only very tightly coupled utility functions.",
        3: "**CRITICAL RULE (LEVEL 3 - STANDARD GRANULARITY):** Break down the project into **15-20** briqs. This is the standard for most projects.",
        4: "**CRITICAL RULE (LEVEL 4 - BALANCED):** Break down the project into **10-15** briqs. Group related classes and modules into logical components.",
        5: "**CRITICAL RULE (LEVEL 5 - COMPONENT-LEVEL):** Break down the project into **8-12** briqs. Each briq should represent a major component or feature.",
        6: "**CRITICAL RULE (LEVEL 6 - FEATURE-LEVEL):** Break down the project into **5-8** briqs. Each briq should represent a complete feature.",
        7: "**CRITICAL RULE (LEVEL 7 - BROAD):** Break down the project into **3-5** briqs. These are large, multi-feature briqs.",
        8: "**CRITICAL RULE (LEVEL 8 - VERY BROAD):** Break down the project into **2-3** briqs. The entire backend could be one briq, and the frontend another.",
        9: "**CRITICAL RULE (LEVEL 9 - MONOLITHIC):** Output the entire project as **exactly 1** briq. Do not split it under any circumstances.",
    }
    return prompts.get(level, prompts[3]) # Default to 3 if out of range

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

    # Gather Qodeyard Context
    qodeyard_path = Path(os.environ.get('QONQ_WORKSPACE', '/qonq')) / 'qodeyard'
    qodeyard_tree = ""
    if qodeyard_path.exists() and any(qodeyard_path.iterdir()):
        tree_lines = []
        # Start with the root directory name
        tree_lines.append(f"{qodeyard_path.name}/")
        
        # Use a recursive helper function for clarity
        def build_tree(dir_path: Path, prefix: str):
            # List items and sort them (directories first, then files)
            items = sorted(list(dir_path.iterdir()), key=lambda p: (p.is_file(), p.name))
            for i, path in enumerate(items):
                is_last = i == (len(items) - 1)
                connector = '└── ' if is_last else '├── '
                
                if path.is_dir():
                    tree_lines.append(f"{prefix}{connector}{path.name}/")
                    new_prefix = prefix + ('    ' if is_last else '│   ')
                    build_tree(path, new_prefix)
                else:
                    tree_lines.append(f"{prefix}{connector}{path.name}")

        build_tree(qodeyard_path, "")
        qodeyard_tree = "\n".join(tree_lines)
    else:
        qodeyard_tree = "[qodeyard is empty or does not exist]"


    planner_prompt = f"""
You are the **Principal Software Architect** and your only purpose is to break down a technical specification into a precise number of tasks, called 'briqs'. You must follow the rules exactly as specified.

{sens_prompt}

**ARCHITECTURAL DIRECTIVES:**
1.  **ADHERE TO THE BRIQ COUNT:** This is not a suggestion, it is a strict requirement. The number of briqs you generate must be within the range specified in the CRITICAL RULE.
2.  **INFER THE STRUCTURE:** From the input document, deduce every necessary class, utility, configuration file, and boilerplate code.
3.  **SETUP FIRST:** The first few briqs should always be the project setup: creating the root directory, gitignore, requirements files, configuration, and loggers.
4.  **LOGICAL BREAKDOWN:** After the setup, break down the implementation logically based on the required briq count.
5.  **CONSIDER EXISTING STRUCTURE:** Do not redefine files that already exist. Use the file tree below as a reference for the current state of the codebase.
6.  **ACTIONABLE AND CONCRETE:** Each briq MUST describe a concrete, actionable task that results in a tangible output, such as creating or modifying a specific file. Avoid abstract or high-level instructions. For example, instead of "Integrate branding", a good briq would be "Create `src/assets/logo.svg` with the QonQrete squid logo" and another briq "Modify `tailwind.config.js` to add the QonQrete color palette".

**OUTPUT FORMAT (STRICT XML):**
You must wrap each task in `<briq title="A_Short_And_Clear_Title">...</briq>` tags. The title should be short and descriptive. Do not include any other text or formatting outside of the `<briq>` tags.

**EXISTING FILE STRUCTURE in qodeyard:**
```
{qodeyard_tree}
```

**INPUT DOCUMENT:**
{task_content}

**BEGIN ATOMIC BREAKDOWN (Adhering to the CRITICAL RULE):**
"""

    master_plan = ""
    try:
        master_plan = lib_ai.run_ai_completion(ai_provider, ai_model, planner_prompt)
    except Exception as e:
        sys.stderr.write(f"Instruqtor Failure: {e}\\n")
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
