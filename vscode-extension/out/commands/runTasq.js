"use strict";
/**
 * QonQrete task-file run commands
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
exports.executeRunTasq = executeRunTasq;
exports.executeRunAsQonqreteTasq = executeRunAsQonqreteTasq;
exports.registerRunTasqCommands = registerRunTasqCommands;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const qonqreteRunner_1 = require("../cli/qonqreteRunner");
const configWizard_1 = require("../ui/configWizard");
const aiConfig_1 = require("./aiConfig");
/**
 * Save the document if it's dirty
 */
async function saveDocumentIfNeeded(uri) {
    const document = vscode.workspace.textDocuments.find(doc => doc.uri.toString() === uri.toString());
    if (document && document.isDirty) {
        const saved = await document.save();
        if (!saved) {
            const choice = await vscode.window.showWarningMessage('Failed to save the document. Run anyway with the last saved version?', 'Run Anyway', 'Cancel');
            return choice === 'Run Anyway';
        }
    }
    return true;
}
/**
 * Check if runner can execute, waiting for verification if in progress
 */
async function checkCanExecute() {
    const runner = (0, qonqreteRunner_1.getRunner)();
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
            vscode.window.showErrorMessage(canExec.reason || 'Shell verification failed');
            return false;
        }
        return true;
    }
    if (!canExec.canRun) {
        const result = await vscode.window.showErrorMessage(canExec.reason || 'Cannot run QonQrete', 'Install Git Bash', 'Cancel');
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
async function processQonstructionName(name) {
    if (!name)
        return undefined;
    const runner = (0, qonqreteRunner_1.getRunner)();
    const result = runner.sanitizeQonstructionName(name);
    if (result.wasModified) {
        const proceed = await vscode.window.showWarningMessage(`Qonstruction name sanitized:\n"${result.original}" → "${result.sanitized}"\n\nOnly alphanumeric characters, underscores, and hyphens are allowed.`, 'Use Sanitized Name', 'Cancel');
        if (proceed !== 'Use Sanitized Name') {
            return undefined;
        }
    }
    return result.sanitized;
}
/**
 * Execute the run tasq command
 */
async function executeRunTasq(fileUri) {
    // Check execution capability first
    if (!await checkCanExecute()) {
        return;
    }
    const runner = (0, qonqreteRunner_1.getRunner)();
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
        const result = await vscode.window.showWarningMessage('QonQrete runtime not found in this workspace.', 'Deploy to Workspace', 'Configure Path', 'Cancel');
        if (result === 'Deploy to Workspace') {
            await vscode.commands.executeCommand('qonqrete.deployToWorkspace');
        }
        else if (result === 'Configure Path') {
            await vscode.commands.executeCommand('workbench.action.openSettings', 'qonqrete.qonqretePath');
        }
        return;
    }
    // Check if a default task file exists (workspace root or internal compatibility copy)
    const hasTasq = await runner.hasTasqFile();
    if (!hasTasq) {
        const result = await vscode.window.showWarningMessage('No default task file found. Create a starter task file to define your build task.', 'Create Task File', 'Cancel');
        if (result === 'Create Task File') {
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
    // Auto-init if image is missing
    const initStatus = await runner.isInitialized();
    if (!initStatus.hasImage) {
        const initChoice = await vscode.window.showInformationMessage('Container image not built yet. Build it now? (This may take a few minutes)', 'Build & Run', 'Cancel');
        if (initChoice !== 'Build & Run')
            return;
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'QonQrete: Building container image...',
            cancellable: false,
        }, async () => {
            await runner.init();
        });
        vscode.window.showInformationMessage('Container image building in terminal. Run Tasq again when init completes.', 'Show Terminal').then(r => { if (r)
            vscode.commands.executeCommand('workbench.action.terminal.focus'); });
        return;
    }
    // Check for missing API keys
    const workingDir = await runner.getQonQreteWorkingDir();
    if (workingDir) {
        const configYaml = path.join(workingDir, 'worqspace', 'config.yaml');
        const keysOk = await (0, aiConfig_1.promptForMissingApiKeys)(configYaml);
        if (!keysOk)
            return;
    }
    // Show configuration wizard
    const config = await showConfigurationDialog();
    if (!config) {
        return;
    }
    // Ask for qonstruction name with sanitization feedback
    const rawName = await (0, configWizard_1.showQonstructionNameDialog)();
    if (rawName !== undefined) {
        const sanitizedName = await processQonstructionName(rawName);
        if (rawName && !sanitizedName) {
            return; // User cancelled after seeing sanitization
        }
        config.qonstructionName = sanitizedName;
    }
    try {
        await runner.run(config);
        vscode.window.showInformationMessage('QonQrete run started. Check the terminal for output.', 'Show Terminal').then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    }
    catch (error) {
        vscode.window.showErrorMessage(`Failed to run QonQrete: ${error instanceof Error ? error.message : String(error)}`);
    }
}
/**
 * Execute run on a specific task markdown file
 */
