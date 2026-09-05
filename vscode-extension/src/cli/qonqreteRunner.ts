/**
 * QonQrete v2 CLI runner.
 *
 * The v2 engine is the `qq` Python CLI (installed globally or run via
 * `python -m qq`). This runner locates that binary and executes commands in
 * an integrated terminal or captures short JSON/help output for the UI.
 */
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as cp from 'child_process';
import * as os from 'os';

export interface QqInvocation {
    command: string;
    argsPrefix: string[];
    cwd: string | undefined;
    found: boolean;
}

export interface QonQreteRunOptions {
    taskFile: string;
    destinationDir: string;
    noTui: boolean;
    provider?: string;
    configPath?: string;
}

export interface RunInfo {
    id: string;
    state: string;
    runner: string;
    root: string;
}

let cachedInvocation: QqInvocation | undefined;

function expandHome(p: string): string {
    if (!p) { return p; }
    if (p === '~') { return os.homedir(); }
    if (p.startsWith('~/') || p.startsWith('~\\')) {
        return path.join(os.homedir(), p.slice(2));
    }
    return p;
}

/** Locate the qq binary. Prefers an explicit setting, then PATH, then python. */
export function resolveQqInvocation(): QqInvocation {
    if (cachedInvocation) {
        return cachedInvocation;
    }

    const configured = vscode.workspace.getConfiguration('qonqrete').get<string>('qqPath');
    if (configured) {
        const p = expandHome(configured);
        if (fs.existsSync(p)) {
            cachedInvocation = { command: p, argsPrefix: [], cwd: undefined, found: true };
            return cachedInvocation;
        }
    }

    const qqSrc = process.env.QQ_SRC;
    const candidates: string[] = [];
    if (process.platform === 'win32') {
        candidates.push(path.join(os.homedir(), '.local', 'bin', 'qq'), 'qq');
    } else {
        candidates.push(path.join(os.homedir(), '.local', 'bin', 'qq'), 'qq');
    }

    for (const candidate of candidates) {
        const found = cp.spawnSync(candidate, ['--version'], { shell: true, encoding: 'utf8', timeout: 5000 });
        if (!found.error && found.status !== 127 && found.status !== null) {
            cachedInvocation = { command: candidate, argsPrefix: [], cwd: undefined, found: true };
            return cachedInvocation;
        }
    }

    // Fall back to `python3 -m qq` (or `python`).
    const python = process.platform === 'win32' ? 'python' : 'python3';
    const pythonCheck = cp.spawnSync(python, ['-m', 'qq', '--version'], { encoding: 'utf8', timeout: 8000 });
    if (!pythonCheck.error && pythonCheck.status !== null) {
        cachedInvocation = {
            command: python,
            argsPrefix: ['-m', 'qq'],
            cwd: qqSrc ? path.resolve(qqSrc) : undefined,
            found: true,
        };
        return cachedInvocation;
    }

    cachedInvocation = { command: 'qq', argsPrefix: [], cwd: undefined, found: false };
    return cachedInvocation;
}

export function clearInvocationCache(): void {
    cachedInvocation = undefined;
}

/** Capture stdout from a qq subcommand. */
export async function execCapture(args: string[], cwd?: string): Promise<string> {
    const inv = resolveQqInvocation();
    return new Promise((resolve, reject) => {
        cp.execFile(
            inv.command,
            [...inv.argsPrefix, ...args],
            { cwd: cwd || inv.cwd, encoding: 'utf8', timeout: 30000, maxBuffer: 10 * 1024 * 1024 },
            (error, stdout, stderr) => {
                if (error) {
                    reject(new Error(stderr || stdout || error.message));
                } else {
                    resolve(stdout.trim());
                }
            },
        );
    });
}

function shellQuote(arg: string): string {
    if (!arg) { return "''"; }
    if (/^[a-zA-Z0-9_\-./:=]+$/.test(arg)) { return arg; }
    return `'${arg.replace(/'/g, "'\\''")}'`;
}

function toUnix(p: string): string {
    if (process.platform !== 'win32') { return p; }
    return p.replace(/\\/g, '/');
}

