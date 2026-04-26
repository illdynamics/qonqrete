# worqer/qualifier/adapters/html_css.py
# ═══════════════════════════════════════════════════════════════════════════════
# HTML/CSS adapter — qualify_html_css.
#
# Chosen CSS-native path: Stylelint (mature, dedicated CSS tooling).
# HTML path: html-validate.
#
# Truthful shipped scope here is HTML + plain CSS only. We do NOT claim
# SCSS/Sass/Less support unless their custom syntax/tooling/config path is
# actually wired and shipped, which it currently is not.
#
# We explicitly do NOT bolt Biome-for-CSS onto the same adapter — per spec,
# pick one coherent CSS path and stick with it.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

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


_HTML_EXTS = {".html", ".htm"}
_CSS_EXTS = {".css"}

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

    def preflight(self, ctx: QualifyContext) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        if find_binary("html-validate", cwd=ctx.qodeyard_path) is None:
            results.append(result_info(
                file_path="-",
                check_type="html_css:html-validate",
                message=(
                    "html-validate not found — using degraded built-in HTML structural checks. "
                    "Install via `npm i -g html-validate` for stronger validation."
                ),
            ))
        if find_binary("stylelint", cwd=ctx.qodeyard_path) is None:
            results.append(result_info(
                file_path="-",
                check_type="html_css:stylelint",
                message=(
                    "stylelint not found — using degraded built-in CSS structural checks. "
                    "Install via `npm i -g stylelint stylelint-config-standard` for stronger validation."
                ),
            ))
        return results

    def qualify(
        self,
        file_path: Path,
        ctx: QualifyContext,
    ) -> list[VerificationResult]:
        rel = rel_name(file_path, ctx.qodeyard_path)
        ext = file_path.suffix.lower()
        results: list[VerificationResult] = []

        if ext in _HTML_EXTS:
            html_validate = find_binary("html-validate", cwd=ctx.qodeyard_path)
            if html_validate is not None:
                results.extend(_run_html_validate(file_path, rel, html_validate))
            else:
                results.extend(_run_fallback_html_check(file_path, rel))
        elif ext in _CSS_EXTS:
            stylelint = find_binary("stylelint", cwd=ctx.qodeyard_path)
            if stylelint is not None:
                results.extend(_run_stylelint(file_path, rel, stylelint))
            else:
                results.extend(_run_fallback_css_check(file_path, rel))

        return results


# ─── helpers ───────────────────────────────────────────────────────────────

def _run_fallback_html_check(file_path: Path, rel: str) -> list[VerificationResult]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [result_error(rel, "html_css:html-fallback", f"Read error: {exc}")]
        
    out: list[VerificationResult] = []
    
    from html.parser import HTMLParser
    class StrictParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.errors = []
            self.void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
            
        def handle_starttag(self, tag, attrs):
            if tag not in self.void_tags:
                self.stack.append((tag, self.getpos()[0]))
                
        def handle_endtag(self, tag):
            if tag in self.void_tags:
                return
            if not self.stack:
                self.errors.append((self.getpos()[0], f"Unexpected end tag </{tag}>"))
            elif self.stack[-1][0] == tag:
                self.stack.pop()
            else:
                self.errors.append((self.getpos()[0], f"Mismatched end tag </{tag}>, expected </{self.stack[-1][0]}>"))
                
    parser = StrictParser()
    try:
        parser.feed(text)
        for line, err in parser.errors:
            out.append(result_error(rel, "html_css:html-fallback", err, line_number=line))
        for tag, line in parser.stack:
            out.append(result_error(rel, "html_css:html-fallback", f"Unclosed tag <{tag}>", line_number=line))
    except Exception as exc:
        out.append(result_error(rel, "html_css:html-fallback", f"Parse error: {exc}"))

    for m in _HTML_REF_PATTERN.finditer(text):
        cleaned = _clean_ref(m.group(1))
        if _is_local_ref(cleaned):
            target = (file_path.parent / cleaned).resolve()
            if not target.exists():
                out.append(result_error(
                    rel, "html_css:html-fallback", 
                    f"Missing local reference: {cleaned}",
                    line_number=text[:m.start()].count("\\n") + 1
                ))
                
    if not out:
        out.append(result_pass(rel, "html_css:html-fallback", "Fallback HTML structure and local refs clean (degraded validation)"))
    return out


