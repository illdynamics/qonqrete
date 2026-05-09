#!/usr/bin/env bash
set -euo pipefail

# QonQrete Bootstrap — deploy the runtime from a cloned repo into a project.
# Bash 3.2 compatible: no associative arrays.
#
# Usage:
#   ./qonqrete-bootstrap.sh                    # deploy to current directory
#   ./qonqrete-bootstrap.sh /path/to/project    # deploy to specific project
#   ./qonqrete-bootstrap.sh --auto /path/to/project
#
# Auto mode:
#   QONQRETE_AUTO=1 QONQRETE_PROVIDER=deepseek QONQRETE_MODEL=deepseek-chat \
#   ./qonqrete-bootstrap.sh /path/to/project

say() { printf '%s\n' "$*"; }
fail() { printf '❌ %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

prompt() {
    local msg="$*"
    local ans=""
    if [ -r /dev/tty ] && [ -w /dev/tty ]; then
        printf '%s ' "$msg" > /dev/tty
        IFS= read -r ans < /dev/tty || ans=""
    else
        printf '%s ' "$msg" >&2
        IFS= read -r ans || ans=""
    fi
    printf '%s\n' "$ans"
}

get_env_var() {
    local name="$1"
    [ -n "$name" ] || return 0
    eval 'printf "%s" "${'"$name"':-}"'
}

preview_secret() {
    local s="${1-}"
    local len=${#s}
    if [ "$len" -le 12 ]; then
        printf '<set:%s chars>' "$len"
    else
        printf '%s...%s' "${s:0:8}" "${s:$((len - 4)):4}"
    fi
}

shell_single_quote_payload() {
    printf '%s' "${1-}" | sed "s/'/'\\\\''/g"
}

usage() {
    cat <<'USAGE'
Usage: qonqrete-bootstrap.sh [--auto] [/path/to/project]

Deploy QonQrete runtime from the current cloned repo into a target project.

Environment overrides:
  QONQRETE_AUTO=1
  QONQRETE_PROVIDER=deepseek
  QONQRETE_MODEL=deepseek-chat
  QONQRETE_API_BASE_URL=http://localhost:8080/v1
USAGE
}

AUTO_MODE=0
TARGET_ARG=""
if [ "$#" -gt 0 ]; then
    for arg in "$@"; do
        case "$arg" in
            --auto|-a) AUTO_MODE=1 ;;
            --help|-h) usage; exit 0 ;;
            *)
                if [ -z "$TARGET_ARG" ]; then
                    TARGET_ARG="$arg"
                else
                    fail "Unexpected extra argument: $arg"
                fi
                ;;
        esac
    done
fi
[ "${QONQRETE_AUTO:-0}" = "1" ] && AUTO_MODE=1

TARGET="${TARGET_ARG:-.}"
TARGET_DISPLAY="$TARGET"
TARGET="$(cd "$TARGET" 2>/dev/null && pwd || echo "")"
if [ -z "$TARGET" ]; then
    fail "Target directory does not exist: ${TARGET_DISPLAY}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${TARGET}/.qonqrete"

# ── Colour helpers ───────────────────────────────────────────────────────────
BOLD=""; CYAN=""; GREEN=""; YELLOW=""; RED=""; RESET=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD="$(tput bold 2>/dev/null || true)"
    CYAN="$(tput setaf 6 2>/dev/null || true)"
    GREEN="$(tput setaf 2 2>/dev/null || true)"
    YELLOW="$(tput setaf 3 2>/dev/null || true)"
    RED="$(tput setaf 1 2>/dev/null || true)"
    RESET="$(tput sgr0 2>/dev/null || true)"
fi

# ── Provider catalog, Bash 3.2-safe ──────────────────────────────────────────

PROVIDERS_ORDERED=(
    "openai" "codex" "google" "gemini-cli" "anthropic" "claude-code"
    "deepseek" "codeseeq" "venice" "qwen" "openrouter"
    "mlx" "llama-cpp"
)
DEFAULT_PROVIDER_INDEX=7

