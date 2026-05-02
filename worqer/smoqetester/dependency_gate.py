from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .discovery import find_binary
from .models import (
    EXECUTION_KIND_STATIC,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    SmoketestResult,
)
from .python_bootstrap import provision_validation_env


PY_MANIFESTS = [
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "poetry.lock",
    "uv.lock",
    "setup.py",
    "setup.cfg",
]

NETWORK_FAILURE_PATTERNS = (
    "temporary failure in name resolution",
    "name or service not known",
    "failed to establish a new connection",
    "network is unreachable",
    "connection timed out",
    "timed out",
    "econnreset",
    "etimedout",
    "unable to fetch",
    "failed to fetch",
    "registry.npmjs.org",
    "pypi.org",
)

PY_IMPORT_PACKAGE_MAP = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "flask": "flask",
    "requests": "requests",
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "pil": "pillow",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "jwt": "pyjwt",
}

NODE_BUILTINS = {
    "assert",
    "buffer",
    "child_process",
    "crypto",
    "events",
    "fs",
    "http",
    "https",
    "net",
    "os",
    "path",
    "stream",
    "timers",
    "tls",
    "url",
    "util",
    "zlib",
}


def _result(
    *,
    name: str,
    status: str,
    message: str,
    severity: str = SEVERITY_INFO,
    command: str = "",
    files: list[str] | None = None,
    failure_kind: str | None = None,
    environment_blocked: bool = False,
    stdout: str = "",
    stderr: str = "",
) -> SmoketestResult:
    return SmoketestResult(
        adapter="dependency_gate",
        name=name,
        status=status,
        executed=False,
        execution_kind=EXECUTION_KIND_STATIC,
        message=message,
        files=sorted(set(files or [])),
        related_files=sorted(set(files or [])),
        scope="project",
        command=command,
        severity=severity,
        failure_kind=failure_kind,
        environment_blocked=environment_blocked,
        stdout=stdout[:1200],
        stderr=stderr[:1200],
    )


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path.name)


def _detect_managers(qodeyard: Path) -> list[dict]:
    managers: list[dict] = []
    py_found = [name for name in PY_MANIFESTS if (qodeyard / name).exists()]
    if py_found:
        managers.append({"ecosystem": "python", "manifests": py_found})
    if (qodeyard / "package.json").exists():
        manifests = ["package.json"]
        for name in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"):
            if (qodeyard / name).exists():
                manifests.append(name)
        managers.append({"ecosystem": "node", "manifests": manifests})
    if (qodeyard / "Cargo.toml").exists():
        manifests = ["Cargo.toml"]
        if (qodeyard / "Cargo.lock").exists():
            manifests.append("Cargo.lock")
        managers.append({"ecosystem": "rust", "manifests": manifests})
    if (qodeyard / "go.mod").exists():
        manifests = ["go.mod"]
        if (qodeyard / "go.sum").exists():
            manifests.append("go.sum")
        managers.append({"ecosystem": "go", "manifests": manifests})
    if (qodeyard / "Gemfile").exists():
        manifests = ["Gemfile"]
        if (qodeyard / "Gemfile.lock").exists():
            manifests.append("Gemfile.lock")
        managers.append({"ecosystem": "ruby", "manifests": manifests})
    if (qodeyard / "composer.json").exists():
        manifests = ["composer.json"]
        if (qodeyard / "composer.lock").exists():
            manifests.append("composer.lock")
        managers.append({"ecosystem": "php", "manifests": manifests})
    return managers


def _looks_like_registry_error(stdout: str, stderr: str) -> bool:
    combined = ((stdout or "") + "\n" + (stderr or "")).lower()
    return any(token in combined for token in NETWORK_FAILURE_PATTERNS)


def _looks_like_resolution_error(stdout: str, stderr: str) -> bool:
    combined = ((stdout or "") + "\n" + (stderr or "")).lower()
    markers = (
        "could not find a version that satisfies",
        "no matching distribution found",
        "resolution impossible",
        "unable to resolve dependency tree",
        "version solving failed",
        "conflict",
    )
    return any(token in combined for token in markers)


def _parse_requirements(content: str) -> set[str]:
    deps: set[str] = set()
    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.split(r"[<>=!~\[\]; ]", line, maxsplit=1)[0]
        normalized = line.strip().lower().replace("_", "-")
        if normalized:
            deps.add(normalized)
    return deps


def _collect_python_import_roots(qodeyard: Path) -> set[str]:
    roots: set[str] = set()
    for py_file in sorted(qodeyard.rglob("*.py")):
        if "/.venv/" in str(py_file).replace("\\", "/"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0].lower())
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0].lower())
    return roots


