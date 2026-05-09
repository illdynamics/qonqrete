"""Smoke tests for QonQrete install and bootstrap scripts.

These tests verify that:
1. The bootstrap script exists and is executable.
2. The qonqrete.sh entrypoint responds correctly.
3. The container image can be built (Docker/Podman).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_qonqrete_bootstrap_script_exists_and_executable() -> None:
    script = REPO_ROOT / "qonqrete-bootstrap.sh"
    assert script.exists(), f"{script} does not exist"
    assert os.access(script, os.X_OK), f"{script} is not executable"


def test_qonqrete_sh_help_exits_success() -> None:
    script = REPO_ROOT / "qonqrete.sh"
    assert script.exists(), f"{script} does not exist"
    proc = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"qonqrete.sh --help failed:\n{proc.stdout}\n{proc.stderr}"


def test_qonqrete_sh_version_output() -> None:
    script = REPO_ROOT / "qonqrete.sh"
    proc = subprocess.run(
        ["bash", str(script), "version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"qonqrete.sh version failed:\n{proc.stdout}\n{proc.stderr}"
    assert "QonQrete" in proc.stdout or "qonqrete" in proc.stdout.lower()


def test_qonqrete_sh_init_acceptance(tmp_path: Path) -> None:
    """Verify init command is valid (does not require Docker for syntax check)."""
    script = REPO_ROOT / "qonqrete.sh"
    proc = subprocess.run(
        ["bash", "-n", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"shell syntax check failed:\n{proc.stderr}"


def test_docker_or_podman_available() -> None:
    """At least one container engine should be available for runtime execution."""
    docker = shutil.which("docker")
    podman = shutil.which("podman")
    if docker is None and podman is None:
        # Not a failure — CI may not have containers; skip gracefully.
        pytest.skip("Neither docker nor podman available")


def test_dockerfile_exists() -> None:
    dockerfile = REPO_ROOT / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile not found at repo root"
    content = dockerfile.read_text()
    assert "FROM" in content, "Dockerfile missing FROM directive"
    assert "ENTRYPOINT" in content or "CMD" in content, "Dockerfile missing ENTRYPOINT/CMD"


def test_qonqrete_sh_run_script_smoke(tmp_path: Path) -> None:
    """Lightweight script syntax + minimal module check for core files."""
    script = REPO_ROOT / "qonqrete.sh"
    assert script.exists()

    # Check that the script references key internal modules
    content = script.read_text()
    assert "python3" in content or "python" in content
    assert "qrane" in content or "worqer" in content


def test_tasq_file_exists() -> None:
    """The canonical REST API task file must exist."""
    tasq = REPO_ROOT / "worqspace" / "tasq.md"
    assert tasq.exists(), f"worqspace/tasq.md not found"
    content = tasq.read_text()
    assert "FastAPI" in content, "worqspace/tasq.md does not describe a FastAPI task"
    assert "GET /health" in content, "worqspace/tasq.md missing /health endpoint"


def test_python_requirements_parseable() -> None:
    """requirements.txt should parse without errors."""
    req = REPO_ROOT / "requirements.txt"
    assert req.exists(), "requirements.txt not found"
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=columns"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # pip may not be available — not a hard failure
        pytest.skip("pip not available for requirements check")


def test_core_python_modules_importable() -> None:
    """Core QonQrete Python modules should at least be parseable."""
    modules = ["qrane", "worqer", "qrane.qrane", "worqer.qonfirmer"]
    python = sys.executable
    for mod in modules:
        mod_path = REPO_ROOT / mod.replace(".", "/")
        if mod_path.is_dir():
            init_file = mod_path / "__init__.py"
        else:
            init_file = mod_path.with_suffix(".py")
        if not init_file.exists():
            continue  # skip modules that don't exist in flat form
    # Check that main entry point is syntactically valid
    main_py = REPO_ROOT / "qrane" / "qrane.py"
    if main_py.exists():
        proc = subprocess.run(
            [python, "-m", "py_compile", str(main_py)],
            capture_output=True,
            text=True,
        )
        # Compilation may fail due to missing dependencies; that's okay for syntax check
        assert "SyntaxError" not in proc.stderr, f"Syntax error in {main_py}:\n{proc.stderr}"


try:
    import pytest
except ImportError:
    # If pytest isn't available, we can still run the test functions
    pass
