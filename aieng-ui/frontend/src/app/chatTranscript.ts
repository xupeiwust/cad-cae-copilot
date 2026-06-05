// Live slice retained after the MCP-first cutover (#17, #8): the in-UI chat and
// its transcript rendering were removed, so the run→transcript projection that
// used to live here (and the resolvedIntent / editVerification modules it pulled
// in) is gone. What survives is the agent-activity event shape consumed by the
// live SSE stream and the terminal-status predicate used by the activity
// fallback. Keep this module focused on those two; do not re-grow a projection
// layer here unless an in-UI transcript comes back.

/** Shape of a live agent-activity event delivered over the SSE stream. */
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

/** A run/agent status is terminal (stopped) — completed, failed, or cancelled. */
export function isTerminalAutopilotStatus(status: unknown): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}
