#!/usr/bin/env python3
# worqer/inspeqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InspeQtor Agent - Multi-Stage Code Review System
# v1.3.0 - QONTRACT Enforcement + Qonfirmer Integration
# ═══════════════════════════════════════════════════════════════════════════════
#
# STAGE 1 (This File): Per-briq tactical reviews (batched or individual)
# STAGE 2 (inspeqtor_meta.py): Global meta-review aggregating all briq reqaps
#
# v0.9.0 IMPROVEMENTS:
# - Batched reviews: Groups briqs into batches for 90% fewer API calls
# - Default model wiring: venice / deepseek-v3.2
# - Cost estimation before each batch
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
import yaml
import re
import glob
import json
import hashlib
from datetime import datetime, timezone
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


def sha256_file(path: Path) -> str:
    """Compute sha256 hash of a file."""
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def sha256_text(text: str) -> str:
    """Compute sha256 hash of text."""
    return hashlib.sha256(str(text or "").encode('utf-8', errors='replace')).hexdigest()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: 
    import lib_ai
except ImportError: 
    print("CRITICAL: lib_ai.py not found.", flush=True)
    sys.exit(1)

# v1.3.0: Import Qonfirmer
try:
    import qonfirmer
except ImportError:
    qonfirmer = None
    print("[WARN] qonfirmer module not found — deterministic checks disabled", flush=True)

try:
    import smoqetester
except ImportError:
    smoqetester = None
    print("[WARN] smoqetester module not found — smoketest checks disabled", flush=True)

# Import cost estimation
try:
    from calqulator import estimate_tokens, calculate_cost, format_cost
except ImportError:
    # Fallback if calqulator not available
    def estimate_tokens(text, model="gpt-4.1"): return len(text) // 4

# v1.3.10: Path hygiene — cwd-drift guard so reqaps never get written
# inside qodeyard/<sub>/ when cwd has drifted.
try:
    from path_hygiene import assert_cwd_outside_qodeyard
except ImportError:
    def assert_cwd_outside_qodeyard(agent_name="agent"):  # type: ignore
        pass
    def calculate_cost(tokens, model, is_input=True): return (tokens / 1_000_000) * (2.0 if is_input else 8.0)
    def format_cost(cost): return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"

try:
    from integration_checks import (
        build_issue_fingerprint_entries,
        collect_scope_validation_issues,
        derive_group_scope_files,
        normalize_file_hints,
    )
except ImportError:
    def build_issue_fingerprint_entries(*args, **kwargs):  # type: ignore
        return []

    def collect_scope_validation_issues(*args, **kwargs):  # type: ignore
        return []

    def derive_group_scope_files(*args, **kwargs):  # type: ignore
        return []

    def normalize_file_hints(values):  # type: ignore
        return []


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

