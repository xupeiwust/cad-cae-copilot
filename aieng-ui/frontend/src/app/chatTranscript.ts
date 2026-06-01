import type { PersistedChatMessage } from "../api";
import type { ChatHistoryItem } from "../appTypes";
import type { AutopilotObservation, AutopilotRunState } from "../types";

export type TranscriptStatus = "pending" | "running" | "done" | "failed" | "blocked" | "approval" | "queued";

type TranscriptBase = {
  id: string;
  sourceId: string;
  kind: "message" | "tool" | "approval" | "artifact" | "status" | "error";
  runId?: string | null;
  sessionId?: string | null;
  projectId?: string | null;
  createdAt: string;
  detail?: unknown;
};

export type TranscriptUserMessage = TranscriptBase & {
  kind: "message";
  role: "user";
  text: string;
  status?: TranscriptStatus;
};

export type TranscriptAgentMessage = TranscriptBase & {
  kind: "message";
  role: "agent";
  text: string;
};

export type TranscriptToolLine = TranscriptBase & {
  kind: "tool";
  status: TranscriptStatus;
  toolName: string;
  summary: string;
  elapsedMs?: number | null;
};

export type TranscriptApprovalLine = TranscriptBase & {
  kind: "approval";
  status: "approval";
  toolName: string;
  summary: string;
  sideEffectSummary?: string | null;
  riskSummary?: string | null;
  targetProjectId?: string | null;
  codePreview?: string | null;
  artifactPreview?: string | null;
  recommendedAction?: string | null;
};

export type TranscriptArtifactLine = TranscriptBase & {
  kind: "artifact";
  status: TranscriptStatus;
  summary: string;
  previewUrl?: string | null;
  previewFormat?: string | null;
  artifactPaths?: string[];
  namedParts?: string[];
  partsAdded?: string[];
};

export type TranscriptStatusLine = TranscriptBase & {
  kind: "status";
  status: TranscriptStatus;
  summary: string;
};

export type TranscriptErrorLine = TranscriptBase & {
  kind: "error";
  status: "failed";
  summary: string;
};

export type ChatTranscriptItem =
  | TranscriptUserMessage
  | TranscriptAgentMessage
  | TranscriptToolLine
  | TranscriptApprovalLine
  | TranscriptArtifactLine
  | TranscriptStatusLine
  | TranscriptErrorLine;

export type AgentTranscriptEvent = {
  event_id?: string;
  type: string;
  run_id?: string | null;
  project_id?: string | null;
  session_id?: string | null;
  status?: string | null;
  content?: string | null;
  payload?: Record<string, unknown> | null;
  created_at?: string;
  ts?: number;
  [key: string]: unknown;
};

export function runToTranscriptItems(
  run: AutopilotRunState,
  options: { includeUserMessage?: boolean } = {},
): ChatTranscriptItem[] {
  const items: ChatTranscriptItem[] = [];
  const createdAt = safeDate(run.created_at);
  const base = {
    runId: run.run_id,
    sessionId: run.session_id ?? null,
    projectId: run.project_id ?? null,
  };

  if (options.includeUserMessage) {
    items.push({
      ...base,
      id: `run-${run.run_id}-user`,
      sourceId: `run:${run.run_id}:message`,
      kind: "message",
      role: "user",
      text: run.message,
      createdAt,
    });
  }

  for (const [index, obs] of run.observations.entries()) {
    items.push(...observationToTranscriptItems(run, obs, index));
  }

  if (run.pending_approval) {
    const sourceId = `run:${run.run_id}:approval:${run.pending_approval.id}`;
    if (!items.some((item) => item.sourceId === sourceId)) {
      items.push(approvalToTranscriptItem(run, run.pending_approval, sourceId));
    }
  }

  if (run.final_message) {
    const sourceId = `run:${run.run_id}:final-message`;
    if (!items.some((item) => item.sourceId === sourceId)) {
      const alreadyInObs = items.some(
        (item) => item.kind === "message" && item.role === "agent" && item.text === run.final_message,
      );
      if (!alreadyInObs) {
        items.push({
          ...base,
          id: sourceId,
          sourceId,
          kind: "message",
          role: "agent",
          text: run.final_message,
          createdAt: safeDate(run.updated_at || run.created_at),
        });
      }
    }
  }

  for (const [index, err] of run.errors.entries()) {
    items.push({
      ...base,
      id: `run-${run.run_id}-error-${index}`,
      sourceId: `run:${run.run_id}:error:${index}:${err}`,
      kind: "error",
      status: "failed",
      summary: err,
      createdAt: safeDate(run.updated_at || run.created_at),
    });
  }

  return dedupeAndSort(dedupeAgentMessagesByText(items));
}