provider_label() {
    case "$1" in
        openai)      printf '%s' 'OpenAI (API)' ;;
        codex)       printf '%s' 'OpenAI Codex (CLI)' ;;
        google)      printf '%s' 'Google Gemini (API)' ;;
        gemini-cli)  printf '%s' 'Gemini CLI' ;;
        anthropic)   printf '%s' 'Anthropic (API)' ;;
        claude-code) printf '%s' 'Claude Code (CLI)' ;;
        deepseek)    printf '%s' 'DeepSeek (API)' ;;
        codeseeq)    printf '%s' 'CodeSeeq (Codex CLI on DeepSeek)' ;;
        venice)      printf '%s' 'Venice (API)' ;;
        qwen)        printf '%s' 'Qwen (API)' ;;
        openrouter)  printf '%s' 'OpenRouter (API)' ;;
        mlx)         printf '%s' 'MLX (local/LAN)' ;;
        llama-cpp)   printf '%s' 'Llama-cpp (local/LAN)' ;;
        *)           printf '%s' "$1" ;;
    esac
}

provider_env() {
    case "$1" in
        openai|codex)          printf '%s' 'OPENAI_API_KEY' ;;
        google|gemini-cli)     printf '%s' 'GOOGLE_API_KEY' ;;
        anthropic|claude-code) printf '%s' 'ANTHROPIC_API_KEY' ;;
        deepseek|codeseeq)     printf '%s' 'DEEPSEEK_API_KEY' ;;
        venice)                printf '%s' 'VENICE_API_KEY' ;;
        qwen)                  printf '%s' 'QWEN_API_KEY' ;;
        openrouter)            printf '%s' 'OPENROUTER_API_KEY' ;;
        mlx)                   printf '%s' 'MLX_API_KEY' ;;
        llama-cpp)             printf '%s' 'LLAMA_CPP_API_KEY' ;;
        *)                     printf '%s' '' ;;
    esac
}

provider_models() {
    case "$1" in
        openai)      printf '%s' 'gpt-4.1 gpt-4.1-mini gpt-4.1-nano gpt-4o gpt-4o-mini o3-mini o4-mini' ;;
        codex)       printf '%s' 'gpt-5-codex gpt-5.5-codex-mini' ;;
        google)      printf '%s' 'gemini-2.5-pro gemini-2.5-flash gemini-2.0-flash gemini-2.0-flash-lite' ;;
        gemini-cli)  printf '%s' 'gemini-2.5-pro gemini-2.5-flash' ;;
        anthropic)   printf '%s' 'claude-sonnet-4-20250514 claude-haiku-4-5-20251001 claude-opus-4-20250514' ;;
        claude-code) printf '%s' 'claude-sonnet-4-20250514 claude-opus-4-20250514' ;;
        deepseek)    printf '%s' 'deepseek-chat deepseek-reasoner' ;;
        codeseeq)    printf '%s' 'deepseek-v4-flash deepseek-v4-flash-thinking deepseek-v4-pro deepseek-v4-pro-thinking' ;;
        venice)      printf '%s' 'deepseek-v3.2 qwen3-coder-480b-a35b-instruct-turbo venice-uncensored llama-3.3-70b' ;;
        qwen)        printf '%s' 'qwen-plus qwen-turbo qwen-max' ;;
        openrouter)  printf '%s' 'anthropic/claude-sonnet-4 openai/gpt-4.1 google/gemini-2.5-pro deepseek/deepseek-chat-v3' ;;
        mlx|llama-cpp) printf '%s' '' ;;
        *)           printf '%s' '' ;;
    esac
}

provider_notes() {
    case "$1" in
        codex)       printf '%s' 'Requires the official Codex CLI installed on your system.' ;;
        google)      printf '%s' 'GOOGLE_API_KEY or GEMINI_API_KEY accepted.' ;;
        gemini-cli)  printf '%s' 'Requires the Gemini CLI installed on your system.' ;;
        claude-code) printf '%s' 'Requires the Claude Code CLI installed on your system.' ;;
        deepseek)    printf '%s' 'Default provider. DEEPSEEK_API_KEY required.' ;;
        codeseeq)    printf '%s' 'Uses CodeSeeq CLI wrapper. Requires DEEPSEEK_API_KEY + CodeSeeq installed.' ;;
        venice)      printf '%s' 'VENICE_API_KEY required. Many models available — see Venice docs for full list.' ;;
        openrouter)  printf '%s' 'Multi-provider gateway. OPENROUTER_API_KEY required.' ;;
        mlx)         printf '%s' 'Local MLX (Apple Silicon) runtime. Model name optional. api_base_url required in config.' ;;
        llama-cpp)   printf '%s' 'Local llama.cpp runtime. Model name optional. api_base_url required in config.' ;;
        *)           printf '%s' '' ;;
    esac
}

