import { useEffect, useMemo, useRef, useState, type RefObject } from "react";

import { chatHistoryToTranscriptItems, type AgentTranscriptEvent } from "../../app/chatTranscript";
import type { StreamingState } from "../../app/useChatTranscript";
import type { ContextSummary } from "../../api";
import type { CadGenerationProgress, ChatHistoryItem, PickedFace } from "../../appTypes";
import type { ApprovalMode, AutopilotAgentMode, AutopilotRunState, ChatConnection, RuntimeRun } from "../../types";
import type { EngineeringContextSource } from "../../app/engineeringContextSource";
import { AgentActivityLine, type AgentActivityTone } from "../agent/AgentActivityLine";
import { ContextSummaryPanel } from "../agent/ContextSummaryPanel";
import { AgentInputBox } from "../chat/AgentInputBox";
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
  agentMode: AutopilotAgentMode;
  approvalMode: ApprovalMode;
  approvalModeDisabled: boolean;
  selectedConnectionBlocked: boolean;
  selectedId: string | null;
  activeSessionId: string | null;
  engineeringContext?: EngineeringContextSource | null;
  onContextSummaryChange?(summary: ContextSummary | null, updatedAt?: string | null): void;
  chatBusy: boolean;
  cadGenerating: boolean;
  cadGenerationProgress: CadGenerationProgress | null;
  llmReady: boolean;
  chatHistory: ChatHistoryItem[];
  agentEvents: AgentTranscriptEvent[];
  chatLogRef: RefObject<HTMLDivElement | null>;
  message: string;
  lastRuntimeRun: RuntimeRun | null;
  simulationPending: boolean;
  simulationProgress: SimulationProgress | null;
  setSelectedChatConnectionId(value: string): void;
  setAgentMode(value: AutopilotAgentMode): void;
  setApprovalMode(value: ApprovalMode): void;
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
  agentMode,
  approvalMode,
  approvalModeDisabled,
  selectedConnectionBlocked,
  selectedId,
  activeSessionId,
  engineeringContext,
  onContextSummaryChange,
  chatBusy,
  cadGenerating,
  cadGenerationProgress,
  llmReady,
  chatHistory,
  agentEvents,
  chatLogRef,
  message,
  lastRuntimeRun,
  simulationPending,
  simulationProgress,
  setSelectedChatConnectionId,
  setAgentMode,
  setApprovalMode,
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
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [newActivityAvailable, setNewActivityAvailable] = useState(false);
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

  const activityLine = currentActivityLine({
    cadGenerationProgress,
    simulationProgress,
    lastRuntimeRun,
    activeAutopilotRun,
    chatBusy,
    nowMs,
  });

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

  return (
    <section className="chat-pane-body">
      <ContextSummaryPanel
        projectId={selectedId}
        sessionId={activeSessionId}
        engineeringContext={engineeringContext}
        onSummaryChange={onContextSummaryChange}
      />

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
            onReplyAutopilot={reviseAutopilot}
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

      {(lastRuntimeRun?.status === "awaiting_approval" || simulationPending) ? (
        <div className="chat-approval-dock">
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
        </div>
      ) : null}

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

      <AgentInputBox
        chatConnections={chatConnections}
        selectedChatConnectionId={selectedChatConnectionId}
        agentMode={agentMode}
        approvalMode={approvalMode}
        approvalModeDisabled={approvalModeDisabled}
        selectedConnectionBlocked={selectedConnectionBlocked}
        llmReady={llmReady}
        message={message}
        activeAutopilotRun={activeAutopilotRun}
        recentPickedFaces={recentPickedFaces}
        setSelectedChatConnectionId={setSelectedChatConnectionId}
        setAgentMode={setAgentMode}
        setApprovalMode={setApprovalMode}
        setSettingsOpen={setSettingsOpen}
        setMessage={setMessage}
        sendUnified={sendUnified}
        cancelAutopilot={cancelAutopilot}
      />
    </section>
  );
}
