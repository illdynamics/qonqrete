#!/usr/bin/env python3
"""CLI entrypoint for QonQrete swarm orchestration.

Usage:
    python3 worqer/orchestrate_cli.py --task TASK_FILE [options]

Options:
    --task PATH            Task file to plan and build
    --parallel             Enable parallel execution (default: true)
    --serial               Disable parallel execution
    --max-workers N        Max parallel workers (default: 4)
    --max-iterations N     Max self-review iterations (default: 3)
    --strictness MODE      Validator strictness: normal|strict|relaxed
    --dry-run              Planning mode without execution
    --json                 Output results as JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure worqer is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codeseeq_orchestrator import (
    OrchestratorConfig,
    OrchestratorRunResult,
    orchestrate,
)
from construqtor_briq_worker import default_build_fn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QonQrete swarm orchestration CLI",
    )
    parser.add_argument("--task", type=str, required=True,
                        help="Path to task file")
    parser.add_argument("--parallel", action="store_true", dest="parallel", default=None,
                        help="Enable parallel execution")
    parser.add_argument("--serial", action="store_false", dest="parallel",
                        help="Disable parallel execution")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="Max parallel workers (default: 4)")
    parser.add_argument("--max-iterations", type=int, default=3,
                        help="Max self-review iterations (default: 3)")
    parser.add_argument("--strictness", type=str, default="normal",
                        choices=["normal", "strict", "relaxed"],
                        help="Validator strictness (default: normal)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Planning mode without execution")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    task_path = Path(args.task).resolve()
    if not task_path.exists():
        print(f"[ERROR] Task file not found: {task_path}", file=sys.stderr)
        return 1

    # Build config from CLI args, with env fallback
    config = OrchestratorConfig.from_env()

    # CLI overrides
    if args.parallel is not None:
        config.parallel_enabled = args.parallel
    config.max_workers = args.max_workers
    config.max_self_review_iterations = args.max_iterations
    config.validator_strictness = args.strictness
    config.dry_run = args.dry_run
    config.task_path = str(task_path)

    print(f"[ORCHESTRATOR] Task: {task_path.name}")
    print(f"[ORCHESTRATOR] Parallel: {config.parallel_enabled}, "
          f"Max workers: {config.max_workers}, "
          f"Max iterations: {config.max_self_review_iterations}")
    print(f"[ORCHESTRATOR] Strictness: {config.validator_strictness}")
    if config.dry_run:
        print("[ORCHESTRATOR] DRY RUN MODE")

    result = orchestrate(task_path, default_build_fn, config)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n[{chr(10003) if result.overall_status == 'PASS' else chr(10007)}] "
              f"Overall: {result.overall_status}")
        print(f"  Planner: {result.planner_status}")
        print(f"  Workers: {len(result.worker_results)}")
        print(f"  Sqrewdriver: {result.sqrewdriver_result.status if result.sqrewdriver_result else 'N/A'}")
        print(f"  Inspeqtor: {result.inspeqtor_result.status if result.inspeqtor_result else 'N/A'}")

        if result.parallel_groups:
            print(f"  Parallel batches: {len(result.parallel_groups)}")
            for batch in result.parallel_groups:
                print(f"    - {', '.join(batch)}")
        if result.serial_groups:
            print(f"  Serial groups: {len(result.serial_groups)}")

        if result.validation_errors:
            print(f"  Warnings/Errors ({len(result.validation_errors)}):")
            for err in result.validation_errors[:5]:
                print(f"    - {err}")
            if len(result.validation_errors) > 5:
                print(f"    ... and {len(result.validation_errors) - 5} more")

    return 0 if result.overall_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
