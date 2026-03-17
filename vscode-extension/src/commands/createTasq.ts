/**
 * QonQrete Create Tasq Command
 * Creates a starter tasq.md at workspace root
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

const TASQ_TEMPLATE = `# TasQ - Define Your Objective

<!--
Welcome to QonQrete! Define your task below.
This file lives at your workspace root for easy editing.
When you run QonQrete, it gets synced into the runtime automatically.

Tips for a good TasQ:
- Be specific about what you want to build
- Include file/folder structure if you have preferences
- Mention any specific libraries or frameworks
- Define success criteria

Example:
Create a Python CLI tool that:
1. Reads a CSV file from command line argument
2. Generates a summary report with statistics
3. Saves the report as JSON

Requirements:
- Use argparse for CLI
- Use pandas for data processing
- Include error handling for missing files
- Write unit tests
-->

## Your TasQ:



`;

/**
 * Execute the create tasq command
 */
export async function executeCreateTasq(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage('No workspace folder open.');
        return;
    }

    const wsRoot = workspaceFolders[0].uri.fsPath;
    const tasqPath = path.join(wsRoot, 'tasq.md');

    if (fs.existsSync(tasqPath)) {
        // Just open it
        const doc = await vscode.workspace.openTextDocument(tasqPath);
        await vscode.window.showTextDocument(doc);
        return;
    }

    // Create with template
    fs.writeFileSync(tasqPath, TASQ_TEMPLATE, 'utf8');

    // Open in editor
    const doc = await vscode.workspace.openTextDocument(tasqPath);
    await vscode.window.showTextDocument(doc);

    vscode.window.showInformationMessage('tasq.md created! Edit it and run QonQrete when ready.');
}

/**
 * Register the create tasq command
 */
export function registerCreateTasqCommand(context: vscode.ExtensionContext): vscode.Disposable {
    return vscode.commands.registerCommand('qonqrete.createTasq', executeCreateTasq);
}
