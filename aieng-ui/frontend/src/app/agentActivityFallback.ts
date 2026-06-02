import type { CadGenerationProgress } from "../appTypes";
import type { LiveSyncStatus } from "../appUtils";
import type { AutopilotRunState } from "../types";

export function nextStatusAfterStreamError(current: LiveSyncStatus): LiveSyncStatus {
  return current === "polling" ? "polling" : "reconnecting";
}

export function shouldPollActivityFallback({
  selectedId,
  liveSyncStatus,
  agentBusy,
  cadGenerationProgress,
}: {
  selectedId: string | null;
  liveSyncStatus: LiveSyncStatus;
  agentBusy: boolean;
  cadGenerationProgress: CadGenerationProgress | null;
}): boolean {
  if (!selectedId) return false;
  if (liveSyncStatus === "live") return false;
  return liveSyncStatus === "reconnecting" || liveSyncStatus === "polling" || agentBusy || Boolean(cadGenerationProgress);
}

export function isTerminalAutopilotRun(run: AutopilotRunState): boolean {
  return run.status !== "running";
}
