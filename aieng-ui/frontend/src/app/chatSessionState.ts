import type { ChatSession, ContextSummary } from "../api";

export function applyContextSummaryToSessions(
  sessions: ChatSession[],
  activeSessionId: string | null,
  contextSummary: ContextSummary | null,
  updatedAt?: string | null,
): ChatSession[] {
  if (!activeSessionId) return sessions;
  return sessions.map((session) => (
    session.id === activeSessionId
      ? {
          ...session,
          context_summary: contextSummary,
          context_summary_json: contextSummary ? JSON.stringify(contextSummary) : null,
          context_summary_updated_at: updatedAt ?? contextSummary?.updated_at ?? null,
        }
      : session
  ));
}