export function chatHistoryToTranscriptItems(
  chatHistory: ChatHistoryItem[],
  agentEvents: AgentTranscriptEvent[] = [],
): ChatTranscriptItem[] {
  const items: ChatTranscriptItem[] = [];
  const seenRunIds = new Set<string>();
  const runStatusById = new Map<string, string>();

  for (const entry of chatHistory) {
    const base = {
      sessionId: null,
      projectId: null,
      createdAt: safeDate(entry.createdAt),
    };
    if (entry.body.trim() && !entry.autopilotRun) {
      items.push({
        ...base,
        id: `message-${entry.id}`,
        sourceId: `chat:${entry.id}`,
        kind: "message",
        role: entry.role === "user" ? "user" : "agent",
        text: entry.body,
        detail: entry,
      });
    } else if (entry.role === "user") {
      items.push({
        ...base,
        id: `message-${entry.id}`,
        sourceId: `chat:${entry.id}`,
        kind: "message",
        role: "user",
        text: entry.body,
        detail: entry,
      });
    }

    if (entry.autopilotRun && !seenRunIds.has(entry.autopilotRun.run_id)) {
      runStatusById.set(entry.autopilotRun.run_id, entry.autopilotRun.status);
      seenRunIds.add(entry.autopilotRun.run_id);
      items.push(...runToTranscriptItems(entry.autopilotRun));
    } else if (entry.autopilotRun) {
      runStatusById.set(entry.autopilotRun.run_id, entry.autopilotRun.status);
    }

    items.push(...legacyArtifactsToTranscriptItems(entry));
  }

  for (const event of agentEvents) {
    const runId = event.run_id ?? stringValue(objectValue(event.payload).run_id);
    const status = event.type === "run_cancelled"
      ? "cancelled"
      : event.status ?? stringValue(objectValue(event.payload).status);
    if (runId && status && terminalTranscriptStatus(status)) {
      runStatusById.set(runId, status);
    }
    items.push(...agentEventToTranscriptItems(event));
  }

  return dedupeAndSort(
    collapseProgressRows(
      normalizeTerminalRunRows(
        dedupeSnapshotRowsCoveredByEvents(items),
        runStatusById,
      ),
    ),
  );
}

export function persistedMessageToTranscriptItems(message: PersistedChatMessage): ChatTranscriptItem[] {
  const text = message.content.trim();
  if (!text) return [];
  return [{
    id: `db-message-${message.id}`,
    sourceId: `db-chat:${message.id}`,
    kind: "message",
    role: message.role === "user" ? "user" : "agent",
    text,
    sessionId: message.session_id ?? null,
    projectId: message.project_id,
    createdAt: safeDate(message.created_at),
    detail: message,
  }];
}

