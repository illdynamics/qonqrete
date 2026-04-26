# worqer/smoqetester/adapters/html_css.py
from __future__ import annotations

import re
from pathlib import Path

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
from ..models import EXECUTION_KIND_EXECUTED, EXECUTION_KIND_STATIC, EXECUTION_KIND_HTTP, EXECUTION_KIND_BROWSER, SmoketestResult


_HTML_REF_PATTERN = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_CSS_URL_PATTERN = re.compile(r"""url\(([^)]+)\)""", re.IGNORECASE)
_REMOTE_REF_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _clean_ref(raw: str) -> str:
    value = str(raw or "").strip().strip("\"'")
    value = value.split("#", 1)[0]
    value = value.split("?", 1)[0]
    return value


def _is_local_ref(ref: str) -> bool:
    if not ref:
        return False
    if ref.startswith("#") or ref.startswith("//"):
        return False
    if _REMOTE_REF_PATTERN.match(ref):
        return False
    return True


class HtmlCssAdapter(Adapter):
    name = "html_css"
    extensions = (".html", ".htm", ".css")

    def preflight(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        related = sorted(set(rel_name(item, ctx.qodeyard_path) for item in scope_files))
        return [result_pass(
            self.name,
            "html_css_local_static",
            "HTML/CSS smoketest uses local static checks only (no browser/runtime execution).",
            execution_kind=EXECUTION_KIND_STATIC,
            related_files=related,
            scope="preflight",
        )]

    def _run_browser_or_http_probe(self, ctx: SmoketestContext, html_file: Path, scope_files: list[Path]) -> SmoketestResult:
        rel = rel_name(html_file, ctx.qodeyard_path)
        import shutil
        python_bin = shutil.which("python3") or shutil.which("python")
        if not python_bin:
            return result_skip(
                self.name,
                "html:http_probe",
                "Python not available to run local HTTP server probe.",
                execution_kind=EXECUTION_KIND_HTTP,
                scope="project",
                file=rel,
            )

        probe_script = f"""import http.server
import socketserver
import threading
import urllib.request
import sys
import time

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.5)
    
    url = f"http://127.0.0.1:{{port}}/{rel}"
    try:
        req = urllib.request.urlopen(url, timeout=5)
        if req.status == 200:
            print("HTTP probe successful: able to serve and fetch the file locally.")
            print("Note: degraded runtime validation. No browser automation available to prove JS execution.")
            sys.exit(0)
        else:
            print(f"HTTP probe failed: HTTP {{req.status}}")
            sys.exit(1)
    except Exception as e:
        print(f"HTTP probe failed: {{e}}")
        sys.exit(1)
"""
        probe_path = ctx.qodeyard_path / ".qonqrete_http_probe.py"
        try:
            probe_path.write_text(probe_script)
            res = run_command(
                self.name,
                "html:http_probe",
                [python_bin, ".qonqrete_http_probe.py"],
                ctx,
                scope_files,
                execution_kind=EXECUTION_KIND_HTTP,
                scope="project",
                target_file=html_file,
            )
            res.command = "python _http_probe.py"
            return res
        finally:
            if probe_path.exists():
                try:
                    probe_path.unlink()
                except OSError:
                    pass

    def project_smoketest(self, ctx: SmoketestContext, scope_files: list[Path]) -> list[SmoketestResult]:
        append_changed_files = bool(ctx.adapter_config.get("append_changed_files", False))
        commands = collect_commands(self.name, ctx.adapter_config)
        results: list[SmoketestResult] = []
        
        for command_name, command, kind_override in commands:
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
            
        if bool(ctx.adapter_config.get("auto_http_probe", True)):
            html_candidates = [f for f in scope_files if f.suffix.lower() in {".html", ".htm"}]
            if not html_candidates:
                index = ctx.qodeyard_path / "index.html"
                if index.exists():
                    html_candidates = [index]
            
            if html_candidates:
                html_candidates.sort(key=lambda p: len(p.parts))
                results.append(self._run_browser_or_http_probe(ctx, html_candidates[0], scope_files))

        return results

    def _check_html_file(self, ctx: SmoketestContext, file_path: Path, scope_files: list[Path]) -> SmoketestResult:
        rel_file = rel_name(file_path, ctx.qodeyard_path)
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            return result_fail(
                self.name,
                "html:read",
                f"Unable to read HTML file: {exc}",
                execution_kind=EXECUTION_KIND_STATIC,
                file=rel_file,
                files=[rel_file],
                related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
                scope="file",
                severity="error",
            )

        missing_refs: list[str] = []
        for raw_ref in _HTML_REF_PATTERN.findall(text):
            cleaned = _clean_ref(raw_ref)
            if not _is_local_ref(cleaned):
                continue
            target = (file_path.parent / cleaned).resolve()
            if not target.exists():
                missing_refs.append(cleaned)

        if missing_refs:
            uniq = sorted(set(missing_refs))
            related = [rel_name(item, ctx.qodeyard_path) for item in scope_files]
            related.extend(rel_name((file_path.parent / ref).resolve(), ctx.qodeyard_path) for ref in uniq)
            return result_fail(
                self.name,
                "html:local_refs",
                f"Missing local HTML references: {', '.join(uniq[:8])}",
                execution_kind=EXECUTION_KIND_STATIC,
                file=rel_file,
                files=[rel_file],
                related_files=sorted(set(related)),
                scope="file",
            )

        return result_pass(
            self.name,
            "html:local_refs",
            "Local HTML references resolved.",
            execution_kind=EXECUTION_KIND_STATIC,
            file=rel_file,
            files=[rel_file],
            related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
            scope="file",
        )

    def _check_css_file(self, ctx: SmoketestContext, file_path: Path, scope_files: list[Path]) -> SmoketestResult:
        rel_file = rel_name(file_path, ctx.qodeyard_path)
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            return result_fail(
                self.name,
                "css:read",
                f"Unable to read CSS file: {exc}",
                execution_kind=EXECUTION_KIND_STATIC,
                file=rel_file,
                files=[rel_file],
                related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
                scope="file",
                severity="error",
            )

        if text.count("{") != text.count("}"):
            return result_fail(
                self.name,
                "css:brace_balance",
                "Unbalanced CSS braces detected.",
                execution_kind=EXECUTION_KIND_STATIC,
                file=rel_file,
                files=[rel_file],
                related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
                scope="file",
            )

        missing_refs: list[str] = []
        for raw_url in _CSS_URL_PATTERN.findall(text):
            cleaned = _clean_ref(raw_url)
            if not _is_local_ref(cleaned):
                continue
            target = (file_path.parent / cleaned).resolve()
            if not target.exists():
                missing_refs.append(cleaned)

        if missing_refs:
            uniq = sorted(set(missing_refs))
            related = [rel_name(item, ctx.qodeyard_path) for item in scope_files]
            related.extend(rel_name((file_path.parent / ref).resolve(), ctx.qodeyard_path) for ref in uniq)
            return result_fail(
                self.name,
                "css:local_assets",
                f"Missing local CSS asset references: {', '.join(uniq[:8])}",
                execution_kind=EXECUTION_KIND_STATIC,
                file=rel_file,
                files=[rel_file],
                related_files=sorted(set(related)),
                scope="file",
            )

        return result_pass(
            self.name,
            "css:local_assets",
            "CSS structural checks and local asset references look valid (degraded, non-parser validation).",
            execution_kind=EXECUTION_KIND_STATIC,
            file=rel_file,
            files=[rel_file],
            related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
            scope="file",
        )

    def file_smoketest(self, ctx: SmoketestContext, file_path: Path, scope_files: list[Path]) -> list[SmoketestResult]:
        suffix = file_path.suffix.lower()
        if suffix in {".html", ".htm"}:
            return [self._check_html_file(ctx, file_path, scope_files)]
        if suffix == ".css":
            return [self._check_css_file(ctx, file_path, scope_files)]
        return [result_skip(
            self.name,
            "file_unsupported",
            "Unsupported file extension for html_css adapter.",
            execution_kind=EXECUTION_KIND_STATIC,
            file=rel_name(file_path, ctx.qodeyard_path),
            files=[rel_name(file_path, ctx.qodeyard_path)],
            related_files=[rel_name(item, ctx.qodeyard_path) for item in scope_files],
            scope="file",
        )]


__all__ = ["HtmlCssAdapter"]
