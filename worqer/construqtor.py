#!/usr/bin/env python3
# worqer/construqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# ConstruQtor Agent - Code Generation with Interleaved Per-Briq Review
# v1.0.4-stable - QONTRACT + Cycle1 Tasq Context Wiring
# ═══════════════════════════════════════════════════════════════════════════════
#
# CHANGELOG v1.0.0-stable:
# - BULLETPROOF language detection: 400+ language identifiers (GitHub Linguist,
#   OpenAI, Claude, Gemini, DeepSeek, Qwen outputs all covered)
# - SMART filename validation: distinguishes real files from language keywords
# - KNOWN extensionless files: Dockerfile, Makefile, go.mod, etc.
# - INFRA-AS-CODE support: tf, tfvars, hcl, ansible, puppet, kubernetes, helm
# - MULTI-PROVIDER tested: OpenAI, Gemini, Claude, DeepSeek, Qwen all safe
# - Interleaved per-briq validation (build briq → validate briq → next briq)
# - Local validation after each briq (syntax, imports)
# - Optional AI quick-review per briq
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
import ast
import json
import shutil
import subprocess
import hashlib
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: 
    import lib_ai
except ImportError: 
    print("CRITICAL: lib_ai.py not found.", flush=True)
    sys.exit(1)

# v1.0.4: Import QontractGuard for per-briq contract gating
try:
    import qontract_guard
except ImportError:
    qontract_guard = None

try:
    from lib_security import safe_write_file
except ImportError:
    safe_write_file = None


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

