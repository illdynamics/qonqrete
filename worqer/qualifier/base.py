# worqer/qualifier/base.py
# ═══════════════════════════════════════════════════════════════════════════════
# Adapter base interface + shared helpers.
#
# Each language adapter implements the Adapter protocol. The runner never
# cares about language-specific detail — it only sees:
#   - adapter.name
#   - adapter.extensions
#   - adapter.preflight(ctx)  -> list[VerificationResult]  (tool diagnostics)
#   - adapter.qualify(file_path, ctx) -> list[VerificationResult]
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import (
    VerificationResult,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)


@dataclass
class QualifyContext:
    """Per-run context handed to every adapter.

    Intentionally minimal: everything an adapter needs to do its job is
    here. Adapters MUST NOT reach into global state or re-read config.
    """

    qodeyard_path: Path
    qontext_path: Optional[Path]
    # Full raw config dict (already-loaded yaml). Adapters may read their
    # own section but should tolerate missing keys.
    config: dict = field(default_factory=dict)
    # Legacy per-check toggles from verification.checks.*. Python adapter
    # consults these so v1.3.0 config behaviour is preserved bit-for-bit.
    python_checks: dict = field(default_factory=dict)
    # A scratch dict the runner can stash cross-adapter lookups in
    # (e.g. "a tsconfig.json exists at path X"). Not persisted.
    scratch: dict = field(default_factory=dict)
    # v1.4.0: Task tier (low, medium, high) for severity gating.
    tier: str = "low"


class Adapter(ABC):
    """Pluggable per-language validator adapter."""

    #: Human-friendly name — also used as the top-level namespace for
    #: check_type slugs emitted by this adapter.
    name: str = "base"

    #: File extensions this adapter handles. Lowercase, include the dot.
    extensions: tuple[str, ...] = ()

    def preflight(self, ctx: QualifyContext) -> list[VerificationResult]:
        """Run once per cycle before any qualify() call.

        Default implementation returns nothing. Adapters that rely on
        external binaries should override this to emit one `info` result
        per missing required tool. Crashes here must not propagate —
        return an error-severity result instead.
        """
        return []

    @abstractmethod
    def qualify(
        self,
        file_path: Path,
        ctx: QualifyContext,
    ) -> list[VerificationResult]:
        """Validate a single file and return normalized results."""
        raise NotImplementedError


# ─── result-construction helpers ───────────────────────────────────────────

def result_pass(
    file_path: str,
    check_type: str,
    message: str = "OK",
) -> VerificationResult:
    return VerificationResult(
        file_path=file_path,
        check_type=check_type,
        passed=True,
        message=message,
    )


def result_warn(
    file_path: str,
    check_type: str,
    message: str,
    line_number: Optional[int] = None,
) -> VerificationResult:
    return VerificationResult(
        file_path=file_path,
        check_type=check_type,
        passed=False,
        message=message,
        line_number=line_number,
        severity=SEVERITY_WARNING,
    )


def result_error(
    file_path: str,
    check_type: str,
    message: str,
    line_number: Optional[int] = None,
) -> VerificationResult:
    return VerificationResult(
        file_path=file_path,
        check_type=check_type,
        passed=False,
        message=message,
        line_number=line_number,
        severity=SEVERITY_ERROR,
    )


def result_info(
    file_path: str,
    check_type: str,
    message: str,
) -> VerificationResult:
    return VerificationResult(
        file_path=file_path,
        check_type=check_type,
        passed=True,  # info is advisory; passed=True keeps it non-blocking
        message=message,
        severity=SEVERITY_INFO,
    )


def rel_name(file_path: Path, qodeyard_path: Path) -> str:
    """Relative file name for reporting. Falls back to .name on failure."""
    try:
        return str(file_path.relative_to(qodeyard_path))
    except Exception:
        return file_path.name


__all__ = [
    "Adapter",
    "QualifyContext",
    "result_pass",
    "result_warn",
    "result_error",
    "result_info",
    "rel_name",
]
