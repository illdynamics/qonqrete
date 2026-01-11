#!/usr/bin/env python3
# worqer/instruqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InstruQtor Agent - Task Decomposition & Planning
# v1.1.2 - LOCAL MODE: Zero-cost task splitting via LocalInstruQtor
# ═══════════════════════════════════════════════════════════════════════════════
#
# v1.1.2 NEW: Local mode support for zero-cost task splitting!
# Set provider: local and model: instruqtor in config.yaml to enable.
# LocalInstruQtor splits tasks using pattern-based analysis:
#   - Paragraphs, bullet points, sections, logical conjunctions
#   - Technical compound patterns (e.g., "build X and Y" → two tasks)
#   - NO LLM calls, NO API costs!
#
# v2.1.5 INVERTED BRIQ SENSITIVITY SCALE
# Now: Higher number = MORE briqs (more intuitive!)
# 
# SENSITIVITY SCALE (0-16):
#   0 = Monolithic (exactly 1 briq) - One giant briq for simple tasks
#   1 = Very Broad (2-3 briqs)
#   2 = Broad (3-5 briqs)
#   3 = Feature-level (5-8 briqs)
#   4 = Component-level (8-12 briqs)
#   5 = Balanced (10-15 briqs) ← RECOMMENDED DEFAULT
#   6 = Standard (15-20 briqs)
#   7 = High Granularity (20-30 briqs)
#   8 = Very High (30-40 briqs)
#   9 = Atomic (40-60 briqs)
#  10 = Ultra (50-75 briqs)
#  11 = Mega (60-90 briqs)
#  12 = Hyper (75-110 briqs)
#  13 = Extreme (90-130 briqs)
#  14 = Maximum (110-160 briqs)
#  15 = Insane (130-200 briqs)
#  16 = QONQRETE MAX (160-250 briqs) - For mega-enterprise tasqs!
#
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
# v1.9.7: Force unbuffered stdout
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"): sys.stderr.reconfigure(line_buffering=True)
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


# ═══════════════════════════════════════════════════════════════════════════════
# ENFORCED BRIQ SENSITIVITY RANGES (v1.0.0)
# ═══════════════════════════════════════════════════════════════════════════════
# Each sensitivity level has a strict (min, max, target) briq count.
# The system will ENFORCE these ranges, not just hint at them.

BRIQ_RANGES = {
    # v2.1.5: INVERTED SCALE - Higher number = More briqs!
    0: (1, 1, 1),        # Monolithic: exactly 1 briq
    1: (2, 3, 2),        # Very Broad: 2-3 briqs
    2: (3, 5, 4),        # Broad: 3-5 briqs
    3: (5, 8, 6),        # Feature-level: 5-8 briqs
    4: (8, 12, 10),      # Component-level: 8-12 briqs
    5: (10, 15, 12),     # Balanced: 10-15 briqs (RECOMMENDED DEFAULT)
    6: (15, 20, 18),     # Standard: 15-20 briqs
    7: (20, 30, 25),     # High Granularity: 20-30 briqs
    8: (30, 40, 35),     # Very High: 30-40 briqs
    9: (40, 60, 50),     # Atomic: 40-60 briqs
    # v2.1.5: Extended range for mega-projects
    10: (50, 75, 60),    # Ultra: 50-75 briqs
    11: (60, 90, 75),    # Mega: 60-90 briqs
    12: (75, 110, 90),   # Hyper: 75-110 briqs
    13: (90, 130, 110),  # Extreme: 90-130 briqs
    14: (110, 160, 135), # Maximum: 110-160 briqs
    15: (130, 200, 165), # Insane: 130-200 briqs
    16: (160, 250, 200), # QONQRETE MAX: 160-250 briqs (enterprise mega-tasqs)
}


def clean_input_content(text: str) -> str:
    text = text.replace('\u200b', '').replace('\ufeff', '')
    text = text.replace('\xa0', ' ')
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    return text


