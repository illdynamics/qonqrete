#!/usr/bin/env python3
"""Medium-task benchmark harness for validation infrastructure.

Runs deterministic + browser validation across benchmark fixtures
and produces structured results. Usage:

    python3 tools/benchmark_runner.py [--fixture recipe_planner/good]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from qualifier.adapters.html_css import _run_fallback_html_check, _run_fallback_css_check
try:
    from qualifier.adapters.js_ts import _run_fallback_js_check
except ImportError:
    _run_fallback_js_check = None
from smoqetester.acceptance_contract import make_recipe_planner_contract, write_contract
from smoqetester.verdict import (
    resolve_verdict,
    SUCCESS_VERIFIED,
    SUCCESS_LOW_COVERAGE,
    PARTIAL_VALIDATION_DEGRADED,
    FAILED_BLOCKING_VALIDATION,
    FAILED_BROWSER_E2E,
    FAILED_ACCEPTANCE_CONTRACT,
)


BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"


def run_deterministic_checks(qodeyard: Path) -> dict[str, Any]:
    """Run HTML/CSS/JS deterministic validation."""
    html_errors = 0
    css_errors = 0
    js_errors = 0
    html_checked = 0
    css_checked = 0
    js_checked = 0
    results: list[dict] = []

    for f in sorted(qodeyard.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = str(f.relative_to(qodeyard))
        if f.suffix in (".html", ".htm"):
            r = _run_fallback_html_check(f, rel)
            html_checked += 1
        elif f.suffix == ".css":
            r = _run_fallback_css_check(f, rel)
            css_checked += 1
        elif f.suffix in (".js", ".mjs") and _run_fallback_js_check is not None:
            r = _run_fallback_js_check(f, rel)
            js_checked += 1
        else:
            continue
        for item in r:
            results.append({
                "file": item.file_path,
                "check": item.check_type,
                "passed": item.passed,
                "severity": item.severity,
                "message": item.message,
                "line": item.line_number,
            })
            if not item.passed and item.severity == "error":
                if f.suffix in (".html", ".htm"):
                    html_errors += 1
                elif f.suffix == ".css":
                    css_errors += 1
                elif f.suffix in (".js", ".mjs"):
                    js_errors += 1

    return {
        "html_checked": html_checked,
        "css_checked": css_checked,
        "js_checked": js_checked,
        "html_errors": html_errors,
        "css_errors": css_errors,
        "js_errors": js_errors,
        "total_errors": html_errors + css_errors + js_errors,
        "total_warnings": sum(1 for r in results if not r["passed"] and r["severity"] == "warning"),
        "results": results,
    }


def detect_browser_available() -> bool:
    """Check if Playwright/node is available."""
    import shutil
    return shutil.which("playwright") is not None or shutil.which("npx") is not None


def run_benchmark(fixture_path: Path, browser_required: bool = True) -> dict[str, Any]:
    """Run validation on a single benchmark fixture."""
    name = str(fixture_path.relative_to(BENCHMARKS_DIR))
    start = time.monotonic()

    # Deterministic checks
    det = run_deterministic_checks(fixture_path)

    # Browser availability
    browser_avail = detect_browser_available()

    # Acceptance contract
    contract_path = fixture_path / "acceptance-contract.json"
    contract_present = contract_path.exists()
    if not contract_present:
        contract = make_recipe_planner_contract()
        write_contract(contract, contract_path)
        contract_present = True

    # Browser smoke (skipped if playwright not available)
    browser_ran = False
    browser_failures = 0
    browser_result = None
    if browser_avail and browser_required:
        try:
            from smoqetester.adapters.playwright_browser import (
                _load_acceptance_contract,
                _run_playwright_test,
            )
            from smoqetester.base import SmoketestContext
            contract = _load_acceptance_contract(contract_path)
            ctx = SmoketestContext(
                qodeyard_path=fixture_path,
                cycle_num="bench",
                timeout_seconds=30,
            )
            result = _run_playwright_test(fixture_path, contract, ctx)
            browser_ran = True
            if result.status in ("FAIL", "ERROR"):
                browser_failures = 1
            browser_result = result.to_dict()
        except Exception as exc:
            browser_result = {"error": str(exc)}

    # Resolve verdict
    verdict = resolve_verdict(
        qualifier_errors=det["total_errors"],
        qualifier_warnings=0,
        html_checked=det["html_checked"],
        css_checked=det["css_checked"],
        js_checked=det["js_checked"],
        browser_required=browser_required,
        browser_available=browser_avail,
        browser_ran=browser_ran,
        browser_failures=browser_failures,
        contract_present=contract_present,
    )

    elapsed = time.monotonic() - start

    return {
        "fixture": name,
        "type": "frontend",
        "elapsed_sec": round(elapsed, 3),
        "verdict": verdict.to_dict(),
        "deterministic": {
            "html_checked": det["html_checked"],
            "css_checked": det["css_checked"],
            "js_checked": det["js_checked"],
            "total_errors": det["total_errors"],
        },
        "browser": {
            "available": browser_avail,
            "ran": browser_ran,
            "failures": browser_failures,
            "result": browser_result,
        },
        "acceptance_contract_present": contract_present,
    }


def run_all_benchmarks() -> list[dict[str, Any]]:
    """Run all benchmark fixtures."""
    results = []
    for fixture in sorted(BENCHMARKS_DIR.rglob("*")):
        if not fixture.is_dir():
            continue
        # Skip dirs that don't have index.html
        if not (fixture / "index.html").exists():
            continue
        result = run_benchmark(fixture)
        results.append(result)
    return results


def print_summary(results: list[dict[str, Any]]) -> None:
    """Print human-readable benchmark summary."""
    print("\n" + "=" * 70)
    print("  BENCHMARK RESULTS")
    print("=" * 70)
    for r in results:
        v = r["verdict"]
        status = v["status"]
        d = r["deterministic"]
        b = r["browser"]
        icon = "✅" if status == SUCCESS_VERIFIED else ("⚠️" if status == SUCCESS_LOW_COVERAGE else "❌")
        print(f"\n  {icon} {r['fixture']}")
        print(f"     Verdict: {status}")
        print(f"     HTML/CSS/JS: {d['html_checked']}/{d['css_checked']}/{d['js_checked']} files, {d['total_errors']} errors")
        if b["ran"]:
            print(f"     Browser: ran, {b['failures']} failures")
        elif b["available"]:
            print(f"     Browser: available but not run")
        else:
            print(f"     Browser: not available")
        print(f"     Elapsed: {r['elapsed_sec']}s")
        if v.get("reasons"):
            for reason in v["reasons"]:
                print(f"     → {reason}")
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["verdict"]["status"] == SUCCESS_VERIFIED)
    print(f"  {passed}/{len(results)} fixtures achieved SUCCESS_VERIFIED")
    print("=" * 70)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Benchmark runner")
    p.add_argument("--fixture", help="Run a specific fixture path (relative to benchmarks/)")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args()

    if args.fixture:
        fixture_path = BENCHMARKS_DIR / args.fixture
        if not fixture_path.exists():
            print(f"Fixture not found: {fixture_path}", file=sys.stderr)
            sys.exit(1)
        results = [run_benchmark(fixture_path)]
    else:
        results = run_all_benchmarks()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_summary(results)
