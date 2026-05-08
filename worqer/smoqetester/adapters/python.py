# worqer/smoqetester/adapters/python.py
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..base import (
    Adapter,
    SmoketestContext,
    collect_commands,
    rel_name,
    result_error,
    result_fail,
    result_pass,
    result_skip,
    run_command,
)
from ..discovery import find_binary
from ..models import (
    EXECUTION_KIND_EXECUTED,
    EXECUTION_KIND_STATIC,
    EXECUTION_KIND_PROCESS_BOOT,
    EXECUTION_KIND_HTTP,
    EXECUTION_KIND_SYNTAX,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    SmoketestResult
)
from ..python_bootstrap import provision_validation_env


_PYTHON_CMD_RE = re.compile(r"^python(?:\d+(?:\.\d+)*)?$", re.IGNORECASE)


class PythonAdapter(Adapter):
    name = "python"
    extensions = (".py", ".pyi")

    def _python_bin(self, ctx: SmoketestContext) -> tuple[str | None, str | None]:
        # v1.3.9: Provision task-local validation env if manifests exist
        cached_bin = ctx.adapter_config.get("_resolved_python_bin")
        cached_err = ctx.adapter_config.get("_resolved_python_err")
        if cached_bin or cached_err:
            return cached_bin, cached_err

        # Try to provision
        env_root = os.environ.get("QONQ_WORKSPACE")
        worqspace_root = Path(env_root) if env_root else ctx.qodeyard_path.parent
        
        prov_bin, prov_err = provision_validation_env(worqspace_root, ctx.qodeyard_path)
        if prov_bin:
            ctx.adapter_config["_resolved_python_bin"] = prov_bin
            return prov_bin, None
        
        if prov_err:
            # Bootstrap was attempted but failed
            ctx.adapter_config["_resolved_python_err"] = prov_err
            return None, prov_err

        # Fallback to system binaries if no manifest was found
        candidates = [
            ctx.adapter_config.get("python_bin"),
            sys.executable,
            "python3",
            "python",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            resolved = find_binary(str(candidate), cwd=ctx.qodeyard_path)
            if resolved:
                ctx.adapter_config["_resolved_python_bin"] = resolved
                return resolved, None
        
        ctx.adapter_config["_resolved_python_bin"] = None
        return None, None

    def _classify_failure(self, res: SmoketestResult, ctx: SmoketestContext):
        """Enhances SmoketestResult with structured failure classification."""
        if res.status not in {STATUS_FAIL, STATUS_ERROR}:
            return
        if res.failure_kind:
            return

        stderr = res.stderr or ""
        stdout = res.stdout or ""
        combined = (stdout + "\n" + stderr).strip()

        # Detect missing module
        match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", combined)
        if not match:
            match = re.search(r"ImportError: No module named ([^ ]+)", combined)
        if not match:
            match = re.search(r"ImportError: cannot import name '([^']+)'", combined)
        if not match:
            match = re.search(r"No module named '([^']+)'", combined)
            
        if match:
            missing = match.group(1)
            res.missing_module = missing
            
            # Check if it's declared in manifest
            declared = False
            manifest_names = ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"]
            manifest_found = False
            for m in manifest_names:
                p = ctx.qodeyard_path / m
                if p.exists():
                    manifest_found = True
                    try:
                        content = p.read_text(encoding="utf-8", errors="ignore").lower()
                        # Simple heuristic: look for module name in manifest
                        search_term = missing.lower().replace("_", "-")
                        if search_term in content.replace("_", "-"):
                            declared = True
                            break
                    except Exception:
                        continue
            
            if declared:
                # Declared but missing -> Validator/Environment issue
                res.failure_kind = "environment_dependency_missing"
                res.environment_blocked = True
                res.message = f"Validator environment missing declared dependency: {missing}"
            elif manifest_found:
                # Manifest exists but dependency is not there -> Project declaration defect
                res.failure_kind = "dependency_declaration_failures"
                res.environment_blocked = False
                res.message = f"Dependency declaration defect: '{missing}' is imported but NOT declared in project manifests."
            else:
                # No manifest at all? Might be a code defect or missing declaration
                res.failure_kind = "blocking_code_failures"
                res.environment_blocked = False
                res.message = f"Code defect or missing declaration for module: {missing}"
        elif "SyntaxError" in combined or "IndentationError" in combined:
            res.failure_kind = "blocking_code_failures"
            res.message = f"Code defect: syntax error detected."
        elif "command not found" in combined.lower() or "no such file or directory" in combined.lower():
            res.failure_kind = "tooling_missing"
            res.environment_blocked = True
            res.message = f"Validator environment missing required tooling."
        else:
            # Fallback for other runtime errors
            res.failure_kind = "blocking_code_failures"

    def _tests_plausibly_exist(self, ctx: SmoketestContext) -> bool:
        qodeyard = ctx.qodeyard_path
        if (qodeyard / "tests").is_dir():
            return True
        for pattern in ("test_*.py", "*_test.py", "**/test_*.py", "**/*_test.py"):
            for candidate in qodeyard.glob(pattern):
                if not candidate.is_file():
                    continue
                try:
                    rel = str(candidate.relative_to(qodeyard)).lower()
                except ValueError:
                    rel = str(candidate).lower()
                if "manual" in rel:
                    continue
                return True
        return False

    def _bind_python_command(self, command: list[str], python_bin: str) -> list[str]:
        if not command:
            return command
        executable = Path(str(command[0])).name
        if _PYTHON_CMD_RE.fullmatch(executable):
            return [python_bin, *command[1:]]
        return command

    def _detect_safe_cli_entrypoint(self, ctx: SmoketestContext, scope_files: list[Path]) -> Path | None:
        names = {"cli.py", "__main__.py", "main.py"}
        candidates = [item for item in scope_files if item.name in names]
        if not candidates:
            for name in sorted(names):
                candidate = ctx.qodeyard_path / name
                if candidate.is_file():
                    candidates.append(candidate)
        for candidate in sorted(set(candidates)):
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lowered = text.lower()
            if "__name__" not in text or "__main__" not in text:
                continue
            if "argparse" in lowered or "click" in lowered or "typer" in lowered:
                return candidate
        return None

    def _detect_safe_fastapi_entrypoint(self, ctx: SmoketestContext, scope_files: list[Path]) -> Path | None:
        names = {"main.py", "app.py", "server.py", "api.py"}
        candidates = [item for item in scope_files if item.name in names]
        if not candidates:
            for name in sorted(names):
                candidate = ctx.qodeyard_path / name
                if candidate.is_file():
                    candidates.append(candidate)
        for candidate in sorted(set(candidates)):
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "FastAPI" in text and ("app" in text or "api" in text):
                return candidate
        return None

    def _run_fastapi_probe(self, ctx: SmoketestContext, python_bin: str, entrypoint: Path, scope_files: list[Path]) -> list[SmoketestResult]:
        # v1.4.0: Hardened truthful FastAPI probe.
        # Splits BOOT from HTTP probe, avoids unsafe imports, and respects exit codes.
        module_path = str(entrypoint.resolve())
        module_stem = entrypoint.stem.replace("-", "_").replace(".", "_")
        if not module_stem or not (module_stem[0].isalpha() or module_stem[0] == "_"):
            module_stem = f"mod_{module_stem}"

        probe_script = f"""
import sys
import importlib.util
import json
from pathlib import Path

def load_module(file_path, module_name):
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"BOOT_FAIL: {{e}}")
        return None

module = load_module(r"{module_path}", "{module_stem}")
if not module:
    sys.exit(1)

# App discovery
app = getattr(module, "app", getattr(module, "api", getattr(module, "server", None)))
if not app:
    print("BOOT_PASS: Module imported, but no 'app'/'api'/'server' object found.")
    sys.exit(0)

print("BOOT_PASS: FastAPI app object located.")

try:
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # 1. Health Probe
    has_health = any(getattr(r, "path", None) == "/health" for r in getattr(app, "routes", []))
    if has_health:
        try:
            resp = client.get("/health", timeout=5)
            if resp.status_code == 200:
                print(f"HTTP_PASS: /health returned 200")
            else:
                print(f"HTTP_FAIL: /health returned {{resp.status_code}}")
                sys.exit(2)
        except Exception as e:
            print(f"HTTP_FAIL: /health request failed: {{e}}")
            sys.exit(2)
    else:
        print("HTTP_SKIP: No /health route defined.")

    # 2. Websocket Probe (Optional)
    has_ws = any(getattr(r, "path", None) == "/ws" for r in getattr(app, "routes", []))
    if has_ws:
        try:
            with client.websocket_connect("/ws") as ws:
                print("WS_PASS: Websocket connected.")
        except Exception as e:
            print(f"WS_FAIL: Websocket connection failed: {{e}}")
    
except ImportError:
    print("PROBE_SKIP: fastapi.testclient not available.")
except Exception as e:
    msg = str(e)
    if "requires the httpx package" in msg.lower():
        print(f"PROBE_SKIP: {{msg}}")
        sys.exit(0)
    print(f"PROBE_ERROR: {{msg}}")
    sys.exit(3)

sys.exit(0)
"""
        probe_path = ctx.qodeyard_path / ".qonqrete_fastapi_probe.py"
        try:
            probe_path.write_text(probe_script, encoding="utf-8")
            res = run_command(
                self.name,
                "python:fastapi_probe",
                [python_bin, ".qonqrete_fastapi_probe.py"],
                ctx,
                scope_files,
                execution_kind=EXECUTION_KIND_HTTP,
                scope="project",
                target_file=entrypoint,
            )
            
            stdout = res.stdout or ""
            results: list[SmoketestResult] = []
            
            # Extract Boot evidence
            boot_res = SmoketestResult(
                adapter=self.name,
                name="python:fastapi_boot",
                status=STATUS_PASS if "BOOT_PASS" in stdout else (STATUS_FAIL if "BOOT_FAIL" in stdout else STATUS_SKIP),
                executed="BOOT_PASS" in stdout or "BOOT_FAIL" in stdout,
                message="FastAPI app boot/import check.",
                execution_kind=EXECUTION_KIND_PROCESS_BOOT,
                scope="project",
                related_files=res.related_files,
                file=res.file,
                stdout=res.stdout if "BOOT_FAIL" in stdout else None,
                stderr=res.stderr if "BOOT_FAIL" in stdout else None,
                command=res.command,
            )
            if "BOOT_FAIL" in stdout:
                boot_res.message = f"FastAPI app failed to boot: {stdout.split('BOOT_FAIL:')[1].splitlines()[0].strip()}"
            results.append(boot_res)

            # Extract HTTP evidence
            if "HTTP_PASS" in stdout:
                results.append(result_pass(
                    res.file, "python:fastapi_http", "/health responded 200",
                    execution_kind=EXECUTION_KIND_HTTP, related_files=res.related_files, scope="project"
                ))
            elif "HTTP_FAIL" in stdout:
                fail_msg = stdout.split("HTTP_FAIL:")[1].splitlines()[0].strip()
                results.append(result_fail(
                    res.file, "python:fastapi_http", f"/health probe failed: {fail_msg}",
                    execution_kind=EXECUTION_KIND_HTTP, related_files=res.related_files, scope="project"
                ))
            elif "HTTP_SKIP" in stdout:
                results.append(result_skip(
                    self.name, "python:fastapi_http", "No /health route defined; skipping HTTP probe.",
                    execution_kind=EXECUTION_KIND_HTTP, related_files=res.related_files, scope="project"
                ))
            
            if "PROBE_SKIP" in stdout:
                results.append(result_skip(
                    self.name, "python:fastapi_http", "fastapi.testclient unavailable; HTTP probe skipped.",
                    execution_kind=EXECUTION_KIND_HTTP, related_files=res.related_files, scope="project"
                ))
            elif "PROBE_ERROR" in stdout:
                probe_error_line = next(
                    (line.split("PROBE_ERROR:", 1)[1].strip() for line in stdout.splitlines() if "PROBE_ERROR:" in line),
                    "unspecified error",
                )
                if "HTTP_PASS" in stdout:
                    # Do not fail healthy apps because of late probe harness glitches.
                    results.append(result_skip(
                        self.name,
                        "python:fastapi_probe_error",
                        f"FastAPI probe degraded after successful /health probe: {probe_error_line}",
                        execution_kind=EXECUTION_KIND_HTTP,
                        related_files=res.related_files,
                        scope="project",
                    ))
                else:
                    probe_error_result = result_error(
                        self.name,
                        "python:fastapi_probe_error",
                        f"FastAPI probe harness encountered an error: {probe_error_line}",
                        execution_kind=EXECUTION_KIND_HTTP,
                        related_files=res.related_files,
                        scope="project",
                    )
                    probe_error_result.failure_kind = "validator_degraded"
                    probe_error_result.environment_blocked = True
                    probe_error_result.stdout = (res.stdout or "")[:1200]
                    probe_error_result.stderr = (res.stderr or "")[:1200]
                    results.append(probe_error_result)

            for r in results:
                self._classify_failure(r, ctx)
            return results
        finally:
            if probe_path.exists():
                try:
                    probe_path.unlink()
                except OSError:
                    pass

    def preflight(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        python_bin, python_err = self._python_bin(ctx)
        
        if python_err:
            return [SmoketestResult(
                adapter=self.name,
                name="python_bootstrap_failed",
                status=STATUS_ERROR,
                executed=False,
                message=f"Python validation environment bootstrap failed: {python_err}",
                execution_kind=EXECUTION_KIND_STATIC,
                severity="error",
                environment_blocked=True,
                failure_kind="validator_degraded",
                scope="preflight",
                related_files=related,
            )]

        if not python_bin:
            return [result_skip(
                self.name,
                "python_runtime_missing",
                "Python runtime not found; python smoketest checks skipped.",
                execution_kind=EXECUTION_KIND_STATIC,
                related_files=related,
                scope="preflight",
            )]
        
        return [result_pass(
            self.name,
            "python_runtime",
            f"Python runtime available: {python_bin}",
            execution_kind=EXECUTION_KIND_STATIC,
            related_files=related,
            scope="preflight",
        )]

    def project_smoketest(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        python_bin, python_err = self._python_bin(ctx)
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        
        if python_err:
            return [SmoketestResult(
                adapter=self.name,
                name="project_smoke_skipped_bootstrap_failed",
                status=STATUS_ERROR,
                executed=False,
                message=f"Python validation environment bootstrap failed: {python_err}",
                execution_kind=EXECUTION_KIND_EXECUTED,
                severity="error",
                environment_blocked=True,
                failure_kind="validator_degraded",
                scope="project",
                related_files=related,
            )]

        if not python_bin:
            return [result_skip(
                self.name,
                "project_smoke_skipped_no_runtime",
                "Python runtime unavailable; project smoketest skipped.",
                execution_kind=EXECUTION_KIND_EXECUTED,
                related_files=related,
                scope="project",
            )]

        append_changed_files = bool(ctx.adapter_config.get("append_changed_files", False))
        commands = collect_commands(self.name, ctx.adapter_config)
        results: list[SmoketestResult] = []
        for command_name, command, kind_override in commands:
            bound_command = self._bind_python_command(command, python_bin)
            res = run_command(
                self.name,
                command_name,
                bound_command,
                ctx,
                scope_files,
                append_changed_files=append_changed_files,
                execution_kind=kind_override,
                scope="project",
            )
            self._classify_failure(res, ctx)
            results.append(res)

        if bool(ctx.adapter_config.get("auto_unittest_discover", True)):
            if self._tests_plausibly_exist(ctx):
                res = run_command(
                    self.name,
                    "python:unittest_discover",
                    [python_bin, "-m", "unittest", "discover"],
                    ctx,
                    scope_files,
                    execution_kind=EXECUTION_KIND_EXECUTED,
                    scope="project",
                )
                self._classify_failure(res, ctx)
                results.append(res)
            else:
                results.append(result_skip(
                    self.name,
                    "python:unittest_discover",
                    "No plausible Python tests found; unittest discover skipped.",
                    execution_kind=EXECUTION_KIND_EXECUTED,
                    command="python -m unittest discover",
                    related_files=related,
                    scope="project",
                ))

        if bool(ctx.adapter_config.get("auto_cli_help", False)):
            entrypoint = self._detect_safe_cli_entrypoint(ctx, scope_files)
            if entrypoint is not None:
                res = run_command(
                    self.name,
                    "python:cli_help",
                    [python_bin, rel_name(entrypoint, ctx.qodeyard_path), "--help"],
                    ctx,
                    scope_files,
                    execution_kind=EXECUTION_KIND_EXECUTED,
                    scope="project",
                    target_file=entrypoint,
                )
                self._classify_failure(res, ctx)
                results.append(res)

        if bool(ctx.adapter_config.get("auto_fastapi_probe", True)):
            fastapi_entrypoint = self._detect_safe_fastapi_entrypoint(ctx, scope_files)
            if fastapi_entrypoint is not None:
                probe_result = self._run_fastapi_probe(ctx, python_bin, fastapi_entrypoint, scope_files)
                if probe_result is None:
                    pass
                elif isinstance(probe_result, (list, tuple)):
                    results.extend(probe_result)
                else:
                    # Defensive normalization for tests/mocks that return one result.
                    results.append(probe_result)

        return results or [result_skip(
            self.name,
            "project_smoke_not_configured",
            "No Python project smoketest command was configured and no safe auto-smoke path was enabled.",
            execution_kind=EXECUTION_KIND_EXECUTED,
            related_files=related,
            scope="project",
        )]

    def file_smoketest(self, ctx: SmoketestContext, file_path: Path, scope_files: list[Path]) -> list[SmoketestResult]:
        python_bin, _ = self._python_bin(ctx)
        rel_file = rel_name(file_path, ctx.qodeyard_path)
        if not python_bin:
            return [result_skip(
                self.name,
                "python:py_compile",
                "Python runtime unavailable; per-file syntax smoke skipped.",
                execution_kind=EXECUTION_KIND_SYNTAX,
                file=rel_file,
                files=[rel_file],
                related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
                scope="file",
                command="python -m py_compile <file>",
            )]
        res = run_command(
            self.name,
            "python:py_compile",
            [python_bin, "-m", "py_compile"],
            ctx,
            [file_path], # Only check THIS file
            append_changed_files=True,
            execution_kind=EXECUTION_KIND_SYNTAX,
            scope="file",
            target_file=file_path,
        )
        self._classify_failure(res, ctx)
        return [res]


__all__ = ["PythonAdapter"]
