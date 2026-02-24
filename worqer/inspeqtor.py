#!/usr/bin/env python3
# worqer/inspeqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InspeQtor Agent - Multi-Stage Code Review System
# v1.0.4-stable - QONTRACT Enforcement + QontractGuard Integration
# ═══════════════════════════════════════════════════════════════════════════════
#
# STAGE 1 (This File): Per-briq tactical reviews (batched or individual)
# STAGE 2 (inspeqtor_meta.py): Global meta-review aggregating all briq reqaps
#
# v0.9.0 IMPROVEMENTS:
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

# v1.0.4: Import QontractGuard
try:
    import qontract_guard
except ImportError:
    qontract_guard = None
    print("[WARN] qontract_guard module not found — deterministic checks disabled", flush=True)

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
    
    # BATCHED REVIEW CONFIG (v0.9.0+)
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
# BATCHED REVIEW SYSTEM (v0.9.0)
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
    cycle_goal: str = "",
    qontract_context: str = ""  # v1.0.4
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
    
    # v1.0.4: QONTRACT section
    qontract_section = ""
    if qontract_context:
        qontract_section = f"""

## 📜 PROJECT CONSTITUTION (QONTRACT)
{qontract_context[:3000]}
**You MUST verify code against these invariants.**
"""

    prompt = f"""You are the 'inspeQtor', a senior software quality engineer performing a focused code review.

**SCOPE:** You are reviewing a SINGLE briq (task unit) from a larger cycle. Focus only on this specific unit.
{qontract_section}
**YOUR TASK:**
Determine if the code changes for this briq are complete, correct, and consistent with the existing architecture.

**REVIEW CRITERIA:**
1. **Correctness:** Is the code logically correct and free of obvious bugs?
2. **Completeness:** Did the code fully implement what the briq specified?
3. **Consistency:** Do the changes integrate properly with existing code patterns and conventions?
4. **Contract Compliance:** Does the code comply with QONTRACT invariants?

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
        # BATCHED REVIEW MODE (v0.9.0+)
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
    v1.0.4-stable: Reordered stages per G4.5/G4.6 spec.
    
    Stage order:
      STAGE 0: QontractGuard (deterministic, BEFORE AI)
      STAGE 1: LoQal Verification (syntax/import sanity, BEFORE AI)
      STAGE 2: Per-Briq Tactical Reviews (AI, only if guard passes or report-only)
      STAGE 3: Global Meta-Review (AI aggregation)
    
    Usage: inspeqtor.py <summary_path> <changed_files_path> <reqap_output_path>
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
    bloq_path = worqspace_root / "bloq.d"
    briq_dir = worqspace_root / "briq.d"
    exeq_dir = worqspace_root / "exeq.d"
    reqap_dir = worqspace_root / "reqap.d"
    tasq_dir = worqspace_root / "tasq.d"
    struqture_dir = worqspace_root / "struqture"
    
    print(f"=== InspeQtor v1.0.4: Multi-Stage Review for cyQle {cycle_num} ===", flush=True)

    # Load configuration
    config = load_inspeqtor_config(worqspace_root / 'config.yaml')

    # ═══════════════════════════════════════════════════════════════════════════
    # B) FAIL-FAST: Contract must exist (cycles > 1)
    # ═══════════════════════════════════════════════════════════════════════════
    qontract_dir = worqspace_root / "qontract.d"
    if cycle_num != '1':
        try:
            from runtime_checks import ensure_qontract_present
            ensure_qontract_present(worqspace_root)
            print(f"    ✅ Contract present (fail-fast check passed)", flush=True)
        except RuntimeError as e:
            print(f"    ❌ {e}", flush=True)
            sys.exit(1)
        except ImportError:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.0.4 (C): CONTEXT ASSEMBLY — Contract + Tasqs + Qodeyard (primary)
    # bloq.d and qontext.d are optional and may be stale
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n--- Context Assembly ---", flush=True)

    # 1. QONTRACT (always included, from qontract.d/)
    qontract_content = ""
    qontract_md_path = qontract_dir / "qontract.md"
    if qontract_md_path.exists():
        try:
            with open(qontract_md_path, 'r', encoding='utf-8') as f:
                qontract_content = f.read()
            print(f"    [ok] QONTRACT: {qontract_md_path} ({len(qontract_content)} chars)", flush=True)
        except Exception as e:
            print(f"    [!!] QONTRACT: Could not load {qontract_md_path}: {e}", flush=True)
    else:
        print(f"    [--] QONTRACT: Not found at {qontract_md_path}", flush=True)

    # 2. Current cycle tasq (always included)
    cycle_tasq_content = ""
    cycle_tasq_path = tasq_dir / f"cyqle{cycle_num}_tasq.md"
    if cycle_tasq_path.exists():
        try:
            with open(cycle_tasq_path, 'r', encoding='utf-8') as f:
                cycle_tasq_content = f.read()
            print(f"    [ok] Cycle {cycle_num} Tasq: {cycle_tasq_path} ({len(cycle_tasq_content)} chars)", flush=True)
        except Exception as e:
            print(f"    [!!] Cycle {cycle_num} Tasq: Could not load: {e}", flush=True)
    else:
        print(f"    [--] Cycle {cycle_num} Tasq: Not found", flush=True)

    # 3. Cycle 1 tasq (always included as big-picture anchor)
    cycle1_tasq_content = ""
    cycle1_tasq_path = tasq_dir / "cyqle1_tasq.md"
    if cycle_num != '1' and cycle1_tasq_path.exists():
        try:
            with open(cycle1_tasq_path, 'r', encoding='utf-8') as f:
                cycle1_tasq_content = f.read()
            if len(cycle1_tasq_content) > 6000:
                cycle1_tasq_content = cycle1_tasq_content[:6000] + "\n[...truncated...]"
            print(f"    [ok] Cycle 1 Tasq (anchor): {cycle1_tasq_path} ({len(cycle1_tasq_content)} chars)", flush=True)
        except Exception as e:
            print(f"    [!!] Cycle 1 Tasq: Could not load: {e}", flush=True)

    # 4. QODEYARD (PRIMARY truth source for current-cycle code)
    qodeyard_files = []
    if qodeyard_path.is_dir():
        for root, _, files in os.walk(qodeyard_path):
            for file in files:
                fpath = str(Path(root) / file)
                qodeyard_files.append(fpath)
        print(f"    [ok] qodeyard/*: {len(qodeyard_files)} files (PRIMARY truth — current-cycle code)", flush=True)
        for qf in qodeyard_files[:8]:
            print(f"       + {Path(qf).name}", flush=True)
        if len(qodeyard_files) > 8:
            print(f"       ... and {len(qodeyard_files) - 8} more", flush=True)
    else:
        print(f"    [!!] qodeyard/: Not found — no code to review", flush=True)

    # 5. bloq.d/* (OPTIONAL — may be stale, qompressor runs AFTER inspeqtor)
    bloq_files = []
    if bloq_path.is_dir():
        for root, _, files in os.walk(bloq_path):
            for file in files:
                fpath = str(Path(root) / file)
                bloq_files.append(fpath)
        print(f"    [ok] bloq.d/*: {len(bloq_files)} files (compact context)", flush=True)
        print(f"         NOTE: bloq.d may be stale because qompressor runs after inspeqtor in current pipeline order.", flush=True)
        for bf in bloq_files[:5]:
            print(f"       + {Path(bf).name}", flush=True)
        if len(bloq_files) > 5:
            print(f"       ... and {len(bloq_files) - 5} more", flush=True)
    else:
        print(f"    [--] bloq.d/: Not found (qompressor runs after inspeqtor)", flush=True)

    # 6. qontext.d/* (OPTIONAL — may be stale, qontextor runs AFTER inspeqtor)
    qontext_files = []
    if qontext_path.is_dir():
        for root, _, files in os.walk(qontext_path):
            for file in files:
                fpath = str(Path(root) / file)
                qontext_files.append(fpath)
        print(f"    [ok] qontext.d/*: {len(qontext_files)} files (dependency hints)", flush=True)
        print(f"         NOTE: qontext.d may be stale because qontextor runs after inspeqtor in current pipeline order.", flush=True)
        for qf in qontext_files[:5]:
            print(f"       + {Path(qf).name}", flush=True)
        if len(qontext_files) > 5:
            print(f"       ... and {len(qontext_files) - 5} more", flush=True)
    else:
        print(f"    [--] qontext.d/: Not found (qontextor runs after inspeqtor)", flush=True)

    # Merge: qodeyard is primary, bloq/qontext are supplementary
    all_inspeqtor_context = qodeyard_files + bloq_files + qontext_files
    print(f"    Total context files for InspeQtor: {len(all_inspeqtor_context)} "
          f"(qodeyard: {len(qodeyard_files)}, bloq: {len(bloq_files)}, qontext: {len(qontext_files)})", flush=True)

    # Write context log to struqture/qonsole_inspeqtor.log
    _write_inspeqtor_context_log(
        struqture_dir, cycle_num, qontract_md_path, cycle_tasq_path,
        cycle1_tasq_path, qodeyard_files, bloq_files, qontext_files, all_inspeqtor_context
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 0 (G4.6): QontractGuard (Deterministic, BEFORE AI Review)
    # ═══════════════════════════════════════════════════════════════════════════
    guard_report = None
    guard_passed = True
    qontract_json_path = qontract_dir / "qontract.json"

    print(f"\n--- STAGE 0: QontractGuard (Deterministic — Full Cycle) ---", flush=True)
    if qontract_guard and qontract_json_path.exists():
        try:
            import json as _json
            contract = qontract_guard.load_contract(qontract_json_path)
            if not contract:
                # B) Never silently skip — treat empty/missing as FAIL
                guard_report = qontract_guard.GuardReport(passed=False)
                guard_report.add_violation(qontract_guard.Violation(
                    rule='CONTRACT_MISSING',
                    file_path=str(qontract_json_path),
                    line_number=None,
                    message="Contract loaded but empty — cannot enforce invariants"
                ))
                guard_passed = False
            else:
                guard_report = qontract_guard.run_guard(contract, qodeyard_path)
            guard_passed = guard_report.passed

            # Write guard report (markdown + JSON)
            guard_md_output = reqap_dir / f"cyqle{cycle_num}_qontract_guard.md"
            guard_md_output.parent.mkdir(parents=True, exist_ok=True)
            with open(guard_md_output, 'w', encoding='utf-8') as f:
                f.write(guard_report.to_markdown())

            guard_json_output = reqap_dir / f"cyqle{cycle_num}_qontract_guard.json"
            with open(guard_json_output, 'w', encoding='utf-8') as f:
                _json.dump(guard_report.to_json(), f, indent=2)

            print(f"    Guard report: {guard_md_output}", flush=True)
            print(f"    Guard JSON:   {guard_json_output}", flush=True)

            if not guard_passed:
                print(f"    QontractGuard FAILED — {len(guard_report.violations)} violations", flush=True)
                for v in guard_report.violations[:10]:
                    print(f"       {v}", flush=True)
            else:
                print(f"    QontractGuard PASSED", flush=True)

        except Exception as e:
            print(f"    [WARN] QontractGuard failed to run: {e}", flush=True)
    else:
        # B) Never silently skip — treat missing contract as FAIL
        if not qontract_guard:
            print(f"    [WARN] qontract_guard module not available", flush=True)
        elif not qontract_json_path.exists():
            guard_report = GuardReport(passed=False) if 'GuardReport' in dir() else None
            try:
                guard_report = qontract_guard.GuardReport(passed=False)
                guard_report.add_violation(qontract_guard.Violation(
                    rule='CONTRACT_MISSING',
                    file_path=str(qontract_json_path),
                    line_number=None,
                    message=f"Contract file not found: {qontract_json_path}"
                ))
                guard_passed = False
                print(f"    FAIL — Contract JSON not found at {qontract_json_path}", flush=True)
            except Exception:
                print(f"    FAIL — Contract JSON not found at {qontract_json_path}", flush=True)
                guard_passed = False

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1 (G4.6): LoQal Verification (Deterministic, BEFORE AI Review)
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n--- STAGE 1: LoQal Verification (Syntax/Import Sanity) ---", flush=True)

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

            verification_output = reqap_dir / f"cyqle{cycle_num}" / f"cyqle{cycle_num}_verification.md"
            verification_output.parent.mkdir(parents=True, exist_ok=True)
            with open(verification_output, 'w', encoding='utf-8') as f:
                f.write(verification_report.to_markdown())

            print(f"    Verification report: {verification_output}", flush=True)
            verification_results = verification_report

            if verification_report.errors > 0:
                print(f"    Verification found {verification_report.errors} errors", flush=True)
            else:
                print(f"    Verification passed ({verification_report.passed} checks OK)", flush=True)

        except ImportError:
            print("    [WARN] loqal_verifier module not found — skipping", flush=True)
        except Exception as e:
            print(f"    [WARN] Verification failed: {e}", flush=True)
    else:
        print("    LoQal verification disabled in config", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # DECISION: Should AI InspeQtor run?
    # ═══════════════════════════════════════════════════════════════════════════
    ai_review_mode = "normal"  # "normal" | "report_only" | "skipped"

    if not guard_passed:
        ai_review_mode = "report_only"
        print(f"\n    QontractGuard FAILED — AI InspeQtor will run in REPORT-ONLY mode", flush=True)
        print(f"    (Guard failure forces overall FAIL regardless of AI opinion)", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Per-Briq Tactical Reviews (AI)
    # ═══════════════════════════════════════════════════════════════════════════
    if ai_review_mode != "skipped":
        print(f"\n--- STAGE 2: Per-Briq Tactical Reviews (mode: {ai_review_mode}) ---", flush=True)

        briq_results = run_per_briq_reviews(
            cycle_num,
            briq_dir,
            exeq_dir,
            qodeyard_path,
            qontext_path,
            reqap_dir,
            config
        )
    else:
        print(f"\n--- STAGE 2: Per-Briq Reviews SKIPPED (AI review skipped due to contract failure) ---", flush=True)
        briq_results = []

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: Global Meta-Review (AI Aggregation)
    # ═══════════════════════════════════════════════════════════════════════════
    if ai_review_mode != "skipped":
        print(f"\n--- STAGE 3: Global Meta-Review ---", flush=True)
    else:
        print(f"\n--- STAGE 3: Meta-Review SKIPPED ---", flush=True)
    
    # Read original summary
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary_content = f.read()
    except:
        summary_content = "[Summary not available]"
    
    # Aggregate briq results
    briq_summaries = []
    success_count = 0
    partial_count = 0
    failure_count = 0
    failed_briq_suggestions = []
    
    for result in briq_results:
        if result['assessment'] == '[SUCCESS]':
            success_count += 1
        elif result['assessment'] == '[PARTIAL]':
            partial_count += 1
        else:
            failure_count += 1
        
        try:
            with open(result['reqap_path'], 'r', encoding='utf-8') as f:
                briq_reqap = f.read()
        except:
            briq_reqap = f"Assessment: {result['assessment']}\n\nError: {result.get('error', 'Unknown')}"
        
        if result['assessment'] in ['[FAILURE]', '[PARTIAL]']:
            suggestions_match = re.search(r'## Suggestions\s*\n(.*?)(?=\n##|\Z)', briq_reqap, re.DOTALL)
            if suggestions_match:
                failed_briq_suggestions.append({
                    'briq': result['briq_name'],
                    'assessment': result['assessment'],
                    'suggestions': suggestions_match.group(1).strip()
                })
            else:
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
    
    # Cross-briq consistency check
    cross_briq_warnings = []
    briq_file_map = {}
    all_touched_files = set()
    
    for briq_file in briq_dir.glob(f"cyqle{cycle_num}_*.md"):
        briq_name = briq_file.stem
        try:
            with open(briq_file, 'r', encoding='utf-8') as f:
                briq_content = f.read()
            file_refs = set(re.findall(r'`([^`]+\.\w{2,4})`', briq_content))
            briq_file_map[briq_name] = file_refs
            all_touched_files.update(file_refs)
        except:
            pass
    
    for target_file in all_touched_files:
        touching_briqs = [b for b, files in briq_file_map.items() if target_file in files]
        if len(touching_briqs) > 1:
            cross_briq_warnings.append(f"`{target_file}` touched by multiple briqs: {', '.join(touching_briqs)}")
    
    print(f"\n[CROSS-BRIQ] Found {len(cross_briq_warnings)} potential integration points", flush=True)
    
    # Determine overall assessment
    if failure_count > 0:
        overall_assessment = "[FAILURE]"
    elif partial_count > 0:
        overall_assessment = "[PARTIAL]"
    else:
        overall_assessment = "[SUCCESS]"

    # G4.6: Force FAIL if QontractGuard failed (hard enforcement)
    if guard_report and not guard_passed:
        overall_assessment = "[FAILURE]"
        print(f"[QONTRACT] Guard FAILED — forcing overall assessment to FAILURE", flush=True)

    # Downgrade if verification found errors
    if verification_results and hasattr(verification_results, 'errors') and verification_results.errors > 0:
        if overall_assessment == "[SUCCESS]":
            overall_assessment = "[PARTIAL]"
            print(f"[VERIFY] Verification errors found — downgrading to PARTIAL", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # WRITE FINAL REQAP
    # ═══════════════════════════════════════════════════════════════════════════
    if ai_review_mode == "skipped" or not briq_results:
        _write_guard_only_reqap(
            reqap_path, cycle_num, guard_report, verification_results,
            overall_assessment, qontract_content
        )
    else:
        # Build meta-review prompt
        meta_prompt = f"""You are the 'inspeQtor Meta-Reviewer', synthesizing per-briq code reviews into a final cycle assessment.

