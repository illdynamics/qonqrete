#!/bin/bash
# qonqrete.sh

set -euo pipefail
IMAGE_NAME="qonqrete-qage"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WORKSPACE_DIR="${SCRIPT_DIR}/worqspace"
CONTAINER_WORKSPACE="/qonq"

# --- SPLASH SCREEN LOGIC ---
show_splash() {
    SPLASH_IMG="${SCRIPT_DIR}/qrane/splash.png"
    if [ -f "$SPLASH_IMG" ] && command -v chafa >/dev/null 2>&1; then
        clear
        # Use chafa to render the image in a wide aspect ratio.
        chafa "$SPLASH_IMG" --size=128x36 --stretch
        sleep 2
        clear
    fi
}

usage() {
    cat <<EOF
Usage: ./qonqrete.sh {init|run} [options]

Commands:
  init            Build the Qage image (Docker by default).
  run             Run the Qrane/Qage system.

Options:
  --msb           Use Microsandbox (msb/mbx) instead of Docker.
  --auto          Enable Autonomous Mode (no user gate).
  --tui           Enable the Qontroldeck (Terminal UI).
  -w, --wonqrete  Enable experimental mode.
EOF
    exit 1
}

cd "$SCRIPT_DIR"
COMMAND="${1:-}"
shift || true

# Parse global flags
USE_MSB=false
AUTO=""
TUI=""
WONQ=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --msb) USE_MSB=true ;;
        --auto) AUTO="--auto" ;;
        --tui) TUI="--tui" ;;
        -w|--wonqrete) WONQ="--wonqrete" ;;
        -h|--help) usage ;;
        *) echo "[WARN] Unknown argument ignored: $1" ;;
    esac
    shift
done

case "$COMMAND" in
    init)
        echo "[INFO] Initializing QonQrete..."
        if [ "$USE_MSB" = true ]; then
            echo "[INFO] Building Qage with Microsandbox..."
            if command -v msb >/dev/null 2>&1; then msb build "$IMAGE_NAME"
            elif command -v mbx >/dev/null 2>&1; then mbx build "$IMAGE_NAME"
            else echo "[ERROR] --msb specified but binaries not found."; exit 1; fi
        else
            echo "[INFO] Building Qage with Docker..."
            docker build -t "$IMAGE_NAME" -f Dockerfile .
        fi
        ;;

    run)
        # [FEATURE] Show Splash before running
        show_splash

        if [[ -z "${OPENAI_API_KEY:-}" || -z "${GOOGLE_API_KEY:-}" ]]; then
            echo "[ERROR] API Keys missing. Export OPENAI_API_KEY and GOOGLE_API_KEY."
            exit 1
        fi

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        echo "[INFO] Seeding worqspace at: $RUN_HOST_PATH"
        mkdir -p "$RUN_HOST_PATH"/{tasq.d,exeq.d,reqap.d,qodeyard,struqture}

        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"; fi

        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then
            cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        else
            echo "Create a simple Python script." > "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        fi

        echo "[INFO] Starting Qrane..."

        # [DEV MODE] Mount local source code to allow instant updates without rebuilding
        DEV_MOUNTS="-v ${SCRIPT_DIR}/qrane:/qonqrete/qrane -v ${SCRIPT_DIR}/worqer:/qonqrete/worqer"

        if [ "$USE_MSB" = true ]; then
            SECURE_CMD="export OPENAI_API_KEY='${OPENAI_API_KEY}'; export GOOGLE_API_KEY='${GOOGLE_API_KEY}'; export GEMINI_API_KEY='${GOOGLE_API_KEY}'; export QONQ_WORKSPACE='/qonq/${RUN_DIR_NAME}'; cd /qonqrete && python3 qrane/qrane.py $AUTO $TUI $WONQ"

            CMD="msb run"
            if command -v mbx >/dev/null 2>&1; then CMD="mbx run"; fi

            $CMD "$IMAGE_NAME" -- /bin/sh -c "$SECURE_CMD"

        else
            # --- DOCKER RUNTIME ---
            RUN_CMD="python3 qrane/qrane.py $AUTO $TUI $WONQ"

            docker run --rm -it \
                -v "$RUN_HOST_PATH:$CONTAINER_WORKSPACE" \
                $DEV_MOUNTS \
                -e OPENAI_API_KEY="$OPENAI_API_KEY" \
                -e GOOGLE_API_KEY="$GOOGLE_API_KEY" \
                -e GEMINI_API_KEY="$GOOGLE_API_KEY" \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" \
                "$IMAGE_NAME" $RUN_CMD
        fi
        ;;
    *)
        usage
        ;;
esac
