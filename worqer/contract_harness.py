from __future__ import annotations

import ast
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
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


IMPORT_TO_PACKAGE = {
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

DECLARED_BY_TRANSITIVE_PROVIDER = {
    # FastAPI bundles pydantic usage for this harness contract.
    "pydantic": {"fastapi"},
}

ENV_REGISTRY_PATTERNS = (
    "temporary failure in name resolution",
    "name or service not known",
    "failed to establish a new connection",
    "network is unreachable",
    "connection timed out",
    "econnreset",
    "etimedout",
    "unable to fetch",
    "failed to fetch",
    "package registry unavailable",
)


def detect_harness_class(task_text: str) -> str | None:
    if "fastapi" in task_text.lower() and "user" in task_text.lower():
        return "fastapi_users_memory_api.v1"
    return None


def build_harness(task_text: str, existing_qontract: dict | None = None) -> dict:
    return {
        "schema_version": "harness-result.v1",
        "harness_id": detect_harness_class(task_text),
        "required_files": ["main.py", "requirements.txt", "run.sh"],
    }


def write_harness(worqspace_root: Path, harness: dict) -> None:
    qontract_dir = worqspace_root / "qontract.d"
    qontract_dir.mkdir(parents=True, exist_ok=True)
    with open(qontract_dir / "qontract-harness.v1.json", "w", encoding="utf-8") as f:
        json.dump(harness, f, indent=2)
    with open(qontract_dir / "qontract-harness.md", "w", encoding="utf-8") as f:
        f.write("# Deterministic Acceptance Harness\n\n```json\n" + json.dumps(harness, indent=2) + "\n```")


def load_harness(worqspace_root: Path) -> dict:
    p = worqspace_root / "qontract.d" / "qontract-harness.v1.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def apply_autofixes(qodeyard: Path, harness: dict) -> dict:
    if not harness.get("harness_id"):
        return {}
    applied: list[str] = []

    req_file = qodeyard / "requirements.txt"
    requirements = _read_text(req_file).lower()
    if not req_file.exists() or "fastapi" not in requirements or "uvicorn" not in requirements:
        req_file.write_text("fastapi\nuvicorn\n", encoding="utf-8")
        applied.append("requirements.txt")

    run_file = qodeyard / "run.sh"
    expected = "#!/bin/sh\nset -eu\npython -m uvicorn main:app --reload --port \"$PORT\"\n"
    if not run_file.exists() or _read_text(run_file) != expected:
        run_file.write_text(expected, encoding="utf-8")
        run_file.chmod(run_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        applied.append("run.sh")

    return {"autofixes_applied": applied}


def run_harness(qodeyard: Path, harness: dict, *, apply_fixes: bool = False) -> dict:
    harness_id = harness.get("harness_id")
    if not harness_id:
        return {"passed": True, "status": "PASS", "completion_override": {"allowed": False}}

    result = {
        "schema_version": "harness-result.v1",
        "harness_id": harness_id,
        "status": "PASS",
        "passed": True,
        "verdict_classification": "PASS",
        "required_files": {"status": "PASS", "missing": [], "present": []},
        "static_checks": [],
        "behavior_checks": [],
        "autofixes_applied": [],
        "violations": [],
        "repair_directive": "",
        "completion_override": {
            "allowed": True,
            "task_completed": True,
            "repair_required": False,
            "evidence_status": "EVIDENCE_COMPLETE",
        },
    }

    if apply_fixes:
        result["autofixes_applied"] = apply_autofixes(qodeyard, harness).get("autofixes_applied", [])

    required_files = harness.get("required_files", [])
    for rf in required_files:
        path = qodeyard / rf
        if not path.exists():
            result["required_files"]["missing"].append(rf)
        else:
            result["required_files"]["present"].append(rf)

    if result["required_files"]["missing"]:
        result["required_files"]["status"] = "FAIL"
        for missing in result["required_files"]["missing"]:
            _add_violation(
                result,
                "FAIL_REQUIRED_SHELLSCRIPT_MISSING" if missing == "run.sh" else "FAIL_REQUIRED_FILE_MISSING",
                f"Required file missing: {missing}",
                file=missing,
            )
        return _finalize_fail(result, "FAIL: required shellscript missing")

    main_py = qodeyard / "main.py"
    req_file = qodeyard / "requirements.txt"
    run_sh = qodeyard / "run.sh"

    main_content = _read_text(main_py)
    requirements_content = _read_text(req_file)
    run_content = _read_text(run_sh)

    port_literal = _extract_port_literal(main_content)
    if port_literal != 8000:
        _add_violation(
            result,
            "FAIL_CODE_BEHAVIOR",
            "main.py must define `PORT = 8000` near the top.",
            file="main.py",
            expected="PORT = 8000",
        )

    if not re.search(
        r"#\s*run with:\s*\n\s*#\s*uvicorn\s+main:app\s+--reload\s+--port\s+\$PORT",
        main_content,
        flags=re.IGNORECASE,
    ):
        _add_violation(
            result,
            "FAIL_SHELLSCRIPT_CONTRACT",
            "main.py run instruction comment must reference `$PORT` exactly.",
            file="main.py",
            expected="# Run with:\\n# uvicorn main:app --reload --port $PORT",
        )

    for msg in _validate_user_model_fields(main_content):
        _add_violation(
            result,
            "FAIL_CODE_BEHAVIOR",
            msg,
            file="main.py",
            expected="User model must contain exactly: id, username, email, password",
        )

    missing_packages = _missing_declared_python_dependencies(main_content, requirements_content, qodeyard)
    if missing_packages:
        _add_violation(
            result,
            "FAIL_DEPENDENCY_DECLARATION",
            "Missing dependency declarations: " + ", ".join(sorted(missing_packages)),
            file="requirements.txt",
            expected="Declared dependencies include all imported third-party packages",
            actual="Missing: " + ", ".join(sorted(missing_packages)),
        )

    if _has_violation(result, "FAIL_DEPENDENCY_DECLARATION"):
        return _finalize_fail(result, "FAIL: dependency not declared")
    if _has_violation(result, "FAIL_SHELLSCRIPT_CONTRACT"):
        return _finalize_fail(result, "FAIL: shellscript contract mismatch")
    if _has_violation(result, "FAIL_CODE_BEHAVIOR"):
        return _finalize_fail(result, "FAIL: code behavior mismatch")

    shell_mode = pick_shell_mode(run_sh, run_content)
    shell_bin = shutil.which(shell_mode) or shutil.which("sh")
    if not shell_bin:
        _add_violation(
            result,
            "ENVIRONMENT_BLOCKED_UNAVAILABLE_TOOL",
            f"Unavailable external tool: {shell_mode}",
            file="run.sh",
        )
        return _finalize_fail(result, "ENVIRONMENT_BLOCKED: unavailable external tool")

    syntax = subprocess.run(
        [shell_bin, "-n", str(run_sh)],
        capture_output=True,
        text=True,
        check=False,
    )
    if syntax.returncode != 0:
        _add_violation(
            result,
            "FAIL_SHELLSCRIPT_SYNTAX",
            "run.sh failed shell syntax check.",
            file="run.sh",
            command=f"{shell_bin} -n run.sh",
            stderr=(syntax.stderr or syntax.stdout or "").strip(),
        )
        return _finalize_fail(result, "FAIL: shellscript syntax error")

    for msg in validate_run_sh_contract(run_content, "exact_variable_port"):
        _add_violation(
            result,
            "FAIL_SHELLSCRIPT_CONTRACT",
            f"run.sh contract mismatch: {msg}",
            file="run.sh",
            expected="python -m uvicorn main:app --reload --port $PORT",
        )
    if _has_violation(result, "FAIL_SHELLSCRIPT_CONTRACT"):
        return _finalize_fail(result, "FAIL: shellscript contract mismatch")

    unsafe = detect_unsafe_commands(run_content)
    if unsafe:
        _add_violation(
            result,
            "SKIPPED_UNSAFE_COMMAND",
            "run.sh contains unsafe command patterns; launch skipped.",
            file="run.sh",
            actual=", ".join(unsafe),
        )
        return _finalize_fail(result, "SKIPPED_UNSAFE_COMMAND")

    if not os.access(run_sh, os.X_OK):
        result["behavior_checks"].append({
            "check_id": "shell_executable",
            "status": "PARTIAL",
            "message": "run.sh is not executable; continuing by invoking via shell runtime.",
        })

    launch = _launch_and_exercise_server(qodeyard, run_sh, shell_bin, port_literal or 8000)
    if launch["classification"] != "PASS":
        _add_violation(
            result,
            launch["code"],
            launch["message"],
            file="run.sh",
            command=launch.get("command"),
            stdout=launch.get("stdout", ""),
            stderr=launch.get("stderr", ""),
        )
        return _finalize_fail(result, launch["classification"])

    return result


def render_harness_markdown(harness: dict) -> str:
    return "# Harness\n\n```json\n" + json.dumps(harness, indent=2) + "\n```"


def render_result_markdown(result: dict) -> str:
    return "# Harness Result\n\n```json\n" + json.dumps(result, indent=2) + "\n```"


def build_repair_directive(result: dict) -> str:
    if result.get("passed", False):
        return ""
    issues = [v.get("message", "") for v in result.get("violations", []) if v.get("message")]
    return "Fix the following issues strictly to satisfy the acceptance harness: " + " | ".join(issues)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_port_literal(main_content: str) -> int | None:
    try:
        tree = ast.parse(main_content or "")
    except Exception:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not node.targets:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "PORT":
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                return node.value.value
    return None


def _collect_import_roots(main_content: str) -> set[str]:
    imports: set[str] = set()
    try:
        tree = ast.parse(main_content or "")
    except Exception:
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0].lower())
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0].lower())
    return imports


