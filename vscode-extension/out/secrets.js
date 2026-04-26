"use strict";
/**
 * QonQrete Secrets Manager
 * Secure API key storage using VS Code SecretStorage API
 *
 * SECURITY:
 * - Keys stored in OS keychain via ExtensionContext.secrets
 * - Never in settings.json, never in terminal commands, never in logs
 * - Env vars take precedence over stored secrets
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.PROVIDERS = exports.ALL_API_KEYS = exports.PROVIDER_ENV_MAP = void 0;
exports.initSecrets = initSecrets;
exports.storeSecret = storeSecret;
exports.getSecret = getSecret;
exports.deleteSecret = deleteSecret;
exports.hasApiKey = hasApiKey;
exports.resolveApiKey = resolveApiKey;
exports.buildSecureEnvMap = buildSecureEnvMap;
exports.migrateFromSettings = migrateFromSettings;
const vscode = __importStar(require("vscode"));
/** Centralized provider → env var mapping (single source of truth) */
exports.PROVIDER_ENV_MAP = {
    openai: 'OPENAI_API_KEY',
    anthropic: 'ANTHROPIC_API_KEY',
    openrouter: 'OPENROUTER_API_KEY',
    google: 'GOOGLE_API_KEY',
    gemini: 'GOOGLE_API_KEY',
    deepseek: 'DEEPSEEK_API_KEY',
    qwen: 'QWEN_API_KEY',
    // v1.3.12: Venice requires its own dedicated key; no fallback.
    venice: 'VENICE_API_KEY',
    // v1.3.12: mlx and llama-cpp have optional API keys. They are NOT treated
    // as required by the IDE layer.
    mlx: 'MLX_API_KEY',
    'llama-cpp': 'LLAMA_CPP_API_KEY',
};
/** All supported env key names */
exports.ALL_API_KEYS = [
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'OPENROUTER_API_KEY',
    'GOOGLE_API_KEY',
    'DEEPSEEK_API_KEY',
    'QWEN_API_KEY',
    // v1.3.12
    'VENICE_API_KEY',
    'MLX_API_KEY',
    'LLAMA_CPP_API_KEY',
];
/** Provider metadata */
exports.PROVIDERS = {
    openai: {
        label: 'OpenAI',
        envKey: 'OPENAI_API_KEY',
        models: ['gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano', 'gpt-4o', 'gpt-4o-mini', 'o3-mini', 'o4-mini'],
    },
    gemini: {
        label: 'Google Gemini',
        envKey: 'GOOGLE_API_KEY',
        models: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite'],
    },
    anthropic: {
        label: 'Anthropic',
        envKey: 'ANTHROPIC_API_KEY',
        models: ['claude-sonnet-4-20250514', 'claude-haiku-4-5-20251001', 'claude-opus-4-20250514'],
    },
    deepseek: {
        label: 'DeepSeek',
        envKey: 'DEEPSEEK_API_KEY',
        models: ['deepseek-chat', 'deepseek-reasoner'],
    },
    qwen: {
        label: 'Qwen',
        envKey: 'QWEN_API_KEY',
        models: ['qwen-plus', 'qwen-turbo', 'qwen-max'],
    },
    openrouter: {
        label: 'OpenRouter',
        envKey: 'OPENROUTER_API_KEY',
        models: ['anthropic/claude-sonnet-4', 'openai/gpt-4.1', 'google/gemini-2.5-pro', 'deepseek/deepseek-chat-v3'],
    },
    // v1.3.12: Venice API (OpenAI-compatible). VENICE_API_KEY required.
    venice: {
        label: 'Venice',
        envKey: 'VENICE_API_KEY',
        models: [
            'deepseek-v3.2',
            'venice-uncensored',
            'qwen3-coder-480b-a35b-instruct-turbo',
            'qwen3-235b',
            'qwen3-235b-a22b-instruct',
            'qwen3-235b-a22b-thinking',
            'qwen3-next-80b',
            'qwen3-4b',
            'qwen-2.5-qwq-32b',
            'qwen-2.5-coder-32b',
            'qwen-2.5-vl',
            'mistral-31-24b',
            'mistral-small-3.2-24b-instruct',
            'llama-3.3-70b',
            'llama-3.2-3b',
            'llama-3.1-405b',
            'dolphin-2.9.2-qwen2-72b',
            'deepseek-r1-671b',
            'deepseek-r1-llama-70b',
            'deepseek-coder-v2-lite',
            'claude-opus-4.6',
            'claude-sonnet-4.6',
            'glm-5',
            'glm-4.7-flash-heretic',
            'minimax-2.5',
        ],
        notes: 'VENICE_API_KEY required. Model list is a snapshot — Venice may add more; use the Custom model option for any valid Venice model ID.',
    },
    // v1.3.12: MLX provider for local/LAN OpenAI-compatible runtimes.
    // API key is OPTIONAL; api_base_url must be set in the per-agent config.
    mlx: {
        label: 'MLX (local/LAN)',
        envKey: 'MLX_API_KEY',
        models: [],
        optionalAuth: true,
        notes: 'Local MLX runtime. Set api_base_url per-agent in config.yaml. MLX_API_KEY is optional.',
        uiSelectable: false,
    },
    // v1.3.12: Llama-cpp provider for local/LAN OpenAI-compatible runtimes.
    // API key is OPTIONAL; api_base_url must be set in the per-agent config.
    'llama-cpp': {
        label: 'Llama-cpp (local/LAN)',
        envKey: 'LLAMA_CPP_API_KEY',
        models: [],
        optionalAuth: true,
        notes: 'Local llama.cpp runtime. Set api_base_url per-agent in config.yaml. LLAMA_CPP_API_KEY is optional.',
        uiSelectable: false,
    },
};
let _secrets;
/**
 * Initialize the secrets manager. Call once during extension activation.
 */
