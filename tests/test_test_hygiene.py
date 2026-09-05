"""
Hygiene tests that enforce coding standards in the test suite.

These tests scan test files with the ``ast`` module and fail on
unguarded ``subprocess.run(...)`` / ``sp.run(...)`` calls that lack an
explicit ``timeout=`` argument.
"""
import ast
import os
import sys
import unittest

TESTS_DIR = os.path.normpath(os.path.dirname(__file__))

# Files INSIDE tests/ that must still pass the subprocess-guard check.
# Exclude __init__.py because run_cli_checked lives there (it IS the guard).
# Exclude this file itself.
_EXCLUDE_FILES = {"__init__.py", "test_test_hygiene.py"}


def _gather_test_modules() -> list[str]:
    """Return absolute paths of all Python test files to scan."""
    paths: list[str] = []
    for fname in sorted(os.listdir(TESTS_DIR)):
        if fname in _EXCLUDE_FILES:
            continue
        if fname.endswith(".py"):
            paths.append(os.path.join(TESTS_DIR, fname))
    return paths


def _is_patch_decorator_or_context(node):
    """Return True if node is a @patch('subprocess.run') or with patch(...) call.

    In the AST, ``@patch('subprocess.run')`` appears as a Call node whose
    func resolves to ``patch``.
    """
    if isinstance(node, ast.Call):
        func = node.func
        # Simple name: patch(...)
        if isinstance(func, ast.Name) and func.id == "patch":
            return True
        # Attribute: mock.patch(...) or unittest.mock.patch(...)
        if isinstance(func, ast.Attribute) and func.attr == "patch":
            return True
    return False


def _has_timeout_keyword(keywords) -> bool:
    """Return True if the keyword list contains ``timeout=...``."""
    for kw in keywords:
        if kw.arg == "timeout":
            return True
    return False


class SubprocessRunVisitor(ast.NodeVisitor):
    """Walk an AST and collect violations of the subprocess-guard rule."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[str] = []  # human-readable descriptions

    def visit_Call(self, node: ast.Call):
        # Detect: subprocess.run(...) or sp.run(...)
        func = node.func
        if isinstance(func, ast.Attribute):
            # attr chain: subprocess.run or sp.run
            obj = func.value
            if (isinstance(obj, ast.Name)
                    and obj.id in ("subprocess", "sp")
                    and func.attr == "run"):
                # Check for timeout= keyword
                if not _has_timeout_keyword(node.keywords):
                    self.violations.append(
                        f"{self.filename}:{node.lineno}: "
                        f"{obj.id}.run(...) without timeout="
                    )
        # Also detect bare run(...) if it's a plain subprocess.run call
        # (covered by the check above for subprocess.run)

        # Generic visit
        self.generic_visit(node)


class TestTestHygiene(unittest.TestCase):
    """Every test file must not call subprocess.run/sp.run without timeout=."""

    def test_no_unguarded_subprocess_calls(self):
        modules = _gather_test_modules()
        self.assertGreater(len(modules), 0, "Expected at least one test module to scan")

        all_violations: list[str] = []
        for modpath in modules:
            with open(modpath, "r", encoding="utf-8") as fh:
                source = fh.read()
            try:
                tree = ast.parse(source, filename=modpath)
            except SyntaxError as exc:
                all_violations.append(f"{modpath}: SyntaxError: {exc}")
                continue

            visitor = SubprocessRunVisitor(modpath)
            visitor.visit(tree)
            all_violations.extend(visitor.violations)

        if all_violations:
            self.fail(
                "Found unguarded subprocess.run() / sp.run() calls "
                "without timeout=:\n" + "\n".join(all_violations)
            )

    def test_run_cli_checked_is_accepted(self):
        """Verify run_cli_checked() calls are NOT flagged (sanity check)."""
        # run_cli_checked lives in tests/__init__.py, which is excluded
        # from the main scan.  This test ensures the helper itself wouldn't
        # cause a violation if it were scanned.
        init_path = os.path.join(TESTS_DIR, "__init__.py")
        with open(init_path, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=init_path)
        visitor = SubprocessRunVisitor(init_path)
        visitor.visit(tree)

        # run_cli_checked uses subprocess.run internally, but it passes
        # timeout=timeout.  The visitor should find zero violations.
        self.assertEqual(
            len(visitor.violations), 0,
            f"tests/__init__.py itself should have zero unguarded calls, "
            f"but found: {visitor.violations}"
        )


if __name__ == "__main__":
    unittest.main()
