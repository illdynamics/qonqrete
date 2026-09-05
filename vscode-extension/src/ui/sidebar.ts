/**
 * QonQrete v2 sidebar control panel.
 */
import * as vscode from 'vscode';
import { randomBytes } from 'crypto';
import { getRunner } from '../cli/qonqreteRunner';
import { readQonQreteConfig, resolveConfigPath } from '../config';

export class QonQreteSidebarProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'qonqreteControlPanel';

    private _view?: vscode.WebviewView;
    private _extensionUri: vscode.Uri;

    constructor(extensionUri: vscode.Uri) {
        this._extensionUri = extensionUri;
    }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken,
    ): void {
        this._view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };
        webviewView.webview.html = this._getHtmlContent(webviewView.webview);

        webviewView.webview.onDidReceiveMessage(async (data) => {
            switch (data.type) {
                case 'runCurrentFile':
                    await vscode.commands.executeCommand('qonqrete.runCurrentFile');
                    break;
                case 'configure':
                    await vscode.commands.executeCommand('qonqrete.configure');
                    break;
                case 'openConfigFile':
                    await vscode.commands.executeCommand('qonqrete.openConfigFile');
                    break;
                case 'doctor':
                    await vscode.commands.executeCommand('qonqrete.doctor');
                    break;
                case 'verify':
                    await vscode.commands.executeCommand('qonqrete.verify');
                    break;
                case 'cleanup':
                    await vscode.commands.executeCommand('qonqrete.cleanup');
                    break;
                case 'replay':
                    await vscode.commands.executeCommand('qonqrete.replay');
                    break;
                case 'runs':
                    await vscode.commands.executeCommand('qonqrete.runs');
                    break;
                case 'exec':
                    await vscode.commands.executeCommand('qonqrete.exec');
                    break;
                case 'chat':
                    await vscode.commands.executeCommand('qonqrete.chat');
                    break;
                case 'showOutput':
                    getRunner().showOutput();
                    break;
                case 'refresh':
                    await this._sendStatus();
                    break;
            }
        });

        this._sendStatus();
    }

    public refresh(): void {
        this._sendStatus();
    }

    private async _sendStatus(): Promise<void> {
        if (!this._view) { return; }
        const runner = getRunner();
        const cfg = await readQonQreteConfig();
        this._view.webview.postMessage({
            type: 'status',
            data: {
                available: runner.isAvailable(),
                configPath: cfg?.configPath || resolveConfigPath(),
                provider: cfg?.provider || 'unknown',
                model: cfg?.models.construqtor || 'unknown',
            },
        });
    }

    private _getHtmlContent(webview: vscode.Webview): string {
        const nonce = randomBytes(16).toString('base64');
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
<title>QonQrete</title>
<style>
:root{--pad:10px;--radius:4px}
body{padding:var(--pad);font-family:var(--vscode-font-family);font-size:var(--vscode-font-size);color:var(--vscode-foreground);background:var(--vscode-sideBar-background)}
h2{font-size:1.1em;margin:0 0 10px 0;padding-bottom:6px;border-bottom:1px solid var(--vscode-panel-border);display:flex;align-items:center;gap:6px}
.badge{padding:2px 8px;border-radius:10px;font-size:0.8em;font-weight:600}
.badge-ready{background:#2ea043;color:#fff}.badge-missing{background:#da3633;color:#fff}
.section{margin-bottom:14px}.section-title{font-weight:600;margin-bottom:6px;color:var(--vscode-descriptionForeground);font-size:0.8em;text-transform:uppercase}
button{width:100%;padding:6px 10px;border:none;border-radius:var(--radius);cursor:pointer;font-family:inherit;font-weight:600;margin-top:5px}
button:hover{opacity:.9}.btn-primary{background:var(--vscode-button-background);color:var(--vscode-button-foreground)}
.btn-secondary{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground)}
.info-row{display:flex;justify-content:space-between;padding:2px 0;font-size:0.85em}
.info-label{color:var(--vscode-descriptionForeground)}.info-value{font-weight:600}
.muted{opacity:.7;font-size:.8em;margin-top:6px}
</style>
</head>
<body>
<h2><span>⬡</span> QonQrete <span id="badge" class="badge badge-ready">Ready</span></h2>

<div class="section">
  <div class="section-title">Build</div>
  <button id="runBtn" class="btn-primary">▶ Run Open Task File</button>
  <button id="chatBtn" class="btn-secondary">💬 Chat</button>
  <button id="execBtn" class="btn-secondary">⌨ Exec</button>
</div>

<div class="section">
  <div class="section-title">Setup</div>
  <button id="configureBtn" class="btn-secondary">🤖 Provider &amp; Model</button>
  <button id="openConfigBtn" class="btn-secondary">📄 Open Config</button>
</div>

<div class="section">
  <div class="section-title">Diagnostics</div>
  <button id="doctorBtn" class="btn-secondary">🩺 Doctor</button>
  <button id="verifyBtn" class="btn-secondary">✅ Verify</button>
  <button id="cleanupBtn" class="btn-secondary">🧹 Cleanup</button>
</div>

<div class="section">
  <div class="section-title">Runs</div>
  <button id="runsBtn" class="btn-secondary">📜 List Runs</button>
  <button id="replayBtn" class="btn-secondary">↺ Replay Run</button>
</div>

<div class="info-row"><span class="info-label">Provider:</span><span id="provider" class="info-value">…</span></div>
<div class="info-row"><span class="info-label">Model:</span><span id="model" class="info-value">…</span></div>
<div class="info-row"><span class="info-label">Config:</span><span id="config" class="info-value">…</span></div>

<button id="outputBtn" class="btn-secondary">📋 Output</button>
<div class="muted">Run the currently open Markdown file as a QonQrete task. Destination + TUI/headless are chosen when you run.</div>

<script nonce="${nonce}">
const v = acquireVsCodeApi();
function $(id){return document.getElementById(id)}
$('runBtn').onclick=()=>v.postMessage({type:'runCurrentFile'});
$('chatBtn').onclick=()=>v.postMessage({type:'chat'});
$('execBtn').onclick=()=>v.postMessage({type:'exec'});
$('configureBtn').onclick=()=>v.postMessage({type:'configure'});
$('openConfigBtn').onclick=()=>v.postMessage({type:'openConfigFile'});
$('doctorBtn').onclick=()=>v.postMessage({type:'doctor'});
$('verifyBtn').onclick=()=>v.postMessage({type:'verify'});
$('cleanupBtn').onclick=()=>v.postMessage({type:'cleanup'});
$('runsBtn').onclick=()=>v.postMessage({type:'runs'});
$('replayBtn').onclick=()=>v.postMessage({type:'replay'});
$('outputBtn').onclick=()=>v.postMessage({type:'showOutput'});
window.addEventListener('message',e=>{
  const msg=e.data;
  if(msg.type!=='status')return;
  const d=msg.data;
  $('badge').textContent=d.available?'Ready':'Missing';
  $('badge').className='badge '+(d.available?'badge-ready':'badge-missing');
  $('provider').textContent=d.provider||'?';
  $('model').textContent=d.model||'?';
  $('config').textContent=d.configPath||'(not found)';
});
v.postMessage({type:'refresh'});
</script>
</body>
</html>`;
    }

    private _getNonce(): string {
        return randomBytes(16).toString('base64');
    }
}
