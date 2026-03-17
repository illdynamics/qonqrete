/**
 * QonQrete Run Tasq Commands
 * 
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { getRunner, QonQreteRunConfig } from '../cli/qonqreteRunner';
import { 
    showQuickConfigWizard, 
    showFullConfigWizard, 
    showQonstructionNameDialog 
} from '../ui/configWizard';
import { promptForMissingApiKeys } from './aiConfig';

/**
 * Save the document if it's dirty
 */
async function saveDocumentIfNeeded(uri: vscode.Uri): Promise<boolean> {
    const document = vscode.workspace.textDocuments.find(
        doc => doc.uri.toString() === uri.toString()
    );
    
    if (document && document.isDirty) {
        const saved = await document.save();
        if (!saved) {
            const choice = await vscode.window.showWarningMessage(
                'Failed to save the document. Run anyway with the last saved version?',
                'Run Anyway',
                'Cancel'
            );
            return choice === 'Run Anyway';
        }
    }
    
    return true;
}

/**
 * Check if runner can execute, waiting for verification if in progress
 */
async function checkCanExecute(): Promise<boolean> {
    const runner = getRunner();
    let canExec = runner.canExecute();
    
    // If verification is in progress, wait for it with a progress indicator
    if (canExec.verifying) {
        const verified = await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'QonQrete: Verifying shell...',
            cancellable: false,
        }, async () => {
            return await runner.waitForVerification();
        });
        
        if (!verified) {
            canExec = runner.canExecute();
            vscode.window.showErrorMessage(
                canExec.reason || 'Shell verification failed'
            );
            return false;
        }
        return true;
    }
    
    if (!canExec.canRun) {
        const result = await vscode.window.showErrorMessage(
            canExec.reason || 'Cannot run QonQrete',
            'Install Git Bash',
            'Cancel'
        );
        
        if (result === 'Install Git Bash') {
            await vscode.env.openExternal(vscode.Uri.parse('https://git-scm.com/download/win'));
        }
        return false;
    }
    
    return true;
}

/**
 * Process qonstruction name with user feedback
 */
async function processQonstructionName(name?: string): Promise<string | undefined> {
    if (!name) return undefined;
    
    const runner = getRunner();
    const result = runner.sanitizeQonstructionName(name);
    
    if (result.wasModified) {
        const proceed = await vscode.window.showWarningMessage(
            `Qonstruction name sanitized:\n"${result.original}" → "${result.sanitized}"\n\nOnly alphanumeric characters, underscores, and hyphens are allowed.`,
            'Use Sanitized Name',
            'Cancel'
        );
        
        if (proceed !== 'Use Sanitized Name') {
            return undefined;
        }
    }
    
    return result.sanitized;
}

/**
 * Execute the run tasq command
 */
export async function executeRunTasq(fileUri?: vscode.Uri): Promise<void> {
    // Check execution capability first
    if (!await checkCanExecute()) {
        return;
    }

    const runner = getRunner();

    // If a specific file was selected, use it
    if (fileUri) {
        if (!await saveDocumentIfNeeded(fileUri)) {
            return;
        }
        return executeRunSpecificTasq(fileUri);
    }

    // Check if runtime is deployed
    const scriptPath = await runner.getQonQretePath();
    if (!scriptPath) {
        const result = await vscode.window.showWarningMessage(
            'QonQrete runtime not found in this workspace.',
            'Deploy to Workspace',
            'Configure Path',
            'Cancel'
        );
        if (result === 'Deploy to Workspace') {
            await vscode.commands.executeCommand('qonqrete.deployToWorkspace');
        } else if (result === 'Configure Path') {
            await vscode.commands.executeCommand('workbench.action.openSettings', 'qonqrete.qonqretePath');
        }
        return;
    }

    // Check if tasq.md exists (workspace root or internal)
    const hasTasq = await runner.hasTasqFile();
    if (!hasTasq) {
        const result = await vscode.window.showWarningMessage(
            'No tasq.md found. Create one to define your build task.',
            'Create tasq.md',
            'Cancel'
        );
        if (result === 'Create tasq.md') {
            await vscode.commands.executeCommand('qonqrete.createTasq');
        }
        return;
    }

    // Save any open tasq.md before running
    const tasqPath = await runner.getTasqPath();
    if (tasqPath) {
        if (!await saveDocumentIfNeeded(vscode.Uri.file(tasqPath))) {
            return;
        }
    }

    // Sync workspace-root tasq.md into internal runtime location
    await runner.syncRootTasqToInternal();

    // Auto-init if image is missing
    const initStatus = await runner.isInitialized();
    if (!initStatus.hasImage) {
        const initChoice = await vscode.window.showInformationMessage(
            'Container image not built yet. Build it now? (This may take a few minutes)',
            'Build & Run',
            'Cancel'
        );
        if (initChoice !== 'Build & Run') return;

        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'QonQrete: Building container image...',
            cancellable: false,
        }, async () => {
            await runner.init();
        });

        vscode.window.showInformationMessage(
            'Container image building in terminal. Run Tasq again when init completes.',
            'Show Terminal'
        ).then(r => { if (r) vscode.commands.executeCommand('workbench.action.terminal.focus'); });
        return;
    }

    // Check for missing API keys
    const workingDir = await runner.getQonQreteWorkingDir();
    if (workingDir) {
        const configYaml = path.join(workingDir, 'worqspace', 'config.yaml');
        const keysOk = await promptForMissingApiKeys(configYaml);
        if (!keysOk) return;
    }

    // Show configuration wizard
    const config = await showConfigurationDialog();
    if (!config) {
        return;
    }

    // Ask for qonstruction name with sanitization feedback
    const rawName = await showQonstructionNameDialog();
    if (rawName !== undefined) {
        const sanitizedName = await processQonstructionName(rawName);
        if (rawName && !sanitizedName) {
            return; // User cancelled after seeing sanitization
        }
        config.qonstructionName = sanitizedName;
    }

    try {
        await runner.run(config);

        vscode.window.showInformationMessage(
            'QonQrete run started. Check the terminal for output.',
            'Show Terminal'
        ).then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage(
            `Failed to run QonQrete: ${error instanceof Error ? error.message : String(error)}`
        );
    }
}

