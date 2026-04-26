# worqer/smoqetester/adapters/js_ts.py
from __future__ import annotations

import json
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


class JsTsAdapter(Adapter):
    name = "js_ts"
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

    def _package_json(self, ctx: SmoketestContext) -> tuple[Path | None, dict]:
        manifest_path = ctx.qodeyard_path / "package.json"
        if not manifest_path.exists():
            return None, {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return manifest_path, payload
        except Exception:
            pass
        return manifest_path, {}

    def _has_node_modules(self, ctx: SmoketestContext) -> bool:
        return (ctx.qodeyard_path / "node_modules").is_dir()

    def _choose_script_name(self, scripts: dict) -> str | None:
        for name in ["smoke", "test", "build"]:
            if name in scripts:
                return name
        return None

    def _package_manager_command(self, ctx: SmoketestContext, script_name: str) -> list[str] | None:
        if (ctx.qodeyard_path / "pnpm-lock.yaml").exists():
            pnpm = find_binary("pnpm", cwd=ctx.qodeyard_path)
            if pnpm:
                return [pnpm, "run", script_name]
        if (ctx.qodeyard_path / "yarn.lock").exists():
            yarn = find_binary("yarn", cwd=ctx.qodeyard_path)
            if yarn:
                return [yarn, script_name]
        npm = find_binary("npm", cwd=ctx.qodeyard_path)
        if npm:
            return [npm, "run", script_name]
        return None

    def preflight(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        node_bin = find_binary("node", cwd=ctx.qodeyard_path)
        if not node_bin:
            return [result_skip(
                self.name,
                "node_runtime_missing",
                "Node runtime not found; JS/TS parse checks are limited.",
                execution_kind=EXECUTION_KIND_STATIC,
                related_files=related,
                scope="preflight",
            )]
        return [result_pass(
            self.name,
            "node_runtime",
            f"Node runtime available: {node_bin}",
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
            is_single_file_tool = tool == "node" and "--check" in command

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

        has_ts_scope = any(item.suffix.lower() in {".ts", ".tsx"} for item in scope_files)
        if bool(ctx.adapter_config.get("auto_tsc_no_emit", True)) and has_ts_scope:
            tsc = find_binary("tsc", cwd=ctx.qodeyard_path)
            tsconfig = ctx.qodeyard_path / "tsconfig.json"
            if tsc and tsconfig.exists():
                results.append(
                    run_command(
                        self.name,
                        "js_ts:tsc_no_emit",
                        [tsc, "--noEmit", "--pretty", "false"],
                        ctx,
                        scope_files,
                        execution_kind=EXECUTION_KIND_STATIC,
                        scope="project",
                    )
                )
            elif not tsconfig.exists():
                results.append(result_skip(
                    self.name,
                    "js_ts:tsc_no_emit",
                    "TypeScript scope detected but tsconfig.json is missing; static typecheck skipped.",
                    execution_kind=EXECUTION_KIND_STATIC,
                    command="tsc --noEmit --pretty false",
                    related_files=related,
                    scope="project",
                ))
            else:
                results.append(result_skip(
                    self.name,
                    "js_ts:tsc_no_emit",
                    "TypeScript scope detected but `tsc` was not found; static typecheck skipped.",
                    execution_kind=EXECUTION_KIND_STATIC,
                    command="tsc --noEmit --pretty false",
                    related_files=related,
                    scope="project",
                ))

        if bool(ctx.adapter_config.get("allow_script_execution", False)):
            manifest_path, payload = self._package_json(ctx)
            scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
            if not manifest_path or not payload:
                results.append(result_skip(
                    self.name,
                    "js_ts:script_smoke",
                    "Project script smoke skipped: package.json missing or unreadable.",
                    execution_kind=EXECUTION_KIND_EXECUTED,
                    scope="project",
                    related_files=related,
                ))
            else:
                script_name = self._choose_script_name(scripts)
                if not script_name:
                    results.append(result_skip(
                        self.name,
                        "js_ts:script_smoke",
                        "Project script smoke skipped: no smoke/test/build script found.",
                        execution_kind=EXECUTION_KIND_EXECUTED,
                        scope="project",
                        related_files=related,
                    ))
                elif bool(ctx.adapter_config.get("require_dependencies", True)) and not self._has_node_modules(ctx):
                    results.append(result_skip(
                        self.name,
                        "js_ts:script_smoke",
                        f"Project script `{script_name}` skipped because node_modules is missing and require_dependencies=true.",
                        execution_kind=EXECUTION_KIND_EXECUTED,
                        command=f"npm run {script_name}",
                        scope="project",
                        related_files=related,
                    ))
                else:
                    runner_command = self._package_manager_command(ctx, script_name)
                    if runner_command:
                        results.append(
                            run_command(
                                self.name,
                                f"js_ts:script:{script_name}",
                                runner_command,
                                ctx,
                                scope_files,
                                execution_kind=EXECUTION_KIND_EXECUTED,
                                scope="project",
                            )
                        )
                    else:
                        results.append(result_skip(
                            self.name,
                            "js_ts:script_smoke",
                            "Project script smoke skipped: no supported package manager binary found.",
                            execution_kind=EXECUTION_KIND_EXECUTED,
                            command=f"npm run {script_name}",
                            scope="project",
                            related_files=related,
                        ))

        return results or [result_skip(
            self.name,
            "project_smoke_not_configured",
            "No JS/TS project smoketest command configured; relying on static per-file checks.",
            execution_kind=EXECUTION_KIND_EXECUTED,
            related_files=related,
            scope="project",
        )]

    def file_smoketest(self, ctx: SmoketestContext, file_path: Path, scope_files: list[Path]) -> list[SmoketestResult]:
        suffix = file_path.suffix.lower()
        rel_file = rel_name(file_path, ctx.qodeyard_path)
        if suffix not in {".js", ".jsx", ".mjs", ".cjs"}:
            return []
        node = find_binary("node", cwd=ctx.qodeyard_path)
        if not node:
            return [result_skip(
                self.name,
                "js_ts:node_check",
                "Node runtime unavailable; JS parse check skipped.",
                execution_kind=EXECUTION_KIND_STATIC,
                command=f"node --check {rel_file}",
                file=rel_file,
                files=[rel_file],
                related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
                scope="file",
            )]
        return [
            run_command(
                self.name,
                "js_ts:node_check",
                [node, "--check", rel_file],
                ctx,
                scope_files,
                execution_kind=EXECUTION_KIND_SYNTAX,
                scope="file",
                target_file=file_path,
            )
        ]


__all__ = ["JsTsAdapter"]
