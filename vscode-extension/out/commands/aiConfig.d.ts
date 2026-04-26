/**
 * QonQrete AI Configuration Command
 * Set providers, models, and API keys for AI agents
 *
 * SECURITY: API keys stored via ExtensionContext.secrets (OS keychain)
 * Never in settings.json, never in terminal commands, never in logs
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
/**
 * Get env keys required by configured providers
 */
export declare function getRequiredApiKeys(configPath: string): string[];
/**
 * Check which API keys are missing. Respects env > secrets precedence.
 */
export declare function getMissingApiKeys(configPath: string): Promise<string[]>;
/**
 * Prompt user for missing API keys (secure storage)
 */
export declare function promptForMissingApiKeys(configPath: string): Promise<boolean>;
/**
 * Execute the Set AI Configuration command
 */
export declare function executeSetAIConfig(): Promise<void>;
export declare function registerAIConfigCommand(context: vscode.ExtensionContext): vscode.Disposable;
//# sourceMappingURL=aiConfig.d.ts.map