/**
 * Execute run on a specific tasq.md file
 */
async function executeRunSpecificTasq(fileUri: vscode.Uri): Promise<void> {
    const runner = getRunner();
    const filePath = fileUri.fsPath;

    // Show configuration wizard
    const config = await showConfigurationDialog();
    if (!config) {
        return;
    }

    const rawName = await showQonstructionNameDialog();
    if (rawName !== undefined) {
        const sanitizedName = await processQonstructionName(rawName);
        if (rawName && !sanitizedName) {
            return;
        }
        config.qonstructionName = sanitizedName;
    }

    try {
        await runner.runSpecificTasq(filePath, config);
        
        const parentName = path.basename(path.dirname(filePath));
        vscode.window.showInformationMessage(
            parentName === 'worqspace' 
                ? 'Running QonQrete from selected workspace.'
                : 'Running with selected file as temporary tasq.md.',
            'Show Terminal'
        ).then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage(
            `Failed to run: ${error instanceof Error ? error.message : String(error)}`
        );
    }
}

/**
 * Execute run as QonQrete tasq (for non-tasq.md files)
 */
export async function executeRunAsQonqreteTasq(fileUri?: vscode.Uri): Promise<void> {
    // Check execution capability first
    if (!await checkCanExecute()) {
        return;
    }

    const runner = getRunner();

    // Determine the file to use
    let filePath: string | undefined;
    let fileUriToSave: vscode.Uri | undefined;
    
    if (fileUri) {
        filePath = fileUri.fsPath;
        fileUriToSave = fileUri;
    } else {
        const activeEditor = vscode.window.activeTextEditor;
        if (activeEditor && activeEditor.document.languageId === 'markdown') {
            filePath = activeEditor.document.uri.fsPath;
            fileUriToSave = activeEditor.document.uri;
        }
    }

    if (!filePath || !fileUriToSave) {
        vscode.window.showWarningMessage('No markdown file selected.');
        return;
    }

    // Save before running
    if (!await saveDocumentIfNeeded(fileUriToSave)) {
        return;
    }

    // Confirm with user
    const fileName = path.basename(filePath);
    const result = await vscode.window.showInformationMessage(
        `Use "${fileName}" as temporary tasq.md for this QonQrete run?\n\nThe original tasq.md will be restored after the run completes.`,
        { modal: true },
        'Yes, Run',
        'Cancel'
    );

    if (result !== 'Yes, Run') {
        return;
    }

    // Check if qonqrete.sh exists — offer deploy if not
    const folder = runner.getWorkspaceFolderForFile(filePath);
    const scriptPath = await runner.getQonQretePath(folder);
    if (!scriptPath) {
        const deployChoice = await vscode.window.showWarningMessage(
            'QonQrete runtime not found in this workspace.',
            'Deploy to Workspace',
            'Cancel'
        );
        if (deployChoice === 'Deploy to Workspace') {
            await vscode.commands.executeCommand('qonqrete.deployToWorkspace');
        }
        return;
    }

    // Auto-init if image is missing
    const initStatus = await runner.isInitialized(folder);
    if (!initStatus.hasImage) {
        const initChoice = await vscode.window.showInformationMessage(
            'Container image not built yet. Build it now? (This may take a few minutes)',
            'Build & Run',
            'Cancel'
        );
        if (initChoice !== 'Build & Run') return;

        await runner.init(folder);
        vscode.window.showInformationMessage(
            'Container image building in terminal. Run again when init completes.',
            'Show Terminal'
        ).then(r => { if (r) vscode.commands.executeCommand('workbench.action.terminal.focus'); });
        return;
    }

    // Show configuration wizard
    const config = await showConfigurationDialog();
    if (!config) {
        return;
    }

    const rawName = await showQonstructionNameDialog();
    if (rawName !== undefined) {
        const sanitizedName = await processQonstructionName(rawName);
        if (rawName && !sanitizedName) {
            return;
        }
        config.qonstructionName = sanitizedName;
    }

    try {
        await runner.runWithFile(filePath, config, folder);
        
        vscode.window.showInformationMessage(
            `Running with "${fileName}" as temporary tasq.md. Original will be restored when done.`,
            'Show Terminal'
        ).then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage(
            `Failed to run: ${error instanceof Error ? error.message : String(error)}`
        );
    }
}

