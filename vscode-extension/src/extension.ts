/**
 * QonQrete VS Code Extension
 * Main entry point
 * 
 * @author WoNQ
 * @version 1.2.4
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import { getRunner, disposeRunner, RunStatus } from './cli/qonqreteRunner';
import { registerInitCommand } from './commands/init';
import { registerRunTasqCommands } from './commands/runTasq';
import { registerResumeCommands } from './commands/resume';
import { registerDeployCommand } from './commands/deploy';
import { registerCreateTasqCommand } from './commands/createTasq';
import { registerAIConfigCommand } from './commands/aiConfig';
import { initSecrets, migrateFromSettings } from './secrets';
import { QonQreteSidebarProvider } from './ui/sidebar';

let statusBarItem: vscode.StatusBarItem;
let sidebarProvider: QonQreteSidebarProvider;
let runStateDisposable: vscode.Disposable | undefined;

/**
 * Extension activation
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
    console.log('QonQrete extension activating...');

    // Initialize secure secret storage
    initSecrets(context);

    // Migrate any API keys from old settings to secure storage
    migrateFromSettings().catch(err => console.warn('[QonQrete] Migration warning:', err));

    const runner = getRunner();
    const shellInfo = runner.getShellInfo();

    // Show blocking warning on Windows without bash
    if (shellInfo.isWindows && !shellInfo.hasBash) {
        const result = await vscode.window.showErrorMessage(
            'QonQrete requires a bash shell to run.\n\nOn Windows, please install Git Bash or use WSL.\n\nYou can also set GIT_BASH environment variable to a custom bash path.',
            { modal: false },
            'Install Git Bash',
            'WSL Documentation',
            'Dismiss'
        );
        
        if (result === 'Install Git Bash') {
            await vscode.env.openExternal(vscode.Uri.parse('https://git-scm.com/download/win'));
        } else if (result === 'WSL Documentation') {
            await vscode.env.openExternal(vscode.Uri.parse('https://docs.microsoft.com/en-us/windows/wsl/install'));
        }
    }

    // Register commands
    context.subscriptions.push(registerInitCommand(context));
    context.subscriptions.push(...registerRunTasqCommands(context));
    context.subscriptions.push(...registerResumeCommands(context));
    context.subscriptions.push(registerDeployCommand(context));
    context.subscriptions.push(registerCreateTasqCommand(context));
    context.subscriptions.push(registerAIConfigCommand(context));

    // Register show status command (single registration point)
    context.subscriptions.push(
        vscode.commands.registerCommand('qonqrete.showStatus', async () => {
            const scriptPath = await runner.getQonQretePath();
            const version = await runner.getVersion();
            const initStatus = await runner.isInitialized();
            const hasTasq = await runner.hasTasqFile();
            const qages = await runner.getAvailableQages();
            const shell = runner.getShellInfo();
            const canExec = runner.canExecute();

            const lines = [
                `QonQrete v${version || 'unknown'}`,
                ``,
                `Script: ${scriptPath || 'Not found'}`,
                `Image: ${initStatus.hasImage ? `Built (${initStatus.engine})` : 'Not built'}`,
                `tasq.md: ${hasTasq ? 'Found' : 'Missing'}`,
                `Qages: ${qages.length}`,
                ``,
                `Shell: ${shell.shellType}${shell.verified ? ' (verified)' : ''}`,
                `Can Execute: ${canExec.canRun ? 'Yes' : canExec.verifying ? 'Verifying...' : 'No'}`,
                !canExec.canRun && canExec.reason ? `Reason: ${canExec.reason}` : '',
            ].filter(l => l !== '');

            await vscode.window.showInformationMessage(lines.join('\n'), { modal: true });
        })
    );

    // Create sidebar provider
    sidebarProvider = new QonQreteSidebarProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            QonQreteSidebarProvider.viewType,
            sidebarProvider
        )
    );

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left,
        100
    );
    statusBarItem.command = 'qonqrete.runTasq';
    context.subscriptions.push(statusBarItem);

    // Subscribe to run state changes
    runStateDisposable = runner.onRunStateChange(handleRunStateChange);
    context.subscriptions.push(runStateDisposable);

    // Initial status bar update (shows verifying state)
    await updateStatusBar();

    // Clean up any orphaned backup files from previous interrupted sessions
    await runner.cleanupOrphanedBackups();

    // Verify shell on activation
    if (shellInfo.hasBash) {
        runner.verifyShell().then((verified) => {
            if (verified) {
                console.log('QonQrete shell verified successfully');
            } else {
                console.log('QonQrete shell verification failed');
            }
            // Update status bar with verification result
            updateStatusBar();
            sidebarProvider.refresh();
        });
    }

    // Watch for workspace changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(async () => {
            runner.clearPathCache();
            await updateStatusBar();
            sidebarProvider.refresh();
        })
    );

    // Watch for worqspace file changes
    const fileWatcher = vscode.workspace.createFileSystemWatcher(
        '**/worqspace/**',
        false, false, false
    );
    fileWatcher.onDidCreate(() => sidebarProvider.refresh());
    fileWatcher.onDidDelete(() => sidebarProvider.refresh());
    fileWatcher.onDidChange(() => sidebarProvider.refresh());
    context.subscriptions.push(fileWatcher);

    // Watch for tasq.md changes
    const tasqWatcher = vscode.workspace.createFileSystemWatcher(
        '**/tasq.md',
        false, false, false
    );
    tasqWatcher.onDidCreate(() => updateStatusBar());
    tasqWatcher.onDidDelete(() => updateStatusBar());
    context.subscriptions.push(tasqWatcher);

    // Watch for config changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(async (event) => {
            if (event.affectsConfiguration('qonqrete')) {
                if (event.affectsConfiguration('qonqrete.qonqretePath')) {
                    runner.clearPathCache();
                }
                await updateStatusBar();
                sidebarProvider.refresh();
            }
        })
    );

    // Welcome message on first activation
    const hasShownWelcome = context.globalState.get<boolean>('qonqrete.welcomeShown');
    if (!hasShownWelcome) {
        showWelcomeMessage();
        context.globalState.update('qonqrete.welcomeShown', true);
    }

    console.log('QonQrete extension activated');
}

