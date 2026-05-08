from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

try:
    from .shellscript_validation import (
        detect_unsafe_commands,
        pick_shell_mode,
        validate_run_sh_contract,
    )
except Exception:
    from shellscript_validation import (  # type: ignore
        detect_unsafe_commands,
        pick_shell_mode,
        validate_run_sh_contract,
    )

try:
    from .path_hygiene import is_infra_path
except Exception:
    def is_infra_path(path_hint: str) -> bool:  # type: ignore
        rel = str(path_hint or "").strip().replace("\\", "/")
        if not rel:
            return False
        parts = [part for part in rel.split("/") if part]
        blocked = {
            "build",
            "attempts",
            "validation-root",
            "recovery",
            "staging",
            "reqap.d",
            ".qonqrete",
            "qonstructions",
            "struqture",
            "exeq.d",
            "qontext.d",
            "bloq.d",
            "tasq.d",
            "briq.d",
            "qontract.d",
            "qache.d",
            "planning",
            "task",
            "validation",
            "realization",
            "verdict",
            "audit",
            "__pycache__",
        }
        return any(part in blocked for part in parts)

try:
    from .smoqetester.python_bootstrap import provision_validation_env
except Exception:
    try:
        from smoqetester.python_bootstrap import provision_validation_env  # type: ignore
    except Exception:
        provision_validation_env = None  # type: ignore


CONTRACT_SCHEMA_VERSION = "qontract-harness.v2"
RESULT_SCHEMA_VERSION = "harness-result.v2"
CONTRACT_ID = "dynamic_tasq_contract.v2"

CODE_FILE_REQUIRED_MISSING = "FILE_REQUIRED_MISSING"
CODE_FILE_FORBIDDEN_PRESENT = "FILE_FORBIDDEN_PRESENT"
CODE_FILE_EXTRA_PRESENT = "FILE_EXTRA_PRESENT"
CODE_FILE_GLOB_REQUIRED_MISSING = "FILE_GLOB_REQUIRED_MISSING"
CODE_FILE_SCOPE_VIOLATION = "FILE_SCOPE_VIOLATION"
CODE_FILE_EXECUTABLE_BIT_MISMATCH = "FILE_EXECUTABLE_BIT_MISMATCH"
CODE_DELIVERABLE_SET_MISMATCH = "DELIVERABLE_SET_MISMATCH"

CODE_RUNTIME_UNSUPPORTED = "RUNTIME_TYPE_UNSUPPORTED"
CODE_RUNTIME_ENTRY_MISSING = "RUNTIME_ENTRYPOINT_MISSING"
CODE_RUNTIME_ENTRY_AMBIG = "RUNTIME_ENTRYPOINT_AMBIGUOUS"
CODE_RUNTIME_LAUNCH_FAILED = "RUNTIME_LAUNCH_FAILED"
CODE_RUNTIME_PROBE_FAILED = "RUNTIME_PROBE_FAILED"
CODE_RUNTIME_ENV_BLOCKED = "RUNTIME_ENVIRONMENT_BLOCKED"
CODE_STATIC_DOM_FAILED = "STATIC_APP_DOM_CHECK_FAILED"
CODE_STATIC_INTERACTION_FAILED = "STATIC_APP_INTERACTION_FAILED"
CODE_STATIC_PERSISTENCE_FAILED = "STATIC_APP_PERSISTENCE_FAILED"
CODE_STATIC_EXTERNAL_FORBIDDEN = "STATIC_APP_EXTERNAL_ASSET_FORBIDDEN"
CODE_STATIC_REQUIRED_TEXT_MISSING = "STATIC_APP_REQUIRED_TEXT_MISSING"
CODE_STATIC_REQUIRED_CONTROL_MISSING = "STATIC_APP_REQUIRED_CONTROL_MISSING"
CODE_HTTP_PROBE_FAILED = "HTTP_PROBE_FAILED"
CODE_CLI_PROBE_FAILED = "CLI_PROBE_FAILED"
CODE_FILE_OUTPUT_PROBE_FAILED = "FILE_OUTPUT_PROBE_FAILED"

CODE_SHELL_REQUIRED_MISSING = "SHELLSCRIPT_REQUIRED_MISSING"
CODE_SHELL_UNEXPECTED_PRESENT = "SHELLSCRIPT_UNEXPECTED_PRESENT"
CODE_SHELL_COMMAND_MISMATCH = "SHELLSCRIPT_COMMAND_MISMATCH"
CODE_SHELL_EXTRA_COMMAND = "SHELLSCRIPT_EXTRA_COMMAND"
CODE_SHELL_FORBIDDEN_COMMAND = "SHELLSCRIPT_FORBIDDEN_COMMAND"
CODE_SHELL_UNSAFE = "SHELLSCRIPT_UNSAFE"
CODE_SHELL_NOT_EXECUTABLE = "SHELLSCRIPT_NOT_EXECUTABLE"

CODE_DEP_MANIFEST_UNEXPECTED = "DEPENDENCY_MANIFEST_UNEXPECTED"
CODE_DEP_MISSING_DECL = "DEPENDENCY_MISSING_DECLARATION"
CODE_DEP_EXTRA_DECL = "DEPENDENCY_EXTRA_DECLARATION"
CODE_DEP_MANAGER_FORBIDDEN = "DEPENDENCY_MANAGER_FORBIDDEN"

CODE_CONTRACT_TASK_HASH_MISMATCH = "CONTRACT_TASK_HASH_MISMATCH"
CODE_CONTRACT_QAGE_MISMATCH = "CONTRACT_QAGE_ID_MISMATCH"
CODE_CONTRACT_STALE = "CONTRACT_STALE_ARTIFACT"
CODE_CONTRACT_UNRELATED_DEFAULTS = "CONTRACT_UNRELATED_DEFAULTS_DETECTED"
CODE_VALIDATION_PLAN_STALE = "VALIDATION_PLAN_STALE"
CODE_HARNESS_RESULT_STALE = "HARNESS_RESULT_STALE"
CODE_REPAIR_HISTORY_STALE = "REPAIR_HISTORY_STALE"
CODE_STALE_INVALIDATED = "STALE_ARTIFACT_INVALIDATED"


def _runtime_version() -> str:
    env_version = str(os.environ.get("QONQ_VERSION", "")).strip()
    if env_version:
        return env_version
    try:
        return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "?.?.?"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_qage_id(*, worqspace_root: Path | None = None, qodeyard: Path | None = None) -> str:
    for env_key in ("QONQ_RUN_ID", "QONQ_RUN_NAME", "QONSTRUCTION_NAME"):
        raw = str(os.environ.get(env_key, "")).strip()
        if raw:
            return Path(raw).name

    candidates: list[str] = []
    if worqspace_root is not None:
        candidates.append(str(worqspace_root.name))
    if qodeyard is not None:
        candidates.append(str(qodeyard.parent.name))

    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        if text.lower() in {"qonq", "worqspace", "workspace"}:
            continue
        return text

    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return "unknown-run"


def _normalize_rel_path(value: str | Path | None) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("qodeyard/"):
        text = text[len("qodeyard/"):]
    return text.strip()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _discover_task_source(worqspace_root: Path | None) -> tuple[str, str, str]:
    """
    Returns (source_tasq_path, source_tasq_text, source_tasq_hash).
    """
    if worqspace_root is None:
        return "", "", ""

    candidates: list[Path] = []
    task_spec = _load_json(worqspace_root / "task" / "task-spec.v1.json")
    for row in task_spec.get("inputs", []) if isinstance(task_spec.get("inputs"), list) else []:
        if not isinstance(row, dict):
            continue
        src = row.get("source_ref")
        if isinstance(src, str) and src.strip():
            candidates.append(Path(src.strip()))

    tasq_dir = worqspace_root / "tasq.d"
    if tasq_dir.exists():
        candidates.extend(sorted(tasq_dir.glob("cyqle*_tasq.md")))
    candidates.extend([
        worqspace_root / "tasq.md",
        worqspace_root / "task" / "task.md",
        worqspace_root / "task" / "task_input.md",
    ])

    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        text = _read_text(path)
        if not text.strip():
            continue
        return str(path), text, sha256_text(text)

    return "", "", ""


def _extract_marked_block_items(task_text: str, trigger_patterns: list[str]) -> list[str]:
    rows: list[str] = []
    in_block = False
    for raw in task_text.splitlines():
        line = raw.rstrip("\n")
        lower = line.strip().lower()
        if any(pattern in lower for pattern in trigger_patterns):
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            if re.match(r"^[A-Za-z][A-Za-z0-9 _-]+:\s*$", stripped):
                break
            if not re.match(r"^[-*]|^\d+\.", stripped):
                # stop when we leave bullet/numbered context
                break
            cleaned = re.sub(r"^[-*]\s*", "", stripped)
            cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
            cleaned = cleaned.strip().strip("`\"'")
            if cleaned:
                rows.append(cleaned)
    return rows


def _looks_like_file(candidate: str) -> bool:
    text = _normalize_rel_path(candidate)
    if not text:
        return False
    if text.startswith("../") or text.startswith("/"):
        return False
    if is_infra_path(text):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)+", text):
        return False
    if ":" in text and "/" not in text:
        return False
    if text in {"Dockerfile", "Makefile"}:
        return True
    if "/" in text:
        parts = [part for part in text.split("/") if part]
        if not parts:
            return False
        return all(re.match(r"^[A-Za-z0-9_.-]+$", part) for part in parts)
    return bool(re.match(r"^[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,12}$", text))