DEFAULT_WRITE_STRATEGY = {
    'mode': 'staged_atomic_per_attempt',
    'recovery_policy': 'snapshot_before_commit',
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


def get_write_strategy_config(config: dict) -> dict:
    strategy_cfg = config.get('write_strategy', {})
    result = DEFAULT_WRITE_STRATEGY.copy()
    for key in DEFAULT_WRITE_STRATEGY:
        if key in strategy_cfg:
            result[key] = strategy_cfg[key]
    return result


def canonical_run_id(worqspace_root: Path) -> str:
    return os.environ.get('QONQ_LEGACY_QAGE_ID') or worqspace_root.name


def load_repair_context(worqspace_root: Path) -> str:
    if os.environ.get("QONQ_REPAIR_MODE") != "1":
        return ""
    repair_plan_path = os.environ.get("QONQ_REPAIR_PLAN_PATH")
    if not repair_plan_path:
        return ""
    try:
        payload = json.loads(Path(repair_plan_path).read_text(encoding='utf-8'))
    except Exception:
        return ""
    lines = [
        "**EXPLICIT REPAIR MODE:** This build is a bounded targeted repair pass.",
        f"**Repair Pass Index:** {payload.get('repair_pass_index')}",
        f"**Repair Reason:** {payload.get('repair_reason_summary', 'Targeted repair required.')}",
        "**Repair Constraints:**",
    ]
    for item in payload.get("repair_constraints", []):
        lines.append(f"- {item}")
    lines.append("**Required Actions:**")
    for item in payload.get("required_actions", []):
        lines.append(f"- {item}")
    lines.append("**Target Build Groups:**")
    for item in payload.get("target_build_groups", []):
        lines.append(f"- {item}")
    lines.append("**Target Briqs:**")
    for item in payload.get("target_briq_files", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


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
            'constraint_errors': list[str],
            'import_warnings': list[str],
            'files_checked': int
        }
    """
    result = {
        'passed': True,
        'syntax_errors': [],
        'constraint_errors': [],
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
        elif file_path.suffix == '.sh' and file_path.exists():
            result['files_checked'] += 1

            shell_check = subprocess.run(
                ['sh', '-n', str(file_path)],
                capture_output=True,
                text=True,
            )
            if shell_check.returncode != 0:
                result['syntax_errors'].append(
                    f"{file_name}: {shell_check.stderr.strip() or 'shell syntax check failed'}"
                )
                result['passed'] = False

            if file_name == 'run.sh':
                try:
                    shell_content = file_path.read_text(encoding='utf-8')
                except Exception as exc:
                    result['constraint_errors'].append(f"{file_name}: could not read run.sh ({exc})")
                    result['passed'] = False
                    continue

                if "python -m uvicorn main:app --reload --port" not in shell_content:
                    result['constraint_errors'].append(
                        f"{file_name}: must launch exactly `python -m uvicorn main:app --reload --port $PORT`"
                    )
                if not re.search(r'--port\s+["\']?\$PORT["\']?|--port\s+["\']?\$\{PORT\}["\']?', shell_content):
                    result['constraint_errors'].append(
                        f"{file_name}: uvicorn command must pass the PORT variable instead of a literal value"
                    )
                if re.search(r'--port\s+\d+', shell_content):
                    result['constraint_errors'].append(
                        f"{file_name}: hardcoded numeric port literal found in uvicorn command"
                    )
                if re.search(r'PORT\s*[:=+-]*\s*[\'"]?\d+[\'"]?', shell_content):
                    result['constraint_errors'].append(
                        f"{file_name}: hardcoded numeric PORT assignment found; derive PORT without duplicating the literal from main.py"
                    )

                if result['constraint_errors']:
                    result['passed'] = False
        elif file_path.suffix == '.json' and file_path.exists():
            result['files_checked'] += 1
            try:
                json.loads(file_path.read_text(encoding='utf-8'))
            except Exception as exc:
                result['syntax_errors'].append(f"{file_name}: JSON parse error ({exc})")
                result['passed'] = False
        elif file_path.suffix in {'.yaml', '.yml'} and file_path.exists():
            result['files_checked'] += 1
            try:
                yaml.safe_load(file_path.read_text(encoding='utf-8'))
            except Exception as exc:
                result['syntax_errors'].append(f"{file_name}: YAML parse error ({exc})")
                result['passed'] = False
        elif file_path.suffix == '.toml' and file_path.exists():
            result['files_checked'] += 1
            if tomllib is None:
                result['import_warnings'].append(
                    f"{file_name}: TOML parser unavailable in current runtime; deterministic parse check skipped"
                )
            else:
                try:
                    tomllib.loads(file_path.read_text(encoding='utf-8'))
                except Exception as exc:
                    result['syntax_errors'].append(f"{file_name}: TOML parse error ({exc})")
                    result['passed'] = False

    return result


def build_validation_correction_directive(validation: dict) -> str:
    errors = validation.get('constraint_errors', []) + validation.get('syntax_errors', [])
    if not errors:
        return ""
    bullets = "\n".join(f"- {item}" for item in errors[:10])
    return f"""

CRITICAL RETRY CORRECTION:
The previous output failed deterministic local validation. Regenerate the affected files and fix all of these issues exactly:
{bullets}

For `run.sh`, do not duplicate the numeric port literal from `main.py`. Derive the shell `PORT` value from `main.py` or the environment, then pass `$PORT` to uvicorn.
Return only corrected file blocks.
"""


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_execution_backend(provider: str, model: str) -> dict:
    provider_value = (provider or "unknown").lower()
    model_value = (model or "unknown").lower()
    backend_kind = "reasoning_model"
    backend_family = provider_value or "unknown"
    engine_id = f"{provider or 'unknown'}:{model or 'unknown'}"

    if provider_value == "local" and "codex" in model_value:
        backend_kind = "codex_style_scoped_execution_engine"
        backend_family = "codex"
    elif "codex" in provider_value or "codex" in model_value:
        backend_kind = "codex_style_scoped_execution_engine"
        backend_family = "codex"
    elif provider_value in {"openai", "anthropic", "gemini", "deepseek", "qwen", "openrouter", "llamacpp", "ollama"}:
        backend_kind = "llm_patch_generation_engine"

    return {
        "engine_id": engine_id,
        "backend_kind": backend_kind,
        "backend_family": backend_family,
        "scope_enforcement_model": "qonqrete_manifest_scoped_execution",
        "orchestration_authority": "qrane_manifest_runtime",
        "authority_disclosure": "Execution backend may generate or apply scoped file payloads, but planning and orchestration authority remain outside the backend.",
    }


def parse_briq_metadata(briq_content: str) -> dict:
    metadata = {}
    for line in briq_content.splitlines():
        if not line.strip():
            break
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        metadata[key.strip().lower()] = value.strip()
    return metadata


def extract_briq_target_files(briq_content: str) -> list[str]:
    targets = []
    for candidate in re.findall(r'`([^`]+)`', briq_content):
        if "/" in candidate or re.search(r"\.\w+$", candidate):
            targets.append(candidate)
    for candidate in re.findall(r'\b[\w./-]+\.(?:py|sh|txt|json|ya?ml|toml|md)\b', briq_content):
        targets.append(candidate)
    return sorted(set(targets))


def select_briq_context_files(
    all_context_files: list[str],
    briq_targets: list[str],
    qontext_path: Path,
) -> list[str]:
    filtered_context_files: list[str] = []
    if briq_targets and qontext_path.exists():
        try:
            filtered_context_files = lib_ai.filter_context_by_relevance(
                all_context_files,
                briq_targets,
                str(qontext_path),
                max_neighbors=1,
            )
        except Exception:
            filtered_context_files = []

    if filtered_context_files:
        target_names = {Path(target).name for target in briq_targets}
        for ctx_file in all_context_files:
            if Path(ctx_file).name.replace(".q.yaml", "") in target_names:
                filtered_context_files.append(ctx_file)
        return sorted(dict.fromkeys(filtered_context_files))

    preferred_exact = {"main.py", "run.sh", "requirements.txt", "pyproject.toml", "package.json"}
    preferred_suffixes = {".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt"}
    fallback_files: list[str] = []
    for ctx_file in all_context_files:
        path = Path(ctx_file)
        name = path.name
        suffix = path.suffix.lower()
        if name.endswith(".q.yaml") or suffix == ".md" or name.startswith("."):
            continue
        if name in preferred_exact or suffix in preferred_suffixes:
            fallback_files.append(ctx_file)

    if not fallback_files:
        fallback_files = [
            ctx_file
            for ctx_file in all_context_files
            if not Path(ctx_file).name.endswith(".q.yaml") and Path(ctx_file).suffix.lower() != ".md"
        ]
    if not fallback_files:
        fallback_files = list(all_context_files[:6])
    return sorted(dict.fromkeys(fallback_files[:8]))


def build_group_context(metadata: dict, planning_payload: dict, component_contracts_payload: dict) -> str:
    build_groups = {
        item.get('build_group_id'): item
        for item in planning_payload.get('items', [])
        if item.get('build_group_id')
    }
    component_contracts = {
        item.get('component_id'): item
        for item in component_contracts_payload.get('items', [])
        if item.get('component_id')
    }
    build_group_id = metadata.get('build-group')
    component_id = metadata.get('component-id')
    group = build_groups.get(build_group_id, {})
    component = component_contracts.get(component_id, {})

    if not build_group_id and not component_id:
        return ""

    lines = [
        "",
        "**GROUPED BUILD CONTRACT (MUST RESPECT):**",
        f"- Build Group: {build_group_id or 'n/a'}",
        f"- Scope ID: {metadata.get('scope-id', 'n/a')}",
        f"- Component ID: {component_id or 'n/a'}",
    ]
    if group.get('objective'):
        lines.append(f"- Group Objective: {group['objective']}")
    if group.get('validation_focus'):
        lines.append(f"- Group Validation Focus: {', '.join(group['validation_focus'])}")
    if component.get('summary'):
        lines.append(f"- Component Summary: {component['summary']}")
    if component.get('dependencies'):
        lines.append(f"- Component Dependencies: {', '.join(component['dependencies'])}")
    if component.get('constraints'):
        lines.append("- Component Constraints:")
        for item in component['constraints'][:6]:
            lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


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
            max_prompt_chars=60000,
            prompt_sections=[{
                'label': f'quick_review:{briq_name}',
                'content': prompt,
                'required': True,
                'loss_policy': 'preserve',
                'section_type': 'quick_review',
            }],
            agent_name='construqtor',
            task_type='review',
            output_tokens=500,
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

def _extract_ai_output_files(result: str, qodeyard: Path) -> dict[str, str]:
    """Parse AI markdown output into relative qodeyard file payloads."""
    extracted_files: dict[str, str] = {}

    # ═══════════════════════════════════════════════════════════════════════════
    # ULTIMATE LANGUAGE KEYWORDS SET v1.0.0
    # Comprehensive set of ALL language identifiers that AI models might output
    # This prevents creating files named "py", "js", "ts", etc.
    # Sources: GitHub Linguist, OpenAI, Claude, Gemini, DeepSeek, Qwen outputs
    # ═══════════════════════════════════════════════════════════════════════════
    language_keywords = {
        # ═══ PYTHON (OpenAI loves "py" instead of "python:path") ═══
        'python', 'py', 'py3', 'pyw', 'pyi', 'pyc', 'pyx', 'pxd', 'pxi',
        'python3', 'python2', 'ipython', 'cython', 'pyrex', 'jython',
        'pypy', 'ironpython', 'pythonw', 'sage', 'sagemath',
        'gyp', 'lmi', 'pyde', 'pyp', 'pyt', 'rusthon', 'tac', 'wsgi', 'xpy',
        'numpy', 'numpyw', 'numsc', 'pytb',
        
        # ═══ JAVASCRIPT/TYPESCRIPT (very common shorthand variants) ═══
        'javascript', 'js', 'jsx', 'mjs', 'cjs', 'es6', 'es5', 'es7',
        'ecmascript', 'node', 'nodejs', 'njs', 'ssjs', 'sjs',
        'typescript', 'ts', 'tsx', 'mts', 'cts', 'd.ts',
        'coffeescript', 'coffee', 'cjsx', 'cson', 'iced', '_coffee',
        'livescript', 'ls', '_ls',
        'bones', 'jsb', 'jsfl', 'jsm', 'jss', 'pac', 'jake',
        'sublime-build', 'sublime-commands', 'sublime-completions',
        'sublime-keymap', 'sublime-macro', 'sublime-menu', 'sublime-mousemap',
        'sublime-project', 'sublime-settings', 'sublime-theme',
        'sublime-workspace', 'sublime_metrics', 'sublime_session',
        'xsjs', 'xsjslib', 'gs', 'frag',
        
        # ═══ RUST ═══
        'rust', 'rs', 'rlib',
        
        # ═══ GO ═══
        'go', 'golang',
        
        # ═══ RUBY ═══
        'ruby', 'rb', 'rbw', 'rbx', 'ru', 'rake', 'gemspec', 'god',
        'jbuilder', 'jruby', 'macruby', 'mspec', 'pluginspec', 'podspec',
        'rabl', 'rbuild', 'builder', 'thor', 'watchr', 'irbrc',
        
        # ═══ JAVA/KOTLIN/SCALA ═══
        'java', 'jar', 'jsp', 'jspx', 'jspf',
        'kotlin', 'kt', 'ktm', 'kts',
        'scala', 'sc', 'sbt',
        'groovy', 'grt', 'gtpl', 'gvy', 'gsp',
        'clojure', 'clj', 'cljs', 'cljc', 'cljx', 'cl2', 'edn', 'hic',
        
        # ═══ C/C++/C# ═══
        'c', 'h', 'cats', 'idc', 'w',
        'cpp', 'cc', 'cp', 'cxx', 'c++', 'hpp', 'hh', 'hxx', 'h++',
        'inl', 'ipp', 'tcc', 'tpp',
        'csharp', 'c#', 'cs', 'cshtml', 'csx', 'cake',
        'fsharp', 'f#', 'fs', 'fsi', 'fsx',
        'objectivec', 'objective-c', 'objc', 'obj-c', 'm',
        'objectivecpp', 'objective-c++', 'objc++', 'obj-c++', 'mm',
        
        # ═══ SWIFT/DART/FLUTTER ═══
        'swift',
        'dart', 'flutter',
        
        # ═══ PHP ═══
        'php', 'php3', 'php4', 'php5', 'php7', 'php8', 'phps', 'phpt',
        'phtml', 'ctp', 'inc', 'aw', 'fcgi',
        
        # ═══ SHELL/BASH ═══
        'bash', 'sh', 'shell', 'zsh', 'ksh', 'csh', 'tcsh', 'fish',
        'command', 'bats', 'tmux', 'ash', 'dash',
        'powershell', 'ps1', 'psd1', 'psm1', 'posh',
        'batchfile', 'bat', 'batch', 'cmd', 'dosbatch', 'winbatch',
        
        # ═══ WEB MARKUP/STYLING ═══
        'html', 'htm', 'xhtml', 'xht', 'html5', 'st',
        'css', 'css3', 'scss', 'sass', 'less', 'stylus', 'styl',
        'xml', 'xsl', 'xslt', 'xsd', 'dtd', 'rss', 'atom', 'rdf',
        'svg', 'svgz', 'mathml',
        'haml', 'slim', 'pug', 'jade', 'ejs', 'erb', 'rhtml',
        'liquid', 'mustache', 'handlebars', 'hbs', 'htmlbars',
        'jinja', 'jinja2', 'twig', 'nunjucks', 'njk',
        'vue', 'svelte', 'astro', 'mdx',
        
        # ═══ DATA FORMATS ═══
        'json', 'json5', 'jsonc', 'jsonld', 'geojson', 'topojson',
        'yaml', 'yml', 'raml',
        'toml',
        'xml', 'plist', 'csproj', 'vbproj', 'fsproj', 'vcxproj',
        'csv', 'tsv', 'psv',
        'ini', 'cfg', 'conf', 'config', 'cnf', 'properties', 'prefs',
        'env', 'dotenv',
        'lock', 'lockfile',
        
        # ═══ INFRASTRUCTURE AS CODE (Terraform, Ansible, etc.) ═══
        'terraform', 'tf', 'tfvars', 'tfstate',
        'hcl', 'nomad', 'sentinel', 'packer',
        'ansible', 'ansible-playbook', 'playbook',
        'puppet', 'pp',
        'chef', 'berkshelf',
        'saltstack', 'salt', 'sls',
        'vagrant', 'vagrantfile',
        'cloudformation', 'cfn', 'sam',
        'pulumi',
        'kubernetes', 'k8s', 'helm', 'kustomize',
        
        # ═══ CI/CD & DEVOPS ═══
        'github-actions', 'workflow', 'gitlab-ci', 'circleci',
        'jenkins', 'jenkinsfile', 'groovy-pipeline',
        'drone', 'travis', 'azure-pipelines', 'bitbucket-pipelines',
        'argo', 'argocd', 'flux',
        
        # ═══ DOCKER/CONTAINERS ═══
        'dockerfile', 'docker', 'docker-compose', 'containerfile',
        'podman', 'buildah', 'skopeo',
        
        # ═══ DATABASE/SQL ═══
        'sql', 'mysql', 'postgresql', 'postgres', 'pgsql', 'plpgsql', 'plsql',
        'sqlite', 'sqlite3', 'oracle', 'mssql', 'tsql', 't-sql',
        'cassandra', 'cql', 'hql', 'sparql', 'graphql', 'gql',
        'mongodb', 'mongo', 'redis', 'elasticsearch', 'es',
        'ddl', 'dml', 'prc', 'tab', 'udf', 'viw', 'pkb', 'pks', 'plb', 'pls',
        
        # ═══ DOCUMENTATION/MARKUP ═══
        'markdown', 'md', 'mkd', 'mkdn', 'mkdown', 'mdown', 'mdwn', 'mdtxt',
        'rst', 'restructuredtext', 'rest',
        'asciidoc', 'adoc', 'asc', 'asciidoctor',
        'org', 'orgmode', 'org-mode',
        'tex', 'latex', 'ltx', 'sty', 'cls', 'bib', 'bibtex',
        'pod', 'rdoc', 'textile', 'creole', 'mediawiki', 'wiki',
        'man', 'groff', 'nroff', 'troff', 'roff',
        'mermaid', 'plantuml', 'graphviz', 'dot', 'gv',
        
        # ═══ FUNCTIONAL/ML LANGUAGES ═══
        'haskell', 'hs', 'hsc', 'lhs',
        'ocaml', 'ml', 'mli', 'mll', 'mly', 'eliom',
        'fsharp', 'f#', 'fs', 'fsi', 'fsx',
        'elm',
        'purescript', 'purs',
        'erlang', 'erl', 'hrl', 'escript',
        'elixir', 'ex', 'exs', 'eex', 'heex', 'leex',
        'lisp', 'lsp', 'cl', 'el', 'elisp', 'emacs', 'emacs-lisp',
        'scheme', 'scm', 'ss', 'sld', 'sls', 'sps',
        'racket', 'rkt', 'rktd', 'rktl', 'scrbl',
        'clojure', 'clj', 'cljs', 'cljc',
        
        # ═══ SYSTEMS/LOW-LEVEL ═══
        'asm', 'assembly', 'nasm', 'masm', 'gas', 's', 'a51',
        'llvm', 'll', 'ir', 'bc',
        'wasm', 'wat', 'wast', 'webassembly',
        'cuda', 'cu', 'cuh',
        'opencl', 'cl',
        'glsl', 'hlsl', 'shader', 'vert', 'frag', 'geom', 'comp',
        'verilog', 'v', 'vh', 'sv', 'svh', 'systemverilog',
        'vhdl', 'vhd', 'vhf', 'vhi', 'vho', 'vhs', 'vht', 'vhw',
        
        # ═══ MOBILE/GAME DEV ═══
        'android', 'gradle', 'proguard',
        'ios', 'xcode', 'xcconfig', 'pbxproj', 'storyboard', 'xib',
        'unity', 'unreal', 'godot', 'gd', 'gdscript', 'tscn', 'tres',
        'lua', 'luau', 'moonscript', 'moon',
        
        # ═══ SCRIPTING/AUTOMATION ═══
        'perl', 'pl', 'pm', 'pod', 't', 'psgi',
        'perl6', 'p6', 'p6l', 'p6m', 'pl6', 'pm6', 'nqp', 'raku',
        'awk', 'gawk', 'mawk', 'nawk',
        'sed',
        'tcl', 'tk', 'itcl', 'itk',
        'vim', 'viml', 'vimscript', 'nvim', 'exrc', 'gvimrc', 'vimrc',
        'emacs', 'elisp', 'el',
        'autohotkey', 'ahk', 'ahkl',
        'autoit', 'au3',
        'applescript', 'scpt', 'osascript',
        
        # ═══ SCIENTIFIC/DATA ═══
        'r', 'rscript', 'rmd', 'rmarkdown', 'rnw', 'snw',
        'julia', 'jl',
        'matlab', 'octave', 'm', 'mat',
        'mathematica', 'wl', 'wls', 'nb', 'cdf', 'mma',
        'sas',
        'stata', 'do', 'ado', 'dta',
        'spss', 'sps', 'sav',
        'fortran', 'f', 'for', 'f77', 'f90', 'f95', 'f03', 'f08', 'fpp',
        'jupyter', 'ipynb', 'notebook',
        
        # ═══ CONFIG/WEBSERVERS ═══
        'nginx', 'nginxconf',
        'apache', 'apacheconf', 'htaccess', 'htpasswd',
        'caddy', 'caddyfile',
        'traefik',
        'haproxy',
        'lighttpd', 'lighty',
        'varnish', 'vcl',
        'squid',
        
        # ═══ PROTOCOLS/SERIALIZATION ═══
        'proto', 'protobuf', 'proto3', 'proto2', 'protocol-buffer',
        'grpc',
        'thrift',
        'avro', 'avsc', 'avdl',
        'capnp', 'capnproto',
        'flatbuffers', 'fbs',
        'msgpack', 'messagepack',
        
        # ═══ API SPECS ═══
        'openapi', 'swagger', 'asyncapi',
        'graphql', 'gql', 'graphqls',
        'wsdl', 'soap', 'wadl',
        
        # ═══ SECURITY/CRYPTO ═══
        'pem', 'crt', 'cer', 'key', 'pub', 'csr', 'pfx', 'p12',
        'gpg', 'asc', 'sig',
        'snort', 'suricata', 'yara',
        
        # ═══ GENERIC MARKERS (AI models use these) ═══
        'code', 'snippet', 'output', 'console', 'terminal', 'result',
        'example', 'sample', 'demo', 'test', 'spec',
        'text', 'txt', 'plain', 'plaintext', 'raw',
        'diff', 'patch', 'unified', 'udiff',
        'log', 'logs', 'syslog',
        'trace', 'traceback', 'stacktrace', 'stack',
        'hex', 'binary', 'bin', 'dump', 'hexdump',
        'ascii', 'ansi',
        'repl', 'interactive', 'session', 'shellsession', 'sh-session',
        'output', 'stdout', 'stderr',
        
        # ═══ MISC LANGUAGES ═══
        'ada', 'adb', 'ads',
        'cobol', 'cob', 'cbl', 'cpy',
        'pascal', 'pas', 'pp', 'dpr', 'lpr',
        'delphi', 'dfm',
        'basic', 'bas', 'vb', 'vbs', 'vba', 'vbnet', 'vb.net',
        'forth', '4th', 'fth',
        'prolog', 'pro', 'plt',
        'smalltalk', 'st', 'squeak',
        'apl', 'dyalog',
        'd', 'di',
        'nim', 'nimrod', 'nims',
        'crystal', 'cr',
        'zig', 'zon',
        'v', 'vlang',
        'odin',
        'beef',
        'haxe', 'hx', 'hxml',
        'reason', 're', 'rei',
        'rescript', 'res', 'resi',
        'ballerina', 'bal',
        'solidity', 'sol', 'vyper', 'vy',
        'move', 'mvir',
        'cairo',
        'mojo', '🔥',
        
        # ═══ TEMPLATING ═══
        'template', 'tmpl', 'tpl', 'j2', 'jinja2',
        
        # ═══ LANGUAGE-SPECIFIC REPL MARKERS ═══
        'python-repl', 'ipython', 'bpython', 'ptpython',
        'node-repl', 'deno-repl',
        'irb', 'pry', 'ruby-repl',
        'ghci', 'hugs',
        'utop', 'ocaml-repl',
        'iex', 'elixir-repl',
        'erl-shell', 'erlang-shell',
        'sbt-console', 'scala-repl', 'ammonite',
        'jshell',
        'cling', 'root-cling',
        'gdb', 'lldb', 'debugger',
    }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # KNOWN EXTENSIONLESS FILENAMES (legitimate files without extensions)
    # ═══════════════════════════════════════════════════════════════════════════
    known_extensionless_files = {
        # Build/Make files
        'dockerfile', 'containerfile', 'makefile', 'gnumakefile', 'bsdmakefile',
        'rakefile', 'gemfile', 'guardfile', 'brewfile', 'berksfile', 'cheffile',
        'thorfile', 'capfile', 'puppetfile', 'podfile', 'fastfile', 'appfile',
        'matchfile', 'gymfile', 'snapfile', 'deliverfile', 'scanfile', 'pluginfile',
        'dangerfile', 'steepfile', 'mintfile',
        'cakefile', 'gruntfile', 'gulpfile', 'jakefile', 'justfile',
        'earthfile', 'tiltfile', 'snakefile', 'sconscript', 'sconstruct',
        'cmakelists', 'cmakelists.txt',
        'meson.build', 'meson_options.txt',
        'build.gradle', 'settings.gradle',
        'pom.xml', 'build.xml', 'ivy.xml',
        'cargo.toml', 'cargo.lock',
        'go.mod', 'go.sum', 'go.work',
        'package.json', 'package-lock.json', 'npm-shrinkwrap.json',
        'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
        'composer.json', 'composer.lock',
        'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt', 'pipfile', 'pipfile.lock',
        'poetry.lock', 'pdm.lock', 'uv.lock',
        'deno.json', 'deno.lock', 'import_map.json',
        'tsconfig.json', 'jsconfig.json',
        'babel.config.js', 'webpack.config.js', 'rollup.config.js', 'vite.config.js',
        'tailwind.config.js', 'postcss.config.js', 'prettier.config.js',
        
        # CI/CD files
        'jenkinsfile', 'procfile', 'passengerfile', 'aptfile',
        '.travis.yml', '.gitlab-ci.yml', '.drone.yml', '.circleci/config.yml',
        'azure-pipelines.yml', 'bitbucket-pipelines.yml',
        'cloudbuild.yaml', 'appveyor.yml',
        
        # Git/VCS files
        '.gitignore', '.gitattributes', '.gitmodules', '.gitconfig', '.gitkeep',
        '.dockerignore', '.npmignore', '.eslintignore', '.prettierignore',
        '.hgignore', '.bzrignore', '.cvsignore', '.svnignore', '.p4ignore',
        '.mailmap', '.gitmessage',
        
        # Config dotfiles
        '.env', '.env.local', '.env.development', '.env.production', '.env.test',
        '.editorconfig', '.browserslistrc', '.nvmrc', '.node-version', '.ruby-version',
        '.python-version', '.tool-versions',
        '.eslintrc', '.prettierrc', '.stylelintrc', '.babelrc', '.swcrc',
        '.yarnrc', '.npmrc', '.huskyrc', '.lintstagedrc',
        '.flake8', '.pylintrc', '.isort.cfg', '.mypy.ini', '.bandit',
        '.rubocop.yml', '.reek.yml', '.rspec', '.standard.yml',
        '.clang-format', '.clang-tidy', '.cmake-format',
        '.rustfmt.toml', 'rustfmt.toml', '.clippy.toml',
        '.golangci.yml', '.goreleaser.yml',
        
        # Documentation files
        'readme', 'readme.md', 'readme.txt', 'readme.rst',
        'changelog', 'changelog.md', 'changes', 'history', 'news',
        'license', 'licence', 'license.md', 'license.txt', 'copying', 'unlicense',
        'contributing', 'contributing.md', 'contributors',
        'authors', 'credits', 'thanks', 'acknowledgments',
        'code_of_conduct', 'code_of_conduct.md', 'conduct',
        'security', 'security.md', 'security.txt',
        'support', 'funding', 'sponsors',
        'codeowners', 'maintainers', 'owners',
        
        # Misc
        'vagrantfile', 'berksfile', 'policyfile',
        'profile', '.profile', '.bash_profile', '.bashrc', '.zshrc', '.zshenv',
        '.vimrc', '.gvimrc', '.exrc', 'init.vim', '.ideavimrc',
        '.emacs', 'init.el', '.spacemacs',
        '.tmux.conf', '.screenrc', '.inputrc',
        '.curlrc', '.wgetrc', '.netrc', '.ssh/config',
        'known_hosts', 'authorized_keys',
        '.htaccess', '.htpasswd',
        'robots.txt', 'sitemap.xml', 'humans.txt', 'ads.txt',
        'manifest.json', 'manifest.webmanifest',
        'firebase.json', 'vercel.json', 'netlify.toml', 'fly.toml',
        'renovate.json', 'dependabot.yml',
    }
    
    def _is_valid_filename(candidate: str) -> bool:
        """
        Check if a candidate string looks like a valid filename rather than a language ID.
        
        A valid filename typically:
        1. Contains a file extension (dot followed by 1-10 alphanumeric chars), OR
        2. Is a known extensionless file (Dockerfile, Makefile, etc.), OR
        3. Contains a path separator with valid path components
        
        Returns True if likely a filename, False if likely a language keyword.
        """
        if not candidate:
            return False
            
        candidate_lower = candidate.lower().strip()
        
        # Check if it's a known extensionless filename
        # Also check the basename for path cases like "app/Dockerfile"
        basename = candidate_lower.split('/')[-1]
        if basename in known_extensionless_files or candidate_lower in known_extensionless_files:
            return True
        
        # Check for file extension pattern: .ext where ext is 1-10 alphanumeric chars
        if re.search(r'\.[a-zA-Z0-9]{1,10}$', candidate):
            return True
        
        # Path with multiple components likely indicates a real file path
        # e.g., "src/utils/helpers" or "config/settings"
        if '/' in candidate and len(candidate.split('/')) >= 2:
            # Additional validation: components should look like identifiers
            parts = candidate.split('/')
            if all(re.match(r'^[a-zA-Z_][a-zA-Z0-9_.-]*$', p) for p in parts if p):
                return True
        
        # Single word without extension or path - likely a language keyword
        return False

    # Pattern to find markdown code blocks with filenames
    # Use [^`] to prevent matching across code blocks (don't allow ``` inside content)
    pattern = re.compile(r"```(?:\w+:)?([\w\./-]+)?\s*\n((?:[^`]|`(?!``))*)\n?```", re.DOTALL)
    matches = pattern.findall(result)

    if not matches:
        # Fallback to simpler pattern if no matches
        pattern = re.compile(r"```(?:\w+:)?([\w\./-]+)?\s*\n(.*?)\n```", re.DOTALL)
        matches = pattern.findall(result)

    if not matches:
        return extracted_files

    for filename, code_content in matches:
        if not filename:
            continue
            
        # Skip if filename is just a language keyword (case-insensitive)
        if filename.lower() in language_keywords:
            continue
            
        # Skip if filename doesn't look like a valid file path
        # This catches edge cases where AI outputs something like "script" or "config"
        if not _is_valid_filename(filename):
            # Only skip if it's also short (single word without path/extension)
            if '/' not in filename and '.' not in filename:
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

        safe_filename = proposed_abs.relative_to(qodeyard_abs)
        extracted_files[str(safe_filename)] = code_content

    return extracted_files


def _write_text(path: Path, content: str, jail: Path | None = None) -> None:
    if safe_write_file:
        safe_write_file(path, content, jail=jail or path.parent)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def stage_attempt_files(
    result: str,
    qodeyard: Path,
    worqspace_root: Path,
    attempt_id: str,
    metadata: dict,
) -> dict:
    qodeyard.mkdir(parents=True, exist_ok=True)
    extracted_files = _extract_ai_output_files(result, qodeyard)
    attempt_root = worqspace_root / "build" / "attempts" / attempt_id
    staging_dir = attempt_root / "staging"
    validation_root = attempt_root / "validation-root"
    recovery_dir = attempt_root / "recovery"
    attempt_root.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    recovery_dir.mkdir(parents=True, exist_ok=True)

    staged_files = []
    file_records = []
    for rel_path, content in extracted_files.items():
        stage_path = staging_dir / rel_path
        _write_text(stage_path, content, jail=attempt_root)
        staged_files.append(rel_path)
        file_records.append({
            "path": rel_path,
            "stage_path": str(stage_path.relative_to(worqspace_root)),
            "content_sha256": sha256_text(content),
            "size_bytes": len(content.encode('utf-8')),
        })
        print(f"     - Staged [Code] {rel_path}", flush=True)

    if validation_root.exists():
        shutil.rmtree(validation_root)
    shutil.copytree(qodeyard, validation_root, dirs_exist_ok=True)
    for rel_path, content in extracted_files.items():
        validation_path = validation_root / rel_path
        validation_path.parent.mkdir(parents=True, exist_ok=True)
        validation_path.write_text(content, encoding='utf-8')

    manifest = {
        "schema_version": "build-attempt.v1",
        "attempt_id": attempt_id,
        "run_id": canonical_run_id(worqspace_root),
        "build_group_id": metadata.get('build-group', 'ungrouped'),
        "scope_id": metadata.get('scope-id', 'scope_unknown'),
        "component_id": metadata.get('component-id', 'unassigned'),
        "write_strategy": "staged_atomic_per_attempt",
        "recovery_policy": "snapshot_before_commit",
        "attempt_status": "staged",
        "staged_files": file_records,
        "commit_summary": {
            "committed_files": [],
            "snapshot_refs": [],
            "commit_state": "not_committed",
        },
    }
    manifest_path = attempt_root / "attempt-manifest.v1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding='utf-8')
    return {
        "attempt_id": attempt_id,
        "attempt_root": attempt_root,
        "staging_dir": staging_dir,
        "validation_root": validation_root,
        "recovery_dir": recovery_dir,
        "manifest_path": manifest_path,
        "staged_files": sorted(staged_files),
        "file_records": file_records,
    }


def finalize_attempt_manifest(
    staged_attempt: dict,
    *,
    status: str,
    committed_files: list[dict] | None = None,
    snapshot_refs: list[str] | None = None,
    failure_reason: str | None = None,
) -> None:
    manifest_path = staged_attempt["manifest_path"]
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        payload = {
            "schema_version": "build-attempt.v1",
            "attempt_id": staged_attempt["attempt_id"],
        }
    payload["attempt_status"] = status
    payload["commit_summary"] = {
        "committed_files": committed_files or [],
        "snapshot_refs": snapshot_refs or [],
        "commit_state": "committed" if committed_files else "not_committed",
    }
    if failure_reason:
        payload["failure_reason"] = failure_reason
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding='utf-8')


def commit_staged_attempt(staged_attempt: dict, qodeyard: Path, worqspace_root: Path) -> list[dict]:
    committed_files = []
    snapshot_refs = []
    for file_record in staged_attempt["file_records"]:
        rel_path = file_record["path"]
        staged_path = staged_attempt["staging_dir"] / rel_path
        target_path = qodeyard / rel_path
        prior_exists = target_path.exists()
        snapshot_ref = None
        prior_sha = None
        if prior_exists:
            prior_bytes = target_path.read_bytes()
            prior_sha = sha256_bytes(prior_bytes)
            snapshot_path = staged_attempt["recovery_dir"] / rel_path
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_bytes(prior_bytes)
            snapshot_ref = str(snapshot_path.relative_to(worqspace_root))
            snapshot_refs.append(snapshot_ref)

        new_content = staged_path.read_text(encoding='utf-8')
        if safe_write_file:
            safe_write_file(target_path, new_content, jail=qodeyard)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(new_content, encoding='utf-8')
        committed_files.append({
            "path": rel_path,
            "change_type": "modified" if prior_exists else "created",
            "attempt_id": staged_attempt["attempt_id"],
            "snapshot_ref": snapshot_ref,
            "prior_exists": prior_exists,
            "prior_sha256": prior_sha,
            "content_sha256": file_record["content_sha256"],
            "commit_state": "committed_atomically",
        })

    recovery_manifest = {
        "schema_version": "recovery-metadata.v1",
        "attempt_id": staged_attempt["attempt_id"],
        "run_id": canonical_run_id(worqspace_root),
        "recovery_policy": "snapshot_before_commit",
        "recovery_available": True,
        "workspace_recovery_scope": "attempt_scoped",
        "snapshots": committed_files,
        "restore_contract": "Restore from build/attempts/<attempt_id>/recovery/ snapshots before retrying outside bounded repair flow.",
    }
    recovery_manifest_path = staged_attempt["attempt_root"] / "recovery-metadata.v1.json"
    recovery_manifest_path.write_text(json.dumps(recovery_manifest, indent=2) + "\n", encoding='utf-8')
    finalize_attempt_manifest(
        staged_attempt,
        status="committed",
        committed_files=committed_files,
        snapshot_refs=snapshot_refs,
    )
    return committed_files


# ═══════════════════════════════════════════════════════════════════════════════
# PER-BRIQ PROCESSING WITH INTERLEAVED REVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def process_briq_interleaved(
    briq_file: Path,
    qodeyard_path: Path,
    worqspace_root: Path,
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
    review_model: str = None,
    constitutional_sections: dict | None = None,
    qontract_json_path: Path = None,   # v1.0.4: Path to qontract.json for per-briq guard
    contract_data: dict = None,         # v1.0.4: Loaded contract dict
    planning_payload: dict = None,
    component_contracts_payload: dict = None,
    write_strategy_config: dict | None = None,
    execution_backend: dict | None = None,
) -> dict:
    """
    Process a single briq with interleaved build + review.
    
    Flow:
    1. Build briq (generate code)
    2. Run local validation (syntax, imports)
    3. v1.0.4: If contract-relevant, run QontractGuard on written files
    4. If guard fails → auto-retry with correction directive (max 2-3 attempts)
    5. Optionally run AI quick review
    6. Write per-briq exeQ summary
    
    Returns:
        {
            'briq_file': str,
            'status': 'success' | 'partial' | 'failure',
            'written_files': list[str],
            'validation': dict,
            'review': dict,
            'guard_report': dict | None,
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
        'guard_report': None,
        'attempts': 0,
        'error': None,
        'exeq_path': None,
        'metadata': {},
        'attempt_records': [],
        'execution_backend': execution_backend or {},
        'write_strategy': (write_strategy_config or {}).get('mode', DEFAULT_WRITE_STRATEGY['mode']),
    }
    
    # Read briq content
    try:
        with open(briq_file, 'r', encoding='utf-8') as f:
            briq_content = f.read()
    except Exception as e:
        result['error'] = f"Could not read briq: {e}"
        return result

    briq_metadata = parse_briq_metadata(briq_content)
    result['metadata'] = briq_metadata

    # v1.0.4: Parse Contract-Relevant header from briq
    is_contract_relevant = False
    if re.search(r'^Contract-Relevant:\s*yes', briq_content, re.MULTILINE | re.IGNORECASE):
        is_contract_relevant = True
    constitutional_sections = constitutional_sections or {}
    grouped_context = build_group_context(
        briq_metadata,
        planning_payload or {},
        component_contracts_payload or {}
    )
    repair_context = load_repair_context(worqspace_root)
    briq_targets = extract_briq_target_files(briq_content)
    qontext_path = worqspace_root / "qontext.d"
    filtered_context_files = select_briq_context_files(all_context_files, briq_targets, qontext_path)
    
    # Build prompt
    core_prompt = f"""You are the 'construQtor'.
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
"""
    prompt_sections = [
        {
            'label': 'construqtor_core',
            'content': core_prompt,
            'required': True,
            'loss_policy': 'preserve',
            'section_type': 'instructions',
        },
        {
            'label': 'briq_plan',
            'content': f"**Plan (from Briq):**\n{briq_content}\n",
            'required': True,
            'loss_policy': 'preserve',
            'section_type': 'task',
            'source_files': [str(briq_file)],
        },
    ]
    if constitutional_sections.get('qontract'):
        prompt_sections.append({
            'label': 'qontract',
            'content': f"**PROJECT CONSTITUTION (QONTRACT — MUST OBEY):**\n{constitutional_sections['qontract']}\n",
            'required': True,
            'loss_policy': 'chunkable',
            'section_type': 'contract',
        })
    if grouped_context.strip():
        prompt_sections.append({
            'label': 'grouped_build_context',
            'content': grouped_context,
            'required': True,
            'loss_policy': 'preserve',
            'section_type': 'build_group_context',
        })
    if repair_context.strip():
        prompt_sections.append({
            'label': 'repair_context',
            'content': repair_context,
            'required': True,
            'loss_policy': 'chunkable',
            'section_type': 'repair_context',
        })
    if constitutional_sections.get('cycle1_tasq'):
        prompt_sections.append({
            'label': 'cycle1_tasq_anchor',
            'content': f"**BIG-PICTURE CONTEXT (Cycle 1 Tasq):**\n{constitutional_sections['cycle1_tasq']}\n",
            'required': False,
            'loss_policy': 'summarizable',
            'section_type': 'task_anchor',
        })
    if constitutional_sections.get('structure_tree'):
        prompt_sections.append({
            'label': 'project_structure_tree',
            'content': f"**PROJECT STRUCTURE:**\n```\n{constitutional_sections['structure_tree']}\n```\n",
            'required': False,
            'loss_policy': 'droppable',
            'section_type': 'structure_tree',
        })
    
    committed_written_files: set[str] = set()

    # Track correction directives for deterministic validation / guard retries.
    retry_correction = ""
    
    # Retry loop with interleaved review
    for attempt in range(1, max_attempts + 1):
        result['attempts'] = attempt
        
        if attempt > 1:
            print(f"Construqtor: repair build for {briq_metadata.get('build-group', 'ungrouped')}", flush=True)
            print(f"     [RETRY] Attempt {attempt}/{max_attempts}", flush=True)
            time.sleep(retry_delay)
        
        try:
            # STEP 1: Build (AI code generation)
            current_prompt = core_prompt
            current_sections = [dict(section) for section in prompt_sections]
            if retry_correction:
                current_sections.append({
                    'label': 'retry_correction',
                    'content': retry_correction,
                    'required': True,
                    'loss_policy': 'preserve',
                    'section_type': 'retry_correction',
                })
                print(f"     [RETRY] Including correction directive in prompt", flush=True)
            retry_correction = ""
            
            print("Construqtor: writing code", flush=True)
            print(f"     - Sending to AI (attempt {attempt})...", flush=True)
            
            ai_result = lib_ai.run_ai_completion(
                ai_provider, 
                ai_model, 
                current_prompt, 
                context_files=filtered_context_files,
                prompt_sections=current_sections,
                agent_name="construqtor",
                task_type="code_generation",
            )
            
            if not ai_result or "```" not in ai_result:
                result['error'] = "AI returned no code blocks"
                continue
            
            attempt_id = f"{canonical_run_id(worqspace_root)}-cyqle{os.environ.get('CYCLE_NUM', '1')}-{briq_name}-attempt{attempt:02d}"
            staged_attempt = stage_attempt_files(
                ai_result,
                qodeyard_path,
                worqspace_root,
                attempt_id,
                briq_metadata,
            )
            result['attempt_records'].append({
                "attempt_id": attempt_id,
                "status": "staged",
                "scope_id": briq_metadata.get('scope-id', 'scope_unknown'),
                "build_group_id": briq_metadata.get('build-group', 'ungrouped'),
                "component_id": briq_metadata.get('component-id', 'unassigned'),
                "staged_files": staged_attempt['staged_files'],
                "manifest_ref": str(staged_attempt['manifest_path'].relative_to(worqspace_root)),
                "recovery_ref": str((staged_attempt['attempt_root'] / 'recovery-metadata.v1.json').relative_to(worqspace_root)),
                "committed_files": [],
            })

            if not staged_attempt['staged_files']:
                result['error'] = "No files were written"
                finalize_attempt_manifest(
                    staged_attempt,
                    status="failed_empty",
                    failure_reason=result['error'],
                )
                result['attempt_records'][-1]['status'] = 'failed_empty'
                continue

            print(f"Construqtor: building group {briq_metadata.get('build-group', 'ungrouped')}", flush=True)
            print(f"Construqtor: updating {staged_attempt['staged_files'][0]}", flush=True)
            
            # STEP 2: Local Validation (LoQal Verifier - part of InspeQtor)
            build_passed = True
            
            if do_local_validation:
                print(f"     [LoQal] Running validation...", flush=True)
                validation = run_local_validation(staged_attempt['staged_files'], staged_attempt['validation_root'])
                result['validation'] = validation
                
                if validation['syntax_errors']:
                    print(f"     [LoQal] ❌ Syntax errors found:", flush=True)
                    for err in validation['syntax_errors'][:3]:
                        print(f"            {err}", flush=True)
                    result['error'] = f"{len(validation['syntax_errors'])} syntax errors"
                    build_passed = False
                    if attempt < max_attempts:
                        retry_correction = build_validation_correction_directive(validation)
                elif validation['constraint_errors']:
                    print(f"     [LoQal] ❌ Constraint errors found:", flush=True)
                    for err in validation['constraint_errors'][:3]:
                        print(f"            {err}", flush=True)
                    result['error'] = f"{len(validation['constraint_errors'])} constraint errors"
                    build_passed = False
                    if attempt < max_attempts:
                        retry_correction = build_validation_correction_directive(validation)
                elif validation['import_warnings']:
                    print(f"     [LoQal] ⚠️ Import warnings: {len(validation['import_warnings'])}", flush=True)
                else:
                    print(f"     [LoQal] ✅ Passed", flush=True)
            
            # STEP 2.5 (v1.0.4): Per-Briq QontractGuard Gate
            if is_contract_relevant and qontract_guard and contract_data and build_passed:
                print(f"     [GUARD] Running QontractGuard (contract-relevant briq)...", flush=True)
                briq_guard = qontract_guard.run_guard_for_files(
                    contract_data, staged_attempt['validation_root'], staged_attempt['staged_files']
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
                        retry_correction = briq_guard.get_correction_directive(contract_data)
                        result['error'] = f"QontractGuard: {error_count} contract violations"
                        build_passed = False
                    else:
                        # Max retries exhausted — mark as failure
                        result['error'] = f"QontractGuard: {error_count} violations (retries exhausted)"
                        build_passed = False
                else:
                    print(f"     [GUARD] ✅ Passed", flush=True)
            
            # STEP 3: AI Quick Review (optional)
            if do_ai_review and build_passed:
                print(f"     - Running AI quick review...", flush=True)
                review = run_ai_quick_review(
                    briq_name,
                    briq_content,
                    staged_attempt['staged_files'],
                    staged_attempt['validation_root'],
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
                committed_files = commit_staged_attempt(staged_attempt, qodeyard_path, worqspace_root)
                committed_written_files.update(item['path'] for item in committed_files)
                result['written_files'] = sorted(committed_written_files)
                result['attempt_records'][-1]['status'] = 'committed'
                result['attempt_records'][-1]['committed_files'] = [item['path'] for item in committed_files]
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
                finalize_attempt_manifest(
                    staged_attempt,
                    status="failed_validation",
                    failure_reason=result.get('error'),
                )
                result['attempt_records'][-1]['status'] = 'failed_validation'
                # Try again if we have attempts left
                if attempt >= max_attempts:
                    result['status'] = 'failure'
                    
        except Exception as e:
            result['error'] = str(e)
            print(f"     [ERROR] Attempt {attempt} failed: {e}", flush=True)
            if result.get('attempt_records'):
                result['attempt_records'][-1]['status'] = 'failed_exception'

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
Generated by ConstruQtor v1.0.4 (Interleaved Pipeline)

## Assessment: {status_emoji} [{result['status'].upper()}]

**Attempts:** {result['attempts']}
**Files Written:** {len(result['written_files'])}
**Write Strategy:** {result.get('write_strategy', 'unknown')}

"""
    
    if result['error']:
        exeq += f"**Error:** {result['error']}\n\n"
    
    # Files
    if result['written_files']:
        exeq += "## Generated Files\n\n"
        for f in result['written_files']:
            exeq += f"- `{f}`\n"
        exeq += "\n"

    if result.get('attempt_records'):
        exeq += "## Attempt Lineage\n\n"
        for attempt in result['attempt_records']:
            exeq += f"- `{attempt['attempt_id']}`: {attempt['status']} | staged={len(attempt.get('staged_files', []))} | committed={len(attempt.get('committed_files', []))}\n"
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

        if validation.get('constraint_errors'):
            exeq += "### Constraint Errors\n\n"
            for err in validation['constraint_errors']:
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
    interleaved_config = get_interleaved_config(config)
    write_strategy_config = get_write_strategy_config(config)
    
    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro')
    use_qompressor = config.get('options', {}).get('use_qompressor', True)
    
    # InspeQtor config for reviews
    inspeqtor_cfg = config.get('agents', {}).get('inspeqtor', {})
    review_provider = inspeqtor_cfg.get('provider', ai_provider)
    review_model = inspeqtor_cfg.get('model', ai_model)
    execution_backend = detect_execution_backend(ai_provider, ai_model)

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
    build_groups_dir = worqspace_root / "build" / "groups"
    build_groups_dir.mkdir(parents=True, exist_ok=True)
    planning_payload = load_optional_json(worqspace_root / "planning" / "build-groups.v1.json")
    component_contracts_payload = load_optional_json(worqspace_root / "planning" / "component-contracts.v1.json")

    # Processing stats
    all_results = []
    all_written_files = []
    success_count = 0
    partial_count = 0
    failure_count = 0
    
    stop_on_fail = retry_config['stop_on_briq_fail']
    stopped_early = False

    print(f"--- ConstruQtor v1.0.4: Processing {len(briq_files)} Briqs (Interleaved) ---", flush=True)
    print(f"    Retry: {'enabled' if retry_config['enabled'] else 'disabled'} | Max attempts: {retry_config['max_attempts']}", flush=True)
    print(f"    Interleaved: {'enabled' if interleaved_config['enabled'] else 'disabled'} | Local validation: {interleaved_config['local_validation']} | AI review: {interleaved_config['ai_quick_review']}", flush=True)

    constitutional_sections = {
        "qontract": qontract_content,
        "cycle1_tasq": cycle1_tasq_content,
        "structure_tree": struqture_tree,
    }

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
        briq_metadata = parse_briq_metadata(briq_file.read_text(encoding='utf-8'))
        build_group_id = briq_metadata.get('build-group', 'ungrouped')
        component_id = briq_metadata.get('component-id', 'unassigned')
        scope_id = briq_metadata.get('scope-id', 'scope_unknown')
        print(f"Construqtor: building group {build_group_id}", flush=True)
        print(f"\n-- Processing Briq: {briq_file.name} --", flush=True)
        print(f"   Group: {build_group_id} | Component: {component_id} | Scope: {scope_id}", flush=True)
        
        result = process_briq_interleaved(
            briq_file,
            qodeyard_path,
            worqspace_root,
            exeq_briq_dir,
            merged_context_files,
            context_type,
            mode,
            mode_prompt,
            ai_provider,
            ai_model,
            retry_config,
            interleaved_config,
            review_provider,
            review_model,
            constitutional_sections=constitutional_sections,
            qontract_json_path=qontract_json_path,
            contract_data=contract_data,
            planning_payload=planning_payload,
            component_contracts_payload=component_contracts_payload,
            write_strategy_config=write_strategy_config,
            execution_backend=execution_backend,
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

    grouped_results = {}
    for result in all_results:
        metadata = result.get('metadata', {})
        group_id = metadata.get('build-group', 'ungrouped')
        component_id = metadata.get('component-id', 'unassigned')
        scope_id = metadata.get('scope-id', f"scope_build_group_{group_id.replace('-', '_')}")
        group_entry = grouped_results.setdefault(group_id, {
            'scope_id': scope_id,
            'component_ids': set(),
            'briq_files': [],
            'written_files': set(),
            'statuses': [],
            'attempt_ids': [],
            'attempt_manifests': [],
            'recovery_refs': [],
            'attempt_records': [],
        })
        group_entry['component_ids'].add(component_id)
        group_entry['briq_files'].append(result['briq_file'])
        group_entry['written_files'].update(result['written_files'])
        group_entry['statuses'].append(result['status'])
        for attempt_record in result.get('attempt_records', []):
            group_entry['attempt_records'].append(attempt_record)
            group_entry['attempt_ids'].append(attempt_record['attempt_id'])
            group_entry['attempt_manifests'].append(attempt_record['manifest_ref'])
            group_entry['recovery_refs'].append(attempt_record['recovery_ref'])

    # --- Write Main Summary File ---
    summary_content = f"# Execution Summary (ConstruQtor v1.0.4 - Interleaved Pipeline)\n\n"
    summary_content += f"**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(all_results)}/{len(briq_files)} briqs\n"
    summary_content += f"**Results:** ✅ {success_count} | ⚠️ {partial_count} | ❌ {failure_count}\n\n"
    
    if stopped_early:
        summary_content += f"⚠️ **Cycle halted early due to `stop_on_briq_fail=true`**\n\n"
    
    summary_content += "## Build Group Overview\n\n"
    for group_id, group_entry in sorted(grouped_results.items()):
        summary_content += f"### {group_id}\n"
        summary_content += f"- Scope ID: {group_entry['scope_id']}\n"
        summary_content += f"- Components: {', '.join(sorted(group_entry['component_ids']))}\n"
        summary_content += f"- Briqs: {len(group_entry['briq_files'])}\n"
        summary_content += f"- Files Changed: {len(group_entry['written_files'])}\n\n"
        summary_content += f"- Write Strategy: {write_strategy_config['mode']}\n"
        summary_content += f"- Build Attempts: {len(set(group_entry['attempt_ids']))}\n\n"

    summary_content += "## Briq Details\n\n"
    for result in all_results:
        status_emoji = "✅" if result['status'] == 'success' else ("⚠️" if result['status'] == 'partial' else "❌")
        summary_content += f"### {result['briq_file']}: {status_emoji} {result['status']}\n"
        metadata = result.get('metadata', {})
        if metadata.get('build-group'):
            summary_content += f"- Build Group: `{metadata['build-group']}`\n"
        if metadata.get('component-id'):
            summary_content += f"- Component: `{metadata['component-id']}`\n"
        if metadata.get('scope-id'):
            summary_content += f"- Scope ID: `{metadata['scope-id']}`\n"
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
        if validation.get('constraint_errors'):
            summary_content += f"- Constraint Errors: {len(validation['constraint_errors'])}\n"
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
            if fb.get('validation', {}).get('constraint_errors'):
                summary_content += f"- Constraint errors:\n"
                for err in fb['validation']['constraint_errors']:
                    summary_content += f"  - {err}\n"
            summary_content += "\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)

    # --- Write Changed Files Summary ---
    changed_files_content = "# Changed Files\n\n"
    for group_id, group_entry in sorted(grouped_results.items()):
        changed_files_content += f"## {group_id}\n\n"
        changed_files_content += f"- Scope ID: `{group_entry['scope_id']}`\n"
        changed_files_content += f"- Components: {', '.join(sorted(group_entry['component_ids']))}\n"
        changed_files_content += f"- Write Strategy: `{write_strategy_config['mode']}`\n"
        changed_files_content += f"- Build Attempts: {', '.join(sorted(set(group_entry['attempt_ids']))) or 'None'}\n"
        for f_name in sorted(group_entry['written_files']):
            changed_files_content += f"- `{f_name}`\n"
        changed_files_content += "\n"
        
    os.makedirs(changed_files_summary_file.parent, exist_ok=True)
    with open(changed_files_summary_file, 'w', encoding='utf-8') as f:
        f.write(changed_files_content)

    for group_id, group_entry in sorted(grouped_results.items()):
        group_dir = build_groups_dir / group_id
        group_dir.mkdir(parents=True, exist_ok=True)
        if any(status == 'failure' for status in group_entry['statuses']):
            group_status = "FAILURE"
        elif any(status == 'partial' for status in group_entry['statuses']):
            group_status = "PARTIAL"
        else:
            group_status = "SUCCESS"
        build_report = {
            "schema_version": "build-report.v1",
            "build_report_id": f"{cycle_num}-{group_id}",
            "run_id": canonical_run_id(worqspace_root),
            "build_group_id": group_id,
            "status": group_status,
            "files": sorted(group_entry['written_files']),
            "changed_files": [{"path": path, "change_type": "modified_or_created"} for path in sorted(group_entry['written_files'])],
            "assumptions_used": [],
            "scope_id": group_entry['scope_id'],
            "write_strategy": write_strategy_config['mode'],
            "write_strategy_disclosure": "Scoped staged writes validate against an overlay workspace and commit atomically per briq attempt.",
            "recovery_policy": write_strategy_config['recovery_policy'],
            "capability_mode": "MIXED_REASONING_EXECUTION",
            "execution_backend": execution_backend,
            "component_ids": sorted(group_entry['component_ids']),
            "briq_files": group_entry['briq_files'],
            "build_attempt_ids": sorted(set(group_entry['attempt_ids'])),
            "attempt_manifest_refs": sorted(set(group_entry['attempt_manifests'])),
            "recovery_refs": sorted(set(group_entry['recovery_refs'])),
            "attempt_records": group_entry['attempt_records'],
        }
        changed_scope_manifest = {
            "schema_version": "changed-scope-manifest.v1",
            "run_id": canonical_run_id(worqspace_root),
            "build_group_id": group_id,
            "scope_id": group_entry['scope_id'],
            "write_strategy": write_strategy_config['mode'],
            "recovery_policy": write_strategy_config['recovery_policy'],
            "build_attempt_ids": sorted(set(group_entry['attempt_ids'])),
            "component_refs": [
                {
                    "component_id": component_id,
                    "declared_touch": True,
                    "touched_files": sorted(group_entry['written_files']),
                }
                for component_id in sorted(group_entry['component_ids'])
            ],
            "changed_files": [
                {
                    "path": path,
                    "change_type": "modified_or_created",
                    "in_intended_scope": True,
                    "commit_state": "committed_atomically",
                    "evidence_class": "direct_execution_evidence",
                    "source_build_ref": f"build/groups/{group_id}/build-report.v1.json",
                    "attempt_ids": sorted({
                        attempt_record['attempt_id']
                        for attempt_record in group_entry['attempt_records']
                        if path in attempt_record.get('committed_files', [])
                    }),
                }
                for path in sorted(group_entry['written_files'])
            ],
            "attempt_manifest_refs": sorted(set(group_entry['attempt_manifests'])),
            "recovery_refs": sorted(set(group_entry['recovery_refs'])),
        }
        with open(group_dir / "build-report.v1.json", "w", encoding="utf-8") as f:
            json.dump(build_report, f, indent=2)
            f.write("\n")
        with open(group_dir / "changed-files.v1.json", "w", encoding="utf-8") as f:
            json.dump(changed_scope_manifest, f, indent=2)
            f.write("\n")

    print(f"\n--- ConstruQtor v1.0.4 Complete: {final_status} ---", flush=True)
    print(f"    Per-briq exeQ summaries written to: exeq.d/cyqle{cycle_num}/", flush=True)
    print(f"    Build-group reports written to: build/groups/", flush=True)


if __name__ == "__main__":
    main()
