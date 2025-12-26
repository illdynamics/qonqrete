#!/usr/bin/env python3
# worqer/construqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# ConstruQtor Agent - Code Generation with Interleaved Per-Briq Review
# v0.9.0 - Improved Code Block Parsing + Empty File Handling
# ═══════════════════════════════════════════════════════════════════════════════
#
# NEW IN v0.9.0:
# - Interleaved per-briq validation (build briq → validate briq → next briq)
# - Local validation after each briq (syntax, imports)
# - Optional AI quick-review per briq
# - Fail-fast or fail-tolerant modes
# - Per-briq exeQ summaries generated during construction
#
# ═══════════════════════════════════════════════════════════════════════════════
import sys
import os
import yaml
import re
import time
import ast
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: 
    import lib_ai
except ImportError: 
    print("CRITICAL: lib_ai.py not found.", flush=True)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_RETRY_CONFIG = {
    'enabled': True,
    'max_attempts': 3,
    'stop_on_briq_fail': False,
    'retry_delay': 2,
}

DEFAULT_INTERLEAVED_CONFIG = {
    'enabled': True,                    # Enable interleaved build→review
    'local_validation': True,           # Run local syntax/import checks
    'ai_quick_review': False,           # Run lightweight AI review per briq
    'retry_on_review_fail': True,       # Retry build if review fails
}