/**
 * Show the configuration dialog
 */
async function showConfigurationDialog(): Promise<QonQreteRunConfig | undefined> {
    const wizardChoice = await vscode.window.showQuickPick([
        { label: '$(zap) Quick Config', description: 'Essential options only', value: 'quick' },
        { label: '$(gear) Full Config', description: 'All configuration options', value: 'full' },
        { label: '$(play) Use Defaults', description: 'Run with saved settings', value: 'default' },
    ], {
        placeHolder: 'Choose configuration mode',
    });

    if (!wizardChoice) {
        return undefined;
    }

    switch (wizardChoice.value) {
        case 'quick':
            return await showQuickConfigWizard();
        case 'full':
            return await showFullConfigWizard();
        case 'default':
            return getDefaultConfig();
        default:
            return undefined;
    }
}

/**
 * Get default config from VS Code settings
 */
function getDefaultConfig(): QonQreteRunConfig {
    const vsConfig = vscode.workspace.getConfiguration('qonqrete');
    return {
        sensitivity: vsConfig.get<number>('defaultSensitivity', 6),
        cycles: vsConfig.get<number>('defaultCycles', 3),
        mode: vsConfig.get<string>('defaultMode', 'program'),
        autonomous: vsConfig.get<boolean>('defaultAutonomous', false),
        useSqrapyard: vsConfig.get<boolean>('useSqrapyard', false),
        containerEngine: vsConfig.get<'auto' | 'docker' | 'podman' | 'msb'>('containerEngine', 'auto'),
        enableTui: vsConfig.get<boolean>('enableTui', false),
    };
}

/**
 * Register the run tasq commands
 */
export function registerRunTasqCommands(context: vscode.ExtensionContext): vscode.Disposable[] {
    return [
        vscode.commands.registerCommand('qonqrete.runTasq', executeRunTasq),
        vscode.commands.registerCommand('qonqrete.runAsQonqreteTasq', executeRunAsQonqreteTasq),
        vscode.commands.registerCommand('qonqrete.openConfigDialog', async () => {
            if (!await checkCanExecute()) {
                return;
            }
            
            const runner = getRunner();
            
            // Check for tasq.md before showing config dialog
            const hasTasq = await runner.hasTasqFile();
            if (!hasTasq) {
                const result = await vscode.window.showWarningMessage(
                    'No tasq.md found. Create one at the workspace root or use "Run as QonQrete Tasq" on a markdown file.',
                    'Create tasq.md',
                    'Cancel'
                );
                
                if (result === 'Create tasq.md') {
                    const tasqPath = await runner.getTasqPath();
                    if (tasqPath) {
                        const uri = vscode.Uri.file(tasqPath);
                        await vscode.workspace.fs.writeFile(uri, Buffer.from('# Task\n\nDescribe your task here.\n'));
                        await vscode.window.showTextDocument(uri);
                    }
                }
                return;
            }
            
            const config = await showFullConfigWizard();
            if (!config) {
                return;
            }
            
            // Consistent qonstruction name handling (same as other run commands)
            const rawName = await showQonstructionNameDialog();
            if (rawName !== undefined) {
                const sanitizedName = await processQonstructionName(rawName);
                if (rawName && !sanitizedName) {
                    return; // User cancelled sanitization
                }
                config.qonstructionName = sanitizedName;
            }
            
            const tasqPath = await runner.getTasqPath();
            if (tasqPath) {
                await saveDocumentIfNeeded(vscode.Uri.file(tasqPath));
            }
            
            try {
                await runner.run(config);
                vscode.window.showInformationMessage(
                    'Running QonQrete with full configuration.',
                    'Show Terminal'
                ).then(result => {
                    if (result === 'Show Terminal') {
                        vscode.commands.executeCommand('workbench.action.terminal.focus');
                    }
                });
            } catch (error) {
                vscode.window.showErrorMessage(
                    `Failed to run: ${error instanceof Error ? error.message : String(error)}`
                );
            }
        }),
    ];
}
