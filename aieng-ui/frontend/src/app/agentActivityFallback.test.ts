import { isTerminalAutopilotRun, nextStatusAfterStreamError, shouldPollActivityFallback } from "./agentActivityFallback";
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

function expectEqual(actual: unknown, expected: unknown, label: string) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
});
