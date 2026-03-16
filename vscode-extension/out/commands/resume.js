"use strict";
/**
 * QonQrete Resume and Clean Commands
 *
 * @author WoNQ
 * @version 1.1.9
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
exports.executeResume = executeResume;
exports.executeClean = executeClean;
exports.registerResumeCommands = registerResumeCommands;
const vscode = __importStar(require("vscode"));
const qonqreteRunner_1 = require("../cli/qonqreteRunner");
const configWizard_1 = require("../ui/configWizard");
/**
 * Check if runner can execute, waiting for verification if in progress.
 * Consistent with runTasq.ts behavior.
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
 * Execute the resume command
 */
async function executeResume() {
    // Check execution capability (waits for verification if needed)
    if (!await checkCanExecute()) {
        return;
    }
    const runner = (0, qonqreteRunner_1.getRunner)();
    const scriptPath = await runner.getQonQretePath();
    if (!scriptPath) {
        vscode.window.showErrorMessage('QonQrete script not found.');
        return;
    }
    const qages = await runner.getAvailableQages();
    if (qages.length === 0) {
        vscode.window.showInformationMessage('No Qages found to resume from. Run QonQrete first to create a Qage.');
        return;
    }
    const selectedQage = await (0, configWizard_1.showQageSelectionDialog)(qages);
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
    const qonstructionName = await (0, configWizard_1.showQonstructionNameDialog)();
    // Handle sanitization with user feedback
    let sanitizedName;
    if (qonstructionName) {
        const result = runner.sanitizeQonstructionName(qonstructionName);
        if (result.wasModified) {
            const proceed = await vscode.window.showWarningMessage(`Name sanitized: "${result.original}" → "${result.sanitized}"`, 'Continue', 'Cancel');
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
        vscode.window.showInformationMessage(`Resuming from ${selectedQage}. Check the terminal for output.`, 'Show Terminal').then(result => {
            if (result === 'Show Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.focus');
            }
        });
    }
    catch (error) {
        vscode.window.showErrorMessage(`Failed to resume: ${error instanceof Error ? error.message : String(error)}`);
    }
}
/**
 * Execute the clean Qages command
 */
async function executeClean() {
    // Check execution capability (waits for verification if needed)
    if (!await checkCanExecute()) {
        return;
    }
    const runner = (0, qonqreteRunner_1.getRunner)();
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
    const cleanResult = await (0, configWizard_1.showCleanConfirmDialog)(qages);
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
    }
    catch (error) {
        vscode.window.showErrorMessage(`Failed to clean: ${error instanceof Error ? error.message : String(error)}`);
    }
}
/**
 * Register the resume and clean commands
 * NOTE: showStatus is registered in extension.ts to avoid duplicate registration
 */
function registerResumeCommands(context) {
    return [
        vscode.commands.registerCommand('qonqrete.resumeRun', executeResume),
        vscode.commands.registerCommand('qonqrete.cleanQages', executeClean),
        // showStatus is NOT registered here - it's in extension.ts
    ];
}
//# sourceMappingURL=resume.js.map