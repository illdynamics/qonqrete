#!/usr/bin/env python3
# worqer/construqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# ConstruQtor Agent - Code Generation with Contract-Aware Retries
# v1.2.2-stable - QONTRACT + Cycle1 Tasq Context Wiring
# ═══════════════════════════════════════════════════════════════════════════════
#
# CHANGELOG v1.2.2-stable:
# - BULLETPROOF language detection: 400+ language identifiers (GitHub Linguist,
#   OpenAI, Claude, Gemini, DeepSeek, Qwen outputs all covered)
# - SMART filename validation: distinguishes real files from language keywords
# - KNOWN extensionless files: Dockerfile, Makefile, go.mod, etc.
# - INFRA-AS-CODE support: tf, tfvars, hcl, ansible, puppet, kubernetes, helm
# - MULTI-PROVIDER tested: OpenAI, Gemini, Claude, DeepSeek, Qwen all safe
# - Interleaved per-briq generation with contract-aware retries
# - Fail-fast or fail-tolerant modes
# - Per-briq exeQ summaries generated during construction
#
# NO MORE "py" OR "js" FILES BEING CREATED! 🎉
#
# ═══════════════════════════════════════════════════════════════════════════════
import sys
import os
import yaml
import re
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
    from mode_policy import (
        extract_scope_class,
        load_mode_policy,
        render_construqtor_directives,
    )
except ImportError:
    print("CRITICAL: lib_ai.py not found.", flush=True)
    sys.exit(1)

# v1.0.4: Import QontractGuard for per-briq contract gating
try:
    import qontract_guard
except ImportError:
    qontract_guard = None


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_RETRY_CONFIG = {
    'enabled': True,
    'max_attempts': 3,
    'stop_on_briq_fail': False,
    'retry_delay': 2,
}


def load_config(config_path: Path) -> dict:
    """Load configuration from config.yaml."""
    config = {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        pass
    return config


def get_retry_config(config: dict) -> dict:
    """Extract retry configuration with defaults."""
    retry_cfg = config.get('retry', {})
    result = DEFAULT_RETRY_CONFIG.copy()
    for key in DEFAULT_RETRY_CONFIG:
        if key in retry_cfg:
            result[key] = retry_cfg[key]
    return result

def get_mode_persona(mode: str, scope_class: str) -> str:
    policy = load_mode_policy(mode)
    return render_construqtor_directives(policy, scope_class)


# ═══════════════════════════════════════════════════════════════════════════════
# BRIQ PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def process_briq_interleaved(
    briq_file: Path,
    qodeyard_path: Path,
    exeq_dir: Path,
    all_context_files: list[str],
    context_type: str,
    mode: str,
    mode_prompt: str,
    ai_provider: str,
    ai_model: str,
    retry_config: dict,
    constitutional_context: str = "",  # v1.0.4: QONTRACT + cycle1 tasq
    contract_data: dict = None,          # v1.0.4: Loaded contract dict
    timeout: int = None,
    provider_options: dict = None
) -> dict:
    """
    Process a single briq with interleaved generation + guard retries.
    
    Flow:
    1. Build briq (generate code)
    2. v1.0.4: If contract-relevant, run QontractGuard on written files
    3. If guard fails → auto-retry with correction directive (max 2-3 attempts)
    4. Write per-briq exeQ summary
    
    Returns:
        {
            'briq_file': str,
            'status': 'success' | 'partial' | 'failure',
            'written_files': list[str],
            'guard_report': dict | None,
            'attempts': int,
            'error': str | None,
            'exeq_path': str
        }
    """
    briq_name = briq_file.stem
    max_attempts = retry_config['max_attempts'] if retry_config['enabled'] else 1
    retry_delay = retry_config['retry_delay']
    result = {
        'briq_file': briq_file.name,
        'status': 'failure',
        'written_files': [],
        'guard_report': None,
        'attempts': 0,
        'error': None,
        'exeq_path': None
    }
    
    # Read briq content
    try:
        with open(briq_file, 'r', encoding='utf-8') as f:
            briq_content = f.read()
    except Exception as e:
        result['error'] = f"Could not read briq: {e}"
        return result
    
    # v1.0.4: Parse Contract-Relevant header from briq
    is_contract_relevant = False
    if re.search(r'^Contract-Relevant:\s*yes', briq_content, re.MULTILINE | re.IGNORECASE):
        is_contract_relevant = True
    
    scope_class = extract_scope_class(briq_content, briq_name)
    mode_prompt = get_mode_persona(mode, scope_class)

    # Build prompt
    prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan defined in the 'briq'.