def _parse_declared_requirements(requirements_content: str) -> set[str]:
    declared: set[str] = set()
    for raw in (requirements_content or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.split(r"[<>=!~\[\]; ]", line, maxsplit=1)[0]
        norm = line.strip().lower().replace("_", "-")
        if norm:
            declared.add(norm)
    return declared


def _missing_declared_python_dependencies(main_content: str, requirements_content: str, qodeyard: Path) -> list[str]:
    declared = _parse_declared_requirements(requirements_content)

    import_roots = _collect_import_roots(main_content)
    stdlib = set(getattr(__import__("sys"), "stdlib_module_names", set()))
    missing: list[str] = []
    for root in sorted(import_roots):
        if root in stdlib:
            continue
        if (qodeyard / f"{root}.py").exists() or (qodeyard / root).is_dir():
            continue
        package = IMPORT_TO_PACKAGE.get(root, root).lower().replace("_", "-")
        if _is_declared_or_covered(package, declared):
            continue
        if package not in missing:
            missing.append(package)
    return missing


def _is_declared_or_covered(package: str, declared: set[str]) -> bool:
    if package in declared:
        return True
    providers = DECLARED_BY_TRANSITIVE_PROVIDER.get(package, set())
    return any(provider in declared for provider in providers)


def _validate_user_model_fields(main_content: str) -> list[str]:
    try:
        tree = ast.parse(main_content or "")
    except Exception:
        return []

    classes: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        fields: set[str] = set()
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.add(item.target.id)
        base_names: list[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(base.attr)
        classes[node.name] = {"fields": fields, "bases": base_names}

    if "User" not in classes:
        return ["Missing required `User` model class."]

    cache: dict[str, set[str]] = {}

    def resolve_fields(name: str, chain: tuple[str, ...] = ()) -> set[str]:
        if name in cache:
            return set(cache[name])
        if name in chain:
            return set()
        item = classes.get(name)
        if not item:
            return set()
        resolved = set(item["fields"])
        for base_name in item["bases"]:
            resolved |= resolve_fields(base_name, chain + (name,))
        cache[name] = set(resolved)
        return resolved

    user_fields = resolve_fields("User")
    required_fields = {"id", "username", "email", "password"}
    issues: list[str] = []
    for field in sorted(required_fields - user_fields):
        issues.append(f"User model missing field '{field}'.")
    for field in sorted(user_fields - required_fields):
        issues.append(f"Forbidden field '{field}' in class 'User'.")
    return issues


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


def _classify_runtime_failure(stderr: str, stdout: str, requirements_content: str) -> tuple[str, str, str]:
    combined = ((stdout or "") + "\n" + (stderr or "")).strip()
    lower = combined.lower()

    cmd_not_found = re.search(r"(?m)^\S+:\s+line\s+\d+:\s+([a-zA-Z0-9_.-]+):\s+command not found$", combined)
    if cmd_not_found:
        tool = cmd_not_found.group(1)
        return (
            "ENVIRONMENT_BLOCKED: unavailable external tool",
            "ENVIRONMENT_BLOCKED_UNAVAILABLE_TOOL",
            f"Unavailable external tool: {tool}",
        )

    missing_match = re.search(r"No module named ['\"]?([^'\"\\s]+)['\"]?", combined)
    if missing_match:
        module_name = missing_match.group(1).strip().lower()
        package_name = IMPORT_TO_PACKAGE.get(module_name, module_name).replace("_", "-")
        declared = _parse_declared_requirements(requirements_content)
        if declared and package_name not in declared:
            return (
                "FAIL: dependency not declared",
                "FAIL_DEPENDENCY_DECLARATION",
                f"Missing dependency declaration: {package_name}",
            )
        return (
            "ENVIRONMENT_BLOCKED: package registry unavailable",
            "ENVIRONMENT_BLOCKED_PACKAGE_REGISTRY",
            "Runtime failed because dependency import could not be satisfied in validator environment.",
        )

    if any(fragment in lower for fragment in ENV_REGISTRY_PATTERNS):
        return (
            "ENVIRONMENT_BLOCKED: package registry unavailable",
            "ENVIRONMENT_BLOCKED_PACKAGE_REGISTRY",
            "Package installation or runtime dependency fetch was blocked by registry/network availability.",
        )

    return (
        "FAIL: shellscript runtime error",
        "FAIL_SHELLSCRIPT_RUNTIME",
        "run.sh exited before service became healthy.",
    )


def _launch_and_exercise_server(qodeyard: Path, run_sh: Path, shell_bin: str, port: int) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "PORT": str(port),
    }
    command = [shell_bin, str(run_sh.name)]
    proc = None
    stdout = ""
    stderr = ""
    shim_dir: Path | None = None

    try:
        if not shutil.which("python", path=env["PATH"]):
            shim_dir = Path(tempfile.mkdtemp(prefix="qonq-python-shim-"))
            shim = shim_dir / "python"
            try:
                shim.symlink_to(Path(sys.executable))
            except Exception:
                shutil.copy2(sys.executable, shim)
                shim.chmod(0o755)
            env["PATH"] = f"{shim_dir}{os.pathsep}{env['PATH']}"

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
        ready = False
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                code, payload, _ = _http_json_request("GET", f"{base}/health", timeout=1.2)
                if code == 200 and payload == {"status": "healthy"}:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.25)

        if not ready:
            out, err = proc.communicate(timeout=1) if proc.poll() is not None else ("", "")
            stdout = out or ""
            stderr = err or ""
            classification, code, message = _classify_runtime_failure(stderr, stdout, _read_text(qodeyard / "requirements.txt"))
            return {
                "classification": classification,
                "code": code,
                "message": message,
                "stdout": stdout[:1200],
                "stderr": stderr[:1200],
                "command": " ".join(command),
            }

        check = _exercise_fastapi_contract(base)
        if check is not None:
            return {
                "classification": "FAIL: code behavior mismatch",
                "code": "FAIL_CODE_BEHAVIOR",
                "message": check,
                "stdout": "",
                "stderr": "",
                "command": " ".join(command),
            }

        return {
            "classification": "PASS",
            "code": "PASS",
            "message": "run.sh launched API successfully and endpoint contract passed.",
            "stdout": "",
            "stderr": "",
            "command": " ".join(command),
        }
    except subprocess.TimeoutExpired:
        return {
            "classification": "FAIL: shellscript runtime error",
            "code": "FAIL_SHELLSCRIPT_RUNTIME",
            "message": "run.sh launch timed out before readiness could be confirmed.",
            "stdout": stdout[:1200],
            "stderr": stderr[:1200],
            "command": " ".join(command),
        }
    except FileNotFoundError:
        return {
            "classification": "ENVIRONMENT_BLOCKED: unavailable external tool",
            "code": "ENVIRONMENT_BLOCKED_UNAVAILABLE_TOOL",
            "message": f"Unavailable external tool: {shell_bin}",
            "stdout": "",
            "stderr": "",
            "command": " ".join(command),
        }
    except Exception as exc:
        return {
            "classification": "FAIL: shellscript runtime error",
            "code": "FAIL_SHELLSCRIPT_RUNTIME",
            "message": f"run.sh runtime error: {exc}",
            "stdout": "",
            "stderr": "",
            "command": " ".join(command),
        }
    finally:
        if proc is not None:
            _terminate_process(proc)
        if shim_dir is not None:
            shutil.rmtree(shim_dir, ignore_errors=True)