def parse_xml_briqs(content: str) -> list[dict]:
    """Robust parsing that handles potential AI formatting glitches."""
    pattern_strict = re.compile(r'<briq\s+title=["\']([^"\']*)["\']>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
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
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
    s3 = re.sub(r'\W+', '_', s2)
    s4 = re.sub(r'_+', '_', s3)
    slug = s4.strip('_').lower()
    return "_".join(slug.split('_')[:8]) if slug else "task"


def get_sensitivity_config(level: int) -> tuple[int, int, int, str]:
    """
    Returns (min_briqs, max_briqs, target_briqs, prompt_text) for the given sensitivity level.
    """
    min_b, max_b, target_b = BRIQ_RANGES.get(level, BRIQ_RANGES[5])  # v2.1.5: Default to 5 (Balanced)
    
    prompts = {
        # v2.1.5: INVERTED - Higher = More briqs
        0: f"**MANDATORY BRIQ COUNT: EXACTLY 1 BRIQ.** Output the entire project as a single monolithic briq. Do not split under any circumstances. This is non-negotiable.",
        1: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create very broad briqs. Example: 'Backend' and 'Frontend' as separate briqs. Maximum {max_b} briqs allowed.",
        2: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create broad briqs covering major components. Each briq should handle multiple related files.",
        3: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create feature-level briqs. Each major feature or module gets its own briq.",
        4: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create component-level briqs. Group related classes and utilities together.",
        5: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create balanced briqs. Each significant class or module gets a briq. This is the RECOMMENDED DEFAULT.",
        6: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Standard granularity. Most files get their own briq.",
        7: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** High granularity. Split classes into separate briqs where logical.",
        8: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Very high granularity. Each function or small utility gets a briq.",
        9: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** ATOMIC decomposition. Maximum granularity - every function, class, and config gets its own briq.",
        # v2.1.5: Extended levels for mega-projects
        10: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** ULTRA decomposition. Break down every component into fine-grained briqs.",
        11: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** MEGA decomposition. Extremely detailed briqs for large enterprise projects.",
        12: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** HYPER decomposition. Each method, config option, and utility gets its own briq.",
        13: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** EXTREME decomposition. Maximum detail for complex multi-layer architectures.",
        14: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** MAXIMUM decomposition. Near line-by-line granularity for critical systems.",
        15: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** INSANE decomposition. Every single requirement gets dedicated attention.",
        16: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** QONQRETE MAX. Enterprise mega-project level. Use for tasqs with 1000+ requirements.",
    }
    
    prompt = prompts.get(level, prompts[5])  # v2.1.5: Default to 5 (Balanced)
    return min_b, max_b, target_b, prompt


def merge_briqs(briqs: list[dict], target_count: int) -> list[dict]:
    """
    Merge briqs to reduce count to target.
    Strategy: Combine consecutive briqs until we reach target count.
    """
    if len(briqs) <= target_count:
        return briqs
    
    print(f"  [ENFORCE] Merging {len(briqs)} briqs down to {target_count}...", flush=True)
    
    # Calculate how many briqs to merge into each final briq
    merge_factor = math.ceil(len(briqs) / target_count)
    merged = []
    
    for i in range(0, len(briqs), merge_factor):
        chunk = briqs[i:i + merge_factor]
        if len(chunk) == 1:
            merged.append(chunk[0])
        else:
            # Combine titles and content
            combined_title = " + ".join([b['title'][:30] for b in chunk])
            combined_content = "\n\n---\n\n".join([
                f"## {b['title']}\n{b['content']}" for b in chunk
            ])
            merged.append({
                'title': combined_title[:80],
                'content': combined_content
            })
    
    return merged[:target_count]


def generate_briqs_with_enforcement(
    ai_provider: str,
    ai_model: str,
    base_prompt: str,
    sensitivity: int,
    task_content: str,
    qodeyard_tree: str,
    max_retries: int = 2
) -> list[dict]:
    """
    Generate briqs with ENFORCED count ranges.
    Will retry with stronger prompts if AI doesn't comply.
    """
    min_briqs, max_briqs, target_briqs, sens_prompt = get_sensitivity_config(sensitivity)
    
    for attempt in range(max_retries + 1):
        # Build enforcement prompt
        if attempt == 0:
            enforcement = sens_prompt
        else:
            # Stronger enforcement on retry
            enforcement = f"""
⚠️ RETRY ATTEMPT {attempt + 1} - STRICT ENFORCEMENT ⚠️

{sens_prompt}

YOUR PREVIOUS OUTPUT DID NOT COMPLY. YOU MUST OUTPUT BETWEEN {min_briqs} AND {max_briqs} BRIQS.

COUNT YOUR BRIQS BEFORE OUTPUTTING. If you have fewer than {min_briqs}, split your briqs further.
If you have more than {max_briqs}, combine related briqs together.

THIS IS A HARD REQUIREMENT. NON-COMPLIANCE WILL CAUSE SYSTEM FAILURE.
"""
        
        full_prompt = base_prompt.replace("{SENSITIVITY_PROMPT}", enforcement)
        
        # Estimate and log cost
        input_tokens = estimate_tokens(full_prompt, ai_model)
        estimated_output_tokens = 2000
        input_cost = calculate_cost(input_tokens, ai_model, is_input=True)
        output_cost = calculate_cost(estimated_output_tokens, ai_model, is_input=False)
        total_cost = input_cost + output_cost
        
        if attempt == 0:
            print(f"Estimated cost: {format_cost(total_cost)} ({input_tokens:,} in + ~{estimated_output_tokens:,} out tokens @ {ai_model})", flush=True)
        
        # Call AI
        try:
            response = lib_ai.run_ai_completion(ai_provider, ai_model, full_prompt)
        except Exception as e:
            sys.stderr.write(f"InstruQtor AI call failed: {e}\n")
            if attempt < max_retries:
                continue
            sys.exit(1)
        
        # Parse briqs
        briqs = parse_xml_briqs(response)
        
        if not briqs:
            print(f"  [WARN] No valid briqs parsed, attempt {attempt + 1}", flush=True)
            if attempt < max_retries:
                continue
            # Fallback: create single briq from raw response
            briqs = [{'title': 'Master_Plan_Fallback', 'content': response}]
        
        briq_count = len(briqs)
        
        # Check compliance
        if min_briqs <= briq_count <= max_briqs:
            print(f"  [OK] Briq count {briq_count} is within range [{min_briqs}-{max_briqs}]", flush=True)
            return briqs
        elif briq_count > max_briqs:
            # Too many - merge them
            print(f"  [ENFORCE] Got {briq_count} briqs, max is {max_briqs}. Merging...", flush=True)
            return merge_briqs(briqs, max_briqs)
        else:
            # Too few - retry with stronger prompt
            print(f"  [ENFORCE] Got {briq_count} briqs, need at least {min_briqs}. Retrying...", flush=True)
            if attempt >= max_retries:
                # Last resort: accept what we have
                print(f"  [WARN] Could not achieve minimum briq count after {max_retries + 1} attempts. Proceeding with {briq_count} briqs.", flush=True)
                return briqs
    
    return briqs


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

    try: sensitivity = int(os.environ.get('QONQ_SENSITIVITY', 5))  # v2.1.5: Default 5
    except: sensitivity = 5
    
    # Clamp sensitivity to valid range (v2.1.5: extended to 0-16)
    sensitivity = max(0, min(16, sensitivity))

    # Get briq range info for logging
    min_briqs, max_briqs, target_briqs, _ = get_sensitivity_config(sensitivity)
    print(f"  [CONFIG] Sensitivity: {sensitivity} → Target: {target_briqs} briqs (range: {min_briqs}-{max_briqs})", flush=True)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # LOCAL INSTRUQTOR ROUTING (v1.1.2) - Zero-cost task splitting
    # v2.1.5: Gap-Filling for Cycle 2+ - Create missing files!
    # ═══════════════════════════════════════════════════════════════════════════════
    if ai_provider.lower() == 'local' and ai_model.lower() in ('instruqtor', 'local_instruqtor', 'mindstaq'):
        print(f"  [LOCAL] Using LocalInstruQtor (zero-cost mode)", flush=True)
        
        try:
            from worqer.mindstaq.local_instruqtor import LocalInstruQtor
            
            local_cfg = config.get('mindstaq', {})
            instruqtor = LocalInstruQtor(local_cfg)
            result = instruqtor.split(task_content, sensitivity)
            
            # Convert to briq dicts
            briqs = [{'title': b.title, 'content': b.content} for b in result.briqs]
            
            # ═══════════════════════════════════════════════════════════════════════════
            # v2.1.5: QONVERGER - Gap-Filling for Cycle 2+ 🔥
            # Check previous cycle's qodeyard for missing files and add CREATE briqs
            # ═══════════════════════════════════════════════════════════════════════════
            if int(cycle_num) > 1:
                print(f"  [QONVERGER] Cycle {cycle_num} - Checking for missing files from previous cycle...", flush=True)
                try:
                    from worqer.mindstaq.qonverger import Qonverger
                    
                    # Find original tasq.md
                    worqspace_root = Path(os.getcwd())
                    original_tasq = worqspace_root / "tasq.md"
                    if not original_tasq.exists():
                        original_tasq = worqspace_root / "tasq.d" / "cyqle1_tasq.md"
                    
                    qodeyard_path = worqspace_root / "qodeyard"
                    
                    if original_tasq.exists() and qodeyard_path.exists():
                        with open(original_tasq, 'r', encoding='utf-8') as f:
                            tasq_content = f.read()
                        
                        qonverger = Qonverger(tasq_content, qodeyard_path)
                        gaps = qonverger.find_gaps()
                        
                        if gaps:
                            print(f"  [QONVERGER] Found {len(gaps)} missing files! Adding CREATE briqs...", flush=True)
                            
                            # Generate creation briqs for gaps
                            gap_briqs = qonverger.generate_creation_briqs(gaps, max_briqs=max_briqs)
                            
                            # Add gap briqs at the BEGINNING (higher priority)
                            creation_briqs = []
                            for gb in gap_briqs:
                                creation_briqs.append({
                                    'title': f"🆕 {gb['title']}",
                                    'content': gb['content'],
                                })
                            
                            # Prepend creation briqs to regular briqs
                            briqs = creation_briqs + briqs
                            print(f"  [QONVERGER] Added {len(creation_briqs)} CREATE briqs (total: {len(briqs)} briqs)", flush=True)
                        else:
                            print(f"  [QONVERGER] No gaps found - all files present! ✅", flush=True)
                            
                except Exception as e:
                    print(f"  [QONVERGER] Qonvergence analysis skipped: {e}", flush=True)
            # ═══════════════════════════════════════════════════════════════════════════
            
            print(f"--- LocalInstruQtor Generated {len(briqs)} Build Phases (Sens:{sensitivity}, Range:{min_briqs}-{max_briqs}) ---", flush=True)
            
            # Write briqs to output
            for i, item in enumerate(briqs):
                step_slug = clean_filename_slug(item['title'])
                filename = f"cyqle{cycle_num}_tasq1_briq{i:03d}_{step_slug}.md"
                file_path = output_dir / filename
                
                briq_content = f"# {item['title']}\n\n**ARCHITECT'S INSTRUCTION:**\n{item['content']}"
                briq_tokens = estimate_tokens(briq_content, "local")
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {item['title']} [Local: {briq_tokens:,} toks | $0.00]\n\n**ARCHITECT'S INSTRUCTION:**\n{item['content']}")
                
                print(f"  - Wrote [Plan] {filename}", flush=True)
            
            return  # Exit early - local mode complete
            
        except ImportError as e:
            sys.stderr.write(f"[WARN] LocalInstruQtor not available: {e}. Falling back to AI.\n")
            ai_provider = 'openai'
        except Exception as e:
            sys.stderr.write(f"[WARN] LocalInstruQtor failed: {e}. Falling back to AI.\n")
            ai_provider = 'openai'
    # ═══════════════════════════════════════════════════════════════════════════════

    # Gather Qodeyard Context
    qodeyard_path = Path(os.environ.get('QONQ_WORKSPACE', '/qonq')) / 'qodeyard'
    qodeyard_tree = ""
    qodeyard_file_count = 0
    if qodeyard_path.exists() and any(qodeyard_path.iterdir()):
        tree_lines = []
        tree_lines.append(f"{qodeyard_path.name}/")
        
        def build_tree(dir_path: Path, prefix: str):
            nonlocal qodeyard_file_count
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

    # Build the universal file rule
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

This rule applies to ALL cycles. The qodeyard is your source of truth.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    # Context awareness message
    if qodeyard_file_count > 0:
        context_msg = f"\n📊 QODEYARD STATUS: {qodeyard_file_count} files exist. Build on this foundation.\n"
    else:
        context_msg = "\n📊 QODEYARD STATUS: Empty. This is cycle 1 - build from scratch.\n"

    # Build base prompt with placeholder for sensitivity
    planner_prompt = f"""
You are the **Principal Software Architect** and your only purpose is to break down a technical specification into a precise number of tasks, called 'briqs'. You must follow the rules EXACTLY as specified.

{{SENSITIVITY_PROMPT}}

{universal_file_rule}
{context_msg}

**ARCHITECTURAL DIRECTIVES:**
1.  **ADHERE TO THE BRIQ COUNT:** This is a STRICT requirement. Count your briqs before outputting!
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

**BEGIN ATOMIC BREAKDOWN (Count your briqs to ensure compliance!):**
"""

    # Generate briqs with enforcement
    briqs = generate_briqs_with_enforcement(
        ai_provider=ai_provider,
        ai_model=ai_model,
        base_prompt=planner_prompt,
        sensitivity=sensitivity,
        task_content=task_content,
        qodeyard_tree=qodeyard_tree
    )

    print(f"--- Architect Generated {len(briqs)} Build Phases (Sens:{sensitivity}, Range:{min_briqs}-{max_briqs}) ---", flush=True)

    for i, item in enumerate(briqs):
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq1_briq{i:03d}_{step_slug}.md"
        file_path = output_dir / filename

        # Estimate tokens for this briq
        briq_content = f"# {item['title']}\n\n**ARCHITECT'S INSTRUCTION:**\n{item['content']}"
        briq_tokens = estimate_tokens(briq_content, ai_model)
        briq_cost = calculate_cost(briq_tokens, ai_model, is_input=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# {item['title']} [Est: {briq_tokens:,} toks | {format_cost(briq_cost)}]\n\n**ARCHITECT'S INSTRUCTION:**\n{item['content']}")

        print(f"  - Wrote [Plan] {filename}", flush=True)


if __name__ == '__main__':
    main()
