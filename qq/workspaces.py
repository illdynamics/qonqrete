"""
Isolated workspace management.

WORKSPACE_ROOT / REPO_ROOT:
    Where actual user project work happens. Coding, building, testing
    all happen here. This is the --target path passed to `qq run`.

RUN_ROOT:
    QonQrete metadata only. Internal state, logs, events.
    Derived from --run-root. Must never be used as project cwd.

Speed optimizations:
  - Git repo bootstrap is skipped when .git already exists (warm checkout).
  - .gitignore entries are cached by mtime — only re-read when the file changes.
  - Redundant `git add -A` on an unchanged index is short-circuited.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from typing import Dict, List, Optional, Tuple

from .models import ReviewIssue, slugify_id


# ---------------------------------------------------------------------------
# Run ID generation
# ---------------------------------------------------------------------------
def generate_run_id() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{ts}-{short}"


def default_run_root(repo_root: str,
                     run_id: Optional[str] = None) -> str:
    if run_id is None:
        run_id = generate_run_id()
    return os.path.join(os.path.abspath(repo_root),
                        ".qq", "runs", run_id)


# ---------------------------------------------------------------------------
# Git primer helpers
# ---------------------------------------------------------------------------
_GITIGNORE_ENTRIES = [
    ".qq**",
    ".qq",
    ".qq/**",
    ".codeseeq/",
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
    "._*",
    ".env",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
]

# Default entries for .qqignore — files/directories Qq agents skip
# when reading the project. Works like .gitignore but for Qq.
_DEFAULT_QQIGNORE_ENTRIES = [
    ".codeseeq",
    ".codeseeq/",
    ".codeseeq/**",
    ".env",
    ".qq",
    ".qq/",
    ".qq/**",
]

# Per-repo cache of .qqignore mtime → whether entries are already present
_qqignore_mtime_cache: Dict[str, Tuple[float, bool]] = {}

# Per-repo cache of .gitignore mtime → whether entries are already present
_gitignore_mtime_cache: Dict[str, Tuple[float, bool]] = {}


def _ensure_git_repo(repo_root: str) -> None:
    """Bootstrap a git repo if one doesn't exist.

    Warm-checkout fast path: if .git already exists as a directory, skip
    init/config and go straight to gitignore check.  This saves ~0.5-1s
    per run on repos that are already git-tracked.
    """
    git_dir = os.path.join(repo_root, ".git")

    if os.path.isdir(git_dir):
        # Warm checkout — repo already exists, just ensure gitignore
        if _ensure_gitignore(repo_root):
            subprocess.run(["git", "add", ".gitignore"], cwd=repo_root,
                           check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m",
                           "qq: update .gitignore"],
                           cwd=repo_root, check=True,
                           capture_output=True)
            _try_push(repo_root)
        return

    # Cold checkout — need to initialize
    subprocess.run(["git", "init"], cwd=repo_root, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.email",
                   "qq@local"],
                   cwd=repo_root, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "Qq"],
                   cwd=repo_root, check=True,
                   capture_output=True)

    _ensure_gitignore(repo_root)

    subprocess.run(["git", "add", "-A"], cwd=repo_root,
                   check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m",
                   "qq: initial snapshot", "--allow-empty"],
                   cwd=repo_root, check=True,
                   capture_output=True)
    _try_push(repo_root)


def _ensure_gitignore(repo_root: str) -> bool:
    """Ensure .gitignore has required Qq entries. Returns True if entries were added.

    Uses mtime-based caching: if the .gitignore file hasn't changed since
    the last check and was already known-good, skip the read entirely.
    """
    gi_path = os.path.join(repo_root, ".gitignore")

    # Fast path: check mtime cache
    try:
        mtime = os.path.getmtime(gi_path)
    except OSError:
        mtime = 0.0

    cache_key = repo_root
    cached = _gitignore_mtime_cache.get(cache_key)
    if cached and cached[0] == mtime:
        # File hasn't changed, and was already known-good — nothing to do
        return False

    # Read and check
    existing: List[str] = []
    if os.path.exists(gi_path):
        with open(gi_path, "r", encoding="utf-8") as fh:
            existing = [line.strip() for line in fh]

    needed = [e for e in _GITIGNORE_ENTRIES
              if e not in existing]
    if needed:
        with open(gi_path, "a", encoding="utf-8") as fh:
            fh.write("\n# Qq\n")
            for entry in needed:
                fh.write(entry + "\n")
        # Update cache with new mtime
        try:
            new_mtime = os.path.getmtime(gi_path)
        except OSError:
            new_mtime = time.time()
        _gitignore_mtime_cache[cache_key] = (new_mtime, True)
        return True

    # All entries present, cache the mtime
    _gitignore_mtime_cache[cache_key] = (mtime, True)
    return False


def _ensure_qqignore(repo_root: str) -> bool:
    """Ensure .qqignore exists with default Qq entries. Returns True if
    the file was created or entries were appended.

    .qqignore works like .gitignore — Qq agents (and the codeseeq binary)
    skip files/directories listed in it when reading the project, so
    internal Qq artifacts (.qq/, .codeseeq/, .env) are never ingested
    into agent prompts.

    Uses mtime-based caching: if the .qqignore file hasn't changed since
    the last check and was already known-good, skip the read entirely.
    """
    qqi_path = os.path.join(repo_root, ".qqignore")

    # Fast path: check mtime cache
    try:
        mtime = os.path.getmtime(qqi_path)
    except OSError:
        mtime = 0.0

    cache_key = repo_root
    cached = _qqignore_mtime_cache.get(cache_key)
    if cached and cached[0] == mtime:
        # File hasn't changed, and was already known-good — nothing to do
        return False

    # Read existing entries
    existing: List[str] = []
    if os.path.exists(qqi_path):
        with open(qqi_path, "r", encoding="utf-8") as fh:
            existing = [line.strip() for line in fh]
    else:
        # File doesn't exist — create it fresh with all defaults
        with open(qqi_path, "w", encoding="utf-8") as fh:
            fh.write("# Qq — files/directories agents skip (like .gitignore for Qq)\n")
            fh.write("# Add project-specific patterns below.\n")
            for entry in _DEFAULT_QQIGNORE_ENTRIES:
                fh.write(entry + "\n")
        try:
            new_mtime = os.path.getmtime(qqi_path)
        except OSError:
            new_mtime = time.time()
        _qqignore_mtime_cache[cache_key] = (new_mtime, True)
        return True

    # File exists — append any missing defaults
    needed = [e for e in _DEFAULT_QQIGNORE_ENTRIES
              if e not in existing]
    if needed:
        with open(qqi_path, "a", encoding="utf-8") as fh:
            fh.write("\n# Qq defaults\n")
            for entry in needed:
                fh.write(entry + "\n")
        # Update cache with new mtime
        try:
            new_mtime = os.path.getmtime(qqi_path)
        except OSError:
            new_mtime = time.time()
        _qqignore_mtime_cache[cache_key] = (new_mtime, True)
        return True

    # All entries present, cache the mtime
    _qqignore_mtime_cache[cache_key] = (mtime, True)
    return False


def _try_push(repo_root: str) -> None:
    """Push to origin if a remote is configured. Non-fatal on failure."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return  # No remote, nothing to push
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=repo_root, capture_output=True,
    )


