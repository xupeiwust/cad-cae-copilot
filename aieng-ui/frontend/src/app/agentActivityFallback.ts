import type { CadGenerationProgress } from "../appTypes";
import type { LiveSyncStatus } from "../appUtils";
import type { AutopilotRunState } from "../types";
import { isTerminalAutopilotStatus } from "./chatTranscript";

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

export function isTerminalAutopilotRun(run: AutopilotRunState | null | undefined): boolean {
  // Only completed/failed/cancelled are terminal. awaiting_approval, chatting,
  // blocked, paused and any unknown/future status are NON-terminal, so the live
  // stream and polling fallback keep busy/polling/streaming alive while a run is
  // waiting on the user. Shares the single source of truth in chatTranscript.
  return isTerminalAutopilotStatus(run?.status);
}
