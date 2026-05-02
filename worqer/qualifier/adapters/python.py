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
import re
import sys
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
# they are stdlib modules.
STDLIB_PREFIXES = {
    "os", "sys", "re", "json", "yaml", "time", "datetime", "pathlib",
    "typing", "collections", "itertools", "functools", "dataclasses",
    "logging", "subprocess", "threading", "multiprocessing", "asyncio",
    "ast", "inspect", "importlib", "abc", "copy", "io", "shutil",
    "http", "urllib", "socket", "ssl", "hashlib", "base64", "uuid",
    "math", "random", "statistics", "decimal", "fractions",
    "unittest", "pytest", "mock", "tempfile", "glob", "platform",
    "signal", "warnings", "traceback", "contextlib", "enum",
    "struct", "pickle", "queue", "concurrent",
}
# v1.4.0: Dynamic stdlib detection (Python 3.10+)
if hasattr(sys, "stdlib_module_names"):
    STDLIB_PREFIXES.update(sys.stdlib_module_names)

# Known third-party packages that must be declared in manifests.
KNOWN_THIRD_PARTY_PREFIXES = {
    "numpy", "pandas", "requests", "flask", "django", "sqlalchemy",
    "openai", "anthropic", "google", "transformers", "torch", "tensorflow",
    "cryptography", "grpc", "proto", "pydantic", "aiohttp", "click",
    "typer", "rich", "fastapi", "celery", "redis", "pymongo",
}

# Common mapping from import name to package name in requirements.txt
IMPORT_TO_PACKAGE_MAP = {
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "cv2": "opencv-python",
}

LOCAL_PREFIX_HINTS = ["src.", "lib.", "app.", "core.", "utils.", "tests."]

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
    "Path", "Field", "dataclass", "Enum", "ABC",
}
IGNORE_SKELETON_SYMBOLS.update(STDLIB_PREFIXES)
IGNORE_SKELETON_SYMBOLS.update(KNOWN_THIRD_PARTY_PREFIXES)


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
                    ctx=ctx,
                    local_python_files=local_python_files,
                )
            )

        if do_skeleton and ctx.qontext_path is not None:
            results.extend(
                _compare_with_qontext(file_path, rel, ctx.qontext_path, ctx=ctx)
            )

        # Ruff — additive. Runs if binary available. Missing → no-op
        # (preflight already surfaced the info row).
        ruff_bin = find_binary("ruff")
        if ruff_bin is not None:
            results.extend(_run_ruff(file_path, rel, ruff_bin, ctx))

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


def _collect_manifest_dependencies(qodeyard_path: Path) -> set[str]:
    """Collect declared package names from common Python manifests."""
    deps = set()
    # requirements.txt
    reqs = qodeyard_path / "requirements.txt"
    if reqs.exists():
        try:
            text = reqs.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-r", "-e")):
                    continue
                # Match name before version specifiers or environment markers
                match = re.match(r'^([a-zA-Z0-9\-_.]+)', line)
                if match:
                    deps.add(match.group(1).lower().replace("_", "-"))
        except Exception:
            pass

    # pyproject.toml (simple regex parser to avoid toml dependency)
    pyproject = qodeyard_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            # Look for dependencies = [ ... ]
            m = re.search(r'dependencies\s*=\s*\[(.*?)\]', text, re.DOTALL)
            if m:
                for dep in re.findall(r'["\']([a-zA-Z0-9\-_.]+)', m.group(1)):
                    deps.add(dep.lower().replace("_", "-"))
        except Exception:
            pass
    return deps


def _detect_local_package_roots(qodeyard_path: Path) -> list[str]:
    """Dynamically detect local package roots (dirs with __init__.py or project name)."""
    roots = []
    # 1. Any top-level dir with __init__.py is a local package
    if qodeyard_path.exists():
        try:
            for entry in qodeyard_path.iterdir():
                if entry.is_dir() and (entry / "__init__.py").exists():
                    roots.append(entry.name)
        except OSError:
            pass

    # 2. Check pyproject.toml for project name
    pyproject = qodeyard_path / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
            if m:
                roots.append(m.group(1).replace("-", "_"))
        except Exception:
            pass
    return sorted(set(roots))


