import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";

import { api, type PersistedAgentEvent, type PersistedChatMessage } from "../api";
import type { ChatHistoryItem } from "../appTypes";
import type { AutopilotRunState, RuntimeRun } from "../types";
import type { AgentTranscriptEvent } from "./chatTranscript";
import {
  chatItemExtra,
  getPersistedClientId,
  persistedAgentEventToTranscriptEvent,
  persistedMessageToChatItem,
  upsertAgentEvent,
  upsertAutopilotChatItem,
  upsertPersistedChatMessage,
} from "./chatStateUtils";
import { runtimeRunChatEntry } from "./runtimeRunChat";

const ACTIVE_AUTOPILOT_STATUSES = new Set(["running", "awaiting_approval", "chatting"]);

type UseChatTranscriptArgs = {
  selectedId: string | null;
  activeSessionId: string | null;
  activeRunId?: string | null;
  sessionsReady: boolean;
  onAutopilotRunUpdate(run: AutopilotRunState): void;
};

export type StreamingState = {
  text: string;
  runId: string;
  toolName?: string;
  status: "streaming" | "tool_call";
  /** 'progress' = heartbeat phase message; 'content' = real agent output */
  kind?: "progress" | "content";
} | null;

export function useChatTranscript({
  selectedId,
  activeSessionId,
  activeRunId,
  sessionsReady,
  onAutopilotRunUpdate,
}: UseChatTranscriptArgs) {
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [agentEvents, setAgentEvents] = useState<AgentTranscriptEvent[]>([]);
  const [streamingState, setStreamingState] = useState<StreamingState>(null);
  const persistedChatIdsRef = useRef<Set<string>>(new Set());

  const persistChatItem = useCallback((item: ChatHistoryItem) => {
    if (!selectedId || !activeSessionId || persistedChatIdsRef.current.has(item.id)) return;
    persistedChatIdsRef.current.add(item.id);
    void api.saveChatMessage(selectedId, {
      session_id: activeSessionId,
      role: item.role,
      content: item.body,
      mode: item.mode,
      created_at: item.createdAt,
      extra: chatItemExtra(item),
    }).catch(() => {
      persistedChatIdsRef.current.delete(item.id);
    });
  }, [activeSessionId, selectedId]);

  const setPersistentChatHistory = useCallback((value: SetStateAction<ChatHistoryItem[]>) => {
    setChatHistory((current) => {
      const next = typeof value === "function" ? value(current) : value;
      const currentIds = new Set(current.map((item) => item.id));
      for (const item of next) {
        if (!currentIds.has(item.id)) persistChatItem(item);
      }
      return next;
    });
  }, [persistChatItem]);

  const handleLiveChatMessage = useCallback((messageRecord: PersistedChatMessage) => {
    setChatHistory((current) => upsertPersistedChatMessage(current, messageRecord));
    persistedChatIdsRef.current.add(`db-${messageRecord.id}`);
    const clientId = getPersistedClientId(messageRecord);
    if (clientId) persistedChatIdsRef.current.add(clientId);
  }, []);

  const handleLiveAgentEvent = useCallback((event: AgentTranscriptEvent) => {
    const content = event.content;
    const runId = event.run_id;
    if (event.type === "agent_message" && content && runId) {
      setStreamingState((current) => {
        if (!current || current.runId !== runId) {
          return { text: content, runId, status: "streaming", kind: "content" };
        }
        return { ...current, text: content, status: "streaming", kind: "content" };
      });
    }
    if (event.type === "tool_started" && runId) {
      const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
      const toolName = (payload.tool_name as string) || (payload.tool as string) || "tool";
      setStreamingState((current) => {
        if (!current || current.runId !== runId) {
          return { text: "", runId, toolName, status: "tool_call" };
        }
        return { ...current, toolName, status: "tool_call" };
      });
    }
    if (event.type === "run_status_changed" && runId && content) {
      const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
      if (payload.progress_event) {
        setStreamingState((current) => {
          if (!current || current.runId !== runId) {
            return { text: content, runId, status: "streaming", kind: "progress" };
          }
          return { ...current, text: content, status: "streaming", kind: "progress" };
        });
      }
    }
    setAgentEvents((current) => upsertAgentEvent(current, event));
  }, []);

  const appendRunToChatHistory = useCallback((run: RuntimeRun) => {
    setPersistentChatHistory((current) => [...current, runtimeRunChatEntry(run)]);
  }, [setPersistentChatHistory]);

  const clearStreamingState = useCallback(() => {
    setStreamingState(null);
  }, []);

  useEffect(() => {
    persistedChatIdsRef.current = new Set();
    setChatHistory([]);
    setAgentEvents([]);
    setStreamingState(null);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !activeSessionId) {
      persistedChatIdsRef.current = new Set();
      setChatHistory([]);
      setAgentEvents([]);
      return;
    }
    if (!sessionsReady) return;
    let cancelled = false;
    void Promise.all([
      api.getChatMessages(selectedId, activeSessionId),
      api.getAgentEvents(selectedId, activeSessionId).catch(() => [] as PersistedAgentEvent[]),
    ])
      .then(([messages, events]) => {
        if (cancelled) return;
        const items = messages.map(persistedMessageToChatItem);
        persistedChatIdsRef.current = new Set(items.map((item) => item.id));
        setChatHistory(items);
        setAgentEvents(events.map(persistedAgentEventToTranscriptEvent));

        const staleRunIds = new Set<string>();
        for (const item of items) {
          if (item.autopilotRun?.run_id && ACTIVE_AUTOPILOT_STATUSES.has(item.autopilotRun.status)) {
            staleRunIds.add(item.autopilotRun.run_id);
          }
        }
        for (const runId of staleRunIds) {
          api.getAutopilotRun(runId)
            .then((run) => {
              if (!cancelled) {
                setChatHistory((current) => upsertAutopilotChatItem(current, run));
              }
            })
            .catch(() => {
              if (cancelled) return;
              setChatHistory((current) => current.map((item) => {
                if (item.autopilotRun?.run_id !== runId) return item;
                if (!ACTIVE_AUTOPILOT_STATUSES.has(item.autopilotRun.status)) return item;
                return {
                  ...item,
                  body: `${item.body}\n\n*(Run state is no longer available; status may be stale.)*`,
                  autopilotRun: {
                    ...item.autopilotRun,
                    status: "failed" as const,
                    errors: [...(item.autopilotRun.errors || []), "Run state is no longer available."],
                  },
                };
              }));
            });
        }
      })
      .catch(() => {
        persistedChatIdsRef.current = new Set();
        if (!cancelled) {
          setChatHistory([]);
          setAgentEvents([]);
        }
      });
    return () => { cancelled = true; };
  }, [activeSessionId, selectedId, sessionsReady]);

  useEffect(() => {
    if (!activeRunId) return;
    let cancelled = false;
    void api.getAutopilotRun(activeRunId)
      .then((run) => {
        if (cancelled) return;
        onAutopilotRunUpdate(run);
        setChatHistory((current) => upsertAutopilotChatItem(current, run));
      })
      .catch(() => {
        if (cancelled) return;
        setChatHistory((current) => current.map((item) => {
          const run = item.autopilotRun;
          if (!run || run.run_id !== activeRunId) return item;
          if (!ACTIVE_AUTOPILOT_STATUSES.has(run.status)) return item;
          return {
            ...item,
            body: `${item.body}\n\n*(Run state is no longer available; status may be stale.)*`,
            autopilotRun: {
              ...run,
              status: "failed" as const,
              errors: [...(run.errors || []), "Run state is no longer available."],
            },
          };
        }));
      });
    return () => { cancelled = true; };
  }, [activeRunId, onAutopilotRunUpdate]);

  const clearAgentEvents = useCallback(() => {
    setAgentEvents([]);
  }, []);

  return {
    chatHistory,
    agentEvents,
    setChatHistory,
    setPersistentChatHistory,
    handleLiveChatMessage,
    handleLiveAgentEvent,
    appendRunToChatHistory,
    clearAgentEvents,
    streamingState,
    clearStreamingState,
  };
}