**CONTEXT:** You have been provided with the {context_type} of the existing codebase. Use this structural context to ensure your generated code integrates correctly with the existing project.
**ABSOLUTE DIRECTIVE:** ALL code output MUST be written to the `qodeyard/` directory.
**OUTPUT FORMAT:** You MUST format your response using markdown code blocks. Each file must have its path specified after the language in the format `language:path/to/file.ext`.
{constitutional_context}
**MANDATORY NAMING CONVENTIONS (STRICT):**
All function and method names MUST follow these verb prefixes for deterministic mapping:
- `get_`, `fetch_`, `load_`, `read_`, `retrieve_`, `find_`, `lookup_`, `query_`, `select_` → Data retrieval
- `set_`, `update_`, `modify_`, `patch_`, `change_` → Data modification
- `is_`, `has_`, `can_`, `should_`, `check_`, `verify_`, `validate_` → Boolean checks
- `create_`, `make_`, `build_`, `generate_`, `init_`, `initialize_` → Object creation
- `delete_`, `remove_`, `destroy_`, `drop_`, `clear_`, `purge_` → Data removal
- `parse_`, `convert_`, `transform_`, `translate_`, `map_`, `encode_`, `decode_` → Data transformation
- `send_`, `emit_`, `dispatch_`, `publish_`, `broadcast_`, `notify_` → Event emission
- `handle_`, `process_`, `consume_`, `accept_`, `on_` → Event handling
- `save_`, `store_`, `persist_`, `write_`, `commit_`, `export_` → Data persistence
- `render_`, `display_`, `show_`, `draw_`, `present_`, `format_` → Output rendering

**EXAMPLE:**
```python:qodeyard/main.py
print("Hello, World!")
```

**RESTRICTION:** GENERATE ONLY THE FILE BLOCKS AS SHOWN IN THE EXAMPLE. Do not add any other text, conversation, or explanations outside the markdown blocks.

**MODE:** {mode.upper()}
{mode_prompt}