provider_config() {
    case "$1" in
        google|gemini-cli)   printf '%s' 'gemini' ;;
        codex)               printf '%s' 'openai' ;;
        claude-code)         printf '%s' 'anthropic' ;;
        *)                   printf '%s' "$1" ;;
    esac
}

provider_exists() {
    local want="$1"
    local pid
    for pid in "${PROVIDERS_ORDERED[@]}"; do
        [ "$pid" = "$want" ] && return 0
    done
    return 1
}

# ── Validation ───────────────────────────────────────────────────────────────

if [ ! -f "${SCRIPT_DIR}/qonqrete.sh" ] && [ ! -f "${SCRIPT_DIR}/.qonqrete/qonqrete.sh" ]; then
    fail "Could not find qonqrete.sh. Make sure you're running this from the cloned QonQrete repo."
fi

if [ -f "${SCRIPT_DIR}/.qonqrete/qonqrete.sh" ]; then
    RUNTIME_SRC="${SCRIPT_DIR}/.qonqrete"
elif [ -f "${SCRIPT_DIR}/qonqrete.sh" ]; then
    RUNTIME_SRC="${SCRIPT_DIR}"
else
    fail "Cannot determine runtime source directory."
fi

# ── Interactive setup ────────────────────────────────────────────────────────

interactive_setup() {
    say "${BOLD}Step 1: Select your AI provider${RESET}"
    say ""
    say "  This provider will be used for all primary agents"
    say "  (Qrystallizer, InstruQtor, ConstruQtor, InspeQtor)."
    say ""

    local i=1
    local pid note label
    PROVIDER_NUM=()
    for pid in "${PROVIDERS_ORDERED[@]}"; do
        label="$(provider_label "$pid")"
        note="$(provider_notes "$pid")"
        [ -n "$note" ] && note=" — $note"
        printf "  ${GREEN}%2d${RESET}) %s%s\n" "$i" "$label" "$note"
        PROVIDER_NUM[$i]="$pid"
        i=$((i + 1))
    done

    say ""
    SELECTED_PROVIDER=""
    while [ -z "$SELECTED_PROVIDER" ]; do
        REPLY="$(prompt "  Choice [$DEFAULT_PROVIDER_INDEX = DeepSeek (default)]:")"
        REPLY="${REPLY:-$DEFAULT_PROVIDER_INDEX}"
        if [[ "$REPLY" =~ ^[0-9]+$ ]] && [ -n "${PROVIDER_NUM[$REPLY]:-}" ]; then
            SELECTED_PROVIDER="${PROVIDER_NUM[$REPLY]}"
        else
            for pid in "${PROVIDERS_ORDERED[@]}"; do
                [ "$pid" = "$REPLY" ] && SELECTED_PROVIDER="$pid" && break
            done
            [ -z "$SELECTED_PROVIDER" ] && say "  ${RED}Invalid choice. Enter a number or provider name.${RESET}"
        fi
    done

    say ""
    say "  ✅ Selected: ${GREEN}$(provider_label "$SELECTED_PROVIDER")${RESET}"
    say ""

    say "${BOLD}Step 2: Select a model${RESET}"
    say ""

    local MODEL_LIST
    MODEL_LIST="$(provider_models "$SELECTED_PROVIDER")"
    if [ -n "$MODEL_LIST" ]; then
        say "  Available models for $(provider_label "$SELECTED_PROVIDER"):"
        say ""
        i=1
        MODEL_NUM=()
        MODELS_ARRAY=()
        local m
        for m in $MODEL_LIST; do
            printf "  ${GREEN}%2d${RESET}) %s\n" "$i" "$m"
            MODEL_NUM[$i]="$m"
            MODELS_ARRAY[$((i - 1))]="$m"
            i=$((i + 1))
        done
        say "  ${GREEN} 0${RESET}) Custom model name"
        say ""
        SELECTED_MODEL=""
        while [ -z "$SELECTED_MODEL" ]; do
            REPLY="$(prompt "  Choice [1 = ${MODELS_ARRAY[0]}]:")"
            REPLY="${REPLY:-1}"
            if [ "$REPLY" = "0" ]; then
                SELECTED_MODEL="$(prompt "  Enter custom model name:")"
                [ -n "$SELECTED_MODEL" ] || { say "  ${RED}Model name cannot be empty.${RESET}"; SELECTED_MODEL=""; }
            elif [[ "$REPLY" =~ ^[0-9]+$ ]] && [ -n "${MODEL_NUM[$REPLY]:-}" ]; then
                SELECTED_MODEL="${MODEL_NUM[$REPLY]}"
            else
                say "  ${RED}Invalid choice. Enter a number.${RESET}"
            fi
        done
    else
        if [ "$SELECTED_PROVIDER" = "mlx" ] || [ "$SELECTED_PROVIDER" = "llama-cpp" ]; then
            say "  $(provider_label "$SELECTED_PROVIDER") needs an api_base_url."
            say "  Example: http://localhost:8080/v1"
            say ""
            API_BASE_URL="$(prompt "  Enter api_base_url:")"
            SELECTED_MODEL="$(prompt "  Enter model name [optional, press Enter to skip]:")"
        else
            SELECTED_MODEL="$(prompt "  Enter model name [optional, press Enter to skip]:")"
        fi
    fi

    say ""
    say "  ✅ Selected model: ${GREEN}${SELECTED_MODEL:-<none>}${RESET}"
    say ""

    say "${BOLD}Step 3: API key${RESET}"
    say ""

    ENV_VAR="$(provider_env "$SELECTED_PROVIDER")"
    DETECTED_KEY="$(get_env_var "$ENV_VAR")"
    API_KEY=""

    if [ -n "$DETECTED_KEY" ]; then
        say "  🔍 Detected ${ENV_VAR}=$(preview_secret "$DETECTED_KEY") in your environment."
        REPLY="$(prompt "  Use this key? [Y/n]:")"
        REPLY="${REPLY:-y}"
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            API_KEY="$DETECTED_KEY"
        else
            API_KEY="$(prompt "  Enter ${ENV_VAR}:")"
        fi
    else
        say "  No ${ENV_VAR} detected in environment."
        API_KEY="$(prompt "  Enter ${ENV_VAR}:")"
    fi

    if [ "$ENV_VAR" = "GOOGLE_API_KEY" ] && [ -z "$API_KEY" ]; then
        DETECTED_KEY="$(get_env_var GEMINI_API_KEY)"
        if [ -n "$DETECTED_KEY" ]; then
            say "  🔍 Detected GEMINI_API_KEY=$(preview_secret "$DETECTED_KEY") in your environment."
            REPLY="$(prompt "  Use this key? [Y/n]:")"
            REPLY="${REPLY:-y}"
            [[ "$REPLY" =~ ^[Yy]$ ]] && API_KEY="$DETECTED_KEY"
        fi
    fi

    [ -z "$API_KEY" ] && say "  ${YELLOW}⚠️  No API key provided. You can set ${ENV_VAR} later.${RESET}"
    say ""
}

