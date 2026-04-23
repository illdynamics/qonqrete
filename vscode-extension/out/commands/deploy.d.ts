/**
 * QonQrete Deploy to Workspace Command
 * Downloads and extracts the QonQrete runtime into <workspace>/.qonqrete/
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
/**
 * Execute the deploy to workspace command
 */
export declare function executeDeploy(): Promise<void>;
/**
 * Register the deploy command and capture extension context for version resolution
 */
export declare function registerDeployCommand(context: vscode.ExtensionContext): vscode.Disposable;
//# sourceMappingURL=deploy.d.ts.map