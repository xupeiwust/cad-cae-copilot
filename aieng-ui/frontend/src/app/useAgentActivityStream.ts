import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { CadGenerationProgress, ChatHistoryItem, Notice } from "../appTypes";
import type { AgentActivityEvent, LiveSyncStatus } from "../appUtils";
import { applyAgentActivityEvent, createChatId } from "../appUtils";
import type { AutopilotRunState } from "../types";
import type { ChatSession, PersistedChatMessage } from "../api";
import type { AgentTranscriptEvent } from "./chatTranscript";
import {
  isTerminalAutopilotRun,
  nextStatusAfterStreamError,
  shouldKeepAgentBusyForRun,
  shouldPollActivityFallback,
} from "./agentActivityFallback";
import { upsertAutopilotChatItem } from "./chatStateUtils";
import {
  autopilotAgentLabel,
  summarizeAutopilotRun,
} from "./workbenchHelpers";

type UseAgentActivityStreamArgs = {
  selectedId: string | null;
  activeSessionId: string | null;
  activeRunId?: string | null;
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
  clearStreamingState(): void;
};

export function useAgentActivityStream({
  selectedId,
  activeSessionId,
  activeRunId,
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
  clearStreamingState,
}: UseAgentActivityStreamArgs) {
  const [liveSyncStatus, setLiveSyncStatus] = useState<LiveSyncStatus>("connecting");
  const [liveSyncDetail, setLiveSyncDetail] = useState("Connecting to backend activity stream...");
  const [liveSyncLastEventAt, setLiveSyncLastEventAt] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(selectedId);
  const activeSessionIdRef = useRef<string | null>(activeSessionId);
  const activeRunIdRef = useRef<string | null | undefined>(activeRunId);
  const onAutopilotRunUpdateRef = useRef(onAutopilotRunUpdate);
  const onChatMessageRef = useRef(onChatMessage);
  const onChatSessionChangeRef = useRef(onChatSessionChange);
  const onChatSessionDeleteRef = useRef(onChatSessionDelete);
  const onAgentEventRef = useRef(onAgentEvent);
  // The SSE connection below is created once (deps []) and lives for the hook's
  // whole lifetime, so it must invoke the LATEST props — not the ones captured
  // on mount. Route every externally-supplied callback/setter through a ref that
  // the assignment effect keeps current. This is what the exhaustive-deps
  // suppression on the connection effect used to paper over (a long-lived stream
  // calling stale callbacks: e.g. refreshProjects closing over the first render's
  // runtime snapshot).
  const refreshProjectsRef = useRef(refreshProjects);
  const refreshViewerAssetRef = useRef(refreshViewerAsset);
  const stopAutopilotPollRef = useRef(stopAutopilotPoll);
  const clearStreamingStateRef = useRef(clearStreamingState);
  const setAgentBusyRef = useRef(setAgentBusy);
  const setNoticeRef = useRef(setNotice);
  const setChatHistoryRef = useRef(setChatHistory);
  const setCadGenerationProgressRef = useRef(setCadGenerationProgress);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    activeRunIdRef.current = activeRunId;
  }, [activeRunId]);

  useEffect(() => {
    onAutopilotRunUpdateRef.current = onAutopilotRunUpdate;
    onChatMessageRef.current = onChatMessage;
    onChatSessionChangeRef.current = onChatSessionChange;
    onChatSessionDeleteRef.current = onChatSessionDelete;
    onAgentEventRef.current = onAgentEvent;
    refreshProjectsRef.current = refreshProjects;
    refreshViewerAssetRef.current = refreshViewerAsset;
    stopAutopilotPollRef.current = stopAutopilotPoll;
    clearStreamingStateRef.current = clearStreamingState;
    setAgentBusyRef.current = setAgentBusy;
    setNoticeRef.current = setNotice;
    setChatHistoryRef.current = setChatHistory;
    setCadGenerationProgressRef.current = setCadGenerationProgress;
  }, [
    onAutopilotRunUpdate,
    onChatMessage,
    onChatSessionChange,
    onChatSessionDelete,
    onAgentEvent,
    refreshProjects,
    refreshViewerAsset,
    stopAutopilotPoll,
    clearStreamingState,
    setAgentBusy,
    setNotice,
    setChatHistory,
    setCadGenerationProgress,
  ]);

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
        void refreshProjectsRef.current(selectedIdRef.current);
        setChatHistoryRef.current((curr) => [
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
        const matchesCurrentProject = !run.project_id || !current || run.project_id === current;
        const matchesCurrentSession = !run.session_id || !currentSession || run.session_id === currentSession;
        if (!matchesCurrentProject || !matchesCurrentSession) return;
        setAgentBusyRef.current(shouldKeepAgentBusyForRun(run));
        if (isTerminalAutopilotRun(run)) {
          stopAutopilotPollRef.current();
          clearStreamingStateRef.current();
        }
        setChatHistoryRef.current((currentHistory) => upsertAutopilotChatItem(currentHistory, run));
        if (run.status === "chatting") {
          stopAutopilotPollRef.current();
          clearStreamingStateRef.current();
          return;
        }
        if (isTerminalAutopilotRun(run)) {
          setNoticeRef.current({
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
        event.type === "ask_user_requested" ||
        event.type === "agent_plan_created" ||
        event.type === "agent_plan_step_updated" ||
        event.type === "agent_phase_changed" ||
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

      setCadGenerationProgressRef.current((prev) => applyAgentActivityEvent(prev, event));

      if (isViewerAssetChange && event.project_id) {
        refreshViewerAssetRef.current(event.project_id, event.preview_url, event.preview_format);
      }

      if ((isProjectChange || isViewerAssetChange) && event.project_id) {
        void refreshProjectsRef.current(event.project_id);
      }

      if (isBuildDone && event.project_id) {
        refreshViewerAssetRef.current(event.project_id, event.preview_url, event.preview_format);
        void refreshProjectsRef.current(event.project_id);
        window.setTimeout(() => setCadGenerationProgressRef.current(null), 1500);
      }
    };
    source.onerror = () => {
      setLiveSyncStatus((current) => nextStatusAfterStreamError(current));
      setLiveSyncDetail("Live stream disconnected; browser will auto-reconnect and polling fallback is active.");
    };
    return () => source.close();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    const shouldPoll = shouldPollActivityFallback({ selectedId, liveSyncStatus, agentBusy, cadGenerationProgress });
    if (!shouldPoll) return;
    setLiveSyncStatus("polling");
    setLiveSyncDetail("Live stream unavailable; polling project state every 2.5s.");
    const timer = window.setInterval(() => {
      const current = selectedIdRef.current;
      if (current) void refreshProjectsRef.current(current);
      const runId = activeRunIdRef.current;
      if (runId) {
        void api.getAutopilotRun(runId)
          .then((run) => {
            onAutopilotRunUpdateRef.current(run);
            setChatHistoryRef.current((currentHistory) => upsertAutopilotChatItem(currentHistory, run));
            setAgentBusyRef.current(shouldKeepAgentBusyForRun(run));
            if (isTerminalAutopilotRun(run)) {
              stopAutopilotPollRef.current();
              clearStreamingStateRef.current();
            }
          })
          .catch(() => {});
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [agentBusy, cadGenerationProgress, liveSyncStatus, selectedId]);

  return {
    liveSyncStatus,
    liveSyncDetail,
    liveSyncLastEventAt,
  };
}
