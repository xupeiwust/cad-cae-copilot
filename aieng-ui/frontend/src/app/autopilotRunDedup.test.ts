// Hand-rolled assertions (matches the repo's existing *.test.ts convention; no
// runner dependency, type-checked by `tsc --noEmit`).
//
// Covers B-6: autopilot run items collapse to a single canonical entry
// (id `run-${run_id}`) across optimistic insert + SSE update + reload, distinct
// runs are never merged, user-message client_id dedup is untouched, and
// tool/approval/artifact events still project.

import type { PersistedChatMessage } from "../api";
import type { ChatHistoryItem } from "../appTypes";
import { chatHistoryToTranscriptItems, type AgentTranscriptEvent } from "./chatTranscript";
import { upsertAutopilotChatItem, upsertPersistedChatMessage } from "./chatStateUtils";
import { transcriptMappingFixtures } from "./chatTranscriptFixtures";
import { test } from "vitest";

test("autopilot run dedup", () => {

const runA = transcriptMappingFixtures.completed; // run_id "fixture-completed", final "Geometry is ready."
const runFailed = transcriptMappingFixtures.failed; // run_id "fixture-failed", error "cad.execute_build123d failed"

function row(id: string): ChatHistoryItem {
  return {
    id,
    role: "assistant",
    body: "Run completed",
    createdAt: runA.created_at,
    mode: "runtime",
    autopilotRun: runA,
    errors: runA.errors,
  };
}

function agentFinals(items: ReturnType<typeof chatHistoryToTranscriptItems>): number {
  return items.filter(
    (item) => item.kind === "message" && item.role === "agent" && item.text === runA.final_message,
  ).length;
}

// 1. upsert is idempotent by run_id and uses the canonical id ------------------
{
  let h: ChatHistoryItem[] = [];
  h = upsertAutopilotChatItem(h, runA); // optimistic insert
  expectEqual(h.length, 1, "optimistic insert adds one row");
  expectEqual(h[0].id, `run-${runA.run_id}`, "canonical run id");
  h = upsertAutopilotChatItem(h, { ...runA, final_message: "updated" }); // SSE update
  expectEqual(h.length, 1, "SSE update collapses onto the same row");
  expectEqual(h[0].autopilotRun?.final_message, "updated", "row carries latest run state");
}

// 2. duplicate rows for the same run_id do not multiply transcript content -----
{
  const single = chatHistoryToTranscriptItems([row(`run-${runA.run_id}`)], []);
  // Simulates the optimistic-vs-SSE race leaving two rows for the same run.
  const duplicated = chatHistoryToTranscriptItems([row(`run-${runA.run_id}`), row("chat-legacy")], []);
  expectEqual(duplicated.length, single.length, "duplicate rows add no extra transcript items");
  expectEqual(agentFinals(duplicated), 1, "final message projected exactly once");
}

// 3. distinct runs are never merged -------------------------------------------
{
  let h: ChatHistoryItem[] = [];
  h = upsertAutopilotChatItem(h, runA);
  h = upsertAutopilotChatItem(h, runFailed);
  expectEqual(h.length, 2, "two distinct runs kept as separate rows");
  const transcript = chatHistoryToTranscriptItems(h, []);
  expectEqual(
    transcript.some((item) => item.kind === "message" && item.text === runA.final_message),
    true,
    "run A final present",
  );
  expectEqual(
    transcript.some((item) => item.kind === "error" && item.summary === runFailed.errors[0]),
    true,
    "failed run error present",
  );
}

// 4. user-message client_id dedup is unaffected -------------------------------
{
  const optimisticUser: ChatHistoryItem = {
    id: "chat-user-1",
    role: "user",
    body: "hello",
    createdAt: "2026-05-30T00:00:00.000Z",
  };
  const persisted: PersistedChatMessage = {
    id: 5,
    project_id: "p",
    session_id: "s",
    role: "user",
    content: "hello",
    mode: null,
    created_at: "2026-05-30T00:00:00.000Z",
    extra: { client_id: "chat-user-1" },
  };
  const merged = upsertPersistedChatMessage([optimisticUser], persisted);
  expectEqual(merged.length, 1, "client_id round-trip keeps a single user row");
  expectEqual(merged[0].id, "chat-user-1", "optimistic id preserved on merge");
}

// 5. tool / approval / artifact events still project --------------------------
{
  const at = "2026-05-30T00:03:00.000Z";
  const events: AgentTranscriptEvent[] = [
    { event_id: "e1", type: "tool_started", run_id: "r9", payload: { tool_name: "cad.execute_build123d" }, created_at: at },
    { event_id: "e2", type: "approval_requested", run_id: "r9", payload: { tool_name: "cad.execute_build123d", explanation: "review" }, created_at: at },
    { event_id: "e3", type: "artifact_ready", run_id: "r9", content: "Viewer refreshed", payload: { preview_url: "/x.glb" }, created_at: at },
  ];
  const transcript = chatHistoryToTranscriptItems([], events);
  expectEqual(transcript.some((item) => item.kind === "tool"), true, "tool event present");
  expectEqual(transcript.some((item) => item.kind === "approval"), true, "approval event present");
  expectEqual(transcript.some((item) => item.kind === "artifact"), true, "artifact event present");
}

// eslint-disable-next-line no-console
console.log("autopilotRunDedup.test.ts: all assertions passed");

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
});
