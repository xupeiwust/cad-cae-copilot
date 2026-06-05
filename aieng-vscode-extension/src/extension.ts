import * as vscode from "vscode";

import { BackendManager } from "./backendManager";
import { HomePanel } from "./homePanel";
import { backendUrl, chooseLiveProject } from "./livePreview";
import { readAiengPackage } from "./packageReader";
import { modifyPrompt, projectContextPrompt, starterPrompt } from "./prompts";
import type { WebviewToHostMessage } from "./protocol";
import { bindWebviewMessages, configureLiveWorkbenchWebview, configureWebview, postMessage } from "./webview";

class AiengDocument implements vscode.CustomDocument {
  constructor(readonly uri: vscode.Uri) {}
  dispose(): void {}
}

class AiengPreviewProvider implements vscode.CustomReadonlyEditorProvider<AiengDocument> {
  constructor(private readonly extensionUri: vscode.Uri) {}

  openCustomDocument(uri: vscode.Uri): AiengDocument {
    return new AiengDocument(uri);
  }

  async resolveCustomEditor(document: AiengDocument, panel: vscode.WebviewPanel): Promise<void> {
    configureWebview(panel.webview, this.extensionUri);
    const subscriptions: vscode.Disposable[] = [];
    let loading = false;
    const refresh = async () => {
      if (loading) return;
      loading = true;
      try {
        await postMessage(panel.webview, await readAiengPackage(document.uri));
      } catch (error) {
        await postMessage(panel.webview, {
          kind: "status",
          tone: "error",
          detail: error instanceof Error ? error.message : String(error),
        });
      } finally {
        loading = false;
      }
    };
    bindWebviewMessages(panel.webview, subscriptions, refresh, refresh);

    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(vscode.Uri.joinPath(document.uri, ".."), document.uri.path.split("/").pop() ?? "*.aieng"),
    );
    subscriptions.push(watcher);
    subscriptions.push(watcher.onDidChange(refresh));
    subscriptions.push(watcher.onDidCreate(refresh));
    subscriptions.push(panel.onDidDispose(() => subscriptions.splice(0).forEach((item) => item.dispose())));
  }
}

class LivePreviewPanel {
  private static current: LivePreviewPanel | undefined;

  static async open(
    extensionUri: vscode.Uri,
    backend: BackendManager,
    project?: { id: string; name?: string; status?: string; updated_at?: string; named_parts?: string[] },
  ): Promise<void> {
    const selectedProject = project ?? await chooseLiveProject();
    if (!selectedProject) return;
    if (LivePreviewPanel.current) {
      if (LivePreviewPanel.current.projectId !== selectedProject.id) {
        LivePreviewPanel.current.panel.dispose();
      } else {
        LivePreviewPanel.current.panel.reveal(vscode.ViewColumn.Beside);
        return;
      }
    }
    const panel = vscode.window.createWebviewPanel(
      "aieng.liveCadPreview",
      `AIENG: ${selectedProject.name || selectedProject.id}`,
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    LivePreviewPanel.current = new LivePreviewPanel(panel, extensionUri, backend, selectedProject.id, selectedProject.name || selectedProject.id);
  }

  private readonly subscriptions: vscode.Disposable[] = [];

  private constructor(
    readonly panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    private readonly backend: BackendManager,
    private readonly projectId: string,
    private readonly projectName: string,
  ) {
    // The live panel embeds the backend-served React workbench in an iframe, so
    // the model, panels, face-picking, and live refresh come from the single SPA
    // (no bespoke viewer, no payload plumbing). The shell only relays handoff.
    configureLiveWorkbenchWebview(panel.webview, backendUrl(), projectId, projectName);
    bindWebviewMessages(
      panel.webview,
      this.subscriptions,
      () => undefined,
      () => undefined,
      (message) => this.handlePreviewAction(message, extensionUri),
    );
    this.subscriptions.push(panel.onDidDispose(() => {
      this.subscriptions.splice(0).forEach((item) => item.dispose());
      LivePreviewPanel.current = undefined;
    }));
  }

  private async handlePreviewAction(message: WebviewToHostMessage, extensionUri: vscode.Uri): Promise<void> {
    if (message.kind === "copyStarterPrompt") {
      await this.copyPrompt(starterPrompt({ projectId: this.projectId, projectName: this.projectName }));
      return;
    }
    if (message.kind === "copyModifyPrompt") {
      await this.copyPrompt(modifyPrompt({ projectId: this.projectId, projectName: this.projectName, pointers: message.pointers }));
      return;
    }
    if (message.kind === "copyProjectContext") {
      await this.copyPrompt(projectContextPrompt({ projectId: this.projectId, projectName: this.projectName }));
      return;
    }
    if (message.kind === "openHome") {
      HomePanel.open(extensionUri, {
        openLiveProject: (project) => LivePreviewPanel.open(extensionUri, this.backend, project),
        openPackage,
        backend: this.backend,
      });
    }
  }

  private async copyPrompt(text: string): Promise<void> {
    await vscode.env.clipboard.writeText(text);
    vscode.window.setStatusBarMessage("AIENG: Copied agent handoff prompt", 2500);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const backend = new BackendManager();
  context.subscriptions.push(backend);
  const provider = new AiengPreviewProvider(context.extensionUri);
  context.subscriptions.push(vscode.window.registerCustomEditorProvider("aieng.cadPreview", provider, {
    supportsMultipleEditorsPerDocument: false,
  }));
  context.subscriptions.push(vscode.commands.registerCommand("aieng.openLivePreview", () => LivePreviewPanel.open(context.extensionUri, backend)));
  context.subscriptions.push(vscode.commands.registerCommand("aieng.openPackagePreview", openPackage));
  context.subscriptions.push(vscode.commands.registerCommand("aieng.openHome", () => HomePanel.open(context.extensionUri, {
    openLiveProject: (project) => LivePreviewPanel.open(context.extensionUri, backend, project),
    openPackage,
    backend,
  })));
}

export function deactivate(): void {}

async function openPackage(): Promise<void> {
  const selected = await vscode.window.showOpenDialog({
    canSelectMany: false,
    filters: { "AIENG package": ["aieng"] },
  });
  if (selected?.[0]) await vscode.commands.executeCommand("vscode.openWith", selected[0], "aieng.cadPreview");
}
