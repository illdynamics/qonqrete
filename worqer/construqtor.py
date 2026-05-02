#!/usr/bin/env python3
# worqer/construqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# ConstruQtor Agent - Code Generation with Interleaved Per-Briq Review
# v1.3.0 - QONTRACT + Cycle1 Tasq Context Wiring
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
import copy
import yaml
import re
import time
import ast
import json
import base64
import shutil
import subprocess
import hashlib
import threading
from pathlib import Path


def _runtime_version() -> str:
    env_version = str(os.environ.get("QONQ_VERSION", "")).strip()
    if env_version:
        return env_version
    try:
        return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "?.?.?"


RUNTIME_VERSION = _runtime_version()

# Ensure unbuffered/line-buffered output for real-time progress in QonQrete environment
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

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

try:
    import lib_sandbox_diff
except ImportError:
    lib_sandbox_diff = None

# v1.3.0: Import Qonfirmer for per-briq contract gating
try:
    import qonfirmer
except ImportError:
    qonfirmer = None

try:
    from lib_loqal import safe_write_file
except ImportError:
    safe_write_file = None

# v1.3.10: Path hygiene — infra-dir detection, project-prefix stripping,
# cwd-drift guard. Prevents AI-emitted filenames like
# `test-small/main.py` or `build/attempts/.../reqap.d/...` from polluting
# qodeyard, and refuses to run if cwd drifted into qodeyard/<sub>.
try:
    from path_hygiene import (
        is_infra_path,
        strip_project_prefix,
        assert_cwd_outside_qodeyard,
        INFRA_DIR_NAMES,
    )
except ImportError:
    # Fallback stubs if module missing — keep running but log loudly.
    def is_infra_path(p):  # type: ignore
        return False

    def strip_project_prefix(r, names):  # type: ignore
        return r

    def assert_cwd_outside_qodeyard(agent_name="agent"):  # type: ignore
        pass

    INFRA_DIR_NAMES = frozenset()  # type: ignore
    print("     [WARN] path_hygiene module not available — qodeyard hygiene disabled", flush=True)

try:
    from integration_checks import (
        build_issue_fingerprint_entries,
        collect_scope_validation_issues,
        derive_group_scope_files,
        fingerprint_issue,
        normalize_file_hints,
    )
except ImportError:
    def build_issue_fingerprint_entries(*args, **kwargs):  # type: ignore
        return []

    def collect_scope_validation_issues(*args, **kwargs):  # type: ignore
        return []

    def derive_group_scope_files(*args, **kwargs):  # type: ignore
        return []

    def fingerprint_issue(*args, **kwargs):  # type: ignore
        return ""

    def normalize_file_hints(values):  # type: ignore
        return []

try:
    from shellscript_validation import pick_shell_mode, validate_run_sh_contract
except ImportError:
    try:
        from worqer.shellscript_validation import pick_shell_mode, validate_run_sh_contract  # type: ignore
    except ImportError:
        pick_shell_mode = None
        validate_run_sh_contract = None


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_RETRY_CONFIG = {
    'enabled': True,
    'max_attempts': 4,
    'stop_on_briq_fail': False,
    'retry_delay': 1.0,
}

DEFAULT_INTERLEAVED_CONFIG = {
    'enabled': True,                    # Enable interleaved build→review
    'local_validation': True,           # Run local syntax/import checks
    'ai_quick_review': False,           # Run lightweight AI review per briq
    'retry_on_review_fail': True,       # Retry build if review fails
}

DEFAULT_REPAIR_ESCALATION_CONFIG = {
    'enabled': True,
    'max_level': 4,
    'start_policy': 'failure_class',
    'bump_policy': 'on_same_class_repeat',
}

DEFAULT_STREAMING_POLICY = {
    'enabled': True,
    'fallback_to_non_streaming_on_error': True,
}

REPAIR_FAILURE_CLASS_TO_LEVEL = {
    "collateral_churn_overrewrite": 1,
    "required_output_missing": 2,
    "transport_write_failure": 2,
    "runtime_syntax_launch_failure": 2,
    "exact_validator_violation": 3,
    "file_scoped_contract_miss": 3,
    "broad_task_shape_miss": 4,
}

DEFAULT_WRITE_STRATEGY = {
    'mode': 'staged_atomic_per_attempt',
    'coding_mode': 'hybrid',  # heredoc | direct | hybrid
    'recovery_policy': 'snapshot_before_commit',
    'hybrid_policy': {
        # Baseline policy:
        # - new file => heredoc
        # - existing file => direct
        # Deterministic overrides/fallbacks are controlled by these thresholds.
        'direct_parse_failure_to_heredoc_threshold': 2,
        'same_failure_class_escalation_threshold': 2,
        'broad_rewrite_line_ratio_threshold': 0.35,
        'broad_rewrite_min_changed_lines': 120,
        'primary_deliverable_prefer_heredoc': True,
        'fallback_from_heredoc_to_direct': False,
        # Deterministic recovery for stubborn "required output missing" loops.
        # This only applies after repeated heredoc misses for the SAME file.
        'missing_required_direct_recovery_enabled': True,
        'missing_required_to_direct_recovery_threshold': 2,
        'degradation_ratio_threshold': 0.2,
        'placeholder_guard_enabled': True,
        'placeholder_small_content_max_bytes': 220,
    },
}

DEFAULT_CONTEXT_FILES_PER_ATTEMPT = 12
RETRY_CONTEXT_FILES_PER_ATTEMPT = 8

_HTML_AUTOFIX_EXTENSIONS = {'.html', '.htm'}


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
    env_override = os.environ.get("QONQ_RETRY_MAX_ATTEMPTS")
    if env_override not in (None, ""):
        try:
            parsed = int(env_override)
            if parsed > 0:
                result['max_attempts'] = parsed
        except Exception:
            pass
    try:
        result['retry_delay'] = max(0.0, float(result.get('retry_delay', 1.0)))
    except Exception:
        result['retry_delay'] = 1.0
    return result


def get_streaming_policy(config: dict) -> dict:
    """Resolve concise streaming policy for ConstruQtor AI calls."""
    result = DEFAULT_STREAMING_POLICY.copy()
    agent_cfg = ((config or {}).get('agents', {}) or {}).get('construqtor', {}) or {}
    streaming_cfg = agent_cfg.get('streaming', {}) or {}
    if isinstance(streaming_cfg, bool):
        result['enabled'] = bool(streaming_cfg)
    elif isinstance(streaming_cfg, dict):
        for key in result:
            if key in streaming_cfg:
                result[key] = streaming_cfg[key]

    env_force_off = str(os.environ.get("QONQ_STREAMING", "")).strip().lower()
    if env_force_off in {"0", "false", "no", "off"}:
        result['enabled'] = False

    env_fallback = str(os.environ.get("QONQ_STREAM_FALLBACK", "")).strip().lower()
    if env_fallback in {"0", "false", "no", "off"}:
        result['fallback_to_non_streaming_on_error'] = False
    elif env_fallback in {"1", "true", "yes", "on"}:
        result['fallback_to_non_streaming_on_error'] = True

    for key in ("enabled", "fallback_to_non_streaming_on_error"):
        raw = result.get(key, True)
        if isinstance(raw, bool):
            continue
        result[key] = str(raw).strip().lower() in {"1", "true", "yes", "on"}
    return result


def get_interleaved_config(config: dict) -> dict:
    """Extract interleaved review configuration with defaults."""
    interleaved_cfg = config.get('interleaved', {})
    result = DEFAULT_INTERLEAVED_CONFIG.copy()
    for key in DEFAULT_INTERLEAVED_CONFIG:
        if key in interleaved_cfg:
            result[key] = interleaved_cfg[key]
    return result


def get_repair_escalation_config(config: dict) -> dict:
    """Extract bounded repair-escalation settings with sane defaults.

    Supports both the canonical nested config shape::

        repair:
          repair_escalation: {...}

    and the legacy/top-level compatibility alias::

        repair_escalation: {...}
    """
    cfg = config or {}
    repair_cfg = cfg.get('repair', {}) or {}
    raw = repair_cfg.get('repair_escalation', None)
    if raw in (None, {}):
        raw = cfg.get('repair_escalation', {})

    # Support both boolean and object forms for compatibility.
    if isinstance(raw, bool):
        result = DEFAULT_REPAIR_ESCALATION_CONFIG.copy()
        result['enabled'] = bool(raw)
        return result

    result = DEFAULT_REPAIR_ESCALATION_CONFIG.copy()
    if isinstance(raw, dict):
        for key in DEFAULT_REPAIR_ESCALATION_CONFIG:
            if key in raw:
                result[key] = raw[key]

    # Optional alias if users set `auto_repair_strategy` in existing configs.
    raw_dict = raw if isinstance(raw, dict) else {}
    if 'auto_repair_strategy' in repair_cfg and 'enabled' not in raw_dict:
        result['enabled'] = bool(repair_cfg.get('auto_repair_strategy'))

    try:
        result['max_level'] = max(1, min(4, int(result.get('max_level', 4))))
    except Exception:
        result['max_level'] = 4

    start_policy = str(result.get('start_policy', 'failure_class') or 'failure_class').strip().lower()
    if start_policy not in {'failure_class', 'attempt_count'}:
        start_policy = 'failure_class'
    result['start_policy'] = start_policy

    bump_policy = str(result.get('bump_policy', 'on_same_class_repeat') or 'on_same_class_repeat').strip().lower()
    if bump_policy not in {'on_same_class_repeat', 'on_attempt_repeat'}:
        bump_policy = 'on_same_class_repeat'
    result['bump_policy'] = bump_policy
    return result


def normalize_failure_class(value: str | None) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in REPAIR_FAILURE_CLASS_TO_LEVEL:
        return text
    return "broad_task_shape_miss"


def classify_attempt_failure(
    *,
    failure_status: str,
    error_message: str | None,
    direct_loop_meta: dict | None,
    validation: dict | None,
    qonfirmer_report: dict | None,
    missing_primary_outputs: list[str] | None = None,
) -> tuple[str, str]:
    status = str(failure_status or "").strip().lower()
    message = " ".join(str(error_message or "").split())
    direct_meta = direct_loop_meta or {}
    validation_payload = validation or {}
    qonfirmer_payload = qonfirmer_report or {}
    missing_primary_outputs = missing_primary_outputs or []

    parse_failures = int(direct_meta.get("parse_failures", 0) or 0)
    apply_errors = int(direct_meta.get("apply_errors", 0) or 0)
    truncated_responses = int(direct_meta.get("truncated_responses", 0) or 0)
    if parse_failures > 0 or apply_errors > 0:
        reason = (
            "direct tool-call transport failed "
            f"(parse_failures={parse_failures}, apply_errors={apply_errors}, truncated={truncated_responses})"
        )
        return "transport_write_failure", reason

    if status == "failed_missing_required" or missing_primary_outputs:
        listed = ", ".join(missing_primary_outputs[:8]) or "required deliverables missing"
        return "required_output_missing", listed

    if status == "failed_trivial":
        return "collateral_churn_overrewrite", message or "suspiciously tiny or trivial primary output was rejected"

    if qonfirmer_payload and qonfirmer_payload.get("status") == "FAIL":
        violation_count = len(qonfirmer_payload.get("violations", []) or [])
        return "exact_validator_violation", f"qonfirmer reported {violation_count} violation(s)"

    syntax_errors = validation_payload.get("syntax_errors") or []
    constraint_errors = validation_payload.get("constraint_errors") or []
    if syntax_errors:
        return "runtime_syntax_launch_failure", str(syntax_errors[0])
    if constraint_errors:
        return "file_scoped_contract_miss", str(constraint_errors[0])

    if status in {"failed_empty", "failed_validation"}:
        return "broad_task_shape_miss", message or "attempt did not produce a passing scoped candidate"

    return "broad_task_shape_miss", message or "repair required"


def choose_repair_level(
    *,
    config: dict,
    attempt_index: int,
    failure_class: str,
    failure_fingerprint: str,
    prior_attempt_records: list[dict],
    recommended_start_level: int | None = None,
) -> tuple[int, str]:
    cfg = get_repair_escalation_config(config)
    failure_class_norm = normalize_failure_class(failure_class)
    if not cfg.get("enabled", True):
        return 1, "repair_escalation_disabled"

    max_level = int(cfg.get("max_level", 4) or 4)
    if cfg.get("start_policy") == "attempt_count":
        level = max(1, attempt_index)
        reason = "attempt_count_policy"
    else:
        level = int(REPAIR_FAILURE_CLASS_TO_LEVEL.get(failure_class_norm, 1))
        reason = f"failure_class:{failure_class_norm}"

    if recommended_start_level is not None:
        try:
            recommended = int(recommended_start_level)
        except Exception:
            recommended = level
        if recommended > level:
            level = recommended
            reason = f"{reason}+repair_plan_recommendation"

    if prior_attempt_records:
        last = prior_attempt_records[-1]
        last_class = normalize_failure_class(last.get("failure_class"))
        last_fingerprint = str(last.get("failure_fingerprint", "")).strip()
        last_level = int(last.get("repair_level", level))
        same_class = (last_class == failure_class_norm)
        same_fingerprint = bool(last_fingerprint and last_fingerprint == failure_fingerprint)
        
        level = max(level, last_level)

        if cfg.get("bump_policy") == "on_attempt_repeat" and attempt_index > 1:
            level += max(0, attempt_index - 1)
            reason = f"{reason}+attempt_repeat"
        elif cfg.get("bump_policy") == "on_same_class_repeat" and (same_class or same_fingerprint):
            level += 1
            reason = f"{reason}+same_shape_repeat"

    level = max(1, min(max_level, int(level)))
    return level, reason


def format_violation_rows_for_retry(violation_rows: list[str], *, cap: int = 20) -> str:
    rows = [str(item).strip() for item in (violation_rows or []) if str(item).strip()]
    if not rows:
        return ""
    rendered = "\n".join(f"- {row}" for row in rows[:cap])
    if len(rows) > cap:
        rendered += f"\n- ... and {len(rows) - cap} more"
    return rendered


def build_escalated_retry_correction(
    *,
    repair_level: int,
    failure_class: str,
    escalation_reason: str,
    base_directive: str,
    target_files: list[str] | None = None,
    violation_rows: list[str] | None = None,
) -> str:
    target_files = [str(item).strip() for item in (target_files or []) if str(item).strip()]
    violations_text = format_violation_rows_for_retry(violation_rows or [])
    failure_class_norm = normalize_failure_class(failure_class)

    header = [
        "REPAIR ESCALATION DIRECTIVE",
        f"- repair_level: {repair_level}",
        f"- failure_class: {failure_class_norm}",
        f"- escalation_reason: {escalation_reason}",
    ]
    if target_files:
        header.append("- target_files: " + ", ".join(sorted(set(target_files))))
    if violations_text:
        header.append("Exact violation list:")
        header.append(violations_text)

    if repair_level <= 1:
        strategy = (
            "Level 1 (surgical): minimal diffs for remaining defects only.\n"
            "No collateral rewrites, no scope expansion."
        )
    elif repair_level == 2:
        strategy = (
            "Level 2 (deterministic): resolve exact listed violations only.\n"
            "Preserve unaffected files/sections; do not re-generate whole project."
        )
    elif repair_level == 3:
        strategy = (
            "Level 3 (focused): edit only targeted files/subsystem.\n"
            "Avoid unrelated rewrites and preserve already-correct behavior."
        )
    else:
        strategy = (
            "Level 4 (broad corrective): restore missing foundational outputs and satisfy task shape.\n"
            "Do not invent new architecture."
        )

    return (
        "\n".join(header)
        + "\n"
        + strategy
        + "\n\n"
        + (base_directive or "").strip()
        + "\n"
    )


