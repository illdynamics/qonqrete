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
    lock_path = cache_root / f"{m_hash}.lock"
    
    timeout = int(os.environ.get("QONQ_BOOTSTRAP_TIMEOUT", 600))
    
    # Path handling for both repo-native and containerized modes
    venv_python = venv_dir / "bin" / "python"
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    complete_marker = venv_dir / ".bootstrap_complete"

    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        
        # v1.4.0: Harden with file lock and timeouts
        import fcntl
        with open(lock_path, "w") as lock_file:
            try:
                # Non-blocking attempt first to avoid silent hang
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                # Another process is provisioning, wait for it
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                
            # Revalidate after lock acquisition
            if venv_python.exists() and complete_marker.exists():
                return str(venv_python), None

            if venv_dir.exists():
                # Stale/partial cache entries are unsafe to reuse.
                shutil.rmtree(venv_dir, ignore_errors=True)

            venv_dir.mkdir(parents=True, exist_ok=True)
            
            # Common pip safety flags
            pip_install = [str(venv_python), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--quiet"]

            # 1. Create venv
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True, capture_output=True, text=True, timeout=timeout
            )
            
            # 2. Update pip
            subprocess.run(
                pip_install + ["--upgrade", "pip"],
                check=True, capture_output=True, text=True, timeout=timeout
            )
            
            # 3. Install found manifests
            if (qodeyard_path / "requirements.txt").is_file():
                subprocess.run(
                    pip_install + ["-r", "requirements.txt"],
                    cwd=str(qodeyard_path),
                    check=True, capture_output=True, text=True, timeout=timeout
                )
            
            if (qodeyard_path / "pyproject.toml").is_file():
                subprocess.run(
                    pip_install + ["."],
                    cwd=str(qodeyard_path),
                    check=True, capture_output=True, text=True, timeout=timeout
                )
            elif (qodeyard_path / "setup.py").is_file() or (qodeyard_path / "setup.cfg").is_file():
                subprocess.run(
                    pip_install + ["."],
                    cwd=str(qodeyard_path),
                    check=True, capture_output=True, text=True, timeout=timeout
                )

            complete_marker.write_text("ok\n", encoding="utf-8")
            return str(venv_python), None
        
    except subprocess.TimeoutExpired:
        return None, f"Python bootstrap timed out after {timeout}s"
    except subprocess.CalledProcessError as e:
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        err_msg = f"Python bootstrap failed during dependency installation.\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
        return None, err_msg
    except Exception as e:
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        return None, f"Python bootstrap failed: {str(e)}"
