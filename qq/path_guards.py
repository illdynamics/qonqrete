"""
Path guardrails — ensures QonQrete never writes project files into its
own metadata directories (.qq, run_root, etc.) and never runs commands
with cwd pointing to metadata directories.

WORKSPACE_ROOT / REPO_ROOT:
    Where actual user project work happens. Coding, building, testing
    all happen here. This is the --target path:

        qq run [options] <task_file> <target_path>

    Examples:
      - /x/qq/testwebsite
      - /x/projects/myrepo

RUN_ROOT / STATE_ROOT:
    QonQrete metadata only. Internal state, logs, events.
    This path is derived from --run-root and must never become the
    project working directory.

    Examples:
      - /x/qq/runs/<run_id>
      - <workspace_root>/.qq/runs/<run_id>

.qq METADATA ROOT:
    The .qq directory under workspace_root. Metadata only.
    Must never contain user project files.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Forbidden project deliverable scan with whitelist
# ---------------------------------------------------------------------------

# Forbidden directory names (anywhere under run_root or workspace_root/.qq)
_FORBIDDEN_DIR_NAMES = frozenset({
    "src", "tests", "test", "public", "dist", "build",
    "node_modules", "target", "lib", "app", "components",
    "pages", "assets", "static", "templates", "migrations",
    "vendor", "venv", ".venv",
})

# Forbidden file names (anywhere under run_root or workspace_root/.qq)
_FORBIDDEN_FILE_NAMES = frozenset({
    "app.py", "main.py", "calculator.py",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
    "Cargo.toml", "go.mod",
    "index.html", "README.md",
    "Makefile", "Dockerfile", "docker-compose.yml",
})

# Forbidden file extensions (anywhere under run_root or workspace_root/.qq)
# unless explicitly whitelisted as metadata
_FORBIDDEN_EXTENSIONS = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss",
    ".html", ".vue", ".svelte", ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".hpp", ".sh", ".sql", ".md",
})

# Allowed metadata artifact basenames (only in expected locations)
_METADATA_ARTIFACT_NAMES = frozenset({
    # Event/core files
    "events.jsonl",
    # State files
    "origin.json", "completion_callback.json", "completion_callback.lock",
    "final.json", "task.json", "clarified_task.json", "plan.json",
    # Runner state files
    "runner.stdout.log", "runner.stderr.log", "runner.exit_code",
    "runner.finished",
    # Agent receipt JSON files (canonical output of each agent)
    "qlarifier_output.json", "instruqtor_output.json",
    "construqtor_output.json", "inspeqtor_output.json",
})

# Allowed metadata filenames under agents/**/call-* directories
_AGENT_ARTIFACT_NAMES = frozenset({
    "prompt.md", "stdout.txt", "stderr.txt", "result.json", "metadata.json",
})

# Allowed canonical QonQrete artifact markdown basenames under run_root/artifacts/
_ALLOWED_RUN_ARTIFACT_MD = frozenset({
    "task-original.md",
    "task-enhanced.md",
    "planning.md",
})

# Allowed sandbox metadata filenames
_ALLOWED_SANDBOX_METADATA = frozenset({
    "prompt.md",
    "stdout.txt", "stderr.txt", "result.json", "metadata.json",
})


def _is_in_agent_call_dir(rel_path: str) -> bool:
    """Check if the relative path is under agents/**/call-* directories."""
    parts = Path(rel_path).parts
    # Expected pattern: agents/cycle-NNN/role/call-XXX/...
    if len(parts) >= 4 and parts[0] == "agents":
        # parts[1] is cycle-NNN, parts[2] is role, parts[3] is call-XXX
        if parts[3].startswith("call-"):
            return True
    return False


def _is_allowed_metadata(rel_path: str, fname: str, scope: str = "run_root") -> bool:
    """Return True if the file is a known metadata artifact at an expected location.

    rel_path: path relative to the scan root (run_root or .qq)
    fname: basename of the file
    scope: "run_root" when scanning run_root, "workspace_dot_qq" when scanning .qq
    """
    parts = Path(rel_path).parts

    # When scanning .qq, every tree under .qq/runs/<run_id>/ is QonQrete run
    # metadata (our own run_root included, plus sibling / prior / archived
    # runs). Strip the leading "runs/<run_id>/" prefix so the remainder is
    # evaluated with the same run-root metadata rules below. Genuinely stray
    # non-metadata files dropped into a runs dir (e.g. .qq/runs/x/app.py) are
    # still flagged because app.py matches no metadata rule.
    if scope == "workspace_dot_qq" and len(parts) >= 2 and parts[0] == "runs":
        inner = parts[2:]
        if inner:
            parts = inner
            rel_path = str(Path(*inner))
            # This is now a run-internal path; apply the full run-root
            # metadata rules (artifacts/, sandbox/, etc.).
            scope = "run_root"
        else:
            return True  # the runs/<run_id> dir itself

    # Top-level metadata files (events.jsonl, etc.) — only at root or first level
    if fname in _METADATA_ARTIFACT_NAMES:
        # Allow at root level or state/ dir
        if len(parts) <= 1 or (len(parts) == 2 and parts[0] == "state"):
            return True

    # State directory: any .json or .lock file under state/ is metadata
    if len(parts) >= 2 and parts[0] == "state":
        if fname.endswith(".json") or fname.endswith(".lock"):
            return True

    # Agent artifacts under agents/**/ directories
    if len(parts) >= 4 and parts[0] == "agents":
        # Files under call-* dirs with agent artifact names
        if parts[3].startswith("call-") and fname in _AGENT_ARTIFACT_NAMES:
            return True
        # Agent receipt JSON files directly under role directory
        # (e.g. agents/cycle-000/qlarifier/qlarifier_output.json)
        if fname in _METADATA_ARTIFACT_NAMES:
            return True
        # Per-call receipt JSON files under receipts/ subdirectory
        # (e.g. agents/cycle-001/construqtor/receipts/bg-contact__call-abc123.json)
        if len(parts) >= 5 and parts[3] == "receipts":
            if fname.endswith(".json"):
                return True

    # Also allow receipt JSONs at agents/cycle-XXX/<role>/ level (len(parts) == 4, parts[3] is filename)
    if len(parts) == 4 and parts[0] == "agents":
        if fname in _METADATA_ARTIFACT_NAMES:
            return True

    # --- run_root scope: canonical QonQrete artifact markdown ---
    if scope == "run_root":
        # artifacts/task-original.md, task-enhanced.md, planning.md (canonical only)
        if len(parts) == 2 and parts[0] == "artifacts" and fname in _ALLOWED_RUN_ARTIFACT_MD:
            return True
        # sandbox/input/<call_id>/prompt.md etc. (sandbox metadata)
        if (len(parts) == 4 and parts[0] == "sandbox" and parts[1] == "input"
                and fname in _ALLOWED_SANDBOX_METADATA):
            return True
        # sandbox/output/<call_id>/stdout.txt, stderr.txt, result.json, metadata.json
        if (len(parts) == 4 and parts[0] == "sandbox" and parts[1] == "output"
                and fname in _ALLOWED_SANDBOX_METADATA):
            return True
        # Per-call agent artifacts nested under any role/instruction directory
        # (e.g. instruction/construqtor/call-*/prompt.md, inspeqtor/call-*/prompt.md,
        # agents/cycle-NN/<role>/call-*/...). A "call-*" path component marks the
        # file as a per-call metadata artifact; keep canonical artifacts/*.md strict.
        if any(p.startswith("call-") for p in parts):
            if fname.endswith((".md", ".txt", ".json", ".log", ".lock")):
                return True

    # --- Allow known metadata extensions anywhere under agents/ tree ---
    if len(parts) >= 2 and parts[0] == "agents":
        # .json files anywhere under agents/ are metadata
        if fname.endswith(".json"):
            return True
        # .md files under agents/ are prompt artifacts
        if fname.endswith(".md"):
            return True
        # .txt files under agents/ (stdout.txt, stderr.txt)
        if fname.endswith(".txt"):
            return True
        # .log files under agents/
        if fname.endswith(".log"):
            return True

    # --- Allow known metadata extensions under sandbox/ tree ---
    if len(parts) >= 2 and parts[0] == "sandbox":
        # .json files anywhere under sandbox/ (result.json, metadata.json)
        if fname.endswith(".json"):
            return True
        # .md files under sandbox/ (prompt.md)
        if fname.endswith(".md"):
            return True
        # .txt files under sandbox/ (stdout.txt, stderr.txt)
        if fname.endswith(".txt"):
            return True
        # .log files under sandbox/
        if fname.endswith(".log"):
            return True
        # .lock files under sandbox/
        if fname.endswith(".lock"):
            return True
        # .toml, .yaml, .yml files under sandbox/ (config files)
        if fname.endswith(".toml") or fname.endswith(".yaml") or fname.endswith(".yml"):
            return True
        # hidden files (like .gitignore snippets, .env templates) under sandbox/
        if fname.startswith("."):
            return True

    # --- Allow anything under .codeseeq-home/ (CodeSeeq/Codex per-call state) ---
    if len(parts) >= 2 and parts[0] == ".codeseeq-home":
        return True

    # --- workspace_dot_qq scope: stricter ---
    # Agent artifacts under .qq/runs/<run_id>/agents/... are still allowed
    # (already handled above via generic check)

    return False


class PathPolicyViolation(ValueError):
    """Raised when a file write or command cwd violates the path policy."""

    def __init__(
        self,
        path: str,
        reason: str,
        workspace_root: str,
        run_root: str,
        detail: str = "",
        agent: str = "",
        build_group_id: str = "",
        cycle: int = 0,
    ):
        self.path = path
        self.reason = reason
        self.workspace_root = workspace_root
        self.run_root = run_root
        self.detail = detail
        self.agent = agent
        self.build_group_id = build_group_id
        self.cycle = cycle
        msg = (
            f"Path policy violation: {reason}\n"
            f"  Path: {path}\n"
            f"  Workspace root: {workspace_root}\n"
            f"  Run root: {run_root}\n"
            + (f"  Detail: {detail}\n" if detail else "")
        )
        super().__init__(msg)

    def to_event(self, agent: str = "") -> dict:
        """Convert to an event dict for eventlog."""
        return {
            "type": "path_policy_violation",
            "severity": "error",
            "path": self.path,
            "reason": self.reason,
            "workspace_root": self.workspace_root,
            "run_root": self.run_root,
            "agent": agent or self.agent,
        }



def _path_kind(path: str, run_root: str, workspace_root: str) -> str:
    """Determine whether a path is under run_root, target_path, or unknown."""
    try:
        real_path = str(Path(path).resolve())
        real_run = str(Path(run_root).resolve())
        real_ws = str(Path(workspace_root).resolve())
    except (ValueError, OSError):
        return "unknown"
    if is_under(real_path, real_run):
        return "run_root"
    if is_under(real_path, real_ws):
        return "target_path"
    return "unknown"


def scan_for_forbidden_deliverables(
    run_root: str, workspace_root: str,
    agent: str = "", build_group_id: str = "", cycle: int = 0,
    event_log=None,
) -> List[dict]:
    """Scan run_root and workspace_root/.qq for forbidden project deliverables.

    Returns a list of violation dicts. Empty list means clean.
    Each violation dict has: path, reason, workspace_root, run_root,
    agent, build_group_id, cycle.

    Whitelisted metadata artifacts (allowed):
      - events.jsonl
      - state/*.json
      - state/*.lock
      - agents/**/call-*/prompt.md, stdout.txt, stderr.txt, result.json, metadata.json
      - runner.stdout.log, runner.stderr.log, runner.exit_code, runner.finished
      - artifacts/task-original.md, artifacts/task-enhanced.md, artifacts/planning.md
      - sandbox/input/<call_id>/prompt.md, sandbox/output/<call_id>/stdout.txt, etc.

    Forbidden anywhere under run_root or workspace_root/.qq:
      - Project source files by extension (.py, .js, .ts, etc.)
      - Project directories (src/, test/, public/, dist/, etc.)
      - Known project filenames (package.json, pyproject.toml, index.html, etc.)
    """
    violations: List[dict] = []

    def _scan_dir(scan_root: str, location_label: str):
        """Scan a single directory tree for violations."""
        if not os.path.isdir(scan_root):
            return

        # Walk the tree, checking dir names and file names
        dirs_to_prune = {".git", "__pycache__", ".codeseeq-home"}
        # Also prune known metadata dirs from forbidden-dir checking
        # But we still scan INSIDE them for forbidden files

        for root, dirs, files in os.walk(scan_root):
            # Compute relative path from scan_root
            rel_root = os.path.relpath(root, scan_root)
            if rel_root == ".":
                rel_root = ""

            # Prune known noise dirs
            dirs[:] = [d for d in dirs if d not in dirs_to_prune]

            # Check directory names — but skip internal QonQrete metadata dirs
            # (runs/, agents/, state/, worktrees/ are all internal)
            _INTERNAL_METADATA_DIRS = {"runs", "agents", "state", "worktrees", "sandbox", "receipts", ".codeseeq-home"}
            rel_parts = Path(rel_root).parts if rel_root else ()
            # Skip forbidden-dir check if any parent is an internal metadata dir
            _in_internal = any(p in _INTERNAL_METADATA_DIRS for p in rel_parts)
            
            for d in dirs:
                if d in _FORBIDDEN_DIR_NAMES and not _in_internal:
                    full_path = os.path.join(root, d)
                    violations.append({
                        "path": full_path,
                        "offending_path": full_path,
                        "reason": "forbidden_project_directory_in_metadata",
                        "workspace_root": workspace_root,
                        "run_root": run_root,
                        "target_path": workspace_root,
                        "path_kind": _path_kind(full_path, run_root, workspace_root),
                        "agent": agent,
                        "build_group_id": build_group_id,
                        "cycle": cycle,
                    })

            # Check file names and extensions
            for fname in files:
                rel = os.path.join(rel_root, fname) if rel_root else fname
                full_path = os.path.join(root, fname)

                # Check if it's an allowed metadata artifact
                if _is_allowed_metadata(rel, fname, scope="run_root"):
                    continue

                # Check forbidden filenames
                if fname in _FORBIDDEN_FILE_NAMES:
                    violations.append({
                        "path": full_path,
                        "offending_path": full_path,
                        "reason": "project_deliverable_in_metadata",
                        "workspace_root": workspace_root,
                        "run_root": run_root,
                        "target_path": workspace_root,
                        "path_kind": _path_kind(full_path, run_root, workspace_root),
                        "extension": os.path.splitext(fname)[1].lower(),
                        "agent": agent,
                        "build_group_id": build_group_id,
                        "cycle": cycle,
                    })
                    continue

                # Check forbidden extensions
                ext = os.path.splitext(fname)[1].lower()
                if ext in _FORBIDDEN_EXTENSIONS:
                    violations.append({
                        "path": full_path,
                        "offending_path": full_path,
                        "reason": "forbidden_project_extension_in_metadata",
                        "workspace_root": workspace_root,
                        "run_root": run_root,
                        "target_path": workspace_root,
                        "path_kind": _path_kind(full_path, run_root, workspace_root),
                        "extension": ext,
                        "agent": agent,
                        "build_group_id": build_group_id,
                        "cycle": cycle,
                    })
                    continue

    # Scan run_root
    _scan_dir(run_root, "run_root")

    # Scan workspace_root/.qq — always scan .qq, but only areas NOT already
    # covered by run_root (which was already scanned above).
    # This catches forbidden deliverables like .qq/src/main.js or .qq/app.py
    # that exist outside the run_root metadata tree.
    qq_dir = os.path.join(workspace_root, ".qq")
    if os.path.isdir(qq_dir):
        run_real = None
        try:
            run_real = os.path.realpath(run_root)
        except (ValueError, OSError):
            pass

        # Walk .qq but skip subtrees that are under run_root (already scanned)
        dirs_to_prune = {".git", "__pycache__", ".codeseeq-home"}
        for root, dirs, files in os.walk(qq_dir):
            # If this directory is under run_root, skip it and all children
            if run_real:
                try:
                    root_real = os.path.realpath(root)
                    if is_under(root_real, run_real) or root_real == run_real:
                        dirs.clear()  # don't descend further
                        continue
                except (ValueError, OSError):
                    pass

            rel_root = os.path.relpath(root, qq_dir)
            if rel_root == ".":
                rel_root = ""

            dirs[:] = [d for d in dirs if d not in dirs_to_prune]

            # Check directory names — only flag if NOT an internal .qq metadata dir
            rel_parts = Path(rel_root).parts if rel_root else ()
            _INTERNAL_METADATA_DIRS = {"runs", "agents", "state", "worktrees", "sandbox", "receipts", ".codeseeq-home"}
            _in_internal = any(p in _INTERNAL_METADATA_DIRS for p in rel_parts)

            for d in dirs:
                if d in _FORBIDDEN_DIR_NAMES and not _in_internal:
                    full_path = os.path.join(root, d)
                    violations.append({
                        "path": full_path,
                        "offending_path": full_path,
                        "reason": "forbidden_project_directory_in_metadata",
                        "workspace_root": workspace_root,
                        "run_root": run_root,
                        "target_path": workspace_root,
                        "path_kind": _path_kind(full_path, run_root, workspace_root),
                        "agent": agent,
                        "build_group_id": build_group_id,
                        "cycle": cycle,
                    })

            for fname in files:
                rel = os.path.join(rel_root, fname) if rel_root else fname
                full_path = os.path.join(root, fname)

                if _is_allowed_metadata(rel, fname, scope="workspace_dot_qq"):
                    continue

                if fname in _FORBIDDEN_FILE_NAMES:
                    violations.append({
                        "path": full_path,
                        "offending_path": full_path,
                        "reason": "project_deliverable_in_metadata",
                        "workspace_root": workspace_root,
                        "run_root": run_root,
                        "target_path": workspace_root,
                        "path_kind": _path_kind(full_path, run_root, workspace_root),
                        "extension": os.path.splitext(fname)[1].lower(),
                        "agent": agent,
                        "build_group_id": build_group_id,
                        "cycle": cycle,
                    })
                    continue

                ext = os.path.splitext(fname)[1].lower()
                if ext in _FORBIDDEN_EXTENSIONS:
                    violations.append({
                        "path": full_path,
                        "offending_path": full_path,
                        "reason": "forbidden_project_extension_in_metadata",
                        "workspace_root": workspace_root,
                        "run_root": run_root,
                        "target_path": workspace_root,
                        "path_kind": _path_kind(full_path, run_root, workspace_root),
                        "extension": ext,
                        "agent": agent,
                        "build_group_id": build_group_id,
                        "cycle": cycle,
                    })
                    continue

    if violations and event_log:
        for v in violations:
            event_log.emit("path_policy_violation",
                           severity="error",
                           **v)
    return violations





def cleanup_forbidden_deliverables(violations: list) -> int:
    """Remove forbidden project deliverables found by the scanner.
    
    Only removes files/directories that are explicitly flagged as forbidden.
    Returns count of items removed.
    Safe: never removes known metadata files or real project files under workspace_root outside .qq.
    """
    import shutil
    removed = 0
    for v in violations:
        path = v.get("path", "")
        if not path:
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
            elif os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)
                removed += 1
        except (OSError, PermissionError):
            pass
    return removed

def scan_for_forbidden_bool(
    run_root: str, workspace_root: str,
    agent: str = "", build_group_id: str = "", cycle: int = 0,
    event_log=None,
) -> bool:
    """Backwards-compatible bool wrapper for scan_for_forbidden_deliverables."""
    violations = scan_for_forbidden_deliverables(
        run_root, workspace_root, agent=agent,
        build_group_id=build_group_id, cycle=cycle, event_log=event_log)
    return len(violations) > 0


# ---------------------------------------------------------------------------
# Escape hatch config
# ---------------------------------------------------------------------------
def _allow_writes_in_qq() -> bool:
    """Check whether project writes inside .qq are explicitly allowed.
    Default is False. Only set to 'true' in forbidden-path tests."""
    return os.environ.get("QONQRETE_ALLOW_PROJECT_WRITES_IN_QQ", "false").lower() in (
        "1", "true", "yes"
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def is_under(path: str, root: str) -> bool:
    """Return True if `path` resolves inside or equals `root`."""
    try:
        p = Path(path).resolve()
        r = Path(root).resolve()
        # Use os.path.commonpath for a clean check
        common = os.path.commonpath([str(p), str(r)])
        return common == str(r)
    except (ValueError, OSError):
        return False


def has_path_component(path: str, component: str) -> bool:
    """Return True if `component` appears as a component in the resolved path.
    Does not require the component directory to exist."""
    try:
        parts = Path(path).resolve().parts
        return component in parts
    except (ValueError, OSError):
        return component in path.split(os.sep)


def is_under_qq_metadata(
    path: str, workspace_root: Optional[str] = None, run_root: Optional[str] = None
) -> bool:
    """Return True if path is under any QonQrete metadata directory.

    Checks:
      - run_root and any subdirectory of run_root
      - <workspace_root>/.qq and any subdirectory of it
    Does not require .qq directory to exist.
    """
    # Check run_root
    if run_root:
        if is_under(path, run_root):
            return True
    # Check workspace_root/.qq — regardless of whether it exists
    if workspace_root:
        try:
            ws_resolved = Path(workspace_root).resolve()
            qq_root = ws_resolved / ".qq"
            path_resolved = Path(path).resolve()
            # Check using commonpath — does not require qq_root to exist
            common = os.path.commonpath([str(path_resolved), str(qq_root)])
            if common == str(qq_root):
                return True
        except (ValueError, OSError):
            pass
    # Also check if path itself contains ".qq" as a component
    if has_path_component(path, ".qq"):
        return True
    return False


def assert_project_write_allowed(
    path: str, workspace_root: str, run_root: str
) -> None:
    """Raise PathPolicyViolation if writing `path` would violate policy.

    Allowed:  path is under workspace_root and NOT under .qq or run_root.
    Forbidden: path is inside run_root, .qq, or outside workspace_root.
    """
    if _allow_writes_in_qq():
        return

    resolved = str(Path(path).resolve())
    ws_resolved = str(Path(workspace_root).resolve())
    run_resolved = str(Path(run_root).resolve())

    # Check if under run_root
    if is_under(resolved, run_resolved):
        raise PathPolicyViolation(
            path=resolved,
            reason="project_write_inside_qonqrete_metadata",
            workspace_root=ws_resolved,
            run_root=run_resolved,
            detail="Path is inside run_root — QonQrete metadata only.",
        )

    # Check if under .qq — regardless of whether .qq exists
    qq_dir = os.path.join(ws_resolved, ".qq")
    if is_under(resolved, qq_dir):
        raise PathPolicyViolation(
            path=resolved,
            reason="project_write_inside_qonqrete_metadata",
            workspace_root=ws_resolved,
            run_root=run_resolved,
            detail="Path is inside .qq metadata directory.",
        )

    # Check if inside workspace_root
    if not is_under(resolved, ws_resolved):
        raise PathPolicyViolation(
            path=resolved,
            reason="project_write_outside_workspace",
            workspace_root=ws_resolved,
            run_root=run_resolved,
            detail="Path is outside workspace_root.",
        )


def assert_command_cwd_allowed(
    cwd: str, workspace_root: str, run_root: str
) -> None:
    """Raise PathPolicyViolation if a command cwd would be in QonQrete metadata.

    Allowed cwd:
      - workspace_root or a subdirectory of workspace_root
    Forbidden cwd:
      - run_root or any subdirectory of run_root
      - .qq or any subdirectory of .qq
      - outside workspace_root (any path not under workspace_root)
    """
    if _allow_writes_in_qq():
        return

    resolved = str(Path(cwd).resolve())
    ws_resolved = str(Path(workspace_root).resolve())
    run_resolved = str(Path(run_root).resolve())

    # Check if under run_root
    if is_under(resolved, run_resolved):
        raise PathPolicyViolation(
            path=resolved,
            reason="command_cwd_inside_qonqrete_metadata",
            workspace_root=ws_resolved,
            run_root=run_resolved,
            detail="Command cwd is inside run_root — QonQrete metadata only.",
        )

    # Check if under .qq — regardless of whether .qq exists
    qq_dir = os.path.join(ws_resolved, ".qq")
    if is_under(resolved, qq_dir):
        raise PathPolicyViolation(
            path=resolved,
            reason="command_cwd_inside_qonqrete_metadata",
            workspace_root=ws_resolved,
            run_root=run_resolved,
            detail="Command cwd is inside .qq metadata directory.",
        )

    # Check if inside workspace_root
    if not is_under(resolved, ws_resolved):
        raise PathPolicyViolation(
            path=resolved,
            reason="command_cwd_outside_workspace",
            workspace_root=ws_resolved,
            run_root=run_resolved,
            detail="Command cwd is outside workspace_root — commands must run inside the project.",
        )


def resolve_project_path(
    relative_or_absolute: str, workspace_root: str, run_root: str
) -> Path:
    """Resolve a project path against workspace_root and validate it.

    Returns the resolved path. Raises PathPolicyViolation if the resolved
    path would violate the workspace/metadata boundary.
    """
    # If absolute, use as-is. Otherwise resolve against workspace_root.
    if os.path.isabs(relative_or_absolute):
        resolved = str(Path(relative_or_absolute).resolve())
    else:
        resolved = str((Path(workspace_root) / relative_or_absolute).resolve())

    assert_project_write_allowed(resolved, workspace_root, run_root)
    return Path(resolved)

# ---------------------------------------------------------------------------
# Metadata sweeper — move QonQrete metadata JSON out of target path
# ---------------------------------------------------------------------------

# QonQrete metadata filenames that must live under run_root, not target_path
_QONQRETE_METADATA_PATTERNS = (
    "inspeqtor_output",
    "qlarifier_output",
    "instruqtor_output",
    "construqtor_output",
    "clarifier_output",
    "instructor_output",
    "agent_output",
    "review_output",
    "briq_output",
)

# Legitimate project JSON files that should NOT be moved
_LEGITIMATE_PROJECT_JSON = frozenset({
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "tsconfig.json", "jsconfig.json", "vite.config.json",
    "site.webmanifest", "manifest.json",
})


def _is_qonqrete_metadata_filename(fname: str) -> bool:
    """Return True if fname matches a QonQrete metadata pattern."""
    if fname in _LEGITIMATE_PROJECT_JSON:
        return False
    basename = os.path.splitext(fname)[0]
    for pattern in _QONQRETE_METADATA_PATTERNS:
        if basename.startswith(pattern):
            return True
    return False


def move_qonqrete_metadata_out_of_target(
    run_root: str, target_path: str, event_log=None, cycle: int = 0,
) -> list:
    """Detect and move QonQrete metadata JSON files from target_path to run_root.

    Returns list of MovedArtifact dicts: {from, to, reason}.

    Does NOT move legitimate project JSON such as:
      package.json, package-lock.json, pnpm-lock.yaml, yarn.lock,
      tsconfig.json, jsconfig.json, vite.config.json,
      site.webmanifest, manifest.json
    """
    moved = []
    if not os.path.isdir(target_path):
        return moved

    # Resolve canonical paths to avoid symlink tricks
    try:
        real_target = str(Path(target_path).resolve())
        real_run = str(Path(run_root).resolve())
    except (ValueError, OSError):
        return moved

    # Do not move anything from run_root itself
    if is_under(real_target, real_run) or real_target == real_run:
        return moved

    dest_base = os.path.join(run_root, "artifacts", "migrated-from-target")
    os.makedirs(dest_base, exist_ok=True)

    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules"}]
        for fname in files:
            full = os.path.join(root, fname)
            # Only handle .json files
            if not fname.endswith(".json"):
                continue
            if not _is_qonqrete_metadata_filename(fname):
                continue

            # Skip files already under run_root
            try:
                real_full = str(Path(full).resolve())
            except (ValueError, OSError):
                continue
            if is_under(real_full, real_run):
                continue

            # Compute relative path from target_path
            rel = os.path.relpath(full, target_path)
            dest = os.path.join(dest_base, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            try:
                import shutil
                shutil.move(full, dest)
            except OSError:
                continue

            moved.append({"from": full, "to": dest, "reason": "qonqrete_metadata_written_to_target"})
            if event_log:
                event_log.emit("metadata.moved_from_target",
                               from_path=full, to_path=dest,
                               reason="qonqrete_metadata_written_to_target",
                               severity="warning",
                               note="New agent receipts should be written directly under run_root; this indicates a prompt or adapter regression.",
                               cycle=cycle)

    return moved