def _missing_python_declarations(qodeyard: Path, manifests: list[str]) -> list[str]:
    declared: set[str] = set()
    req_path = qodeyard / "requirements.txt"
    if req_path.exists():
        declared.update(_parse_requirements(req_path.read_text(encoding="utf-8", errors="ignore")))

    pyproject = qodeyard / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="ignore").lower().replace("_", "-")
        for package in set(PY_IMPORT_PACKAGE_MAP.values()):
            if package in text:
                declared.add(package)

    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    missing: set[str] = set()
    for root in _collect_python_import_roots(qodeyard):
        if root in stdlib:
            continue
        if (qodeyard / f"{root}.py").exists() or (qodeyard / root).is_dir():
            continue
        package = PY_IMPORT_PACKAGE_MAP.get(root, root).replace("_", "-")
        if declared and package not in declared:
            missing.add(package)
    return sorted(missing)


def _collect_node_imports(qodeyard: Path) -> set[str]:
    imports: set[str] = set()
    pattern_import = re.compile(r"""import\s+(?:[^'"]+\s+from\s+)?['"]([^'"]+)['"]""")
    pattern_require = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
    for ext in ("*.js", "*.jsx", "*.mjs", "*.cjs", "*.ts", "*.tsx"):
        for file_path in sorted(qodeyard.rglob(ext)):
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for match in pattern_import.findall(content):
                imports.add(match)
            for match in pattern_require.findall(content):
                imports.add(match)
    normalized: set[str] = set()
    for item in imports:
        if not item or item.startswith(".") or item.startswith("/"):
            continue
        if item.startswith("node:"):
            continue
        root = item.split("/")[0]
        if root.startswith("@") and "/" in item:
            root = "/".join(item.split("/")[:2])
        if root in NODE_BUILTINS:
            continue
        normalized.add(root)
    return normalized


def _missing_node_declarations(qodeyard: Path) -> list[str]:
    package_json = qodeyard / "package.json"
    if not package_json.exists():
        return []
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return []

    declared: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        section = payload.get(key)
        if isinstance(section, dict):
            declared.update(str(name).strip() for name in section.keys() if str(name).strip())
    if not declared:
        return []
    missing = sorted(dep for dep in _collect_node_imports(qodeyard) if dep not in declared)
    return missing


def _run_command(command: list[str], qodeyard: Path, timeout_seconds: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(qodeyard),
        capture_output=True,
        text=True,
        timeout=max(20, timeout_seconds),
        check=False,
    )


def _node_install_command(qodeyard: Path) -> tuple[list[str], str] | tuple[None, str]:
    if (qodeyard / "pnpm-lock.yaml").exists():
        tool = find_binary("pnpm", cwd=qodeyard)
        return ([tool, "install", "--frozen-lockfile"], "pnpm") if tool else (None, "pnpm")
    if (qodeyard / "yarn.lock").exists():
        tool = find_binary("yarn", cwd=qodeyard)
        return ([tool, "install", "--frozen-lockfile"], "yarn") if tool else (None, "yarn")
    if (qodeyard / "bun.lockb").exists():
        tool = find_binary("bun", cwd=qodeyard)
        return ([tool, "install"], "bun") if tool else (None, "bun")
    tool = find_binary("npm", cwd=qodeyard)
    if not tool:
        return None, "npm"
    if (qodeyard / "package-lock.json").exists() or (qodeyard / "npm-shrinkwrap.json").exists():
        return [tool, "ci"], "npm"
    return [tool, "install"], "npm"


