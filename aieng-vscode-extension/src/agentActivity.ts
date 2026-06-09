import { EventSource } from "eventsource";
import * as vscode from "vscode";

import { backendUrl } from "./livePreview";

type AgentActivityEvent = {
  type?: unknown;
  project_id?: unknown;
};

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

export function projectIdFromEvent(data: unknown): string | undefined {
  return projectActivityFromEvent(data)?.projectId;
}

export type ProjectActivityEvent = {
  type: string;
  projectId: string;
};

export function projectActivityFromEvent(data: unknown): ProjectActivityEvent | undefined {
  if (typeof data !== "string") return undefined;
  try {
    const event = JSON.parse(data) as AgentActivityEvent;
    if (typeof event.project_id !== "string" || !event.project_id.trim()) return undefined;
    return {
      type: typeof event.type === "string" ? event.type : "",
      projectId: event.project_id.trim(),
    };
  } catch {
    return undefined;
  }
}