function initSecrets(context) {
    _secrets = context.secrets;
}
function getSecrets() {
    if (!_secrets)
        throw new Error('Secrets not initialized. Call initSecrets() first.');
    return _secrets;
}
/**
 * Store an API key securely.
 */
async function storeSecret(envKey, value) {
    await getSecrets().store(`qonqrete.${envKey}`, value);
}
/**
 * Retrieve a stored API key.
 */
async function getSecret(envKey) {
    return await getSecrets().get(`qonqrete.${envKey}`);
}
/**
 * Delete a stored API key.
 */
async function deleteSecret(envKey) {
    await getSecrets().delete(`qonqrete.${envKey}`);
}
/**
 * Check if an API key is available (env var OR stored secret).
 */
async function hasApiKey(envKey) {
    // Env var takes priority
    if (process.env[envKey])
        return true;
    // Gemini/Google equivalence
    if (envKey === 'GOOGLE_API_KEY' && process.env['GEMINI_API_KEY'])
        return true;
    if (envKey === 'GEMINI_API_KEY' && process.env['GOOGLE_API_KEY'])
        return true;
    // Check secret store
    const stored = await getSecret(envKey);
    return !!stored;
}
/**
 * Resolve an API key value with correct precedence:
 * 1. Real env var (process.env)
 * 2. Stored secret
 * 3. undefined
 */
async function resolveApiKey(envKey) {
    // 1. Real env var
    if (process.env[envKey])
        return process.env[envKey];
    // Gemini/Google equivalence
    if (envKey === 'GOOGLE_API_KEY' && process.env['GEMINI_API_KEY'])
        return process.env['GEMINI_API_KEY'];
    // 2. Stored secret
    return await getSecret(envKey);
}
/**
 * Build a SAFE environment map for terminal/process injection.
 * Only includes keys that are stored but NOT already in process.env.
 * Returns a plain object suitable for TerminalOptions.env or spawn env.
 */
async function buildSecureEnvMap() {
    const env = {};
    // IDE-driven runs are always non-interactive
    env['QONQ_NON_INTERACTIVE'] = '1';
    for (const envKey of exports.ALL_API_KEYS) {
        // Skip if already in real environment
        if (process.env[envKey])
            continue;
        // Gemini equivalence
        if (envKey === 'GOOGLE_API_KEY' && process.env['GEMINI_API_KEY'])
            continue;
        const stored = await getSecret(envKey);
        if (stored) {
            env[envKey] = stored;
            // Double-map Google → Gemini
            if (envKey === 'GOOGLE_API_KEY') {
                env['GEMINI_API_KEY'] = stored;
            }
        }
    }
    return env;
}
/**
 * Migrate API keys from old VS Code settings to secure storage.
 * Call once during activation.
 */
async function migrateFromSettings() {
    const config = vscode.workspace.getConfiguration('qonqrete');
    const oldKeyMap = {
        apiKeyOpenai: 'OPENAI_API_KEY',
        apiKeyGemini: 'GOOGLE_API_KEY',
        apiKeyAnthropic: 'ANTHROPIC_API_KEY',
        apiKeyDeepseek: 'DEEPSEEK_API_KEY',
        apiKeyQwen: 'QWEN_API_KEY',
    };
    let migrated = 0;
    for (const [settingKey, envKey] of Object.entries(oldKeyMap)) {
        const val = config.get(settingKey, '');
        if (val) {
            await storeSecret(envKey, val);
            // Remove from settings
            await config.update(settingKey, undefined, vscode.ConfigurationTarget.Global);
            migrated++;
        }
    }
    if (migrated > 0) {
        console.log(`[QonQrete] Migrated ${migrated} API key(s) from settings to secure storage`);
    }
}
//# sourceMappingURL=secrets.js.map