/**
 * Handle run state changes and update status bar
 */
function handleRunStateChange(status: RunStatus): void {
    switch (status.state) {
        case 'running':
            statusBarItem.text = '$(sync~spin) QonQrete Running';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            statusBarItem.tooltip = `Running: ${status.command || 'qonqrete'}\nStarted: ${status.startTime?.toLocaleTimeString() || '?'}`;
            break;
            
        case 'completed':
            statusBarItem.text = `$(check) QonQrete Done${status.exitCode !== undefined ? ` (${status.exitCode})` : ''}`;
            statusBarItem.backgroundColor = undefined;
            statusBarItem.tooltip = `Completed at ${status.endTime?.toLocaleTimeString() || '?'}\nExit code: ${status.exitCode ?? 'unknown'}`;
            setTimeout(() => updateStatusBar(), 5000);
            break;
            
        case 'failed':
            statusBarItem.text = `$(error) QonQrete Failed${status.exitCode !== undefined ? ` (${status.exitCode})` : ''}`;
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
            statusBarItem.tooltip = `Failed at ${status.endTime?.toLocaleTimeString() || '?'}\nExit code: ${status.exitCode ?? 'unknown'}`;
            setTimeout(() => updateStatusBar(), 8000);
            break;
            
        case 'timeout':
            statusBarItem.text = '$(warning) QonQrete Timeout';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            statusBarItem.tooltip = 'Run status unknown - marker file not detected.';
            setTimeout(() => updateStatusBar(), 10000);
            break;
            
        default:
            updateStatusBar();
    }
    
    sidebarProvider?.refresh();
}

/**
 * Update status bar based on workspace state.
 * Now uses clean canExecute() contract.
 */
async function updateStatusBar(): Promise<void> {
    const runner = getRunner();
    const runStatus = runner.getRunStatus();

    // Don't override if currently running
    if (runStatus.state === 'running') {
        return;
    }

    const scriptPath = await runner.getQonQretePath();
    const version = await runner.getVersion();
    const canExec = runner.canExecute();
    const shellInfo = runner.getShellInfo();

    if (scriptPath) {
        const hasTasq = await runner.hasTasqFile();
        const initStatus = await runner.isInitialized();
        
        // No bash = blocked
        if (!shellInfo.hasBash) {
            statusBarItem.text = '$(error) QonQrete (no bash)';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
            statusBarItem.tooltip = 'No bash shell found. Install Git Bash or use WSL.';
            statusBarItem.command = 'qonqrete.showStatus';
        } else if (canExec.verifying) {
            // Has bash but verification in progress
            statusBarItem.text = '$(beaker) QonQrete (verifying...)';
            statusBarItem.backgroundColor = undefined;
            statusBarItem.tooltip = `QonQrete v${version || '?'}\nVerifying shell...`;
            statusBarItem.command = 'qonqrete.showStatus';
        } else if (!canExec.canRun) {
            // Verification failed
            statusBarItem.text = '$(error) QonQrete (shell error)';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
            statusBarItem.tooltip = `Shell verification failed: ${canExec.reason || 'unknown'}`;
            statusBarItem.command = 'qonqrete.showStatus';
        } else if (!initStatus.hasImage) {
            statusBarItem.text = '$(beaker) QonQrete (init needed)';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            statusBarItem.tooltip = 'Container image not built. Click to initialize.';
            statusBarItem.command = 'qonqrete.initWorkspace';
        } else if (!hasTasq) {
            statusBarItem.text = '$(beaker) QonQrete (no tasq)';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            statusBarItem.tooltip = 'No tasq.md found. Click to create one.';
            statusBarItem.command = 'qonqrete.runTasq';
        } else {
            // Fully ready and verified
            statusBarItem.text = '$(beaker) QonQrete Ready';
            statusBarItem.backgroundColor = undefined;
            statusBarItem.tooltip = `QonQrete v${version || '?'}\nShell: ${shellInfo.shellType} (verified)\nClick to run tasq.md`;
            statusBarItem.command = 'qonqrete.runTasq';
        }
        
        statusBarItem.show();
    } else {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders && workspaceFolders.length > 0) {
            statusBarItem.text = '$(beaker) QonQrete';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            statusBarItem.tooltip = 'QonQrete not found. Click to deploy.';
            statusBarItem.command = 'qonqrete.deployToWorkspace';
            statusBarItem.show();
        } else {
            statusBarItem.hide();
        }
    }
}

/**
 * Show welcome message
 */
function showWelcomeMessage(): void {
    vscode.window.showInformationMessage(
        'Welcome to QonQrete! Use "Deploy to Workspace" to get started',
        'Deploy to Workspace',
        'Documentation'
    ).then(result => {
        if (result === 'Deploy to Workspace') {
            vscode.commands.executeCommand('qonqrete.deployToWorkspace');
        } else if (result === 'Documentation') {
            vscode.env.openExternal(vscode.Uri.parse('https://qonqrete.sh'));
        }
    });
}

/**
 * Extension deactivation
 */
export function deactivate(): void {
    console.log('QonQrete extension deactivating...');
    
    disposeRunner();
    statusBarItem?.dispose();
    runStateDisposable?.dispose();

    console.log('QonQrete extension deactivated');
}
