#!/bin/bash
# qonqrete.sh - The Entry Point
# v1.2.0 - Container Runtime Auto-Detect + Versioned Images (Docker / Podman / MSB)

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
IMAGE_NAME="qonqrete-qage:${QONQ_V}"
IMAGE_NAME_LATEST="qonqrete-qage:latest"
IMAGE_NAME_LEGACY="qonqrete-qage"
WORKSPACE_DIR="${SCRIPT_DIR}/worqspace"
CONFIG_FILE="${WORKSPACE_DIR}/pipeline_config.yaml"
CONTAINER_WORKSPACE="/qonq"
QONSTRUCTIONS_DIR="${WORKSPACE_DIR}/qonstructions"

# --- DOCKER/PODMAN SECURITY FLAGS ---
# These flags harden the container runtime:
#   --read-only         : Root filesystem is read-only (only /qonq is writable)
#   --cap-drop=ALL      : Drop all Linux capabilities
#   --cap-add=SETUID/GID: Required for gosu to switch users
#   --cap-add=CHOWN     : Required for entrypoint to fix /qonq permissions
#   --cap-add=FOWNER    : Required for chmod on files
#   --cap-add=DAC_OVERRIDE: Required to access host-mounted directories
#   --memory/--cpus     : Resource limits to prevent DoS
#   --pids-limit        : Prevent fork bombs
#   --tmpfs             : Ephemeral /tmp and cache with noexec
SECURITY_FLAGS="--read-only \
    --cap-drop=ALL \
    --cap-add=SETUID \
    --cap-add=SETGID \
    --cap-add=CHOWN \
    --cap-add=FOWNER \
    --cap-add=DAC_OVERRIDE \
    --memory=4g \
    --memory-swap=4g \
    --cpus=2 \
    --pids-limit=100 \
    --tmpfs /tmp:rw,noexec,nosuid,size=100m \
    --tmpfs /home/qrane/.cache:rw,size=500m"

# Legacy alias for backward compat if any external script references it
DOCKER_SECURITY_FLAGS="$SECURITY_FLAGS"

# --- STYLING & COLORS ---
B=$'\033[1;34m'
W=$'\033[1;37m'
G=$'\033[1;32m'
Y=$'\033[1;33m'
C=$'\033[1;36m'
R=$'\033[0m'

PADDING="      "
PREFIX_TPL="${B}〘{PREFIX}〙『${W}Qrane${B}』${PADDING}⸎${R}"

# --- HELPERS ---

log_qrane() {
    local prefix="_QQ"
    if [[ "${PY_ARGS:-}" == *"--auto"* ]]; then
        prefix="aQQ"
    elif [[ "${COMMAND:-}" == "run" ]]; then
        prefix="_QQ"
    elif [[ "${COMMAND:-}" == "resume" ]]; then
        prefix="rQQ"
    elif [[ "${COMMAND:-}" == "clean" ]]; then
        prefix="cQQ"
    fi
    echo -e "${PREFIX_TPL/\{PREFIX\}/$prefix} $1"
}

exec_qrane() {
    "$@" 2>&1 | while IFS= read -r line; do
        if [[ -n "${line//[[:space:]]/}" ]]; then
            echo -e "${PREFIX_TPL/\{PREFIX\}/_QQ} $line"
        fi
    done
}

show_version() {
    echo "$VERSION"
}

show_help() {
    cat <<EOF
$VERSION

Usage: ./qonqrete.sh [COMMAND] [OPTIONS]

Commands:
  init              Build the Qage container image.
  run               Start fresh QonQrete session (ignores sqrapyard by default).
  resume            Resume from a previous Qage (interactive or -q <n>).
  clean             Remove Qage directories (interactive or -q <n> or -A/--all).

Global Options:
  -h, --help        Show this help message.
  -V, --version     Show version information.

Run Options:
  -a, --auto                   Enable Autonomous Mode.
  -u, --user                   Force User-gated Mode.
  -t, --tui                    Enable TUI Mode. ${Y}[EXPERIMENTAL]${R}
  -m, --mode <n>               Set Operational Mode (program, enterprise, security, etc).
  -b, --briq-sensitivity <N>   Set Granularity (0-16). Default: 6. Higher = more briqs!
  -c, --cyqles <N>             Set max auto-cycles (1-50). Default: 3
  -n, --qonstruction-name <n>  Auto-save as qonstruction (non-interactive). v1.0.2
  -s, --sqrapyard              Seed from sqrapyard/ directory contents.
  -M, --msb                    Force Microsandbox (msb). ${Y}[EXPERIMENTAL]${R}
  -d, --docker                 Force Docker engine.
  -p, --podman                 Force Podman engine.
  -w, --wonqrete               Enable experimental mode.

Resume Options:
  -q, --qage <n>            Resume from specific Qage directory.
  (no args)                    Interactive Qage selection (kubectx-style).

Clean Options:
  -q, --qage <n>            Clean specific Qage directory.
  -A, --all                    Clean ALL Qage directories (current behavior).
  (no args)                    Interactive Qage selection for deletion.

Environment Overrides:
  CONTAINER_ENGINE=docker|podman   Override engine auto-detection.
  BUILD_BACKEND=buildx|plain       Override build backend auto-detection.

Examples:
  ./qonqrete.sh run                        # Fresh start, no sqrapyard
  ./qonqrete.sh run -s                     # Start with sqrapyard contents
  ./qonqrete.sh run --auto --mode security # Autonomous security mode
  ./qonqrete.sh run -b 6 -c 3              # Sensitivity 6, 3 cycles (default)
  ./qonqrete.sh run -b 5 -c 6              # Complex project: sens 5, 6 cycles
  ./qonqrete.sh run -a -n myproject        # Auto-save as 'myproject' qonstruction
  ./qonqrete.sh run --podman               # Use Podman engine explicitly
  ./qonqrete.sh resume                     # Interactive Qage picker
  ./qonqrete.sh resume -q qage_20251226    # Resume specific Qage
  ./qonqrete.sh clean                      # Interactive Qage deletion
  ./qonqrete.sh clean -A                   # Delete ALL Qages
EOF
}

