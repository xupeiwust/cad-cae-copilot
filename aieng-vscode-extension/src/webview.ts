import * as vscode from "vscode";

import type { HostToWebviewMessage, WebviewToHostMessage } from "./protocol";

export function configureWebview(webview: vscode.Webview, extensionUri: vscode.Uri): void {
  webview.options = {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extensionUri, "media")],
  };
  const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "media", "viewer.js"));
  const nonce = getNonce();
  webview.html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} blob: data:; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>AIENG CAD Preview</title>
</head>
<body>
  <main id="app"></main>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
}

export function bindWebviewMessages(
  webview: vscode.Webview,
  subscriptions: vscode.Disposable[],
  onReady: () => void | Promise<void>,
  onRefresh: () => void | Promise<void>,
): void {
  subscriptions.push(webview.onDidReceiveMessage(async (message: WebviewToHostMessage) => {
    if (message.kind === "ready") {
      await onReady();
      return;
    }
    if (message.kind === "refresh") {
      await onRefresh();
      return;
    }
    if (message.kind === "copy") {
      await vscode.env.clipboard.writeText(message.text);
      vscode.window.setStatusBarMessage(`AIENG: Copied ${message.text}`, 2500);
    }
  }));
}

export async function postMessage(webview: vscode.Webview, message: HostToWebviewMessage): Promise<void> {
  await webview.postMessage(message);
}

function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let value = "";
  for (let i = 0; i < 32; i++) value += chars.charAt(Math.floor(Math.random() * chars.length));
  return value;
}
