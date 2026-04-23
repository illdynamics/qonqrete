#!/usr/bin/env bash
# qonqrete.sh — QonQrete launcher & container orchestrator
#
# Changes from vibecoded predecessor:
#   * VERSION file is the single source of truth (fail loud if missing)
#   * One variable name: QONQ_VERSION (no more QONQ_V / QONQ_VERSION schism)
#   * `set -euo pipefail` — strict mode throughout. Functions return 0 explicitly.
#   * HOST_UID build-arg matching on Linux/WSL → no more helper containers
#   * Helper containers deleted entirely (fix_qage_permissions, engine_run_helper)
#   * delete_qage → plain rm -rf (UID match makes it work)
#   * Security flags: --security-opt=no-new-privileges, --cap-drop=ALL with
#     ZERO caps added (no gosu = no setuid = no caps needed)
#   * tmpfs hardened with nodev,nosuid,noexec
#   * Dev mounts (qrane/, worqer/) mounted read-only
#   * API keys passed as `-e KEY` (env passthrough, not argv)
#   * PY_ARGS as array, no shell-string concat, no `bash -lc` wrapper
#   * docker-entrypoint.sh eliminated — umask inlined in Dockerfile ENTRYPOINT
#   * Manifest parsing via python3 JSON, not grep+sed
#   * No silent podman security-flag fallback
#   * Podman preferred over Docker in auto-detect (rootless-native, no daemon)
#   * CONTAINER_ENGINE env override captured BEFORE being clobbered
#   * Buildx only used with Docker, never with Podman
#   * save_qonstruction_core extracted from the two duplicated save paths
#   * Dead code removed: IMAGE_NAME_LEGACY, shadow symlink, CONFIG_FILE, etc.
#   * Image tag includes host UID on Linux/WSL for per-user cache correctness

set -euo pipefail

# ============================================================================
# Paths and version — VERSION file is the single source of truth
# ============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

if [ ! -f "$VERSION_FILE" ]; then
    echo "[FATAL] VERSION file missing at ${VERSION_FILE}" >&2
    echo "        VERSION is the single source of truth — cannot continue without it." >&2
    exit 1
fi

QONQ_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [ -z "$QONQ_VERSION" ]; then
    echo "[FATAL] VERSION file at ${VERSION_FILE} is empty." >&2
    exit 1
fi
export QONQ_VERSION

VERSION_DISPLAY="QonQrete v${QONQ_VERSION}"
IMAGE_BASE="qonqrete-qage"

WORKSPACE_DIR="${SCRIPT_DIR}/worqspace"
CONTAINER_WORKSPACE="/qonq"
QONSTRUCTIONS_DIR="${WORKSPACE_DIR}/qonstructions"

if [ "$(basename "$SCRIPT_DIR")" = ".qonqrete" ]; then
    PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
    RUNTIME_DEPLOYED_IN_REPO=true
else
    PROJECT_ROOT="$SCRIPT_DIR"
    RUNTIME_DEPLOYED_IN_REPO=false
fi

load_repo_env() {
    local env_file
    for env_file in "${PROJECT_ROOT}/.env" "${SCRIPT_DIR}/.env"; do
        if [ -f "$env_file" ]; then
            set -a
            # shellcheck disable=SC1090
            . "$env_file"
            set +a
        fi
    done
}

load_repo_env

# ============================================================================
# Colors / logging
# ============================================================================

B=$'\033[1;34m'
W=$'\033[1;37m'
G=$'\033[1;32m'
Y=$'\033[1;33m'
C=$'\033[1;36m'
R=$'\033[0m'

AGENT_BASELINE_WIDTH=12
QRANE_LABEL="Qrane"
QRANE_PADDING_COUNT=$((AGENT_BASELINE_WIDTH - ${#QRANE_LABEL}))
if [ "$QRANE_PADDING_COUNT" -lt 0 ]; then
    QRANE_PADDING_COUNT=0
fi
PADDING="$(printf '%*s' "$QRANE_PADDING_COUNT" "")"
PREFIX_TPL="${B}〘{PREFIX}〙『${W}${QRANE_LABEL}${B}』${PADDING} ⸎ ${R}"

# Globals referenced by log_qrane — initialised here so `set -u` is happy.
COMMAND=""
PY_ARGS=()

log_qrane() {
    local prefix="_QQ"
    if [[ " ${PY_ARGS[*]:-} " == *" --auto "* ]]; then
        prefix="aQQ"
    elif [[ "$COMMAND" == "resume" ]]; then
        prefix="rQQ"
    elif [[ "$COMMAND" == "clean" ]]; then
        prefix="cQQ"
    fi
    echo -e "${PREFIX_TPL/\{PREFIX\}/$prefix} $1"
}

exec_qrane() {
    # Pipe-failure-tolerant runner; with `set -o pipefail`, a failure in the
    # wrapped command still propagates through the pipe.
    "$@" 2>&1 | while IFS= read -r line; do
        if [[ -n "${line//[[:space:]]/}" ]]; then
            echo -e "${PREFIX_TPL/\{PREFIX\}/_QQ} $line"
        fi
    done
}

# ============================================================================
# OS / engine detection
# ============================================================================

DETECTED_OS="Linux"
BUILD_BACKEND_MODE=""

# Capture CONTAINER_ENGINE from the parent environment BEFORE we declare the
# working variable. The old code blanked it first, then tried to capture —
# which made the documented `CONTAINER_ENGINE=podman ./qonqrete.sh` override
# silently dead. Fixed: capture first, blank the working var second.
_CONTAINER_ENGINE_FROM_ENV="${CONTAINER_ENGINE:-}"
CONTAINER_ENGINE=""
if [ -n "$_CONTAINER_ENGINE_FROM_ENV" ]; then
    CONTAINER_ENGINE="$(printf '%s' "$_CONTAINER_ENGINE_FROM_ENV" | tr '[:upper:]' '[:lower:]')"
fi

detect_os() {
    local uname_s
    uname_s="$(uname -s 2>/dev/null || echo "Unknown")"
    case "$uname_s" in
        Linux)
            if [ -f /proc/version ] && grep -qi "Microsoft\|WSL" /proc/version 2>/dev/null; then
                DETECTED_OS="WSL"
            else
                DETECTED_OS="Linux"
            fi
            ;;
        Darwin)               DETECTED_OS="Darwin" ;;
        MINGW*|MSYS*|CYGWIN*) DETECTED_OS="MSYS" ;;
        *)
            case "${OSTYPE:-}" in
                msys*|mingw*|cygwin*) DETECTED_OS="MSYS" ;;
                *)                    DETECTED_OS="Linux" ;;
            esac
            ;;
    esac
}

detect_engine() {
    # Explicit engine requests from env/flags are honored first.
    case "${CONTAINER_ENGINE:-}" in
        docker)
            if command -v docker >/dev/null 2>&1; then
                return 0
            fi
            log_qrane "${Y}[WARN]${R} Docker requested but not found. Auto-detecting."
            CONTAINER_ENGINE=""
            ;;
        podman)
            if command -v podman >/dev/null 2>&1; then
                return 0
            fi
            log_qrane "${Y}[WARN]${R} Podman requested but not found. Auto-detecting."
            CONTAINER_ENGINE=""
            ;;
        none)
            return 0
            ;;
        "")
            ;;
        *)
            log_qrane "${Y}[WARN]${R} Unknown CONTAINER_ENGINE='${CONTAINER_ENGINE}'. Auto-detecting."
            CONTAINER_ENGINE=""
            ;;
    esac

    # Default behavior: prefer Podman; otherwise use repo-native host mode.
    if command -v podman >/dev/null 2>&1; then
        CONTAINER_ENGINE="podman"
    else
        CONTAINER_ENGINE="none"
        log_qrane "${Y}[WARN]${R} Podman not found. Falling back to repo-native host execution."
    fi
}

