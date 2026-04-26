# worqer/qualifier/__init__.py
# ═══════════════════════════════════════════════════════════════════════════════
# Qualifier — pluggable per-language deterministic validation package.
#
# Public API (stable, consumed by worqer/inspeqtor.py):
#   - run_verification(qodeyard_path, qontext_path, cycle_num, config,
#                      changed_files=None)   # v2.x: scope-aware, back-compat
#   - normalize_scoped_files(qodeyard_path, changed_files)  # v2.x helper
#   - VerificationResult
#   - VerificationReport
#
# InspeQtor does `import qualifier; qualifier.run_verification(...)` and
# that shape is preserved by this package exactly. Do not break it.
# The 4-arg positional call continues to work unchanged (full-scan mode);
# new callers that can narrow the work set pass `changed_files=...` to
# opt into SCOPED mode.
# ═══════════════════════════════════════════════════════════════════════════════
from .models import VerificationResult, VerificationReport
from .runner import run_verification, normalize_scoped_files
from . import registry  # re-exported for tests / advanced callers

__all__ = [
    "VerificationResult",
    "VerificationReport",
    "run_verification",
    "normalize_scoped_files",
    "registry",
]

from pathlib import Path

# Package version follows the repo VERSION file so CLI/docs/container labels stay honest.
__version__ = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
