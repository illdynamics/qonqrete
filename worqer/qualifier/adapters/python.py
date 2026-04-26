# worqer/qualifier/adapters/python.py
# ═══════════════════════════════════════════════════════════════════════════════
# Python adapter — qualify_python.
#
# Preserves EVERY check from the v1.3.0 monolith:
#   - compile() syntax check
#   - local-import resolution (stdlib/third-party allowlist + qodeyard lookup)
#   - qontext skeleton / signature comparison (with IGNORE_SYMBOLS)
# Adds:
#   - Ruff (ruff check --output-format=json) when the ruff binary is found
#
# Legacy per-check toggles at verification.checks.{syntax,imports,skeleton_match}
# are honoured bit-for-bit via ctx.python_checks — this keeps existing
# worqspace/config.yaml files working unchanged.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from ..base import (
    Adapter,
    QualifyContext,
    rel_name,
    result_error,
    result_info,
    result_pass,
    result_warn,
)
from ..discovery import find_binary
from ..models import VerificationResult


# ─── preserved allowlists (verbatim from v1.3.0 monolith) ──────────────────

# Imports under these prefixes are NOT checked as "missing local module" —
# they are stdlib or well-known third-party packages that are expected to
# be resolved at runtime, not from the qodeyard tree.
STDLIB_PREFIXES = [
    "os", "sys", "re", "json", "yaml", "time", "datetime", "pathlib",
    "typing", "collections", "itertools", "functools", "dataclasses",
    "logging", "subprocess", "threading", "multiprocessing", "asyncio",
    "ast", "inspect", "importlib", "abc", "copy", "io", "shutil",
    "http", "urllib", "socket", "ssl", "hashlib", "base64", "uuid",
    "math", "random", "statistics", "decimal", "fractions",
    "unittest", "pytest", "mock", "tempfile", "glob", "platform",
    "signal", "warnings", "traceback", "contextlib", "enum",
    "struct", "pickle", "queue", "concurrent",
    "numpy", "pandas", "requests", "flask", "django", "sqlalchemy",
    "openai", "anthropic", "google", "transformers", "torch", "tensorflow",
    "cryptography", "grpc", "proto", "pydantic", "aiohttp", "click",
    "typer", "rich", "fastapi", "celery", "redis", "pymongo",
]

LOCAL_PREFIX_HINTS = ("src.", "lib.", "app.", "core.", "utils.", "tests.")

# Symbols in qontext skeletons that are NOT functions — we must not flag
# these as "expected function missing".
IGNORE_SKELETON_SYMBOLS = {
    "argparse", "sys", "os", "re", "json", "yaml", "time", "datetime",
    "pathlib", "typing", "collections", "logging", "subprocess", "asyncio",
    "hashlib", "base64", "uuid", "math", "random", "io", "shutil",
    "http", "urllib", "socket", "ssl", "ast", "inspect", "functools",
    "itertools", "copy", "pickle", "struct", "tempfile", "glob",
    "threading", "multiprocessing", "queue", "contextlib", "dataclasses",
    "enum", "abc", "warnings", "traceback", "platform", "signal",
    "List", "Dict", "Set", "Tuple", "Optional", "Union", "Any", "Callable",
    "Type", "TypeVar", "Generic", "Protocol", "Literal", "Final",
    "Sequence", "Mapping", "Iterable", "Iterator", "Generator",
    "Awaitable", "Coroutine", "AsyncGenerator", "ClassVar",
    "numpy", "pandas", "requests", "flask", "django", "fastapi",
    "openai", "anthropic", "google", "grpc", "proto", "pydantic",
    "sqlalchemy", "pytest", "click", "typer", "rich", "aiohttp",
    "Path", "Field", "dataclass", "Enum", "ABC",
}


# ─── adapter ───────────────────────────────────────────────────────────────