def run_dependency_gate(ctx, active_files: list[Path]) -> list[SmoketestResult]:
    qodeyard = Path(ctx.qodeyard_path)
    managers = _detect_managers(qodeyard)
    if not managers:
        return [_result(
            name="dependency_gate:not_detected",
            status=STATUS_PASS,
            message="No dependency manager manifests detected in project scope.",
            files=[_safe_rel(path, qodeyard) for path in active_files[:8] if path.exists()],
        )]

    results: list[SmoketestResult] = []

    for manager in managers:
        ecosystem = manager["ecosystem"]
        manifests = manager["manifests"]
        manifest_label = ", ".join(manifests)

        if ecosystem == "python":
            missing = _missing_python_declarations(qodeyard, manifests)
            if missing:
                results.append(_result(
                    name="dependency_gate:python_declarations",
                    status=STATUS_FAIL,
                    severity=SEVERITY_ERROR,
                    message="Dependency not declared: " + ", ".join(missing),
                    files=manifests,
                    failure_kind="dependency_not_declared",
                    environment_blocked=False,
                ))
                continue

            env_root = Path(os.environ.get("QONQ_WORKSPACE", str(qodeyard.parent)))
            python_bin, err = provision_validation_env(env_root, qodeyard)
            if python_bin:
                results.append(_result(
                    name="dependency_gate:python_provision",
                    status=STATUS_PASS,
                    message=f"Python dependencies provisioned in isolated validation env from {manifest_label}.",
                    files=manifests,
                    command="python -m venv + pip install ...",
                ))
                continue

            if err:
                if _looks_like_registry_error("", err):
                    results.append(_result(
                        name="dependency_gate:python_provision",
                        status=STATUS_ERROR,
                        severity=SEVERITY_ERROR,
                        message="Package registry unavailable while provisioning Python dependencies.",
                        files=manifests,
                        failure_kind="package_registry_unavailable",
                        environment_blocked=True,
                        stderr=err,
                    ))
                else:
                    results.append(_result(
                        name="dependency_gate:python_provision",
                        status=STATUS_FAIL,
                        severity=SEVERITY_ERROR,
                        message="Python dependency resolution failed during provisioning.",
                        files=manifests,
                        failure_kind="dependency_resolution_failed",
                        environment_blocked=False,
                        stderr=err,
                    ))
                continue

            results.append(_result(
                name="dependency_gate:python_provision",
                status=STATUS_PASS,
                message=f"Python manifests detected ({manifest_label}); no provisioning action required.",
                files=manifests,
            ))
            continue

        if ecosystem == "node":
            missing = _missing_node_declarations(qodeyard)
            if missing:
                results.append(_result(
                    name="dependency_gate:node_declarations",
                    status=STATUS_FAIL,
                    severity=SEVERITY_ERROR,
                    message="Dependency not declared: " + ", ".join(missing),
                    files=manifests,
                    failure_kind="dependency_not_declared",
                    environment_blocked=False,
                ))
                continue

            command, tool_name = _node_install_command(qodeyard)
            if not command:
                results.append(_result(
                    name="dependency_gate:node_install",
                    status=STATUS_ERROR,
                    severity=SEVERITY_ERROR,
                    message=f"Unavailable external tool: {tool_name}",
                    files=manifests,
                    failure_kind="unavailable_external_tool",
                    environment_blocked=True,
                ))
                continue

            proc = _run_command(command, qodeyard, timeout_seconds=max(45, int(ctx.timeout_seconds) * 3))
            if proc.returncode == 0:
                results.append(_result(
                    name="dependency_gate:node_install",
                    status=STATUS_PASS,
                    message=f"Node dependencies installed using {' '.join(command)}.",
                    files=manifests,
                    command=" ".join(command),
                    stdout=proc.stdout,
                ))
            elif _looks_like_registry_error(proc.stdout, proc.stderr):
                results.append(_result(
                    name="dependency_gate:node_install",
                    status=STATUS_ERROR,
                    severity=SEVERITY_ERROR,
                    message="Package registry unavailable during Node dependency install.",
                    files=manifests,
                    command=" ".join(command),
                    failure_kind="package_registry_unavailable",
                    environment_blocked=True,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                ))
            else:
                kind = "dependency_resolution_failed" if _looks_like_resolution_error(proc.stdout, proc.stderr) else "dependency_resolution_failed"
                results.append(_result(
                    name="dependency_gate:node_install",
                    status=STATUS_FAIL,
                    severity=SEVERITY_ERROR,
                    message="Node dependency resolution failed.",
                    files=manifests,
                    command=" ".join(command),
                    failure_kind=kind,
                    environment_blocked=False,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                ))
            continue

        tool_by_ecosystem = {
            "rust": ("cargo", ["cargo", "fetch"]),
            "go": ("go", ["go", "mod", "download"]),
            "ruby": ("bundle", ["bundle", "install"]),
            "php": ("composer", ["composer", "install", "--no-interaction", "--no-progress"]),
        }
        tool_name, command = tool_by_ecosystem.get(ecosystem, (None, None))
        if not tool_name or not command:
            continue
        tool_path = find_binary(tool_name, cwd=qodeyard)
        if not tool_path:
            results.append(_result(
                name=f"dependency_gate:{ecosystem}_install",
                status=STATUS_ERROR,
                severity=SEVERITY_ERROR,
                message=f"Unavailable external tool: {tool_name}",
                files=manifests,
                failure_kind="unavailable_external_tool",
                environment_blocked=True,
            ))
            continue
        command = [tool_path, *command[1:]]
        proc = _run_command(command, qodeyard, timeout_seconds=max(45, int(ctx.timeout_seconds) * 3))
        if proc.returncode == 0:
            results.append(_result(
                name=f"dependency_gate:{ecosystem}_install",
                status=STATUS_PASS,
                message=f"{ecosystem} dependencies prepared via {' '.join(command)}.",
                files=manifests,
                command=" ".join(command),
                stdout=proc.stdout,
            ))
        elif _looks_like_registry_error(proc.stdout, proc.stderr):
            results.append(_result(
                name=f"dependency_gate:{ecosystem}_install",
                status=STATUS_ERROR,
                severity=SEVERITY_ERROR,
                message="Package registry unavailable during dependency install.",
                files=manifests,
                command=" ".join(command),
                failure_kind="package_registry_unavailable",
                environment_blocked=True,
                stdout=proc.stdout,
                stderr=proc.stderr,
            ))
        else:
            results.append(_result(
                name=f"dependency_gate:{ecosystem}_install",
                status=STATUS_FAIL,
                severity=SEVERITY_ERROR,
                message=f"{ecosystem} dependency resolution failed.",
                files=manifests,
                command=" ".join(command),
                failure_kind="dependency_resolution_failed",
                environment_blocked=False,
                stdout=proc.stdout,
                stderr=proc.stderr,
            ))

    return results


__all__ = ["run_dependency_gate"]
