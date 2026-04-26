# worqer/qualifier/__main__.py
# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point.
#
# Usage:
#   python -m qualifier <qodeyard_path> [qontext_path] [output_path]
#
# Preserves the invocation contract of the v1.3.0 monolith so any
# shell wrapper or CI job that shelled out to `qualifier.py` directly
# will continue to work by switching to `python -m qualifier`.
# ═══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from .runner import run_verification


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else ([sys.argv[0]] + list(argv)))
    if len(argv) < 2:
        print(
            "Usage: python -m qualifier <qodeyard_path> "
            "[qontext_path] [output_path]",
            flush=True,
        )
        return 1

    qodeyard_path = Path(argv[1])
    qontext_path = Path(argv[2]) if len(argv) > 2 else (
        qodeyard_path.parent / "qontext.d"
    )
    output_path = Path(argv[3]) if len(argv) > 3 else None
    cycle_num = os.environ.get("CYCLE_NUM", "1")

    # Best-effort config load — missing config is non-fatal.
    config: dict = {}
    config_path = qodeyard_path.parent / "config.yaml"
    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
    except Exception as exc:
        print(f"[Qualifier] Could not read {config_path}: {exc}", flush=True)

    report = run_verification(qodeyard_path, qontext_path, cycle_num, config)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())
        print(f"[Qualifier] Report written to {output_path}", flush=True)
    else:
        print(report.to_markdown())

    return 0 if report.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
