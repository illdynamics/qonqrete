#!/usr/bin/env python3
# worqer/lib_sandbox_diff.py
"""Helper to detect changes in a sandbox compared to a baseline."""

import os
import hashlib
from pathlib import Path

def sha256_file(path: Path) -> str:
    """Calculate SHA256 of a file."""
    if not path.exists():
        return ""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def detect_sandbox_changes(sandbox_path: Path, baseline_path: Path) -> dict[str, str]:
    """
    Compare sandbox with baseline and return a map of {rel_path: content}.
    Only includes files that are new or changed in the sandbox.
    """
    changes = {}
    sandbox_path = sandbox_path.resolve()
    baseline_path = baseline_path.resolve()

    for root, dirs, files in os.walk(sandbox_path):
        dirs.sort()
        files.sort()
        for file in files:
            sandbox_file = Path(root) / file
            rel_path = sandbox_file.relative_to(sandbox_path)
            baseline_file = baseline_path / rel_path

            # Skip common infra dirs if they leaked into sandbox
            if any(part in {".qonqrete", "build", "attempts", "validation-root"} for part in rel_path.parts):
                continue

            if not baseline_file.exists():
                # New file
                try:
                    changes[str(rel_path)] = sandbox_file.read_text(encoding='utf-8')
                except Exception:
                    pass
            else:
                # Compare hashes
                if sha256_file(sandbox_file) != sha256_file(baseline_file):
                    try:
                        changes[str(rel_path)] = sandbox_file.read_text(encoding='utf-8')
                    except Exception:
                        pass
    
    # Check for deletions (optional: ConstruQtor currently focuses on creation/update)
    # We won't handle deletions for now to stay consistent with staged_atomic_per_attempt logic
    # which usually appends/updates.

    return changes
