import type { AgentTranscriptEvent } from "./chatTranscript";

/**
 * MCP-first approval surface (issue #17).
 *
 * When an external MCP agent calls a gated tool, the workbench MCP server (in
 * managed-approval mode) blocks on the backend broker and emits an
 * `approval_requested` event into the live activity stream; the workbench viewer
 * renders a prompt and resolves it via `POST /api/agent/agentic/permission/{id}/resolve`.
 * This module is the pure projection of those events into the viewer's pending list.
 */
export type PendingApproval = {
  permissionId: string;
  toolName: string;
  projectId: string | null;
  explanation: string;
  codePreview: string | null;
};

function readPayload(event: AgentTranscriptEvent): Record<string, unknown> {
  const payload = (event as { payload?: unknown }).payload;
  return payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Fold one `approval_requested` / `approval_resolved` event into the pending list.
 * Pure: returns a new array. `approval_requested` appends (deduped by permissionId);
 * `approval_resolved` removes. Any other event (or one without a permission id) is a no-op.
 */
export function applyApprovalEvent(
  current: PendingApproval[],
  event: AgentTranscriptEvent,
): PendingApproval[] {
  const payload = readPayload(event);
  const permissionId = str(payload.agentic_permission_id);
  if (!permissionId) return current;

  if (event.type === "approval_resolved") {
    return current.filter((item) => item.permissionId !== permissionId);
  }
  if (event.type === "approval_requested") {
    if (current.some((item) => item.permissionId === permissionId)) return current;
    return [
      ...current,
      {
        permissionId,
        toolName: str(payload.tool_name) ?? "tool",
        projectId: str((event as { project_id?: unknown }).project_id) ?? str(payload.target_project_id),
        explanation: str(payload.explanation) ?? str((event as { content?: unknown }).content) ?? "",
        codePreview: str(payload.code_preview),
      },
    ];
  }
  return current;
}