def _extract_required_files(task_text: str) -> tuple[list[str], bool, list[dict], list[str]]:
    reasons: list[dict] = []
    ambiguities: list[str] = []
    required: list[str] = []
    forbidden_line_markers = (
        "do not add",
        "don't add",
        "do not include",
        "don't include",
        "must not add",
        "must not include",
        "forbidden",
        "no extra file",
        "extra files",
        "unexpected file",
    )

    explicit = _extract_marked_block_items(
        task_text,
        [
            "must contain exactly these files",
            "project must contain exactly these files",
            "repo root contains",
            "the repo root contains",
            "required files",
        ],
    )
    for item in explicit:
        if _looks_like_file(item):
            required.append(_normalize_rel_path(item))

    file_token_re = re.compile(
        r"(?<![\w/])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,12}|Dockerfile|Makefile)(?![\w/])"
    )
    for raw_line in task_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(marker in lower for marker in forbidden_line_markers):
            continue
        for candidate in re.findall(r"`([^`]+)`", line):
            if _looks_like_file(candidate):
                required.append(_normalize_rel_path(candidate))
        for match in file_token_re.finditer(line):
            token = _normalize_rel_path(match.group(1))
            if _looks_like_file(token):
                required.append(token)

    required = sorted({item for item in required if item})

    strict_scope_mode = bool(
        re.search(r"must\s+contain\s+exactly\s+these\s+files", task_text, flags=re.IGNORECASE)
        or re.search(r"\bno\s+extra\s+files\b", task_text, flags=re.IGNORECASE)
        or re.search(r"\bonly\s+implement\s+what\s+is\s+explicitly\s+described\b", task_text, flags=re.IGNORECASE)
        or re.search(r"\bif\s+something\s+is\s+not\s+specified,\s*do\s+not\s+invent\s+it\b", task_text, flags=re.IGNORECASE)
        or re.search(r"\bstay\s+strictly\s+within\s+the\s+defined\s+contract\b", task_text, flags=re.IGNORECASE)
        or re.search(r"\bno\s+additional\s+frameworks\b", task_text, flags=re.IGNORECASE)
        or re.search(r"\bno\s+extra\s+frameworks\b", task_text, flags=re.IGNORECASE)
    )
    exact_mode = bool(required and strict_scope_mode)

    if required:
        reasons.append(
            {
                "rule_id": "file.required_files",
                "reason": "Task text explicitly lists required files.",
                "confidence": 0.97 if explicit else 0.82,
            }
        )
    else:
        ambiguities.append("No explicit deliverable file list was extracted from task text.")

    if exact_mode:
        reasons.append(
            {
                "rule_id": "file.allowed_only_files",
                "reason": "Task text requests exact file scope and forbids extras.",
                "confidence": 0.95,
            }
        )

    return required, exact_mode, reasons, ambiguities


def _extract_local_storage_keys(task_text: str) -> tuple[list[str], bool]:
    if "localstorage" not in task_text.lower():
        return [], False
    keys = _extract_marked_block_items(task_text, ["localstorage", "storage keys"])
    out: list[str] = []
    for item in keys:
        cleaned = item.strip().strip("`\"'")
        if cleaned:
            out.append(cleaned)
    exact = bool(re.search(r"exactly\s+these\s+keys", task_text, flags=re.IGNORECASE))
    return sorted(set(out)), exact


def _extract_exact_launch_command(task_text: str) -> str | None:
    """Extract a launcher command after exact/exectly launch wording."""
    text = str(task_text or "")
    patterns = [
        r"launch\s+ex[ae]ctly[^:]*:\s*([^\n]+)",
        r"launch\s+exact\s+command\s*:?\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            command = match.group(1).strip().strip("`")
            # Task prose often appends clarification after the literal command,
            # for example: "... --port $PORT (same port value ...)".
            # Keep that prose out of the exact shell command contract.
            command = re.sub(r"\s+\([^)]*\)\s*$", "", command).strip()
            if command:
                return command
    return None


def _extract_exact_field_set(task_text: str) -> dict[str, list[str]]:
    model_fields: dict[str, list[str]] = {}
    pattern = re.compile(
        r"(?:each\s+stored\s+([A-Za-z_][A-Za-z0-9_\- ]*)\s+must\s+contain\s+exactly\s+these\s+fields|([A-Za-z_][A-Za-z0-9_\- ]*)\s+must\s+contain\s+exactly\s+these\s+fields)",
        flags=re.IGNORECASE,
    )
    lines = task_text.splitlines()
    for idx, raw in enumerate(lines):
        match = pattern.search(raw)
        if not match:
            continue
        model = (match.group(1) or match.group(2) or "model").strip().lower().replace(" ", "_")
        fields: list[str] = []
        for follow in lines[idx + 1:]:
            stripped = follow.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            if not re.match(r"^[-*]|^\d+\.", stripped):
                break
            cleaned = re.sub(r"^[-*]\s*", "", stripped)
            cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
            cleaned = cleaned.strip().strip("`\"'")
            if cleaned:
                fields.append(cleaned)
        if fields:
            model_fields[model] = sorted(dict.fromkeys(fields))
    return model_fields


