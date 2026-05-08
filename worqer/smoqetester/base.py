# worqer/smoqetester/base.py
# ═══════════════════════════════════════════════════════════════════════════════
# Adapter protocol and subprocess helpers for deterministic smoketest execution.
#
# Truthfulness contract (v1.3.5 patch):
#   - A subprocess running successfully is NOT sufficient to call a check
#     "executed". Every result carries an explicit `execution_kind` whose value
#     is derived from (in order of precedence):
#       1. an explicit override passed by the adapter,
#       2. a config-level override on the command entry,
#       3. a conservative inference in `classify_command_execution_kind`
#          (unknown => "static", never "executed").
#   - The `executed` boolean on a result is derived from execution_kind and
#     never from "subprocess ran". See run_command().
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .discovery import find_binary
from .models import (
    EXECUTION_KIND_STATIC,
    EXECUTION_KIND_SYNTAX,
    EXECUTION_KIND_PROCESS_BOOT,
    EXECUTION_KIND_HTTP,
    EXECUTION_KIND_WS,
    EXECUTION_KIND_BROWSER,
    EXECUTION_KIND_EXECUTED,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    SmoketestResult,
    _VALID_EXECUTION_KINDS,
)


# Tools whose output is syntactic/semantic parsing only and never exercises
# program runtime behavior. Classifying any of these as "executed" would be
# lying — they don't exercise application code paths.
_STATIC_TOOL_BASENAMES = {
    "black",
    "cppcheck",
    "eslint",
    "flake8",
    "golangci-lint",
    "hadolint",
    "isort",
    "ktlint",
    "mypy",
    "prettier",
    "py_compile",
    "pyflakes",
    "pylint",
    "ruff",
    "shellcheck",
    "shfmt",
    "stylelint",
    "tsc",
    "vulture",
    "yamllint",
}


# Test/build runners whose explicit purpose is to exercise runtime behavior.
# Calling any of these is genuine executed smoke.
_EXECUTED_TOOL_BASENAMES = {
    "cargo",
    "cypress",
    "dotnet",
    "go",
    "gradle",
    "jest",
    "make",
    "mocha",
    "mvn",
    "playwright",
    "pytest",
    "rake",
    "rspec",
    "vitest",
}


# npm/pnpm/yarn scripts whose name suggests runtime-exercising behavior.
_NPM_EXECUTED_SCRIPT_NAMES = {
    "dev",
    "e2e",
    "integration",
    "run",
    "serve",
    "smoke",
    "smoketest",
    "start",
    "test",
}

# npm/pnpm/yarn scripts whose name suggests purely static tooling.
_NPM_STATIC_SCRIPT_NAMES = {
    "build",
    "check",
    "format",
    "fmt",
    "lint",
    "tsc",
    "typecheck",
}


@dataclass
class SmoketestContext:
    qodeyard_path: Path
    cycle_num: str
    config: dict = field(default_factory=dict)
    smoke_config: dict = field(default_factory=dict)
    adapter_config: dict = field(default_factory=dict)
    mode: str = "full"
    timeout_seconds: int = 45
    max_output_chars: int = 800


class Adapter:
    name: str = "base"
    extensions: tuple[str, ...] = ()

    def preflight(
        self,
        ctx: SmoketestContext,
        scope_files: list[Path],
    ) -> list[SmoketestResult]:
        return []

    def project_smoketest(
        self,
        ctx: SmoketestContext,
        scope_files: list[Path],
    ) -> list[SmoketestResult]:
        return []

    def file_smoketest(
        self,
        ctx: SmoketestContext,
        file_path: Path,
        scope_files: list[Path],
    ) -> list[SmoketestResult]:
        return []

    def run(
        self,
        ctx: SmoketestContext,
        scope_files: list[Path],
    ) -> list[SmoketestResult]:
        """Compatibility shim for older adapters that only implemented run()."""
        results: list[SmoketestResult] = []
        results.extend(self.project_smoketest(ctx, scope_files) or [])
        for file_path in scope_files:
            results.extend(self.file_smoketest(ctx, file_path, scope_files) or [])
        return results


