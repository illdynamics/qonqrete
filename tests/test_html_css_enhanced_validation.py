"""Tests for enhanced HTML/CSS fallback validation checks."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

from qualifier.adapters.html_css import (
    _run_fallback_html_check,
    _run_fallback_css_check,
    _check_placeholder_content,
)


class HTMLFallbackEnhancedTests(unittest.TestCase):
    def _check(self, html: str) -> list:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html)
            f.flush()
            path = Path(f.name)
        try:
            return _run_fallback_html_check(path, "test.html")
        finally:
            path.unlink(missing_ok=True)

    def _check_project(self, html: str, assets: dict[str, str] | None = None) -> list:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html_path = root / "index.html"
            html_path.write_text(html, encoding="utf-8")
            for rel, content in (assets or {}).items():
                asset_path = root / rel
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                asset_path.write_text(content, encoding="utf-8")
            return _run_fallback_html_check(html_path, "index.html")

    def test_clean_html_passes(self):
        html = "<!doctype html>\n<html><head></head><body><p>hello</p></body></html>\n"
        results = self._check(html)
        self.assertTrue(any(r.passed for r in results), f"Expected pass: {results}")

    def test_img_with_alt_passes(self):
        html = "<!doctype html>\n<html><head></head><body><img src='pic.png' alt='ok'></body></html>\n"
        results = self._check_project(html, {"pic.png": "fake image bytes"})
        errors = [r for r in results if (not r.passed) and r.severity == "error"]
        self.assertFalse(errors, f"Expected no errors: {[r.message for r in errors]}")

    def test_decorative_empty_alt_passes(self):
        html = "<!doctype html>\n<html><head></head><body><img src='pic.png' alt=''></body></html>\n"
        results = self._check_project(html, {"pic.png": "fake image bytes"})
        errors = [r for r in results if (not r.passed) and r.severity == "error"]
        self.assertFalse(errors, f"Expected no errors: {[r.message for r in errors]}")

    def test_hidden_input_does_not_warn(self):
        html = "<!doctype html>\n<html><head></head><body><input type='hidden' name='csrf'></body></html>\n"
        results = self._check(html)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertFalse(any("label" in r.message.lower() for r in warnings),
                         f"Expected no label warning: {[r.message for r in warnings]}")

    def test_text_input_with_label_passes(self):
        html = "<!doctype html>\n<html><head></head><body><label for='email'>Email</label><input id='email' type='text'></body></html>\n"
        results = self._check(html)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertFalse(any("label" in r.message.lower() for r in warnings),
                         f"Expected no label warning: {[r.message for r in warnings]}")

    def test_text_input_with_aria_label_passes(self):
        html = "<!doctype html>\n<html><head></head><body><input type='text' aria-label='Email'></body></html>\n"
        results = self._check(html)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertFalse(any("label" in r.message.lower() for r in warnings),
                         f"Expected no label warning: {[r.message for r in warnings]}")

    def test_missing_doctype_error(self):
        html = "<html><head></head><body><p>hi</p></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("doctype" in r.message.lower() for r in errors),
                        f"Expected doctype error, got: {[r.message for r in errors]}")

    def test_missing_html_head_body_errors(self):
        html = "<!doctype html>\n<title>oops</title><p>hi</p>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        messages = [r.message.lower() for r in errors]
        self.assertTrue(any("missing <html>" in msg for msg in messages), messages)
        self.assertTrue(any("missing <head>" in msg for msg in messages), messages)
        self.assertTrue(any("missing <body>" in msg for msg in messages), messages)

    def test_duplicate_id_error(self):
        html = "<!doctype html>\n<html><body><div id='x'></div><div id='x'></div></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("duplicate id" in r.message.lower() for r in errors),
                        f"Expected duplicate id error: {[r.message for r in errors]}")

    def test_broken_anchor_error(self):
        html = "<!doctype html>\n<html><body><a href='#missing'>link</a></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("broken anchor" in r.message.lower() for r in errors),
                        f"Expected broken anchor error: {[r.message for r in errors]}")

    def test_img_missing_alt_error(self):
        html = "<!doctype html>\n<html><body><img src='x.png'></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("missing alt" in r.message.lower() for r in errors),
                        f"Expected missing alt error: {[r.message for r in errors]}")

    def test_missing_local_ref_error(self):
        html = "<!doctype html>\n<html><head><script src='nonexistent.js'></script></head><body></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("missing local reference" in r.message.lower() for r in errors),
                        f"Expected missing ref error: {[r.message for r in errors]}")

    def test_external_network_ref_error(self):
        html = "<!doctype html>\n<html><head><script src='https://cdn.example/lib.js'></script></head><body></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("external network" in r.message.lower() for r in errors),
                        f"Expected external ref error: {[r.message for r in errors]}")

    def test_form_missing_label_warning(self):
        html = "<!doctype html>\n<html><body><form><input type='text' name='email'></form></body></html>\n"
        results = self._check(html)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertTrue(any("label" in r.message.lower() for r in warnings),
                        f"Expected label warning: {[r.message for r in warnings]}")

    def test_todo_placeholder_warning(self):
        html = "<!doctype html>\n<html><body><p>TODO: implement this</p></body></html>\n"
        results = self._check(html)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertTrue(any("todo" in r.message.lower() for r in warnings),
                        f"Expected TODO warning: {[r.message for r in warnings]}")

    def test_unclosed_tag_error(self):
        html = "<!doctype html>\n<html><body><div>unclosed</body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("unclosed" in r.message.lower() or "implicitly closing" in r.message.lower() for r in errors),
                        f"Expected unclosed tag error: {[r.message for r in errors]}")

    def test_blocking_errors_not_downgraded(self):
        """Ensure blocking HTML errors are never advisory."""
        html = "<html><body><img src='x.png'><a href='#ghost'>link</a></body></html>\n"
        results = self._check(html)
        errors = [r for r in results if r.severity == "error"]
        self.assertGreater(len(errors), 0, "Must have blocking errors")
        # No pass result should hide the errors
        self.assertFalse(all(r.passed for r in results))


class CSSFallbackEnhancedTests(unittest.TestCase):
    def _check(self, css: str) -> list:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".css", delete=False) as f:
            f.write(css)
            f.flush()
            path = Path(f.name)
        try:
            return _run_fallback_css_check(path, "test.css")
        finally:
            path.unlink(missing_ok=True)

    def test_clean_css_passes(self):
        css = "body { color: black; }\nh1 { font-size: 2em; }\n"
        results = self._check(css)
        self.assertTrue(any(r.passed for r in results),
                        f"Expected pass: {results}")

    def test_empty_stylesheet_error(self):
        results = self._check("")
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("empty" in r.message.lower() for r in errors),
                        f"Expected empty error: {[r.message for r in errors]}")

    def test_unbalanced_braces_error(self):
        css = "body { color: black;\n"
        results = self._check(css)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("unbalanced" in r.message.lower() for r in errors),
                        f"Expected unbalanced error: {[r.message for r in errors]}")

    def test_merge_conflict_error(self):
        css = "body { color: black; }\n<<<<<<< HEAD\nh1 { font-size: 1em; }\n=======\nh1 { font-size: 2em; }\n>>>>>>> branch\n"
        results = self._check(css)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("merge conflict" in r.message.lower() for r in errors),
                        f"Expected merge conflict error: {[r.message for r in errors]}")

    def test_missing_local_asset_error(self):
        css = "body { background: url('nonexistent.png'); }\n"
        results = self._check(css)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("missing local css asset" in r.message.lower() for r in errors),
                        f"Expected missing asset error: {[r.message for r in errors]}")

    def test_remote_import_error(self):
        css = "@import url(https://fonts.example.com/font.css);\nbody { color: black; }\n"
        results = self._check(css)
        errors = [r for r in results if r.severity == "error"]
        self.assertTrue(any("remote @import" in r.message.lower() for r in errors),
                        f"Expected remote import error: {[r.message for r in errors]}")

    def test_duplicate_selector_warning(self):
        css = "body { color: black; }\nbody { font-size: 1em; }\n"
        results = self._check(css)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertTrue(any("duplicate" in r.message.lower() for r in warnings),
                        f"Expected duplicate warning: {[r.message for r in warnings]}")

    def test_todo_placeholder_warning(self):
        css = "/* TODO: add responsive styles */\nbody { color: black; }\n"
        results = self._check(css)
        warnings = [r for r in results if r.severity == "warning"]
        self.assertTrue(any("todo" in r.message.lower() for r in warnings),
                        f"Expected TODO warning: {[r.message for r in warnings]}")

    def test_blocking_errors_not_downgraded(self):
        """Ensure blocking CSS errors are never advisory."""
        css = "@import url(https://evil.com/x.css);\nbody { background: url('gone.png'); }\n"
        results = self._check(css)
        errors = [r for r in results if r.severity == "error"]
        self.assertGreaterEqual(len(errors), 2, "Must have at least 2 blocking errors")


class PlaceholderContentTests(unittest.TestCase):
    def test_todo_detected(self):
        out = []
        _check_placeholder_content("TODO: fix this", "test.html", "test", out)
        self.assertTrue(any("TODO" in o.message for o in out))

    def test_lorem_ipsum_detected(self):
        out = []
        _check_placeholder_content("lorem ipsum dolor sit amet", "test.html", "test", out)
        self.assertTrue(any("lorem ipsum" in o.message.lower() for o in out))

    def test_scaffold_detected(self):
        out = []
        _check_placeholder_content("scaffolding here", "test.html", "test", out)
        self.assertTrue(any("scaffold" in o.message.lower() for o in out))


if __name__ == "__main__":
    unittest.main()
