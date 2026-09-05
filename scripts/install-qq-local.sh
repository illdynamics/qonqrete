#!/usr/bin/env bash
set -euo pipefail

ROOT="${QQ_SRC:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${QQ_PYTHON:-python3}"
BIN="${QQ_BIN_DIR:-$HOME/.local/bin}"

echo "=== QonQrete qq local installer ==="
echo "Source tree:   $ROOT"
echo "Python:        $PY"
echo "Install bin:   $BIN"
echo ""

mkdir -p "$BIN"

# ── Detect whether we're inside a virtual environment ──
# If VIRTUAL_ENV is set and we're inside a venv, skip --user (it's incompatible).
INSIDE_PROJECT_VENV=false
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "→ Detected virtual environment: $VIRTUAL_ENV"
    if [ "$VIRTUAL_ENV" = "$ROOT/.venv" ]; then
        INSIDE_PROJECT_VENV=true
        echo "   (this is the project .venv — will install the editable package + pyproject deps)"
    fi
fi

# ── Install Python qq package ──
if [ "$INSIDE_PROJECT_VENV" = true ]; then
    echo "→ Installing qq in editable mode (deps from pyproject.toml) …"
    "$PY" -m pip install -e "$ROOT" 2>&1 | tail -3
elif [ -n "${VIRTUAL_ENV:-}" ]; then
    # Inside a different venv — pip install without --user
    echo "→ Installing Python qq (editable) …"
    "$PY" -m pip install -e "$ROOT" 2>&1 | tail -3
else
    # Outside any venv — use --user
    echo "→ Installing Python qq (editable) …"
    "$PY" -m pip install --user -e "$ROOT" 2>&1 | tail -3
fi
echo ""

# ── Build the migrated internal TUI ──
if command -v cargo >/dev/null 2>&1; then
    echo "→ Building internal QonQrete TUI …"
    cargo build --release --manifest-path "$ROOT/qq/tui/Cargo.toml" 2>&1 | tail -5
else
    echo "⚠  cargo not found — the Python CLI will still work, but the full TUI cannot be built."
fi
echo ""

# ── Install CodeSeeq into ./qq/codeseeq ──
echo "→ Checking CodeSeeq runtime prerequisites …"
for dep in podman node npm codex; do
    if command -v "$dep" >/dev/null 2>&1; then
        echo "   $dep: OK"
    else
        echo "   ERROR: $dep is required before CodeSeeq can be installed." >&2
        exit 1
    fi
done
echo "→ Installing CodeSeeq into $ROOT/qq/codeseeq …"
(
    cd "$ROOT/qq"
    curl -fsSL https://raw.githubusercontent.com/illdynamics/codeseeq/main/scripts/install.sh | bash
)
if [ ! -x "$ROOT/qq/codeseeq/codeseeq" ]; then
    echo "WARNING: CodeSeeq installer completed but $ROOT/qq/codeseeq/codeseeq was not found." >&2
else
    echo "   CodeSeeq installed: $ROOT/qq/codeseeq/codeseeq"
fi
echo ""

# ── Create wrapper for source-tree convenience ──
# Prefer the project venv interpreter (install.sh flow) so `qq` keeps working
# in fresh shells; fall back to the interpreter used for a --user install.
if [ -x "$ROOT/.venv/bin/python" ]; then
    WRAPPER_PY="$ROOT/.venv/bin/python"
else
    WRAPPER_PY="${QQ_PYTHON:-$PY}"
fi
# NOTE: heredoc delimiter is UNQUOTED so $ROOT, $WRAPPER_PY, $BIN expand at install time.
cat > "$BIN/qq" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:\$PATH"
export QQ_SRC="\${QQ_SRC:-$ROOT}"
export QQ_PYTHON="\${QQ_PYTHON:-$WRAPPER_PY}"
exec "\$QQ_PYTHON" -m qq "\$@"
EOF
chmod 0755 "$BIN/qq"

echo "→ Wrapper installed: $BIN/qq"
echo ""

# ── Add to PATH hint ──
if ! echo "$PATH" | grep -q "$BIN"; then
    echo "⚠  $BIN is not on your PATH."
    echo "   Add this to your shell config:"
    echo ""
    echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# ── Verify ──
echo "→ Verifying installation …"
"$PY" -c "import qq; print('  Python qq module: OK')" 2>&1 || echo "  Python qq module: FAILED"
"$PY" -m qq doctor --offline 2>&1 | head -5