detect_build_backend() {
    if [ "$CONTAINER_ENGINE" = "none" ]; then
        BUILD_BACKEND_MODE="host"
        return 0
    fi
    # Buildx is a Docker-only feature. Podman always uses plain builds.
    if [ "$CONTAINER_ENGINE" = "podman" ]; then
        BUILD_BACKEND_MODE="plain"
        return 0
    fi
    if [ -n "${BUILD_BACKEND:-}" ]; then
        case "$BUILD_BACKEND" in
            buildx|plain) BUILD_BACKEND_MODE="$BUILD_BACKEND"; return 0 ;;
            *) log_qrane "${Y}[WARN]${R} Unknown BUILD_BACKEND='${BUILD_BACKEND}', auto-detecting." ;;
        esac
    fi
    if docker buildx version >/dev/null 2>&1; then
        BUILD_BACKEND_MODE="buildx"
    else
        BUILD_BACKEND_MODE="plain"
    fi
}

ensure_podman_machine() {
    [ "$DETECTED_OS" = "Darwin" ] || return 0
    [ "$CONTAINER_ENGINE" = "podman" ] || return 0

    local machine_list
    machine_list="$(podman machine list --format '{{.Name}}' 2>/dev/null || true)"
    if [ -z "$machine_list" ]; then
        log_qrane "Initializing Podman machine..."
        exec_qrane podman machine init || {
            log_qrane "${Y}[ERROR]${R} Podman machine init failed."
            exit 1
        }
    fi

    local machine_running
    machine_running="$(podman machine list --format '{{.Running}}' 2>/dev/null | head -1 || echo "false")"
    if [ "$machine_running" != "true" ]; then
        log_qrane "Starting Podman machine..."
        exec_qrane podman machine start || {
            log_qrane "${Y}[ERROR]${R} Podman machine start failed."
            exit 1
        }
    fi
}

host_uid() { id -u; }

image_tag() {
    # On Linux/WSL the image is UID-specific to avoid cache conflicts between
    # users sharing the same source tree (different HOST_UID build args produce
    # different images; sharing the :latest pointer would poison each other).
    case "$DETECTED_OS" in
        Linux|WSL) printf '%s:%s-u%s\n' "$IMAGE_BASE" "$QONQ_VERSION" "$(host_uid)" ;;
        *)         printf '%s:%s\n'     "$IMAGE_BASE" "$QONQ_VERSION" ;;
    esac
}

print_runtime_info() {
    log_qrane "Container engine: ${G}${CONTAINER_ENGINE}${R}"
    log_qrane "Build backend:    ${G}${BUILD_BACKEND_MODE}${R}"
    log_qrane "OS detected:      ${G}${DETECTED_OS}${R}"
    if [ "$CONTAINER_ENGINE" != "none" ]; then
        log_qrane "Image tag:        ${G}$(image_tag)${R}"
    fi
    if [ "$RUNTIME_DEPLOYED_IN_REPO" = true ]; then
        log_qrane "Repo-native mode: ${G}${PROJECT_ROOT}${R}"
    fi
    if [ "$DETECTED_OS" = "MSYS" ]; then
        log_qrane "${Y}Git Bash detected. WSL2 is recommended.${R}"
    fi
    return 0
}

# ============================================================================
# Security flags — one place, no duplication, no silent fallback
# ============================================================================

security_flags() {
    # With USER qrane (Dockerfile) + HOST_UID match + no root phase, we can
    # drop ALL caps — no SETUID/SETGID/CHOWN/FOWNER/DAC_OVERRIDE needed.
    # no-new-privileges prevents any setuid binary from re-escalating.
    local flags=(
        --read-only
        --cap-drop=ALL
        --security-opt=no-new-privileges
        --tmpfs /tmp:rw,noexec,nosuid,nodev,size=100m
        --tmpfs /home/qrane/.cache:rw,noexec,nosuid,nodev,size=500m
    )
    # Rootless podman: keep host UID mapping consistent so bind-mounted files
    # land with the host user's ownership (equivalent of HOST_UID match for docker).
    if [ "$CONTAINER_ENGINE" = "podman" ] && [ "$(id -u)" -ne 0 ]; then
        flags+=(--userns=keep-id)
    fi
    printf '%s\n' "${flags[@]}"
}

# ============================================================================
# Engine wrappers — one branching point each, zero duplication
# ============================================================================

engine_build() {
    case "$CONTAINER_ENGINE" in
        docker)
            if [ "$BUILD_BACKEND_MODE" = "buildx" ]; then
                exec_qrane docker buildx build --load "$@"
            else
                exec_qrane docker build "$@"
            fi
            ;;
        podman)
            exec_qrane podman build "$@"
            ;;
        *)
            log_qrane "[ERROR] Unknown engine: ${CONTAINER_ENGINE}"
            exit 1
            ;;
    esac
}

