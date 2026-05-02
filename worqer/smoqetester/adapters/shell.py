# worqer/smoqetester/adapters/shell.py
from __future__ import annotations

import ast
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..base import (
    Adapter,
    SmoketestContext,
    collect_commands,
    rel_name,
    result_fail,
    result_pass,
    result_skip,
    run_command,
)
from ..discovery import find_binary
from ..models import (
    EXECUTION_KIND_EXECUTED,
    EXECUTION_KIND_HTTP,
    EXECUTION_KIND_PROCESS_BOOT,
    EXECUTION_KIND_STATIC,
    EXECUTION_KIND_SYNTAX,
    SEVERITY_ERROR,
    STATUS_ERROR,
    SmoketestResult,
)
try:
    from ...shellscript_validation import (
        detect_unsafe_commands,
        validate_run_sh_contract,
    )
except Exception:
    from shellscript_validation import (  # type: ignore
        detect_unsafe_commands,
        validate_run_sh_contract,
    )


_SHELL_BY_SUFFIX = {
    ".sh": "sh",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ksh": "ksh",
}

_SHELL_HINTS = ("bash", "zsh", "ksh", "sh")

_NETWORK_ERROR_PATTERNS = (
    "temporary failure in name resolution",
    "failed to establish a new connection",
    "network is unreachable",
    "connection timed out",
    "timed out",
)

_IMPORT_TO_PACKAGE = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
}