async function executeRunSpecificTasq(fileUri) {
    const runner = (0, qonqreteRunner_1.getRunner)();
    const filePath = fileUri.fsPath;
    // Show configuration wizard
    const config = await showConfigurationDialog();
    if (!config) {
        return;
    }
    const rawName = await (0, configWizard_1.showQonstructionNameDialog)();
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
        vscode.window.showInformationMessage(parentName === 'worqspace'
            ? 'Running QonQrete from selected workspace.'
            : 'Running QonQrete with the selected task file.', 'Show Terminal').then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    }
    catch (error) {
        vscode.window.showErrorMessage(`Failed to run: ${error instanceof Error ? error.message : String(error)}`);
    }
}
/**
 * Execute run as a QonQrete task file (for non-default markdown files)
 */
async function executeRunAsQonqreteTasq(fileUri) {
    // Check execution capability first
    if (!await checkCanExecute()) {
        return;
    }
    const runner = (0, qonqreteRunner_1.getRunner)();
    // Determine the file to use
    let filePath;
    let fileUriToSave;
    if (fileUri) {
        filePath = fileUri.fsPath;
        fileUriToSave = fileUri;
    }
    else {
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
    const result = await vscode.window.showInformationMessage(`Use "${fileName}" as the task file for this QonQrete run?`, { modal: true }, 'Yes, Run', 'Cancel');
    if (result !== 'Yes, Run') {
        return;
    }
    // Check if qonqrete.sh exists — offer deploy if not
    const folder = runner.getWorkspaceFolderForFile(filePath);
    const scriptPath = await runner.getQonQretePath(folder);
    if (!scriptPath) {
        const deployChoice = await vscode.window.showWarningMessage('QonQrete runtime not found in this workspace.', 'Deploy to Workspace', 'Cancel');
        if (deployChoice === 'Deploy to Workspace') {
            await vscode.commands.executeCommand('qonqrete.deployToWorkspace');
        }
        return;
    }
    // Auto-init if image is missing
    const initStatus = await runner.isInitialized(folder);
    if (!initStatus.hasImage) {
        const initChoice = await vscode.window.showInformationMessage('Container image not built yet. Build it now? (This may take a few minutes)', 'Build & Run', 'Cancel');
        if (initChoice !== 'Build & Run')
            return;
        await runner.init(folder);
        vscode.window.showInformationMessage('Container image building in terminal. Run again when init completes.', 'Show Terminal').then(r => { if (r)
            vscode.commands.executeCommand('workbench.action.terminal.focus'); });
        return;
    }
    // Check for missing API keys
    const runAsWorkingDir = await runner.getQonQreteWorkingDir(folder);
    if (runAsWorkingDir) {
        const runAsConfigYaml = path.join(runAsWorkingDir, 'worqspace', 'config.yaml');
        const runAsKeysOk = await (0, aiConfig_1.promptForMissingApiKeys)(runAsConfigYaml);
        if (!runAsKeysOk)
            return;
    }
    // Show configuration wizard
    const config = await showConfigurationDialog();
    if (!config) {
        return;
    }
    const rawName = await (0, configWizard_1.showQonstructionNameDialog)();
    if (rawName !== undefined) {
        const sanitizedName = await processQonstructionName(rawName);
        if (rawName && !sanitizedName) {
            return;
        }
        config.qonstructionName = sanitizedName;
    }
    try {
        await runner.runWithFile(filePath, config, folder);
        vscode.window.showInformationMessage(`Running QonQrete with "${fileName}" as the task file.`, 'Show Terminal').then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    }
    catch (error) {
        vscode.window.showErrorMessage(`Failed to run: ${error instanceof Error ? error.message : String(error)}`);
    }
}
/**
 * Show the configuration dialog
 */
async function showConfigurationDialog() {
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
            return await (0, configWizard_1.showQuickConfigWizard)();
        case 'full':
            return await (0, configWizard_1.showFullConfigWizard)();
        case 'default':
            return getDefaultConfig();
        default:
            return undefined;
    }
}
/**
 * Get default config from VS Code settings
 */
