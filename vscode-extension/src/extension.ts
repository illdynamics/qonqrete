/**
 * QonQrete v2 VS Code extension — main entry point.
 */
import * as vscode from 'vscode';
import { getRunner, disposeRunner, clearInvocationCache } from './cli/qonqreteRunner';
import { initSecrets, buildSecureEnvMap } from './secrets';
import { QonQreteSidebarProvider } from './ui/sidebar';
import { registerCommands } from './commands';

let statusBarItem: vscode.StatusBarItem;
let sidebarProvider: QonQreteSidebarProvider | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    console.log('QonQrete extension activating…');

    initSecrets(context);

    // Pre-warm secret env so the first terminal run has API keys available.
    await buildSecureEnvMap().catch(() => undefined);

    registerCommands(context);

    sidebarProvider = new QonQreteSidebarProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(QonQreteSidebarProvider.viewType, sidebarProvider),
    );

    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'qonqrete.runCurrentFile';
    context.subscriptions.push(statusBarItem);

    await updateStatusBar();

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(async (event) => {
            if (event.affectsConfiguration('qonqrete')) {
                clearInvocationCache();
                await updateStatusBar();
                sidebarProvider?.refresh();
            }
        }),
    );

    console.log('QonQrete extension activated');
}

async function updateStatusBar(): Promise<void> {
    const runner = getRunner();
    if (runner.isAvailable()) {
        statusBarItem.text = '$(beaker) QonQrete';
        statusBarItem.tooltip = 'Run the currently open Markdown file as a QonQrete task';
        statusBarItem.command = 'qonqrete.runCurrentFile';
        statusBarItem.backgroundColor = undefined;
    } else {
        statusBarItem.text = '$(warning) QonQrete';
        statusBarItem.tooltip = 'QonQrete (qq) not found — set qonqrete.qqPath';
        statusBarItem.command = 'qonqrete.configure';
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
    statusBarItem.show();
}

export function deactivate(): void {
    disposeRunner();
    statusBarItem?.dispose();
    sidebarProvider = undefined;
}
