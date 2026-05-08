#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="$(tr -d '[:space:]' < VERSION)"
if [[ -z "$VERSION" ]]; then
  echo "FATAL: VERSION file is empty" >&2
  exit 1
fi

OUTPUT_ZIP="${OUTPUT_ZIP:-qonqrete-source-v${VERSION}.zip}"
PYTHON_BIN="${PYTHON:-python3}"

export QONQ_SOURCE_ROOT="$ROOT_DIR"
export QONQ_SOURCE_VERSION="$VERSION"
export QONQ_SOURCE_OUTPUT="$OUTPUT_ZIP"

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import os
import stat
import sys
import zipfile
from pathlib import Path


ROOT = Path(os.environ["QONQ_SOURCE_ROOT"]).resolve()
VERSION = os.environ["QONQ_SOURCE_VERSION"]
OUTPUT = Path(os.environ["QONQ_SOURCE_OUTPUT"])
if not OUTPUT.is_absolute():
    OUTPUT = ROOT / OUTPUT
OUTPUT = OUTPUT.resolve()
TMP_OUTPUT = OUTPUT.with_name(f".{OUTPUT.name}.tmp")
ZIP_PREFIX = f"qonqrete-source-v{VERSION}"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

FORBIDDEN_DIR_NAMES = {
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
FORBIDDEN_FILE_NAMES = {".DS_Store"}
FORBIDDEN_FILE_PREFIXES = ("._",)
FORBIDDEN_FILE_SUFFIXES = (".pyc", ".gradle.kts")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _has_vscode_out(parts: tuple[str, ...]) -> bool:
    return any(
        parts[index] == "vscode-extension" and parts[index + 1] == "out"
        for index in range(len(parts) - 1)
    )


def is_forbidden_rel(rel: Path, *, is_dir: bool = False) -> bool:
    parts = tuple(part for part in rel.parts if part not in ("", "."))
    if not parts:
        return False
    if ".qonqrete" in parts and ".git" in parts:
        return True
    if any(part in FORBIDDEN_DIR_NAMES for part in parts):
        return True
    if _has_vscode_out(parts):
        return True
    if is_dir:
        return False
    name = parts[-1]
    if name in FORBIDDEN_FILE_NAMES:
        return True
    if any(name.startswith(prefix) for prefix in FORBIDDEN_FILE_PREFIXES):
        return True
    if any(name.endswith(suffix) for suffix in FORBIDDEN_FILE_SUFFIXES):
        return True
    return False


def is_forbidden_zip_entry(name: str) -> bool:
    parts = tuple(part for part in name.replace("\\", "/").split("/") if part)
    if parts and parts[0] == ZIP_PREFIX:
        parts = parts[1:]
    if not parts:
        return False
    return is_forbidden_rel(Path(*parts), is_dir=name.endswith("/"))


def should_skip_path(path: Path, *, is_dir: bool = False) -> bool:
    if path == OUTPUT or path == TMP_OUTPUT:
        return True
    if _is_relative_to(path, ROOT):
        rel = path.relative_to(ROOT)
        return is_forbidden_rel(rel, is_dir=is_dir)
    return True


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(ROOT):
        root_path = Path(root)
        dirs[:] = [
            dirname
            for dirname in sorted(dirs)
            if not should_skip_path(root_path / dirname, is_dir=True)
        ]
        for filename in sorted(filenames):
            path = root_path / filename
            if should_skip_path(path):
                continue
            files.append(path)
    files.sort(key=lambda path: path.relative_to(ROOT).as_posix())
    return files


def add_file(zf: zipfile.ZipFile, path: Path) -> None:
    rel = path.relative_to(ROOT).as_posix()
    arcname = f"{ZIP_PREFIX}/{rel}"
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if not mode:
        mode = 0o644
    info = zipfile.ZipInfo(arcname, FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = mode << 16
    with path.open("rb") as handle:
        zf.writestr(info, handle.read())


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if TMP_OUTPUT.exists():
        TMP_OUTPUT.unlink()
    if OUTPUT.exists():
        OUTPUT.unlink()

    with zipfile.ZipFile(TMP_OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in iter_source_files():
            add_file(zf, path)

    with zipfile.ZipFile(TMP_OUTPUT, "r") as zf:
        offenders = [name for name in zf.namelist() if is_forbidden_zip_entry(name)]
    if offenders:
        TMP_OUTPUT.unlink(missing_ok=True)
        print("FATAL: source snapshot contains forbidden entries:", file=sys.stderr)
        for offender in offenders[:50]:
            print(f"  {offender}", file=sys.stderr)
        return 2

    TMP_OUTPUT.replace(OUTPUT)
    print(f"Wrote {OUTPUT}")
    return 0


raise SystemExit(main())
PY
