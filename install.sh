#!/usr/bin/env bash
set -euo pipefail

# install.sh — one-shot QonQrete (qq) installer
#
# Works from a git clone AND from an extracted release zip:
#   git clone <qonqrete-repo>        # or: unzip qonqrete-v*.zip
#   cd qonqrete
#   ./install.sh
#
# (Website one-liner that fetches the latest runtime zip first:
#    curl -fsSL https://qonqrete.sh/install.sh | bash )
#
# This script:
#   1. Creates a Python venv in .venv (if not existing)
#   2. Activates it
#   3. pip install -e .  (installs qq + its pyproject.toml dependencies)
#   4. Runs scripts/install-qq-local.sh which:
#        - builds the integrated Rust TUI cockpit when cargo is available
#          (OPTIONAL — `qq run` falls back to Python streaming without it)
#        - ensures the *system* CodeSeeq CLI for the codeseeq/chatgpt providers
#          (OPTIONAL — never vendored into ./qq/codeseeq; the default
#          'llama-cpp' provider needs no CodeSeeq. Skip with
#          QONQRETE_SKIP_CODESEEQ=1)
#        - creates the `qq` wrapper on PATH (~/.local/bin)
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
# Editable installs (PEP 660) need a reasonably modern pip; very old pythons
# ship pip < 21.3 which cannot do `pip install -e` on a pyproject-only
# project. Upgrading pip first keeps the one-shot installer reliable.
echo "→ Ensuring a modern pip in the venv …"
python -m pip install --quiet --upgrade pip 2>&1 | tail -2 || true
echo "→ Installing qq in editable mode (deps from pyproject.toml) …"
pip install -e "$ROOT" 2>&1 | tail -3
echo ""
echo "   Note: image/video generation extras (google-genai, gradio_client,"
echo "   playwright) are optional — install later with:"
echo "     pip install -e \"${ROOT}[media]\""
echo ""

# ── Step 4: Run the local install script ──
INSTALL_SCRIPT="$ROOT/scripts/install-qq-local.sh"
if [ -f "$INSTALL_SCRIPT" ]; then
    echo "→ Running local install script (TUI when cargo present, optional"
    echo "  system CodeSeeq CLI, qq wrapper) …"
    bash "$INSTALL_SCRIPT"
else
    echo "⚠  install-qq-local.sh not found at $INSTALL_SCRIPT"
    echo "   Skipping optional TUI build, CodeSeeq setup and wrapper creation."
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
