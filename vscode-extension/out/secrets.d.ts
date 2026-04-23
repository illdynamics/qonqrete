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
import * as vscode from 'vscode';
/** Centralized provider → env var mapping (single source of truth) */
export declare const PROVIDER_ENV_MAP: Record<string, string>;
/** All supported env key names */
export declare const ALL_API_KEYS: readonly ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY", "VENICE_API_KEY", "MLX_API_KEY", "LLAMA_CPP_API_KEY"];
/** Provider metadata */
export declare const PROVIDERS: Record<string, {
    label: string;
    envKey: string;
    models: string[];
    optionalAuth?: boolean;
    notes?: string;
    uiSelectable?: boolean;
}>;
/**
 * Initialize the secrets manager. Call once during extension activation.
 */
export declare function initSecrets(context: vscode.ExtensionContext): void;
/**
 * Store an API key securely.
 */
export declare function storeSecret(envKey: string, value: string): Promise<void>;
/**
 * Retrieve a stored API key.
 */
export declare function getSecret(envKey: string): Promise<string | undefined>;
/**
 * Delete a stored API key.
 */
export declare function deleteSecret(envKey: string): Promise<void>;
/**
 * Check if an API key is available (env var OR stored secret).
 */
export declare function hasApiKey(envKey: string): Promise<boolean>;
/**
 * Resolve an API key value with correct precedence:
 * 1. Real env var (process.env)
 * 2. Stored secret
 * 3. undefined
 */
export declare function resolveApiKey(envKey: string): Promise<string | undefined>;
/**
 * Build a SAFE environment map for terminal/process injection.
 * Only includes keys that are stored but NOT already in process.env.
 * Returns a plain object suitable for TerminalOptions.env or spawn env.
 */
export declare function buildSecureEnvMap(): Promise<Record<string, string>>;
/**
 * Migrate API keys from old VS Code settings to secure storage.
 * Call once during activation.
 */
export declare function migrateFromSettings(): Promise<void>;
//# sourceMappingURL=secrets.d.ts.map