engine_run() {
    local -a sec_flags cmd
    local flag
    while IFS= read -r flag; do
        [ -n "$flag" ] && sec_flags+=("$flag")
    done < <(security_flags)
    # No silent fallback. If security flags fail, surface the real error.
    cmd=("$CONTAINER_ENGINE" run)
    if [ ${#sec_flags[@]} -gt 0 ]; then
        cmd+=("${sec_flags[@]}")
    fi
    cmd+=("$@")
    "${cmd[@]}"
}

# ============================================================================
# Manifest helpers — JSON parsed by python3, not grep+sed
# ============================================================================

read_manifest_value() {
    local manifest_path="$1" field="$2"
    [ -f "$manifest_path" ] || return 0
    python3 - "$manifest_path" "$field" <<'PY' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    val = data.get(sys.argv[2], "")
    if val is not None and val != "":
        print(val)
except Exception:
    pass
PY
}

# ============================================================================
# File helpers
# ============================================================================

resolve_absolute_path() {
    # Portable absolute-path resolver. `realpath -m` isn't on macOS BSD, so
    # we delegate to python3 which is available on all target platforms.
    python3 - "$1" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
}

normalize_mount_path() {
    local path="$1"
    if [ "$DETECTED_OS" = "MSYS" ]; then
        echo "$path" | sed 's|^/\([a-zA-Z]\)/|\1:/|'
    else
        echo "$path"
    fi
}

copy_dir_contents() {
    local src="$1" dst="$2"
    [ -d "$src" ] || return 0
    mkdir -p "$dst"
    (cd "$src" && tar -cf - --exclude='.DS_Store' --exclude='._*' .) \
        | (cd "$dst" && tar -xf -)
}

copy_runtime_configs() {
    local dst="$1" name
    for name in config.yaml pipeline_config.yaml; do
        [ -f "${WORKSPACE_DIR}/${name}" ] && cp "${WORKSPACE_DIR}/${name}" "$dst/"
    done
    # v1.3.13: Six-Shooter Qontract support — copy all template docs to run-local qontract.d
    if [ -d "${WORKSPACE_DIR}/qontract.d" ]; then
        mkdir -p "$dst/qontract.d"
        copy_dir_contents "${WORKSPACE_DIR}/qontract.d" "$dst/qontract.d"
    fi
    return 0
}

is_interactive_session() {
    [ -z "${QONQ_NON_INTERACTIVE:-}" ] && [ -t 0 ] && [ -t 1 ]
}

# ============================================================================
# Qage lifecycle — no helper containers, native rm works via UID matching
# ============================================================================

delete_qage() {
    # With HOST_UID build-arg matching, qage files are owned by the host user.
    # Plain rm -rf works — no container-side chmod spray needed.
    local qage_path="$1"
    [ -d "$qage_path" ] || return 0
    rm -rf "$qage_path"
}

select_qage_interactive() {
    local qages=() i=1 qage_dir
    while IFS= read -r qage_dir; do
        [ -d "$qage_dir" ] && qages+=("$(basename "$qage_dir")")
    done < <(ls -1dt "${WORKSPACE_DIR}"/qage_* 2>/dev/null || true)

    if [ ${#qages[@]} -eq 0 ]; then
        echo "No Qage directories found in worqspace." >&2
        return 1
    fi

    echo "" >&2
    echo -e "${C}┌───────────────────────────────────────────────────────────┐${R}" >&2
    echo -e "${C}│${W}            Available Qages (newest first)                 ${C}│${R}" >&2
    echo -e "${C}├───────────────────────────────────────────────────────────┤${R}" >&2

    local qage ts formatted_ts status_summary manifest_path
    local run_status lifecycle current_stage
    for qage in "${qages[@]}"; do
        ts="${qage#qage_}"
        formatted_ts="${ts:0:4}-${ts:4:2}-${ts:6:2} ${ts:9:2}:${ts:11:2}:${ts:13:2}"
        status_summary=""
        manifest_path="${WORKSPACE_DIR}/${qage}/run-manifest.v1.json"
        if [ -f "$manifest_path" ]; then
            run_status="$(read_manifest_value "$manifest_path" "run_status")"
            lifecycle="$(read_manifest_value "$manifest_path" "lifecycle_state")"
            current_stage="$(read_manifest_value "$manifest_path" "current_stage")"
            if [ -n "$run_status" ] || [ -n "$current_stage" ]; then
                status_summary="  ${C}[${current_stage:-unknown}/${run_status:-unknown}/${lifecycle:-unknown}]${R}"
            fi
        fi
        echo -e "${C}│${R}  ${G}${i})${R} ${qage}  ${Y}(${formatted_ts})${R}${status_summary}" >&2
        ((i++)) || true
    done

    echo -e "${C}└───────────────────────────────────────────────────────────┘${R}" >&2
    echo "" >&2
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Select Qage [1-${#qages[@]}] or 'q' to quit: " >&2

    local selection
    read -r selection </dev/tty

    if [[ "$selection" == "q" || "$selection" == "Q" ]]; then
        echo "Selection cancelled." >&2
        return 1
    fi
    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt ${#qages[@]} ]; then
        echo "Invalid selection: ${selection}" >&2
        return 1
    fi

    echo "${qages[$((selection-1))]}"
}

sanitize_name() {
    local raw="$1" cleaned
    cleaned="$(printf '%s' "$raw" | tr -cd '[:alnum:]_-')"
    if [ -n "$cleaned" ]; then
        printf '%s\n' "$cleaned"
    else
        printf 'project_%s\n' "$(date +%Y%m%d_%H%M%S)"
    fi
}

write_qonstruction_meta() {
    local dst="$1" qage_name="$2" project_name="$3"
    cat > "$dst/meta.yaml" <<EOF_META
project_name: "${project_name}"
source_qage: "${qage_name}"
created_at: "$(date -Iseconds)"
qonqrete_version: "${QONQ_VERSION}"
EOF_META
}

save_qonstruction_core() {
    # Single shared implementation used by both the interactive and
    # non-interactive save paths.
    local qage_path="$1" project_name="$2"
    local qage_name
    qage_name="$(basename "$qage_path")"

    mkdir -p "$QONSTRUCTIONS_DIR"
    local qonstruction_path="${QONSTRUCTIONS_DIR}/${project_name}"
    [ -d "$qonstruction_path" ] && rm -rf "$qonstruction_path"
    if [ ! -d "$qage_path" ]; then
        echo "Qage path does not exist: $qage_path" >&2
        return 1
    fi
    copy_dir_contents "$qage_path" "$qonstruction_path" || return 1
    mkdir -p "$qonstruction_path"
    write_qonstruction_meta "$qonstruction_path" "$qage_name" "$project_name"
}

save_qonstruction_non_interactive() {
    local qage_path="$1" project_name
    project_name="$(sanitize_name "$2")"

    log_qrane "Non-interactive save requested for Qonstruction: ${project_name}"
    save_qonstruction_core "$qage_path" "$project_name"
    log_qrane "Qonstruction saved successfully!"
    delete_qage "$qage_path"
    log_qrane "Original Qage '$(basename "$qage_path")' deleted."
}

prompt_save_qonstruction() {
    local qage_path="$1" qage_name
    qage_name="$(basename "$qage_path")"

    echo ""
    echo -e "${C}┌─────────────────────────────────────────────────┐${R}"
    echo -e "${C}│${W}           QonQrete Session Complete            ${C}│${R}"
    echo -e "${C}└─────────────────────────────────────────────────┘${R}"
    echo ""

    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Save this run as a Qonstruction? [y/N] "
    local save_answer
    read -n 1 -r save_answer
    echo ""

    if [[ ! "$save_answer" =~ ^[Yy]$ ]]; then
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Delete this Qage? [y/N] "
        local delete_answer
        read -n 1 -r delete_answer
        echo ""
        if [[ "$delete_answer" =~ ^[Yy]$ ]]; then
            delete_qage "$qage_path"
            log_qrane "Qage deleted: ${qage_name}"
        else
            log_qrane "Qage preserved at: ${qage_name}"
        fi
        return 0
    fi

    local default_name="project_${qage_name#qage_}"
    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Enter project name [${default_name}]: "
    local project_name
    read -r project_name
    project_name="$(sanitize_name "${project_name:-$default_name}")"

    local qonstruction_path="${QONSTRUCTIONS_DIR}/${project_name}"
    if [ -d "$qonstruction_path" ]; then
        log_qrane "Qonstruction '${project_name}' already exists!"
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Overwrite? [y/N] "
        local overwrite
        read -n 1 -r overwrite
        echo ""
        if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
            log_qrane "Save cancelled."
            return 0
        fi
    fi

    save_qonstruction_core "$qage_path" "$project_name"
    log_qrane "Qonstruction saved successfully!"

    echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Delete original Qage? [y/N] "
    local delete_qage_answer
    read -n 1 -r delete_qage_answer
    echo ""
    if [[ "$delete_qage_answer" =~ ^[Yy]$ ]]; then
        delete_qage "$qage_path"
        log_qrane "Original Qage deleted."
    fi
}

# ============================================================================
# Task input preparation
# ============================================================================

create_tasq_interactive() {
    local tasq_path="$1" editor="${EDITOR:-vim}"
    mkdir -p "$(dirname "$tasq_path")"
    log_qrane "No default task file found. Opening ${editor} to create tasq.md..."

    cat > "$tasq_path" <<'EOF_TASQ'
# TasQ - Define Your Objective

<!--
Welcome to QonQrete! Define your task below.
This file will be clarified by Qrystallizer on Cycle 1.

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

EOF_TASQ

    "$editor" "$tasq_path"

    local content
    content="$(grep -v '^#' "$tasq_path" | grep -v '^<!--' | grep -v '^\s*$' | head -1 || true)"
    if [ -z "$content" ]; then
        log_qrane "Warning: the starter task file appears empty."
        echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Continue anyway? [y/N] "
        local continue_anyway
        read -n 1 -r continue_anyway
        echo ""
        if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
            log_qrane "Aborting. Please edit the task file and try again."
            return 1
        fi
    fi
}

task_input_path() {
    if [ -n "${TASK_SOURCE_PATH:-}" ]; then
        printf '%s\n' "$TASK_SOURCE_PATH"
    elif [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] && [ -f "${PROJECT_ROOT}/tasq.md" ]; then
        printf '%s\n' "${PROJECT_ROOT}/tasq.md"
    else
        printf '%s\n' "${WORKSPACE_DIR}/tasq.md"
    fi
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

    QONQ_TASK_SOURCE_PATH="$(resolve_absolute_path "$selected_task_path")"
    QONQ_TASK_SOURCE_LABEL="$(basename "$selected_task_path")"
    export QONQ_TASK_SOURCE_PATH QONQ_TASK_SOURCE_LABEL
}

# ============================================================================
# State / run management
# ============================================================================



resolve_target_qage() {
    # Explicit -q flag takes precedence
    if [ -n "${QAGE_NAME:-}" ]; then
        printf '%s\n' "${WORKSPACE_DIR}/${QAGE_NAME}"
        return 0
    fi
    # Otherwise: newest qage by filesystem timestamp
    local latest_qage
    latest_qage="$(ls -1dt "${WORKSPACE_DIR}"/qage_* 2>/dev/null | head -1 || true)"
    [ -n "$latest_qage" ] || return 1
    printf '%s\n' "$latest_qage"
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

    echo "$VERSION_DISPLAY"
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
    echo "Qonstrictor Result: ${target_qage}/qontract.d/qonstrictor-result.v1.json"
    echo "Execution Blueprint: ${target_qage}/planning/execution-blueprint.v1.json"
    echo "Validation Bundle: ${target_qage}/validation/validation-bundle.v1.json"
    echo "Realization Bundle: ${target_qage}/realization/realization-bundle.v1.json"
    echo "Inspection Verdict: ${target_qage}/verdict/inspection-verdict.v1.json"
    echo "Repair Plan: ${target_qage}/verdict/repair-plan.v1.json"
    echo "Continuation Metadata: ${target_qage}/continuation/continuation-metadata.v1.json"
    echo "Build Attempts: ${target_qage}/build/attempts"
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

# ============================================================================
# Repo-native seeding / output sync
# ============================================================================

seed_qodeyard_from_repo() {
    local run_host_path="$1"
    local selected_task_source="${2:-${QONQ_TASK_SOURCE_PATH:-}}"
    [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] || return 0
    [ -d "$PROJECT_ROOT" ] || return 0

    local repo_file_count
    repo_file_count="$(find "$PROJECT_ROOT" -mindepth 1 -maxdepth 1 ! -name '.git' ! -name '.qonqrete' | wc -l | tr -d ' ')"
    [ "${repo_file_count:-0}" -gt 0 ] || return 0

    local selected_task_rel=""
    if [ -n "$selected_task_source" ]; then
        selected_task_rel="$(python3 - "$PROJECT_ROOT" "$selected_task_source" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
task = Path(sys.argv[2]).resolve()
try:
    rel = task.relative_to(repo).as_posix()
except Exception:
    rel = ""
if rel and not rel.startswith(".qonqrete/"):
    print(rel)
PY
)"
    fi

    log_qrane "Repo seed enabled. Seeding current repository into qodeyard."
    if [ -n "$selected_task_rel" ]; then
        log_qrane "Excluding selected task file from seed: ${selected_task_rel}"
    fi

    mkdir -p "$run_host_path/qodeyard"

    local -a tar_excludes=(
        --exclude='.git'
        --exclude='.qonqrete'
        --exclude='.venv'
        --exclude='node_modules'
        --exclude='__pycache__'
        --exclude='.pytest_cache'
        --exclude='.mypy_cache'
        --exclude='.ruff_cache'
        --exclude='.cache'
        --exclude='.DS_Store'
        --exclude='._*'
        --exclude='worqspace'
        --exclude='worqer'
        --exclude='qrane'
        --exclude='Dockerfile'
        --exclude='qonqrete.sh'
        --exclude='requirements.txt'
        --exclude='VERSION'
        --exclude='build'
        --exclude='attempts'
        --exclude='validation-root'
        --exclude='recovery'
        --exclude='staging'
        --exclude='reqap.d'
        --exclude='qonstructions'
        --exclude='struqture'
        --exclude='exeq.d'
        --exclude='qontext.d'
        --exclude='bloq.d'
        --exclude='tasq.d'
        --exclude='briq.d'
        --exclude='qontract.d'
        --exclude='qache.d'
        --exclude='planning'
        --exclude='sqrapyard'
        --exclude='qage_*'
        --exclude='*_qonfirmer.json'
        --exclude='*_qonfirmer.md'
        --exclude='*_reqap.md'
        --exclude='*_verification.md'
        --exclude='*_smoketest.md'
        --exclude='*_smoketest.v1.json'
        --exclude='attempt-manifest.v1.json'
        --exclude='run-manifest.v1.json'
        --exclude='recovery-metadata.v1.json'
    )
    if [ -n "$selected_task_rel" ]; then
        tar_excludes+=(--exclude="$selected_task_rel" --exclude="./$selected_task_rel")
    fi

    (
        cd "$PROJECT_ROOT"
        tar -cf - "${tar_excludes[@]}" .
    ) | (
        cd "$run_host_path/qodeyard"
        tar -xf -
    )
}

warn_non_seed_visible_root_content() {
    local selected_task_source="${1:-${QONQ_TASK_SOURCE_PATH:-}}"
    [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] || return 0
    [ -d "$PROJECT_ROOT" ] || return 0

    local visible_entries
    visible_entries="$(python3 - "$PROJECT_ROOT" "$selected_task_source" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
task_raw = sys.argv[2] if len(sys.argv) > 2 else ""
task_path = Path(task_raw).resolve() if task_raw else None

entries = []
for child in sorted(repo.iterdir(), key=lambda p: p.name.lower()):
    name = child.name
    if name.startswith("."):
        continue
    if task_path is not None and child.resolve() == task_path:
        continue
    entries.append(name)

for item in entries:
    print(item)
PY
)"

    [ -z "$visible_entries" ] && return 0
    log_qrane "${Y}[WARN]${R} Non-seeded run requested, but repository root already has visible content."
    while IFS= read -r entry; do
        [ -n "$entry" ] && log_qrane "${Y}[WARN]${R}   - ${entry}"
    done <<< "$visible_entries"
}

record_pre_run_visible_snapshot() {
    local run_host_path="$1"
    local selected_task_source="${2:-${QONQ_TASK_SOURCE_PATH:-}}"
    [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] || return 0

    local snapshot_path="${run_host_path}/task/pre_run_visible_files.v1.json"
    mkdir -p "$(dirname "$snapshot_path")"
    python3 - "$PROJECT_ROOT" "$selected_task_source" "$snapshot_path" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
task_raw = sys.argv[2] if len(sys.argv) > 2 else ""
out_path = Path(sys.argv[3]).resolve()
task_path = Path(task_raw).resolve() if task_raw else None

visible_files = []
for path in sorted(repo.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(repo).as_posix()
    parts = rel.split("/")
    if any(part.startswith(".") for part in parts):
        continue
    if parts and parts[0] == ".qonqrete":
        continue
    if task_path is not None and path.resolve() == task_path:
        continue
    visible_files.append(rel)

payload = {
    "schema_version": "pre-run-visible-files.v1",
    "files": visible_files,
}
out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
    log_qrane "Recorded pre-run visible file snapshot for collision checks."
}

seed_qodeyard_from_sqrapyard() {
    local _run_host_path="$1"
    [ "${USE_SQRAPYARD:-false}" = true ] || return 0
    log_qrane "${Y}[WARN]${R} --sqrapyard is now a compatibility alias for --seed-repo."
}

sync_repo_outputs_from_qage() {
    local qage_path="$1"
    [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] || return 0
    [ -d "$qage_path" ] || return 0
    [ -d "$PROJECT_ROOT" ] || return 0

    local manifest_path="${qage_path}/run-manifest.v1.json"
    local build_bridge_path="${qage_path}/build/build-output-bridge.v1.json"
    [ -f "$manifest_path" ] || return 0
    [ -f "$build_bridge_path" ] || return 0

    local run_status
    run_status="$(read_manifest_value "$manifest_path" "run_status")"
    if [ "$run_status" != "RUN_COMPLETED" ] && [ "$run_status" != "RUN_PARTIAL" ]; then
        log_qrane "Repo-native export skipped: run status ${run_status:-unknown}."
        return 0
    fi

    local changed_files
    changed_files="$(python3 - "$qage_path" "$PROJECT_ROOT" <<'PY'
import json, sys
from pathlib import Path

try:
    qage_root = Path(sys.argv[1]).resolve()
    project_root = Path(sys.argv[2]).resolve()
    qodeyard_root = (qage_root / "qodeyard").resolve()
    build_bridge = qage_root / "build" / "build-output-bridge.v1.json"

    if not build_bridge.is_file() or not qodeyard_root.is_dir():
        sys.exit(0)

    payload = json.loads(build_bridge.read_text(encoding="utf-8"))
    changed_files = []
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
        print(rel_path)
except Exception as e:
    print(f"[sync-error] {e}", file=sys.stderr)
    sys.exit(1)
PY
    )" || {
        log_qrane "${Y}[WARN]${R} Output sync encountered errors; check stderr."
        return 0
    }

    if [ -z "$changed_files" ]; then
        log_qrane "Repo-native export found no changed files to sync."
        return 0
    fi

    local snapshot_path="${qage_path}/task/pre_run_visible_files.v1.json"
    local non_seeded_run=false
    local pre_run_visible_files=""
    if [ -f "$snapshot_path" ]; then
        non_seeded_run=true
        pre_run_visible_files="$(python3 - "$snapshot_path" <<'PY'
import json, sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for item in payload.get("files", []):
    if isinstance(item, str) and item:
        print(item)
PY
)" || pre_run_visible_files=""
    fi

    local conflicts=""
    if [ "$non_seeded_run" = true ] && [ -n "$pre_run_visible_files" ]; then
        while IFS= read -r rel_path; do
            [ -z "$rel_path" ] && continue
            if grep -Fqx -- "$rel_path" <<< "$pre_run_visible_files"; then
                conflicts+="${rel_path}"$'\n'
            fi
        done <<< "$changed_files"
    fi

    local skipped_overwrites=""
    if [ -n "$conflicts" ]; then
        if is_interactive_session && [ "${QONQ_FORCE_OVERWRITE:-0}" != "1" ]; then
            log_qrane "${Y}[WARN]${R} Non-seeded export detected existing paths. Confirmation required before overwrite."
            while IFS= read -r rel_path; do
                [ -z "$rel_path" ] && continue
                echo -ne "${PREFIX_TPL/\{PREFIX\}/_QQ} Overwrite existing file '${rel_path}'? [y/N] "
                local overwrite_answer
                read -r overwrite_answer </dev/tty || overwrite_answer="n"
                if [[ ! "$overwrite_answer" =~ ^[Yy]$ ]]; then
                    skipped_overwrites+="${rel_path}"$'\n'
                    log_qrane "Skipped overwrite for ${rel_path}"
                fi
            done <<< "$conflicts"
        elif [ "${QONQ_FORCE_OVERWRITE:-0}" = "1" ]; then
            log_qrane "${Y}[WARN]${R} Non-seeded export detected existing paths. QONQ_FORCE_OVERWRITE=1 enabled; overwriting."
        else
            log_qrane "${Y}[ERROR]${R} Non-seeded export aborted: changed outputs collide with pre-existing files."
            while IFS= read -r rel_path; do
                [ -n "$rel_path" ] && log_qrane "${Y}[ERROR]${R}   - ${rel_path}"
            done <<< "$conflicts"
            return 1
        fi
    fi

    if [ "$run_status" = "RUN_PARTIAL" ]; then
        log_qrane "Repo-native export syncing partial outputs back into target repository."
    else
        log_qrane "Repo-native export syncing built outputs back into target repository."
    fi

    local synced_files=""
    while IFS= read -r rel_path; do
        [ -z "$rel_path" ] && continue
        if [ -n "$skipped_overwrites" ] && grep -Fqx -- "$rel_path" <<< "$skipped_overwrites"; then
            continue
        fi

        local src="${qage_path}/qodeyard/${rel_path}"
        local dst="${PROJECT_ROOT}/${rel_path}"
        [ -f "$src" ] || continue

        mkdir -p "$(dirname "$dst")"
        cp -p "$src" "$dst"
        if [[ "$dst" == *.sh ]]; then
            chmod +x "$dst" || true
        fi
        synced_files+="${rel_path}"$'\n'
        log_qrane "Repo-native export synced: ${rel_path}"
    done <<< "$changed_files"

    if [ -z "$synced_files" ]; then
        log_qrane "Repo-native export completed with no file writes."
    fi
}

# ============================================================================
# Image build / existence check
# ============================================================================

image_exists() {
    local tag
    tag="$(image_tag)"
    "$CONTAINER_ENGINE" image inspect "$tag" >/dev/null 2>&1 \
        || "$CONTAINER_ENGINE" image inspect "${IMAGE_BASE}:latest" >/dev/null 2>&1
}

build_runtime_image() {
    log_qrane "Initializing QonQrete..."

    if [ "$CONTAINER_ENGINE" = "none" ]; then
        log_qrane "Host mode selected. Skipping container image build."
        return 0
    fi

    local -a build_args=(--progress=plain --build-arg "QONQ_VERSION=${QONQ_VERSION}")

    # UID matching only helps on kernel-level bind mounts (Linux + WSL2).
    # macOS/Windows Docker Desktop translates ownership via its VM layer,
    # so passing host UIDs there is pointless — default 1000 works fine.
    case "$DETECTED_OS" in
        Linux|WSL)
            local uid
            uid="$(host_uid)"
            if ! [[ "$uid" =~ ^[0-9]+$ ]]; then
                log_qrane "[ERROR] id -u returned garbage: $uid"
                exit 1
            fi
            if [ "$uid" -eq 0 ]; then
                log_qrane "${Y}[WARN]${R} Running as root on host; using default UID 1000 for qrane."
                uid=1000
            fi
            log_qrane "Matching container qrane UID to host ${G}${uid}${R}"
            build_args+=(--build-arg "HOST_UID=${uid}")
            ;;
        Darwin|MSYS)
            log_qrane "Host OS ${DETECTED_OS}: Docker Desktop VM translates ownership; using default UID 1000."
            ;;
    esac

    local tag latest_tag
    tag="$(image_tag)"
    latest_tag="${IMAGE_BASE}:latest"

    if [ ${#build_args[@]} -gt 0 ]; then
        engine_build -t "$tag" -f "${SCRIPT_DIR}/Dockerfile" "$SCRIPT_DIR" "${build_args[@]}"
    else
        engine_build -t "$tag" -f "${SCRIPT_DIR}/Dockerfile" "$SCRIPT_DIR"
    fi
    "$CONTAINER_ENGINE" tag "$tag" "$latest_tag" 2>/dev/null || true
    log_qrane "Image tagged: ${tag}, ${latest_tag}"
}

ensure_runtime_image() {
    [ "$CONTAINER_ENGINE" = "none" ] && return 0
    image_exists && return 0
    log_qrane "No local runtime image found. Auto-initializing before run."
    build_runtime_image
}

# ============================================================================
# Container run — secrets pass-through, read-only dev mounts, argv array
# ============================================================================

build_api_env_args() {
    # Pass-through form: `-e KEY` (no =VALUE) reads the value from the parent
    # environment without exposing it in docker's argv (where `ps` could see it).
    API_ENV_ARGS=()
    local key
    for key in OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY \
               ANTHROPIC_API_KEY DEEPSEEK_API_KEY QWEN_API_KEY OPENROUTER_API_KEY \
               VENICE_API_KEY MLX_API_KEY LLAMA_CPP_API_KEY; do
        if [ -n "${!key:-}" ]; then
            API_ENV_ARGS+=(-e "$key")
        fi
    done
    # Convention: if GOOGLE_API_KEY is set but GEMINI_API_KEY isn't, export
    # GEMINI_API_KEY with the same value so downstream SDKs find it.
    if [ -n "${GOOGLE_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
        export GEMINI_API_KEY="$GOOGLE_API_KEY"
        API_ENV_ARGS+=(-e GEMINI_API_KEY)
    fi
}

run_container() {
    local run_host_path="$1"

    if [ "$CONTAINER_ENGINE" = "none" ]; then
        log_qrane "Executing repo-native host run (no container engine)."
        QONQ_WORKSPACE="$run_host_path" \
        QONQ_VERSION="$QONQ_VERSION" \
        QONQ_RUN_KIND="$QONQ_RUN_KIND" \
        QONQ_RESUMED_FROM_QAGE="$QONQ_RESUMED_FROM_QAGE" \
        QONQ_REPO_SYNC_MODE="$QONQ_REPO_SYNC_MODE" \
        QONQ_TASK_SOURCE_PATH="${QONQ_TASK_SOURCE_PATH:-}" \
        QONQ_TASK_SOURCE_LABEL="${QONQ_TASK_SOURCE_LABEL:-}" \
        python3 qrane/qrane.py "${PY_ARGS[@]}"
        return $?
    fi

    local norm_script_dir norm_run_path
    norm_script_dir="$(normalize_mount_path "$SCRIPT_DIR")"
    norm_run_path="$(normalize_mount_path "$run_host_path")"

    local -a run_mounts dev_mounts tty_flags
    local dev_mount_ro_suffix=":ro"
    run_mounts=(-v "${norm_run_path}:${CONTAINER_WORKSPACE}")
    if [ "$CONTAINER_ENGINE" = "podman" ] && [ "$DETECTED_OS" = "Linux" ]; then
        dev_mount_ro_suffix=":ro,z"
    fi
    # Dev code mounts are READ-ONLY. The container must not mutate its own code.
    dev_mounts=(
        -v "${norm_script_dir}/qrane:/qonqrete/qrane${dev_mount_ro_suffix}"
        -v "${norm_script_dir}/worqer:/qonqrete/worqer${dev_mount_ro_suffix}"
    )
    tty_flags=()
    [[ -t 0 && -t 1 ]] && tty_flags=(-it)

    build_api_env_args
    local tag
    tag="$(image_tag)"

    # PY_ARGS is an array, passed as argv to python3. No shell-string concat,
    # no bash -lc wrapper, no shell-injection surface on user-provided values.
    local -a run_cmd
    run_cmd=(--rm)
    if [ ${#tty_flags[@]} -gt 0 ]; then
        run_cmd+=("${tty_flags[@]}")
    fi
    run_cmd+=("${run_mounts[@]}")
    run_cmd+=("${dev_mounts[@]}")
    if [ ${#API_ENV_ARGS[@]} -gt 0 ]; then
        run_cmd+=("${API_ENV_ARGS[@]}")
    fi
    run_cmd+=(
        -e QONQ_WORKSPACE="$CONTAINER_WORKSPACE"
        -e QONQ_VERSION
        -e QONQ_RUN_KIND
        -e QONQ_RESUMED_FROM_QAGE
        -e QONQ_REPO_SYNC_MODE
        -e QONQ_TASK_SOURCE_PATH
        -e QONQ_TASK_SOURCE_LABEL
        "$tag"
        python3 qrane/qrane.py
    )
    if [ ${#PY_ARGS[@]} -gt 0 ]; then
        run_cmd+=("${PY_ARGS[@]}")
    fi
    engine_run "${run_cmd[@]}"
}

prepare_run_exports() {
    local run_dir_name="$1" run_kind="$2"
    export QONQ_RUN_KIND="$run_kind"
    if [ "$SYNC_TO_REPO" = true ]; then
        export QONQ_REPO_SYNC_MODE="sync_to_repo_root"
    else
        export QONQ_REPO_SYNC_MODE="no_sync"
    fi
}

finalize_run_session() {
    local run_host_path="$1"
    if [ "$SYNC_TO_REPO" = true ]; then
        sync_repo_outputs_from_qage "$run_host_path"
    else
        log_qrane "Repo-native export skipped by --no-sync; outputs remain in Qage/Qonstruction paths."
    fi
    if [ -n "${QONSTRUCTION_NAME:-}" ]; then
        save_qonstruction_non_interactive "$run_host_path" "$QONSTRUCTION_NAME"
    elif [ -n "${QONQ_NON_INTERACTIVE:-}" ]; then
        log_qrane "Non-interactive mode: Qage preserved at $(basename "$run_host_path")"
    else
        prompt_save_qonstruction "$run_host_path"
    fi
}

clean_repo_outputs() {
    local target_qage="$1"
    [ "$RUNTIME_DEPLOYED_IN_REPO" = true ] || return 0
    [ -d "$target_qage" ] || return 0
    
    local snapshot_path="${target_qage}/task/pre_run_visible_files.v1.json"
    if [ ! -f "$snapshot_path" ]; then
        log_qrane "${Y}[WARN]${R} No pre-run snapshot found in $(basename "$target_qage")."
        log_qrane "        Cannot safely identify generated files for cleanup."
        return 1
    fi

    log_qrane "Cleaning generated files from repo root based on snapshot: $(basename "$target_qage")"
    
    # We identify files that are currently in the repo root but were NOT in the snapshot.
    python3 - "$PROJECT_ROOT" "$snapshot_path" <<'PY'
import json
import sys
import os
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
snapshot_path = Path(sys.argv[2]).resolve()

with open(snapshot_path) as f:
    snapshot = json.load(f)
original_files = set(snapshot.get("files", []))

current_files = []
for path in sorted(repo.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(repo).as_posix()
    parts = rel.split("/")
    if any(part.startswith(".") for part in parts):
        continue
    if parts and parts[0] == ".qonqrete":
        continue
    current_files.append(rel)

generated = [f for f in current_files if f not in original_files]

for f in generated:
    target = (repo / f).resolve()
    if not str(target).startswith(str(repo)):
        continue
    print(f"Removing generated file: {f}")
    try:
        if target.is_file():
            os.remove(target)
            # Attempt to remove empty parent directories
            parent = target.parent
            while parent != repo:
                if parent.is_dir() and not any(parent.iterdir()):
                    print(f"Removing empty directory: {parent.relative_to(repo)}")
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break
    except Exception as e:
        print(f"Error removing {f}: {e}")
PY
}

# ============================================================================
# Help / version
# ============================================================================

show_version() { echo "$VERSION_DISPLAY"; }

show_help() {
    cat <<EOF_HELP
$VERSION_DISPLAY

Usage:
  ./qonqrete.sh [COMMAND] [OPTIONS]
  ./qonqrete.sh <task-file.md> [OPTIONS]

Commands:
  init              Build the QonQrete container image.
  run               Start a new run. Canonical task input is a task file.
  resume            Continue from a previous run.
  status            Show the latest run state and audit locations.
  audit             Show audit paths for the latest or selected run.
  clean             Remove qage run directories.
  clean-outputs     Remove generated files from the repository root.

Global Options:
  -h, --help        Show this help message.
  -V, --version     Show version information.

Run Options:
  -f, --task-file <path>           Use the given task file as canonical task input.
  -a, --auto                       Enable Autonomous Mode.
  -u, --user                       Force User-gated Mode.
  -m, --mode <name>                Set operational mode.
  -b, --briq-sensitivity <N>       Set granularity (0-16).
  -B, --auto-briq-sensitivity      Force automatic briq sensitivity detection.
  -c, --cyqles <N>                 Set max total iterations (sum of all build + repair passes).
                                     Matches options.max_total_iterations in config.
                                     Build-pass and repair caps remain controlled by options.max_build_passes and repair.max_attempts_per_build_pass.
  -n, --qonstruction-name <name>   Auto-save as qonstruction.
  --seed-repo, --continue-from-repo  Seed current repository into qodeyard before run.
  -s, --sqrapyard                    Legacy alias for --seed-repo (kept for compatibility).
  -N, --no-sync                    Skip sync-back into repo root; keep results in worqspace/qonstructions/qage flows.
  -d, --docker                     Force Docker engine (auto-detect prefers Podman).
  -p, --podman                     Force Podman engine (default when both available).

Resume / Status / Audit Options:
  -q, --qage <name>                Target a specific qage run directory.
  (no args)                        Uses the latest run where applicable.

Clean Options:
  -q, --qage <name>                Clean specific Qage directory.
  -A, --all                        Clean all Qage directories.
  (no args)                        Interactive Qage selection for deletion.

Environment Overrides:
  CONTAINER_ENGINE=docker|podman   Override engine auto-detection (default: podman if available).
  BUILD_BACKEND=buildx|plain       Override build backend auto-detection (buildx is Docker-only).

Examples:
  ./qonqrete.sh tasq.md
  ./qonqrete.sh run -f tasq.md
  ./qonqrete.sh run --auto --mode security
  ./qonqrete.sh run -a -n myproject
  ./qonqrete.sh run -N -n local_only_output
  ./qonqrete.sh resume
  ./qonqrete.sh status
  ./qonqrete.sh audit -q qage_20260410_123456
  ./qonqrete.sh clean -A
EOF_HELP
}

need_value() {
    local flag="$1" next="${2-}"
    if [ -z "$next" ]; then
        log_qrane "[ERROR] Missing value for ${flag}"
        exit 1
    fi
    # Allow negative numbers as values but reject other flags.
    if [[ "$next" == -* ]] && ! [[ "$next" =~ ^-[0-9]+$ ]]; then
        log_qrane "[ERROR] Missing value for ${flag} (got another flag: $next)"
        exit 1
    fi
}

# ============================================================================
# Argument parsing — single pass, no dead branches
# ============================================================================

USE_SQRAPYARD=false
USE_REPO_SEED=false
SYNC_TO_REPO=true
QAGE_NAME=""
CLEAN_ALL=false
QONSTRUCTION_NAME=""
TASK_SOURCE_PATH=""

detect_os

if [[ $# -eq 0 ]]; then
    show_help
    exit 0
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        init|run|resume|status|audit|clean|clean-outputs)
            COMMAND="$1"; shift ;;
        -h|--help)    show_help; exit 0 ;;
        -V|--version) show_version; exit 0 ;;
        -f|--task-file)
            need_value "$1" "${2-}"
            TASK_SOURCE_PATH="$(resolve_absolute_path "$2")"
            shift 2 ;;
        -a|--auto)                       PY_ARGS+=(--auto); shift ;;
        -u|--user)                       PY_ARGS+=(--user); shift ;;
        -m|--mode)
            need_value "$1" "${2-}"; PY_ARGS+=(--mode "$2"); shift 2 ;;
        -b|--briq-sensitivity)
            need_value "$1" "${2-}"; PY_ARGS+=(--briq-sensitivity "$2"); shift 2 ;;
        -B|--auto-briq-sensitivity)      PY_ARGS+=(--auto-briq-sensitivity); shift ;;
        -c|--cyqles)
            need_value "$1" "${2-}"; PY_ARGS+=(--cyqles "$2"); shift 2 ;;
        --seed-repo|--continue-from-repo|--sync-repo)
                                           USE_REPO_SEED=true; shift ;;
        -s|--sqrapyard)                  USE_SQRAPYARD=true; USE_REPO_SEED=true; shift ;;
        -N|--no-sync)                    SYNC_TO_REPO=false; shift ;;
        -q|--qage)
            need_value "$1" "${2-}"; QAGE_NAME="$2"; shift 2 ;;
        -n|--qonstruction-name)
            need_value "$1" "${2-}"; QONSTRUCTION_NAME="$2"; shift 2 ;;
        -A|--all)                        CLEAN_ALL=true; shift ;;
        -d|--docker)                     CONTAINER_ENGINE="docker"; shift ;;
        -p|--podman)                     CONTAINER_ENGINE="podman"; shift ;;
        --)                              shift; break ;;
        -*)
            log_qrane "${Y}[WARN]${R} Unknown flag: $1"; shift ;;
        *)
            # Positional: if it's an existing file and no COMMAND set yet,
            # treat as a task file and imply `run`.
            if [ -z "$COMMAND" ] && [ -f "$1" ]; then
                COMMAND="run"
                TASK_SOURCE_PATH="$(resolve_absolute_path "$1")"
                shift
            else
                log_qrane "${Y}[WARN]${R} Ignoring positional: $1"
                shift
            fi
            ;;
    esac
