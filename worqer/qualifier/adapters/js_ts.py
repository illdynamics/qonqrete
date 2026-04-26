# worqer/qualifier/adapters/js_ts.py
# ═══════════════════════════════════════════════════════════════════════════════
# JS/TS adapter — qualify_js_ts.
#
# Checks:
#   - Biome   (biome check <file>) — JS/TS/JSX/TSX lint + formatting sanity
#   - tsc --noEmit                  — TypeScript type-checking, only when
#                                     a tsconfig.json exists near the file
#
# tsc is invoked ONCE at preflight over the project (not per-file), because
# tsc's model is project-based. Per-file qualify() still runs biome which
# is fast and per-file-friendly.
#
# Discovery: local node_modules/.bin first, then PATH. Missing tools ->
# info-level diagnostic at preflight, no crash.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import json
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


_TS_EXTS = {".ts", ".tsx"}
_NON_BLOCKING_BIOME_PREFIXES = (
    "format",
    "lint/style/",
    "lint/complexity/",
)


class JsTsAdapter(Adapter):
    name = "js_ts"
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

    def preflight(self, ctx: QualifyContext) -> list[VerificationResult]:
        results: list[VerificationResult] = []

        biome = find_binary("biome", cwd=ctx.qodeyard_path)
        if biome is None:
            results.append(result_info(
                file_path="-",
                check_type="js_ts:biome",
                message=(
                    "biome not found — using degraded Node.js syntax checks. "
                    "Install via `npm i -g @biomejs/biome` for stronger validation."
                ),
            ))

        # Only complain about tsc if there's actually a TS project to check
        has_ts_project = _has_ts_project(ctx.qodeyard_path)
        tsc = find_binary("tsc", cwd=ctx.qodeyard_path)
        if has_ts_project and tsc is None:
            results.append(result_info(
                file_path="-",
                check_type="js_ts:tsc",
                message=(
                    "tsc not found — TypeScript type-check disabled. "
                    "Install via `npm i -g typescript` or include it "
                    "in the repo's node_modules."
                ),
            ))

        # Run tsc once at preflight (project-wide). Per-file tsc doesn't
        # produce meaningful results because TypeScript is project-based.
        if has_ts_project and tsc is not None:
            ctx.scratch["js_ts:tsc_results"] = _run_tsc_project(
                tsc, ctx.qodeyard_path,
            )
            results.extend(ctx.scratch["js_ts:tsc_results"])

        return results

    def qualify(
        self,
        file_path: Path,
        ctx: QualifyContext,
    ) -> list[VerificationResult]:
        rel = rel_name(file_path, ctx.qodeyard_path)
        results: list[VerificationResult] = []

        biome = find_binary("biome", cwd=ctx.qodeyard_path)
        if biome is not None:
            results.extend(_run_biome(file_path, rel, biome))
        else:
            node = find_binary("node", cwd=ctx.qodeyard_path)
            if node is not None and file_path.suffix.lower() in {".js", ".jsx", ".cjs", ".mjs"}:
                results.extend(_run_node_check(file_path, rel, node))

        return results


# ─── helpers ───────────────────────────────────────────────────────────────

def _run_node_check(
    file_path: Path,
    rel: str,
    node_bin: str,
) -> list[VerificationResult]:
    try:
        proc = subprocess.run(
            [node_bin, "--check", str(file_path)],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "js_ts:node-check", "node --check timed out")]
    except Exception as exc:
        return [result_warn(rel, "js_ts:node-check", f"node --check failed: {exc}")]

    if proc.returncode == 0:
        return [result_pass(rel, "js_ts:node-check", "Node syntax check passed (degraded validation)")]

    stderr = (proc.stderr or proc.stdout or "").strip()
    
    # Try to extract line number from stderr
    import re
    m = re.search(r":(\d+)\n", stderr)
    line_number = int(m.group(1)) if m else None
        
    return [result_error(rel, "js_ts:node-check", f"Syntax error: {stderr.splitlines()[0] if stderr else 'unknown'}", line_number=line_number)]

