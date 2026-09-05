"""
Canonical agent receipt paths — one source of truth for where every agent
writes its JSON output.

New runs: receipts go under <run_root>/agents/cycle-XXX/<role>/
Old runs: legacy fallback reads for target-path and artifacts/agent-outputs/
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Canonical role slugs used in directory / filename construction
_CANONICAL_SLUGS = {
    "qlarifier": "qlarifier",
    "clarifier": "qlarifier",
    "instruqtor": "instruqtor",
    "instructor": "instruqtor",
    "construqtor": "construqtor",
    "constructor": "construqtor",
    "inspeqtor": "inspeqtor",
    "inspector": "inspeqtor",
}

# Canonical receipt filenames per role
_RECEIPT_FILENAMES = {
    "qlarifier": "qlarifier_output.json",
    "instruqtor": "instruqtor_output.json",
    "construqtor": "construqtor_output.json",
    "inspeqtor": "inspeqtor_output.json",
}

# Legacy receipt filenames for fallback reads
_LEGACY_FILENAMES = {
    "qlarifier": ["clarifier_output.json", "qlarifier_output.json"],
    "instruqtor": ["instructor_output.json", "instruqtor_output.json"],
    "construqtor": ["construqtor_output.json"],
    "inspeqtor": ["inspeqtor_output.json"],
}

# All QonQrete metadata filenames that must never live in target path
_ALL_METADATA_NAMES = frozenset({
    "qlarifier_output.json",
    "clarifier_output.json",
    "instruqtor_output.json",
    "instructor_output.json",
    "construqtor_output.json",
    "inspeqtor_output.json",
    "agent_output.json",
    "review_output.json",
    "briq_output.json",
})


def canonical_role_slug(role: str) -> str:
    """Normalize a role string to its canonical slug."""
    r = role.lower().strip()
    return _CANONICAL_SLUGS.get(r, r)


def receipt_filename(role: str) -> str:
    """Return the canonical receipt filename for a role."""
    slug = canonical_role_slug(role)
    return _RECEIPT_FILENAMES.get(slug, f"{slug}_output.json")


def legacy_filenames(role: str) -> list:
    """Return legacy filenames for fallback reads."""
    slug = canonical_role_slug(role)
    return _LEGACY_FILENAMES.get(slug, [])


def cycle_dir(run_root: str, cycle: int) -> Path:
    """Return the canonical cycle directory under run_root."""
    return Path(run_root) / "agents" / f"cycle-{cycle:03d}"


def agent_receipt_path(run_root: str, cycle: int, role: str) -> Path:
    """Return the absolute canonical receipt path for an agent.

    Example: <run_root>/agents/cycle-000/qlarifier/qlarifier_output.json
    """
    slug = canonical_role_slug(role)
    fname = _RECEIPT_FILENAMES.get(slug, f"{slug}_output.json")
    return cycle_dir(run_root, cycle) / slug / fname


def agent_artifact_dir(run_root: str, cycle: int, role: str,
                       call_id: str) -> Path:
    """Return the artifact directory for a specific agent call."""
    slug = canonical_role_slug(role)
    return cycle_dir(run_root, cycle) / slug / call_id


def per_call_receipt_path(run_root: str, cycle: int, role: str,
                          build_group_id: str, call_id: str) -> Path:
    """Return the unique per-call receipt path for parallel agents.

    Example: <run_root>/agents/cycle-001/construqtor/receipts/bg-contact__call-abc123.json
    """
    slug = canonical_role_slug(role)
    safe_bg = build_group_id.replace("/", "-").replace("\\", "-")
    safe_call = call_id.replace("/", "-").replace("\\", "-")
    return cycle_dir(run_root, cycle) / slug / "receipts" / f"{safe_bg}__{safe_call}.json"


def aggregate_receipt_path(run_root: str, cycle: int, role: str) -> Path:
    """Return the aggregate receipt path for a role in a cycle.

    Example: <run_root>/agents/cycle-001/construqtor/construqtor_output.json
    """
    return agent_receipt_path(run_root, cycle, role)


def artifacts_dir(run_root: str) -> Path:
    """Return the artifacts directory under run_root."""
    return Path(run_root) / "artifacts"


def task_original_path(run_root: str) -> Path:
    """Path for the original user task markdown artifact."""
    return artifacts_dir(run_root) / "task-original.md"


def task_enhanced_path(run_root: str) -> Path:
    """Path for the enhanced/qlarified task markdown artifact."""
    return artifacts_dir(run_root) / "task-enhanced.md"


def planning_path(run_root: str) -> Path:
    """Path for the full instruQtor planning markdown artifact."""
    return artifacts_dir(run_root) / "planning.md"


def state_dir(run_root: str) -> Path:
    """Return the state directory under run_root."""
    return Path(run_root) / "state"


def is_metadata_filename(fname: str) -> bool:
    """Return True if fname is a known QonQrete metadata receipt name."""
    return fname in _ALL_METADATA_NAMES or _is_metadata_pattern(fname)


def _is_metadata_pattern(fname: str) -> bool:
    """Check for metadata patterns like inspeqtor_output_bg-*.json."""
    base = os.path.splitext(fname)[0]
    return base.startswith("inspeqtor_output_") or base.startswith("inspeqtor_output")


def find_legacy_receipt(run_root: str, role: str,
                        cycle: int = 0) -> Optional[Path]:
    """Try to find a legacy receipt for fallback reads.

    Search order:
      1. Canonical path (new)
      2. Under artifacts/agent-outputs/ (legacy run_root area)
      3. Not searched: target-path (caller must provide that separately)

    Returns Path if found, None otherwise.
    """
    # 1. Canonical path
    canonical = agent_receipt_path(run_root, cycle, role)
    if canonical.exists():
        return canonical

    # 2. Legacy artifacts/agent-outputs/
    legacy_dir = Path(run_root) / "artifacts" / "agent-outputs"
    if legacy_dir.is_dir():
        for fname in legacy_filenames(role):
            candidate = legacy_dir / fname
            if candidate.exists():
                return candidate

    return None


def write_aggregate_receipt(filepath: Path, receipts: list,
                            role: str, cycle: int) -> None:
    """Write (or append-merge) receipts into an aggregate file.

    Uses file locking to prevent race conditions from parallel writers.
    """
    import json
    import fcntl
    import time

    filepath.parent.mkdir(parents=True, exist_ok=True)

    aggregate = {
        "role": canonical_role_slug(role),
        "cycle": cycle,
        "receipts": receipts,
    }

    if not filepath.exists():
        # Fresh write — still use lock for safety
        with open(filepath, "w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                json.dump(aggregate, fh, indent=2)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return

    # Read-modify-write with lock
    with open(filepath, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            try:
                existing = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                existing = {"role": canonical_role_slug(role), "cycle": cycle, "receipts": []}

            existing_receipts = existing.get("receipts", [])
            if not isinstance(existing_receipts, list):
                existing_receipts = []

            existing_receipts.extend(receipts)
            existing["receipts"] = existing_receipts
            existing["role"] = canonical_role_slug(role)
            existing["cycle"] = cycle

            fh.seek(0)
            fh.truncate()
            json.dump(existing, fh, indent=2)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def merge_per_call_receipts(run_root: str, cycle: int, role: str,
                            event_log=None) -> list:
    """Merge all per-call receipt files into the aggregate and return receipts.

    Reads all files under <run_root>/agents/cycle-XXX/<role>/receipts/*.json,
    merges them into the aggregate file, and returns the list of receipts.
    """
    import json
    slug = canonical_role_slug(role)
    receipts_dir = cycle_dir(run_root, cycle) / slug / "receipts"

    if not receipts_dir.is_dir():
        return []

    receipts = []
    for fpath in sorted(receipts_dir.glob("*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            receipts.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    if receipts:
        aggregate_path = aggregate_receipt_path(run_root, cycle, role)
        write_aggregate_receipt(aggregate_path, receipts, role, cycle)

    return receipts


def ensure_dir(p) -> None:
    """Create directory and parents if they don't exist. Accepts str or Path."""
    Path(p).mkdir(parents=True, exist_ok=True)
