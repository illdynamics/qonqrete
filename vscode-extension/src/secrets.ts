/**
 * QonQrete v2 secrets manager.
 *
 * The v2 engine uses the configured provider's API key from the environment
 * (DEEPSEEK_API_KEY for CodeSeeq/DeepSeek, OPENAI_API_KEY for OpenAI/Codex,
 * GOOGLE_API_KEY for Gemini, ANTHROPIC_API_KEY for Claude). We keep those keys
 * in VS Code's OS keychain and inject them into the terminal environment only —
 * never into command text or logs.
 */
import * as vscode from 'vscode';

export const PROVIDER_ENV_MAP: Record<string, string> = {
    codeseeq: 'DEEPSEEK_API_KEY',
    deepseek: 'DEEPSEEK_API_KEY',
    openai: 'OPENAI_API_KEY',
    codex: 'OPENAI_API_KEY',
    anthropic: 'ANTHROPIC_API_KEY',
    'claude-code': 'ANTHROPIC_API_KEY',
    google: 'GOOGLE_API_KEY',
    gemini: 'GOOGLE_API_KEY',
    'gemini-cli': 'GOOGLE_API_KEY',
    openrouter: 'OPENROUTER_API_KEY',
    qwen: 'QWEN_API_KEY',
};

let secrets: vscode.SecretStorage | undefined;

export function initSecrets(context: vscode.ExtensionContext): void {
    secrets = context.secrets;
}

function getSecrets(): vscode.SecretStorage {
    if (!secrets) { throw new Error('Secrets not initialized.'); }
    return secrets;
}

export async function storeSecret(envKey: string, value: string): Promise<void> {
    await getSecrets().store(`qonqrete.${envKey}`, value);
}

export async function getSecret(envKey: string): Promise<string | undefined> {
    return getSecrets().get(`qonqrete.${envKey}`);
}

export async function deleteSecret(envKey: string): Promise<void> {
    await getSecrets().delete(`qonqrete.${envKey}`);
}

/** Build an env map with any stored keys not already present in process.env. */
export async function buildSecureEnvMap(): Promise<Record<string, string>> {
    const env: Record<string, string> = {};
    for (const envKey of Object.values(PROVIDER_ENV_MAP)) {
        if (process.env[envKey]) { continue; }
        const stored = await getSecret(envKey);
        if (stored) { env[envKey] = stored; }
    }
    return env;
}

export async function promptForApiKey(provider: string): Promise<void> {
    const envKey = PROVIDER_ENV_MAP[provider];
    if (!envKey) { return; }
    const existing = process.env[envKey] || await getSecret(envKey);
    const value = await vscode.window.showInputBox({
        title: `QonQrete ${provider} API key`,
        prompt: `Enter ${envKey} (stored securely in the OS keychain)`,
        password: true,
        placeHolder: existing ? '(already set — leave blank to keep)' : 'sk-...',
        ignoreFocusOut: true,
    });
    if (value !== undefined && value.trim()) {
        await storeSecret(envKey, value.trim());
        vscode.window.showInformationMessage(`${envKey} saved securely.`);
    }
}