def update_attempt_manifest_context(staged_attempt: dict, context_payload: dict) -> None:
    manifest_path = staged_attempt.get("manifest_path")
    if not manifest_path:
        return
    try:
        payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception:
        return
    context_obj = payload.get("attempt_context")
    if not isinstance(context_obj, dict):
        context_obj = {}
    for key, value in (context_payload or {}).items():
        context_obj[key] = value
    payload["attempt_context"] = context_obj
    Path(manifest_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def get_write_strategy_config(config: dict) -> dict:
    strategy_cfg = config.get('write_strategy', {}) or {}
    result = copy.deepcopy(DEFAULT_WRITE_STRATEGY)
    for key in DEFAULT_WRITE_STRATEGY:
        if key == "hybrid_policy":
            continue
        if key in strategy_cfg:
            result[key] = strategy_cfg[key]
    if isinstance(strategy_cfg.get("hybrid_policy"), dict):
        for key, value in strategy_cfg.get("hybrid_policy", {}).items():
            if key in result["hybrid_policy"]:
                result["hybrid_policy"][key] = value
    
    # v1.3.10: Support per-agent override for coding_mode
    agent_cfg = config.get('agents', {}).get('construqtor', {})
    if 'coding_mode' in agent_cfg:
        result['coding_mode'] = agent_cfg['coding_mode']
    env_mode = str(os.environ.get("QONQ_CODING_MODE", "")).strip().lower()
    if env_mode:
        result['coding_mode'] = env_mode
    
    # v1.3.15: Strict validation of coding_mode (additive hybrid mode)
    valid_modes = {'heredoc', 'direct', 'hybrid'}
    if result['coding_mode'] not in valid_modes:
        print(f"CRITICAL: Invalid coding_mode '{result['coding_mode']}' in config. "
              f"Must be one of: {', '.join(sorted(valid_modes))}.", flush=True)
        sys.exit(1)

    policy = result.get("hybrid_policy", {})
    if not isinstance(policy, dict):
        policy = copy.deepcopy(DEFAULT_WRITE_STRATEGY["hybrid_policy"])
        result["hybrid_policy"] = policy

    def _int_cfg(key: str, minimum: int, maximum: int | None = None) -> None:
        raw = policy.get(key, DEFAULT_WRITE_STRATEGY["hybrid_policy"][key])
        try:
            value = int(raw)
        except Exception:
            value = int(DEFAULT_WRITE_STRATEGY["hybrid_policy"][key])
        value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        policy[key] = value

    def _float_cfg(key: str, minimum: float, maximum: float) -> None:
        raw = policy.get(key, DEFAULT_WRITE_STRATEGY["hybrid_policy"][key])
        try:
            value = float(raw)
        except Exception:
            value = float(DEFAULT_WRITE_STRATEGY["hybrid_policy"][key])
        value = max(minimum, min(maximum, value))
        policy[key] = value

    def _bool_cfg(key: str) -> None:
        raw = policy.get(key, DEFAULT_WRITE_STRATEGY["hybrid_policy"][key])
        if isinstance(raw, bool):
            policy[key] = raw
            return
        text = str(raw).strip().lower()
        policy[key] = text in {"1", "true", "yes", "on"}

    _int_cfg("direct_parse_failure_to_heredoc_threshold", 1, 8)
    _int_cfg("same_failure_class_escalation_threshold", 1, 8)
    _float_cfg("broad_rewrite_line_ratio_threshold", 0.05, 1.0)
    _int_cfg("broad_rewrite_min_changed_lines", 20, 2000)
    _bool_cfg("primary_deliverable_prefer_heredoc")
    _bool_cfg("fallback_from_heredoc_to_direct")
    _bool_cfg("missing_required_direct_recovery_enabled")
    _int_cfg("missing_required_to_direct_recovery_threshold", 1, 8)
    _float_cfg("degradation_ratio_threshold", 0.05, 0.95)
    _bool_cfg("placeholder_guard_enabled")
    _int_cfg("placeholder_small_content_max_bytes", 64, 4096)
        
    print(f"     [Config] Active coding_mode: {result['coding_mode']}", flush=True)
        
    return result


def canonical_run_id(worqspace_root: Path) -> str:
    return worqspace_root.name


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
    repair_escalation = payload.get("repair_escalation", {}) if isinstance(payload.get("repair_escalation"), dict) else {}
    if repair_escalation:
        lines.append("**Repair Escalation Guidance:**")
        lines.append(f"- Enabled: {bool(repair_escalation.get('enabled', True))}")
        lines.append(f"- Recommended Failure Class: {repair_escalation.get('recommended_failure_class', 'unknown')}")
        lines.append(f"- Recommended Start Level: {repair_escalation.get('recommended_start_level', 1)}")
        if repair_escalation.get("reason"):
            lines.append(f"- Reason: {repair_escalation.get('reason')}")
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


def detect_serialized_code_artifact(file_path: Path) -> str | None:
    """Detect AI output that was serialized as a Python list/string blob.

    This catches a common malformed artifact where a file is syntactically-valid
    Python but semantically just one giant quoted blob with escaped newlines.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    stripped = text.strip()
    if not stripped:
        return None

    single_line = "\n" not in stripped
    escaped_newlines = stripped.count("\\n")
    looks_like_list_blob = (
        stripped.startswith("['")
        or stripped.startswith('["')
        or stripped.startswith("[u'")
        or stripped.startswith('[u"')
    )
    has_fragment_separators = ("', '" in stripped) or ('", "' in stripped)

    if single_line and escaped_newlines >= 5 and looks_like_list_blob and has_fragment_separators:
        return (
            "serialized code blob detected (single-line escaped list/string fragments); "
            "regenerate this file as plain executable source text"
        )
    return None


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

            blob_error = detect_serialized_code_artifact(file_path)
            if blob_error:
                result['syntax_errors'].append(f"{file_name}: {blob_error}")
                result['passed'] = False
        elif file_path.suffix == '.sh' and file_path.exists():
            result['files_checked'] += 1
            shell_content = ""
            try:
                shell_content = file_path.read_text(encoding='utf-8')
            except Exception as exc:
                result['syntax_errors'].append(f"{file_name}: could not read shell script ({exc})")
                result['passed'] = False
                continue

            shell_mode = pick_shell_mode(file_path, shell_content) if pick_shell_mode else "sh"
            shell_bin = shutil.which(shell_mode) or shutil.which("sh")
            if not shell_bin:
                result['syntax_errors'].append(
                    f"{file_name}: shell interpreter unavailable for syntax check ({shell_mode})"
                )
                result['passed'] = False
                continue

            shell_check = subprocess.run(
                [shell_bin, '-n', str(file_path)],
                capture_output=True,
                text=True,
            )
            if shell_check.returncode != 0:
                result['syntax_errors'].append(
                    f"{file_name}: {shell_check.stderr.strip() or 'shell syntax check failed'}"
                )
                result['passed'] = False

            if file_name == 'run.sh':
                policy = resolve_run_sh_port_policy(qodeyard_path.parent)
                run_sh_errors = validate_run_sh_constraints(shell_content, policy)
                if run_sh_errors:
                    result['constraint_errors'].extend(
                        [f"{file_name}: {msg}" for msg in run_sh_errors]
                    )
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


def run_scoped_qualification(
    written_files: list[str],
    qodeyard_path: Path,
    worqspace_root: Path,
    cycle_label: str,
) -> dict:
    """Scoped qualifier-backed interleaved validation.

    Reuses the real ``qualifier`` package on the exact subset of files
    that the current briq just wrote, then layers the legacy
    ``run.sh`` constraint checks on top (those aren't a qualifier
    concern — they're ConstruQtor-specific business rules).

    Behaviour:
      * Calls ``qualifier.run_verification(...)`` with ``changed_files``
        set to the just-written files → only relevant adapters load
        (e.g. a TS-only briq never boots the Python adapter).
      * Translates the resulting ``VerificationReport`` back into the
        legacy dict shape consumed by the rest of ConstruQtor so this
        drop-in swap has zero blast radius on downstream call sites.
      * Honest mapping: JS/TS/HTML/CSS/shell errors surface as
        ``syntax_errors`` so the retry-correction directive actually
        gets built for them instead of being silently discarded.
      * Config is loaded fresh from the worqspace (full tree, not the
        flattened inspeqtor-only view) so ``verification.checks.*``
        toggles are honoured.

    If the qualifier package cannot be imported (env not set up) we
    fall back to the legacy ``run_local_validation`` so construqtor
    continues to function — scoped reuse is an upgrade, never a gate.
    """
    result = {
        'passed': True,
        'syntax_errors': [],
        'constraint_errors': [],
        'import_warnings': [],
        'files_checked': 0,
    }

    try:
        # Resolve qualifier via the same import path InspeQtor uses.
        this_dir = os.path.dirname(os.path.abspath(__file__))
        if this_dir not in sys.path:
            sys.path.insert(0, this_dir)
        import qualifier  # noqa: F401  (lazy import — may be missing in stripped envs)
    except ImportError:
        # Env without the qualifier package — fall back to the legacy
        # narrow validator so construqtor stays usable.
        return run_local_validation(written_files, qodeyard_path)

    # Load the REAL (unflattened) config tree so verification.checks.*
    # survives the trip into the qualifier's Python adapter.
    config = load_config(worqspace_root / 'config.yaml')

    # v1.4.0: Task tier awareness
    tier = "low"
    criteria_path = worqspace_root / 'planning' / 'completion-criteria.v1.json'
    if criteria_path.exists():
        try:
            import json as _json
            with open(criteria_path, 'r', encoding='utf-8') as f:
                _criteria_doc = _json.load(f)
                tier = str(_criteria_doc.get('tier', 'low')).lower()
        except Exception:
            pass

    try:
        report = qualifier.run_verification(
            qodeyard_path,
            None,                          # qontext not wired at interleaved time
            str(cycle_label),
            config,
            changed_files=written_files or None,
            tier=tier,
        )
    except Exception as exc:
        # Never let a qualifier crash kill the briq pipeline. Surface
        # the crash as a constraint error so retry logic can react.
        result['passed'] = False
        result['constraint_errors'].append(
            f"qualifier crashed during scoped run: {exc}"
        )
        return result

    # v1.4.0: Interleaved integration validation
    # Catch wiring/integration issues (missing DOM IDs, router registration, etc) early.
    try:
        from integration_checks import collect_scope_validation_issues
        integration_issues = collect_scope_validation_issues(
            worqspace_root,
            scope_files=written_files or None
        )
        for issue in integration_issues:
            # We treat integration errors as constraint errors to trigger immediate repair
            if issue.get('severity') == 'error':
                result['passed'] = False
                result['constraint_errors'].append(issue.get('message') or issue.get('summary'))
    except (ImportError, Exception) as exc:
        # Integration checker is an upgrade, not a blocker.
        pass

    result['files_checked'] = int(report.files_checked or 0)

    for r in report.results:
        # 'info' is observational only — e.g. "tsc not on PATH".
        if getattr(r, 'severity', 'error') == 'info':
            continue
        if getattr(r, 'passed', False):
            continue
        line_suffix = f" (line {r.line_number})" if r.line_number else ""
        rendered = f"{r.file_path}{line_suffix}: [{r.check_type}] {r.message}"
        if getattr(r, 'severity', 'error') == 'warning':
            # Warnings don't fail the build, but we surface them as
            # import_warnings so they get logged and retained.
            result['import_warnings'].append(rendered)
        else:
            result['syntax_errors'].append(rendered)
            result['passed'] = False

    # Catch semantically-invalid serialized code blobs that can slip through
    # pure syntax checks because they parse as a giant list/string literal.
    for file_name in written_files:
        file_path = qodeyard_path / file_name
        if file_path.suffix != ".py" or not file_path.exists():
            continue
        blob_error = detect_serialized_code_artifact(file_path)
        if blob_error:
            result['syntax_errors'].append(f"{file_name}: {blob_error}")
            result['passed'] = False

    # ── ConstruQtor-specific run.sh constraint layer ─────────────────
    # These rules aren't something qualifier enforces (they're not
    # generic syntax/lint — they're this pipeline's contract for how
    # a uvicorn-backed app must boot). Keep them running on top of
    # the qualifier pass.
    for file_name in written_files:
        if file_name != 'run.sh':
            continue
        file_path = qodeyard_path / file_name
        if not file_path.exists():
            continue
        try:
            shell_content = file_path.read_text(encoding='utf-8')
        except Exception as exc:
            result['constraint_errors'].append(
                f"{file_name}: could not read run.sh ({exc})"
            )
            result['passed'] = False
            continue

        policy = resolve_run_sh_port_policy(worqspace_root)
        run_sh_errors = validate_run_sh_constraints(shell_content, policy)
        if run_sh_errors:
            result['constraint_errors'].extend(
                [f"{file_name}: {msg}" for msg in run_sh_errors]
            )
            result['passed'] = False

    return result


def _resolve_repair_scope_files(
    worqspace_root: Path,
    *,
    repair_plan_payload: dict,
    briq_metadata: dict | None = None,
    briq_targets: list[str] | None = None,
    primary_deliverables: list[str] | None = None,
) -> list[str]:
    metadata = briq_metadata or {}
    briq_ref = metadata.get("briq-ref") or metadata.get("briq_ref")
    build_group = metadata.get("build-group") or metadata.get("build_group")
    scope_files = derive_group_scope_files(
        worqspace_root,
        target_files=(repair_plan_payload or {}).get("target_files") or list(briq_targets or []) + list(primary_deliverables or []),
        target_build_groups=(repair_plan_payload or {}).get("target_build_groups") or ([build_group] if build_group else []),
        target_briq_refs=(repair_plan_payload or {}).get("target_briq_refs") or ([briq_ref] if briq_ref else []),
        current_build_group=build_group,
        current_briq_ref=briq_ref,
    )
    if not scope_files:
        scope_files = sorted(set(list(primary_deliverables or []) + list(briq_targets or [])))
    return scope_files



def _qualifier_issue_dicts(qualification: dict) -> list[dict]:
    issues: list[dict] = []
    payload = qualification or {}
    for key, severity in (("syntax_errors", "error"), ("constraint_errors", "error"), ("warnings", "warning")):
        for message in payload.get(key, []) or []:
            text = str(message or "").strip()
            if not text:
                continue
            rel_file = None
            if ":" in text:
                rel_file = text.split(":", 1)[0].strip()
            issues.append({
                "source": "qualification",
                "severity": severity,
                "message": text,
                "file": rel_file,
                "files": [rel_file] if rel_file else [],
                "check_type": key,
            })
    return issues



def _open_repair_fingerprints_for_scope(
    deterministic_issues: list[dict],
    repair_plan_payload: dict,
    *,
    build_group: str | None,
) -> list[dict]:
    issue_map = {}
    for issue in deterministic_issues or []:
        fp = fingerprint_issue(issue)
        if fp:
            issue_map[fp] = issue

    relevant: list[dict] = []
    for item in (repair_plan_payload or {}).get("issue_fingerprints", []) or []:
        if not isinstance(item, dict):
            continue
        fp = str(item.get("fingerprint") or "").strip()
        if not fp or fp not in issue_map:
            continue
        item_groups = {str(group).strip() for group in (item.get("build_groups") or []) if str(group).strip()}
        item_files = set(normalize_file_hints(item.get("files")))
        if item_files:
            relevant.append(item)
        elif build_group and item_groups and build_group in item_groups:
            relevant.append(item)
        elif not item_groups:
            relevant.append(item)
    return relevant



def _evaluate_repair_scope_state(
    worqspace_root: Path,
    qodeyard_path: Path,
    *,
    repair_targets: list[str],
    validation_scope_files: list[str],
    is_contract_relevant: bool,
    contract_data: dict | None,
    build_group: str | None,
    repair_plan_payload: dict,
) -> dict:
    missing_targets = [rel for rel in repair_targets if not (qodeyard_path / rel).exists()]
    qualification = run_scoped_qualification(
        validation_scope_files or repair_targets,
        qodeyard_path,
        worqspace_root,
        "repair-scope",
    )
    deterministic_issues = _qualifier_issue_dicts(qualification)
    deterministic_issues.extend(
        collect_scope_validation_issues(
            worqspace_root,
            scope_files=validation_scope_files or repair_targets,
            target_build_groups=[build_group] if build_group else None,
        )
    )
    qonfirmer_report = None
    if is_contract_relevant and qonfirmer and contract_data:
        try:
            qf_result = qonfirmer.run_qonfirmer_for_files(contract_data, qodeyard_path, validation_scope_files or repair_targets)
            qonfirmer_report = qf_result.to_json()
            if not qf_result.passed:
                deterministic_issues.extend([
                    {
                        "source": "qonfirmer",
                        "severity": "error",
                        "message": violation.get("message") or violation.get("summary") or "Qonfirmer violation",
                        "file": violation.get("file"),
                        "files": violation.get("files") or normalize_file_hints(violation.get("file")),
                        "check_type": violation.get("check_type") or "qonfirmer",
                    }
                    for violation in (qonfirmer_report or {}).get("violations", [])
                    if isinstance(violation, dict)
                ])
        except Exception as exc:
            deterministic_issues.append({
                "source": "qonfirmer",
                "severity": "error",
                "message": f"Qonfirmer failed while rechecking repair scope: {exc}",
                "files": validation_scope_files or repair_targets,
                "check_type": "qonfirmer_runtime",
            })

    open_fingerprints = _open_repair_fingerprints_for_scope(
        [issue for issue in deterministic_issues if str(issue.get("severity", "")).lower() == "error"],
        repair_plan_payload,
        build_group=build_group,
    )
    passed = not missing_targets and qualification.get("passed", False) and not open_fingerprints and not any(
        str(issue.get("severity", "")).lower() == "error" for issue in deterministic_issues
    )
    return {
        "passed": passed,
        "missing_targets": missing_targets,
        "qualification": qualification,
        "deterministic_issues": deterministic_issues,
        "open_fingerprints": open_fingerprints,
        "qonfirmer_report": qonfirmer_report,
        "scope_files": validation_scope_files or repair_targets,
    }



def _render_open_fingerprint_summaries(open_fingerprints: list[dict]) -> str:
    summaries = []
    for item in open_fingerprints or []:
        summary = str(item.get("summary") or item.get("fingerprint") or "").strip()
        if summary:
            summaries.append(summary)
    return "; ".join(summaries[:3])



def _load_task_contract_blob(worqspace_root: Path) -> str:
    parts: list[str] = []
    task_spec = load_optional_json(worqspace_root / "task" / "task-spec.v1.json")
    for key in ("clarified_task_body", "goal"):
        value = task_spec.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    tasq_path = worqspace_root / "tasq.md"
    if tasq_path.exists():
        try:
            parts.append(tasq_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n".join(parts).lower()


def resolve_run_sh_port_policy(worqspace_root: Path) -> str:
    """Resolve run.sh port policy from task contract text.

    Returns:
      - "exact_literal_8000": task explicitly requires exact literal launch cmd.
      - "exact_variable_port": task explicitly requires exact `$PORT` launch cmd.
      - "port_variable": task explicitly requires $PORT-style invocation.
      - "generic": no explicit strict port style found.
    """
    blob = _load_task_contract_blob(worqspace_root)
    if not blob:
        return "generic"

    exact_literal_cmd = "python -m uvicorn main:app --reload --port 8000"
    if exact_literal_cmd in blob and "must launch exactly" in blob:
        return "exact_literal_8000"

    exact_var_cmd = "python -m uvicorn main:app --reload --port $port"
    exact_var_markers = (
        "must launch exactly",
        "launch exectly this uvicorn command",
        "launch exactly this uvicorn command",
    )
    if exact_var_cmd in blob and any(marker in blob for marker in exact_var_markers):
        return "exact_variable_port"

    if (
        "--port $port" in blob
        or "--port ${port}" in blob
        or "pass the port variable" in blob
        or "derive port from environment" in blob
    ):
        return "port_variable"

    return "generic"


def validate_run_sh_constraints(shell_content: str, policy: str) -> list[str]:
    if validate_run_sh_contract is None:
        # Fallback for stripped environments where helper import failed.
        return ["shellscript validator unavailable; could not enforce run.sh launch contract"]
    return validate_run_sh_contract(shell_content, policy)




def build_validation_correction_directive(validation: dict) -> str:
    errors = validation.get('constraint_errors', []) + validation.get('syntax_errors', [])
    if not errors:
        return ""
    bullets = "\n".join(f"- {item}" for item in errors[:10])
    return f"""

CRITICAL RETRY CORRECTION:
The previous output failed deterministic local validation. Regenerate the affected files and fix all of these issues exactly:
{bullets}

For `run.sh`, follow the task's explicit launch-command contract exactly and avoid introducing alternate port conventions not requested by the task.
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
    elif provider_value in {"openai", "anthropic", "gemini", "deepseek", "qwen", "openrouter", "mlx", "llama-cpp", "venice"}:
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
    def _looks_numeric_decimal_token(text: str) -> bool:
        # Guard against decimal values from timing/ratio prose (e.g. "0.00003")
        # being misidentified as file paths.
        return bool(re.fullmatch(r"\d+(?:\.\d+)+", text))

    def _looks_like_target_file(candidate: str) -> bool:
        text = _normalize_context_target(candidate)
        if not text:
            return False
        if text.startswith("../") or text.startswith("/"):
            return False
        if _looks_numeric_decimal_token(text):
            return False
        if ":" in text and "/" not in text:
            # Likely "main:app" or similar non-file token.
            return False
        if is_infra_path(text):
            return False
        if "/" in text:
            parts = [part for part in text.split("/") if part]
            if not parts:
                return False
            if all(re.match(r"^[A-Za-z0-9_.-]+$", part) for part in parts):
                tail = parts[-1]
                if tail in {"Dockerfile", "Makefile", "run.sh", "requirements.txt"}:
                    return True
                if "." not in tail or _looks_numeric_decimal_token(tail):
                    return False
                base, ext = tail.rsplit(".", 1)
                if any(ch.isalpha() for ch in (base + ext)):
                    return True
                return False
        ext_match = re.match(r"^([A-Za-z0-9_.-]+)\.([A-Za-z0-9]{1,10})$", text)
        if ext_match and not _looks_numeric_decimal_token(text):
            base, ext = ext_match.groups()
            if any(ch.isalpha() for ch in (base + ext)):
                return True
        if text in {"Dockerfile", "Makefile", "run.sh", "requirements.txt"}:
            return True
        return False

    targets: list[str] = []

    # Primary extraction: explicit file mentions in backticks.
    for candidate in re.findall(r'`([^`]+)`', briq_content):
        cleaned = _normalize_context_target(candidate)
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    # Secondary extraction: required-file sections often list bare filenames.
    in_required_block = False
    for raw_line in briq_content.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        inline_required = re.search(r"required[-_ ]files?\s*:\s*\[(.+)\]", line, flags=re.IGNORECASE)
        if inline_required:
            for part in inline_required.group(1).split(","):
                cleaned = _normalize_context_target(part.strip().strip("`\"'"))
                if _looks_like_target_file(cleaned):
                    targets.append(cleaned)
        if (
            re.search(r"\brequired[-_ ]files?\b", lower)
            or "must contain exactly these files" in lower
            or "project must contain exactly these files" in lower
            or "repo root contains" in lower
            or "the repo root contains" in lower
        ):
            in_required_block = True
            continue
        if in_required_block:
            if line.startswith("#"):
                in_required_block = False
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9 _-]+:\s*$", line) and not re.search(r"\brequired[-_ ]files?\b", lower):
                in_required_block = False
                continue
        if not in_required_block:
            continue
        if not line:
            continue
        candidate = line.lstrip("-*").strip()
        candidate = re.sub(r"^\d+\.\s*", "", candidate).strip()
        candidate = candidate.strip("`\"'")
        cleaned = _normalize_context_target(candidate)
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    # Fallback extraction for plain prose ("Add script run.sh", etc.).
    for match in re.finditer(
        r"(?<![\w/])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,10}|Dockerfile|Makefile|run\.sh|requirements\.txt)(?![\w/])",
        briq_content,
    ):
        candidate = _normalize_context_target(match.group(1))
        if _looks_like_target_file(candidate):
            targets.append(candidate)

    return sorted(set(targets))


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_context_target(value: str) -> str:
    cleaned = str(value or "").strip().replace("\\", "/")
    if cleaned.startswith("qodeyard/"):
        cleaned = cleaned[len("qodeyard/"):]
    return cleaned


def _parse_metadata_file_list(value: str | None) -> list[str]:
    if value is None:
        return []
    raw = str(value).strip()
    if not raw or raw.lower() in {"none", "n/a", "na"}:
        return []
    candidates: list[str] = []
    for chunk in re.split(r"[,\n;]+", raw):
        item = _normalize_context_target(chunk).strip()
        if not item:
            continue
        if item.startswith("../") or item.startswith("/"):
            continue
        if is_infra_path(item):
            continue
        candidates.append(item)
    return sorted(set(candidates))


def _resolve_completion_required_files(completion_criteria_payload: dict | None) -> list[str]:
    if not isinstance(completion_criteria_payload, dict):
        return []
    required = []
    for item in completion_criteria_payload.get("required_files", []) or []:
        cleaned = _normalize_context_target(str(item))
        if cleaned and not is_infra_path(cleaned):
            required.append(cleaned)
    return sorted(set(required))


def _resolve_briq_primary_deliverables(
    briq_metadata: dict,
    briq_targets: list[str],
    planning_payload: dict | None,
    completion_required_files: list[str],
) -> list[str]:
    primary = set(_parse_metadata_file_list(briq_metadata.get("primary-deliverables")))
    group_targets = set(_parse_metadata_file_list(briq_metadata.get("target-files")))
    if not group_targets:
        group_targets = {t for t in briq_targets if _normalize_context_target(t)}
    build_group_id = str(briq_metadata.get("build-group", "")).strip()
    briq_ref = str(briq_metadata.get("briq-ref", "")).strip().lower()
    if isinstance(planning_payload, dict):
        # Prefer briq-local primary ownership from inventory to avoid forcing
        # downstream group primaries too early (e.g. CSS file required in HTML briq).
        for briq_item in planning_payload.get("briq_inventory", []) or []:
            candidate_ref = str(briq_item.get("briq_ref", "")).strip().lower()
            if not briq_ref or not candidate_ref or candidate_ref != briq_ref:
                continue
            for item in briq_item.get("primary_files", []) or []:
                cleaned = _normalize_context_target(str(item))
                if cleaned and not is_infra_path(cleaned) and (not group_targets or cleaned in group_targets):
                    primary.add(cleaned)
            break

        # Fallback only when group has a single briq; in that case group primary
        # deliverables are effectively briq-local.
        if not primary:
            for group in planning_payload.get("items", []) or []:
                if str(group.get("build_group_id", "")).strip() != build_group_id:
                    continue
                group_briqs = [str(item).strip().lower() for item in (group.get("briq_refs", []) or []) if str(item).strip()]
                if len(group_briqs) == 1 and (not briq_ref or group_briqs[0] == briq_ref):
                    for item in group.get("primary_files", []) or []:
                        cleaned = _normalize_context_target(str(item))
                        if cleaned and not is_infra_path(cleaned) and (not group_targets or cleaned in group_targets):
                            primary.add(cleaned)
                break
    if not primary and completion_required_files:
        primary.update({t for t in group_targets if t in set(completion_required_files)})
    return sorted(primary)


def _missing_required_outputs(
    required_files: list[str],
    *,
    staged_files: list[str],
    qodeyard_path: Path,
) -> list[str]:
    if not required_files:
        return []
    staged_set = {str(item).strip() for item in staged_files if str(item).strip()}
    missing = []
    for rel_path in required_files:
        if rel_path in staged_set:
            continue
        if (qodeyard_path / rel_path).exists():
            continue
        missing.append(rel_path)
    return sorted(set(missing))


def _evaluate_primary_deliverable_sizes(
    staged_attempt: dict,
    qodeyard_path: Path,
    primary_deliverables: list[str],
    *,
    policy_cfg: dict | None = None,
) -> list[str]:
    """
    Return a list of suspiciously tiny primary deliverables.
    Gate: staged size < min(256 bytes, 0.2 * prior_size) when prior exists.
    For new files, reject empty/near-empty placeholder payloads.
    For existing files, also reject obvious placeholder/degradation clobbers.
    """
    policy = policy_cfg if isinstance(policy_cfg, dict) else {}
    degradation_ratio = float(policy.get("degradation_ratio_threshold", 0.2) or 0.2)
    placeholder_guard = bool(policy.get("placeholder_guard_enabled", True))
    placeholder_max_bytes = int(policy.get("placeholder_small_content_max_bytes", 220) or 220)

    primary_set = {str(item).strip() for item in primary_deliverables if str(item).strip()}
    if not primary_set:
        return []
    suspicious: list[str] = []
    for file_record in staged_attempt.get("file_records", []):
        rel_path = str(file_record.get("path", "")).strip()
        if rel_path not in primary_set:
            continue
        staged_size = int(file_record.get("size_bytes", 0) or 0)
        prior_path = qodeyard_path / rel_path
        staged_path = staged_attempt.get("staging_dir", Path(".")) / rel_path
        try:
            staged_text = staged_path.read_text(encoding="utf-8")
        except Exception:
            staged_text = ""
        if prior_path.exists():
            try:
                prior_size = int(prior_path.stat().st_size)
            except Exception:
                prior_size = 0
            threshold = int(min(256, 0.2 * max(0, prior_size)))
            if threshold > 0 and staged_size < threshold:
                suspicious.append(
                    f"{rel_path} (size={staged_size}B, threshold={threshold}B, prior={prior_size}B)"
                )
                continue
            if placeholder_guard:
                placeholder_reason = _detect_placeholder_reason(
                    staged_text,
                    max_bytes=placeholder_max_bytes,
                )
                if placeholder_reason:
                    suspicious.append(
                        f"{rel_path} (placeholder-like replacement rejected: {placeholder_reason})"
                    )
                    continue
            try:
                prior_text = prior_path.read_text(encoding="utf-8")
            except Exception:
                prior_text = ""
            degrade_reason = _detect_degradation_reason(
                prior_text,
                staged_text,
                ratio_threshold=degradation_ratio,
            )
            if degrade_reason:
                suspicious.append(f"{rel_path} ({degrade_reason})")
        else:
            if staged_size == 0:
                suspicious.append(f"{rel_path} (size=0B for new primary deliverable)")
                continue
            if placeholder_guard:
                placeholder_reason = _detect_placeholder_reason(
                    staged_text,
                    max_bytes=placeholder_max_bytes,
                )
                if placeholder_reason:
                    suspicious.append(
                        f"{rel_path} (placeholder-like content for new primary deliverable: {placeholder_reason})"
                    )
    return suspicious


def _build_qonfirmer_targeted_retry_directive(
    qonfirmer_report,
    contract_data: dict | None,
    staged_files: list[str],
) -> str:
    base = qonfirmer_report.get_correction_directive(contract_data)
    violation_rows = []
    for violation in (qonfirmer_report.violations or [])[:25]:
        loc = f":{violation.line_number}" if violation.line_number else ""
        violation_rows.append(
            f"- [{violation.rule}] {violation.file_path}{loc}: {violation.message}"
        )
    scoped_files = sorted(set(str(item).strip() for item in staged_files if str(item).strip()))
    strict_scope = (
        "\nTARGETED REPAIR SCOPE (STRICT):\n"
        + ("- Files you may edit: " + ", ".join(scoped_files) + "\n" if scoped_files else "- Files you may edit: staged files only\n")
        + "- Fix ONLY the listed violations.\n"
        + "- Do NOT regenerate unrelated files.\n"
    )
    if violation_rows:
        strict_scope += "Violation list to resolve:\n" + "\n".join(violation_rows) + "\n"
    return (base or "") + strict_scope


def _select_context_files_for_briq(
    all_context_files: list[str],
    briq_targets: list[str],
    qontext_path: Path,
    *,
    max_files: int = DEFAULT_CONTEXT_FILES_PER_ATTEMPT,
) -> list[str]:
    """Deterministically choose a bounded context subset for a briq."""
    if max_files <= 0:
        return []

    deduped = _dedupe_preserve_order(sorted(all_context_files))
    targets = [_normalize_context_target(t) for t in briq_targets if _normalize_context_target(t)]
    target_basenames = {Path(t).name for t in targets if t}

    matched_targets: list[str] = []
    for ctx_file in deduped:
        ctx_norm = ctx_file.replace("\\", "/")
        ctx_name = Path(ctx_norm).name
        if targets and any(ctx_norm.endswith(t) or ctx_norm.endswith(f"/{t}") for t in targets):
            matched_targets.append(ctx_file)
            continue
        if ctx_name in target_basenames:
            matched_targets.append(ctx_file)

    relevant_qontext: list[str] = []
    if targets and qontext_path.exists():
        try:
            relevant_qontext = lib_ai.filter_context_by_relevance(
                deduped,
                targets,
                str(qontext_path),
                max_neighbors=1,
            )
        except Exception:
            relevant_qontext = []

    allow_markdown_context = any(
        Path(target).suffix.lower() in {".md", ".markdown"}
        for target in targets
    )

    selected: list[str] = []
    for bucket in (matched_targets, relevant_qontext, deduped):
        for ctx_file in bucket:
            if ctx_file in selected:
                continue
            ctx_norm = ctx_file.replace("\\", "/").lower()
            if not allow_markdown_context and ctx_norm.endswith(".md"):
                continue
            # qontract content is already injected as a dedicated section.
            if "/qontract.d/qontract.md" in ctx_norm:
                continue
            selected.append(ctx_file)
            if len(selected) >= max_files:
                return selected

    return selected[:max_files]


def _resolve_briq_output_tokens(
    briq_content: str,
    briq_targets: list[str],
    coding_mode: str,
) -> int | None:
    """Use smaller deterministic budgets for focused briqs."""
    target_count = len(briq_targets)
    content_size = len(briq_content or "")

    if target_count <= 2 and content_size <= 2200:
        if coding_mode == "direct":
            return 4000
        if coding_mode == "hybrid":
            return 4500
        return 5000
    if target_count <= 4 and content_size <= 3200:
        if coding_mode == "direct":
            return 6000
        if coding_mode == "hybrid":
            return 6500
        return 7000
    return 8000


def _nonempty_line_count(content: str) -> int:
    return sum(1 for line in str(content or "").splitlines() if line.strip())


def _detect_placeholder_reason(content: str, *, max_bytes: int = 220) -> str | None:
    raw = str(content or "")
    compact = " ".join(raw.split())
    if not compact:
        return "blank_content"
    lowered = compact.lower()

    exact_tokens = {
        "todo",
        "tbd",
        "placeholder",
        "stub",
        "fixme",
        "pass",
        "none",
        "null",
        "{}",
        ";",
        "// todo",
        "# todo",
    }
    if lowered in exact_tokens:
        return f"placeholder_token:{lowered[:40]}"

    payload_bytes = len(raw.encode("utf-8"))
    if payload_bytes > max_bytes:
        return None

    suspicious_phrases = (
        "read file first",
        "placeholder",
        "todo",
        "tbd",
        "implement this",
        "add implementation here",
        "coming soon",
        "same as before",
        "left intentionally blank",
        "replace with actual code",
    )
    if any(token in lowered for token in suspicious_phrases):
        return "placeholder_phrase"

    stripped_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if stripped_lines and len(stripped_lines) <= 4:
        comment_only = all(
            line.startswith(("#", "//", "/*", "*", "--"))
            or re.fullmatch(r"[-=/*#\s]+", line)
            for line in stripped_lines
        )
        if comment_only:
            return "comment_only_stub"

    return None


def _detect_degradation_reason(
    prior_content: str,
    staged_content: str,
    *,
    ratio_threshold: float,
) -> str | None:
    prior_bytes = len((prior_content or "").encode("utf-8"))
    staged_bytes = len((staged_content or "").encode("utf-8"))
    if prior_bytes <= 0:
        return None
    ratio = staged_bytes / max(1, prior_bytes)
    if ratio < ratio_threshold:
        return f"size_collapse ratio={ratio:.3f} ({staged_bytes}B/{prior_bytes}B)"

    prior_lines = _nonempty_line_count(prior_content)
    staged_lines = _nonempty_line_count(staged_content)
    if prior_lines >= 24 and staged_lines <= max(3, int(prior_lines * 0.2)):
        return f"line_collapse {staged_lines}/{prior_lines}"
    return None


def _is_broad_rewrite_intent(
    *,
    briq_content: str,
    target_file: str,
    qodeyard_path: Path,
    policy_cfg: dict,
) -> tuple[bool, str]:
    candidate = str(target_file or "").strip()
    if not candidate:
        return False, ""

    lower = str(briq_content or "").lower()
    basename = Path(candidate).name.lower()
    broad_markers = (
        "rewrite",
        "replace entire",
        "full file",
        "from scratch",
        "complete implementation",
        "overhaul",
        "regenerate",
    )
    marker_hit = any(marker in lower for marker in broad_markers)
    references_file = basename and basename in lower

    prior_path = qodeyard_path / candidate
    prior_lines = 0
    if prior_path.exists():
        try:
            prior_lines = _nonempty_line_count(prior_path.read_text(encoding="utf-8"))
        except Exception:
            prior_lines = 0

    min_lines = int(policy_cfg.get("broad_rewrite_min_changed_lines", 120) or 120)
    if marker_hit and references_file and prior_lines >= max(20, min_lines // 2):
        return True, f"briq_marker+large_prior({prior_lines} lines)"
    if marker_hit and references_file and prior_lines >= min_lines:
        return True, f"briq_marker+very_large_prior({prior_lines} lines)"
    return False, ""


def _filter_extracted_files_to_allowlist(
    extracted_files: dict[str, str],
    allowed_paths: set[str] | None,
) -> tuple[dict[str, str], list[str]]:
    if not allowed_paths:
        return dict(extracted_files or {}), []
    allowed_norm = {str(item).strip() for item in allowed_paths if str(item).strip()}
    filtered: dict[str, str] = {}
    dropped: list[str] = []
    for rel_path, content in (extracted_files or {}).items():
        rel = str(rel_path or "").strip()
        if rel in allowed_norm:
            filtered[rel] = content
        else:
            dropped.append(rel)
    return filtered, sorted(set(dropped))


def _build_hybrid_transport_decisions(
    *,
    briq_content: str,
    candidate_files: list[str],
    primary_deliverables: list[str],
    qodeyard_path: Path,
    transport_locks: dict[str, str],
    direct_failure_counts: dict[str, int],
    missing_required_counts: dict[str, int],
    policy_cfg: dict,
    attempt_index: int,
) -> list[dict]:
    decisions: list[dict] = []
    primary_set = {str(item).strip() for item in primary_deliverables if str(item).strip()}
    threshold = int(policy_cfg.get("direct_parse_failure_to_heredoc_threshold", 2) or 2)
    missing_recovery_enabled = bool(policy_cfg.get("missing_required_direct_recovery_enabled", True))
    missing_recovery_threshold = int(
        policy_cfg.get("missing_required_to_direct_recovery_threshold", 2) or 2
    )

    for rel_path in sorted({str(item).strip() for item in candidate_files if str(item).strip()}):
        existed = (qodeyard_path / rel_path).exists()
        lock_before = str(transport_locks.get(rel_path) or "").strip()
        prior_failures = int(direct_failure_counts.get(rel_path, 0) or 0)
        prior_missing_required = int(missing_required_counts.get(rel_path, 0) or 0)
        is_primary = rel_path in primary_set
        reasons: list[str] = []
        missing_recovery_triggered = bool(
            missing_recovery_enabled
            and not existed
            and prior_missing_required >= missing_recovery_threshold
        )

        if lock_before in {"direct", "heredoc"}:
            chosen = lock_before
            reasons.append(f"transport_lock:{lock_before}")
            if lock_before == "heredoc" and missing_recovery_triggered:
                chosen = "direct"
                reasons.append(
                    f"missing_required_recovery_to_direct:{prior_missing_required}>={missing_recovery_threshold}"
                )
        elif not existed:
            # v1.3.13: Six-Shooter Qontract support — prefer direct for new primary files in high-sens runs
            sensitivity = int(os.environ.get("QONQ_BRIQ_SENSITIVITY", "1"))
            if is_primary and sensitivity > 3:
                chosen = "direct"
                reasons.append(f"new_primary_high_sens_recovery_to_direct(sens={sensitivity})")
            else:
                chosen = "heredoc"
                reasons.append("new_file_default_heredoc")
                if missing_recovery_triggered:
                    chosen = "direct"
                    reasons.append(
                        f"missing_required_recovery_to_direct:{prior_missing_required}>={missing_recovery_threshold}"
                    )
        else:
            chosen = "direct"
            reasons.append("existing_file_default_direct")

            broad_rewrite, broad_reason = _is_broad_rewrite_intent(
                briq_content=briq_content,
                target_file=rel_path,
                qodeyard_path=qodeyard_path,
                policy_cfg=policy_cfg,
            )
            if broad_rewrite:
                chosen = "heredoc"
                reasons.append(f"broad_rewrite:{broad_reason}")

            if (
                chosen == "direct"
                and bool(policy_cfg.get("primary_deliverable_prefer_heredoc", True))
                and is_primary
                and attempt_index > 1
            ):
                chosen = "heredoc"
                reasons.append("primary_deliverable_repair_prefers_coherence")

            if chosen == "direct" and prior_failures >= threshold:
                chosen = "heredoc"
                reasons.append(f"direct_failure_threshold_reached:{prior_failures}>={threshold}")

        lock_after = lock_before or chosen
        if lock_before == "direct" and chosen == "heredoc":
            lock_after = "heredoc"
        if lock_before == "heredoc" and chosen == "direct":
            lock_after = "direct"
        transport_locks[rel_path] = lock_after

        decisions.append(
            {
                "file_path": rel_path,
                "file_existed_pre_attempt": existed,
                "chosen_transport": chosen,
                "decision_reason_codes": reasons or ["default"],
                "is_primary_deliverable": is_primary,
                "failure_counts_by_class": {
                    "direct_transport_failures": prior_failures,
                    "required_output_missing_failures": prior_missing_required,
                },
                "transport_lock_state_before": lock_before or "unset",
                "transport_lock_state_after": lock_after,
                "fallback_occurred": False,
                "fallback_reason_code": None,
            }
        )
    return decisions


def _strip_trailing_whitespace_and_normalize_newline(content: str) -> tuple[str, set[str]]:
    categories: set[str] = set()
    if content == "":
        return content, categories

    lines = content.splitlines()
    had_trailing_ws = any(line != line.rstrip(" \t") for line in lines)
    normalized = "\n".join(line.rstrip(" \t") for line in lines)
    if normalized:
        normalized += "\n"

    if had_trailing_ws:
        categories.add("trailing_whitespace")
    if content and not content.endswith("\n"):
        categories.add("eof_newline")

    return normalized, categories


def _escape_raw_ampersands_in_html_text_nodes(content: str) -> tuple[str, bool]:
    changed = False

    def _escape_amp(segment: str) -> str:
        return re.sub(
            r'&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]+;)',
            '&amp;',
            segment,
        )

    def _replace(match: re.Match) -> str:
        nonlocal changed
        inner = match.group(1)
        fixed = _escape_amp(inner)
        if fixed != inner:
            changed = True
        return f">{fixed}<"

    updated = re.sub(r'>([^<]+)<', _replace, content, flags=re.DOTALL)
    return updated, changed


def _apply_trivial_autofix(file_paths: list[str], roots: list[Path]) -> dict:
    """Apply deterministic low-risk formatting/entity fixes in-place."""
    if not file_paths or not roots:
        return {"applied": False, "changed_files": [], "categories": []}

    changed_files: list[str] = []
    categories: set[str] = set()
    unique_files = sorted(dict.fromkeys(file_paths))

    for rel_path in unique_files:
        rel = str(rel_path or "").strip()
        if not rel:
            continue

        source_path = None
        for root in roots:
            candidate = root / rel
            if candidate.exists() and candidate.is_file():
                source_path = candidate
                break
        if source_path is None:
            continue

        try:
            original = source_path.read_text(encoding='utf-8')
        except Exception:
            continue

        updated, ws_categories = _strip_trailing_whitespace_and_normalize_newline(original)
        categories.update(ws_categories)

        if Path(rel).suffix.lower() in _HTML_AUTOFIX_EXTENSIONS:
            html_fixed, html_changed = _escape_raw_ampersands_in_html_text_nodes(updated)
            if html_changed:
                updated = html_fixed
                categories.add("html_ampersand_escape")

        if updated == original:
            continue

        for root in roots:
            target = root / rel
            if target.exists() and target.is_file():
                _write_text(target, updated, jail=root)
        changed_files.append(rel)

    return {
        "applied": bool(changed_files),
        "changed_files": sorted(changed_files),
        "categories": sorted(categories),
    }


def get_component_contract(metadata: dict, component_contracts_payload: dict) -> dict:
    component_id = metadata.get('component-id')
    if not component_id:
        return {}
    component_contracts = {
        item.get('component_id'): item
        for item in component_contracts_payload.get('items', [])
        if item.get('component_id')
    }
    return component_contracts.get(component_id, {})



def build_group_context(metadata: dict, planning_payload: dict, component_contracts_payload: dict) -> str:
    build_groups = {
        item.get('build_group_id'): item
        for item in planning_payload.get('items', [])
        if item.get('build_group_id')
    }
    build_group_id = metadata.get('build-group')
    component_id = metadata.get('component-id')
    group = build_groups.get(build_group_id, {})
    component = get_component_contract(metadata, component_contracts_payload)

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
        raw_name = filename.strip()
        if raw_name.startswith('qodeyard/'):
            raw_name = raw_name[len('qodeyard/'):]

        # v1.3.10: Strip leading project-name segment. If the AI emits
        # `test-small/main.py` because it thinks the project lives in a
        # subfolder named after the qonstruction, flatten it to `main.py`.
        # We collect candidate project names from env (QONSTRUCTION_NAME,
        # QONQ_RUN_NAME), the qodeyard's parent dir name (the qage/run id),
        # and any existing top-level dir inside qodeyard that is NOT a
        # recognised source layout name (src/, lib/, tests/, etc. are fine).
        project_name_candidates: list[str] = []
        for env_key in ("QONSTRUCTION_NAME", "QONQ_RUN_NAME", "QONQ_PROJECT_NAME"):
            v = os.environ.get(env_key)
            if v:
                project_name_candidates.append(v.strip())
        try:
            qage_name = qodeyard.resolve().parent.name
            if qage_name and qage_name not in ("worqspace", "qonqrete"):
                project_name_candidates.append(qage_name)
        except Exception:
            pass
        if project_name_candidates:
            raw_name = strip_project_prefix(raw_name, project_name_candidates)

        # v1.3.10: Reject infrastructure paths outright. The AI has no
        # legitimate reason to emit build/, attempts/, validation-root/,
        # reqap.d/, recovery/, qonfirmer/reqap/smoketest/verification
        # artifact filenames, or nested .qonqrete/ trees. If it does, it's
        # re-emitting context leakage and we MUST NOT write it into qodeyard.
        if is_infra_path(raw_name):
            print(f"     [REJECT] Infra path blocked (not user code): {filename}", flush=True)
            continue

        filename = raw_name

        qodeyard_abs = qodeyard.resolve()
        proposed_path = qodeyard_abs.joinpath(filename.strip())
        proposed_abs = proposed_path.resolve()

        # Security check
        if not str(proposed_abs).startswith(str(qodeyard_abs)):
            print(f"     [WARN] Skipping unsafe path: {filename}", flush=True)
            continue

        safe_filename = proposed_abs.relative_to(qodeyard_abs)

        # v1.3.10: Belt-and-braces — re-check after relativisation in case
        # path traversal or symlink resolution surfaced an infra segment.
        if is_infra_path(safe_filename):
            print(f"     [REJECT] Infra path blocked post-resolve: {safe_filename}", flush=True)
            continue

        extracted_files[str(safe_filename)] = code_content

    return extracted_files


def _write_text(path: Path, content: str, jail: Path | None = None) -> None:
    if safe_write_file:
        safe_write_file(path, content, jail=jail or path.parent)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _stage_extracted_files(
    extracted_files: dict[str, str],
    qodeyard: Path,
    worqspace_root: Path,
    attempt_id: str,
    metadata: dict,
    validation_root: Path | None = None,
    coding_mode: str = 'heredoc',
    requested_coding_mode: str | None = None,
    transport_decisions: list[dict] | None = None,
) -> dict:
    qodeyard.mkdir(parents=True, exist_ok=True)
    attempt_root = worqspace_root / "build" / "attempts" / attempt_id
    staging_dir = attempt_root / "staging"
    if validation_root is None:
        validation_root = attempt_root / "validation-root"
    recovery_dir = attempt_root / "recovery"
    
    attempt_root.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    recovery_dir.mkdir(parents=True, exist_ok=True)

    staged_files = []
    file_records = []
    # v1.3.12: Sort keys for deterministic staging order
    for rel_path in sorted(extracted_files.keys()):
        content = extracted_files[rel_path]
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

    # Populate validation_root if it wasn't already handled by direct coding
    if not validation_root.exists():
        _initialize_direct_sandbox(qodeyard, validation_root)
        
    # Apply extracted files to validation_root (ensures latest changes are present)
    for rel_path in sorted(extracted_files.keys()):
        content = extracted_files[rel_path]
        validation_path = validation_root / rel_path
        _write_text(validation_path, content, jail=validation_root)

    manifest = {
        "schema_version": "build-attempt.v1",
        "attempt_id": attempt_id,
        "run_id": canonical_run_id(worqspace_root),
        "build_group_id": metadata.get('build-group', 'ungrouped'),
        "scope_id": metadata.get('scope-id', 'scope_unknown'),
        "component_id": metadata.get('component-id', 'unassigned'),
        "write_strategy": "staged_atomic_per_attempt",
        "coding_mode": coding_mode,
        "requested_coding_mode": requested_coding_mode or coding_mode,
        "recovery_policy": "snapshot_before_commit",
        "attempt_status": "staged",
        "staged_files": file_records,
        "transport_decisions": transport_decisions or [],
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

def stage_attempt_files(
    result: str,
    qodeyard: Path,
    worqspace_root: Path,
    attempt_id: str,
    metadata: dict,
    coding_mode: str = 'heredoc',
) -> dict:
    extracted_files = _extract_ai_output_files(result, qodeyard)
    return _stage_extracted_files(extracted_files, qodeyard, worqspace_root, attempt_id, metadata, coding_mode=coding_mode)


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


def commit_staged_attempt(staged_attempt: dict, qodeyard: Path, worqspace_root: Path, attempt: int = 1) -> list[dict]:
    committed_files = []
    snapshot_refs = []
    for file_record in staged_attempt["file_records"]:
        rel_path = file_record["path"]
        staged_path = staged_attempt["staging_dir"] / rel_path
        target_path = qodeyard / rel_path
        prior_exists = target_path.exists()
        
        action_label = "Created" if not prior_exists else ("Rewrote (repair)" if attempt > 1 else "Updated")
        print(f"     - {action_label}: {rel_path}", flush=True)
        
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
# UTILS
# ═══════════════════════════════════════════════════════════════════════════════

class Heartbeat:
    """Helper to print progress during long-running agent work."""
    def __init__(self, message: str = "Working", interval: int = 15):
        self.message = message
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.attempts = 0
        self.exeq_count = 0

    def _run(self):
        last_beat = time.time()
        while not self.stop_event.is_set():
            time.sleep(1)
            if time.time() - last_beat >= self.interval:
                last_beat = time.time()

    def set_message(self, message: str):
        self.message = message

    def start(self, attempts: int = 0, exeq_count: int = 0):
        self.attempts = attempts
        self.exeq_count = exeq_count
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread:
            self.stop_event.set()
            self.thread.join(timeout=1.0)
            self.thread = None


DIRECT_CODING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file_direct",
            "description": "Write or update a file in the project workspace sandbox. Use this tool ONLY for the files you are assigned to create or modify. Once your changes pass validation, DO NOT rewrite them again. If you have no more changes, stop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative path to the file within the project root (qodeyard/)."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text content to write to the file."
                    },
                    "content_base64": {
                        "type": "string",
                        "description": "Optional: base64-encoded UTF-8 file content (safer for large multiline payloads)."
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Optional: append content to existing file instead of replacing it."
                    }
                },
                "required": ["path"]
            }
        }
    }
]


