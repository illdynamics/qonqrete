#!/usr/bin/env bash
set -euo pipefail

# QonQrete Bootstrap — Deploy the runtime from a cloned repo into your project
# with interactive provider/model/API-key setup, then auto-init.
#
# Usage:
#   ./qonqrete-bootstrap.sh                  # deploy to current directory
#   ./qonqrete-bootstrap.sh /path/to/project  # deploy to specific project
#
# After cloning:
#   git clone https://github.com/illdynamics/qonqrete.git
#   cd qonqrete
#   ./qonqrete-bootstrap.sh /path/to/my-project
#   cd /path/to/my-project
#   ./.qonqrete/qonqrete.sh tasq.md

TARGET="${1:-.}"
TARGET="$(cd "$TARGET" 2>/dev/null && pwd || echo "")"
if [ -z "$TARGET" ]; then
    echo "❌ Target directory does not exist: $1" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${TARGET}/.qonqrete"

say() { printf '%s\n' "$*"; }
prompt() { printf '%s ' "$*"; read -r REPLY; printf '%s\n' "$REPLY"; }

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

# ── Provider catalog ─────────────────────────────────────────────────────────
# Each provider has: label, env var(s), models[], notes
declare -A PROVIDER_LABEL PROVIDER_ENV PROVIDER_MODELS PROVIDER_NOTES

PROVIDERS_ORDERED=(
    "openai" "codex" "google" "gemini-cli" "anthropic" "claude-code"
    "deepseek" "codeseeq" "venice" "qwen" "openrouter"
    "mlx" "llama-cpp"
)

PROVIDER_LABEL[openai]="OpenAI (API)"
PROVIDER_ENV[openai]="OPENAI_API_KEY"
PROVIDER_MODELS[openai]="gpt-4.1 gpt-4.1-mini gpt-4.1-nano gpt-4o gpt-4o-mini o3-mini o4-mini"
PROVIDER_NOTES[openai]=""

PROVIDER_LABEL[codex]="OpenAI Codex (CLI)"
PROVIDER_ENV[codex]="OPENAI_API_KEY"
PROVIDER_MODELS[codex]="gpt-5-codex gpt-5.5-codex-mini"
PROVIDER_NOTES[codex]="Requires the official Codex CLI installed on your system."

PROVIDER_LABEL[google]="Google Gemini (API)"
PROVIDER_ENV[google]="GOOGLE_API_KEY"
PROVIDER_MODELS[google]="gemini-2.5-pro gemini-2.5-flash gemini-2.0-flash gemini-2.0-flash-lite"
PROVIDER_NOTES[google]="GOOGLE_API_KEY or GEMINI_API_KEY accepted."

PROVIDER_LABEL[gemini-cli]="Gemini CLI"
PROVIDER_ENV[gemini-cli]="GOOGLE_API_KEY"
PROVIDER_MODELS[gemini-cli]="gemini-2.5-pro gemini-2.5-flash"
PROVIDER_NOTES[gemini-cli]="Requires the Gemini CLI installed on your system."

PROVIDER_LABEL[anthropic]="Anthropic (API)"
PROVIDER_ENV[anthropic]="ANTHROPIC_API_KEY"
PROVIDER_MODELS[anthropic]="claude-sonnet-4-20250514 claude-haiku-4-5-20251001 claude-opus-4-20250514"
PROVIDER_NOTES[anthropic]=""

PROVIDER_LABEL[claude-code]="Claude Code (CLI)"
PROVIDER_ENV[claude-code]="ANTHROPIC_API_KEY"
PROVIDER_MODELS[claude-code]="claude-sonnet-4-20250514 claude-opus-4-20250514"
PROVIDER_NOTES[claude-code]="Requires the Claude Code CLI installed on your system."

PROVIDER_LABEL[deepseek]="DeepSeek (API)"
PROVIDER_ENV[deepseek]="DEEPSEEK_API_KEY"
PROVIDER_MODELS[deepseek]="deepseek-chat deepseek-reasoner"
PROVIDER_NOTES[deepseek]="Default provider. DEEPSEEK_API_KEY required."