**Plan (from Briq):**
{briq_content}
"""
    
    # v1.0.4: Track correction directive for guard retries
    guard_correction = ""
    
    # Retry loop with contract-aware regeneration
    for attempt in range(1, max_attempts + 1):
        result['attempts'] = attempt
        
        if attempt > 1:
            print(f"     [RETRY] Attempt {attempt}/{max_attempts}", flush=True)
            time.sleep(retry_delay)
        
        try:
            # STEP 1: Build (AI code generation)
            # v1.0.4: Include guard correction directive if retrying due to contract violation
            current_prompt = prompt
            if guard_correction:
                current_prompt = prompt + guard_correction
                print(f"     [GUARD] Including correction directive in prompt", flush=True)
            
            print(f"     - Sending to AI (attempt {attempt})...", flush=True)
            
            ai_result = lib_ai.run_ai_completion(
                ai_provider, 
                ai_model, 
                current_prompt, 
                context_files=all_context_files,
                timeout=timeout,
                provider_options=provider_options
            )
            
            if not ai_result or "```" not in ai_result:
                result['error'] = "AI returned no code blocks"
                continue
            
            # Write files
            written_files = _write_ai_output_to_qodeyard(ai_result, qodeyard_path)
            result['written_files'] = written_files
            
            if not written_files:
                result['error'] = "No files were written"
                continue
            
            # STEP 2: ConstruQtor stops after code generation; Qualifier owns validation.
            build_passed = True

            # STEP 2.5 (v1.0.4): Per-Briq QontractGuard Gate
            guard_correction = ""  # Reset for next iteration
            if is_contract_relevant and qontract_guard and contract_data and build_passed:
                print(f"     [GUARD] Running QontractGuard (contract-relevant briq)...", flush=True)
                briq_guard = qontract_guard.run_guard_for_files(
                    contract_data, qodeyard_path, written_files
                )
                result['guard_report'] = briq_guard.to_json()
                
                if not briq_guard.passed:
                    error_count = len([v for v in briq_guard.violations if v.severity == 'error'])
                    print(f"     [GUARD] ❌ FAIL — {error_count} contract violations", flush=True)
                    for v in briq_guard.violations[:5]:
                        loc = f" (line {v.line_number})" if v.line_number else ""
                        print(f"            [{v.rule}] {v.file_path}{loc}: {v.message}", flush=True)
                    
                    if attempt < max_attempts:
                        # Build correction directive for retry
                        guard_correction = briq_guard.get_correction_directive(contract_data)
                        result['error'] = f"QontractGuard: {error_count} contract violations"
                        build_passed = False
                    else:
                        # Max retries exhausted — mark as failure
                        result['error'] = f"QontractGuard: {error_count} violations (retries exhausted)"
                        build_passed = False
                else:
                    print(f"     [GUARD] ✅ Passed", flush=True)
            
            # STEP 3: Determine result
            if build_passed:
                result['status'] = 'success'
                result['error'] = None
                break
            else:
                # Try again if we have attempts left
                if attempt >= max_attempts:
                    result['status'] = 'failure'
                    
        except Exception as e:
            result['error'] = str(e)
            print(f"     [ERROR] Attempt {attempt} failed: {e}", flush=True)
    
    # STEP 5: Write per-briq exeQ summary
    exeq_path = exeq_dir / f"{briq_name}_exeq.md"
    exeq_content = generate_briq_exeq(briq_name, briq_content, result)
    
    try:
        exeq_dir.mkdir(parents=True, exist_ok=True)
        with open(exeq_path, 'w', encoding='utf-8') as f:
            f.write(exeq_content)
        result['exeq_path'] = str(exeq_path)
        print(f"     - Wrote exeQ: {exeq_path.name}", flush=True)
    except Exception as e:
        print(f"     [WARN] Could not write exeQ: {e}", flush=True)
    
    return result


def generate_briq_exeq(briq_name: str, briq_content: str, result: dict) -> str:
    """Generate a per-briq exeQ summary markdown file."""
    status_emoji = "✅" if result['status'] == 'success' else ("⚠️" if result['status'] == 'partial' else "❌")
    
    exeq = f"""# Briq ExeQ: {briq_name}
Generated by ConstruQtor v1.1.0 (Generation + Change Tracking)

## Assessment: {status_emoji} [{result['status'].upper()}]

**Attempts:** {result['attempts']}
**Files Written:** {len(result['written_files'])}