def _extract_runtime_rules(task_text: str, required_files: list[str]) -> tuple[list[dict], list[dict], list[str]]:
    reasons: list[dict] = []
    ambiguities: list[str] = []
    runtime: list[dict] = []

    lowered = task_text.lower()
    required_ext = {Path(path).suffix.lower() for path in required_files}
    has_html = any(ext in {".html", ".htm"} for ext in required_ext)
    endpoint_hits = re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s`]+)", task_text, flags=re.IGNORECASE)
    if endpoint_hits:
        if "run.sh" in required_files:
            launch_command = "sh run.sh"
        else:
            launch_command = _extract_exact_launch_command(task_text)

        probes = []
        ready_probe = None
        for method, path in endpoint_hits:
            m = method.upper()
            p = path.strip()
            
            # v1.4.1: Replace common placeholders in path for probing
            if "{user_id}" in p:
                p = p.replace("{user_id}", "1")
            
            payload = None
            if m == "POST" and p == "/users":
                # Sample payload for user creation
                payload = {"username": "testuser", "email": "test@example.com", "password": "password123"}
            elif m == "PUT" and p.startswith("/users/"):
                 payload = {"username": "updateduser", "email": "updated@example.com", "password": "newpassword123"}

            probes.append(
                {
                    "method": m,
                    "path": p,
                    "payload": payload,
                    "expected_status": 201 if m == "POST" else 200,
                }
            )
            if p == "/health" and not ready_probe:
                ready_probe = {"path": "/health", "expected_status": 200}

        def _probe_order(probe: dict) -> tuple[int, str, str]:
            method = str(probe.get("method") or "").upper()
            path = str(probe.get("path") or "")
            if method == "GET" and path == "/health":
                priority = 0
            elif method == "POST" and path == "/users":
                priority = 10
            elif method == "GET" and path == "/users":
                priority = 20
            elif method == "GET" and re.fullmatch(r"/users/\d+", path):
                priority = 30
            elif method in {"PUT", "PATCH"} and re.fullmatch(r"/users/\d+", path):
                priority = 40
            elif method == "DELETE" and re.fullmatch(r"/users/\d+", path):
                priority = 90
            else:
                priority = 50
            return priority, method, path

        probes.sort(key=_probe_order)
        
        if not ready_probe and probes:
            ready_probe = {"path": probes[0]["path"], "expected_status": probes[0]["expected_status"]}

        runtime.append(
            {
                "runtime_type": "http_service",
                "required": True,
                "launch_command": launch_command,
                "ready_probe": ready_probe,
                "probes": probes,
            }
        )
        reasons.append(
            {
                "rule_id": "runtime.http_service",
                "reason": "HTTP endpoint declarations were extracted from task text.",
                "confidence": 0.88,
            }
        )

    if has_html and not endpoint_hits:
        entry_candidates = [path for path in required_files if Path(path).suffix.lower() in {".html", ".htm"}]
        entrypoint = entry_candidates[0] if len(entry_candidates) == 1 else None
        required_text = []
        for match in re.finditer(r":\s*`([^`]+)`", task_text):
            text = match.group(1).strip()
            if text and len(text) <= 140:
                required_text.append(text)
        required_text = sorted(dict.fromkeys(required_text))

        control_hints = []
        control_keywords = ["input", "textarea", "button", "select", "toggle", "form", "grid", "area"]
        for item in _extract_marked_block_items(task_text, ["the page must include", "layout"]):
            candidate = item.strip()
            if not candidate:
                continue
            quoted = [token.strip() for token in re.findall(r"`([^`]+)`", candidate) if token.strip()]
            if quoted:
                control_hints.extend(quoted)
                continue
            lowered_candidate = candidate.lower()
            for keyword in control_keywords:
                if keyword in lowered_candidate:
                    control_hints.append(keyword)
                    break

        storage_keys, storage_exact = _extract_local_storage_keys(task_text)

        runtime.append(
            {
                "runtime_type": "static_browser_app",
                "required": True,
                "entrypoint": entrypoint,
                "entrypoint_candidates": entry_candidates,
                "required_visible_text": required_text,
                "required_controls": sorted(dict.fromkeys(control_hints)),
                "required_storage_keys": storage_keys,
                "storage_keys_exact": storage_exact,
                "forbid_external_network": bool(re.search(r"no\s+external\s+network\s+requests", lowered)),
                "forbid_external_assets": bool(
                    re.search(r"do\s+not\s+use\s+external\s+libraries", lowered)
                    or re.search(r"do\s+not\s+use\s+external\s+assets", lowered)
                    or re.search(r"no\s+external\s+libraries", lowered)
                ),
                "interaction_requirements": [
                    line.strip()
                    for line in _extract_marked_block_items(
                        task_text,
                        [
                            "interaction requirements",
                            "behavior requirements",
                            "acceptance criteria",
                            "user interactions",
                        ],
                    )
                ],
            }
        )

        reasons.append(
            {
                "rule_id": "runtime.static_browser_app",
                "reason": "Deliverable file set indicates a static browser application.",
                "confidence": 0.92,
            }
        )
        if not entrypoint:
            ambiguities.append("Static app entrypoint is ambiguous because multiple HTML candidates were detected.")

    if not runtime:
        runtime.append({"runtime_type": "no_runtime_required", "required": False})
        reasons.append(
            {
                "rule_id": "runtime.none",
                "reason": "No explicit runtime requirements were extracted.",
                "confidence": 0.74,
            }
        )

    return runtime, reasons, ambiguities


def _extract_shell_rules(task_text: str, required_files: list[str]) -> tuple[list[dict], list[dict], list[str]]:
    reasons: list[dict] = []
    ambiguities: list[str] = []
    rules: list[dict] = []

    shell_files = [path for path in required_files if Path(path).suffix.lower() in {".sh", ".bash", ".zsh", ".ksh"}]
    if not shell_files:
        return rules, reasons, ambiguities

    exact_cmd = None
    exact_cmd = _extract_exact_launch_command(task_text)

    for rel in shell_files:
        command_policy: dict = {
            "allow_wrapper": exact_cmd is None,
            "allowed_boilerplate": ["set", "export"],
            "forbidden_command_patterns": detect_unsafe_commands(""),
        }
        if exact_cmd:
            command_policy["exact_command_required"] = exact_cmd
        if "$PORT" in task_text or "${PORT}" in task_text:
            command_policy["required_variables"] = ["PORT"]

        rules.append(
            {
                "path": rel,
                "required": True,
                "executable_required": bool(re.search(r"\bexecutable\b", task_text, flags=re.IGNORECASE)),
                "command_policy": command_policy,
                "shebang_policy": "optional",
            }
        )

    reasons.append(
        {
            "rule_id": "shellscript.rules",
            "reason": "Shellscript deliverables were explicitly listed in task text.",
            "confidence": 0.89,
        }
    )

    return rules, reasons, ambiguities


def _extract_dependency_rules(task_text: str, required_files: list[str]) -> tuple[dict, list[dict], list[str]]:
    reasons: list[dict] = []
    ambiguities: list[str] = []
    lowered = task_text.lower()

    manifests = {
        "requirements.txt": "pip",
        "package.json": "npm",
        "pyproject.toml": "python-packaging",
    }
    managers_forbidden: list[str] = []
    manifest_forbidden = False

    if re.search(r"no\s+package\s+manager", lowered):
        managers_forbidden.extend(["npm", "pnpm", "yarn", "pip"])
        manifest_forbidden = True
        reasons.append(
            {
                "rule_id": "dependency.manager_forbidden",
                "reason": "Task text forbids package-manager/build-tool flows.",
                "confidence": 0.95,
            }
        )

    required_dependencies: list[str] = []
    req_rows = _extract_marked_block_items(task_text, ["include requirements.txt with", "requirements.txt with", "dependencies"])
    for row in req_rows:
        token = row.strip().strip("`\"'")
        if token and re.match(r"^[A-Za-z0-9_.-]+$", token):
            required_dependencies.append(token)

    lines = task_text.splitlines()
    for index, raw in enumerate(lines):
        lower = raw.strip().lower()
        if "requirements.txt" not in lower or "with" not in lower:
            continue
        for follow in lines[index + 1:]:
            stripped = follow.strip()
            if not stripped:
                if required_dependencies:
                    break
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9 _/-]+:\s*$", stripped):
                break
            cleaned = re.sub(r"^[-*]\s*", "", stripped)
            cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
            cleaned = cleaned.strip().strip("`\"'")
            if re.match(r"^[A-Za-z0-9_.-]+$", cleaned):
                required_dependencies.append(cleaned)
                continue
            break

    if required_dependencies:
        reasons.append(
            {
                "rule_id": "dependency.required_packages",
                "reason": "Dependency list extracted from explicit task dependency section.",
                "confidence": 0.84,
            }
        )

    required_managers = sorted({
        manifests[path]
        for path in required_files
        if path in manifests
    })
    strict_dependency_scope = bool(
        re.search(r"\bno\s+additional\s+frameworks\b", lowered)
        or re.search(r"\bno\s+extra\s+frameworks\b", lowered)
        or re.search(r"\bavoid\s+introducing\s+new\s+external\s+dependencies\b", lowered)
        or re.search(r"\bdo\s+not\s+(?:add|introduce)\s+(?:new\s+)?(?:external\s+)?dependencies\b", lowered)
    )

    dependency_rules = {
        "required_dependencies": sorted(dict.fromkeys(required_dependencies)),
        "forbidden_dependencies": [],
        "required_managers": required_managers,
        "forbidden_managers": sorted(set(managers_forbidden)),
        "forbid_manifests": manifest_forbidden,
        "allowed_manifests": sorted(path for path in required_files if path in manifests),
        "allow_unspecified_dependencies": not bool(required_dependencies) and not strict_dependency_scope,
    }

    if not required_dependencies and not required_managers and not manifest_forbidden:
        ambiguities.append("Task does not explicitly define dependency declarations; dependency checks stay minimal.")

    return dependency_rules, reasons, ambiguities


def _extract_scope_rules(task_text: str) -> tuple[list[str], list[dict]]:
    scope_rules: list[str] = []
    reasons: list[dict] = []
    for item in _extract_marked_block_items(task_text, ["strict scope", "scope rules"]):
        cleaned = item.strip()
        if cleaned:
            scope_rules.append(cleaned)
    if scope_rules:
        reasons.append(
            {
                "rule_id": "scope.strict_rules",
                "reason": "Strict scope directives extracted from task text.",
                "confidence": 0.88,
            }
        )
    return sorted(dict.fromkeys(scope_rules)), reasons


def _build_static_rules(contract: dict) -> list[dict]:
    static_rules: list[dict] = []
    file_rules = contract.get("file_rules", {}) if isinstance(contract.get("file_rules"), dict) else {}
    required_files = [
        _normalize_rel_path(item)
        for item in file_rules.get("required_files", []) if _normalize_rel_path(item)
    ]
    runtime_checks = contract.get("runtime_checks", []) if isinstance(contract.get("runtime_checks"), list) else []

    html_files = [path for path in required_files if Path(path).suffix.lower() in {".html", ".htm"}]
    js_files = [path for path in required_files if Path(path).suffix.lower() == ".js"]
    css_files = [path for path in required_files if Path(path).suffix.lower() == ".css"]
    py_files = [path for path in required_files if Path(path).suffix.lower() == ".py"]

    for path in py_files:
        static_rules.append({"type": "parse_python_ast", "file": path, "required": True})
    for path in js_files:
        static_rules.append({"type": "parse_js_syntax", "file": path, "required": True})
    for path in css_files:
        static_rules.append({"type": "parse_css_basic", "file": path, "required": True})
    for path in html_files:
        static_rules.append({"type": "parse_html_basic", "file": path, "required": True})

    for runtime in runtime_checks:
        if not isinstance(runtime, dict):
            continue
        if runtime.get("runtime_type") != "static_browser_app":
            continue
        entrypoint = _normalize_rel_path(runtime.get("entrypoint"))
        if entrypoint:
            required_text = runtime.get("required_visible_text") if isinstance(runtime.get("required_visible_text"), list) else []
            if required_text:
                static_rules.append(
                    {
                        "type": "html_required_text",
                        "file": entrypoint,
                        "required": True,
                        "text": [str(item) for item in required_text if str(item).strip()],
                    }
                )
            required_controls = runtime.get("required_controls") if isinstance(runtime.get("required_controls"), list) else []
            if required_controls:
                static_rules.append(
                    {
                        "type": "html_required_controls",
                        "file": entrypoint,
                        "required": True,
                        "controls": [str(item) for item in required_controls if str(item).strip()],
                    }
                )
        keys = runtime.get("required_storage_keys") if isinstance(runtime.get("required_storage_keys"), list) else []
        if keys and js_files:
            static_rules.append(
                {
                    "type": "storage_keys_exact",
                    "files": js_files,
                    "required": True,
                    "keys": [str(item) for item in keys if str(item).strip()],
                    "exact": bool(runtime.get("storage_keys_exact", False)),
                }
            )

    data_models = contract.get("behavior_checks", {}).get("exact_model_fields", {}) if isinstance(contract.get("behavior_checks"), dict) else {}
    if isinstance(data_models, dict) and data_models and js_files:
        static_rules.append(
            {
                "type": "data_model_exact_fields",
                "files": js_files,
                "required": False,
                "models": data_models,
            }
        )

    return static_rules


def _build_contract(task_text: str, *, worqspace_root: Path | None = None, source_tasq_path: str | None = None) -> dict:
    task_hash = sha256_text(task_text)
    source_path, source_text, source_hash = _discover_task_source(worqspace_root)
    if source_tasq_path:
        candidate = Path(source_tasq_path)
        if candidate.exists():
            source_path = str(candidate)
            source_text = _read_text(candidate)
            source_hash = sha256_text(source_text) if source_text else ""

    qage_id = _canonical_qage_id(worqspace_root=worqspace_root)

    required_files, exact_only, file_reasons, file_ambiguities = _extract_required_files(task_text)
    runtime_checks, runtime_reasons, runtime_ambiguities = _extract_runtime_rules(task_text, required_files)
    shell_checks, shell_reasons, shell_ambiguities = _extract_shell_rules(task_text, required_files)
    dep_rules, dep_reasons, dep_ambiguities = _extract_dependency_rules(task_text, required_files)
    scope_rules, scope_reasons = _extract_scope_rules(task_text)

    forbidden_files: list[str] = []
    if re.search(r"no\s+readme", task_text, flags=re.IGNORECASE):
        forbidden_files.extend(["README", "README.md"])

    forbidden_globs: list[str] = []
    lowered = task_text.lower()
    if "no typescript" in lowered:
        forbidden_globs.extend(["*.ts", "*.tsx"])
    if "no backend" in lowered:
        forbidden_globs.extend(["*.py", "*.rb", "*.go", "*.java"])

    allowed_only = required_files if exact_only and required_files else []

    local_storage_keys, local_storage_exact = _extract_local_storage_keys(task_text)
    model_fields = _extract_exact_field_set(task_text)

    behavior_checks = {
        "local_storage_keys": local_storage_keys,
        "local_storage_exact": local_storage_exact,
        "exact_model_fields": model_fields,
    }

    contract = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "generated_at": now_utc(),
        "tool_version": _runtime_version(),
        "strictness": "strict" if exact_only else "balanced",
        "task_identity": {
            "qage_id": qage_id,
            "source_tasq_path": source_path,
            "source_tasq_hash": source_hash,
            "task_hash": task_hash,
        },
        "file_rules": {
            "required_files": required_files,
            "forbidden_files": sorted(set(forbidden_files)),
            "allowed_only_files": allowed_only,
            "allowed_globs": [],
            "forbidden_globs": sorted(set(forbidden_globs)),
            "optional_files": [],
            "generated_artifacts": [],
            "exclude_hidden_from_deliverables": True,
            "exclude_system_artifacts": True,
            "readme_policy": "forbidden" if any(name.lower().startswith("readme") for name in forbidden_files) else "allowed",
        },
        "dependency_rules": dep_rules,
        "shellscript_checks": shell_checks,
        "runtime_checks": runtime_checks,
        "behavior_checks": behavior_checks,
        "scope_rules": scope_rules,
        "ambiguity_notes": sorted(set(file_ambiguities + runtime_ambiguities + shell_ambiguities + dep_ambiguities)),
        "rule_reasons": file_reasons + runtime_reasons + shell_reasons + dep_reasons + scope_reasons,
    }

    contract["static_checks"] = _build_static_rules(contract)
    contract["task_identity"]["contract_hash"] = _compute_contract_hash(contract)

    # Safety signal to prevent unrelated default carryover.
    if source_text and required_files:
        mentioned = 0
        lower_source = source_text.lower()
        for item in required_files:
            if Path(item).name.lower() in lower_source or item.lower() in lower_source:
                mentioned += 1
        if mentioned < len(required_files):
            contract.setdefault("ambiguity_notes", []).append(
                "Some required files were inferred without explicit exact mention; review contract confidence before treating as strict pass gate."
            )

    return contract