function getDefaultConfig() {
    const vsConfig = vscode.workspace.getConfiguration('qonqrete');
    return {
        sensitivity: vsConfig.get('defaultSensitivity', 1),
        autoSensitivity: vsConfig.get('defaultAutoBriqSensitivity', false),
        cycles: vsConfig.get('defaultCycles', 1),
        mode: vsConfig.get('defaultMode', 'program'),
        autonomous: vsConfig.get('defaultAutonomous', true),
        noSync: vsConfig.get('noSync', false),
        useSqrapyard: vsConfig.get('useSqrapyard', false),
        containerEngine: vsConfig.get('containerEngine', 'auto'),
    };
}
/**
 * Register the run tasq commands
 */
function registerRunTasqCommands(context) {
    return [
        vscode.commands.registerCommand('qonqrete.runTasq', executeRunTasq),
        vscode.commands.registerCommand('qonqrete.runAsQonqreteTasq', executeRunAsQonqreteTasq),
        vscode.commands.registerCommand('qonqrete.openConfigDialog', async () => {
            if (!await checkCanExecute()) {
                return;
            }
            const runner = (0, qonqreteRunner_1.getRunner)();
            // Check for a default task file before showing config dialog
            const hasTasq = await runner.hasTasqFile();
            if (!hasTasq) {
                const result = await vscode.window.showWarningMessage('No default task file found. Create one at the workspace root or run a markdown file directly as the task input.', 'Create Task File', 'Cancel');
                if (result === 'Create Task File') {
                    const tasqPath = await runner.getTasqPath();
                    if (tasqPath) {
                        const uri = vscode.Uri.file(tasqPath);
                        await vscode.workspace.fs.writeFile(uri, Buffer.from('# Task\n\nDescribe your task here.\n'));
                        await vscode.window.showTextDocument(uri);
                    }
                }
                return;
            }
            const config = await (0, configWizard_1.showFullConfigWizard)();
            if (!config) {
                return;
            }
            // Consistent qonstruction name handling (same as other run commands)
            const rawName = await (0, configWizard_1.showQonstructionNameDialog)();
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
                vscode.window.showInformationMessage('Running QonQrete with full configuration.', 'Show Terminal').then(result => {
                    if (result === 'Show Terminal') {
                        vscode.commands.executeCommand('workbench.action.terminal.focus');
                    }
                });
            }
            catch (error) {
                vscode.window.showErrorMessage(`Failed to run: ${error instanceof Error ? error.message : String(error)}`);
            }
        }),
    ];
}
//# sourceMappingURL=runTasq.js.map