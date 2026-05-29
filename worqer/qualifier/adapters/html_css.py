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

_PLACEHOLDER_PATTERNS = [
    (re.compile(r"\bTODO\b"), "TODO marker"),
    (re.compile(r"\bFIXME\b"), "FIXME marker"),
    (re.compile(r"\blorem\s+ipsum\b", re.IGNORECASE), "lorem ipsum placeholder"),
    (re.compile(r"\bscaffold(?:ing)?\b", re.IGNORECASE), "scaffold reference"),
    (re.compile(r"\bplaceholder\b", re.IGNORECASE), "placeholder text"),
    (re.compile(r"\btemplate\s+(?:content|text|code)\b", re.IGNORECASE), "template content"),
]


def _check_placeholder_content(
    text: str,
    rel: str,
    check_type: str,
    out: list,
) -> None:
    """Scan for placeholder/scaffold/TODO content and add warnings."""
    for pattern, label in _PLACEHOLDER_PATTERNS:
        matches = list(pattern.finditer(text))
        if 0 < len(matches) <= 10:
            for m in matches:
                line_no = text[:m.start()].count("\n") + 1
                out.append(result_warn(
                    rel, check_type,
                    f"Placeholder content detected: {label}",
                    line_number=line_no,
                ))
        elif len(matches) > 10:
            line_no = text[:matches[0].start()].count("\n") + 1
            out.append(result_warn(
                rel, check_type,
                f"Widespread placeholder content: {len(matches)} occurrences of {label}",
                line_number=line_no,
            ))


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
    """Deterministic HTML structural check with blocking errors and advisory warnings."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [result_error(rel, "html_css:html-fallback", f"Read error: {exc}")]

    out: list[VerificationResult] = []
    lowered = text.lower()

    if not re.search(r"<!doctype\s+html", lowered[:300], re.IGNORECASE):
        out.append(result_error(
            rel, "html_css:html-fallback",
            "Missing <!doctype html> for standalone HTML document",
        ))

    from html.parser import HTMLParser

    class _FallbackHTMLParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self._stack: list[tuple[str, int]] = []
            self._errors: list[tuple[int, str]] = []
            self.tags_seen: set[str] = set()
            self.ids: dict[str, int] = {}
            self.duplicate_ids: list[tuple[int, str, int]] = []
            self.anchor_refs: list[tuple[int, str]] = []
            self.label_for_ids: set[str] = set()
            self.controls: list[dict[str, object]] = []
            self.images: list[dict[str, object]] = []
            self.refs: list[tuple[int, str]] = []
            self.external_refs: list[str] = []
            self._label_depth = 0
            self._void_tags = {
                "area", "base", "br", "col", "embed", "hr", "img", "input",
                "link", "meta", "param", "source", "track", "wbr",
            }

        def handle_starttag(self, tag, attrs):
            tag = str(tag or "").lower()
            line = self.getpos()[0]
            attr_map = {str(k).lower(): ("" if v is None else str(v)) for k, v in attrs}
            self.tags_seen.add(tag)

            id_value = attr_map.get("id", "").strip()
            if id_value:
                if id_value in self.ids:
                    self.duplicate_ids.append((line, id_value, self.ids[id_value]))
                else:
                    self.ids[id_value] = line

            if tag == "label":
                self._label_depth += 1
                label_for = attr_map.get("for", "").strip()
                if label_for:
                    self.label_for_ids.add(label_for)

            if tag == "a":
                href = attr_map.get("href", "").strip()
                if href.startswith("#") and len(href) > 1:
                    self.anchor_refs.append((line, href[1:]))

            if tag == "img":
                self.images.append({"line": line, "has_alt": "alt" in attr_map})

            if tag in {"input", "select", "textarea"}:
                self.controls.append({
                    "line": line,
                    "tag": tag,
                    "type": attr_map.get("type", "").strip().lower(),
                    "id": id_value,
                    "has_accessible_name": bool(
                        attr_map.get("aria-label", "").strip()
                        or attr_map.get("aria-labelledby", "").strip()
                        or attr_map.get("title", "").strip()
                        or self._label_depth > 0
                    ),
                })

            for attr_name in ("src", "href"):
                ref = attr_map.get(attr_name)
                if ref is None:
                    continue
                if re.match(r"^https?://", ref, flags=re.IGNORECASE):
                    self.external_refs.append(ref)
                self.refs.append((line, ref))

            if tag not in self._void_tags:
                self._stack.append((tag, line))

        def handle_endtag(self, tag):
            tag = str(tag or "").lower()
            if tag == "label" and self._label_depth > 0:
                self._label_depth -= 1
            if tag in self._void_tags:
                return
            if not self._stack:
                self._errors.append(
                    (self.getpos()[0], f"Unexpected end tag </{tag}> with no open element")
                )
            elif self._stack[-1][0] == tag:
                self._stack.pop()
            else:
                found = False
                for i in range(len(self._stack) - 1, -1, -1):
                    if self._stack[i][0] == tag:
                        found = True
                        unclosed = [t for t, _ in self._stack[i + 1:]]
                        self._stack = self._stack[:i]
                        self._errors.append((
                            self.getpos()[0],
                            f"Mismatched end tag </{tag}> - implicitly closing: {chr(44).join(unclosed)}",
                        ))
                        break
                if not found:
                    self._errors.append((
                        self.getpos()[0],
                        f"Unexpected end tag </{tag}>, expected </{self._stack[-1][0]}>",
                    ))

    parser = _FallbackHTMLParser()
    try:
        parser.feed(text)
        for line, err in parser._errors:
            out.append(result_error(rel, "html_css:html-fallback", err, line_number=line))
        for tag, line in parser._stack:
            out.append(result_error(
                rel, "html_css:html-fallback",
                f"Unclosed tag <{tag}>", line_number=line,
            ))
    except Exception as exc:
        out.append(result_error(rel, "html_css:html-fallback", f"Parse error: {exc}"))

    for tag in ("html", "head", "body"):
        if tag not in parser.tags_seen:
            out.append(result_warn(
                rel, "html_css:html-fallback",
                f"Missing <{tag}> element in standalone HTML document",
            ))

    for line_no, id_val, first_line in parser.duplicate_ids:
        out.append(result_warn(
            rel, "html_css:html-fallback",
            f"Duplicate id \x27{id_val}\x27 (first at line {first_line})",
            line_number=line_no,
        ))

    for line_no, anchor_target in parser.anchor_refs:
        if anchor_target and anchor_target not in parser.ids:
            out.append(result_warn(
                rel, "html_css:html-fallback",
                f"Broken anchor reference \x27#{anchor_target}\x27 - no matching id found",
                line_number=line_no,
            ))

    for control in parser.controls:
        tag_name = str(control.get("tag") or "")
        input_type = str(control.get("type") or "")
        if tag_name == "input" and input_type in {"hidden", "submit", "button", "reset", "image"}:
            continue
        input_id = str(control.get("id") or "").strip()
        if input_id and input_id in parser.label_for_ids:
            continue
        if bool(control.get("has_accessible_name")):
            continue
        out.append(result_warn(
            rel, "html_css:html-fallback",
            f"<{tag_name}> may be missing an associated <label>",
            line_number=int(control.get("line") or 0) or None,
        ))

    for image in parser.images:
        if not image.get("has_alt"):
            out.append(result_warn(
                rel, "html_css:html-fallback",
                "<img> missing alt attribute",
                line_number=int(image.get("line") or 0) or None,
            ))

    for line_no, raw_ref in parser.refs:
        cleaned = _clean_ref(raw_ref)
        if _is_local_ref(cleaned):
            target = (file_path.parent / cleaned).resolve()
            if not target.exists():
                out.append(result_warn(
                    rel, "html_css:html-fallback",
                    f"Missing local reference: {cleaned}",
                    line_number=line_no,
                ))

    if parser.external_refs:
        msg = f"Forbidden external network references: {chr(44).join(parser.external_refs[:5])}"
        if len(parser.external_refs) > 5:
            msg += f" ... +{len(parser.external_refs) - 5} more"
        out.append(result_warn(rel, "html_css:html-fallback", msg))

    # WARNING: placeholder/scaffold content
    _check_placeholder_content(text, rel, "html_css:html-fallback", out)

    # Final verdict
    errors = [v for v in out if v.severity == "error"]
    warnings_list = [v for v in out if v.severity == "warning"]
    if not errors and not warnings_list:
        out.append(result_pass(
            rel, "html_css:html-fallback",
            "Fallback HTML structure, IDs, anchors, forms, images, local refs, and external deps clean (degraded validation)",
        ))
    return out


def _run_fallback_css_check(file_path: Path, rel: str) -> list[VerificationResult]:
    """Deterministic CSS structural check with blocking errors."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [result_error(rel, "html_css:css-fallback", f"Read error: {exc}")]

    out: list[VerificationResult] = []

    # BLOCKING: empty stylesheet
    stripped = text.strip()
    if not stripped or stripped in ("", "/**/", "/* empty */", "/* */"):
        out.append(result_error(
            rel, "html_css:css-fallback", "Empty or near-empty stylesheet",
        ))
        return out

    # BLOCKING: merge conflict markers
    if re.search(r"^<{7,}\s|^={7,}\s|^>{7,}\s", text, re.MULTILINE):
        out.append(result_error(
            rel, "html_css:css-fallback",
            "Unresolved merge conflict markers detected",
        ))

    # BLOCKING: unbalanced braces
    open_count = text.count("{")
    close_count = text.count("}")
    if open_count != close_count:
        out.append(result_error(
            rel, "html_css:css-fallback",
            f"Unbalanced braces: {{ = {open_count}, }} = {close_count}",
        ))

    # BLOCKING: missing local CSS asset references
    for m in _CSS_URL_PATTERN.finditer(text):
        cleaned = _clean_ref(m.group(1))
        if _is_local_ref(cleaned):
            target = (file_path.parent / cleaned).resolve()
            if not target.exists():
                line_no = text[:m.start()].count("\n") + 1
                out.append(result_error(
                    rel, "html_css:css-fallback",
                    f"Missing local CSS asset: {cleaned}",
                    line_number=line_no,
                ))

    # BLOCKING: forbidden remote @import
    remote_import_pattern = re.compile(
        r"""@import\s+url\(["\x27]?(https?://[^"\x27)\s]+)["\x27]?\)""",
        re.IGNORECASE,
    )
    remote_imports: list[str] = []
    for m in remote_import_pattern.finditer(text):
        remote_imports.append(m.group(1))
    if remote_imports:
        msg = f"Forbidden remote @import: {chr(44).join(remote_imports[:3])}"
        if len(remote_imports) > 3:
            msg += f" ... +{len(remote_imports) - 3} more"
        out.append(result_error(rel, "html_css:css-fallback", msg))

    # WARNING: duplicate selectors (top-level only, conservative)
    top_level_selectors: dict[str, int] = {}
    selector_pattern = re.compile(r"""^\s*([^{}\n]+?)\s*\{""", re.MULTILINE)
    for m in selector_pattern.finditer(text):
        sel = " ".join(m.group(1).split()).strip()
        if not sel or sel.startswith("@") or sel.startswith("//") or sel.startswith("/*"):
            continue
        line_no = text[:m.start()].count("\n") + 1
        if sel in top_level_selectors:
            out.append(result_warn(
                rel, "html_css:css-fallback",
                f"Duplicate top-level selector \x27{sel}\x27 (first at line {top_level_selectors[sel]})",
                line_number=line_no,
            ))
        else:
            top_level_selectors[sel] = line_no

    # WARNING: placeholder/scaffold content
    _check_placeholder_content(text, rel, "html_css:css-fallback", out)

    # Final verdict
    errors = [v for v in out if v.severity == "error"]
    warnings_list = [v for v in out if v.severity == "warning"]
    if not errors and not warnings_list:
        out.append(result_pass(
            rel, "html_css:css-fallback",
            "Fallback CSS structure, assets, imports, and selectors clean (degraded validation)",
        ))
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
