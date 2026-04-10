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
if [ "$(basename "$SCRIPT_DIR")" = ".qonqrete" ]; then
    PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
    STATE_ROOT="$SCRIPT_DIR"
    RUNTIME_DEPLOYED_IN_REPO=true
else
    PROJECT_ROOT="$SCRIPT_DIR"
    STATE_ROOT="${PROJECT_ROOT}/.qonqrete"
    RUNTIME_DEPLOYED_IN_REPO=false
fi
STATE_RUNS_DIR="${STATE_ROOT}/runs"
STATE_LATEST_LINK="${STATE_RUNS_DIR}/latest"
STATE_LATEST_RUN_FILE="${STATE_ROOT}/state/latest-run.txt"

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

Usage:
  ./qonqrete.sh [COMMAND] [OPTIONS]
  ./qonqrete.sh <task-file.md> [OPTIONS]

Commands:
  init              Build the QonQrete container image.
  run               Start a new run. Canonical task input is a task file.
  resume            Continue from a previous run (interactive or -q <qage>).
  status            Show the latest run state, manifest path, and audit locations.
  audit             Show audit/manifest paths for the latest or selected run.
  clean             Remove legacy qage run directories.

Global Options:
  -h, --help        Show this help message.
  -V, --version     Show version information.

Run Options:
  -f, --task-file <path>       Use the given task file as canonical task input.
  -a, --auto                   Enable Autonomous Mode.
  -u, --user                   Force User-gated Mode.
  --legacy-cycle-continuation  Re-enable legacy reqap -> next tasq continuation.
  -t, --tui                    Enable TUI Mode. ${Y}[EXPERIMENTAL]${R}
  -m, --mode <n>               Set Operational Mode (program, enterprise, security, etc).
  -b, --briq-sensitivity <N>   Set Granularity (0-16). Default: 6. Higher = more briqs!
  -c, --cyqles <N>             Set max auto-cycles (1-50). Default: 3
  -n, --qonstruction-name <n>  Auto-save as qonstruction (non-interactive). v1.0.2
  -s, --sqrapyard              Legacy compatibility overlay from sqrapyard/.
  -M, --msb                    Force Microsandbox (msb). ${Y}[EXPERIMENTAL]${R}
  -d, --docker                 Force Docker engine.
  -p, --podman                 Force Podman engine.
  -w, --wonqrete               Enable experimental mode.

Resume / Status / Audit Options:
  -q, --qage <n>               Target a specific qage run directory.
  (no args)                    Uses the latest run where applicable.

Clean Options:
  -q, --qage <n>               Clean specific Qage directory.
  -A, --all                    Clean ALL Qage directories (current behavior).
  (no args)                    Interactive Qage selection for deletion.

Environment Overrides:
  CONTAINER_ENGINE=docker|podman   Override engine auto-detection.
  BUILD_BACKEND=buildx|plain       Override build backend auto-detection.

