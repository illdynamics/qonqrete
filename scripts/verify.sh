#!/usr/bin/env bash
set -euo pipefail

# Qq verification script — thin Python wrapper.
# All acceptance checks are orchestrated by qq.verify (Python subprocess
# management with deterministic process-tree cleanup).
# Usage: bash scripts/verify.sh [ARGS...]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

python3 -m qq.verify "$@"
