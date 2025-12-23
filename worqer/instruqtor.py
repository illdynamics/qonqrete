#!/usr/bin/env python3
# worqer/instruqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InstruQtor Agent - Task Decomposition & Planning
# v0.8.9 - Universal File Rule (s00permode)
# ═══════════════════════════════════════════════════════════════════════════════
#
# v0.8.9 FIX: Removed artificial "refinement modes". Instead uses one simple
# universal rule that applies to ALL cycles:
#
#   📁 File EXISTS in qodeyard? → MODIFY/EXTEND it (never recreate)
#   📄 File DOESN'T EXIST? → CREATE it (new modules welcome!)
#
# This prevents the rebuild-from-scratch bug while keeping full creative freedom.
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
import yaml
import re
import math
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

# Import cost estimation
sys.path.insert(0, str(Path(__file__).parent.parent / 'qrane'))
try:
    from lib_funqtions import estimate_tokens, calculate_cost, format_cost
except ImportError:
    # Fallback if lib_funqtions not available
    def estimate_tokens(text, model="gpt-4.1-mini"): return len(text) // 4
    def calculate_cost(tokens, model, is_input=True): return (tokens / 1_000_000) * (0.4 if is_input else 1.6)
    def format_cost(cost): return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"

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
    qodeyard_file_count = 0
    if qodeyard_path.exists() and any(qodeyard_path.iterdir()):
        tree_lines = []
        # Start with the root directory name
        tree_lines.append(f"{qodeyard_path.name}/")
        
        # Use a recursive helper function for clarity
        def build_tree(dir_path: Path, prefix: str):
            nonlocal qodeyard_file_count
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
                    qodeyard_file_count += 1
                    tree_lines.append(f"{prefix}{connector}{path.name}")

        build_tree(qodeyard_path, "")
        qodeyard_tree = "\n".join(tree_lines)
    else:
        qodeyard_tree = "[qodeyard is empty - this is a fresh build]"

    # Build the universal file rule (applies to ALL cycles)
    universal_file_rule = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 UNIVERSAL FILE RULE (STRICTLY ENFORCED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before creating ANY briq, check the file tree below:

  📁 FILE EXISTS in qodeyard?
     → Create a briq to MODIFY it (fix bugs, improve implementation)
     → Create a briq to EXTEND it (add new functions, classes, features)
     → NEVER create a briq to recreate it from scratch
     
  📄 FILE DOESN'T EXIST yet?
     → Create a briq to CREATE it (new modules are welcome!)

EXAMPLES:
  ✅ "Implement HavocClient RPC methods in src/c2/havoc_client.py" (MODIFY existing)
  ✅ "Add geofencing module at src/safety/geofencing.py" (CREATE new)
  ✅ "Fix syntax error in src/traffic/dga.py" (MODIFY existing)
  ❌ "Setup project root and create main.py" (main.py EXISTS - don't recreate!)
  ❌ "Create the configuration system" (config.yaml EXISTS - modify if needed!)

This rule applies to ALL cycles. The qodeyard is your source of truth.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    # Context awareness message
    if qodeyard_file_count > 0:
        context_msg = f"\n📊 QODEYARD STATUS: {qodeyard_file_count} files exist. Build on this foundation.\n"
    else:
        context_msg = "\n📊 QODEYARD STATUS: Empty. This is cycle 1 - build from scratch.\n"

    planner_prompt = f"""
You are the **Principal Software Architect** and your only purpose is to break down a technical specification into a precise number of tasks, called 'briqs'. You must follow the rules exactly as specified.

{sens_prompt}
{universal_file_rule}
{context_msg}

**ARCHITECTURAL DIRECTIVES:**
1.  **ADHERE TO THE BRIQ COUNT:** This is a strict requirement. The number of briqs must be within the range specified in the CRITICAL RULE.
2.  **RESPECT EXISTING FILES:** Check the file tree. Don't recreate what exists - modify or extend it.
3.  **ADDRESS THE INPUT:** If the input contains a review with issues, create briqs to fix those issues.
4.  **ADD MISSING PIECES:** Create briqs for genuinely missing functionality.
5.  **LOGICAL ORDERING:** Order briqs logically - foundations before features that depend on them.

**OUTPUT FORMAT (STRICT XML):**
You must wrap each task in `<briq title="A_Short_And_Clear_Title">...</briq>` tags. The title should be short and descriptive. Do not include any other text or formatting outside of the `<briq>` tags.

**EXISTING FILE STRUCTURE in qodeyard:**
```
{qodeyard_tree}
```

**INPUT DOCUMENT:**
{task_content}

**BEGIN ATOMIC BREAKDOWN (Adhering to the CRITICAL RULE and UNIVERSAL FILE RULE):**
"""

    # Estimate cost for this AI call
    input_tokens = estimate_tokens(planner_prompt, ai_model)
    estimated_output_tokens = 2000  # Typical briq breakdown output
    input_cost = calculate_cost(input_tokens, ai_model, is_input=True)
    output_cost = calculate_cost(estimated_output_tokens, ai_model, is_input=False)
    total_cost = input_cost + output_cost
    print(f"Estimated cost: {format_cost(total_cost)} ({input_tokens:,} in + ~{estimated_output_tokens:,} out tokens @ {ai_model})", flush=True)

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