def _compute_contract_hash(contract: dict) -> str:
    payload = json.loads(json.dumps(contract))
    if isinstance(payload.get("task_identity"), dict):
        payload["task_identity"].pop("contract_hash", None)
    payload.pop("generated_at", None)
    payload.pop("tool_version", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)


def detect_harness_class(task_text: str) -> str | None:
    del task_text
    return CONTRACT_ID


def build_harness(task_text: str, existing_qontract: dict | None = None, *, worqspace_root: Path | None = None, source_tasq_path: str | None = None) -> dict:
    del existing_qontract
    return _build_contract(task_text, worqspace_root=worqspace_root, source_tasq_path=source_tasq_path)


def write_harness(worqspace_root: Path, harness: dict) -> None:
    qontract_dir = worqspace_root / "qontract.d"
    qontract_dir.mkdir(parents=True, exist_ok=True)
    with open(qontract_dir / "qontract-harness.v1.json", "w", encoding="utf-8") as f:
        json.dump(harness, f, indent=2)
        f.write("\n")
    with open(qontract_dir / "qontract-harness.md", "w", encoding="utf-8") as f:
        f.write(render_harness_markdown(harness))


def load_harness(worqspace_root: Path) -> dict:
    p = worqspace_root / "qontract.d" / "qontract-harness.v1.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def apply_autofixes(qodeyard: Path, harness: dict) -> dict:
    del qodeyard, harness
    return {"autofixes_applied": []}