def truncate_output(text: str, max_chars: int) -> str:
    raw = str(text or "")
    if max_chars <= 0:
        return ""
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + "\n...[truncated]"


def rel_name(file_path: Path, qodeyard_path: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(qodeyard_path.resolve()))
    except Exception:
        return str(file_path)


def normalize_command(raw_command: object) -> list[str] | None:
    if raw_command is None:
        return None
    if isinstance(raw_command, str):
        parts = shlex.split(raw_command)
        return parts or None
    if isinstance(raw_command, (list, tuple)):
        values = [str(item).strip() for item in raw_command]
        values = [item for item in values if item]
        return values or None
    return None


def command_to_string(command: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def normalize_execution_kind_value(value: object) -> Optional[str]:
    """Parse a config-supplied execution_kind value.

    Returns the valid execution kind when recognized, None when
    the value means "let the classifier decide" (missing, empty, or "auto").
    """
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw == "auto":
        return None
    # Map legacy static/executed to specific kinds
    if raw == "static":
        return EXECUTION_KIND_STATIC
    if raw in _VALID_EXECUTION_KINDS:
        return raw
    return None


def _classify_npm_style(tool: str, args: list[str]) -> str:
    """Classify npm/pnpm/yarn commands based on the script name.

    Conservative fallback: when uncertain, return static.
    """
    script_name: Optional[str] = None
    if tool in {"npm", "pnpm"}:
        # `npm run <script>`, `npm exec <bin>`, or bare `npm test` / `npm start`.
        if args and args[0] in {"test", "start"}:
            script_name = args[0]
        elif "run" in args:
            idx = args.index("run")
            if idx + 1 < len(args):
                script_name = args[idx + 1]
        elif "exec" in args:
            return EXECUTION_KIND_EXECUTED
    elif tool == "yarn":
        # `yarn <script>` is implicit run for non-package-management verbs.
        if args and args[0] not in {
            "install", "add", "remove", "upgrade", "dedupe",
            "audit", "info", "config", "cache", "why",
        }:
            script_name = args[0]

    if script_name is None:
        # Ambiguous — conservative.
        return EXECUTION_KIND_STATIC
    if script_name in _NPM_EXECUTED_SCRIPT_NAMES:
        return EXECUTION_KIND_EXECUTED
    if script_name in _NPM_STATIC_SCRIPT_NAMES:
        return EXECUTION_KIND_STATIC
    # Unknown script name — conservative.
    return EXECUTION_KIND_STATIC


def classify_command_execution_kind(command: list[str]) -> str:
    """Infer execution_kind from a command vector.

    Contract:
      - Known static checks (py_compile, bash -n, node --check, tsc, linters,
        formatters) => "syntax_probe" or "static_probe".
      - Known runtime-exercising entrypoints (unittest/pytest, test runners,
        `python script.py`, `node script.js`, `npm run test|smoke|...`) =>
        "executed".
      - Anything ambiguous => "static_probe" (conservative default). A subprocess
        running successfully is NEVER grounds to declare executed smoke.
    """
    if not command:
        return EXECUTION_KIND_STATIC
    lower = [str(part).strip().lower() for part in command if str(part).strip()]
    if not lower:
        return EXECUTION_KIND_STATIC

    tool = Path(lower[0]).name
    args = lower[1:]
    flags = set(args)

    # --- Shell: `sh -n`, `bash -n`, etc. are parse-only. ---
    if tool in {"sh", "bash", "zsh", "ksh", "dash"}:
        if "-n" in flags:
            return EXECUTION_KIND_SYNTAX
        # A shell with -c or a script target actually runs code.
        if "-c" in flags:
            return EXECUTION_KIND_EXECUTED
        if args and not args[0].startswith("-"):
            return EXECUTION_KIND_EXECUTED
        return EXECUTION_KIND_STATIC

    # --- Node: --check is parse-only; otherwise it runs code. ---
    if tool == "node":
        if "--check" in flags:
            return EXECUTION_KIND_SYNTAX
        # `node script.js` or `node -e '...'` actually runs code.
        if args:
            return EXECUTION_KIND_EXECUTED
        return EXECUTION_KIND_STATIC

    # --- Known static tooling (covers tsc regardless of --noEmit flag). ---
    if tool in _STATIC_TOOL_BASENAMES:
        return EXECUTION_KIND_STATIC

    # --- Known runtime-exercising tooling. ---
    if tool in _EXECUTED_TOOL_BASENAMES:
        return EXECUTION_KIND_EXECUTED

    # --- Python dispatch. ---
    if tool.startswith("python"):
        if "-m" in flags:
            try:
                module = lower[lower.index("-m") + 1]
            except Exception:
                module = ""
            if module in {"py_compile", "compileall"}:
                return EXECUTION_KIND_SYNTAX
            if module in {"unittest", "pytest"}:
                return EXECUTION_KIND_EXECUTED
            # Unknown -m module: conservative.
            return EXECUTION_KIND_STATIC
        # `python script.py` or `python -c '...'` actually runs code.
        if args:
            return EXECUTION_KIND_EXECUTED
        return EXECUTION_KIND_STATIC

    # --- npm/pnpm/yarn: script-name aware. ---
    if tool in {"npm", "pnpm", "yarn"}:
        return _classify_npm_style(tool, args)

    # --- Unknown tool: conservative. A subprocess running is not evidence. ---
    return EXECUTION_KIND_STATIC


def collect_commands(
    adapter_name: str,
    adapter_config: dict,
) -> list[tuple[str, list[str], Optional[str]]]:
    """Collect configured commands.

    Returns a list of ``(name, command_argv, execution_kind_override)`` triples.
    ``execution_kind_override`` is None when the caller should infer the kind.

    Supported config shapes:

      - Legacy scalar:
            command: "python -m py_compile"
            # optional sibling override:
            execution_kind: static  # or "executed" or "auto"

      - Legacy list (strings or list-of-lists):
            commands:
              - "python -m py_compile"
              - ["node", "--check"]
            execution_kind: static  # adapter-default override

      - Structured list (each entry may have its own kind):
            commands:
              - command: "npm run smoke"
                execution_kind: executed
              - command: "npm run lint"
                execution_kind: static

    Backward compatibility is preserved — configs without ``execution_kind``
    behave exactly as before (the classifier decides).
    """
    adapter_default_kind = normalize_execution_kind_value(
        adapter_config.get("execution_kind")
    )

    commands: list[tuple[str, list[str], Optional[str]]] = []

    raw_many = adapter_config.get("commands")
    if isinstance(raw_many, list):
        for index, raw in enumerate(raw_many, start=1):
            if isinstance(raw, dict):
                cmd = normalize_command(raw.get("command"))
                entry_kind = (
                    normalize_execution_kind_value(raw.get("execution_kind"))
                    or adapter_default_kind
                )
                if cmd:
                    commands.append((f"{adapter_name}:{index}", cmd, entry_kind))
            else:
                cmd = normalize_command(raw)
                if cmd:
                    commands.append(
                        (f"{adapter_name}:{index}", cmd, adapter_default_kind)
                    )

    if not commands:
        single = normalize_command(adapter_config.get("command"))
        if single:
            kind = adapter_default_kind
            # Legacy alias kept for config shapes that used per_file_execution_kind.
            if adapter_config.get("per_file_execution_kind") is not None:
                alt = normalize_execution_kind_value(
                    adapter_config.get("per_file_execution_kind")
                )
                if alt is not None:
                    kind = alt
            commands.append((f"{adapter_name}:command", single, kind))

    return commands


def result_skip(
    adapter: str,
    name: str,
    message: str,
    *,
    execution_kind: str = EXECUTION_KIND_STATIC,
    command: str = "",
    severity: str = SEVERITY_INFO,
    file: str | None = None,
    files: Optional[Iterable[str]] = None,
    related_files: Optional[Iterable[str]] = None,
    scope: str | None = None,
) -> SmoketestResult:
    return SmoketestResult(
        adapter=adapter,
        name=name,
        status=STATUS_SKIP,
        executed=False,
        execution_kind=execution_kind,
        message=message,
        file=file,
        files=sorted(set(files or [])),
        related_files=sorted(set(related_files or [])),
        scope=scope,
        command=command,
        severity=severity,
    )


def run_command(
    adapter: str,
    name: str,
    command: list[str],
    ctx: SmoketestContext,
    scope_files: list[Path],
    *,
    append_changed_files: bool = False,
    execution_kind: str | None = None,
    severity: str | None = None,
    scope: str | None = None,
    target_file: Path | None = None,
) -> SmoketestResult:
    """Run a subprocess and wrap the outcome in a SmoketestResult.

    The caller is responsible for declaring ``execution_kind`` when it knows the
    truth about the command. When unspecified, we fall back to the conservative
    inference in ``classify_command_execution_kind``. The ``executed`` flag on
    the result is derived exclusively from ``execution_kind`` — a subprocess
    exit code of 0 NEVER inflates a static check into "executed".
    """
    related = [rel_name(item, ctx.qodeyard_path) for item in scope_files]
    related = sorted(set(item for item in related if item))
    command_display = command_to_string(command)
    normalized_kind = execution_kind or classify_command_execution_kind(command)
    if normalized_kind not in _VALID_EXECUTION_KINDS:
        normalized_kind = EXECUTION_KIND_STATIC

    # `executed` is True for any kind that exercises runtime behavior.
    is_executed = normalized_kind in {
        EXECUTION_KIND_EXECUTED,
        EXECUTION_KIND_PROCESS_BOOT,
        EXECUTION_KIND_HTTP,
        EXECUTION_KIND_WS,
        EXECUTION_KIND_BROWSER,
    }

    primary_file = rel_name(target_file, ctx.qodeyard_path) if target_file else None
    files = [primary_file] if primary_file else related[:12]

    executable = find_binary(command[0], cwd=ctx.qodeyard_path)
    if executable is None:
        return result_skip(
            adapter,
            name,
            f"Missing required tool: {command[0]}",
            execution_kind=normalized_kind,
            command=command_display,
            severity=SEVERITY_INFO,
            file=primary_file,
            files=files,
            related_files=related,
            scope=scope,
        )

    final_command = [executable] + command[1:]
    if append_changed_files:
        final_command.extend(related)

    start = time.monotonic()
    try:
        proc = subprocess.run(
            final_command,
            cwd=str(ctx.qodeyard_path),
            capture_output=True,
            text=True,
            timeout=max(1, int(ctx.timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return SmoketestResult(
            adapter=adapter,
            name=name,
            status=STATUS_ERROR,
            executed=is_executed,
            execution_kind=normalized_kind,
            message=f"Command timed out after {ctx.timeout_seconds}s",
            file=primary_file,
            files=files,
            related_files=related,
            scope=scope,
            command=command_display,
            duration_ms=elapsed,
            severity=severity or SEVERITY_ERROR,
            stdout=truncate_output(exc.stdout or "", ctx.max_output_chars),
            stderr=truncate_output(exc.stderr or "", ctx.max_output_chars),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return SmoketestResult(
            adapter=adapter,
            name=name,
            status=STATUS_ERROR,
            executed=False,
            execution_kind=normalized_kind,
            message=f"Command execution failed: {exc}",
            file=primary_file,
            files=files,
            related_files=related,
            scope=scope,
            command=command_display,
            duration_ms=elapsed,
            severity=severity or SEVERITY_ERROR,
        )

    elapsed = int((time.monotonic() - start) * 1000)
    status = STATUS_PASS if proc.returncode == 0 else STATUS_FAIL
    summary = "Command passed" if status == STATUS_PASS else f"Command failed (exit {proc.returncode})"
    resolved_severity = severity or (SEVERITY_INFO if status == STATUS_PASS else SEVERITY_ERROR)
    return SmoketestResult(
        adapter=adapter,
        name=name,
        status=status,
        # `executed` is derived from execution_kind, NEVER from subprocess success.
        executed=is_executed,
        execution_kind=normalized_kind,
        message=summary,
        file=primary_file,
        files=files,
        related_files=related,
        scope=scope,
        command=command_display,
        exit_code=proc.returncode,
        duration_ms=elapsed,
        severity=resolved_severity,
        stdout=truncate_output(proc.stdout or "", ctx.max_output_chars),
        stderr=truncate_output(proc.stderr or "", ctx.max_output_chars),
    )


def result_pass(
    adapter: str,
    name: str,
    message: str,
    *,
    execution_kind: str = EXECUTION_KIND_STATIC,
    command: str = "",
    file: str | None = None,
    files: Optional[Iterable[str]] = None,
    related_files: Optional[Iterable[str]] = None,
    scope: str | None = None,
) -> SmoketestResult:
    is_executed = execution_kind in {
        EXECUTION_KIND_EXECUTED,
        EXECUTION_KIND_PROCESS_BOOT,
        EXECUTION_KIND_HTTP,
        EXECUTION_KIND_WS,
        EXECUTION_KIND_BROWSER,
    }
    return SmoketestResult(
        adapter=adapter,
        name=name,
        status=STATUS_PASS,
        executed=is_executed,
        execution_kind=execution_kind,
        message=message,
        file=file,
        files=sorted(set(files or [])),
        related_files=sorted(set(related_files or [])),
        scope=scope,
        command=command,
        severity=SEVERITY_INFO,
    )


def result_fail(
    adapter: str,
    name: str,
    message: str,
    *,
    execution_kind: str = EXECUTION_KIND_STATIC,
    command: str = "",
    file: str | None = None,
    files: Optional[Iterable[str]] = None,
    related_files: Optional[Iterable[str]] = None,
    scope: str | None = None,
    severity: str = SEVERITY_ERROR,
) -> SmoketestResult:
    is_executed = execution_kind in {
        EXECUTION_KIND_EXECUTED,
        EXECUTION_KIND_PROCESS_BOOT,
        EXECUTION_KIND_HTTP,
        EXECUTION_KIND_WS,
        EXECUTION_KIND_BROWSER,
    }
    return SmoketestResult(
        adapter=adapter,
        name=name,
        status=STATUS_FAIL,
        executed=is_executed,
        execution_kind=execution_kind,
        message=message,
        file=file,
        files=sorted(set(files or [])),
        related_files=sorted(set(related_files or [])),
        scope=scope,
        command=command,
        severity=severity,
    )


def result_error(
    adapter: str,
    name: str,
    message: str,
    *,
    execution_kind: str = EXECUTION_KIND_STATIC,
    command: str = "",
    file: str | None = None,
    files: Optional[Iterable[str]] = None,
    related_files: Optional[Iterable[str]] = None,
    scope: str | None = None,
) -> SmoketestResult:
    is_executed = execution_kind in {
        EXECUTION_KIND_EXECUTED,
        EXECUTION_KIND_PROCESS_BOOT,
        EXECUTION_KIND_HTTP,
        EXECUTION_KIND_WS,
        EXECUTION_KIND_BROWSER,
    }
    return SmoketestResult(
        adapter=adapter,
        name=name,
        status=STATUS_ERROR,
        executed=is_executed,
        execution_kind=execution_kind,
        message=message,
        file=file,
        files=sorted(set(files or [])),
        related_files=sorted(set(related_files or [])),
        scope=scope,
        command=command,
        severity=SEVERITY_ERROR,
    )


__all__ = [
    "Adapter",
    "SmoketestContext",
    "classify_command_execution_kind",
    "collect_commands",
    "command_to_string",
    "normalize_command",
    "normalize_execution_kind_value",
    "rel_name",
    "result_error",
    "result_fail",
    "result_pass",
    "result_skip",
    "run_command",
    "truncate_output",
]
