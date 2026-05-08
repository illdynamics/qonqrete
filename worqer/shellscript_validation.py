from __future__ import annotations

import re
import shlex
from pathlib import Path

UNSAFE_COMMAND_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\bsudo\b",
    r"\bcurl\b[^\n|]*\|\s*(?:sh|bash)\b",
    r"\bwget\b[^\n|]*\|\s*(?:sh|bash)\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+-R\s+777\s+/",
]


def pick_shell_mode(script_path: Path, content: str | None = None) -> str:
    if script_path.suffix.lower() == ".bash":
        return "bash"
    if script_path.suffix.lower() == ".zsh":
        return "zsh"
    if script_path.suffix.lower() == ".ksh":
        return "ksh"

    text = content
    if text is None:
        try:
            text = script_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
    first = (text.splitlines()[:1] or [""])[0].strip().lower()
    if first.startswith("#!"):
        if "bash" in first:
            return "bash"
        if "zsh" in first:
            return "zsh"
        if "ksh" in first:
            return "ksh"
    return "sh"


def detect_unsafe_commands(shell_content: str) -> list[str]:
    findings: list[str] = []
    text = shell_content or ""
    for pattern in UNSAFE_COMMAND_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(pattern)
    return findings


def split_script_commands(shell_content: str) -> list[tuple[int, str]]:
    lines = (shell_content or "").splitlines()
    commands: list[tuple[int, str]] = []
    pending = ""
    pending_line = 0

    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if pending:
            line = pending + line.lstrip()
        else:
            pending_line = idx

        if line.endswith("\\"):
            pending = line[:-1] + " "
            continue

        pending = ""
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#!"):
            continue
        if stripped.startswith("#"):
            continue
        commands.append((pending_line, stripped))

    if pending.strip():
        commands.append((pending_line, pending.strip()))
    return commands


def _tokenize_command(command: str) -> list[str] | None:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def _normalize_var_token(token: str) -> str:
    raw = str(token or "").strip()
    return raw.strip("\"'")


def _matches_allowed_boilerplate(command: str, allowed_boilerplate: list[str]) -> bool:
    stripped = command.strip()
    if not stripped:
        return True
    
    # Allow simple variable assignments: VAR=val, VAR="val", or VAR=${VAR:-val}.
    # Command substitution is executable wrapper logic, not boilerplate.
    if re.match(r'^[A-Z_][A-Z0-9_]*=', stripped) and "$(" not in stripped and "`" not in stripped:
        return True

    first = stripped.split()[0].lower()
    return first in {item.lower() for item in allowed_boilerplate}


def _convert_string_policy(policy: str) -> tuple[dict, str | None]:
    profile = str(policy or "generic").strip().lower() or "generic"
    if profile in {"generic", "default"}:
        return (
            {
                "allow_wrapper": True,
                "allowed_boilerplate": ["set", "export"],
            },
            None,
        )
    if profile in {"strict", "exact"}:
        return (
            {
                "allow_wrapper": False,
                "allowed_boilerplate": ["set", "export"],
            },
            None,
        )
    if profile == "exact_variable_port":
        return (
            {
                "allow_wrapper": False,
                "allowed_boilerplate": ["set", "export"],
                "exact_command_required": "python -m uvicorn main:app --reload --port $PORT",
                "required_variables": ["PORT"],
            },
            None,
        )
    if profile == "exact_literal_8000":
        return (
            {
                "allow_wrapper": False,
                "allowed_boilerplate": ["set", "export"],
                "exact_command_required": "python -m uvicorn main:app --reload --port 8000",
            },
            None,
        )
    if profile == "port_variable":
        return (
            {
                "allow_wrapper": True,
                "allowed_boilerplate": ["set", "export"],
                "required_variables": ["PORT"],
            },
            None,
        )
    return (
        {
            "allow_wrapper": True,
            "allowed_boilerplate": ["set", "export"],
        },
        f"unsupported shellscript policy profile: {profile}",
    )


