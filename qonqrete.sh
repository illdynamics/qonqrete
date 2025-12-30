#!/bin/bash
# qonqrete.sh - The Entry Point
# v1.0.0-stable - Production Release with Enforced Briq Sensitivity

set -euo pipefail

# --- DYNAMIC VERSIONING ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

if [ -f "$VERSION_FILE" ]; then
    QONQ_V=$(cat "$VERSION_FILE" | tr -d '[:space:]')
else
    QONQ_V="0.0.0"
fi

VERSION="QonQrete v${QONQ_V}-stable"
IMAGE_NAME="qonqrete-qage"
WORKSPACE_DIR="${SCRIPT_DIR}/worqspace"
CONFIG_FILE="${WORKSPACE_DIR}/pipeline_config.yaml"
CONTAINER_WORKSPACE="/qonq"
QONSTRUCTIONS_DIR="${WORKSPACE_DIR}/qonstructions"

# --- DOCKER SECURITY FLAGS ---
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
DOCKER_SECURITY_FLAGS="--read-only \
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
  resume            Resume from a previous Qage (interactive or -q <name>).
  clean             Remove Qage directories (interactive or -q <name> or -A/--all).

Global Options:
  -h, --help        Show this help message.
  -V, --version     Show version information.

Run Options:
  -a, --auto                   Enable Autonomous Mode.
  -u, --user                   Force User-gated Mode.
  -t, --tui                    Enable TUI Mode. ${Y}[EXPERIMENTAL]${R}
  -m, --mode <n>               Set Operational Mode (program, enterprise, security, etc).
  -b, --briq-sensitivity <N>   Set Granularity (0-9). Default: 7
  -c, --cyqles <N>             Set max auto-cycles (1-50). Default: 4
  -s, --sqrapyard              Seed from sqrapyard/ directory contents.
  -M, --msb                    Force Microsandbox (msb). ${Y}[EXPERIMENTAL]${R}
  -d, --docker                 Force Docker.
  -w, --wonqrete               Enable experimental mode.

Resume Options:
  -q, --qage <name>            Resume from specific Qage directory.
  (no args)                    Interactive Qage selection (kubectx-style).

Clean Options:
  -q, --qage <name>            Clean specific Qage directory.
  -A, --all                    Clean ALL Qage directories (current behavior).
  (no args)                    Interactive Qage selection for deletion.

Examples:
  ./qonqrete.sh run                        # Fresh start, no sqrapyard
  ./qonqrete.sh run -s                     # Start with sqrapyard contents
  ./qonqrete.sh run --auto --mode security # Autonomous security mode
  ./qonqrete.sh run -b 7 -c 4              # Sensitivity 7, 4 cycles (default)
  ./qonqrete.sh run -b 5 -c 6              # Complex project: sens 5, 6 cycles
  ./qonqrete.sh resume                     # Interactive Qage picker
  ./qonqrete.sh resume -q qage_20251226    # Resume specific Qage
  ./qonqrete.sh clean                      # Interactive Qage deletion
  ./qonqrete.sh clean -A                   # Delete ALL Qages
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