def _decode_tool_text_field(raw_value: str) -> str:
    value = str(raw_value)
    for quote in ('"', "'"):
        try:
            return json.loads(f"{quote}{value}{quote}")
        except Exception:
            continue
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    value = value.replace('\\"', '"').replace("\\'", "'")
    return value


def _parse_direct_tool_arguments(args_raw) -> tuple[dict | None, str | None]:
    if isinstance(args_raw, dict):
        return dict(args_raw), None

    raw = str(args_raw or "").strip()
    if not raw:
        return None, "empty arguments"

    decoder = json.JSONDecoder()
    candidates = [raw]
    brace_idx = raw.find("{")
    if brace_idx > 0:
        candidates.append(raw[brace_idx:])

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, None
        except Exception:
            pass
        try:
            parsed, _ = decoder.raw_decode(candidate)
            if isinstance(parsed, dict):
                return parsed, None
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(candidate)
            if isinstance(parsed, dict):
                return parsed, None
        except Exception:
            pass

    parsed: dict[str, object] = {}
    field_re = re.compile(r'["\'](?P<key>path|content|content_base64|append)["\']\s*:\s*', re.IGNORECASE)
    for match in field_re.finditer(raw):
        key = match.group("key").lower()
        idx = match.end()
        while idx < len(raw) and raw[idx].isspace():
            idx += 1
        if idx >= len(raw):
            continue

        if raw[idx] in {'"', "'"}:
            quote = raw[idx]
            idx += 1
            if key in {"content", "content_base64"}:
                end = raw.rfind(quote)
                if end <= idx:
                    # Unclosed quoted payload; treat as parse failure.
                    continue
                value = raw[idx:end]
            else:
                buf: list[str] = []
                escaped = False
                end = idx
                while end < len(raw):
                    ch = raw[end]
                    if escaped:
                        buf.append(ch)
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == quote:
                        break
                    else:
                        buf.append(ch)
                    end += 1
                value = "".join(buf)
            parsed[key] = _decode_tool_text_field(value)
        else:
            end = idx
            while end < len(raw) and raw[end] not in ",}":
                end += 1
            token = raw[idx:end].strip()
            if key == "append":
                parsed[key] = token.lower() in {"true", "1", "yes", "on"}
            else:
                parsed[key] = token.strip("\"'")

    has_path = bool(str(parsed.get("path", "")).strip())
    has_content = "content" in parsed or "content_base64" in parsed
    if has_path and has_content:
        return parsed, None
    return None, "malformed arguments (expected path + content/content_base64)"