**YOUR TASK:**
Aggregate the individual briq reviews into a single, coherent cycle-level assessment. DO NOT re-review code - focus on patterns, themes, and overall quality.

**CRITICAL:** Pay special attention to:
1. FAILED and PARTIAL briqs - their suggestions MUST be prominently included in your output
2. Cross-briq integration warnings - files touched by multiple briqs may have consistency issues
3. Patterns across briqs - recurring problems indicate systemic issues

**INPUTS:**

## Original Cycle Goal
{cycle_tasq_content[:3000]}{'...[truncated]' if len(cycle_tasq_content) > 3000 else ''}

## ConstruQtor Execution Summary
{summary_content[:2000]}{'...[truncated]' if len(summary_content) > 2000 else ''}

## QONTRACT (Project Constitution)
{qontract_content[:2000] if qontract_content else '[No QONTRACT available]'}
{'...[truncated]' if len(qontract_content) > 2000 else ''}
"""

        if guard_report:
            guard_status = "PASS" if guard_report.passed else "FAIL"
            meta_prompt += f"\n## QontractGuard Results: {guard_status}\n"
            if guard_report.violations:
                for v in guard_report.violations[:15]:
                    meta_prompt += f"- {v}\n"
            else:
                meta_prompt += "No contract violations found.\n"

        if verification_results and hasattr(verification_results, 'errors'):
            v_status = "PASS" if verification_results.errors == 0 else "ISSUES"
            meta_prompt += f"\n## LoQal Verification: {v_status}\n"
            meta_prompt += f"Files checked: {verification_results.files_checked}, Errors: {verification_results.errors}, Warnings: {verification_results.warnings}\n"

        meta_prompt += f"\n## Per-Briq Results ({success_count} success, {partial_count} partial, {failure_count} failure)\n\n"

        for briq in briq_summaries:
            truncated_content = briq['content'][:600]
            meta_prompt += f"### {briq['name']}: {briq['assessment']}\n{truncated_content}\n\n"

        if cross_briq_warnings:
            meta_prompt += "## Cross-Briq Warnings\n"
            for w in cross_briq_warnings:
                meta_prompt += f"- {w}\n"
            meta_prompt += "\n"

        if failed_briq_suggestions:
            meta_prompt += "## FAILED/PARTIAL BRIQ SUGGESTIONS (MUST INCLUDE ALL IN OUTPUT)\n\n"
            for item in failed_briq_suggestions:
                meta_prompt += f"### {item['briq']} {item['assessment']}\n{item['suggestions'][:800]}\n\n"

        meta_prompt += f"""
