/**
 * QonQrete AI Configuration Command
 * Set providers, models, and API keys for AI agents
 *
 * SECURITY: API keys stored via ExtensionContext.secrets (OS keychain)
 * Never in settings.json, never in terminal commands, never in logs
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { getRunner } from '../cli/qonqreteRunner';
import {
    PROVIDERS,
    PROVIDER_ENV_MAP,
    ALL_API_KEYS,
    storeSecret,
    getSecret,
    hasApiKey,
} from '../secrets';

const AI_AGENTS = ['tasqleveler', 'instruqtor', 'construqtor', 'inspeqtor'] as const;
type AgentName = typeof AI_AGENTS[number];

interface AgentConfig { provider: string; model: string; }

function readAgentConfigs(configPath: string): Record<AgentName, AgentConfig> {
    const defaults: Record<AgentName, AgentConfig> = {
        tasqleveler: { provider: 'openai', model: 'gpt-4o-mini' },
        instruqtor: { provider: 'openai', model: 'gpt-4o-mini' },
        construqtor: { provider: 'openai', model: 'gpt-4o-mini' },
        inspeqtor: { provider: 'openai', model: 'gpt-4o-mini' },
    };
    if (!fs.existsSync(configPath)) return defaults;
    try {
        const lines = fs.readFileSync(configPath, 'utf8').split('\n');
        let currentAgent: string | null = null;
        for (const line of lines) {
            const agentMatch = line.match(/^\s{2}(\w+):\s*$/);
            if (agentMatch && AI_AGENTS.includes(agentMatch[1] as AgentName)) {
                currentAgent = agentMatch[1]; continue;
            }
            if (currentAgent && AI_AGENTS.includes(currentAgent as AgentName)) {
                const pm = line.match(/^\s{4}provider:\s*(\S+)/);
                if (pm) { defaults[currentAgent as AgentName].provider = pm[1]; continue; }
                const mm = line.match(/^\s{4}model:\s*(\S+)/);
                if (mm) { defaults[currentAgent as AgentName].model = mm[1]; continue; }
                if (line.match(/^\s{0,2}\S/)) currentAgent = null;
            }
        }
        return defaults;
    } catch { return defaults; }
}

function writeAgentConfig(configPath: string, agent: AgentName, provider: string, model: string): boolean {
    if (!fs.existsSync(configPath)) return false;
    try {
        const lines = fs.readFileSync(configPath, 'utf8').split('\n');
        const result: string[] = [];
        let inAgent = false; let providerSet = false; let modelSet = false;
        for (const line of lines) {
            if (line.match(new RegExp(`^\\s{2}${agent}:\\s*$`))) {
                inAgent = true; providerSet = false; modelSet = false; result.push(line); continue;
            }
            if (inAgent) {
                if (line.match(/^\s{4}provider:\s*\S+/) && !providerSet) {
                    result.push(`    provider: ${provider}`); providerSet = true; continue;
                }
                if (line.match(/^\s{4}model:\s*\S+/) && !modelSet) {
                    result.push(`    model: ${model}`); modelSet = true; continue;
                }
                if (line.match(/^\s{0,2}\S/)) inAgent = false;
            }
            result.push(line);
        }
        fs.writeFileSync(configPath, result.join('\n'), 'utf8');
        return true;
    } catch { return false; }
}

/**
 * Get env keys required by configured providers
 */
export function getRequiredApiKeys(configPath: string): string[] {
    const configs = readAgentConfigs(configPath);
    const provs = new Set<string>();
    for (const agent of AI_AGENTS) {
        const p = configs[agent].provider;
        if (p && p !== 'local') provs.add(p);
    }
    const keys: string[] = [];
    for (const p of provs) {
        const envKey = PROVIDER_ENV_MAP[p];
        if (envKey && !keys.includes(envKey)) keys.push(envKey);
    }
    return keys;
}

/**
 * Check which API keys are missing. Respects env > secrets precedence.
 */
export async function getMissingApiKeys(configPath: string): Promise<string[]> {
    const required = getRequiredApiKeys(configPath);
    const missing: string[] = [];
    for (const envKey of required) {
        if (!await hasApiKey(envKey)) missing.push(envKey);
    }
    return missing;
}

/**
 * Prompt user for missing API keys (secure storage)
 */
export async function promptForMissingApiKeys(configPath: string): Promise<boolean> {
    const missing = await getMissingApiKeys(configPath);
    if (missing.length === 0) return true;

    const names = missing.map(k => {
        for (const [, info] of Object.entries(PROVIDERS)) {
            if (info.envKey === k) return info.label;
        }
        return k;
    });

    const result = await vscode.window.showWarningMessage(
        `API keys needed for: ${names.join(', ')}.\nSet them now?`,
        'Set API Keys', 'Skip (use env vars)'
    );

    if (result === 'Set API Keys') {
        for (const envKey of missing) {
            const label = Object.values(PROVIDERS).find(p => p.envKey === envKey)?.label || envKey;
            const key = await vscode.window.showInputBox({
                title: `${label} API Key`,
                prompt: `Enter your ${label} API key (${envKey})`,
                password: true,
                placeHolder: 'sk-...',
            });
            if (key) await storeSecret(envKey, key);
        }
        return true;
    }
    return result === 'Skip (use env vars)';
}