def _has_ts_project(qodeyard: Path) -> bool:
    """Project has TS work to type-check if:
       - a tsconfig.json exists, OR
       - at least one .ts/.tsx file is present.

    v1.3.10: walks with the shared infra skip list so tsconfigs / *.ts
    files buried inside validation-root/, attempts/, node_modules/ etc.
    do NOT cause us to claim 'yes, there is a TS project' against a
    polluted qodeyard.
    """
    try:
        from ..runner import _SKIP_DIR_NAMES as _SKIP
    except Exception:
        _SKIP = set()

    def _safe_walk(root):
        stack = [root]
        while stack:
            cur = stack.pop()
            try:
                entries = list(cur.iterdir())
            except OSError:
                continue
            for e in entries:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    if e.name in _SKIP or e.name.startswith("qage_"):
                        continue
                    stack.append(e)
                elif e.is_file():
                    yield e

    try:
        for f in _safe_walk(qodeyard):
            n = f.name
            if n == "tsconfig.json" or (n.startswith("tsconfig") and n.endswith(".json")):
                return True
            if n.endswith(".ts") or n.endswith(".tsx"):
                return True
    except Exception:
        return False
    return False


def _run_biome(
    file_path: Path,
    rel: str,
    biome_bin: str,
) -> list[VerificationResult]:
    """Biome in diagnostic mode. We ask for JSON via --reporter=json."""
    try:
        proc = subprocess.run(
            [biome_bin, "check", "--reporter=json", "--no-errors-on-unmatched",
             str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "js_ts:biome", "biome timed out")]
    except Exception as exc:
        return [result_warn(rel, "js_ts:biome", f"biome failed: {exc}")]

    # Biome: rc=0 clean, rc=1 violations, rc>=2 internal error
    if proc.returncode == 0 and not (proc.stdout or "").strip():
        return [result_pass(rel, "js_ts:biome", "biome clean")]

    if proc.returncode >= 2:
        stderr = (proc.stderr or "").strip()
        return [result_warn(
            rel, "js_ts:biome",
            f"biome error (rc={proc.returncode}): {stderr[:200]}",
        )]

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        # Fall back to the human-readable stderr/stdout
        text = (proc.stderr or proc.stdout or "").strip()
        if not text:
            return [result_pass(rel, "js_ts:biome", "biome clean")]
        return [result_warn(
            rel, "js_ts:biome", f"biome: {text[:300]}",
        )]

    # Biome JSON shape has varied across versions. We accept either a
    # top-level "diagnostics" list or a "summary"/"files" structure and
    # pull what we can find.
    diagnostics = []
    if isinstance(payload, dict):
        diagnostics = payload.get("diagnostics") or []
        if not diagnostics and "files" in payload:
            for f_entry in payload.get("files", []) or []:
                diagnostics.extend(f_entry.get("diagnostics", []) or [])

    out: list[VerificationResult] = []
    for d in diagnostics:
        severity = (d.get("severity") or "warning").lower()
        category = str(d.get("category") or "biome")
        effective_severity = severity
        if (
            effective_severity == "error"
            and _is_non_blocking_biome_category(category)
        ):
            # Keep style/format drift visible but don't block execution.
            effective_severity = "warning"
        desc = (
            d.get("description")
            or (d.get("message") or {}).get("content")
            or "biome violation"
        )
        if isinstance(desc, list):
            desc = " ".join(
                str(seg.get("content", seg)) if isinstance(seg, dict) else str(seg)
                for seg in desc
            )
        line = None
        loc = d.get("location") or {}
        span = loc.get("span") or {}
        if isinstance(span, dict):
            line = span.get("start", {}).get("line") if isinstance(
                span.get("start"), dict
            ) else span.get("start_line")

        msg = f"{category}: {str(desc)[:300]}"
        if effective_severity == "error":
            out.append(result_error(rel, "js_ts:biome", msg, line_number=line))
        else:
            out.append(result_warn(rel, "js_ts:biome", msg, line_number=line))

    if not out:
        out.append(result_pass(rel, "js_ts:biome", "biome clean"))
    return out


