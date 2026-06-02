// Hand-rolled assertions (matches the repo's existing *.test.ts convention; no
// runner dependency, type-checked by `tsc --noEmit`).
//
// Covers B-7 (stable, causal ordering — no `new Date()` fallback, no sourceId
// lexicographic tie-break) and B-8 (synthetic event ids don't collide and drop
// distinct events that share type/run/timestamp).

import { chatHistoryToTranscriptItems, type AgentTranscriptEvent } from "./chatTranscript";
import { test } from "vitest";

test("transcript ordering", () => {

const T = "2026-05-30T00:00:00.000Z";

function sourceIds(items: ReturnType<typeof chatHistoryToTranscriptItems>): string[] {
  return items.map((item) => item.sourceId);
}

// B-7.1 — same-timestamp events keep causal/arrival order, not sourceId lexical -
{
  // Input order: tool (sourceId "event:zzz") then artifact (sourceId "event:aaa").
  // Old comparator broke ties on sourceId, flipping these to artifact-before-tool.
  const events: AgentTranscriptEvent[] = [
    { event_id: "zzz", type: "tool_started", run_id: "r", payload: { tool_name: "toolA" }, created_at: T },
    { event_id: "aaa", type: "artifact_ready", run_id: "r", content: "art", payload: { preview_url: "/x.glb" }, created_at: T },
  ];
  const items = chatHistoryToTranscriptItems([], events);
  const toolIdx = items.findIndex((i) => i.kind === "tool");
  const artifactIdx = items.findIndex((i) => i.kind === "artifact");
  expectEqual(toolIdx >= 0 && artifactIdx >= 0, true, "both rows present");
  expectEqual(toolIdx < artifactIdx, true, "causal order preserved (tool before artifact)");
}

// B-7.2 — missing timestamps project deterministically (no `new Date()` drift) --
{
  const events: AgentTranscriptEvent[] = [
    { type: "agent_message", run_id: "r", content: "hi", payload: {} },
    { type: "agent_message", run_id: "r", content: "yo", payload: {} },
  ];
  const first = sourceIds(chatHistoryToTranscriptItems([], events));
  const second = sourceIds(chatHistoryToTranscriptItems([], events));
  expectDeepEqual(first, second, "repeated projection of missing-timestamp events is identical");
  const texts = chatHistoryToTranscriptItems([], events)
    .filter((i) => i.kind === "message")
    .map((i) => (i.kind === "message" ? i.text : ""));
  expectDeepEqual(texts, ["hi", "yo"], "missing-timestamp events keep arrival order");
}

// B-8.1 — distinct no-id events sharing type/run/timestamp are not merged --------
{
  const events: AgentTranscriptEvent[] = [
    { type: "tool_started", run_id: "r", payload: { tool_name: "toolA" }, created_at: T },
    { type: "tool_started", run_id: "r", payload: { tool_name: "toolB" }, created_at: T },
  ];
  const tools = chatHistoryToTranscriptItems([], events).filter((i) => i.kind === "tool");
  expectEqual(tools.length, 2, "two distinct no-id tool events both survive");
  const names = new Set(tools.map((i) => (i.kind === "tool" ? i.toolName : "")));
  expectEqual(names.has("toolA") && names.has("toolB"), true, "both tool names present");
}

// B-8.2 — events with a real event_id still dedupe by it -------------------------
{
  const events: AgentTranscriptEvent[] = [
    { event_id: "dup", type: "tool_started", run_id: "r", payload: { tool_name: "t" }, created_at: T },
    { event_id: "dup", type: "tool_started", run_id: "r", payload: { tool_name: "t" }, created_at: T },
  ];
  const tools = chatHistoryToTranscriptItems([], events).filter((i) => i.kind === "tool");
  expectEqual(tools.length, 1, "duplicate event_id collapses to one row");
}

// eslint-disable-next-line no-console
console.log("transcriptOrdering.test.ts: all assertions passed");

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function expectDeepEqual(actual: unknown, expected: unknown, label: string) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`${label}: expected ${expectedJson}, got ${actualJson}`);
  }
}
});
