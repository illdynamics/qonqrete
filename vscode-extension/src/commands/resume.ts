/**
 * QonQrete Resume and Clean Commands
 * 
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import { getRunner } from '../cli/qonqreteRunner';
import { 
    showQageSelectionDialog, 
    showCleanConfirmDialog,
    showQonstructionNameDialog 
} from '../ui/configWizard';

/**
 * Check if runner can execute, waiting for verification if in progress.
 * Consistent with runTasq.ts behavior.
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
 * Execute the resume command
 */
export async function executeResume(): Promise<void> {
    // Check execution capability (waits for verification if needed)
    if (!await checkCanExecute()) {
        return;
    }

    const runner = getRunner();

    const scriptPath = await runner.getQonQretePath();
    if (!scriptPath) {
        vscode.window.showErrorMessage('QonQrete script not found.');
        return;
    }

    const qages = await runner.getAvailableQages();
    
    if (qages.length === 0) {
        vscode.window.showInformationMessage(
            'No Qages found to resume from. Run QonQrete first to create a Qage.'
        );
        return;
    }

    const selectedQage = await showQageSelectionDialog(qages);
    if (!selectedQage) {
        return;
    }

    const modeChoice = await vscode.window.showQuickPick([
        { label: '$(person) Interactive', description: 'User confirms each cycle', value: false },
        { label: '$(robot) Autonomous', description: 'Run without confirmations', value: true },
    ], {
        placeHolder: 'Select resume mode',
    });

    if (!modeChoice) {
        return;
    }

    const qonstructionName = await showQonstructionNameDialog();

    // Handle sanitization with user feedback
    let sanitizedName: string | undefined;
    if (qonstructionName) {
        const result = runner.sanitizeQonstructionName(qonstructionName);
        if (result.wasModified) {
            const proceed = await vscode.window.showWarningMessage(
                `Name sanitized: "${result.original}" → "${result.sanitized}"`,
                'Continue',
                'Cancel'
            );
            if (proceed !== 'Continue') {
                return;
            }
        }
        sanitizedName = result.sanitized;
    }

    try {
        await runner.resume(selectedQage, {
            autonomous: modeChoice.value,
            qonstructionName: sanitizedName,
        });

        vscode.window.showInformationMessage(
            `Resuming from ${selectedQage}. Check the terminal for output.`,
            'Show Terminal'
        ).then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage(
            `Failed to resume: ${error instanceof Error ? error.message : String(error)}`
        );
    }
}

/**
 * Execute the clean Qages command
 */
export async function executeClean(): Promise<void> {
    // Check execution capability (waits for verification if needed)
    if (!await checkCanExecute()) {
        return;
    }

    const runner = getRunner();

    const scriptPath = await runner.getQonQretePath();
    if (!scriptPath) {
        vscode.window.showErrorMessage('QonQrete script not found.');
        return;
    }

    const qages = await runner.getAvailableQages();
    
    if (qages.length === 0) {
        vscode.window.showInformationMessage('No Qages found to clean.');
        return;
    }

    const cleanResult = await showCleanConfirmDialog(qages);
    if (!cleanResult) {
        return;
    }

    try {
        await runner.clean(cleanResult.qageName, cleanResult.cleanAll);

        const message = cleanResult.cleanAll
            ? 'Cleaning all Qages. Check the terminal for progress.'
            : `Cleaning ${cleanResult.qageName}. Check the terminal for progress.`;

        vscode.window.showInformationMessage(message, 'Show Terminal').then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage(
            `Failed to clean: ${error instanceof Error ? error.message : String(error)}`
        );
    }
}

/**
 * Register the resume and clean commands
 * NOTE: showStatus is registered in extension.ts to avoid duplicate registration
 */
export function registerResumeCommands(context: vscode.ExtensionContext): vscode.Disposable[] {
    return [
        vscode.commands.registerCommand('qonqrete.resumeRun', executeResume),
        vscode.commands.registerCommand('qonqrete.cleanQages', executeClean),
        // showStatus is NOT registered here - it's in extension.ts
    ];
}
