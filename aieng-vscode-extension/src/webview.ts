import * as vscode from "vscode";

import type { HostToWebviewMessage, WebviewToHostMessage } from "./protocol";

export function configureWebview(webview: vscode.Webview, extensionUri: vscode.Uri, scriptName = "viewer.js"): void {
  webview.options = {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extensionUri, "media")],
  };
  const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "media", scriptName));
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

/**
 * Live workbench webview: a thin shell that embeds the backend-served React SPA
 * (`/app/?project=...&embed=vscode`) in an iframe, plus a native toolbar that
 * relays agent-handoff actions to the extension host. This replaces the bespoke
 * Three.js viewer for live projects so there is a single UI source of truth.
 */
export function configureLiveWorkbenchWebview(
  webview: vscode.Webview,
  backendUrl: string,
  projectId: string,
  projectName: string,
): void {
  webview.options = { enableScripts: true };
  const nonce = getNonce();
  const src = `${backendUrl}/app/?project=${encodeURIComponent(projectId)}&embed=vscode`;
  webview.html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${backendUrl}; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>AIENG CAD Preview</title>
  <style>
    html, body { height: 100%; margin: 0; background: #0a0e1a; color: #dbe7fb; font-family: Inter, "Segoe UI", sans-serif; }
    #app { display: flex; flex-direction: column; height: 100vh; }
    .bar { display: flex; gap: 8px; align-items: center; padding: 7px 10px; background: #0a0e1a; border-bottom: 1px solid #1e293b; }
    .bar .name { font-size: 12px; font-weight: 600; max-width: 30%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar .hint { font-size: 11px; color: #64748b; }
    .bar .spacer { margin-left: auto; }
    .bar .sep { width: 1px; height: 20px; background: #1e293b; }
    .bar button { font: inherit; font-size: 12px; color: #dbe7fb; background: rgba(8, 15, 30, 0.9); border: 1px solid #334155; border-radius: 8px; padding: 5px 10px; cursor: pointer; transition: border-color .15s ease, color .15s ease; }
    .bar button:hover { border-color: #38bdf8; color: #38bdf8; }
    .bar button.primary { background: #2563eb; border-color: transparent; color: #fff; }
    .bar button.primary:hover { color: #fff; border-color: transparent; }
    iframe { flex: 1; width: 100%; border: 0; background: #0a0e1a; }
    .toast { position: fixed; left: 50%; top: 50px; transform: translateX(-50%); background: #2563eb; color: #fff; border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; opacity: 0; transition: opacity .18s; pointer-events: none; }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>
  <div id="app">
    <div class="bar">
      <span class="name">${escapeHtml(projectName)}</span>
      <span class="hint">Hand off to your agent →</span>
      <button data-act="copyStarterPrompt" title="Copy a prompt that asks your agent to create the first model — paste it into your agent chat">Build</button>
      <button data-act="copyModifyPrompt" title="Copy a prompt to modify this model. Pick faces in the 3D view first to target them.">Modify</button>
      <button data-act="copyProjectContext" title="Copy the project id and backend URL to mention in your agent chat">Context</button>
      <span class="spacer"></span>
      <span class="sep"></span>
      <button data-act="reload" title="Reload the preview">Reload</button>
      <button data-act="openHome" title="Back to AIENG Home">Home</button>
    </div>
    <iframe id="frame" src="${src}" allow="clipboard-read; clipboard-write"></iframe>
  </div>
  <div class="toast"></div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const frame = document.getElementById("frame");
    const modifyButton = document.querySelector('[data-act="copyModifyPrompt"]');
    const toast = document.querySelector(".toast");
    let pointers = [];
    let toastTimer;
    function showToast(text) {
      if (!toast) return;
      toast.textContent = text;
      toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove("show"), 1800);
    }
    function syncModify() {
      if (!modifyButton) return;
      const n = pointers.length;
      modifyButton.textContent = n ? ("Modify (" + n + ")") : "Modify";
      modifyButton.classList.toggle("primary", n > 0);
    }
    document.querySelectorAll(".bar button").forEach((button) => button.addEventListener("click", () => {
      const act = button.getAttribute("data-act");
      if (act === "reload") { frame.src = frame.src; return; }
      if (act === "openHome") { vscode.postMessage({ kind: act }); return; }
      if (act === "copyModifyPrompt") {
        vscode.postMessage({ kind: act, pointers });
        showToast(pointers.length ? ("Copied — targets " + pointers.length + " face" + (pointers.length > 1 ? "s" : "") + ". Paste into your agent.") : "Copied modify prompt — paste into your agent chat");
        return;
      }
      vscode.postMessage({ kind: act });
      showToast("Copied — paste into your agent chat");
    }));
    // Messages from the embedded SPA: track the picked faces so "Modify"
    // targets them; relay any direct copy/openHome handoff to the host.
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (!data || typeof data !== "object" || typeof data.kind !== "string") return;
      if (data.kind === "selectionChanged") { pointers = Array.isArray(data.pointers) ? data.pointers : []; syncModify(); return; }
      if (data.kind === "copy" || data.kind.startsWith("copy") || data.kind === "openHome") vscode.postMessage(data);
    });
  </script>
</body>
</html>`;
}

export function bindWebviewMessages(
  webview: vscode.Webview,
  subscriptions: vscode.Disposable[],
  onReady: () => void | Promise<void>,
  onRefresh: () => void | Promise<void>,
  onUnhandled?: (message: WebviewToHostMessage) => void | Promise<void>,
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
      return;
    }
    await onUnhandled?.(message);
  }));
}

export async function postMessage(webview: vscode.Webview, message: HostToWebviewMessage): Promise<void> {
  await webview.postMessage(message);
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}

function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let value = "";
  for (let i = 0; i < 32; i++) value += chars.charAt(Math.floor(Math.random() * chars.length));
  return value;
}
