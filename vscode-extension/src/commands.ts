/**
 * QonQrete v2 command registrations.
 */
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { getRunner } from './cli/qonqreteRunner';
import {
    readQonQreteConfig,
    listProviders,
    listModels,
    saveProviderAndModel,
    resolveConfigPath,
} from './config';
import { promptForApiKey, getSecret, PROVIDER_ENV_MAP } from './secrets';

function workspaceRoot(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function defaultDestination(): string {
    const configured = vscode.workspace.getConfiguration('qonqrete').get<string>('destinationDir');
    if (configured) { return configured; }
    return workspaceRoot() || '';
}

async function chooseNoTui(): Promise<boolean | undefined> {
    const pick = await vscode.window.showQuickPick([
        { label: '$(device-desktop) TUI cockpit', description: 'Run in the full QonQrete terminal cockpit (default)', value: false },
        { label: '$(terminal) Headless', description: 'Add --no-tui and stream output plainly', value: true },
    ], { title: 'QonQrete run mode', placeHolder: 'Choose run mode' });
    return pick?.value;
}

async function ensureApiKey(provider: string): Promise<void> {
    const envKey = PROVIDER_ENV_MAP[provider];
    if (!envKey) { return; }
    if (process.env[envKey]) { return; }
    const stored = await getSecret(envKey);
    if (!stored) {
        await promptForApiKey(provider);
    }
}

/** Run a task file through the v2 engine with destination + mode prompts. */
async function runTaskFile(taskFile: string): Promise<void> {
    const runner = getRunner();
    if (!runner.isAvailable()) {
        const action = await vscode.window.showErrorMessage(
            'QonQrete (qq) CLI not found. Install QonQrete or set the qonqrete.qqPath setting.',
            'Open Settings',
        );
        if (action === 'Open Settings') {
            await vscode.commands.executeCommand('workbench.action.openSettings', 'qonqrete.qqPath');
        }
        return;
    }

    const configuredNoTui = vscode.workspace.getConfiguration('qonqrete').get<boolean>('noTui', false);
    const noTui = configuredNoTui ? true : await chooseNoTui();
    if (noTui === undefined) { return; }

    const dest = await runner.pickDestinationDir(defaultDestination());
    if (!dest) { return; }

    const cfg = await readQonQreteConfig();
    if (cfg?.provider) {
        await ensureApiKey(cfg.provider);
    }

    try {
        await runner.runTask({
            taskFile,
            destinationDir: dest,
            noTui,
            provider: cfg?.provider,
            configPath: cfg?.configPath,
        });
        vscode.window.showInformationMessage('QonQrete run started. Watch the QonQrete terminal.');
    } catch (err) {
        vscode.window.showErrorMessage(`Failed to start QonQrete: ${err instanceof Error ? err.message : String(err)}`);
    }
}

export async function runCurrentFile(): Promise<void> {
    const active = vscode.window.activeTextEditor?.document;
    let taskFile: string | undefined;
    if (active && !active.isUntitled && (active.languageId === 'markdown' || active.fileName.endsWith('.md'))) {
        if (active.isDirty) { await active.save(); }
        taskFile = active.uri.fsPath;
    }
    if (!taskFile) {
        taskFile = await getRunner().pickTaskFile();
    }
    if (!taskFile) {
        vscode.window.showWarningMessage('Open or select a Markdown task file first.');
        return;
    }
    await runTaskFile(taskFile);
}

export async function runTask(): Promise<void> {
    const taskFile = await getRunner().pickTaskFile();
    if (!taskFile) { return; }
    await runTaskFile(taskFile);
}

export async function configure(): Promise<void> {
    const providers = await listProviders();
    const current = await readQonQreteConfig();
    if (providers.length === 0) {
        vscode.window.showErrorMessage('Could not load providers. Check that QonQrete is installed.');
        return;
    }

    const providerPick = await vscode.window.showQuickPick(
        providers.map((p) => ({
            label: p.name,
            description: `${p.status}${p.defaultModel ? ` · default ${p.defaultModel}` : ''}`,
            detail: p.models.join(', '),
            picked: current?.provider === p.name,
        })),
        { title: 'QonQrete provider', placeHolder: 'Select provider' },
    );
    if (!providerPick) { return; }
    const provider = providerPick.label;

    const models = await listModels(provider);
    const modelItems = models.length > 0
        ? models.map((m) => ({ label: m }))
        : [{ label: 'Custom model…' }];
    const modelPick = await vscode.window.showQuickPick(modelItems, {
        title: `QonQrete model for ${provider}`,
        placeHolder: 'Select model (applies to all QonQrete roles)',
    });
    if (!modelPick) { return; }

    let model = modelPick.label;
    if (model.includes('Custom model')) {
        const custom = await vscode.window.showInputBox({
            title: 'Custom model',
            prompt: `Enter the model id for ${provider}`,
        });
        if (!custom) { return; }
        model = custom.trim();
    }

    const saved = await saveProviderAndModel(provider, model);
    if (!saved) {
        vscode.window.showErrorMessage('Could not save configuration. Set qonqrete.configPath to the QonQrete config/qq.yaml file.');
        return;
    }

    vscode.window.showInformationMessage(`QonQrete configured: ${provider} / ${model}`);

    // Offer to store the matching API key.
    const envKey = PROVIDER_ENV_MAP[provider];
    if (envKey && !process.env[envKey]) {
        const result = await vscode.window.showInformationMessage(
            `Set the ${envKey} API key for ${provider}?`,
            'Set API Key',
            'Skip',
        );
        if (result === 'Set API Key') {
            await promptForApiKey(provider);
        }
    }
}

export async function openConfigFile(): Promise<void> {
    const configPath = resolveConfigPath();
    if (!configPath) {
        vscode.window.showWarningMessage('QonQrete config not found. Set qonqrete.configPath.');
        return;
    }
    const uri = vscode.Uri.file(configPath);
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);
}