def _initialize_direct_sandbox(qodeyard_path: Path, validation_root: Path) -> None:
    """Prepare the validation-root sandbox for direct coding by syncing it with qodeyard."""
    if validation_root.exists():
        shutil.rmtree(validation_root)
    
    def _infra_ignore(directory, names):
        ignored: list[str] = []
        for n in names:
            full = Path(directory) / n
            if full.is_dir() and n in INFRA_DIR_NAMES:
                ignored.append(n)
            elif full.is_dir() and n.startswith("qage_"):
                ignored.append(n)
            elif full.is_symlink():
                ignored.append(n)
        return ignored

    shutil.copytree(qodeyard_path, validation_root, dirs_exist_ok=True, ignore=_infra_ignore)


_STREAMING_FALLBACK_HINTS = (
    "event stream",
    "sse",
    "stream",
    "chunk",
    "broken pipe",
    "connection reset",
    "remote protocol error",
    "incomplete read",
    "timeout",
)


def _is_streaming_fallback_error(exc: Exception) -> bool:
    timeout_cls = getattr(lib_ai, "TimeoutError", None)
    if timeout_cls is not None and isinstance(exc, timeout_cls):
        return True
    text = str(exc or "").strip().lower()
    if not text:
        return False
    if "stream_callback=false" in text:
        return False
    return any(token in text for token in _STREAMING_FALLBACK_HINTS)


def _run_ai_completion_with_streaming_policy(
    *,
    ai_provider: str,
    ai_model: str,
    prompt: str,
    context_files: list[str],
    prompt_sections: list[dict],
    agent_name: str,
    task_type: str,
    output_tokens: int | None,
    tools: list[dict] | None = None,
    allow_tool_streaming: bool = False,
    streaming_policy: dict | None = None,
    stream_label: str = "generation",
) -> tuple[str | dict, bool]:
    """Run AI completion with stream-first policy and narrow non-streaming fallback."""
    policy = dict(DEFAULT_STREAMING_POLICY)
    if isinstance(streaming_policy, dict):
        policy.update(streaming_policy)

    request_kwargs = {
        "provider": ai_provider,
        "model": ai_model,
        "prompt": prompt,
        "context_files": context_files,
        "prompt_sections": prompt_sections,
        "agent_name": agent_name,
        "task_type": task_type,
        "output_tokens": output_tokens,
        "tools": tools,
        "allow_tool_streaming": allow_tool_streaming,
    }
    if not policy.get("enabled", True):
        request_kwargs["stream_callback"] = False

    try:
        return lib_ai.run_ai_completion(**request_kwargs), False
    except Exception as exc:
        if request_kwargs.get("stream_callback") is False:
            raise
        if not policy.get("fallback_to_non_streaming_on_error", True):
            raise
        if not _is_streaming_fallback_error(exc):
            raise
        print(
            f"     [Stream] ⚠️ Streaming failed for {stream_label}; retrying once with non-streaming fallback ({exc})",
            flush=True,
        )
        request_kwargs["stream_callback"] = False
        return lib_ai.run_ai_completion(**request_kwargs), True

def _run_direct_coding_loop(
    ai_provider: str,
    ai_model: str,
    prompt: str,
    prompt_sections: list[dict],
    context_files: list[str],
    validation_root: Path,
    qodeyard_path: Path,
    worqspace_root: Path,
    briq_metadata: dict,
    output_tokens: int | None = None,
    return_meta: bool = False,
    allowed_paths: set[str] | None = None,
    heartbeat: Heartbeat | None = None,
    streaming_policy: dict | None = None,
) -> dict[str, str] | tuple[dict[str, str], dict]:
    """Execute the AI tool-calling loop with iterative repair-forward in the sandbox."""
    _initialize_direct_sandbox(qodeyard_path, validation_root)
    
    modified_files = {}
    max_tool_iterations = int(os.environ.get("QONQ_DIRECT_MAX_TOOL_ITERATIONS", "4") or "4")
    max_tool_iterations = max(1, min(8, max_tool_iterations))
    max_no_progress_iterations = int(os.environ.get("QONQ_DIRECT_MAX_NO_PROGRESS", "2") or "2")
    max_no_progress_iterations = max(1, min(5, max_no_progress_iterations))
    current_iteration = 0
    loop_meta = {
        "iterations": 0,
        "ai_call_count": 0,
        "tool_calls_seen": 0,
        "parse_failures": 0,
        "apply_errors": 0,
        "truncated_responses": 0,
        "fallback_used": False,
        "large_payload_parse_failures": 0,
        "max_tool_argument_chars": 0,
        "disallowed_path_calls": 0,
        "stream_fallback_count": 0,
        "no_progress_iterations": 0,
        "written_files": [],
        "validation_gate_scope": "group_batch",
        "validated_batches": [],
        "last_failed_batch": [],
    }
    allowed_norm = {str(item).strip() for item in (allowed_paths or set()) if str(item).strip()}
    
    # Track correction directives for iterative repair inside the loop
    internal_retry_correction = ""
    fallback_markdown_attempted = False
    consecutive_truncated_tool_errors = 0
    parse_error_streak = 0
    no_progress_streak = 0
    current_output_tokens = output_tokens
    max_direct_output_tokens = int(os.environ.get("QONQ_DIRECT_MAX_OUTPUT_TOKENS", "8192") or "8192")
    fallback_output_tokens = int(os.environ.get("QONQ_DIRECT_FALLBACK_OUTPUT_TOKENS", "4096") or "4096")

    # Local helper for validation inside the loop
    def _validate_current_sandbox(files_to_check: list[str]) -> tuple[bool, str]:
        cycle_label = os.environ.get('CYCLE_NUM', '1')
        val_res = run_scoped_qualification(
            files_to_check,
            validation_root,
            worqspace_root,
            f"direct-interleaved-{cycle_label}"
        )
        if val_res['passed']:
            return True, ""
        errors = val_res.get('syntax_errors', []) + val_res.get('constraint_errors', [])
        return False, "\n".join(f"- {e}" for e in errors[:10])

    while current_iteration < max_tool_iterations:
        current_iteration += 1
        loop_meta["iterations"] = current_iteration
        
        print(f"     [Tool] AI Thinking (iteration {current_iteration})...", flush=True)
        if heartbeat:
            heartbeat.set_message(f"AI Thinking (iteration {current_iteration})")
        
        # Build current turn's prompt
        current_prompt = prompt
        if internal_retry_correction:
            current_prompt += f"\n\n{internal_retry_correction}"
        
        ai_response, stream_fallback_used = _run_ai_completion_with_streaming_policy(
            ai_provider=ai_provider,
            ai_model=ai_model,
            prompt=current_prompt,
            context_files=context_files,
            prompt_sections=prompt_sections,
            agent_name="construqtor",
            task_type="direct_coding",
            output_tokens=current_output_tokens,
            tools=DIRECT_CODING_TOOLS,
            allow_tool_streaming=True,
            streaming_policy=streaming_policy,
            stream_label="direct-tool-turn",
        )
        loop_meta["ai_call_count"] += 1
        if stream_fallback_used:
            loop_meta["stream_fallback_count"] += 1
        
        # A response might be a dict (tool use) or a string (text fallback)
        tool_calls = []
        response_text = ""
        response_truncated = False
        if isinstance(ai_response, dict):
            tool_calls = ai_response.get("tool_calls") or []
            response_text = ai_response.get("text") or ""
            response_truncated = bool(ai_response.get("truncated", False))
        else:
            response_text = str(ai_response)
        if response_truncated:
            loop_meta["truncated_responses"] += 1
        loop_meta["tool_calls_seen"] += len(tool_calls)
        
        # v1.3.12: Fallback logic for toolless responses or empty tool calls
        if not tool_calls:
            # Check for fenced blocks as a fallback compatibility measure
            extracted = _extract_ai_output_files(response_text, qodeyard_path)

            if extracted:
                print(f"     [Tool] No tool calls, but found {len(extracted)} fenced blocks. Falling back...", flush=True)
                extracted_filtered, dropped = _filter_extracted_files_to_allowlist(
                    extracted,
                    allowed_norm,
                )
                if dropped:
                    loop_meta["disallowed_path_calls"] = loop_meta.get("disallowed_path_calls", 0) + len(dropped)
                    print(
                        "     [Tool] 🚫 Dropped out-of-scope fenced fallback files: "
                        + ", ".join(sorted(dropped)),
                        flush=True,
                    )
                for rel_path, content in extracted_filtered.items():
                    target_path = validation_root / rel_path
                    try:
                        _write_text(target_path, content, jail=validation_root)
                        modified_files[rel_path] = content
                    except Exception as e:
                        print(f"     [Tool] ❌ Failed fallback write for {rel_path}: {e}", flush=True)
                break
            else:
                # No tools and no blocks
                if current_iteration == 1:
                    print(f"     [Tool] ❌ AI emitted no tools and no file blocks.", flush=True)
                    # We'll break and let downstream decide if it's a failure
                else:
                    print(f"     [Tool] No more changes requested by AI.", flush=True)
                break
            
        current_batch_modified = []
        iteration_parse_failures = 0
        iteration_apply_errors = 0
        large_payload_parse_failure = False
        for call in tool_calls:
            func = call.get("function", {})
            name = func.get("name")
            args_str = func.get("arguments", "{}")
            arg_chars = len(str(args_str))
            if arg_chars > loop_meta["max_tool_argument_chars"]:
                loop_meta["max_tool_argument_chars"] = arg_chars
            args, parse_err = _parse_direct_tool_arguments(args_str)
            if args is None:
                iteration_parse_failures += 1
                if arg_chars >= 1800 and ("content" in str(args_str) or "content_base64" in str(args_str)):
                    large_payload_parse_failure = True
                    loop_meta["large_payload_parse_failures"] += 1
                
                preview = str(args_str).replace("\n", "\\n")
                # v1.3.13: More helpful error for large payload failures
                err_suffix = " (likely truncation or malformed JSON)" if arg_chars > 2000 else ""
                print(
                    f"     [Tool] ❌ Failed to parse tool arguments ({parse_err}){err_suffix}: {preview[:200]}...",
                    flush=True,
                )
                continue
                
            if name == "write_file_direct":
                rel_path = str(args.get("path", "")).strip().replace("\\", "/")
                # v1.3.13: Robust path normalization
                while rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                if rel_path.startswith("qodeyard/"):
                    rel_path = rel_path[len("qodeyard/"):]
                
                content = args.get("content")
                content_base64 = args.get("content_base64")
                if (content is None or content == "") and content_base64:
                    try:
                        import base64
                        content = base64.b64decode(str(content_base64), validate=True).decode("utf-8")
                    except Exception as exc:
                        iteration_apply_errors += 1
                        print(f"     [Tool] ❌ Invalid content_base64 for {rel_path or '<unknown>'}: {exc}", flush=True)
                        continue
                if content is None:
                    iteration_apply_errors += 1
                    print(f"     [Tool] ❌ Missing content for write_file_direct: {rel_path or '<unknown>'}", flush=True)
                    continue
                if not isinstance(content, str):
                    content = str(content)
                append_mode = bool(args.get("append", False))

                if not rel_path:
                    iteration_apply_errors += 1
                    print("     [Tool] ❌ Empty file path for write_file_direct", flush=True)
                    continue
                if allowed_norm and rel_path not in allowed_norm:
                    loop_meta["disallowed_path_calls"] += 1
                    iteration_apply_errors += 1
                    print(f"     [Tool] 🚫 Blocked out-of-scope path for direct transport: {rel_path} (Allowed: {', '.join(sorted(allowed_norm))})", flush=True)
                    continue
                if is_infra_path(rel_path):
                    iteration_apply_errors += 1
                    print(f"     [Tool] 🚫 Blocked infra path: {rel_path}", flush=True)
                    continue
                
                target_path = validation_root / rel_path
                if append_mode and target_path.exists():
                    try:
                        prior = target_path.read_text(encoding='utf-8')
                    except Exception:
                        prior = ""
                    content = prior + content
                
                # Content-aware change detection
                is_changed = True
                if target_path.exists():
                    try:
                        existing_content = target_path.read_text(encoding='utf-8')
                        if existing_content == content:
                            is_changed = False
                    except Exception:
                        pass

                if not is_changed:
                    print(f"     - [Tool] No changes for {rel_path}", flush=True)
                    continue

                try:
                    # v1.3.12: Use hardened write helper with explicit jail
                    _write_text(target_path, content, jail=validation_root)
                    print(f"     - [Tool] Wrote {rel_path}", flush=True)
                    modified_files[rel_path] = content
                    if rel_path not in loop_meta["written_files"]:
                        loop_meta["written_files"].append(rel_path)
                    current_batch_modified.append(rel_path)
                except Exception as e:
                    iteration_apply_errors += 1
                    print(f"     [Tool] ❌ Failed to write {rel_path}: {e}", flush=True)
            else:
                # Unknown tool name from model output.
                iteration_apply_errors += 1
                print(f"     [Tool] ⚠️ Unknown tool call name: {name}", flush=True)
        
        loop_meta["parse_failures"] += iteration_parse_failures
        loop_meta["apply_errors"] += iteration_apply_errors
        if not current_batch_modified:
            no_progress_streak += 1
            loop_meta["no_progress_iterations"] = no_progress_streak
            if iteration_parse_failures or iteration_apply_errors:
                parse_error_streak += 1
                if response_truncated:
                    consecutive_truncated_tool_errors += 1
                    if current_output_tokens is not None and current_output_tokens < max_direct_output_tokens:
                        boosted_tokens = min(
                            max_direct_output_tokens,
                            max(current_output_tokens + 512, int(current_output_tokens * 1.5)),
                        )
                        if boosted_tokens > current_output_tokens:
                            print(
                                f"     [Tool] ⚙️ Increased output token budget for retry: "
                                f"{current_output_tokens} -> {boosted_tokens}",
                                flush=True,
                            )
                            current_output_tokens = boosted_tokens
                else:
                    consecutive_truncated_tool_errors = 0

                if loop_meta.get("disallowed_path_calls", 0) >= 2 and no_progress_streak >= 2:
                    print(
                        "     [Tool] 🛑 Repeated out-of-scope tool calls with no progress; stopping direct loop early.",
                        flush=True,
                    )
                    break

                should_attempt_fallback = (
                    not fallback_markdown_attempted
                    and (
                        current_iteration >= max_tool_iterations
                        or parse_error_streak >= 3
                        or (
                            parse_error_streak >= 2
                            and (large_payload_parse_failure or loop_meta["large_payload_parse_failures"] >= 1)
                        )
                        or consecutive_truncated_tool_errors >= 2
                        or (
                            response_truncated
                            and iteration_parse_failures > 0
                            and (large_payload_parse_failure or loop_meta["large_payload_parse_failures"] >= 1)
                        )
                    )
                )
                if should_attempt_fallback:
                    fallback_markdown_attempted = True
                    loop_meta["fallback_used"] = True
                    print(
                        "     [Tool] ⚠️ Tool-call failures persisted; switching early to fenced-block fallback for this briq.",
                        flush=True,
                    )
                    fallback_tokens = current_output_tokens
                    if fallback_tokens is None:
                        fallback_tokens = fallback_output_tokens
                    fallback_tokens = max(fallback_tokens, fallback_output_tokens)
                    fallback_tokens = min(fallback_tokens, max_direct_output_tokens)
                    fallback_prompt = (
                        current_prompt
                        + "\n\nDIRECT TOOL MODE FAILED DUE TO MALFORMED/TRUNCATED TOOL JSON.\n"
                        + "Fallback now: DO NOT call any tools.\n"
                        + "Return ONLY fenced file blocks using this format exactly:\n"
                        + "```language:qodeyard/<path>\n<full file content>\n```\n"
                        + "Include complete file bodies for files you need to change.\n"
                        + "Do not omit required primary deliverables.\n"
                    )
                    fallback_response_text = ""
                    try:
                        fallback_response_text, fallback_stream_fallback = _run_ai_completion_with_streaming_policy(
                            ai_provider=ai_provider,
                            ai_model=ai_model,
                            prompt=fallback_prompt,
                            context_files=context_files,
                            prompt_sections=prompt_sections,
                            agent_name="construqtor",
                            task_type="direct_coding",
                            output_tokens=fallback_tokens,
                            streaming_policy=streaming_policy,
                            stream_label="direct-markdown-fallback",
                        )
                        loop_meta["ai_call_count"] += 1
                        if fallback_stream_fallback:
                            loop_meta["stream_fallback_count"] += 1
                    except Exception as exc:
                        print(f"     [Tool] ❌ Fallback fenced-block request failed: {exc}", flush=True)
                        fallback_response_text = ""

                    extracted_files = _extract_ai_output_files(str(fallback_response_text), qodeyard_path)
                    if extracted_files:
                        # v1.3.13: Filter fallback extraction by allowed_paths to prevent scope-creep
                        fallback_filtered, dropped = _filter_extracted_files_to_allowlist(
                            extracted_files,
                            allowed_norm,
                        )
                        if dropped:
                             print(f"     - [Tool] Dropped out-of-scope fallback files: {', '.join(sorted(dropped))}", flush=True)
                             loop_meta["disallowed_path_calls"] = loop_meta.get("disallowed_path_calls", 0) + len(dropped)

                        for norm_path, content in fallback_filtered.items():
                            if not norm_path or is_infra_path(norm_path):
                                continue
                            try:
                                _write_text(validation_root / norm_path, content, jail=validation_root)
                                modified_files[norm_path] = content
                                current_batch_modified.append(norm_path)
                                print(f"     - [Tool] Fallback wrote {norm_path}", flush=True)
                            except Exception as exc:
                                print(f"     [Tool] ❌ Fallback write failed for {norm_path}: {exc}", flush=True)
                        if current_batch_modified:
                            consecutive_truncated_tool_errors = 0
                            parse_error_streak = 0
                        else:
                            print(
                                "     [Tool] No files modified and tool-call errors persisted through max iterations.",
                                flush=True,
                            )
                            break
                    else:
                            print(
                                "     [Tool] No files modified and tool-call errors persisted through max iterations.",
                                flush=True,
                            )
                            break
                elif no_progress_streak >= max_no_progress_iterations:
                    print(
                        f"     [Tool] 🛑 No-progress streak ({no_progress_streak}) reached threshold; ending direct loop.",
                        flush=True,
                    )
                    break
                elif current_iteration < max_tool_iterations:
                    print("     [Tool] ⚠️ Tool call errors detected; requesting corrected tool arguments.", flush=True)
                    truncation_hint = ""
                    if response_truncated:
                        truncation_hint = (
                            "Your previous response was truncated before the JSON tool payload completed.\n"
                            "You MUST emit smaller tool payloads.\n"
                            "For large files, call write_file_direct multiple times with append=true "
                            "and chunk each content/content_base64 payload to <= 900 chars.\n"
                        )
                    internal_retry_correction = (
                        "TOOL ARGUMENT FORMAT ERROR:\n"
                        f"- parse_failures: {iteration_parse_failures}\n"
                        f"- apply_errors: {iteration_apply_errors}\n"
                        f"- response_truncated: {response_truncated}\n"
                        f"- large_payload_parse_failure: {large_payload_parse_failure}\n"
                        + truncation_hint +
                        "Re-emit write_file_direct tool calls as VALID JSON.\n"
                        "Use keys: path + content (or content_base64 for large multiline bodies).\n"
                        "If chunking large files, call write_file_direct repeatedly with append=true.\n"
                        "Do not emit malformed JSON."
                    )
                    continue
                else:
                    print("     [Tool] No files modified and tool-call errors persisted through max iterations.", flush=True)
                    break
            else:
                parse_error_streak = 0
                print(f"     [Tool] No NEW files modified in this iteration. Finalizing.", flush=True)
                break
        else:
            no_progress_streak = 0
            loop_meta["no_progress_iterations"] = 0
            parse_error_streak = 0
            consecutive_truncated_tool_errors = 0
            
        # INTERATIVE REPAIR-FORWARD: Validate the CUMULATIVE delta
        all_modified = sorted(list(modified_files.keys()))
        passed, error_msg = _validate_current_sandbox(all_modified)
        batch_validation_record = {
            "batch_index": len(loop_meta["validated_batches"]) + 1,
            "batch_files": sorted(current_batch_modified),
            "cumulative_files": list(all_modified),
            "status": "PASS" if passed else "FAIL",
        }
        if passed:
            loop_meta["validated_batches"].append(batch_validation_record)
            print(f"     [Tool] ✅ Group validation passed for cumulative batch", flush=True)
            # Freeze on first passing cumulative candidate inside the attempt.
            break
        else:
            batch_validation_record["error_preview"] = error_msg[:500]
            loop_meta["validated_batches"].append(batch_validation_record)
            loop_meta["last_failed_batch"] = sorted(current_batch_modified)
            autofix = _apply_trivial_autofix(all_modified, [validation_root])
            if autofix.get("applied"):
                cats = ", ".join(autofix.get("categories", [])) or "trivial fixes"
                print(f"     [Tool] 🔧 Applied deterministic autofix ({cats})", flush=True)
                passed_after_fix, error_after_fix = _validate_current_sandbox(all_modified)
                if passed_after_fix:
                    print(f"     [Tool] ✅ Validation passed after deterministic autofix", flush=True)
                    break
                error_msg = error_after_fix
            print(f"     [Tool] ❌ Validation failed. Requesting repair...", flush=True)
            internal_retry_correction = f"ITERATIVE REPAIR REQUIRED:\nThe following issues were found in the cumulative set of modified files. Fix them and re-write the affected files:\n{error_msg}"

    if lib_sandbox_diff:
        diff_changes = lib_sandbox_diff.detect_sandbox_changes(validation_root, qodeyard_path)
        # Merge diff_changes into modified_files (diff is more authoritative)
        modified_files.update(diff_changes)
    
    if return_meta:
        return modified_files, loop_meta
    return modified_files