@dataclass
class HarnessIssue:
    code: str
    message: str
    severity: str = "error"
    file: str | None = None
    expected: str | None = None
    actual: str | None = None
    details: dict | None = None

    def to_dict(self) -> dict:
        payload = {
            "rule_id": self.code,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.file:
            payload["file"] = self.file
        if self.expected is not None:
            payload["expected"] = self.expected
        if self.actual is not None:
            payload["actual"] = self.actual
        if self.details:
            payload.update(self.details)
        return payload


def _make_result_template(harness: dict, qodeyard: Path) -> dict:
    identity = harness.get("task_identity", {}) if isinstance(harness.get("task_identity"), dict) else {}
    current_qage_id = _canonical_qage_id(qodeyard=qodeyard)
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "harness_schema_version": str(harness.get("schema_version") or ""),
        "harness_id": str(harness.get("contract_id") or harness.get("harness_id") or CONTRACT_ID),
        "generated_at": now_utc(),
        "status": "PASS",
        "passed": True,
        "verdict_classification": "PASS",
        "artifact_identity": {
            "qage_id": str(identity.get("qage_id") or current_qage_id),
            "source_tasq_path": str(identity.get("source_tasq_path") or ""),
            "source_tasq_hash": str(identity.get("source_tasq_hash") or ""),
            "task_hash": str(identity.get("task_hash") or ""),
            "contract_hash": str(identity.get("contract_hash") or _compute_contract_hash(harness if isinstance(harness, dict) else {})),
            "tool_version": _runtime_version(),
            "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        },
        "checks": {
            "artifact_binding": {"status": "PASS", "issues": []},
            "files": {"status": "PASS", "issues": []},
            "static": {"status": "PASS", "issues": []},
            "dependency": {"status": "PASS", "issues": []},
            "shellscript": {"status": "PASS", "issues": []},
            "runtime": {"status": "PASS", "issues": []},
        },
        "violations": [],
        "repair_directive": "",
        "completion_override": {
            "allowed": True,
            "task_completed": True,
            "repair_required": False,
            "evidence_status": "EVIDENCE_COMPLETE",
        },
    }


def _append_issue(result: dict, section: str, issue: HarnessIssue) -> None:
    row = issue.to_dict()
    result["violations"].append(row)
    result["checks"][section]["issues"].append(row)


def _finalize_result(result: dict) -> dict:
    errors = [row for row in result.get("violations", []) if str(row.get("severity", "error")).lower() == "error"]
    blocking_codes = {
        CODE_RUNTIME_UNSUPPORTED,
        CODE_RUNTIME_ENV_BLOCKED,
    }
    has_blocked_required = any(row.get("code") in blocking_codes for row in errors)

    if errors:
        result["passed"] = False
        if has_blocked_required:
            result["status"] = "BLOCKED"
            result["verdict_classification"] = "BLOCKED: required validation is unsupported or environment blocked"
        else:
            result["status"] = "FAIL"
            result["verdict_classification"] = "FAIL: deterministic contract validation failed"
        result["completion_override"]["allowed"] = False
        result["completion_override"]["task_completed"] = False
        result["completion_override"]["repair_required"] = True
        result["completion_override"]["evidence_status"] = "EVIDENCE_PARTIAL"
    else:
        result["status"] = "PASS"
        result["passed"] = True
        result["verdict_classification"] = "PASS"

    # Promote section statuses.
    for section in result.get("checks", {}).values():
        if not isinstance(section, dict):
            continue
        section_issues = section.get("issues", [])
        if any(str(item.get("severity", "error")).lower() == "error" for item in section_issues if isinstance(item, dict)):
            section["status"] = "FAIL"

    if not result["passed"]:
        result["repair_directive"] = build_repair_directive(result)
    return result


def _is_hidden_path(rel_path: str) -> bool:
    return any(part.startswith(".") for part in Path(rel_path).parts)


def _collect_deliverable_files(root: Path, *, exclude_hidden: bool, exclude_system: bool) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = _normalize_rel_path(path.relative_to(root).as_posix())
        if not rel:
            continue
        if exclude_hidden and _is_hidden_path(rel):
            continue
        if exclude_system:
            if is_infra_path(rel):
                continue
            if Path(rel).name.lower() in {".ds_store"}:
                continue
            if "__pycache__" in Path(rel).parts:
                continue
        found.append(rel)
    return sorted(found)


def _extract_declared_dependencies(qodeyard: Path) -> set[str]:
    declared: set[str] = set()

    req = qodeyard / "requirements.txt"
    if req.exists():
        for raw in _read_text(req).splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            token = re.split(r"[<>=!~\[\]; ]", line, maxsplit=1)[0].strip()
            if token:
                declared.add(token.lower())

    package_json = qodeyard / "package.json"
    if package_json.exists():
        payload = _load_json(package_json)
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            deps = payload.get(key)
            if isinstance(deps, dict):
                for dep in deps.keys():
                    text = str(dep).strip().lower()
                    if text:
                        declared.add(text)

    return declared


def _validate_artifact_binding(result: dict, qodeyard: Path, harness: dict) -> None:
    identity = harness.get("task_identity", {}) if isinstance(harness.get("task_identity"), dict) else {}
    current_qage = _canonical_qage_id(qodeyard=qodeyard)
    contract_hash = _compute_contract_hash(harness)

    if str(identity.get("qage_id") or "") and str(identity.get("qage_id")) != current_qage:
        _append_issue(
            result,
            "artifact_binding",
            HarnessIssue(
                CODE_CONTRACT_QAGE_MISMATCH,
                "Contract qage id does not match current qage.",
                file="qontract.d/qontract-harness.v1.json",
                expected=current_qage,
                actual=str(identity.get("qage_id")),
            ),
        )

    if str(identity.get("contract_hash") or "") and str(identity.get("contract_hash")) != contract_hash:
        _append_issue(
            result,
            "artifact_binding",
            HarnessIssue(
                CODE_CONTRACT_STALE,
                "Contract hash mismatch indicates stale or mutated harness artifact.",
                file="qontract.d/qontract-harness.v1.json",
                expected=contract_hash,
                actual=str(identity.get("contract_hash")),
            ),
        )

    source_path = str(identity.get("source_tasq_path") or "")
    source_hash = str(identity.get("source_tasq_hash") or "")
    if source_path:
        source_file = Path(source_path)
        if source_file.exists() and source_file.is_file():
            live_hash = sha256_text(_read_text(source_file))
            if source_hash and source_hash != live_hash:
                _append_issue(
                    result,
                    "artifact_binding",
                    HarnessIssue(
                        CODE_CONTRACT_TASK_HASH_MISMATCH,
                        "Task hash mismatch indicates contract is stale for the current tasq source.",
                        file=source_path,
                        expected=live_hash,
                        actual=source_hash,
                    ),
                )
        else:
            _append_issue(
                result,
                "artifact_binding",
                HarnessIssue(
                    CODE_CONTRACT_STALE,
                    "Task source path referenced by contract no longer exists.",
                    file=source_path,
                ),
            )

    required_files = harness.get("file_rules", {}).get("required_files", []) if isinstance(harness.get("file_rules"), dict) else harness.get("required_files", [])
    if isinstance(required_files, list) and required_files and source_path:
        source_text = _read_text(Path(source_path)).lower() if Path(source_path).exists() else ""
        if source_text:
            missing_mentions = [item for item in required_files if Path(str(item)).name.lower() not in source_text and str(item).lower() not in source_text]
            if missing_mentions and len(missing_mentions) == len(required_files):
                _append_issue(
                    result,
                    "artifact_binding",
                    HarnessIssue(
                        CODE_CONTRACT_UNRELATED_DEFAULTS,
                        "Required file set appears unrelated to current task text; stale defaults suspected.",
                        file="qontract.d/qontract-harness.v1.json",
                        actual=", ".join(sorted(str(item) for item in missing_mentions)),
                    ),
                )

    if result["checks"]["artifact_binding"]["issues"]:
        _append_issue(
            result,
            "artifact_binding",
            HarnessIssue(
                CODE_STALE_INVALIDATED,
                "Stale artifact detected and invalidated; deterministic pass cannot proceed.",
            ),
        )


def _validate_files(result: dict, qodeyard: Path, harness: dict) -> None:
    file_rules = harness.get("file_rules", {}) if isinstance(harness.get("file_rules"), dict) else {}

    required_files = sorted({_normalize_rel_path(item) for item in file_rules.get("required_files", []) if _normalize_rel_path(item)})
    forbidden_files = sorted({_normalize_rel_path(item) for item in file_rules.get("forbidden_files", []) if _normalize_rel_path(item)})
    allowed_only = sorted({_normalize_rel_path(item) for item in file_rules.get("allowed_only_files", []) if _normalize_rel_path(item)})
    allowed_globs = [str(item).strip() for item in file_rules.get("allowed_globs", []) if str(item).strip()]
    forbidden_globs = [str(item).strip() for item in file_rules.get("forbidden_globs", []) if str(item).strip()]
    optional_files = sorted({_normalize_rel_path(item) for item in file_rules.get("optional_files", []) if _normalize_rel_path(item)})
    generated_artifacts = sorted({_normalize_rel_path(item) for item in file_rules.get("generated_artifacts", []) if _normalize_rel_path(item)})

    present = _collect_deliverable_files(
        qodeyard,
        exclude_hidden=bool(file_rules.get("exclude_hidden_from_deliverables", True)),
        exclude_system=bool(file_rules.get("exclude_system_artifacts", True)),
    )

    present_set = set(present)
    for rel in required_files:
        if rel not in present_set:
            _append_issue(
                result,
                "files",
                HarnessIssue(
                    CODE_FILE_REQUIRED_MISSING,
                    f"Required file is missing: {rel}",
                    file=rel,
                ),
            )

    for rel in forbidden_files:
        if rel in present_set:
            _append_issue(
                result,
                "files",
                HarnessIssue(
                    CODE_FILE_FORBIDDEN_PRESENT,
                    f"Forbidden file is present: {rel}",
                    file=rel,
                ),
            )

    for pattern in forbidden_globs:
        for rel in present:
            if fnmatch.fnmatch(rel, pattern):
                _append_issue(
                    result,
                    "files",
                    HarnessIssue(
                        CODE_FILE_SCOPE_VIOLATION,
                        f"File matches forbidden glob `{pattern}`: {rel}",
                        file=rel,
                        expected=pattern,
                    ),
                )

    for pattern in allowed_globs:
        if not any(fnmatch.fnmatch(rel, pattern) for rel in present):
            _append_issue(
                result,
                "files",
                HarnessIssue(
                    CODE_FILE_GLOB_REQUIRED_MISSING,
                    f"No deliverable matched required glob `{pattern}`.",
                    expected=pattern,
                ),
            )

    if allowed_only:
        allowed_set = set(allowed_only) | set(optional_files) | set(generated_artifacts)
        extras = sorted(rel for rel in present if rel not in allowed_set)
        if extras:
            for rel in extras:
                _append_issue(
                    result,
                    "files",
                    HarnessIssue(
                        CODE_FILE_EXTRA_PRESENT,
                        f"Unexpected extra deliverable file is present: {rel}",
                        file=rel,
                    ),
                )
            _append_issue(
                result,
                "files",
                HarnessIssue(
                    CODE_DELIVERABLE_SET_MISMATCH,
                    "Deliverable set does not match allowed-only file contract.",
                    actual=", ".join(extras),
                    expected=", ".join(allowed_only),
                ),
            )


def _validate_dependency_rules(result: dict, qodeyard: Path, harness: dict) -> None:
    rules = harness.get("dependency_rules", {}) if isinstance(harness.get("dependency_rules"), dict) else {}
    required_deps = {str(item).strip().lower() for item in rules.get("required_dependencies", []) if str(item).strip()}
    forbidden_deps = {str(item).strip().lower() for item in rules.get("forbidden_dependencies", []) if str(item).strip()}
    forbid_manifests = bool(rules.get("forbid_manifests", False))
    allowed_manifests = {str(item).strip() for item in rules.get("allowed_manifests", []) if str(item).strip()}
    forbidden_managers = {str(item).strip().lower() for item in rules.get("forbidden_managers", []) if str(item).strip()}

    manifest_by_manager = {
        "requirements.txt": "pip",
        "package.json": "npm",
        "pyproject.toml": "python-packaging",
    }

    present_manifests = [name for name in manifest_by_manager.keys() if (qodeyard / name).exists()]

    if forbid_manifests:
        for manifest in present_manifests:
            if manifest not in allowed_manifests:
                _append_issue(
                    result,
                    "dependency",
                    HarnessIssue(
                        CODE_DEP_MANIFEST_UNEXPECTED,
                        f"Dependency manifest is unexpected for this task: {manifest}",
                        file=manifest,
                    ),
                )

    for manifest in present_manifests:
        manager = manifest_by_manager.get(manifest)
        if manager and manager.lower() in forbidden_managers:
            _append_issue(
                result,
                "dependency",
                HarnessIssue(
                    CODE_DEP_MANAGER_FORBIDDEN,
                    f"Dependency manager is forbidden by contract: {manager}",
                    file=manifest,
                ),
            )

    declared = _extract_declared_dependencies(qodeyard)

    for dep in sorted(required_deps):
        if dep not in declared:
            _append_issue(
                result,
                "dependency",
                HarnessIssue(
                    CODE_DEP_MISSING_DECL,
                    f"Required dependency declaration is missing: {dep}",
                    expected=dep,
                ),
            )

    allow_unspecified = bool(rules.get("allow_unspecified_dependencies", True))
    if not allow_unspecified and required_deps:
        extras = sorted(dep for dep in declared if dep not in required_deps)
        for dep in extras:
            _append_issue(
                result,
                "dependency",
                HarnessIssue(
                    CODE_DEP_EXTRA_DECL,
                    f"Extra dependency declaration is present: {dep}",
                    actual=dep,
                ),
            )

    for dep in sorted(forbidden_deps):
        if dep in declared:
            _append_issue(
                result,
                "dependency",
                HarnessIssue(
                    CODE_DEP_EXTRA_DECL,
                    f"Forbidden dependency declaration is present: {dep}",
                    actual=dep,
                ),
            )


def _extract_commands(shell_content: str) -> list[str]:
    commands = []
    for raw in (shell_content or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("#!"):
            continue
        commands.append(line)
    return commands


def _validate_shellscript_rules(result: dict, qodeyard: Path, harness: dict) -> None:
    checks = harness.get("shellscript_checks", []) if isinstance(harness.get("shellscript_checks"), list) else []
    if not checks:
        return

    for row in checks:
        if not isinstance(row, dict):
            continue
        path = _normalize_rel_path(row.get("path") or row.get("file"))
        if not path:
            continue
        script = qodeyard / path
        required = bool(row.get("required", True))

        if required and not script.exists():
            _append_issue(
                result,
                "shellscript",
                HarnessIssue(
                    CODE_SHELL_REQUIRED_MISSING,
                    f"Required shellscript is missing: {path}",
                    file=path,
                ),
            )
            continue
        if not required and script.exists():
            _append_issue(
                result,
                "shellscript",
                HarnessIssue(
                    CODE_SHELL_UNEXPECTED_PRESENT,
                    f"Unexpected shellscript is present: {path}",
                    file=path,
                ),
            )
            continue
        if not script.exists():
            continue

        content = _read_text(script)

        if row.get("executable_required") is True:
            mode = script.stat().st_mode
            if mode & 0o111 == 0:
                _append_issue(
                    result,
                    "shellscript",
                    HarnessIssue(
                        CODE_SHELL_NOT_EXECUTABLE,
                        f"Shellscript must be executable: {path}",
                        file=path,
                    ),
                )

        unsafe_hits = detect_unsafe_commands(content)
        if unsafe_hits:
            _append_issue(
                result,
                "shellscript",
                HarnessIssue(
                    CODE_SHELL_UNSAFE,
                    f"Shellscript contains unsafe command patterns: {', '.join(unsafe_hits)}",
                    file=path,
                ),
            )

        interpreter = shutil.which(pick_shell_mode(script, content)) or shutil.which("sh")
        if interpreter:
            syntax = subprocess.run([interpreter, "-n", str(script)], capture_output=True, text=True, check=False)
            if syntax.returncode != 0:
                _append_issue(
                    result,
                    "shellscript",
                    HarnessIssue(
                        CODE_SHELL_COMMAND_MISMATCH,
                        "Shellscript syntax check failed.",
                        file=path,
                        details={"stderr_excerpt": (syntax.stderr or syntax.stdout or "")[:1200]},
                    ),
                )

        policy = row.get("command_policy")
        if policy is None:
            policy = row.get("policy")
        if not isinstance(policy, (dict, str)):
            policy = {}
        policy_errors = validate_run_sh_contract(content, policy)
        for err in policy_errors:
            code = CODE_SHELL_COMMAND_MISMATCH
            if "forbidden" in err.lower():
                code = CODE_SHELL_FORBIDDEN_COMMAND
            elif "extra command" in err.lower():
                code = CODE_SHELL_EXTRA_COMMAND
            _append_issue(
                result,
                "shellscript",
                HarnessIssue(code, err, file=path),
            )


def _strip_js_comments(content: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", content or "", flags=re.DOTALL)
    return re.sub(r"//[^\n\r]*", "", without_block)


def _js_const_string_literals(content: str) -> dict[str, str]:
    constants: dict[str, str] = {}
    for name, quote, value in re.findall(
        r"\bconst\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(['\"])(.*?)\2\s*;",
        content or "",
        flags=re.DOTALL,
    ):
        constants[name] = value
    return constants


def _resolve_localstorage_key_expr(expr: str, constants: dict[str, str]) -> str | None:
    text = (expr or "").strip()
    literal = re.match(r"^['\"]([^'\"]+)['\"]$", text)
    if literal:
        return literal.group(1)
    if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", text):
        return constants.get(text)
    return None


def _localstorage_keys_in_js(content: str) -> set[str]:
    source = _strip_js_comments(content or "")
    constants = _js_const_string_literals(source)
    key_exprs: list[str] = []
    key_exprs.extend(
        re.findall(r"localStorage\.(?:getItem|removeItem)\(\s*([^)]+?)\s*\)", source, flags=re.DOTALL)
    )
    key_exprs.extend(
        re.findall(r"localStorage\.setItem\(\s*([^,]+?)\s*,", source, flags=re.DOTALL)
    )
    keys: set[str] = set()
    for expr in key_exprs:
        resolved = _resolve_localstorage_key_expr(expr, constants)
        if resolved:
            keys.add(resolved)
    return keys


class _HTMLInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.text_nodes: list[str] = []
        self.controls: list[dict] = []

    def handle_starttag(self, tag: str, attrs):
        attrs_dict = {k: v for k, v in attrs}
        if attrs_dict.get("id"):
            self.ids.add(str(attrs_dict["id"]))
        # Contract-derived "control hints" are heuristic evidence. Container
        # tags such as form/section/div can legitimately carry ids, roles, or
        # labels that satisfy those hints.
        self.controls.append({"tag": tag, "attrs": attrs_dict})

    def handle_data(self, data: str):
        text = str(data or "").strip()
        if text:
            self.text_nodes.append(text)


def _validate_static_rules(result: dict, qodeyard: Path, harness: dict) -> None:
    checks = harness.get("static_checks", []) if isinstance(harness.get("static_checks"), list) else []
    for check in checks:
        if not isinstance(check, dict):
            continue
        check_type = str(check.get("type") or "").strip().lower()
        required = bool(check.get("required", False))

        files = []
        if check.get("file"):
            files = [_normalize_rel_path(check.get("file"))]
        elif isinstance(check.get("files"), list):
            files = [_normalize_rel_path(item) for item in check.get("files") if _normalize_rel_path(item)]

        if check_type in {"parse_python_ast", "parse_js_syntax", "parse_css_basic", "parse_html_basic", "html_required_text", "html_required_controls", "contains_text", "not_contains_text", "regex_present", "regex_absent"} and not files:
            continue

        for rel in files:
            file_path = qodeyard / rel
            text = _read_text(file_path)
            if not file_path.exists():
                if required:
                    _append_issue(
                        result,
                        "static",
                        HarnessIssue(CODE_FILE_REQUIRED_MISSING, f"Static validation file is missing: {rel}", file=rel),
                    )
                continue

            if check_type == "contains_text":
                expected = str(check.get("text") or "")
                if expected and expected not in text:
                    _append_issue(result, "static", HarnessIssue(CODE_STATIC_REQUIRED_TEXT_MISSING, f"Expected text not found in {rel}", file=rel, expected=expected))
            elif check_type == "not_contains_text":
                forbidden = str(check.get("text") or "")
                if forbidden and forbidden in text:
                    _append_issue(result, "static", HarnessIssue(CODE_FILE_SCOPE_VIOLATION, f"Forbidden text found in {rel}", file=rel, actual=forbidden))
            elif check_type == "regex_present":
                pattern = str(check.get("pattern") or "")
                if pattern and not re.search(pattern, text, flags=re.MULTILINE):
                    _append_issue(result, "static", HarnessIssue(CODE_STATIC_REQUIRED_TEXT_MISSING, f"Required regex did not match in {rel}", file=rel, expected=pattern))
            elif check_type == "regex_absent":
                pattern = str(check.get("pattern") or "")
                if pattern and re.search(pattern, text, flags=re.MULTILINE):
                    _append_issue(result, "static", HarnessIssue(CODE_FILE_SCOPE_VIOLATION, f"Forbidden regex matched in {rel}", file=rel, expected=pattern))
            elif check_type == "parse_python_ast":
                try:
                    ast.parse(text or "")
                except Exception as exc:
                    _append_issue(result, "static", HarnessIssue(CODE_STATIC_DOM_FAILED, f"Python parse failed for {rel}: {exc}", file=rel))
            elif check_type == "parse_js_syntax":
                node_bin = shutil.which("node")
                if not node_bin:
                    if required:
                        _append_issue(result, "static", HarnessIssue(CODE_RUNTIME_UNSUPPORTED, f"JavaScript syntax validation requires node, which is unavailable.", file=rel))
                    continue
                syntax = subprocess.run([node_bin, "--check", str(file_path)], capture_output=True, text=True, check=False)
                if syntax.returncode != 0:
                    _append_issue(
                        result,
                        "static",
                        HarnessIssue(
                            CODE_STATIC_DOM_FAILED,
                            f"JavaScript parse failed for {rel}",
                            file=rel,
                            details={"stderr_excerpt": (syntax.stderr or syntax.stdout or "")[:1200]},
                        ),
                    )
            elif check_type == "parse_css_basic":
                open_braces = text.count("{")
                close_braces = text.count("}")
                if open_braces != close_braces:
                    _append_issue(result, "static", HarnessIssue(CODE_STATIC_DOM_FAILED, f"CSS brace mismatch in {rel}", file=rel))
            elif check_type == "parse_html_basic":
                parser = _HTMLInspector()
                try:
                    parser.feed(text)
                except Exception as exc:
                    _append_issue(result, "static", HarnessIssue(CODE_STATIC_DOM_FAILED, f"HTML parse failed for {rel}: {exc}", file=rel))
            elif check_type == "html_required_text":
                expected_text = [str(item) for item in check.get("text", []) if str(item).strip()]
                parser = _HTMLInspector()
                parser.feed(text)
                merged = "\n".join(parser.text_nodes)
                for token in expected_text:
                    if token not in merged:
                        _append_issue(result, "static", HarnessIssue(CODE_STATIC_REQUIRED_TEXT_MISSING, f"Required visible text is missing in {rel}: {token}", file=rel, expected=token))
            elif check_type == "html_required_controls":
                expected_controls = [str(item) for item in check.get("controls", []) if str(item).strip()]
                parser = _HTMLInspector()
                parser.feed(text)
                lowered_text = "\n".join(parser.text_nodes).lower()
                serialized_controls = "\n".join(
                    f"{row.get('tag')} {json.dumps(row.get('attrs', {}), sort_keys=True)}" for row in parser.controls
                ).lower()
                for descriptor in expected_controls:
                    token = descriptor.lower()
                    if token not in lowered_text and token not in serialized_controls:
                        _append_issue(result, "static", HarnessIssue(CODE_STATIC_REQUIRED_CONTROL_MISSING, f"Required control hint is missing in {rel}: {descriptor}", file=rel, expected=descriptor))

        if check_type == "storage_keys_exact":
            js_files = [_normalize_rel_path(item) for item in check.get("files", []) if _normalize_rel_path(item)]
            expected_keys = {str(item) for item in check.get("keys", []) if str(item).strip()}
            exact = bool(check.get("exact", False))
            used: set[str] = set()
            for rel in js_files:
                fpath = qodeyard / rel
                if fpath.exists():
                    used.update(_localstorage_keys_in_js(_read_text(fpath)))
            missing = sorted(key for key in expected_keys if key not in used)
            if missing:
                _append_issue(
                    result,
                    "static",
                    HarnessIssue(
                        CODE_STATIC_PERSISTENCE_FAILED,
                        f"Required localStorage keys are missing: {', '.join(missing)}",
                        file=js_files[0] if js_files else None,
                        expected=", ".join(sorted(expected_keys)),
                        actual=", ".join(sorted(used)),
                    ),
                )
            if exact and used:
                extras = sorted(key for key in used if key not in expected_keys)
                if extras:
                    _append_issue(
                        result,
                        "static",
                        HarnessIssue(
                            CODE_STATIC_PERSISTENCE_FAILED,
                            f"Unexpected localStorage keys are used: {', '.join(extras)}",
                            file=js_files[0] if js_files else None,
                            expected=", ".join(sorted(expected_keys)),
                            actual=", ".join(sorted(used)),
                        ),
                    )

        if check_type == "data_model_exact_fields":
            # Conservative parser: look for object-literal keys in JS source.
            js_files = [_normalize_rel_path(item) for item in check.get("files", []) if _normalize_rel_path(item)]
            models = check.get("models", {}) if isinstance(check.get("models"), dict) else {}
            if not models:
                continue
            all_text = "\n".join(_read_text(qodeyard / rel) for rel in js_files if (qodeyard / rel).exists())
            detected_keys = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:", all_text))
            for model_name, fields in models.items():
                if not isinstance(fields, list) or not fields:
                    continue
                required = {str(item) for item in fields if str(item).strip()}
                missing = sorted(field for field in required if field not in detected_keys)
                if missing:
                    _append_issue(
                        result,
                        "static",
                        HarnessIssue(
                            CODE_STATIC_DOM_FAILED,
                            f"Model field contract for `{model_name}` appears incomplete; missing keys: {', '.join(missing)}",
                            file=js_files[0] if js_files else None,
                            expected=", ".join(sorted(required)),
                            actual=", ".join(sorted(detected_keys)),
                        ),
                    )


def _http_json_request(method: str, url: str, payload: dict | None = None, timeout: float = 2.0):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url=url, data=data, headers=headers, method=method.upper())
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = (resp.read() or b"").decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else None
            except Exception:
                parsed = None
            return resp.getcode(), parsed, body
    except urllib_error.HTTPError as exc:
        body = (exc.read() or b"").decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = None
        return exc.code, parsed, body


def _is_subset(subset, superset):
    if isinstance(subset, dict) and isinstance(superset, dict):
        return all(k in superset and _is_subset(subset[k], superset[k]) for k in subset)
    if isinstance(subset, list) and isinstance(superset, list):
        return all(any(_is_subset(s_item, sup_item) for sup_item in superset) for s_item in subset)
    return subset == superset


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass


def _validate_static_browser_runtime(result: dict, qodeyard: Path, check: dict) -> None:
    entrypoint = _normalize_rel_path(check.get("entrypoint"))
    candidates = [_normalize_rel_path(item) for item in check.get("entrypoint_candidates", []) if _normalize_rel_path(item)]

    if not entrypoint:
        if len(candidates) == 1:
            entrypoint = candidates[0]
        elif len(candidates) > 1:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_RUNTIME_ENTRY_AMBIG,
                    "Static app entrypoint is ambiguous.",
                    expected=", ".join(candidates),
                ),
            )
            return
        else:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_RUNTIME_ENTRY_MISSING,
                    "Static app entrypoint is missing from contract.",
                ),
            )
            return

    html_path = qodeyard / entrypoint
    if not html_path.exists():
        _append_issue(
            result,
            "runtime",
            HarnessIssue(
                CODE_RUNTIME_ENTRY_MISSING,
                f"Static app entrypoint file is missing: {entrypoint}",
                file=entrypoint,
            ),
        )
        return

    html_text = _read_text(html_path)
    parser = _HTMLInspector()
    parser.feed(html_text)
    all_text = "\n".join(parser.text_nodes)

    for expected_text in check.get("required_visible_text", []) if isinstance(check.get("required_visible_text"), list) else []:
        token = str(expected_text).strip()
        if token and token not in all_text:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_STATIC_REQUIRED_TEXT_MISSING,
                    f"Required visible text is missing from runtime entrypoint: {token}",
                    file=entrypoint,
                    expected=token,
                ),
            )

    controls_payload = "\n".join(
        f"{row.get('tag')} {json.dumps(row.get('attrs', {}), sort_keys=True)}" for row in parser.controls
    ).lower()
    for control in check.get("required_controls", []) if isinstance(check.get("required_controls"), list) else []:
        token = str(control).strip().lower()
        if token and token not in controls_payload and token not in all_text.lower():
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_STATIC_REQUIRED_CONTROL_MISSING,
                    f"Required control hint is missing: {control}",
                    file=entrypoint,
                    expected=str(control),
                ),
            )

    if bool(check.get("forbid_external_assets", False)):
        external_refs = re.findall(r"(?:src|href)=[\"'](https?://|//)[^\"']+[\"']", html_text, flags=re.IGNORECASE)
        if external_refs:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_STATIC_EXTERNAL_FORBIDDEN,
                    "External assets are forbidden by contract but found in entrypoint.",
                    file=entrypoint,
                ),
            )

    if bool(check.get("forbid_external_network", False)):
        script_refs = [
            _normalize_rel_path(path)
            for path in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html_text, flags=re.IGNORECASE)
        ]
        js_candidates = []
        for rel in script_refs:
            if rel and not rel.startswith("http") and not rel.startswith("//"):
                js_candidates.append(rel)
        js_candidates.extend(
            [
                rel
                for rel in _collect_deliverable_files(qodeyard, exclude_hidden=True, exclude_system=True)
                if rel.endswith(".js")
            ]
        )
        external_network_hits = []
        for rel in sorted(set(js_candidates)):
            text = _read_text(qodeyard / rel)
            if re.search(r"fetch\(\s*['\"]https?://", text) or re.search(r"XMLHttpRequest\(", text):
                external_network_hits.append(rel)
        if external_network_hits:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_STATIC_EXTERNAL_FORBIDDEN,
                    "External network requests are forbidden by contract but were detected.",
                    file=external_network_hits[0],
                    actual=", ".join(external_network_hits),
                ),
            )

    required_storage = [str(item) for item in check.get("required_storage_keys", []) if str(item).strip()]
    if required_storage:
        js_files = [rel for rel in _collect_deliverable_files(qodeyard, exclude_hidden=True, exclude_system=True) if rel.endswith(".js")]
        used_keys: set[str] = set()
        for rel in js_files:
            used_keys.update(_localstorage_keys_in_js(_read_text(qodeyard / rel)))
        missing = [key for key in required_storage if key not in used_keys]
        if missing:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_STATIC_PERSISTENCE_FAILED,
                    f"Required localStorage keys are not used: {', '.join(missing)}",
                    file=js_files[0] if js_files else entrypoint,
                ),
            )

    # Interaction semantics are partially covered by structural/static checks.
    # Full browser automation is intentionally out of scope for this runtime.


