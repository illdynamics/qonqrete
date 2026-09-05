#!/usr/bin/env bash
set -euo pipefail

# install.sh — one-shot QonQrete (qq) installer
#
# Works from a git clone AND from an extracted release zip:
#   git clone <qonqrete-repo>        # or: unzip qonqrete-qq-v*.zip
#   cd qonqrete
#   ./install.sh
#
# This script:
#   1. Creates a Python venv in .venv (if not existing)
#   2. Activates it
#   3. pip install -e .  (installs qq + its pyproject.toml dependencies)
#   4. Runs scripts/install-qq-local.sh (builds the integrated Rust TUI,
#      installs CodeSeeq, and creates the `qq` wrapper on PATH)
#
# Optional media features (image/video generation) need the `media` extra:
#   pip install -e "$ROOT[media]"    # google-genai, gradio_client, playwright
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

# ── Step 2: Activate venv ──
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
echo "   Virtual environment activated."
echo ""

# ── Step 3: Install qq package (dependencies come from pyproject.toml) ──
echo "→ Installing qq in editable mode (deps from pyproject.toml) …"
pip install -e "$ROOT" 2>&1 | tail -3
echo ""
echo "   Note: image/video generation extras (google-genai, gradio_client,"
echo "   playwright) are optional — install later with:"
echo "     pip install -e \"$ROOT[media]\""
echo ""

# ── Step 4: Run the local install script ──
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