class PythonAdapter(Adapter):
    name = "python"
    extensions = (".py", ".pyi")

    def preflight(self, ctx: QualifyContext) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        # Ruff is additive. If missing we surface ONE info-level row per
        # run rather than crashing the adapter — spec: "missing external
        # tools are handled explicitly, not by crashing".
        if find_binary("ruff") is None:
            results.append(result_info(
                file_path="-",
                check_type="python:ruff",
                message=(
                    "ruff binary not found on PATH — skipping lint "
                    "checks. Install via `pip install ruff` to enable."
                ),
            ))
        return results

    def qualify(
        self,
        file_path: Path,
        ctx: QualifyContext,
    ) -> list[VerificationResult]:
        rel = rel_name(file_path, ctx.qodeyard_path)
        results: list[VerificationResult] = []

        do_syntax = ctx.python_checks.get("syntax", True)
        do_imports = ctx.python_checks.get("imports", True)
        do_skeleton = ctx.python_checks.get("skeleton_match", True)

        if do_syntax:
            results.extend(_check_syntax(file_path, rel))

        if do_imports:
            local_python_files = ctx.scratch.get("python_local_file_index")
            if local_python_files is None:
                local_python_files = _collect_local_python_files(ctx.qodeyard_path)
                ctx.scratch["python_local_file_index"] = local_python_files
            results.extend(
                _check_imports(
                    file_path,
                    rel,
                    ctx.qodeyard_path,
                    local_python_files=local_python_files,
                )
            )

        if do_skeleton and ctx.qontext_path is not None:
            results.extend(
                _compare_with_qontext(file_path, rel, ctx.qontext_path)
            )

        # Ruff — additive. Runs if binary available. Missing → no-op
        # (preflight already surfaced the info row).
        ruff_bin = find_binary("ruff")
        if ruff_bin is not None:
            results.extend(_run_ruff(file_path, rel, ruff_bin))

        return results


# ─── individual check implementations ──────────────────────────────────────

def _check_syntax(file_path: Path, rel: str) -> list[VerificationResult]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        compile(code, str(file_path), "exec")
        return [result_pass(rel, "syntax", "Syntax OK")]
    except SyntaxError as e:
        return [VerificationResult(
            file_path=rel,
            check_type="syntax",
            passed=False,
            message=str(e.msg),
            line_number=e.lineno,
            severity="error",
        )]
    except Exception as e:
        return [result_error(rel, "syntax", f"Could not parse: {e}")]


def _extract_imports(file_path: Path) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append((node.module, node.lineno))
    except Exception:
        pass
    return imports


