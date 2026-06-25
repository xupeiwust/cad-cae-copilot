import { EventSource } from "eventsource";
import * as vscode from "vscode";

import {
  projectActivityFromEvent,
  projectIdFromEvent,
  type ProjectActivityDiagnostic,
  type ProjectActivityEvent,
} from "./agentActivityModel";
import { backendUrl } from "./livePreview";

export { projectActivityFromEvent, projectIdFromEvent, type ProjectActivityEvent };

export class AgentActivitySubscriber implements vscode.Disposable {
  private source: EventSource | undefined;
  private readonly subscriptions: vscode.Disposable[] = [];
  private disposed = false;

  constructor(private readonly onProjectActivity: (event: ProjectActivityEvent) => Promise<void> | void) {
    this.connect();
    this.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("aieng.backendUrl")) this.reconnect();
    }));
  }

  dispose(): void {
    this.disposed = true;
    this.source?.close();
    this.source = undefined;
    this.subscriptions.splice(0).forEach((item) => item.dispose());
  }

  private connect(): void {
    if (this.disposed) return;
    try {
      const source = new EventSource(`${backendUrl()}/api/agent-activity/stream`);
      source.onmessage = (message) => {
        const event = projectActivityFromEvent(message.data);
        if (!event || !autoOpenPreviewEnabled()) return;
        if (event.diagnostic) {
          vscode.window.setStatusBarMessage(`AIENG: ${formatDiagnostic(event.diagnostic)}`, 7000);
        }
        void Promise.resolve(this.onProjectActivity(event)).catch((error) => {
          console.warn("AIENG: Could not auto-open live preview from agent activity.", error);
        });
      };
      this.source = source;
    } catch (error) {
      console.warn("AIENG: Could not subscribe to backend agent activity.", error);
    }
  }

  private reconnect(): void {
    this.source?.close();
    this.source = undefined;
    this.connect();
  }
}

function autoOpenPreviewEnabled(): boolean {
  return vscode.workspace.getConfiguration("aieng").get<boolean>("autoOpenPreviewOnActivity", true);
}

function formatDiagnostic(diagnostic: ProjectActivityDiagnostic): string {
  const message = diagnostic.remediation || diagnostic.message;
  return `${diagnostic.code}: ${message}`;
}
