from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_run_baseline_uses_safe_repo_relative_task_resolution() -> None:
    root_script = _read(WORKSPACE_ROOT / "run_baseline.sh")
    assert root_script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in root_script
    assert 'ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in root_script
    assert '.qonqrete/worqspace/tasq.md' in root_script
    assert '.qonqrete/qonqrete.sh' in root_script
    assert "-f ./tasq-small.md" not in root_script

    script = _read(REPO_ROOT / "tools" / "run_baseline.sh")
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script
    assert 'ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"' in script
    assert '.qonqrete/worqspace/tasq.md' in script
    assert '.qonqrete/qonqrete.sh' in script
    assert "-f ./tasq-small.md" not in script


def test_runtime_release_zip_excludes_common_junk_patterns() -> None:
    script = _read(REPO_ROOT / "tools" / "package_runtime_release.sh")
    for token in (
        "*/.DS_Store",
        "*/._*",
        "*/__MACOSX/*",
        "*.pyc",
        "*/__pycache__/*",
        "*/.gradle/*",
        "*/node_modules/*",
        "*/.git/*",
        "*/.venv/*",
        "*/.test_venv/*",
        "*/.pytest_cache/*",
        "*/.ruff_cache/*",
        "*/.mypy_cache/*",
        "*/.validation-env-cache/*",
        "*/qages/*",
        "*/audit/*",
        "*/qonstructions/*",
        "*/struqture/*",
        "*/vscode-extension/out/*",
    ):
        assert token in script


def test_dockerfile_avoids_nodesource_curl_pipe_bash() -> None:
    dockerfile = _read(REPO_ROOT / "Dockerfile")
    assert "deb.nodesource.com/setup_20.x | bash -" not in dockerfile
    assert "/etc/apt/keyrings/nodesource.gpg" in dockerfile
    assert "node_20.x nodistro main" in dockerfile


def test_runtime_requirements_are_pinned_for_fastapi_stack() -> None:
    requirements = _read(REPO_ROOT / "requirements.txt")
    assert re.search(r"^fastapi==", requirements, flags=re.MULTILINE)
    assert re.search(r"^uvicorn==", requirements, flags=re.MULTILINE)
    assert re.search(r"^httpx==", requirements, flags=re.MULTILINE)


def test_gitignore_covers_release_junk() -> None:
    ignore = _read(REPO_ROOT / ".gitignore")
    for pattern in ("__MACOSX/", ".DS_Store", "._*", "*.pyc", "__pycache__/", ".gradle/", "node_modules/", ".test_venv/"):
        assert pattern in ignore


def _is_forbidden_zip_entry(name: str) -> bool:
    normalized = name.replace("\\", "/")
    base = normalized.rsplit("/", 1)[-1]
    if base == ".DS_Store" or base.startswith("._") or base.endswith(".pyc"):
        return True
    banned_parts = {
        ".git",
        ".venv",
        ".test_venv",
        "node_modules",
        ".gradle",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".validation-env-cache",
        "__MACOSX",
        "qages",
        "audit",
        "qonstructions",
        "struqture",
    }
    parts = [part for part in normalized.split("/") if part]
    if any(part in banned_parts for part in parts):
        return True
    return any(
        parts[index] == "vscode-extension" and parts[index + 1] == "out"
        for index in range(len(parts) - 1)
    )


def test_source_tree_has_no_forbidden_release_junk() -> None:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    offenders: list[str] = []
    for raw in proc.stdout.splitlines():
        if not raw:
            continue
        if not (REPO_ROOT / raw).exists():
            continue
        if _is_forbidden_zip_entry(raw):
            offenders.append(raw)
    assert not offenders, f"forbidden source-tree entries found: {offenders[:20]}"


def test_source_snapshot_generated_zip_has_no_forbidden_entries(tmp_path: Path) -> None:
    script = REPO_ROOT / "tools" / "package_source_snapshot.sh"
    generated_zip = tmp_path / "qonqrete-source.zip"
    version = _read(REPO_ROOT / "VERSION").strip()

    env = os.environ.copy()
    env["OUTPUT_ZIP"] = str(generated_zip)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    proc = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert generated_zip.exists()

    with zipfile.ZipFile(generated_zip, "r") as zf:
        names = set(zf.namelist())
        offenders = [name for name in zf.namelist() if _is_forbidden_zip_entry(name)]
    assert not offenders, f"forbidden source snapshot entries found: {offenders[:20]}"
    assert f"qonqrete-source-v{version}/qonqrete.sh" in names
    assert f"qonqrete-source-v{version}/tools/package_source_snapshot.sh" in names
    assert not any("/.gradle/" in name for name in names)
    assert not any(name.startswith(f"qonqrete-source-v{version}/vscode-extension/out/") for name in names)


def test_runtime_release_generated_zip_has_no_forbidden_entries() -> None:
    if subprocess.run(["which", "zip"], capture_output=True).returncode != 0:
        import pytest
        pytest.skip("zip command not available")
    script = REPO_ROOT / "tools" / "package_runtime_release.sh"
    version = _read(REPO_ROOT / "VERSION").strip()
    versioned_zip = REPO_ROOT / f"qonqrete-v{version}.zip"
    sha_file = REPO_ROOT / f"qonqrete-v{version}-SHA256.txt"
    generated_zip = REPO_ROOT / "generated.zip"

    env = os.environ.copy()
    env["ALLOW_DIRTY_RELEASE"] = "1"
    env["OUTPUT_ZIP"] = "generated.zip"

    try:
        proc = subprocess.run(
            ["bash", str(script)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
        assert generated_zip.exists()

        with zipfile.ZipFile(generated_zip, "r") as zf:
            names = set(zf.namelist())
            offenders = [name for name in zf.namelist() if _is_forbidden_zip_entry(name)]
        assert not offenders, f"forbidden packaged entries found: {offenders[:20]}"
        assert f"qonqrete-v{version}/qrane/qrane.py" in names
        assert f"qonqrete-v{version}/worqer/qonfirmer.py" in names
        assert f"qonqrete-v{version}/tests/test_release_hygiene_regressions.py" in names
        assert f"qonqrete-v{version}/qrane.py" not in names
    finally:
        for path in (generated_zip, versioned_zip, sha_file):
            if path.exists():
                path.unlink()
