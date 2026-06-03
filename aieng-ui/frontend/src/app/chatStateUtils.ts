import type { PersistedAgentEvent, PersistedChatMessage } from "../api";
import type { ChatHistoryItem } from "../appTypes";
import type { AutopilotRunState } from "../types";
import type { AgentTranscriptEvent } from "./chatTranscript";
import { summarizeAutopilotRun } from "./workbenchHelpers";

export function chatItemExtra(item: ChatHistoryItem): Record<string, unknown> | undefined {
  const {
    id: _id,
    role: _role,
    body: _body,
    createdAt: _createdAt,
    mode: _mode,
    composerIntent,
    ...extra
  } = item;
  const entries = Object.entries(extra).filter(([, value]) => value !== undefined);
  const result: Record<string, unknown> = Object.fromEntries([["client_id", item.id], ...entries]);
  // Persist intent metadata under a stable snake_case key the backend can read.
  if (composerIntent !== undefined) result.composer_intent = composerIntent;
  return result;
}

export function persistedMessageToChatItem(message: PersistedChatMessage): ChatHistoryItem {
  const {
    client_id: _clientId,
    composer_intent,
    ...extra
  } = (message.extra ?? {}) as Partial<ChatHistoryItem> & {
    client_id?: string;
    composer_intent?: ChatHistoryItem["composerIntent"];
  };
  const role = message.role === "assistant" ? "assistant" : "user";
  const mode =
    message.mode === "plan" || message.mode === "execute" || message.mode === "runtime"
      ? message.mode
      : undefined;
  return {
    ...extra,
    id: `db-${message.id}`,
    role,
    body: message.content,
    createdAt: message.created_at,
    mode,
    ...(composer_intent ? { composerIntent: composer_intent } : {}),
  };
}

export function getPersistedClientId(message: PersistedChatMessage): string | null {
  const clientId = (message.extra as { client_id?: unknown } | null | undefined)?.client_id;
  return typeof clientId === "string" && clientId ? clientId : null;
}

export function upsertPersistedChatMessage(current: ChatHistoryItem[], message: PersistedChatMessage): ChatHistoryItem[] {
  const dbId = `db-${message.id}`;
  const clientId = getPersistedClientId(message);
  const index = current.findIndex((item) => item.id === dbId || (clientId ? item.id === clientId : false));
  if (index === -1) return [...current, persistedMessageToChatItem(message)];
  const updated = [...current];
  updated[index] = {
    ...updated[index],
    ...persistedMessageToChatItem(message),
    id: updated[index].id,
  };
  return updated;
}

export function autopilotRunToChatItem(run: AutopilotRunState): ChatHistoryItem {
  return {
    id: `run-${run.run_id}`,
    role: "assistant",
    body: summarizeAutopilotRun(run),
    createdAt: run.created_at,
    mode: "runtime",
    autopilotRun: run,
    errors: run.errors,
  };
}

export function upsertAutopilotChatItem(current: ChatHistoryItem[], run: AutopilotRunState): ChatHistoryItem[] {
  const index = current.findIndex((item) => item.autopilotRun?.run_id === run.run_id);
  if (index === -1) {
    return [...current, autopilotRunToChatItem(run)];
  }
  const updated = [...current];
  updated[index] = {
    ...updated[index],
    body: summarizeAutopilotRun(run),
    autopilotRun: run,
    errors: run.errors,
  };
  return updated;
}

export function persistedAgentEventToTranscriptEvent(event: PersistedAgentEvent): AgentTranscriptEvent {
  return {
    event_id: event.event_id,
    type: event.type,
    run_id: event.run_id ?? null,
    project_id: event.project_id ?? null,
    session_id: event.session_id ?? null,
    status: event.status ?? null,
    content: event.content ?? null,
    payload: event.payload ?? {},
    created_at: event.created_at,
  };
}

export function upsertAgentEvent(current: AgentTranscriptEvent[], event: AgentTranscriptEvent): AgentTranscriptEvent[] {
  const eventId = event.event_id;
  if (!eventId) return [...current, event];
  const index = current.findIndex((item) => item.event_id === eventId);
  if (index === -1) return [...current, event];
  const updated = [...current];
  updated[index] = { ...updated[index], ...event };
  return updated;
}