done

if [[ -z "$COMMAND" ]]; then
    if [ -n "$TASK_SOURCE_PATH" ]; then
        COMMAND="run"
    else
        log_qrane "[ERROR] No command specified."
        show_help
        exit 1
    fi
fi

if [[ "$COMMAND" =~ ^(init|run|resume|clean)$ ]]; then
    detect_engine
    detect_build_backend
    ensure_podman_machine
    print_runtime_info
fi

cd "$SCRIPT_DIR"

# ============================================================================
# Dispatch
# ============================================================================

case "$COMMAND" in
    init)
        build_runtime_image
        ;;

    status)
        target_qage="$(resolve_target_qage)" || { log_qrane "[ERROR] No runs found."; exit 1; }
        show_run_status "$target_qage"
        ;;

    audit)
        target_qage="$(resolve_target_qage)" || { log_qrane "[ERROR] No runs found."; exit 1; }
        show_run_audit "$target_qage"
        ;;

    clean-outputs)
        target_qage="$(resolve_target_qage)" || { log_qrane "[ERROR] No runs found."; exit 1; }
        clean_repo_outputs "$target_qage"
        ;;

    clean)
        log_qrane "QonQrete Cleanup Mode..."
        if [ "$CLEAN_ALL" = true ]; then
            if ls "${WORKSPACE_DIR}"/qage_* >/dev/null 2>&1; then
                qage_count="$(ls -1d "${WORKSPACE_DIR}"/qage_* 2>/dev/null | wc -l | tr -d ' ')"
                log_qrane "Found ${qage_count} Qage directories."
                echo -ne "${PREFIX_TPL/\{PREFIX\}/cQQ} Delete ALL ${qage_count} 'qage_*' directories? [y/N] "
                read -r REPLY </dev/tty
                if [[ "$REPLY" =~ ^[Yy]$ ]]; then
                    for qage_dir in "${WORKSPACE_DIR}"/qage_*; do
                        [ -d "$qage_dir" ] && delete_qage "$qage_dir"
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
                echo -ne "${PREFIX_TPL/\{PREFIX\}/cQQ} Delete '${QAGE_NAME}'? [y/N] "
                read -r REPLY </dev/tty
                if [[ "$REPLY" =~ ^[Yy]$ ]]; then
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
            selected="$(select_qage_interactive)" || exit 1
            target_qage="${WORKSPACE_DIR}/${selected}"
            echo -ne "${PREFIX_TPL/\{PREFIX\}/cQQ} Delete '${selected}'? [y/N] "
            read -r REPLY </dev/tty
            if [[ "$REPLY" =~ ^[Yy]$ ]]; then
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
            selected="$(select_qage_interactive)" || exit 1
            SOURCE_QAGE="${WORKSPACE_DIR}/${selected}"
            QAGE_NAME="$selected"
        fi

        if [ ! -d "$SOURCE_QAGE" ]; then
            log_qrane "[ERROR] Qage '${QAGE_NAME}' not found."
            exit 1
        fi

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        log_qrane "Resuming from: ${QAGE_NAME}"
        log_qrane "Creating new Qage: ${RUN_DIR_NAME}"
        source_manifest="${SOURCE_QAGE}/run-manifest.v1.json"
        if [ -f "$source_manifest" ]; then
            source_run_status="$(read_manifest_value "$source_manifest" "run_status")"
            source_lifecycle="$(read_manifest_value "$source_manifest" "lifecycle_state")"
            if [ "$source_run_status" = "RUN_WAITING_FOR_INPUT" ] && [ "$source_lifecycle" = "BLOCKED" ]; then
                log_qrane "Source run is blocked on intake clarification; resume will re-enter cycle-1 clarification stages."
            fi
        fi

        mkdir -p "$RUN_HOST_PATH"
        copy_dir_contents "$SOURCE_QAGE" "$RUN_HOST_PATH"
        mkdir -p "$RUN_HOST_PATH"/{task,qontract.d,planning,estimation,build,validation,realization,verdict,continuation,audit}
        rm -f "$RUN_HOST_PATH/task/pre_run_visible_files.v1.json"
        copy_runtime_configs "$RUN_HOST_PATH"

        prepare_task_input || exit 1
        if [ -f "${WORKSPACE_DIR}/tasq.md" ]; then
            log_qrane "Canonical task input available for continuation if the scheduler/runtime needs it."
        fi

        prepare_run_exports "$RUN_DIR_NAME" "resume"
        export QONQ_RESUMED_FROM_QAGE="$QAGE_NAME"
        run_container "$RUN_HOST_PATH"
        finalize_run_session "$RUN_HOST_PATH"
        ;;

    run)
        [ -f "${WORKSPACE_DIR}/config.yaml" ]          || { log_qrane "QonQrete session ended: config.yaml not found.";          exit 1; }
        [ -f "${WORKSPACE_DIR}/pipeline_config.yaml" ] || { log_qrane "QonQrete session ended: pipeline_config.yaml not found."; exit 1; }

        ensure_runtime_image
        prepare_task_input || exit 1

        TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
        RUN_DIR_NAME="qage_${TIMESTAMP}"
        RUN_HOST_PATH="${WORKSPACE_DIR}/${RUN_DIR_NAME}"

        prepare_run_exports "$RUN_DIR_NAME" "run"
        export QONQ_RESUMED_FROM_QAGE=""

        log_qrane "Seeding worQspace in Qage at: $RUN_HOST_PATH"
        log_qrane "Canonical intake path: task file -> Qrystallizer -> Qonstrictor -> Planning -> Build -> Validation -> Realization -> Inspection"

        mkdir -p "$RUN_HOST_PATH"/{tasq.d,task,briq.d,qontract.d,planning,estimation,qodeyard,exeq.d,build,validation,realization,verdict,continuation,reqap.d,struqture,qontext.d,bloq.d,qache.d,audit}
        copy_runtime_configs "$RUN_HOST_PATH"
        if [ "$USE_REPO_SEED" = true ]; then
            seed_qodeyard_from_repo "$RUN_HOST_PATH" "${QONQ_TASK_SOURCE_PATH:-}"
            seed_qodeyard_from_sqrapyard "$RUN_HOST_PATH"
        else
            log_qrane "Default run mode: starting from empty qodeyard (no repo seed)."
            warn_non_seed_visible_root_content "${QONQ_TASK_SOURCE_PATH:-}"
            record_pre_run_visible_snapshot "$RUN_HOST_PATH" "${QONQ_TASK_SOURCE_PATH:-}"
        fi
        cp "${WORKSPACE_DIR}/tasq.md" "$RUN_HOST_PATH/tasq.d/cyqle1_tasq.md"
        run_container "$RUN_HOST_PATH"
        finalize_run_session "$RUN_HOST_PATH"
        ;;
esac