# --- INTERACTIVE QAGE SELECTOR (kubectx-style) ---
select_qage_interactive() {
    local qages=()
    local i=1
    
    # Find all qage_* directories, sorted by date (newest first)
    for qage_dir in $(ls -1dt "${WORKSPACE_DIR}"/qage_* 2>/dev/null); do
        if [ -d "$qage_dir" ]; then
            qages+=("$(basename "$qage_dir")")
        fi
    done
    
    if [ ${#qages[@]} -eq 0 ]; then
        echo "No Qage directories found in worqspace." >&2
        return 1
    fi
    
    # Output menu to stderr so it shows on screen (stdout is captured)
    echo "" >&2
    echo -e "${C}┌───────────────────────────────────────────────────────────┐${R}" >&2
    echo -e "${C}│${W}            Available Qages (newest first)                 ${C}│${R}" >&2
    echo -e "${C}├───────────────────────────────────────────────────────────┤${R}" >&2
    
    for qage in "${qages[@]}"; do
        # Extract timestamp for prettier display
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
    
    # Allow quit
    if [[ "$selection" == "q" ]] || [[ "$selection" == "Q" ]]; then
        echo "Selection cancelled." >&2
        return 1
    fi
    
    # Validate selection
    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt ${#qages[@]} ]; then
        echo "Invalid selection: ${selection}" >&2
        return 1
    fi
    
    # Return selected qage name to stdout (this is what gets captured)
    echo "${qages[$((selection-1))]}"
}

# --- PERMISSION FIX HELPER ---
# Fix permissions on qage directory so host user can access AND modify files
# Container creates files as qrane user, this makes them writable by host
fix_qage_permissions() {
    local qage_path="$1"
    if [ -d "$qage_path" ] && command -v docker >/dev/null 2>&1; then
        docker run --rm -v "${qage_path}:/fix" \
            --entrypoint /bin/bash "$IMAGE_NAME" \
            -c "chmod -R a+rwX /fix 2>/dev/null || true" 2>/dev/null || true
    fi
}

# --- DELETE QAGE HELPER ---
# Delete qage using docker if host permissions fail
delete_qage() {
    local qage_path="$1"
    
    # First try normal delete
    if rm -rf "$qage_path" 2>/dev/null; then
        return 0
    fi
    
    # If that failed, use docker to delete (runs as root)
    if [ -d "$qage_path" ] && command -v docker >/dev/null 2>&1; then
        docker run --rm -v "${qage_path}:/delete" \
            --entrypoint /bin/bash "$IMAGE_NAME" \
            -c "rm -rf /delete/* /delete/.[!.]* 2>/dev/null || true" 2>/dev/null
        # Now try to remove the empty directory
        rmdir "$qage_path" 2>/dev/null || rm -rf "$qage_path" 2>/dev/null || true
    fi
}

# --- QONSTRUCTIONS SAVE PROMPT ---
prompt_save_qonstruction() {
    local qage_path="$1"
    local qage_name="$(basename "$qage_path")"
    
    # Fix permissions first so we can access files
    fix_qage_permissions "$qage_path"
    
    echo ""
    echo -e "${C}┌─────────────────────────────────────────────────┐${R}"
    echo -e "${C}│${W}           QonQrete Session Complete            ${C}│${R}"
    echo -e "${C}└─────────────────────────────────────────────────┘${R}"
    echo ""
    
    local save_prompt="${PREFIX_TPL/\{PREFIX\}/_QQ} Save this run as a Qonstruction? [y/N] "
    echo -ne "$save_prompt"
    read -n 1 -r save_answer
    echo ""
    
    if [[ ! $save_answer =~ ^[Yy]$ ]]; then
        # User declined to save - ask if they want to delete the qage
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
    
    # Create qonstructions directory if it doesn't exist
    mkdir -p "$QONSTRUCTIONS_DIR"
    
    # Suggest a name based on timestamp
    local default_name="project_${qage_name#qage_}"
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Enter project name [${default_name}]: "
    read -r project_name
    
    # Use default if empty
    project_name="${project_name:-$default_name}"
    
    # Sanitize name (remove special chars except underscore and hyphen)
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
    
    # Copy the entire qage contents to the qonstruction
    log_qrane "Saving Qonstruction to: qonstructions/${project_name}"
    cp -r "$qage_path"/* "$qonstruction_path/"
    
    # Create metadata file
    cat > "$qonstruction_path/meta.yaml" <<METAEOF
# QonQrete Qonstruction Metadata
project_name: "${project_name}"
source_qage: "${qage_name}"
created_at: "$(date -Iseconds)"
qonqrete_version: "${QONQ_V}"
METAEOF
    
    log_qrane "Qonstruction saved successfully!"
    
    # Ask if user wants to delete the original qage
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Delete original Qage? [y/N] "
    read -n 1 -r delete_qage
    echo ""
    
    if [[ $delete_qage =~ ^[Yy]$ ]]; then
        rm -rf "$qage_path"
        log_qrane "Original Qage deleted."
    fi
}

# --- TASQ.MD INTERACTIVE EDITOR ---
create_tasq_interactive() {
    local tasq_path="$1"
    local editor="${EDITOR:-vim}"
    
    log_qrane "No tasq.md found. Opening ${editor} to create one..."
    
    # Create a template
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

    # Open editor
    "$editor" "$tasq_path"
    
    # Verify something was written
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

# --- MAIN ARGUMENT PARSING ---
COMMAND=""
PY_ARGS=""
RUNTIME_MODE=$(detect_runtime)
USE_SQRAPYARD=false
QAGE_NAME=""
CLEAN_ALL=false

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

        # Sqrapyard flag (for run command)
        -s|--sqrapyard) USE_SQRAPYARD=true; shift ;;

        # Qage selection (for resume/clean)
        -q|--qage)
            QAGE_NAME="$2"
            shift 2
            ;;

        # Clean all flag
        -A|--all) CLEAN_ALL=true; shift ;;

        # Runtime flags
        -M|--msb) RUNTIME_MODE="msb"; log_qrane "${Y}[EXPERIMENTAL]${R} Microsandbox mode enabled."; shift ;;
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
        log_qrane "QonQrete Cleanup Mode..."
        
        if [ "$CLEAN_ALL" = true ]; then
            # Original behavior: clean all qages
            if ls "${WORKSPACE_DIR}"/qage_* 1> /dev/null 2>&1; then
                # Count qages
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
            # Specific qage deletion
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
            # Interactive selection
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
        
        # Determine which qage to resume from
        if [ -n "$QAGE_NAME" ]; then
            SOURCE_QAGE="${WORKSPACE_DIR}/${QAGE_NAME}"
        else
            # Interactive selection
            selected=$(select_qage_interactive) || exit 1
            SOURCE_QAGE="${WORKSPACE_DIR}/${selected}"
            QAGE_NAME="$selected"
        fi
        
        if [ ! -d "$SOURCE_QAGE" ]; then
            log_qrane "[ERROR] Qage '${QAGE_NAME}' not found."
            exit 1
        fi
        
        log_qrane "Resuming from: ${QAGE_NAME}"
        
        # Create new qage with fresh timestamp
        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"
        
        log_qrane "Creating new Qage: ${RUN_DIR_NAME}"
        
        # Copy EVERYTHING from source qage (not just qodeyard)
        cp -r "$SOURCE_QAGE" "$RUN_HOST_PATH"
        
        # Update config files from workspace (in case they changed)
        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then 
            cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"
        fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then 
            cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"
        fi
        
        # Check if tasq.md exists in workspace (user might have updated it)
        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then
            log_qrane "Using updated tasq.md from worqspace."
            # Find the highest cycle number in tasq.d
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

        DEV_MOUNTS="-v ${SCRIPT_DIR}/qrane:/qonqrete/qrane -v ${SCRIPT_DIR}/worqer:/qonqrete/worqer"
        RUN_MOUNTS="-v ${RUN_HOST_PATH}:${CONTAINER_WORKSPACE}"

        SPLASH_CMD=""
        if [[ "$PY_ARGS" != *"--tui"* ]]; then
             SPLASH_CMD="if command -v chafa >/dev/null; then clear; chafa /qonqrete/qrane/splash.png --size=128x36 --stretch; sleep 1; clear; fi;"
        fi

        CONTAINER_CMD="${SPLASH_CMD} exec python3 qrane/qrane.py ${PY_ARGS}"

        API_ENV_VARS=""
        if [ -n "${OPENAI_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e OPENAI_API_KEY=${OPENAI_API_KEY}"; fi
        if [ -n "${GOOGLE_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e GOOGLE_API_KEY=${GOOGLE_API_KEY} -e GEMINI_API_KEY=${GOOGLE_API_KEY}"; fi
        if [ -n "${GEMINI_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e GEMINI_API_KEY=${GEMINI_API_KEY}"; fi
        if [ -n "${ANTHROPIC_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"; fi
        if [ -n "${DEEPSEEK_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}"; fi
        if [ -n "${QWEN_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e QWEN_API_KEY=${QWEN_API_KEY}"; fi

        if [ "$RUNTIME_MODE" == "msb" ]; then
            CMD_BIN="msb"; if command -v mbx >/dev/null 2>&1; then CMD_BIN="mbx"; fi
            $CMD_BIN run --rm -it $RUN_MOUNTS $DEV_MOUNTS \
                $API_ENV_VARS \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" "$IMAGE_NAME" /bin/bash -c "$CONTAINER_CMD"
        else
            docker run --rm -it $DOCKER_SECURITY_FLAGS \
                $RUN_MOUNTS $DEV_MOUNTS \
                $API_ENV_VARS \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" "$IMAGE_NAME" /bin/bash -c "$CONTAINER_CMD"
        fi
        
        # After run completes, prompt to save
        prompt_save_qonstruction "$RUN_HOST_PATH"
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

        # Check for tasq.md - if not present, open editor
        if [ ! -f "${WORKSPACE_DIR}/tasq.md" ]; then
            create_tasq_interactive "${WORKSPACE_DIR}/tasq.md" || exit 1
        fi

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        log_qrane "Seeding worQspace in Qage at: $RUN_HOST_PATH"

        mkdir -p "$RUN_HOST_PATH"/{tasq.d,exeq.d,reqap.d,qodeyard,struqture,qontext.d,bloq.d,briq.d}

        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"; fi

        # Sqrapyard seeding logic - ONLY if -s/--sqrapyard flag is used
        SQRAPYARD_PATH="${WORKSPACE_DIR}/sqrapyard"
        
        if [ "$USE_SQRAPYARD" = true ]; then
            log_qrane "Sqrapyard mode enabled (-s flag detected)."
            if [ -d "$SQRAPYARD_PATH" ] && [ -n "$(ls -A "$SQRAPYARD_PATH" 2>/dev/null)" ]; then
                log_qrane "Found qontent in sqrapyard, seeding this run..."
                cp -r "$SQRAPYARD_PATH"/* "$RUN_HOST_PATH/qodeyard/"
                
                # Check if sqrapyard has its own tasq.md
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
        
        # Always use workspace tasq.md
        cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"

        log_qrane "Handing off to Qrane in 3 seconds..."
        sleep 3

        DEV_MOUNTS="-v ${SCRIPT_DIR}/qrane:/qonqrete/qrane -v ${SCRIPT_DIR}/worqer:/qonqrete/worqer"
        RUN_MOUNTS="-v ${RUN_HOST_PATH}:${CONTAINER_WORKSPACE}"

        SPLASH_CMD=""
        if [[ "$PY_ARGS" != *"--tui"* ]]; then
             SPLASH_CMD="if command -v chafa >/dev/null; then clear; chafa /qonqrete/qrane/splash.png --size=128x36 --stretch; sleep 1; clear; fi;"
        fi

        CONTAINER_CMD="${SPLASH_CMD} exec python3 qrane/qrane.py ${PY_ARGS}"

        API_ENV_VARS=""
        if [ -n "${OPENAI_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e OPENAI_API_KEY=${OPENAI_API_KEY}"; fi
        if [ -n "${GOOGLE_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e GOOGLE_API_KEY=${GOOGLE_API_KEY} -e GEMINI_API_KEY=${GOOGLE_API_KEY}"; fi
        if [ -n "${GEMINI_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e GEMINI_API_KEY=${GEMINI_API_KEY}"; fi
        if [ -n "${ANTHROPIC_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"; fi
        if [ -n "${DEEPSEEK_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}"; fi
        if [ -n "${QWEN_API_KEY-}" ]; then API_ENV_VARS="$API_ENV_VARS -e QWEN_API_KEY=${QWEN_API_KEY}"; fi

        if [ "$RUNTIME_MODE" == "msb" ]; then
            CMD_BIN="msb"; if command -v mbx >/dev/null 2>&1; then CMD_BIN="mbx"; fi
            $CMD_BIN run --rm -it $RUN_MOUNTS $DEV_MOUNTS \
                $API_ENV_VARS \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" "$IMAGE_NAME" /bin/bash -c "$CONTAINER_CMD"
        else
            docker run --rm -it $DOCKER_SECURITY_FLAGS \
                $RUN_MOUNTS $DEV_MOUNTS \
                $API_ENV_VARS \
                -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" "$IMAGE_NAME" /bin/bash -c "$CONTAINER_CMD"
        fi
        
        # After run completes, prompt to save
        prompt_save_qonstruction "$RUN_HOST_PATH"
        ;;
esac
