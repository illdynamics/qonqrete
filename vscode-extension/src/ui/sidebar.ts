/**
 * QonQrete Sidebar Panel
 * WebView-based control panel
 * 
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

import * as vscode from 'vscode';
import { getRunner, QonQreteRunConfig, RunStatus } from '../cli/qonqreteRunner';

export class QonQreteSidebarProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'qonqreteControlPanel';

    private _view?: vscode.WebviewView;
    private _extensionUri: vscode.Uri;
    private _runStateDisposable?: vscode.Disposable;

    constructor(extensionUri: vscode.Uri) {
        this._extensionUri = extensionUri;
    }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ): void {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        webviewView.webview.html = this._getHtmlContent(webviewView.webview);

        webviewView.webview.onDidReceiveMessage(async (data) => {
            switch (data.type) {
                case 'runTasq':
                    await this._handleRunTasq(data.config);
                    break;
                case 'resumeRun':
                    await vscode.commands.executeCommand('qonqrete.resumeRun');
                    break;
                case 'initWorkspace':
                    await vscode.commands.executeCommand('qonqrete.initWorkspace');
                    break;
                case 'cleanQages':
                    await vscode.commands.executeCommand('qonqrete.cleanQages');
                    break;
                case 'openSettings':
                    await vscode.commands.executeCommand('workbench.action.openSettings', 'qonqrete');
                    break;
                case 'getStatus':
                    await this._sendStatus();
                    break;
                case 'getQages':
                    await this._sendQageList();
                    break;
                case 'getQageDetails':
                    await this._sendQageDetails(data.qageName);
                    break;
                case 'openQage':
                    await this._openQage(data.qageName);
                    break;
                case 'openFile':
                    await this._openFile(data.filePath);
                    break;
                case 'showOutput':
                    getRunner().showOutput();
                    break;
                case 'installBash':
                    await vscode.env.openExternal(vscode.Uri.parse('https://git-scm.com/download/win'));
                    break;
                case 'deployWorkspace':
                    await vscode.commands.executeCommand('qonqrete.deployToWorkspace');
                    break;
                case 'createTasq':
                    await vscode.commands.executeCommand('qonqrete.createTasq');
                    break;
                case 'setAIConfig':
                    await vscode.commands.executeCommand('qonqrete.setAIConfig');
                    break;
            }
        });

        this._runStateDisposable = getRunner().onRunStateChange((status) => {
            this._sendRunState(status);
        });

        this._sendStatus();
    }

    private async _handleRunTasq(config: QonQreteRunConfig): Promise<void> {
        const runner = getRunner();
        
        // Check if we can execute, waiting for verification if in progress
        let canExec = runner.canExecute();
        if (canExec.verifying) {
            // Wait for verification with progress indicator (consistent with command palette)
            const verified = await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'QonQrete: Verifying shell...',
                cancellable: false,
            }, async () => {
                return await runner.waitForVerification();
            });
            
            if (!verified) {
                canExec = runner.canExecute();
                vscode.window.showErrorMessage(canExec.reason || 'Shell verification failed');
                return;
            }
        } else if (!canExec.canRun) {
            vscode.window.showErrorMessage(canExec.reason || 'Cannot run QonQrete');
            return;
        }
        
        try {
            const hasTasq = await runner.hasTasqFile();
            if (!hasTasq) {
                vscode.window.showWarningMessage('No tasq.md found. Use "Create tasq.md" first.');
                return;
            }

            // Handle qonstruction name sanitization
            if (config.qonstructionName) {
                const result = runner.sanitizeQonstructionName(config.qonstructionName);
                if (result.wasModified) {
                    const proceed = await vscode.window.showWarningMessage(
                        `Name sanitized: "${result.original}" → "${result.sanitized}"`,
                        'Continue',
                        'Cancel'
                    );
                    if (proceed !== 'Continue') {
                        return;
                    }
                }
                config.qonstructionName = result.sanitized;
            }

            const tasqPath = await runner.getTasqPath();
            if (tasqPath) {
                const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === tasqPath);
                if (doc?.isDirty) await doc.save();
            }

            await runner.run(config);
            
            vscode.window.showInformationMessage('QonQrete started.', 'Show Terminal')
                .then(r => { if (r) vscode.commands.executeCommand('workbench.action.terminal.focus'); });
        } catch (error) {
            vscode.window.showErrorMessage(`Run failed: ${error}`);
        }
    }

    private async _sendStatus(): Promise<void> {
        if (!this._view) return;

        const runner = getRunner();
        const scriptPath = await runner.getQonQretePath();
        const version = await runner.getVersion();
        const qages = await runner.getAvailableQages();
        const hasTasq = await runner.hasTasqFile();
        const initStatus = await runner.isInitialized();
        const runStatus = runner.getRunStatus();
        const shellInfo = runner.getShellInfo();
        const canExec = runner.canExecute();

        const config = vscode.workspace.getConfiguration('qonqrete');

        this._view.webview.postMessage({
            type: 'status',
            data: {
                installed: !!scriptPath,
                version: version || 'unknown',
                qageCount: qages.length,
                hasTasq,
                hasImage: initStatus.hasImage,
                engine: initStatus.engine,
                runState: runStatus.state,
                exitCode: runStatus.exitCode,
                canExecute: canExec.canRun,
                canExecuteVerifying: canExec.verifying,
                canExecuteReason: canExec.reason,
                shell: {
                    type: shellInfo.shellType,
                    hasBash: shellInfo.hasBash,
                    isWindows: shellInfo.isWindows,
                    verified: shellInfo.verified,
                },
                defaultConfig: {
                    sensitivity: config.get<number>('defaultSensitivity', 1),
                    cycles: config.get<number>('defaultCycles', 1),
                    mode: config.get<string>('defaultMode', 'program'),
                    autonomous: config.get<boolean>('defaultAutonomous', true),
                    useSqrapyard: config.get<boolean>('useSqrapyard', false),
                    containerEngine: config.get<string>('containerEngine', 'auto'),
                    enableTui: config.get<boolean>('enableTui', false),
                },
            },
        });
    }

    private async _sendQageList(): Promise<void> {
        if (!this._view) return;

        const runner = getRunner();
        const qages = await runner.getAvailableQages();
        
        const qageDetails = await Promise.all(
            qages.slice(0, 10).map(async (name) => {
                const details = await runner.getQageDetails(name);
                return {
                    name,
                    timestamp: details?.timestamp?.toISOString() || null,
                    counts: details ? {
                        qodeyard: details.artifacts.qodeyard.length,
                        briqs: details.artifacts.briqs.length,
                        exeq: details.artifacts.exeq.length,
                        reqap: details.artifacts.reqap.length,
                    } : null,
                };
            })
        );

        this._view.webview.postMessage({
            type: 'qageList',
            data: { qages: qageDetails, total: qages.length },
        });
    }

    private async _sendQageDetails(qageName: string): Promise<void> {
        if (!this._view) return;

        const runner = getRunner();
        const details = await runner.getQageDetails(qageName);

        this._view.webview.postMessage({
            type: 'qageDetails',
            data: details ? {
                name: qageName,
                path: details.path,
                timestamp: details.timestamp?.toISOString(),
                artifacts: details.artifacts,
                configFiles: details.configFiles,
            } : null,
        });
    }

    private async _openQage(qageName: string): Promise<void> {
        const runner = getRunner();
        const details = await runner.getQageDetails(qageName);
        if (details) {
            await vscode.commands.executeCommand('revealInExplorer', vscode.Uri.file(details.path));
        }
    }

    private async _openFile(filePath: string): Promise<void> {
        try {
            const doc = await vscode.workspace.openTextDocument(filePath);
            await vscode.window.showTextDocument(doc);
        } catch {
            vscode.window.showErrorMessage(`Could not open file: ${filePath}`);
        }
    }

    private _sendRunState(status: RunStatus): void {
        if (!this._view) return;
        this._view.webview.postMessage({ type: 'runState', data: status });
    }

    public refresh(): void {
        this._sendStatus();
        this._sendQageList();
    }

    private _getHtmlContent(webview: vscode.Webview): string {
        const nonce = this._getNonce();

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
    <title>QonQrete Control</title>
    <style>
        :root { --pad: 10px; --radius: 4px; }
        body {
            padding: var(--pad);
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background: var(--vscode-sideBar-background);
        }
        h2 {
            font-size: 1.1em;
            margin: 0 0 10px 0;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--vscode-panel-border);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .badge {
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            font-weight: 500;
        }
        .badge-ready { background: #2ea043; color: white; }
        .badge-running { background: #1f6feb; color: white; animation: pulse 1.5s infinite; }
        .badge-done { background: #2ea043; color: white; }
        .badge-failed { background: #da3633; color: white; }
        .badge-blocked { background: #6e7681; color: white; }
        .badge-timeout { background: #d29922; color: white; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        
        .section { margin-bottom: 14px; }
        .section-title { font-weight: 600; margin-bottom: 5px; color: var(--vscode-descriptionForeground); font-size: 0.85em; text-transform: uppercase; }
        
        .form-group { margin-bottom: 8px; }
        .form-group label { display: block; margin-bottom: 2px; font-size: 0.9em; }
        
        input[type="number"], input[type="text"], select {
            width: 100%;
            padding: 4px 6px;
            border: 1px solid var(--vscode-input-border);
            border-radius: var(--radius);
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            font-family: inherit;
            box-sizing: border-box;
        }
        
        .slider-row { display: flex; align-items: center; gap: 8px; }
        .slider-row input[type="range"] {
            flex: 1; -webkit-appearance: none; height: 4px;
            background: var(--vscode-scrollbarSlider-background); border-radius: 2px;
        }
        .slider-row input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none; width: 12px; height: 12px;
            background: var(--vscode-button-background); border-radius: 50%; cursor: pointer;
        }
        .slider-value { min-width: 20px; text-align: center; font-weight: 500; }
        
        .checkbox-row { display: flex; align-items: center; gap: 5px; margin-bottom: 5px; }
        .checkbox-row input { width: 14px; height: 14px; margin: 0; }
        .checkbox-row label { margin: 0; font-size: 0.85em; }
        
        button {
            width: 100%; padding: 6px 10px; border: none; border-radius: var(--radius);
            cursor: pointer; font-family: inherit; font-weight: 500; margin-top: 5px;
        }
        button:hover { opacity: 0.9; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        .btn-secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        .btn-danger { background: #da3633; color: white; }
        .btn-small { padding: 3px 6px; font-size: 0.85em; width: auto; margin: 0; }
        
        .info-row { display: flex; justify-content: space-between; padding: 2px 0; font-size: 0.85em; }
        .info-label { color: var(--vscode-descriptionForeground); }
        .info-value { font-weight: 500; }
        .info-warn { color: #d29922; }
        .info-ok { color: #2ea043; }
        .info-error { color: #da3633; }
        
        .divider { height: 1px; background: var(--vscode-panel-border); margin: 12px 0; }
        
        .alert { padding: 8px; border-radius: var(--radius); margin-bottom: 10px; font-size: 0.85em; }
        .alert-error { background: rgba(218, 54, 51, 0.15); border: 1px solid #da3633; }
        .alert-warn { background: rgba(210, 153, 34, 0.15); border: 1px solid #d29922; }
        
        .qage-list { max-height: 150px; overflow-y: auto; border: 1px solid var(--vscode-panel-border); border-radius: var(--radius); }
        .qage-item { padding: 5px 8px; cursor: pointer; border-bottom: 1px solid var(--vscode-panel-border); font-size: 0.85em; }
        .qage-item:last-child { border-bottom: none; }
        .qage-item:hover { background: var(--vscode-list-hoverBackground); }
        .qage-item-header { display: flex; justify-content: space-between; align-items: center; }
        .qage-item-name { font-weight: 500; }
        .qage-item-meta { color: var(--vscode-descriptionForeground); font-size: 0.8em; }
        .qage-details { padding: 4px 8px; background: var(--vscode-editor-background); font-size: 0.8em; }
        .qage-details-row { padding: 2px 0; }
        .qage-file-link { color: var(--vscode-textLink-foreground); cursor: pointer; }
        .qage-file-link:hover { text-decoration: underline; }
        
        .collapsed { display: none; }
        .expand-btn { background: none; border: none; color: var(--vscode-textLink-foreground); cursor: pointer; font-size: 0.85em; padding: 0; margin: 3px 0; width: auto; }
        .expand-btn:hover { text-decoration: underline; }
        .hidden { display: none; }
        .name-hint { font-size: 0.75em; color: var(--vscode-descriptionForeground); margin-top: 2px; }
    </style>
</head>
<body>
    <h2>
        <span>⬡</span> QonQrete
        <span id="statusBadge" class="badge badge-ready">Ready</span>
    </h2>

    <div id="blockedAlert" class="alert alert-error hidden">
        <strong>⚠️ No bash shell found</strong><br>
        QonQrete requires bash to run. On Windows, install Git Bash or use WSL.
        <button class="btn-secondary btn-small" style="margin-top: 6px" onclick="installBash()">Install Git Bash</button>
    </div>

    <div id="notInstalled" class="section hidden">
        <p>QonQrete not found in workspace.</p>
        <button class="btn-primary" onclick="deployWorkspace()">⬡ Deploy to Workspace</button>
        <button class="btn-secondary" onclick="openSettings()">Configure Path</button>
    </div>

    <div id="mainContent">
        <div class="section">
            <div class="section-title">Configuration</div>
            
            <div class="form-group">
                <label>Briq Sensitivity (0-16)</label>
                <div class="slider-row">
                    <input type="range" id="sensitivity" min="0" max="16" value="1" oninput="updateSlider('sensitivity')">
                    <span id="sensitivityValue" class="slider-value">1</span>
                </div>
            </div>

            <div class="form-group">
                <label>Cycles</label>
                <input type="number" id="cycles" min="1" max="50" value="1">
            </div>

            <div class="form-group">
                <label>Mode</label>
                <select id="mode">
                    <option value="program">Program</option>
                    <option value="enterprise">Enterprise</option>
                    <option value="security">Security</option>
                    <option value="data">Data</option>
                    <option value="devops">DevOps</option>
                    <option value="web">Web</option>
                </select>
            </div>

            <div class="checkbox-row">
                <input type="checkbox" id="autonomous">
                <label for="autonomous">Autonomous Mode</label>
            </div>

            <div class="checkbox-row">
                <input type="checkbox" id="useSqrapyard">
                <label for="useSqrapyard">Seed from Sqrapyard</label>
            </div>
            
            <button class="expand-btn" onclick="toggleAdvanced()">▸ Advanced</button>
            <div id="advancedOptions" class="collapsed">
                <div class="form-group">
                    <label>Qonstruction Name</label>
                    <input type="text" id="qonstructionName" placeholder="(optional)">
                    <div class="name-hint">Allowed: a-z, A-Z, 0-9, _, -</div>
                </div>
                
                <div class="form-group">
                    <label>Container Engine</label>
                    <select id="containerEngine">
                        <option value="auto">Auto-detect</option>
                        <option value="docker">Docker</option>
                        <option value="podman">Podman</option>
                        <option value="msb">MicroSandbox</option>
                    </select>
                </div>
                
                <div class="checkbox-row">
                    <input type="checkbox" id="enableTui">
                    <label for="enableTui">TUI Mode</label>
                </div>
                
                <div class="checkbox-row">
                    <input type="checkbox" id="enableWonqrete">
                    <label for="enableWonqrete">Wonqrete Mode</label>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Actions</div>
            <button class="btn-primary" id="runBtn" onclick="runTasq()">▶ Run Tasq</button>
            <button class="btn-secondary" onclick="deployWorkspace()">⬡ Deploy</button>
            <button class="btn-secondary" onclick="createTasq()">+ Create tasq.md</button>
            <button class="btn-secondary" onclick="setAIConfig()">🤖 AI Config</button>
            <button class="btn-secondary" onclick="resumeRun()">⟳ Resume</button>
            <button class="btn-secondary" onclick="initWorkspace()">⚙ Init</button>
            <button class="btn-danger" onclick="cleanQages()">🗑 Clean</button>
        </div>

        <div class="divider"></div>

        <div class="section">
            <div class="section-title">Status</div>
            <div class="info-row">
                <span class="info-label">Version:</span>
                <span id="versionInfo" class="info-value">-</span>
            </div>
            <div class="info-row">
                <span class="info-label">Image:</span>
                <span id="imageInfo" class="info-value">-</span>
            </div>
            <div class="info-row">
                <span class="info-label">tasq.md:</span>
                <span id="tasqStatus" class="info-value">-</span>
            </div>
            <div class="info-row">
                <span class="info-label">Shell:</span>
                <span id="shellInfo" class="info-value">-</span>
            </div>
            <div id="exitCodeRow" class="info-row hidden">
                <span class="info-label">Last Exit:</span>
                <span id="exitCodeInfo" class="info-value">-</span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Qages (<span id="qageCount">0</span>)</div>
            <div id="qageList" class="qage-list">
                <div class="qage-item" style="color: var(--vscode-descriptionForeground)">Loading...</div>
            </div>
        </div>

        <button class="btn-secondary" onclick="openSettings()">⚙ Settings</button>
        <button class="btn-secondary" onclick="showOutput()">📋 Log</button>
    </div>

    <script nonce="${nonce}">
        const vscode = acquireVsCodeApi();
        let advancedOpen = false;
        let expandedQage = null;
        let canExecute = true;

        vscode.postMessage({ type: 'getStatus' });
        vscode.postMessage({ type: 'getQages' });

        window.addEventListener('message', event => {
            const msg = event.data;
            if (msg.type === 'status') updateStatus(msg.data);
            if (msg.type === 'qageList') updateQageList(msg.data);
            if (msg.type === 'qageDetails') updateQageDetails(msg.data);
            if (msg.type === 'runState') updateRunState(msg.data);
        });

        function updateStatus(data) {
            const badge = document.getElementById('statusBadge');
            const notInstalled = document.getElementById('notInstalled');
            const main = document.getElementById('mainContent');
            const blockedAlert = document.getElementById('blockedAlert');
            const runBtn = document.getElementById('runBtn');
            
            canExecute = data.canExecute;
            
            if (!data.installed) {
                badge.textContent = 'Not Found';
                badge.className = 'badge badge-failed';
                notInstalled.classList.remove('hidden');
                main.classList.add('hidden');
                blockedAlert.classList.add('hidden');
                return;
            }

            notInstalled.classList.add('hidden');
            main.classList.remove('hidden');

            // Show blocked alert if no bash
            if (!data.canExecute) {
                blockedAlert.classList.remove('hidden');
                runBtn.disabled = true;
                badge.textContent = 'Blocked';
                badge.className = 'badge badge-blocked';
            } else {
                blockedAlert.classList.add('hidden');
                runBtn.disabled = false;
                
                const state = data.runState || 'idle';
                if (state === 'running') {
                    badge.textContent = 'Running';
                    badge.className = 'badge badge-running';
                } else if (state === 'completed') {
                    badge.textContent = 'Done';
                    badge.className = 'badge badge-done';
                } else if (state === 'failed') {
                    badge.textContent = 'Failed';
                    badge.className = 'badge badge-failed';
                } else if (state === 'timeout') {
                    badge.textContent = 'Timeout';
                    badge.className = 'badge badge-timeout';
                } else {
                    badge.textContent = 'Ready';
                    badge.className = 'badge badge-ready';
                }
            }

            document.getElementById('versionInfo').textContent = 'v' + data.version;
            
            const imgInfo = document.getElementById('imageInfo');
            imgInfo.textContent = data.hasImage ? '✓ ' + data.engine : '✗ Not built';
            imgInfo.className = 'info-value ' + (data.hasImage ? 'info-ok' : 'info-warn');
            
            const tasqInfo = document.getElementById('tasqStatus');
            tasqInfo.textContent = data.hasTasq ? '✓ Found' : '✗ Missing';
            tasqInfo.className = 'info-value ' + (data.hasTasq ? 'info-ok' : 'info-warn');

            if (data.shell) {
                const shellTypes = { bash: 'Bash', gitbash: 'Git Bash', wsl: 'WSL', none: 'None' };
                const shellEl = document.getElementById('shellInfo');
                const shellName = shellTypes[data.shell.type] || data.shell.type;
                const verifiedStatus = data.shell.verified ? ' ✓' : ' ?';
                shellEl.textContent = shellName + verifiedStatus;
                shellEl.className = 'info-value ' + (data.shell.hasBash ? (data.shell.verified ? 'info-ok' : 'info-warn') : 'info-error');
            }

            // Show exit code if available
            const exitRow = document.getElementById('exitCodeRow');
            const exitInfo = document.getElementById('exitCodeInfo');
            if (data.exitCode !== undefined && data.exitCode !== null) {
                exitRow.classList.remove('hidden');
                exitInfo.textContent = data.exitCode.toString();
                exitInfo.className = 'info-value ' + (data.exitCode === 0 ? 'info-ok' : 'info-error');
            } else {
                exitRow.classList.add('hidden');
            }

            if (data.defaultConfig) {
                document.getElementById('sensitivity').value = data.defaultConfig.sensitivity;
                document.getElementById('sensitivityValue').textContent = data.defaultConfig.sensitivity;
                document.getElementById('cycles').value = data.defaultConfig.cycles;
                document.getElementById('mode').value = data.defaultConfig.mode;
                document.getElementById('autonomous').checked = data.defaultConfig.autonomous;
                document.getElementById('useSqrapyard').checked = data.defaultConfig.useSqrapyard;
                document.getElementById('containerEngine').value = data.defaultConfig.containerEngine;
                document.getElementById('enableTui').checked = data.defaultConfig.enableTui;
            }
        }

        function updateQageList(data) {
            document.getElementById('qageCount').textContent = data.total;
            const list = document.getElementById('qageList');
            
            if (!data.qages || data.qages.length === 0) {
                list.innerHTML = '<div class="qage-item" style="color: var(--vscode-descriptionForeground)">No qages yet</div>';
                return;
            }
            
            list.innerHTML = data.qages.map(q => {
                const ts = q.timestamp ? new Date(q.timestamp).toLocaleString() : '';
                const counts = q.counts ? Object.entries(q.counts).filter(([k,v]) => v > 0).map(([k,v]) => v + ' ' + k).join(', ') : '';
                return \`<div class="qage-item" id="qage-\${q.name}">
                    <div class="qage-item-header" onclick="toggleQage('\${q.name}')">
                        <div>
                            <span class="qage-item-expand">\${expandedQage === q.name ? '▾' : '▸'}</span>
                            <span class="qage-item-name">\${q.name.replace('qage_', '')}</span>
                        </div>
                        <button class="btn-small btn-secondary" onclick="event.stopPropagation(); openQage('\${q.name}')">📂</button>
                    </div>
                    <div class="qage-item-meta">\${ts}</div>
                    <div class="qage-item-meta">\${counts || 'empty'}</div>
                    <div id="qage-details-\${q.name}" class="qage-details \${expandedQage === q.name ? '' : 'collapsed'}"></div>
                </div>\`;
            }).join('');
            
            if (data.total > data.qages.length) {
                list.innerHTML += \`<div class="qage-item" style="color: var(--vscode-descriptionForeground); text-align: center">... +\${data.total - data.qages.length} more</div>\`;
            }
        }

        function toggleQage(name) {
            if (expandedQage === name) {
                expandedQage = null;
            } else {
                expandedQage = name;
                vscode.postMessage({ type: 'getQageDetails', qageName: name });
            }
            vscode.postMessage({ type: 'getQages' });
        }

        function updateQageDetails(data) {
            if (!data) return;
            const el = document.getElementById('qage-details-' + data.name);
            if (!el) return;

            let html = '';
            for (const [dir, files] of Object.entries(data.artifacts)) {
                if (files.length > 0) {
                    html += '<div class="qage-details-row"><strong>' + dir + '/</strong> (' + files.length + ')</div>';
                    html += files.slice(0, 5).map(f => 
                        '<div class="qage-details-row">  <span class="qage-file-link" onclick="openFile(\\'' + (data.path + '/' + dir + '/' + f).replace(/\\\\/g, '/').replace(/'/g, "\\\\'") + '\\')">' + f + '</span></div>'
                    ).join('');
                    if (files.length > 5) html += '<div class="qage-details-row" style="color: var(--vscode-descriptionForeground)">  ... +' + (files.length - 5) + ' more</div>';
                }
            }
            el.innerHTML = html || '<div class="qage-details-row">No artifacts</div>';
        }

        function updateRunState(status) {
            const badge = document.getElementById('statusBadge');
            const runBtn = document.getElementById('runBtn');
            
            if (!canExecute) return; // Don't update if blocked
            
            if (status.state === 'running') {
                badge.textContent = 'Running';
                badge.className = 'badge badge-running';
                runBtn.disabled = true;
                runBtn.textContent = '⏳ Running...';
            } else if (status.state === 'completed') {
                const code = status.exitCode !== undefined ? ' (' + status.exitCode + ')' : '';
                badge.textContent = 'Done' + code;
                badge.className = 'badge badge-done';
                runBtn.disabled = false;
                runBtn.textContent = '▶ Run Tasq';
                
                // Show exit code
                document.getElementById('exitCodeRow').classList.remove('hidden');
                const exitInfo = document.getElementById('exitCodeInfo');
                exitInfo.textContent = (status.exitCode !== undefined ? status.exitCode : '?').toString();
                exitInfo.className = 'info-value ' + (status.exitCode === 0 ? 'info-ok' : 'info-error');
            } else if (status.state === 'failed') {
                const code = status.exitCode !== undefined ? ' (' + status.exitCode + ')' : '';
                badge.textContent = 'Failed' + code;
                badge.className = 'badge badge-failed';
                runBtn.disabled = false;
                runBtn.textContent = '▶ Run Tasq';
            } else if (status.state === 'timeout') {
                // HONEST: Unknown outcome - show warning, not success
                badge.textContent = 'Timeout';
                badge.className = 'badge badge-timeout';
                runBtn.disabled = false;
                runBtn.textContent = '▶ Run Tasq';
            } else {
                badge.textContent = 'Ready';
                badge.className = 'badge badge-ready';
                runBtn.disabled = false;
                runBtn.textContent = '▶ Run Tasq';
            }
        }

        function updateSlider(id) {
            document.getElementById(id + 'Value').textContent = document.getElementById(id).value;
        }

        function toggleAdvanced() {
            advancedOpen = !advancedOpen;
            document.getElementById('advancedOptions').classList.toggle('collapsed', !advancedOpen);
            document.querySelector('.expand-btn').textContent = (advancedOpen ? '▾' : '▸') + ' Advanced';
        }

        function getConfig() {
            const name = document.getElementById('qonstructionName').value.trim();
            return {
                sensitivity: parseInt(document.getElementById('sensitivity').value, 10),
                cycles: parseInt(document.getElementById('cycles').value, 10),
                mode: document.getElementById('mode').value,
                autonomous: document.getElementById('autonomous').checked,
                useSqrapyard: document.getElementById('useSqrapyard').checked,
                qonstructionName: name || undefined,
                containerEngine: document.getElementById('containerEngine').value,
                enableTui: document.getElementById('enableTui').checked,
                enableWonqrete: document.getElementById('enableWonqrete').checked,
            };
        }

        function runTasq() { 
            if (!canExecute) return;
            vscode.postMessage({ type: 'runTasq', config: getConfig() }); 
        }
        function resumeRun() { vscode.postMessage({ type: 'resumeRun' }); }
        function initWorkspace() { vscode.postMessage({ type: 'initWorkspace' }); }
        function cleanQages() { vscode.postMessage({ type: 'cleanQages' }); }
        function openSettings() { vscode.postMessage({ type: 'openSettings' }); }
        function showOutput() { vscode.postMessage({ type: 'showOutput' }); }
        function openQage(name) { vscode.postMessage({ type: 'openQage', qageName: name }); }
        function openFile(path) { vscode.postMessage({ type: 'openFile', filePath: path }); }
        function installBash() { vscode.postMessage({ type: 'installBash' }); }
        function deployWorkspace() { vscode.postMessage({ type: 'deployWorkspace' }); }
        function createTasq() { vscode.postMessage({ type: 'createTasq' }); }
        function setAIConfig() { vscode.postMessage({ type: 'setAIConfig' }); }
    </script>
</body>
</html>`;
    }

    private _getNonce(): string {
        let text = '';
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        for (let i = 0; i < 32; i++) text += chars.charAt(Math.floor(Math.random() * chars.length));
        return text;
    }

    public dispose(): void {
        this._runStateDisposable?.dispose();
    }
}