# ═══════════════════════════════════════════════════════════════════════════════
# OS + CONTAINER ENGINE DETECTION (v1.0.4)
# ═══════════════════════════════════════════════════════════════════════════════

# Detected values (set by detect_os and detect_engine)
DETECTED_OS="Linux"        # Linux | Darwin | WSL | MSYS
CONTAINER_ENGINE=""        # docker | podman | msb
BUILD_BACKEND_MODE=""      # buildx | plain

detect_os() {
    local uname_s
    uname_s="$(uname -s 2>/dev/null || echo "Unknown")"

    case "$uname_s" in
        Linux)
            # Check if running inside WSL
            if [ -f /proc/version ] && grep -qi "Microsoft\|WSL" /proc/version 2>/dev/null; then
                DETECTED_OS="WSL"
            else
                DETECTED_OS="Linux"
            fi
            ;;
        Darwin)
            DETECTED_OS="Darwin"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            DETECTED_OS="MSYS"
            ;;
        *)
            # Also check OSTYPE for Git Bash / MSYS
            case "${OSTYPE:-}" in
                msys*|mingw*|cygwin*)
                    DETECTED_OS="MSYS"
                    ;;
                *)
                    DETECTED_OS="Linux"
                    ;;
            esac
            ;;
    esac
}

detect_engine() {
    # Priority: CONTAINER_ENGINE env > CLI flag (already set) > MSB config > auto-detect

    # 1. Check env override (only if CLI flag didn't already set it)
    if [ -z "$CONTAINER_ENGINE" ] && [ -n "${CONTAINER_ENGINE_ENV:-}" ]; then
        case "$CONTAINER_ENGINE_ENV" in
            docker|podman)
                CONTAINER_ENGINE="$CONTAINER_ENGINE_ENV"
                log_qrane "Engine override: ${CONTAINER_ENGINE} (from CONTAINER_ENGINE env)"
                return 0
                ;;
            *)
                log_qrane "[WARN] Unknown CONTAINER_ENGINE='${CONTAINER_ENGINE_ENV}', auto-detecting."
                ;;
        esac
    fi

    # 2. CLI flag already set CONTAINER_ENGINE (handled in arg parser)
    if [ -n "$CONTAINER_ENGINE" ]; then
        return 0
    fi

    # 3. Check MSB config (existing behavior)
    if [ -f "$CONFIG_FILE" ]; then
        if grep -iq "^[[:space:]]*microsandbox:[[:space:]]*true" "$CONFIG_FILE"; then
            CONTAINER_ENGINE="msb"
            return 0
        fi
    fi

    # 4. Auto-detect: docker first, then podman
    if command -v docker >/dev/null 2>&1; then
        CONTAINER_ENGINE="docker"
    elif command -v podman >/dev/null 2>&1; then
        CONTAINER_ENGINE="podman"
    else
        log_qrane "${Y}[ERROR]${R} No container engine found. Install Docker or Podman."
        log_qrane "  Docker: https://docs.docker.com/get-docker/"
        log_qrane "  Podman: https://podman.io/getting-started/installation"
        exit 1
    fi
}

detect_build_backend() {
    # Priority: BUILD_BACKEND env > auto-detect
    if [ -n "${BUILD_BACKEND:-}" ]; then
        case "$BUILD_BACKEND" in
            buildx|plain)
                BUILD_BACKEND_MODE="$BUILD_BACKEND"
                return 0
                ;;
            *)
                log_qrane "[WARN] Unknown BUILD_BACKEND='${BUILD_BACKEND}', auto-detecting."
                ;;
        esac
    fi

    if [ "$CONTAINER_ENGINE" = "docker" ]; then
        if docker buildx version >/dev/null 2>&1; then
            BUILD_BACKEND_MODE="buildx"
        else
            BUILD_BACKEND_MODE="plain"
        fi
    elif [ "$CONTAINER_ENGINE" = "podman" ]; then
        BUILD_BACKEND_MODE="plain"
    else
        BUILD_BACKEND_MODE="plain"
    fi
}