export function agentEventToTranscriptItems(event: AgentTranscriptEvent): ChatTranscriptItem[] {
  const payload = event.payload && typeof event.payload === "object" ? event.payload : event;
  const eventId = event.event_id || stringValue(payload.event_id) || `${event.type}:${event.run_id ?? ""}:${event.ts ?? event.created_at ?? ""}`;
  const createdAt = safeDate(event.created_at || (typeof event.ts === "number" ? new Date(event.ts * 1000).toISOString() : undefined));
  const base = {
    id: `event-${eventId}`,
    sourceId: `event:${eventId}`,
    runId: event.run_id ?? stringValue(payload.run_id),
    sessionId: event.session_id ?? stringValue(payload.session_id),
    projectId: event.project_id ?? stringValue(payload.project_id),
    createdAt,
    detail: event,
  };

  switch (event.type) {
    case "agent_message":
      return [{
        ...base,
        kind: "message",
        role: "agent",
        text: event.content || stringValue(payload.message) || stringValue(payload.summary) || "Agent message",
      }];
    case "tool_started":
      return [{
        ...base,
        kind: "tool",
        status: "running",
        toolName: stringValue(payload.tool_name) || stringValue(payload.tool) || "tool",
        summary: event.content || stringValue(payload.summary) || "Running tool",
      }];
    case "tool_completed":
      {
        const artifact = outputToArtifactLine(base, payload, "done");
        return artifact ? [artifact] : [{
          ...base,
          kind: "tool",
          status: payload.status === "error" ? "failed" : "done",
          toolName: stringValue(payload.tool_name) || stringValue(payload.tool) || "tool",
          summary: event.content || stringValue(payload.summary) || "Tool completed",
        }];
      }
    case "tool_failed":
      return [{
        ...base,
        kind: "tool",
        status: "failed",
        toolName: stringValue(payload.tool_name) || stringValue(payload.tool) || "tool",
        summary: event.content || stringValue(payload.summary) || stringValue(payload.error) || "Tool failed",
      }];
    case "approval_requested":
      return [{
        ...base,
        kind: "approval",
        status: "approval",
        toolName: stringValue(payload.tool_name) || "tool",
        summary: event.content || stringValue(payload.explanation) || "Review before applying changes",
        sideEffectSummary: stringValue(payload.side_effect_summary),
        riskSummary: stringValue(payload.risk_summary),
        targetProjectId: stringValue(payload.target_project_id),
        codePreview: stringValue(payload.code_preview),
        artifactPreview: stringValue(payload.artifact_preview),
        recommendedAction: stringValue(payload.recommended_action),
      }];
    case "artifact_ready":
    case "viewer_asset_changed":
      return [artifactLineFromPayload(base, payload, event.content || "Viewer refreshed")];
    case "run_cancelled":
      return [{
        ...base,
        kind: "status",
        status: "blocked",
        summary: event.content || "Run cancelled",
      }];
    case "run_status_changed":
      return [{
        ...base,
        kind: "status",
        status: normalizeStatus(event.status || stringValue(payload.status)),
        summary: event.content || `Run ${event.status || payload.status || "updated"}`,
      }];
    default:
      return [];
  }
}

function observationToTranscriptItems(run: AutopilotRunState, obs: AutopilotObservation, index: number): ChatTranscriptItem[] {
  const sourceId = `run:${run.run_id}:obs:${obs.id || index}`;
  const base = {
    id: `run-${run.run_id}-obs-${obs.id || index}`,
    sourceId,
    runId: run.run_id,
    sessionId: run.session_id ?? null,
    projectId: run.project_id ?? null,
    createdAt: safeDate(obs.created_at || run.created_at),
    detail: obs,
  };
  const toolName = stringValue(obs.data?.tool_name);
  if (obs.kind === "context") {
    return [{ ...base, kind: "status", status: "done", summary: obs.summary }];
  }
  if (obs.kind === "agent_activity") {
    const isRunActive = run.status === "running";
    if (toolName) {
      return [{ ...base, kind: "tool", status: isRunActive ? "running" : "done", toolName, summary: obs.summary }];
    }
    return [{ ...base, kind: "status", status: isRunActive ? "running" : "done", summary: obs.summary }];
  }
  if (obs.kind === "tool_result") {
    const artifact = outputToArtifactLine(base, obs.data, "done");
    return [
      { ...base, kind: "tool", status: "done", toolName: toolName || "tool", summary: obs.summary },
      ...(artifact ? [artifact] : []),
    ];
  }
  if (obs.kind === "tool_error") {
    return [{ ...base, kind: "tool", status: "failed", toolName: toolName || "tool", summary: obs.summary }];
  }
  if (obs.kind === "approval_required") {
    return [approvalToTranscriptItem(run, obs.data, sourceId, obs)];
  }
  if (obs.kind === "agent_thought") {
    return [{ ...base, kind: "message", role: "agent", text: obs.summary }];
  }
  if (obs.kind === "user_message") {
    return [{ ...base, kind: "message", role: "agent", text: obs.summary }];
  }
  if (obs.kind === "final") {
    return [{ ...base, kind: "message", role: "agent", text: obs.summary }];
  }
  if (obs.kind === "policy_block") {
    return [{ ...base, kind: "status", status: "blocked", summary: obs.summary }];
  }
  return [{ ...base, kind: "status", status: normalizeStatus(run.status), summary: obs.summary }];
}

