"""
Tests for packaging CLI flags exposed through `qq package`.
Uses direct function calls (qq.package.build, check_tree, check_archive,
check_uploaded_zip) to avoid spawning nested Python processes that can
hang during full-suite runs.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from qq import __version__ as qq_version
from qq.package import build, check_tree, check_archive, get_version


class TestPackageCLIFlags(unittest.TestCase):
    """Test that the packaging functions work correctly via direct calls."""

    def test_package_check_passes_on_clean_tree(self):
        """check_tree should pass on a cleaned source tree."""
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "clean")
            def _ignore(src, names):
                banned = {".git", ".codeseeq", "__pycache__",
                          ".pytest_cache", ".ruff_cache",
                          ".mypy_cache", ".hypothesis", "dist",
                          ".DS_Store", ".qq_artifacts", "qq.egg-info", "prompt12.md",
                          "promptje.md", "promptje2.md", "promptje3.md", "prompt.md",
                          ".env",
                          # Qq metadata + runtime artifacts must never ship in a tree
                          ".qq",
                          # Large build artifact directories
                          ".venv", "node_modules",
                          "target",  # Rust build artifacts (qq-tui/target, qq/web/target)
                          # IDE build output (VS Code / IntelliJ)
                          "build", ".gradle", "out",
                          }
                return [n for n in names if n in banned or n.endswith(".vsix")]
            shutil.copytree(PROJECT_ROOT, dst, ignore=_ignore)
            rc = check_tree(root=dst)
            self.assertEqual(rc, 0, f"check_tree failed: rc={rc}")

    def test_package_check_upload_tree_direct(self):
        """check_tree with upload_mode=True should fail when .git/ or .codeseeq/ exists."""
        git_exists = os.path.isdir(os.path.join(PROJECT_ROOT, '.git'))
        codeseeq_exists = os.path.isdir(os.path.join(PROJECT_ROOT, '.codeseeq'))
        try:
            rc = check_tree(root=PROJECT_ROOT, upload_mode=True)
        except SystemExit as e:
            rc = e.code
        if git_exists or codeseeq_exists:
            # .git/ or .codeseeq/ should cause upload_tree check to fail
            self.assertNotEqual(rc, 0,
                f"check_tree(upload_mode=True) should have failed on "
                f".git/={git_exists} .codeseeq/={codeseeq_exists}")
        else:
            self.assertEqual(rc, 0, "check_tree(upload_mode=True) should pass without .git/")

    def test_package_check_upload_tree_on_clean_temp(self):
        """check_tree with upload_mode=True should pass on a temp tree without .git/."""
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "clean")
            def _ignore(src, names):
                return [n for n in names if n in (".git", ".codeseeq", "__pycache__",
                                                  ".pytest_cache", ".ruff_cache",
                                                  ".mypy_cache", ".hypothesis",
                                                  "dist", ".DS_Store", ".qq_artifacts", "qq.egg-info",
                                                  "prompt12.md", "promptje.md", "promptje2.md", "promptje3.md", "prompt.md",
                                                  ".env",
                                                  # Qq metadata must never ship in a tree
                                                  ".qq",
                                                  # Large build artifact directories
                                                  ".venv", "node_modules",
                                                  "target",  # Rust build artifacts (qq-tui/target, qq/web/target)
                                                  # IDE build output (VS Code / IntelliJ)
                                                  "build", ".gradle", "out",
                                                  ) or n.endswith(".vsix")]
            shutil.copytree(PROJECT_ROOT, dst, ignore=_ignore)
            rc = check_tree(root=dst, upload_mode=True)
            self.assertEqual(rc, 0, f"Expected pass on clean temp: rc={rc}")

    def test_package_final_builds_and_returns_path(self):
        """build() should create the zip and return its path."""
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = build(root=PROJECT_ROOT, dist_dir=tmp)
            expected_name = f"qonqrete-qq-v{qq_version}"
            self.assertIn(expected_name, zip_path)
            self.assertTrue(os.path.isfile(zip_path),
                            f"Expected zip at {zip_path}")

    def test_package_check_archive_direct(self):
        """check_archive should pass on a clean built archive."""
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = build(root=PROJECT_ROOT, dist_dir=tmp)
            rc = check_archive(zip_path)
            self.assertEqual(rc, 0, f"check_archive failed: rc={rc}")

    def test_package_check_uploaded_zip_direct(self):
        """check_archive (aliased as check_uploaded_zip) should pass on built archive."""
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = build(root=PROJECT_ROOT, dist_dir=tmp)
            rc = check_archive(zip_path)
            self.assertEqual(rc, 0, f"check_uploaded_zip failed: rc={rc}")

    def test_check_uploaded_zip_fails_on_dirty_zip(self):
        """check_archive should fail on a dirty zip with .git/."""
        with tempfile.TemporaryDirectory() as tmp:
            dirty_zip = os.path.join(tmp, "dirty.zip")
            with zipfile.ZipFile(dirty_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("dirty/.git/config", "fake")
                zf.writestr("dirty/src/hello.py", "print('hi')")
            rc = check_archive(dirty_zip)
            self.assertNotEqual(rc, 0, f"Expected failure on dirty zip, got rc={rc}")

    def test_version_consistency(self):
        """qq.__version__ must match pyproject.toml project.version."""
        pyproject_path = os.path.join(PROJECT_ROOT, "pyproject.toml")
        with open(pyproject_path) as f:
            pyproject_text = f.read()
        match = re.search(r'^version\s*=\s*"(.*?)"', pyproject_text, re.MULTILINE)
        self.assertIsNotNone(match, "Could not find version in pyproject.toml")
        pyproject_version = match.group(1)
        self.assertEqual(qq_version, pyproject_version,
                         f"qq.__version__ ({qq_version}) != pyproject.toml ({pyproject_version})")

    def test_archive_name_matches_version(self):
        """build() must create dist/qonqrete-qq-v{qq.__version__}.zip."""
        expected_name = f"qonqrete-qq-v{qq_version}.zip"
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = build(root=PROJECT_ROOT, dist_dir=tmp)
            self.assertTrue(os.path.isfile(zip_path),
                            f"Expected archive, not found: {zip_path}")
            self.assertIn(expected_name, os.path.basename(zip_path),
                          f"Archive name mismatch: expected {expected_name} in {zip_path}")


if __name__ == "__main__":
    unittest.main()
