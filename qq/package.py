"""
Qq release packaging — pure Python, no external shell script needed.

Usage:
    python -m qq package            # build release zip
    python -m qq package --check    # validate source tree is package-clean
    python -m qq package --check-upload-tree  # stricter: also fail on .git/
    python -m qq package --check-archive <zip>   # validate an archive
    python -m qq package --check-uploaded-zip <zip>  # same as --check-archive
    python -m qq package --final    # build and print final artifact path
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile

# Prevent __pycache__ creation during checks
sys.dont_write_bytecode = True

# Project root is one level above qq/
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), ".."))


def get_version() -> str:
    try:
        from qq import __version__
        return __version__
    except ImportError:
        return "2.0.0"


# Patterns for files/dirs to EXCLUDE from the release archive
_EXCLUDE_PATTERNS = [
    r"\.git/",
    r"__MACOSX/",
    r"\.DS_Store",
    r"\._.*",
    r"__pycache__/",
    r"\.pyc$",
    r"\.pytest_cache/",
    r"\.ruff_cache/",
    r"\.mypy_cache/",
    r"qq/tui/target/",
    r"qq/web/target/",
    r"(^|/)target/",
    r"qonqrete_cybersquid",
    r"\.qq/runs/",
    r"\.qq/worktrees/",
    r"\.qq/image-tests/",
    r"\.codeseeq/",
    r"\.venv/",
    r"^ide\.md$",
    r"\.env$",
    r"dist/",
    r"\.hypothesis/",
    r"\.zip$",
    # Build artifact directories
    r"node_modules/",
    r"Cargo\.lock$",
    r"pnpm-lock\.yaml$",
    r"package-lock\.json$",
    # Rust build artifacts
    r"\.rlib$",
    r"\.rmeta$",
    r"\.d$",
    # Prompt scratch files
    r"prompt[a-z]*[0-9]*\.md$",
    r"prompt[a-z0-9-]*\.md$",
    r"prompt[a-z]*\.md$",  # e.g. promptje.md
    r"prompt[a-z0-9-]*\.md$",  # e.g. prompt-images.md
    r"\.qq_artifacts/",
    # Generated metadata — must not be shipped
    r"\.egg-info/",
    r"\*\.egg-info/",
]

# Banned names in source-tree check (TREE-ONLY — .git is OK in dev checkout)
_TREE_BANNED_DIRS = [
    "__MACOSX", ".qq_artifacts",
]
_TREE_BANNED_FILES_STARTSWITH = ["._", ".DS_Store"]
_TREE_BANNED_FILES_ENDSWITH = [".pyc"]
_TREE_BANNED_DIRS_CONTAINS = [
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".hypothesis",
]
_TREE_BANNED_STRAY = [
    ".env",  # in repo root
]

# Files that match prompt scratch patterns and should not exist in source tree
_TREE_BANNED_FILES_REGEX = [
    re.compile(r"^prompt[a-z]*[0-9]*\.md$"),
]

# Extra dirs that are banned in upload-tree mode
_TREE_UPLOAD_BANNED_DIRS = [
    ".git",
]

# Banned in archive (MUST NOT appear in any zip entry path component)
_ARCHIVE_BANNED_NAMES = {
    ".git", "__MACOSX", ".DS_Store", ".env", ".codeseeq", ".venv",
    ".qq", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".hypothesis", ".egg-info", "*.egg-info",
    "qq.egg-info",
}

# Banned basename patterns in archive
_ARCHIVE_BANNED_BASENAMES = [
    r"\._.*",       # AppleDouble
    r".*\.pyc$",    # bytecode
    r".*\.zip$",    # nested zip
    r"prompt[a-z]*[0-9]*\.md$",
    r"prompt[a-z0-9-]*\.md$",
    r"prompt[a-z]*[0-9]*\.md$",
    r"prompt[a-z0-9-]*\.md$",  # all prompt scratch files
    r".*\.egg-info/.*",   # generated metadata
    r".*egg-info/PKG-INFO",  # stale version metadata
]

# Directories that must NOT exist under .qq/ in an archive
_ARCHIVE_BANNED_QQ_SUBDIRS = [
    "runs", "worktrees", "artifacts", "image-tests",
]


def _should_exclude(rel_path: str) -> bool:
    """Check if a relative path should be excluded from the release."""
    for pat in _EXCLUDE_PATTERNS:
        if re.search(pat, rel_path):
            return True
    return False


def check_tree(root: str = None, upload_mode: bool = False) -> int:
    """Validate the source tree is package-clean. Returns exit code."""
    if root is None:
        root = _PROJECT_ROOT
    # Clean pycache first — importing qq creates it
    _clean_pycache(root)
    print("Checking source tree...")
    issues = 0

    root_abs = os.path.abspath(root)

    # Check for banned top-level dirs
    banned_dirs = list(_TREE_BANNED_DIRS)
    if upload_mode:
        banned_dirs.extend(_TREE_UPLOAD_BANNED_DIRS)
    for d in banned_dirs:
        full = os.path.join(root_abs, d)
        if os.path.isdir(full):
            print(f"  FAIL: {d}/ directory exists in source tree")
            issues += 1

    # Walk the tree (skip .git unless in upload_mode)
    for dirpath, dirnames, filenames in os.walk(root_abs):
        rel_dir = os.path.relpath(dirpath, root_abs)

        # Skip .git entirely (unless upload_mode)
        if not upload_mode and ".git" in dirpath.split(os.sep):
            continue

        # Check directory names for banned patterns
        for dname in dirnames:
            for banned_contains in _TREE_BANNED_DIRS_CONTAINS:
                if banned_contains in dname:
                    print(f"  FAIL: {banned_contains}/ directory exists at {os.path.join(rel_dir, dname)}")
                    issues += 1
                    break

        # Check files
        for fname in filenames:
            rel_path = os.path.join(rel_dir, fname) if rel_dir else fname

            # Check starts-with patterns
            for prefix in _TREE_BANNED_FILES_STARTSWITH:
                if fname.startswith(prefix):
                    print(f"  FAIL: {prefix}* file exists at {rel_path}")
                    issues += 1

            # Check ends-with patterns
            for suffix in _TREE_BANNED_FILES_ENDSWITH:
                if fname.endswith(suffix):
                    print(f"  FAIL: {suffix} file exists at {rel_path}")
                    issues += 1

            # Check regex patterns (prompt scratch files)
            for pat in _TREE_BANNED_FILES_REGEX:
                if pat.match(fname):
                    print(f"  FAIL: prompt scratch file exists at {rel_path}")
                    issues += 1

            # Check for nested zip files outside dist/
            if fname.endswith(".zip"):
                if not rel_path.startswith("dist/"):
                    print(f"  FAIL: nested .zip at {rel_path} (outside dist/)")
                    issues += 1

    # Check for .qq subdirectories that shouldn't be in source tree
    for subdir in ["runs", "worktrees"]:
        full = os.path.join(root_abs, ".qq", subdir)
        if os.path.isdir(full):
            print(f"  FAIL: .qq/{subdir}/ directory exists in source tree")
            issues += 1

    # Check for stray files in root
    for fname in _TREE_BANNED_STRAY:
        if os.path.exists(os.path.join(root_abs, fname)):
            print(f"  FAIL: {fname} file exists in source tree")
            issues += 1

    # Check for .codeseeq/
    codeseeq_dir = os.path.join(root_abs, ".codeseeq")
    if os.path.isdir(codeseeq_dir):
        print("  FAIL: .codeseeq/ directory exists in source tree")
        issues += 1

    # Check for .qq_artifacts/
    arts_dir = os.path.join(root_abs, ".qq_artifacts")
    if os.path.isdir(arts_dir):
        print("  FAIL: .qq_artifacts/ directory exists in source tree")
        issues += 1

    # Check for .egg-info directories and stale PKG-INFO versions
    for dirpath, dirnames, filenames in os.walk(root_abs):
        for dname in list(dirnames):
            if dname.endswith(".egg-info"):
                egg_path = os.path.join(dirpath, dname)
                rel = os.path.relpath(egg_path, root_abs)
                print(f"  FAIL: *.egg-info/ directory exists at {rel}")
                issues += 1

                # Also check for stale version in PKG-INFO
                pkg_info = os.path.join(egg_path, "PKG-INFO")
                if os.path.isfile(pkg_info):
                    try:
                        with open(pkg_info) as f:
                            for line in f:
                                if line.startswith("Version:"):
                                    egg_ver = line.split(":", 1)[1].strip()
                                    if egg_ver != get_version():
                                        print(f"  FAIL: stale version in {dname}/PKG-INFO: "
                                              f"{egg_ver} (expected {get_version()})")
                                        issues += 1
                                    break
                    except Exception:
                        pass

    # Final pycache cleanup to prevent pycache after check
    _clean_pycache(root)

    if issues > 0:
        print(f"FAIL: {issues} blocking issue(s) found.")
        return 1
    print("Source tree check passed.")
    return 0


def check_archive(zip_path: str) -> int:
    """Validate a release zip archive. Returns exit code."""
    print(f"Checking archive: {zip_path}")
    if not os.path.isfile(zip_path):
        print(f"FAIL: archive not found: {zip_path}")
        return 1

    issues = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Check exactly one top-level directory
        top_dirs = set()
        for name in names:
            parts = name.split("/")
            if parts[0]:
                top_dirs.add(parts[0])
        if len(top_dirs) != 1:
            print(f"  FAIL: archive must have exactly one top-level "
                  f"directory, found ({len(top_dirs)}): {top_dirs}")
            issues += 1
        else:
            top = list(top_dirs)[0]
            print(f"  Top-level dir: {top}")

        # Check every entry
        for name in names:
            parts = name.split("/")
            basename = os.path.basename(name) if name.endswith("/") else parts[-1]

            # Check each path component for banned names
            for part in parts:
                if part in _ARCHIVE_BANNED_NAMES:
                    print(f"  BANNED: '{part}' found in archive "
                          f"(path: {name})")
                    issues += 1
                    break

            # Check basename against banned patterns
            for pat in _ARCHIVE_BANNED_BASENAMES:
                if re.match(pat, basename):
                    print(f"  BANNED: pattern '{pat}' matched: {name}")
                    issues += 1

            # Check for .qq subdirectories in archive
            for i, part in enumerate(parts):
                if part == ".qq" and i + 1 < len(parts):
                    next_part = parts[i + 1]
                    if next_part in _ARCHIVE_BANNED_QQ_SUBDIRS:
                        print(f"  BANNED: .qq/{next_part}/ in archive: {name}")
                        issues += 1

            # Check for nested zip
            if name.endswith(".zip"):
                print(f"  BANNED: nested .zip in archive: {name}")
                issues += 1

        # v2.0.0 (since v0.2.20): Verify scripts/verify.sh has executable bits in archive metadata
        verify_entries = [n for n in names if n.endswith("/scripts/verify.sh")]
        if verify_entries:
            info = zf.getinfo(verify_entries[0])
            mode = (info.external_attr >> 16) & 0o777
            if not (mode & 0o111):
                print(f"  FAIL: scripts/verify.sh in archive must have "
                      f"executable bits, got mode {oct(mode)}")
                issues += 1
            else:
                print(f"  scripts/verify.sh archive mode: {oct(mode)} (OK)")
        else:
            print("  WARNING: scripts/verify.sh not found in archive")

    if issues > 0:
        print(f"FAIL: {issues} issue(s) found in archive.")
        return 1
    print("Archive is clean.")
    return 0


def _clean_pycache(root: str) -> None:
    """Remove all __pycache__ directories and .pyc files under root.
    Also remove .hypothesis, .pytest_cache, .ruff_cache, .mypy_cache."""
    for dirpath, dirnames, filenames in os.walk(root):
        if '__pycache__' in dirnames:
            shutil.rmtree(os.path.join(dirpath, '__pycache__'), ignore_errors=True)
        for fname in filenames:
            if fname.endswith('.pyc'):
                os.remove(os.path.join(dirpath, fname))
    for d in ('.hypothesis', '.pytest_cache', '.ruff_cache', '.mypy_cache'):
        p = os.path.join(root, d)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


def build(root: str = None, dist_dir: str = None) -> str:
    """Build the release zip. Returns the path to the created zip."""
    if root is None:
        root = _PROJECT_ROOT
    if dist_dir is None:
        dist_dir = os.path.join(root, "dist")

    # Clean pycache before build so check_tree passes
    _clean_pycache(root)

    version = get_version()
    name = f"qonqrete-qq-v{version}"
    print(f"Building {name}...")

    os.makedirs(dist_dir, exist_ok=True)

    # Build into a temp dir first, then zip
    build_dir = os.path.join(dist_dir, name)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    # Copy files, excluding patterns
    for dirpath, dirnames, filenames in os.walk(root):
        # Compute relative path
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""

        # Filter out excluded dirs
        dirnames[:] = [
            d for d in dirnames
            if not _should_exclude(
                os.path.join(rel_dir, d) + "/" if rel_dir
                else d + "/")
        ]

        for fname in filenames:
            rel_path = os.path.join(rel_dir, fname) if rel_dir else fname
            if _should_exclude(rel_path):
                continue

            src = os.path.join(dirpath, fname)
            dst_dir = os.path.join(build_dir, rel_dir) if rel_dir else build_dir
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(dst_dir, fname))

    # Verify scripts/package.sh was included
    pkg_sh = os.path.join(build_dir, "scripts", "package.sh")
    if not os.path.exists(pkg_sh):
        print("  WARNING: scripts/package.sh not included in build")

    # Force executable mode on known shell scripts before packaging.
    # Source trees extracted from zips may lose executable bits.
    for dirpath, dirnames, filenames in os.walk(build_dir):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, build_dir)
            if (fname.endswith(".sh")
                    and (rel.startswith("scripts/") or fname == "install.sh")):
                os.chmod(fpath, 0o755)

    # Create zip
    zip_path = os.path.join(dist_dir, f"{name}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(build_dir):
            arc_dir = os.path.relpath(dirpath, dist_dir)
            for fname in filenames:
                file_path = os.path.join(dirpath, fname)
                arc_name = os.path.join(arc_dir, fname)
                # Filter out anything we don't want (double-check)
                if _should_exclude(arc_name):
                    continue

                # Preserve executable mode for scripts
                src_mode = os.stat(file_path).st_mode
                is_executable = (src_mode & 0o111) != 0
                # Build ZipInfo with external_attr preserving execute bits
                info = zipfile.ZipInfo(arc_name)
                info.external_attr = (src_mode & 0xFFFF) << 16  # Unix permissions
                with open(file_path, "rb") as src_fh:
                    data = src_fh.read()
                zf.writestr(info, data)

    # Clean up build dir
    shutil.rmtree(build_dir, ignore_errors=True)

    # Final pycache cleanup
    _clean_pycache(root)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Created: {zip_path} ({size_mb:.1f} MB)")

    # Validate the archive
    result = check_archive(zip_path)
    if result != 0:
        sys.exit(result)

    return zip_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="qq-package",
        description="Build and validate Qq release archives",
    )
    parser.add_argument("--check", action="store_true",
                        help="Validate the source tree is package-clean")
    parser.add_argument("--check-upload-tree", action="store_true",
                        help="Stricter tree check (also fails on .git/ and dist/*.zip)")
    parser.add_argument("--check-archive", default=None, metavar="ZIP",
                        help="Validate a specific release zip")
    parser.add_argument("--check-uploaded-zip", default=None, metavar="ZIP",
                        help="Validate an uploaded zip (alias for --check-archive)")
    parser.add_argument("--final", action="store_true",
                        help="Build and print the final artifact path prominently")
    parser.add_argument("--root", default=None,
                        help="Project root (default: auto-detect)")
    parser.add_argument("--dist-dir", default=None,
                        help="Output directory for the zip")

    args = parser.parse_args(argv)

    root_override = args.root or _PROJECT_ROOT
    dist_dir = args.dist_dir or os.path.join(root_override, "dist")

    if args.check:
        sys.exit(check_tree(root_override))
    elif args.check_upload_tree:
        sys.exit(check_tree(root_override, upload_mode=True))
    elif args.check_archive:
        sys.exit(check_archive(args.check_archive))
    elif args.check_uploaded_zip:
        sys.exit(check_archive(args.check_uploaded_zip))
    elif args.final:
        # Build and print final message prominently
        zip_path = build(root_override, dist_dir)
        print()
        print("=" * 60)
        print(f"FINAL ARTIFACT: {zip_path}")
        print("Upload this file directly. Do not zip the source folder.")
        print("=" * 60)
        return 0
    else:
        # Default: build
        check_tree(root_override)
        zip_path = build(root_override, dist_dir)
        print()
        print("=" * 60)
        print(f"FINAL ARTIFACT: {zip_path}")
        print("Upload this file directly. Do not zip the source folder.")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    main()