function approvalToTranscriptItem(
  run: AutopilotRunState,
  approvalLike: unknown,
  sourceId: string,
  detail?: unknown,
): TranscriptApprovalLine {
  const approval = objectValue(approvalLike);
  return {
    id: sourceId.replaceAll(":", "-"),
    sourceId,
    kind: "approval",
    status: "approval",
    runId: run.run_id,
    sessionId: run.session_id ?? null,
    projectId: run.project_id ?? null,
    createdAt: safeDate(stringValue(approval.created_at) || run.updated_at || run.created_at),
    toolName: stringValue(approval.tool_name) || "tool",
    summary: stringValue(approval.explanation) || "Review before applying changes",
    sideEffectSummary: stringValue(approval.side_effect_summary),
    riskSummary: stringValue(approval.risk_summary),
    targetProjectId: stringValue(approval.target_project_id),
    codePreview: stringValue(approval.code_preview) || stringValue(objectValue(approval.input).code),
    artifactPreview: stringValue(approval.artifact_preview),
    recommendedAction: stringValue(approval.recommended_action),
    detail: detail ?? approval,
  };
}

function legacyArtifactsToTranscriptItems(entry: ChatHistoryItem): ChatTranscriptItem[] {
  const createdAt = safeDate(entry.createdAt);
  const base = {
    runId: entry.autopilotRun?.run_id ?? null,
    sessionId: null,
    projectId: null,
    createdAt,
    detail: entry,
  };
  const items: ChatTranscriptItem[] = [];
  if (entry.artifactPaths?.length) {
    items.push({
      ...base,
      id: `legacy-artifacts-${entry.id}`,
      sourceId: `legacy:${entry.id}:artifact-paths`,
      kind: "artifact",
      status: "done",
      summary: `${entry.artifactPaths.length} artifact${entry.artifactPaths.length === 1 ? "" : "s"} changed`,
      artifactPaths: entry.artifactPaths,
    });
  }
  if (entry.cadResult) {
    items.push({
      ...base,
      id: `legacy-cad-${entry.id}`,
      sourceId: `legacy:${entry.id}:cad`,
      kind: "artifact",
      status: "done",
      summary: `CAD result ready: ${entry.cadResult.face_count} faces, ${entry.cadResult.feature_count} features`,
    });
  }
  if (entry.simulationResult) {
    items.push({
      ...base,
      id: `legacy-sim-${entry.id}`,
      sourceId: `legacy:${entry.id}:simulation`,
      kind: "artifact",
      status: entry.simulationResult.status === "completed" ? "done" : "failed",
      summary: entry.simulationResult.message || `Simulation ${entry.simulationResult.status}`,
      artifactPaths: entry.simulationResult.written_artifacts,
    });
  }
  if (entry.preprocessResult) {
    items.push({
      ...base,
      id: `legacy-preprocess-${entry.id}`,
      sourceId: `legacy:${entry.id}:preprocess`,
      kind: "artifact",
      status: "done",
      summary: `CAE setup drafted: ${entry.preprocessResult.bc_count} BCs, ${entry.preprocessResult.load_count} loads`,
      artifactPaths: entry.preprocessResult.written_artifacts,
    });
  }
  return items;
}

