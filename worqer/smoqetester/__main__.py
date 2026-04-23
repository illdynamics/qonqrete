# worqer/smoqetester/__main__.py
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .runner import run_smoketest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic smoketest adapters.")
    parser.add_argument("qodeyard_path", nargs="?", default="qodeyard")
    parser.add_argument("--cycle", default="1")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = parser.parse_args(argv)

    qodeyard_path = Path(args.qodeyard_path)
    config: dict = {}
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}

    report = run_smoketest(
        qodeyard_path,
        str(args.cycle),
        config,
        changed_files=args.changed_file or None,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_markdown())

    return 0 if report.failed == 0 and report.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