def _validation_python_path_prefix(qodeyard: Path) -> str | None:
    if provision_validation_env is None:
        return None
    try:
        python_bin, _ = provision_validation_env(qodeyard.parent, qodeyard)
    except Exception:
        return None
    if not python_bin:
        return None
    bin_dir = Path(str(python_bin)).parent
    if not bin_dir.exists():
        return None
    return str(bin_dir)


def _validate_http_runtime(result: dict, qodeyard: Path, check: dict) -> None:
    launch_cmd = str(check.get("launch_command") or "").strip()
    if not launch_cmd:
        _append_issue(
            result,
            "runtime",
            HarnessIssue(CODE_RUNTIME_ENTRY_MISSING, "HTTP runtime check is missing launch command."),
        )
        return

    try:
        command = shlex.split(launch_cmd)
    except Exception:
        _append_issue(
            result,
            "runtime",
            HarnessIssue(CODE_RUNTIME_LAUNCH_FAILED, "Launch command could not be tokenized.", expected=launch_cmd),
        )
        return

    port = int(check.get("port") or check.get("default_port") or 8000)
    env = dict(os.environ)
    validation_path_prefix = _validation_python_path_prefix(qodeyard)
    if validation_path_prefix:
        current_path = env.get("PATH", "")
        env["PATH"] = validation_path_prefix + (os.pathsep + current_path if current_path else "")
    env.update({
        str(check.get("port_variable") or "PORT"): str(port),
    })

    proc = None
    try:
        popen_kwargs = {
            "cwd": str(qodeyard),
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name != "nt":
            popen_kwargs["preexec_fn"] = os.setsid
        proc = subprocess.Popen(command, **popen_kwargs)

        base = f"http://127.0.0.1:{port}"
        ready_probe = check.get("ready_probe") if isinstance(check.get("ready_probe"), dict) else {}
        ready_path = str(ready_probe.get("path") or "/")
        ready_status = int(ready_probe.get("expected_status") or 200)

        ready = False
        deadline = time.time() + float(check.get("ready_timeout_seconds") or 30)
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                code, payload, _ = _http_json_request("GET", f"{base}{ready_path}", timeout=1.2)
                if code == ready_status:
                    subset = ready_probe.get("expected_json_subset")
                    if subset is None or _is_subset(subset, payload):
                        ready = True
                        break
            except Exception:
                pass
            time.sleep(0.25)

        if not ready:
            out, err = proc.communicate(timeout=1) if proc.poll() is not None else ("", "")
            lower = ((out or "") + "\n" + (err or "")).lower()
            code = CODE_RUNTIME_LAUNCH_FAILED
            if "command not found" in lower or "no such file or directory" in lower:
                code = CODE_RUNTIME_ENV_BLOCKED
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    code,
                    "Runtime service did not become ready.",
                    details={
                        "command": launch_cmd,
                        "stdout_excerpt": (out or "")[:1200],
                        "stderr_excerpt": (err or "")[:1200],
                    },
                ),
            )
            return

        probes = check.get("probes", []) if isinstance(check.get("probes"), list) else []
        for probe in probes:
            if not isinstance(probe, dict):
                continue
            method = str(probe.get("method") or "GET").upper()
            path = str(probe.get("path") or "/")
            payload = probe.get("payload") if isinstance(probe.get("payload"), dict) else None
            exp_status = int(probe.get("expected_status") or 200)
            code, data, body = _http_json_request(method, f"{base}{path}", payload=payload)
            if code != exp_status:
                _append_issue(
                    result,
                    "runtime",
                    HarnessIssue(
                        CODE_HTTP_PROBE_FAILED,
                        f"HTTP probe failed: {method} {path} returned {code}, expected {exp_status}",
                        details={"response_body_excerpt": (body or "")[:800]},
                    ),
                )
                continue

            subset = probe.get("expected_json_subset")
            if subset is not None and not _is_subset(subset, data):
                _append_issue(
                    result,
                    "runtime",
                    HarnessIssue(
                        CODE_HTTP_PROBE_FAILED,
                        f"HTTP probe JSON subset mismatch for {method} {path}",
                        actual=json.dumps(data, sort_keys=True)[:800],
                        expected=json.dumps(subset, sort_keys=True)[:800],
                    ),
                )

            exact_keys = probe.get("exact_keys") if isinstance(probe.get("exact_keys"), list) else []
            if exact_keys and isinstance(data, dict):
                if set(map(str, data.keys())) != set(map(str, exact_keys)):
                    _append_issue(
                        result,
                        "runtime",
                        HarnessIssue(
                            CODE_HTTP_PROBE_FAILED,
                            f"HTTP probe exact-keys mismatch for {method} {path}",
                            actual=", ".join(sorted(data.keys())),
                            expected=", ".join(sorted(map(str, exact_keys))),
                        ),
                    )

    except Exception as exc:
        _append_issue(result, "runtime", HarnessIssue(CODE_RUNTIME_LAUNCH_FAILED, f"Runtime launch crashed: {exc}"))
    finally:
        if proc is not None:
            _terminate_process(proc)


