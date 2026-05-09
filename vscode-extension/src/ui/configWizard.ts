/**
 * QonQrete Configuration Wizard
 * Provides VS Code UI dialogs for configuring QonQrete runs
 * 
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import { QonQreteRunConfig } from '../cli/qonqreteRunner';

/**
 * Mode descriptions for the mode selection QuickPick
 */
const MODE_OPTIONS: vscode.QuickPickItem[] = [
    { label: 'program', description: 'General programming mode', picked: true },
    { label: 'enterprise', description: 'Enterprise application development' },
    { label: 'security', description: 'Security-focused development' },
    { label: 'data', description: 'Data processing and analysis' },
    { label: 'devops', description: 'DevOps and infrastructure' },
    { label: 'web', description: 'Web development' },
];

/**
 * Container engine options
 */
const ENGINE_OPTIONS: vscode.QuickPickItem[] = [
    { label: 'auto', description: 'Auto-detect available engine', picked: true },
    { label: 'docker', description: 'Use Docker' },
    { label: 'podman', description: 'Use Podman' },
];

/**
 * Get default configuration from VS Code settings
 */
function getDefaultConfig(): QonQreteRunConfig {
    const config = vscode.workspace.getConfiguration('qonqrete');
    
    return {
        sensitivity: config.get<number>('defaultSensitivity', 1),
        autoSensitivity: config.get<boolean>('defaultAutoBriqSensitivity', true),
        cycles: config.get<number>('defaultCycles', 1),
        mode: config.get<string>('defaultMode', 'program'),
        autonomous: config.get<boolean>('defaultAutonomous', true),
        noSync: config.get<boolean>('noSync', false),
        useSqrapyard: config.get<boolean>('useSqrapyard', false),
        containerEngine: config.get<'auto' | 'docker' | 'podman'>('containerEngine', 'auto'),
    };
}

/**
 * Show the quick configuration wizard
 * Returns the configuration or undefined if cancelled
 */
export async function showQuickConfigWizard(): Promise<QonQreteRunConfig | undefined> {
    const defaults = getDefaultConfig();

    // Step 1: Briq Sensitivity
    const sensitivityInput = await vscode.window.showInputBox({
        title: 'QonQrete Configuration (1/4)',
        prompt: 'Briq Sensitivity (0-16). Higher = more granular briqs',
        value: defaults.sensitivity.toString(),
        ignoreFocusOut: true,
        validateInput: (value) => {
            const num = parseInt(value, 10);
            if (isNaN(num) || num < 0 || num > 16) {
                return 'Please enter a number between 0 and 16';
            }
            return undefined;
        },
    });

    if (sensitivityInput === undefined) {
        return undefined;
    }

    // Step 2: Cycles
    const cyclesInput = await vscode.window.showInputBox({
        title: 'QonQrete Configuration (2/4)',
        prompt: 'Number of execution cycles (1-50)',
        value: defaults.cycles.toString(),
        validateInput: (value) => {
            const num = parseInt(value, 10);
            if (isNaN(num) || num < 1 || num > 50) {
                return 'Please enter a number between 1 and 50';
            }
            return undefined;
        },
    });

    if (cyclesInput === undefined) {
        return undefined;
    }

    // Step 3: Mode
    const modeOptions = MODE_OPTIONS.map(opt => ({
        ...opt,
        picked: opt.label === defaults.mode,
    }));

    const modeSelection = await vscode.window.showQuickPick(modeOptions, {
        title: 'QonQrete Configuration (3/4)',
        placeHolder: 'Select operational mode',
    });

    if (!modeSelection) {
        return undefined;
    }

    // Step 4: Autonomous Mode
    const autonomousSelection = await vscode.window.showQuickPick([
        { label: 'Interactive', description: 'User confirms each cycle', picked: !defaults.autonomous },
        { label: 'Autonomous', description: 'Run without user confirmations', picked: defaults.autonomous },
    ], {
        title: 'QonQrete Configuration (4/4)',
        placeHolder: 'Select execution mode',
    });

    if (!autonomousSelection) {
        return undefined;
    }

    return {
        sensitivity: parseInt(sensitivityInput, 10),
        autoSensitivity: defaults.autoSensitivity ?? true,
        cycles: parseInt(cyclesInput, 10),
        mode: modeSelection.label,
        autonomous: autonomousSelection.label === 'Autonomous',
        noSync: defaults.noSync,
        useSqrapyard: defaults.useSqrapyard,
        containerEngine: defaults.containerEngine,
    };
}

