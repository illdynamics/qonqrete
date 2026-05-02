from __future__ import annotations

import re
import shlex
from pathlib import Path


EXPECTED_UVICORN_VAR_COMMAND = [
    "python",
    "-m",
    "uvicorn",
    "main:app",
    "--reload",
    "--port",
    "$PORT",
]

EXPECTED_UVICORN_LITERAL_COMMAND = [
    "python",
    "-m",
    "uvicorn",
    "main:app",
    "--reload",
    "--port",
    "8000",
]

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


def _normalize_port_token(token: str) -> str:
    raw = str(token or "").strip()
    stripped = raw.strip("\"'")
    if stripped in {"$PORT", "${PORT}"}:
        return "$PORT"
    return raw


def _tokenize_command(command: str) -> list[str] | None:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def _is_python_uvicorn_invocation(tokens: list[str]) -> bool:
    if len(tokens) < 4:
        return False
    exe = tokens[0].lower()
    if not re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", exe):
        return False
    return tokens[1] == "-m" and tokens[2] == "uvicorn"


def _is_uvicorn_binary_invocation(tokens: list[str]) -> bool:
    return bool(tokens) and tokens[0] == "uvicorn"


def _find_port_value(tokens: list[str]) -> tuple[str | None, str | None]:
    for idx, token in enumerate(tokens):
        if token != "--port":
            continue
        if idx + 1 >= len(tokens):
            return None, "missing"
        nxt = tokens[idx + 1]
        if nxt.startswith("--"):
            return None, "missing"
        return _normalize_port_token(nxt), None
    return None, "absent"


def validate_run_sh_contract(shell_content: str, policy: str) -> list[str]:
    errors: list[str] = []
    commands = split_script_commands(shell_content)

    uvicorn_rows: list[tuple[int, str, list[str]]] = []
    parse_failures: list[tuple[int, str]] = []
    for line_no, cmd in commands:
        tokens = _tokenize_command(cmd)
        if tokens is None:
            parse_failures.append((line_no, cmd))
            continue
        if _is_python_uvicorn_invocation(tokens) or _is_uvicorn_binary_invocation(tokens):
            uvicorn_rows.append((line_no, cmd, tokens))

    if parse_failures:
        for line_no, cmd in parse_failures:
            errors.append(f"line {line_no}: shell tokenization failed for command: {cmd[:200]}")

    if not uvicorn_rows:
        errors.append("must launch `python -m uvicorn main:app`")
        return errors

    expected_var = "python -m uvicorn main:app --reload --port $PORT"
    expected_literal = "python -m uvicorn main:app --reload --port 8000"

    strict_exact_var = policy == "exact_variable_port"
    strict_exact_literal = policy == "exact_literal_8000"
    require_port_variable = policy in {"port_variable", "exact_variable_port"}
    disallow_numeric_port = policy in {"generic", "port_variable", "exact_variable_port"}

    if strict_exact_var:
        match_found = False
        for line_no, cmd, tokens in uvicorn_rows:
            normalized = [_normalize_port_token(token) for token in tokens]
            if normalized == EXPECTED_UVICORN_VAR_COMMAND:
                match_found = True
                break
            if "--port" in normalized:
                port_value, port_err = _find_port_value(normalized)
                if port_err == "missing":
                    errors.append(f"line {line_no}: missing value after --port (expected $PORT)")
                elif port_value and port_value != "$PORT":
                    errors.append(f"line {line_no}: hardcoded port `{port_value}` is forbidden; expected $PORT")
        if not match_found:
            errors.append(f"must launch exactly `{expected_var}`")
        return errors

    if strict_exact_literal:
        match_found = False
        for line_no, cmd, tokens in uvicorn_rows:
            normalized = [_normalize_port_token(token) for token in tokens]
            if normalized == EXPECTED_UVICORN_LITERAL_COMMAND:
                match_found = True
                break
            if "--port" in normalized:
                port_value, port_err = _find_port_value(normalized)
                if port_err == "missing":
                    errors.append(f"line {line_no}: missing value after --port (expected 8000)")
        if not match_found:
            errors.append(f"must launch exactly `{expected_literal}`")
        return errors

    target_ok = False
    for line_no, cmd, tokens in uvicorn_rows:
        normalized = [_normalize_port_token(token) for token in tokens]

        if _is_uvicorn_binary_invocation(normalized):
            errors.append(f"line {line_no}: must launch `python -m uvicorn main:app`")
            continue
        if normalized[3] != "main:app":
            errors.append(f"line {line_no}: expected uvicorn target `main:app`, got `{normalized[3]}`")
            continue
        target_ok = True

        port_value, port_err = _find_port_value(normalized)
        if port_err == "absent":
            errors.append(f"line {line_no}: uvicorn command must include a valid --port argument")
            continue
        if port_err == "missing":
            errors.append(f"line {line_no}: missing value after --port")
            continue

        if require_port_variable and port_value != "$PORT":
            errors.append(f"line {line_no}: uvicorn command must pass $PORT instead of a literal value")
        if disallow_numeric_port and port_value and re.fullmatch(r"\d+", port_value):
            errors.append(f"line {line_no}: hardcoded numeric port literal found in uvicorn command")

    if not target_ok:
        errors.append("must launch `python -m uvicorn main:app`")

    if require_port_variable:
        if not re.search(r"--port\s+(?:\"?\$PORT\"?|'?\$PORT'|\"?\$\{PORT\}\"?|'?\$\{PORT\}')", shell_content or ""):
            errors.append("uvicorn command must pass the PORT variable instead of a literal value")
        if re.search(r"\bPORT\s*[:=+-]*\s*['\"]?\d+['\"]?", shell_content or "", flags=re.IGNORECASE):
            errors.append("hardcoded numeric PORT assignment found; derive PORT without duplicating the literal from main.py")

    return sorted(set(errors))


__all__ = [
    "EXPECTED_UVICORN_VAR_COMMAND",
    "EXPECTED_UVICORN_LITERAL_COMMAND",
    "UNSAFE_COMMAND_PATTERNS",
    "pick_shell_mode",
    "detect_unsafe_commands",
    "split_script_commands",
    "validate_run_sh_contract",
]

