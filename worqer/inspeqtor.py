#!/usr/bin/env python3
# worqer/inspeqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InspeQtor Agent - Multi-Stage Code Review System
# v0.8.9 - Batched Reviews + Cost Efficiency + Gemini Flash-Lite
# ═══════════════════════════════════════════════════════════════════════════════
#
# STAGE 1 (This File): Per-briq tactical reviews (batched or individual)
# STAGE 2 (inspeqtor_meta.py): Global meta-review aggregating all briq reqaps
#
# v0.8.9 IMPROVEMENTS:
# - Batched reviews: Groups briqs into batches for 90% fewer API calls
# - Default model: gemini-2.5-flash-lite ($0.10/$0.40 per 1M tokens)
# - Cost estimation before each batch
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
import yaml
import re
import glob
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: 
    import lib_ai
except ImportError: 
    print("CRITICAL: lib_ai.py not found.", flush=True)
    sys.exit(1)

# Import cost estimation
sys.path.insert(0, str(Path(__file__).parent.parent / 'qrane'))
try:
    from lib_funqtions import estimate_tokens, calculate_cost, format_cost
except ImportError:
    # Fallback if lib_funqtions not available
    def estimate_tokens(text, model="gpt-4.1"): return len(text) // 4
    def calculate_cost(tokens, model, is_input=True): return (tokens / 1_000_000) * (2.0 if is_input else 8.0)
    def format_cost(cost): return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_INSPEQTOR_CONFIG = {
    # Per-briq limits (used when batch_mode=false or as fallback)
    'max_prompt_chars_per_briq': 500_000,     # ~500KB per briq review
    'max_context_files_per_briq': 40,         # Max context files per briq
    'max_chars_per_context_file': 80_000,     # Max chars per single context file
    'use_filtered_context': True,             # Only include relevant context files
    'include_neighbor_depth': 1,              # How many hops of dependencies to include
    
    # BATCHED REVIEW CONFIG (v0.8.9+)
    'batch_mode': True,                       # Enable batched reviews (recommended)
    'batch_token_roof': 60000,                # Max input tokens per batch (~240KB)
    'batch_max_briqs': 12,                    # Max briqs per batch (safety cap)
}


