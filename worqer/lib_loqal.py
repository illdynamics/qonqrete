#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

DEFAULT_JAIL = Path("/qonq")
MAX_GENERATED_FILE_SIZE = 1024 * 1024


class SecurityError(RuntimeError):
    pass


def ensure_qontract_present(worqspace_root: Path) -> tuple[Path, Path]:
    qontract_dir = Path(worqspace_root) / "qontract.d"
    md_path = qontract_dir / "qontract.md"
    json_path = qontract_dir / "qontract.json"

    missing: list[str] = []
    if not md_path.exists():
        missing.append(str(md_path))
    if not json_path.exists():
        missing.append(str(json_path))

    if missing:
        raise RuntimeError(
            "FAIL-FAST: Contract files missing — pipeline cannot proceed.\n"
            f"  Missing: {', '.join(missing)}\n"
            f"  Expected location: {qontract_dir}/\n"
            "  Action: Ensure cycle 1 InstruQtor has run and generated the contract.\n"
            "  The QONTRACT is mandatory for all cycles > 1."
        )

    return md_path, json_path


def get_jail_path() -> Path:
    return Path(os.environ.get("QONQ_WORKSPACE", str(DEFAULT_JAIL)))


def is_path_within_jail(path: Path, jail: Optional[Path] = None) -> bool:
    real_jail = Path(os.path.realpath(str(jail or get_jail_path())))
    try:
        real_path = Path(os.path.realpath(str(path)))
        real_path.relative_to(real_jail)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def validate_path(path: Path, jail: Optional[Path] = None, must_exist: bool = False) -> Path:
    jail_path = Path(jail) if jail is not None else get_jail_path()
    try:
        resolved = Path(os.path.realpath(str(path)))
        resolved_jail = Path(os.path.realpath(str(jail_path)))
    except (OSError, RuntimeError) as exc:
        raise SecurityError(f"Cannot resolve path: {path}") from exc

    try:
        resolved.relative_to(resolved_jail)
    except ValueError as exc:
        raise SecurityError(f"Path outside jail: {path}") from exc

    if must_exist and not resolved.exists():
        raise SecurityError(f"Path does not exist: {path}")

    return resolved


def safe_write_file(
    path: Path,
    content: str,
    max_size: int = MAX_GENERATED_FILE_SIZE,
    jail: Optional[Path] = None,
) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > max_size:
        raise SecurityError(f"Content exceeds size limit: {len(encoded)} > {max_size}")

    validated = validate_path(path, jail=jail)
    validated.parent.mkdir(parents=True, exist_ok=True)

    temp_path = validated.with_name(validated.name + ".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_path, validated)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def safe_read_file(
    path: Path,
    max_size: int = MAX_GENERATED_FILE_SIZE,
    jail: Optional[Path] = None,
) -> str:
    validated = validate_path(path, jail=jail, must_exist=True)
    file_size = validated.stat().st_size
    if file_size > max_size:
        raise SecurityError(f"File exceeds size limit: {file_size} > {max_size}")

    with open(validated, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


__all__ = [
    "DEFAULT_JAIL",
    "MAX_GENERATED_FILE_SIZE",
    "SecurityError",
    "ensure_qontract_present",
    "get_jail_path",
    "is_path_within_jail",
    "validate_path",
    "safe_write_file",
    "safe_read_file",
]