PROVIDER_LABEL[codeseeq]="CodeSeeq (Codex CLI on DeepSeek)"
PROVIDER_ENV[codeseeq]="DEEPSEEK_API_KEY"
PROVIDER_MODELS[codeseeq]="deepseek-v4-flash deepseek-v4-flash-thinking deepseek-v4-pro deepseek-v4-pro-thinking"
PROVIDER_NOTES[codeseeq]="Uses CodeSeeq CLI wrapper. Requires DEEPSEEK_API_KEY + CodeSeeq installed."

PROVIDER_LABEL[venice]="Venice (API)"
PROVIDER_ENV[venice]="VENICE_API_KEY"
PROVIDER_MODELS[venice]="deepseek-v3.2 qwen3-coder-480b-a35b-instruct-turbo venice-uncensored llama-3.3-70b"
PROVIDER_NOTES[venice]="VENICE_API_KEY required. Many models available — see Venice docs for full list."

PROVIDER_LABEL[qwen]="Qwen (API)"
PROVIDER_ENV[qwen]="QWEN_API_KEY"
PROVIDER_MODELS[qwen]="qwen-plus qwen-turbo qwen-max"
PROVIDER_NOTES[qwen]=""

PROVIDER_LABEL[openrouter]="OpenRouter (API)"
PROVIDER_ENV[openrouter]="OPENROUTER_API_KEY"
PROVIDER_MODELS[openrouter]="anthropic/claude-sonnet-4 openai/gpt-4.1 google/gemini-2.5-pro deepseek/deepseek-chat-v3"
PROVIDER_LABEL[mlx]="MLX (local/LAN)"
PROVIDER_ENV[mlx]="MLX_API_KEY"
PROVIDER_MODELS[mlx]=""
PROVIDER_NOTES[mlx]="Local MLX (Apple Silicon) runtime. Model name optional. api_base_url required in config."

PROVIDER_LABEL[llama-cpp]="Llama-cpp (local/LAN)"
PROVIDER_ENV[llama-cpp]="LLAMA_CPP_API_KEY"
PROVIDER_MODELS[llama-cpp]=""
PROVIDER_NOTES[llama-cpp]="Local llama.cpp runtime. Model name optional. api_base_url required in config."

PROVIDER_NOTES[openrouter]="Multi-provider gateway. OPENROUTER_API_KEY required."

# ── Validation ───────────────────────────────────────────────────────────────

if [ ! -f "${SCRIPT_DIR}/qonqrete.sh" ] && [ ! -f "${SCRIPT_DIR}/.qonqrete/qonqrete.sh" ]; then
    echo "❌ Could not find qonqrete.sh. Make sure you're running this from the cloned QonQrete repo." >&2
    exit 1
fi

# Determine the runtime source
if [ -f "${SCRIPT_DIR}/.qonqrete/qonqrete.sh" ]; then
    RUNTIME_SRC="${SCRIPT_DIR}/.qonqrete"
elif [ -f "${SCRIPT_DIR}/qonqrete.sh" ]; then
    RUNTIME_SRC="${SCRIPT_DIR}"
else
    echo "❌ Cannot determine runtime source directory." >&2
    exit 1
fi

# ── Welcome ──────────────────────────────────────────────────────────────────

say ""
say "${BOLD}${CYAN}🧱  QonQrete Bootstrap${RESET}"
say ""
say "   Target:  ${TARGET}"
say "   Runtime: ${RUNTIME_SRC}"
say ""

# ── Step 1: Choose provider ─────────────────────────────────────────────────

say "${BOLD}Step 1: Select your AI provider${RESET}"
say ""
say "  This provider will be used for all four primary agents"
say "  (Qrystallizer, InstruQtor, ConstruQtor, InspeQtor)."
say ""

