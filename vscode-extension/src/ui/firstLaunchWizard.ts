/**
 * First-Launch Provider Wizard
 * 3-step QuickPick flow: provider → model → API key
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import { PROVIDERS, PROVIDER_ENV_MAP, resolveApiKey } from '../secrets';

export interface SetupResult {
    provider: string;
    model: string;
    apiKey: string;
    envKey: string;
}

/**
 * Show the 3-step first-launch wizard.
 * Returns SetupResult or undefined if user cancels.
 */
export async function showFirstLaunchWizard(): Promise<SetupResult | undefined> {
    // ── Step 1: Choose provider ──────────────────────────────────────────
    const providerItems = Object.entries(PROVIDERS)
        .filter(([, p]) => p.uiSelectable !== false)
        .map(([id, p]) => ({
            label: p.label,
            description: id,
            detail: p.notes || `Requires ${p.envKey}`,
        }));

    const providerPick = await vscode.window.showQuickPick(providerItems, {
        title: 'QonQrete Setup (1/3) — Select your AI provider',
        placeHolder: 'Choose a provider...',
        matchOnDescription: true,
    });
    if (!providerPick) return undefined;

    const providerId = providerPick.description!;
    const providerInfo = PROVIDERS[providerId];
    if (!providerInfo) return undefined;

    // ── Step 2: Choose model ─────────────────────────────────────────────
    let model: string;

    if (providerInfo.models.length > 0) {
        const modelItems: vscode.QuickPickItem[] = providerInfo.models.map(m => ({ label: m }));
        modelItems.push({ label: '$(edit) Custom model name...', description: 'custom', detail: 'Enter a custom model name' });

        const modelPick = await vscode.window.showQuickPick(modelItems, {
            title: `QonQrete Setup (2/3) — Select a model for ${providerInfo.label}`,
            placeHolder: 'Choose a model...',
        });
        if (!modelPick) return undefined;

        if ((modelPick as any).description === 'custom') {
            const customModel = await vscode.window.showInputBox({
                title: `Enter custom model name for ${providerInfo.label}`,
                placeHolder: 'e.g. gpt-4.1',
            });
            if (!customModel) return undefined;
            model = customModel.trim();
        } else {
            model = modelPick.label;
        }
    } else {
        // Local providers: ask for model name (optional) or api_base_url
        const customModel = await vscode.window.showInputBox({
            title: `QonQrete Setup (2/3) — Model name for ${providerInfo.label}`,
            placeHolder: 'Model name (optional, leave empty for default)',
            prompt: 'Local runtime — model is optional. Set api_base_url in config.yaml.',
        });
        if (customModel === undefined) return undefined;
        model = customModel.trim();
    }

    // ── Step 3: API key ──────────────────────────────────────────────────
    const envKey = PROVIDER_ENV_MAP[providerId] || providerInfo.envKey;
    const existingKey = (await resolveApiKey(envKey)) || '';

    let apiKey: string;

    if (existingKey && existingKey.length > 0) {
        const masked = existingKey.length > 12
            ? `${existingKey.slice(0, 8)}...${existingKey.slice(-4)}`
            : '****';

        const useExisting = await vscode.window.showQuickPick(
            [
                {
                    label: '$(check) Yes',
                    description: `Use ${envKey}=${masked}`,
                },
                {
                    label: '$(edit) No, enter a new key',
                    description: 'Provide a different key',
                },
            ],
            {
                title: `QonQrete Setup (3/3) — Detected ${envKey}`,
                placeHolder: 'Use detected key?',
            }
        );
        if (!useExisting) return undefined;

        if (useExisting.label.includes('Yes')) {
            apiKey = existingKey;
        } else {
            const newKey = await vscode.window.showInputBox({
                title: `QonQrete Setup (3/3) — Enter ${envKey}`,
                password: true,
                placeHolder: 'Paste your API key...',
            });
            if (!newKey) return undefined;
            apiKey = newKey.trim();
        }
    } else {
        const newKey = await vscode.window.showInputBox({
            title: `QonQrete Setup (3/3) — Enter ${envKey} for ${providerInfo.label}`,
            password: true,
            placeHolder: 'Paste your API key...',
            prompt: `Required: ${envKey}`,
        });
        if (!newKey) return undefined;
        apiKey = newKey.trim();
    }

    if (!apiKey) return undefined;

    return { provider: providerId, model, apiKey, envKey };
}
