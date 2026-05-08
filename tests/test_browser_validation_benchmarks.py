"""Tests for browser validation layer, verdict semantics, and benchmark fixtures."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from smoqetester.verdict import (
    SUCCESS_VERIFIED,
    SUCCESS_LOW_COVERAGE,
    PARTIAL_VALIDATION_DEGRADED,
    FAILED_VALIDATION_INFRA,
    FAILED_BLOCKING_VALIDATION,
    FAILED_BROWSER_E2E,
    FAILED_ACCEPTANCE_CONTRACT,
    ValidationVerdict,
    resolve_verdict,
)
from smoqetester.acceptance_contract import (
    extract_contract_from_task_spec,
    make_recipe_planner_contract,
    write_contract,
)


class VerdictSemanticsTests(unittest.TestCase):
    def test_clean_deterministic_no_browser_required(self):
        v = resolve_verdict(
            qualifier_errors=0, qualifier_warnings=0,
            browser_required=False, browser_available=False, browser_ran=False,
            html_checked=1, css_checked=1, js_checked=1,
        )
        self.assertEqual(v.status, SUCCESS_VERIFIED)

    def test_blocking_deterministic_errors_fail(self):
        v = resolve_verdict(
            qualifier_errors=3, qualifier_warnings=0,
            browser_required=False, browser_available=False, browser_ran=False,
        )
        self.assertEqual(v.status, FAILED_BLOCKING_VALIDATION)

    def test_browser_required_but_unavailable(self):
        v = resolve_verdict(
            qualifier_errors=0, qualifier_warnings=0,
            browser_required=True, browser_available=False, browser_ran=False,
            contract_present=True,
        )
        self.assertEqual(v.status, PARTIAL_VALIDATION_DEGRADED)

    def test_browser_required_and_failed(self):
        v = resolve_verdict(
            qualifier_errors=0, qualifier_warnings=0,
            browser_required=True, browser_available=True, browser_ran=True,
            browser_failures=2, contract_present=True,
        )
        self.assertEqual(v.status, FAILED_BROWSER_E2E)

    def test_browser_required_and_passed_gives_verified(self):
        v = resolve_verdict(
            qualifier_errors=0, qualifier_warnings=0,
            browser_required=True, browser_available=True, browser_ran=True,
            browser_failures=0, html_checked=1, css_checked=1, js_checked=1,
            contract_present=True,
        )
        self.assertEqual(v.status, SUCCESS_VERIFIED)

    def test_warnings_only_gives_low_coverage(self):
        v = resolve_verdict(
            qualifier_errors=0, qualifier_warnings=3,
            browser_required=False, browser_available=False, browser_ran=False,
            html_checked=1,
        )
        self.assertEqual(v.status, SUCCESS_LOW_COVERAGE)

    def test_browser_required_no_contract_fails(self):
        v = resolve_verdict(
            qualifier_errors=0, qualifier_warnings=0,
            browser_required=True, browser_available=True, browser_ran=False,
            contract_present=False,
        )
        self.assertEqual(v.status, FAILED_ACCEPTANCE_CONTRACT)

    def test_false_success_never_downgraded_to_success(self):
        """Broken frontend with errors must NOT receive SUCCESS_VERIFIED or SUCCESS_LOW_COVERAGE."""
        v = resolve_verdict(
            qualifier_errors=5, qualifier_warnings=2,
            browser_required=True, browser_available=True, browser_ran=True,
            browser_failures=0,
        )
        self.assertTrue(v.is_failure)
        self.assertFalse(v.is_success)

    def test_verdict_to_dict(self):
        v = resolve_verdict(qualifier_errors=0, html_checked=1)
        d = v.to_dict()
        self.assertEqual(d["status"], SUCCESS_VERIFIED)
        self.assertIn("reasons", d)


class AcceptanceContractTests(unittest.TestCase):
    def test_extract_contract_from_task_spec(self):
        spec = {
            "index_file": "index.html",
            "required_files": ["index.html", "app.js", "style.css"],
            "required_selectors": ["#app", ".header"],
            "localStorage_keys": ["my_app_data"],
            "no_external_network": True,
            "check_reload_persistence": True,
            "forbidden_texts": ["TODO", "FIXME"],
            "user_flows": [{"name": "login", "steps": [{"action": "click", "selector": "#login"}]}],
        }
        contract = extract_contract_from_task_spec(spec)
        self.assertEqual(contract["index_file"], "index.html")
        self.assertEqual(contract["required_files"], ["app.js", "index.html", "style.css"])
        self.assertEqual(contract["required_selectors"], ["#app", ".header"])
        self.assertEqual(contract["localStorage_keys"], ["my_app_data"])
        self.assertTrue(contract["no_external_network"])
        self.assertTrue(contract["check_reload_persistence"])

    def test_recipe_planner_contract_is_complete(self):
        contract = make_recipe_planner_contract()
        self.assertIn("index.html", contract["required_files"])
        self.assertIn("qonqrete_recipes", contract["localStorage_keys"])
        self.assertTrue(contract["no_external_network"])
        self.assertTrue(contract["check_reload_persistence"])
        self.assertGreater(len(contract["required_selectors"]), 3)
        self.assertGreater(len(contract["user_flows"]), 2)

    def test_write_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acceptance-contract.json"
            contract = make_recipe_planner_contract()
            write_contract(contract, path)
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["localStorage_keys"], ["qonqrete_recipes"])


class BenchmarkFixtureTests(unittest.TestCase):
    def setUp(self):
        self.bench_dir = PROJECT_ROOT / "benchmarks"

    def test_good_recipe_planner_fixture_exists(self):
        good = self.bench_dir / "recipe_planner" / "good"
        self.assertTrue((good / "index.html").exists())
        self.assertTrue((good / "styles.css").exists())
        self.assertTrue((good / "script.js").exists())

    def test_all_bad_fixtures_exist(self):
        bad_names = [
            "bad_no_persistence", "bad_broken_favorite", "bad_missing_weekly",
            "bad_external_asset", "bad_wrong_key", "bad_js_error",
        ]
        for name in bad_names:
            fixture = self.bench_dir / "recipe_planner" / name
            self.assertTrue((fixture / "index.html").exists(), f"{name} missing index.html")
            self.assertTrue((fixture / "script.js").exists(), f"{name} missing script.js")

    def test_deterministic_validation_catches_blocking_errors(self):
        """Good recipe should pass; bad fixtures should have errors."""
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        from benchmark_runner import run_deterministic_checks

        # Good fixture should have zero blocking errors (warnings OK)
        good = self.bench_dir / "recipe_planner" / "good"
        det = run_deterministic_checks(good)
        self.assertEqual(det["total_errors"], 0, f"Good fixture has blocking errors: {[r for r in det['results'] if r['severity'] == 'error']}")

        # Bad external asset fixture should have errors
        bad = self.bench_dir / "recipe_planner" / "bad_external_asset"
        det = run_deterministic_checks(bad)
        self.assertGreater(det["total_errors"], 0, "External asset fixture should have blocking errors")

    def test_verdict_for_bad_fixture_is_not_success(self):
        """A broken fixture must not produce SUCCESS_VERIFIED."""
        v = resolve_verdict(
            qualifier_errors=1,  # has at least one blocking error
            browser_required=True, browser_available=True, browser_ran=True, browser_failures=0,
        )
        self.assertNotEqual(v.status, SUCCESS_VERIFIED)


if __name__ == "__main__":
    unittest.main()
