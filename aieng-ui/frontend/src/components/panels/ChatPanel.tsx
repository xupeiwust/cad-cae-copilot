import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { ArrowUp, Square } from "lucide-react";

import { chatHistoryToTranscriptItems, type AgentTranscriptEvent } from "../../app/chatTranscript";
import type { StreamingState } from "../../app/useChatTranscript";
import type { CadGenerationProgress, ChatHistoryItem, PickedFace } from "../../appTypes";
import type { AutopilotRunState, ChatConnection, RuntimeRun } from "../../types";
import { AgentActivityLine, type AgentActivityTone } from "../agent/AgentActivityLine";
import { ChatTranscript } from "../chat/ChatTranscript";
import { ActionIcon } from "../common";

type SimulationProgress = { step: string; message: string };
type CurrentActivity = {
  title: string;
  detail?: string;
  tone: AgentActivityTone;
  running: boolean;
  elapsed?: string;
};

const ACTIVE_AUTOPILOT_STATUSES = new Set(["running", "awaiting_approval", "chatting"]);

function formatElapsed(createdAt: string | undefined, nowMs: number): string {
  if (!createdAt) return "0:00";
  const startMs = Date.parse(createdAt);
  if (!Number.isFinite(startMs)) return "0:00";
  const total = Math.max(0, Math.floor((nowMs - startMs) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

type QuickAction = { label: string; prompt: string };

function hasCadResult(history: ChatHistoryItem[]): boolean {
  return history.some((e) =>
    Boolean(e.cadResult) ||
    (e.artifactPaths && e.artifactPaths.length > 0) ||
    e.autopilotRun?.observations?.some(
      (o) =>
        o.kind === "tool_result" &&
        ((o.data?.output as Record<string, unknown>)?.named_parts as string[] | undefined)?.length,
    ),
  );
}

function hasSimulationResult(history: ChatHistoryItem[]): boolean {
  return history.some((e) => e.simulationResult?.status === "completed");
}

function buildQuickActions(history: ChatHistoryItem[]): QuickAction[] {
  const hasCad = hasCadResult(history);
  const hasSim = hasSimulationResult(history);
  const actions: QuickAction[] = [];

  if (hasSim) {
    actions.push(
      { label: "View stress hotspots", prompt: "Show me the stress hotspots and regions with high von Mises stress in the model" },
      { label: "Generate report", prompt: "Generate an engineering analysis report summarizing the simulation results and key findings" },
      { label: "Optimize design", prompt: "Based on the simulation results, suggest design improvements to reduce stress concentrations" },
    );
  } else if (hasCad) {
    actions.push(
      { label: "Run simulation", prompt: "Run a structural FEA simulation on this geometry using Gmsh + CalculiX" },
      { label: "Edit parameters", prompt: "Show me the available editable parameters for this geometry" },
      { label: "Check model", prompt: "Review the current geometry and point out any potential issues" },
    );
  }

  actions.push(
    { label: "Continue", prompt: "Continue with the next step" },
    { label: "Describe changes", prompt: "I would like to make some changes. What options do I have?" },
  );

  return actions.slice(0, 5);
}

function latestActiveAutopilotRun(chatHistory: ChatHistoryItem[]): AutopilotRunState | null {
  return [...chatHistory]
    .reverse()
    .map((entry) => entry.autopilotRun)
    .find((run): run is AutopilotRunState => Boolean(run && ACTIVE_AUTOPILOT_STATUSES.has(run.status))) ?? null;
}

function currentAutopilotActivity(run: AutopilotRunState): { title: string; detail: string; tone: AgentActivityTone } {
  const agentLabel = run.adapter_id === "llm-api" ? "LLM agent" : "local agent";
  if (run.status === "awaiting_approval" && run.pending_approval) {
    return {
      title: "Waiting for approval",
      detail: `${run.pending_approval.tool_name}: ${run.pending_approval.explanation}`,
      tone: "approval",
    };
  }
  if (run.status === "completed") {
    return { title: "Completed", detail: `The ${agentLabel} finished this turn.`, tone: "done" };
  }
  if (run.status === "failed") {
    return { title: "Failed", detail: run.errors[0] || `The ${agentLabel} stopped with an error.`, tone: "error" };
  }
  if (run.status === "cancelled") {
    return { title: "Cancelled", detail: "The local agent run was cancelled.", tone: "idle" };
  }
  if (run.status === "blocked") {
    const latest = run.observations[run.observations.length - 1];
    return { title: "Blocked", detail: latest?.summary || "The local agent needs more information.", tone: "approval" };
  }
  if (run.status === "chatting") {
    const latest = run.observations[run.observations.length - 1];
    return { title: "Ready for follow-up", detail: latest?.summary || `The ${agentLabel} is waiting for your reply.`, tone: "done" };
  }
  const latest =
    [...run.observations].reverse().find((obs) => obs.kind === "agent_activity") ??
    run.observations[run.observations.length - 1];
  return {
    title: "Working",
    detail: latest?.summary || `Starting ${agentLabel} run.`,
    tone: "running",
  };
}

function currentActivityLine({
  cadGenerationProgress,
  simulationProgress,
  lastRuntimeRun,
  activeAutopilotRun,
  chatBusy,
  nowMs,
}: {
  cadGenerationProgress: CadGenerationProgress | null;
  simulationProgress: SimulationProgress | null;
  lastRuntimeRun: RuntimeRun | null;
  activeAutopilotRun: AutopilotRunState | null;
  chatBusy: boolean;
  nowMs: number;
}): CurrentActivity | null {
  if (cadGenerationProgress) {
    const activeStage = cadGenerationProgress.stages.find((s) => s.id === cadGenerationProgress.activeStage);
    const fallbackStage = cadGenerationProgress.stages[cadGenerationProgress.stages.length - 1];
    const stage = activeStage ?? fallbackStage;
    const fatalError = cadGenerationProgress.fatalError;
    return {
      title: fatalError ? "CAD generation needs attention" : activeStage ? `Generating CAD · ${stage.label}` : "CAD generation complete",
      detail: activeStage?.message ?? fatalError ?? "Artifacts are ready in the viewer.",
      tone: fatalError ? "error" : activeStage ? "running" : "done",
      running: Boolean(activeStage && !fatalError),
    };
  }
  if (simulationProgress) {
    return {
      title: `Running simulation · ${simulationProgress.step.replace(/_/g, " ")}`,
      detail: simulationProgress.message,
      tone: "running",
      running: true,
    };
  }
  if (activeAutopilotRun) {
    const activity = currentAutopilotActivity(activeAutopilotRun);
    return {
      ...activity,
      running: activeAutopilotRun.status === "running",
      elapsed: formatElapsed(activeAutopilotRun.created_at, nowMs),
    };
  }
  if (lastRuntimeRun?.status === "awaiting_approval") {
    const pendingStep = typeof lastRuntimeRun.pending_step_index === "number"
      ? lastRuntimeRun.plan[lastRuntimeRun.pending_step_index]
      : null;
    return {
      title: "Waiting for approval",
      detail: pendingStep ? `${pendingStep.name}: ${pendingStep.description}` : "Review the pending tool call before continuing.",
      tone: "approval",
      running: false,
    };
  }
  if (chatBusy) {
    return {
      title: "Thinking through the next step",
      detail: "The agent is reading context and preparing a response.",
      tone: "running",
      running: true,
    };
  }
  return null;
}

type ChatPanelProps = {
  chatConnections: ChatConnection[];
  selectedChatConnectionId: string;
  selectedConnectionBlocked: boolean;
  selectedId: string | null;
  chatBusy: boolean;
  cadGenerating: boolean;
  cadGenerationProgress: CadGenerationProgress | null;
  chatHistory: ChatHistoryItem[];
  agentEvents: AgentTranscriptEvent[];
  chatLogRef: RefObject<HTMLDivElement | null>;
  message: string;
  lastRuntimeRun: RuntimeRun | null;
  simulationPending: boolean;
  simulationProgress: SimulationProgress | null;
  setSelectedChatConnectionId(value: string): void;
  setSettingsOpen(value: boolean): void;
  setMessage(value: string): void;
  sendUnified(promptOverride?: string): Promise<void>;
  viewArtifact(path: string): Promise<void>;
  approveRun(): Promise<void>;
  rejectRun(): Promise<void>;
  approveAutopilot(runId: string): void;
  rejectAutopilot(runId: string): void;
  cancelAutopilot(runId: string): void;
  reviseAutopilot?(runId: string, message: string): void;
  approveSimulation(): void;
  rejectSimulation(): void;
  recentPickedFaces: PickedFace[];
  streamingState: StreamingState;
};

export function ChatPanel({
  chatConnections,
  selectedChatConnectionId,
  selectedConnectionBlocked,
  selectedId,
  chatBusy,
  cadGenerating,
  cadGenerationProgress,
  chatHistory,
  agentEvents,
  chatLogRef,
  message,
  lastRuntimeRun,
  simulationPending,
  simulationProgress,
  setSelectedChatConnectionId,
  setSettingsOpen,
  setMessage,
  sendUnified,
  viewArtifact,
  approveRun,
  rejectRun,
  approveAutopilot,
  rejectAutopilot,
  cancelAutopilot,
  reviseAutopilot,
  approveSimulation,
  rejectSimulation,
  recentPickedFaces,
  streamingState,
}: ChatPanelProps) {
  const [acOpen, setAcOpen] = useState(false);
  const [acQuery, setAcQuery] = useState("");
  const [acIndex, setAcIndex] = useState(0);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [newActivityAvailable, setNewActivityAvailable] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const acCursorRef = useRef<{ start: number; end: number } | null>(null);
  const wasNearBottomRef = useRef(true);

  const activeAutopilotRun = latestActiveAutopilotRun(chatHistory);
  const transcriptItems = useMemo(
    () => chatHistoryToTranscriptItems(chatHistory, agentEvents).sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt) || a.sourceId.localeCompare(b.sourceId)),
    [agentEvents, chatHistory],
  );

  useEffect(() => {
    if (!activeAutopilotRun) return;
    setNowMs(Date.now());
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeAutopilotRun]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (!message) el.style.height = "auto";
  }, [message]);

  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const wasNearBottom = wasNearBottomRef.current || distanceFromBottom < 120;
    if (wasNearBottom) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      setNewActivityAvailable(false);
    } else {
      setNewActivityAvailable(true);
    }
  }, [chatHistory, transcriptItems.length, chatLogRef]);

  const acMatches = recentPickedFaces.filter((f) =>
    f.pointer.toLowerCase().includes(acQuery.toLowerCase()) ||
    f.label.toLowerCase().includes(acQuery.toLowerCase()),
  );
  const activityLine = currentActivityLine({
    cadGenerationProgress,
    simulationProgress,
    lastRuntimeRun,
    activeAutopilotRun,
    chatBusy,
    nowMs,
  });

  function closeAutocomplete() {
    setAcOpen(false);
    setAcQuery("");
    acCursorRef.current = null;
  }

  function insertAutocomplete(face: PickedFace) {
    if (!textareaRef.current || !acCursorRef.current) return;
    const { start } = acCursorRef.current;
    const before = message.slice(0, start - 1);
    const after = message.slice(textareaRef.current.selectionStart);
    const replacement = `${before}${face.pointer} ${after}`;
    setMessage(replacement);
    closeAutocomplete();
    setTimeout(() => {
      if (textareaRef.current) {
        const pos = (before + face.pointer + " ").length;
        textareaRef.current.selectionStart = pos;
        textareaRef.current.selectionEnd = pos;
        textareaRef.current.focus();
      }
    }, 0);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (acOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setAcIndex((i) => (i + 1) % acMatches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setAcIndex((i) => (i - 1 + acMatches.length) % acMatches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (acMatches[acIndex]) insertAutocomplete(acMatches[acIndex]);
        return;
      }
      if (e.key === "Escape") {
        closeAutocomplete();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (message.trim()) void sendUnified();
    }
  }

  function handleInput(value: string) {
    setMessage(value);
    const el = textareaRef.current;
    if (!el) return;
    const cursor = el.selectionStart;
    const textBefore = value.slice(0, cursor);
    const atIdx = textBefore.lastIndexOf("@");
    if (atIdx !== -1 && !textBefore.slice(atIdx + 1).includes(" ") && recentPickedFaces.length) {
      acCursorRef.current = { start: atIdx + 1, end: atIdx + 1 };
      setAcQuery(textBefore.slice(atIdx + 1));
      setAcIndex(0);
      setAcOpen(true);
    } else {
      closeAutocomplete();
    }
  }

  function markScrollPosition() {
    const el = chatLogRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    wasNearBottomRef.current = nearBottom;
    if (nearBottom) setNewActivityAvailable(false);
  }

  function scrollToBottom() {
    const el = chatLogRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    wasNearBottomRef.current = true;
    setNewActivityAvailable(false);
  }

  const selectedConn = chatConnections.find((c) => c.id === selectedChatConnectionId);
  const connStatus = selectedConn?.status ?? "blocked";
  const statusText = connStatus === "ready" ? "Ready" : connStatus === "blocked" ? "Unavailable" : connStatus.replace(/_/g, " ");

  return (
    <section className="chat-pane-body">
      <div className="chat-window" ref={chatLogRef as RefObject<HTMLDivElement>} onScroll={markScrollPosition} data-i18n-skip>
        {transcriptItems.length ? (
          <ChatTranscript
            items={transcriptItems}
            busy={chatBusy}
            streamingState={streamingState}
            onViewArtifact={(path) => void viewArtifact(path)}
            onApproveAutopilot={approveAutopilot}
            onRejectAutopilot={rejectAutopilot}
            onCancelAutopilot={cancelAutopilot}
            onReviseAutopilot={reviseAutopilot}
          />
        ) : (
          <div className="summary-note summary-muted chat-empty-state">
            <strong>Engineering Agent ready</strong>
            <p>
              {selectedId
                ? "Type a description to generate CAD geometry, or ask about the current project."
                : "Create or select a project, then describe what you want to model or analyse."}
            </p>
          </div>
        )}

        {lastRuntimeRun?.status === "awaiting_approval" ? (
          <div className="approval-line runtime-approval-line">
            <div className="approval-line-main">
              <span className="approval-line-badge">runtime</span>
              <strong>Review pending runtime step</strong>
              <span>
                {typeof lastRuntimeRun.pending_step_index === "number"
                  ? lastRuntimeRun.plan[lastRuntimeRun.pending_step_index]?.description
                  : "Approve or reject the pending runtime action."}
              </span>
            </div>
            <div className="approval-line-actions">
              <button type="button" disabled={chatBusy} onClick={() => void approveRun()}>
                <ActionIcon name="approve" />
                Approve
              </button>
              <button type="button" className="ghost-button" disabled={chatBusy} onClick={() => void rejectRun()}>
                <ActionIcon name="reject" />
                Reject
              </button>
            </div>
          </div>
        ) : null}

        {simulationPending ? (
          <div className="approval-line chat-sim-approval">
            <div className="approval-line-main">
              <span className="approval-line-badge">solver</span>
              <strong>Run Gmsh mesh + CalculiX solver on this geometry?</strong>
            </div>
            <div className="approval-line-actions">
              <button disabled={chatBusy} onClick={approveSimulation}>
                <ActionIcon name="approve" />
                Run Simulation
              </button>
              <button disabled={chatBusy} className="ghost-button" onClick={rejectSimulation}>
                <ActionIcon name="reject" />
                Cancel
              </button>
            </div>
          </div>
        ) : null}

        {activityLine ? (
          <AgentActivityLine
            title={activityLine.title}
            detail={activityLine.detail}
            tone={activityLine.tone}
            running={activityLine.running}
            elapsed={activityLine.elapsed}
          />
        ) : null}
        {newActivityAvailable ? (
          <button type="button" className="new-activity-button" onClick={scrollToBottom}>
            New activity
          </button>
        ) : null}
      </div>

      {activeAutopilotRun?.status === "chatting" ? (
        <div className="chat-quick-actions">
          {buildQuickActions(chatHistory).map((action) => (
            <button
              key={action.label}
              type="button"
              className="chat-quick-action-chip"
              disabled={chatBusy}
              onClick={() => void sendUnified(action.prompt)}
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="chat-input-toolbar">
        <select
          className="chat-connection-select"
          value={selectedChatConnectionId}
          onChange={(e) => setSelectedChatConnectionId(e.target.value)}
        >
          {chatConnections.map((conn) => (
            <option key={conn.id} value={conn.id}>
              {conn.status === "ready" ? "●" : conn.status === "blocked" ? "○" : "◐"} {conn.label}
            </option>
          ))}
        </select>
        <span className={`connection-status status-${connStatus}`} title={selectedConn?.detail ?? ""}>
          {statusText}
        </span>
        <button
          type="button"
          className="ghost-button icon-only-button"
          onClick={() => setSettingsOpen(true)}
          title="Settings"
          style={{ marginLeft: "auto" }}
        >
          <ActionIcon name="settings" />
        </button>
      </div>

      <div className="chat-input-row">
        <div className="chat-input-wrap">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => {
              handleInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${e.target.scrollHeight}px`;
            }}
            onKeyDown={handleKeyDown}
            placeholder={selectedConnectionBlocked ? "Select a project to start..." : "Check the current project status and generate a reviewable engineering execution plan."}
            disabled={selectedConnectionBlocked}
          />
          {acOpen && acMatches.length > 0 ? (
            <div className="chat-autocomplete">
              {acMatches.map((f, i) => (
                <button
                  key={f.pointer}
                  type="button"
                  className={i === acIndex ? "chat-autocomplete-item active" : "chat-autocomplete-item"}
                  onClick={() => insertAutocomplete(f)}
                >
                  <span className="chat-autocomplete-badge">{f.surface_type}</span>
                  <code>{f.pointer}</code>
                  <span className="chat-autocomplete-label">{f.label}</span>
                </button>
              ))}
            </div>
          ) : null}
          {activeAutopilotRun && !message.trim() ? (
            <button
              type="button"
              className="chat-action-button chat-action-button-stop"
              disabled={!activeAutopilotRun.run_id}
              onClick={() => cancelAutopilot(activeAutopilotRun.run_id)}
              title="Stop active agent run"
            >
              <Square className="button-icon" />
            </button>
          ) : (
            <button
              type="button"
              className="chat-action-button chat-action-button-send"
              disabled={selectedConnectionBlocked || !message.trim()}
              onClick={() => void sendUnified()}
              title="Send"
            >
              <ArrowUp className="button-icon" />
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
