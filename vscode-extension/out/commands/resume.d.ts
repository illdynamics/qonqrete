/**
 * QonQrete Resume and Clean Commands
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
/**
 * Execute the resume command
 */
export declare function executeResume(): Promise<void>;
/**
 * Execute the clean Qages command
 */
export declare function executeClean(): Promise<void>;
/**
 * Register the resume and clean commands
 * NOTE: showStatus is registered in extension.ts to avoid duplicate registration
 */
export declare function registerResumeCommands(context: vscode.ExtensionContext): vscode.Disposable[];
//# sourceMappingURL=resume.d.ts.map