"""
    
    if result['error']:
        exeq += f"**Error:** {result['error']}\n\n"
    
    # Files
    if result['written_files']:
        exeq += "## Generated Files\n\n"
        for f in result['written_files']:
            exeq += f"- `{f}`\n"
        exeq += "\n"
    
    # v1.0.4: QontractGuard results
    guard = result.get('guard_report')
    if guard:
        guard_status = guard.get('status', 'N/A')
        guard_emoji = "✅" if guard_status == 'PASS' else "❌"
        exeq += f"## 🛡️ QontractGuard: {guard_emoji} {guard_status}\n\n"
        violations = guard.get('violations', [])
        if violations:
            exeq += f"**Violations:** {len(violations)}\n\n"
            for v in violations:
                loc = f" (line {v.get('line', '')})" if v.get('line') else ""
                exeq += f"- [{v.get('rule_id', '?')}] {v.get('file', '?')}{loc}: {v.get('message', '?')}\n"
            exeq += "\n"
    
    # Original briq (truncated)
    exeq += "## Original Briq\n\n"
    exeq += "<details>\n<summary>Click to expand</summary>\n\n"
    exeq += briq_content[:2000]
    if len(briq_content) > 2000:
        exeq += "\n\n[...truncated...]"
    exeq += "\n</details>\n"
    
    return exeq


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) != 4:
        print("Usage: construqtor.py <input_dir> <summary_output> <changed_files_output>", flush=True)
        sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    changed_files_summary_file = Path(sys.argv[3])
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"

    # Load configuration
    config = load_config(worqspace_root / 'config.yaml')
    retry_config = get_retry_config(config)
    
    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro')
    ai_timeout = agent_cfg.get('timeout')
    ai_provider_options = agent_cfg.get(ai_provider) if ai_provider == 'llamacpp' else None
    
    use_qompressor = config.get('options', {}).get('use_qompressor', True)
    
    mode_policy = load_mode_policy(os.environ.get('QONQ_MODE', 'program'))
    mode = mode_policy.semantic_mode
    mode_prompt = ''  # per-briq scope prompt is computed inside process_briq_interleaved

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briqs found for pattern {pattern}", flush=True)
        sys.exit(1)

    # Determine context source
    bloq_path = worqspace_root / "bloq.d"
    context_source_path = bloq_path if use_qompressor and bloq_path.is_dir() else qodeyard_path
    context_type = "code skeletons from `bloq.d/`" if use_qompressor else "full source code from `qodeyard/`"

    all_context_files = []
    if context_source_path.is_dir():
        for root, _, files in os.walk(context_source_path):
            for file in files:
                all_context_files.append(str(Path(root) / file))

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.0.4: QONTRACT.D + CYCLE1 TASQ + QONTEXT.D CONTEXT WIRING
    # ═══════════════════════════════════════════════════════════════════════════
    qontract_path = worqspace_root / "qontract.d"
    qontext_path = worqspace_root / "qontext.d"
    tasq_dir = worqspace_root / "tasq.d"

    # B) Fail-fast: contract must exist for cycles > 1
    cycle_num_val = os.environ.get('CYCLE_NUM', '1')
    if cycle_num_val != '1':
        try:
            from runtime_checks import ensure_qontract_present
            ensure_qontract_present(worqspace_root)
            print(f"    ✅ Contract present (fail-fast check passed)", flush=True)
        except RuntimeError as e:
            print(f"    ❌ {e}", flush=True)
            sys.exit(1)
        except ImportError:
            pass  # Module not yet available in some test contexts

    # Load QONTRACT (always included — from qontract.d/)
    qontract_content = ""
    qontract_md_path = qontract_path / "qontract.md"
    if qontract_md_path.exists():
        try:
            with open(qontract_md_path, 'r', encoding='utf-8') as f:
                qontract_content = f.read()
            print(f"    QONTRACT: Loaded ({len(qontract_content)} chars)", flush=True)
        except Exception as e:
            print(f"    QONTRACT: ⚠️ Could not load: {e}", flush=True)
    else:
        print(f"    QONTRACT: Not found at {qontract_md_path}", flush=True)

    # Load cycle1 tasq (always included as big-picture anchor)
    cycle1_tasq_content = ""
    cycle1_tasq_path = tasq_dir / "cyqle1_tasq.md"
    if cycle1_tasq_path.exists():
        try:
            with open(cycle1_tasq_path, 'r', encoding='utf-8') as f:
                cycle1_tasq_content = f.read()
            # Truncate if very large but keep meaningful context
            if len(cycle1_tasq_content) > 8000:
                cycle1_tasq_content = cycle1_tasq_content[:8000] + "\n\n[...truncated for token budget...]"
            print(f"    Cycle1 Tasq: Loaded ({len(cycle1_tasq_content)} chars)", flush=True)
        except Exception as e:
            print(f"    Cycle1 Tasq: ⚠️ Could not load: {e}", flush=True)
    else:
        print(f"    Cycle1 Tasq: Not found (cycle 1 in progress)", flush=True)

    # Load qontext.d dependency/relationship files
    qontext_extra_files = []
    if qontext_path.is_dir():
        for root, _, files in os.walk(qontext_path):
            for file in files:
                fpath = str(Path(root) / file)
                if fpath not in all_context_files:
                    qontext_extra_files.append(fpath)

    # Generate struqture tree summary
    struqture_tree = ""
    tree_path = worqspace_root / "struqture" / "tree.txt"
    if tree_path.exists():
        try:
            with open(tree_path, 'r', encoding='utf-8') as f:
                struqture_tree = f.read()
        except:
            pass
    if not struqture_tree and qodeyard_path.is_dir():
        # Generate a quick tree from qodeyard
        tree_lines = ["qodeyard/"]
        for root, dirs, files in os.walk(qodeyard_path):
            level = len(Path(root).relative_to(qodeyard_path).parts)
            indent = "  " * level
            tree_lines.append(f"{indent}{Path(root).name}/")
            for f in sorted(files)[:20]:
                tree_lines.append(f"{indent}  {f}")
        struqture_tree = "\n".join(tree_lines[:100])

    # Merge all context sources for ConstruQtor
    # Priority: qontract files + qontext.d files + bloq.d/qodeyard files
    merged_context_files = qontext_extra_files + all_context_files

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.0.4: CONTEXT LOGGING
    # ═══════════════════════════════════════════════════════════════════════════
    included_count = len(merged_context_files)
    excluded_reasons = []
    if not qontract_md_path.exists():
        excluded_reasons.append("qontract.md: not found")
    if not cycle1_tasq_path.exists():
        excluded_reasons.append("cyqle1_tasq.md: not found")

    print(f"    Context files: {included_count} total", flush=True)
    if included_count > 0:
        shown = min(10, included_count)
        for cf in merged_context_files[:shown]:
            print(f"      + {Path(cf).name}", flush=True)
        if included_count > shown:
            print(f"      ... and {included_count - shown} more", flush=True)
    if excluded_reasons:
        for reason in excluded_reasons:
            print(f"      ✗ {reason}", flush=True)

    # Setup exeQ directory for per-briq execution summaries
    exeq_briq_dir = worqspace_root / "exeq.d" / f"cyqle{cycle_num}"
    exeq_briq_dir.mkdir(parents=True, exist_ok=True)

    # Processing stats
    all_results = []
    all_written_files = []
    success_count = 0
    partial_count = 0
    failure_count = 0
    
    stop_on_fail = retry_config['stop_on_briq_fail']
    stopped_early = False

    print(f"--- ConstruQtor v1.1.0: Processing {len(briq_files)} Briqs (Generation Only) ---", flush=True)
    print(f"    Retry: {'enabled' if retry_config['enabled'] else 'disabled'} | Max attempts: {retry_config['max_attempts']}", flush=True)

    # v1.0.4: Build constitutional context string for prompts
    constitutional_parts = []
    if qontract_content:
        constitutional_parts.append(f"\n**PROJECT CONSTITUTION (QONTRACT — MUST OBEY):**\n{qontract_content}\n")
    if cycle1_tasq_content:
        constitutional_parts.append(f"\n**BIG-PICTURE CONTEXT (Cycle 1 Tasq):**\n{cycle1_tasq_content}\n")
    if struqture_tree:
        constitutional_parts.append(f"\n**PROJECT STRUCTURE:**\n```\n{struqture_tree}\n```\n")
    constitutional_context = "\n".join(constitutional_parts)

    # v1.0.4: Load contract data for per-briq QontractGuard gate
    qontract_json_path = qontract_path / "qontract.json"
    contract_data = None
    if qontract_json_path.exists() and qontract_guard:
        try:
            contract_data = qontract_guard.load_contract(qontract_json_path)
            if contract_data:
                print(f"    QontractGuard: Loaded contract for per-briq gating", flush=True)
        except Exception as e:
            print(f"    QontractGuard: ⚠️ Could not load contract: {e}", flush=True)

    for briq_file in briq_files:
        print(f"\n-- Processing Briq: {briq_file.name} --", flush=True)
        
        result = process_briq_interleaved(
            briq_file,
            qodeyard_path,
            exeq_briq_dir,
            merged_context_files,
            context_type,
            mode,
            mode_prompt,
            ai_provider,
            ai_model,
            retry_config,
            constitutional_context=constitutional_context,
            contract_data=contract_data,
            timeout=ai_timeout,
            provider_options=ai_provider_options
        )
        
        all_results.append(result)
        all_written_files.extend(result['written_files'])
        
        if result['status'] == 'success':
            success_count += 1
            status_str = f"✅ SUCCESS"
        elif result['status'] == 'partial':
            partial_count += 1
            status_str = f"⚠️ PARTIAL"
        else:
            failure_count += 1
            status_str = f"❌ FAILURE"
        
        print(f"-- Briq Complete: {briq_file.name} [{status_str}] (attempts: {result['attempts']}) --", flush=True)
        
        # Check stop_on_briq_fail
        if result['status'] == 'failure' and stop_on_fail:
            print(f"\n[STOP] stop_on_briq_fail=true, halting cycle after {briq_file.name}", flush=True)
            stopped_early = True
            break

    # Determine overall status
    if failure_count > 0:
        final_status = "Failure"
    elif partial_count > 0:
        final_status = "Partial"
    else:
        final_status = "Success"

    if stopped_early:
        final_status = "Halted"

    # --- Write Main Summary File ---
    summary_content = f"# Execution Summary (ConstruQtor v1.1.0 - Generation + Change Tracking)\n\n"
    summary_content += f"**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(all_results)}/{len(briq_files)} briqs\n"
    summary_content += f"**Results:** ✅ {success_count} | ⚠️ {partial_count} | ❌ {failure_count}\n\n"
    
    if stopped_early:
        summary_content += f"⚠️ **Cycle halted early due to `stop_on_briq_fail=true`**\n\n"
    
    summary_content += "## Briq Details\n\n"
    for result in all_results:
        status_emoji = "✅" if result['status'] == 'success' else ("⚠️" if result['status'] == 'partial' else "❌")
        summary_content += f"### {result['briq_file']}: {status_emoji} {result['status']}\n"
        summary_content += f"- Attempts: {result['attempts']}\n"
        summary_content += f"- Files: {len(result['written_files'])}\n"
        if result['exeq_path']:
            summary_content += f"- ExeQ: `{Path(result['exeq_path']).name}`\n"
        if result['error']:
            summary_content += f"- Error: {result['error']}\n"
        
        
        summary_content += "\n"

    # Failed briqs section
    failed_briqs = [r for r in all_results if r['status'] == 'failure']
    if failed_briqs:
        summary_content += "## ❌ Failed Briqs (Require Attention)\n\n"
        for fb in failed_briqs:
            summary_content += f"### {fb['briq_file']}\n"
            summary_content += f"- Attempts: {fb['attempts']}\n"
            summary_content += f"- Error: {fb['error']}\n"
            summary_content += "\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)

    # --- Write Changed Files Summary ---
    changed_files_content = "# Changed Files\n\n"
    for f_name in sorted(list(set(all_written_files))):
        changed_files_content += f"- `{f_name}`\n"
        
    os.makedirs(changed_files_summary_file.parent, exist_ok=True)
    with open(changed_files_summary_file, 'w', encoding='utf-8') as f:
        f.write(changed_files_content)

    print(f"\n--- ConstruQtor v1.2.2 Complete: {final_status} ---", flush=True)
    print(f"    Per-briq exeQ summaries written to: exeq.d/cyqle{cycle_num}/", flush=True)


if __name__ == "__main__":
    main()
