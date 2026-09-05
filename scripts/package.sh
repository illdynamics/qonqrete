#!/usr/bin/env bash
set -euo pipefail

# Qq release packaging script — thin wrapper around the Python packager.
# Preferred usage: python3 -m qq package
# This script exists for compatibility and for inclusion in the release archive.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

exec python3 -m qq.package "$@"