## Overall Preliminary Assessment: {overall_assessment}

**IMPORTANT:** Every suggestion from a FAILED briq must appear in your output. Do not drop or summarize away failure details.

**Begin Meta-Review:**
"""

        meta_input_tokens = estimate_tokens(meta_prompt, config['model'])
        meta_output_tokens = 2000
        meta_input_cost = calculate_cost(meta_input_tokens, config['model'], is_input=True)
        meta_output_cost = calculate_cost(meta_output_tokens, config['model'], is_input=False)
        meta_cost = meta_input_cost + meta_output_cost
        print(f"Estimated cost: {format_cost(meta_cost)} (meta-review @ {config['model']})", flush=True)

        try:
            meta_response = lib_ai.run_ai_completion(
                config['provider'],
                config['model'],
                meta_prompt,
                context_files=[],
                max_prompt_chars=100_000
            )

            final_content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v1.0.4 (Multi-Stage Review: Guard > Verify > AI)

{meta_response}

---
"""

            if guard_report and guard_report.violations:
                final_content += "\n## QontractGuard Violations\n"
                for v in guard_report.violations:
                    final_content += f"- {v}\n"
                final_content += "\n---\n"

            if verification_results and hasattr(verification_results, 'errors'):
                if verification_results.errors > 0 or verification_results.warnings > 0:
                    final_content += _format_verification_section(verification_results)

            if cross_briq_warnings:
                final_content += "\n## Cross-Briq Integration Points\n"
                final_content += "These files were touched by multiple briqs - verify consistency:\n\n"
                for warning in cross_briq_warnings:
                    final_content += f"- {warning}\n"
                final_content += "\n---\n"

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
            _write_fallback_reqap(
                reqap_path, cycle_num, overall_assessment, e,
                success_count, partial_count, failure_count,
                guard_report, verification_results,
                cross_briq_warnings, failed_briq_suggestions
            )

    print(f"\n=== InspeQtor v1.0.4 Complete: {overall_assessment} ===", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (v1.0.4)
# ═══════════════════════════════════════════════════════════════════════════════

def _write_inspeqtor_context_log(
    struqture_dir: Path, cycle_num: str, qontract_path: Path,
    cycle_tasq_path: Path, cycle1_tasq_path: Path,
    qodeyard_files: list, bloq_files: list, qontext_files: list, all_context: list
):
    """Write detailed context log to struqture/qonsole_inspeqtor.log."""
    struqture_dir.mkdir(parents=True, exist_ok=True)
    log_path = struqture_dir / "qonsole_inspeqtor.log"

    lines = [
        f"=== InspeQtor Context Log — Cycle {cycle_num} ===",
        "",
        "--- Explicit Paths ---",
        f"QONTRACT:      {qontract_path} (exists: {qontract_path.exists()})",
        f"Cycle Tasq:    {cycle_tasq_path} (exists: {cycle_tasq_path.exists()})",
        f"Cycle 1 Tasq:  {cycle1_tasq_path} (exists: {cycle1_tasq_path.exists()})",
        "",
        f"--- qodeyard/* ({len(qodeyard_files)} files) — PRIMARY truth source ---",
    ]
    for qf in qodeyard_files[:30]:
        lines.append(f"  + {qf}")
    if len(qodeyard_files) > 30:
        lines.append(f"  ... and {len(qodeyard_files) - 30} more")

    lines.append(f"\n--- bloq.d/* ({len(bloq_files)} files) — OPTIONAL, may be stale ---")
    lines.append("NOTE: bloq.d may be stale because qompressor runs after inspeqtor in current pipeline order.")
    for bf in bloq_files[:20]:
        lines.append(f"  + {bf}")
    if len(bloq_files) > 20:
        lines.append(f"  ... and {len(bloq_files) - 20} more")

    lines.append(f"\n--- qontext.d/* ({len(qontext_files)} files) — OPTIONAL, may be stale ---")
    lines.append("NOTE: qontext.d may be stale because qontextor runs after inspeqtor in current pipeline order.")
    for qf in qontext_files[:20]:
        lines.append(f"  + {qf}")
    if len(qontext_files) > 20:
        lines.append(f"  ... and {len(qontext_files) - 20} more")

    lines.append(f"\n--- Total Context: {len(all_context)} files ---")
    lines.append("=== End Context Log ===\n")

    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"    Context log: {log_path}", flush=True)


