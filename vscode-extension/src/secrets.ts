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
 * @version 1.2.0
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';

/** Centralized provider → env var mapping (single source of truth) */
export const PROVIDER_ENV_MAP: Record<string, string> = {
    openai: 'OPENAI_API_KEY',
    anthropic: 'ANTHROPIC_API_KEY',
    openrouter: 'OPENROUTER_API_KEY',
    google: 'GOOGLE_API_KEY',
    gemini: 'GOOGLE_API_KEY',
    deepseek: 'DEEPSEEK_API_KEY',
    qwen: 'QWEN_API_KEY',
};

/** All supported env key names */
export const ALL_API_KEYS = [
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'OPENROUTER_API_KEY',
    'GOOGLE_API_KEY',
    'DEEPSEEK_API_KEY',
    'QWEN_API_KEY',
] as const;

/** Provider metadata */
export const PROVIDERS: Record<string, { label: string; envKey: string; models: string[] }> = {
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
};

let _secrets: vscode.SecretStorage | undefined;

/**
 * Initialize the secrets manager. Call once during extension activation.
 */
export function initSecrets(context: vscode.ExtensionContext): void {
    _secrets = context.secrets;
}

function getSecrets(): vscode.SecretStorage {
    if (!_secrets) throw new Error('Secrets not initialized. Call initSecrets() first.');
    return _secrets;
}

/**
 * Store an API key securely.
 */
export async function storeSecret(envKey: string, value: string): Promise<void> {
    await getSecrets().store(`qonqrete.${envKey}`, value);
}

/**
 * Retrieve a stored API key.
 */
export async function getSecret(envKey: string): Promise<string | undefined> {
    return await getSecrets().get(`qonqrete.${envKey}`);
}

/**
 * Delete a stored API key.
 */
export async function deleteSecret(envKey: string): Promise<void> {
    await getSecrets().delete(`qonqrete.${envKey}`);
}

/**
 * Check if an API key is available (env var OR stored secret).
 */
export async function hasApiKey(envKey: string): Promise<boolean> {
    // Env var takes priority
    if (process.env[envKey]) return true;
    // Gemini/Google equivalence
    if (envKey === 'GOOGLE_API_KEY' && process.env['GEMINI_API_KEY']) return true;
    if (envKey === 'GEMINI_API_KEY' && process.env['GOOGLE_API_KEY']) return true;
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
export async function resolveApiKey(envKey: string): Promise<string | undefined> {
    // 1. Real env var
    if (process.env[envKey]) return process.env[envKey];
    // Gemini/Google equivalence
    if (envKey === 'GOOGLE_API_KEY' && process.env['GEMINI_API_KEY']) return process.env['GEMINI_API_KEY'];
    // 2. Stored secret
    return await getSecret(envKey);
}

/**
 * Build a SAFE environment map for terminal/process injection.
 * Only includes keys that are stored but NOT already in process.env.
 * Returns a plain object suitable for TerminalOptions.env or spawn env.
 */
export async function buildSecureEnvMap(): Promise<Record<string, string>> {
    const env: Record<string, string> = {};

    // IDE-driven runs are always non-interactive
    env['QONQ_NON_INTERACTIVE'] = '1';

    for (const envKey of ALL_API_KEYS) {
        // Skip if already in real environment
        if (process.env[envKey]) continue;
        // Gemini equivalence
        if (envKey === 'GOOGLE_API_KEY' && process.env['GEMINI_API_KEY']) continue;

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
export async function migrateFromSettings(): Promise<void> {
    const config = vscode.workspace.getConfiguration('qonqrete');
    const oldKeyMap: Record<string, string> = {
        apiKeyOpenai: 'OPENAI_API_KEY',
        apiKeyGemini: 'GOOGLE_API_KEY',
        apiKeyAnthropic: 'ANTHROPIC_API_KEY',
        apiKeyDeepseek: 'DEEPSEEK_API_KEY',
        apiKeyQwen: 'QWEN_API_KEY',
    };

    let migrated = 0;
    for (const [settingKey, envKey] of Object.entries(oldKeyMap)) {
        const val = config.get<string>(settingKey, '');
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
