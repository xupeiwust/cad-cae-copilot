import {
  isRunActivelyProcessing,
  isTerminalAutopilotRun,
  nextStatusAfterStreamError,
  shouldKeepAgentBusyForRun,
  shouldPollActivityFallback,
} from "./agentActivityFallback";
import { test } from "vitest";

test("agent activity fallback", () => {

expectEqual(nextStatusAfterStreamError("live"), "reconnecting", "live error status");
expectEqual(nextStatusAfterStreamError("polling"), "polling", "polling error status");
expectEqual(
  shouldPollActivityFallback({
    selectedId: "project-1",
    liveSyncStatus: "reconnecting",
    agentBusy: false,
    cadGenerationProgress: null,
  }),
  true,
  "poll during reconnect",
);
expectEqual(
  shouldPollActivityFallback({
    selectedId: "project-1",
    liveSyncStatus: "live",
    agentBusy: true,
    cadGenerationProgress: null,
  }),
  false,
  "live stream wins over busy polling",
);
expectEqual(
  shouldPollActivityFallback({
    selectedId: null,
    liveSyncStatus: "polling",
    agentBusy: true,
    cadGenerationProgress: null,
  }),
  false,
  "no selected project",
);
expectEqual(isTerminalAutopilotRun({ status: "completed" } as never), true, "completed terminal");
expectEqual(isTerminalAutopilotRun({ status: "failed" } as never), true, "failed terminal");
expectEqual(isTerminalAutopilotRun({ status: "cancelled" } as never), true, "cancelled terminal");
expectEqual(isTerminalAutopilotRun({ status: "running" } as never), false, "running not terminal");
expectEqual(isTerminalAutopilotRun({ status: "awaiting_approval" } as never), false, "awaiting_approval not terminal");
expectEqual(isTerminalAutopilotRun({ status: "chatting" } as never), false, "chatting not terminal");
expectEqual(isTerminalAutopilotRun({ status: "blocked" } as never), false, "blocked not terminal");
expectEqual(isTerminalAutopilotRun({ status: "some_future_status" } as never), false, "unknown not terminal");
expectEqual(isTerminalAutopilotRun(null), false, "null run not terminal");
expectEqual(isTerminalAutopilotRun(undefined), false, "undefined run not terminal");

// isRunActivelyProcessing: only a recently-updated "running" run drives the spinner/Stop.
const now = Date.parse("2026-06-02T12:00:00.000Z");
const recent = "2026-06-02T11:59:30.000Z"; // 30s ago
const stale = "2026-06-02T11:00:00.000Z"; // 60min ago (worker gone, e.g. backend restart)
const run = (status: string, updated: string) => ({ status, updated_at: updated, created_at: updated }) as never;
expectEqual(isRunActivelyProcessing(null, now), false, "no run -> not processing (initial load)");
expectEqual(isRunActivelyProcessing(undefined, now), false, "undefined run -> not processing");
expectEqual(isRunActivelyProcessing(run("running", recent), now), true, "running + recent -> processing");
expectEqual(isRunActivelyProcessing(run("running", stale), now), false, "running + stale -> NOT processing (no infinite spinner)");
expectEqual(isRunActivelyProcessing(run("awaiting_approval", recent), now), false, "awaiting_approval active but not processing");
expectEqual(isRunActivelyProcessing(run("blocked", recent), now), false, "blocked active but not processing");
expectEqual(isRunActivelyProcessing(run("chatting", recent), now), false, "chatting not processing");
expectEqual(isRunActivelyProcessing(run("completed", recent), now), false, "completed not processing");
expectEqual(isRunActivelyProcessing(run("failed", recent), now), false, "failed not processing");
expectEqual(isRunActivelyProcessing(run("cancelled", recent), now), false, "cancelled not processing");
expectEqual(isRunActivelyProcessing(run("running", "not-a-date"), now), false, "invalid updated_at -> not processing");

// shouldKeepAgentBusyForRun: only true while the agent is actually executing.
expectEqual(shouldKeepAgentBusyForRun(run("running", recent)), true, "running keeps agentBusy");
expectEqual(shouldKeepAgentBusyForRun(run("awaiting_approval", recent)), false, "awaiting_approval unlocks controls");
expectEqual(shouldKeepAgentBusyForRun(run("blocked", recent)), false, "blocked unlocks controls");
expectEqual(shouldKeepAgentBusyForRun(run("chatting", recent)), false, "chatting unlocks controls");
expectEqual(shouldKeepAgentBusyForRun(run("completed", recent)), false, "completed clears agentBusy");
expectEqual(shouldKeepAgentBusyForRun(run("failed", recent)), false, "failed clears agentBusy");
expectEqual(shouldKeepAgentBusyForRun(run("cancelled", recent)), false, "cancelled clears agentBusy");
expectEqual(shouldKeepAgentBusyForRun(null), false, "null run clears agentBusy");
expectEqual(shouldKeepAgentBusyForRun(undefined), false, "undefined run clears agentBusy");

function expectEqual(actual: unknown, expected: unknown, label: string) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
});
