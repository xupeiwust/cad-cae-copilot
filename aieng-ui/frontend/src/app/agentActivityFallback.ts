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

// Frontend "busy" is narrower than "active": once a run is waiting on the user
// (awaiting_approval / blocked / chatting), controls should unlock immediately.
// Only an actually executing run keeps agentBusy true.
export function shouldKeepAgentBusyForRun(run: AutopilotRunState | null | undefined): boolean {
  return run?.status === "running";
}

// A "running" run drives the processing spinner / composer Stop only while a
// worker is plausibly still alive — i.e. it was updated recently. Grace exceeds
// the max adapter step timeout (Claude Code: 180s) so a live run mid-step is not
// misread as idle. A run left "running" with no recent update (e.g. the backend
// restarted and abandoned the worker) is NOT actively processing, so on initial
// load it shows a passive "paused" line instead of an infinite spinner.
// awaiting_approval / blocked / chatting are active runs but are NOT processing.
export const ACTIVELY_PROCESSING_GRACE_MS = 240_000;

export function isRunActivelyProcessing(
  run: AutopilotRunState | null | undefined,
  nowMs: number,
): boolean {
  if (!run || run.status !== "running") return false;
  const updatedMs = Date.parse(run.updated_at ?? run.created_at ?? "");
  if (!Number.isFinite(updatedMs)) return false;
  return nowMs - updatedMs <= ACTIVELY_PROCESSING_GRACE_MS;
}