/**
 * Execute the Set AI Configuration command
 */
export async function executeSetAIConfig(): Promise<void> {
    const runner = getRunner();
    const workingDir = await runner.getQonQreteWorkingDir();
    if (!workingDir) {
        vscode.window.showWarningMessage('QonQrete runtime not found. Deploy first.');
        return;
    }
    const configPath = path.join(workingDir, 'worqspace', 'config.yaml');
    if (!fs.existsSync(configPath)) {
        vscode.window.showErrorMessage('config.yaml not found in runtime.');
        return;
    }

    const currentConfigs = readAgentConfigs(configPath);
    const providerNames = Object.keys(PROVIDERS);

    let done = false;
    while (!done) {
        const items: vscode.QuickPickItem[] = [
            { label: '$(symbol-misc) AI Agents', kind: vscode.QuickPickItemKind.Separator },
        ];

        for (const agent of AI_AGENTS) {
            const cfg = currentConfigs[agent];
            const provLabel = PROVIDERS[cfg.provider]?.label || cfg.provider;
            items.push({
                label: `$(beaker) ${agent}`,
                description: `${provLabel} / ${cfg.model}`,
                detail: 'Click to change provider and model',
            });
        }

        items.push({ label: '$(key) API Keys', kind: vscode.QuickPickItemKind.Separator });

        for (const [, info] of Object.entries(PROVIDERS)) {
            const has = await hasApiKey(info.envKey);
            items.push({
                label: `$(key) ${info.label}`,
                description: has ? '✓ Set' : '✗ Not set',
                detail: info.envKey,
            });
        }

        items.push(
            { label: '', kind: vscode.QuickPickItemKind.Separator },
            { label: '$(check) Done', description: 'Save and close' },
        );

        const selected = await vscode.window.showQuickPick(items, {
            title: 'QonQrete AI Configuration',
            placeHolder: 'Select an agent or API key to configure',
        });

        if (!selected || selected.label.includes('Done')) { done = true; continue; }

        // Handle agent config
        const agentMatch = AI_AGENTS.find(a => selected.label.includes(a));
        if (agentMatch) {
            const providerPick = await vscode.window.showQuickPick(
                providerNames.map(p => ({
                    label: PROVIDERS[p].label, description: p,
                    picked: currentConfigs[agentMatch].provider === p,
                })),
                { title: `${agentMatch}: Select Provider` }
            );
            if (!providerPick) continue;
            const provId = providerPick.description!;
            const provInfo = PROVIDERS[provId];

            const modelPick = await vscode.window.showQuickPick([
                ...provInfo.models.map(m => ({ label: m, picked: currentConfigs[agentMatch].model === m })),
                { label: '$(edit) Custom model...', description: 'Enter a custom model name' },
            ], { title: `${agentMatch}: Select Model (${provInfo.label})` });
            if (!modelPick) continue;

            let model = modelPick.label;
            if (model.includes('Custom')) {
                const custom = await vscode.window.showInputBox({
                    title: `${agentMatch}: Custom Model`,
                    prompt: `Enter model name for ${provInfo.label}`,
                    value: currentConfigs[agentMatch].model,
                });
                if (!custom) continue;
                model = custom;
            }

            if (writeAgentConfig(configPath, agentMatch, provId, model)) {
                currentConfigs[agentMatch] = { provider: provId, model };
                vscode.window.showInformationMessage(`${agentMatch}: ${provInfo.label} / ${model}`);
            }
            continue;
        }

        // Handle API key
        const keyMatch = Object.entries(PROVIDERS).find(([, info]) => selected.label.includes(info.label));
        if (keyMatch) {
            const [, info] = keyMatch;
            const existing = await getSecret(info.envKey);
            const key = await vscode.window.showInputBox({
                title: `${info.label} API Key (stored securely)`,
                prompt: `Enter your ${info.label} API key (${info.envKey})`,
                password: true,
                placeHolder: existing ? '(already set — leave empty to keep)' : 'sk-...',
            });
            if (key !== undefined && key) {
                await storeSecret(info.envKey, key);
                vscode.window.showInformationMessage(`${info.label} API key saved securely.`);
            }
        }
    }
}

export function registerAIConfigCommand(context: vscode.ExtensionContext): vscode.Disposable {
    return vscode.commands.registerCommand('qonqrete.setAIConfig', executeSetAIConfig);
}