def _write_guard_only_reqap(
    reqap_path: Path, cycle_num: str, guard_report, verification_results,
    overall_assessment: str, qontract_content: str
):
    """Write a reqap when AI review was skipped due to guard failure."""
    content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v1.0.4 (Guard-Only Mode — AI review skipped due to contract failure)

## Assessment: {overall_assessment}

**AI review skipped due to contract failure.** The QontractGuard detected violations that must
be fixed before AI review can provide meaningful feedback.

"""
    if guard_report and guard_report.violations:
        content += "## QontractGuard Violations (MUST FIX)\n\n"
        for v in guard_report.violations:
            content += f"- {v}\n"
        content += "\n"

    if verification_results and hasattr(verification_results, 'errors') and verification_results.errors > 0:
        content += _format_verification_section(verification_results)

    content += "\n## Next Steps\n\n"
    content += "1. Fix all QontractGuard violations listed above\n"
    content += "2. Ensure code passes local syntax verification\n"
    content += "3. Re-run the cycle to get full AI review\n"

    os.makedirs(reqap_path.parent, exist_ok=True)
    with open(reqap_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"ReQap (guard-only): {reqap_path}", flush=True)


def _write_fallback_reqap(
    reqap_path: Path, cycle_num: str, overall_assessment: str, error,
    success_count: int, partial_count: int, failure_count: int,
    guard_report, verification_results,
    cross_briq_warnings: list, failed_briq_suggestions: list
):
    """Write a fallback reqap when meta-review AI call fails."""
    fallback_content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v1.0.4 (Fallback Mode - Meta-review failed)

Assessment: {overall_assessment}

## Summary
Meta-review failed with error: {error}

Per-briq results: Success: {success_count} | Partial: {partial_count} | Failure: {failure_count}

"""
    if guard_report and guard_report.violations:
        fallback_content += "## QontractGuard Violations\n"
        for v in guard_report.violations:
            fallback_content += f"- {v}\n"
        fallback_content += "\n"

    if verification_results and hasattr(verification_results, 'errors') and verification_results.errors > 0:
        fallback_content += _format_verification_section(verification_results)

    if cross_briq_warnings:
        fallback_content += "## Cross-Briq Integration Points\n"
        for warning in cross_briq_warnings:
            fallback_content += f"- {warning}\n"
        fallback_content += "\n"

    if failed_briq_suggestions:
        fallback_content += "## Failed/Partial Briq Suggestions (MUST ADDRESS)\n"
        for item in failed_briq_suggestions:
            fallback_content += f"\n### {item['briq']} {item['assessment']}\n"
            fallback_content += f"{item['suggestions']}\n"
        fallback_content += "\n"

    fallback_content += f"## Next Steps\n- Review individual briq reqaps in `reqap.d/cyqle{cycle_num}/`\n"

    os.makedirs(reqap_path.parent, exist_ok=True)
    with open(reqap_path, 'w', encoding='utf-8') as f:
        f.write(fallback_content)


def _format_verification_section(verification_results) -> str:
    """Format verification results for inclusion in reqap."""
    section = f"""
---

## LoQal Verification Results

**Status:** {verification_results.overall_status}
**Checked:** {verification_results.files_checked} files
**Results:** Passed: {verification_results.passed} | Warnings: {verification_results.warnings} | Errors: {verification_results.errors}

"""
    errors = [r for r in verification_results.results if not r.passed and r.severity == 'error']
    if errors:
        section += "### Errors (MUST FIX)\n\n"
        for r in errors:
            line_info = f" (line {r.line_number})" if r.line_number else ""
            section += f"- **{r.file_path}**{line_info}: [{r.check_type}] {r.message}\n"
        section += "\n"

    warnings = [r for r in verification_results.results if not r.passed and r.severity == 'warning']
    if warnings:
        section += "### Warnings\n\n"
        for r in warnings:
            line_info = f" (line {r.line_number})" if r.line_number else ""
            section += f"- **{r.file_path}**{line_info}: [{r.check_type}] {r.message}\n"
        section += "\n"

    return section


if __name__ == '__main__':
    main()
