# worqer/smoqetester/adapters/shell.py
from __future__ import annotations

from pathlib import Path

from ..base import (
    Adapter,
    SmoketestContext,
    collect_commands,
    rel_name,
    result_pass,
    result_skip,
    run_command,
)
from ..discovery import find_binary
from ..models import EXECUTION_KIND_EXECUTED, EXECUTION_KIND_STATIC, EXECUTION_KIND_SYNTAX, SmoketestResult


_SHELL_BY_SUFFIX = {
    ".sh": "sh",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ksh": "ksh",
}

_SHELL_HINTS = ("bash", "zsh", "ksh", "sh")


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
        if not commands:
            return [result_skip(
                self.name,
                "project_smoke_not_configured",
                "No project-level shell smoke command configured; only static file checks ran.",
                execution_kind=EXECUTION_KIND_EXECUTED,
                related_files=related,
                scope="project",
            )]

        results: list[SmoketestResult] = []
        for command_name, command, kind_override in commands:
            tool = Path(command[0]).name
            is_single_file_tool = tool in {"sh", "bash", "zsh", "ksh", "dash"} and "-n" in command
            
            if append_changed_files and is_single_file_tool and len(scope_files) > 0:
                # Convert to per-file invocations
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
