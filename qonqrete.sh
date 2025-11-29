#!/bin/bash
# qonqrete.sh - The Entry Point

set -euo pipefail

# --- DYNAMIC VERSIONING ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

if [ -f "$VERSION_FILE" ]; then
    QONQ_V=$(cat "$VERSION_FILE" | tr -d '[:space:]')
else
    QONQ_V="0.0.0"
fi

VERSION="QonQrete v${QONQ_V}"
IMAGE_NAME="qonqrete-qage"
WORKSPACE_DIR="${SCRIPT_DIR}/worqspace"
CONFIG_FILE="${WORKSPACE_DIR}/pipeline_config.yaml"
CONTAINER_WORKSPACE="/qonq"

# --- STYLING & COLORS ---
B=$'\033[1;34m'
W=$'\033[1;37m'
R=$'\033[0m'

PADDING="      "
PREFIX_TPL="${B}〘{PREFIX}〙『${W}Qrane${B}』${PADDING}⸎${R}"

# --- HELPERS ---

log_qrane() {
    local prefix="_QQ"
    if [[ "$PY_ARGS" == *"--auto"* ]]; then
        prefix="aQQ"
    elif [[ "$COMMAND" == "run" ]]; then
        prefix="_QQ"
    fi
    echo -e "${PREFIX_TPL/\{PREFIX\}/$prefix} $1"
}

exec_qrane() {
    "$@" 2>&1 | while IFS= read -r line; do
        echo -e "${PREFIX_TPL/\{PREFIX\}/_QQ} $line"
    done
}

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
  -a, --auto                  Enable Autonomous Mode.
  -t, --tui                   Enable TUI Mode.
  -m, --mode <NAME>           Set Operational Mode (program, enterprise, security, etc).
  -b, --briq-sensitivity <N>  Set Granularity (0-9).
  -s, --msb                   Force Microsandbox (msb).
  -d, --docker                Force Docker.
  -w, --wonqrete              Enable experimental mode.
EOF
}

# --- CONFIGURATION PARSER ---
detect_runtime() {
    local runtime="docker"
    if [ -f "$CONFIG_FILE" ]; then
        if grep -iq "^[[:space:]]*microsandbox:[[:space:]]*true" "$CONFIG_FILE"; then
            runtime="msb"
        fi
    fi
    echo "$runtime"
}

# --- MAIN ARGUMENT PARSING ---
COMMAND=""
PY_ARGS=""
RUNTIME_MODE=$(detect_runtime)

if [[ $# -eq 0 ]]; then show_help; exit 0; fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        init|run|clean)
            COMMAND="$1"
            shift
            ;;
        -h|--help) show_help; exit 0 ;;
        -V|--version) show_version; exit 0 ;;

        -a|--auto) PY_ARGS="$PY_ARGS --auto"; shift ;;
        -t|--tui) PY_ARGS="$PY_ARGS --tui"; shift ;;
        -w|--wonqrete) PY_ARGS="$PY_ARGS --wonqrete"; shift ;;

        -m|--mode)
            PY_ARGS="$PY_ARGS --mode $2"
            shift 2
            ;;
        -b|--briq-sensitivity)
            PY_ARGS="$PY_ARGS --briq-sensitivity $2"
            shift 2
            ;;

        -s|--msb) RUNTIME_MODE="msb"; shift ;;
        -d|--docker) RUNTIME_MODE="docker"; shift ;;

        *)
            log_qrane "[WARN] Unknown argument: $1"
            shift
            ;;
    esac
done

if [[ -z "$COMMAND" ]]; then
    log_qrane "[ERROR] No command specified."; show_help; exit 1
fi

# --- EXECUTION ---
cd "$SCRIPT_DIR"

case "$COMMAND" in
    init)
        log_qrane "Initializing QonQrete..."
        BUILD_ARGS="--build-arg QONQ_VERSION=${QONQ_V}"

        if [ "$RUNTIME_MODE" == "msb" ]; then
            log_qrane "Building Qage with Microsandbox..."
            if command -v msb >/dev/null 2>&1; then exec_qrane msb build . -t "$IMAGE_NAME" $BUILD_ARGS
            elif command -v mbx >/dev/null 2>&1; then exec_qrane mbx build . -t "$IMAGE_NAME" $BUILD_ARGS
            else log_qrane "[ERROR] msb/mbx not found."; exit 1; fi
        else
            log_qrane "Building Qage with Docker..."
            exec_qrane docker build -t "$IMAGE_NAME" -f Dockerfile . --progress=plain $BUILD_ARGS
        fi
        ;;

    clean)
        log_qrane "Cleaning QonQrete workspaces..."
        if ls "${WORKSPACE_DIR}"/qage_* 1> /dev/null 2>&1; then
            log_qrane "Found previous run directories."
            read -p "Delete all 'qage_*' directories? [y/N] " -n 1 -r; echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rm -rf "${WORKSPACE_DIR}"/qage_*
                log_qrane "Workspace cleaned."
            else
                log_qrane "Clean aborted."
            fi
        else
            log_qrane "No 'qage_*' directories found."
        fi
        ;;

    run)
        if [[ -z "${OPENAI_API_KEY:-}" || -z "${GOOGLE_API_KEY:-}" ]]; then
            log_qrane "[ERROR] API Keys missing."; exit 1
        fi

        if [[ "$PY_ARGS" != *"--tui"* ]]; then show_splash; fi

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        if [ "$RUNTIME_MODE" == "msb" ]; then
             log_qrane "Seeding worQspace in Qage at: $RUN_HOST_PATH"
        else
             log_qrane "Seeding worQspace locally at: $RUN_HOST_PATH"
        fi

        mkdir -p "$RUN_HOST_PATH"/{tasq.d,exeq.d,reqap.d,qodeyard,struqture}

        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        else echo "Create a simple Python script." > "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"; fi

        DEV_MOUNTS="-v ${SCRIPT_DIR}/qrane:/qonqrete/qrane -v ${SCRIPT_DIR}/worqer:/qonqrete/worqer"
        RUN_MOUNTS="-v ${RUN_HOST_PATH}:${CONTAINER_WORKSPACE}"
        RUN_CMD="python3 qrane/qrane.py $PY_ARGS"

        if [ "$RUNTIME_MODE" == "msb" ]; then
            CMD_BIN="msb"; if command -v mbx >/dev/null 2>&1; then CMD_BIN="mbx"; fi
            $CMD_BIN run --rm -it $RUN_MOUNTS $DEV_MOUNTS \
                -e OPENAI_API_KEY="$OPENAI_API_KEY" -e GOOGLE_API_KEY="$GOOGLE_API_KEY" -e GEMINI_API_KEY="$GOOGLE_API_KEY" \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" "$IMAGE_NAME" $RUN_CMD
        else
            docker run --rm -it $RUN_MOUNTS $DEV_MOUNTS \
                -e OPENAI_API_KEY="$OPENAI_API_KEY" -e GOOGLE_API_KEY="$GOOGLE_API_KEY" -e GEMINI_API_KEY="$GOOGLE_API_KEY" \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" "$IMAGE_NAME" $RUN_CMD
        fi
        ;;
esac