function outputToArtifactLine(
  base: Omit<TranscriptArtifactLine, "kind" | "status" | "summary" | "sourceId" | "id"> & { sourceId: string; id: string },
  payload: Record<string, unknown>,
  status: TranscriptStatus,
): TranscriptArtifactLine | null {
  const output = objectValue(payload.output) || payload;
  const namedParts = stringArray(output.named_parts);
  const partsAdded = stringArray(output.parts_added);
  const artifactPaths = stringArray(output.artifact_paths).concat(stringArray(output.written_artifacts));
  const previewUrl = stringValue(output.preview_url) || stringValue(payload.preview_url);
  const previewFormat = stringValue(output.preview_format) || stringValue(payload.preview_format);
  const solverRunId = stringValue(output.solver_run_id) || stringValue(output.run_id);
  const resultSummary = stringValue(output.result_summary) || stringValue(output.message);
  if (!namedParts.length && !partsAdded.length && !artifactPaths.length && !previewUrl && !solverRunId && !resultSummary) {
    return null;
  }
  return artifactLineFromPayload(
    {
      ...base,
      sourceId: `${base.sourceId}:artifact`,
      id: `${base.id}-artifact`,
    },
    { ...output, preview_url: previewUrl, preview_format: previewFormat, artifact_paths: artifactPaths, named_parts: namedParts, parts_added: partsAdded },
    resultSummary || artifactSummary({ namedParts, partsAdded, artifactPaths, solverRunId, previewUrl }),
    status,
  );
}

function artifactLineFromPayload(
  base: Omit<TranscriptArtifactLine, "kind" | "status" | "summary">,
  payload: Record<string, unknown>,
  summary: string,
  status: TranscriptStatus = "done",
): TranscriptArtifactLine {
  return {
    ...base,
    kind: "artifact",
    status,
    summary,
    previewUrl: stringValue(payload.preview_url),
    previewFormat: stringValue(payload.preview_format),
    artifactPaths: stringArray(payload.artifact_paths).concat(stringArray(payload.written_artifacts)),
    namedParts: stringArray(payload.named_parts),
    partsAdded: stringArray(payload.parts_added),
  };
}

function artifactSummary({
  namedParts,
  partsAdded,
  artifactPaths,
  solverRunId,
  previewUrl,
}: {
  namedParts: string[];
  partsAdded: string[];
  artifactPaths: string[];
  solverRunId?: string | null;
  previewUrl?: string | null;
}) {
  if (partsAdded.length) return `CAD updated: ${partsAdded.length} part${partsAdded.length === 1 ? "" : "s"} added`;
  if (namedParts.length) return `CAD ready: ${namedParts.length} named part${namedParts.length === 1 ? "" : "s"}`;
  if (solverRunId) return `Solver result ready: ${solverRunId}`;
  if (artifactPaths.length) return `${artifactPaths.length} artifact${artifactPaths.length === 1 ? "" : "s"} ready`;
  if (previewUrl) return "Viewer preview ready";
  return "Artifact ready";
}

function normalizeStatus(status?: string | null): TranscriptStatus {
  if (status === "completed" || status === "ok" || status === "done") return "done";
  if (status === "failed" || status === "error") return "failed";
  if (status === "blocked" || status === "cancelled") return "blocked";
  if (status === "awaiting_approval" || status === "approval") return "approval";
  if (status === "queued") return "queued";
  return "running";
}

function terminalTranscriptStatus(runStatus?: string | null): TranscriptStatus | null {
  if (runStatus === "completed") return "done";
  if (runStatus === "failed") return "failed";
  if (runStatus === "cancelled" || runStatus === "blocked") return "blocked";
  return null;
}

