#!/usr/bin/env python3
"""Verify a QonQrete release zip contains no forbidden paths."""
import sys
import zipfile

FORBIDDEN = [
    '__MACOSX/', '.DS_Store', '._',
    '__pycache__/', '.pyc',
    '.pytest_cache/', '.ruff_cache/', '.mypy_cache/',
    '.gradle/', '.git/',
    'node_modules/', '.venv/', '.test_venv/',
    '.validation-env-cache/',
    'vscode-extension/out/',
    'worqspace/qonstructions/', 'worqspace/audit/',
    'worqspace/qage_', 'worqspace/codeseeq-smoke-logs/',
    'qages/', 'struqture/', 'audit/', 'qonstructions/',
    'playwright_browser.py',
    'test_browser_validation_benchmarks.py',
    'benchmarks/recipe_planner/',
    'masterwonqprompt.md',
    '.codeseeq/',
    'sqrapyard/',
]

def verify(zip_path: str) -> bool:
    ok = True
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = zf.namelist()
        for name in names:
            for bad in FORBIDDEN:
                if bad in name:
                    print(f"FORBIDDEN: {name}  (matches pattern: {bad})")
                    ok = False
    if ok:
        print(f"PASS: {zip_path} is clean  ({len(names)} entries)")
    else:
        print(f"FAIL: {zip_path} contains forbidden paths")
    return ok

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python tools/verify_zip_hygiene.py <release.zip>")
        sys.exit(1)
    sys.exit(0 if verify(sys.argv[1]) else 1)
