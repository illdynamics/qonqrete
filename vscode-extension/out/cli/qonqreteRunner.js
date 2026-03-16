"use strict";
/**
 * QonQrete CLI Runner
 * Handles execution of qonqrete.sh commands
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
exports.QonQreteRunner = void 0;
exports.getRunner = getRunner;
exports.disposeRunner = disposeRunner;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const child_process_1 = require("child_process");
class QonQreteRunner {
    terminal;
    terminalName = 'QonQrete Engine';
    outputChannel;
    runStatus = { state: 'idle' };
    stateChangeCallbacks = [];
    pathCache = new Map();
    shellInfo;
    terminalCloseListener;
    markerWatcher;
    markerPollInterval;
    currentMarkerPath;
    timeoutHandle;
    verificationPromise;
    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('QonQrete');
        this.shellInfo = this.detectShell();
        this.outputChannel.appendLine(`[QonQrete] Shell detected: ${this.shellInfo.shellType} at ${this.shellInfo.shellPath}`);
    }
    /**
     * Detect available shell environment.
     * Now also checks environment variables as fallback.
     */
    detectShell() {
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
        const bashPaths = [
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
    async verifyShell() {
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
    async reverifyShell() {
        this.shellInfo.verified = false;
        this.shellInfo.verificationError = undefined;
        this.verificationPromise = undefined;
        return this.verifyShell();
    }
    async doVerifyShell() {
        try {
            const result = await this.runCommand(this.shellInfo.shellPath, ['--version']);
            if (result.exitCode === 0 && result.stdout.toLowerCase().includes('bash')) {
                this.shellInfo.verified = true;
                this.shellInfo.verificationError = undefined;
                this.outputChannel.appendLine(`[QonQrete] Shell verified: ${result.stdout.split('\n')[0]}`);
                return true;
            }
            else {
                this.shellInfo.verified = false;
                this.shellInfo.verificationError = `Unexpected output: ${result.stdout.substring(0, 100)}`;
                this.outputChannel.appendLine(`[QonQrete] Shell verification failed: unexpected output`);
                return false;
            }
        }
        catch (err) {
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
    async waitForVerification() {
        return this.verifyShell();
    }
    /**
     * Check if the extension can run QonQrete commands.
     *
     * CLEAN CONTRACT:
     * - canRun: false if no bash OR not verified yet
     * - canRun: true only when bash is found AND verified
     */
    canExecute() {
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
    async cleanupOrphanedBackups() {
        const workingDir = await this.getQonQreteWorkingDir();
        if (!workingDir)
            return;
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
            }
            catch (err) {
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
        }
        catch {
            // Ignore errors cleaning markers
        }
    }
    onRunStateChange(callback) {
        this.stateChangeCallbacks.push(callback);
        return new vscode.Disposable(() => {
            const index = this.stateChangeCallbacks.indexOf(callback);
            if (index >= 0) {
                this.stateChangeCallbacks.splice(index, 1);
            }
        });
    }
    getRunStatus() {
        return { ...this.runStatus };
    }
    updateRunStatus(status) {
        this.runStatus = { ...this.runStatus, ...status };
        this.stateChangeCallbacks.forEach(cb => cb(this.getRunStatus()));
    }
    sanitizeQonstructionName(name) {
        const original = name;
        const sanitized = name.replace(/[^a-zA-Z0-9_\-]/g, '_').substring(0, 64);
        return {
            original,
            sanitized,
            wasModified: original !== sanitized,
        };
    }
    escapeShellArg(arg) {
        if (!arg)
            return '""';
        if (/^[a-zA-Z0-9_\-./]+$/.test(arg)) {
            return arg;
        }
        return `'${arg.replace(/'/g, "'\\''")}'`;
    }
    toUnixPath(filePath) {
        if (!this.shellInfo.isWindows) {
            return filePath;
        }
        return filePath
            .replace(/\\/g, '/')
            .replace(/^([A-Za-z]):/, (_, drive) => `/${drive.toLowerCase()}`);
    }
    async getQonQretePath(preferredFolder) {
        const config = vscode.workspace.getConfiguration('qonqrete');
        const customPath = config.get('qonqretePath');
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
    async findQonQreteInFolder(folderPath) {
        const possiblePaths = [
            path.join(folderPath, 'qonqrete.sh'),
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
            if (parentDir === currentDir)
                break;
            currentDir = parentDir;
        }
        return undefined;
    }
    getWorkspaceFolderForFile(filePath) {
        return vscode.workspace.getWorkspaceFolder(vscode.Uri.file(filePath));
    }
    async getQonQreteWorkingDir(preferredFolder) {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        return scriptPath ? path.dirname(scriptPath) : undefined;
    }
    async hasTasqFile(preferredFolder) {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir)
            return false;
        return fs.existsSync(path.join(workingDir, 'worqspace', 'tasq.md'));
    }
    async getTasqPath(preferredFolder) {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        return workingDir ? path.join(workingDir, 'worqspace', 'tasq.md') : undefined;
    }
    async isInitialized(preferredFolder) {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            return { hasDockerfile: false, hasImage: false, engine: null };
        }
        const workingDir = path.dirname(scriptPath);
        const hasDockerfile = fs.existsSync(path.join(workingDir, 'Dockerfile'));
        if (!hasDockerfile) {
            return { hasDockerfile: false, hasImage: false, engine: null };
        }
        const imageCheck = await this.checkImageExists('qonqrete-qage');
        return { hasDockerfile: true, ...imageCheck };
    }
    async checkImageExists(imageName) {
        const engines = ['docker', 'podman'];
        for (const engine of engines) {
            try {
                const result = await this.runCommand(engine, ['image', 'inspect', imageName]);
                if (result.exitCode === 0) {
                    return { hasImage: true, engine };
                }
            }
            catch {
                // Engine not available
            }
        }
        return { hasImage: false, engine: null };
    }
    runCommand(command, args) {
        return new Promise((resolve) => {
            const proc = (0, child_process_1.spawn)(command, args, {
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
    getOrCreateTerminal() {
        if (this.terminal) {
            const existingTerminals = vscode.window.terminals;
            if (!existingTerminals.some(t => t.name === this.terminalName)) {
                this.terminal = undefined;
                this.terminalCloseListener?.dispose();
            }
        }
        if (!this.terminal) {
            const terminalOptions = {
                name: this.terminalName,
                iconPath: new vscode.ThemeIcon('beaker'),
            };
            if (this.shellInfo.hasBash) {
                terminalOptions.shellPath = this.shellInfo.shellPath;
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
    createMarkerPath(workingDir) {
        const timestamp = Date.now();
        return path.join(workingDir, 'worqspace', `.qonqrete_run_${timestamp}.marker`);
    }
    /**
     * Watch for marker file with both fs.watch AND polling fallback.
     */
    watchMarkerFile(markerPath, timeout = 3600000) {
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
        }
        catch (err) {
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
    readMarkerAndComplete(markerPath) {
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
                    }
                    catch {
                        // Ignore cleanup errors
                    }
                }
                this.stopMarkerWatch();
            }, 100);
        }
        catch (err) {
            this.outputChannel.appendLine(`[QonQrete] Error reading marker: ${err}`);
            this.stopMarkerWatch();
        }
    }
    stopMarkerWatch() {
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
    buildRunArgs(config) {
        const args = ['run'];
        args.push('--briq-sensitivity', config.sensitivity.toString());
        args.push('--cyqles', config.cycles.toString());
        if (config.mode && config.mode !== 'program') {
            args.push('--mode', config.mode);
        }
        if (config.autonomous) {
            args.push('--auto');
        }
        if (config.qonstructionName) {
            args.push('--qonstruction-name', config.qonstructionName);
        }
        if (config.useSqrapyard) {
            args.push('--sqrapyard');
        }
        if (config.containerEngine !== 'auto') {
            args.push(`--${config.containerEngine}`);
        }
        if (config.enableTui) {
            args.push('--tui');
        }
        if (config.enableWonqrete) {
            args.push('--wonqrete');
        }
        return args;
    }
    /**
     * Execute in terminal with marker-based completion tracking.
     * Requires shell to be verified first.
     */
    async executeInTerminal(workingDir, qonqreteCommand, description) {
        // Ensure shell is verified before execution
        const verified = await this.waitForVerification();
        if (!verified) {
            throw new Error(`Shell verification failed: ${this.shellInfo.verificationError || 'unknown error'}`);
        }
        const markerPath = this.createMarkerPath(workingDir);
        const unixMarkerPath = this.toUnixPath(markerPath);
        const unixWorkingDir = this.toUnixPath(workingDir);
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
        const terminal = this.getOrCreateTerminal();
        terminal.show();
        terminal.sendText(fullCommand);
        this.outputChannel.appendLine(`[QonQrete] ${description}`);
        this.outputChannel.appendLine(`[QonQrete] Directory: ${workingDir}`);
        this.outputChannel.appendLine(`[QonQrete] Command: ${qonqreteCommand}`);
        this.outputChannel.appendLine(`[QonQrete] Marker: ${markerPath}`);
    }
    async init(preferredFolder) {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }
        await this.executeInTerminal(path.dirname(scriptPath), './qonqrete.sh init', 'Building container image');
    }
    async run(config, preferredFolder) {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }
        const args = this.buildRunArgs(config);
        const command = `./qonqrete.sh ${args.join(' ')}`;
        this.outputChannel.appendLine(`[QonQrete] Config: sens=${config.sensitivity}, cycles=${config.cycles}, mode=${config.mode}, auto=${config.autonomous}`);
        await this.executeInTerminal(path.dirname(scriptPath), command, 'Running QonQrete');
    }
    async runWithFile(filePath, config, preferredFolder) {
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
        const worqspaceTasq = path.join(workingDir, 'worqspace', 'tasq.md');
        const backupPath = path.join(workingDir, 'worqspace', '.tasq.md.qonqrete-backup');
        let hadOriginal = false;
        if (fs.existsSync(worqspaceTasq)) {
            fs.copyFileSync(worqspaceTasq, backupPath);
            hadOriginal = true;
            this.outputChannel.appendLine('[QonQrete] Backed up original tasq.md');
        }
        fs.copyFileSync(filePath, worqspaceTasq);
        this.outputChannel.appendLine(`[QonQrete] Copied ${path.basename(filePath)} → worqspace/tasq.md`);
        const markerPath = this.createMarkerPath(workingDir);
        const unixMarkerPath = this.toUnixPath(markerPath);
        const unixWorkingDir = this.toUnixPath(workingDir);
        const unixBackup = this.toUnixPath(backupPath);
        const unixTasq = this.toUnixPath(worqspaceTasq);
        const args = this.buildRunArgs(config);
        const runCommand = `./qonqrete.sh ${args.join(' ')}`;
        const restoreCmd = hadOriginal
            ? `cp ${this.escapeShellArg(unixBackup)} ${this.escapeShellArg(unixTasq)} && rm -f ${this.escapeShellArg(unixBackup)} && echo "[QonQrete] Restored original tasq.md"`
            : `echo "[QonQrete] No original to restore"`;
        const fullCommand = `cd ${this.escapeShellArg(unixWorkingDir)} && ${runCommand}; _qexit=$?; ${restoreCmd}; echo $_qexit > ${this.escapeShellArg(unixMarkerPath)}; echo "[QonQrete exit code: $_qexit]"`;
        this.updateRunStatus({
            state: 'running',
            startTime: new Date(),
            command: runCommand,
        });
        this.watchMarkerFile(markerPath);
        const terminal = this.getOrCreateTerminal();
        terminal.show();
        terminal.sendText(fullCommand);
        this.outputChannel.appendLine(`[QonQrete] Running with temporary tasq from: ${filePath}`);
    }
    async runSpecificTasq(tasqFilePath, config) {
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
        }
        else {
            const folder = this.getWorkspaceFolderForFile(tasqFilePath);
            return this.runWithFile(tasqFilePath, config, folder);
        }
    }
    isValidQageName(name) {
        return /^qage_\d{8}_\d{6}$/.test(name);
    }
    async getAvailableQages(preferredFolder) {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir)
            return [];
        const worqspacePath = path.join(workingDir, 'worqspace');
        if (!fs.existsSync(worqspacePath))
            return [];
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
        }
        catch {
            return [];
        }
    }
    parseQageTimestamp(qageName) {
        const match = qageName.match(/qage_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
        if (!match)
            return null;
        const [, year, month, day, hour, minute, second] = match;
        return new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(minute), parseInt(second));
    }
    async getQageDetails(qageName, preferredFolder) {
        if (!this.isValidQageName(qageName)) {
            return undefined;
        }
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir)
            return undefined;
        const qagePath = path.join(workingDir, 'worqspace', qageName);
        if (!fs.existsSync(qagePath))
            return undefined;
        const listDir = (subdir) => {
            const fullPath = path.join(qagePath, subdir);
            if (!fs.existsSync(fullPath))
                return [];
            try {
                return fs.readdirSync(fullPath);
            }
            catch {
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
    async resume(qageName, config, preferredFolder) {
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
    async clean(qageName, cleanAll = false, preferredFolder) {
        const scriptPath = await this.getQonQretePath(preferredFolder);
        if (!scriptPath) {
            throw new Error('QonQrete script not found.');
        }
        let command = './qonqrete.sh clean';
        if (cleanAll) {
            command += ' --all';
        }
        else if (qageName) {
            if (!this.isValidQageName(qageName)) {
                throw new Error(`Invalid qage name format: ${qageName}`);
            }
            command += ` --qage ${qageName}`;
        }
        await this.executeInTerminal(path.dirname(scriptPath), command, `Cleaning ${cleanAll ? 'all' : qageName || '(interactive)'}`);
    }
    async getVersion(preferredFolder) {
        const workingDir = await this.getQonQreteWorkingDir(preferredFolder);
        if (!workingDir)
            return undefined;
        const versionPath = path.join(workingDir, 'VERSION');
        try {
            return fs.readFileSync(versionPath, 'utf8').trim();
        }
        catch {
            return undefined;
        }
    }
    getShellInfo() {
        return { ...this.shellInfo };
    }
    clearPathCache() {
        this.pathCache.clear();
    }
    showOutput() {
        this.outputChannel.show();
    }
    dispose() {
        this.stopMarkerWatch();
        this.terminal?.dispose();
        this.terminalCloseListener?.dispose();
        this.outputChannel.dispose();
    }
}
exports.QonQreteRunner = QonQreteRunner;
let runnerInstance;
function getRunner() {
    if (!runnerInstance) {
        runnerInstance = new QonQreteRunner();
    }
    return runnerInstance;
}
function disposeRunner() {
    runnerInstance?.dispose();
    runnerInstance = undefined;
}
//# sourceMappingURL=qonqreteRunner.js.map