# ═══════════════════════════════════════════════════════════════════════════════
# PER-BRIQ PROCESSING WITH INTERLEAVED REVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def _build_core_prompt(coding_mode: str, context_type: str, mode: str, mode_prompt: str) -> str:
    """Build the core prompt instructions based on the active coding mode."""
    
    base_instructions = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan defined in the 'briq'.
**CONTEXT:** You have been provided with the {context_type} of the existing codebase. Use this structural context to ensure your generated code integrates correctly with the existing project.
**ABSOLUTE DIRECTIVE:** ALL code output MUST be written to the `qodeyard/` directory.
Your output files live at repo root. Never import using qodeyard or any workspace-internal path.

━━━ 🚫 HARD PATH RULES (v1.3.10 — strictly enforced) ━━━
The `qodeyard/` directory IS the project root. Place source files directly in it.
  ❌ DO NOT wrap the project inside a subfolder named after the project, run,
     or qonstruction. Forbidden patterns include (but are not limited to):
        `qodeyard/<project-name>/main.py`   ← WRONG
        `qodeyard/<run-name>/src/app.py`    ← WRONG
        `qodeyard/my-api/server.js`         ← WRONG
     CORRECT: `qodeyard/main.py`, `qodeyard/src/app.py`, `qodeyard/server.js`.
  ❌ DO NOT emit file paths under any of these qonqrete-internal directories:
        build/   attempts/   validation-root/   recovery/   staging/
        reqap.d/   .qonqrete/   qonstructions/   struqture/
        exeq.d/   qontext.d/   bloq.d/   tasq.d/   briq.d/   qontract.d/
        qache.d/   planning/   qage_*/
  ✅ If the file tree shown to you contains any of the above, IGNORE those
     entries — they are transient runtime state, NOT part of the codebase.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
"""

    if coding_mode == 'direct':
        mode_specific = """
**OUTPUT FORMAT:** You MUST use the `write_file_direct` tool to write or update files in the workspace. 
Call the tool for each file you need to create or modify. 
Do NOT use markdown code blocks for the final file output; use the tool instead.
Tool-call arguments MUST be valid JSON.
For large multiline payloads, prefer `content_base64` (base64-encoded UTF-8 content).
If splitting large files into multiple calls, use `append: true` on follow-up chunks.
"""
    elif coding_mode == 'hybrid':
        mode_specific = """
**OUTPUT FORMAT (HYBRID POLICY):** Transport is policy-selected per file and included in the prompt context.
- For files assigned `direct`: you MUST use `write_file_direct` with valid JSON arguments.
- For files assigned `heredoc`: you MUST emit fenced file blocks only using this exact format:
```language:qodeyard/<path>
<full file content>
```
Do NOT invent your own transport choices. Follow the assigned transport list exactly.
Never rewrite unrelated files.
When emitting heredoc blocks, output ONLY file blocks and no extra commentary.
"""
    else:
        # heredoc mode (legacy)
        mode_specific = """
**OUTPUT FORMAT:** You MUST format your response using markdown code blocks. 
Each file must have its path specified after the language in the format `language:path/to/file.ext`.

**EXAMPLE:**
```python:qodeyard/main.py
print("Hello, World!")
```

