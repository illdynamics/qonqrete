#!/usr/bin/env python3
# worqer/runtime_checks.py
# ═══════════════════════════════════════════════════════════════════════════════
# Runtime Checks — Fail-Fast Contract Dependency Enforcement
# v1.0.4-stable
# ═══════════════════════════════════════════════════════════════════════════════
#
# Shared helper for ensuring mandatory pipeline prerequisites exist.
# Called by ConstruQtor and InspeQtor at startup.
# ═══════════════════════════════════════════════════════════════════════════════
from pathlib import Path


def ensure_qontract_present(worqspace_root: Path) -> tuple:
    """
    Assert both qontract.md and qontract.json exist in qontract.d/.

    Returns:
        (md_path, json_path) if both exist

    Raises:
        RuntimeError with clear actionable message if either is missing.
    """
    qontract_dir = Path(worqspace_root) / "qontract.d"
    md_path = qontract_dir / "qontract.md"
    json_path = qontract_dir / "qontract.json"

    missing = []
    if not md_path.exists():
        missing.append(str(md_path))
    if not json_path.exists():
        missing.append(str(json_path))

    if missing:
        raise RuntimeError(
            f"FAIL-FAST: Contract files missing — pipeline cannot proceed.\n"
            f"  Missing: {', '.join(missing)}\n"
            f"  Expected location: {qontract_dir}/\n"
            f"  Action: Ensure cycle 1 InstruQtor has run and generated the contract.\n"
            f"  The QONTRACT is mandatory for all cycles > 1."
        )

    return (md_path, json_path)
