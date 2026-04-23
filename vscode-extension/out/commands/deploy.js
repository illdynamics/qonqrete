"use strict";
/**
 * QonQrete Deploy to Workspace Command
 * Downloads and extracts the QonQrete runtime into <workspace>/.qonqrete/
 *
 * @author WoNQ
 * @version VERSION
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
exports.executeDeploy = executeDeploy;
exports.registerDeployCommand = registerDeployCommand;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const https = __importStar(require("https"));
const http = __importStar(require("http"));
const qonqreteRunner_1 = require("../cli/qonqreteRunner");
const GITHUB_RELEASE_BASE = 'https://github.com/illdynamics/qonqrete/releases/download';
/** Cached extension context — set at registration time */
let extensionContext;
/**
 * Resolve runtime version from single source of truth.
 *
 * Priority:
 *   1. <workspace>/.qonqrete/VERSION  (if runtime already deployed)
 *   2. Extension's own package.json version
 *   3. "latest" as ultimate fallback
 */
function getRuntimeVersion(workspaceRoot) {
    // 1. Try deployed VERSION file
    try {
        const versionFile = path.join(workspaceRoot, '.qonqrete', 'VERSION');
        if (fs.existsSync(versionFile)) {
            const v = fs.readFileSync(versionFile, 'utf8').trim().replace(/^v/i, '');
            if (v && /^\d+\.\d+/.test(v)) {
                return v;
            }
        }
    }
    catch { }
    // 2. Extension version from package.json
    try {
        if (extensionContext) {
            const extVersion = extensionContext.extension.packageJSON.version;
            if (extVersion && typeof extVersion === 'string') {
                const v = extVersion.trim().replace(/^v/i, '');
                if (v && /^\d+\.\d+/.test(v)) {
                    return v;
                }
            }
        }
    }
    catch { }
    // 3. Ultimate fallback
    return 'latest';
}
/**
 * Download a file from URL to a local path
 */
function downloadFile(url, destPath) {
    return new Promise((resolve, reject) => {
        const file = fs.createWriteStream(destPath);
        const protocol = url.startsWith('https') ? https : http;
        const request = protocol.get(url, (response) => {
            // Handle redirects
            if (response.statusCode === 301 || response.statusCode === 302) {
                const redirectUrl = response.headers.location;
                if (redirectUrl) {
                    file.close();
                    fs.unlinkSync(destPath);
                    downloadFile(redirectUrl, destPath).then(resolve).catch(reject);
                    return;
                }
            }
            if (response.statusCode !== 200) {
                file.close();
                fs.unlinkSync(destPath);
                reject(new Error(`Download failed: HTTP ${response.statusCode}`));
                return;
            }
            response.pipe(file);
            file.on('finish', () => { file.close(); resolve(); });
        });
        request.on('error', (err) => {
            file.close();
            try {
                fs.unlinkSync(destPath);
            }
            catch { }
            reject(err);
        });
        request.setTimeout(60000, () => {
            request.destroy();
            reject(new Error('Download timeout'));
        });
    });
}
/**
 * Extract a zip file using the system unzip command or Node child_process
 */
async function extractZip(zipPath, destDir) {
    const { execSync } = require('child_process');
    // Try unzip first (available on macOS/Linux), then tar (fallback)
    try {
        execSync(`unzip -o -q "${zipPath}" -d "${destDir}"`, { stdio: 'pipe' });
        return;
    }
    catch { }
    // Try PowerShell on Windows
    try {
        execSync(`powershell -Command "Expand-Archive -Path '${zipPath}' -DestinationPath '${destDir}' -Force"`, { stdio: 'pipe' });
        return;
    }
    catch { }
    throw new Error('Could not extract zip. Please install unzip or use PowerShell.');
}
/**
 * Flatten a single top-level directory from extraction
 * e.g., .qonqrete/qonqrete-vX.Y.Z/qonqrete.sh → .qonqrete/qonqrete.sh
 */
function flattenTopLevel(dirPath) {
    const entries = fs.readdirSync(dirPath);
    // Filter out __MACOSX and similar junk
    const realEntries = entries.filter(e => !e.startsWith('__MACOSX') && !e.startsWith('.'));
    if (realEntries.length === 1) {
        const onlyEntry = path.join(dirPath, realEntries[0]);
        if (fs.statSync(onlyEntry).isDirectory()) {
            // Move contents up one level
            const innerEntries = fs.readdirSync(onlyEntry);
            for (const inner of innerEntries) {
                const src = path.join(onlyEntry, inner);
                const dest = path.join(dirPath, inner);
                fs.renameSync(src, dest);
            }
            // Remove the now-empty directory
            fs.rmdirSync(onlyEntry);
        }
    }
    // Clean up __MACOSX if it exists
    const macosxDir = path.join(dirPath, '__MACOSX');
    if (fs.existsSync(macosxDir)) {
        fs.rmSync(macosxDir, { recursive: true, force: true });
    }
}
/**
 * Execute the deploy to workspace command
 */
