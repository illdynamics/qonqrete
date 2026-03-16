/**
 * QonQrete CLI Runner
 * Handles execution of qonqrete.sh commands
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
export interface QonQreteRunConfig {
    sensitivity: number;
    cycles: number;
    mode: string;
    autonomous: boolean;
    qonstructionName?: string;
    useSqrapyard: boolean;
    containerEngine: 'auto' | 'docker' | 'podman' | 'msb';
    enableTui: boolean;
    enableWonqrete?: boolean;
}
export interface SanitizeResult {
    original: string;
    sanitized: string;
    wasModified: boolean;
}
export type RunState = 'idle' | 'running' | 'completed' | 'failed' | 'timeout';
export interface RunStatus {
    state: RunState;
    exitCode?: number;
    startTime?: Date;
    endTime?: Date;
    command?: string;
    error?: string;
}
export interface ShellInfo {
    shellPath: string;
    isWindows: boolean;
    hasBash: boolean;
    shellType: 'bash' | 'gitbash' | 'wsl' | 'msys2' | 'env' | 'none';
    verified: boolean;
    verificationError?: string;
}
export type RunStateChangeCallback = (status: RunStatus) => void;
export declare class QonQreteRunner {
    private terminal;
    private readonly terminalName;
    private outputChannel;
    private runStatus;
    private stateChangeCallbacks;
    private pathCache;
    private shellInfo;
    private terminalCloseListener;
    private markerWatcher;
    private markerPollInterval;
    private currentMarkerPath;
    private timeoutHandle;
    private verificationPromise;
    constructor();
    /**
     * Detect available shell environment.
     * Now also checks environment variables as fallback.
     */
    private detectShell;
    /**
     * Verify the detected shell actually works.
     * Returns a promise that resolves to verification result.
     * Caches the promise during verification, but clears on failure to allow retry.
     */
    verifyShell(): Promise<boolean>;
    /**
     * Force re-verification of the shell.
     * Use when verification may have failed due to transient issues.
     */
    reverifyShell(): Promise<boolean>;
    private doVerifyShell;
    /**
     * Wait for shell verification to complete.
     * Use this before running commands to ensure clean contract.
     */
    waitForVerification(): Promise<boolean>;
    /**
     * Check if the extension can run QonQrete commands.
     *
     * CLEAN CONTRACT:
     * - canRun: false if no bash OR not verified yet
     * - canRun: true only when bash is found AND verified
     */
    canExecute(): {
        canRun: boolean;
        reason?: string;
        verifying?: boolean;
    };
    /**
     * Clean up orphaned backup files from previous interrupted runs.
     * Call this on extension activation.
     */
    cleanupOrphanedBackups(): Promise<void>;
    onRunStateChange(callback: RunStateChangeCallback): vscode.Disposable;
    getRunStatus(): RunStatus;
    private updateRunStatus;
    sanitizeQonstructionName(name: string): SanitizeResult;
    private escapeShellArg;
    private toUnixPath;
    getQonQretePath(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined>;
    private findQonQreteInFolder;
    getWorkspaceFolderForFile(filePath: string): vscode.WorkspaceFolder | undefined;
    getQonQreteWorkingDir(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined>;
    hasTasqFile(preferredFolder?: vscode.WorkspaceFolder): Promise<boolean>;
    getTasqPath(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined>;
    isInitialized(preferredFolder?: vscode.WorkspaceFolder): Promise<{
        hasDockerfile: boolean;
        hasImage: boolean;
        engine: string | null;
    }>;
    private checkImageExists;
    private runCommand;
    private getOrCreateTerminal;
    private createMarkerPath;
    /**
     * Watch for marker file with both fs.watch AND polling fallback.
     */
    private watchMarkerFile;
    private readMarkerAndComplete;
    private stopMarkerWatch;
    private buildRunArgs;
    /**
     * Execute in terminal with marker-based completion tracking.
     * Requires shell to be verified first.
     */
    private executeInTerminal;
    init(preferredFolder?: vscode.WorkspaceFolder): Promise<void>;
    run(config: QonQreteRunConfig, preferredFolder?: vscode.WorkspaceFolder): Promise<void>;
    runWithFile(filePath: string, config: QonQreteRunConfig, preferredFolder?: vscode.WorkspaceFolder): Promise<void>;
    runSpecificTasq(tasqFilePath: string, config: QonQreteRunConfig): Promise<void>;
    isValidQageName(name: string): boolean;
    getAvailableQages(preferredFolder?: vscode.WorkspaceFolder): Promise<string[]>;
    private parseQageTimestamp;
    getQageDetails(qageName: string, preferredFolder?: vscode.WorkspaceFolder): Promise<{
        path: string;
        timestamp: Date | null;
        artifacts: {
            qodeyard: string[];
            exeq: string[];
            reqap: string[];
            briqs: string[];
            bloqs: string[];
        };
        configFiles: string[];
    } | undefined>;
    resume(qageName?: string, config?: Partial<QonQreteRunConfig>, preferredFolder?: vscode.WorkspaceFolder): Promise<void>;
    clean(qageName?: string, cleanAll?: boolean, preferredFolder?: vscode.WorkspaceFolder): Promise<void>;
    getVersion(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined>;
    getShellInfo(): ShellInfo;
    clearPathCache(): void;
    showOutput(): void;
    dispose(): void;
}
export declare function getRunner(): QonQreteRunner;
export declare function disposeRunner(): void;
//# sourceMappingURL=qonqreteRunner.d.ts.map