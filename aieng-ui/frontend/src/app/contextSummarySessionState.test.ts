import type { ChatSession, ContextSummary } from "../api";
import { applyContextSummaryToSessions } from "./chatSessionState";
import { test } from "vitest";

test("context summary session state", () => {

const summary: ContextSummary = {
  schema_version: 1,
  session_id: "session-active",
  project_id: "project-1",
  goal: "Review the current model",
  current_state: "Summary refreshed from messages and events.",
  important_decisions: ["Use active project context."],
  completed_steps: ["Loaded prior chat."],
  pending_steps: ["Inspect plan."],
  user_constraints: [],
  relevant_files: ["geometry/source.py"],
  risks: ["Missing CAE setup."],
  next_action: "Continue with plan review.",
  updated_at: "2026-06-02T01:00:00.000Z",
};

const sessions: ChatSession[] = [
  session("session-active"),
  session("session-other"),
];

const updated = applyContextSummaryToSessions(sessions, "session-active", summary, summary.updated_at);

expectEqual(updated[0].context_summary?.goal, summary.goal, "active session summary");
expectEqual(updated[0].context_summary_updated_at, summary.updated_at, "active session updated_at");
expectEqual(updated[0].context_summary_json, JSON.stringify(summary), "active session raw summary");
expectEqual(updated[1].context_summary, null, "other session remains untouched");
expectEqual(sessions[0].context_summary, null, "input sessions remain immutable");

const cleared = applyContextSummaryToSessions(updated, "session-active", null);
expectEqual(cleared[0].context_summary, null, "cleared summary");
expectEqual(cleared[0].context_summary_json, null, "cleared raw summary");
expectEqual(cleared[0].context_summary_updated_at, null, "cleared updated_at");

function session(id: string): ChatSession {
  return {
    id,
    project_id: "project-1",
    title: id,
    status: "idle",
    active_run_id: null,
    approval_mode: "balanced",
    context_summary_json: null,
    context_summary: null,
    context_summary_updated_at: null,
    created_at: "2026-06-02T00:00:00.000Z",
    updated_at: "2026-06-02T00:00:00.000Z",
  };
}

function expectEqual(actual: unknown, expected: unknown, label: string) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
});
