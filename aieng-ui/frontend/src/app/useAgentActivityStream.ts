import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { CadGenerationProgress, ChatHistoryItem, Notice } from "../appTypes";
import type { AgentActivityEvent, LiveSyncStatus } from "../appUtils";
import { applyAgentActivityEvent, createChatId } from "../appUtils";
import type { AutopilotRunState } from "../types";
import type { ChatSession, PersistedChatMessage } from "../api";
import type { AgentTranscriptEvent } from "./chatTranscript";
import {
  autopilotAgentLabel,
  summarizeAutopilotRun,
} from "./workbenchHelpers";

type UseAgentActivityStreamArgs = {
  selectedId: string | null;
  activeSessionId: string | null;
  agentBusy: boolean;
  cadGenerationProgress: CadGenerationProgress | null;
  refreshProjects(nextSelectedId?: string | null): Promise<void>;
  refreshViewerAsset(projectId: string, previewUrl?: string | null, previewFormat?: string | null): void;
  stopAutopilotPoll(): void;
  onAutopilotRunUpdate(run: AutopilotRunState): void;
  onChatMessage(message: PersistedChatMessage): void;
  onChatSessionChange(session: ChatSession, action?: string | null): void;
  onChatSessionDelete(sessionId: string): void;
  onAgentEvent(event: AgentTranscriptEvent): void;
  setAgentBusy: Dispatch<SetStateAction<boolean>>;
  setNotice: Dispatch<SetStateAction<Notice | null>>;
  setChatHistory: Dispatch<SetStateAction<ChatHistoryItem[]>>;
  setCadGenerationProgress: Dispatch<SetStateAction<CadGenerationProgress | null>>;
  clearAgentEvents(): void;
  clearStreamingState(): void;
};

export function useAgentActivityStream({
  selectedId,
  activeSessionId,
  agentBusy,
  cadGenerationProgress,
  refreshProjects,
  refreshViewerAsset,
  stopAutopilotPoll,
  onAutopilotRunUpdate,
  onChatMessage,
  onChatSessionChange,
  onChatSessionDelete,
  onAgentEvent,
  setAgentBusy,
  setNotice,
  setChatHistory,
  setCadGenerationProgress,
  clearAgentEvents,
  clearStreamingState,
}: UseAgentActivityStreamArgs) {
  const [liveSyncStatus, setLiveSyncStatus] = useState<LiveSyncStatus>("connecting");
  const [liveSyncDetail, setLiveSyncDetail] = useState("Connecting to backend activity stream...");
  const [liveSyncLastEventAt, setLiveSyncLastEventAt] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(selectedId);
  const activeSessionIdRef = useRef<string | null>(activeSessionId);
  const onAutopilotRunUpdateRef = useRef(onAutopilotRunUpdate);
  const onChatMessageRef = useRef(onChatMessage);
  const onChatSessionChangeRef = useRef(onChatSessionChange);
  const onChatSessionDeleteRef = useRef(onChatSessionDelete);
  const onAgentEventRef = useRef(onAgentEvent);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    onAutopilotRunUpdateRef.current = onAutopilotRunUpdate;
    onChatMessageRef.current = onChatMessage;
    onChatSessionChangeRef.current = onChatSessionChange;
    onChatSessionDeleteRef.current = onChatSessionDelete;
    onAgentEventRef.current = onAgentEvent;
  }, [onAutopilotRunUpdate, onChatMessage, onChatSessionChange, onChatSessionDelete, onAgentEvent]);

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
      const currentSession = activeSessionIdRef.current;
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
        const run = event.run as AutopilotRunState | undefined;
        if (!run?.run_id) return;
        onAutopilotRunUpdateRef.current(run);
        if (run.status !== "running") {
          stopAutopilotPoll();
          setAgentBusy(false);
          clearAgentEvents();
          clearStreamingState();
        }
        if (run.project_id && current && run.project_id !== current) return;
        if (run.session_id && currentSession && run.session_id !== currentSession) return;
        setChatHistory((currentHistory) => {
          const index = currentHistory.findIndex((item) => item.autopilotRun?.run_id === run.run_id);
          if (index === -1) {
            return [
              ...currentHistory,
              {
                id: `run-${run.run_id}`,
                role: "assistant",
                body: summarizeAutopilotRun(run),
                createdAt: run.created_at,
                mode: "runtime",
                autopilotRun: run,
                errors: run.errors,
              },
            ];
          }
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
          clearStreamingState();
          return;
        }
        if (run.status !== "running") {
          stopAutopilotPoll();
          setAgentBusy(false);
          setNotice({
            tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
            title: `${autopilotAgentLabel(run)} — ${run.status}`,
            detail: summarizeAutopilotRun(run),
          });
        }
        return;
      }

      if (event.type === "chat_message") {
        const message = event.chat_message as PersistedChatMessage | undefined;
        if (!message?.id) return;
        if (message.project_id && current && message.project_id !== current) return;
        if (message.session_id && currentSession && message.session_id !== currentSession) return;
        onChatMessageRef.current(message);
        return;
      }

      if (event.type === "chat_session_changed") {
        const session = event.session as ChatSession | undefined;
        if (!session?.id) return;
        if (session.project_id && current && session.project_id !== current) return;
        onChatSessionChangeRef.current(session, event.action);
        return;
      }

      if (event.type === "chat_session_deleted") {
        if (event.project_id && current && event.project_id !== current) return;
        if (event.session_id) onChatSessionDeleteRef.current(event.session_id);
        return;
      }

      if (
        event.type === "agent_message" ||
        event.type === "tool_started" ||
        event.type === "tool_completed" ||
        event.type === "tool_failed" ||
        event.type === "approval_requested" ||
        event.type === "approval_resolved" ||
        event.type === "artifact_ready" ||
        event.type === "run_status_changed" ||
        event.type === "run_cancelled"
      ) {
        if (event.project_id && current && event.project_id !== current) return;
        if (event.session_id && currentSession && event.session_id !== currentSession) return;
        onAgentEventRef.current(event as AgentTranscriptEvent);
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