def _validate_cli_runtime(result: dict, qodeyard: Path, check: dict) -> None:
    commands = check.get("commands", []) if isinstance(check.get("commands"), list) else []
    if not commands:
        _append_issue(result, "runtime", HarnessIssue(CODE_RUNTIME_ENTRY_MISSING, "CLI runtime check has no commands."))
        return

    for row in commands:
        if not isinstance(row, dict):
            continue
        cmd = str(row.get("command") or "").strip()
        if not cmd:
            _append_issue(result, "runtime", HarnessIssue(CODE_CLI_PROBE_FAILED, "CLI probe command is empty."))
            continue
        env = dict(os.environ)
        validation_path_prefix = _validation_python_path_prefix(qodeyard)
        if validation_path_prefix:
            current_path = env.get("PATH", "")
            env["PATH"] = validation_path_prefix + (os.pathsep + current_path if current_path else "")
        try:
            proc = subprocess.run(
                shlex.split(cmd),
                cwd=str(qodeyard),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=float(row.get("timeout_seconds") or 20),
            )
        except FileNotFoundError:
            _append_issue(result, "runtime", HarnessIssue(CODE_RUNTIME_ENV_BLOCKED, "CLI command tool is unavailable.", expected=cmd))
            continue
        except Exception as exc:
            _append_issue(result, "runtime", HarnessIssue(CODE_CLI_PROBE_FAILED, f"CLI probe crashed: {exc}", expected=cmd))
            continue

        expected_exit = row.get("expected_exit")
        if expected_exit is not None and int(expected_exit) != proc.returncode:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_CLI_PROBE_FAILED,
                    f"CLI probe returned exit code {proc.returncode}, expected {expected_exit}",
                    expected=str(expected_exit),
                    actual=str(proc.returncode),
                ),
            )

        stdout_regex = str(row.get("stdout_regex") or "").strip()
        if stdout_regex and not re.search(stdout_regex, proc.stdout or "", flags=re.MULTILINE):
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_CLI_PROBE_FAILED,
                    "CLI probe stdout did not match expected regex.",
                    expected=stdout_regex,
                    actual=(proc.stdout or "")[:400],
                ),
            )


