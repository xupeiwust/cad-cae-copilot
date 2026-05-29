import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { CadGenerationProgress, ChatHistoryItem, Notice } from "../appTypes";
import type { AgentActivityEvent, LiveSyncStatus } from "../appUtils";
import { applyAgentActivityEvent, createChatId } from "../appUtils";
import {
  autopilotAgentLabel,
  summarizeAutopilotRun,
} from "./workbenchHelpers";

type UseAgentActivityStreamArgs = {
  selectedId: string | null;
  agentBusy: boolean;
  cadGenerationProgress: CadGenerationProgress | null;
  refreshProjects(nextSelectedId?: string | null): Promise<void>;
  refreshViewerAsset(projectId: string, previewUrl?: string | null, previewFormat?: string | null): void;
  stopAutopilotPoll(): void;
  setAgentBusy: Dispatch<SetStateAction<boolean>>;
  setNotice: Dispatch<SetStateAction<Notice | null>>;
  setChatHistory: Dispatch<SetStateAction<ChatHistoryItem[]>>;
  setCadGenerationProgress: Dispatch<SetStateAction<CadGenerationProgress | null>>;
};

export function useAgentActivityStream({
  selectedId,
  agentBusy,
  cadGenerationProgress,
  refreshProjects,
  refreshViewerAsset,
  stopAutopilotPoll,
  setAgentBusy,
  setNotice,
  setChatHistory,
  setCadGenerationProgress,
}: UseAgentActivityStreamArgs) {
  const [liveSyncStatus, setLiveSyncStatus] = useState<LiveSyncStatus>("connecting");
  const [liveSyncDetail, setLiveSyncDetail] = useState("Connecting to backend activity stream...");
  const [liveSyncLastEventAt, setLiveSyncLastEventAt] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(selectedId);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    const url = `${api.base}/api/agent-activity/stream`;
    const source = new EventSource(url);
    source.onopen = () => {
      setLiveSyncStatus("live");
      setLiveSyncDetail("Live updates connected");
    };
    source.onmessage = (msg) => {
      let event: AgentActivityEvent;
      try {
        event = JSON.parse(msg.data) as AgentActivityEvent;
      } catch {
        return;
      }
      setLiveSyncLastEventAt(new Date().toISOString());
      if (event.type === "connected") {
        setLiveSyncStatus("live");
        setLiveSyncDetail("Live updates connected");
        return;
      }

      const current = selectedIdRef.current;
      const isBuildDone =
        event.type === "tool_completed" &&
        event.tool === "cad.execute_build123d" &&
        event.status === "ok" &&
        Boolean(event.project_id);
      const isProjectChange = event.type === "project_changed" && Boolean(event.project_id);
      const isViewerAssetChange = event.type === "viewer_asset_changed" && Boolean(event.project_id);
      const isForCurrent = !event.project_id || !current || event.project_id === current;

      if (isBuildDone && !isForCurrent) {
        void refreshProjects(selectedIdRef.current);
        setChatHistory((curr) => [
          ...curr,
          {
            id: createChatId(),
            role: "assistant",
            body: `An agent finished building a model in project ${event.project_id}. Select that project to view it.`,
            createdAt: new Date().toISOString(),
          },
        ]);
        return;
      }

      if (event.type === "autopilot_update") {
        const payload = event as unknown as Record<string, unknown>;
        const runId = payload.run_id as string;
        void (async () => {
          try {
            const run = await api.getAutopilotRun(runId);
            setChatHistory((currentHistory) => {
              const index = currentHistory.findIndex((item) => item.autopilotRun?.run_id === runId);
              if (index === -1) return currentHistory;
              const updated = [...currentHistory];
              updated[index] = {
                ...updated[index],
                autopilotRun: run,
                errors: run.errors,
                body: summarizeAutopilotRun(run),
              };
              return updated;
            });
            if (run.status === "chatting") {
              stopAutopilotPoll();
              setAgentBusy(false);
            } else if (run.status !== "running") {
              stopAutopilotPoll();
              setAgentBusy(false);
              setNotice({
                tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
                title: `${autopilotAgentLabel(run)} — ${run.status}`,
                detail: summarizeAutopilotRun(run),
              });
            }
          } catch {
            // Next SSE event or poll tick will retry.
          }
        })();
        return;
      }

      if (!isForCurrent) return;

      setCadGenerationProgress((prev) => applyAgentActivityEvent(prev, event));

      if (isViewerAssetChange && event.project_id) {
        refreshViewerAsset(event.project_id, event.preview_url, event.preview_format);
      }

      if ((isProjectChange || isViewerAssetChange) && event.project_id) {
        void refreshProjects(event.project_id);
      }

      if (isBuildDone && event.project_id) {
        refreshViewerAsset(event.project_id, event.preview_url, event.preview_format);
        void refreshProjects(event.project_id);
        window.setTimeout(() => setCadGenerationProgress(null), 1500);
      }
    };
    source.onerror = () => {
      setLiveSyncStatus((current) => (current === "live" ? "reconnecting" : current === "polling" ? "polling" : "reconnecting"));
      setLiveSyncDetail("Live stream disconnected; browser will auto-reconnect and polling fallback is active.");
    };
    return () => source.close();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedId) return;
    if (liveSyncStatus === "live") return;
    const shouldPoll = liveSyncStatus === "reconnecting" || liveSyncStatus === "polling" || agentBusy || Boolean(cadGenerationProgress);
    if (!shouldPoll) return;
    setLiveSyncStatus("polling");
    setLiveSyncDetail("Live stream unavailable; polling project state every 2.5s.");
    const timer = window.setInterval(() => {
      const current = selectedIdRef.current;
      if (current) void refreshProjects(current);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [agentBusy, cadGenerationProgress, liveSyncStatus, selectedId, refreshProjects]);

  return {
    liveSyncStatus,
    liveSyncDetail,
    liveSyncLastEventAt,
  };
}
