"""Tests for workspace manager: safe IDs, git init, dirty detection, merge conflicts."""
import unittest
import sys
import os
import subprocess
import tempfile
import shutil
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from qq.workspaces import (
    WorkspaceManager, safe_branch_name, generate_run_id,
    default_run_root, slugify_id, _is_dirty, _ensure_git_repo,
)


class TestRunID(unittest.TestCase):
    def test_generate_run_id(self):
        rid = generate_run_id()
        self.assertIn("-", rid)
        parts = rid.split("-")
        self.assertGreaterEqual(len(parts), 3)

    def test_default_run_root(self):
        root = default_run_root("/tmp/testrepo")
        self.assertTrue(
            root.startswith("/tmp/testrepo/.qq/runs/"))
        self.assertNotIn("latest", root)

    def test_default_run_root_with_id(self):
        root = default_run_root("/tmp/testrepo", "my-custom-run")
        self.assertTrue(root.endswith("my-custom-run"))


class TestSafeBranchNames(unittest.TestCase):
    def test_safe_branch_name(self):
        branch = safe_branch_name("run-1", "bg-core", 3)
        self.assertTrue(branch.startswith("qq/run-1/"))
        self.assertIn("/cycle-3", branch)
        self.assertNotIn(" ", branch)

    def test_safe_branch_name_traversal(self):
        branch = safe_branch_name("run-1", "../../etc", 0)
        self.assertNotIn("..", branch)
        self.assertFalse(branch.startswith("/"))

    def test_git_check_ref_format(self):
        """All generated branch names must pass git check-ref-format."""
        cases = [
            ("run-2025", "bg-core", 1),
            ("run-1", "build-group-with-dashes", 5),
            ("run-abc", "bg_with_underscores", 10),
        ]
        for run_id, bg_id, cycle in cases:
            branch = safe_branch_name(run_id, bg_id, cycle)
            from tests import run_cli_checked
            result = run_cli_checked(
                ["git", "check-ref-format", "--branch", branch],
                cwd="/tmp", timeout=10,
            )
            self.assertEqual(
                result.returncode, 0,
                f"Invalid branch name: '{branch}' — git says: {result.stderr}"
            )


class TestGitRepoInit(unittest.TestCase):
    def test_ensure_git_repo(self):
        tmp = tempfile.mkdtemp(prefix="qq_git_")
        try:
            _ensure_git_repo(tmp)
            self.assertTrue(os.path.isdir(os.path.join(tmp, ".git")))
            self.assertTrue(os.path.exists(os.path.join(tmp, ".gitignore")))
            with open(os.path.join(tmp, ".gitignore")) as fh:
                content = fh.read()
            self.assertIn(".qq/", content)
            self.assertIn("__pycache__/", content)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dirty_detection(self):
        tmp = tempfile.mkdtemp(prefix="qq_dirty_")
        try:
            _ensure_git_repo(tmp)
            self.assertFalse(_is_dirty(tmp))
            with open(os.path.join(tmp, "newfile.txt"), "w") as fh:
                fh.write("hello")
            self.assertTrue(_is_dirty(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_clean_repo_stays_clean(self):
        """Existing clean repos should not be made dirty by gitignore append."""
        tmp = tempfile.mkdtemp(prefix="qq_clean_")
        try:
            _ensure_git_repo(tmp)
            # Repo should be clean after init
            self.assertFalse(_is_dirty(tmp))
            # Running ensure again should not dirty it
            _ensure_git_repo(tmp)
            self.assertFalse(_is_dirty(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestWorkspaceManager(unittest.TestCase):
    def test_refuses_dirty(self):
        tmp = tempfile.mkdtemp(prefix="qq_dirty_")
        try:
            _ensure_git_repo(tmp)
            with open(os.path.join(tmp, "newfile.txt"), "w") as fh:
                fh.write("dirty")
            with self.assertRaises(RuntimeError):
                WorkspaceManager(
                    tmp, os.path.join(tmp, ".qq", "runs", "test"),
                    "run-1")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_allow_dirty(self):
        tmp = tempfile.mkdtemp(prefix="qq_allowdirty_")
        try:
            _ensure_git_repo(tmp)
            with open(os.path.join(tmp, "newfile.txt"), "w") as fh:
                fh.write("dirty")
            wm = WorkspaceManager(
                tmp, os.path.join(tmp, ".qq", "runs", "test"),
                "run-1", allow_dirty=True)
            self.assertEqual(wm.repo_root, os.path.abspath(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_worktree_for_raises_not_implemented(self):
        """Worktree mode is disabled — worktree_for must raise NotImplementedError."""
        tmp = tempfile.mkdtemp(prefix="qq_nowt_")
        try:
            _ensure_git_repo(tmp)
            wm = WorkspaceManager(
                tmp, os.path.join(tmp, ".qq", "runs", "test"),
                "run-1")
            with self.assertRaises(NotImplementedError):
                wm.worktree_for("bg-test", cycle=1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_worktree_for_does_not_return_under_run_root(self):
        """worktree_for should not return a path under run_root (worktree mode disabled)."""
        tmp = tempfile.mkdtemp(prefix="qq_nowt2_")
        try:
            _ensure_git_repo(tmp)
            run_root = os.path.join(tmp, ".qq", "runs", "test")
            wm = WorkspaceManager(tmp, run_root, "run-1")
            with self.assertRaises(NotImplementedError):
                wm.worktree_for("bg-test", cycle=1)
            # Verify no worktrees directory was created under run_root
            self.assertFalse(
                os.path.exists(os.path.join(run_root, "worktrees")),
                "worktrees dir should not exist under run_root")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_direct_mode_still_works(self):
        """Direct-to-repo-root mode remains functional."""
        tmp = tempfile.mkdtemp(prefix="qq_direct_")
        try:
            _ensure_git_repo(tmp)
            wm = WorkspaceManager(
                tmp, os.path.join(tmp, ".qq", "runs", "test"),
                "run-1")
            # Direct commit should work
            with open(os.path.join(tmp, "output.txt"), "w") as fh:
                fh.write("direct mode")
            wm.commit_direct("qq: direct test commit")
            self.assertTrue(os.path.exists(os.path.join(tmp, "output.txt")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