export async function showRuns(): Promise<void> {
    const runner = getRunner();
    const runs = await runner.listRuns();
    if (runs.length === 0) {
        vscode.window.showInformationMessage('No QonQrete runs found.');
        return;
    }
    const pick = await vscode.window.showQuickPick(
        runs.map((r) => ({
            label: r.id,
            description: r.state,
            detail: r.root ? `Root: ${r.root}` : undefined,
        })),
        { title: 'QonQrete runs', placeHolder: 'Select a run to open its root or list details' },
    );
    if (!pick) { return; }
    const selected = runs.find((r) => r.id === pick.label);
    if (selected?.root && fs.existsSync(selected.root)) {
        await vscode.commands.executeCommand('revealFileInOS', vscode.Uri.file(selected.root));
    }
}

export function registerCommands(context: vscode.ExtensionContext): void {
    const reg = (id: string, fn: (...args: any[]) => any) => {
        context.subscriptions.push(vscode.commands.registerCommand(id, fn));
    };

    reg('qonqrete.runCurrentFile', runCurrentFile);
    reg('qonqrete.runTask', runTask);
    reg('qonqrete.configure', configure);
    reg('qonqrete.openConfigFile', openConfigFile);
    reg('qonqrete.doctor', () => getRunner().runDoctor());
    reg('qonqrete.verify', () => getRunner().runVerify());
    reg('qonqrete.cleanup', async () => {
        const dest = await getRunner().pickDestinationDir(defaultDestination());
        if (dest) { await getRunner().runCleanup(dest); }
    });
    reg('qonqrete.replay', () => getRunner().runReplay());
    reg('qonqrete.runs', showRuns);
    reg('qonqrete.exec', async () => {
        const command = await vscode.window.showInputBox({
            title: 'QonQrete exec',
            prompt: 'Command to run through qq exec',
            placeHolder: 'e.g. ls -la',
        });
        if (command) { await getRunner().runExec(command); }
    });
    reg('qonqrete.chat', () => getRunner().runChat());
    reg('qonqrete.showOutput', () => getRunner().showOutput());
}
