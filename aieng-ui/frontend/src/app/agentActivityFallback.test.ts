import { isTerminalAutopilotRun, nextStatusAfterStreamError, shouldPollActivityFallback } from "./agentActivityFallback";

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
expectEqual(isTerminalAutopilotRun({ status: "running" } as never), false, "running not terminal");

function expectEqual(actual: unknown, expected: unknown, label: string) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