# --- macOS Podman Machine Init/Start (idempotent) ---
ensure_podman_machine() {
    if [ "$DETECTED_OS" != "Darwin" ] || [ "$CONTAINER_ENGINE" != "podman" ]; then
        return 0
    fi

    log_qrane "macOS + Podman detected — checking machine status..."

    # Check if any machine exists
    local machine_list
    machine_list="$(podman machine list --format '{{.Name}}' 2>/dev/null || true)"

    if [ -z "$machine_list" ]; then
        log_qrane "No Podman machine found. Initializing default machine..."
        if ! podman machine init 2>&1 | while IFS= read -r line; do
            echo -e "${PREFIX_TPL/\{PREFIX\}/_QQ}   $line"
        done; then
            log_qrane "${Y}[ERROR]${R} Failed to initialize Podman machine."
            log_qrane "  Try manually: podman machine init"
            exit 1
        fi
        log_qrane "Podman machine initialized."
    fi

    # Check if machine is running
    local machine_running
    machine_running="$(podman machine list --format '{{.Running}}' 2>/dev/null | head -1 || echo "false")"

    if [ "$machine_running" != "true" ]; then
        log_qrane "Starting Podman machine..."
        if ! podman machine start 2>&1 | while IFS= read -r line; do
            echo -e "${PREFIX_TPL/\{PREFIX\}/_QQ}   $line"
        done; then
            log_qrane "${Y}[ERROR]${R} Failed to start Podman machine."
            log_qrane "  Try manually: podman machine start"
            exit 1
        fi
        log_qrane "Podman machine started."
    else
        log_qrane "Podman machine already running."
    fi
}

print_runtime_info() {
    log_qrane "Container engine: ${G}${CONTAINER_ENGINE}${R}"
    log_qrane "Build backend:    ${G}${BUILD_BACKEND_MODE}${R}"
    log_qrane "OS detected:      ${G}${DETECTED_OS}${R}"

    if [ "$DETECTED_OS" = "MSYS" ]; then
        log_qrane "${Y}Git Bash detected. WSL2 is recommended for best compatibility.${R}"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# ENGINE-AWARE WRAPPERS (v1.0.4)
# Replace hardcoded docker/podman calls with engine-agnostic functions.
# ═══════════════════════════════════════════════════════════════════════════════

engine_build() {
    # Usage: engine_build [args...]
    # Handles: docker build / docker buildx build / podman build / msb build
    case "$CONTAINER_ENGINE" in
        msb)
            local cmd_bin="msb"
            if command -v mbx >/dev/null 2>&1; then cmd_bin="mbx"; fi
            exec_qrane $cmd_bin build "$@"
            ;;
        podman)
            exec_qrane podman build "$@"
            ;;
        docker)
            if [ "$BUILD_BACKEND_MODE" = "buildx" ]; then
                exec_qrane docker buildx build --load "$@"
            else
                exec_qrane docker build "$@"
            fi
            ;;
        *)
            log_qrane "[ERROR] Unknown engine: ${CONTAINER_ENGINE}"
            exit 1
            ;;
    esac
}

engine_run() {
    # Usage: engine_run [args...]
    # Handles: docker run / podman run / msb run
    # Security flags applied for docker/podman (not msb).
    case "$CONTAINER_ENGINE" in
        msb)
            local cmd_bin="msb"
            if command -v mbx >/dev/null 2>&1; then cmd_bin="mbx"; fi
            $cmd_bin run "$@"
            ;;
        podman)
            # Podman: apply security flags. Some flags (memory-swap) may not work
            # everywhere, so fallback to run without security flags if needed.
            podman run $SECURITY_FLAGS "$@" 2>/dev/null || podman run "$@"
            ;;
        docker)
            docker run $SECURITY_FLAGS "$@"
            ;;
        *)
            log_qrane "[ERROR] Unknown engine: ${CONTAINER_ENGINE}"
            exit 1
            ;;
    esac
}

engine_run_helper() {
    # Lightweight helper run (no security flags, no tty, --rm)
    # Used for fix_qage_permissions and delete_qage
    case "$CONTAINER_ENGINE" in
        docker)
            docker run --rm "$@" 2>/dev/null || true
            ;;
        podman)
            podman run --rm "$@" 2>/dev/null || true
            ;;
        msb)
            local cmd_bin="msb"
            if command -v mbx >/dev/null 2>&1; then cmd_bin="mbx"; fi
            $cmd_bin run --rm "$@" 2>/dev/null || true
            ;;
        *)
            return 0
            ;;
    esac
}

