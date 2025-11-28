#!/bin/bash
# qonqrete.sh - The Entry Point

set -euo pipefail
VERSION="QonQrete v0.1.0"
IMAGE_NAME="qonqrete-qage"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WORKSPACE_DIR="${SCRIPT_DIR}/worqspace"
CONFIG_FILE="${WORKSPACE_DIR}/pipeline_config.yaml"
CONTAINER_WORKSPACE="/qonq"

# --- HELPERS ---
show_splash() {
    SPLASH_IMG="${SCRIPT_DIR}/qrane/splash.png"
    if [ -f "$SPLASH_IMG" ] && command -v chafa >/dev/null 2>&1; then
        clear
        chafa "$SPLASH_IMG" --size=128x36 --stretch
        sleep 1
        clear
    fi
}

show_version() {
    echo "$VERSION"
}

show_help() {
    cat <<EOF
$VERSION
Usage: ./qonqrete.sh [COMMAND] [OPTIONS]

Commands:
  init            Build the Qage container image.
  run             Start the Qrane orchestration engine.
  clean           Remove all 'qage_*' run directories from worqspace.

Global Options:
  -h, --help      Show this help message.
  -V, --version   Show version information.

Run Options:
  -a, --auto      Enable Autonomous Mode (skip checkpoints).
  -t, --tui       Enable TUI Mode (Split-screen interface).
  --msb           Force usage of Microsandbox (msb/mbx).
  --docker        Force usage of Docker.
  -w, --wonqrete  Enable experimental mode.

Configuration:
  Defaults are read from worqspace/pipeline_config.yaml.
  Flags (--msb, --docker) override configuration files.

Examples:
  ./qonqrete.sh init --msb
  ./qonqrete.sh run -a -t
  ./qonqrete.sh clean
EOF
}

# --- CONFIGURATION PARSER ---
detect_runtime() {
    # 1. Default to Docker
    local runtime="docker"

    # 2. Check pipeline_config.yaml
    if [ -f "$CONFIG_FILE" ]; then
        # Grep for 'microsandbox: true' (case insensitive, ignoring whitespace)
        if grep -iq "^[[:space:]]*microsandbox:[[:space:]]*true" "$CONFIG_FILE"; then
            runtime="msb"
        fi
    fi

    # 3. Flags override everything (handled in main loop)
    echo "$runtime"
}

# --- MAIN ARGUMENT PARSING ---
COMMAND=""
PY_ARGS=""
RUNTIME_MODE=$(detect_runtime) # Set initial mode from config

if [[ $# -eq 0 ]]; then show_help; exit 0; fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        init|run|clean)
            COMMAND="$1"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -V|--version)
            show_version
            exit 0
            ;;
        -a|--auto)
            PY_ARGS="$PY_ARGS --auto"
            shift
            ;;
        -t|--tui)
            PY_ARGS="$PY_ARGS --tui"
            shift
            ;;
        -w|--wonqrete)
            PY_ARGS="$PY_ARGS --wonqrete"
            shift
            ;;
        --msb)
            RUNTIME_MODE="msb"
            shift
            ;;
        --docker)
            RUNTIME_MODE="docker"
            shift
            ;;
        *)
            echo "[WARN] Unknown argument: $1"
            shift
            ;;
    esac
done

if [[ -z "$COMMAND" ]]; then
    echo "[ERROR] No command specified (init/run/clean)."
    show_help
    exit 1
fi

# --- EXECUTION ---
cd "$SCRIPT_DIR"

case "$COMMAND" in
    init)
        echo "[INFO] Initializing QonQrete..."
        if [ "$RUNTIME_MODE" == "msb" ]; then
            echo "[INFO] Building Qage with Microsandbox using Sandboxfile..."
            if command -v msb >/dev/null 2>&1; then
                msb build . -t "$IMAGE_NAME"
            elif command -v mbx >/dev/null 2>&1; then
                mbx build . -t "$IMAGE_NAME"
            else
                echo "[ERROR] --msb specified (or configured) but binaries not found."; exit 1;
            fi
        else
            echo "[INFO] Building Qage with Docker..."
            docker build -t "$IMAGE_NAME" -f Dockerfile .
        fi
        ;;

    clean)
        echo "[INFO] Cleaning QonQrete workspaces..."
        if ls "${WORKSPACE_DIR}"/qage_* 1> /dev/null 2>&1; then
            echo "Found previous run directories in: ${WORKSPACE_DIR}"
            read -p "Are you sure you want to delete all 'qage_*' directories? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rm -rf "${WORKSPACE_DIR}"/qage_*
                echo "[INFO] Workspace cleaned."
            else
                echo "[INFO] Clean aborted."
            fi
        else
            echo "[INFO] No 'qage_*' directories found."
        fi
        ;;

    run)
        # Check API Keys
        if [[ -z "${OPENAI_API_KEY:-}" || -z "${GOOGLE_API_KEY:-}" ]]; then
            echo "[ERROR] API Keys missing. Export OPENAI_API_KEY and GOOGLE_API_KEY."
            exit 1
        fi

        if [[ "$PY_ARGS" != *"--tui"* ]]; then
            show_splash
        fi

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        if [ "$RUNTIME_MODE" == "msb" ]; then
             echo "[INFO] Seeding worqspace in microsandbox at: $RUN_HOST_PATH"
        else
             echo "[INFO] Seeding worqspace in docker at: $RUN_HOST_PATH"
        fi

        mkdir -p "$RUN_HOST_PATH"/{tasq.d,exeq.d,reqap.d,qodeyard,struqture}

        # Config Copy
        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then
            cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        else
            echo "Create a simple Python script." > "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        fi

        # [DEV MODE] Mounts
        # Note: Paths must be absolute for Docker/MSB
        DEV_MOUNTS="-v ${SCRIPT_DIR}/qrane:/qonqrete/qrane -v ${SCRIPT_DIR}/worqer:/qonqrete/worqer"
        RUN_MOUNTS="-v ${RUN_HOST_PATH}:${CONTAINER_WORKSPACE}"

        RUN_CMD="python3 qrane/qrane.py $PY_ARGS"

        if [ "$RUNTIME_MODE" == "msb" ]; then
            # MSB Logic
            # We assume msb run supports -v flags similar to docker, or we pass them if the CLI differs.
            # Standard MSB usage often mirrors docker run.

            CMD_BIN="msb"
            if command -v mbx >/dev/null 2>&1; then CMD_BIN="mbx"; fi

            # Construct command string for MSB to execute inside
            # We pass ENV vars via command line or -e flags if MSB supports them.
            # Assuming standard container runtime CLI compatibility:

            $CMD_BIN run --rm -it \
                $RUN_MOUNTS \
                $DEV_MOUNTS \
                -e OPENAI_API_KEY="$OPENAI_API_KEY" \
                -e GOOGLE_API_KEY="$GOOGLE_API_KEY" \
                -e GEMINI_API_KEY="$GOOGLE_API_KEY" \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" \
                "$IMAGE_NAME" \
                $RUN_CMD

        else
            # Docker Logic
            docker run --rm -it \
                $RUN_MOUNTS \
                $DEV_MOUNTS \
                -e OPENAI_API_KEY="$OPENAI_API_KEY" \
                -e GOOGLE_API_KEY="$GOOGLE_API_KEY" \
                -e GEMINI_API_KEY="$GOOGLE_API_KEY" \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" \
                "$IMAGE_NAME" $RUN_CMD
        fi
        ;;
esac
