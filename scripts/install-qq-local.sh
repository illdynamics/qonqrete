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
        echo "   (this is the project .venv — will install deps and editable package)"
    fi
fi

# ── Install Python qq package ──
if [ "$INSIDE_PROJECT_VENV" = true ]; then
    echo "→ Installing Python dependencies from requirements.txt …"
    "$PY" -m pip install -r "$ROOT/requirements.txt" 2>&1 | tail -3
    echo "→ Installing qq in editable mode …"
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

# ── Build Rust qq-tui if cargo is available ──
if command -v cargo >/dev/null 2>&1; then
    echo "→ Building Rust qq-tui …"
    cargo build --release --manifest-path "$ROOT/qq-tui/Cargo.toml" 2>&1 | tail -5
    if [ -f "$ROOT/qq-tui/target/release/qq-tui" ]; then
        install -m 0755 "$ROOT/qq-tui/target/release/qq-tui" "$BIN/qq-tui"
        echo "   qq-tui installed to $BIN/qq-tui"
    else
        echo "   WARNING: qq-tui binary not found — Rust build may have failed."
    fi
else
    echo "⚠  cargo not found — skipping Rust qq-tui build."
    echo "   Install Rust from https://rustup.rs or use the pre-built binary."
fi
echo ""

# ── Create wrapper for source-tree convenience ──
# NOTE: heredoc delimiter is UNQUOTED so $ROOT, $PY, $BIN are expanded at install time.
cat > "$BIN/qq" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:\$PATH"
export QQ_SRC="\${QQ_SRC:-$ROOT}"
export QQ_PYTHON="\${QQ_PYTHON:-$PY}"
if command -v qq-tui >/dev/null 2>&1; then
    export QQ_TUI_BIN="\$(command -v qq-tui)"
elif [ -f "\$QQ_SRC/qq-tui/target/release/qq-tui" ]; then
    export QQ_TUI_BIN="\$QQ_SRC/qq-tui/target/release/qq-tui"
fi
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