# --- CONFIGURATION PARSER (legacy compat — detect_runtime kept for any external callers) ---
detect_runtime() {
    local runtime="docker"
    if [ -f "$CONFIG_FILE" ]; then
        if grep -iq "^[[:space:]]*microsandbox:[[:space:]]*true" "$CONFIG_FILE"; then
            runtime="msb"
        fi
    fi
    echo "$runtime"
}

# --- INTERACTIVE QAGE SELECTOR (kubectx-style) ---
select_qage_interactive() {
    local qages=()
    local i=1
    
    for qage_dir in $(ls -1dt "${WORKSPACE_DIR}"/qage_* 2>/dev/null); do
        if [ -d "$qage_dir" ]; then
            qages+=("$(basename "$qage_dir")")
        fi
    done
    
    if [ ${#qages[@]} -eq 0 ]; then
        echo "No Qage directories found in worqspace." >&2
        return 1
    fi
    
    echo "" >&2
    echo -e "${C}┌───────────────────────────────────────────────────────────┐${R}" >&2
    echo -e "${C}│${W}            Available Qages (newest first)                 ${C}│${R}" >&2
    echo -e "${C}├───────────────────────────────────────────────────────────┤${R}" >&2
    
    for qage in "${qages[@]}"; do
        local ts="${qage#qage_}"
        local formatted_ts="${ts:0:4}-${ts:4:2}-${ts:6:2} ${ts:9:2}:${ts:11:2}:${ts:13:2}"
        echo -e "${C}│${R}  ${G}${i})${R} ${qage}  ${Y}(${formatted_ts})${R}" >&2
        ((i++))
    done
    
    echo -e "${C}└───────────────────────────────────────────────────────────┘${R}" >&2
    echo "" >&2
    
    local selection
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Select Qage [1-${#qages[@]}] or 'q' to quit: " >&2
    read -r selection </dev/tty
    
    if [[ "$selection" == "q" ]] || [[ "$selection" == "Q" ]]; then
        echo "Selection cancelled." >&2
        return 1
    fi
    
    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt ${#qages[@]} ]; then
        echo "Invalid selection: ${selection}" >&2
        return 1
    fi
    
    echo "${qages[$((selection-1))]}"
}

# --- PERMISSION FIX HELPER (engine-aware) ---
fix_qage_permissions() {
    local qage_path="$1"
    if [ ! -d "$qage_path" ]; then return 0; fi

    if [ -n "${CONTAINER_ENGINE:-}" ] && [ "$CONTAINER_ENGINE" != "msb" ]; then
        engine_run_helper -v "${qage_path}:/fix" \
            --entrypoint /bin/bash "$IMAGE_NAME" \
            -c "chmod -R a+rwX /fix 2>/dev/null || true"
    elif command -v docker >/dev/null 2>&1; then
        docker run --rm -v "${qage_path}:/fix" \
            --entrypoint /bin/bash "$IMAGE_NAME" \
            -c "chmod -R a+rwX /fix 2>/dev/null || true" 2>/dev/null || true
    elif command -v podman >/dev/null 2>&1; then
        podman run --rm -v "${qage_path}:/fix" \
            --entrypoint /bin/bash "$IMAGE_NAME" \
            -c "chmod -R a+rwX /fix 2>/dev/null || true" 2>/dev/null || true
    else
        log_qrane "${Y}[WARN]${R} No engine for permission fix. Try: chmod -R a+rwX ${qage_path}"
    fi
}

# --- DELETE QAGE HELPER (engine-aware) ---
delete_qage() {
    local qage_path="$1"
    
    if rm -rf "$qage_path" 2>/dev/null; then
        return 0
    fi
    
    if [ -d "$qage_path" ]; then
        if [ -n "${CONTAINER_ENGINE:-}" ] && [ "$CONTAINER_ENGINE" != "msb" ]; then
            engine_run_helper -v "${qage_path}:/delete" \
                --entrypoint /bin/bash "$IMAGE_NAME" \
                -c "rm -rf /delete/* /delete/.[!.]* 2>/dev/null || true"
        elif command -v docker >/dev/null 2>&1; then
            docker run --rm -v "${qage_path}:/delete" \
                --entrypoint /bin/bash "$IMAGE_NAME" \
                -c "rm -rf /delete/* /delete/.[!.]* 2>/dev/null || true" 2>/dev/null
        elif command -v podman >/dev/null 2>&1; then
            podman run --rm -v "${qage_path}:/delete" \
                --entrypoint /bin/bash "$IMAGE_NAME" \
                -c "rm -rf /delete/* /delete/.[!.]* 2>/dev/null || true" 2>/dev/null
        else
            log_qrane "${Y}[WARN]${R} No engine for delete. Try: sudo rm -rf ${qage_path}"
        fi
        rmdir "$qage_path" 2>/dev/null || rm -rf "$qage_path" 2>/dev/null || true
    fi
}

# --- NON-INTERACTIVE QONSTRUCTION SAVE (v1.0.2) ---
save_qonstruction_non_interactive() {
    local qage_path="$1"
    local qage_name="$(basename "$qage_path")"
    local project_name="$2"

    log_qrane "Non-interactive save requested for Qonstruction: ${project_name}"
    mkdir -p "$QONSTRUCTIONS_DIR"
    project_name=$(echo "$project_name" | tr -cd '[:alnum:]_-')
    
    local qonstruction_path="${QONSTRUCTIONS_DIR}/${project_name}"
    
    if [ -d "$qonstruction_path" ]; then
        log_qrane "Qonstruction '${project_name}' already exists. Overwriting."
        rm -rf "$qonstruction_path"
    fi
    
    mkdir -p "$qonstruction_path"
    log_qrane "Saving Qonstruction to: qonstructions/${project_name}"
    cp -r "$qage_path"/* "$qonstruction_path/"
    
    cat > "$qonstruction_path/meta.yaml" <<METAEOF
# QonQrete Qonstruction Metadata
project_name: "${project_name}"
source_qage: "${qage_name}"
created_at: "$(date -Iseconds)"
qonqrete_version: "${QONQ_V}"
METAEOF
    
    log_qrane "Qonstruction saved successfully!"
    delete_qage "$qage_path"
    log_qrane "Original Qage '${qage_name}' deleted."
}

# --- QONSTRUCTIONS SAVE PROMPT ---
prompt_save_qonstruction() {
    local qage_path="$1"
    local qage_name="$(basename "$qage_path")"
    
    fix_qage_permissions "$qage_path"
    
    echo ""
    echo -e "${C}┌─────────────────────────────────────────────────┐${R}"
    echo -e "${C}│${W}           QonQrete Session Complete            ${C}│${R}"
    echo -e "${C}└─────────────────────────────────────────────────┘${R}"
    echo ""
    
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Save this run as a Qonstruction? [y/N] "
    read -n 1 -r save_answer
    echo ""
    
    if [[ ! $save_answer =~ ^[Yy]$ ]]; then
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Delete this Qage? [y/N] "
        read -n 1 -r delete_answer
        echo ""
        if [[ $delete_answer =~ ^[Yy]$ ]]; then
            delete_qage "$qage_path"
            log_qrane "Qage deleted: ${qage_name}"
        else
            log_qrane "Qage preserved at: ${qage_name}"
        fi
        return 0
    fi
    
    mkdir -p "$QONSTRUCTIONS_DIR"
    local default_name="project_${qage_name#qage_}"
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Enter project name [${default_name}]: "
    read -r project_name
    project_name="${project_name:-$default_name}"
    project_name=$(echo "$project_name" | tr -cd '[:alnum:]_-')
    
    local qonstruction_path="${QONSTRUCTIONS_DIR}/${project_name}"
    
    if [ -d "$qonstruction_path" ]; then
        log_qrane "Qonstruction '${project_name}' already exists!"
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Overwrite? [y/N] "
        read -n 1 -r overwrite
        echo ""
        if [[ ! $overwrite =~ ^[Yy]$ ]]; then
            log_qrane "Save cancelled."
            return 0
        fi
        rm -rf "$qonstruction_path"
    fi
    
    mkdir -p "$qonstruction_path"
    log_qrane "Saving Qonstruction to: qonstructions/${project_name}"
    cp -r "$qage_path"/* "$qonstruction_path/"
    
    cat > "$qonstruction_path/meta.yaml" <<METAEOF
# QonQrete Qonstruction Metadata
project_name: "${project_name}"
source_qage: "${qage_name}"
created_at: "$(date -Iseconds)"
qonqrete_version: "${QONQ_V}"
METAEOF
    
    log_qrane "Qonstruction saved successfully!"
    
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Delete original Qage? [y/N] "
    read -n 1 -r delete_qage_answer
    echo ""
    
    if [[ $delete_qage_answer =~ ^[Yy]$ ]]; then
        rm -rf "$qage_path"
        log_qrane "Original Qage deleted."
    fi
}

# --- TASQ.MD INTERACTIVE EDITOR ---
create_tasq_interactive() {
    local tasq_path="$1"
    local editor="${EDITOR:-vim}"
    
    log_qrane "No tasq.md found. Opening ${editor} to create one..."
    
    cat > "$tasq_path" <<'TASQTPL'
# TasQ - Define Your Objective

<!-- 
Welcome to QonQrete! Define your task below.
This file will be enhanced by TasqLeveler on Cycle 1.

Tips for a good TasQ:
- Be specific about what you want to build
- Include file/folder structure if you have preferences  
- Mention any specific libraries or frameworks
- Define success criteria

Example:
Create a Python CLI tool that:
1. Reads a CSV file from command line argument
2. Generates a summary report with statistics
3. Saves the report as JSON

Requirements:
- Use argparse for CLI
- Use pandas for data processing
- Include error handling for missing files
-->

# Your TasQ:


TASQTPL

    "$editor" "$tasq_path"
    
    local content=$(grep -v '^#' "$tasq_path" | grep -v '^<!--' | grep -v '^\s*$' | head -1 || true)
    if [ -z "$content" ]; then
        log_qrane "Warning: tasq.md appears to be empty or only contains comments."
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Continue anyway? [y/N] "
        read -n 1 -r continue_anyway
        echo ""
        if [[ ! $continue_anyway =~ ^[Yy]$ ]]; then
            log_qrane "Aborting. Please edit worqspace/tasq.md and try again."
            return 1
        fi
    fi
    
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
# VOLUME MOUNT PATH NORMALIZATION (Windows Git Bash / MSYS)
# ═══════════════════════════════════════════════════════════════════════════════
normalize_mount_path() {
    local path="$1"
    if [ "$DETECTED_OS" = "MSYS" ]; then
        # Convert /c/Users/... to C:/Users/... for Docker Desktop on Windows
        echo "$path" | sed 's|^/\([a-zA-Z]\)/|\1:/|'
    else
        echo "$path"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# SHARED EXECUTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

build_api_env_vars() {
    local env_vars=""
    if [ -n "${OPENAI_API_KEY-}" ]; then env_vars="$env_vars -e OPENAI_API_KEY=${OPENAI_API_KEY}"; fi
    if [ -n "${GOOGLE_API_KEY-}" ]; then env_vars="$env_vars -e GOOGLE_API_KEY=${GOOGLE_API_KEY} -e GEMINI_API_KEY=${GOOGLE_API_KEY}"; fi
    if [ -n "${GEMINI_API_KEY-}" ]; then env_vars="$env_vars -e GEMINI_API_KEY=${GEMINI_API_KEY}"; fi
    if [ -n "${ANTHROPIC_API_KEY-}" ]; then env_vars="$env_vars -e ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"; fi
    if [ -n "${DEEPSEEK_API_KEY-}" ]; then env_vars="$env_vars -e DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}"; fi
    if [ -n "${QWEN_API_KEY-}" ]; then env_vars="$env_vars -e QWEN_API_KEY=${QWEN_API_KEY}"; fi
    if [ -n "${OPENROUTER_API_KEY-}" ]; then env_vars="$env_vars -e OPENROUTER_API_KEY=${OPENROUTER_API_KEY}"; fi
    echo "$env_vars"
}

build_splash_cmd() {
    if [[ "${PY_ARGS:-}" != *"--tui"* ]]; then
        echo "if command -v chafa >/dev/null; then clear; chafa /qonqrete/qrane/qonqrete.jpg --size=128x36 --stretch; sleep 1; clear; fi;"
    fi
}

run_container() {
    local run_host_path="$1"
    local norm_script_dir norm_run_path

    norm_script_dir="$(normalize_mount_path "${SCRIPT_DIR}")"
    norm_run_path="$(normalize_mount_path "${run_host_path}")"

    local dev_mounts="-v ${norm_script_dir}/qrane:/qonqrete/qrane -v ${norm_script_dir}/worqer:/qonqrete/worqer"
    local run_mounts="-v ${norm_run_path}:${CONTAINER_WORKSPACE}"
    local splash_cmd="$(build_splash_cmd)"
    local container_cmd="${splash_cmd} exec python3 qrane/qrane.py ${PY_ARGS}"
    local api_env_vars="$(build_api_env_vars)"

    engine_run --rm -it \
        $run_mounts $dev_mounts \
        $api_env_vars \
        -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" \
        "$IMAGE_NAME" /bin/bash -c "$container_cmd"
}

# --- MAIN ARGUMENT PARSING ---
COMMAND=""
PY_ARGS=""
USE_SQRAPYARD=false
QAGE_NAME=""
CLEAN_ALL=false
QONSTRUCTION_NAME=""

# Save env override before arg parsing might interfere
CONTAINER_ENGINE_ENV="${CONTAINER_ENGINE:-}"
CONTAINER_ENGINE=""

# Detect OS early (needed for path normalization)
detect_os

if [[ $# -eq 0 ]]; then show_help; exit 0; fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        init|run|resume|clean)
            COMMAND="$1"
            shift
            ;;
        -h|--help) show_help; exit 0 ;;
        -V|--version) show_version; exit 0 ;;

        # Run/Resume options
        -a|--auto) PY_ARGS="$PY_ARGS --auto"; shift ;;
        -u|--user) PY_ARGS="$PY_ARGS --user"; shift ;;
        -t|--tui) PY_ARGS="$PY_ARGS --tui"; log_qrane "${Y}[EXPERIMENTAL]${R} TUI mode enabled."; shift ;;
        -w|--wonqrete) PY_ARGS="$PY_ARGS --wonqrete"; shift ;;

        -m|--mode)
            PY_ARGS="$PY_ARGS --mode $2"
            shift 2
            ;;
        -b|--briq-sensitivity)
            PY_ARGS="$PY_ARGS --briq-sensitivity $2"
            shift 2
            ;;
        -c|--cyqles)
            PY_ARGS="$PY_ARGS --cyqles $2"
            shift 2
            ;;

        -s|--sqrapyard) USE_SQRAPYARD=true; shift ;;

        -q|--qage)
            QAGE_NAME="$2"
            shift 2
            ;;
        
        -n|--qonstruction-name)
            QONSTRUCTION_NAME="$2"
            shift 2
            ;;

        -A|--all) CLEAN_ALL=true; shift ;;

        # Runtime/engine flags
        -M|--msb) CONTAINER_ENGINE="msb"; log_qrane "${Y}[EXPERIMENTAL]${R} Microsandbox mode enabled."; shift ;;
        -d|--docker) CONTAINER_ENGINE="docker"; shift ;;
        -p|--podman) CONTAINER_ENGINE="podman"; shift ;;

        *)
            log_qrane "[WARN] Unknown argument: $1"
            shift
            ;;
    esac
done

if [[ -z "$COMMAND" ]]; then
    log_qrane "[ERROR] No command specified."; show_help; exit 1
fi

# --- DETECT ENGINE + BUILD BACKEND ---
detect_engine
detect_build_backend

# macOS Podman: ensure machine is running (idempotent)
ensure_podman_machine

# Print runtime info
print_runtime_info

# --- EXECUTION ---
cd "$SCRIPT_DIR"

case "$COMMAND" in
    init)
        log_qrane "Initializing QonQrete..."
        BUILD_ARGS="--build-arg QONQ_VERSION=${QONQ_V}"

        engine_build -t "$IMAGE_NAME" -f Dockerfile . --progress=plain $BUILD_ARGS

        # Also tag as :latest and legacy untagged name for backward compat
        case "$CONTAINER_ENGINE" in
            docker)
                docker tag "$IMAGE_NAME" "$IMAGE_NAME_LATEST" 2>/dev/null || true
                docker tag "$IMAGE_NAME" "$IMAGE_NAME_LEGACY" 2>/dev/null || true
                ;;
            podman)
                podman tag "$IMAGE_NAME" "$IMAGE_NAME_LATEST" 2>/dev/null || true
                podman tag "$IMAGE_NAME" "$IMAGE_NAME_LEGACY" 2>/dev/null || true
                ;;
        esac
        log_qrane "Image tagged: ${IMAGE_NAME}, ${IMAGE_NAME_LATEST}, ${IMAGE_NAME_LEGACY}"
        ;;

    clean)
        log_qrane "QonQrete Cleanup Mode..."
        
        if [ "$CLEAN_ALL" = true ]; then
            if ls "${WORKSPACE_DIR}"/qage_* 1> /dev/null 2>&1; then
                qage_count=$(ls -1d "${WORKSPACE_DIR}"/qage_* 2>/dev/null | wc -l)
                log_qrane "Found ${qage_count} Qage directories."

                PROMPT_STR="${PREFIX_TPL/\{PREFIX\}/cQQ} Delete ALL ${qage_count} 'qage_*' directories? [y/N] "
                echo -ne "$PROMPT_STR"
                read -r REPLY </dev/tty

                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    for qage_dir in "${WORKSPACE_DIR}"/qage_*; do
                        if [ -d "$qage_dir" ]; then
                            delete_qage "$qage_dir"
                        fi
                    done
                    log_qrane "All Qages cleaned."
                else
                    log_qrane "Clean aborted."
                fi
            else
                log_qrane "No 'qage_*' directories found."
            fi
        elif [ -n "$QAGE_NAME" ]; then
            target_qage="${WORKSPACE_DIR}/${QAGE_NAME}"
            if [ -d "$target_qage" ]; then
                log_qrane "Found Qage: ${QAGE_NAME}"
                echo -ne "${PREFIX_TPL/\{PREFIX\}/cQQ} Delete '${QAGE_NAME}'? [y/N] "
                read -r REPLY </dev/tty
                
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    delete_qage "$target_qage"
                    log_qrane "Qage '${QAGE_NAME}' deleted."
                else
                    log_qrane "Clean aborted."
                fi
            else
                log_qrane "[ERROR] Qage '${QAGE_NAME}' not found."
                exit 1
            fi
        else
            selected=$(select_qage_interactive)
            if [ $? -ne 0 ] || [ -z "$selected" ]; then
                exit 1
            fi
            target_qage="${WORKSPACE_DIR}/${selected}"
            echo -ne "${PREFIX_TPL/\{PREFIX\}/cQQ} Delete '${selected}'? [y/N] "
            read -r REPLY </dev/tty
            
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                delete_qage "$target_qage"
                log_qrane "Qage '${selected}' deleted."
            else
                log_qrane "Clean aborted."
            fi
        fi
        ;;

    resume)
        log_qrane "QonQrete Resume Mode..."
        
        if [ -n "$QAGE_NAME" ]; then
            SOURCE_QAGE="${WORKSPACE_DIR}/${QAGE_NAME}"
        else
            selected=$(select_qage_interactive) || exit 1
            SOURCE_QAGE="${WORKSPACE_DIR}/${selected}"
            QAGE_NAME="$selected"
        fi
        
        if [ ! -d "$SOURCE_QAGE" ]; then
            log_qrane "[ERROR] Qage '${QAGE_NAME}' not found."
            exit 1
        fi
        
        log_qrane "Resuming from: ${QAGE_NAME}"
        
        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"
        
        log_qrane "Creating new Qage: ${RUN_DIR_NAME}"
        
        cp -r "$SOURCE_QAGE" "$RUN_HOST_PATH"
        
        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then 
            cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"
        fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then 
            cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"
        fi
        
        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then
            log_qrane "Using updated tasq.md from worqspace."
            max_cycle=0
            if ls "$RUN_HOST_PATH/tasq.d"/cyqle*_tasq.md 1>/dev/null 2>&1; then
                for f in "$RUN_HOST_PATH/tasq.d"/cyqle*_tasq.md; do
                    if [ -f "$f" ]; then
                        num=$(basename "$f" | grep -oP 'cyqle\K[0-9]+' || echo "0")
                        if [ "$num" -gt "$max_cycle" ]; then
                            max_cycle=$num
                        fi
                    fi
                done
            fi
            next_cycle=$((max_cycle + 1))
            cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle${next_cycle}_tasq.md"
        fi
        
        log_qrane "Handing off to Qrane in 3 seconds..."
        sleep 3

        run_container "$RUN_HOST_PATH"
        
        if [ -n "$QONSTRUCTION_NAME" ]; then
            save_qonstruction_non_interactive "$RUN_HOST_PATH" "$QONSTRUCTION_NAME"
        else
            prompt_save_qonstruction "$RUN_HOST_PATH"
        fi
        ;;

    run)
        if [ ! -f "${WORKSPACE_DIR}/config.yaml" ]; then
            log_qrane "QonQrete session ended: config.yaml not found."
            exit 1
        fi

        if [ ! -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then
            log_qrane "QonQrete session ended: pipeline_config.yaml not found."
            exit 1
        fi

        if [ ! -f "${WORKSPACE_DIR}/tasq.md" ]; then
            create_tasq_interactive "${WORKSPACE_DIR}/tasq.md" || exit 1
        fi

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        log_qrane "Seeding worQspace in Qage at: $RUN_HOST_PATH"

        mkdir -p "$RUN_HOST_PATH"/{tasq.d,exeq.d,reqap.d,qodeyard,struqture,qontext.d,bloq.d,briq.d,qontract.d}

        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"; fi

        SQRAPYARD_PATH="${WORKSPACE_DIR}/sqrapyard"
        
        if [ "$USE_SQRAPYARD" = true ]; then
            log_qrane "Sqrapyard mode enabled (-s flag detected)."
            if [ -d "$SQRAPYARD_PATH" ] && [ -n "$(ls -A "$SQRAPYARD_PATH" 2>/dev/null)" ]; then
                log_qrane "Found qontent in sqrapyard, seeding this run..."
                cp -r "$SQRAPYARD_PATH"/* "$RUN_HOST_PATH/qodeyard/"
                
                if [ -f "$SQRAPYARD_PATH/tasq.md" ]; then
                    log_qrane "Note: sqrapyard/tasq.md found but using worqspace/tasq.md (master tasq takes precedence)."
                fi
            else
                log_qrane "Sqrapyard flag used but sqrapyard is empty. Starting fresh."
            fi
        else
            log_qrane "Fresh start mode (no sqrapyard seeding)."
            if [ -d "$SQRAPYARD_PATH" ] && [ -n "$(ls -A "$SQRAPYARD_PATH" 2>/dev/null)" ]; then
                log_qrane "${Y}Note:${R} Sqrapyard contains files. Use -s/--sqrapyard to seed from it."
            fi
        fi
        
        cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"

        log_qrane "Handing off to Qrane in 3 seconds..."
        sleep 3

        run_container "$RUN_HOST_PATH"
        
        if [ -n "$QONSTRUCTION_NAME" ]; then
            save_qonstruction_non_interactive "$RUN_HOST_PATH" "$QONSTRUCTION_NAME"
        else
            prompt_save_qonstruction "$RUN_HOST_PATH"
        fi
        ;;
esac
