"use strict";
/**
 * QonQrete Create Tasq Command
 * Creates a starter tasq.md at workspace root
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.executeCreateTasq = executeCreateTasq;
exports.registerCreateTasqCommand = registerCreateTasqCommand;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
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
async function executeCreateTasq() {
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
    vscode.window.showInformationMessage('Starter task file created as tasq.md. Edit it and run QonQrete when ready.');
}
/**
 * Register the create tasq command
 */
function registerCreateTasqCommand(context) {
    return vscode.commands.registerCommand('qonqrete.createTasq', executeCreateTasq);
}
//# sourceMappingURL=createTasq.js.map