def _validate_file_output_runtime(result: dict, qodeyard: Path, check: dict) -> None:
    outputs = [_normalize_rel_path(item) for item in check.get("expected_files", []) if _normalize_rel_path(item)]
    if not outputs:
        _append_issue(result, "runtime", HarnessIssue(CODE_FILE_OUTPUT_PROBE_FAILED, "File-output runtime check has no expected files."))
        return
    for rel in outputs:
        if not (qodeyard / rel).exists():
            _append_issue(result, "runtime", HarnessIssue(CODE_FILE_OUTPUT_PROBE_FAILED, f"Expected output file is missing: {rel}", file=rel))


def _validate_runtime_rules(result: dict, qodeyard: Path, harness: dict) -> None:
    checks = harness.get("runtime_checks", []) if isinstance(harness.get("runtime_checks"), list) else []
    for check in checks:
        if not isinstance(check, dict):
            continue
        runtime_type = str(check.get("runtime_type") or check.get("type") or "").strip().lower()
        required = bool(check.get("required", False))

        if runtime_type in {"", "no_runtime_required"}:
            continue
        if runtime_type == "static_browser_app":
            _validate_static_browser_runtime(result, qodeyard, check)
        elif runtime_type == "http_service":
            _validate_http_runtime(result, qodeyard, check)
        elif runtime_type == "cli_command":
            _validate_cli_runtime(result, qodeyard, check)
        elif runtime_type == "file_output":
            _validate_file_output_runtime(result, qodeyard, check)
        elif runtime_type in {"generated_file", "test_script", "long_running_process", "library_import"}:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_RUNTIME_UNSUPPORTED,
                    f"Runtime check type is not yet implemented: {runtime_type}",
                    severity="error" if required else "warning",
                ),
            )
        else:
            _append_issue(
                result,
                "runtime",
                HarnessIssue(
                    CODE_RUNTIME_UNSUPPORTED,
                    f"Runtime check type is unsupported: {runtime_type}",
                    severity="error" if required else "warning",
                ),
            )


def run_harness(qodeyard: Path, harness: dict, *, apply_fixes: bool = False) -> dict:
    del apply_fixes
    if not isinstance(harness, dict) or not harness:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "harness_id": CONTRACT_ID,
            "status": "BLOCKED",
            "passed": False,
            "verdict_classification": "BLOCKED: contract missing",
            "violations": [
                {
                    "rule_id": CODE_CONTRACT_STALE,
                    "code": CODE_CONTRACT_STALE,
                    "severity": "error",
                    "message": "Harness contract is missing.",
                }
            ],
            "repair_directive": "Generate a current tasq-derived contract before running deterministic validation.",
            "completion_override": {
                "allowed": False,
                "task_completed": False,
                "repair_required": True,
                "evidence_status": "EVIDENCE_PARTIAL",
            },
        }

    # Backward compatibility bridge for legacy contracts.
    if "required_files" in harness and "file_rules" not in harness:
        required = [_normalize_rel_path(item) for item in harness.get("required_files", []) if _normalize_rel_path(item)]
        dep_checks = harness.get("dependency_checks", {}) if isinstance(harness.get("dependency_checks"), dict) else {}
        harness = {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "contract_id": str(harness.get("harness_id") or CONTRACT_ID),
            "generated_at": now_utc(),
            "tool_version": _runtime_version(),
            "task_identity": {
                "qage_id": _canonical_qage_id(qodeyard=qodeyard),
                "source_tasq_path": "",
                "source_tasq_hash": "",
                "task_hash": "",
            },
            "file_rules": {
                "required_files": required,
                "forbidden_files": [],
                "allowed_only_files": [],
                "allowed_globs": [],
                "forbidden_globs": [],
                "optional_files": [],
                "generated_artifacts": [],
                "exclude_hidden_from_deliverables": True,
                "exclude_system_artifacts": True,
            },
            "dependency_rules": {
                "required_dependencies": dep_checks.get("required_packages", []) if isinstance(dep_checks.get("required_packages"), list) else [],
                "forbidden_dependencies": dep_checks.get("forbidden_packages", []) if isinstance(dep_checks.get("forbidden_packages"), list) else [],
                "required_managers": [],
                "forbidden_managers": [],
                "forbid_manifests": False,
                "allowed_manifests": [],
                "allow_unspecified_dependencies": True,
            },
            "shellscript_checks": harness.get("shellscript_checks", []),
            "runtime_checks": harness.get("runtime_checks", []),
            "static_checks": harness.get("static_checks", []),
            "behavior_checks": {},
            "scope_rules": [],
            "ambiguity_notes": ["Legacy harness schema was auto-upgraded to contract v2 compatibility mode."],
            "rule_reasons": [],
        }
        harness["task_identity"]["contract_hash"] = _compute_contract_hash(harness)

    result = _make_result_template(harness, qodeyard)

    _validate_artifact_binding(result, qodeyard, harness)
    _validate_files(result, qodeyard, harness)
    _validate_dependency_rules(result, qodeyard, harness)
    _validate_shellscript_rules(result, qodeyard, harness)
    _validate_static_rules(result, qodeyard, harness)
    _validate_runtime_rules(result, qodeyard, harness)

    return _finalize_result(result)


def render_harness_markdown(harness: dict) -> str:
    return "# Deterministic Validation Contract\n\n```json\n" + json.dumps(harness, indent=2) + "\n```\n"


def render_result_markdown(result: dict) -> str:
    return "# Deterministic Validation Result\n\n```json\n" + json.dumps(result, indent=2) + "\n```\n"


def build_repair_directive(result: dict) -> str:
    violations = result.get("violations", []) if isinstance(result.get("violations"), list) else []
    if not violations:
        return ""
    parts = []
    for row in violations:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or row.get("rule_id") or "VALIDATION_ERROR").strip()
        msg = str(row.get("message") or "").strip()
        file = str(row.get("file") or "").strip()
        expected = str(row.get("expected") or "").strip()
        actual = str(row.get("actual") or "").strip()
        segment = f"[{code}]"
        if file:
            segment += f" {file}:"
        segment += f" {msg}"
        if expected:
            segment += f" | expected={expected}"
        if actual:
            segment += f" | actual={actual}"
        parts.append(segment)
    return "Apply targeted repairs for current-contract failures only: " + " || ".join(parts[:20])


__all__ = [
    "detect_harness_class",
    "build_harness",
    "write_harness",
    "load_harness",
    "apply_autofixes",
    "run_harness",
    "render_harness_markdown",
    "render_result_markdown",
    "build_repair_directive",
]