def _resolve_local_import(
    module_name: str,
    qodeyard_path: Path,
    local_python_files: list[Path],
) -> bool:
    """True if the module can be resolved locally in the qodeyard."""
    module_parts = module_name.split(".")
    
    # Direct relative-to-root check
    possible_paths = [
        qodeyard_path / "/".join(module_parts) / "__init__.py",
        qodeyard_path / ("/".join(module_parts) + ".py"),
    ]

    # Handle common 'src.' or 'lib.' patterns if they exist
    if len(module_parts) > 1:
        possible_paths.extend([
            qodeyard_path / "/".join(module_parts[1:]) / "__init__.py",
            qodeyard_path / ("/".join(module_parts[1:]) + ".py"),
        ])

    # Check the probes
    if any(p.exists() for p in possible_paths):
        return True

    # Recursive search for final module name in the index
    final_module = module_parts[-1]
    for f in local_python_files:
        if f.name == f"{final_module}.py":
            return True
        elif f.name == "__init__.py" and f.parent.name == final_module:
            return True
            
    return False


def _check_imports(
    file_path: Path,
    rel: str,
    qodeyard_path: Path,
    ctx: QualifyContext,
    local_python_files: list[Path] | None = None,
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    imports = _extract_imports(file_path)

    # Cache dynamic lookups in ctx.scratch
    local_package_roots = ctx.scratch.get("python_local_package_roots")
    if local_package_roots is None:
        local_package_roots = _detect_local_package_roots(qodeyard_path)
        ctx.scratch["python_local_package_roots"] = local_package_roots

    manifest_dependencies = ctx.scratch.get("python_manifest_dependencies")
    if manifest_dependencies is None:
        manifest_dependencies = _collect_manifest_dependencies(qodeyard_path)
        ctx.scratch["python_manifest_dependencies"] = manifest_dependencies

    python_index = local_python_files or _collect_local_python_files(qodeyard_path)

    for module_name, line_num in imports:
        root_module = module_name.split(".")[0]

        # 1. Standard Library?
        if root_module in STDLIB_PREFIXES:
            continue

        # 2. Local Project?
        is_local_hint = any(module_name.startswith(p) for p in LOCAL_PREFIX_HINTS)
        is_local_root = root_module in local_package_roots
        
        if is_local_hint or is_local_root:
            if not _resolve_local_import(module_name, qodeyard_path, python_index):
                results.append(result_warn(
                    file_path=rel,
                    check_type="import",
                    message=f"Local module '{module_name}' not found in qodeyard",
                    line_number=line_num,
                ))
            continue

        # 3. Third-party?
        # Check against manifest declaration
        package_name = IMPORT_TO_PACKAGE_MAP.get(root_module, root_module).lower().replace("_", "-")
        if package_name in manifest_dependencies:
            continue
            
        # Undeclared dependency
        severity = "error" if ctx.tier in {"medium", "high"} else "warning"
        results.append(VerificationResult(
            file_path=rel,
            check_type="import:undeclared",
            passed=False,
            message=f"Undeclared third-party dependency: '{root_module}' (not in requirements.txt or pyproject.toml)",
            line_number=line_num,
            severity=severity,
        ))

    if not results:
        results.append(result_pass(
            rel, "import", "All imports resolved"
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
    ctx: QualifyContext,
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
                    # v1.4.0: Tier-aware severity for skeleton mismatch
                    severity = "error" if ctx.tier in {"medium", "high"} else "warning"
                    results.append(VerificationResult(
                        file_path=rel,
                        check_type="signature",
                        passed=False,
                        message=f"Expected function '{name}' not found",
                        severity=severity,
                    ))
    except Exception:
        # Non-fatal — matches v1.3.0 behaviour
        pass
    return results


def _run_ruff(
    file_path: Path,
    rel: str,
    ruff_bin: str,
    ctx: QualifyContext,
) -> list[VerificationResult]:
    """Run ruff check in JSON mode and normalize diagnostics."""
    timeout = int(ctx.config.get("verification", {}).get("timeout_seconds_ruff", 30))
    try:
        proc = subprocess.run(
            [ruff_bin, "check", "--output-format=json", "--force-exclude",
             "--no-fix", str(file_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "python:ruff", f"ruff timed out (>{timeout}s)")]
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