**RESTRICTION:** GENERATE ONLY THE FILE BLOCKS AS SHOWN IN THE EXAMPLE. Do not add any other text, conversation, or explanations outside the markdown blocks.
"""

    return f"{base_instructions}\n{mode_specific}\n**MODE:** {mode.upper()}\n{mode_prompt}\n"


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
    qontract_json_path: Path = None,   # v1.3.0: Path to qontract.json for per-briq Qonfirmer gate
    contract_data: dict = None,         # v1.3.0: Loaded contract dict
    planning_payload: dict = None,
    completion_criteria_payload: dict | None = None,
    component_contracts_payload: dict = None,
    write_strategy_config: dict | None = None,
    execution_backend: dict | None = None,
    repo_config: dict | None = None,
) -> dict:
    """
    Process a single briq with interleaved build + review.
    
    Flow:
    1. Build briq (generate code)
    2. Run local validation (syntax, imports)
    3. v1.3.0: If contract-relevant, run Qonfirmer on written files
    4. If the Qonfirmer gate fails → auto-retry with correction directive (max 2-3 attempts)
    5. Optionally run AI quick review
    6. Write per-briq exeQ summary
    
    Returns:
        {
            'briq_file': str,
            'status': 'success' | 'partial' | 'failure',
            'written_files': list[str],
            'validation': dict,
            'review': dict,
            'qonfirmer_report': dict | None,
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
        'qonfirmer_report': None,
        'attempts': 0,
        'error': None,
        'exeq_path': None,
        'metadata': {},
        'attempt_records': [],
        'repair_escalation': {},
        'execution_backend': execution_backend or {},
        'write_strategy': (write_strategy_config or {}).get('mode', DEFAULT_WRITE_STRATEGY['mode']),
        'coding_mode': (write_strategy_config or {}).get('coding_mode', DEFAULT_WRITE_STRATEGY['coding_mode']),
    }
    
    coding_mode = result['coding_mode']
    hybrid_policy_cfg = copy.deepcopy(
        (write_strategy_config or {}).get('hybrid_policy', DEFAULT_WRITE_STRATEGY.get('hybrid_policy', {}))
    )
    effective_repo_config = repo_config if isinstance(repo_config, dict) else {}
    repair_escalation_cfg = get_repair_escalation_config(effective_repo_config)
    streaming_policy = get_streaming_policy(effective_repo_config)
    repair_plan_payload = {}
    if os.environ.get("QONQ_REPAIR_MODE") == "1":
        repair_plan_path = os.environ.get("QONQ_REPAIR_PLAN_PATH")
        if repair_plan_path:
            repair_plan_payload = load_optional_json(Path(repair_plan_path))
    repair_plan_escalation = (
        repair_plan_payload.get("repair_escalation", {})
        if isinstance(repair_plan_payload.get("repair_escalation"), dict)
        else {}
    )
    repair_plan_target_files = sorted(list(set(
        repair_plan_payload.get("target_files") or []
    )))
    recommended_failure_class = normalize_failure_class(
        repair_plan_escalation.get("recommended_failure_class")
    )
    recommended_start_level = repair_plan_escalation.get("recommended_start_level")
    try:
        recommended_start_level = int(recommended_start_level) if recommended_start_level is not None else None
    except Exception:
        recommended_start_level = None
    initial_level = max(1, min(int(repair_escalation_cfg.get("max_level", 4) or 4), recommended_start_level or 1))
    pending_repair_level = initial_level
    pending_failure_class = recommended_failure_class
    pending_escalation_reason = str(repair_plan_escalation.get("reason") or "initial_attempt")
    completed_failure_records: list[dict] = list(repair_plan_escalation.get("prior_attempt_records", []) or [])
    hybrid_transport_locks: dict[str, str] = {}
    hybrid_direct_failure_counts: dict[str, int] = {}
    hybrid_missing_required_counts: dict[str, int] = {}
    
    # Read briq content
    try:
        with open(briq_file, 'r', encoding='utf-8') as f:
            briq_content = f.read()
    except Exception as e:
        result['error'] = f"Could not read briq: {e}"
        return result

    briq_metadata = parse_briq_metadata(briq_content)
    result['metadata'] = briq_metadata

    # v1.3.0: Parse Contract-Relevant header from briq
    is_contract_relevant = False
    if re.search(r'^Contract-Relevant:\s*yes', briq_content, re.MULTILINE | re.IGNORECASE):
        is_contract_relevant = True
    constitutional_sections = constitutional_sections or {}
    active_component_contract = get_component_contract(briq_metadata, component_contracts_payload or {})
    active_component_constraints = [
        str(item).strip()
        for item in active_component_contract.get('constraints', [])
        if str(item).strip()
    ]
    grouped_context = build_group_context(
        briq_metadata,
        planning_payload or {},
        component_contracts_payload or {}
    )
    repair_context = load_repair_context(worqspace_root)
    briq_targets = extract_briq_target_files(briq_content)
    completion_required_files = _resolve_completion_required_files(completion_criteria_payload)
    primary_deliverables = _resolve_briq_primary_deliverables(
        briq_metadata,
        briq_targets,
        planning_payload if isinstance(planning_payload, dict) else None,
        completion_required_files,
    )
    if os.environ.get("QONQ_REPAIR_MODE") == "1" and repair_plan_target_files:
        # Surgical repair: focus only on files identified by InspeQtor
        primary_deliverables = [f for f in primary_deliverables if f in repair_plan_target_files]

    result['metadata']['target_files'] = briq_targets
    result['metadata']['primary_deliverables'] = primary_deliverables
    result['metadata']['completion_required_files'] = completion_required_files
    validation_scope_files = _resolve_repair_scope_files(
        worqspace_root,
        repair_plan_payload=repair_plan_payload,
        briq_metadata=briq_metadata,
        briq_targets=briq_targets,
        primary_deliverables=primary_deliverables,
    )
    result['metadata']['validation_scope_files'] = validation_scope_files
    qontext_path = worqspace_root / "qontext.d"
    filtered_context_files = _select_context_files_for_briq(
        all_context_files,
        briq_targets,
        qontext_path,
        max_files=DEFAULT_CONTEXT_FILES_PER_ATTEMPT,
    )
    
    # Build prompt
    core_prompt = _build_core_prompt(coding_mode, context_type, mode, mode_prompt)
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
    # v1.3.13: Six-Shooter Qontract selective ingestion
    six_shooter_docs = (constitutional_sections or {}).get("six_shooter_docs", {})
    if six_shooter_docs:
        # 01-execution-plan and 05-target-state are always included as core anchors
        always_docs = ["01", "05"]
        contextual_docs = []
        briq_tags = [str(t).lower() for t in (briq_metadata.get("scope_tags") or [])]
        if any(t in briq_tags for t in ("migration", "bridge", "legacy")):
            contextual_docs.append("03")
        if any(t in briq_tags for t in ("contract", "api", "interface", "endpoint")):
            contextual_docs.append("04")
        if any(t in briq_tags for t in ("rules", "strict", "invariant", "hard-rules")):
            contextual_docs.append("02")
        
        # Keyword-based fallback for contextual selection
        briq_lower = briq_content.lower()
        if "03" not in contextual_docs and ("migration" in briq_lower or "legacy" in briq_lower):
            contextual_docs.append("03")
        if "04" not in contextual_docs and ("contract" in briq_lower or "interface" in briq_lower or "api" in briq_lower):
            contextual_docs.append("04")
        if "02" not in contextual_docs and ("rule" in briq_lower or "invariant" in briq_lower or "strict" in briq_lower):
            contextual_docs.append("02")

        selected_ids = sorted(list(set(always_docs + contextual_docs)))
        for doc_id in selected_ids:
            found_name = next((n for n in six_shooter_docs if n.startswith(doc_id)), None)
            if found_name:
                label_pretty = found_name.split('-', 1)[-1].replace('.md', '').upper().replace('-', ' ')
                prompt_sections.append({
                    'label': f'six_shooter_{doc_id}',
                    'content': f"**PROJECT CONSTITUTION ({label_pretty} — MUST OBEY):**\n{six_shooter_docs[found_name]}\n",
                    'required': True,
                    'loss_policy': 'chunkable',
                    'section_type': 'contract',
                })

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
    briq_output_tokens = _resolve_briq_output_tokens(
        briq_content,
        briq_targets,
        coding_mode,
    )

    # Track correction directives for deterministic validation / Qonfirmer retries.
    retry_correction = ""

    # v1.3.13: Level 0 Verification Gate (Recheck before repair)
    if os.environ.get("QONQ_REPAIR_MODE") == "1":
        if repair_plan_target_files:
            repair_targets = sorted([f for f in (validation_scope_files or briq_targets or primary_deliverables) if f in repair_plan_target_files])
            if not repair_targets:
                 print(f"     [Level 0] No repair targets for {briq_name} in the global plan. Skipping.", flush=True)
                 result['status'] = 'success'
                 result['written_files'] = []
                 result['attempts'] = 0
                 return result
        else:
            repair_targets = sorted(primary_deliverables)
            if not repair_targets:
                 print(f"     [Level 0] No primary deliverables for {briq_name} to recheck. Proceeding.", flush=True)
                 repair_targets = []

        if repair_targets:
            print(f"     [Level 0] Rechecking existing state for {len(repair_targets)} target(s) in {briq_name}:", flush=True)
            for t in repair_targets:
                 print(f"       - {t}", flush=True)

            l0_state = _evaluate_repair_scope_state(
                worqspace_root,
                qodeyard_path,
                repair_targets=repair_targets,
                validation_scope_files=validation_scope_files or repair_targets,
                is_contract_relevant=is_contract_relevant,
                contract_data=contract_data,
                build_group=briq_metadata.get('build-group') or briq_metadata.get('build_group'),
                repair_plan_payload=repair_plan_payload,
            )
            result['metadata']['level0_scope_files'] = l0_state.get('scope_files', [])
            if l0_state.get('passed'):
                print(f"     [Level 0] ✅ EXISTING STATE VERIFIED. Skipping repair for this briq.", flush=True)
                result['status'] = 'success'
                result['written_files'] = repair_targets
                result['attempts'] = 0
                result['qonfirmer_report'] = l0_state.get('qonfirmer_report')
                return result
            if l0_state.get('missing_targets'):
                for rel_path in l0_state.get('missing_targets', []):
                    print(f"     [Level 0] Target missing: {rel_path}", flush=True)
            if l0_state.get('open_fingerprints'):
                print(
                    "     [Level 0] Open deterministic issues still reproduce: "
                    + _render_open_fingerprint_summaries(l0_state.get('open_fingerprints', [])),
                    flush=True,
                )
            elif l0_state.get('deterministic_issues'):
                print(f"     [Level 0] Deterministic validation still fails in the repair scope.", flush=True)
            print(f"     [Level 0] ❌ Existing state is invalid. Proceeding with repair loop.", flush=True)
        else:
            print(f"     [Level 0] No repair targets identified for {briq_name}. Proceeding with repair loop.", flush=True)

    def _plan_retry_after_failure(
        *,
        attempt_number: int,
        failure_status: str,
        error_message: str,
        direct_meta: dict,
        validation_payload: dict,
        qonfirmer_payload: dict | None,
        missing_primary: list[str],
        target_files: list[str],
        violation_rows: list[str],
    ) -> tuple[str, int, str, str, str]:
        failure_class, failure_reason = classify_attempt_failure(
            failure_status=failure_status,
            error_message=error_message,
            direct_loop_meta=direct_meta,
            validation=validation_payload,
            qonfirmer_report=qonfirmer_payload or {},
            missing_primary_outputs=missing_primary,
        )
        fingerprint_seed = "\n".join(
            [
                failure_status or "",
                failure_class,
                failure_reason,
                *(violation_rows or []),
                *(missing_primary or []),
            ]
        )
        fingerprint = sha256_text(fingerprint_seed)[:16]
        next_level, escalation_reason = choose_repair_level(
            config=effective_repo_config,
            attempt_index=attempt_number + 1,
            failure_class=failure_class,
            failure_fingerprint=fingerprint,
            prior_attempt_records=completed_failure_records,
            recommended_start_level=recommended_start_level if attempt_number == 1 else None,
        )
        base = retry_correction.strip() if retry_correction else (
            "REPAIR REQUIRED:\n"
            f"- Failure status: {failure_status}\n"
            f"- Error: {error_message or failure_reason}\n"
            "Fix the defects and regenerate only the affected files.\n"
        )
        enriched = build_escalated_retry_correction(
            repair_level=next_level,
            failure_class=failure_class,
            escalation_reason=escalation_reason,
            base_directive=base,
            target_files=target_files,
            violation_rows=violation_rows,
        )
        return enriched, next_level, failure_class, f"{escalation_reason}; {failure_reason}", fingerprint

    # Retry loop with interleaved review
    last_briq_attempt_fingerprint = ""
    heartbeat = Heartbeat("Initializing attempt")
    for attempt in range(1, max_attempts + 1):
        attempt_start_time = time.time()
        result['attempts'] = attempt
        attempt_failure_status = "failed_validation"
        active_repair_level = pending_repair_level
        active_failure_class = pending_failure_class
        active_escalation_reason = pending_escalation_reason
        attempt_failure_fingerprint = ""
        attempt_violation_rows: list[str] = []
        current_failure_reason = ""
        current_failure_class = active_failure_class

        # Tracking metrics for this attempt
        attempt_metrics = {
            "attempt_start_timestamp": attempt_start_time,
            "retry_sleep_duration_sec": 0,
            "validation_duration_sec": 0,
            "qonfirmer_duration_sec": 0,
            "ai_call_count": 0,
            "tool_iteration_count": 0,
            "stream_fallback_count": 0,
        }

        heartbeat.start(attempts=attempt, exeq_count=len(committed_written_files))

        if attempt > 1:
            heartbeat.set_message("Repair cooling down")
            print(f"Repair build for {briq_metadata.get('build-group', 'ungrouped')}", flush=True)
            print(f"     [RETRY] Attempt {attempt}/{max_attempts}", flush=True)
            print(
                f"     [REPAIR] escalation level={active_repair_level} class={active_failure_class} ({active_escalation_reason})",
                flush=True,
            )
            adaptive_retry_delay = float(retry_delay)
            if active_failure_class in {
                "transport_write_failure",
                "runtime_syntax_launch_failure",
                "exact_validator_violation",
                "required_output_missing",
            }:
                adaptive_retry_delay = min(adaptive_retry_delay, 0.25)
            if adaptive_retry_delay > 0:
                time.sleep(adaptive_retry_delay)
            attempt_metrics["retry_sleep_duration_sec"] = adaptive_retry_delay
        try:
            # STEP 1: Build (AI code generation)
            current_prompt = ""
            current_sections = []
            for section in prompt_sections:
                label = section.get('label', '')
                # Keep large global anchors on first attempt only.
                if attempt > 1 and label in {'cycle1_tasq_anchor', 'project_structure_tree'}:
                    continue
                current_sections.append(dict(section))

            # v1.3.13: Surgical repair directive
            if os.environ.get("QONQ_REPAIR_MODE") == "1" and repair_plan_target_files:
                surgical_text = (
                    "**SURGICAL REPAIR DIRECTIVE (MUST OBEY):**\n"
                    "This is a precision repair pass. You MUST ONLY modify the following files:\n"
                    + "\n".join(f"- {f}" for f in sorted(repair_plan_target_files)) + "\n"
                    + "Do NOT touch any other files. If a file is not in this list, it is considered already correct.\n"
                )
                current_sections.insert(0, {
                    'label': 'surgical_repair_directive',
                    'content': surgical_text,
                    'required': True,
                    'loss_policy': 'preserve',
                    'section_type': 'instructions',
                })

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

            # Previous-agent logs are useful repair context, but only on repair attempts.
            previous_log_env = os.environ.get("QONQ_INCLUDE_PREVIOUS_LOG")
            os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = "1" if attempt > 1 else "0"

            attempt_context_cap = (
                DEFAULT_CONTEXT_FILES_PER_ATTEMPT
                if attempt == 1
                else RETRY_CONTEXT_FILES_PER_ATTEMPT
            )
            attempt_context_files = filtered_context_files[:attempt_context_cap]
            
            print("Writing code", flush=True)
            print(f"     - Sending to AI (attempt {attempt})...", flush=True)
            
            attempt_id = f"{canonical_run_id(worqspace_root)}-cyqle{os.environ.get('CYCLE_NUM', '1')}-{briq_name}-attempt{attempt:02d}"
            attempt_root = worqspace_root / "build" / "attempts" / attempt_id
            validation_root = attempt_root / "validation-root"
            
            extracted_files = {}
            hybrid_transport_decisions: list[dict] = []
            hybrid_fallback_events: list[dict] = []
            direct_targets_for_attempt: list[str] = []

            direct_loop_meta = {
                "iterations": 0,
                "ai_call_count": 0,
                "tool_calls_seen": 0,
                "parse_failures": 0,
                "apply_errors": 0,
                "stream_fallback_count": 0,
            }
            try:
                if coding_mode == 'direct':
                    print(f"     [Mode] direct coding enabled (sandbox + repair-forward)", flush=True)
                    # v1.3.13: Surgical repair focus. In repair mode, we anchor on 
                    # primary_deliverables to avoid collateral damage to dependencies 
                    # that are merely in Target-Files.
                    if os.environ.get("QONQ_REPAIR_MODE") == "1":
                        repair_anchor = primary_deliverables if primary_deliverables else briq_targets
                    else:
                        repair_anchor = set(primary_deliverables or []) | set(briq_targets or [])
                    
                    direct_targets_for_attempt = sorted(set(repair_anchor or []))
                    
                    if os.environ.get("QONQ_REPAIR_MODE") == "1" and repair_plan_target_files:
                        # Only repair files that are actually in the repair plan's target list
                        direct_targets_for_attempt = [
                            f for f in direct_targets_for_attempt
                            if f in repair_plan_target_files
                        ]

                    direct_targets_for_attempt = [
                        path for path in direct_targets_for_attempt if str(path).strip() and not is_infra_path(path)
                    ]
                    direct_sections = list(current_sections)
                    if direct_targets_for_attempt:
                        print(
                            "     [Direct] scoped targets: "
                            + ", ".join(direct_targets_for_attempt[:8])
                            + (" ..." if len(direct_targets_for_attempt) > 8 else ""),
                            flush=True,
                        )
                        direct_sections.append(
                            {
                                "label": "direct_transport_assignment",
                                "content": (
                                    "DIRECT SCOPE ASSIGNMENT:\n"
                                    + "Use write_file_direct only for these files:\n"
                                    + "\n".join(f"- {path}" for path in direct_targets_for_attempt)
                                    + "\nDo not modify any other file in this turn."
                                ),
                                "required": True,
                                "loss_policy": "preserve",
                                "section_type": "direct_transport_assignment",
                            }
                        )

                    direct_result = _run_direct_coding_loop(
                        ai_provider,
                        ai_model,
                        current_prompt,
                        direct_sections,
                        attempt_context_files,
                        validation_root,
                        qodeyard_path,
                        worqspace_root,
                        briq_metadata,
                        output_tokens=briq_output_tokens,
                        return_meta=True,
                        allowed_paths=set(direct_targets_for_attempt) if direct_targets_for_attempt else None,
                        streaming_policy=streaming_policy,
                    )
                    if isinstance(direct_result, tuple):
                        extracted_files, direct_loop_meta = direct_result
                    else:
                        extracted_files = direct_result
                    attempt_metrics["ai_call_count"] += int(direct_loop_meta.get("ai_call_count", 0) or 0)
                    attempt_metrics["tool_iteration_count"] += int(direct_loop_meta.get("iterations", 0) or 0)
                    attempt_metrics["stream_fallback_count"] += int(direct_loop_meta.get("stream_fallback_count", 0) or 0)
                    
                    # v1.3.11: If no files were modified in direct mode, it might mean the AI 
                    # correctly decided no changes were needed. We should treat this as success 
                    # if the briq's target files exist.
                    if not extracted_files:
                        print(f"     [Tool] AI decided no changes are needed for this briq.", flush=True)
                        # We'll allow it to pass through to validation below.
                elif coding_mode == 'hybrid':
                    print(f"     [Mode] hybrid coding enabled (policy-driven transport)", flush=True)

                    # v1.3.13: Surgical repair focus for heredoc mode
                    if os.environ.get("QONQ_REPAIR_MODE") == "1":
                        repair_anchor = primary_deliverables if primary_deliverables else briq_targets
                    else:
                        repair_anchor = set(primary_deliverables or []) | set(briq_targets or [])
                        
                    candidate_files = sorted(set(repair_anchor or []))
                    
                    if os.environ.get("QONQ_REPAIR_MODE") == "1" and repair_plan_target_files:
                        # Only repair files that are actually in the repair plan's target list
                        candidate_files = [
                            f for f in candidate_files
                            if f in repair_plan_target_files
                        ]

                    candidate_files = [path for path in candidate_files if not is_infra_path(path)]
                    if not candidate_files:
                        print("     [Hybrid] No explicit target files found; defaulting this attempt to heredoc.", flush=True)

                        ai_result, stream_fallback_used = _run_ai_completion_with_streaming_policy(
                            ai_provider=ai_provider,
                            ai_model=ai_model,
                            prompt=current_prompt,
                            context_files=attempt_context_files,
                            prompt_sections=current_sections,
                            agent_name="construqtor",
                            task_type="code_generation",
                            output_tokens=briq_output_tokens,
                            streaming_policy=streaming_policy,
                            stream_label="hybrid-default-heredoc",
                        )
                        attempt_metrics["ai_call_count"] += 1
                        if stream_fallback_used:
                            attempt_metrics["stream_fallback_count"] += 1
                        extracted_files = _extract_ai_output_files(str(ai_result), qodeyard_path)
                        if extracted_files:
                            hybrid_transport_decisions = [
                                {
                                    "file_path": rel_path,
                                    "file_existed_pre_attempt": (qodeyard_path / rel_path).exists(),
                                    "chosen_transport": "heredoc",
                                    "decision_reason_codes": ["no_explicit_targets_default_heredoc"],
                                    "is_primary_deliverable": rel_path in set(primary_deliverables or []),
                                    "failure_counts_by_class": {"direct_transport_failures": 0},
                                    "transport_lock_state_before": str(hybrid_transport_locks.get(rel_path) or "unset"),
                                    "transport_lock_state_after": "heredoc",
                                    "fallback_occurred": False,
                                    "fallback_reason_code": None,
                                }
                                for rel_path in sorted(extracted_files.keys())
                            ]
                            for decision in hybrid_transport_decisions:
                                hybrid_transport_locks[decision["file_path"]] = "heredoc"
                    else:
                        hybrid_transport_decisions = _build_hybrid_transport_decisions(
                            briq_content=briq_content,
                            candidate_files=candidate_files,
                            primary_deliverables=primary_deliverables,
                            qodeyard_path=qodeyard_path,
                            transport_locks=hybrid_transport_locks,
                            direct_failure_counts=hybrid_direct_failure_counts,
                            missing_required_counts=hybrid_missing_required_counts,
                            policy_cfg=hybrid_policy_cfg,
                            attempt_index=attempt,
                        )
                        direct_targets_for_attempt = [
                            item["file_path"]
                            for item in hybrid_transport_decisions
                            if item.get("chosen_transport") == "direct"
                        ]
                        heredoc_targets_for_attempt = [
                            item["file_path"]
                            for item in hybrid_transport_decisions
                            if item.get("chosen_transport") == "heredoc"
                        ]

                        if direct_targets_for_attempt:
                            print(
                                "     [Hybrid] direct targets: "
                                + ", ".join(direct_targets_for_attempt[:8])
                                + (" ..." if len(direct_targets_for_attempt) > 8 else ""),
                                flush=True,
                            )
                            direct_sections = list(current_sections)
                            direct_sections.append(
                                {
                                    "label": "hybrid_transport_assignment_direct",
                                    "content": (
                                        "HYBRID TRANSPORT ASSIGNMENT (DIRECT ONLY):\n"
                                        + "Use write_file_direct only for these files:\n"
                                        + "\n".join(f"- {path}" for path in direct_targets_for_attempt)
                                        + "\nDo not modify any other file in this turn."
                                    ),
                                    "required": True,
                                    "loss_policy": "preserve",
                                    "section_type": "hybrid_transport_assignment",
                                }
                            )
                            direct_result = _run_direct_coding_loop(
                                ai_provider,
                                ai_model,
                                current_prompt,
                                direct_sections,
                                attempt_context_files,
                                validation_root,
                                qodeyard_path,
                                worqspace_root,
                                briq_metadata,
                                output_tokens=briq_output_tokens,
                                return_meta=True,
                                allowed_paths=set(direct_targets_for_attempt),
                                streaming_policy=streaming_policy,
                            )
                            if isinstance(direct_result, tuple):
                                direct_files, direct_loop_meta = direct_result
                            else:
                                direct_files = direct_result
                            attempt_metrics["ai_call_count"] += int(direct_loop_meta.get("ai_call_count", 0) or 0)
                            attempt_metrics["tool_iteration_count"] += int(direct_loop_meta.get("iterations", 0) or 0)
                            attempt_metrics["stream_fallback_count"] += int(direct_loop_meta.get("stream_fallback_count", 0) or 0)
                            extracted_files.update(direct_files or {})

                            direct_errors = int(direct_loop_meta.get("parse_failures", 0) or 0) + int(
                                direct_loop_meta.get("apply_errors", 0) or 0
                            )
                            if direct_errors > 0:
                                for target in direct_targets_for_attempt:
                                    hybrid_direct_failure_counts[target] = int(
                                        hybrid_direct_failure_counts.get(target, 0) or 0
                                    ) + 1
                            else:
                                for target in direct_targets_for_attempt:
                                    if target in direct_files:
                                        hybrid_direct_failure_counts[target] = 0

                            parse_failure_threshold = int(
                                hybrid_policy_cfg.get("direct_parse_failure_to_heredoc_threshold", 2) or 2
                            )
                            direct_fallback_triggered = bool(
                                int(direct_loop_meta.get("parse_failures", 0) or 0) >= parse_failure_threshold
                                or int(direct_loop_meta.get("large_payload_parse_failures", 0) or 0) > 0
                                or int(direct_loop_meta.get("disallowed_path_calls", 0) or 0) > 0
                                or bool(direct_loop_meta.get("fallback_used", False))
                            )
                            if direct_fallback_triggered:
                                for item in hybrid_transport_decisions:
                                    if item.get("file_path") in direct_targets_for_attempt:
                                        item["fallback_occurred"] = True
                                        if not item.get("fallback_reason_code"):
                                            item["fallback_reason_code"] = "direct_transport_failure"
                                        item["transport_lock_state_after"] = "heredoc"
                                        if "fallback:direct_transport_failure" not in item.get("decision_reason_codes", []):
                                            item.setdefault("decision_reason_codes", []).append(
                                                "fallback:direct_transport_failure"
                                            )
                                        hybrid_transport_locks[item["file_path"]] = "heredoc"
                                fallback_targets = [
                                    path for path in direct_targets_for_attempt if path not in set((direct_files or {}).keys())
                                ]
                                # v1.3.13: If _run_direct_coding_loop already used its internal fallback and we still
                                # have missing targets, don't immediately issue a second identical AI request.
                                # Let the outer repair cycle handle it with better context or escalation.
                                if fallback_targets and not direct_loop_meta.get("fallback_used"):
                                    print(
                                        "     [Hybrid] direct fragility detected; falling back to heredoc for: "
                                        + ", ".join(fallback_targets),
                                        flush=True,
                                    )
                                    fallback_sections = list(current_sections)
                                    fallback_sections.append(
                                        {
                                            "label": "hybrid_transport_assignment_heredoc_fallback",
                                            "content": (
                                                "HYBRID TRANSPORT FALLBACK (HEREDOC ONLY):\n"
                                                + "Return fenced blocks only for these files:\n"
                                                + "\n".join(f"- {path}" for path in fallback_targets)
                                                + "\nUse EXACT format for each file:\n"
                                                + "```language:qodeyard/<path>\n<full file content>\n```\n"
                                                + "Do not modify any other file in this turn.\n"
                                                + "Output only file blocks."
                                            ),
                                            "required": True,
                                            "loss_policy": "preserve",
                                            "section_type": "hybrid_transport_assignment",
                                        }
                                    )
                                    heartbeat.set_message("Fallback generating (AI)")
                                    fallback_ai_result, fallback_stream_fallback = _run_ai_completion_with_streaming_policy(
                                        ai_provider=ai_provider,
                                        ai_model=ai_model,
                                        prompt=current_prompt,
                                        context_files=attempt_context_files,
                                        prompt_sections=fallback_sections,
                                        agent_name="construqtor",
                                        task_type="code_generation",
                                        output_tokens=briq_output_tokens,
                                        streaming_policy=streaming_policy,
                                        stream_label="hybrid-heredoc-fallback",
                                    )
                                    attempt_metrics["ai_call_count"] += 1
                                    if fallback_stream_fallback:
                                        attempt_metrics["stream_fallback_count"] += 1
                                    fallback_extracted = _extract_ai_output_files(str(fallback_ai_result), qodeyard_path)
                                    fallback_filtered, dropped = _filter_extracted_files_to_allowlist(
                                        fallback_extracted,
                                        set(fallback_targets),
                                    )
                                    if dropped:
                                        print(
                                            "     [Hybrid] Dropped out-of-scope fallback files: "
                                            + ", ".join(sorted(dropped)),
                                            flush=True,
                                        )
                                    extracted_files.update(fallback_filtered)
                                    for item in hybrid_transport_decisions:
                                        if item.get("file_path") in fallback_targets:
                                            if item["file_path"] in fallback_filtered:
                                                item["chosen_transport"] = "heredoc"
                                                hybrid_fallback_events.append(
                                                    {
                                                        "file_path": item["file_path"],
                                                        "from_transport": "direct",
                                                        "to_transport": "heredoc",
                                                        "reason": "direct_transport_failure",
                                                    }
                                                )
                                elif fallback_targets:
                                     print(f"     [Hybrid] Skipping redundant outer fallback for {len(fallback_targets)} targets as inner fallback was already exhausted.", flush=True)

                        if heredoc_targets_for_attempt:
                            print(
                                "     [Hybrid] heredoc targets: "
                                + ", ".join(heredoc_targets_for_attempt[:8])
                                + (" ..." if len(heredoc_targets_for_attempt) > 8 else ""),
                                flush=True,
                            )
                            heredoc_sections = list(current_sections)
                            heredoc_sections.append(
                                {
                                    "label": "hybrid_transport_assignment_heredoc",
                                    "content": (
                                        "HYBRID TRANSPORT ASSIGNMENT (HEREDOC ONLY):\n"
                                        + "Return fenced blocks only for these files:\n"
                                        + "\n".join(f"- {path}" for path in heredoc_targets_for_attempt)
                                        + "\nUse EXACT format for each file:\n"
                                        + "```language:qodeyard/<path>\n<full file content>\n```\n"
                                        + "Do not modify any other file in this turn.\n"
                                        + "Output only file blocks."
                                    ),
                                    "required": True,
                                    "loss_policy": "preserve",
                                    "section_type": "hybrid_transport_assignment",
                                }
                            )
                            heartbeat.set_message("Heredoc generating (AI)")
                            ai_result, heredoc_stream_fallback = _run_ai_completion_with_streaming_policy(
                                ai_provider=ai_provider,
                                ai_model=ai_model,
                                prompt=current_prompt,
                                context_files=attempt_context_files,
                                prompt_sections=heredoc_sections,
                                agent_name="construqtor",
                                task_type="code_generation",
                                output_tokens=briq_output_tokens,
                                streaming_policy=streaming_policy,
                                stream_label="hybrid-heredoc",
                            )
                            attempt_metrics["ai_call_count"] += 1
                            if heredoc_stream_fallback:
                                attempt_metrics["stream_fallback_count"] += 1
                            heredoc_extracted = _extract_ai_output_files(str(ai_result), qodeyard_path)
                            heredoc_filtered, dropped = _filter_extracted_files_to_allowlist(
                                heredoc_extracted,
                                set(heredoc_targets_for_attempt),
                            )
                            if dropped:
                                print(
                                    "     [Hybrid] Dropped out-of-scope heredoc files: "
                                    + ", ".join(sorted(dropped)),
                                    flush=True,
                                )
                            extracted_files.update(heredoc_filtered)
                else:
                    # Legacy heredoc mode
                    heartbeat.set_message("Heredoc generating (AI)")
                    ai_result, heredoc_stream_fallback = _run_ai_completion_with_streaming_policy(
                        ai_provider=ai_provider,
                        ai_model=ai_model,
                        prompt=current_prompt,
                        context_files=attempt_context_files,
                        prompt_sections=current_sections,
                        agent_name="construqtor",
                        task_type="code_generation",
                        output_tokens=briq_output_tokens,
                        streaming_policy=streaming_policy,
                        stream_label="heredoc",
                    )
                    attempt_metrics["ai_call_count"] += 1
                    if heredoc_stream_fallback:
                        attempt_metrics["stream_fallback_count"] += 1
                    
                    if not ai_result or "```" not in ai_result:
                        result['error'] = "AI returned no code blocks"
                        continue
                    
                    extracted_files = _extract_ai_output_files(str(ai_result), qodeyard_path)
                    heredoc_allowlist = sorted(set(primary_deliverables or []) | set(briq_targets or []))
                    heredoc_allowlist = [
                        path for path in heredoc_allowlist if str(path).strip() and not is_infra_path(path)
                    ]
                    if heredoc_allowlist:
                        extracted_files, dropped = _filter_extracted_files_to_allowlist(
                            extracted_files,
                            set(heredoc_allowlist),
                        )
                        if dropped:
                            print(
                                "     [Heredoc] Dropped out-of-scope files: "
                                + ", ".join(sorted(dropped)),
                                flush=True,
                            )
            finally:
                if previous_log_env is None:
                    os.environ.pop("QONQ_INCLUDE_PREVIOUS_LOG", None)
                else:
                    os.environ["QONQ_INCLUDE_PREVIOUS_LOG"] = previous_log_env

            if not extracted_files and coding_mode != 'direct':
                 print(f"     [WARN] No files extracted from AI response (attempt {attempt})", flush=True)

            # v1.3.13: Stagnation check to avoid infinite retry loops on identical content
            # (which would just fail validation the same way again).
            current_attempt_fingerprint = hashlib.sha256(json.dumps(extracted_files, sort_keys=True).encode('utf-8')).hexdigest()
            if attempt > 1 and current_attempt_fingerprint == last_briq_attempt_fingerprint:
                print(f"     [Tool] 🛑 Stagnation detected: AI produced identical code in attempt {attempt}. Breaking retry loop.", flush=True)
                result['error'] = f"Stagnation: Identical code produced in attempt {attempt}"
                break
            last_briq_attempt_fingerprint = current_attempt_fingerprint

            # Unified staging from extracted_files map
            staged_attempt = _stage_extracted_files(
                extracted_files,
                qodeyard_path,
                worqspace_root,
                attempt_id,
                briq_metadata,
                validation_root=validation_root,
                coding_mode=coding_mode,
                requested_coding_mode=result.get('coding_mode', coding_mode),
                transport_decisions=hybrid_transport_decisions if coding_mode == 'hybrid' else [],
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
                "direct_loop_meta": direct_loop_meta if coding_mode in {'direct', 'hybrid'} else {},
                "validation_gate_scope": (
                    (direct_loop_meta or {}).get("validation_gate_scope")
                    if coding_mode in {'direct', 'hybrid'}
                    else "build_group"
                ),
                "transport_decisions": hybrid_transport_decisions if coding_mode == 'hybrid' else [],
                "hybrid_fallback_events": hybrid_fallback_events if coding_mode == 'hybrid' else [],
                "repair_level": active_repair_level,
                "failure_class": active_failure_class,
                "escalation_reason": active_escalation_reason,
                "failure_fingerprint": None,
                "metrics": dict(attempt_metrics),
            })
            update_attempt_manifest_context(
                staged_attempt,
                {
                    "briq_name": briq_name,
                    "repair_level": active_repair_level,
                    "failure_class": active_failure_class,
                    "escalation_reason": active_escalation_reason,
                    "repair_escalation_enabled": bool(repair_escalation_cfg.get("enabled", True)),
                    "transport_decisions": hybrid_transport_decisions if coding_mode == 'hybrid' else [],
                    "hybrid_fallback_events": hybrid_fallback_events if coding_mode == 'hybrid' else [],
                    "metrics": dict(attempt_metrics),
                },
            )
            if coding_mode == 'hybrid':
                for rel_path in staged_attempt.get('staged_files', []):
                    if str(rel_path).strip():
                        hybrid_missing_required_counts[str(rel_path).strip()] = 0

            if not staged_attempt['staged_files']:
                # v1.3.12: If direct mode yielded no files, it might be a legitimate no-op success
                # if the target files already exist in qodeyard.
                legit_no_op = False
                missing_primary_outputs = _missing_required_outputs(
                    primary_deliverables,
                    staged_files=staged_attempt['staged_files'],
                    qodeyard_path=qodeyard_path,
                )
                if coding_mode in {'direct', 'hybrid'} and (briq_targets or primary_deliverables):
                    parse_failures = int(direct_loop_meta.get("parse_failures", 0))
                    apply_errors = int(direct_loop_meta.get("apply_errors", 0))
                    no_tool_errors = (parse_failures == 0 and apply_errors == 0)
                    # Check if all target files already exist in qodeyard
                    noop_targets = sorted(set(primary_deliverables or []) | set(briq_targets or []))
                    all_exist = True
                    for target in noop_targets:
                        target_path = qodeyard_path / target
                        if not target_path.exists():
                            all_exist = False
                            break
                    if all_exist and no_tool_errors and not missing_primary_outputs:
                        no_op_state = _evaluate_repair_scope_state(
                            worqspace_root,
                            qodeyard_path,
                            repair_targets=noop_targets,
                            validation_scope_files=validation_scope_files or noop_targets,
                            is_contract_relevant=is_contract_relevant,
                            contract_data=contract_data,
                            build_group=briq_metadata.get('build-group') or briq_metadata.get('build_group'),
                            repair_plan_payload=repair_plan_payload,
                        )
                        result['validation'] = no_op_state.get('qualification', {})
                        result['qonfirmer_report'] = no_op_state.get('qonfirmer_report')
                        if no_op_state.get('passed'):
                            legit_no_op = True
                        else:
                            legit_no_op = False
                            attempt_failure_status = "failed_validation"
                            result['error'] = "No-op not allowed: existing target files fail scoped validation; open deterministic/group issues remain in the repair scope."
                            if no_op_state.get('open_fingerprints'):
                                result['error'] += " " + _render_open_fingerprint_summaries(no_op_state.get('open_fingerprints', []))
                            if attempt < max_attempts:
                                retry_correction = (
                                    "NO-OP TARGETS FAIL ISSUE-AWARE VALIDATION:\n"
                                    + build_validation_correction_directive(no_op_state.get('qualification', {}))
                                    + "\nResolve the remaining deterministic/group validation failures in this repair scope."
                                )
                    elif all_exist and missing_primary_outputs:
                        result['error'] = (
                            "No-op not allowed: required primary deliverables are missing: "
                            + ", ".join(missing_primary_outputs)
                        )
                        attempt_failure_status = "failed_missing_required"
                        if attempt < max_attempts:
                            retry_correction = (
                                "PRIMARY DELIVERABLES MISSING:\n"
                                + "\n".join(f"- {item}" for item in missing_primary_outputs)
                                + "\nCreate these files with full intended content. Do not return a no-op."
                            )
                    elif all_exist and not no_tool_errors:
                        result['error'] = (
                            "No files were written due to tool-call failures "
                            f"(parse_failures={parse_failures}, apply_errors={apply_errors})"
                        )
                        
                if legit_no_op:
                    print(f"     [Tool] No new files written, but target files already exist. Treating as no-op success.", flush=True)
                    attempt_metrics["attempt_duration_sec"] = time.time() - attempt_start_time
                    result['attempt_records'][-1]['metrics'] = dict(attempt_metrics)
                    update_attempt_manifest_context(
                        staged_attempt,
                        {"metrics": dict(attempt_metrics)},
                    )
                    finalize_attempt_manifest(
                        staged_attempt,
                        status="committed", # It's a no-op commit
                        committed_files=[],
                    )
                    result['attempt_records'][-1]['status'] = 'committed'
                    result['status'] = 'success'
                    break
                else:
                    if not result.get('error'):
                        result['error'] = "No files were written"
                    if missing_primary_outputs:
                        if coding_mode == 'hybrid':
                            for rel_path in missing_primary_outputs:
                                rel = str(rel_path).strip()
                                if rel:
                                    hybrid_missing_required_counts[rel] = int(
                                        hybrid_missing_required_counts.get(rel, 0) or 0
                                    ) + 1
                        result['error'] = (
                            "No files were written and required primary deliverables are missing: "
                            + ", ".join(missing_primary_outputs)
                        )
                        attempt_failure_status = "failed_missing_required"
                        if attempt < max_attempts:
                            retry_correction = (
                                "PRIMARY DELIVERABLES MISSING:\n"
                                + "\n".join(f"- {item}" for item in missing_primary_outputs)
                                + "\nCreate these files with full intended content."
                            )
                    if attempt < max_attempts:
                        retry_correction, pending_repair_level, pending_failure_class, pending_escalation_reason, attempt_failure_fingerprint = _plan_retry_after_failure(
                            attempt_number=attempt,
                            failure_status=attempt_failure_status if attempt_failure_status != "failed_validation" else "failed_empty",
                            error_message=result.get('error', ''),
                            direct_meta=direct_loop_meta,
                            validation_payload=result.get('validation', {}),
                            qonfirmer_payload=result.get('qonfirmer_report'),
                            missing_primary=missing_primary_outputs,
                            target_files=primary_deliverables or briq_targets,
                            violation_rows=[],
                        )
                    current_failure_class, current_failure_reason = classify_attempt_failure(
                        failure_status=attempt_failure_status if attempt_failure_status != "failed_validation" else "failed_empty",
                        error_message=result.get('error', ''),
                        direct_loop_meta=direct_loop_meta,
                        validation=result.get('validation', {}),
                        qonfirmer_report=result.get('qonfirmer_report') or {},
                        missing_primary_outputs=missing_primary_outputs,
                    )
                    result['attempt_records'][-1]['failure_class'] = current_failure_class
                    result['attempt_records'][-1]['failure_fingerprint'] = attempt_failure_fingerprint or None
                    attempt_metrics["attempt_duration_sec"] = time.time() - attempt_start_time
                    result['attempt_records'][-1]['metrics'] = dict(attempt_metrics)
                    update_attempt_manifest_context(
                        staged_attempt,
                        {
                            "failure_class": current_failure_class,
                            "failure_reason": result.get('error', ''),
                            "failure_fingerprint": attempt_failure_fingerprint or None,
                            "metrics": dict(attempt_metrics),
                        },
                    )
                    completed_failure_records.append(
                        {
                            "failure_class": current_failure_class,
                            "failure_fingerprint": attempt_failure_fingerprint or "",
                        }
                    )
                    finalize_attempt_manifest(
                        staged_attempt,
                        status=attempt_failure_status if attempt_failure_status != "failed_validation" else "failed_empty",
                        failure_reason=result['error'],
                    )
                    result['attempt_records'][-1]['status'] = (
                        attempt_failure_status if attempt_failure_status != "failed_validation" else 'failed_empty'
                    )
                    continue

            print(f"Building group {briq_metadata.get('build-group', 'ungrouped')}", flush=True)
            
            # STEP 2: Qualification
            build_passed = True
            missing_primary_outputs = _missing_required_outputs(
                primary_deliverables,
                staged_files=staged_attempt['staged_files'],
                qodeyard_path=qodeyard_path,
            )
            if missing_primary_outputs:
                if coding_mode == 'hybrid':
                    for rel_path in missing_primary_outputs:
                        rel = str(rel_path).strip()
                        if rel:
                            hybrid_missing_required_counts[rel] = int(
                                hybrid_missing_required_counts.get(rel, 0) or 0
                            ) + 1
                result['error'] = (
                    "Primary deliverables missing after staging: "
                    + ", ".join(missing_primary_outputs)
                )
                build_passed = False
                attempt_failure_status = "failed_missing_required"
                print(f"     [Gate] ❌ Missing primary deliverables: {', '.join(missing_primary_outputs)}", flush=True)
                if attempt < max_attempts:
                    retry_correction = (
                        "PRIMARY DELIVERABLES MISSING:\n"
                        + "\n".join(f"- {item}" for item in missing_primary_outputs)
                        + "\nWrite these files in this attempt. Do not skip them."
                    )
            
            if do_local_validation and build_passed:
                print(f"     [Qualifier] Running validation...", flush=True)
                v_start = time.time()
                # v2.x: scoped reuse of the real qualifier package
                # (covers py/sh/js/ts/html/css honestly), with the
                # run.sh constraint layer stacked on top. The older
                # narrow `run_local_validation` is kept on the shelf
                # for compat / fallback inside run_scoped_qualification.
                cycle_label_for_validation = os.environ.get(
                    'CYCLE_NUM', 'interleaved'
                )
                validation = run_scoped_qualification(
                    staged_attempt['staged_files'],
                    staged_attempt['validation_root'],
                    worqspace_root,
                    f"interleaved-{cycle_label_for_validation}-"
                    f"{staged_attempt['attempt_id']}",
                )
                attempt_metrics["validation_duration_sec"] += (time.time() - v_start)
                result['validation'] = validation
                result['attempt_records'][-1]['validated_files'] = list(staged_attempt['staged_files'])
                result['attempt_records'][-1]['validation_gate_scope'] = 'build_group'

                if validation['syntax_errors'] or validation['constraint_errors']:
                    autofix = _apply_trivial_autofix(
                        staged_attempt['staged_files'],
                        [staged_attempt['validation_root'], staged_attempt['staging_dir']],
                    )
                    if autofix.get('applied'):
                        cats = ", ".join(autofix.get('categories', [])) or "trivial fixes"
                        print(f"     [Qualifier] 🔧 Applied deterministic autofix ({cats})", flush=True)
                        v_start_autofix = time.time()
                        validation = run_scoped_qualification(
                            staged_attempt['staged_files'],
                            staged_attempt['validation_root'],
                            worqspace_root,
                            f"interleaved-{cycle_label_for_validation}-"
                            f"{staged_attempt['attempt_id']}-autofix",
                        )
                        attempt_metrics["validation_duration_sec"] += (time.time() - v_start_autofix)
                        result['validation'] = validation
                        if validation['passed']:
                            print(f"     [Qualifier] ✅ Passed after deterministic autofix", flush=True)
                
                    if validation['syntax_errors']:
                        print(f"     [Qualifier] ❌ Syntax errors found:", flush=True)
                        for err in validation['syntax_errors'][:5]:
                            print(f"     [Qualifier]    - {err}", flush=True)
                        result['error'] = f"{len(validation['syntax_errors'])} syntax errors"
                        build_passed = False
                        if attempt < max_attempts:
                            retry_correction = build_validation_correction_directive(validation)
                    elif validation['constraint_errors']:
                        print(f"     [Qualifier] ❌ Constraint errors found:", flush=True)
                        for err in validation['constraint_errors'][:5]:
                            print(f"     [Qualifier]    - {err}", flush=True)
                        if active_component_constraints:
                            print(f"     [Qualifier] Relevant constraints:", flush=True)
                            for item in active_component_constraints[:6]:
                                print(f"     [Qualifier]    • {item}", flush=True)
                        result['error'] = f"{len(validation['constraint_errors'])} constraint errors"
                        build_passed = False
                        if attempt < max_attempts:
                            retry_correction = build_validation_correction_directive(validation)
                elif validation['import_warnings']:
                    print(f"     [Qualifier] ⚠️ Import warnings: {len(validation['import_warnings'])}", flush=True)
                else:
                    print(f"     [Qualifier] ✅ Passed", flush=True)
            
            # STEP 2.5 (v1.3.0): Per-Briq Qonfirmer Gate
            if is_contract_relevant and build_passed:
                if not qonfirmer:
                    result['error'] = "Qonfirmer module unavailable but contract enforcement required."
                    build_passed = False
                    print(f"     [Qonfirmer] ❌ FAIL — {result['error']}", flush=True)
                elif not contract_data:
                    result['error'] = "QONTRACT artifact missing but contract enforcement required."
                    build_passed = False
                    print(f"     [Qonfirmer] ❌ FAIL — {result['error']}", flush=True)
                else:
                    print(f"     [Qonfirmer] Running (contract-relevant briq)...", flush=True)
                    q_start = time.time()
                    briq_qonfirmer_result = qonfirmer.run_qonfirmer_for_files(
                        contract_data, staged_attempt['validation_root'], staged_attempt['staged_files']
                    )
                    attempt_metrics["qonfirmer_duration_sec"] = time.time() - q_start
                    result['qonfirmer_report'] = briq_qonfirmer_result.to_json()
                    
                    if not briq_qonfirmer_result.passed:
                        error_count = len([v for v in briq_qonfirmer_result.violations if v.severity == 'error'])
                        warning_count = len([v for v in briq_qonfirmer_result.violations if v.severity != 'error'])
                        print(f"     [Qonfirmer] ❌ FAIL — {error_count} contract violations", flush=True)
                        for v in briq_qonfirmer_result.violations[:8]:
                            loc = f" (line {v.line_number})" if v.line_number else ""
                            sev = (v.severity or 'error').upper()
                            print(f"     [Qonfirmer]    - [{sev}] [{v.rule}] {v.file_path}{loc}: {v.message}", flush=True)
                        if len(briq_qonfirmer_result.violations) > 8:
                            remaining = len(briq_qonfirmer_result.violations) - 8
                            print(f"     [Qonfirmer]    - ... and {remaining} more violation(s)", flush=True)

                        relevant_contract_lines = []
                        if contract_data:
                            invariants = contract_data.get('invariants', {})
                            violated_rules = {v.rule for v in briq_qonfirmer_result.violations}
                            if 'forbidden_import' in violated_rules and invariants.get('forbidden_imports'):
                                imports = ', '.join(invariants['forbidden_imports'])
                                relevant_contract_lines.append(f"Forbidden imports: {imports}")
                            if any(rule.startswith('schema') for rule in violated_rules) and invariants.get('schemas'):
                                for model_name, spec in invariants['schemas'].items():
                                    fields = ', '.join(f"`{field}`" for field in spec.get('fields', {}))
                                    exact = ' (EXACT)' if spec.get('exact') else ''
                                    relevant_contract_lines.append(f"Schema {model_name}{exact}: {fields}")
                            if any(rule.startswith('required_file') for rule in violated_rules) and invariants.get('required_files'):
                                relevant_contract_lines.append(
                                    "Required files: " + ', '.join(invariants['required_files'])
                                )
                            if any(rule.startswith('fastapi_') for rule in violated_rules) and invariants.get('fastapi'):
                                relevant_contract_lines.append(
                                    "FastAPI constraints active in qontract invariants."
                                )
                        if relevant_contract_lines:
                            print(f"     [Qonfirmer] Relevant contract constraints:", flush=True)
                            for item in relevant_contract_lines[:8]:
                                print(f"     [Qonfirmer]    • {item}", flush=True)
                            if len(relevant_contract_lines) > 8:
                                remaining = len(relevant_contract_lines) - 8
                                print(f"     [Qonfirmer]    • ... and {remaining} more relevant constraint(s)", flush=True)
                        elif warning_count:
                            print(f"     [Qonfirmer]    - {warning_count} warning(s) also present in contract report", flush=True)

                        if attempt < max_attempts:
                            attempt_violation_rows = [
                                f"[{v.rule}] {v.file_path}{':' + str(v.line_number) if getattr(v, 'line_number', None) else ''}: {v.message}"
                                for v in (briq_qonfirmer_result.violations or [])[:25]
                            ]
                            # Build correction directive for retry
                            retry_correction = _build_qonfirmer_targeted_retry_directive(
                                briq_qonfirmer_result,
                                contract_data,
                                staged_attempt['staged_files'],
                            )
                            result['error'] = f"Qonfirmer: {error_count} contract violations"
                            build_passed = False
                        else:
                            # Max retries exhausted — mark as failure
                            result['error'] = f"Qonfirmer: {error_count} violations (retries exhausted)"
                            build_passed = False
                    else:
                        print(f"     [Qonfirmer] ✅ Passed", flush=True)
            
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

            if build_passed:
                suspicious_primary_outputs = _evaluate_primary_deliverable_sizes(
                    staged_attempt,
                    qodeyard_path,
                    primary_deliverables,
                    policy_cfg=hybrid_policy_cfg if coding_mode == 'hybrid' else None,
                )
                if suspicious_primary_outputs:
                    attempt_failure_status = "failed_trivial"
                    build_passed = False
                    result['error'] = (
                        "Primary deliverable content appears trivially small: "
                        + "; ".join(suspicious_primary_outputs)
                    )
                    print(
                        "     [Gate] ❌ Rejected suspiciously tiny primary deliverable(s): "
                        + "; ".join(suspicious_primary_outputs),
                        flush=True,
                    )
                    if attempt < max_attempts:
                        retry_correction = (
                            "PRIMARY DELIVERABLE CONTENT TOO SMALL:\n"
                            + "\n".join(f"- {item}" for item in suspicious_primary_outputs)
                            + "\nRegenerate these files with full intended implementation. "
                            + "Do not emit placeholder or near-empty files."
                        )
            
            # STEP 4: Determine result
            if build_passed:
                attempt_metrics["attempt_duration_sec"] = time.time() - attempt_start_time
                committed_files = commit_staged_attempt(staged_attempt, qodeyard_path, worqspace_root, attempt=attempt)
                committed_written_files.update(item['path'] for item in committed_files)
                result['written_files'] = sorted(committed_written_files)
                result['attempt_records'][-1]['status'] = 'committed'
                result['attempt_records'][-1]['committed_files'] = [item['path'] for item in committed_files]
                result['attempt_records'][-1]['metrics'] = dict(attempt_metrics)
                update_attempt_manifest_context(
                    staged_attempt,
                    {"metrics": dict(attempt_metrics)},
                )
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
                if attempt < max_attempts:
                    retry_correction, pending_repair_level, pending_failure_class, pending_escalation_reason, attempt_failure_fingerprint = _plan_retry_after_failure(
                        attempt_number=attempt,
                        failure_status=attempt_failure_status,
                        error_message=result.get('error', ''),
                        direct_meta=direct_loop_meta,
                        validation_payload=result.get('validation', {}),
                        qonfirmer_payload=result.get('qonfirmer_report'),
                        missing_primary=missing_primary_outputs,
                        target_files=primary_deliverables or briq_targets,
                        violation_rows=attempt_violation_rows,
                    )
                current_failure_class, current_failure_reason = classify_attempt_failure(
                    failure_status=attempt_failure_status,
                    error_message=result.get('error', ''),
                    direct_loop_meta=direct_loop_meta,
                    validation=result.get('validation', {}),
                    qonfirmer_report=result.get('qonfirmer_report') or {},
                    missing_primary_outputs=missing_primary_outputs,
                )
                result['attempt_records'][-1]['failure_class'] = current_failure_class
                result['attempt_records'][-1]['failure_fingerprint'] = attempt_failure_fingerprint or None
                result['attempt_records'][-1]['escalation_reason'] = current_failure_reason or active_escalation_reason
                attempt_metrics["attempt_duration_sec"] = time.time() - attempt_start_time
                result['attempt_records'][-1]['metrics'] = dict(attempt_metrics)
                update_attempt_manifest_context(
                    staged_attempt,
                    {
                        "failure_class": current_failure_class,
                        "failure_reason": result.get('error', ''),
                        "failure_fingerprint": attempt_failure_fingerprint or None,
                        "repair_level": active_repair_level,
                        "metrics": dict(attempt_metrics),
                    },
                )
                completed_failure_records.append(
                    {
                        "failure_class": current_failure_class,
                        "failure_fingerprint": attempt_failure_fingerprint or "",
                    }
                )
                finalize_attempt_manifest(
                    staged_attempt,
                    status=attempt_failure_status,
                    failure_reason=result.get('error'),
                )
                result['attempt_records'][-1]['status'] = attempt_failure_status
                # Try again if we have attempts left
                if attempt >= max_attempts:
                    result['status'] = 'failure'
                    
        except Exception as e:
            result['error'] = str(e)
            print(f"     [ERROR] Attempt {attempt} failed: {e}", flush=True)
            attempt_metrics["attempt_duration_sec"] = time.time() - attempt_start_time
            if result.get('attempt_records'):
                result['attempt_records'][-1]['status'] = 'failed_exception'
                result['attempt_records'][-1]['metrics'] = dict(attempt_metrics)

    result["ai_call_count_total"] = sum(
        int((attempt.get("metrics") or {}).get("ai_call_count", 0) or 0)
        for attempt in result.get("attempt_records", [])
    )
    result["tool_iteration_count_total"] = sum(
        int((attempt.get("metrics") or {}).get("tool_iteration_count", 0) or 0)
        for attempt in result.get("attempt_records", [])
    )
    result["retry_sleep_duration_total_sec"] = sum(
        float((attempt.get("metrics") or {}).get("retry_sleep_duration_sec", 0.0) or 0.0)
        for attempt in result.get("attempt_records", [])
    )

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
    
    result['repair_escalation'] = {
        "prior_attempt_records": completed_failure_records,
        "recommended_start_level": pending_repair_level,
        "recommended_failure_class": pending_failure_class,
        "reason": pending_escalation_reason,
    }
    return result