i=1
declare -A PROVIDER_NUM
for pid in "${PROVIDERS_ORDERED[@]}"; do
    note=""
    [ -n "${PROVIDER_NOTES[$pid]}" ] && note=" — ${PROVIDER_NOTES[$pid]}"
    printf "  ${GREEN}%2d${RESET}) %s${note}\n" "$i" "${PROVIDER_LABEL[$pid]}"
    PROVIDER_NUM[$i]="$pid"
    ((i++))
done

say ""
SELECTED_PROVIDER=""
while [ -z "$SELECTED_PROVIDER" ]; do
    REPLY="$(prompt "  Choice [3 = DeepSeek (default)]:")"
    REPLY="${REPLY:-3}"
    if [[ "$REPLY" =~ ^[0-9]+$ ]] && [ -n "${PROVIDER_NUM[$REPLY]:-}" ]; then
        SELECTED_PROVIDER="${PROVIDER_NUM[$REPLY]}"
    else
        # Also accept provider name directly
        for pid in "${PROVIDERS_ORDERED[@]}"; do
            if [ "${pid}" = "$REPLY" ]; then
                SELECTED_PROVIDER="$pid"
                break
            fi
        done
        if [ -z "$SELECTED_PROVIDER" ]; then
            say "  ${RED}Invalid choice. Enter a number or provider name.${RESET}"
        fi
    fi
done

say ""
say "  ✅ Selected: ${GREEN}${PROVIDER_LABEL[$SELECTED_PROVIDER]}${RESET}"
say ""

# ── Step 2: Choose model ────────────────────────────────────────────────────

say "${BOLD}Step 2: Select a model${RESET}"
say ""

MODEL_LIST="${PROVIDER_MODELS[$SELECTED_PROVIDER]}"
if [ -n "$MODEL_LIST" ]; then
    say "  Available models for ${PROVIDER_LABEL[$SELECTED_PROVIDER]}:"
    say ""
    i=1
    declare -A MODEL_NUM
    MODELS_ARRAY=()
    for m in $MODEL_LIST; do
        printf "  ${GREEN}%2d${RESET}) %s\n" "$i" "$m"
        MODEL_NUM[$i]="$m"
        MODELS_ARRAY+=("$m")
        ((i++))
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
    # Local providers: mlx, llama-cpp — need api_base_url
    if [ "$SELECTED_PROVIDER" = "mlx" ] || [ "$SELECTED_PROVIDER" = "llama-cpp" ]; then
        say "  ${PROVIDER_LABEL[$SELECTED_PROVIDER]} needs an api_base_url."
        say "  (This is your local OpenAI-compatible HTTP server URL)"
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

# ── Step 3: API key ─────────────────────────────────────────────────────────

say "${BOLD}Step 3: API key${RESET}"
say ""

ENV_VAR="${PROVIDER_ENV[$SELECTED_PROVIDER]}"
DETECTED_KEY=""

# Auto-detect from environment
if [ -n "${!ENV_VAR:-}" ]; then
    DETECTED_KEY="${!ENV_VAR}"
    KEY_PREVIEW="${DETECTED_KEY:0:8}...${DETECTED_KEY: -4}"
    say "  🔍 Detected ${ENV_VAR}=${KEY_PREVIEW} in your environment."
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

# Also handle GOOGLE_API_KEY / GEMINI_API_KEY equivalence
if [ "$ENV_VAR" = "GOOGLE_API_KEY" ]; then
    # Check if GEMINI_API_KEY is also set
    if [ -z "$API_KEY" ] && [ -n "${GEMINI_API_KEY:-}" ]; then
        DETECTED_KEY="${GEMINI_API_KEY}"
        KEY_PREVIEW="${DETECTED_KEY:0:8}...${DETECTED_KEY: -4}"
        say "  🔍 Detected GEMINI_API_KEY=${KEY_PREVIEW} in your environment."
        REPLY="$(prompt "  Use this key? [Y/n]:")"
        REPLY="${REPLY:-y}"
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            API_KEY="$DETECTED_KEY"
        else
            API_KEY="$(prompt "  Enter GOOGLE_API_KEY:")"
        fi
    fi
fi

if [ -z "$API_KEY" ]; then
    say "  ${YELLOW}⚠️  No API key provided. You can set ${ENV_VAR} later.${RESET}"