/**
 * Show the full configuration wizard with all options
 */
export async function showFullConfigWizard(): Promise<QonQreteRunConfig | undefined> {
    const defaults = getDefaultConfig();

    // Create multi-step input using QuickPick
    const configItems: vscode.QuickPickItem[] = [
        {
            label: `$(symbol-number) Sensitivity: ${defaults.sensitivity}`,
            description: 'Briq granularity (0-16)',
            detail: 'Higher values create more granular, smaller briqs',
        },
        {
            label: `$(symbol-number) Cycles: ${defaults.cycles}`,
            description: 'Execution cycles (1-50)',
            detail: 'Number of build/review cycles to run',
        },
        {
            label: `$(symbol-misc) Mode: ${defaults.mode}`,
            description: 'Operational mode',
            detail: 'Specialized mode for different project types',
        },
        {
            label: `$(robot) Autonomous: ${defaults.autonomous ? 'Yes' : 'No'}`,
            description: 'Auto-run without confirmations',
            detail: 'When enabled, QonQrete runs without user intervention',
        },
        {
            label: `$(package) Seed Repo: ${defaults.useSqrapyard ? 'Yes' : 'No'}`,
            description: 'Seed from current repository',
            detail: 'Use existing repository code as qodeyard starting state (--seed-repo)',
        },
        {
            label: `$(sync-ignored) No Sync: ${defaults.noSync ? 'Yes' : 'No'}`,
            description: 'Keep outputs in qage/qonstructions only',
            detail: 'Skip repo-root sync-back after run (--no-sync)',
        },
        {
            label: `$(vm) Container: ${defaults.containerEngine}`,
            description: 'Container engine',
            detail: 'Docker, Podman, or auto-detect',
        },
    ];

    const config: QonQreteRunConfig = { ...defaults };
    const continueEditing = true;

    while (continueEditing) {
        // Update labels with current values
        configItems[0].label = `$(symbol-number) Sensitivity: ${config.sensitivity}`;
        configItems[1].label = `$(symbol-number) Cycles: ${config.cycles}`;
        configItems[2].label = `$(symbol-misc) Mode: ${config.mode}`;
        configItems[3].label = `$(robot) Autonomous: ${config.autonomous ? 'Yes' : 'No'}`;
        configItems[4].label = `$(package) Seed Repo: ${config.useSqrapyard ? 'Yes' : 'No'}`;
        configItems[5].label = `$(sync-ignored) No Sync: ${config.noSync ? 'Yes' : 'No'}`;
        configItems[6].label = `$(vm) Container: ${config.containerEngine}`;

        const selected = await vscode.window.showQuickPick([
            ...configItems,
            { label: '', kind: vscode.QuickPickItemKind.Separator },
            { label: '$(play) Run QonQrete', description: 'Start with current configuration' },
            { label: '$(close) Cancel', description: 'Abort configuration' },
        ], {
            title: 'QonQrete Configuration',
            placeHolder: 'Select an option to configure or run',
        });

        if (!selected) {
            return undefined;
        }

        if (selected.label.includes('Run QonQrete')) {
            return config;
        }

        if (selected.label.includes('Cancel')) {
            return undefined;
        }

        // Handle configuration changes
        if (selected.label.includes('Sensitivity')) {
            const input = await vscode.window.showInputBox({
                prompt: 'Briq Sensitivity (0-16)',
                value: config.sensitivity.toString(),
                validateInput: (v) => {
                    const n = parseInt(v, 10);
                    return (isNaN(n) || n < 0 || n > 16) ? 'Enter 0-16' : undefined;
                },
            });
            if (input !== undefined) {
                config.sensitivity = parseInt(input, 10);
            }
        } else if (selected.label.includes('Cycles')) {
            const input = await vscode.window.showInputBox({
                prompt: 'Execution Cycles (1-50)',
                value: config.cycles.toString(),
                validateInput: (v) => {
                    const n = parseInt(v, 10);
                    return (isNaN(n) || n < 1 || n > 50) ? 'Enter 1-50' : undefined;
                },
            });
            if (input !== undefined) {
                config.cycles = parseInt(input, 10);
            }
        } else if (selected.label.includes('Mode')) {
            const modeOptions = MODE_OPTIONS.map(opt => ({
                ...opt,
                picked: opt.label === config.mode,
            }));
            const modeSelection = await vscode.window.showQuickPick(modeOptions, {
                placeHolder: 'Select operational mode',
            });
            if (modeSelection) {
                config.mode = modeSelection.label;
            }
        } else if (selected.label.includes('Autonomous')) {
            config.autonomous = !config.autonomous;
        } else if (selected.label.includes('Seed Repo')) {
            config.useSqrapyard = !config.useSqrapyard;
        } else if (selected.label.includes('No Sync')) {
            config.noSync = !config.noSync;
        } else if (selected.label.includes('Container')) {
            const engineOptions = ENGINE_OPTIONS.map(opt => ({
                ...opt,
                picked: opt.label === config.containerEngine,
            }));
            const engineSelection = await vscode.window.showQuickPick(engineOptions, {
                placeHolder: 'Select container engine',
            });
            if (engineSelection) {
                config.containerEngine = engineSelection.label as 'auto' | 'docker' | 'podman';
            }
        }
    }

    return config;
}

