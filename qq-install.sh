#!/usr/bin/env bash
set -euo pipefail

# qq-install.sh — one-shot QonQrete installer from a fresh clone
#
# Usage:
#   git clone <qonqrete-repo>
#   cd qonqrete
#   ./qq-install.sh
#
# This script:
#   1. Creates a Python venv in .venv (if not existing)
#   2. Sources the venv
#   3. pip install -r requirements.txt
#   4. pip install -e . (editable install of qq)
#   5. Runs scripts/install-qq-local.sh (builds Rust qq-tui, creates wrapper)
#
# After this, just run:
#   qq run <path-to-task-file> <path-to-target-directory>

ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="${QQ_PYTHON:-python3}"

echo "============================================"
echo "  QonQrete one-shot installer"
echo "============================================"
echo "Source tree:   $ROOT"
echo "Python:        $PY"
echo ""

# ── Step 1: Create venv ──
if [ ! -d "$ROOT/.venv" ]; then
    echo "→ Creating Python virtual environment in .venv …"
    "$PY" -m venv "$ROOT/.venv"
    echo "   .venv created."
else
    echo "→ Using existing .venv"
fi

# ── Step 2: Source venv ──
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
echo "   Virtual environment activated."
echo ""

# ── Step 3: Install Python dependencies ──
if [ -f "$ROOT/requirements.txt" ]; then
    echo "→ Installing Python dependencies …"
    pip install -r "$ROOT/requirements.txt" 2>&1 | tail -3
    echo ""
else
    echo "⚠  No requirements.txt found — skipping pip install -r"
fi

# ── Step 4: Install qq package (editable) ──
echo "→ Installing qq package in editable mode …"
pip install -e "$ROOT" 2>&1 | tail -3
echo ""

# ── Step 5: Run the local install script ──
INSTALL_SCRIPT="$ROOT/scripts/install-qq-local.sh"
if [ -f "$INSTALL_SCRIPT" ]; then
    echo "→ Running local install script …"
    bash "$INSTALL_SCRIPT"
else
    echo "⚠  install-qq-local.sh not found at $INSTALL_SCRIPT"
    echo "   Skipping Rust build and wrapper creation."
fi

echo ""
echo "============================================"
echo "  QonQrete installed!"
echo "============================================"
echo ""
echo "Try: qq run <path-to-task-file> <path-to-target-directory>"
echo "     qq models"
echo "     qq doctor"
echo ""