def _check_imports(
    file_path: Path,
    rel: str,
    qodeyard_path: Path,
    local_python_files: list[Path] | None = None,
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    imports = _extract_imports(file_path)

    for module_name, line_num in imports:
        # Skip stdlib and well-known third-party
        if any(
            module_name == p or module_name.startswith(p + ".")
            for p in STDLIB_PREFIXES
        ):
            continue

        # Only check imports that look like local project imports
        if not module_name.startswith(LOCAL_PREFIX_HINTS):
            continue

        module_parts = module_name.split(".")

        possible_paths = [
            qodeyard_path / "/".join(module_parts) / "__init__.py",
            qodeyard_path / ("/".join(module_parts) + ".py"),
        ]

        # Also check without the first component
        if len(module_parts) > 1:
            possible_paths.extend([
                qodeyard_path / "/".join(module_parts[1:]) / "__init__.py",
                qodeyard_path / ("/".join(module_parts[1:]) + ".py"),
            ])

        # Recursive search for final module name.
        # File index is cached per run in ctx.scratch to avoid repeated full
        # qodeyard walks for each Python file in a scoped qualification pass.
        final_module = module_parts[-1]
        search_files = local_python_files or _collect_local_python_files(qodeyard_path)
        for f in search_files:
            if f.name == f"{final_module}.py":
                possible_paths.append(f)
            elif f.name == "__init__.py" and f.parent.name == final_module:
                possible_paths.append(f)

        found = any(p.exists() for p in possible_paths)
        if not found:
            results.append(result_warn(
                file_path=rel,
                check_type="import",
                message=f"Local module '{module_name}' not found in qodeyard",
                line_number=line_num,
            ))

    if not results:
        results.append(result_pass(
            rel, "import", "All local imports resolved"
        ))

    return results


def _collect_local_python_files(qodeyard_path: Path) -> list[Path]:
    try:
        from ..runner import _SKIP_DIR_NAMES as _SKIP
    except Exception:
        _SKIP = set()

    stack = [qodeyard_path]
    files: list[Path] = []
    while stack:
        cur = stack.pop()
        try:
            entries = sorted(cur.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in _SKIP or entry.name.startswith("qage_"):
                    continue
                stack.append(entry)
            elif entry.is_file() and entry.suffix in {".py", ".pyi"}:
                files.append(entry)
    return files


def _extract_function_signatures(file_path: Path) -> dict[str, dict]:
    signatures: dict[str, dict] = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = []
                for arg in node.args.args:
                    arg_info: dict = {"name": arg.arg}
                    if arg.annotation:
                        try:
                            arg_info["type"] = ast.unparse(arg.annotation)
                        except Exception:
                            pass
                    args.append(arg_info)
                signatures[node.name] = {
                    "args": args,
                    "line": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "returns": (
                        ast.unparse(node.returns) if node.returns else None
                    ),
                }
    except Exception:
        pass
    return signatures


def _compare_with_qontext(
    file_path: Path,
    rel: str,
    qontext_path: Path,
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    qontext_file = qontext_path / (file_path.name + ".q.yaml")
    if not qontext_file.exists():
        return results

    try:
        with open(qontext_file, "r", encoding="utf-8") as f:
            qontext_data = yaml.safe_load(f) or {}
        expected_symbols = qontext_data.get("symbols", []) or []
        if not expected_symbols:
            return results

        actual_signatures = _extract_function_signatures(file_path)

        for symbol in expected_symbols:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                symbol_type = symbol.get("type", "")

                if name in IGNORE_SKELETON_SYMBOLS:
                    continue
                if symbol_type in (
                    "import", "module", "class", "type", "constant",
                ):
                    continue
                if len(name) == 1:
                    continue
                # Uppercase-leading names are classes/types unless flagged
                if name and name[0].isupper() and symbol_type != "function":
                    continue
                if name and name not in actual_signatures:
                    results.append(result_warn(
                        file_path=rel,
                        check_type="signature",
                        message=f"Expected function '{name}' not found",
                    ))
    except Exception:
        # Non-fatal — matches v1.3.0 behaviour
        pass
    return results


def _run_ruff(
    file_path: Path,
    rel: str,
    ruff_bin: str,
) -> list[VerificationResult]:
    """Run ruff check in JSON mode and normalize diagnostics."""
    try:
        proc = subprocess.run(
            [ruff_bin, "check", "--output-format=json", "--force-exclude",
             "--no-fix", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "python:ruff", "ruff timed out (>30s)")]
    except Exception as exc:
        return [result_warn(rel, "python:ruff", f"ruff invocation failed: {exc}")]

    # Ruff exits 0 = clean, 1 = violations found, other = internal error
    if proc.returncode not in (0, 1):
        stderr = (proc.stderr or "").strip()
        return [result_warn(
            rel, "python:ruff",
            f"ruff error (rc={proc.returncode}): {stderr[:200]}",
        )]

    if proc.returncode == 0 and not (proc.stdout or "").strip():
        return [result_pass(rel, "python:ruff", "ruff clean")]

    try:
        diagnostics = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return [result_warn(
            rel, "python:ruff",
            "ruff produced non-JSON output",
        )]

    out: list[VerificationResult] = []
    for d in diagnostics:
        code = d.get("code") or "E???"
        msg = d.get("message") or "ruff violation"
        line = _ruff_line(d)
        out.append(result_warn(
            file_path=rel,
            check_type="python:ruff",
            message=f"{code}: {msg}",
            line_number=line,
        ))
    if not out:
        out.append(result_pass(rel, "python:ruff", "ruff clean"))
    return out


def _ruff_line(d: dict) -> Optional[int]:
    loc = d.get("location") or {}
    if isinstance(loc, dict) and "row" in loc:
        try:
            return int(loc["row"])
        except (TypeError, ValueError):
            return None
    return None


__all__ = ["PythonAdapter"]
