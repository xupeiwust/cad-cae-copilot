import * as vscode from "vscode";

import type { BackendManager } from "./backendManager";
import { backendUrl, createProject, listProjects, type Project } from "./livePreview";
import { detectAgentMcp } from "./mcpStatus";
import { modifyPrompt, projectContextPrompt, starterPrompt } from "./prompts";
import type { HomeProject, HomeStateMessage, HomeToWebviewMessage, HomeWebviewMessage } from "./protocol";
import { configureWebview } from "./webview";

type HomeActions = {
  openLiveProject(project?: Project): Promise<void> | void;
  openPackage(): Promise<void> | void;
  backend: BackendManager;
};

export class HomePanel {
  private static current: HomePanel | undefined;

  static open(extensionUri: vscode.Uri, actions: HomeActions): void {
    if (HomePanel.current) {
      HomePanel.current.panel.reveal(vscode.ViewColumn.One);
      void HomePanel.current.refresh();
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "aieng.home",
      "AIENG Home",
      vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    HomePanel.current = new HomePanel(panel, extensionUri, actions);
  }

  private readonly subscriptions: vscode.Disposable[] = [];

  private constructor(
    private readonly panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    private readonly actions: HomeActions,
  ) {
    configureWebview(panel.webview, extensionUri, "home.js");
    this.subscriptions.push(panel.webview.onDidReceiveMessage((message: HomeWebviewMessage) => {
      void this.handleMessage(message);
    }));
    this.subscriptions.push(panel.onDidDispose(() => {
      this.subscriptions.splice(0).forEach((item) => item.dispose());
      HomePanel.current = undefined;
    }));
  }

  private async handleMessage(message: HomeWebviewMessage): Promise<void> {
    if (message.kind === "ready" || message.kind === "retry") {
      await this.refresh();
      return;
    }
    if (message.kind === "startBackend") {
      await this.startBackend();
      return;
    }
    if (message.kind === "stopBackend") {
      this.actions.backend.stop();
      await this.refresh();
      return;
    }
    if (message.kind === "openPackage") {
      await this.actions.openPackage();
      return;
    }
    if (message.kind === "copyHomePrompt") {
      await this.copy(message.text);
      return;
    }
    if (message.kind === "openLiveProject") {
      const projects = await this.safeProjects();
      const project = message.projectId ? projects.find((item) => item.id === message.projectId) : undefined;
      await this.actions.openLiveProject(project);
      return;
    }
    if (message.kind === "createProject") {
      await this.createBlankProject();
      return;
    }
    if (message.kind === "copyStarterPrompt") {
      await this.copy(starterPrompt(message));
      return;
    }
    if (message.kind === "copyModifyPrompt") {
      await this.copy(modifyPrompt(message));
      return;
    }
    if (message.kind === "copyProjectContext") {
      await this.copy(projectContextPrompt(message));
    }
  }

  private async createBlankProject(): Promise<void> {
    await this.post({ kind: "homeBusy", busy: true, detail: "Creating blank AIENG project..." });
    try {
      const project = await createProject("Untitled project");
      await this.post({ kind: "homeToast", tone: "info", detail: `Created ${project.name || project.id}` });
      await this.refresh();
      await this.actions.openLiveProject(project);
    } catch (error) {
      await this.post({
        kind: "homeToast",
        tone: "error",
        detail: error instanceof Error ? error.message : String(error),
      });
    } finally {
      await this.post({ kind: "homeBusy", busy: false });
    }
  }

  private async refresh(): Promise<void> {
    await this.post({ kind: "homeBusy", busy: true, detail: "Checking AIENG backend..." });
    const agentMcp = detectAgentMcp();
    try {
      const projects = await listProjects();
      const backend = this.actions.backend.state();
      const state: HomeStateMessage = {
        kind: "homeState",
        backendUrl: backendUrl(),
        status: "connected",
        backendMode: backend.running ? "managed" : "external",
        projects: projects.slice(0, 8).map(toHomeProject),
        detail: projects.length
          ? backend.running ? "Connected to managed backend" : "Connected to existing backend"
          : backend.running ? "Managed backend running - no projects yet" : "Connected to backend - no projects yet",
        startCommand: backend.commandLine,
        agentMcp,
      };
      await this.post(state);
    } catch (error) {
      const backend = this.actions.backend.state();
      await this.post({
        kind: "homeState",
        backendUrl: backendUrl(),
        status: "unreachable",
        backendMode: backend.running ? "managed" : "stopped",
        projects: [],
        detail: backend.lastMessage || (error instanceof Error ? error.message : String(error)),
        startCommand: backend.commandLine,
        agentMcp,
      });
    } finally {
      await this.post({ kind: "homeBusy", busy: false });
    }
  }

  private async startBackend(): Promise<void> {
    await this.post({ kind: "homeBusy", busy: true, detail: "Starting AIENG backend..." });
    try {
      await this.actions.backend.start();
      await this.waitForBackend();
      await this.refresh();
      await this.post({ kind: "homeToast", tone: "info", detail: "AIENG backend is running" });
    } catch (error) {
      await this.post({
        kind: "homeToast",
        tone: "error",
        detail: error instanceof Error ? error.message : String(error),
      });
      await this.refresh();
    } finally {
      await this.post({ kind: "homeBusy", busy: false });
    }
  }

  private async waitForBackend(): Promise<void> {
    const deadline = Date.now() + 15000;
    let lastError: unknown;
    while (Date.now() < deadline) {
      try {
        await listProjects();
        return;
      } catch (error) {
        lastError = error;
        await new Promise((resolve) => setTimeout(resolve, 650));
      }
    }
    throw lastError instanceof Error ? lastError : new Error("Backend did not become reachable in time.");
  }

  private async safeProjects(): Promise<Project[]> {
    try {
      return await listProjects();
    } catch {
      return [];
    }
  }

  private async copy(text: string): Promise<void> {
    await vscode.env.clipboard.writeText(text);
    vscode.window.setStatusBarMessage("AIENG: Copied agent handoff prompt", 2500);
    await this.post({ kind: "homeToast", tone: "info", detail: "Copied prompt to clipboard" });
  }

  private async post(message: HomeToWebviewMessage): Promise<void> {
    await this.panel.webview.postMessage(message);
  }
}

function toHomeProject(project: Project): HomeProject {
  return {
    id: project.id,
    name: project.name || project.id,
    status: project.status,
    updatedAt: project.updated_at,
    namedParts: project.named_parts ?? [],
  };
}
