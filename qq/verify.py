"""
Qq verification runner — Python-based acceptance check orchestration.

Replaces the fragile shell-based timeout/process-control in
scripts/verify.sh with Python subprocess management via qq.process.

Usage:
    python3 -m qq.verify                   # run all checks (fail-fast)
    python3 -m qq verify                   # same, via CLI
    python3 -m qq.verify --help            # show options
    python3 -m qq.verify --continue-on-failure  # run all checks, don't stop on first failure

The verifier runs these checks in order:
  1. compileall
  2. unittest discover
  3. pytest
  4. providers --json
  5. doctor --offline
  6. dry-run
  7. streaming dry-run
  8. package --check
  9. package --final
 10. package --check-archive
 11. package --check-uploaded-zip
 12. orphan-process audit

By default, verification FAILS FAST: if a required step fails, the verifier
prints the failure, prints a summary, and exits non-zero immediately. Use
--continue-on-failure to keep running after a failed required step.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import textwrap

from .process import run_subprocess, orphan_audit

# Project root is one level above qq/
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def get_version() -> str:
    from qq import __version__
    return __version__


def get_archive_name() -> str:
    return f"dist/qonqrete-qq-v{get_version()}.zip"


# ---------------------------------------------------------------------------
# Individual check steps
# ---------------------------------------------------------------------------

CHECK_STEPS = [
    ("compileall",         180, ["python3", "-m", "compileall", "-q", "qq", "tests"]),
    ("unittest discover",  600, ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ("pytest",             180, ["python3", "-m", "pytest", "-q", "-s"]),
    ("providers --json",    30, ["python3", "-m", "qq", "providers", "--json"]),
    ("doctor --offline",    30, ["python3", "-m", "qq", "doctor", "--offline"]),
]


def _build_dry_run_step() -> tuple:
    """Build the dry-run step with a temp dir."""
    return (
        "dry-run", 90,
        ["python3", "-m", "qq", "run", "examples/example_task.md",
         "${TMPDIR_DRY}",
         "--dry-run", "--max-cycles", "10"],
    )


def _build_streaming_step() -> tuple:
    """Build the streaming dry-run step with a temp dir."""
    return (
        "streaming dry-run", 90,
        ["python3", "-m", "qq", "run", "examples/example_task.md",
         "${TMPDIR_STREAM}",
         "--dry-run", "--max-cycles", "10", "--stream-agent-output"],
    )


def _build_package_check_step() -> tuple:
    return ("package --check", 60, ["python3", "-m", "qq", "package", "--check"])


def _build_package_final_step() -> tuple:
    archive = get_archive_name()
    return ("package --final", 120, ["python3", "-m", "qq", "package", "--final"])


def _build_check_archive_step() -> tuple:
    archive = get_archive_name()
    return ("package --check-archive", 30, ["python3", "-m", "qq", "package", "--check-archive", archive])


def _build_check_uploaded_zip_step() -> tuple:
    archive = get_archive_name()
    return ("package --check-uploaded-zip", 30, ["python3", "-m", "qq", "package", "--check-uploaded-zip", archive])


_PACKAGE_DEPENDENT_STEPS = [
    _build_package_check_step,
    _build_package_final_step,
    _build_check_archive_step,
    _build_check_uploaded_zip_step,
]


def _resolve_tempdir(cmd: list, tmp_dir: str) -> list:
    """Replace ${TMPDIR_DRY} / ${TMPDIR_STREAM} placeholders."""
    return [
        arg.replace("${TMPDIR_DRY}", tmp_dir).replace("${TMPDIR_STREAM}", tmp_dir)
        for arg in cmd
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_verification(
    root: str = None,
    timeout_scale: float = 1.0,
    skip_pytest: bool = False,
    skip_package_steps: bool = False,
    print_label: str = "",
    continue_on_failure: bool = False,
) -> int:
    """Run all acceptance checks and return exit code (0 = all pass).

    Args:
        root: Project root directory (default: auto-detect).
        timeout_scale: Multiplier for all timeouts (1.0 = default).
        skip_pytest: Skip pytest if it's not installed.
        skip_package_steps: Skip package build/check steps (dev-tree mode).
        print_label: Optional label for the banner (e.g., "Source Tree").
        continue_on_failure: If True, keep running after a required step fails.
    """
    if root is None:
        root = _PROJECT_ROOT

    os.chdir(root)
    version = get_version()

    banner = f"Qq v{version} Verification"
    if print_label:
        banner += f" — {print_label}"
    print("=" * 56, flush=True)
    print(banner, flush=True)
    print("=" * 56, flush=True)
    if continue_on_failure:
        print("(continue-on-failure mode)", flush=True)
    print(flush=True)

    passed = 0
    failed = 0
    skipped = 0

    # Build the full step list
    steps = list(CHECK_STEPS)

    # Add dry-run and streaming dry-run (need temp dirs)
    tmp_dry = tempfile.mkdtemp(prefix="qq_verify_dry_")
    tmp_stream = tempfile.mkdtemp(prefix="qq_verify_stream_")
    try:
        dry_label, dry_timeout, dry_cmd = _build_dry_run_step()
        steps.append((dry_label, dry_timeout, _resolve_tempdir(dry_cmd, tmp_dry)))

        str_label, str_timeout, str_cmd = _build_streaming_step()
        steps.append((str_label, str_timeout, _resolve_tempdir(str_cmd, tmp_stream)))
    except Exception:
        # cleanup temps if step building failed
        import shutil
        shutil.rmtree(tmp_dry, ignore_errors=True)
        shutil.rmtree(tmp_stream, ignore_errors=True)
        raise

    # Add package-dependent steps
    if skip_package_steps:
        print("--- package steps ---", flush=True)
        print("SKIP: package steps skipped (dev tree mode)", flush=True)
        print(flush=True)
        skipped += 4  # check, final, check-archive, check-uploaded-zip
    else:
        for builder in _PACKAGE_DEPENDENT_STEPS:
            label, timeout, cmd = builder()
            steps.append((label, timeout, cmd))

    # Run each step
    for label, timeout, cmd in steps:
        effective_timeout = max(5, int(timeout * timeout_scale))

        # Handle pytest skip
        if label == "pytest" and skip_pytest:
            print(f"--- {label} ---", flush=True)
            print("SKIP: pytest not available", flush=True)
            skipped += 1
            print()
            continue

        print(f"--- {label} (timeout={effective_timeout}s) ---", flush=True)
        try:
            result = run_subprocess(cmd, cwd=root, timeout=effective_timeout, label=label)
            if result.returncode == 0:
                print(f"PASS: {label}", flush=True)
                passed += 1
            else:
                print(f"FAIL: {label} (exit code {result.returncode})", flush=True)
                failed += 1
                if not continue_on_failure:
                    _fail_fast_exit(passed, failed, skipped)
        except RuntimeError as e:
            print(f"FAIL: {label} — {e}", flush=True)
            failed += 1
            if not continue_on_failure:
                _fail_fast_exit(passed, failed, skipped)
        print(flush=True)

    # Clean up temp dirs
    import shutil
    shutil.rmtree(tmp_dry, ignore_errors=True)
    shutil.rmtree(tmp_stream, ignore_errors=True)

    # Orphan-process audit
    print("--- orphan-process audit ---", flush=True)
    orphans = orphan_audit()
    if orphans:
        print("FAIL: orphan Qq test processes detected", flush=True)
        for line in orphans:
            print(f"  {line}", flush=True)
        failed += 1
    else:
        print("PASS: orphan-process audit (clean)", flush=True)
        passed += 1
    print()

    # Summary
    _print_summary(passed, failed, skipped)
    if failed > 0:
        return 1
    return 0


def _fail_fast_exit(passed: int, failed: int, skipped: int) -> None:
    """Print summary and exit non-zero immediately."""
    print(flush=True)
    _print_summary(passed, failed, skipped)
    print("FAIL-FAST: stopping after first failure. Use --continue-on-failure to run all checks.", flush=True)
    sys.exit(1)


def _print_summary(passed: int, failed: int, skipped: int) -> None:
    """Print the results summary line."""
    total = passed + failed + skipped
    print("=" * 56, flush=True)
    summary = f"RESULTS: {passed} passed, {failed} failed"
    if skipped:
        summary += f", {skipped} skipped"
    print(summary, flush=True)
    print("=" * 56, flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qq-verify",
        description="Run all Qq acceptance checks (Python-based, no shell timeout fragility)",
    )
    parser.add_argument("--root", default=None, help="Project root directory")
    parser.add_argument("--timeout-scale", type=float, default=1.0,
                        help="Multiplier for all timeouts")
    parser.add_argument("--skip-pytest", action="store_true",
                        help="Skip pytest if not installed")
    parser.add_argument("--skip-package-steps", action="store_true",
                        help="Skip package build/check steps (dev tree)")
    parser.add_argument("--label", default="", help="Banner label")
    parser.add_argument("--continue-on-failure", action="store_true",
                        help="Keep running after a required step fails")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Check for dev tree
    skip_pkg = args.skip_package_steps
    if not skip_pkg:
        root = args.root or _PROJECT_ROOT
        if os.path.isdir(os.path.join(root, ".codeseeq")):
            skip_pkg = True

    return run_verification(
        root=args.root,
        timeout_scale=args.timeout_scale,
        skip_pytest=args.skip_pytest,
        skip_package_steps=skip_pkg,
        print_label=args.label,
        continue_on_failure=args.continue_on_failure,
    )


if __name__ == "__main__":
    sys.exit(main())