def generate_briq_exeq(briq_name: str, briq_content: str, result: dict) -> str:
    """Generate a per-briq exeQ summary markdown file."""
    status_emoji = "✅" if result['status'] == 'success' else ("⚠️" if result['status'] == 'partial' else "❌")
    
    exeq = f"""# Briq ExeQ: {briq_name}
Generated by ConstruQtor v{RUNTIME_VERSION} (Interleaved Pipeline)

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
            metrics = attempt.get("metrics") or {}
            exeq += (
                f"- `{attempt['attempt_id']}`: {attempt['status']} | "
                f"staged={len(attempt.get('staged_files', []))} | "
                f"committed={len(attempt.get('committed_files', []))} | "
                f"ai_calls={int(metrics.get('ai_call_count', 0) or 0)} | "
                f"tool_iters={int(metrics.get('tool_iteration_count', 0) or 0)} | "
                f"validation={float(metrics.get('validation_duration_sec', 0.0) or 0.0):.2f}s | "
                f"retry_sleep={float(metrics.get('retry_sleep_duration_sec', 0.0) or 0.0):.2f}s\n"
            )
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
    
    # v1.3.0: Qonfirmer results
    qonfirmer_report = result.get('qonfirmer_report')
    if qonfirmer_report:
        qonfirmer_status = qonfirmer_report.get('status', 'N/A')
        qonfirmer_emoji = "✅" if qonfirmer_status == 'PASS' else "❌"
        exeq += f"## 🛡️ qonfirmer: {qonfirmer_emoji} {qonfirmer_status}\n\n"
        violations = qonfirmer_report.get('violations', [])
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

    # v1.3.10: Fail loud if cwd has drifted inside qodeyard/. Otherwise
    # worqspace_root would resolve to qodeyard/<sub>/ and we'd write
    # build/, attempts/, validation-root/ INSIDE qodeyard, polluting the
    # code tree. See worqer/path_hygiene.py for full rationale.
    assert_cwd_outside_qodeyard("construqtor")

    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"

    # Load configuration
    config = load_config(worqspace_root / 'config.yaml')
    retry_config = get_retry_config(config)
    interleaved_config = get_interleaved_config(config)
    repair_escalation_config = get_repair_escalation_config(config)
    write_strategy_config = get_write_strategy_config(config)
    
    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider, ai_model = lib_ai.get_agent_ai_params(config, 'construqtor', 'venice', 'deepseek-v3.2')
    use_qompressor = config.get('options', {}).get('use_qompressor', True)
    
    is_repair_pass = os.environ.get("QONQ_REPAIR_MODE") == "1"
    if is_repair_pass:
        repair_plan_path = os.environ.get("QONQ_REPAIR_PLAN_PATH")
        if repair_plan_path:
            rp_payload = load_optional_json(Path(repair_plan_path))
            repair_level = rp_payload.get("recommended_start_level", 4)
            if repair_level <= 1:
                print("    [Surgical] Level 1 repair pass: disabling Qompressor and Qontextor to reduce churn.", flush=True)
                use_qompressor = False
                config.get('options', {})['use_qontextor'] = False
    
    # InspeQtor config for reviews
    review_provider, review_model = lib_ai.get_agent_ai_params(config, 'inspeqtor', ai_provider, ai_model)
    execution_backend = detect_execution_backend(ai_provider, ai_model)
    print(f"[AI] construqtor provider={ai_provider} model={ai_model}", flush=True)
    print(f"[AI] review provider={review_provider} model={review_model}", flush=True)

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
    # v1.3.0: QONTRACT.D + FIRST-BUILD-PASS TASQ + QONTEXT.D CONTEXT WIRING
    # ═══════════════════════════════════════════════════════════════════════════
    qontract_path = worqspace_root / "qontract.d"
    qontext_path = worqspace_root / "qontext.d"
    tasq_dir = worqspace_root / "tasq.d"

    # B) Fail-fast: contract must exist after the first build pass
    cycle_num_val = os.environ.get('CYCLE_NUM', '1')
    build_pass_index = os.environ.get('QONQ_BUILD_PASS_INDEX', cycle_num_val)
    pass_kind = os.environ.get('QONQ_PASS_KIND', 'build')
    if not (pass_kind == 'build' and build_pass_index == '1'):
        try:
            from lib_loqal import ensure_qontract_present
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

    # Load first-build-pass tasq (always included as big-picture anchor)
    cycle1_tasq_content = ""
    cycle1_tasq_path = tasq_dir / "cyqle1_tasq.md"
    if cycle1_tasq_path.exists():
        try:
            with open(cycle1_tasq_path, 'r', encoding='utf-8') as f:
                cycle1_tasq_content = f.read()
            print(f"    First Build-Pass Tasq: Loaded ({len(cycle1_tasq_content)} chars)", flush=True)
        except Exception as e:
            print(f"    First Build-Pass Tasq: ⚠️ Could not load: {e}", flush=True)
    else:
        print(f"    First Build-Pass Tasq: Not found (first build pass in progress)", flush=True)

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
    # v1.3.0: CONTEXT LOGGING
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
    completion_criteria_payload = load_optional_json(worqspace_root / "planning" / "completion-criteria.v1.json")
    component_contracts_payload = load_optional_json(worqspace_root / "planning" / "component-contracts.v1.json")

    # Processing stats
    all_results = []
    all_written_files = []
    success_count = 0
    partial_count = 0
    failure_count = 0
    
    stop_on_fail = retry_config['stop_on_briq_fail']
    stopped_early = False

    print(f"Processing {len(briq_files)} Briqs (Interleaved)", flush=True)
    print(f"    Retry: {'enabled' if retry_config['enabled'] else 'disabled'} | Max attempts: {retry_config['max_attempts']}", flush=True)
    print(f"    Interleaved: {'enabled' if interleaved_config['enabled'] else 'disabled'} | Local validation: {interleaved_config['local_validation']} | AI review: {interleaved_config['ai_quick_review']}", flush=True)
    print(
        "    Repair Escalation: "
        f"{'enabled' if repair_escalation_config.get('enabled', True) else 'disabled'} "
        f"(max_level={repair_escalation_config.get('max_level', 4)}, "
        f"start={repair_escalation_config.get('start_policy')}, "
        f"bump={repair_escalation_config.get('bump_policy')})",
        flush=True,
    )

    constitutional_sections = {
        "qontract": qontract_content,
        "cycle1_tasq": cycle1_tasq_content,
        "structure_tree": struqture_tree,
    }

    # v1.3.13: Six-Shooter Qontract support
    six_shooter_manifest = load_optional_json(qontract_path / "six-shooter-manifest.v1.json")
    if six_shooter_manifest:
        selected_docs = six_shooter_manifest.get("selected_docs", [])
        six_shooter_docs = {}
        for doc_name in selected_docs:
            doc_path = qontract_path / doc_name
            if doc_path.exists():
                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        six_shooter_docs[doc_name] = f.read()
                except:
                    pass
        if six_shooter_docs:
            constitutional_sections["six_shooter_docs"] = six_shooter_docs
            constitutional_sections["six_shooter_manifest"] = six_shooter_manifest
            print(f"    🔫 [SIX-SHOOTER] Loaded {len(six_shooter_docs)} Qontract docs", flush=True)

    # v1.3.0: Load contract data for per-briq Qonfirmer gate
    qontract_json_path = qontract_path / "qontract.json"
    contract_data = None
    if qontract_json_path.exists():
        try:
            if qonfirmer:
                contract_data = qonfirmer.load_contract(qontract_json_path)
            else:
                with open(qontract_json_path, 'r', encoding='utf-8') as f:
                    contract_data = json.load(f)
            if contract_data:
                print(f"    qonfirmer: Loaded contract for per-briq gating", flush=True)
        except Exception as e:
            print(f"    Qonfirmer: ⚠️ Could not load contract: {e}", flush=True)

    # v1.3.13: Total briq count so users see "N of M" progress instead of
    # a blind per-briq print with no denominator. Helps when individual briqs
    # are long-running even with streaming enabled.
    total_briqs = len(briq_files)
    
    is_repair_pass = os.environ.get("QONQ_REPAIR_MODE") == "1"
    repair_plan_required_files = []
    repair_plan_payload_runner = {}
    if is_repair_pass:
        repair_plan_path = os.environ.get("QONQ_REPAIR_PLAN_PATH")
        if repair_plan_path:
            repair_plan_payload_runner = load_optional_json(Path(repair_plan_path))
            repair_plan_required_files = repair_plan_payload_runner.get("target_files") or repair_plan_payload_runner.get("repair_escalation", {}).get("target_files", []) or []

    early_stopped_repair = False

    for briq_idx, briq_file in enumerate(briq_files, start=1):
        if is_repair_pass and repair_plan_required_files:
            early_state = _evaluate_repair_scope_state(
                worqspace_root,
                qodeyard_path,
                repair_targets=repair_plan_required_files,
                validation_scope_files=repair_plan_payload_runner.get("validation_scope_files") or repair_plan_required_files,
                is_contract_relevant=False,
                contract_data=contract_data,
                build_group=None,
                repair_plan_payload=repair_plan_payload_runner,
            )
            if early_state.get("passed"):
                print("      [Early Stop] Target issue fingerprints cleared. Short-circuiting remaining briqs.", flush=True)
                early_stopped_repair = True
                break

        briq_metadata = parse_briq_metadata(briq_file.read_text(encoding='utf-8'))
        build_group_id = briq_metadata.get('build-group', 'ungrouped')
        component_id = briq_metadata.get('component-id', 'unassigned')
        scope_id = briq_metadata.get('scope-id', 'scope_unknown')
        print(f"Building group {build_group_id}", flush=True)
        print(f"\n-- Processing briQ [{briq_idx}/{total_briqs}]: {briq_file.name} --", flush=True)
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
            completion_criteria_payload=completion_criteria_payload,
            component_contracts_payload=component_contracts_payload,
            write_strategy_config=write_strategy_config,
            execution_backend=execution_backend,
            repo_config=config,
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

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW v1.4: HARNESS EXECUTION & HYGIENE
    # ═══════════════════════════════════════════════════════════════════════════
    import shutil
    import contract_harness
    harness = contract_harness.load_harness(worqspace_root)
    if harness:
        print("  📜 [HARNESS] Running acceptance harness...", flush=True)
        harness_result = contract_harness.run_harness(qodeyard_path, harness, apply_fixes=False)
        qontract_dir = worqspace_root / 'qontract.d'
        with open(qontract_dir / 'harness-result.v1.json', 'w') as f:
            import json as json_mod
            json_mod.dump(harness_result, f, indent=2)
        with open(qontract_dir / 'harness-result.md', 'w') as f:
            f.write(contract_harness.render_result_markdown(harness_result))
        if not harness_result.get("passed"):
            print("  ❌ [HARNESS] Failed. Directives available for repair plan.", flush=True)
            # If harness fails, force failure state to trigger repair unless we are halting
            if failure_count == 0 and partial_count == 0:
                failure_count += 1
                all_results.append({
                    'briq_file': 'harness_validation',
                    'status': 'failure',
                    'written_files': [],
                    'attempts': 1,
                    'error': 'Harness failed',
                    'exeq_path': None
                })
        else:
            print("  ✅ [HARNESS] Passed.", flush=True)

        print("  🧹 [HYGIENE] Cleaning up runtime noise...", flush=True)
        for p in [".pytest_cache", ".ruff_cache", "__pycache__"]:
            target_dir = qodeyard_path / p
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
        for f in [".DS_Store", ".qonqrete_fastapi_probe.py", ".test_behavior.py"]:
            target_file = qodeyard_path / f
            if target_file.exists():
                target_file.unlink(missing_ok=True)

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
            'metrics_totals': {
                'ai_call_count': 0,
                'tool_iteration_count': 0,
                'validation_duration_sec': 0.0,
                'retry_sleep_duration_sec': 0.0,
                'attempt_duration_sec': 0.0,
                'stream_fallback_count': 0,
            },
            'per_briq_ai_call_count': {},
        })
        group_entry['component_ids'].add(component_id)
        group_entry['briq_files'].append(result['briq_file'])
        group_entry['written_files'].update(result['written_files'])
        group_entry['statuses'].append(result['status'])
        group_entry['per_briq_ai_call_count'][result['briq_file']] = int(result.get('ai_call_count_total', 0) or 0)
        for attempt_record in result.get('attempt_records', []):
            group_entry['attempt_records'].append(attempt_record)
            group_entry['attempt_ids'].append(attempt_record['attempt_id'])
            group_entry['attempt_manifests'].append(attempt_record['manifest_ref'])
            group_entry['recovery_refs'].append(attempt_record['recovery_ref'])
            metrics = attempt_record.get('metrics') or {}
            totals = group_entry['metrics_totals']
            totals['ai_call_count'] += int(metrics.get('ai_call_count', 0) or 0)
            totals['tool_iteration_count'] += int(metrics.get('tool_iteration_count', 0) or 0)
            totals['validation_duration_sec'] += float(metrics.get('validation_duration_sec', 0.0) or 0.0)
            totals['retry_sleep_duration_sec'] += float(metrics.get('retry_sleep_duration_sec', 0.0) or 0.0)
            totals['attempt_duration_sec'] += float(metrics.get('attempt_duration_sec', 0.0) or 0.0)
            totals['stream_fallback_count'] += int(metrics.get('stream_fallback_count', 0) or 0)

    # --- Write Main Summary File ---
    summary_content = f"# Execution Summary (ConstruQtor v{RUNTIME_VERSION} - Interleaved Pipeline)\n\n"
    summary_content += f"**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(all_results)}/{len(briq_files)} briqs\n"
    summary_content += f"**Results:** ✅ {success_count} | ⚠️ {partial_count} | ❌ {failure_count}\n\n"
    
    if stopped_early:
        summary_content += f"⚠️ **Cycle halted early due to `stop_on_briq_fail=true`**\n\n"
    if early_stopped_repair:
        summary_content += f"⚠️ **Repair cycle short-circuited early (criteria met)**\n\n"
    
    summary_content += "## Build Group Overview\n\n"
    for group_id, group_entry in sorted(grouped_results.items()):
        summary_content += f"### {group_id}\n"
        summary_content += f"- Scope ID: {group_entry['scope_id']}\n"
        summary_content += f"- Components: {', '.join(sorted(group_entry['component_ids']))}\n"
        summary_content += f"- Briqs: {len(group_entry['briq_files'])}\n"
        summary_content += f"- Files Changed: {len(group_entry['written_files'])}\n\n"
        summary_content += f"- Write Strategy: {write_strategy_config['mode']}\n"
        summary_content += f"- Coding Mode: {write_strategy_config['coding_mode']}\n"
        summary_content += f"- Build Attempts: {len(set(group_entry['attempt_ids']))}\n\n"
        summary_content += f"- AI Calls: {group_entry['metrics_totals']['ai_call_count']}\n"
        summary_content += f"- Tool Iterations: {group_entry['metrics_totals']['tool_iteration_count']}\n"
        summary_content += f"- Validation Time: {group_entry['metrics_totals']['validation_duration_sec']:.2f}s\n"
        summary_content += f"- Retry Sleep: {group_entry['metrics_totals']['retry_sleep_duration_sec']:.2f}s\n"
        summary_content += f"- Stream Fallbacks: {group_entry['metrics_totals']['stream_fallback_count']}\n\n"

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
        summary_content += f"- AI Calls: {int(result.get('ai_call_count_total', 0) or 0)}\n"
        summary_content += f"- Tool Iterations: {int(result.get('tool_iteration_count_total', 0) or 0)}\n"
        summary_content += f"- Retry Sleep: {float(result.get('retry_sleep_duration_total_sec', 0.0) or 0.0):.2f}s\n"
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
    existing_groups = {}
    if changed_files_summary_file.exists():
        try:
            current_group = None
            with open(changed_files_summary_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("## "):
                        current_group = line[3:].strip()
                        existing_groups[current_group] = {
                            "scope_id": "unknown",
                            "component_ids": set(),
                            "written_files": set(),
                            "attempt_ids": [],
                            "mode": "unknown",
                            "coding_mode": "unknown",
                        }
                    elif current_group and line.startswith("- Scope ID: `"):
                        existing_groups[current_group]["scope_id"] = line.split("`")[1]
                    elif current_group and line.startswith("- Components: "):
                        comps = line[len("- Components: "):].split(", ")
                        existing_groups[current_group]["component_ids"] = set(c for c in comps if c)
                    elif current_group and line.startswith("- Write Strategy: `"):
                        existing_groups[current_group]["mode"] = line.split("`")[1]
                    elif current_group and line.startswith("- Coding Mode: `"):
                        existing_groups[current_group]["coding_mode"] = line.split("`")[1]
                    elif current_group and line.startswith("- Build Attempts: "):
                        attempts = line[len("- Build Attempts: "):]
                        if attempts != "None":
                            existing_groups[current_group]["attempt_ids"] = attempts.split(", ")
                    elif current_group and line.startswith("- `") and line.endswith("`"):
                        f_name = line[3:-1]
                        existing_groups[current_group]["written_files"].add(f_name)
        except Exception:
            pass

    for group_id, group_entry in grouped_results.items():
        if group_id not in existing_groups:
            existing_groups[group_id] = {
                "scope_id": group_entry.get('scope_id', 'unknown'),
                "component_ids": set(),
                "written_files": set(),
                "attempt_ids": [],
                "mode": write_strategy_config.get('mode', 'unknown'),
                "coding_mode": write_strategy_config.get('coding_mode', 'unknown'),
            }
        existing_groups[group_id]["component_ids"].update(group_entry.get('component_ids', set()))
        existing_groups[group_id]["written_files"].update(group_entry.get('written_files', set()))
        existing_groups[group_id]["attempt_ids"].extend(group_entry.get('attempt_ids', []))

    changed_files_content = "# Changed Files\n\n"
    for group_id, group_entry in sorted(existing_groups.items()):
        changed_files_content += f"## {group_id}\n\n"
        changed_files_content += f"- Scope ID: `{group_entry['scope_id']}`\n"
        comps = ', '.join(sorted(c for c in group_entry['component_ids'] if c))
        changed_files_content += f"- Components: {comps}\n"
        changed_files_content += f"- Write Strategy: `{group_entry['mode']}`\n"
        changed_files_content += f"- Coding Mode: `{group_entry['coding_mode']}`\n"
        attempts = ', '.join(sorted(set(group_entry['attempt_ids']))) or 'None'
        changed_files_content += f"- Build Attempts: {attempts}\n"
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
            "coding_mode": write_strategy_config['coding_mode'],
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
            "metrics": {
                "totals": group_entry['metrics_totals'],
                "per_briq_ai_call_count": group_entry.get('per_briq_ai_call_count', {}),
            },
        }
        changed_scope_manifest = {
            "schema_version": "changed-scope-manifest.v1",
            "run_id": canonical_run_id(worqspace_root),
            "build_group_id": group_id,
            "scope_id": group_entry['scope_id'],
            "write_strategy": write_strategy_config['mode'],
            "coding_mode": write_strategy_config['coding_mode'],
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

    print(f"\n--- ConstruQtor v{RUNTIME_VERSION} Complete: {final_status} ---", flush=True)
    print(f"    Per-briq exeQ summaries written to: exeq.d/cyqle{cycle_num}/", flush=True)
    print(f"    Build-group reports written to: build/groups/", flush=True)


if __name__ == "__main__":
    main()