def _is_non_blocking_biome_category(category: str) -> bool:
    normalized = (category or "").strip().lower()
    if not normalized:
        return False
    return normalized.startswith(_NON_BLOCKING_BIOME_PREFIXES)


def _run_tsc_project(
    tsc_bin: str,
    qodeyard: Path,
) -> list[VerificationResult]:
    """Run tsc --noEmit over the qodeyard. Project-based, so one shot.

    v1.3.10: uses the shared infra skip list so tsc never ends up
    type-checking files inside validation-root/, attempts/, build/,
    node_modules/, etc.
    """
    try:
        from ..runner import _SKIP_DIR_NAMES as _SKIP
    except Exception:
        _SKIP = set()

    def _safe_walk(root):
        stack = [root]
        while stack:
            cur = stack.pop()
            try:
                entries = list(cur.iterdir())
            except OSError:
                continue
            for e in entries:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    if e.name in _SKIP or e.name.startswith("qage_"):
                        continue
                    stack.append(e)
                elif e.is_file():
                    yield e

    # Prefer running against the nearest tsconfig.json if present; else
    # just fall back to an all-files sweep with --noEmit --allowJs=false.
    tsconfigs = [f for f in _safe_walk(qodeyard) if f.name == "tsconfig.json"]
    if tsconfigs:
        # Pick the shallowest tsconfig — least surprising default
        tsconfig = min(tsconfigs, key=lambda p: len(p.parts))
        cmd = [tsc_bin, "--noEmit", "--pretty", "false", "-p", str(tsconfig)]
    else:
        # No tsconfig — only check the .ts/.tsx files explicitly
        ts_files = [
            str(f) for f in _safe_walk(qodeyard)
            if f.is_file() and (f.suffix == ".ts" or f.suffix == ".tsx")
        ]
        if not ts_files:
            return []
        cmd = [tsc_bin, "--noEmit", "--pretty", "false"] + ts_files

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(qodeyard),
        )
    except subprocess.TimeoutExpired:
        return [result_warn("-", "js_ts:tsc", "tsc timed out (>120s)")]
    except Exception as exc:
        return [result_warn("-", "js_ts:tsc", f"tsc invocation failed: {exc}")]

    if proc.returncode == 0:
        return [result_pass("-", "js_ts:tsc", "tsc --noEmit clean")]

    # Parse each tsc diagnostic line: "path/to/file.ts(line,col): error TSxxxx: message"
    import re
    pattern = re.compile(
        r"^(?P<path>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s+"
        r"(?P<sev>error|warning)\s+(?P<code>TS\d+):\s+(?P<msg>.+)$"
    )
    diagnostics: list[VerificationResult] = []
    for raw in (proc.stdout or "").splitlines():
        m = pattern.match(raw)
        if not m:
            continue
        p = Path(m.group("path"))
        try:
            rel = str(p.resolve().relative_to(qodeyard.resolve()))
        except Exception:
            rel = p.name
        sev = m.group("sev")
        msg = f"{m.group('code')}: {m.group('msg')}"
        line = int(m.group("line"))
        if sev == "error":
            diagnostics.append(result_error(rel, "js_ts:tsc", msg, line_number=line))
        else:
            diagnostics.append(result_warn(rel, "js_ts:tsc", msg, line_number=line))

    if not diagnostics:
        # Non-zero exit but nothing parseable — record as a warning
        stderr = (proc.stderr or "").strip()
        diagnostics.append(result_warn(
            "-", "js_ts:tsc",
            f"tsc exited {proc.returncode}: {stderr[:200] or '(no output)'}",
        ))
    return diagnostics


__all__ = ["JsTsAdapter"]
