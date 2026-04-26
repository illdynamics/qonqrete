/**
 * QonQrete Sidebar Panel
 * WebView-based control panel
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */
import * as vscode from 'vscode';
export declare class QonQreteSidebarProvider implements vscode.WebviewViewProvider {
    static readonly viewType = "qonqreteControlPanel";
    private _view?;
    private _extensionUri;
    private _runStateDisposable?;
    constructor(extensionUri: vscode.Uri);
    resolveWebviewView(webviewView: vscode.WebviewView, _context: vscode.WebviewViewResolveContext, _token: vscode.CancellationToken): void;
    private _handleRunTasq;
    private _sendStatus;
    private _sendQageList;
    private _sendQageDetails;
    private _openQage;
    private _openFile;
    private _sendRunState;
    refresh(): void;
    private _getHtmlContent;
    private _getNonce;
    dispose(): void;
}
//# sourceMappingURL=sidebar.d.ts.map