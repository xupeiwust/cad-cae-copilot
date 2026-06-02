import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type ChatSession } from "../api";
import type { ApprovalMode, AutopilotRunState } from "../types";

type UseChatSessionsArgs = {
  selectedId: string | null;
};

export function useChatSessions({ selectedId }: UseChatSessionsArgs) {
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionsProjectId, setSessionsProjectId] = useState<string | null>(null);

  const sessionsReady = Boolean(selectedId && sessionsProjectId === selectedId);
  const activeSession = useMemo(
    () => chatSessions.find((item) => item.id === activeSessionId) ?? null,
    [activeSessionId, chatSessions],
  );

  useEffect(() => {
    if (!selectedId) {
      setSessionsProjectId(null);
      setChatSessions([]);
      setActiveSessionId(null);
      return;
    }
    setSessionsProjectId(null);
    setActiveSessionId(null);
    let cancelled = false;
    void api.getChatSessions(selectedId)
      .then((sessions) => {
        if (cancelled) return;
        setSessionsProjectId(selectedId);
        setChatSessions(sessions);
        setActiveSessionId((current) => (
          current && sessions.some((session) => session.id === current)
            ? current
            : sessions[0]?.id ?? null
        ));
      })
      .catch(() => {
        if (!cancelled) {
          setSessionsProjectId(null);
          setChatSessions([]);
          setActiveSessionId(null);
        }
      });
    return () => { cancelled = true; };
  }, [selectedId]);

  const updateActiveSessionFromRun = useCallback((run: AutopilotRunState) => {
    const projectId = run.project_id ?? selectedId;
    const sessionId = run.session_id ?? activeSessionId;
    if (!projectId || !sessionId) return;
    const status =
      run.status === "running" || run.status === "awaiting_approval" || run.status === "chatting"
        ? "running"
        : run.status === "completed"
          ? "completed"
          : run.status === "cancelled"
            ? "cancelled"
            : run.status === "failed"
              ? "failed"
              : "idle";
    setChatSessions((current) => current.map((session) => (
      session.id === sessionId
        ? { ...session, status, active_run_id: run.run_id, updated_at: run.updated_at }
        : session
    )));
  }, [activeSessionId, selectedId]);

  const handleLiveChatSessionChange = useCallback((session: ChatSession) => {
    setChatSessions((current) => {
      const index = current.findIndex((item) => item.id === session.id);
      if (index === -1) return [session, ...current];
      const updated = [...current];
      updated[index] = session;
      return updated.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    });
  }, []);

  const handleLiveChatSessionDelete = useCallback((sessionId: string) => {
    setChatSessions((current) => current.filter((session) => session.id !== sessionId));
    setActiveSessionId((current) => current === sessionId ? null : current);
  }, []);

  const renameActiveSessionForPrompt = useCallback((prompt: string) => {
    if (!selectedId || !activeSessionId || !activeSession || !/^default session|new session$/i.test(activeSession.title)) {
      return;
    }
    const title = prompt.length > 54 ? `${prompt.slice(0, 51)}...` : prompt;
    setChatSessions((current) => current.map((session) => (
      session.id === activeSessionId ? { ...session, title } : session
    )));
    void api.updateChatSession(selectedId, activeSessionId, { title }).catch(() => {});
  }, [activeSession, activeSessionId, selectedId]);

  async function createChatSession(title?: string) {
    if (!selectedId) return;
    const session = await api.createChatSession(selectedId, title ?? "New session");
    setChatSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]);
    setActiveSessionId(session.id);
  }

  function selectChatSession(sessionId: string) {
    setActiveSessionId(sessionId);
  }

  async function deleteChatSession(sessionId: string) {
    if (!selectedId) return;
    await api.deleteChatSession(selectedId, sessionId);
    setChatSessions((current) => current.filter((session) => session.id !== sessionId));
    setActiveSessionId((current) => {
      if (current !== sessionId) return current;
      const remaining = chatSessions.filter((session) => session.id !== sessionId);
      return remaining[0]?.id ?? null;
    });
  }

  async function updateActiveSessionApprovalMode(approvalMode: ApprovalMode) {
    if (!selectedId || !activeSessionId) return;
    const previous = chatSessions;
    setChatSessions((current) => current.map((session) => (
      session.id === activeSessionId
        ? { ...session, approval_mode: approvalMode, updated_at: new Date().toISOString() }
        : session
    )));
    try {
      const updated = await api.updateChatSession(selectedId, activeSessionId, { approval_mode: approvalMode });
      setChatSessions((current) => current.map((session) => session.id === updated.id ? updated : session));
    } catch (error) {
      setChatSessions(previous);
      throw error;
    }
  }

  return {
    chatSessions,
    activeSessionId,
    activeSession,
    sessionsReady,
    createChatSession,
    selectChatSession,
    deleteChatSession,
    updateActiveSessionFromRun,
    handleLiveChatSessionChange,
    handleLiveChatSessionDelete,
    renameActiveSessionForPrompt,
    updateActiveSessionApprovalMode,
  };
}