function normalizeTerminalRunRows(
  items: ChatTranscriptItem[],
  runStatusById: Map<string, string>,
): ChatTranscriptItem[] {
  return items.map((item) => {
    if (
      (item.kind !== "tool" && item.kind !== "status" && item.kind !== "artifact") ||
      item.status !== "running" ||
      !item.runId
    ) {
      return item;
    }
    const terminal = terminalTranscriptStatus(runStatusById.get(item.runId));
    if (!terminal) return item;
    return { ...item, status: terminal };
  });
}

function collapseProgressRows(items: ChatTranscriptItem[]): ChatTranscriptItem[] {
  const latestByProgressKey = new Map<string, string>();
  for (const item of items) {
    const key = progressRowKey(item);
    if (!key) continue;
    latestByProgressKey.set(key, item.sourceId);
  }
  if (!latestByProgressKey.size) return items;
  return items.filter((item) => {
    const key = progressRowKey(item);
    return !key || latestByProgressKey.get(key) === item.sourceId;
  });
}

function progressRowKey(item: ChatTranscriptItem): string | null {
  if (item.kind !== "tool" && item.kind !== "status") return null;
  const run = item.runId || "";
  if (!run) return null;
  const detail = objectValue(item.detail);
  const payload = objectValue(detail.payload);
  const data = objectValue(detail.data);
  const isProgress = payload.progress_event === true || data.progress_event === true;
  if (!isProgress) return null;
  const phase = stringValue(payload.phase) || stringValue(data.phase) || item.summary;
  return `${run}:progress:${phase}`;
}

/**
 * Remove duplicate agent messages within the same run by text content.
 * Preserves the first occurrence (usually from an observation).
 */
function dedupeAgentMessagesByText(items: ChatTranscriptItem[]): ChatTranscriptItem[] {
  const seenAgentTexts = new Set<string>();
  return items.filter((item) => {
    if (item.kind === "message" && item.role === "agent") {
      if (seenAgentTexts.has(item.text)) return false;
      seenAgentTexts.add(item.text);
    }
    return true;
  });
}

function dedupeSnapshotRowsCoveredByEvents(items: ChatTranscriptItem[]): ChatTranscriptItem[] {
  const eventKeys = new Set<string>();
  for (const item of items) {
    if (!item.sourceId.startsWith("event:")) continue;
    const key = comparableActivityKey(item);
    if (key) eventKeys.add(key);
  }
  if (!eventKeys.size) return items;
  return items.filter((item) => {
    if (item.sourceId.startsWith("event:")) return true;
    const key = comparableActivityKey(item);
    return !key || !eventKeys.has(key);
  });
}

function comparableActivityKey(item: ChatTranscriptItem): string | null {
  const run = item.runId || "";
  if (!run) return null;
  if (item.kind === "message" && item.role === "agent") {
    return `${run}:message:${item.text}`;
  }
  if (item.kind === "tool") {
    return `${run}:tool:${item.toolName}:${item.summary}`;
  }
  if (item.kind === "status") {
    return `${run}:status:${item.summary}`;
  }
  if (item.kind === "approval") {
    return `${run}:approval:${item.toolName}:${item.summary}`;
  }
  if (item.kind === "artifact") {
    return `${run}:artifact:${item.summary}`;
  }
  return null;
}

function dedupeAndSort(items: ChatTranscriptItem[]): ChatTranscriptItem[] {
  const seen = new Set<string>();
  return items
    .filter((item) => {
      if (seen.has(item.sourceId)) return false;
      seen.add(item.sourceId);
      return true;
    })
    .sort((a, b) => {
      const time = Date.parse(a.createdAt) - Date.parse(b.createdAt);
      return time || a.sourceId.localeCompare(b.sourceId);
    });
}

function safeDate(value?: string | null): string {
  if (value && Number.isFinite(Date.parse(value))) return value;
  return new Date().toISOString();
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
}
