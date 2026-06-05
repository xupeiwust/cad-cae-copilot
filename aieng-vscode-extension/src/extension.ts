import * as vscode from "vscode";

import { chooseLiveProject, loadLivePreview, watchLiveProject } from "./livePreview";
import { readAiengPackage } from "./packageReader";
import type { PreviewPayload } from "./protocol";
import { bindWebviewMessages, configureWebview, postMessage } from "./webview";

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

  static async open(extensionUri: vscode.Uri): Promise<void> {
    if (LivePreviewPanel.current) {
      LivePreviewPanel.current.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }
    const project = await chooseLiveProject();
    if (!project) return;
    const panel = vscode.window.createWebviewPanel(
      "aieng.liveCadPreview",
      `AIENG: ${project.name || project.id}`,
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    LivePreviewPanel.current = new LivePreviewPanel(panel, extensionUri, project.id, project.name || project.id);
  }

  private readonly subscriptions: vscode.Disposable[] = [];
  private loading = false;

  private constructor(
    readonly panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    private readonly projectId: string,
    private readonly projectName: string,
  ) {
    configureWebview(panel.webview, extensionUri);
    bindWebviewMessages(panel.webview, this.subscriptions, () => this.refresh(), () => this.refresh());
    this.subscriptions.push(watchLiveProject(projectId, () => void this.refresh()));
    this.subscriptions.push(panel.onDidDispose(() => {
      this.subscriptions.splice(0).forEach((item) => item.dispose());
      LivePreviewPanel.current = undefined;
    }));
  }

  private async refresh(): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    try {
      const payload: PreviewPayload = await loadLivePreview({ id: this.projectId, name: this.projectName });
      await postMessage(this.panel.webview, payload);
    } catch (error) {
      await postMessage(this.panel.webview, {
        kind: "status",
        tone: "error",
        detail: error instanceof Error ? error.message : String(error),
      });
    } finally {
      this.loading = false;
    }
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const provider = new AiengPreviewProvider(context.extensionUri);
  context.subscriptions.push(vscode.window.registerCustomEditorProvider("aieng.cadPreview", provider, {
    supportsMultipleEditorsPerDocument: false,
  }));
  context.subscriptions.push(vscode.commands.registerCommand("aieng.openLivePreview", () => LivePreviewPanel.open(context.extensionUri)));
  context.subscriptions.push(vscode.commands.registerCommand("aieng.openPackagePreview", async () => {
    const selected = await vscode.window.showOpenDialog({
      canSelectMany: false,
      filters: { "AIENG package": ["aieng"] },
    });
    if (selected?.[0]) await vscode.commands.executeCommand("vscode.openWith", selected[0], "aieng.cadPreview");
  }));
}

export function deactivate(): void {}