def _exercise_fastapi_contract(base_url: str) -> str | None:
    code, payload, body = _http_json_request("GET", f"{base_url}/health")
    if code != 200 or payload != {"status": "healthy"}:
        return f"GET /health contract mismatch: status={code} payload={payload or body}"

    p1 = {"username": "a", "email": "a@x.com", "password": "pw"}
    code, u1, body = _http_json_request("POST", f"{base_url}/users", payload=p1)
    if code not in {200, 201} or not isinstance(u1, dict):
        return f"POST /users failed: status={code} body={body}"
    if u1.get("id") != 1:
        return f"POST /users first id mismatch: expected 1, got {u1.get('id')}"
    if set(u1.keys()) != {"id", "username", "email", "password"}:
        return f"POST /users returned unexpected fields: {sorted(u1.keys())}"

    p2 = {"username": "b", "email": "b@x.com", "password": "pw2"}
    code, u2, body = _http_json_request("POST", f"{base_url}/users", payload=p2)
    if code not in {200, 201} or not isinstance(u2, dict):
        return f"POST /users second call failed: status={code} body={body}"
    if u2.get("id") != 2:
        return f"POST /users second id mismatch: expected 2, got {u2.get('id')}"

    code, users, body = _http_json_request("GET", f"{base_url}/users")
    if code != 200 or not isinstance(users, list) or len(users) != 2:
        return f"GET /users mismatch: status={code} payload={users or body}"

    code, user1, body = _http_json_request("GET", f"{base_url}/users/1")
    if code != 200 or not isinstance(user1, dict) or user1.get("id") != 1:
        return f"GET /users/1 mismatch: status={code} payload={user1 or body}"

    code, _, body = _http_json_request("GET", f"{base_url}/users/999")
    if code != 404:
        return f"GET /users/999 should return 404, got {code} body={body}"

    return None


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


def _add_violation(
    result: dict,
    rule_id: str,
    message: str,
    *,
    file: str = "",
    expected: str | None = None,
    actual: str | None = None,
    command: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
) -> None:
    payload = {"rule_id": rule_id, "message": message, "file": file}
    if expected:
        payload["expected"] = expected
    if actual:
        payload["actual"] = actual
    if command:
        payload["command"] = command
    if stdout:
        payload["stdout_excerpt"] = stdout[:1200]
    if stderr:
        payload["stderr_excerpt"] = stderr[:1200]
    result["violations"].append(payload)


def _has_violation(result: dict, prefix: str) -> bool:
    return any(str(v.get("rule_id", "")).startswith(prefix) for v in result.get("violations", []))


def _finalize_fail(result: dict, classification: str) -> dict:
    result["passed"] = False
    result["status"] = "FAIL"
    result["verdict_classification"] = classification
    result["completion_override"]["allowed"] = False
    result["completion_override"]["task_completed"] = False
    result["completion_override"]["repair_required"] = True
    result["repair_directive"] = build_repair_directive(result)
    return result
