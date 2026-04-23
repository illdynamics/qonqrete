/**
 * QonQrete task-file run commands
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
/**
 * Execute the run tasq command
 */
export declare function executeRunTasq(fileUri?: vscode.Uri): Promise<void>;
/**
 * Execute run as a QonQrete task file (for non-default markdown files)
 */
export declare function executeRunAsQonqreteTasq(fileUri?: vscode.Uri): Promise<void>;
/**
 * Register the run tasq commands
 */
export declare function registerRunTasqCommands(context: vscode.ExtensionContext): vscode.Disposable[];
//# sourceMappingURL=runTasq.d.ts.map