def load_inspeqtor_config(config_path: Path) -> dict:
    """Load inspeqtor-specific configuration from config.yaml."""
    config = {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except:
        pass
    
    agent_cfg = config.get('agents', {}).get('inspeqtor', {})
    
    # Merge with defaults
    result = DEFAULT_INSPEQTOR_CONFIG.copy()
    for key in DEFAULT_INSPEQTOR_CONFIG:
        if key in agent_cfg:
            result[key] = agent_cfg[key]
    
    # Add provider/model
    result['provider'] = agent_cfg.get('provider', 'openai')
    result['model'] = agent_cfg.get('model', 'gpt-4o')
    result['use_qontextor'] = config.get('options', {}).get('use_qontextor', True)
    
    return result


def extract_changed_files(changed_files_content: str, qodeyard_path: Path) -> list[tuple[str, str]]:
    """
    Extract list of changed files and their contents from the changed files manifest.
    
    Returns:
        List of (filename, content) tuples
    """
    changed_files = re.findall(r'`([^`]+)`', changed_files_content)
    result = []
    
    for file_str in set(changed_files):
        file_path = qodeyard_path / file_str
        if file_path.is_file():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                result.append((file_str, content))
            except Exception as e:
                result.append((file_str, f"[Could not read: {e}]"))
        else:
            result.append((file_str, "[File not found in qodeyard]"))
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# BATCHED REVIEW SYSTEM (v0.8.9)
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_briq_tokens(briq_file: Path, all_changed: list[tuple[str, str]]) -> int:
    """Estimate the token count for reviewing a single briq."""
    try:
        briq_content = briq_file.read_text(encoding='utf-8')
    except:
        briq_content = ""
    
    # Base: briq content
    total_chars = len(briq_content)
    
    # Add relevant changed files (estimate ~20% of total changed per briq)
    for filename, content in all_changed[:5]:  # Assume max 5 relevant files per briq
        total_chars += len(content) // 3  # Rough estimate
    
    # Convert chars to tokens (4 chars per token average)
    return total_chars // 4


def group_briqs_into_batches(
    briq_files: list[Path],
    all_changed: list[tuple[str, str]],
    token_roof: int,
    max_briqs_per_batch: int
) -> list[list[Path]]:
    """
    Group briqs into batches that fit under the token roof.
    
    Returns:
        List of batches, where each batch is a list of briq file paths
    """
    batches = []
    current_batch = []
    current_tokens = 0
    
    # Base overhead per batch (prompt template, instructions)
    BASE_OVERHEAD = 2000  # tokens
    
    for briq_file in briq_files:
        briq_tokens = estimate_briq_tokens(briq_file, all_changed)
        
        # Check if adding this briq would exceed limits
        would_exceed_tokens = (current_tokens + briq_tokens + BASE_OVERHEAD) > token_roof
        would_exceed_count = len(current_batch) >= max_briqs_per_batch
        
        if current_batch and (would_exceed_tokens or would_exceed_count):
            # Start new batch
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        
        current_batch.append(briq_file)
        current_tokens += briq_tokens
    
    # Don't forget the last batch
    if current_batch:
        batches.append(current_batch)
    
    return batches


def build_batched_review_prompt(
    briqs_data: list[dict],  # [{'name': str, 'content': str, 'changed': list}]
) -> str:
    """Build a prompt for reviewing multiple briqs at once."""
    
    briq_sections = []
    for i, briq in enumerate(briqs_data):
        changed_section = ""
        if briq['changed']:
            changed_files = "\n".join([
                f"**{fname}:**\n```\n{content[:8000]}\n```"  # Limit per file
                for fname, content in briq['changed'][:3]  # Max 3 files per briq in batch
            ])
            changed_section = f"\n**Changed Files:**\n{changed_files}"
        
        briq_sections.append(f"""
### BRIQ {i+1}: {briq['name']}

**Instructions:**
{briq['content'][:4000]}
{changed_section}
""")
    
    return f"""You are a senior code reviewer. Review the following {len(briqs_data)} briqs and provide an assessment for EACH one.

**CRITICAL:** You must provide a separate assessment for EACH briq using this EXACT format:

```
=== BRIQ_REVIEW: briq_name_here ===
Assessment: [SUCCESS|PARTIAL|FAILURE]
Summary: One-line summary of the review
Issues: List any issues found (or "None")
===
```

Review each briq for:
1. Does the code match the architect's instructions?
2. Are there any syntax errors or obvious bugs?
3. Is the implementation complete?

**BRIQS TO REVIEW:**
{"".join(briq_sections)}

**BEGIN REVIEWS (one === BRIQ_REVIEW block per briq):**
"""


def parse_batched_response(response: str, briq_names: list[str]) -> dict[str, dict]:
    """
    Parse a batched review response to extract individual briq assessments.
    
    Returns:
        Dict mapping briq_name -> {'assessment': str, 'summary': str, 'issues': str}
    """
    results = {}
    
    # Try to find each briq's review block
    pattern = r'===\s*BRIQ_REVIEW:\s*(\S+)\s*===\s*Assessment:\s*\[?(SUCCESS|PARTIAL|FAILURE)\]?\s*Summary:\s*(.+?)(?:Issues:\s*(.+?))?(?====|$)'
    
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        name = match[0].strip()
        assessment = f"[{match[1].upper()}]"
        summary = match[2].strip()
        issues = match[3].strip() if len(match) > 3 and match[3] else "None"
        
        # Try to match to actual briq names (fuzzy matching)
        matched_name = None
        for briq_name in briq_names:
            if name.lower() in briq_name.lower() or briq_name.lower() in name.lower():
                matched_name = briq_name
                break
        
        if matched_name:
            results[matched_name] = {
                'assessment': assessment,
                'summary': summary,
                'issues': issues,
                'raw': f"Assessment: {assessment}\nSummary: {summary}\nIssues: {issues}"
            }
    
    # Fill in missing briqs with UNKNOWN
    for briq_name in briq_names:
        if briq_name not in results:
            # Try to extract from response using briq name directly
            if briq_name in response:
                if "[SUCCESS]" in response[response.find(briq_name):response.find(briq_name)+500]:
                    results[briq_name] = {'assessment': '[SUCCESS]', 'summary': 'Extracted from batch', 'issues': 'None', 'raw': ''}
                elif "[PARTIAL]" in response[response.find(briq_name):response.find(briq_name)+500]:
                    results[briq_name] = {'assessment': '[PARTIAL]', 'summary': 'Extracted from batch', 'issues': 'See batch review', 'raw': ''}
                elif "[FAILURE]" in response[response.find(briq_name):response.find(briq_name)+500]:
                    results[briq_name] = {'assessment': '[FAILURE]', 'summary': 'Extracted from batch', 'issues': 'See batch review', 'raw': ''}
                else:
                    results[briq_name] = {'assessment': '[UNKNOWN]', 'summary': 'Could not parse from batch', 'issues': 'Review manually', 'raw': ''}
            else:
                results[briq_name] = {'assessment': '[UNKNOWN]', 'summary': 'Not found in batch response', 'issues': 'Review manually', 'raw': ''}
    
    return results


def filter_context_for_files(
    all_context_files: list[str],
    target_files: list[str],
    qontext_path: Path,
    neighbor_depth: int = 1
) -> list[str]:
    """
    Filter context files to only those relevant to the target files.
    
    Uses dependency information from .q.yaml files to find neighbors.
    """
    relevant = set()
    target_basenames = {Path(f).name for f in target_files}
    
    # Build lookup: source_name -> context_file_path
    qontext_lookup = {}
    for ctx_file in all_context_files:
        if ctx_file.endswith('.q.yaml'):
            basename = Path(ctx_file).name
            source_name = basename.replace('.q.yaml', '')
            qontext_lookup[source_name] = ctx_file
    
    # Phase 1: Direct matches
    for target in target_files:
        target_basename = Path(target).name
        if target_basename in qontext_lookup:
            relevant.add(qontext_lookup[target_basename])
    
    # Phase 2: Neighbor expansion (if depth > 0)
    if neighbor_depth > 0:
        current_frontier = list(relevant)
        
        for _ in range(neighbor_depth):
            next_frontier = []
            
            for ctx_file in current_frontier:
                try:
                    with open(ctx_file, 'r', encoding='utf-8') as f:
                        ctx_data = yaml.safe_load(f) or {}
                    
                    # Get dependencies
                    deps = ctx_data.get('dependencies', [])
                    if isinstance(deps, list):
                        for dep in deps:
                            if isinstance(dep, str):
                                dep_name = dep.split('.')[-1]
                                for source_name, neighbor_file in qontext_lookup.items():
                                    if dep_name in source_name and neighbor_file not in relevant:
                                        relevant.add(neighbor_file)
                                        next_frontier.append(neighbor_file)
                    
                    # Get inbound references
                    inbound = ctx_data.get('inbound_refs', [])
                    if isinstance(inbound, list):
                        for ref in inbound:
                            if isinstance(ref, str):
                                ref_name = ref.split('.')[-1]
                                for source_name, neighbor_file in qontext_lookup.items():
                                    if ref_name in source_name and neighbor_file not in relevant:
                                        relevant.add(neighbor_file)
                                        next_frontier.append(neighbor_file)
                except:
                    pass
            
            current_frontier = next_frontier
    
    return list(relevant)


def build_briq_review_prompt(
    briq_name: str,
    briq_content: str,
    changed_files: list[tuple[str, str]],
    cycle_goal: str = ""
) -> str:
    """Build the prompt for reviewing a single briq."""
    
    # Build changed code section
    changed_code_section = ""
    if changed_files:
        changed_code_section = "\n## Changed Code Artifacts\n"
        for filename, content in changed_files:
            # Truncate very large files in the prompt itself
            if len(content) > 50_000:
                content = content[:50_000] + "\n\n[...TRUNCATED for review...]"
            changed_code_section += f"\n### File: `{filename}`\n```\n{content}\n```\n"
    else:
        changed_code_section = "\n_No changed code artifacts for this briq._\n"
    
    prompt = f"""You are the 'inspeQtor', a senior software quality engineer performing a focused code review.

**SCOPE:** You are reviewing a SINGLE briq (task unit) from a larger cycle. Focus only on this specific unit.

**YOUR TASK:**
Determine if the code changes for this briq are complete, correct, and consistent with the existing architecture.

**REVIEW CRITERIA:**
1. **Correctness:** Is the code logically correct and free of obvious bugs?
2. **Completeness:** Did the code fully implement what the briq specified?
3. **Consistency:** Do the changes integrate properly with existing code patterns and conventions?

**OUTPUT FORMAT (Strict Markdown):**

```
Assessment: [SUCCESS|PARTIAL|FAILURE]

## Summary
(2-3 sentences justifying your assessment)

## Issues Found
- (List any problems, or "None" if clean)

## Suggestions
- (Specific, actionable improvements for the next cycle)
```

**INPUTS FOR YOUR REVIEW:**

## Briq: {briq_name}
{briq_content}
{changed_code_section}

---
*Architectural context (`.q.yaml` skeletons) has been provided in the background.*
---

**Begin Review:**
"""
    return prompt


def run_per_briq_reviews(
    cycle_num: str,
    briq_dir: Path,
    exeq_dir: Path,
    qodeyard_path: Path,
    qontext_path: Path,
    reqap_dir: Path,
    config: dict
) -> list[dict]:
    """
    Run per-briq reviews for all briqs in the current cycle.
    
    Supports two modes:
    - batch_mode=True: Groups briqs into batches for fewer API calls (recommended)
    - batch_mode=False: Reviews each briq individually (legacy)
    
    Returns:
        List of briq review results: [{briq_name, assessment, reqap_path, error}]
    """
    results = []
    
    # Find all briqs for this cycle
    briq_pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(briq_pattern))
    
    if not briq_files:
        print(f"[WARN] No briqs found for cycle {cycle_num}", flush=True)
        return results
    
    # Gather all context files once
    all_context_files = []
    if config['use_qontextor'] and qontext_path.is_dir():
        for root, _, files in os.walk(qontext_path):
            for file in files:
                if file.endswith('.q.yaml'):
                    all_context_files.append(str(Path(root) / file))
    
    # Read the changed files manifest for the cycle
    changed_manifest_path = exeq_dir / f"cyqle{cycle_num}_changed.md"
    try:
        with open(changed_manifest_path, 'r', encoding='utf-8') as f:
            changed_manifest = f.read()
        all_changed = extract_changed_files(changed_manifest, qodeyard_path)
    except:
        all_changed = []
    
    # Create cycle reqap directory
    cycle_reqap_dir = reqap_dir / f"cyqle{cycle_num}"
    cycle_reqap_dir.mkdir(parents=True, exist_ok=True)
    
    # Track total estimated cost
    total_review_cost = 0.0
    
    # Check if batch mode is enabled
    batch_mode = config.get('batch_mode', True)
    
    if batch_mode:
        # ═══════════════════════════════════════════════════════════════════════════
        # BATCHED REVIEW MODE (v0.8.9+)
        # ═══════════════════════════════════════════════════════════════════════════
        token_roof = config.get('batch_token_roof', 60000)
        max_briqs = config.get('batch_max_briqs', 12)
        
        # Group briqs into batches
        batches = group_briqs_into_batches(briq_files, all_changed, token_roof, max_briqs)
        
        print(f"--- InspeQtor: Reviewing {len(briq_files)} briqs in {len(batches)} batches (cyQle {cycle_num}) ---", flush=True)
        
        for batch_idx, batch in enumerate(batches):
            batch_briq_names = [bf.stem for bf in batch]
            print(f"-- Batch {batch_idx + 1}/{len(batches)}: {len(batch)} briqs --", flush=True)
            
            try:
                # Build batch data
                briqs_data = []
                for briq_file in batch:
                    briq_content = briq_file.read_text(encoding='utf-8')
                    briq_name = briq_file.stem
                    
                    # Extract file targets from this briq
                    briq_targets = re.findall(r'`([^`]+\.\w+)`', briq_content)
                    briq_targets = [t for t in briq_targets if '/' in t or t.endswith('.py') or t.endswith('.sh')]
                    
                    # Filter changed files to those relevant
                    briq_changed = []
                    for filename, content in all_changed:
                        if not briq_targets or any(t in filename or filename in t for t in briq_targets):
                            briq_changed.append((filename, content))
                    
                    if not briq_changed and all_changed:
                        briq_changed = all_changed[:3]  # Limit in batch mode
                    
                    briqs_data.append({
                        'name': briq_name,
                        'content': briq_content,
                        'changed': briq_changed
                    })
                
                # Build batched prompt
                prompt = build_batched_review_prompt(briqs_data)
                
                # Estimate cost
                input_tokens = estimate_tokens(prompt, config['model'])
                estimated_output_tokens = len(batch) * 150  # ~150 tokens per briq assessment
                input_cost = calculate_cost(input_tokens, config['model'], is_input=True)
                output_cost = calculate_cost(estimated_output_tokens, config['model'], is_input=False)
                batch_cost = input_cost + output_cost
                total_review_cost += batch_cost
                
                print(f"   Estimated batch cost: {format_cost(batch_cost)}", flush=True)
                
                # Call AI for batched review
                response = lib_ai.run_ai_completion(
                    config['provider'],
                    config['model'],
                    prompt,
                    context_files=[],  # Context embedded in prompt for batched
                    max_prompt_chars=config.get('batch_token_roof', 60000) * 4  # chars
                )
                
                # Parse batch response
                parsed_results = parse_batched_response(response, batch_briq_names)
                
                # Write individual reqaps and collect results
                for briq_name in batch_briq_names:
                    parsed = parsed_results.get(briq_name, {
                        'assessment': '[UNKNOWN]',
                        'summary': 'Not found in batch',
                        'issues': 'Review manually',
                        'raw': ''
                    })
                    
                    reqap_path = cycle_reqap_dir / f"{briq_name}_reqap.md"
                    with open(reqap_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Briq Review: {briq_name}\n\n")
                        f.write(f"Assessment: {parsed['assessment']}\n\n")
                        f.write(f"## Summary\n{parsed['summary']}\n\n")
                        f.write(f"## Issues\n{parsed['issues']}\n")
                    
                    results.append({
                        'briq_name': briq_name,
                        'assessment': parsed['assessment'],
                        'reqap_path': str(reqap_path),
                        'error': None
                    })
                
                # Count assessments
                successes = sum(1 for r in parsed_results.values() if r['assessment'] == '[SUCCESS]')
                partials = sum(1 for r in parsed_results.values() if r['assessment'] == '[PARTIAL]')
                failures = sum(1 for r in parsed_results.values() if r['assessment'] == '[FAILURE]')
                print(f"   Batch results: ✅{successes} ⚠️{partials} ❌{failures}", flush=True)
                
            except Exception as e:
                print(f"   [ERROR] Batch review failed: {e}", flush=True)
                
                # Mark all briqs in batch as failed
                for briq_file in batch:
                    briq_name = briq_file.stem
                    reqap_path = cycle_reqap_dir / f"{briq_name}_reqap.md"
                    with open(reqap_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Briq Review: {briq_name}\n\nAssessment: [FAILURE]\n\n## Error\nBatch review failed: {e}")
                    
                    results.append({
                        'briq_name': briq_name,
                        'assessment': '[FAILURE]',
                        'reqap_path': str(reqap_path),
                        'error': str(e)
                    })
    
    else:
        # ═══════════════════════════════════════════════════════════════════════════
        # LEGACY PER-BRIQ MODE
        # ═══════════════════════════════════════════════════════════════════════════
        print(f"--- InspeQtor: Reviewing {len(briq_files)} briqs individually (cyQle {cycle_num}) ---", flush=True)
        
        for briq_file in briq_files:
            briq_name = briq_file.stem
            print(f"-- Reviewing: {briq_name} --", flush=True)
            
            try:
                with open(briq_file, 'r', encoding='utf-8') as f:
                    briq_content = f.read()
                
                # Extract file targets from this briq
                briq_targets = re.findall(r'`([^`]+\.\w+)`', briq_content)
                briq_targets = [t for t in briq_targets if '/' in t or t.endswith('.py') or t.endswith('.sh')]
                
                # Filter changed files
                briq_changed = []
                for filename, content in all_changed:
                    if not briq_targets or any(t in filename or filename in t for t in briq_targets):
                        briq_changed.append((filename, content))
                
                if not briq_changed and all_changed:
                    briq_changed = all_changed[:5]
                
                # Filter context
                if config['use_filtered_context'] and briq_changed:
                    changed_file_names = [f for f, _ in briq_changed]
                    context_files = filter_context_for_files(
                        all_context_files,
                        changed_file_names,
                        qontext_path,
                        config['include_neighbor_depth']
                    )
                else:
                    context_files = all_context_files[:config['max_context_files_per_briq']]
                
                # Build prompt
                prompt = build_briq_review_prompt(briq_name, briq_content, briq_changed)
                
                # Estimate cost
                context_size = sum(len(Path(f).read_text(encoding='utf-8', errors='ignore')) for f in context_files if Path(f).exists())
                input_tokens = estimate_tokens(prompt, config['model']) + (context_size // 4)
                estimated_output_tokens = 500
                input_cost = calculate_cost(input_tokens, config['model'], is_input=True)
                output_cost = calculate_cost(estimated_output_tokens, config['model'], is_input=False)
                review_cost = input_cost + output_cost
                total_review_cost += review_cost
                
                # Call AI
                response = lib_ai.run_ai_completion(
                    config['provider'],
                    config['model'],
                    prompt,
                    context_files=context_files,
                    max_prompt_chars=config['max_prompt_chars_per_briq'],
                    max_context_files=config['max_context_files_per_briq'],
                    max_chars_per_file=config['max_chars_per_context_file']
                )
                
                # Extract assessment
                assessment = "[UNKNOWN]"
                if "[SUCCESS]" in response:
                    assessment = "[SUCCESS]"
                elif "[PARTIAL]" in response:
                    assessment = "[PARTIAL]"
                elif "[FAILURE]" in response:
                    assessment = "[FAILURE]"
                
                # Write reqap
                reqap_path = cycle_reqap_dir / f"{briq_name}_reqap.md"
                with open(reqap_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Briq Review: {briq_name}\n\n{response}")
                
                print(f"   Assessment: {assessment}", flush=True)
                
                results.append({
                    'briq_name': briq_name,
                    'assessment': assessment,
                    'reqap_path': str(reqap_path),
                    'error': None
                })
                
            except Exception as e:
                print(f"   [ERROR] Review failed: {e}", flush=True)
                
                reqap_path = cycle_reqap_dir / f"{briq_name}_reqap.md"
                with open(reqap_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Briq Review: {briq_name}\n\nAssessment: [FAILURE]\n\n## Error\nReview failed: {e}")
                
                results.append({
                    'briq_name': briq_name,
                    'assessment': '[FAILURE]',
                    'reqap_path': str(reqap_path),
                    'error': str(e)
                })
    
    # Print total estimated review cost
    print(f"--- Reviews complete: {len(results)} briqs, estimated {format_cost(total_review_cost)} total ---", flush=True)
    
    return results


def main() -> None:
    """
    InspeQtor main entry point.
    
    Usage: inspeqtor.py <summary_path> <changed_files_path> <reqap_output_path>
    
    This now runs per-briq reviews and then triggers the meta-review.
    """
    if len(sys.argv) != 4:
        print("Usage: inspeqtor.py <summary_path> <changed_files_path> <reqap_output_path>", flush=True)
        sys.exit(1)

    summary_path = Path(sys.argv[1])
    changed_files_path = Path(sys.argv[2])
    reqap_path = Path(sys.argv[3])
    
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    qontext_path = worqspace_root / "qontext.d"
    briq_dir = worqspace_root / "briq.d"
    exeq_dir = worqspace_root / "exeq.d"
    reqap_dir = worqspace_root / "reqap.d"
    tasq_dir = worqspace_root / "tasq.d"
    
    print(f"=== InspeQtor v0.9.0: Two-Stage Review for cyQle {cycle_num} ===", flush=True)

    # Load configuration
    config = load_inspeqtor_config(worqspace_root / 'config.yaml')
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: Per-Briq Tactical Reviews
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- STAGE 1: Per-Briq Tactical Reviews ---", flush=True)
    
    briq_results = run_per_briq_reviews(
        cycle_num,
        briq_dir,
        exeq_dir,
        qodeyard_path,
        qontext_path,
        reqap_dir,
        config
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Global Meta-Review (Aggregation)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- STAGE 2: Global Meta-Review ---", flush=True)
    
    # Read original summary
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary_content = f.read()
    except:
        summary_content = "[Summary not available]"
    
    # Read cycle tasq (the original goal)
    cycle_tasq_path = tasq_dir / f"cyqle{cycle_num}_tasq.md"
    try:
        with open(cycle_tasq_path, 'r', encoding='utf-8') as f:
            cycle_goal = f.read()
    except:
        cycle_goal = "[Cycle goal not available]"
    
    # Aggregate briq results for meta-review
    briq_summaries = []
    success_count = 0
    partial_count = 0
    failure_count = 0
    failed_briq_suggestions = []  # Collect ALL suggestions from failed briqs
    
    for result in briq_results:
        if result['assessment'] == '[SUCCESS]':
            success_count += 1
        elif result['assessment'] == '[PARTIAL]':
            partial_count += 1
        else:
            failure_count += 1
        
        # Read briq reqap content
        try:
            with open(result['reqap_path'], 'r', encoding='utf-8') as f:
                briq_reqap = f.read()
        except:
            briq_reqap = f"Assessment: {result['assessment']}\n\nError: {result.get('error', 'Unknown')}"
        
        # For failed/partial briqs, extract suggestions with NO truncation
        if result['assessment'] in ['[FAILURE]', '[PARTIAL]']:
            # Extract suggestions section if present
            suggestions_match = re.search(r'## Suggestions\s*\n(.*?)(?=\n##|\Z)', briq_reqap, re.DOTALL)
            if suggestions_match:
                failed_briq_suggestions.append({
                    'briq': result['briq_name'],
                    'assessment': result['assessment'],
                    'suggestions': suggestions_match.group(1).strip()
                })
            else:
                # Fallback: include full content for failed briqs
                failed_briq_suggestions.append({
                    'briq': result['briq_name'],
                    'assessment': result['assessment'],
                    'suggestions': briq_reqap
                })
        
        briq_summaries.append({
            'name': result['briq_name'],
            'assessment': result['assessment'],
            'content': briq_reqap
        })
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CROSS-BRIQ CONSISTENCY CHECK
    # ═══════════════════════════════════════════════════════════════════════════
    # Detect potential integration issues by checking for file overlaps
    cross_briq_warnings = []
    
    # Build a map of which briqs touched which files
    briq_file_map = {}
    all_touched_files = set()
    
    for briq_file in briq_dir.glob(f"cyqle{cycle_num}_*.md"):
        briq_name = briq_file.stem
        try:
            with open(briq_file, 'r', encoding='utf-8') as f:
                briq_content = f.read()
            # Extract file references
            file_refs = set(re.findall(r'`([^`]+\.\w{2,4})`', briq_content))
            briq_file_map[briq_name] = file_refs
            all_touched_files.update(file_refs)
        except:
            pass
    
    # Check for files touched by multiple briqs (potential integration points)
    for target_file in all_touched_files:
        touching_briqs = [b for b, files in briq_file_map.items() if target_file in files]
        if len(touching_briqs) > 1:
            cross_briq_warnings.append(f"⚠️ `{target_file}` touched by multiple briqs: {', '.join(touching_briqs)}")
    
    print(f"\n[CROSS-BRIQ] Found {len(cross_briq_warnings)} potential integration points", flush=True)
    
    # Determine overall assessment
    total_briqs = len(briq_results)
    if failure_count > 0:
        overall_assessment = "[FAILURE]"
    elif partial_count > 0:
        overall_assessment = "[PARTIAL]"
    else:
        overall_assessment = "[SUCCESS]"
    
    # Build meta-review prompt (NO CODE - only summaries and reqaps)
    meta_prompt = f"""You are the 'inspeQtor Meta-Reviewer', synthesizing per-briq code reviews into a final cycle assessment.

**YOUR TASK:**
Aggregate the individual briq reviews into a single, coherent cycle-level assessment. DO NOT re-review code - focus on patterns, themes, and overall quality.

**CRITICAL:** Pay special attention to:
1. FAILED and PARTIAL briqs - their suggestions MUST be prominently included in your output
2. Cross-briq integration warnings - files touched by multiple briqs may have consistency issues
3. Patterns across briqs - recurring problems indicate systemic issues

**INPUTS:**

## Original Cycle Goal
{cycle_goal[:3000]}{'...[truncated]' if len(cycle_goal) > 3000 else ''}

## ConstruQtor Execution Summary
{summary_content[:2000]}{'...[truncated]' if len(summary_content) > 2000 else ''}

## Per-Briq Review Results
Total: {total_briqs} briqs | ✅ {success_count} SUCCESS | ⚠️ {partial_count} PARTIAL | ❌ {failure_count} FAILURE

"""
    
    # Add cross-briq warnings prominently
    if cross_briq_warnings:
        meta_prompt += "\n## ⚠️ CROSS-BRIQ INTEGRATION WARNINGS\n"
        meta_prompt += "These files were modified by multiple briqs - verify consistency:\n"
        for warning in cross_briq_warnings[:20]:  # Limit to 20 warnings
            meta_prompt += f"- {warning}\n"
        meta_prompt += "\n"
    
    # Add failed briq suggestions IN FULL (no truncation for failures!)
    if failed_briq_suggestions:
        meta_prompt += "\n## 🚨 FAILED/PARTIAL BRIQ SUGGESTIONS (MUST ADDRESS)\n"
        for item in failed_briq_suggestions:
            meta_prompt += f"\n### {item['briq']} {item['assessment']}\n"
            # Include full suggestions, but cap at 3000 chars per briq
            suggestions = item['suggestions']
            if len(suggestions) > 3000:
                suggestions = suggestions[:3000] + "\n[...continued in briq reqap file...]"
            meta_prompt += f"{suggestions}\n"
        meta_prompt += "\n"
    
    # Add briq summaries (truncated to fit)
    for briq in briq_summaries:
        briq_section = f"\n### {briq['name']}: {briq['assessment']}\n{briq['content'][:1500]}\n"
        if len(meta_prompt) + len(briq_section) < 50_000:  # Keep meta prompt reasonable
            meta_prompt += briq_section
        else:
            meta_prompt += f"\n### {briq['name']}: {briq['assessment']}\n[Content truncated]\n"
    
    meta_prompt += f"""

---

**OUTPUT FORMAT:**

```
Assessment: {overall_assessment}

## Executive Summary
(2-3 sentence high-level summary of the entire cycle)

## 🚨 Critical Issues (from Failed/Partial Briqs)
(List ALL suggestions from failed briqs - these MUST be fixed in the next cycle)

## ⚠️ Integration Concerns  
(Any cross-briq consistency issues detected)

## Per-Briq Breakdown
| Briq | Status | Key Finding |
|------|--------|-------------|
(Table summarizing each briq)

## Consolidated Suggestions
### High Priority
- (Critical issues that block integration)

### Medium Priority  
- (Important improvements)

### Low Priority
- (Nice-to-haves and minor polish)

## Patterns Observed
(Any recurring themes across briqs - good or bad)
```

**IMPORTANT:** Every suggestion from a FAILED briq must appear in your output. Do not drop or summarize away failure details.

**Begin Meta-Review:**
"""
    
    # Estimate cost for meta-review
    meta_input_tokens = estimate_tokens(meta_prompt, config['model'])
    meta_output_tokens = 2000  # Meta-review is longer
    meta_input_cost = calculate_cost(meta_input_tokens, config['model'], is_input=True)
    meta_output_cost = calculate_cost(meta_output_tokens, config['model'], is_input=False)
    meta_cost = meta_input_cost + meta_output_cost
    print(f"Estimated cost: {format_cost(meta_cost)} (meta-review @ {config['model']})", flush=True)
    
    try:
        # Meta-review doesn't need architectural context - it's purely textual aggregation
        meta_response = lib_ai.run_ai_completion(
            config['provider'],
            config['model'],
            meta_prompt,
            context_files=[],  # No context needed for meta-review
            max_prompt_chars=100_000  # Meta-review prompt is much smaller
        )
        
        # Write final reqap
        final_content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v0.9.0 (Two-Stage Review)

{meta_response}

---
"""
        
        # Add cross-briq warnings section
        if cross_briq_warnings:
            final_content += "\n## Cross-Briq Integration Points\n"
            final_content += "These files were touched by multiple briqs - verify consistency:\n\n"
            for warning in cross_briq_warnings:
                final_content += f"- {warning}\n"
            final_content += "\n---\n"
        
        # Add failed briq details prominently
        if failed_briq_suggestions:
            final_content += "\n## Failed/Partial Briq Details (Full)\n"
            for item in failed_briq_suggestions:
                final_content += f"\n### {item['briq']} {item['assessment']}\n"
                final_content += f"{item['suggestions']}\n"
            final_content += "\n---\n"
        
        final_content += "\n## Individual Briq ReQaps\n"
        for briq in briq_summaries:
            final_content += f"\n### {briq['name']}\n{briq['content']}\n"
        
        os.makedirs(reqap_path.parent, exist_ok=True)
        with open(reqap_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        print(f"\n=== Final Assessment: {overall_assessment} ===", flush=True)
        print(f"ReQap written to {reqap_path}", flush=True)
        
    except Exception as e:
        print(f"[ERROR] Meta-review failed: {e}", flush=True)
        
        # Fallback: write a simple aggregated reqap WITH failed briq details
        fallback_content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v0.8.2 (Fallback Mode - Meta-review failed)

Assessment: {overall_assessment}

## Summary
Meta-review failed with error: {e}

Per-briq results:
- Success: {success_count}
- Partial: {partial_count}  
- Failure: {failure_count}

"""
        # Still include cross-briq warnings even in fallback
        if cross_briq_warnings:
            fallback_content += "## Cross-Briq Integration Points\n"
            for warning in cross_briq_warnings:
                fallback_content += f"- {warning}\n"
            fallback_content += "\n"
        
        # Still include failed briq suggestions even in fallback
        if failed_briq_suggestions:
            fallback_content += "## 🚨 Failed/Partial Briq Suggestions (MUST ADDRESS)\n"
            for item in failed_briq_suggestions:
                fallback_content += f"\n### {item['briq']} {item['assessment']}\n"
                fallback_content += f"{item['suggestions']}\n"
            fallback_content += "\n"
        
        fallback_content += f"## Next Steps\n- Review the individual briq reqaps in `reqap.d/cyqle{cycle_num}/` for details.\n"
        
        os.makedirs(reqap_path.parent, exist_ok=True)
        with open(reqap_path, 'w', encoding='utf-8') as f:
            f.write(fallback_content)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: Local Verification (Deterministic, No AI)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- STAGE 3: LoQal Verification ---", flush=True)
    
    verification_enabled = config.get('verification', {}).get('enabled', True)
    verification_results = None
    
    if verification_enabled:
        try:
            import loqal_verifier
            
            verification_report = loqal_verifier.run_verification(
                qodeyard_path,
                qontext_path,
                cycle_num,
                load_inspeqtor_config(worqspace_root / 'config.yaml')
            )
            
            # Write verification report
            verification_output = reqap_dir / f"cyqle{cycle_num}_verification.md"
            with open(verification_output, 'w', encoding='utf-8') as f:
                f.write(verification_report.to_markdown())
            
            print(f"Verification report: {verification_output}", flush=True)
            
            # Store for appending to reqap
            verification_results = verification_report
            
            # Update overall assessment if verification found errors
            if verification_report.errors > 0 and overall_assessment == "[SUCCESS]":
                overall_assessment = "[PARTIAL]"
                print(f"[WARN] Verification found {verification_report.errors} errors - downgrading to PARTIAL", flush=True)
                
        except ImportError:
            print("[WARN] loqal_verifier module not found - skipping verification", flush=True)
        except Exception as e:
            print(f"[WARN] Verification failed: {e}", flush=True)
    else:
        print("LoQal verification disabled in config", flush=True)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # APPEND VERIFICATION RESULTS TO REQAP
    # ═══════════════════════════════════════════════════════════════════════════
    # The reqap gets promoted to next cycle's tasq via promote_reqap() in qrane.py
    # So we just need to make sure ALL failure info is in the reqap!
    
    if verification_results and (verification_results.errors > 0 or verification_results.warnings > 0):
        try:
            # Read current reqap
            with open(reqap_path, 'r', encoding='utf-8') as f:
                current_reqap = f.read()
            
            # Append verification failures
            verification_section = f"""

---

## 🔍 LoQal Verification Results

**Status:** {verification_results.overall_status}
**Checked:** {verification_results.files_checked} files
**Results:** ✅ {verification_results.passed} | ⚠️ {verification_results.warnings} | ❌ {verification_results.errors}

"""
            # Add errors
            errors = [r for r in verification_results.results if not r.passed and r.severity == 'error']
            if errors:
                verification_section += "### ❌ Errors (MUST FIX)\n\n"
                for r in errors:
                    line_info = f" (line {r.line_number})" if r.line_number else ""
                    verification_section += f"- **{r.file_path}**{line_info}: [{r.check_type}] {r.message}\n"
                verification_section += "\n"
            
            # Add warnings
            warnings = [r for r in verification_results.results if not r.passed and r.severity == 'warning']
            if warnings:
                verification_section += "### ⚠️ Warnings\n\n"
                for r in warnings:
                    line_info = f" (line {r.line_number})" if r.line_number else ""
                    verification_section += f"- **{r.file_path}**{line_info}: [{r.check_type}] {r.message}\n"
                verification_section += "\n"
            
            # Write updated reqap
            with open(reqap_path, 'w', encoding='utf-8') as f:
                f.write(current_reqap + verification_section)
            
            print(f"Appended verification results to reqap", flush=True)
            
        except Exception as e:
            print(f"[WARN] Could not append verification to reqap: {e}", flush=True)
    
    print(f"\n=== InspeQtor v0.8.9 Complete: {overall_assessment} ===", flush=True)


if __name__ == '__main__':
    main()
