/**
 * QonQrete Run Tasq Commands
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
/**
 * Execute the run tasq command
 */
export declare function executeRunTasq(fileUri?: vscode.Uri): Promise<void>;
/**
 * Execute run as QonQrete tasq (for non-tasq.md files)
 */
export declare function executeRunAsQonqreteTasq(fileUri?: vscode.Uri): Promise<void>;
/**
 * Register the run tasq commands
 */
export declare function registerRunTasqCommands(context: vscode.ExtensionContext): vscode.Disposable[];
//# sourceMappingURL=runTasq.d.ts.map