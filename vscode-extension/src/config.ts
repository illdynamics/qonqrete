/**
 * QonQrete v2 config helpers.
 *
 * The new architecture keeps configuration in the QonQrete repository itself
 * (config/qq.yaml + config/providers.yaml) rather than a per-workspace
 * worqspace/config.yaml. These helpers locate that config and safely apply
 * the only settings the IDE exposes: provider + model.
 */
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execCapture } from './cli/qonqreteRunner';

export interface ProviderInfo {
    name: string;
    status: string;
    kind: string;
    models: string[];
    defaultModel: string;
    supportsThinkingMode: boolean;
}

export interface QonQreteConfigView {
    configPath: string | undefined;
    providersPath: string | undefined;
    provider: string;
    models: { qlarifier: string; instruqtor: string; construqtor: string; inspeqtor: string };
}

function workspaceRoot(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

/** Resolve the qq config path using settings, QQ_SRC, then the workspace. */
export function resolveConfigPath(): string | undefined {
    const configured = vscode.workspace.getConfiguration('qonqrete').get<string>('configPath');
    if (configured && fs.existsSync(configured)) {
        return configured;
    }

    const qqSrc = process.env.QQ_SRC;
    if (qqSrc) {
        const p = path.join(qqSrc, 'config', 'qq.yaml');
        if (fs.existsSync(p)) {
            return p;
        }
    }

    const root = workspaceRoot();
    if (root) {
        const p = path.join(root, 'config', 'qq.yaml');
        if (fs.existsSync(p)) {
            return p;
        }
    }

    // Fall back to the configured path even if missing so the UI can surface it.
    return configured || undefined;
}

export function resolveProvidersPath(): string | undefined {
    const configured = vscode.workspace.getConfiguration('qonqrete').get<string>('providersPath');
    if (configured && fs.existsSync(configured)) {
        return configured;
    }

    const qqSrc = process.env.QQ_SRC;
    if (qqSrc) {
        const p = path.join(qqSrc, 'config', 'providers.yaml');
        if (fs.existsSync(p)) {
            return p;
        }
    }

    const configPath = resolveConfigPath();
    if (configPath) {
        const p = path.join(path.dirname(configPath), 'providers.yaml');
        if (fs.existsSync(p)) {
            return p;
        }
    }

    return configured || undefined;
}

function parseYamlValue(lines: string[], key: string): string | undefined {
    const idx = lines.findIndex((l) => l.trim().startsWith(key + ':') || l.trim() === key + ':');
    if (idx === -1) {
        return undefined;
    }
    const m = lines[idx].match(new RegExp('^\\s*' + key + '\\s*:\\s*(.*)$'));
    return m ? m[1].replace(/^['"]|['"]$/g, '').trim() : '';
}

function readQqYaml(configPath: string): { provider: string; models: Record<string, string> } {
    const lines = fs.readFileSync(configPath, 'utf8').split(/\r?\n/);
    const provider = parseYamlValue(lines, 'provider') || 'codeseeq';
    const models: Record<string, string> = {};

    // Walk the top-level `models:` block and read `model:` keys for each role.
    let inModels = false;
    let currentRole = '';
    for (const line of lines) {
        if (/^\s*models\s*:\s*$/.test(line)) {
            inModels = true;
            continue;
        }
        if (inModels) {
            const roleMatch = line.match(/^\s{2}([A-Za-z0-9_]+)\s*:\s*$/);
            if (roleMatch) {
                currentRole = roleMatch[1];
                continue;
            }
            const modelMatch = line.match(/^\s{4}model\s*:\s*(.+)\s*$/);
            if (modelMatch && currentRole) {
                models[currentRole] = modelMatch[1].replace(/^['"]|['"]$/g, '').trim();
            }
            // A top-level (no indent) key ends the models block.
            if (/^\S/.test(line) && !/^\s/.test(line) && !/^\s*models\s*:\s*$/.test(line)) {
                inModels = false;
            }
        }
    }

    return { provider, models };
}

export async function readQonQreteConfig(): Promise<QonQreteConfigView | undefined> {
    const configPath = resolveConfigPath();
    if (!configPath) {
        return undefined;
    }
    const raw = readQqYaml(configPath);
    const defaults = {
        qlarifier: 'deepseek-v4-pro-thinking',
        instruqtor: 'deepseek-v4-pro-thinking',
        construqtor: 'deepseek-v4-flash',
        inspeqtor: 'deepseek-v4-pro-thinking',
    };
    return {
        configPath,
        providersPath: resolveProvidersPath(),
        provider: raw.provider,
        models: {
            qlarifier: raw.models.qlarifier || defaults.qlarifier,
            instruqtor: raw.models.instruqtor || defaults.instruqtor,
            construqtor: raw.models.construqtor || defaults.construqtor,
            inspeqtor: raw.models.inspeqtor || defaults.inspeqtor,
        },
    };
}

/** List providers from `qq providers --json` with a fallback to providers.yaml. */
export async function listProviders(): Promise<ProviderInfo[]> {
    try {
        const out = await execCapture(['providers', '--json']);
        const parsed = JSON.parse(out);
        return Object.entries(parsed).map(([name, raw]) => {
            const info = raw as any;
            return {
                name,
                status: info.status || 'unknown',
                kind: info.kind || 'cli',
                models: Array.isArray(info.models) ? info.models : [],
                defaultModel: info.default_model || '',
                supportsThinkingMode: !!info.supports_thinking_mode,
            };
        });
    } catch {
        // Fallback: read providers.yaml and expose a usable subset.
        const providersPath = resolveProvidersPath();
        if (!providersPath) {
            return [];
        }
        const lines = fs.readFileSync(providersPath, 'utf8').split(/\r?\n/);
        const result: ProviderInfo[] = [];
        let current = '';
        let currentInfo: any = null;
        for (const line of lines) {
            const m = line.match(/^  ([A-Za-z0-9_-]+)\s*:\s*$/);
            if (m) {
                if (current && currentInfo) {
                    result.push({ name: current, ...currentInfo });
                }
                current = m[1];
                currentInfo = { status: 'unknown', kind: 'cli', models: [], defaultModel: '', supportsThinkingMode: false };
                continue;
            }
            if (!currentInfo) {
                continue;
            }
            const status = line.match(/^\s{4}status\s*:\s*(\S+)/);
            if (status) { currentInfo.status = status[1]; continue; }
            const dm = line.match(/^\s{4}default_model\s*:\s*(\S+)/);
            if (dm) { currentInfo.defaultModel = dm[1]; continue; }
            const mm = line.match(/^\s{6}-\s*(.+)\s*$/);
            if (mm) { currentInfo.models.push(mm[1].trim()); }
        }
        if (current && currentInfo) {
            result.push({ name: current, ...currentInfo });
        }
        return result;
    }
}

/** List models for a provider from `qq models --provider X --json`. */
export async function listModels(provider: string): Promise<string[]> {
    try {
        const out = await execCapture(['models', '--provider', provider, '--json']);
        const parsed = JSON.parse(out);
        if (Array.isArray(parsed.models)) {
            return parsed.models;
        }
        return [];
    } catch {
        const providers = await listProviders();
        const found = providers.find((p) => p.name === provider);
        return found?.models ?? [];
    }
}

/**
 * Persist provider + a single model to config/qq.yaml.
 *
 * The IDE intentionally exposes one model value and applies it to all four
 * QonQrete roles (qlarifier/instruqtor/construqtor/inspeqtor) so the
 * configuration remains simple, exactly matching the new engine surface.
 */
export async function saveProviderAndModel(provider: string, model: string): Promise<boolean> {
    const configPath = resolveConfigPath();
    if (!configPath) {
        return false;
    }
    if (!fs.existsSync(configPath)) {
        // Create a minimal config file if none exists.
        fs.mkdirSync(path.dirname(configPath), { recursive: true });
        fs.writeFileSync(
            configPath,
            `provider: ${provider}\n\nmodels:\n  qlarifier:\n    model: ${model}\n  instruqtor:\n    model: ${model}\n  construqtor:\n    model: ${model}\n  inspeqtor:\n    model: ${model}\n`,
            'utf8',
        );
        return true;
    }

    const lines = fs.readFileSync(configPath, 'utf8').split(/\r?\n/);
    const result: string[] = [];
    let providerSet = false;
    let inModels = false;
    let currentRole = '';
    const roles = ['qlarifier', 'instruqtor', 'construqtor', 'inspeqtor'];
    const modelSetFor = new Set<string>();

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Update the top-level provider line.
        if (!providerSet && /^\s*provider\s*:/.test(line)) {
            result.push(`provider: ${provider}`);
            providerSet = true;
            continue;
        }

        if (/^\s*models\s*:\s*$/.test(line)) {
            inModels = true;
            result.push(line);
            continue;
        }

        if (inModels) {
            const roleMatch = line.match(/^\s{2}([A-Za-z0-9_]+)\s*:\s*$/);
            if (roleMatch) {
                currentRole = roleMatch[1];
                result.push(line);
                continue;
            }
            const modelMatch = line.match(/^(\s{4})model\s*:.*$/);
            if (modelMatch && roles.includes(currentRole)) {
                result.push(`${modelMatch[1]}model: ${model}`);
                modelSetFor.add(currentRole);
                continue;
            }
            if (/^\S/.test(line)) {
                inModels = false;
                currentRole = '';
            }
        }

        result.push(line);
    }

    // If the file had no `provider:` line at all, insert one at the top.
    if (!providerSet) {
        result.unshift(`provider: ${provider}`);
    }

    // If any role is missing entirely, append a models block with it.
    const missing = roles.filter((r) => !modelSetFor.has(r));
    if (missing.length > 0) {
        result.push('');
        if (!result.some((l) => /^\s*models\s*:\s*$/.test(l))) {
            result.push('models:');
        }
        for (const role of missing) {
            result.push(`  ${role}:`);
            result.push(`    model: ${model}`);
        }
    }

    fs.writeFileSync(configPath, result.join('\n'), 'utf8');
    return true;
}