# ── Welcome ──────────────────────────────────────────────────────────────────

say ""
say "${BOLD}${CYAN}🧱  QonQrete Bootstrap${RESET}"
say ""
say "   Target:  ${TARGET}"
say "   Runtime: ${RUNTIME_SRC}"
say ""

if [ "$AUTO_MODE" = "1" ]; then
    SELECTED_PROVIDER="${QONQRETE_PROVIDER:-deepseek}"
    provider_exists "$SELECTED_PROVIDER" || fail "Unknown QONQRETE_PROVIDER: $SELECTED_PROVIDER"
    SELECTED_MODEL="${QONQRETE_MODEL:-deepseek-chat}"
    API_BASE_URL="${QONQRETE_API_BASE_URL:-${API_BASE_URL:-}}"
    ENV_VAR="$(provider_env "$SELECTED_PROVIDER")"
    API_KEY="$(get_env_var "$ENV_VAR")"
    say "🤖 Auto mode: provider=${SELECTED_PROVIDER}, model=${SELECTED_MODEL}"
    say ""
else
    interactive_setup
fi

# ── Deploy runtime ───────────────────────────────────────────────────────────

if [ -d "$RUNTIME_DIR" ]; then
    BACKUP="${RUNTIME_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
    say "♻️  ${RUNTIME_DIR} already exists. Moving to ${BACKUP}"
    mv "$RUNTIME_DIR" "$BACKUP"