def validate_run_sh_contract(shell_content: str, policy: str | dict) -> list[str]:
    errors: list[str] = []
    commands = split_script_commands(shell_content)

    contract: dict
    if isinstance(policy, str):
        contract, profile_error = _convert_string_policy(policy)
        if profile_error:
            errors.append(profile_error)
    else:
        contract = dict(policy or {})
    allow_wrapper = bool(contract.get("allow_wrapper", True))
    allowed_boilerplate = [str(item).strip() for item in contract.get("allowed_boilerplate", ["set", "export"]) if str(item).strip()]

    parse_failures: list[tuple[int, str]] = []
    tokenized_commands: list[tuple[int, str, list[str]]] = []
    for line_no, cmd in commands:
        tokens = _tokenize_command(cmd)
        if tokens is None:
            parse_failures.append((line_no, cmd))
            continue
        tokenized_commands.append((line_no, cmd, tokens))

    for line_no, cmd in parse_failures:
        errors.append(f"line {line_no}: shell tokenization failed for command: {cmd[:200]}")

    exact_required = str(contract.get("exact_command_required") or "").strip()
    allowed_commands = [str(item).strip() for item in contract.get("allowed_commands", []) if str(item).strip()]
    forbidden_commands = [str(item).strip() for item in contract.get("forbidden_commands", []) if str(item).strip()]
    forbidden_patterns = [str(item).strip() for item in contract.get("forbidden_command_patterns", []) if str(item).strip()]
    required_variables = [str(item).strip() for item in contract.get("required_variables", []) if str(item).strip()]
    forbid_literals = [str(item).strip() for item in contract.get("forbid_literal_values", []) if str(item).strip()]
    max_commands = contract.get("max_commands")

    if isinstance(max_commands, int) and max_commands >= 0 and len(tokenized_commands) > max_commands:
        errors.append(f"script contains {len(tokenized_commands)} commands; maximum allowed is {max_commands}")

    normalized_exact = None
    if exact_required:
        exact_tokens = _tokenize_command(exact_required)
        if exact_tokens is not None:
            normalized_exact = [
                _normalize_var_token(token)
                for token in exact_tokens
            ]
        else:
            errors.append("contract exact_command_required could not be tokenized")

    if normalized_exact is not None:
        exact_seen = False
        for line_no, cmd, tokens in tokenized_commands:
            normalized = [_normalize_var_token(token) for token in tokens]
            if normalized == normalized_exact:
                exact_seen = True
                continue
            if not allow_wrapper and not _matches_allowed_boilerplate(cmd, allowed_boilerplate):
                errors.append(f"line {line_no}: only allowed boilerplate and the exact launcher command are permitted")
        if not exact_seen:
            errors.append(f"must include exact command `{exact_required}`")

    allowed_norm = []
    for item in allowed_commands:
        tokens = _tokenize_command(item)
        if tokens is not None:
            allowed_norm.append([_normalize_var_token(token) for token in tokens])

    if allowed_norm:
        for line_no, cmd, tokens in tokenized_commands:
            normalized = [_normalize_var_token(token) for token in tokens]
            if normalized in allowed_norm:
                continue
            if _matches_allowed_boilerplate(cmd, allowed_boilerplate):
                continue
            errors.append(f"line {line_no}: command is not in the allowed command set")

    if forbidden_commands:
        for line_no, cmd, _ in tokenized_commands:
            lowered = cmd.lower()
            for forbidden in forbidden_commands:
                if lowered.startswith(forbidden.lower()):
                    errors.append(f"line {line_no}: forbidden command prefix `{forbidden}` found")

    for pattern in forbidden_patterns:
        for line_no, cmd, _ in tokenized_commands:
            if re.search(pattern, cmd, flags=re.IGNORECASE):
                errors.append(f"line {line_no}: forbidden command pattern matched: {pattern}")

    if required_variables:
        for variable in required_variables:
            var_tokens = {f"${variable}", f"${{{variable}}}"}
            found = False
            for _, _, tokens in tokenized_commands:
                normalized = {_normalize_var_token(token) for token in tokens}
                if normalized & var_tokens:
                    found = True
                    break
            if not found:
                errors.append(f"required variable reference missing: {variable}")

    if forbid_literals:
        forbidden_literals = set(forbid_literals)
        for line_no, _, tokens in tokenized_commands:
            normalized = {_normalize_var_token(token) for token in tokens}
            expanded: set[str] = set(normalized)
            for token in list(normalized):
                if "=" in token:
                    _, rhs = token.split("=", 1)
                    rhs_clean = _normalize_var_token(rhs)
                    if rhs_clean:
                        expanded.add(rhs_clean)
            normalized = expanded
            overlap = forbidden_literals & normalized
            if overlap:
                errors.append(f"line {line_no}: forbidden literal values present: {', '.join(sorted(overlap))}")

    return sorted(set(errors))


__all__ = [
    "UNSAFE_COMMAND_PATTERNS",
    "pick_shell_mode",
    "detect_unsafe_commands",
    "split_script_commands",
    "validate_run_sh_contract",
]
