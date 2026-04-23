/**
 * QonQrete Init Command
 * Initializes the QonQrete workspace by building the container image
 * 
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import { getRunner } from '../cli/qonqreteRunner';

/**
 * Execute the init command
 */
export async function executeInit(): Promise<void> {
    const runner = getRunner();

    // Check if qonqrete.sh exists
    const scriptPath = await runner.getQonQretePath();
    if (!scriptPath) {
        const result = await vscode.window.showErrorMessage(
            'QonQrete script (qonqrete.sh) not found in the workspace.',
            'Configure Path',
            'Learn More'
        );

        if (result === 'Configure Path') {
            await vscode.commands.executeCommand('workbench.action.openSettings', 'qonqrete.qonqretePath');
        } else if (result === 'Learn More') {
            await vscode.env.openExternal(vscode.Uri.parse('https://qonqrete.sh'));
        }
        return;
    }

    // Check initialization status with proper image detection
    const initStatus = await runner.isInitialized();
    
    if (initStatus.hasImage) {
        const result = await vscode.window.showInformationMessage(
            `QonQrete container image already exists (via ${initStatus.engine}). Rebuild?`,
            'Rebuild Image',
            'Cancel'
        );
        
        if (result !== 'Rebuild Image') {
            return;
        }
    } else if (initStatus.hasDockerfile) {
        // Dockerfile exists but no image - user likely needs to init
        const result = await vscode.window.showInformationMessage(
            'Dockerfile found but container image not built yet. Build now?',
            'Build Image',
            'Cancel'
        );
        
        if (result !== 'Build Image') {
            return;
        }
    }
    // If neither - just proceed with init

    try {
        await vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'QonQrete',
                cancellable: false,
            },
            async (progress) => {
                progress.report({ message: 'Building container image...' });
                
                await runner.init();
                
                vscode.window.showInformationMessage(
                    'QonQrete init started. This may take a few minutes.',
                    'Show Terminal'
                ).then(result => {
                    if (result === 'Show Terminal') {
                        vscode.commands.executeCommand('workbench.action.terminal.focus');
                    }
                });
            }
        );
    } catch (error) {
        vscode.window.showErrorMessage(
            `Failed to initialize: ${error instanceof Error ? error.message : String(error)}`
        );
    }
}

/**
 * Register the init command
 */
export function registerInitCommand(context: vscode.ExtensionContext): vscode.Disposable {
    return vscode.commands.registerCommand('qonqrete.initWorkspace', executeInit);
}
