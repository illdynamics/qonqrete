/**
 * QonQrete CLI Runner
 * Handles execution of qonqrete.sh commands
 * 
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { spawn } from 'child_process';

export interface QonQreteRunConfig {
    sensitivity: number;
    autoSensitivity?: boolean;
    cycles: number;
    mode: string;
    autonomous: boolean;
    noSync: boolean;
    qonstructionName?: string;
    useSqrapyard: boolean;
    containerEngine: 'auto' | 'docker' | 'podman';
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

export class QonQreteRunner {
    private terminal: vscode.Terminal | undefined;
    private readonly terminalName = 'QonQrete Engine';
    private outputChannel: vscode.OutputChannel;
    private runStatus: RunStatus = { state: 'idle' };
    private stateChangeCallbacks: RunStateChangeCallback[] = [];
    private pathCache: Map<string, string | undefined> = new Map();
    private shellInfo: ShellInfo;
    private terminalCloseListener: vscode.Disposable | undefined;
    private markerWatcher: fs.FSWatcher | undefined;
    private markerPollInterval: NodeJS.Timeout | undefined;
    private currentMarkerPath: string | undefined;
    private timeoutHandle: NodeJS.Timeout | undefined;
    private verificationPromise: Promise<boolean> | undefined;

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('QonQrete');
        this.shellInfo = this.detectShell();
        this.outputChannel.appendLine(`[QonQrete] Shell detected: ${this.shellInfo.shellType} at ${this.shellInfo.shellPath}`);
    }

    /**
     * Detect available shell environment.
     * Now also checks environment variables as fallback.
     */
    private detectShell(): ShellInfo {
        const isWindows = process.platform === 'win32';
        
        if (!isWindows) {
            // On Unix, check $SHELL env var first, then fall back to /bin/bash
            const envShell = process.env.SHELL;
            if (envShell && envShell.includes('bash') && fs.existsSync(envShell)) {
                return {
                    shellPath: envShell,
                    isWindows: false,
                    hasBash: true,
                    shellType: 'bash',
                    verified: false,
                };
            }
            if (fs.existsSync('/bin/bash')) {
                return {
                    shellPath: '/bin/bash',
                    isWindows: false,
                    hasBash: true,
                    shellType: 'bash',
                    verified: false,
                };
            }
            return {
                shellPath: '',
                isWindows: false,
                hasBash: false,
                shellType: 'none',
                verified: false,
            };
        }

        // Windows - search for bash shells in known locations
        const bashPaths: { path: string; type: 'gitbash' | 'wsl' | 'msys2' }[] = [
            // Git Bash (most common)
            { path: 'C:\\Program Files\\Git\\bin\\bash.exe', type: 'gitbash' },
            { path: 'C:\\Program Files (x86)\\Git\\bin\\bash.exe', type: 'gitbash' },
            // WSL
            { path: 'C:\\Windows\\System32\\bash.exe', type: 'wsl' },
            // MSYS2
            { path: 'C:\\msys64\\usr\\bin\\bash.exe', type: 'msys2' },
            { path: 'C:\\msys32\\usr\\bin\\bash.exe', type: 'msys2' },
        ];

        // Add paths from environment variables
        if (process.env.PROGRAMFILES) {
            bashPaths.unshift({ 
                path: path.join(process.env.PROGRAMFILES, 'Git', 'bin', 'bash.exe'), 
                type: 'gitbash' 
            });
        }
        if (process.env['PROGRAMFILES(X86)']) {
            bashPaths.unshift({ 
                path: path.join(process.env['PROGRAMFILES(X86)'], 'Git', 'bin', 'bash.exe'), 
                type: 'gitbash' 
            });
        }
        
        // Check GIT_BASH environment variable (custom installs)
        if (process.env.GIT_BASH && fs.existsSync(process.env.GIT_BASH)) {
            return {
                shellPath: process.env.GIT_BASH,
                isWindows: true,
                hasBash: true,
                shellType: 'env',
                verified: false,
            };
        }

        for (const { path: bashPath, type } of bashPaths) {
            if (fs.existsSync(bashPath)) {
                return {
                    shellPath: bashPath,
                    isWindows: true,
                    hasBash: true,
                    shellType: type,
                    verified: false,
                };
            }
        }

        return {
            shellPath: '',
            isWindows: true,
            hasBash: false,
            shellType: 'none',
            verified: false,
        };
    }

    /**
     * Verify the detected shell actually works.
     * Returns a promise that resolves to verification result.
     * Caches the promise during verification, but clears on failure to allow retry.
     */
    public async verifyShell(): Promise<boolean> {
        if (!this.shellInfo.hasBash) {
            this.shellInfo.verified = false;
            this.shellInfo.verificationError = 'No bash shell found';
            return false;
        }

        if (this.shellInfo.verified) {
            return true;
        }

        // If verification is already in progress, return the same promise
        if (this.verificationPromise) {
            return this.verificationPromise;
        }

        this.verificationPromise = this.doVerifyShell();
        const result = await this.verificationPromise;
        
        // Clear promise on failure to allow retry
        if (!result) {
            this.verificationPromise = undefined;
        }
        
        return result;
    }

    /**
     * Force re-verification of the shell.
     * Use when verification may have failed due to transient issues.
     */
    public async reverifyShell(): Promise<boolean> {
        this.shellInfo.verified = false;
        this.shellInfo.verificationError = undefined;
        this.verificationPromise = undefined;
        return this.verifyShell();
    }

    private async doVerifyShell(): Promise<boolean> {
        try {
            const result = await this.runCommand(this.shellInfo.shellPath, ['--version']);
            if (result.exitCode === 0 && result.stdout.toLowerCase().includes('bash')) {
                this.shellInfo.verified = true;
                this.shellInfo.verificationError = undefined;
                this.outputChannel.appendLine(`[QonQrete] Shell verified: ${result.stdout.split('\n')[0]}`);
                return true;
            } else {
                this.shellInfo.verified = false;
                this.shellInfo.verificationError = `Unexpected output: ${result.stdout.substring(0, 100)}`;
                this.outputChannel.appendLine(`[QonQrete] Shell verification failed: unexpected output`);
                return false;
            }
        } catch (err) {
            this.shellInfo.verified = false;
            this.shellInfo.verificationError = `Execution failed: ${err}`;
            this.outputChannel.appendLine(`[QonQrete] Shell verification failed: ${err}`);
            return false;
        }
    }

    /**
     * Wait for shell verification to complete.
     * Use this before running commands to ensure clean contract.
     */
    public async waitForVerification(): Promise<boolean> {
        return this.verifyShell();
    }

    /**
     * Check if the extension can run QonQrete commands.
     * 
     * CLEAN CONTRACT:
     * - canRun: false if no bash OR not verified yet
     * - canRun: true only when bash is found AND verified
     */
    public canExecute(): { canRun: boolean; reason?: string; verifying?: boolean } {
        if (!this.shellInfo.hasBash) {
            return {
                canRun: false,
                reason: 'QonQrete requires a bash shell. On Windows, please install Git Bash or use WSL.',
            };
        }
        
        if (!this.shellInfo.verified) {
            return {
                canRun: false,
                verifying: true,
                reason: 'Shell verification in progress...',
            };
        }
        
        return { canRun: true };
    }

    /**
     * Clean up orphaned backup files from previous interrupted runs.
     * Call this on extension activation.
     */
    public async cleanupOrphanedBackups(): Promise<void> {
        const workingDir = await this.getQonQreteWorkingDir();
        if (!workingDir) return;

        const worqspacePath = path.join(workingDir, 'worqspace');
        const backupPath = path.join(worqspacePath, '.tasq.md.qonqrete-backup');
        const tasqPath = path.join(worqspacePath, 'tasq.md');

        if (fs.existsSync(backupPath)) {
            this.outputChannel.appendLine('[QonQrete] Found orphaned backup file from previous session');
            
            try {
                // Check if tasq.md exists and differs from backup
                if (fs.existsSync(tasqPath)) {
                    const backupContent = fs.readFileSync(backupPath, 'utf8');
                    const currentContent = fs.readFileSync(tasqPath, 'utf8');
                    
                    if (backupContent !== currentContent) {
                        // Restore the backup
                        fs.copyFileSync(backupPath, tasqPath);
                        this.outputChannel.appendLine('[QonQrete] Restored original tasq.md from backup');
                    }
                }
                
                // Remove the backup file
                fs.unlinkSync(backupPath);
                this.outputChannel.appendLine('[QonQrete] Cleaned up backup file');
            } catch (err) {
                this.outputChannel.appendLine(`[QonQrete] Warning: Could not clean up backup: ${err}`);
            }
        }

        // Also clean up any stale marker files
        try {
            const files = fs.readdirSync(worqspacePath);
            for (const file of files) {
                if (file.startsWith('.qonqrete_run_') && file.endsWith('.marker')) {
                    const markerPath = path.join(worqspacePath, file);
                    fs.unlinkSync(markerPath);
                    this.outputChannel.appendLine(`[QonQrete] Cleaned up stale marker: ${file}`);
                }
            }
        } catch {
            // Ignore errors cleaning markers
        }
    }

    public onRunStateChange(callback: RunStateChangeCallback): vscode.Disposable {
        this.stateChangeCallbacks.push(callback);
        return new vscode.Disposable(() => {
            const index = this.stateChangeCallbacks.indexOf(callback);
            if (index >= 0) {
                this.stateChangeCallbacks.splice(index, 1);
            }
        });
    }

    public getRunStatus(): RunStatus {
        return { ...this.runStatus };
    }

    private updateRunStatus(status: Partial<RunStatus>): void {
        this.runStatus = { ...this.runStatus, ...status };
        this.stateChangeCallbacks.forEach(cb => cb(this.getRunStatus()));
    }

    public sanitizeQonstructionName(name: string): SanitizeResult {
        const original = name;
        const sanitized = name.replace(/[^a-zA-Z0-9_\-]/g, '_').substring(0, 64);
        return {
            original,
            sanitized,
            wasModified: original !== sanitized,
        };
    }

    private escapeShellArg(arg: string): string {
        if (!arg) return '""';
        if (/^[a-zA-Z0-9_\-./]+$/.test(arg)) {
            return arg;
        }
        return `'${arg.replace(/'/g, "'\\''")}'`;
    }

    private toUnixPath(filePath: string): string {
        if (!this.shellInfo.isWindows) {
            return filePath;
        }
        return filePath
            .replace(/\\/g, '/')
            .replace(/^([A-Za-z]):/, (_, drive) => `/${drive.toLowerCase()}`);
    }

    /**
     * Build a SAFE environment map for terminal injection.
     * Uses secure secret storage — never exposes keys in commands/logs.
     * Returns a promise since secret retrieval is async.
     */
    public async buildSecureEnvMap(): Promise<Record<string, string>> {
        const { buildSecureEnvMap } = require('../secrets');
        return await buildSecureEnvMap();
    }

    public async getQonQretePath(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined> {
        const config = vscode.workspace.getConfiguration('qonqrete');
        const customPath = config.get<string>('qonqretePath');

        if (customPath && fs.existsSync(customPath)) {
            return customPath;
        }

        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            return undefined;
        }

        const foldersToCheck = preferredFolder 
            ? [preferredFolder, ...workspaceFolders.filter(f => f !== preferredFolder)]
            : workspaceFolders;

        for (const folder of foldersToCheck) {
            const cachedPath = this.pathCache.get(folder.uri.fsPath);
            if (cachedPath !== undefined) {
                if (cachedPath === '' || !fs.existsSync(cachedPath)) {
                    continue;
                }
                return cachedPath;
            }

            const foundPath = await this.findQonQreteInFolder(folder.uri.fsPath);
            this.pathCache.set(folder.uri.fsPath, foundPath || '');
            if (foundPath) {
                return foundPath;
            }
        }

        return undefined;
    }

    private async findQonQreteInFolder(folderPath: string): Promise<string | undefined> {
        const possiblePaths = [
            // NEW: .qonqrete workspace-local deployment (preferred)
            path.join(folderPath, '.qonqrete', 'qonqrete.sh'),
            // Legacy: root-level
            path.join(folderPath, 'qonqrete.sh'),
            // Legacy: subdirectory
            path.join(folderPath, 'qonqrete', 'qonqrete.sh'),
        ];

        for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
                return path.resolve(p);
            }
        }

        let currentDir = folderPath;
        for (let i = 0; i < 3; i++) {
            const checkPath = path.join(currentDir, 'qonqrete.sh');
            if (fs.existsSync(checkPath)) {
                return checkPath;
            }
            const parentDir = path.dirname(currentDir);
            if (parentDir === currentDir) break;
            currentDir = parentDir;
        }

        return undefined;
    }

    public getWorkspaceFolderForFile(filePath: string): vscode.WorkspaceFolder | undefined {
        return vscode.workspace.getWorkspaceFolder(vscode.Uri.file(filePath));
    }

    public async getQonQreteWorkingDir(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined> {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        return scriptPath ? path.dirname(scriptPath) : undefined;
    }

    public async hasTasqFile(preferredFolder?: vscode.WorkspaceFolder): Promise<boolean> {
        // Check workspace root first (new canonical location)
        const rootTasq = await this.getRootTasqPath(preferredFolder);
        if (rootTasq && fs.existsSync(rootTasq)) return true;
        // Fallback: internal worqspace tasq
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir) return false;
        return fs.existsSync(path.join(workingDir, 'worqspace', 'tasq.md'));
    }

    public async getTasqPath(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined> {
        // Prefer workspace root tasq.md
        const rootTasq = await this.getRootTasqPath(preferredFolder);
        if (rootTasq && fs.existsSync(rootTasq)) return rootTasq;
        // Fallback: internal worqspace tasq
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        return workingDir ? path.join(workingDir, 'worqspace', 'tasq.md') : undefined;
    }

    /**
     * Get the workspace-root tasq.md path (new v1.3.0 canonical location)
     */
    public async getRootTasqPath(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined> {
        const wsFolder = preferredFolder || vscode.workspace.workspaceFolders?.[0];
        if (!wsFolder) return undefined;
        return path.join(wsFolder.uri.fsPath, 'tasq.md');
    }

    /**
     * Get the internal worqspace tasq path (.qonqrete/worqspace/tasq.md)
     */
    public async getInternalTasqPath(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined> {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        return workingDir ? path.join(workingDir, 'worqspace', 'tasq.md') : undefined;
    }

    /**
     * Check if .qonqrete runtime is deployed in the workspace
     */
    public async isDeployed(preferredFolder?: vscode.WorkspaceFolder): Promise<boolean> {
        const wsFolder = preferredFolder || vscode.workspace.workspaceFolders?.[0];
        if (!wsFolder) return false;
        return fs.existsSync(path.join(wsFolder.uri.fsPath, '.qonqrete', 'qonqrete.sh'));
    }

    /**
     * Sync workspace-root tasq.md into internal .qonqrete/worqspace/tasq.md before run
     */
    public async syncRootTasqToInternal(preferredFolder?: vscode.WorkspaceFolder): Promise<boolean> {
        const rootTasq = await this.getRootTasqPath(preferredFolder);
        const internalTasq = await this.getInternalTasqPath(preferredFolder);
        if (!rootTasq || !internalTasq) return false;
        if (!fs.existsSync(rootTasq)) return false;
        try {
            const worqspaceDir = path.dirname(internalTasq);
            if (!fs.existsSync(worqspaceDir)) {
                fs.mkdirSync(worqspaceDir, { recursive: true });
            }
            fs.copyFileSync(rootTasq, internalTasq);
            this.outputChannel.appendLine(`[QonQrete] Synced tasq.md → .qonqrete/worqspace/tasq.md`);
            return true;
        } catch (err) {
            this.outputChannel.appendLine(`[QonQrete] Failed to sync tasq: ${err}`);
            return false;
        }
    }

    /**
     * Ensure .qonqrete/ is in .gitignore
     */
    public async ensureGitignore(preferredFolder?: vscode.WorkspaceFolder): Promise<void> {
        const wsFolder = preferredFolder || vscode.workspace.workspaceFolders?.[0];
        if (!wsFolder) return;
        const gitignorePath = path.join(wsFolder.uri.fsPath, '.gitignore');
        const entry = '.qonqrete/';
        try {
            if (fs.existsSync(gitignorePath)) {
                const content = fs.readFileSync(gitignorePath, 'utf8');
                if (!content.split('\n').some(line => line.trim() === entry || line.trim() === '.qonqrete')) {
                    fs.appendFileSync(gitignorePath, `\n# QonQrete runtime\n${entry}\n`);
                    this.outputChannel.appendLine('[QonQrete] Added .qonqrete/ to .gitignore');
                }
            } else {
                fs.writeFileSync(gitignorePath, `# QonQrete runtime\n${entry}\n`);
                this.outputChannel.appendLine('[QonQrete] Created .gitignore with .qonqrete/');
            }
        } catch (err) {
            this.outputChannel.appendLine(`[QonQrete] Warning: Could not update .gitignore: ${err}`);
        }
    }

    public async isInitialized(preferredFolder?: vscode.WorkspaceFolder): Promise<{
        hasDockerfile: boolean;
        hasImage: boolean;
        engine: string | null;
    }> {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            return { hasDockerfile: false, hasImage: false, engine: null };
        }

        const workingDir = path.dirname(scriptPath);
        const hasDockerfile = fs.existsSync(path.join(workingDir, 'Dockerfile'));

        if (!hasDockerfile) {
            return { hasDockerfile: false, hasImage: false, engine: null };
        }

        // Check versioned image first, then the untagged compatibility alias
        const version = await this.getVersion(preferredFolder);
        const imageNames = [
            version ? `qonqrete-qage:${version}` : null,
            'qonqrete-qage:latest',
            'qonqrete-qage',
        ].filter(Boolean) as string[];

        for (const imageName of imageNames) {
            const imageCheck = await this.checkImageExists(imageName);
            if (imageCheck.hasImage) return { hasDockerfile: true, ...imageCheck };
        }
        return { hasDockerfile: true, hasImage: false, engine: null };
    }

    private async checkImageExists(imageName: string): Promise<{ hasImage: boolean; engine: string | null }> {
        const engines = ['docker', 'podman'];
        
        for (const engine of engines) {
            try {
                const result = await this.runCommand(engine, ['image', 'inspect', imageName]);
                if (result.exitCode === 0) {
                    return { hasImage: true, engine };
                }
            } catch {
                // Engine not available
            }
        }

        return { hasImage: false, engine: null };
    }

    private runCommand(command: string, args: string[]): Promise<{ exitCode: number; stdout: string; stderr: string }> {
        return new Promise((resolve) => {
            const proc = spawn(command, args, {
                stdio: ['ignore', 'pipe', 'pipe'],
                shell: process.platform === 'win32',
            });

            let stdout = '';
            let stderr = '';

            proc.stdout?.on('data', (data) => { stdout += data.toString(); });
            proc.stderr?.on('data', (data) => { stderr += data.toString(); });

            proc.on('close', (code) => resolve({ exitCode: code ?? 1, stdout, stderr }));
            proc.on('error', () => resolve({ exitCode: 1, stdout, stderr: 'Command not found' }));
        });
    }

    private getOrCreateTerminal(envMap?: Record<string, string>): vscode.Terminal {
        // If env map provided, always create fresh terminal (env is set at creation time)
        if (envMap && Object.keys(envMap).length > 0) {
            this.terminal?.dispose();
            this.terminal = undefined;
            this.terminalCloseListener?.dispose();
        }

        if (this.terminal) {
            const existingTerminals = vscode.window.terminals;
            if (!existingTerminals.some(t => t.name === this.terminalName)) {
                this.terminal = undefined;
                this.terminalCloseListener?.dispose();
            }
        }

        if (!this.terminal) {
            const terminalOptions: vscode.TerminalOptions = {
                name: this.terminalName,
                iconPath: new vscode.ThemeIcon('beaker'),
            };

            if (this.shellInfo.hasBash) {
                terminalOptions.shellPath = this.shellInfo.shellPath;
            }

            // SECURE: inject API keys via terminal env (never in command text)
            if (envMap && Object.keys(envMap).length > 0) {
                terminalOptions.env = envMap;
                this.outputChannel.appendLine(`[QonQrete] API keys injected via secure terminal env (${Object.keys(envMap).length} keys)`);
            }

            this.terminal = vscode.window.createTerminal(terminalOptions);

            this.terminalCloseListener = vscode.window.onDidCloseTerminal((closedTerminal) => {
                if (closedTerminal === this.terminal) {
                    this.terminal = undefined;
                }
            });
        }

        return this.terminal;
    }

    private createMarkerPath(workingDir: string): string {
        const timestamp = Date.now();
        return path.join(workingDir, 'worqspace', `.qonqrete_run_${timestamp}.marker`);
    }

    /**
     * Watch for marker file with both fs.watch AND polling fallback.
     */
    private watchMarkerFile(markerPath: string, timeout: number = 3600000): void {
        this.stopMarkerWatch();
        this.currentMarkerPath = markerPath;

        const markerDir = path.dirname(markerPath);
        const markerName = path.basename(markerPath);

        // Method 1: fs.watch (may not work on all platforms)
        try {
            this.markerWatcher = fs.watch(markerDir, (eventType, filename) => {
                if (filename === markerName) {
                    this.readMarkerAndComplete(markerPath);
                }
            });
        } catch (err) {
            this.outputChannel.appendLine(`[QonQrete] fs.watch failed, using polling only: ${err}`);
        }

        // Method 2: Polling fallback (more reliable)
        this.markerPollInterval = setInterval(() => {
            if (fs.existsSync(markerPath)) {
                this.readMarkerAndComplete(markerPath);
            }
        }, 1000);

        // Timeout: Set state to 'timeout', not 'completed'
        this.timeoutHandle = setTimeout(() => {
            if (this.runStatus.state === 'running') {
                this.outputChannel.appendLine('[QonQrete] Run timeout - marker file not detected');
                this.updateRunStatus({
                    state: 'timeout',
                    endTime: new Date(),
                    error: 'Marker file not detected within timeout.',
                });
                this.stopMarkerWatch();
            }
        }, timeout);
    }

    private readMarkerAndComplete(markerPath: string): void {
        if (this.runStatus.state !== 'running') {
            return;
        }

        if (this.timeoutHandle) {
            clearTimeout(this.timeoutHandle);
            this.timeoutHandle = undefined;
        }

        try {
            setTimeout(() => {
                if (fs.existsSync(markerPath)) {
                    const content = fs.readFileSync(markerPath, 'utf8').trim();
                    const exitCode = parseInt(content, 10);

                    this.updateRunStatus({
                        state: exitCode === 0 ? 'completed' : 'failed',
                        exitCode: isNaN(exitCode) ? undefined : exitCode,
                        endTime: new Date(),
                    });

                    this.outputChannel.appendLine(`[QonQrete] Run finished with exit code: ${exitCode}`);

                    try {
                        fs.unlinkSync(markerPath);
                    } catch {
                        // Ignore cleanup errors
                    }
                }
                this.stopMarkerWatch();
            }, 100);
        } catch (err) {
            this.outputChannel.appendLine(`[QonQrete] Error reading marker: ${err}`);
            this.stopMarkerWatch();
        }
    }

    private stopMarkerWatch(): void {
        if (this.markerWatcher) {
            this.markerWatcher.close();
            this.markerWatcher = undefined;
        }
        if (this.markerPollInterval) {
            clearInterval(this.markerPollInterval);
            this.markerPollInterval = undefined;
        }
        if (this.timeoutHandle) {
            clearTimeout(this.timeoutHandle);
            this.timeoutHandle = undefined;
        }
        this.currentMarkerPath = undefined;
    }

    private buildRunArgs(config: QonQreteRunConfig): string[] {
        const args: string[] = ['run'];

        if (config.autoSensitivity) {
            args.push('--auto-briq-sensitivity');
        } else {
            args.push('--briq-sensitivity', config.sensitivity.toString());
        }
        args.push('--cyqles', config.cycles.toString());

        if (config.mode && config.mode !== 'program') {
            args.push('--mode', config.mode);
        }

        if (config.autonomous) {
            args.push('--auto');
        }

        if (config.noSync) {
            args.push('--no-sync');
        }

        if (config.qonstructionName) {
            args.push('--qonstruction-name', config.qonstructionName);
        }

        if (config.useSqrapyard) {
            args.push('--seed-repo');
        }

        if (config.containerEngine !== 'auto') {
            args.push(`--${config.containerEngine}`);
        }

        return args;
    }

    private buildRunCommand(config: QonQreteRunConfig, taskFilePath?: string): string {
        const args = this.buildRunArgs(config);
        if (!taskFilePath) {
            return `./qonqrete.sh ${args.join(' ')}`;
        }

        const unixTaskPath = this.toUnixPath(taskFilePath);
        const escapedTaskPath = this.escapeShellArg(unixTaskPath);
        // args[0] is 'run', slice it off then re-add as `run -f <task>`
        const runArgs = args.slice(1);
        return runArgs.length > 0
            ? `./qonqrete.sh run -f ${escapedTaskPath} ${runArgs.join(' ')}`
            : `./qonqrete.sh run -f ${escapedTaskPath}`;
    }

    /**
     * Execute in terminal with marker-based completion tracking.
     * Requires shell to be verified first.
     */
    private async executeInTerminal(
        workingDir: string, 
        qonqreteCommand: string, 
        description: string
    ): Promise<void> {
        // Ensure shell is verified before execution
        const verified = await this.waitForVerification();
        if (!verified) {
            throw new Error(`Shell verification failed: ${this.shellInfo.verificationError || 'unknown error'}`);
        }

        const markerPath = this.createMarkerPath(workingDir);
        const unixMarkerPath = this.toUnixPath(markerPath);
        const unixWorkingDir = this.toUnixPath(workingDir);
        // SECURE: no secrets in command text
        const fullCommand = `cd ${this.escapeShellArg(unixWorkingDir)} && ${qonqreteCommand}; _qexit=$?; echo $_qexit > ${this.escapeShellArg(unixMarkerPath)}; echo "[QonQrete exit code: $_qexit]"`;

        this.updateRunStatus({
            state: 'running',
            startTime: new Date(),
            command: qonqreteCommand,
            exitCode: undefined,
            endTime: undefined,
            error: undefined,
        });

        this.watchMarkerFile(markerPath);

        // Build secure env map and inject via terminal env (never in command text)
        const secureEnv = await this.buildSecureEnvMap();
        const terminal = this.getOrCreateTerminal(secureEnv);
        terminal.show();
        terminal.sendText(fullCommand);

        this.outputChannel.appendLine(`[QonQrete] ${description}`);
        this.outputChannel.appendLine(`[QonQrete] Directory: ${workingDir}`);
        this.outputChannel.appendLine(`[QonQrete] Command: ${qonqreteCommand}`);
        this.outputChannel.appendLine(`[QonQrete] Marker: ${markerPath}`);
    }

    public async init(preferredFolder?: vscode.WorkspaceFolder): Promise<void> {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }

        await this.executeInTerminal(
            path.dirname(scriptPath),
            './qonqrete.sh init',
            'Building container image'
        );
    }

    public async run(config: QonQreteRunConfig, preferredFolder?: vscode.WorkspaceFolder): Promise<void> {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }

        const taskFilePath = await this.getTasqPath(preferredFolder);
        if (!taskFilePath || !fs.existsSync(taskFilePath)) {
            throw new Error('No task file found.');
        }

        const command = this.buildRunCommand(config, taskFilePath);

        this.outputChannel.appendLine(
            `[QonQrete] Config: sens=${config.sensitivity}, cycles=${config.cycles}, mode=${config.mode}, auto=${config.autonomous}, noSync=${config.noSync}`
        );
        this.outputChannel.appendLine(`[QonQrete] Task file: ${taskFilePath}`);
        
        await this.executeInTerminal(path.dirname(scriptPath), command, 'Running QonQrete');
    }

    public async runWithFile(
        filePath: string,
        config: QonQreteRunConfig,
        preferredFolder?: vscode.WorkspaceFolder
    ): Promise<void> {
        // Ensure shell is verified before execution
        const verified = await this.waitForVerification();
        if (!verified) {
            throw new Error(`Shell verification failed: ${this.shellInfo.verificationError || 'unknown error'}`);
        }

        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }

        const workingDir = path.dirname(scriptPath);
        const command = this.buildRunCommand(config, filePath);
        this.outputChannel.appendLine(`[QonQrete] Task file: ${filePath}`);
        await this.executeInTerminal(workingDir, command, 'Running QonQrete task file');
    }

    public async runSpecificTasq(tasqFilePath: string, config: QonQreteRunConfig): Promise<void> {
        const parentDir = path.dirname(tasqFilePath);
        const parentName = path.basename(parentDir);
        
        if (parentName === 'worqspace') {
            const workingDir = path.dirname(parentDir);
            const scriptPath = path.join(workingDir, 'qonqrete.sh');
            
            if (!fs.existsSync(scriptPath)) {
                throw new Error(`qonqrete.sh not found at ${workingDir}.`);
            }

            const args = this.buildRunArgs(config);
            await this.executeInTerminal(workingDir, `./qonqrete.sh ${args.join(' ')}`, `Running from ${workingDir}`);
        } else {
            const folder = this.getWorkspaceFolderForFile(tasqFilePath);
            return this.runWithFile(tasqFilePath, config, folder);
        }
    }

    public isValidQageName(name: string): boolean {
        return /^qage_\d{8}_\d{6}$/.test(name);
    }

    public async getAvailableQages(preferredFolder?: vscode.WorkspaceFolder): Promise<string[]> {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir) return [];

        const worqspacePath = path.join(workingDir, 'worqspace');
        if (!fs.existsSync(worqspacePath)) return [];

        try {
            const entries = fs.readdirSync(worqspacePath, { withFileTypes: true });
            return entries
                .filter(entry => entry.isDirectory() && this.isValidQageName(entry.name))
                .map(entry => ({
                    name: entry.name,
                    timestamp: this.parseQageTimestamp(entry.name),
                }))
                .sort((a, b) => {
                    if (a.timestamp && b.timestamp) {
                        return b.timestamp.getTime() - a.timestamp.getTime();
                    }
                    return b.name.localeCompare(a.name);
                })
                .map(q => q.name);
        } catch {
            return [];
        }
    }

    private parseQageTimestamp(qageName: string): Date | null {
        const match = qageName.match(/qage_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
        if (!match) return null;
        
        const [, year, month, day, hour, minute, second] = match;
        return new Date(
            parseInt(year), parseInt(month) - 1, parseInt(day),
            parseInt(hour), parseInt(minute), parseInt(second)
        );
    }

    public async getQageDetails(qageName: string, preferredFolder?: vscode.WorkspaceFolder): Promise<{
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
    } | undefined> {
        if (!this.isValidQageName(qageName)) {
            return undefined;
        }

        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir) return undefined;

        const qagePath = path.join(workingDir, 'worqspace', qageName);
        if (!fs.existsSync(qagePath)) return undefined;

        const listDir = (subdir: string): string[] => {
            const fullPath = path.join(qagePath, subdir);
            if (!fs.existsSync(fullPath)) return [];
            try {
                return fs.readdirSync(fullPath);
            } catch {
                return [];
            }
        };

        return {
            path: qagePath,
            timestamp: this.parseQageTimestamp(qageName),
            artifacts: {
                qodeyard: listDir('qodeyard'),
                exeq: listDir('exeq.d'),
                reqap: listDir('reqap.d'),
                briqs: listDir('briq.d'),
                bloqs: listDir('bloq.d'),
            },
            configFiles: listDir('.').filter(f => f.endsWith('.yaml') || f.endsWith('.md')),
        };
    }

    public async resume(
        qageName?: string,
        config?: Partial<QonQreteRunConfig>,
        preferredFolder?: vscode.WorkspaceFolder
    ): Promise<void> {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }

        let command = './qonqrete.sh resume';

        if (qageName) {
            if (!this.isValidQageName(qageName)) {
                throw new Error(`Invalid qage name format: ${qageName}`);
            }
            command += ` --qage ${qageName}`;
        }

        if (config?.autonomous) {
            command += ' --auto';
        }
        if (config?.qonstructionName) {
            const sanitized = this.sanitizeQonstructionName(config.qonstructionName);
            command += ` --qonstruction-name ${sanitized.sanitized}`;
        }

        await this.executeInTerminal(path.dirname(scriptPath), command, `Resuming ${qageName || '(interactive)'}`);
    }

    public async clean(
        qageName?: string,
        cleanAll: boolean = false,
        preferredFolder?: vscode.WorkspaceFolder
    ): Promise<void> {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }

        let command = './qonqrete.sh clean';

        if (cleanAll) {
            command += ' --all';
        } else if (qageName) {
            if (!this.isValidQageName(qageName)) {
                throw new Error(`Invalid qage name format: ${qageName}`);
            }
            command += ` --qage ${qageName}`;
        }

        await this.executeInTerminal(path.dirname(scriptPath), command, `Cleaning ${cleanAll ? 'all' : qageName || '(interactive)'}`);
    }

    public async getVersion(preferredFolder?: vscode.WorkspaceFolder): Promise<string | undefined> {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir) return undefined;

        const versionPath = path.join(workingDir, 'VERSION');
        try {
            return fs.readFileSync(versionPath, 'utf8').trim();
        } catch {
            return undefined;
        }
    }

    public getShellInfo(): ShellInfo {
        return { ...this.shellInfo };
    }

    public clearPathCache(): void {
        this.pathCache.clear();
    }

    public showOutput(): void {
        this.outputChannel.show();
    }

    public dispose(): void {
        this.stopMarkerWatch();
        this.terminal?.dispose();
        this.terminalCloseListener?.dispose();
        this.outputChannel.dispose();
    }
}

let runnerInstance: QonQreteRunner | undefined;

export function getRunner(): QonQreteRunner {
    if (!runnerInstance) {
        runnerInstance = new QonQreteRunner();
    }
    return runnerInstance;
}

export function disposeRunner(): void {
    runnerInstance?.dispose();
    runnerInstance = undefined;
}
