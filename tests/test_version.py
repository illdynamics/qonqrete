"""Version consistency tests — prevent stale reports, verify scripts, and README drift."""
import os
import unittest
import tomllib  # Python 3.11+


class TestVersionConsistency(unittest.TestCase):
    """Ensure qq.__version__ matches pyproject.toml and all references are consistent."""

    def test_init_matches_pyproject(self):
        """qq.__version__ must equal pyproject.toml project.version."""
        from qq import __version__

        root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), ".."))
        toml_path = os.path.join(root, "pyproject.toml")

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        pyproject_version = data["project"]["version"]
        self.assertEqual(__version__, pyproject_version,
                         f"qq.__version__ ({__version__}) != "
                         f"pyproject.toml version ({pyproject_version})")

    def test_verify_py_archive_name_uses_current_version(self):
        """qq/verify.py get_archive_name() must use the current version."""
        from qq import __version__
        from qq.verify import get_archive_name

        name = get_archive_name()
        expected = f"qonqrete-qq-v{__version__}.zip"
        self.assertIn(expected, name,
                      f"get_archive_name() returned {name}, expected {expected}")

    def test_verify_sh_archive_is_current(self):
        """qq/verify.py get_archive_name() must use the current version."""
        from qq import __version__
        from qq.verify import get_archive_name

        name = get_archive_name()
        expected = f"qonqrete-qq-v{__version__}.zip"
        self.assertIn(expected, name,
                      f"get_archive_name() returned {name}, expected {expected}")

    def test_readme_no_stale_archive_references(self):
        """README.md must not reference stale archive versions outside the version history section."""
        from qq import __version__

        root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), ".."))
        readme_path = os.path.join(root, "README.md")

        with open(readme_path) as f:
            content = f.read()

        # The README should mention the current version
        self.assertIn(__version__, content,
                      f"README.md does not contain version {__version__}")

        # But not old ones — check for patterns that look like stale versions.
        # Exclude the "Version history" section where old versions are documented.
        import re
        # Split at "## Version history" — only check the part before it
        before_history = content.split("## Version history")[0] if "## Version history" in content else content

        version_pattern = re.compile(r'qonqrete-qq-v(\d+\.\d+\.\d+)')
        for match in version_pattern.finditer(before_history):
            found = match.group(1)
            self.assertEqual(found, __version__,
                             f"README.md contains stale archive reference "
                             f"qonqrete-qq-v{found} (expected v{__version__})")

    def test_readme_version_table_current(self):
        """README.md version table must end with the current version."""
        from qq import __version__

        root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), ".."))
        readme_path = os.path.join(root, "README.md")

        with open(readme_path) as f:
            content = f.read()

        import re
        # Find all version lines in the version table
        version_lines = re.findall(r'^(\d+\.\d+\.\d+)\s.*', content, re.MULTILINE)
        self.assertIn(__version__, version_lines,
                      f"README.md version table missing {__version__}")


if __name__ == "__main__":
    unittest.main()