def load_config(config_path: Path) -> dict:
    """Load configuration from config.yaml."""
    config = {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except:
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


def get_interleaved_config(config: dict) -> dict:
    """Extract interleaved review configuration with defaults."""
    interleaved_cfg = config.get('interleaved', {})
    result = DEFAULT_INTERLEAVED_CONFIG.copy()
    for key in DEFAULT_INTERLEAVED_CONFIG:
        if key in interleaved_cfg:
            result[key] = interleaved_cfg[key]
    return result


def get_mode_persona(mode: str) -> str:
    m = mode.lower()
    if m == 'enterprise': 
        return "Code Style: Enterprise. Add logging, error handling, docstrings, and modular structure."
    if m == 'security': 
        return "Code Style: Security. Validate all inputs, use secure defaults."
    return "Code Style: Functional."


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL VALIDATION (Per-Briq, No AI)
# ═══════════════════════════════════════════════════════════════════════════════

def validate_python_syntax(file_path: Path) -> tuple[bool, str]:
    """Validate Python file syntax using compile()."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        compile(code, str(file_path), 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Validation error: {e}"


def validate_imports(file_path: Path, qodeyard_path: Path) -> list[str]:
    """Check if local imports can be resolved."""
    warnings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code, filename=str(file_path))
        
        # Standard library and common packages to skip
        skip_prefixes = [
            'os', 'sys', 're', 'json', 'yaml', 'time', 'datetime', 'pathlib',
            'typing', 'collections', 'logging', 'subprocess', 'asyncio',
            'hashlib', 'base64', 'uuid', 'math', 'random', 'io', 'shutil',
            'http', 'urllib', 'socket', 'ssl', 'ast', 'inspect',
            'numpy', 'pandas', 'requests', 'flask', 'django',
            'openai', 'anthropic', 'google', 'grpc', 'proto'
        ]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module not in skip_prefixes:
                        # Check if it's a local module
                        local_path = qodeyard_path / (module.replace('.', '/') + '.py')
                        local_pkg = qodeyard_path / module.replace('.', '/') / '__init__.py'
                        if not local_path.exists() and not local_pkg.exists():
                            if module.startswith(('src', 'lib', 'app', 'core', 'utils', 'modules')):
                                warnings.append(f"Import '{alias.name}' may not resolve")
                                
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split('.')[0]
                if module not in skip_prefixes:
                    local_path = qodeyard_path / (module.replace('.', '/') + '.py')
                    local_pkg = qodeyard_path / module.replace('.', '/') / '__init__.py'
                    if not local_path.exists() and not local_pkg.exists():
                        if module.startswith(('src', 'lib', 'app', 'core', 'utils', 'modules')):
                            warnings.append(f"Import from '{node.module}' may not resolve")
                            
    except:
        pass
    
    return warnings


def run_local_validation(written_files: list[str], qodeyard_path: Path) -> dict:
    """
    Run local validation on all written files.
    
    Returns:
        {
            'passed': bool,
            'syntax_errors': list[str],
            'import_warnings': list[str],
            'files_checked': int
        }
    """
    result = {
        'passed': True,
        'syntax_errors': [],
        'import_warnings': [],
        'files_checked': 0
    }
    
    for file_name in written_files:
        file_path = qodeyard_path / file_name
        
        if file_path.suffix == '.py' and file_path.exists():
            result['files_checked'] += 1
            
            # Syntax check
            valid, error = validate_python_syntax(file_path)
            if not valid:
                result['syntax_errors'].append(f"{file_name}: {error}")
                result['passed'] = False
            
            # Import check
            import_warns = validate_imports(file_path, qodeyard_path)
            result['import_warnings'].extend([f"{file_name}: {w}" for w in import_warns])
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# AI QUICK REVIEW (Per-Briq, Lightweight)
# ═══════════════════════════════════════════════════════════════════════════════

def run_ai_quick_review(
    briq_name: str,
    briq_content: str,
    written_files: list[str],
    qodeyard_path: Path,
    provider: str,
    model: str
) -> dict:
    """
    Run a lightweight AI review on the briq's output.
    
    Returns:
        {
            'assessment': '[SUCCESS]' | '[PARTIAL]' | '[FAILURE]',
            'issues': list[str],
            'suggestions': list[str]
        }
    """
    result = {
        'assessment': '[SUCCESS]',
        'issues': [],
        'suggestions': []
    }
    
    # Build code snippets (limited size)
    code_snippets = []
    total_chars = 0
    max_chars = 50000  # Very limited for quick review
    
    for file_name in written_files[:5]:  # Max 5 files
        file_path = qodeyard_path / file_name
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if total_chars + len(content) < max_chars:
                    code_snippets.append(f"### {file_name}\n```\n{content[:5000]}\n```")
                    total_chars += len(content)
            except:
                pass
    
    if not code_snippets:
        return result
    
    prompt = f"""You are a quick code reviewer. Give a BRIEF assessment of this code.

**Briq Task:**
{briq_content[:2000]}

**Generated Code:**
{chr(10).join(code_snippets)}

**Instructions:**
1. Check for obvious bugs, syntax issues, or logic errors
2. Respond in this EXACT format:

Assessment: [SUCCESS/PARTIAL/FAILURE]
Issues: (list any critical issues, or "None")
Suggestions: (1-2 quick improvements, or "None")

Keep it brief - max 200 words total.
"""
    
    try:
        response = lib_ai.run_ai_completion(
            provider, model, prompt,
            context_files=[],
            max_prompt_chars=60000
        )
        
        # Parse response
        if '[FAILURE]' in response:
            result['assessment'] = '[FAILURE]'
        elif '[PARTIAL]' in response:
            result['assessment'] = '[PARTIAL]'
        else:
            result['assessment'] = '[SUCCESS]'
        
        # Extract issues
        issues_match = re.search(r'Issues?:\s*(.+?)(?=Suggestions?:|$)', response, re.DOTALL | re.IGNORECASE)
        if issues_match:
            issues_text = issues_match.group(1).strip()
            if issues_text.lower() != 'none':
                result['issues'] = [line.strip().lstrip('- ') for line in issues_text.split('\n') if line.strip() and line.strip() != '-']
        
        # Extract suggestions
        sugg_match = re.search(r'Suggestions?:\s*(.+?)$', response, re.DOTALL | re.IGNORECASE)
        if sugg_match:
            sugg_text = sugg_match.group(1).strip()
            if sugg_text.lower() != 'none':
                result['suggestions'] = [line.strip().lstrip('- ') for line in sugg_text.split('\n') if line.strip() and line.strip() != '-']
                
    except Exception as e:
        print(f"     [WARN] AI quick review failed: {e}", flush=True)
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CODE GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def _write_ai_output_to_qodeyard(result: str, qodeyard: Path) -> list[str]:
    """
    Parse AI markdown output and write code blocks to qodeyard.
    
    Returns:
        List of written file paths (relative to qodeyard)
    """
    qodeyard.mkdir(parents=True, exist_ok=True)
    written_files = []
    
    language_keywords = {
        'python', 'javascript', 'typescript', 'html', 'css', 'json', 'yaml', 'yml',
        'sh', 'bash', 'go', 'rust', 'java', 'c', 'cpp', 'csharp', 'sql', 'ruby',
        'dockerfile', 'makefile', 'toml', 'ini', 'conf', 'nginx', 'proto'
    }

    # Pattern to find markdown code blocks with filenames
    # Use [^`] to prevent matching across code blocks (don't allow ``` inside content)
    pattern = re.compile(r"```(?:\w+:)?([\w\./-]+)?\s*\n((?:[^`]|`(?!``))*)\n?```", re.DOTALL)
    matches = pattern.findall(result)

    if not matches:
        # Fallback to simpler pattern if no matches
        pattern = re.compile(r"```(?:\w+:)?([\w\./-]+)?\s*\n(.*?)\n```", re.DOTALL)
        matches = pattern.findall(result)

    if not matches:
        return written_files

    for filename, code_content in matches:
        if not filename:
            continue
            
        # Skip if filename is just a language keyword
        if filename.lower() in language_keywords:
            continue

        # Clean the content
        code_content = code_content.strip() if code_content else ""
        
        # Skip if content is empty, just backticks, or starts with markdown fence
        if not code_content:
            print(f"     [SKIP] Empty file: {filename}", flush=True)
            continue
        if code_content.startswith('```') or code_content == '```':
            print(f"     [SKIP] Invalid content (markdown fence): {filename}", flush=True)
            continue
        if len(code_content) < 3:
            print(f"     [SKIP] Content too short ({len(code_content)} chars): {filename}", flush=True)
            continue
        
        # CRITICAL: Skip if content contains Qompressor skeleton markers
        # This prevents AI from copying skeleton context back into qodeyard
        skeleton_markers = [
            "# ... (body stripped by Qompressor) ...",
            "// ... (body stripped by Qompressor) ...",
            "/* ... (body stripped by Qompressor) ... */",
            "(body stripped by Qompressor)"
        ]
        if any(marker in code_content for marker in skeleton_markers):
            print(f"     [SKIP] Skeleton detected (not overwriting): {filename}", flush=True)
            continue

        # Sanitize filename
        if filename.strip().startswith('qodeyard/'):
            filename = filename.strip()[len('qodeyard/'):]

        qodeyard_abs = qodeyard.resolve()
        proposed_path = qodeyard_abs.joinpath(filename.strip())
        proposed_abs = proposed_path.resolve()

        # Security check
        if not str(proposed_abs).startswith(str(qodeyard_abs)):
            print(f"     [WARN] Skipping unsafe path: {filename}", flush=True)
            continue
        
        full_path = proposed_abs
        safe_filename = full_path.relative_to(qodeyard_abs)
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code_content, encoding='utf-8')
        
        written_files.append(str(safe_filename))
        print(f"     - Wrote [Code] {safe_filename}", flush=True)

    return written_files


# ═══════════════════════════════════════════════════════════════════════════════
# PER-BRIQ PROCESSING WITH INTERLEAVED REVIEW
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
    interleaved_config: dict,
    review_provider: str = None,
    review_model: str = None
) -> dict:
    """
    Process a single briq with interleaved build + review.
    
    Flow:
    1. Build briq (generate code)
    2. Run local validation (syntax, imports)
    3. Optionally run AI quick review
    4. If validation/review fails and retry enabled, go back to step 1
    5. Write per-briq exeQ summary
    
    Returns:
        {
            'briq_file': str,
            'status': 'success' | 'partial' | 'failure',
            'written_files': list[str],
            'validation': dict,
            'review': dict,
            'attempts': int,
            'error': str | None,
            'exeq_path': str
        }
    """
    briq_name = briq_file.stem
    max_attempts = retry_config['max_attempts'] if retry_config['enabled'] else 1
    retry_delay = retry_config['retry_delay']
    do_local_validation = interleaved_config['local_validation']
    do_ai_review = interleaved_config['ai_quick_review']
    retry_on_review_fail = interleaved_config['retry_on_review_fail']
    
    result = {
        'briq_file': briq_file.name,
        'status': 'failure',
        'written_files': [],
        'validation': {},
        'review': {},
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
    
    # Build prompt
    prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan defined in the 'briq'.
**CONTEXT:** You have been provided with the {context_type} of the existing codebase. Use this structural context to ensure your generated code integrates correctly with the existing project.
**ABSOLUTE DIRECTIVE:** ALL code output MUST be written to the `qodeyard/` directory.
**OUTPUT FORMAT:** You MUST format your response using markdown code blocks. Each file must have its path specified after the language in the format `language:path/to/file.ext`.

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
    
    # Retry loop with interleaved review
    for attempt in range(1, max_attempts + 1):
        result['attempts'] = attempt
        
        if attempt > 1:
            print(f"     [RETRY] Attempt {attempt}/{max_attempts}", flush=True)
            time.sleep(retry_delay)
        
        try:
            # STEP 1: Build (AI code generation)
            print(f"     - Sending to AI (attempt {attempt})...", flush=True)
            
            ai_result = lib_ai.run_ai_completion(
                ai_provider, 
                ai_model, 
                prompt, 
                context_files=all_context_files
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
            
            # STEP 2: Local Validation (LoQal Verifier - part of InspeQtor)
            build_passed = True
            
            if do_local_validation:
                print(f"     [LoQal] Running validation...", flush=True)
                validation = run_local_validation(written_files, qodeyard_path)
                result['validation'] = validation
                
                if validation['syntax_errors']:
                    print(f"     [LoQal] ❌ Syntax errors found:", flush=True)
                    for err in validation['syntax_errors'][:3]:
                        print(f"            {err}", flush=True)
                    result['error'] = f"{len(validation['syntax_errors'])} syntax errors"
                    build_passed = False
                elif validation['import_warnings']:
                    print(f"     [LoQal] ⚠️ Import warnings: {len(validation['import_warnings'])}", flush=True)
                else:
                    print(f"     [LoQal] ✅ Passed", flush=True)
            
            # STEP 3: AI Quick Review (optional)
            if do_ai_review and build_passed:
                print(f"     - Running AI quick review...", flush=True)
                review = run_ai_quick_review(
                    briq_name,
                    briq_content,
                    written_files,
                    qodeyard_path,
                    review_provider or ai_provider,
                    review_model or ai_model
                )
                result['review'] = review
                
                print(f"     - Review: {review['assessment']}", flush=True)
                
                if review['assessment'] == '[FAILURE]':
                    if retry_on_review_fail and attempt < max_attempts:
                        result['error'] = "AI review failed"
                        build_passed = False
                    else:
                        # Accept with issues noted
                        pass
            
            # STEP 4: Determine result
            if build_passed:
                if result.get('validation', {}).get('import_warnings'):
                    result['status'] = 'partial'
                    result['error'] = "Import warnings"
                elif result.get('review', {}).get('assessment') == '[PARTIAL]':
                    result['status'] = 'partial'
                    result['error'] = "Review partial"
                else:
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
Generated by ConstruQtor v0.9.0 (Interleaved Pipeline)

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
    
    # Validation results
    validation = result.get('validation', {})
    if validation:
        exeq += "## Local Validation\n\n"
        exeq += f"**Files Checked:** {validation.get('files_checked', 0)}\n"
        exeq += f"**Passed:** {'✅ Yes' if validation.get('passed', True) else '❌ No'}\n\n"
        
        if validation.get('syntax_errors'):
            exeq += "### Syntax Errors\n\n"
            for err in validation['syntax_errors']:
                exeq += f"- {err}\n"
            exeq += "\n"
        
        if validation.get('import_warnings'):
            exeq += "### Import Warnings\n\n"
            for warn in validation['import_warnings']:
                exeq += f"- {warn}\n"
            exeq += "\n"
    
    # AI Review results
    review = result.get('review', {})
    if review:
        exeq += f"## AI Quick Review: {review.get('assessment', 'N/A')}\n\n"
        
        if review.get('issues'):
            exeq += "### Issues\n\n"
            for issue in review['issues']:
                exeq += f"- {issue}\n"
            exeq += "\n"
        
        if review.get('suggestions'):
            exeq += "### Suggestions\n\n"
            for sugg in review['suggestions']:
                exeq += f"- {sugg}\n"
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
    interleaved_config = get_interleaved_config(config)
    
    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro')
    use_qompressor = config.get('options', {}).get('use_qompressor', True)
    
    # InspeQtor config for reviews
    inspeqtor_cfg = config.get('agents', {}).get('inspeqtor', {})
    review_provider = inspeqtor_cfg.get('provider', ai_provider)
    review_model = inspeqtor_cfg.get('model', ai_model)

    mode = os.environ.get('QONQ_MODE', 'enterprise')
    mode_prompt = get_mode_persona(mode)

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

    print(f"--- ConstruQtor v0.9.0: Processing {len(briq_files)} Briqs (Interleaved) ---", flush=True)
    print(f"    Retry: {'enabled' if retry_config['enabled'] else 'disabled'} | Max attempts: {retry_config['max_attempts']}", flush=True)
    print(f"    Interleaved: {'enabled' if interleaved_config['enabled'] else 'disabled'} | Local validation: {interleaved_config['local_validation']} | AI review: {interleaved_config['ai_quick_review']}", flush=True)

    for briq_file in briq_files:
        print(f"\n-- Processing Briq: {briq_file.name} --", flush=True)
        
        result = process_briq_interleaved(
            briq_file,
            qodeyard_path,
            exeq_briq_dir,
            all_context_files,
            context_type,
            mode,
            mode_prompt,
            ai_provider,
            ai_model,
            retry_config,
            interleaved_config,
            review_provider,
            review_model
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
    summary_content = f"# Execution Summary (ConstruQtor v0.9.0 - Interleaved Pipeline)\n\n"
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
        
        # Validation summary
        validation = result.get('validation', {})
        if validation.get('syntax_errors'):
            summary_content += f"- Syntax Errors: {len(validation['syntax_errors'])}\n"
        if validation.get('import_warnings'):
            summary_content += f"- Import Warnings: {len(validation['import_warnings'])}\n"
        
        # Review summary
        review = result.get('review', {})
        if review.get('assessment'):
            summary_content += f"- AI Review: {review['assessment']}\n"
        
        summary_content += "\n"

    # Failed briqs section
    failed_briqs = [r for r in all_results if r['status'] == 'failure']
    if failed_briqs:
        summary_content += "## ❌ Failed Briqs (Require Attention)\n\n"
        for fb in failed_briqs:
            summary_content += f"### {fb['briq_file']}\n"
            summary_content += f"- Attempts: {fb['attempts']}\n"
            summary_content += f"- Error: {fb['error']}\n"
            if fb.get('validation', {}).get('syntax_errors'):
                summary_content += f"- Syntax errors:\n"
                for err in fb['validation']['syntax_errors']:
                    summary_content += f"  - {err}\n"
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

    print(f"\n--- ConstruQtor v0.9.0 Complete: {final_status} ---", flush=True)
    print(f"    Per-briq exeQ summaries written to: exeq.d/cyqle{cycle_num}/", flush=True)


if __name__ == "__main__":
    main()