/**
 * Show qonstruction name input dialog
 */
export async function showQonstructionNameDialog(): Promise<string | undefined> {
    return await vscode.window.showInputBox({
        title: 'Save Qonstruction',
        prompt: 'Enter a name for this qonstruction (leave empty to skip)',
        placeHolder: 'my_project',
        validateInput: (value) => {
            if (value && !/^[a-zA-Z0-9_-]+$/.test(value)) {
                return 'Name must contain only letters, numbers, underscores, and hyphens';
            }
            return undefined;
        },
    });
}

/**
 * Show Qage selection dialog
 */
export async function showQageSelectionDialog(qages: string[]): Promise<string | undefined> {
    if (qages.length === 0) {
        vscode.window.showInformationMessage('No Qages found to resume from.');
        return undefined;
    }

    const items = qages.map(qage => {
        // Parse timestamp from qage name (format: qage_YYYYMMDD_HHMMSS)
        const match = qage.match(/qage_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
        let description = '';
        if (match) {
            const [, year, month, day, hour, minute, second] = match;
            description = `${year}-${month}-${day} ${hour}:${minute}:${second}`;
        }
        return {
            label: qage,
            description,
        };
    });

    const selected = await vscode.window.showQuickPick(items, {
        title: 'Select Qage to Resume',
        placeHolder: 'Choose a Qage directory',
    });

    return selected?.label;
}

/**
 * Show clean confirmation dialog
 */
export async function showCleanConfirmDialog(qages: string[]): Promise<{ qageName?: string; cleanAll: boolean } | undefined> {
    if (qages.length === 0) {
        vscode.window.showInformationMessage('No Qages found to clean.');
        return undefined;
    }

    const items: vscode.QuickPickItem[] = [
        { label: '$(trash) Clean All Qages', description: `Delete all ${qages.length} Qage directories` },
        { label: '', kind: vscode.QuickPickItemKind.Separator },
        ...qages.map(qage => {
            const match = qage.match(/qage_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
            let description = '';
            if (match) {
                const [, year, month, day, hour, minute, second] = match;
                description = `${year}-${month}-${day} ${hour}:${minute}:${second}`;
            }
            return {
                label: `$(file-directory) ${qage}`,
                description,
            };
        }),
    ];

    const selected = await vscode.window.showQuickPick(items, {
        title: 'Select Qage to Clean',
        placeHolder: 'Choose a Qage to delete or clean all',
    });

    if (!selected) {
        return undefined;
    }

    if (selected.label.includes('Clean All')) {
        const confirm = await vscode.window.showWarningMessage(
            `Are you sure you want to delete all ${qages.length} Qage directories?`,
            { modal: true },
            'Yes, Delete All'
        );
        if (confirm === 'Yes, Delete All') {
            return { cleanAll: true };
        }
        return undefined;
    }

    // Extract qage name from label
    const qageName = selected.label.replace('$(file-directory) ', '');
    const confirm = await vscode.window.showWarningMessage(
        `Are you sure you want to delete ${qageName}?`,
        { modal: true },
        'Yes, Delete'
    );
    if (confirm === 'Yes, Delete') {
        return { qageName, cleanAll: false };
    }

    return undefined;
}