fi

say "📦 Deploying QonQrete to ${RUNTIME_DIR}..."
mkdir -p "$RUNTIME_DIR"

if need_cmd rsync; then
    rsync -a \
        --exclude='.git/' \
        --exclude='.gitignore' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache/' \
        --exclude='.ruff_cache/' \
        --exclude='.mypy_cache/' \
        --exclude='.gradle/' \
        --exclude='node_modules/' \
        --exclude='.venv/' \
        --exclude='.test_venv/' \
        --exclude='.codeseeq/' \
        --exclude='.DS_Store' \
        --exclude='._*' \
        --exclude='__MACOSX/' \
        --exclude='benchmarks/' \
        --exclude='qonqrete-bootstrap.sh' \
        --exclude='*.zip' \
        --exclude='*.sha256' \
        "$RUNTIME_SRC/" "$RUNTIME_DIR/"
else
    say "⚠️  rsync not found; using tar copy fallback."
    (
        cd "$RUNTIME_SRC"
        tar \
            --exclude='.git' \
            --exclude='.gitignore' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='.pytest_cache' \
            --exclude='.ruff_cache' \
            --exclude='.mypy_cache' \
            --exclude='.gradle' \
            --exclude='node_modules' \
            --exclude='.venv' \
            --exclude='.test_venv' \
            --exclude='.codeseeq' \
            --exclude='.DS_Store' \
            --exclude='._*' \
            --exclude='__MACOSX' \
            --exclude='benchmarks' \
            --exclude='qonqrete-bootstrap.sh' \
            --exclude='*.zip' \
            --exclude='*.sha256' \
            -cf - .
    ) | (
        cd "$RUNTIME_DIR"
        tar -xf -
    )
fi

chmod +x "$RUNTIME_DIR/qonqrete.sh"

# ── Configure agents ─────────────────────────────────────────────────────────

CONFIG_FILE="${RUNTIME_DIR}/worqspace/config.yaml"

if [ -f "$CONFIG_FILE" ]; then
    say "⚙️  Configuring agents to use $(provider_label "$SELECTED_PROVIDER") / ${SELECTED_MODEL:-default}..."
    export API_BASE_URL="${API_BASE_URL:-}"
    CONFIG_PROVIDER="$(provider_config "$SELECTED_PROVIDER")"

    if need_cmd python3; then
        python3 - "$CONFIG_FILE" "$CONFIG_PROVIDER" "$SELECTED_MODEL" "${API_BASE_URL:-}" <<'PY'
import sys, re

config_path, provider, model, api_base_url = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""
with open(config_path, 'r') as f:
    content = f.read()

agent_names = ['qrystallizer', 'qonstrictor', 'instruqtor', 'construqtor', 'inspeqtor']
local_agents = {'qonstrictor', 'calqulator', 'qontextor', 'qompressor', 'qontrabender'}

for agent in agent_names:
    if agent in local_agents:
        continue
    content = re.sub(
        rf'(\n  {agent}:\n(?:    .*\n)*?    provider:\s*)\S+',
        rf'\1{provider}',
        content
    )
    if model:
        content = re.sub(
            rf'(\n  {agent}:\n(?:    .*\n)*?    model:\s*)\S+',
            rf'\1{model}',
            content
        )