fi

say ""

# ── Deploy runtime ───────────────────────────────────────────────────────────

if [ -d "$RUNTIME_DIR" ]; then
    BACKUP="${RUNTIME_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
    say "♻️  ${RUNTIME_DIR} already exists. Moving to ${BACKUP}"
    mv "$RUNTIME_DIR" "$BACKUP"
fi

say "📦 Deploying QonQrete to ${RUNTIME_DIR}..."
mkdir -p "$RUNTIME_DIR"

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

chmod +x "$RUNTIME_DIR/qonqrete.sh"

# ── Configure the four agents ────────────────────────────────────────────────

CONFIG_FILE="${RUNTIME_DIR}/worqspace/config.yaml"

if [ -f "$CONFIG_FILE" ]; then
    say "⚙️  Configuring all agents to use ${PROVIDER_LABEL[$SELECTED_PROVIDER]} / ${SELECTED_MODEL:-default}..."
    export API_BASE_URL="${API_BASE_URL:-}"

    # Map bootstrap provider names to config provider names
    CONFIG_PROVIDER="$SELECTED_PROVIDER"
    case "$SELECTED_PROVIDER" in
        google)      CONFIG_PROVIDER="gemini" ;;   # config uses 'gemini' not 'google'
        gemini-cli)  CONFIG_PROVIDER="gemini" ;;
        codex)       CONFIG_PROVIDER="openai" ;;    # codex cli runs via openai env
        claude-code) CONFIG_PROVIDER="anthropic" ;;
    esac

    # Use python3 to safely update the YAML config
    python3 - "$CONFIG_FILE" "$CONFIG_PROVIDER" "$SELECTED_MODEL" "${API_BASE_URL:-}" <<'PY'
import sys, re

config_path, provider, model, api_base_url = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""
with open(config_path, 'r') as f:
    content = f.read()

agent_names = ['qrystallizer', 'qonstrictor', 'instruqtor', 'construqtor', 'inspeqtor']
local_agents = {'qonstrictor', 'calqulator', 'qontextor', 'qompressor', 'qontrabender'}

# Update each non-local agent
for agent in agent_names:
    if agent in local_agents:
        continue
    # Replace provider line under this agent
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

with open(config_path, 'w') as f:
    f.write(content)
PY
    say "  ✅ Agent configuration updated."
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

if [ -n "$API_KEY" ]; then
    ENV_FILE="${TARGET}/.env"
    ENV_LINE="export ${ENV_VAR}='${API_KEY}'"

    # Also handle GOOGLE/GEMINI equivalence
    if [ "$ENV_VAR" = "GOOGLE_API_KEY" ]; then
        ENV_LINE="export GOOGLE_API_KEY='${API_KEY}'  # also read as GEMINI_API_KEY"
    fi

    if [ -f "$ENV_FILE" ] && grep -q "^export ${ENV_VAR}=" "$ENV_FILE" 2>/dev/null; then
        # Replace existing key
        if [ "$(uname)" = "Darwin" ]; then
            sed -i '' "s|^export ${ENV_VAR}=.*|${ENV_LINE}|" "$ENV_FILE"
        else
            sed -i "s|^export ${ENV_VAR}=.*|${ENV_LINE}|" "$ENV_FILE"
        fi
        say "✅ Updated ${ENV_VAR} in .env"
    else
        printf '\n%s\n' "$ENV_LINE" >> "$ENV_FILE"
        say "✅ Added ${ENV_VAR} to .env"
    fi
    # Source it for the init step
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

# ── Done ─────────────────────────────────────────────────────────────────────

say ""
say "${BOLD}${GREEN}✅ QonQrete is ready!${RESET}"
say ""
say "   Provider: ${PROVIDER_LABEL[$SELECTED_PROVIDER]}"
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
if [ -z "$API_KEY" ]; then
    say "   ${YELLOW}⚠️  Remember to set ${ENV_VAR} in your environment or .env file.${RESET}"
    say ""
fi
