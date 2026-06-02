// Hand-rolled assertions (matches the repo's existing *.test.ts convention —
// no test-runner dependency; the file is type-checked by `tsc --noEmit` and can
// be executed directly with a TS runner if one is wired up later).
//
// Covers the B-1 streamingState lifecycle helpers: only terminal run states and
// tool failures close the streaming bubble; approval/ask_user/chatting do not.

import { isStreamingClosingEvent, isTerminalAutopilotStatus, type AgentTranscriptEvent } from "./chatTranscript";

function event(type: string, extra: Partial<AgentTranscriptEvent> = {}): AgentTranscriptEvent {
  return { type, run_id: "run-1", ...extra };
}

// --- isTerminalAutopilotStatus -------------------------------------------------
expectEqual(isTerminalAutopilotStatus("completed"), true, "completed is terminal");
expectEqual(isTerminalAutopilotStatus("failed"), true, "failed is terminal");
expectEqual(isTerminalAutopilotStatus("cancelled"), true, "cancelled is terminal");
expectEqual(isTerminalAutopilotStatus("running"), false, "running is not terminal");
expectEqual(isTerminalAutopilotStatus("awaiting_approval"), false, "awaiting_approval is not terminal");
expectEqual(isTerminalAutopilotStatus("chatting"), false, "chatting is not terminal");
expectEqual(isTerminalAutopilotStatus("blocked"), false, "blocked is not terminal");
expectEqual(isTerminalAutopilotStatus("paused"), false, "paused is not terminal");
expectEqual(isTerminalAutopilotStatus("some_future_status"), false, "unknown is not terminal");
expectEqual(isTerminalAutopilotStatus(null), false, "null is not terminal");
expectEqual(isTerminalAutopilotStatus(undefined), false, "undefined is not terminal");

// --- isStreamingClosingEvent: closes the bubble --------------------------------
expectEqual(isStreamingClosingEvent(event("run_cancelled")), true, "run_cancelled closes");
expectEqual(isStreamingClosingEvent(event("tool_failed")), true, "tool_failed closes");
expectEqual(isStreamingClosingEvent(event("run_status_changed", { status: "failed" })), true, "run failed closes");
expectEqual(isStreamingClosingEvent(event("run_status_changed", { status: "completed" })), true, "run completed closes");
expectEqual(isStreamingClosingEvent(event("run_status_changed", { status: "cancelled" })), true, "run cancelled closes");
expectEqual(
  isStreamingClosingEvent(event("run_status_changed", { status: null, payload: { status: "failed" } })),
  true,
  "terminal status from payload closes",
);

// --- isStreamingClosingEvent: keeps the bubble / cards -------------------------
expectEqual(isStreamingClosingEvent(event("run_status_changed", { status: "running" })), false, "running keeps");
expectEqual(
  isStreamingClosingEvent(event("run_status_changed", { status: "awaiting_approval" })),
  false,
  "awaiting_approval keeps (approval card stays)",
);
expectEqual(isStreamingClosingEvent(event("run_status_changed", { status: "blocked" })), false, "blocked keeps");
expectEqual(isStreamingClosingEvent(event("agent_message", { content: "hi" })), false, "agent_message keeps");
expectEqual(isStreamingClosingEvent(event("tool_started")), false, "tool_started keeps");
expectEqual(isStreamingClosingEvent(event("approval_requested")), false, "approval_requested keeps");
expectEqual(isStreamingClosingEvent(event("ask_user_requested")), false, "ask_user_requested keeps");

// eslint-disable-next-line no-console
console.log("streamingLifecycle.test.ts: all assertions passed");

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
