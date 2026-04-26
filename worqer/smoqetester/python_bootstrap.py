# worqer/smoqetester/python_bootstrap.py
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_manifest_hash(qodeyard_path: Path) -> str | None:
    """Calculates a hash of all Python dependency manifests in the qodeyard."""
    manifest_names = ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"]
    contents = []
    for name in manifest_names:
        p = qodeyard_path / name
        if p.is_file():
            try:
                contents.append(f"{name}:{p.read_text(encoding='utf-8', errors='ignore')}")
            except Exception:
                continue
    
    if not contents:
        return None

    # Salt the cache key with runtime identity to prevent cross-runtime reuse.
    contents.append(f"runtime_version:{sys.version}")
    contents.append(f"runtime_platform:{sys.platform}")

    return hashlib.sha256("\n---\n".join(contents).encode("utf-8")).hexdigest()


def provision_validation_env(worqspace_root: Path, qodeyard_path: Path) -> tuple[str | None, str | None]:
    """
    Provisions a task-local Python validation environment if manifests exist.
    Returns (python_bin_path, error_message).
    """
    m_hash = get_manifest_hash(qodeyard_path)
    if not m_hash:
        return None, None
    
    cache_root = worqspace_root / ".validation-env-cache" / "python"
    venv_dir = cache_root / m_hash
    
    # Path handling for both repo-native and containerized modes
    # In containerized mode, bin/python is standard.
    # On Windows (less likely here but good to be safe), it might be Scripts/python.exe
    venv_python = venv_dir / "bin" / "python"
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    complete_marker = venv_dir / ".bootstrap_complete"

    if venv_python.exists() and complete_marker.exists():
        return str(venv_python), None
    if venv_dir.exists():
        # Stale/partial cache entries are unsafe to reuse.
        shutil.rmtree(venv_dir, ignore_errors=True)

    # Provision new venv
    try:
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Create venv
        print(f"[DEBUG] Creating venv in {venv_dir} using {sys.executable}", flush=True)
        cp = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"[DEBUG] venv created. stdout: {cp.stdout}, stderr: {cp.stderr}", flush=True)
        
        # Install dependencies
        # 1. Update pip
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
            text=True
        )
        
        # 2. Install found manifests
        if (qodeyard_path / "requirements.txt").is_file():
            print(f"[DEBUG] Installing requirements.txt", flush=True)
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=str(qodeyard_path),
                check=True,
                capture_output=True,
                text=True
            )
        
        if (qodeyard_path / "pyproject.toml").is_file():
            print(f"[DEBUG] Installing pyproject.toml", flush=True)
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "."],
                cwd=str(qodeyard_path),
                check=True,
                capture_output=True,
                text=True
            )
        elif (qodeyard_path / "setup.py").is_file() or (qodeyard_path / "setup.cfg").is_file():
            print(f"[DEBUG] Installing setup.py/cfg", flush=True)
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "."],
                cwd=str(qodeyard_path),
                check=True,
                capture_output=True,
                text=True
            )

        complete_marker.write_text("ok\n", encoding="utf-8")
        return str(venv_python), None
        
    except subprocess.CalledProcessError as e:
        # Cleanup failed venv attempt
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        
        err_msg = f"Python bootstrap failed during dependency installation.\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
        return None, err_msg
    except Exception as e:
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        return None, f"Python bootstrap failed: {str(e)}"
