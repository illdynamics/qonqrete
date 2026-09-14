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
# If VIRTUAL_ENV is set and we're inside a venv, skip --user (it's
# incompatible). This also recognises a venv interpreter passed through
# QQ_PYTHON (the `qq` wrapper exports it), which is what `qq install` /
# `qq reinstall` use — VIRTUAL_ENV is not set on that path.
INSIDE_PROJECT_VENV=false
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "→ Detected virtual environment: $VIRTUAL_ENV"
    if [ "$VIRTUAL_ENV" = "$ROOT/.venv" ]; then
        INSIDE_PROJECT_VENV=true
        echo "   (this is the project .venv — will install the editable package + pyproject deps)"
    fi
elif "$PY" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' >/dev/null 2>&1; then
    case "$(cd "$(dirname "$PY")/.." 2>/dev/null && pwd)" in
        "$ROOT/.venv")
            INSIDE_PROJECT_VENV=true
            echo "→ Detected project venv interpreter: $PY"
            echo "   (will install the editable package + pyproject deps)"
            ;;
    esac
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

# ── Build the migrated internal Rust TUI (OPTIONAL) ──
# cargo is optional: without the Rust TUI, `qq run` automatically falls back to
# the built-in Python streaming mode, so the engine works either way. A TUI
# build failure therefore never aborts the qq install.
if command -v cargo >/dev/null 2>&1; then
    echo "→ Building the integrated Rust TUI cockpit (qq/tui) …"
    if cargo build --release --manifest-path "$ROOT/qq/tui/Cargo.toml" 2>&1 | tail -5; then
        if [ -x "$ROOT/qq/tui/target/release/qq-internal-tui" ]; then
            echo "   TUI built: $ROOT/qq/tui/target/release/qq-internal-tui"
        fi
    else
        echo "⚠  The Rust TUI build failed — continuing without it (the Python CLI works)." >&2
        echo "   Re-run 'qq reinstall' after fixing the build to get the full TUI cockpit." >&2
    fi
else
    echo "⚠  cargo not found — skipping the optional Rust TUI build."
    echo "   'qq run' will use the built-in Python streaming mode. To get the full"
    echo "   TUI cockpit later, install Rust and run: qq reinstall"
fi
echo ""

# ── Ensure the SYSTEM CodeSeeq CLI (OPTIONAL, never vendored) ──
# qq runs the *system* codeseeq CLI found on PATH (see qq/adapters/codeseeq.py).
# A copy vendored under ./qq/codeseeq is deliberately NOT used: only the system
# install owns the `codeseeq login` session that the codeseeq/chatgpt providers
# reuse. CodeSeeq is needed by the 'codeseeq' (DeepSeek bridge) and 'chatgpt'
# (ChatGPT account) providers only — the default 'llama-cpp' provider works
# without it — so any failure here is a warning, never a reason to abort.
# `codeseeq_present` — 0 when a usable system codeseeq launcher is reachable.
codeseeq_present() {
    [ -n "${QQ_CODESEEQ_BIN:-}" ] && return 0
    command -v codeseeq >/dev/null 2>&1 && return 0
    [ -x "$BIN/codeseeq" ] && return 0
    return 1
}
# `link_codeseeq_launcher` — expose a launcher found at $HOME/bin (upstream's
# default) through $BIN as well, because the qq wrapper puts $BIN on PATH.
link_codeseeq_launcher() {
    if [ -x "${HOME}/bin/codeseeq" ] && [ ! -e "$BIN/codeseeq" ]; then
        ln -s "${HOME}/bin/codeseeq" "$BIN/codeseeq"
        echo "   Linked ${HOME}/bin/codeseeq → $BIN/codeseeq (qq wrapper PATH)"
    fi
}

echo "→ Checking the system CodeSeeq CLI (optional; codeseeq/chatgpt providers only) …"
if [ "${QONQRETE_SKIP_CODESEEQ:-0}" = "1" ]; then
    echo "   Skipped (QONQRETE_SKIP_CODESEEQ=1)."
    echo "   Install it later with:"
    echo "     curl -fsSL https://raw.githubusercontent.com/illdynamics/codeseeq/main/scripts/install.sh | bash"
elif [ -n "${QQ_CODESEEQ_BIN:-}" ]; then
    echo "   Using QQ_CODESEEQ_BIN: $QQ_CODESEEQ_BIN"
elif command -v codeseeq >/dev/null 2>&1; then
    echo "   Already on PATH: $(command -v codeseeq)"
elif [ -x "$BIN/codeseeq" ]; then
    echo "   Already installed: $BIN/codeseeq"
elif [ -x "${HOME}/bin/codeseeq" ]; then
    echo "   Found at ${HOME}/bin/codeseeq"
    link_codeseeq_launcher
else
    if command -v curl >/dev/null 2>&1; then
        echo "→ Installing the latest system CodeSeeq CLI …"
        echo "   (upstream: https://github.com/illdynamics/codeseeq; launcher → $BIN)"
        if (
            cd "$ROOT"
            export CODESEEQ_BIN_DIR="$BIN"
            export CODESEEQ_INSTALL_DIR="${CODESEEQ_INSTALL_DIR:-${HOME}/.config/codeseeq}"
            curl -fsSL https://raw.githubusercontent.com/illdynamics/codeseeq/main/scripts/install.sh | bash
        ); then
            if codeseeq_present; then
                echo "   CodeSeeq CLI installed."
            elif [ -x "${HOME}/bin/codeseeq" ]; then
                link_codeseeq_launcher
                codeseeq_present && echo "   CodeSeeq CLI installed."
            else
                echo "   WARNING: the CodeSeeq installer ran, but 'codeseeq' was not found." >&2
            fi
        else
            echo "   WARNING: the CodeSeeq install failed (network/upstream issue)." >&2
        fi
    else
        echo "   WARNING: curl not found — cannot install the optional CodeSeeq CLI." >&2
    fi
    if ! codeseeq_present; then
        echo "   Install it later with:"
        echo "     curl -fsSL https://raw.githubusercontent.com/illdynamics/codeseeq/main/scripts/install.sh | bash"
        echo "   (or re-run the qq installer without QONQRETE_SKIP_CODESEEQ=1)"
    fi
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
export PATH="$BIN:\$PATH"
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
"$PY" -m qq doctor --offline 2>&1 | head -5 || true