Examples:
  ./qonqrete.sh docs/demo-task.md          # Task-first run
  ./qonqrete.sh run -f docs/demo-task.md   # Explicit task-file run
  ./qonqrete.sh run --auto --mode security # Autonomous security mode
  ./qonqrete.sh run --auto --legacy-cycle-continuation
  ./qonqrete.sh run -a -n myproject        # Auto-save as 'myproject' qonstruction
  ./qonqrete.sh resume                     # Continue latest/selected run
  ./qonqrete.sh status                     # Latest manifest + stage summary
  ./qonqrete.sh audit -q qage_20260410_123456
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
    if [ "$RUNTIME_DEPLOYED_IN_REPO" = true ]; then
        log_qrane "Repo-native mode: ${G}${PROJECT_ROOT}${R}"
        log_qrane "State root:       ${G}${STATE_ROOT}${R}"
    fi

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
        local status_summary=""
        local manifest_path="${WORKSPACE_DIR}/${qage}/run-manifest.v1.json"
        if [ -f "$manifest_path" ]; then
            local run_status lifecycle current_stage
            run_status="$(grep -m1 '"run_status"' "$manifest_path" | sed -E 's/.*"run_status": "([^"]+)".*/\1/' || true)"
            lifecycle="$(grep -m1 '"lifecycle_state"' "$manifest_path" | sed -E 's/.*"lifecycle_state": "([^"]+)".*/\1/' || true)"
            current_stage="$(grep -m1 '"current_stage"' "$manifest_path" | sed -E 's/.*"current_stage": "([^"]+)".*/\1/' || true)"
            if [ -n "$run_status" ] || [ -n "$current_stage" ]; then
                status_summary="  ${C}[${current_stage:-unknown}/${run_status:-unknown}/${lifecycle:-unknown}]${R}"
            fi
        fi
        echo -e "${C}│${R}  ${G}${i})${R} ${qage}  ${Y}(${formatted_ts})${R}${status_summary}" >&2
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

sync_repo_outputs_from_qage() {
    local qage_path="$1"
    if [ "$RUNTIME_DEPLOYED_IN_REPO" != true ]; then
        return 0
    fi
    if [ ! -d "$qage_path" ] || [ ! -d "$PROJECT_ROOT" ]; then
        return 0
    fi

    local manifest_path="${qage_path}/run-manifest.v1.json"
    local build_bridge_path="${qage_path}/build/build-output-bridge.v1.json"
    if [ ! -f "$manifest_path" ] || [ ! -f "$build_bridge_path" ]; then
        return 0
    fi

    local run_status
    run_status="$(read_manifest_value "$manifest_path" "run_status")"
    if [ "$run_status" != "RUN_COMPLETED" ]; then
        log_qrane "Repo-native export skipped: run status ${run_status:-unknown}."
        return 0
    fi

    local synced_files
    synced_files="$(python3 - "$qage_path" "$PROJECT_ROOT" <<'PY'
import json
import shutil
import stat
import sys
from pathlib import Path

qage_root = Path(sys.argv[1]).resolve()
project_root = Path(sys.argv[2]).resolve()
qodeyard_root = (qage_root / "qodeyard").resolve()
build_bridge = qage_root / "build" / "build-output-bridge.v1.json"

if not build_bridge.is_file() or not qodeyard_root.is_dir():
    raise SystemExit(0)

payload = json.loads(build_bridge.read_text(encoding="utf-8"))
changed_files: list[str] = []
for rel_manifest in payload.get("group_changed_scope_manifests", []):
    manifest_path = (qage_root / rel_manifest).resolve()
    if not manifest_path.is_file():
        continue
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("changed_files", []):
        rel_path = item.get("path")
        if rel_path and rel_path not in changed_files:
            changed_files.append(rel_path)

for rel_path in changed_files:
    src = (qodeyard_root / rel_path).resolve()
    dst = (project_root / rel_path).resolve()
    if not str(src).startswith(str(qodeyard_root)):
        continue
    if not str(dst).startswith(str(project_root)):
        continue
    if not src.is_file():
        continue
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if dst.suffix == ".sh":
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(rel_path)
PY
)"

    if [ -z "${synced_files}" ]; then
        log_qrane "Repo-native export found no changed files to sync."
        return 0
    fi

    log_qrane "Repo-native export enabled. Syncing built outputs back into target repository."
    while IFS= read -r rel_path; do
        if [ -n "$rel_path" ]; then
            log_qrane "Repo-native export synced: ${rel_path}"
        fi
    done <<< "$synced_files"
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

# --- DEFAULT TASK FILE INTERACTIVE EDITOR ---
create_tasq_interactive() {
    local tasq_path="$1"
    local editor="${EDITOR:-vim}"
    mkdir -p "$(dirname "$tasq_path")"
    
    log_qrane "No default task file found. Opening ${editor} to create the starter tasq.md..."
    
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
        log_qrane "Warning: the starter task file appears to be empty or only contains comments."
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Continue anyway? [y/N] "
        read -n 1 -r continue_anyway
        echo ""
        if [[ ! $continue_anyway =~ ^[Yy]$ ]]; then
            log_qrane "Aborting. Please edit the task file and try again."
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

ensure_state_dirs() {
    mkdir -p "$STATE_RUNS_DIR" "$(dirname "$STATE_LATEST_RUN_FILE")"
}

resolve_absolute_path() {
    local input_path="$1"
    if [[ "$input_path" = /* ]]; then
        printf '%s\n' "$input_path"
    else
        printf '%s\n' "$(cd "$PWD" && cd "$(dirname "$input_path")" 2>/dev/null && pwd)/$(basename "$input_path")"
    fi
}

write_latest_run_pointer() {
    local run_host_path="$1"
    local run_dir_name
    run_dir_name="$(basename "$run_host_path")"
    ensure_state_dirs
    printf '%s\n' "$run_dir_name" > "$STATE_LATEST_RUN_FILE"
    ln -sfn "$run_host_path" "$STATE_LATEST_LINK"
    ln -sfn "$run_host_path" "${STATE_RUNS_DIR}/${run_dir_name}"
}

read_manifest_value() {
    local manifest_path="$1"
    local field_name="$2"
    if [ ! -f "$manifest_path" ]; then
        return 0
    fi
    grep -m1 "\"${field_name}\"" "$manifest_path" | sed -E "s/.*\"${field_name}\": \"([^\"]+)\".*/\1/" || true
}

resolve_target_qage() {
    if [ -n "$QAGE_NAME" ]; then
        printf '%s\n' "${WORKSPACE_DIR}/${QAGE_NAME}"
        return 0
    fi

    if [ -L "$STATE_LATEST_LINK" ]; then
        readlink "$STATE_LATEST_LINK"
        return 0
    fi

    if [ -f "$STATE_LATEST_RUN_FILE" ]; then
        local latest_name
        latest_name="$(cat "$STATE_LATEST_RUN_FILE" 2>/dev/null || true)"
        if [ -n "$latest_name" ] && [ -d "${WORKSPACE_DIR}/${latest_name}" ]; then
            printf '%s\n' "${WORKSPACE_DIR}/${latest_name}"
            return 0
        fi
    fi

    local latest_qage
    latest_qage="$(ls -1dt "${WORKSPACE_DIR}"/qage_* 2>/dev/null | head -1 || true)"
    if [ -n "$latest_qage" ]; then
        printf '%s\n' "$latest_qage"
        return 0
    fi
    return 1
}

show_run_status() {
    local target_qage="$1"
    local manifest_path="${target_qage}/run-manifest.v1.json"
    local run_name
    run_name="$(basename "$target_qage")"

    if [ ! -d "$target_qage" ]; then
        log_qrane "[ERROR] Run not found: ${target_qage}"
        return 1
    fi

    echo "$VERSION"
    echo "Run: ${run_name}"
    echo "Run Root: ${target_qage}"
    echo "Manifest: ${manifest_path}"
    if [ -f "$manifest_path" ]; then
        echo "Current Stage: $(read_manifest_value "$manifest_path" "current_stage")"
        echo "Lifecycle: $(read_manifest_value "$manifest_path" "lifecycle_state")"
        echo "Run Status: $(read_manifest_value "$manifest_path" "run_status")"
        echo "Validation Mode: $(read_manifest_value "$manifest_path" "validation_execution_mode")"
        echo "Evidence Status: $(read_manifest_value "$manifest_path" "evidence_status")"
        echo "Confidence: $(read_manifest_value "$manifest_path" "confidence_status")"
    else
        echo "Manifest: missing"
    fi
    echo "Audit Timeline: ${target_qage}/audit/timeline.md"
    echo "Audit Events: ${target_qage}/audit/events.ndjson"
    echo "Task Spec: ${target_qage}/task/task-spec.v1.json"
    echo "Validation Bundle: ${target_qage}/validation/validation-bundle.v1.json"
    echo "Realization Bundle: ${target_qage}/realization/realization-bundle.v1.json"
    echo "Inspection Verdict: ${target_qage}/verdict/inspection-verdict.v1.json"
}

show_run_audit() {
    local target_qage="$1"
    show_run_status "$target_qage" || return 1
    local timeline_path="${target_qage}/audit/timeline.md"
    if [ -f "$timeline_path" ]; then
        echo ""
        echo "Recent Audit Timeline:"
        tail -n 12 "$timeline_path"
    fi
}

task_input_path() {
    if [ -n "${TASK_SOURCE_PATH:-}" ]; then
        printf '%s\n' "$TASK_SOURCE_PATH"
        return 0
    fi
    if [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] && [ -f "${PROJECT_ROOT}/tasq.md" ]; then
        printf '%s\n' "${PROJECT_ROOT}/tasq.md"
        return 0
    fi
    printf '%s\n' "${WORKSPACE_DIR}/tasq.md"
}

prepare_task_input() {
    local selected_task_path
    selected_task_path="$(task_input_path)"

    if [ "$selected_task_path" = "${WORKSPACE_DIR}/tasq.md" ] && [ ! -f "$selected_task_path" ]; then
        create_tasq_interactive "$selected_task_path" || return 1
    fi

    if [ ! -f "$selected_task_path" ]; then
        log_qrane "[ERROR] Task file not found: ${selected_task_path}"
        return 1
    fi

    mkdir -p "$WORKSPACE_DIR"
    if [ "$selected_task_path" != "${WORKSPACE_DIR}/tasq.md" ]; then
        cp "$selected_task_path" "${WORKSPACE_DIR}/tasq.md"
        log_qrane "Task file selected: ${selected_task_path}"
        log_qrane "Canonical runtime task copy: ${WORKSPACE_DIR}/tasq.md"
    else
        log_qrane "Task file selected: ${selected_task_path}"
    fi

    export QONQ_TASK_SOURCE_PATH="$(resolve_absolute_path "$selected_task_path")"
    export QONQ_TASK_SOURCE_LABEL="$(basename "$selected_task_path")"
    return 0
}

seed_qodeyard_from_repo() {
    local run_host_path="$1"
    if [ "$RUNTIME_DEPLOYED_IN_REPO" != true ]; then
        return 0
    fi
    if [ ! -d "$PROJECT_ROOT" ]; then
        return 0
    fi

    local repo_file_count
    repo_file_count="$(find "$PROJECT_ROOT" -mindepth 1 -maxdepth 1 ! -name '.git' ! -name '.qonqrete' | wc -l | tr -d ' ')"
    if [ "${repo_file_count:-0}" -eq 0 ]; then
        return 0
    fi

    log_qrane "Repo-native import enabled. Seeding current repository into qodeyard."
    mkdir -p "$run_host_path/qodeyard"
    (
        cd "$PROJECT_ROOT"
        tar -cf - --exclude='.git' --exclude='.qonqrete' .
    ) | (
        cd "$run_host_path/qodeyard"
        tar -xf -
    )
}

seed_qodeyard_from_sqrapyard() {
    local run_host_path="$1"
    local sqrapyard_path="${WORKSPACE_DIR}/sqrapyard"
    if [ "$USE_SQRAPYARD" != true ]; then
        return 0
    fi

    log_qrane "Legacy sqrapyard compatibility overlay enabled."
    if [ -d "$sqrapyard_path" ] && [ -n "$(ls -A "$sqrapyard_path" 2>/dev/null)" ]; then
        cp -r "$sqrapyard_path"/* "$run_host_path/qodeyard/"
        log_qrane "Sqrapyard overlay copied into qodeyard."
    else
        log_qrane "Sqrapyard flag used but sqrapyard is empty."
    fi
}

image_exists() {
    case "$CONTAINER_ENGINE" in
        docker)
            docker image inspect "$IMAGE_NAME" >/dev/null 2>&1 || docker image inspect "$IMAGE_NAME_LATEST" >/dev/null 2>&1 || docker image inspect "$IMAGE_NAME_LEGACY" >/dev/null 2>&1
            ;;
        podman)
            podman image inspect "$IMAGE_NAME" >/dev/null 2>&1 || podman image inspect "$IMAGE_NAME_LATEST" >/dev/null 2>&1 || podman image inspect "$IMAGE_NAME_LEGACY" >/dev/null 2>&1
            ;;
        msb)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

build_runtime_image() {
    log_qrane "Initializing QonQrete..."
    BUILD_ARGS="--build-arg QONQ_VERSION=${QONQ_V}"
    engine_build -t "$IMAGE_NAME" -f Dockerfile . --progress=plain $BUILD_ARGS

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
}

ensure_runtime_image() {
    if image_exists; then
        return 0
    fi
    log_qrane "No local runtime image found. Auto-initializing before run."
    build_runtime_image
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
    local container_tty_flags=""

    if [[ -t 0 && -t 1 ]]; then
        container_tty_flags="-it"
    fi

    engine_run --rm ${container_tty_flags} \
        $run_mounts $dev_mounts \
        $api_env_vars \
        -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE" \
        -e QONQ_RUN_KIND="${QONQ_RUN_KIND:-run}" \
        -e QONQ_LEGACY_QAGE_ID="${QONQ_LEGACY_QAGE_ID:-}" \
        -e QONQ_RESUMED_FROM_QAGE="${QONQ_RESUMED_FROM_QAGE:-}" \
        -e QONQ_ENABLE_LEGACY_CONTINUATION="${QONQ_ENABLE_LEGACY_CONTINUATION:-}" \
        "$IMAGE_NAME" /bin/bash -c "$container_cmd"
}

# --- MAIN ARGUMENT PARSING ---
COMMAND=""
PY_ARGS=""
USE_SQRAPYARD=false
QAGE_NAME=""
CLEAN_ALL=false
QONSTRUCTION_NAME=""
TASK_SOURCE_PATH=""
QONQ_ENABLE_LEGACY_CONTINUATION=""

# Save env override before arg parsing might interfere
CONTAINER_ENGINE_ENV="${CONTAINER_ENGINE:-}"
CONTAINER_ENGINE=""

# Detect OS early (needed for path normalization)
detect_os

if [[ $# -eq 0 ]]; then show_help; exit 0; fi

case "${1:-}" in
    init|run|resume|status|audit|clean|-*|"")
        ;;
    *)
        if [ -f "$1" ]; then
            COMMAND="run"
            TASK_SOURCE_PATH="$(resolve_absolute_path "$1")"
            shift
        fi
        ;;
esac

while [[ $# -gt 0 ]]; do
    case "$1" in
        init|run|resume|status|audit|clean)
            COMMAND="$1"
            shift
            ;;
        -h|--help) show_help; exit 0 ;;
        -V|--version) show_version; exit 0 ;;

        # Run/Resume options
        -f|--task-file)
            TASK_SOURCE_PATH="$(resolve_absolute_path "$2")"
            shift 2
            ;;
        -a|--auto) PY_ARGS="$PY_ARGS --auto"; shift ;;
        -u|--user) PY_ARGS="$PY_ARGS --user"; shift ;;
        --legacy-cycle-continuation) QONQ_ENABLE_LEGACY_CONTINUATION="1"; shift ;;
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
    if [ -n "$TASK_SOURCE_PATH" ]; then
        COMMAND="run"
    else
        log_qrane "[ERROR] No command specified."; show_help; exit 1
    fi
fi

# --- DETECT ENGINE + BUILD BACKEND ---
if [[ "$COMMAND" =~ ^(init|run|resume|clean)$ ]]; then
    detect_engine
    detect_build_backend

    # macOS Podman: ensure machine is running (idempotent)
    ensure_podman_machine

    # Print runtime info
    print_runtime_info
fi

# --- EXECUTION ---
cd "$SCRIPT_DIR"

case "$COMMAND" in
    init)
        build_runtime_image
        ;;

    status)
        target_qage="$(resolve_target_qage)" || {
            log_qrane "[ERROR] No runs found."
            exit 1
        }
        show_run_status "$target_qage"
        ;;

    audit)
        target_qage="$(resolve_target_qage)" || {
            log_qrane "[ERROR] No runs found."
            exit 1
        }
        show_run_audit "$target_qage"
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
        ensure_runtime_image
        
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
        if [ -n "$QONQ_ENABLE_LEGACY_CONTINUATION" ]; then
            log_qrane "Legacy reqap continuation compatibility mode enabled for this resume."
        fi
        
        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"
        
        log_qrane "Creating new Qage: ${RUN_DIR_NAME}"
        
        cp -r "$SOURCE_QAGE" "$RUN_HOST_PATH"
        export QONQ_RUN_KIND="resume"
        export QONQ_LEGACY_QAGE_ID="$RUN_DIR_NAME"
        export QONQ_RESUMED_FROM_QAGE="$QAGE_NAME"
        
        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then 
            cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"
        fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then 
            cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"
        fi

        prepare_task_input || exit 1
        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then
            log_qrane "Using canonical task input for continuation."
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

        write_latest_run_pointer "$RUN_HOST_PATH"
        
        log_qrane "Handing off to Qrane in 3 seconds..."
        sleep 3

        run_container "$RUN_HOST_PATH"
        sync_repo_outputs_from_qage "$RUN_HOST_PATH"
        
        if [ -n "$QONSTRUCTION_NAME" ]; then
            save_qonstruction_non_interactive "$RUN_HOST_PATH" "$QONSTRUCTION_NAME"
        elif [ -n "${QONQ_NON_INTERACTIVE-}" ]; then
            log_qrane "Non-interactive mode: Qage preserved at $(basename "$RUN_HOST_PATH")"
            fix_qage_permissions "$RUN_HOST_PATH"
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

        ensure_runtime_image
        prepare_task_input || exit 1

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"
        export QONQ_RUN_KIND="run"
        export QONQ_LEGACY_QAGE_ID="$RUN_DIR_NAME"
        unset QONQ_RESUMED_FROM_QAGE

        log_qrane "Seeding worQspace in Qage at: $RUN_HOST_PATH"
        if [ -n "$QONQ_ENABLE_LEGACY_CONTINUATION" ]; then
            log_qrane "Legacy reqap continuation compatibility mode enabled for this run."
        fi

        mkdir -p "$RUN_HOST_PATH"/{tasq.d,exeq.d,reqap.d,qodeyard,struqture,qontext.d,bloq.d,briq.d,qontract.d}

        if [ -f "${WORKSPACE_DIR}/config.yaml" ]; then cp "${WORKSPACE_DIR}/config.yaml" "$RUN_HOST_PATH/"; fi
        if [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ]; then cp "${WORKSPACE_DIR}/pipeline_config.yaml" "$RUN_HOST_PATH/"; fi

        seed_qodeyard_from_repo "$RUN_HOST_PATH"
        seed_qodeyard_from_sqrapyard "$RUN_HOST_PATH"
        
        cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        write_latest_run_pointer "$RUN_HOST_PATH"

        log_qrane "Handing off to Qrane in 3 seconds..."
        sleep 3

        run_container "$RUN_HOST_PATH"
        sync_repo_outputs_from_qage "$RUN_HOST_PATH"
        
        if [ -n "$QONSTRUCTION_NAME" ]; then
            save_qonstruction_non_interactive "$RUN_HOST_PATH" "$QONSTRUCTION_NAME"
        elif [ -n "${QONQ_NON_INTERACTIVE-}" ]; then
            log_qrane "Non-interactive mode: Qage preserved at $(basename "$RUN_HOST_PATH")"
            fix_qage_permissions "$RUN_HOST_PATH"
        else
            prompt_save_qonstruction "$RUN_HOST_PATH"
        fi
        ;;
esac