DEFAULT_SMOKETEST_CONFIG = {
    "enabled": False,
    "mode": "scoped",
    "timeout_seconds": 45,
    "max_output_chars": 800,
    "adapters": {
        "python": {
            "enabled": True,
            "command": None,
            "commands": None,
            "append_changed_files": False,
            "auto_unittest_discover": True,
            "auto_cli_help": False,
        },
        "shell": {
            "enabled": True,
            "command": None,
            "commands": None,
            "append_changed_files": False,
        },
        "js_ts": {
            "enabled": True,
            "command": None,
            "commands": None,
            "append_changed_files": False,
            "auto_tsc_no_emit": True,
            "allow_script_execution": False,
            "require_dependencies": True,
        },
        "html_css": {
            "enabled": True,
            "command": None,
            "commands": None,
            "append_changed_files": False,
        },
    },
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_run_id(worqspace_root: Path) -> str:
    return worqspace_root.name


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def normalize_tri_state_status(value: str | None, default: str = "PASS") -> str:
    raw = str(value or "").strip().upper()
    if raw in {"PASS", "SUCCESS"}:
        return "PASS"
    if raw in {"PARTIAL"}:
        return "PARTIAL"
    if raw in {"FAIL", "FAILURE", "ERROR"}:
        return "FAIL"
    return default


def normalize_smoketest_status(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"PASS", "SUCCESS"}:
        return "PASS"
    if raw in {"PARTIAL"}:
        return "PARTIAL"
    if raw in {"FAIL", "FAILURE", "ERROR"}:
        return "FAIL"
    return "PARTIAL"


def is_success_assessment(value: str | None) -> bool:
    return str(value or "").strip().strip("[]").upper() == "SUCCESS"


def _parse_boolish(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def should_run_report_only_briq_reviews(config: dict | None) -> bool:
    env_raw = os.environ.get("QONQ_INSPEQTOR_REPORT_ONLY_BRIQ_REVIEWS")
    if env_raw is not None and str(env_raw).strip():
        return _parse_boolish(env_raw, default=False)

    agent_cfg = (((config or {}).get("agents", {}) or {}).get("inspeqtor", {}) or {})
    return _parse_boolish(agent_cfg.get("report_only_briq_reviews"), default=False)


def enforce_briq_suggestions_for_repair(ai_review_mode: str, failed_briq_suggestions: list[dict]) -> list[dict]:
    # Report-only briq AI feedback is advisory; deterministic evidence remains
    # the only repair-scope authority in this mode.
    if str(ai_review_mode or "").strip().lower() != "normal":
        return []
    return failed_briq_suggestions


def normalize_file_hint(path_value: str | None) -> str | None:
    if path_value is None:
        return None
    normalized = str(path_value).strip().replace("\\", "/")
    if not normalized:
        return None
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized or None


def normalize_file_hints(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        normalized = normalize_file_hint(values)
        return [normalized] if normalized else []
    if isinstance(values, list):
        deduped: list[str] = []
        seen: set[str] = set()
        for item in values:
            normalized = normalize_file_hint(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped
    return []


def smoketest_report_to_dict(smoketest_report) -> dict | None:
    if smoketest_report is None:
        return None
    if isinstance(smoketest_report, dict):
        return smoketest_report
    if hasattr(smoketest_report, "to_dict"):
        try:
            payload = smoketest_report.to_dict()
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
    return None


def _int_or_zero(value) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def normalize_smoketest_execution_kind(value, executed_flag: bool = False) -> str:
    raw = str(value or "").strip().lower()
    # Support all valid granular kinds
    if raw in {
        "static_probe", "syntax_probe", "process_boot",
        "http_probe", "ws_probe", "browser_probe", "executed"
    }:
        return raw
    # Legacy fallbacks
    if raw == "static": return "static_probe"
    return "executed" if bool(executed_flag) else "static_probe"


def summarize_smoketest_counts(smoke_payload: dict | None) -> dict:
    payload = smoke_payload if isinstance(smoke_payload, dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), list) else []

    executed_count = payload.get("executed_count")
    if executed_count is None:
        executed_count = payload.get("executed")
    static_count = payload.get("static_count")
    
    # v1.3.8: Also pull granular counts if present
    syntax_count = payload.get("syntax_count")
    boot_count = payload.get("boot_count")
    http_count = payload.get("http_count")
    ws_count = payload.get("ws_count")
    browser_count = payload.get("browser_count")

    derived_executed = 0
    derived_static = 0
    derived_syntax = 0
    derived_boot = 0
    derived_http = 0
    derived_ws = 0
    derived_browser = 0

    for item in results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).upper()
        if status == "SKIP":
            continue
        
        kind = normalize_smoketest_execution_kind(item.get("execution_kind"), bool(item.get("executed", False)))
        
        if kind == "static_probe":
            derived_static += 1
        elif kind == "syntax_probe":
            derived_syntax += 1
        elif kind == "process_boot":
            derived_boot += 1
        elif kind == "http_probe":
            derived_http += 1
        elif kind == "ws_probe":
            derived_ws += 1
        elif kind == "browser_probe":
            derived_browser += 1
        elif kind == "executed":
            derived_executed += 1

    # Aggregate executed-ish kinds for high-level flags
    total_executed = (
        (executed_count or derived_executed) + 
        (boot_count or derived_boot) + 
        (http_count or derived_http) + 
        (ws_count or derived_ws) + 
        (browser_count or derived_browser)
    )
    total_static = (
        (static_count or derived_static) + 
        (syntax_count or derived_syntax)
    )

    return {
        "executed_count": total_executed,
        "static_count": total_static,
        "has_executed_evidence": total_executed > 0,
        "has_static_evidence": total_static > 0,
        "granular": {
            "static": static_count or derived_static,
            "syntax": syntax_count or derived_syntax,
            "boot": boot_count or derived_boot,
            "http": http_count or derived_http,
            "ws": ws_count or derived_ws,
            "browser": browser_count or derived_browser,
            "executed": executed_count or derived_executed,
        },
        "commands_executed": _int_or_zero(payload.get("commands_executed")),
        "commands_skipped": _int_or_zero(payload.get("commands_skipped")),
    }


def make_smoketest_runtime_config(full_config: dict | None) -> dict:
    source = dict(full_config or {})
    agents = source.get("agents")
    if not isinstance(agents, dict):
        agents = {}
        source["agents"] = agents
    inspeqtor_cfg = agents.get("inspeqtor")
    if not isinstance(inspeqtor_cfg, dict):
        inspeqtor_cfg = {}
        agents["inspeqtor"] = inspeqtor_cfg

    incoming_smoke = inspeqtor_cfg.get("smoketest")
    if not isinstance(incoming_smoke, dict):
        incoming_smoke = {}

    merged = json.loads(json.dumps(DEFAULT_SMOKETEST_CONFIG))
    for key in ("enabled", "mode", "timeout_seconds", "max_output_chars"):
        if key in incoming_smoke:
            merged[key] = incoming_smoke[key]

    incoming_adapters = incoming_smoke.get("adapters")
    if isinstance(incoming_adapters, dict):
        for adapter_name, defaults in merged["adapters"].items():
            adapter_payload = incoming_adapters.get(adapter_name)
            if isinstance(adapter_payload, dict):
                defaults.update(adapter_payload)
        for adapter_name, adapter_payload in incoming_adapters.items():
            if adapter_name in merged["adapters"]:
                continue
            if isinstance(adapter_payload, dict):
                merged["adapters"][adapter_name] = dict(adapter_payload)

    inspeqtor_cfg["smoketest"] = merged
    return source


def resolve_execution_metadata(cycle_num: str) -> dict:
    def _int_or_none(value):
        try:
            return int(value)
        except Exception:
            return None

    global_iteration_index = int(os.environ.get('QONQ_GLOBAL_ITERATION_INDEX', cycle_num) or cycle_num)
    pass_kind = os.environ.get('QONQ_PASS_KIND', 'build')
    build_pass_index = int(os.environ.get('QONQ_BUILD_PASS_INDEX', cycle_num) or cycle_num)
    repair_pass_index = int(os.environ.get('QONQ_REPAIR_PASS_INDEX', '0') or '0')
    repairing_build_pass_index = os.environ.get('QONQ_REPAIRING_BUILD_PASS_INDEX')
    cycle_estimate_mode = str(os.environ.get('QONQ_CYCLE_ESTIMATE_MODE', 'advisory') or 'advisory').strip().lower()
    if cycle_estimate_mode not in {'advisory', 'scheduler'}:
        cycle_estimate_mode = 'advisory'
    return {
        "global_iteration_index": global_iteration_index,
        "pass_kind": pass_kind,
        "build_pass_index": build_pass_index,
        "repair_pass_index": repair_pass_index,
        "repairing_build_pass_index": int(repairing_build_pass_index) if repairing_build_pass_index else None,
        "cycle_estimate_mode": cycle_estimate_mode,
        "estimated_build_passes": _int_or_none(os.environ.get('QONQ_ESTIMATED_BUILD_PASSES')),
        "scheduled_build_pass_target": _int_or_none(os.environ.get('QONQ_SCHEDULED_BUILD_PASS_TARGET')),
    }


def dedupe_changed_files(changed_files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for filename, content in changed_files:
        norm = str(filename or "").strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append((norm, content))
    return deduped


def extract_briq_file_targets(briq_content: str, required_files: list[str] | None = None) -> list[str]:
    def _looks_numeric_decimal_token(text: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:\.\d+)+", text))

    def _normalize(candidate: str) -> str:
        text = str(candidate or "").strip().replace("\\", "/")
        if text.startswith("qodeyard/"):
            text = text[len("qodeyard/"):]
        while text.startswith("./"):
            text = text[2:]
        return text.strip()

    def _looks_like_target_file(candidate: str) -> bool:
        text = _normalize(candidate)
        if not text:
            return False
        if _looks_numeric_decimal_token(text):
            return False
        if text.startswith("../") or text.startswith("/"):
            return False
        if text.startswith(("http://", "https://")):
            return False
        if ":" in text and "/" not in text:
            return False
        if "/" in text:
            parts = [part for part in text.split("/") if part]
            if parts and all(re.match(r"^[A-Za-z0-9_.-]+$", part) for part in parts):
                return True
        if re.match(r"^[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,10}$", text):
            return True
        if text in {"Dockerfile", "Makefile", "run.sh", "requirements.txt"}:
            return True
        return False

    targets: list[str] = []
    for candidate in re.findall(r'`([^`]+)`', briq_content or ""):
        cleaned = _normalize(candidate)
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    in_required_block = False
    for raw_line in (briq_content or "").splitlines():
        line = raw_line.strip()
        lower = line.lower()
        inline_required = re.search(r"required[-_ ]files?\s*:\s*\[(.+)\]", line, flags=re.IGNORECASE)
        if inline_required:
            for part in inline_required.group(1).split(","):
                cleaned = _normalize(part.strip().strip("`\"'"))
                if _looks_like_target_file(cleaned):
                    targets.append(cleaned)
        if (
            re.search(r"\brequired[-_ ]files?\b", lower)
            or "project must contain exactly these files" in lower
            or "must contain exactly these files" in lower
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
        if not in_required_block or not line:
            continue
        candidate = line.lstrip("-*").strip()
        candidate = re.sub(r"^\d+\.\s*", "", candidate).strip()
        candidate = candidate.strip("`\"'")
        cleaned = _normalize(candidate)
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    # More aggressive filename regex: also catch files in titles or sentences
    for match in re.finditer(
        r"(?<![\w/])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,10}|Dockerfile|Makefile|run\.sh|requirements\.txt)(?![\w/])",
        briq_content or "",
    ):
        cleaned = _normalize(match.group(1))
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    # v1.3.13: Special case for "create X" or "update X" patterns
    for match in re.finditer(r"\b(?:create|update|modify|patch|fix|in)\s+([A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,10})\b", briq_content or "", flags=re.IGNORECASE):
        cleaned = _normalize(match.group(1))
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    for item in required_files or []:
        cleaned = _normalize(item)
        if _looks_like_target_file(cleaned):
            targets.append(cleaned)

    return sorted(set(targets))


def extract_briq_scope_hints(briq_content: str) -> tuple[str | None, str | None]:
    build_group = None
    briq_ref = None
    for match in re.finditer(r"^Build-Group:\s*(.+)$", briq_content or "", re.MULTILINE):
        value = str(match.group(1) or "").strip()
        if value:
            build_group = value
            break
    for match in re.finditer(r"^Briq-Ref:\s*(.+)$", briq_content or "", re.MULTILINE):
        value = str(match.group(1) or "").strip()
        if value:
            briq_ref = value
            break
    return build_group, briq_ref



def snapshot_qodeyard_targets(
    qodeyard_path: Path,
    briq_targets: list[str],
    *,
    max_files: int = 6,
) -> list[tuple[str, str]]:
    snapshots: list[tuple[str, str]] = []
    if not qodeyard_path.is_dir():
        return snapshots
    qodeyard_resolved = qodeyard_path.resolve()
    for target in briq_targets:
        if len(snapshots) >= max_files:
            break
        candidate = qodeyard_path / target
        try:
            resolved = candidate.resolve()
            rel_path = resolved.relative_to(qodeyard_resolved)
        except Exception:
            continue
        if not resolved.is_file():
            continue
        try:
            content = resolved.read_text(encoding='utf-8')
        except Exception as e:
            snapshots.append((str(rel_path), f"[Could not read: {e}]"))
            continue
        snapshots.append((str(rel_path), content))
    return snapshots


def merge_briq_changed_files(
    all_changed: list[tuple[str, str]],
    qodeyard_path: Path,
    briq_targets: list[str],
    *,
    fallback_limit: int,
    scope_files: list[str] | None = None,
) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    normalized_scope_files = normalize_file_hints(scope_files) or normalize_file_hints(briq_targets)
    lower_targets = [target.lower() for target in normalized_scope_files]
    for filename, content in all_changed:
        lower_filename = str(filename).lower()
        if not lower_targets or any(
            target in lower_filename or lower_filename.endswith(target) for target in lower_targets
        ):
            selected.append((filename, content))
    snapshot_targets = normalized_scope_files or briq_targets
    selected.extend(snapshot_qodeyard_targets(qodeyard_path, snapshot_targets, max_files=max(fallback_limit, len(snapshot_targets) or fallback_limit)))
    if not selected and all_changed:
        selected = list(all_changed[:fallback_limit])
    return dedupe_changed_files(selected)


def default_grouped_coherence(changed_manifest_files: list[str], error: Exception | str | None = None) -> dict:
    message = "Grouped coherence evaluation did not complete."
    if error:
        message += f" Cause: {error}"
    return {
        "status": "FAIL",
        "checks": [],
        "issues": [
            {
                "severity": "error",
                "scope": "inspection_pipeline",
                "message": message,
                "files": changed_manifest_files,
            }
        ],
        "group_summaries": [],
        "touched_scope_ids": [],
        "touched_group_files": [],
        "undeclared_changed_files": sorted(set(changed_manifest_files)),
        "unassigned_briqs": [],
    }


def default_validation_bundle(
    worqspace_root: Path,
    cycle_num: str,
    issue_message: str,
    changed_manifest_files: list[str],
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    return {
        "schema_version": "validation-bundle.v1",
        "validation_bundle_id": f"{canonical_run_id(worqspace_root)}-validation-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        "global_iteration_index": execution_meta["global_iteration_index"],
        "pass_kind": execution_meta["pass_kind"],
        "build_pass_index": execution_meta["build_pass_index"],
        "repair_pass_index": execution_meta["repair_pass_index"],
        "repairing_build_pass_index": execution_meta["repairing_build_pass_index"],
        "cycle_estimate_mode": execution_meta["cycle_estimate_mode"],
        "estimated_build_passes": execution_meta["estimated_build_passes"],
        "scheduled_build_pass_target": execution_meta["scheduled_build_pass_target"],
        "stage": "VALIDATION",
        "status": "FAIL",
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "validation_execution_mode": "NONE",
        "coverage": {
            "python_files": [],
            "non_python_files": [],
            "strongest_ecosystem": None,
        },
        "capability_disclosure": {
            "deterministic_validation_strength": "PYTHON_CENTRIC_STATIC_VALIDATION",
            "notes": [
                "Validation bundle is degraded due to an InspeQtor runtime substep failure.",
            ],
        },
        "checks": [
            {
                "check_id": "inspection_runtime",
                "level": "inspection_runtime",
                "status": "FAIL",
                "executed": False,
            }
        ],
        "issues": [
            {
                "source": "inspection_runtime",
                "severity": "error",
                "message": issue_message,
            }
        ],
        "grouped_component_validation": [],
        "unknowns": [
            "Validation bundle was generated in degraded mode.",
        ],
        "evidence_refs": [f"exeq.d/cyqle{cycle_num}_changed.md"] if changed_manifest_files else [],
        "created_at": now_utc(),
    }


def default_realization_bundle(
    worqspace_root: Path,
    cycle_num: str,
    validation_bundle: dict,
    changed_manifest_files: list[str],
    issue_message: str,
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    return {
        "schema_version": "realization-bundle.v1",
        "realization_bundle_id": f"{canonical_run_id(worqspace_root)}-realization-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        **execution_meta,
        "stage": "REALIZATION",
        "status": "EVIDENCE_PARTIAL",
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "validation_execution_mode": validation_bundle.get("validation_execution_mode", "NONE"),
        "evidence_status": "EVIDENCE_PARTIAL",
        "confidence": "CONFIDENCE_LOW",
        "scope_summary": {
            "intended_scopes": [],
            "touched_scopes": [],
            "undeclared_touched_scopes": [f"file:{path}" for path in changed_manifest_files],
        },
        "structural_reality": {
            "changed_files": [
                {
                    "path": path,
                    "change_type": "modified_or_created",
                    "build_group_id": None,
                    "scope_id": None,
                    "in_intended_scope": False,
                    "evidence_class": "direct_execution_evidence",
                    "commit_state": "unknown_commit_state",
                    "source_build_ref": f"exeq.d/cyqle{cycle_num}_changed.md",
                }
                for path in changed_manifest_files
            ],
            "touched_components": [],
            "artifact_changes": [],
        },
        "behavioral_reality": {
            "observed_behaviors": [],
            "failed_behaviors": [],
            "unverified_behaviors": [],
            "interface_behavior_deltas": [],
        },
        "system_impact_reality": {
            "performance": {"status": "unknown", "reason": "No benchmark evidence collected."},
            "stability": {"status": "unknown", "reason": "No long-running runtime telemetry collected."},
            "resource_usage": {"status": "unknown", "reason": "No resource telemetry collected."},
            "error_signals": [],
        },
        "unknowns": [
            issue_message,
            "Realization bundle was generated in degraded mode.",
        ],
        "write_strategy": {
            "mode": "unknown",
            "group_modes": [],
            "recovery_policies": [],
            "recovery_refs": [],
            "attempt_manifest_refs": [],
        },
        "execution_backend": {
            "engines": [],
            "authority_disclosure": "Execution backends could not be derived due to degraded inspection mode.",
        },
        "evidence_refs": [],
        "source_build_refs": [],
        "source_validation_refs": ["validation/validation-bundle.v1.json"],
        "manifest_ref": "run-manifest.v1.json",
        "created_at": now_utc(),
    }


def default_inspection_verdict(
    worqspace_root: Path,
    cycle_num: str,
    validation_bundle: dict,
    realization_bundle: dict,
    inspection_input: dict,
    issue_message: str,
    substep_failures: list[dict] | None = None,
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    failures = list(substep_failures or [])
    if not failures:
        failures = [{
            "substep": "inspection_pipeline",
            "recoverable": True,
            "error": issue_message,
        }]
    validation_status = normalize_tri_state_status(validation_bundle.get("status"), default="FAIL")
    repair_required = validation_status != "PASS" or bool(failures)
    status = "FAILURE" if validation_status == "FAIL" else "PARTIAL"
    return {
        "schema_version": "inspection-verdict.v1",
        "inspection_verdict_id": f"{canonical_run_id(worqspace_root)}-inspection-verdict-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        "stage": "INSPECTION",
        "status": status,
        "deterministic_gate": "FAIL" if validation_status == "FAIL" else "PASS",
        "completion_criteria_results": [
            {
                "criterion": "Inspection produced a bounded degraded verdict after substep failure.",
                "status": "PARTIAL",
                "basis": issue_message,
            }
        ],
        "completion_criteria_summary": "Inspection degraded and generated a recoverable fallback verdict.",
        "confidence": realization_bundle.get("confidence", "CONFIDENCE_LOW"),
        "evidence_status": realization_bundle.get("evidence_status", "EVIDENCE_PARTIAL"),
        "validation_execution_mode": validation_bundle.get("validation_execution_mode", "NONE"),
        "capability_mode": realization_bundle.get("capability_mode", "MIXED_REASONING_EXECUTION"),
        "issues": [
            {
                "issue_id": "inspection-runtime-001",
                "summary": issue_message,
                "severity": "error",
                "source": "inspection_runtime",
            }
        ],
        "repair_required": repair_required,
        "task_completed": not repair_required,
        "completion_assessment": "Inspection degraded due to a recoverable runtime error; bounded repair planning should continue when possible.",
        "next_lifecycle_transition": "REPAIRING" if repair_required else "COMPLETED",
        "repair_plan_ref": None,
        "unresolved_issues": [issue_message],
        "inspection_integrity": "DEGRADED",
        "inspection_substep_failures": failures,
        "evidence_refs": [
            "validation/validation-bundle.v1.json",
            "realization/realization-bundle.v1.json",
            "verdict/inspection-input.v1.json",
        ],
        "created_at": now_utc(),
        **execution_meta,
    }


def recommend_repair_start_level_for_failure_class(failure_class: str) -> int:
    mapping = {
        "collateral_churn_overrewrite": 1,
        "required_output_missing": 2,
        "transport_write_failure": 2,
        "runtime_syntax_launch_failure": 2,
        "exact_validator_violation": 3,
        "file_scoped_contract_miss": 3,
        "broad_task_shape_miss": 4,
    }
    return int(mapping.get(str(failure_class or "").strip(), 1))


def classify_repair_failure_for_plan(inspection_verdict: dict, validation_bundle: dict) -> tuple[str, str]:
    issues = inspection_verdict.get("issues", []) if isinstance(inspection_verdict, dict) else []
    summaries = " ".join(str(item.get("summary", "")) for item in issues).lower()
    validation_issues = validation_bundle.get("issues", []) if isinstance(validation_bundle, dict) else []
    failure_kinds = {str(item.get("failure_kind", "")).strip() for item in validation_issues}

    if "required deliverable files exist in qodeyard" in summaries and "missing" in summaries:
        return "required_output_missing", "required deliverables are missing from qodeyard"
    if "collateral churn" in summaries or "suspiciously tiny" in summaries or "overrewrite" in summaries:
        return "collateral_churn_overrewrite", "suspected collateral churn or excessive rewrite detected"
    if any(kind in {"blocking_code_failures", "dependency_declaration_failures"} for kind in failure_kinds):
        return "exact_validator_violation", "deterministic validation violations were reported"
    if any(kind in {"environment_dependency_missing", "tooling_missing"} for kind in failure_kinds):
        return "runtime_syntax_launch_failure", "runtime/tooling checks were blocked or failed"
    if "qonfirmer" in summaries or "deterministic issue" in summaries:
        return "exact_validator_violation", "inspection reported deterministic contract violations"
    if "scope" in summaries or "briq" in summaries:
        return "file_scoped_contract_miss", "scope-specific issues require bounded file-level repair"
    return "broad_task_shape_miss", "repair required across planned scope"


def default_repair_plan(
    worqspace_root: Path,
    cycle_num: str,
    inspection_verdict: dict,
    issue_message: str,
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    failure_class, failure_reason = classify_repair_failure_for_plan(inspection_verdict or {}, {})
    start_level = recommend_repair_start_level_for_failure_class(failure_class)
    target_briq_files = sorted((worqspace_root / "briq.d").glob(f"cyqle{cycle_num}_*.md"))
    target_names = [path.name for path in target_briq_files]
    same_run_eligible = bool(target_names)
    continuation_strategy = "same_run" if same_run_eligible else "linked_continuation"
    next_transition = "REPAIRING" if same_run_eligible else "CONTINUABLE"
    return {
        "schema_version": "repair-plan.v1",
        "repair_plan_id": f"{canonical_run_id(worqspace_root)}-repair-plan-cyqle{cycle_num}",
        "source_run_id": canonical_run_id(worqspace_root),
        "source_cycle": int(cycle_num),
        "source_global_iteration_index": execution_meta["global_iteration_index"],
        "source_pass_kind": execution_meta["pass_kind"],
        "source_build_pass_index": execution_meta["build_pass_index"],
        "source_repair_pass_index": execution_meta["repair_pass_index"],
        "repairing_build_pass_index": execution_meta["repairing_build_pass_index"],
        "source_cycle_estimate_mode": execution_meta["cycle_estimate_mode"],
        "source_estimated_build_passes": execution_meta["estimated_build_passes"],
        "source_scheduled_build_pass_target": execution_meta["scheduled_build_pass_target"],
        "source_verdict_ref": "verdict/inspection-verdict.v1.json",
        "repair_reason_summary": inspection_verdict.get("completion_assessment", issue_message),
        "target_components": [],
        "target_scopes": [],
        "target_build_groups": [],
        "target_briq_refs": [],
        "target_briq_files": target_names,
        "required_actions": [
            "repair deterministic validation and inspection-runtime failures in the targeted scope",
            "re-run validation, realization, and inspection after the targeted repair pass",
        ],
        "planning_reuse_mode": "reuse_locked_plan",
        "repair_pass_index": execution_meta["repair_pass_index"] + 1,
        "repair_constraints": [
            "no architecture mutation",
            "no scope expansion",
            "repair must stay within manifest-linked target groups and briqs",
        ],
        "validation_requirements_for_repair": ["inspection_runtime"],
        "same_run_repair_eligible": same_run_eligible,
        "continuation_strategy": continuation_strategy,
        "next_lifecycle_transition": next_transition,
        "repair_status": "REPAIR_PROPOSED",
        "manifest_refs": ["run-manifest.v1.json"],
        "evidence_refs": [
            "validation/validation-bundle.v1.json",
            "realization/realization-bundle.v1.json",
            "verdict/inspection-verdict.v1.json",
        ],
        "repair_required_semantics": "explicit_bounded_manifest_linked",
        "repair_escalation": {
            "enabled": True,
            "recommended_failure_class": failure_class,
            "recommended_start_level": start_level,
            "reason": failure_reason,
        },
        "created_at": now_utc(),
    }


def mark_substep_failure(failures: list[dict], substep: str, error: Exception | str, recoverable: bool = True) -> None:
    failures.append({
        "substep": substep,
        "recoverable": recoverable,
        "error": str(error),
        "captured_at": now_utc(),
    })


def detect_validation_execution_mode(qonfirmer_report, verification_results, smoketest_report=None) -> str:
    smoke_payload = smoketest_report_to_dict(smoketest_report) or {}
    smoke_counts = summarize_smoketest_counts(smoke_payload)
    has_static = bool(qonfirmer_report or verification_results) or smoke_counts["static_count"] > 0
    has_executed = smoke_counts["executed_count"] > 0
    if has_static and has_executed:
        return "MIXED"
    if has_executed:
        return "EXECUTED"
    if has_static:
        return "STATIC_ONLY"
    return "NONE"


def detect_repo_languages(qodeyard_path: Path) -> dict:
    python_files = []
    non_python_files = []
    
    known_extensionless = {
        'dockerfile', 'makefile', 'gnumakefile', 'jenkinsfile', 
        'gemfile', 'rakefile', 'procfile', 'vagrantfile', 
        'justfile', 'capfile', 'podfile', 'cmakelists.txt',
    }

    for file_path in qodeyard_path.rglob("*"):
        if not file_path.is_file():
            continue
        
        # Skip common non-source directories if they happen to be in qodeyard
        if '.git' in file_path.parts or '__pycache__' in file_path.parts:
            continue

        if file_path.suffix == ".py":
            python_files.append(str(file_path.relative_to(qodeyard_path)))
        elif file_path.suffix:
            non_python_files.append(str(file_path.relative_to(qodeyard_path)))
        else:
            name_lower = file_path.name.lower()
            if name_lower in known_extensionless or os.access(file_path, os.X_OK):
                non_python_files.append(str(file_path.relative_to(qodeyard_path)))

    return {
        "python_files": sorted(python_files),
        "non_python_files": sorted(non_python_files),
    }


def evaluate_grouped_coherence(
    worqspace_root: Path,
    cycle_num: str,
    changed_manifest_files: list[str],
) -> dict:
    build_groups_doc = load_optional_json(worqspace_root / "planning" / "build-groups.v1.json")
    component_contracts_doc = load_optional_json(worqspace_root / "planning" / "component-contracts.v1.json")
    build_group_items = build_groups_doc.get("items", [])
    component_contracts = {
        item.get("component_id"): item
        for item in component_contracts_doc.get("items", [])
        if item.get("component_id")
    }
    briq_inventory = build_groups_doc.get("briq_inventory", [])

    checks = []
    issues = []
    touched_group_files = set()
    touched_scope_ids = set()
    group_summaries = []
    assigned_briq_refs = set()

    for item in build_group_items:
        group_id = item.get("build_group_id")
        scope_id = item.get("scope_id")
        planned_components = sorted(item.get("component_refs", []))
        planned_briqs = item.get("briq_refs", [])
        assigned_briq_refs.update(planned_briqs)

        group_dir = worqspace_root / "build" / "groups" / group_id
        build_report = load_optional_json(group_dir / "build-report.v1.json")
        changed_scope = load_optional_json(group_dir / "changed-files.v1.json")
        report_files = sorted(build_report.get("files", []))
        changed_files = sorted(
            entry.get("path")
            for entry in changed_scope.get("changed_files", [])
            if entry.get("path")
        )
        touched_group_files.update(changed_files)
        if scope_id:
            touched_scope_ids.add(scope_id)

        group_status = "PASS"
        if not build_report:
            group_status = "FAIL"
            issues.append({
                "severity": "error",
                "scope": group_id,
                "message": f"Missing build report for group `{group_id}`.",
            })
        if not changed_scope:
            group_status = "FAIL"
            issues.append({
                "severity": "error",
                "scope": group_id,
                "message": f"Missing changed-scope manifest for group `{group_id}`.",
            })

        reported_components = sorted(build_report.get("component_ids", []))
        if build_report and reported_components != planned_components:
            group_status = "PARTIAL" if group_status == "PASS" else group_status
            issues.append({
                "severity": "warning",
                "scope": group_id,
                "message": f"Planned components {planned_components} do not match build report components {reported_components}.",
            })

        if build_report and changed_scope and report_files != changed_files:
            group_status = "PARTIAL" if group_status == "PASS" else group_status
            issues.append({
                "severity": "warning",
                "scope": group_id,
                "message": f"Build report files and changed-scope files differ for `{group_id}`.",
            })

        attempt_ids = sorted(build_report.get("build_attempt_ids", [])) if build_report else []
        changed_attempt_ids = sorted(changed_scope.get("build_attempt_ids", [])) if changed_scope else []
        if build_report and not build_report.get("write_strategy"):
            group_status = "FAIL" if group_status == "PASS" else group_status
            issues.append({
                "severity": "error",
                "scope": group_id,
                "message": f"Missing explicit write strategy disclosure for `{group_id}`.",
            })
        if changed_scope and not changed_scope.get("recovery_refs"):
            group_status = "PARTIAL" if group_status == "PASS" else group_status
            issues.append({
                "severity": "warning",
                "scope": group_id,
                "message": f"Missing recovery metadata references for `{group_id}`.",
            })
        if build_report and changed_scope:
            if attempt_ids and changed_attempt_ids and attempt_ids != changed_attempt_ids:
                group_status = "FAIL" if group_status == "PASS" else group_status
                issues.append({
                    "severity": "error",
                    "scope": group_id,
                    "message": f"Attempt lineage mismatch between build report and changed-scope manifest for `{group_id}`.",
                })
            elif bool(attempt_ids) != bool(changed_attempt_ids):
                group_status = "PARTIAL" if group_status == "PASS" else group_status
                issues.append({
                    "severity": "warning",
                    "scope": group_id,
                    "message": (
                        f"Attempt lineage metadata is only partially present for `{group_id}`; "
                        "repair targeting will fall back to file/scope evidence."
                    ),
                })

        missing_component_contracts = [
            component_id for component_id in planned_components if component_id not in component_contracts
        ]
        if missing_component_contracts:
            group_status = "PARTIAL" if group_status == "PASS" else group_status
            issues.append({
                "severity": "warning",
                "scope": group_id,
                "message": f"Missing component contracts for {', '.join(missing_component_contracts)}.",
            })

        checks.append({
            "check_id": f"group-coherence-{group_id}",
            "level": "build_group_checks",
            "status": group_status,
            "build_group_id": group_id,
            "scope_id": scope_id,
            "planned_components": planned_components,
            "planned_briq_count": len(planned_briqs),
            "reported_file_count": len(report_files),
            "changed_file_count": len(changed_files),
            "write_strategy": build_report.get("write_strategy") if build_report else None,
            "build_attempt_count": len(attempt_ids),
            "recovery_ref_count": len(changed_scope.get("recovery_refs", [])) if changed_scope else 0,
        })
        group_summaries.append({
            "build_group_id": group_id,
            "scope_id": scope_id,
            "planned_components": planned_components,
            "planned_briq_refs": planned_briqs,
            "reported_files": report_files,
            "changed_files": changed_files,
            "status": group_status,
            "write_strategy": build_report.get("write_strategy") if build_report else None,
            "write_strategy_disclosure": build_report.get("write_strategy_disclosure") if build_report else None,
            "recovery_policy": build_report.get("recovery_policy") if build_report else None,
            "build_attempt_ids": attempt_ids,
            "attempt_manifest_refs": build_report.get("attempt_manifest_refs", []) if build_report else [],
            "recovery_refs": changed_scope.get("recovery_refs", []) if changed_scope else [],
            "execution_backend": build_report.get("execution_backend") if build_report else None,
        })

    unassigned_briqs = [
        item.get("briq_ref")
        for item in briq_inventory
        if item.get("briq_ref") and item.get("briq_ref") not in assigned_briq_refs
    ]
    if unassigned_briqs:
        issues.append({
            "severity": "error",
            "scope": f"cycle-{cycle_num}",
            "message": f"Unassigned briqs detected: {', '.join(unassigned_briqs)}.",
        })

    undeclared_changed_files = sorted(set(changed_manifest_files) - touched_group_files)
    if undeclared_changed_files:
        issues.append({
            "severity": "warning",
            "scope": f"cycle-{cycle_num}",
            "message": "Changed files exist outside grouped scope manifests.",
            "files": undeclared_changed_files,
        })

    overall_status = "PASS"
    if any(issue["severity"] == "error" for issue in issues):
        overall_status = "FAIL"
    elif issues:
        overall_status = "PARTIAL"

    return {
        "status": overall_status,
        "checks": checks,
        "issues": issues,
        "group_summaries": group_summaries,
        "touched_scope_ids": sorted(touched_scope_ids),
        "touched_group_files": sorted(touched_group_files),
        "undeclared_changed_files": undeclared_changed_files,
        "unassigned_briqs": unassigned_briqs,
    }


def _collect_frontend_handler_markers(worqspace_root: Path) -> list[str]:
    task_spec = load_optional_json(worqspace_root / "task" / "task-spec.v1.json")
    contract = load_optional_json(worqspace_root / "qontract.d" / "qontract.json")
    completion = load_optional_json(worqspace_root / "planning" / "completion-criteria.v1.json")
    candidates: list[str] = []

    def _add_from_container(container):
        if not isinstance(container, dict):
            return
        for key in ("required_handler_markers", "frontend_handler_markers", "handler_markers", "required_handlers"):
            value = container.get(key)
            if isinstance(value, list):
                for item in value:
                    text = str(item or "").strip()
                    if text:
                        candidates.append(text)

    _add_from_container(task_spec)
    _add_from_container(task_spec.get("metadata") if isinstance(task_spec.get("metadata"), dict) else {})
    _add_from_container(contract)
    _add_from_container(contract.get("invariants") if isinstance(contract.get("invariants"), dict) else {})
    _add_from_container(completion)

    # Optional extraction from task prose if explicit handler names are called out.
    for text in (
        str(task_spec.get("clarified_task_body", "")),
        str(task_spec.get("goal", "")),
        str(task_spec.get("clarification_summary", "")),
    ):
        for marker in re.findall(r"\b(handle_[a-zA-Z0-9_]+)\b", text):
            candidates.append(marker)

    deduped: list[str] = []
    seen: set[str] = set()
    for marker in candidates:
        norm = marker.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        deduped.append(norm)
    return deduped


def evaluate_frontend_contracts(worqspace_root: Path) -> list[dict]:
    qodeyard = worqspace_root / "qodeyard"
    index_path = qodeyard / "index.html"
    js_path = qodeyard / "app.js"
    issues: list[dict] = []
    if not index_path.exists() or not js_path.exists():
        return issues

    issues.extend(collect_scope_validation_issues(worqspace_root, scope_files=["index.html", "app.js", "styles.css"]))

    try:
        js = js_path.read_text(encoding="utf-8")
    except Exception:
        return issues

    required_handler_markers = _collect_frontend_handler_markers(worqspace_root)
    if required_handler_markers:
        missing_handlers = [marker for marker in required_handler_markers if marker not in js]
        if missing_handlers:
            issues.append({
                "severity": "error",
                "scope": "frontend_contract",
                "message": f"Task-declared UI handlers are missing from app.js: {', '.join(missing_handlers)}",
                "files": ["app.js"],
            })

    deduped: list[dict] = []
    seen: set[tuple] = set()
    for issue in issues:
        key = (
            str(issue.get("source") or "frontend_contract"),
            str(issue.get("severity") or "error"),
            str(issue.get("message") or ""),
            tuple(normalize_file_hints(issue.get("files") or issue.get("file"))),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def build_validation_bundle(
    worqspace_root: Path,
    cycle_num: str,
    qonfirmer_report,
    verification_results,
    smoketest_report,
    grouped_coherence: dict,
    changed_manifest_files: list[str],
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    reqap_dir = worqspace_root / "reqap.d"
    qonfirmer_md = reqap_dir / f"cyqle{cycle_num}_qonfirmer.md"
    qonfirmer_json = reqap_dir / f"cyqle{cycle_num}_qonfirmer.json"
    verification_md = reqap_dir / f"cyqle{cycle_num}" / f"cyqle{cycle_num}_verification.md"
    smoketest_md = reqap_dir / f"cyqle{cycle_num}" / f"cyqle{cycle_num}_smoketest.md"
    smoketest_json = reqap_dir / f"cyqle{cycle_num}" / f"cyqle{cycle_num}_smoketest.v1.json"
    language_inventory = detect_repo_languages(worqspace_root / "qodeyard")

    checks = []
    issues = []
    if qonfirmer_report:
        qonfirmer_status = "PASS" if qonfirmer_report.passed else "FAIL"
        checks.append({
            "check_id": "qonfirmer",
            "level": "project_specific_checks",
            "status": qonfirmer_status,
            "executed": True,
            "files_checked": qonfirmer_report.files_checked,
            "rules_checked": qonfirmer_report.rules_checked,
            "issue_count": len(qonfirmer_report.violations),
        })
        for violation in qonfirmer_report.violations:
            rel_file = getattr(violation, "file_path", None)
            file_hash = sha256_file(worqspace_root / "qodeyard" / rel_file) if rel_file else None
            issues.append({
                "source": "qonfirmer",
                "severity": getattr(violation, "severity", "error"),
                "file": rel_file,
                "line": getattr(violation, "line_number", None),
                "message": getattr(violation, "message", str(violation)),
                "file_hash": file_hash,
                "evidence_freshness": now_utc(),
            })

    if verification_results:
        verification_status = normalize_tri_state_status(getattr(verification_results, "overall_status", None), default="PASS")
        checks.append({
            "check_id": "qualification",
            "level": "language_specific_checks",
            "status": verification_status,
            "executed": True,
            "files_checked": verification_results.files_checked,
            "passed": verification_results.passed,
            "warnings": verification_results.warnings,
            "errors": verification_results.errors,
        })
        for result in verification_results.results:
            if result.passed:
                continue
            rel_file = result.file_path
            file_hash = sha256_file(worqspace_root / "qodeyard" / rel_file) if rel_file else None
            issues.append({
                "source": "qualification",
                "severity": result.severity,
                "file": rel_file,
                "line": result.line_number,
                "message": result.message,
                "check_type": result.check_type,
                "file_hash": file_hash,
                "evidence_freshness": now_utc(),
            })

    smoke_payload = smoketest_report_to_dict(smoketest_report) or {}
    smoke_counts = summarize_smoketest_counts(smoke_payload)
    smoke_status = normalize_smoketest_status(smoke_payload.get("overall_status"))
    smoke_results = smoke_payload.get("results") if isinstance(smoke_payload.get("results"), list) else []
    smoke_executed = smoke_counts["executed_count"]
    smoke_static = smoke_counts["static_count"]
    checks.append({
        "check_id": "smoketest",
        "level": "smoke_checks",
        "status": smoke_status,
        "executed": smoke_executed > 0,
        "mode": smoke_payload.get("mode", "scoped"),
        "enabled": bool(smoke_payload.get("enabled", False)),
        "executed_checks": smoke_executed,
        "executed_count": smoke_executed,
        "static_count": smoke_static,
        "granular_counts": smoke_counts.get("granular", {}),
        "has_executed_evidence": smoke_counts["has_executed_evidence"],
        "has_static_evidence": smoke_counts["has_static_evidence"],
        "commands_executed": smoke_counts["commands_executed"],
        "commands_skipped": smoke_counts["commands_skipped"],
        "failed_checks": int(smoke_payload.get("failed", 0) or 0),
        "warning_checks": int(smoke_payload.get("warnings", 0) or 0),
        "error_checks": int(smoke_payload.get("errors", 0) or 0),
        "skipped_checks": int(smoke_payload.get("skipped", 0) or 0),
        "adapters_triggered": smoke_payload.get("adapters_triggered", []),
    })
    for item in smoke_results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).upper()
        if status in {"PASS", "SKIP"}:
            continue
        related_files = normalize_file_hints(item.get("related_files"))
        files = normalize_file_hints(item.get("files"))
        primary_file = normalize_file_hint(item.get("file"))
        if primary_file and primary_file not in related_files:
            related_files.insert(0, primary_file)
        for value in files:
            if value not in related_files:
                related_files.append(value)
        item_kind = normalize_smoketest_execution_kind(item.get("execution_kind"), bool(item.get("executed", False)))
        raw_severity = str(item.get("severity", "")).strip().lower()
        if raw_severity not in {"info", "warning", "error"}:
            raw_severity = "error" if status in {"FAIL", "ERROR"} else "warning"
        
        file_hash = sha256_file(worqspace_root / "qodeyard" / primary_file) if primary_file else None
        issues.append({
            "source": "smoketest",
            "severity": raw_severity,
            "file": primary_file,
            "files": files,
            "related_files": related_files,
            "scope": item.get("scope"),
            "message": item.get("message", "Smoketest reported a failure."),
            "adapter": item.get("adapter"),
            "check_type": item.get("name"),
            "command": item.get("command"),
            "execution_kind": item_kind,
            "exit_code": item.get("exit_code"),
            "duration_ms": item.get("duration_ms"),
            "executed": item_kind != "static_probe" and item_kind != "syntax_probe",
            "failure_kind": item.get("failure_kind"),
            "missing_module": item.get("missing_module"),
            "environment_blocked": bool(item.get("environment_blocked", False)),
            "file_hash": file_hash,
            "evidence_freshness": now_utc(),
        })

    checks.append({
        "check_id": "grouped_component_coherence",
        "level": "universal_checks",
        "status": normalize_tri_state_status(grouped_coherence.get("status"), default="FAIL"),
        "executed": True,
        "groups_checked": len(grouped_coherence["group_summaries"]),
        "undeclared_changed_file_count": len(grouped_coherence["undeclared_changed_files"]),
        "unassigned_briq_count": len(grouped_coherence["unassigned_briqs"]),
        "changed_manifest_file_count": len(changed_manifest_files),
    })
    issues.extend([
        {
            "source": "grouped_component_coherence",
            **issue,
        }
        for issue in grouped_coherence["issues"]
    ])
    integration_scope_files = changed_manifest_files or ["index.html", "styles.css", "app.js"]
    integration_issues = collect_scope_validation_issues(worqspace_root, scope_files=integration_scope_files)
    issues.extend([
        {
            "source": str(issue.get("source") or "frontend_contract"),
            **{k: v for k, v in issue.items() if k != "source"},
        }
        for issue in integration_issues
    ])
    checks.append({
        "check_id": "group_scope_integration",
        "level": "universal_checks",
        "status": "FAIL" if any(str(issue.get("severity", "")).lower() == "error" for issue in integration_issues) else ("PARTIAL" if integration_issues else "PASS"),
        "executed": True,
        "issue_count": len(integration_issues),
    })

    normalized_check_statuses = [normalize_tri_state_status(check.get("status"), default="PASS") for check in checks]
    validation_status = "PASS"
    if any(status == "FAIL" for status in normalized_check_statuses):
        validation_status = "FAIL"
    elif any(status == "PARTIAL" for status in normalized_check_statuses):
        validation_status = "PARTIAL"

    unknowns = []
    capability_notes = [
        "Deterministic validation is strongest for Python files in the current engine.",
        "Grouped integration checks now cover high-value frontend HTML/JS contracts and Python/FastAPI wiring within the active repair or changed-file scope.",
    ]
    if smoke_executed > 0:
        capability_notes.append("Executed smoketest checks were run inside the canonical validation boundary.")
    elif smoke_static > 0:
        capability_notes.append("Smoketest produced static checks only; no executed smoke commands were observed.")
    else:
        capability_notes.append("No executed smoketest checks ran in this cycle.")
    if language_inventory["non_python_files"]:
        unknowns.append("Non-Python files changed without equivalent deterministic compile/test validation coverage.")
    if not language_inventory["python_files"]:
        unknowns.append("No Python files were available for the strongest deterministic validation path.")
    if smoke_payload and smoke_executed == 0 and smoke_static == 0:
        unknowns.append("Smoketest was configured but neither static nor executed checks ran for the active scope.")

    return {
        "schema_version": "validation-bundle.v1",
        "validation_bundle_id": f"{canonical_run_id(worqspace_root)}-validation-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        "global_iteration_index": execution_meta["global_iteration_index"],
        "pass_kind": execution_meta["pass_kind"],
        "build_pass_index": execution_meta["build_pass_index"],
        "repair_pass_index": execution_meta["repair_pass_index"],
        "repairing_build_pass_index": execution_meta["repairing_build_pass_index"],
        "cycle_estimate_mode": execution_meta["cycle_estimate_mode"],
        "estimated_build_passes": execution_meta["estimated_build_passes"],
        "scheduled_build_pass_target": execution_meta["scheduled_build_pass_target"],
        "stage": "VALIDATION",
        "status": validation_status,
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "validation_execution_mode": detect_validation_execution_mode(qonfirmer_report, verification_results, smoke_payload),
        "evidence_freshness": now_utc(),
        "source_provenance": f"{canonical_run_id(worqspace_root)}-inspeqtor-cyqle{cycle_num}",
        "smoketest": smoke_payload,
        "coverage": {
            "python_files": language_inventory["python_files"],
            "non_python_files": language_inventory["non_python_files"],
            "strongest_ecosystem": "python" if language_inventory["python_files"] else None,
        },
        "capability_disclosure": {
            "deterministic_validation_strength": "PYTHON_CENTRIC_STATIC_VALIDATION",
            "notes": capability_notes,
        },
        "checks": checks,
        "issues": issues,
        "grouped_component_validation": grouped_coherence["group_summaries"],
        "unknowns": unknowns,
        "evidence_refs": [
            str(path)
            for path in [
                qonfirmer_md.relative_to(worqspace_root) if qonfirmer_md.exists() else None,
                qonfirmer_json.relative_to(worqspace_root) if qonfirmer_json.exists() else None,
                verification_md.relative_to(worqspace_root) if verification_md.exists() else None,
                smoketest_md.relative_to(worqspace_root) if smoketest_md.exists() else None,
                smoketest_json.relative_to(worqspace_root) if smoketest_json.exists() else None,
            ]
            if path
        ] + [
            f"build/groups/{group['build_group_id']}/build-report.v1.json"
            for group in grouped_coherence["group_summaries"]
        ] + [
            f"build/groups/{group['build_group_id']}/changed-files.v1.json"
            for group in grouped_coherence["group_summaries"]
        ],
        "created_at": now_utc(),
    }


def build_realization_bundle(
    worqspace_root: Path,
    cycle_num: str,
    validation_bundle: dict,
    smoketest_report,
    grouped_coherence: dict,
    changed_manifest_files: list[str],
    cross_briq_warnings: list[str],
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    build_groups_doc = load_optional_json(worqspace_root / "planning" / "build-groups.v1.json")
    summary_path = worqspace_root / "exeq.d" / f"cyqle{cycle_num}_summary.md"
    changed_path = worqspace_root / "exeq.d" / f"cyqle{cycle_num}_changed.md"

    changed_file_records = []
    for group in grouped_coherence["group_summaries"]:
        changed_manifest = load_optional_json(
            worqspace_root / "build" / "groups" / group["build_group_id"] / "changed-files.v1.json"
        )
        manifest_changed_files = changed_manifest.get("changed_files", [])
        if manifest_changed_files:
            for entry in manifest_changed_files:
                if not entry.get("path"):
                    continue
                changed_file_records.append({
                    "path": entry.get("path"),
                    "change_type": entry.get("change_type", "modified_or_created"),
                    "build_group_id": group["build_group_id"],
                    "scope_id": group["scope_id"],
                    "in_intended_scope": entry.get("in_intended_scope", True),
                    "evidence_class": entry.get("evidence_class", "direct_execution_evidence"),
                    "commit_state": entry.get("commit_state", "committed_atomically"),
                    "source_build_ref": entry.get("source_build_ref", f"build/groups/{group['build_group_id']}/build-report.v1.json"),
                    "attempt_ids": entry.get("attempt_ids", []),
                })
        else:
            for path in group["changed_files"]:
                changed_file_records.append({
                    "path": path,
                    "change_type": "modified_or_created",
                    "build_group_id": group["build_group_id"],
                    "scope_id": group["scope_id"],
                    "in_intended_scope": True,
                    "evidence_class": "direct_execution_evidence",
                    "commit_state": "unknown_commit_state",
                    "source_build_ref": f"build/groups/{group['build_group_id']}/build-report.v1.json",
                    "attempt_ids": [],
                })

    for path in grouped_coherence["undeclared_changed_files"]:
        changed_file_records.append({
            "path": path,
            "change_type": "modified_or_created",
            "build_group_id": None,
            "scope_id": None,
            "in_intended_scope": False,
            "evidence_class": "direct_execution_evidence",
            "commit_state": "committed_atomically_but_out_of_declared_scope",
            "source_build_ref": f"exeq.d/cyqle{cycle_num}_changed.md",
        })

    observed_behaviors = []
    failed_behaviors = []
    unverified_behaviors = []
    for check in validation_bundle.get("checks", []):
        behavior = {
            "behavior_id": check["check_id"],
            "result": check["status"].lower(),
            "evidence_class": "direct_deterministic_evidence",
        }
        if check["status"] == "FAIL":
            failed_behaviors.append(behavior)
        elif check["status"] == "PASS":
            observed_behaviors.append(behavior)
        else:
            observed_behaviors.append(behavior)

    smoke_payload = smoketest_report_to_dict(smoketest_report) or validation_bundle.get("smoketest") or {}
    smoke_counts = summarize_smoketest_counts(smoke_payload)
    smoke_executed = smoke_counts["executed_count"]
    smoke_static = smoke_counts["static_count"]
    smoke_results = smoke_payload.get("results") if isinstance(smoke_payload.get("results"), list) else []
    executed_behavior_rows = 0
    if smoke_executed > 0:
        executed_kinds = {"executed", "process_boot", "http_probe", "ws_probe", "browser_probe"}
        for item in smoke_results:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).upper()
            if status == "SKIP":
                continue
            kind = normalize_smoketest_execution_kind(item.get("execution_kind"), bool(item.get("executed", False)))
            if kind not in executed_kinds:
                continue
            behavior = {
                "behavior_id": f"smoketest:{item.get('adapter', 'unknown')}:{item.get('name', 'check')}",
                "result": status.lower() if status else "unknown",
                "evidence_class": "direct_execution_evidence",
                "related_files": normalize_file_hints(item.get("related_files")),
            }
            executed_behavior_rows += 1
            if status in {"FAIL", "ERROR"}:
                failed_behaviors.append(behavior)
            elif status == "PASS":
                observed_behaviors.append(behavior)
        if executed_behavior_rows == 0:
            unverified_behaviors.append({
                "behavior_id": "smoketest_execution",
                "reason": "Smoketest reported executed evidence but no executed result rows were available.",
            })
    else:
        unverified_behaviors.append({
            "behavior_id": "smoketest_execution",
            "reason": "Smoketest checks were not executed for this cycle.",
        })
    if validation_bundle.get("coverage", {}).get("non_python_files"):
        unverified_behaviors.append({
            "behavior_id": "non_python_deterministic_validation_depth",
            "reason": "Non-Python ecosystems currently rely on weaker deterministic coverage than Python.",
        })

    evidence_status = "EVIDENCE_PARTIAL"
    if not changed_file_records:
        evidence_status = "EVIDENCE_MISSING"
    elif (
        validation_bundle.get("status") == "PASS"
        and validation_bundle.get("validation_execution_mode") in {"EXECUTED", "MIXED"}
        and not grouped_coherence["undeclared_changed_files"]
        and not unverified_behaviors
    ):
        evidence_status = "EVIDENCE_COMPLETE"

    confidence = "CONFIDENCE_HIGH"
    if validation_bundle.get("validation_execution_mode") == "NONE":
        confidence = "CONFIDENCE_LOW"
    elif (
        validation_bundle.get("status") != "PASS"
        or validation_bundle.get("coverage", {}).get("non_python_files")
        or grouped_coherence["undeclared_changed_files"]
    ):
        confidence = "CONFIDENCE_MEDIUM"

    intended_scopes = [
        item.get("scope_id")
        for item in build_groups_doc.get("items", [])
        if item.get("scope_id")
    ]
    unknowns = [
        "System impact telemetry is not collected in the current engine.",
    ]
    try:
        with open(worqspace_root / "config.yaml", "r", encoding="utf-8") as f:
            config_yaml = yaml.safe_load(f) or {}
    except Exception:
        config_yaml = {}
    fallback_write_mode = config_yaml.get("write_strategy", {}).get("mode", "staged_atomic_per_attempt")
    
    group_write_modes = sorted({group.get("write_strategy") for group in grouped_coherence["group_summaries"] if group.get("write_strategy")})
    if not group_write_modes:
        unknowns.append(f"No explicit scoped write strategy was recorded for the observed build groups; falling back to config intent '{fallback_write_mode}'.")
    if cross_briq_warnings:
        unknowns.append("Cross-briq integration points exist and require inspection judgment.")
    if smoke_executed == 0:
        if smoke_static > 0:
            unknowns.append("Smoketest evidence is static-only for this cycle; no executed smoke evidence was collected.")
        else:
            unknowns.append("No executed smoketest evidence was collected for this cycle.")

    return {
        "schema_version": "realization-bundle.v1",
        "realization_bundle_id": f"{canonical_run_id(worqspace_root)}-realization-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        "evidence_freshness": now_utc(),
        "source_provenance": f"{canonical_run_id(worqspace_root)}-inspeqtor-cyqle{cycle_num}",
        **execution_meta,
        "stage": "REALIZATION",
        "status": evidence_status,
        "capability_mode": "MIXED_REASONING_EXECUTION",
        "validation_execution_mode": validation_bundle.get("validation_execution_mode", "NONE"),
        "evidence_status": evidence_status,
        "confidence": confidence,
        "scope_summary": {
            "intended_scopes": sorted(set(intended_scopes)),
            "touched_scopes": grouped_coherence["touched_scope_ids"],
            "undeclared_touched_scopes": [
                f"file:{path}" for path in grouped_coherence["undeclared_changed_files"]
            ],
        },
        "structural_reality": {
            "changed_files": changed_file_records,
            "touched_components": sorted({
                component_id
                for group in grouped_coherence["group_summaries"]
                for component_id in group.get("planned_components", [])
            }),
            "artifact_changes": [
                {"artifact_type": "execution_summary", "path": f"exeq.d/cyqle{cycle_num}_summary.md"} if summary_path.exists() else None,
                {"artifact_type": "changed_manifest", "path": f"exeq.d/cyqle{cycle_num}_changed.md"} if changed_path.exists() else None,
                {"artifact_type": "validation_bundle", "path": "validation/validation-bundle.v1.json"},
            ],
        },
        "behavioral_reality": {
            "observed_behaviors": observed_behaviors,
            "failed_behaviors": failed_behaviors,
            "unverified_behaviors": unverified_behaviors,
            "interface_behavior_deltas": [],
        },
        "system_impact_reality": {
            "performance": {"status": "unknown", "reason": "No benchmark evidence collected."},
            "stability": {"status": "unknown", "reason": "No long-running runtime telemetry collected."},
            "resource_usage": {"status": "unknown", "reason": "No resource telemetry collected."},
            "error_signals": [],
        },
        "unknowns": unknowns,
        "write_strategy": {
            "mode": group_write_modes[0] if len(group_write_modes) == 1 else ("mixed" if len(group_write_modes) > 1 else fallback_write_mode),
            "group_modes": group_write_modes,
            "recovery_policies": sorted({group.get("recovery_policy") for group in grouped_coherence["group_summaries"] if group.get("recovery_policy")}),
            "recovery_refs": sorted({
                ref
                for group in grouped_coherence["group_summaries"]
                for ref in group.get("recovery_refs", [])
            }),
            "attempt_manifest_refs": sorted({
                ref
                for group in grouped_coherence["group_summaries"]
                for ref in group.get("attempt_manifest_refs", [])
            }),
        },
        "execution_backend": {
            "engines": [
                group.get("execution_backend")
                for group in grouped_coherence["group_summaries"]
                if group.get("execution_backend")
            ],
            "authority_disclosure": "Execution backends operate as scoped build engines; orchestration and manifest authority remain with QonQrete runtime contracts.",
        },
        "evidence_refs": [
            f"exeq.d/cyqle{cycle_num}_summary.md" if summary_path.exists() else None,
            f"exeq.d/cyqle{cycle_num}_changed.md" if changed_path.exists() else None,
            "validation/validation-bundle.v1.json",
        ] + [
            f"build/groups/{group['build_group_id']}/build-report.v1.json"
            for group in grouped_coherence["group_summaries"]
        ] + [
            f"build/groups/{group['build_group_id']}/changed-files.v1.json"
            for group in grouped_coherence["group_summaries"]
        ] + [
            ref
            for group in grouped_coherence["group_summaries"]
            for ref in group.get("recovery_refs", [])
        ] + [
            ref
            for group in grouped_coherence["group_summaries"]
            for ref in group.get("attempt_manifest_refs", [])
        ],
        "source_build_refs": [
            f"build/groups/{group['build_group_id']}/build-report.v1.json"
            for group in grouped_coherence["group_summaries"]
        ],
        "source_validation_refs": ["validation/validation-bundle.v1.json"],
        "manifest_ref": "run-manifest.v1.json",
        "created_at": now_utc(),
    }


def build_inspection_input_contract(
    worqspace_root: Path,
    cycle_num: str,
    validation_bundle: dict,
    realization_bundle: dict,
) -> dict:
    execution_meta = resolve_execution_metadata(cycle_num)
    completion_criteria = load_optional_json(worqspace_root / "planning" / "completion-criteria.v1.json")
    execution_blueprint = load_optional_json(worqspace_root / "planning" / "execution-blueprint.v1.json")
    status = "READY"
    missing = []
    if not validation_bundle:
        missing.append("validation/validation-bundle.v1.json")
    if not realization_bundle:
        missing.append("realization/realization-bundle.v1.json")
    if not completion_criteria:
        missing.append("planning/completion-criteria.v1.json")
    if missing:
        status = "BLOCKED"

    return {
        "schema_version": "inspection-input.v1",
        "inspection_input_id": f"{canonical_run_id(worqspace_root)}-inspection-input-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        **execution_meta,
        "stage": "INSPECTION",
        "status": status,
        "required_inputs": {
            "validation_bundle_ref": "validation/validation-bundle.v1.json",
            "realization_bundle_ref": "realization/realization-bundle.v1.json",
            "completion_criteria_ref": "planning/completion-criteria.v1.json",
            "execution_blueprint_ref": "planning/execution-blueprint.v1.json" if execution_blueprint else None,
        },
        "missing_inputs": missing,
        "capability_mode": realization_bundle.get("capability_mode", "MIXED_REASONING_EXECUTION") if realization_bundle else "MIXED_REASONING_EXECUTION",
        "validation_execution_mode": validation_bundle.get("validation_execution_mode", "NONE") if validation_bundle else "NONE",
        "created_at": now_utc(),
    }


def task_declares_exact_required_file_set(worqspace_root: Path) -> bool:
    task_spec = load_optional_json(worqspace_root / "task" / "task-spec.v1.json")
    text_candidates: list[str] = []
    if isinstance(task_spec, dict):
        for key in (
            "clarified_task_body",
            "goal",
            "summary",
            "clarification_summary",
            "original_task",
            "task",
        ):
            value = task_spec.get(key)
            if isinstance(value, str):
                text_candidates.append(value)
        metadata = task_spec.get("metadata")
        if isinstance(metadata, dict):
            for value in metadata.values():
                if isinstance(value, str):
                    text_candidates.append(value)

    for path in (
        worqspace_root / "tasq.md",
        worqspace_root / "task" / "task.md",
        worqspace_root / "task" / "task_input.md",
    ):
        if not path.exists():
            continue
        try:
            text_candidates.append(path.read_text(encoding="utf-8"))
        except Exception:
            continue

    for text in text_candidates:
        lower = text.lower()
        if "must contain exactly these files" in lower:
            return True
        if "project must contain exactly these files" in lower:
            return True
        if "no extra files" in lower and "required files" in lower:
            return True
    return False


def list_qodeyard_files_for_completion_check(worqspace_root: Path) -> list[str]:
    qodeyard = worqspace_root / "qodeyard"
    if not qodeyard.is_dir():
        return []
    discovered: list[str] = []
    for path in sorted(qodeyard.rglob("*")):
        if not path.is_file():
            continue
        rel_path = str(path.relative_to(qodeyard)).replace("\\", "/")
        if not rel_path:
            continue
        if any(part.startswith(".") for part in Path(rel_path).parts):
            continue
        if Path(rel_path).name.lower() == ".ds_store":
            continue
        discovered.append(rel_path)
    return discovered


def build_inspection_verdict(
    worqspace_root: Path,
    cycle_num: str,
    overall_assessment: str,
    validation_bundle: dict,
    realization_bundle: dict,
    inspection_input: dict,
    cross_briq_warnings: list[str],
    failed_briq_suggestions: list[dict],
    inspection_substep_failures: list[dict] | None = None,
) -> dict:
    completion_criteria = load_optional_json(worqspace_root / "planning" / "completion-criteria.v1.json")
    build_groups_doc = load_optional_json(worqspace_root / "planning" / "build-groups.v1.json")

    criteria_results = []
    planning_paths = [
        worqspace_root / "planning" / "execution-blueprint.v1.json",
        worqspace_root / "planning" / "validation-plan.v1.json",
        worqspace_root / "planning" / "completion-criteria.v1.json",
        worqspace_root / "planning" / "build-groups.v1.json",
    ]
    planning_ok = all(path.exists() for path in planning_paths)
    criteria_results.append({
        "criterion": "Required planning artifacts exist and are manifest-linkable.",
        "status": "PASS" if planning_ok else "FAIL",
        "basis": [str(path.relative_to(worqspace_root)) for path in planning_paths],
    })

    expected_briqs = [
        item.get("briq_ref")
        for item in build_groups_doc.get("briq_inventory", [])
        if item.get("briq_ref")
    ]
    assigned_briqs = sorted({
        briq_ref
        for item in build_groups_doc.get("items", [])
        for briq_ref in item.get("briq_refs", [])
    })
    assignment_ok = sorted(expected_briqs) == assigned_briqs
    criteria_results.append({
        "criterion": "Every briq is assigned to a build group and component scope.",
        "status": "PASS" if assignment_ok else "FAIL",
        "basis": {
            "expected_briqs": expected_briqs,
            "assigned_briqs": assigned_briqs,
        },
    })

    grouped_outputs = realization_bundle.get("scope_summary", {}).get("touched_scopes", [])
    build_scope_ok = bool(grouped_outputs) and not realization_bundle.get("scope_summary", {}).get("undeclared_touched_scopes", [])
    criteria_results.append({
        "criterion": "ConstruQtor consumes grouped scope metadata during build.",
        "status": "PASS" if build_scope_ok else "PARTIAL",
        "basis": {
            "touched_scopes": grouped_outputs,
            "undeclared_touched_scopes": realization_bundle.get("scope_summary", {}).get("undeclared_touched_scopes", []),
        },
    })

    criteria_results.append({
        "criterion": "Inspection consumed validation and realization bundles before verdict.",
        "status": "PASS" if inspection_input.get("status") == "READY" else "FAIL",
        "basis": inspection_input.get("required_inputs", {}),
    })

    required_files = [
        str(item).strip().replace("\\", "/")
        for item in completion_criteria.get("required_files", [])
        if str(item).strip()
    ]
    if required_files:
        missing_required_files = [
            rel_path
            for rel_path in required_files
            if not (worqspace_root / "qodeyard" / rel_path).exists()
        ]
        criteria_results.append({
            "criterion": "Required deliverable files exist in qodeyard.",
            "status": "PASS" if not missing_required_files else "FAIL",
            "basis": {
                "required_files": required_files,
                "missing_required_files": missing_required_files,
            },
        })
        if task_declares_exact_required_file_set(worqspace_root):
            present_files = list_qodeyard_files_for_completion_check(worqspace_root)
            extra_files = sorted(set(present_files) - set(required_files))
            criteria_results.append({
                "criterion": "Required file set is exact (no undeclared extra deliverable files).",
                "status": "PASS" if not extra_files and not missing_required_files else "FAIL",
                "basis": {
                    "required_files": required_files,
                    "present_files": present_files,
                    "extra_files": extra_files,
                    "missing_required_files": missing_required_files,
                },
            })

    # v1.3.13: Filter out invalidated issues using fingerprint check.
    # An issue is invalidated if the file it refers to has changed since the evidence was collected.
    raw_issues = validation_bundle.get("issues", [])
    valid_issues = []
    invalidated_issues = []
    for issue in raw_issues:
        rel_file = issue.get("file")
        stored_hash = issue.get("file_hash")
        if rel_file and stored_hash:
            current_hash = sha256_file(worqspace_root / "qodeyard" / rel_file)
            if current_hash != stored_hash:
                print(f"    [STALE] Invalidating issue on {rel_file}: file hash changed ({stored_hash[:8]} -> {current_hash[:8]})", flush=True)
                issue["status"] = "INVALIDATED"
                issue["invalidation_reason"] = "file_hash_changed"
                invalidated_issues.append(issue)
                continue
        valid_issues.append(issue)

    deterministic_failures = [
        issue for issue in valid_issues
        if issue.get("severity") == "error"
    ]
    
    # v1.3.9: Distinguish code defects from validator-environment defects
    blocking_code_failures = [
        issue for issue in deterministic_failures
        if issue.get("failure_kind") in {"blocking_code_failures", None} 
        and not issue.get("environment_blocked", False)
    ]
    dependency_declaration_failures = [
        issue for issue in deterministic_failures
        if issue.get("failure_kind") == "dependency_declaration_failures"
    ]
    environment_blockers = [
        issue for issue in deterministic_failures
        if issue.get("environment_blocked", True) or issue.get("failure_kind") == "environment_dependency_missing"
    ]
    tooling_missing = [
        issue for issue in deterministic_failures
        if issue.get("failure_kind") == "tooling_missing"
    ]
    validator_degraded = [
        issue for issue in deterministic_failures
        if issue.get("failure_kind") == "validator_degraded"
    ]
    
    validation_status = normalize_tri_state_status(validation_bundle.get("status"), default="FAIL")
    explicit_evidence_status = str(realization_bundle.get("evidence_status") or "").strip().upper()
    criteria_failures = any(item["status"] == "FAIL" for item in criteria_results)

    if blocking_code_failures or validation_status == "FAIL":
        verdict = "FAILURE"
    elif dependency_declaration_failures:
        verdict = "FAILURE" # Dependency declaration is still a project defect
    elif environment_blockers or tooling_missing or validator_degraded:
        verdict = "ENVIRONMENT_BLOCKED"
    elif criteria_failures:
        verdict = "PARTIAL"
    elif explicit_evidence_status and explicit_evidence_status != "EVIDENCE_COMPLETE":
        verdict = "PARTIAL"
    else:
        # Deterministic validation + completion criteria are the authoritative
        # gate for completion. AI tactical/meta review remains advisory.
        verdict = "SUCCESS"

    confidence = realization_bundle.get("confidence", "CONFIDENCE_LOW")
    unresolved_issues = []
    unresolved_issues.extend([issue.get("message") for issue in deterministic_failures])
    unresolved_issues.extend(realization_bundle.get("unknowns", []))
    if explicit_evidence_status and explicit_evidence_status != "EVIDENCE_COMPLETE":
        unresolved_issues.append(
            f"Evidence status remains {explicit_evidence_status}; success cannot be treated as fully verified yet."
        )
    if verdict != "SUCCESS":
        unresolved_issues.extend(cross_briq_warnings)
        unresolved_issues.extend(
            f"{item['briq']} {item['assessment']}: {item['suggestions'][:240]}"
            for item in failed_briq_suggestions
        )

    structured_issues = []
    for index, issue in enumerate(deterministic_failures, start=1):
        structured_issues.append({
            "issue_id": f"deterministic-{index:03d}",
            "summary": issue.get("message", "Deterministic validation failure."),
            "severity": issue.get("severity", "error"),
            "source": issue.get("source"),
            "file": issue.get("file"),
            "line": issue.get("line"),
            "failure_kind": issue.get("failure_kind"),
            "missing_module": issue.get("missing_module"),
            "environment_blocked": bool(issue.get("environment_blocked", False)),
        })
    for index, warning in enumerate(cross_briq_warnings, start=1):
        structured_issues.append({
            "issue_id": f"cross-briq-{index:03d}",
            "summary": warning,
            "severity": "warning",
            "source": "cross_briq_consistency",
        })
    for index, item in enumerate(failed_briq_suggestions, start=1):
        advisory_severity = "info" if verdict == "SUCCESS" else "warning"
        structured_issues.append({
            "issue_id": f"briq-review-{index:03d}",
            "summary": f"{item['briq']} {item['assessment']}: {item['suggestions'][:240]}",
            "severity": advisory_severity,
            "source": "briq_review",
            "briq_ref": item["briq"],
        })
    for index, failure in enumerate(inspection_substep_failures or [], start=1):
        structured_issues.append({
            "issue_id": f"inspection-runtime-{index:03d}",
            "summary": f"{failure.get('substep')}: {failure.get('error')}",
            "severity": "warning" if failure.get("recoverable", True) else "error",
            "source": "inspection_runtime",
            "recoverable": bool(failure.get("recoverable", True)),
        })

    if verdict == "SUCCESS":
        completion_assessment = "Observed build, validation, and realization evidence satisfy the current completion criteria."
        next_transition = "COMPLETED"
    elif blocking_code_failures:
        completion_assessment = "Deterministic code defects block completion and require bounded repair."
        next_transition = "REPAIRING"
    elif dependency_declaration_failures:
        completion_assessment = "Missing or incorrect dependency declarations block completion; project manifests require repair."
        next_transition = "REPAIRING"
    elif environment_blockers or tooling_missing or validator_degraded:
        completion_assessment = "Validation is blocked by environment or missing tooling; validator state is DEGRADED/BLOCKED."
        next_transition = "REPAIRING"
    else:
        completion_assessment = "Planned scope is partially realized, but unresolved gaps require bounded evidence-linked repair before completion."
        next_transition = "REPAIRING"

    for issue in invalidated_issues:
        structured_issues.append({
            "issue_id": f"stale-{issue.get('file', 'unknown')}",
            "summary": f"[STALE/INVALIDATED] {issue.get('message', 'Old issue')}",
            "severity": "info",
            "status": "INVALIDATED",
            "file": issue.get("file"),
        })

    execution_meta = resolve_execution_metadata(cycle_num)
    return {
        "schema_version": "inspection-verdict.v1",
        "inspection_verdict_id": f"{canonical_run_id(worqspace_root)}-inspection-verdict-cyqle{cycle_num}",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        "stage": "INSPECTION",
        "status": verdict,
        "deterministic_gate": "FAIL" if deterministic_failures else "PASS",
        "completion_criteria_results": criteria_results,
        "completion_criteria_summary": completion_criteria.get("summary"),
        "confidence": confidence,
        "evidence_status": realization_bundle.get("evidence_status", "EVIDENCE_PARTIAL"),
        "validation_execution_mode": validation_bundle.get("validation_execution_mode", "NONE"),
        "capability_mode": realization_bundle.get("capability_mode", "MIXED_REASONING_EXECUTION"),
        "issues": structured_issues,
        "repair_required": verdict != "SUCCESS",
        "task_completed": verdict == "SUCCESS",
        "completion_assessment": completion_assessment,
        "next_lifecycle_transition": next_transition,
        "repair_plan_ref": None,
        "unresolved_issues": unresolved_issues,
        "inspection_integrity": "DEGRADED" if inspection_substep_failures else "COMPLETE",
        "inspection_substep_failures": inspection_substep_failures or [],
        "evidence_freshness": now_utc(),
        "source_provenance": f"{canonical_run_id(worqspace_root)}-inspeqtor-cyqle{cycle_num}",
        "evidence_refs": [
            "validation/validation-bundle.v1.json",
            "realization/realization-bundle.v1.json",
            "verdict/inspection-input.v1.json",
            "planning/completion-criteria.v1.json",
        ],
        "created_at": now_utc(),
        **execution_meta,
    }


def build_repair_plan(
    worqspace_root: Path,
    cycle_num: str,
    inspection_verdict: dict,
    validation_bundle: dict,
    realization_bundle: dict,
    grouped_coherence: dict,
    failed_briq_suggestions: list[dict],
) -> dict:
    build_groups_doc = load_optional_json(worqspace_root / "planning" / "build-groups.v1.json")
    failure_class, failure_reason = classify_repair_failure_for_plan(inspection_verdict, validation_bundle)
    recommended_start_level = recommend_repair_start_level_for_failure_class(failure_class)

    def _is_deterministic_issue(issue: dict) -> bool:
        issue_id = str(issue.get("issue_id", "") or "")
        source = str(issue.get("source", "") or "").strip().lower()
        if issue_id.startswith("deterministic-"):
            return True
        return source in {
            "qonfirmer",
            "qualification",
            "qualifier",
            "smoketest",
            "grouped_component_coherence",
            "validation",
        }

    deterministic_errors_present = any(
        _is_deterministic_issue(issue)
        and str(issue.get("severity", "")).lower() == "error"
        for issue in inspection_verdict.get("issues", [])
    )
    # When deterministic blockers exist, they remain the repair authority.
    enforce_briq_review_targets = not deterministic_errors_present
    
    # v1.3.13: Precise repair targeting
    target_files_set = set()
    target_criteria_ids = []
    
    # Extract targets from criteria results
    for item in inspection_verdict.get("completion_criteria_results", []):
        if item.get("status") == "FAIL":
            basis = item.get("basis") or {}
            if isinstance(basis, dict):
                missing = basis.get("missing_required_files", [])
                target_files_set.update(missing)
            target_criteria_ids.append(item.get("criterion_id", item.get("criterion")))

    # Extract targets from verdict issues
    for issue in inspection_verdict.get("issues", []):
        if str(issue.get("severity", "")).lower() == "error":
            for f in normalize_file_hints(issue.get("file")):
                target_files_set.add(f)
            for f in normalize_file_hints(issue.get("files")):
                target_files_set.add(f)

    # Extract targets from validation issues
    for issue in validation_bundle.get("issues", []):
        if issue.get("severity") == "error":
            f = issue.get("file")
            if f:
                target_files_set.add(f)
            fs = issue.get("files") or []
            if isinstance(fs, list):
                target_files_set.update(fs)
    
    target_files = sorted(list(target_files_set))

    deterministic_repair_issues: list[dict] = []
    for issue in inspection_verdict.get("issues", []):
        if _is_deterministic_issue(issue) and str(issue.get("severity", "")).lower() == "error":
            deterministic_repair_issues.append(issue)
    for issue in validation_bundle.get("issues", []):
        if str(issue.get("severity", "")).lower() != "error":
            continue
        deterministic_repair_issues.append({
            "source": issue.get("source") or "validation",
            "severity": issue.get("severity") or "error",
            "message": issue.get("message") or issue.get("summary") or "",
            "file": issue.get("file"),
            "files": issue.get("files"),
            "related_files": issue.get("related_files"),
            "scope": issue.get("scope"),
            "build_group_id": issue.get("build_group_id"),
            "check_type": issue.get("check_type") or issue.get("issue_id"),
        })

    # v1.3.13: Determine repair_scope_mode
    repair_scope_mode = "broad"
    if failure_class in {"collateral_churn_overrewrite", "transport_write_failure", "exact_validator_violation"}:
        repair_scope_mode = "surgical"
    elif failure_class in {"file_scoped_contract_miss", "runtime_syntax_launch_failure", "required_output_missing"}:
        repair_scope_mode = "file-scoped"
    
    build_group_items = build_groups_doc.get("items", [])
    briq_inventory = build_groups_doc.get("briq_inventory", [])
    briq_ref_to_file = {}
    for briq_path in sorted((worqspace_root / "briq.d").glob(f"cyqle{cycle_num}_*.md")):
        try:
            briq_text = briq_path.read_text(encoding="utf-8")
        except Exception:
            continue
        match = re.search(r"^Briq-Ref:\s*(.+)$", briq_text, re.MULTILINE)
        if match:
            briq_ref_to_file[match.group(1).strip()] = briq_path.name

    briq_to_group = {}
    group_to_briqs = {}
    group_to_scope = {}
    group_to_components = {}
    file_to_groups = {}
    scope_to_groups: dict[str, set[str]] = {}
    basename_to_groups: dict[str, set[str]] = {}

    for item in build_group_items:
        group_id = item.get("build_group_id")
        if not group_id:
            continue
        group_to_briqs[group_id] = sorted(item.get("briq_refs", []))
        group_to_scope[group_id] = item.get("scope_id")
        if item.get("scope_id"):
            scope_to_groups.setdefault(item.get("scope_id"), set()).add(group_id)
        group_to_components[group_id] = sorted(item.get("component_refs", []))
        for briq_ref in item.get("briq_refs", []):
            briq_to_group[briq_ref] = group_id

    for group in grouped_coherence.get("group_summaries", []):
        group_id = group.get("build_group_id")
        for path in group.get("changed_files", []):
            normalized = normalize_file_hint(path)
            if not normalized:
                continue
            file_to_groups.setdefault(normalized, set()).add(group_id)
            basename_to_groups.setdefault(Path(normalized).name, set()).add(group_id)
        for path in group.get("reported_files", []):
            normalized = normalize_file_hint(path)
            if not normalized:
                continue
            file_to_groups.setdefault(normalized, set()).add(group_id)
            basename_to_groups.setdefault(Path(normalized).name, set()).add(group_id)

    def _target_groups_for_path(path_hint: str | None) -> set[str]:
        normalized = normalize_file_hint(path_hint)
        if not normalized:
            return set()
        if normalized in file_to_groups:
            return set(file_to_groups[normalized])

        matched: set[str] = set()
        for path_key, groups in file_to_groups.items():
            if path_key.endswith(f"/{normalized}") or normalized.endswith(f"/{path_key}"):
                matched.update(groups)
        if matched:
            return matched

        basename = Path(normalized).name
        if basename in basename_to_groups:
            return set(basename_to_groups[basename])
        return set()

    file_ref_pattern = re.compile(r"\b[A-Za-z0-9_./-]+\.[A-Za-z0-9_+-]{1,8}\b")

    # Keep deterministic repairs tightly scoped. Broad grouped-coherence FAIL/PARTIAL
    # statuses can include stale/non-deterministic briq-review noise and cause
    # unnecessary scope expansion.
    if deterministic_errors_present:
        target_groups: set[str] = set()
    else:
        target_groups = {
            group.get("build_group_id")
            for group in grouped_coherence.get("group_summaries", [])
            if group.get("status") in {"FAIL", "PARTIAL"}
        }

    for issue in validation_bundle.get("issues", []):
        severity = str(issue.get("severity", "") or "").lower()
        if deterministic_errors_present and severity != "error":
            continue
        for file_path in normalize_file_hints(issue.get("file")):
            target_groups.update(_target_groups_for_path(file_path))
        for file_path in normalize_file_hints(issue.get("files")):
            target_groups.update(_target_groups_for_path(file_path))
        for file_path in normalize_file_hints(issue.get("related_files")):
            target_groups.update(_target_groups_for_path(file_path))
        scope = issue.get("scope")
        if scope and scope in group_to_briqs:
            target_groups.add(scope)
        if scope and scope in scope_to_groups:
            target_groups.update(scope_to_groups[scope])
        issue_group = issue.get("build_group_id")
        if issue_group and issue_group in group_to_briqs:
            target_groups.add(issue_group)

    deterministic_required_actions: list[str] = []
    for issue in inspection_verdict.get("issues", []):
        if not _is_deterministic_issue(issue):
            continue
        summary = " ".join(str(issue.get("summary", "")).split())
        if not summary:
            continue
        for file_path in normalize_file_hints(issue.get("file")):
            target_groups.update(_target_groups_for_path(file_path))
        for file_path in normalize_file_hints(issue.get("files")):
            target_groups.update(_target_groups_for_path(file_path))
        for file_path in normalize_file_hints(issue.get("related_files")):
            target_groups.update(_target_groups_for_path(file_path))
        for token in file_ref_pattern.findall(summary):
            target_groups.update(_target_groups_for_path(token))
        if str(issue.get("severity", "")).lower() == "error":
            deterministic_required_actions.append(f"resolve deterministic issue: {summary}")

    inventory_refs = {
        item.get("briq_ref")
        for item in briq_inventory
        if item.get("briq_ref")
    }
    if enforce_briq_review_targets:
        for item in failed_briq_suggestions:
            briq_ref = item.get("briq")
            if briq_ref in briq_to_group:
                target_groups.add(briq_to_group[briq_ref])
            elif briq_ref in inventory_refs:
                target_groups.add(briq_to_group.get(briq_ref))

    target_groups = sorted(group_id for group_id in target_groups if group_id)
    target_briqs = sorted({
        briq_ref
        for group_id in target_groups
        for briq_ref in group_to_briqs.get(group_id, [])
    })
    target_briq_files = sorted({
        briq_ref_to_file[briq_ref]
        for briq_ref in target_briqs
        if briq_ref in briq_ref_to_file
    })
    fallback_scope_files = derive_group_scope_files(
        worqspace_root,
        target_files=target_files,
        target_build_groups=target_groups,
        target_briq_refs=target_briqs,
    )
    if fallback_scope_files:
        target_files = sorted(set(target_files) | set(fallback_scope_files))
    target_scopes = sorted({
        group_to_scope.get(group_id)
        for group_id in target_groups
        if group_to_scope.get(group_id)
    })
    target_components = sorted({
        component_id
        for group_id in target_groups
        for component_id in group_to_components.get(group_id, [])
    })
    issue_fingerprints = build_issue_fingerprint_entries(deterministic_repair_issues)
    validation_scope_files = sorted(set(target_files or fallback_scope_files))

    same_run_eligible = bool(target_groups and target_briq_files)
    continuation_strategy = "same_run" if same_run_eligible else "linked_continuation"
    next_transition = "REPAIRING" if same_run_eligible else "CONTINUABLE"

    required_actions: list[str] = []
    for action in deterministic_required_actions:
        if action not in required_actions:
            required_actions.append(action)
    if any(check.get("status") == "FAIL" for check in validation_bundle.get("checks", [])):
        required_actions.append("correct deterministic validation failures in the targeted repair scope")
    if grouped_coherence.get("undeclared_changed_files"):
        required_actions.append("bring changed files back inside declared grouped scope or update targeted scope evidence")
    if enforce_briq_review_targets and failed_briq_suggestions:
        required_actions.append("address failed or partial briq findings for the targeted build groups")
    required_actions.append("re-run validation, realization, and inspection after the targeted repair pass")

    validation_requirements = []
    for check in validation_bundle.get("checks", []):
        if check.get("status") in {"FAIL", "PARTIAL"}:
            validation_requirements.append(check.get("check_id"))
    if not validation_requirements:
        validation_requirements.append("validation-bundle.v1 scoped re-run")

    execution_meta = resolve_execution_metadata(cycle_num)
    existing_pass_index = execution_meta["repair_pass_index"]
    repair_reason_summary = inspection_verdict.get("completion_assessment") or (
        "Inspection found unresolved gaps that require explicit bounded repair."
    )

    # v1.3.13: Persist repair escalation history
    prior_attempt_records = []
    # Collect from previous build reports in this cycle
    build_groups_dir = worqspace_root / "build" / "groups"
    if build_groups_dir.exists():
        for report_path in build_groups_dir.glob("**/build-report.v1.json"):
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                for record in report.get("attempt_records", []):
                    if record.get("failure_class") and record.get("failure_fingerprint"):
                        prior_attempt_records.append({
                            "failure_class": record["failure_class"],
                            "failure_fingerprint": record["failure_fingerprint"],
                        })
            except Exception:
                continue

    # Also collect from previous repair plan if it exists
    prev_repair_plan_path = worqspace_root / "verdict" / "repair-plan.v1.json"
    if prev_repair_plan_path.exists():
        try:
            prev_rp = json.loads(prev_repair_plan_path.read_text(encoding="utf-8"))
            prev_records = prev_rp.get("repair_escalation", {}).get("prior_attempt_records", [])
            if isinstance(prev_records, list):
                for rec in prev_records:
                    if rec not in prior_attempt_records:
                        prior_attempt_records.append(rec)
        except Exception:
            pass

    return {
        "schema_version": "repair-plan.v1",
        "repair_plan_id": f"{canonical_run_id(worqspace_root)}-repair-plan-cyqle{cycle_num}",
        "source_run_id": canonical_run_id(worqspace_root),
        "source_cycle": int(cycle_num),
        "source_global_iteration_index": execution_meta["global_iteration_index"],
        "source_pass_kind": execution_meta["pass_kind"],
        "source_build_pass_index": execution_meta["build_pass_index"],
        "source_repair_pass_index": existing_pass_index,
        "repairing_build_pass_index": execution_meta["repairing_build_pass_index"],
        "source_cycle_estimate_mode": execution_meta["cycle_estimate_mode"],
        "source_estimated_build_passes": execution_meta["estimated_build_passes"],
        "source_scheduled_build_pass_target": execution_meta["scheduled_build_pass_target"],
        "source_verdict_ref": "verdict/inspection-verdict.v1.json",
        "repair_reason_summary": repair_reason_summary,
        "repair_scope_mode": repair_scope_mode,
        "target_components": target_components,
        "target_scopes": target_scopes,
        "target_build_groups": target_groups,
        "target_briq_refs": target_briqs,
        "target_briq_files": target_briq_files,
        "target_files": target_files,
        "validation_scope_files": validation_scope_files,
        "allowed_edit_paths": target_files,
        "issue_fingerprints": issue_fingerprints,
        "target_criteria_ids": target_criteria_ids,
        "recommended_start_level": recommended_start_level,
        "failure_class": failure_class,
        "required_actions": required_actions,
        "planning_reuse_mode": "reuse_locked_plan",
        "repair_pass_index": existing_pass_index + 1,
        "repair_constraints": [
            "no architecture mutation",
            "no scope expansion",
            "repair must stay within manifest-linked target groups and briqs",
        ],
        "validation_requirements_for_repair": validation_requirements,
        "same_run_repair_eligible": same_run_eligible,
        "continuation_strategy": continuation_strategy,
        "next_lifecycle_transition": next_transition,
        "repair_status": "REPAIR_PROPOSED",
        "manifest_refs": ["run-manifest.v1.json"],
        "evidence_refs": [
            "validation/validation-bundle.v1.json",
            "realization/realization-bundle.v1.json",
            "verdict/inspection-verdict.v1.json",
        ],
        "repair_required_semantics": "explicit_bounded_manifest_linked",
        "repair_escalation": {
            "enabled": True,
            "recommended_failure_class": failure_class,
            "recommended_start_level": recommended_start_level,
            "reason": failure_reason,
            "prior_attempt_records": prior_attempt_records,
        },
        "created_at": now_utc(),
    }


def render_repair_plan_summary(repair_plan: dict) -> str:
    lines = [
        "# Repair Plan",
        "",
        f"- Source Global Iteration: {repair_plan.get('source_global_iteration_index')}",
        f"- Source Pass Kind: {repair_plan.get('source_pass_kind')}",
        f"- Source Build Pass: {repair_plan.get('source_build_pass_index')}",
        f"- Source Repair Pass: {repair_plan.get('source_repair_pass_index')}",
        f"- Source Estimate Mode: {repair_plan.get('source_cycle_estimate_mode')}",
        f"- Source Estimated Build Passes: {repair_plan.get('source_estimated_build_passes')}",
        f"- Source Scheduled Build Target: {repair_plan.get('source_scheduled_build_pass_target')}",
        f"- Repair Pass Index: {repair_plan['repair_pass_index']}",
        f"- Continuation Strategy: {repair_plan['continuation_strategy']}",
        f"- Same-Run Eligible: {repair_plan['same_run_repair_eligible']}",
        f"- Next Lifecycle Transition: {repair_plan['next_lifecycle_transition']}",
        "",
        "## Target Scope",
        f"- Build Groups: {', '.join(repair_plan.get('target_build_groups', [])) or 'None'}",
        f"- Components: {', '.join(repair_plan.get('target_components', [])) or 'None'}",
        f"- Scopes: {', '.join(repair_plan.get('target_scopes', [])) or 'None'}",
        f"- Briqs: {', '.join(repair_plan.get('target_briq_files', [])) or 'None'}",
        f"- Target Files: {', '.join(repair_plan.get('target_files', [])) or 'None'}",
        f"- Validation Scope Files: {', '.join(repair_plan.get('validation_scope_files', [])) or 'None'}",
        "",
        "## Required Actions",
    ]
    for item in repair_plan.get("required_actions", []):
        lines.append(f"- {item}")
    issue_fingerprints = repair_plan.get("issue_fingerprints", [])
    if issue_fingerprints:
        lines.extend(["", "## Issue Fingerprints"])
        for item in issue_fingerprints:
            summary = str(item.get("summary") or item.get("fingerprint") or "").strip()
            if summary:
                lines.append(f"- {summary}")
    escalation = repair_plan.get("repair_escalation", {})
    if isinstance(escalation, dict) and escalation:
        lines.extend([
            "",
            "## Repair Escalation",
            f"- Enabled: {bool(escalation.get('enabled', True))}",
            f"- Recommended Failure Class: {escalation.get('recommended_failure_class', 'broad_task_shape_miss')}",
            f"- Recommended Start Level: {escalation.get('recommended_start_level', 1)}",
            f"- Reason: {escalation.get('reason', 'n/a')}",
        ])
    lines.extend(["", "## Evidence References"])
    for item in repair_plan.get("evidence_refs", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_validation_summary(validation_bundle: dict) -> str:
    lines = [
        "# Validation Summary",
        "",
        f"- Status: {validation_bundle['status']}",
        f"- Global Iteration: {validation_bundle.get('global_iteration_index')}",
        f"- Pass Kind: {validation_bundle.get('pass_kind')}",
        f"- Build Pass: {validation_bundle.get('build_pass_index')}",
        f"- Repair Pass: {validation_bundle.get('repair_pass_index')}",
        f"- Repairing Build Pass: {validation_bundle.get('repairing_build_pass_index')}",
        f"- Estimate Mode: {validation_bundle.get('cycle_estimate_mode')}",
        f"- Estimated Build Passes: {validation_bundle.get('estimated_build_passes')}",
        f"- Scheduled Build Target: {validation_bundle.get('scheduled_build_pass_target')}",
        f"- Mode: {validation_bundle['validation_execution_mode']}",
        f"- Capability: {validation_bundle['capability_disclosure']['deterministic_validation_strength']}",
        "",
        "## Checks",
    ]
    for check in validation_bundle.get("checks", []):
        lines.append(f"- {check['check_id']}: {check['status']}")
    lines.extend(["", "## Capability Notes"])
    for note in validation_bundle.get("capability_disclosure", {}).get("notes", []):
        lines.append(f"- {note}")
    if validation_bundle.get("unknowns"):
        lines.extend(["", "## Unknowns"])
        for item in validation_bundle["unknowns"]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_realization_summary(realization_bundle: dict) -> str:
    lines = [
        "# Realization Summary",
        "",
        f"- Global Iteration: {realization_bundle.get('global_iteration_index')}",
        f"- Pass Kind: {realization_bundle.get('pass_kind')}",
        f"- Build Pass: {realization_bundle.get('build_pass_index')}",
        f"- Repair Pass: {realization_bundle.get('repair_pass_index')}",
        f"- Repairing Build Pass: {realization_bundle.get('repairing_build_pass_index')}",
        f"- Estimate Mode: {realization_bundle.get('cycle_estimate_mode')}",
        f"- Estimated Build Passes: {realization_bundle.get('estimated_build_passes')}",
        f"- Scheduled Build Target: {realization_bundle.get('scheduled_build_pass_target')}",
        f"- Evidence Status: {realization_bundle['evidence_status']}",
        f"- Confidence: {realization_bundle['confidence']}",
        f"- Write Strategy: {realization_bundle.get('write_strategy', {}).get('mode', 'unknown')}",
        "",
        "## Scope Summary",
        f"- Intended Scopes: {', '.join(realization_bundle['scope_summary']['intended_scopes']) or 'None'}",
        f"- Touched Scopes: {', '.join(realization_bundle['scope_summary']['touched_scopes']) or 'None'}",
        f"- Undeclared Scope Touches: {', '.join(realization_bundle['scope_summary']['undeclared_touched_scopes']) or 'None'}",
        "",
        "## Changed Files",
    ]
    for item in realization_bundle.get("structural_reality", {}).get("changed_files", []):
        lines.append(f"- `{item['path']}` ({'in-scope' if item['in_intended_scope'] else 'undeclared'})")
    if realization_bundle.get("unknowns"):
        lines.extend(["", "## Unknowns"])
        for item in realization_bundle["unknowns"]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_inspection_verdict_summary(verdict: dict) -> str:
    lines = [
        "# Inspection Verdict",
        "",
        f"- Status: {verdict['status']}",
        f"- Global Iteration: {verdict.get('global_iteration_index')}",
        f"- Pass Kind: {verdict.get('pass_kind')}",
        f"- Build Pass: {verdict.get('build_pass_index')}",
        f"- Repair Pass: {verdict.get('repair_pass_index')}",
        f"- Repairing Build Pass: {verdict.get('repairing_build_pass_index')}",
        f"- Estimate Mode: {verdict.get('cycle_estimate_mode')}",
        f"- Estimated Build Passes: {verdict.get('estimated_build_passes')}",
        f"- Scheduled Build Target: {verdict.get('scheduled_build_pass_target')}",
        f"- Deterministic Gate: {verdict['deterministic_gate']}",
        f"- Confidence: {verdict['confidence']}",
        f"- Evidence Status: {verdict['evidence_status']}",
        "",
        "## Completion Criteria",
    ]
    for item in verdict.get("completion_criteria_results", []):
        lines.append(f"- {item['status']}: {item['criterion']}")
    if verdict.get("unresolved_issues"):
        lines.extend(["", "## Unresolved Issues"])
        for item in verdict["unresolved_issues"][:20]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


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
    result['provider'], result['model'] = lib_ai.get_agent_ai_params(config, 'inspeqtor', 'venice', 'deepseek-v3.2')
    result['use_qontextor'] = config.get('options', {}).get('use_qontextor', True)
    
    return result


def load_full_config(config_path: Path) -> dict:
    """Load the full, unflattened repo config tree.

    ``load_inspeqtor_config`` above intentionally flattens the yaml to an
    agent-specific kwarg dict for InspeQtor's own tuning knobs. That
    flattening throws away top-level sections like ``verification``,
    ``interleaved``, ``retry``, ``repair`` and ``options`` and nested
    blocks like ``agents.inspeqtor.smoketest`` — which deterministic
    validators need to honour.

    This helper returns the raw yaml tree so downstream deterministic
    validators see the real config. Missing / unreadable files yield an
    empty dict — callers are expected to tolerate that.
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def extract_changed_files(changed_files_content: str, qodeyard_path: Path) -> list[tuple[str, str]]:
    """
    Extract list of changed files and their contents from the changed files manifest.
    
    Returns:
        List of (filename, content) tuples
    """
    changed_files = []
    for line in changed_files_content.splitlines():
        match = re.match(r'^\s*-\s+`([^`]+)`\s*$', line)
        if match:
            changed_files.append(match.group(1))
    result = []
    seen_files = set()

    for file_str in changed_files:
        if file_str in seen_files:
            continue
        seen_files.add(file_str)
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


def load_changed_code_artifacts(exeq_dir: Path, cycle_num: str, qodeyard_path: Path) -> list[tuple[str, str]]:
    """Load changed code artifacts for a cycle from exeq and grouped build manifests."""
    changed_files_in_order: list[str] = []
    seen_files: set[str] = set()

    def record_file(rel_path: str) -> None:
        if not rel_path or rel_path in seen_files:
            return
        seen_files.add(rel_path)
        changed_files_in_order.append(rel_path)

    changed_manifest_path = exeq_dir / f"cyqle{cycle_num}_changed.md"
    try:
        with open(changed_manifest_path, 'r', encoding='utf-8') as f:
            changed_manifest = f.read()
        for rel_path, _ in extract_changed_files(changed_manifest, qodeyard_path):
            record_file(rel_path)
    except Exception:
        pass

    build_groups_dir = exeq_dir.parent / "build" / "groups"
    if build_groups_dir.is_dir():
        for manifest_path in sorted(build_groups_dir.glob("*/changed-files.v1.json")):
            try:
                manifest = load_optional_json(manifest_path)
                for item in manifest.get("changed_files", []):
                    record_file(item.get("path", ""))
            except Exception:
                continue

    result = []
    for file_str in changed_files_in_order:
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


def normalize_review_result(
    assessment: str,
    summary: str,
    issues: str,
    changed_files: list[tuple[str, str]],
) -> tuple[str, str, str]:
    """
    Remove file-missing claims that contradict deterministic qodeyard evidence.

    AI review remains advisory, but it should not downgrade a briq for claiming an
    embedded changed file is missing when the deterministic artifact loader already
    confirmed that file exists in qodeyard.
    """
    content_by_file = {
        filename.lower(): content
        for filename, content in changed_files
        if content != "[File not found in qodeyard]"
    }
    evidence_files = set(content_by_file)
    if not evidence_files:
        return assessment, summary, issues

    run_sh_content = content_by_file.get("run.sh", "")
    run_sh_lower = run_sh_content.lower()
    run_sh_uses_port_var = bool(re.search(r'(\$port|\$\{port[:}]|"\$port"|\'\$PORT\')', run_sh_lower))
    run_sh_exports_port = "export port" in run_sh_lower or ": \"${port:=" in run_sh_lower
    run_sh_has_hardcoded_port = bool(
        re.search(r'--port\s+[0-9]+', run_sh_lower)
        or re.search(r'port\s*=\s*[0-9]+', run_sh_lower)
    )

    truncation_terms = (
        "truncat",
        "incomplete",
        "unfinished",
        "cut off",
        "cutoff",
        "abrupt",
        "ends early",
        "ends before",
    )

    def _line_mentions_file(line_lower: str, filename: str) -> bool:
        if filename in line_lower:
            return True
        basename = Path(filename).name.lower()
        if basename and basename in line_lower:
            return True
        if basename.endswith(".js") and ("javascript" in line_lower or "js file" in line_lower):
            return True
        if basename.endswith(".css") and "css" in line_lower:
            return True
        if basename.endswith(".html") and ("html" in line_lower or "markup" in line_lower):
            return True
        return False

    raw_issue_lines = [line.strip() for line in issues.splitlines() if line.strip()]
    kept_issue_lines: list[str] = []
    contradicted_files: set[str] = set()

    for line in raw_issue_lines:
        lower_line = line.lower()
        contradicted_port_claim = False

        if "run.sh" in evidence_files and "run.sh" in lower_line:
            if (
                ("port variable" in lower_line or "uses the port variable" in lower_line)
                and ("no assurance" in lower_line or "no evidence" in lower_line or "not" in lower_line)
                and run_sh_uses_port_var
            ):
                contradicted_port_claim = True
            if ("source" in lower_line or "export" in lower_line) and run_sh_exports_port:
                contradicted_port_claim = True
            if "hardcod" in lower_line and run_sh_uses_port_var and not run_sh_has_hardcoded_port:
                contradicted_port_claim = True

        if (
            "run.sh" in evidence_files
            and "hardcod" in lower_line
            and "main.py" in lower_line
            and run_sh_uses_port_var
            and not run_sh_has_hardcoded_port
        ):
            contradicted_port_claim = True

        if contradicted_port_claim:
            contradicted_files.add("run.sh")
            continue

        contradicted_truncation = [
            filename
            for filename in evidence_files
            if _line_mentions_file(lower_line, filename)
            and any(term in lower_line for term in truncation_terms)
            and bool(str(content_by_file.get(filename, "") or "").strip())
        ]
        if contradicted_truncation:
            contradicted_files.update(contradicted_truncation)
            continue

        contradicted = [
            filename for filename in evidence_files
            if filename in lower_line and ("missing" in lower_line or "not found" in lower_line)
        ]
        if contradicted:
            contradicted_files.update(contradicted)
            continue
        kept_issue_lines.append(line)

    if contradicted_files:
        filtered_issue_lines = []
        for line in kept_issue_lines:
            lower_line = line.lower()
            if any(filename in lower_line for filename in contradicted_files) and (
                "cannot verify" in lower_line or "could not verify" in lower_line
            ):
                continue
            filtered_issue_lines.append(line)
        kept_issue_lines = filtered_issue_lines

        lower_summary = summary.lower()
        if any(filename in lower_summary for filename in contradicted_files) and (
            "missing" in lower_summary
            or "not found" in lower_summary
            or any(term in lower_summary for term in truncation_terms)
        ):
            contradicted_list = ", ".join(sorted(contradicted_files))
            if kept_issue_lines:
                summary = (
                    f"Deterministic qodeyard evidence confirmed the generated files exist, including {contradicted_list}. "
                    "Remaining review notes are preserved below."
                )
            else:
                summary = (
                    f"Deterministic qodeyard evidence confirmed the generated files exist, including {contradicted_list}. "
                    "No remaining review issues were substantiated."
                )

    substantive_issues = [line for line in kept_issue_lines if line.lower() != "none"]
    if contradicted_files and not substantive_issues:
        contradicted_list = ", ".join(sorted(contradicted_files))
        summary = (
            f"Deterministic qodeyard evidence confirmed the generated files exist, including {contradicted_list}. "
            "No remaining review issues were substantiated."
        )

    if assessment in {"[PARTIAL]", "[FAILURE]"} and contradicted_files and not substantive_issues:
        assessment = "[SUCCESS]"
        kept_issue_lines = ["None"]

    normalized_issues = "\n".join(kept_issue_lines) if kept_issue_lines else "None"
    return assessment, summary, normalized_issues


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


def _render_batched_changed_file_evidence(filename: str, content: str, snippet_limit: int = 8000) -> str:
    """Render changed-file evidence with explicit truncation metadata."""
    if content == "[File not found in qodeyard]":
        return (
            f"**{filename}** (evidence=missing_in_qodeyard)\n"
            "_Deterministic loader did not find this file in qodeyard._"
        )
    if isinstance(content, str) and content.startswith("[Could not read:"):
        return (
            f"**{filename}** (evidence=read_error)\n"
            f"_Deterministic loader could not read this file: {content}_"
        )

    safe_content = str(content or "")
    snippet = safe_content[:snippet_limit]
    snippet_truncated = len(safe_content) > len(snippet)
    file_bytes = len(safe_content.encode("utf-8", errors="replace"))
    snippet_chars = len(snippet)
    return (
        f"**{filename}** "
        f"(evidence=authoritative_final_file, file_bytes={file_bytes}, "
        f"snippet_chars={snippet_chars}, snippet_truncated={'true' if snippet_truncated else 'false'})\n"
        f"```\n{snippet}\n```"
    )


def build_batched_review_prompt(
    briqs_data: list[dict],  # [{'name': str, 'content': str, 'changed': list}]
    six_shooter_context: dict[str, str] | None = None  # v1.3.13
) -> str:
    """Build a prompt for reviewing multiple briqs at once."""
    
    # v1.3.13: Six-Shooter QONTRACT section
    qontract_section = ""
    if six_shooter_context:
        qontract_section = "\n## 📜 PROJECT CONSTITUTION (SIX-SHOOTER QONTRACT)\n"
        # For batch review, we prioritize 05-target-state and 02-hard-ruleset as global anchors
        review_docs = ["05-target-state", "02-hard-ruleset"]
        for doc_prefix in review_docs:
            found_name = next((n for n in six_shooter_context if n.startswith(doc_prefix)), None)
            if found_name:
                label = found_name.split('-', 1)[-1].replace('.md', '').upper().replace('-', ' ')
                qontract_section += f"### {label}\n{six_shooter_context[found_name]}\n"
        qontract_section += "**You MUST verify code against these invariants.**\n"
    
    briq_sections = []
    for i, briq in enumerate(briqs_data):
        changed_section = ""
        if briq['changed']:
            changed_files = "\n".join([
                _render_batched_changed_file_evidence(fname, content, snippet_limit=8000)
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

{qontract_section}

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
4. Treat `evidence=authoritative_final_file` entries as source-of-truth over relay/log snippets.
5. `snippet_truncated=true` means prompt clipping only; NEVER treat that alone as a file truncation defect.
6. Relay/log text is secondary context only and must not override deterministic final-file evidence.

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
    qontract_context: str = "",  # v1.3.0
    six_shooter_context: dict[str, str] | None = None  # v1.3.13
) -> str:
    """Build the prompt for reviewing a single briq."""

    # Build changed code section
    changed_code_section = ""
    if changed_files:
        changed_code_section = "\n## Changed Code Artifacts\n"
        for filename, content in changed_files:
            raw_content = str(content or "")
            snippet = raw_content
            snippet_truncated = False
            if len(raw_content) > 50_000:
                snippet = raw_content[:50_000]
                snippet_truncated = True
            file_bytes = len(raw_content.encode("utf-8", errors="replace"))
            snippet_chars = len(snippet)
            changed_code_section += (
                f"\n### File: `{filename}`\n"
                f"_Evidence: authoritative_final_file | file_bytes={file_bytes} | "
                f"snippet_chars={snippet_chars} | snippet_truncated={'true' if snippet_truncated else 'false'}_\n"
                f"```\n{snippet}\n```\n"
            )
    else:
        changed_code_section = "\n_No changed code artifacts for this briq._\n"

    # v1.3.13: Six-Shooter QONTRACT section
    qontract_section = ""
    if six_shooter_context:
        qontract_section = "\n## 📜 PROJECT CONSTITUTION (SIX-SHOOTER QONTRACT)\n"
        # For review, we prioritize 05-target-state and 02-hard-ruleset
        review_docs = ["05-target-state", "02-hard-ruleset", "04-contracts"]
        for doc_prefix in review_docs:
            found_name = next((n for n in six_shooter_context if n.startswith(doc_prefix)), None)
            if found_name:
                label = found_name.split('-', 1)[-1].replace('.md', '').upper().replace('-', ' ')
                qontract_section += f"### {label}\n{six_shooter_context[found_name]}\n"
        qontract_section += "**You MUST verify code against these invariants.**\n"
    elif qontract_context:
        qontract_section = f"""

## 📜 PROJECT CONSTITUTION (QONTRACT)
{qontract_context[:3000]}
**You MUST verify code against these invariants.**
"""

    prompt = f"""You are the 'inspeQtor', a senior software quality engineer performing a focused code review.

**SCOPE:** You are reviewing a SINGLE briq (task unit) from a larger cycle. Focus only on this specific unit.
{qontract_section}**YOUR TASK:**
Determine if the code changes for this briq are complete, correct, and consistent with the existing architecture.

**REVIEW CRITERIA:**
1. **Correctness:** Is the code logically correct and free of obvious bugs?
2. **Completeness:** Did the code fully implement what the briq specified?
3. **Consistency:** Do the changes integrate properly with existing code patterns and conventions?
4. **Contract Compliance:** Does the code comply with QONTRACT invariants?
5. **Evidence Ranking:** Treat `authoritative_final_file` snippets as source-of-truth over relay/log impressions.
6. **Snippet Note:** `snippet_truncated=true` is prompt clipping only and is NOT proof of an incomplete file.

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
    config: dict,
    all_changed: list[tuple[str, str]],
) -> list[dict]:
    """
    Run per-briq reviews for all briqs in the current cycle.
    
    Returns:
        List of briq review results: [{briq_name, assessment, reqap_path, error}]
    """
    # v1.3.13: Six-Shooter Qontract support
    workspace_root = qodeyard_path.parent
    qontract_dir = workspace_root / "qontract.d"
    six_shooter_manifest = load_optional_json(qontract_dir / "six-shooter-manifest.v1.json")
    six_shooter_context = {}
    if six_shooter_manifest:
        for doc_name in six_shooter_manifest.get("selected_docs", []):
            doc_path = qontract_dir / doc_name
            if doc_path.exists():
                try:
                    six_shooter_context[doc_name] = doc_path.read_text(encoding='utf-8')
                except:
                    pass

    results = []
    workspace_root = qodeyard_path.parent
    completion_criteria = load_optional_json(workspace_root / "planning" / "completion-criteria.v1.json")
    required_files = [
        normalize_file_hint(item)
        for item in completion_criteria.get("required_files", [])
    ] if isinstance(completion_criteria.get("required_files"), list) else []
    required_files = [item for item in required_files if item]
    
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
                    
                    # Extract file/group targets from this briq
                    briq_targets = extract_briq_file_targets(briq_content, required_files=required_files)
                    build_group_hint, briq_ref_hint = extract_briq_scope_hints(briq_content)
                    briq_scope_files = derive_group_scope_files(
                        workspace_root,
                        target_files=briq_targets,
                        current_build_group=build_group_hint,
                        current_briq_ref=briq_ref_hint,
                    )
                    briq_changed = merge_briq_changed_files(
                        all_changed,
                        qodeyard_path,
                        briq_targets,
                        fallback_limit=3,
                        scope_files=briq_scope_files,
                    )
                    
                    briqs_data.append({
                        'name': briq_name,
                        'content': briq_content,
                        'changed': briq_changed
                    })
                
                # Build batched prompt
                prompt = build_batched_review_prompt(briqs_data, six_shooter_context=six_shooter_context)
                
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
                    prompt_sections=[{
                        'label': 'batched_review_prompt',
                        'content': prompt,
                        'required': True,
                        'loss_policy': 'chunkable',
                        'section_type': 'review_batch',
                    }],
                    agent_name='inspeqtor',
                    task_type='review',
                    output_tokens=min(4000, max(800, len(batch) * 180)),
                    include_previous_log=False,
                )
                
                # Parse batch response
                parsed_results = parse_batched_response(response, batch_briq_names)
                
                # Write individual reqaps and collect results
                for briq_data in briqs_data:
                    briq_name = briq_data['name']
                    parsed = parsed_results.get(briq_name, {
                        'assessment': '[UNKNOWN]',
                        'summary': 'Not found in batch',
                        'issues': 'Review manually',
                        'raw': ''
                    })
                    normalized_assessment, normalized_summary, normalized_issues = normalize_review_result(
                        parsed['assessment'],
                        parsed['summary'],
                        parsed['issues'],
                        briq_data.get('changed', []),
                    )
                    
                    reqap_path = cycle_reqap_dir / f"{briq_name}_reqap.md"
                    with open(reqap_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Briq Review: {briq_name}\n\n")
                        f.write(f"Assessment: {normalized_assessment}\n\n")
                        f.write(f"## Summary\n{normalized_summary}\n\n")
                        f.write(f"## Issues\n{normalized_issues}\n")
                    
                    results.append({
                        'briq_name': briq_name,
                        'assessment': normalized_assessment,
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
                
                # Extract file/group targets from this briq
                briq_targets = extract_briq_file_targets(briq_content, required_files=required_files)
                build_group_hint, briq_ref_hint = extract_briq_scope_hints(briq_content)
                briq_scope_files = derive_group_scope_files(
                    workspace_root,
                    target_files=briq_targets,
                    current_build_group=build_group_hint,
                    current_briq_ref=briq_ref_hint,
                )
                briq_changed = merge_briq_changed_files(
                    all_changed,
                    qodeyard_path,
                    briq_targets,
                    fallback_limit=5,
                    scope_files=briq_scope_files,
                )
                
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
                prompt = build_briq_review_prompt(briq_name, briq_content, briq_changed, six_shooter_context=six_shooter_context)
                
                # Estimate cost
                context_size_tokens = sum(
                    estimate_tokens(Path(f).read_text(encoding='utf-8', errors='ignore'), config['model'])
                    for f in context_files if Path(f).exists()
                )
                input_tokens = estimate_tokens(prompt, config['model']) + context_size_tokens
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
                    max_chars_per_file=config['max_chars_per_context_file'],
                    prompt_sections=[{
                        'label': f'briq_review:{briq_name}',
                        'content': prompt,
                        'required': True,
                        'loss_policy': 'preserve',
                        'section_type': 'review_prompt',
                    }],
                    agent_name='inspeqtor',
                    task_type='review',
                    output_tokens=1200,
                    include_previous_log=False,
                )
                
                # Extract assessment
                assessment = "[UNKNOWN]"
                if "[SUCCESS]" in response:
                    assessment = "[SUCCESS]"
                elif "[PARTIAL]" in response:
                    assessment = "[PARTIAL]"
                elif "[FAILURE]" in response:
                    assessment = "[FAILURE]"

                summary_match = re.search(r'## Summary\s*\n(.*?)(?=\n##|\Z)', response, re.DOTALL)
                issues_match = re.search(r'## Issues(?: Found)?\s*\n(.*?)(?=\n##|\Z)', response, re.DOTALL)
                summary = summary_match.group(1).strip() if summary_match else "Review completed."
                issues = issues_match.group(1).strip() if issues_match else "None"
                assessment, summary, issues = normalize_review_result(
                    assessment,
                    summary,
                    issues,
                    briq_changed,
                )

                # Write reqap
                reqap_path = cycle_reqap_dir / f"{briq_name}_reqap.md"
                with open(reqap_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Briq Review: {briq_name}\n\n")
                    f.write(f"Assessment: {assessment}\n\n")
                    f.write(f"## Summary\n{summary}\n\n")
                    f.write(f"## Issues\n{issues}\n")
                
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
    """
    if len(sys.argv) != 4:
        print("Usage: inspeqtor.py <summary_path> <changed_files_path> <reqap_output_path>", flush=True)
        sys.exit(1)

    summary_path = Path(sys.argv[1])
    changed_files_path = Path(sys.argv[2])
    reqap_path = Path(sys.argv[3])
    
    cycle_num = os.environ.get('CYCLE_NUM', '1')

    # v1.3.10: Fail loud if cwd has drifted inside qodeyard/. Otherwise
    # reqap_dir would resolve to qodeyard/<sub>/reqap.d/ and reports
    # would pollute the code tree.
    assert_cwd_outside_qodeyard("inspeqtor")

    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    qontext_path = worqspace_root / "qontext.d"
    bloq_path = worqspace_root / "bloq.d"
    briq_dir = worqspace_root / "briq.d"
    exeq_dir = worqspace_root / "exeq.d"
    reqap_dir = worqspace_root / "reqap.d"
    tasq_dir = worqspace_root / "tasq.d"
    struqture_dir = worqspace_root / "struqture"
    changed_code_artifacts = load_changed_code_artifacts(exeq_dir, cycle_num, qodeyard_path)
    scoped_changed_files = []
    seen_scope: set[str] = set()
    for rel_path, _content in (changed_code_artifacts or []):
        normalized = normalize_file_hint(rel_path)
        if not normalized or normalized in seen_scope:
            continue
        seen_scope.add(normalized)
        scoped_changed_files.append(normalized)

    # v1.3.13: If we are in a repair cycle (QONQ_REPAIR_MODE=1), we MUST NOT 
    # limit our inspection to only the files that changed in this narrow iteration.
    # We should at least union with the full qodeyard list or all cumulative changes.
    # For now, if repair mode is active, we expand scoped_changed_files to include
    # everything in qodeyard to ensure full regression coverage.
    if os.environ.get("QONQ_REPAIR_MODE") == "1":
        print(f"    [REPAIR MODE] Expanding inspection scope to all qodeyard files for full regression coverage.", flush=True)
        qodeyard_all = list_qodeyard_files_for_completion_check(worqspace_root)
        for f in qodeyard_all:
            if f not in seen_scope:
                seen_scope.add(f)
                scoped_changed_files.append(f)
    
    print(f"--- Multi-Stage Review for cyQle {cycle_num} ---", flush=True)

    # Load configuration
    config = load_inspeqtor_config(worqspace_root / 'config.yaml')
    full_config = load_full_config(worqspace_root / 'config.yaml')
    full_config_with_smoketest = make_smoketest_runtime_config(full_config)
    print(f"  [AI] inspeqtor provider={config.get('provider')} model={config.get('model')}", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # B) FAIL-FAST: Contract must exist (cycles > 1)
    # ═══════════════════════════════════════════════════════════════════════════
    qontract_dir = worqspace_root / "qontract.d"
    if cycle_num != '1':
        try:
            from lib_loqal import ensure_qontract_present
            ensure_qontract_present(worqspace_root)
            print(f"    ✅ Contract present (fail-fast check passed)", flush=True)
        except RuntimeError as e:
            print(f"    ❌ {e}", flush=True)
            sys.exit(1)
        except ImportError:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.3.0 (C): CONTEXT ASSEMBLY — Contract + Tasqs + Qodeyard (primary)
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
    # STAGE 0 (G4.6): Qonfirmer (Deterministic, BEFORE AI Review)
    # ═══════════════════════════════════════════════════════════════════════════
    qonfirmer_report = None
    qonfirmer_passed = True
    qontract_json_path = qontract_dir / "qontract.json"

    print(f"\n--- STAGE 0: Qonfirmer (Deterministic — Full Cycle) ---", flush=True)
    print("[Qonfirmer] Running deterministic contract validation...", flush=True)
    # QONTRACT enforcement is mandatory if the artifact exists.
    # If the artifact is missing, it is a failure if any contract-relevant work was attempted.
    contract_exists = qontract_json_path.exists()
    
    if qonfirmer and contract_exists:
        try:
            import json as _json
            contract = qonfirmer.load_contract(qontract_json_path)
            if not contract:
                # B) Never silently skip — treat empty/missing as FAIL
                qonfirmer_report = qonfirmer.QonfirmerReport(passed=False)
                qonfirmer_report.add_violation(qonfirmer.Violation(
                    rule='CONTRACT_EMPTY',
                    file_path=str(qontract_json_path),
                    line_number=None,
                    message="Contract artifact is empty — cannot enforce invariants"
                ))
                qonfirmer_passed = False
            else:
                qonfirmer_report = qonfirmer.run_qonfirmer(contract, qodeyard_path)
            qonfirmer_passed = qonfirmer_report.passed

            # Write Qonfirmer report (markdown + JSON)
            qonfirmer_md_output = reqap_dir / f"cyqle{cycle_num}_qonfirmer.md"
            qonfirmer_md_output.parent.mkdir(parents=True, exist_ok=True)
            with open(qonfirmer_md_output, 'w', encoding='utf-8') as f:
                f.write(qonfirmer_report.to_markdown())

            qonfirmer_json_output = reqap_dir / f"cyqle{cycle_num}_qonfirmer.json"
            with open(qonfirmer_json_output, 'w', encoding='utf-8') as f:
                _json.dump(qonfirmer_report.to_json(), f, indent=2)

            print(f"    Qonfirmer report: {qonfirmer_md_output}", flush=True)
            print(f"    Qonfirmer JSON:   {qonfirmer_json_output}", flush=True)
            print(f"[Qonfirmer] Report: {qonfirmer_md_output}", flush=True)

            if not qonfirmer_passed:
                print(f"    Qonfirmer FAILED — {len(qonfirmer_report.violations)} violations", flush=True)
                print(f"[Qonfirmer] FAIL ({len(qonfirmer_report.violations)} violations)", flush=True)
                for v in qonfirmer_report.violations[:10]:
                    print(f"       {v}", flush=True)
            else:
                print(f"    Qonfirmer PASSED", flush=True)
                print("[Qonfirmer] PASS", flush=True)

        except Exception as e:
            print(f"    [ERROR] Qonfirmer failed to run: {e}", flush=True)
            print(f"[Qonfirmer] ERROR: {e}", flush=True)
            qonfirmer_passed = False
    elif contract_exists and not qonfirmer:
        # Artifact exists but engine is missing — HARD FAIL
        print(f"    [WARN] QONTRACT artifact found but qonfirmer module not available. FAILING.", flush=True)
        print("[Qonfirmer] FAIL (module unavailable while contract artifact exists)", flush=True)
        class _DummyViolation:
            def __init__(self, message):
                self.rule = 'QONFIRMER_UNAVAILABLE'
                self.file_path = str(qontract_json_path)
                self.line_number = None
                self.message = message
                self.severity = "error"
            def __str__(self):
                return f"[{self.severity.upper()}] [{self.rule}] {self.file_path}: {self.message}"

        class _DummyReport:
            def __init__(self, message):
                self.passed = False
                self.files_checked = 0
                self.rules_checked = 0
                self.violations = [_DummyViolation(message)]

        qonfirmer_report = _DummyReport("Qonfirmer module unavailable but QONTRACT artifact exists.")
        qonfirmer_passed = False
    elif not contract_exists:
        # Artifact missing — only fail if we were supposed to have one
        # For v1.3.8 we default to warning but allow pass if no other signal requires it.
        # However, if any work was done, we prefer having a contract.
        print(f"    [INFO] No QONTRACT artifact found at {qontract_json_path}. Skipping deterministic enforcement.", flush=True)
        print("[Qonfirmer] SKIP (no contract artifact present)", flush=True)
        qonfirmer_report = None
        qonfirmer_passed = True
    else:
        # Fallback for unexpected states
        qonfirmer_passed = True
        qonfirmer_report = None

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1 (G4.6): Qualification (Deterministic, BEFORE AI Review)
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n--- STAGE 1: Qualification (Syntax/Import Sanity) ---", flush=True)

    inspection_substep_failures: list[dict] = []
    verification_enabled = full_config_with_smoketest.get('verification', {}).get('enabled', True)
    verification_results = None

    if verification_enabled:
        try:
            import qualifier

            verification_report = qualifier.run_verification(
                qodeyard_path,
                qontext_path,
                cycle_num,
                full_config_with_smoketest,
                changed_files=scoped_changed_files or None,
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
            print("    [WARN] qualifier module not found — skipping", flush=True)
        except Exception as e:
            print(f"    [WARN] Verification failed: {e}", flush=True)
    else:
        print("    Qualification disabled in config", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1.5: Executed Smoketest (Deterministic, BEFORE AI Review)
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n--- STAGE 1.5: Smoketest (Static + Executed Checks) ---", flush=True)
    print("[smoQetester] Running scoped smoketest...", flush=True)
    smoketest_report = None
    smoketest_output = reqap_dir / f"cyqle{cycle_num}" / f"cyqle{cycle_num}_smoketest.md"
    smoketest_json_output = reqap_dir / f"cyqle{cycle_num}" / f"cyqle{cycle_num}_smoketest.v1.json"
    smoke_payload: dict = {}
    if smoqetester:
        try:
            smoketest_report = smoqetester.run_smoketest(
                qodeyard_path,
                cycle_num,
                full_config_with_smoketest,
                changed_files=scoped_changed_files or None,
            )
            smoketest_output.parent.mkdir(parents=True, exist_ok=True)
            with open(smoketest_output, "w", encoding="utf-8") as fh:
                fh.write(smoketest_report.to_markdown())
            smoke_payload = smoketest_report_to_dict(smoketest_report) or {}
            smoke_counts = summarize_smoketest_counts(smoke_payload)
            with open(smoketest_json_output, "w", encoding="utf-8") as fh:
                json.dump(smoke_payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
            print(
                f"    Smoketest report: {smoketest_output} "
                f"(executed={smoke_counts['executed_count']}, static={smoke_counts['static_count']}, "
                f"failed={smoke_payload.get('failed', 0)}, errors={smoke_payload.get('errors', 0)})",
                flush=True,
            )
            print(
                f"[smoQetester] Report: {smoketest_output} "
                f"(executed={smoke_counts['executed_count']}, static={smoke_counts['static_count']}, "
                f"failed={smoke_payload.get('failed', 0)}, errors={smoke_payload.get('errors', 0)})",
                flush=True,
            )
            print(f"[smoQetester] {normalize_smoketest_status(smoke_payload.get('overall_status'))}", flush=True)
        except Exception as e:
            print(f"    [WARN] Smoketest failed in recoverable mode: {e}", flush=True)
            print(f"[smoQetester] ERROR: {e}", flush=True)
            mark_substep_failure(inspection_substep_failures, "smoketest", e, recoverable=True)
            smoketest_output.parent.mkdir(parents=True, exist_ok=True)
            with open(smoketest_output, "w", encoding="utf-8") as fh:
                fh.write(
                    "# Smoketest Report\n\n"
                    f"- Status: ERROR\n"
                    f"- Message: {e}\n"
                )
            smoke_payload = {
                "cycle": str(cycle_num),
                "enabled": True,
                "mode": "scoped",
                "overall_status": "FAIL",
                "commands_executed": 0,
                "commands_skipped": 0,
                "executed_count": 0,
                "static_count": 0,
                "failed": 0,
                "warnings": 0,
                "errors": 1,
                "skipped": 0,
                "adapters_triggered": [],
                "results": [{
                    "adapter": "smoketest",
                    "name": "runtime_error",
                    "status": "ERROR",
                    "executed": False,
                    "execution_kind": "static",
                    "message": str(e),
                    "severity": "error",
                }],
            }
            with open(smoketest_json_output, "w", encoding="utf-8") as fh:
                json.dump(smoke_payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
    else:
        print("    [WARN] smoqetester module not found — skipping smoketest checks", flush=True)
        print("[smoQetester] SKIP (module not available)", flush=True)
        smoketest_output.parent.mkdir(parents=True, exist_ok=True)
        with open(smoketest_output, "w", encoding="utf-8") as fh:
            fh.write(
                "# Smoketest Report\n\n"
                "- Status: SKIP\n"
                "- Message: smoqetester module not available.\n"
            )
        smoke_payload = {
            "cycle": str(cycle_num),
            "enabled": False,
            "mode": "scoped",
            "overall_status": "PARTIAL",
            "commands_executed": 0,
            "commands_skipped": 0,
            "executed_count": 0,
            "static_count": 0,
            "failed": 0,
            "warnings": 0,
            "errors": 0,
            "skipped": 1,
            "adapters_triggered": [],
            "results": [{
                "adapter": "smoketest",
                "name": "module_missing",
                "status": "SKIP",
                "executed": False,
                "execution_kind": "static",
                "message": "smoqetester module not available.",
                "severity": "info",
            }],
        }
        with open(smoketest_json_output, "w", encoding="utf-8") as fh:
            json.dump(smoke_payload, fh, indent=2, sort_keys=True)
            fh.write("\n")

    # ═══════════════════════════════════════════════════════════════════════════
    # DECISION: Should AI InspeQtor run?
    # ═══════════════════════════════════════════════════════════════════════════
    ai_review_mode = "normal"  # "normal" | "report_only" | "skipped"

    if not qonfirmer_passed:
        ai_review_mode = "report_only"
        print(f"\n    Qonfirmer FAILED — AI InspeQtor will run in REPORT-ONLY mode", flush=True)
        print(f"    (Qonfirmer failure forces overall FAIL regardless of AI opinion)", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Per-Briq Tactical Reviews (AI)
    # ═══════════════════════════════════════════════════════════════════════════
    run_report_only_briq_reviews = should_run_report_only_briq_reviews(config)
    if ai_review_mode == "report_only" and not run_report_only_briq_reviews:
        print(f"\n--- STAGE 2: Per-Briq Tactical Reviews SKIPPED (report-only deterministic mode) ---", flush=True)
        print("  [SPEED] Qonfirmer already produced deterministic blockers; skipping low-signal report-only briq AI calls.", flush=True)
        briq_results = []
    elif ai_review_mode != "skipped":
        print(f"\n--- STAGE 2: Per-Briq Tactical Reviews (mode: {ai_review_mode}) ---", flush=True)
        try:
            briq_results = run_per_briq_reviews(
                cycle_num,
                briq_dir,
                exeq_dir,
                qodeyard_path,
                qontext_path,
                reqap_dir,
                config,
                changed_code_artifacts,
            )
        except Exception as e:
            print(f"[WARN] Tactical review stage failed in recoverable mode: {e}", flush=True)
            mark_substep_failure(inspection_substep_failures, "tactical_review", e, recoverable=True)
            briq_results = []
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
    briq_name_to_ref = {}
    for briq_file in sorted(briq_dir.glob(f"cyqle{cycle_num}_*.md")):
        try:
            briq_text = briq_file.read_text(encoding='utf-8')
        except Exception:
            continue
        match = re.search(r"^Briq-Ref:\s*(.+)$", briq_text, re.MULTILINE)
        if match:
            briq_name_to_ref[briq_file.stem] = match.group(1).strip()
    
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
        
        if ai_review_mode == "normal" and result['assessment'] in ['[FAILURE]', '[PARTIAL]']:
            failed_briq_ref = briq_name_to_ref.get(result['briq_name'], result['briq_name'])
            suggestions_match = re.search(r'## Suggestions\s*\n(.*?)(?=\n##|\Z)', briq_reqap, re.DOTALL)
            if suggestions_match:
                failed_briq_suggestions.append({
                    'briq': failed_briq_ref,
                    'assessment': result['assessment'],
                    'suggestions': suggestions_match.group(1).strip()
                })
            else:
                failed_briq_suggestions.append({
                    'briq': failed_briq_ref,
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

    # G4.6: Force FAIL if Qonfirmer failed (hard enforcement)
    if qonfirmer_report and not qonfirmer_passed:
        overall_assessment = "[FAILURE]"
        print(f"[QONTRACT] Qonfirmer FAILED — forcing overall assessment to FAILURE", flush=True)

    # Downgrade if verification found errors
    if verification_results and hasattr(verification_results, 'errors') and verification_results.errors > 0:
        if overall_assessment == "[SUCCESS]":
            overall_assessment = "[PARTIAL]"
            print(f"[VERIFY] Verification errors found — downgrading to PARTIAL", flush=True)

    changed_manifest_files = sorted({filename for filename, _ in changed_code_artifacts})
    print("Checking build output", flush=True)
    try:
        grouped_coherence = evaluate_grouped_coherence(
            worqspace_root,
            cycle_num,
            changed_manifest_files,
        )
    except Exception as e:
        print(f"[WARN] Group coherence evaluation failed in recoverable mode: {e}", flush=True)
        mark_substep_failure(inspection_substep_failures, "grouped_coherence", e, recoverable=True)
        grouped_coherence = default_grouped_coherence(changed_manifest_files, e)

    validation_bundle_path = worqspace_root / "validation" / "validation-bundle.v1.json"
    validation_summary_path = worqspace_root / "validation" / "validation-summary.md"
    try:
        validation_bundle = build_validation_bundle(
            worqspace_root,
            cycle_num,
            qonfirmer_report,
            verification_results,
            smoketest_report,
            grouped_coherence,
            changed_manifest_files,
        )
    except Exception as e:
        message = f"Validation bundle generation failed: {e}"
        print(f"[WARN] {message}", flush=True)
        mark_substep_failure(inspection_substep_failures, "validation_bundle", e, recoverable=True)
        validation_bundle = default_validation_bundle(
            worqspace_root,
            cycle_num,
            message,
            changed_manifest_files,
        )
    print("Checking group coherence", flush=True)
    write_json(validation_bundle_path, validation_bundle)
    validation_summary_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        validation_summary_content = render_validation_summary(validation_bundle)
    except Exception:
        validation_summary_content = "# Validation Summary\n\nValidation summary rendering failed; see validation-bundle.v1.json.\n"
    with open(validation_summary_path, 'w', encoding='utf-8') as f:
        f.write(validation_summary_content)

    realization_bundle_path = worqspace_root / "realization" / "realization-bundle.v1.json"
    realization_summary_path = worqspace_root / "realization" / "realization-summary.md"
    try:
        realization_bundle = build_realization_bundle(
            worqspace_root,
            cycle_num,
            validation_bundle,
            smoketest_report,
            grouped_coherence,
            changed_manifest_files,
            cross_briq_warnings,
        )
    except Exception as e:
        message = f"Realization bundle generation failed: {e}"
        print(f"[WARN] {message}", flush=True)
        mark_substep_failure(inspection_substep_failures, "realization_bundle", e, recoverable=True)
        realization_bundle = default_realization_bundle(
            worqspace_root,
            cycle_num,
            validation_bundle,
            changed_manifest_files,
            message,
        )
    write_json(realization_bundle_path, realization_bundle)
    realization_summary_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        realization_summary_content = render_realization_summary(realization_bundle)
    except Exception:
        realization_summary_content = "# Realization Summary\n\nRealization summary rendering failed; see realization-bundle.v1.json.\n"
    with open(realization_summary_path, 'w', encoding='utf-8') as f:
        f.write(realization_summary_content)

    inspection_input_path = worqspace_root / "verdict" / "inspection-input.v1.json"
    try:
        inspection_input = build_inspection_input_contract(
            worqspace_root,
            cycle_num,
            validation_bundle,
            realization_bundle,
        )
    except Exception as e:
        message = f"Inspection input contract generation failed: {e}"
        print(f"[WARN] {message}", flush=True)
        mark_substep_failure(inspection_substep_failures, "inspection_input", e, recoverable=True)
        inspection_input = {
            "schema_version": "inspection-input.v1",
            "inspection_input_id": f"{canonical_run_id(worqspace_root)}-inspection-input-cyqle{cycle_num}",
            "run_id": canonical_run_id(worqspace_root),
            "cycle": int(cycle_num),
            "stage": "INSPECTION",
            "status": "BLOCKED",
            "required_inputs": {
                "validation_bundle_ref": "validation/validation-bundle.v1.json",
                "realization_bundle_ref": "realization/realization-bundle.v1.json",
                "completion_criteria_ref": "planning/completion-criteria.v1.json",
            },
            "missing_inputs": ["inspection_input_generation_failed"],
            "capability_mode": "MIXED_REASONING_EXECUTION",
            "validation_execution_mode": validation_bundle.get("validation_execution_mode", "NONE"),
            "created_at": now_utc(),
        }
    write_json(inspection_input_path, inspection_input)

    enforced_failed_briq_suggestions = enforce_briq_suggestions_for_repair(
        ai_review_mode,
        failed_briq_suggestions,
    )

    try:
        inspection_verdict = build_inspection_verdict(
            worqspace_root,
            cycle_num,
            overall_assessment,
            validation_bundle,
            realization_bundle,
            inspection_input,
            cross_briq_warnings,
            enforced_failed_briq_suggestions,
            inspection_substep_failures=inspection_substep_failures,
        )
    except Exception as e:
        message = f"Inspection verdict generation failed: {e}"
        print(f"[WARN] {message}", flush=True)
        mark_substep_failure(inspection_substep_failures, "inspection_verdict", e, recoverable=True)
        inspection_verdict = default_inspection_verdict(
            worqspace_root,
            cycle_num,
            validation_bundle,
            realization_bundle,
            inspection_input,
            message,
            substep_failures=inspection_substep_failures,
        )

    inspection_runtime_path = worqspace_root / "verdict" / "inspection-runtime.v1.json"
    inspection_runtime_payload = {
        "schema_version": "inspection-runtime.v1",
        "run_id": canonical_run_id(worqspace_root),
        "cycle": int(cycle_num),
        "stage": "INSPECTION",
        "status": "DEGRADED" if inspection_substep_failures else "COMPLETE",
        "failed_substeps": inspection_substep_failures,
        "created_at": now_utc(),
    }
    write_json(inspection_runtime_path, inspection_runtime_payload)
    inspection_verdict["inspection_runtime_ref"] = "verdict/inspection-runtime.v1.json"
    inspection_verdict["inspection_substep_failures"] = inspection_substep_failures
    if inspection_substep_failures and inspection_verdict.get("inspection_integrity") != "DEGRADED":
        inspection_verdict["inspection_integrity"] = "DEGRADED"

    repair_label = "YES" if inspection_verdict.get("repair_required") else "NO"
    print(f"Inspection verdict: {inspection_verdict['status']} | Repair required: {repair_label}", flush=True)
    repair_plan_path = worqspace_root / "verdict" / "repair-plan.v1.json"
    repair_plan_summary_path = worqspace_root / "verdict" / "repair-plan.md"
    if inspection_verdict.get("repair_required"):
        print("Writing repair plan", flush=True)
        try:
            repair_plan = build_repair_plan(
                worqspace_root,
                cycle_num,
                inspection_verdict,
                validation_bundle,
                realization_bundle,
                grouped_coherence,
                enforced_failed_briq_suggestions,
            )
        except Exception as e:
            message = f"Repair plan generation failed: {e}"
            print(f"[WARN] {message}", flush=True)
            mark_substep_failure(inspection_substep_failures, "repair_plan", e, recoverable=True)
            repair_plan = default_repair_plan(
                worqspace_root,
                cycle_num,
                inspection_verdict,
                message,
            )
        inspection_verdict["repair_plan_ref"] = "verdict/repair-plan.v1.json"
        inspection_verdict["next_lifecycle_transition"] = repair_plan.get("next_lifecycle_transition", "CONTINUABLE")
        write_json(repair_plan_path, repair_plan)
        repair_plan_summary_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            repair_plan_summary_content = render_repair_plan_summary(repair_plan)
        except Exception:
            repair_plan_summary_content = "# Repair Plan\n\nRepair plan summary rendering failed; see repair-plan.v1.json.\n"
        with open(repair_plan_summary_path, 'w', encoding='utf-8') as f:
            f.write(repair_plan_summary_content)
    else:
        repair_plan = None
        if repair_plan_path.exists():
            repair_plan_path.unlink()
        if repair_plan_summary_path.exists():
            repair_plan_summary_path.unlink()

    inspection_verdict_path = worqspace_root / "verdict" / "inspection-verdict.v1.json"
    print("Checking component contracts", flush=True)
    inspection_verdict_summary_path = worqspace_root / "verdict" / "inspection-verdict.md"
    write_json(inspection_verdict_path, inspection_verdict)
    inspection_verdict_summary_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        inspection_verdict_summary_content = render_inspection_verdict_summary(inspection_verdict)
    except Exception:
        inspection_verdict_summary_content = "# Inspection Verdict\n\nInspection verdict summary rendering failed; see inspection-verdict.v1.json.\n"
    with open(inspection_verdict_summary_path, 'w', encoding='utf-8') as f:
        f.write(inspection_verdict_summary_content)

    overall_assessment = f"[{inspection_verdict['status']}]"
    print(f"\n[BOUNDARY] Validation bundle: {validation_bundle_path}", flush=True)
    print(f"[BOUNDARY] Realization bundle: {realization_bundle_path}", flush=True)
    print(f"[BOUNDARY] Inspection input: {inspection_input_path}", flush=True)
    print(f"[BOUNDARY] Inspection verdict: {inspection_verdict_path}", flush=True)
    print(f"[BOUNDARY] Inspection runtime: {inspection_runtime_path}", flush=True)
    if repair_plan:
        print(f"[BOUNDARY] Repair plan: {repair_plan_path}", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # WRITE FINAL REQAP
    # ═══════════════════════════════════════════════════════════════════════════
    if ai_review_mode == "skipped" or not briq_results:
        _write_qonfirmer_only_reqap(
            reqap_path, cycle_num, qonfirmer_report, verification_results,
            overall_assessment, qontract_content,
            validation_bundle, realization_bundle, inspection_verdict
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

        if qonfirmer_report:
            qonfirmer_status = "PASS" if qonfirmer_report.passed else "FAIL"
            meta_prompt += f"\n## Qonfirmer Results: {qonfirmer_status}\n"
            if qonfirmer_report.violations:
                for v in qonfirmer_report.violations[:15]:
                    meta_prompt += f"- {v}\n"
            else:
                meta_prompt += "No contract violations found.\n"

        if verification_results and hasattr(verification_results, 'errors'):
            v_status = "PASS" if verification_results.errors == 0 else "ISSUES"
            meta_prompt += f"\n## Qualification: {v_status}\n"
            meta_prompt += f"Files checked: {verification_results.files_checked}, Errors: {verification_results.errors}, Warnings: {verification_results.warnings}\n"

        deterministic_failures = [
            issue for issue in validation_bundle.get("issues", [])
            if issue.get("severity") == "error"
        ]

        # v1.3.9: Ground meta-review in deterministic root causes
        deterministic_root_causes = []
        for issue in deterministic_failures:
            f_kind = issue.get("failure_kind")
            if f_kind == "environment_dependency_missing":
                deterministic_root_causes.append(f"ENVIRONMENT BLOCKER: Declared dependency '{issue.get('missing_module')}' is missing from validator.")
            elif f_kind == "dependency_declaration_failures":
                deterministic_root_causes.append(f"DEPENDENCY DECLARATION DEFECT: Dependency '{issue.get('missing_module')}' is imported but NOT declared in project manifests.")
            elif f_kind == "tooling_missing":
                deterministic_root_causes.append(f"ENVIRONMENT BLOCKER: Required tooling is missing from validator.")
            elif f_kind == "validator_degraded":
                deterministic_root_causes.append(f"VALIDATOR DEGRADED: {issue.get('message')}")
            elif f_kind == "blocking_code_failures" or not issue.get("environment_blocked", False):
                deterministic_root_causes.append(f"CODE DEFECT: {issue.get('message')}")
            else:
                deterministic_root_causes.append(f"DETERMINISTIC FAILURE: {issue.get('message')}")
        
        if deterministic_root_causes:
            meta_prompt += "\n## DETERMINISTIC ROOT CAUSES (CRITICAL GROUND TRUTH)\n"
            meta_prompt += "The following deterministic failures were observed. Prioritize these as the primary root causes:\n"
            for rc in sorted(set(deterministic_root_causes)):
                meta_prompt += f"- {rc}\n"
            meta_prompt += "\n"

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

        try:
            inspeqtor_cfg = ((config.get("agents", {}) or {}).get("inspeqtor", {}) or {})
            raw_meta_mode = inspeqtor_cfg.get("meta_review_mode", os.environ.get("QONQ_META_REVIEW_MODE", "auto"))
            meta_review_mode = str(raw_meta_mode or "auto").strip().lower()
            skip_meta_for_clean_pass = (
                is_success_assessment(overall_assessment)
                and not deterministic_root_causes
                and not failed_briq_suggestions
                and not cross_briq_warnings
            )
            skip_meta_for_deterministic_failures = bool(deterministic_root_causes)
            disable_meta_review = meta_review_mode in {"0", "false", "no", "off", "disabled"}
            force_meta_review = meta_review_mode in {"1", "true", "yes", "on", "force", "always"}

            if disable_meta_review:
                print("  [SPEED] Meta-review disabled by config/env; using deterministic synthesis only.", flush=True)
                meta_response = "Meta-review AI call disabled by configuration. Deterministic evidence and per-briq findings are preserved below."
            elif not force_meta_review and (skip_meta_for_clean_pass or skip_meta_for_deterministic_failures):
                if skip_meta_for_clean_pass:
                    print("  [SPEED] All checks passed. Bypassing redundant AI meta-review.", flush=True)
                    meta_response = "All components meet acceptance criteria. No further recommendations required."
                else:
                    print("  [SPEED] Deterministic root causes already identified. Skipping extra meta-review AI call.", flush=True)
                    meta_response = (
                        "Deterministic root-cause evidence was sufficient for cycle synthesis, "
                        "so the additional meta-review AI call was skipped."
                    )
            else:
                print(f"Estimated cost: {format_cost(meta_cost)} (meta-review @ {config['model']})", flush=True)
                meta_response = lib_ai.run_ai_completion(
                    config['provider'],
                    config['model'],
                    meta_prompt,
                    context_files=[],
                    prompt_sections=[{
                        'label': 'meta_review_prompt',
                        'content': meta_prompt,
                        'required': True,
                        'loss_policy': 'chunkable',
                        'section_type': 'meta_review',
                    }],
                    agent_name='inspeqtor',
                    task_type='review',
                    output_tokens=2000,
                    include_previous_log=False,
                )

            final_content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v{RUNTIME_VERSION} (Multi-Stage Review: Qonfirmer > Qualifier > AI)

## Structured Verdict

- Assessment: {overall_assessment}
- Deterministic Gate: {inspection_verdict['deterministic_gate']}
- Evidence Status: {inspection_verdict['evidence_status']}
- Confidence: {inspection_verdict['confidence']}
- Inspection Integrity: {inspection_verdict.get('inspection_integrity', 'COMPLETE')}
- Validation Bundle: `validation/validation-bundle.v1.json`
- Realization Bundle: `realization/realization-bundle.v1.json`
- Inspection Input Contract: `verdict/inspection-input.v1.json`
- Inspection Verdict: `verdict/inspection-verdict.v1.json`
- Inspection Runtime: `verdict/inspection-runtime.v1.json`

## Completion Criteria Judgment
"""

            for item in inspection_verdict.get('completion_criteria_results', []):
                final_content += f"\n- {item['status']}: {item['criterion']}"

            # v1.3.9: Add Deterministic Root Causes to ReQap
            if deterministic_root_causes:
                final_content += "\n\n## Deterministic Root Cause Analysis\n"
                final_content += "The following high-confidence blockers were identified:\n"
                for rc in sorted(set(deterministic_root_causes)):
                    final_content += f"- {rc}\n"

            if inspection_verdict.get("inspection_substep_failures"):
                final_content += "\n\n## Inspection Runtime Notes\n"
                final_content += "The inspection pipeline ran in degraded mode; substep failures were captured explicitly.\n"
                for failure in inspection_verdict.get("inspection_substep_failures", []):
                    final_content += f"- {failure.get('substep')}: {failure.get('error')}\n"

            final_content += f"""

## AI Inspection Synthesis

{meta_response}

---
"""

            if qonfirmer_report and qonfirmer_report.violations:
                final_content += "\n## Qonfirmer Violations\n"
                for v in qonfirmer_report.violations:
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
            mark_substep_failure(inspection_substep_failures, "meta_review", e, recoverable=True)
            inspection_verdict["inspection_integrity"] = "DEGRADED"
            inspection_verdict["inspection_substep_failures"] = inspection_substep_failures
            write_json(
                worqspace_root / "verdict" / "inspection-runtime.v1.json",
                {
                    "schema_version": "inspection-runtime.v1",
                    "run_id": canonical_run_id(worqspace_root),
                    "cycle": int(cycle_num),
                    "stage": "INSPECTION",
                    "status": "DEGRADED",
                    "failed_substeps": inspection_substep_failures,
                    "created_at": now_utc(),
                },
            )
            write_json(worqspace_root / "verdict" / "inspection-verdict.v1.json", inspection_verdict)
            _write_fallback_reqap(
                reqap_path, cycle_num, overall_assessment, e,
                success_count, partial_count, failure_count,
                qonfirmer_report, verification_results,
                cross_briq_warnings, failed_briq_suggestions,
                validation_bundle, realization_bundle, inspection_verdict
            )

    print(f"\nInspection verdict complete: {overall_assessment}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (v1.3.0)
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


def _write_qonfirmer_only_reqap(
    reqap_path: Path, cycle_num: str, qonfirmer_report, verification_results,
    overall_assessment: str, qontract_content: str,
    validation_bundle: dict, realization_bundle: dict, inspection_verdict: dict
):
    """Write a reqap when AI review was skipped due to Qonfirmer failure."""
    content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v{RUNTIME_VERSION} (Qonfirmer-Only Mode — AI review skipped due to contract failure)

## Assessment: {overall_assessment}

## Structured Verdict

- Deterministic Gate: {inspection_verdict['deterministic_gate']}
- Evidence Status: {inspection_verdict['evidence_status']}
- Confidence: {inspection_verdict['confidence']}
- Inspection Integrity: {inspection_verdict.get('inspection_integrity', 'COMPLETE')}
- Validation Bundle: `validation/validation-bundle.v1.json`
- Realization Bundle: `realization/realization-bundle.v1.json`
- Inspection Verdict: `verdict/inspection-verdict.v1.json`
- Inspection Runtime: `verdict/inspection-runtime.v1.json`

**AI review skipped due to contract failure.** The Qonfirmer detected violations that must
be fixed before AI review can provide meaningful feedback.

"""
    if qonfirmer_report and qonfirmer_report.violations:
        content += "## Qonfirmer Violations (MUST FIX)\n\n"
        for v in qonfirmer_report.violations:
            content += f"- {v}\n"
        content += "\n"

    if verification_results and hasattr(verification_results, 'errors') and verification_results.errors > 0:
        content += _format_verification_section(verification_results)

    content += "\n## Completion Criteria Judgment\n\n"
    for item in inspection_verdict.get('completion_criteria_results', []):
        content += f"- {item['status']}: {item['criterion']}\n"

    if inspection_verdict.get("inspection_substep_failures"):
        content += "\n## Inspection Runtime Notes\n\n"
        for failure in inspection_verdict.get("inspection_substep_failures", []):
            content += f"- {failure.get('substep')}: {failure.get('error')}\n"

    if realization_bundle.get('unknowns'):
        content += "\n## Unknowns / Blind Spots\n\n"
        for item in realization_bundle['unknowns']:
            content += f"- {item}\n"

    content += "\n## Next Steps\n\n"
    content += "1. Fix all Qonfirmer violations listed above\n"
    content += "2. Ensure code passes local syntax verification\n"
    content += "3. Re-run the cycle to get full AI review\n"

    os.makedirs(reqap_path.parent, exist_ok=True)
    with open(reqap_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"ReQap (qonfirmer-only): {reqap_path}", flush=True)


def _write_fallback_reqap(
    reqap_path: Path, cycle_num: str, overall_assessment: str, error,
    success_count: int, partial_count: int, failure_count: int,
    qonfirmer_report, verification_results,
    cross_briq_warnings: list, failed_briq_suggestions: list,
    validation_bundle: dict, realization_bundle: dict, inspection_verdict: dict
):
    """Write a fallback reqap when meta-review AI call fails."""
    fallback_content = f"""# CyQle {cycle_num} Final ReQap
Generated by InspeQtor v{RUNTIME_VERSION} (Fallback Mode - Meta-review failed)

Assessment: {overall_assessment}

## Structured Verdict

- Deterministic Gate: {inspection_verdict['deterministic_gate']}
- Evidence Status: {inspection_verdict['evidence_status']}
- Confidence: {inspection_verdict['confidence']}
- Inspection Integrity: {inspection_verdict.get('inspection_integrity', 'COMPLETE')}
- Validation Bundle: `validation/validation-bundle.v1.json`
- Realization Bundle: `realization/realization-bundle.v1.json`
- Inspection Verdict: `verdict/inspection-verdict.v1.json`
- Inspection Runtime: `verdict/inspection-runtime.v1.json`

## Summary
Meta-review failed with error: {error}

Per-briq results: Success: {success_count} | Partial: {partial_count} | Failure: {failure_count}

"""
    if qonfirmer_report and qonfirmer_report.violations:
        fallback_content += "## Qonfirmer Violations\n"
        for v in qonfirmer_report.violations:
            fallback_content += f"- {v}\n"
        fallback_content += "\n"

    if verification_results and hasattr(verification_results, 'errors') and verification_results.errors > 0:
        fallback_content += _format_verification_section(verification_results)

    if cross_briq_warnings:
        fallback_content += "## Cross-Briq Integration Points\n"
        for warning in cross_briq_warnings:
            fallback_content += f"- {warning}\n"
        fallback_content += "\n"

    fallback_content += "## Completion Criteria Judgment\n"
    for item in inspection_verdict.get('completion_criteria_results', []):
        fallback_content += f"- {item['status']}: {item['criterion']}\n"
    fallback_content += "\n"

    if inspection_verdict.get("inspection_substep_failures"):
        fallback_content += "## Inspection Runtime Notes\n"
        for failure in inspection_verdict.get("inspection_substep_failures", []):
            fallback_content += f"- {failure.get('substep')}: {failure.get('error')}\n"
        fallback_content += "\n"

    if realization_bundle.get('unknowns'):
        fallback_content += "## Unknowns / Blind Spots\n"
        for item in realization_bundle['unknowns']:
            fallback_content += f"- {item}\n"
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

## Qualification Results

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