export class QonQreteRunner {
    private outputChannel: vscode.OutputChannel;
    private terminal: vscode.Terminal | undefined;
    private readonly terminalName = 'QonQrete';

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('QonQrete');
    }

    public showOutput(): void {
        this.outputChannel.show();
    }

    public log(line: string): void {
        this.outputChannel.appendLine(`[QonQrete] ${line}`);
    }

    public isAvailable(): boolean {
        return resolveQqInvocation().found;
    }

    /** Build a `qq ...` command line for terminal execution. */
    private buildCommandLine(args: string[]): string {
        const inv = resolveQqInvocation();
        const parts = [shellQuote(inv.command), ...inv.argsPrefix, ...args.map(shellQuote)];
        return parts.join(' ');
    }

    private getOrCreateTerminal(): vscode.Terminal {
        if (this.terminal) {
            const exists = vscode.window.terminals.some((t) => t === this.terminal);
            if (!exists) { this.terminal = undefined; }
        }
        if (!this.terminal) {
            this.terminal = vscode.window.createTerminal({
                name: this.terminalName,
                iconPath: new vscode.ThemeIcon('beaker'),
            });
        }
        return this.terminal;
    }

    public async runInTerminal(args: string[], description: string, env?: Record<string, string>): Promise<void> {
        const inv = resolveQqInvocation();
        if (!inv.found) {
            throw new Error('qq CLI not found. Install QonQrete or set the qonqrete.qqPath setting.');
        }
        const line = this.buildCommandLine(args);
        this.log(description);
        this.log(`$ ${line}`);
        this.getOrCreateTerminal();
        this.terminal!.show();
        this.terminal!.sendText(line);
    }

    /** Run an arbitrary QonQrete task file. */
    public async runTask(options: QonQreteRunOptions): Promise<void> {
        if (!fs.existsSync(options.taskFile)) {
            throw new Error(`Task file not found: ${options.taskFile}`);
        }
        const dest = path.resolve(options.destinationDir || path.dirname(options.taskFile));
        fs.mkdirSync(dest, { recursive: true });

        const args = ['run', toUnix(options.taskFile), toUnix(dest)];
        if (options.noTui) { args.push('--no-tui'); }
        if (options.provider) { args.push('--provider', options.provider); }
        if (options.configPath) { args.push('--config', options.configPath); }

        await this.runInTerminal(args, 'Running QonQrete task');
    }

    public async runDoctor(): Promise<void> {
        await this.runInTerminal(['doctor'], 'Running qq doctor');
    }

    public async runVerify(): Promise<void> {
        await this.runInTerminal(['verify', '--skip-package-steps'], 'Running qq verify');
    }

    public async runCleanup(repoRoot: string): Promise<void> {
        await this.runInTerminal(['cleanup', '--repo-root', toUnix(path.resolve(repoRoot))], 'Running qq cleanup');
    }

    public async runReplay(eventsFile?: string): Promise<void> {
        const file = eventsFile || await this.pickEventsFile();
        if (!file) { return; }
        await this.runInTerminal(['replay', toUnix(file)], 'Running qq replay');
    }

    public async runRuns(): Promise<void> {
        await this.runInTerminal(['runs', 'sessions'], 'Listing QonQrete runs');
    }

    public async runExec(command: string): Promise<void> {
        await this.runInTerminal(['exec', command], 'Running qq exec');
    }

    public async runChat(): Promise<void> {
        await this.runInTerminal(['chat'], 'Starting QonQrete chat');
    }

    public async listRuns(): Promise<RunInfo[]> {
        try {
            const out = await execCapture(['runs', 'sessions', '--json']);
            const parsed = JSON.parse(out);
            const sessions = Array.isArray(parsed.sessions) ? parsed.sessions : [];
            return sessions.map((s: any) => ({
                id: s.run_id || 'unknown',
                state: s.state || 'unknown',
                runner: s.runner || s.source || 'unknown',
                root: s.run_root || '',
            }));
        } catch {
            // Fall back to scanning .qq/runs directories.
            const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (!root) { return []; }
            const runsDir = path.join(root, '.qq', 'runs');
            if (!fs.existsSync(runsDir)) { return []; }
            return fs.readdirSync(runsDir)
                .filter((d) => fs.statSync(path.join(runsDir, d)).isDirectory())
                .sort()
                .reverse()
                .map((d) => ({ id: d, state: 'unknown', runner: 'local', root: path.join(runsDir, d) }));
        }
    }

    private async pickEventsFile(): Promise<string | undefined> {
        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            filters: { 'QonQrete events': ['jsonl'] },
            title: 'Select a QonQrete events.jsonl file',
        });
        return picked?.[0]?.fsPath;
    }

    public async pickTaskFile(): Promise<string | undefined> {
        const active = vscode.window.activeTextEditor?.document;
        if (active && !active.isUntitled && (active.languageId === 'markdown' || active.fileName.endsWith('.md'))) {
            if (active.isDirty) { await active.save(); }
            return active.uri.fsPath;
        }
        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            filters: { 'Markdown task': ['md'], 'All files': ['*'] },
            title: 'Select a task file',
        });
        return picked?.[0]?.fsPath;
    }

    public async pickDestinationDir(defaultDir?: string): Promise<string | undefined> {
        const defaultUri = defaultDir ? vscode.Uri.file(defaultDir) : undefined;
        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            defaultUri,
            title: 'Choose destination directory',
        });
        if (picked && picked.length > 0) {
            return picked[0].fsPath;
        }
        return defaultDir;
    }

    public dispose(): void {
        this.terminal?.dispose();
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
