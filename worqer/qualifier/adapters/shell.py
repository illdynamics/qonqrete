# worqer/qualifier/adapters/shell.py
# ═══════════════════════════════════════════════════════════════════════════════
# Shell adapter — qualify_shell.
#
# Checks:
#   - syntax via `<shell> -n` — chosen from shebang, defaults to `sh`
#   - ShellCheck — static analysis (if binary available)
#   - shfmt      — run with `-d` (diff) as a parse/formatting-sanity check;
#                  we NEVER mutate the user's file
#
# Missing tools surface ONE info-level row at preflight. Per-file qualify
# still runs `<shell> -n` since /bin/sh and /bin/bash are always present
# on any POSIX system that can run Python.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

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


_SHEBANG_TO_MODE = {
    "bash": "bash",
    "sh": "sh",
    "zsh": "zsh",
    "ksh": "ksh",
    "dash": "sh",
    "ash": "sh",
}


class ShellAdapter(Adapter):
    name = "shell"
    extensions = (".sh", ".bash", ".zsh", ".ksh")

    def preflight(self, ctx: QualifyContext) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        if find_binary("shellcheck") is None:
            results.append(result_info(
                file_path="-",
                check_type="shell:shellcheck",
                message=(
                    "shellcheck not found — static analysis disabled. "
                    "Install via `apt-get install shellcheck`."
                ),
            ))
        if find_binary("shfmt") is None:
            results.append(result_info(
                file_path="-",
                check_type="shell:shfmt",
                message=(
                    "shfmt not found — formatting sanity check disabled. "
                    "Install via `apt-get install shfmt` or the upstream binary."
                ),
            ))
        return results

    def qualify(
        self,
        file_path: Path,
        ctx: QualifyContext,
    ) -> list[VerificationResult]:
        rel = rel_name(file_path, ctx.qodeyard_path)
        results: list[VerificationResult] = []

        # 1. Syntax via <shell> -n
        mode = _pick_shell_mode(file_path)
        results.extend(_check_syntax(file_path, rel, mode))

        # 2. ShellCheck (if available). We don't short-circuit on a failed
        # `-n` — shellcheck often surfaces cleaner messages than bash.
        sc_bin = find_binary("shellcheck")
        if sc_bin is not None:
            results.extend(_run_shellcheck(file_path, rel, sc_bin))

        # 3. shfmt — validation only (diff mode, no mutation)
        fmt_bin = find_binary("shfmt")
        if fmt_bin is not None:
            results.extend(_run_shfmt(file_path, rel, fmt_bin))

        return results


# ─── helpers ───────────────────────────────────────────────────────────────

def _pick_shell_mode(file_path: Path) -> str:
    """Decide which shell to use for `-n` based on shebang/extension."""
    ext = file_path.suffix.lower()
    if ext == ".bash":
        return "bash"
    if ext == ".zsh":
        return "zsh"
    if ext == ".ksh":
        return "ksh"

    # .sh — look at the shebang, fall back to sh
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
    except Exception:
        return "sh"

    if first_line.startswith("#!"):
        low = first_line.lower()
        for key, mode in _SHEBANG_TO_MODE.items():
            if key in low:
                return mode
    return "sh"


def _check_syntax(
    file_path: Path,
    rel: str,
    mode: str,
) -> list[VerificationResult]:
    # Prefer the exact shell when it's available on PATH; otherwise fall
    # back to sh which is effectively guaranteed.
    shell_bin = find_binary(mode) or find_binary("sh")
    if shell_bin is None:
        return [result_warn(
            rel, "shell:syntax",
            "No shell binary available for `-n` check",
        )]
    try:
        proc = subprocess.run(
            [shell_bin, "-n", str(file_path)],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "shell:syntax", "shell -n timed out")]
    except Exception as exc:
        return [result_warn(
            rel, "shell:syntax", f"shell -n invocation failed: {exc}",
        )]

    if proc.returncode == 0:
        return [result_pass(rel, "shell:syntax", f"{mode} -n OK")]
    msg = (proc.stderr or proc.stdout or "shell syntax error").strip()
    # Try to extract a line number of the shape ": line 42:"
    line = _parse_shell_line(msg)
    return [VerificationResult(
        file_path=rel,
        check_type="shell:syntax",
        passed=False,
        message=msg[:500],
        line_number=line,
        severity="error",
    )]


def _parse_shell_line(msg: str) -> Optional[int]:
    # Typical: "<path>: line 12: syntax error: unexpected end of file"
    import re
    m = re.search(r":\s*line\s+(\d+):", msg)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _run_shellcheck(
    file_path: Path,
    rel: str,
    bin_path: str,
) -> list[VerificationResult]:
    import json as _json
    try:
        proc = subprocess.run(
            [bin_path, "--format=json", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "shell:shellcheck", "shellcheck timed out")]
    except Exception as exc:
        return [result_warn(
            rel, "shell:shellcheck", f"shellcheck failed: {exc}",
        )]

    if proc.returncode == 0 and not (proc.stdout or "").strip():
        return [result_pass(rel, "shell:shellcheck", "shellcheck clean")]

    try:
        diagnostics = _json.loads(proc.stdout or "[]")
    except Exception:
        return [result_warn(
            rel, "shell:shellcheck",
            "shellcheck produced non-JSON output",
        )]

    out: list[VerificationResult] = []
    for d in diagnostics:
        level = (d.get("level") or "warning").lower()
        code = d.get("code")
        code_str = f"SC{code}" if code else "SC????"
        msg = d.get("message") or "shellcheck violation"
        line = d.get("line")
        if level == "error":
            out.append(result_error(
                rel, "shell:shellcheck",
                f"{code_str}: {msg}", line_number=line,
            ))
        elif level in ("warning", "style", "info"):
            out.append(result_warn(
                rel, "shell:shellcheck",
                f"{code_str}: {msg}", line_number=line,
            ))
        else:
            out.append(result_warn(
                rel, "shell:shellcheck",
                f"{code_str}: {msg}", line_number=line,
            ))
    if not out:
        out.append(result_pass(rel, "shell:shellcheck", "shellcheck clean"))
    return out


def _run_shfmt(
    file_path: Path,
    rel: str,
    bin_path: str,
) -> list[VerificationResult]:
    """Run shfmt in diff mode — parse-check only, never mutates the file."""
    try:
        proc = subprocess.run(
            [bin_path, "-d", str(file_path)],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return [result_warn(rel, "shell:shfmt", "shfmt timed out")]
    except Exception as exc:
        return [result_warn(rel, "shell:shfmt", f"shfmt failed: {exc}")]

    # shfmt -d exits 0 when already formatted. Non-zero with stdout means
    # "needs formatting" (warning). Non-zero with stderr means parse error.
    if proc.returncode == 0:
        return [result_pass(rel, "shell:shfmt", "shfmt OK")]

    stderr = (proc.stderr or "").strip()
    if stderr and not (proc.stdout or "").strip():
        # Parse-level error — shfmt couldn't even parse the file
        return [result_error(
            rel, "shell:shfmt", f"shfmt parse error: {stderr[:300]}",
        )]

    # Formatting drift — non-fatal, surface as warning with a short hint
    return [result_warn(
        rel, "shell:shfmt",
        "shfmt suggests formatting changes (run `shfmt -w` to apply)",
    )]


__all__ = ["ShellAdapter"]