def _is_dirty(repo_root: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def _current_head(repo_root: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Safe branch / path names
# ---------------------------------------------------------------------------
def safe_branch_name(run_id: str, build_group_id: str,
                     cycle: int) -> str:
    safe_run = slugify_id(run_id, "run")
    safe_bg = slugify_id(build_group_id, "bg")
    branch = f"qq/{safe_run}/{safe_bg}/cycle-{cycle}"
    if len(branch) > 240:
        branch = branch[:240]
    return branch


# ---------------------------------------------------------------------------
# WorkspaceManager
# ---------------------------------------------------------------------------
class WorkspaceManager:
    def __init__(self, repo_root: str, run_root: str, run_id: str,
                 allow_dirty: bool = False, no_repo: bool = False):
        self.repo_root = os.path.abspath(repo_root)
        self.run_root = os.path.abspath(run_root)
        self.run_id = run_id
        os.makedirs(self.repo_root, exist_ok=True)
        os.makedirs(self.run_root, exist_ok=True)

        self.no_repo = no_repo

        if not no_repo:
            if not allow_dirty and _is_dirty(self.repo_root):
                raise RuntimeError(
                    f"Repository {self.repo_root} has uncommitted changes. "
                    f"Commit or stash them first, or pass --allow-dirty."
                )

            _ensure_git_repo(self.repo_root)

        # Always create/update .qqignore so agents skip Qq artifacts
        _ensure_qqignore(self.repo_root)

    # ------------------------------------------------------------------
    # Worktree lifecycle
    # ------------------------------------------------------------------
    def _worktree_path(self, build_group_id: str,
                       cycle: int) -> str:
        safe_bg = slugify_id(build_group_id, "bg")
        return os.path.join(self.run_root, "worktrees",
                            f"{safe_bg}-c{cycle}")

    def worktree_for(self, build_group_id: str,
                     cycle: int = 0) -> str:
        raise NotImplementedError(
            "Worktree mode is disabled. QonQrete uses direct-to-repo-root "
            "mode only. Project work must happen in repo_root, not under "
            "run_root/worktrees."
        )

    def commit_worktree(self, build_group_id: str, cycle: int,
                        message: str) -> None:
        if self.no_repo:
            return
        path = self._worktree_path(build_group_id, cycle)
        if not os.path.isdir(path):
            raise RuntimeError(
                f"Worktree for '{build_group_id}' cycle {cycle} "
                f"not found at {path}. Call worktree_for() first."
            )
        self._clean_artifacts(path)
        subprocess.run(["git", "add", "-A"], cwd=path,
                       check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty"],
            cwd=path, check=True, capture_output=True,
        )

    def commit_direct(self, message: str) -> None:
        """Commit directly in the repo root (no worktree isolation)."""
        if self.no_repo:
            return
        self._clean_artifacts(self.repo_root)
        subprocess.run(["git", "add", "-A"], cwd=self.repo_root,
                       check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty"],
            cwd=self.repo_root, check=True, capture_output=True,
        )


    def merge_build_group(self, build_group_id: str,
                          cycle: int) -> Tuple[bool, Optional[str]]:
        if self.no_repo:
            return True, None
        branch = safe_branch_name(
            self.run_id, build_group_id, cycle)
        # Check if the branch exists; if not, we're in direct-to-repo-root
        # mode and no merge is needed (work was done directly)
        check = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=self.repo_root, capture_output=True, text=True,
        )
        if check.returncode != 0:
            # Branch doesn't exist — direct mode, nothing to merge
            return True, None
        result = subprocess.run(
            ["git", "merge", "--no-edit", branch],
            cwd=self.repo_root, capture_output=True, text=True,
        )
        if result.returncode != 0:
            conflict_info = result.stderr or result.stdout
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self.repo_root, capture_output=True,
            )
            return False, conflict_info.strip()
        return True, None

    def merge_conflict_issue(self, build_group_id: str, cycle: int,
                             error_detail: str) -> ReviewIssue:
        return ReviewIssue(
            build_group_id=build_group_id,
            briq_id=None,
            severity="blocking",
            what_is_wrong=(
                f"Merge conflict in build group "
                f"'{build_group_id}': {error_detail[:300]}"
            ),
            what_to_fix=(
                f"Resolve merge conflict in build group "
                f"'{build_group_id}' "
                f"(branch: {safe_branch_name(self.run_id, build_group_id, cycle)})."
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_artifacts(workdir: str) -> None:
        import shutil
        for fname in list(os.listdir(workdir)):
            if (fname.startswith(".qq_")
                    or fname.startswith(".qq_prompt_")
                    or fname.endswith("_output.json")
                    or fname in (
                        "clarifier_output.json",
                        "qlarifier_output.json",
                        "instruqtor_output.json",
                        "instructor_output.json",
                        "construqtor_output.json",
                        "inspeqtor_output.json",
                    )):
                full = os.path.join(workdir, fname)
                if os.path.isfile(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
        # Also remove .qq_artifacts/ directory
        arts_dir = os.path.join(workdir, ".qq_artifacts")
        if os.path.isdir(arts_dir):
            shutil.rmtree(arts_dir, ignore_errors=True)

    def _remove_worktree(self, path: str) -> None:
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", path],
                cwd=self.repo_root, capture_output=True,
            )
        except Exception:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=self.repo_root, capture_output=True,
            )
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)

    def cleanup_stale_worktrees(self) -> None:
        wtdir = os.path.join(self.run_root, "worktrees")
        if os.path.isdir(wtdir):
            for name in os.listdir(wtdir):
                self._remove_worktree(
                    os.path.join(wtdir, name))