if api_base_url:
    content = re.sub(
        r'(\n  (?:qrystallizer|instruqtor|construqtor|inspeqtor):\n(?:    .*\n)*?    api_base_url:\s*)\S+',
        lambda m: m.group(1) + api_base_url,
        content
    )

with open(config_path, 'w') as f:
    f.write(content)
PY
        say "  ✅ Agent configuration updated."
    else
        say "⚠️  python3 not found; skipping config.yaml auto-update."
    fi
fi

# ── .gitignore ───────────────────────────────────────────────────────────────

GITIGNORE="${TARGET}/.gitignore"
touch "$GITIGNORE"
if ! grep -qxF ".qonqrete/" "$GITIGNORE" 2>/dev/null; then
    printf '\n# QonQrete local runtime\n.qonqrete/\n' >> "$GITIGNORE"
    say "✅ Added .qonqrete/ to .gitignore"
fi

# ── Starter task ─────────────────────────────────────────────────────────────

TASK_FILE="${TARGET}/tasq.md"
if [ ! -e "$TASK_FILE" ]; then
    cat > "$TASK_FILE" <<'TASQEOF'
# Tasq

Describe what you want QonQrete to build, fix, review, or improve.

Keep it concrete. Include:
- the desired outcome
- important constraints
- files or areas to touch
- what "done" means
TASQEOF
    say "✅ Created starter tasq.md"
fi

# ── .env setup ───────────────────────────────────────────────────────────────

if [ -n "${API_KEY:-}" ]; then
    ENV_FILE="${TARGET}/.env"
    escaped="$(shell_single_quote_payload "$API_KEY")"
    ENV_LINE="export ${ENV_VAR}='${escaped}'"

    if [ "$ENV_VAR" = "GOOGLE_API_KEY" ]; then
        ENV_LINE="export GOOGLE_API_KEY='${escaped}'  # also read as GEMINI_API_KEY"
    fi

    touch "$ENV_FILE"
    if grep -q "^export ${ENV_VAR}=" "$ENV_FILE" 2>/dev/null; then
        TMP_ENV="${ENV_FILE}.tmp.$$"
        awk -v var="$ENV_VAR" -v line="$ENV_LINE" '
            index($0, "export " var "=") == 1 { if (!done) { print line; done=1 }; next }
            { print }
        ' "$ENV_FILE" > "$TMP_ENV"
        mv "$TMP_ENV" "$ENV_FILE"
        say "✅ Updated ${ENV_VAR} in .env"
    else
        printf '\n%s\n' "$ENV_LINE" >> "$ENV_FILE"
        say "✅ Added ${ENV_VAR} to .env"
    fi

    export "${ENV_VAR}=${API_KEY}"
    if [ "$ENV_VAR" = "GOOGLE_API_KEY" ]; then
        export GEMINI_API_KEY="${API_KEY}"
    fi
fi

# ── Init ─────────────────────────────────────────────────────────────────────

say ""
say "🚀 Running qonqrete.sh init..."
"$RUNTIME_DIR/qonqrete.sh" init 2>&1 || {
    say ""
    say "${YELLOW}⚠️  init encountered an issue. You may need to run it manually:${RESET}"
    say "     ./.qonqrete/qonqrete.sh init"
}

say ""
say "${BOLD}${GREEN}✅ QonQrete is ready!${RESET}"
say ""
say "   Provider: $(provider_label "$SELECTED_PROVIDER")"
say "   Model:    ${SELECTED_MODEL:-default}"
say "   Runtime:  ${RUNTIME_DIR}"
say ""
say "   Run with a task file:"
say "     cd ${TARGET}"
say "     ./.qonqrete/qonqrete.sh run -f tasq.md"
say ""
say "   Or run interactively (no task file needed):"
say "     ./.qonqrete/qonqrete.sh"
say "   Then paste your task and press Ctrl+D when done."
say ""
say "   Edit tasq.md first to describe what you want to build, then run:"
say "     ./.qonqrete/qonqrete.sh tasq.md"
say ""
if [ -z "${API_KEY:-}" ]; then
    say "   ${YELLOW}⚠️  Remember to set ${ENV_VAR} in your environment or .env file.${RESET}"
    say ""
fi