async function executeDeploy() {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage('No workspace folder open. Please open a project first.');
        return;
    }
    const wsRoot = workspaceFolders[0].uri.fsPath;
    const qonqreteDir = path.join(wsRoot, '.qonqrete');
    const runner = (0, qonqreteRunner_1.getRunner)();
    // Check if already deployed
    if (fs.existsSync(path.join(qonqreteDir, 'qonqrete.sh'))) {
        const action = await vscode.window.showWarningMessage('QonQrete runtime already deployed in this workspace.', 'Reinstall', 'Repair (keep config)', 'Cancel');
        if (action === 'Cancel' || !action)
            return;
        if (action === 'Reinstall') {
            fs.rmSync(qonqreteDir, { recursive: true, force: true });
        }
        // For Repair, we'll overwrite but keep worqspace data
    }
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'QonQrete: Deploying to Workspace',
        cancellable: false,
    }, async (progress) => {
        try {
            // Resolve version dynamically
            const version = getRuntimeVersion(wsRoot);
            console.log(`[QonQrete] Resolved runtime version for deploy: ${version}`);
            // Step 1: Download
            progress.report({ message: `Downloading runtime v${version}...`, increment: 10 });
            const zipUrl = `${GITHUB_RELEASE_BASE}/v${version}/qonqrete-v${version}.zip`;
            const tmpDir = path.join(wsRoot, '.qonqrete-tmp-' + Date.now());
            fs.mkdirSync(tmpDir, { recursive: true });
            const zipPath = path.join(tmpDir, 'qonqrete.zip');
            try {
                await downloadFile(zipUrl, zipPath);
            }
            catch (downloadErr) {
                // Fallback: try shallow git clone
                progress.report({ message: 'Zip download failed, trying git clone fallback...', increment: 10 });
                try {
                    const { execSync } = require('child_process');
                    execSync(`git clone --depth 1 --branch v${version} https://github.com/illdynamics/qonqrete.git "${qonqreteDir}"`, { stdio: 'pipe' });
                    // Remove .git from the clone
                    const gitDir = path.join(qonqreteDir, '.git');
                    if (fs.existsSync(gitDir)) {
                        fs.rmSync(gitDir, { recursive: true, force: true });
                    }
                    progress.report({ message: 'Finalizing...', increment: 60 });
                }
                catch (gitErr) {
                    throw new Error(`Download failed: ${downloadErr}\nGit fallback also failed: ${gitErr}`);
                }
                // Clean up tmp
                fs.rmSync(tmpDir, { recursive: true, force: true });
                // Skip to validation since git clone already placed files
                await finalizeDeploy(wsRoot, qonqreteDir, runner, progress);
                return;
            }
            // Step 2: Extract
            progress.report({ message: 'Extracting runtime...', increment: 30 });
            if (!fs.existsSync(qonqreteDir)) {
                fs.mkdirSync(qonqreteDir, { recursive: true });
            }
            await extractZip(zipPath, qonqreteDir);
            // Step 3: Flatten top-level folder
            progress.report({ message: 'Setting up runtime...', increment: 20 });
            flattenTopLevel(qonqreteDir);
            // Clean up tmp
            fs.rmSync(tmpDir, { recursive: true, force: true });
            await finalizeDeploy(wsRoot, qonqreteDir, runner, progress);
        }
        catch (err) {
            vscode.window.showErrorMessage(`Deploy failed: ${err instanceof Error ? err.message : String(err)}`);
        }
    });
}
async function finalizeDeploy(wsRoot, qonqreteDir, runner, progress) {
    // Step 4: Validate
    progress.report({ message: 'Validating...', increment: 15 });
    const scriptPath = path.join(qonqreteDir, 'qonqrete.sh');
    if (!fs.existsSync(scriptPath)) {
        throw new Error('Deploy failed: qonqrete.sh not found after extraction. The zip structure may be unexpected.');
    }
    // Ensure executable on Unix
    try {
        fs.chmodSync(scriptPath, 0o755);
    }
    catch { }
    // Step 5: .gitignore
    progress.report({ message: 'Updating .gitignore...', increment: 10 });
    await runner.ensureGitignore();
    // Step 6: Refresh
    progress.report({ message: 'Refreshing...', increment: 15 });
    runner.clearPathCache();
    // Offer to create a starter task file
    const rootTasq = path.join(wsRoot, 'tasq.md');
    if (!fs.existsSync(rootTasq)) {
        const createTasq = await vscode.window.showInformationMessage('QonQrete deployed successfully! Create a starter task file to get started?', 'Create Task File', 'Skip');
        if (createTasq === 'Create Task File') {
            await vscode.commands.executeCommand('qonqrete.createTasq');
        }
    }
    else {
        vscode.window.showInformationMessage('QonQrete deployed successfully to .qonqrete/');
    }
    // Prompt for AI configuration
    const configAI = await vscode.window.showInformationMessage('Set up AI providers and API keys now?', 'Set AI Configuration', 'Later');
    if (configAI === 'Set AI Configuration') {
        await vscode.commands.executeCommand('qonqrete.setAIConfig');
    }
}
/**
 * Register the deploy command and capture extension context for version resolution
 */
function registerDeployCommand(context) {
    extensionContext = context;
    return vscode.commands.registerCommand('qonqrete.deployToWorkspace', executeDeploy);
}
//# sourceMappingURL=deploy.js.map