def _run_fallback_css_check(file_path: Path, rel: str) -> list[VerificationResult]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [result_error(rel, "html_css:css-fallback", f"Read error: {exc}")]
        
    out: list[VerificationResult] = []
    if text.count("{") != text.count("}"):
        out.append(result_error(rel, "html_css:css-fallback", "Unbalanced braces '{' and '}'"))
        
    for m in _CSS_URL_PATTERN.finditer(text):
        cleaned = _clean_ref(m.group(1))
        if _is_local_ref(cleaned):
            target = (file_path.parent / cleaned).resolve()
            if not target.exists():
                out.append(result_error(
                    rel, "html_css:css-fallback", 
                    f"Missing local CSS asset: {cleaned}",
                    line_number=text[:m.start()].count("\\n") + 1
                ))
                
    if not out:
        out.append(result_pass(rel, "html_css:css-fallback", "Fallback CSS structure and assets clean (degraded validation)"))
    return out


def _run_html_validate(
    file_path: Path,
    rel: str,
    bin_path: str,
) -> list[VerificationResult]:
    try:
        proc = subprocess.run(
            [bin_path, "--formatter=json", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "html_css:html-validate", "html-validate timed out")]
    except Exception as exc:
        return [result_warn(
            rel, "html_css:html-validate", f"html-validate failed: {exc}",
        )]

    # rc 0 = clean, non-zero = violations found (or internal error)
    raw = (proc.stdout or "").strip()
    if proc.returncode == 0 and not raw:
        return [result_pass(rel, "html_css:html-validate", "html-validate clean")]

    try:
        payload = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        stderr = (proc.stderr or "").strip()
        return [result_warn(
            rel, "html_css:html-validate",
            f"non-JSON output: {(stderr or raw)[:200]}",
        )]

    out: list[VerificationResult] = []
    # html-validate JSON: [ { filePath, messages: [ {severity, ruleId, message, line, column} ], ... } ]
    reports = payload if isinstance(payload, list) else [payload]
    for report in reports:
        for m in (report.get("messages", []) or []):
            sev_num = m.get("severity", 1)  # 1 warning, 2 error
            rule = m.get("ruleId") or "html-validate"
            msg_text = m.get("message") or "html-validate violation"
            line = m.get("line")
            combined = f"{rule}: {msg_text}"
            if sev_num == 2:
                out.append(result_error(
                    rel, "html_css:html-validate", combined, line_number=line,
                ))
            else:
                out.append(result_warn(
                    rel, "html_css:html-validate", combined, line_number=line,
                ))
    if not out:
        out.append(result_pass(rel, "html_css:html-validate", "html-validate clean"))
    return out


def _run_stylelint(
    file_path: Path,
    rel: str,
    bin_path: str,
) -> list[VerificationResult]:
    try:
        proc = subprocess.run(
            [bin_path, "--formatter=json", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "html_css:stylelint", "stylelint timed out")]
    except Exception as exc:
        return [result_warn(rel, "html_css:stylelint", f"stylelint failed: {exc}")]

    raw = (proc.stdout or "").strip()
    if proc.returncode == 0 and (not raw or raw == "[]"):
        return [result_pass(rel, "html_css:stylelint", "stylelint clean")]

    # Stylelint emits JSON on stdout. Exit 1 = violations, 2 = config/other error.
    try:
        payload = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        stderr = (proc.stderr or "").strip()
        return [result_warn(
            rel, "html_css:stylelint",
            f"non-JSON output: {(stderr or raw)[:200]}",
        )]

    out: list[VerificationResult] = []
    reports = payload if isinstance(payload, list) else [payload]
    for report in reports:
        for w in (report.get("warnings", []) or []):
            rule = w.get("rule") or "stylelint"
            msg_text = w.get("text") or "stylelint violation"
            line = w.get("line")
            combined = f"{rule}: {msg_text}"
            # Stylelint warning rows are style-tier signals (format/style/lint),
            # so keep them visible but non-blocking during coding loops.
            out.append(result_warn(
                rel, "html_css:stylelint", combined, line_number=line,
            ))
        # Some stylelint errors land in `parseErrors`
        for pe in (report.get("parseErrors", []) or []):
            out.append(result_error(
                rel, "html_css:stylelint",
                f"parse: {pe.get('text', 'parse error')}",
                line_number=pe.get("line"),
            ))
    if not out:
        out.append(result_pass(rel, "html_css:stylelint", "stylelint clean"))
    return out


__all__ = ["HtmlCssAdapter"]