class ShellAdapter(Adapter):
    name = "shell"
    extensions = (".sh", ".bash", ".zsh", ".ksh")

    def _interpreter_for_file(self, file_path: Path, cwd: Path) -> str | None:
        try:
            first_line = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
        except Exception:
            first_line = ""

        if first_line.startswith("#!"):
            shebang = first_line[2:].strip().split()
            if shebang:
                target = Path(shebang[0]).name
                if target == "env" and len(shebang) > 1:
                    target = shebang[1].strip()
                for hint in _SHELL_HINTS:
                    if hint in target:
                        resolved = find_binary(hint, cwd=cwd)
                        if resolved:
                            return resolved

        fallback = _SHELL_BY_SUFFIX.get(file_path.suffix.lower(), "sh")
        return find_binary(fallback, cwd=cwd)

    def _resolve_run_policy(self, ctx: SmoketestContext) -> str:
        task_parts: list[str] = []
        task_spec = ctx.qodeyard_path.parent / "task" / "task-spec.v1.json"
        if task_spec.exists():
            try:
                payload = json.loads(task_spec.read_text(encoding="utf-8"))
                for key in ("clarified_task_body", "goal"):
                    value = payload.get(key)
                    if isinstance(value, str):
                        task_parts.append(value)
            except Exception:
                pass
        tasq = ctx.qodeyard_path.parent / "tasq.md"
        if tasq.exists():
            try:
                task_parts.append(tasq.read_text(encoding="utf-8"))
            except Exception:
                pass
        blob = "\n".join(task_parts).lower()
        if not blob:
            return "generic"
        if (
            "python -m uvicorn main:app --reload --port $port" in blob
            and ("must launch exactly" in blob or "launch exactly this uvicorn command" in blob or "launch exectly this uvicorn command" in blob)
        ):
            return "exact_variable_port"
        if (
            "python -m uvicorn main:app --reload --port 8000" in blob
            and "must launch exactly" in blob
        ):
            return "exact_literal_8000"
        if "--port $port" in blob or "--port ${port}" in blob or "pass the port variable" in blob:
            return "port_variable"
        return "generic"

    def _extract_port(self, qodeyard: Path) -> int:
        main_py = qodeyard / "main.py"
        if not main_py.exists():
            return 8000
        try:
            tree = ast.parse(main_py.read_text(encoding="utf-8", errors="ignore"))
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    if not node.targets:
                        continue
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id == "PORT":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                            return int(node.value.value)
        except Exception:
            return 8000
        return 8000

    def _parse_requirements(self, qodeyard: Path) -> set[str]:
        req = qodeyard / "requirements.txt"
        if not req.exists():
            return set()
        declared: set[str] = set()
        for raw in req.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            line = re.split(r"[<>=!~\[\]; ]", line, maxsplit=1)[0]
            dep = line.strip().lower().replace("_", "-")
            if dep:
                declared.add(dep)
        return declared

    def _classify_launch_failure(self, stderr: str, stdout: str, qodeyard: Path) -> tuple[str, bool, str]:
        combined = ((stdout or "") + "\n" + (stderr or "")).strip()
        lower = combined.lower()

        match = re.search(r"No module named ['\"]?([^'\"\\s]+)['\"]?", combined)
        if match:
            module_name = match.group(1).lower().strip()
            package = _IMPORT_TO_PACKAGE.get(module_name, module_name).replace("_", "-")
            declared = self._parse_requirements(qodeyard)
            if declared and package not in declared:
                return "dependency_not_declared", False, f"Dependency not declared: {package}"
            return "package_registry_unavailable", True, "Runtime dependency import failed in validator environment."

        if any(marker in lower for marker in _NETWORK_ERROR_PATTERNS):
            return "package_registry_unavailable", True, "Package registry/network unavailable in validator environment."

        if "command not found" in lower or "no such file or directory" in lower:
            return "unavailable_external_tool", True, "Unavailable external tool while launching run.sh."

        return "shellscript_runtime_error", False, "run.sh exited before startup probe succeeded."

    def _http_json_request(self, method: str, url: str, payload: dict | None = None, timeout: float = 2.0):
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

    def _exercise_fastapi_contract(self, base_url: str) -> str | None:
        code, payload, body = self._http_json_request("GET", f"{base_url}/health")
        if code != 200 or payload != {"status": "healthy"}:
            return f"GET /health mismatch: status={code} payload={payload or body}"

        p1 = {"username": "a", "email": "a@x.com", "password": "pw"}
        code, u1, body = self._http_json_request("POST", f"{base_url}/users", payload=p1)
        if code not in {200, 201} or not isinstance(u1, dict):
            return f"POST /users failed: status={code} body={body}"
        if u1.get("id") != 1:
            return f"POST /users first id mismatch: got {u1.get('id')}"
        if set(u1.keys()) != {"id", "username", "email", "password"}:
            return f"POST /users unexpected fields: {sorted(u1.keys())}"

        p2 = {"username": "b", "email": "b@x.com", "password": "pw2"}
        code, u2, body = self._http_json_request("POST", f"{base_url}/users", payload=p2)
        if code not in {200, 201} or not isinstance(u2, dict):
            return f"POST /users second call failed: status={code} body={body}"
        if u2.get("id") != 2:
            return f"POST /users second id mismatch: got {u2.get('id')}"

        code, users, body = self._http_json_request("GET", f"{base_url}/users")
        if code != 200 or not isinstance(users, list) or len(users) != 2:
            return f"GET /users mismatch: status={code} payload={users or body}"

        code, user1, body = self._http_json_request("GET", f"{base_url}/users/1")
        if code != 200 or not isinstance(user1, dict) or user1.get("id") != 1:
            return f"GET /users/1 mismatch: status={code} payload={user1 or body}"

        code, _, body = self._http_json_request("GET", f"{base_url}/users/999")
        if code != 404:
            return f"GET /users/999 should return 404, got {code} body={body}"
        return None

    def _terminate_process(self, proc: subprocess.Popen) -> None:
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

    def _run_run_sh_launch_smoke(self, ctx: SmoketestContext, run_sh: Path, scope_files: list[Path]) -> list[SmoketestResult]:
        rel_file = rel_name(run_sh, ctx.qodeyard_path)
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        related = sorted(set(related + [rel_file]))

        content = run_sh.read_text(encoding="utf-8", errors="ignore")

        unsafe = detect_unsafe_commands(content)
        if unsafe:
            return [SmoketestResult(
                adapter=self.name,
                name="shell:run_sh_launch",
                status=STATUS_ERROR,
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message="Unsafe command detected in run.sh; launch skipped.",
                file=rel_file,
                files=[rel_file],
                related_files=related,
                scope="project",
                severity=SEVERITY_ERROR,
                failure_kind="skipped_unsafe_command",
                environment_blocked=False,
                stderr=", ".join(unsafe),
            )]

        policy = self._resolve_run_policy(ctx)
        contract_errors = validate_run_sh_contract(content, policy)
        if contract_errors:
            return [SmoketestResult(
                adapter=self.name,
                name="shell:run_sh_contract",
                status="FAIL",
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message="run.sh contract mismatch: " + " | ".join(contract_errors),
                file=rel_file,
                files=[rel_file],
                related_files=related,
                scope="project",
                severity=SEVERITY_ERROR,
                failure_kind="shellscript_contract_mismatch",
                environment_blocked=False,
            )]

        interpreter = self._interpreter_for_file(run_sh, ctx.qodeyard_path)
        if not interpreter:
            return [SmoketestResult(
                adapter=self.name,
                name="shell:run_sh_launch",
                status=STATUS_ERROR,
                executed=False,
                execution_kind=EXECUTION_KIND_STATIC,
                message="No compatible shell interpreter found for run.sh launch.",
                file=rel_file,
                files=[rel_file],
                related_files=related,
                scope="project",
                severity=SEVERITY_ERROR,
                failure_kind="unavailable_external_tool",
                environment_blocked=True,
            )]

        syntax = subprocess.run(
            [interpreter, "-n", str(run_sh)],
            cwd=str(ctx.qodeyard_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if syntax.returncode != 0:
            return [SmoketestResult(
                adapter=self.name,
                name="shell:run_sh_launch",
                status="FAIL",
                executed=False,
                execution_kind=EXECUTION_KIND_SYNTAX,
                message="run.sh failed shell syntax check.",
                file=rel_file,
                files=[rel_file],
                related_files=related,
                scope="project",
                severity=SEVERITY_ERROR,
                failure_kind="shellscript_syntax_error",
                environment_blocked=False,
                command=f"{interpreter} -n run.sh",
                stderr=(syntax.stderr or syntax.stdout or "")[:1200],
            )]

        port = self._extract_port(ctx.qodeyard_path)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "PORT": str(port),
        }
        command = [interpreter, run_sh.name]

        proc = None
        stdout = ""
        stderr = ""
        try:
            popen_kwargs = {
                "cwd": str(ctx.qodeyard_path),
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
            }
            if os.name != "nt":
                popen_kwargs["preexec_fn"] = os.setsid
            proc = subprocess.Popen(command, **popen_kwargs)

            base_url = f"http://127.0.0.1:{port}"
            ready = False
            deadline = time.time() + min(12, max(6, ctx.timeout_seconds))
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    code, payload, _ = self._http_json_request("GET", f"{base_url}/health", timeout=1.2)
                    if code == 200 and payload == {"status": "healthy"}:
                        ready = True
                        break
                except Exception:
                    pass
                time.sleep(0.25)

            if not ready:
                if proc.poll() is None:
                    self._terminate_process(proc)
                    out, err = proc.communicate(timeout=1)
                else:
                    out, err = proc.communicate(timeout=1)
                stdout = out or ""
                stderr = err or ""
                failure_kind, environment_blocked, message = self._classify_launch_failure(stderr, stdout, ctx.qodeyard_path)
                return [SmoketestResult(
                    adapter=self.name,
                    name="shell:run_sh_launch",
                    status=STATUS_ERROR if environment_blocked else "FAIL",
                    executed=True,
                    execution_kind=EXECUTION_KIND_PROCESS_BOOT,
                    message=message,
                    file=rel_file,
                    files=[rel_file],
                    related_files=related,
                    scope="project",
                    severity=SEVERITY_ERROR,
                    failure_kind=failure_kind,
                    environment_blocked=environment_blocked,
                    command=" ".join(command),
                    stdout=stdout[:1200],
                    stderr=stderr[:1200],
                )]

            behavior_error = self._exercise_fastapi_contract(base_url)
            if behavior_error:
                return [SmoketestResult(
                    adapter=self.name,
                    name="shell:run_sh_behavior",
                    status="FAIL",
                    executed=True,
                    execution_kind=EXECUTION_KIND_HTTP,
                    message=behavior_error,
                    file=rel_file,
                    files=[rel_file],
                    related_files=related,
                    scope="project",
                    severity=SEVERITY_ERROR,
                    failure_kind="code_behavior_mismatch",
                    environment_blocked=False,
                    command=" ".join(command),
                )]

            return [
                result_pass(
                    self.name,
                    "shell:run_sh_launch",
                    "run.sh launch verified and API contract probe passed.",
                    execution_kind=EXECUTION_KIND_PROCESS_BOOT,
                    file=rel_file,
                    files=[rel_file],
                    related_files=related,
                    scope="project",
                    command=" ".join(command),
                )
            ]
        except Exception as exc:
            return [SmoketestResult(
                adapter=self.name,
                name="shell:run_sh_launch",
                status="FAIL",
                executed=True,
                execution_kind=EXECUTION_KIND_PROCESS_BOOT,
                message=f"run.sh launch check crashed: {exc}",
                file=rel_file,
                files=[rel_file],
                related_files=related,
                scope="project",
                severity=SEVERITY_ERROR,
                failure_kind="shellscript_runtime_error",
                environment_blocked=False,
                command=" ".join(command),
            )]
        finally:
            if proc is not None:
                self._terminate_process(proc)

    def preflight(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        for hint in _SHELL_HINTS:
            if find_binary(hint, cwd=ctx.qodeyard_path):
                return [result_pass(
                    self.name,
                    "shell_runtime",
                    f"Shell runtime available: {hint}",
                    execution_kind=EXECUTION_KIND_STATIC,
                    related_files=related,
                    scope="preflight",
                )]
        return [result_skip(
            self.name,
            "shell_runtime_missing",
            "No shell runtime found; shell smoketest checks skipped.",
            execution_kind=EXECUTION_KIND_STATIC,
            related_files=related,
            scope="preflight",
        )]

    def project_smoketest(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        append_changed_files = bool(ctx.adapter_config.get("append_changed_files", False))
        commands = collect_commands(self.name, ctx.adapter_config)
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        results: list[SmoketestResult] = []

        for command_name, command, kind_override in commands:
            tool = Path(command[0]).name
            is_single_file_tool = tool in {"sh", "bash", "zsh", "ksh", "dash"} and "-n" in command

            if append_changed_files and is_single_file_tool and len(scope_files) > 0:
                for file_path in scope_files:
                    if file_path.suffix.lower() in self.extensions:
                        results.append(
                            run_command(
                                self.name,
                                command_name,
                                command,
                                ctx,
                                [file_path],
                                append_changed_files=True,
                                execution_kind=kind_override,
                                scope="project",
                            )
                        )
            else:
                results.append(
                    run_command(
                        self.name,
                        command_name,
                        command,
                        ctx,
                        scope_files,
                        append_changed_files=append_changed_files,
                        execution_kind=kind_override,
                        scope="project",
                    )
                )

        run_sh = ctx.qodeyard_path / "run.sh"
        if bool(ctx.adapter_config.get("auto_run_sh_launch", True)) and run_sh.exists():
            results.extend(self._run_run_sh_launch_smoke(ctx, run_sh, scope_files))

        if not commands and not run_sh.exists():
            results.append(result_skip(
                self.name,
                "project_smoke_not_configured",
                "No project-level shell smoke command configured; only static file checks ran.",
                execution_kind=EXECUTION_KIND_EXECUTED,
                related_files=related,
                scope="project",
            ))

        return results

    def file_smoketest(self, ctx: SmoketestContext, file_path: Path, scope_files: list[Path]) -> list[SmoketestResult]:
        rel_file = rel_name(file_path, ctx.qodeyard_path)
        interpreter = self._interpreter_for_file(file_path, ctx.qodeyard_path)
        if not interpreter:
            return [result_skip(
                self.name,
                "shell:syntax",
                "No compatible shell interpreter found for static syntax check.",
                execution_kind=EXECUTION_KIND_STATIC,
                command=f"{_SHELL_BY_SUFFIX.get(file_path.suffix.lower(), 'sh')} -n {rel_file}",
                file=rel_file,
                files=[rel_file],
                related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
                scope="file",
            )]
        return [
            run_command(
                self.name,
                "shell:syntax",
                [interpreter, "-n", rel_file],
                ctx,
                scope_files,
                execution_kind=EXECUTION_KIND_SYNTAX,
                scope="file",
                target_file=file_path,
            )
        ]


__all__ = ["ShellAdapter"]
