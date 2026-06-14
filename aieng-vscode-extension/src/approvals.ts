import { EventSource } from "eventsource";
import * as vscode from "vscode";

import { backendUrl } from "./livePreview";

/**
 * In-editor approval surface (#230).
 *
 * In workbench-managed approval mode the backend fans out each gated mutation as
 * an `approval_requested` agent event on `/api/agent-activity/stream`; a
 * connected surface must render it and POST the decision back. This coordinator
 * makes the VS Code extension that surface: it subscribes to the stream, shows a
 * native modal for each request, and resolves it via
 * `POST /api/agent/agentic/permission/{id}/resolve` — so a user driving an
 * agentic session can approve/deny gated CAD/CAE mutations without leaving the
 * editor. Being subscribed also makes `approval-surface` report available, so
 * managed-mode calls no longer fail fast for want of a viewer.
 */

export type ApprovalRequest = {
  permissionId: string;
  toolName: string;
  explanation: string;
  codePreview?: string;
  projectId?: string;
};

/** Parse an `approval_requested` SSE event into a request, or null. Pure. */
export function parseApprovalEvent(data: unknown): ApprovalRequest | null {
  if (typeof data !== "string") return null;
  let event: Record<string, unknown>;
  try {
    event = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
  if (!event || typeof event !== "object" || event.type !== "approval_requested") return null;
  const payload = (event.payload && typeof event.payload === "object" ? event.payload : {}) as Record<string, unknown>;
  const permissionId = String(payload.agentic_permission_id ?? payload.id ?? "").trim();
  if (!permissionId) return null;
  const toolName = String(payload.tool_name ?? "a workbench tool");
  const explanation = String(payload.explanation ?? event.content ?? `Approve ${toolName}?`);
  const codePreview = typeof payload.code_preview === "string" ? payload.code_preview : undefined;
  const eventProject = typeof event.project_id === "string" ? event.project_id.trim() : "";
  const payloadProject = typeof payload.target_project_id === "string" ? payload.target_project_id.trim() : "";
  const projectId = eventProject || payloadProject || undefined;
  return { permissionId, toolName, explanation, codePreview, projectId };
}

/** Extract the permission id from an `approval_resolved` event, or null. Pure. */
export function parseApprovalResolvedId(data: unknown): string | null {
  if (typeof data !== "string") return null;
  try {
    const event = JSON.parse(data) as Record<string, unknown>;
    if (!event || event.type !== "approval_resolved") return null;
    const payload = (event.payload && typeof event.payload === "object" ? event.payload : {}) as Record<string, unknown>;
    const id = String(payload.agentic_permission_id ?? "").trim();
    return id || null;
  } catch {
    return null;
  }
}

/** Build the resolve POST body. Pure. */
export function decisionBody(approved: boolean, projectId?: string, message?: string): Record<string, unknown> {
  const body: Record<string, unknown> = { approved };
  if (projectId) body.project_id = projectId;
  if (message) body.message = message;
  return body;
}

/** Truncate a code preview so the modal stays readable. Pure. */
export function truncatePreview(text: string, max = 1200): string {
  return text.length > max ? `${text.slice(0, max)}\n...(truncated)` : text;
}

async function postApprovalDecision(
  permissionId: string,
  approved: boolean,
  projectId?: string,
  message?: string,
): Promise<void> {
  const response = await fetch(
    `${backendUrl()}/api/agent/agentic/permission/${encodeURIComponent(permissionId)}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decisionBody(approved, projectId, message)),
    },
  );
  if (!response.ok) throw new Error(`resolve failed: ${response.status}`);
}

export class ApprovalCoordinator implements vscode.Disposable {
  private source: EventSource | undefined;
  private readonly seen = new Set<string>();
  private readonly subscriptions: vscode.Disposable[] = [];
  private disposed = false;

  constructor() {
    this.connect();
    this.subscriptions.push(
      vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration("aieng.backendUrl")) this.reconnect();
      }),
    );
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
      source.onmessage = (message) => this.handle(message.data);
      this.source = source;
    } catch (error) {
      console.warn("AIENG: could not subscribe to backend for approvals.", error);
    }
  }

  private reconnect(): void {
    this.source?.close();
    this.source = undefined;
    this.seen.clear();
    this.connect();
  }

  private handle(data: unknown): void {
    const resolvedId = parseApprovalResolvedId(data);
    if (resolvedId) {
      // Resolved elsewhere (e.g. the web viewer) — drop it so we don't re-prompt.
      this.seen.delete(resolvedId);
      return;
    }
    const request = parseApprovalEvent(data);
    if (!request || this.seen.has(request.permissionId)) return;
    this.seen.add(request.permissionId);
    void this.prompt(request);
  }

  private async prompt(request: ApprovalRequest): Promise<void> {
    const detail = request.codePreview
      ? `${request.explanation}\n\n${truncatePreview(request.codePreview)}`
      : request.explanation;
    const choice = await vscode.window.showInformationMessage(
      `AIENG approval: ${request.toolName}`,
      { modal: true, detail },
      "Approve",
      "Deny",
    );
    // No explicit Approve → deny (fail-safe; a dismissed modal never auto-allows).
    const approved = choice === "Approve";
    try {
      await postApprovalDecision(
        request.permissionId,
        approved,
        request.projectId,
        approved ? undefined : "Denied in VS Code.",
      );
      vscode.window.setStatusBarMessage(
        `AIENG: ${approved ? "Approved" : "Denied"} ${request.toolName}`,
        2500,
      );
    } catch (error) {
      vscode.window.showErrorMessage(
        `AIENG: could not submit approval decision: ${error instanceof Error ? error.message : String(error)}`,
      );
      // Allow a retry if the next matching event arrives.
      this.seen.delete(request.permissionId);
    }
  }
}
