import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import type { CadGenerationProgress, ChatHistoryItem, PickedFace } from "../../appTypes";
import { MarkdownText } from "../MarkdownText";
import { PointerText } from "../PointerText";
import { ActionIcon } from "../common";
import { ApprovalCard } from "../agent/ApprovalCard";
import { AgentActivityLine, type AgentActivityTone } from "../agent/AgentActivityLine";
import { AgentPlanCard } from "../agent/AgentPlanCard";
import { AgentResultCard } from "../agent/AgentResultCard";
import { isLowRiskArtifactPath } from "../../appUtils";
import type { AutopilotObservation, AutopilotRunState, ChatConnection, ProjectRecord, RuntimeRun } from "../../types";

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

function statusLabel(status: string): string {
  switch (status) {
    case "running": return "Working";
    case "awaiting_approval": return "Needs approval";
    case "completed": return "Done";
    case "failed": return "Failed";
    case "blocked": return "Blocked";
    case "cancelled": return "Cancelled";
    case "chatting": return "Ready";
    default: return status.replace(/_/g, " ");
  }
}

function observationToolName(obs: AutopilotObservation): string | null {
  const toolName = obs.data?.tool_name;
  return typeof toolName === "string" && toolName ? toolName : null;
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

function autopilotCardTitle(run: AutopilotRunState): string {
  return run.adapter_id === "llm-api" ? "LLM Agent" : "Local Agent";
}

function latestActiveAutopilotRun(chatHistory: ChatHistoryItem[]): AutopilotRunState | null {
  return [...chatHistory]
    .reverse()
    .map((entry) => entry.autopilotRun)
    .find((run): run is AutopilotRunState => Boolean(run && ACTIVE_AUTOPILOT_STATUSES.has(run.status))) ?? null;
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
  selectedProject: ProjectRecord | null;
  selectedId: string | null;
  chatBusy: boolean;
  cadGenerating: boolean;
  cadGenerationProgress: CadGenerationProgress | null;
  chatHistory: ChatHistoryItem[];
  chatLogRef: RefObject<HTMLDivElement | null>;
  message: string;
  lastRuntimeRun: RuntimeRun | null;
  simulationPending: boolean;
  simulationProgress: SimulationProgress | null;
  setSelectedChatConnectionId(value: string): void;
  setSettingsOpen(value: boolean): void;
  setMessage(value: string): void;
  sendUnified(): Promise<void>;
  viewArtifact(path: string): Promise<void>;
  approveRun(): Promise<void>;
  rejectRun(): Promise<void>;
  approveAutopilot(runId: string): void;
  rejectAutopilot(runId: string): void;
  cancelAutopilot(runId: string): void;
  approveSimulation(): void;
  rejectSimulation(): void;
  heatmapActive: boolean;
  heatmapRange: { min: number; max: number } | null;
  onViewHeatmap(): void;
  recentPickedFaces: PickedFace[];
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
  approveSimulation,
  rejectSimulation,
  heatmapActive,
  heatmapRange,
  onViewHeatmap,
  recentPickedFaces,
}: ChatPanelProps) {
  const [acOpen, setAcOpen] = useState(false);
  const [acQuery, setAcQuery] = useState("");
  const [acIndex, setAcIndex] = useState(0);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const acCursorRef = useRef<{ start: number; end: number } | null>(null);

  useEffect(() => {
    const hasActiveAutopilot = chatHistory.some((entry) =>
      entry.autopilotRun && ACTIVE_AUTOPILOT_STATUSES.has(entry.autopilotRun.status),
    );
    if (!hasActiveAutopilot) return;
    setNowMs(Date.now());
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [chatHistory]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (!message) {
      el.style.height = "auto";
    }
  }, [message]);

  const acMatches = recentPickedFaces.filter((f) =>
    f.pointer.toLowerCase().includes(acQuery.toLowerCase()) ||
    f.label.toLowerCase().includes(acQuery.toLowerCase()),
  );

  function openAutocomplete(cursorStart: number, query: string) {
    if (recentPickedFaces.length === 0) return;
    acCursorRef.current = { start: cursorStart, end: cursorStart };
    setAcQuery(query);
    setAcIndex(0);
    setAcOpen(true);
  }

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
        if (acMatches[acIndex]) {
          insertAutocomplete(acMatches[acIndex]);
        }
        return;
      }
      if (e.key === "Escape") {
        closeAutocomplete();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!chatBusy && message.trim()) void sendUnified();
    }
  }

  function handleInput(value: string) {
    setMessage(value);
    const el = textareaRef.current;
    if (!el) return;
    const cursor = el.selectionStart;
    const textBefore = value.slice(0, cursor);
    const atIdx = textBefore.lastIndexOf("@");
    if (atIdx !== -1 && !textBefore.slice(atIdx + 1).includes(" ")) {
      const query = textBefore.slice(atIdx + 1);
      openAutocomplete(atIdx + 1, query);
    } else {
      closeAutocomplete();
    }
  }

  const inputPlaceholder = selectedConnectionBlocked
    ? "Select a project to start…"
    : "";

  const sendLabel = chatBusy
    ? cadGenerating ? "Generating…" : "Thinking…"
    : "Send";
  const activeAutopilotRun = latestActiveAutopilotRun(chatHistory);
  const activityLine = currentActivityLine({
    cadGenerationProgress,
    simulationProgress,
    lastRuntimeRun,
    activeAutopilotRun,
    chatBusy,
    nowMs,
  });

  return (
    <section className="chat-pane-body">
      <div className="chat-window" ref={chatLogRef as RefObject<HTMLDivElement>}>
        {chatHistory.length ? (
          chatHistory.map((entry) => (
            <article
              key={entry.id}
              className={entry.role === "assistant" ? "chat-bubble assistant" : "chat-bubble user"}
            >
              <header>
                <strong>{entry.role === "assistant" ? "Workbench" : "You"}</strong>
                {entry.mode ? (
                  <span className="chat-mode-tag">{entry.mode}</span>
                ) : null}
              </header>

              <MarkdownText text={entry.body} />

              <AgentResultCard
                cadResult={entry.cadResult}
                heatmapActive={heatmapActive}
                heatmapRange={heatmapRange}
                onViewHeatmap={onViewHeatmap}
                simulationResult={entry.simulationResult}
              />

              {entry.targetResult ? (
                <div className="chat-target-result">
                  <span className={`chat-target-badge chat-target-badge-${entry.targetResult.action}`}>
                    {entry.targetResult.action === "added" ? "Target added" : "Target updated"}
                  </span>
                  <span className="chat-target-detail">
                    {entry.targetResult.label}
                    {" "}
                    <code>{entry.targetResult.operator} {entry.targetResult.value}{entry.targetResult.unit ? " " + entry.targetResult.unit : ""}</code>
                  </span>
                  <span className="chat-target-count">{entry.targetResult.total_targets} target{entry.targetResult.total_targets !== 1 ? "s" : ""} total</span>
                </div>
              ) : null}

              {entry.preprocessResult ? (
                <div className="chat-preprocess-result">
                  <div className="chat-preprocess-stats">
                    <span className="chat-preprocess-material">{entry.preprocessResult.material}</span>
                    <span>{entry.preprocessResult.bc_count} BC{entry.preprocessResult.bc_count !== 1 ? "s" : ""}</span>
                    <span>{entry.preprocessResult.load_count} load{entry.preprocessResult.load_count !== 1 ? "s" : ""}</span>
                    <span>mesh {entry.preprocessResult.mesh_size_mm}mm</span>
                  </div>
                  {entry.preprocessResult.written_artifacts.length > 0 ? (
                    <div className="chat-preprocess-files">
                      {entry.preprocessResult.written_artifacts.map((f) => (
                        <span key={f} className="chat-preprocess-file">{f}</span>
                      ))}
                    </div>
                  ) : null}
                  {entry.preprocessResult.warnings.length > 0 ? (
                    <details>
                      <summary>{entry.preprocessResult.warnings.length} warning{entry.preprocessResult.warnings.length !== 1 ? "s" : ""}</summary>
                      <ul className="chat-preprocess-warnings">
                        {entry.preprocessResult.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
              ) : null}

              {entry.advisoryItems?.length ? (
                <div className="chat-advisory-card">
                  <div className="chat-advisory-header">Engineering Advisory</div>
                  <ul className="chat-advisory-list">
                    {entry.advisoryItems.map((item, i) => (
                      <li key={i} className="chat-advisory-item">{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {entry.plan?.length ? (
                <AgentPlanCard steps={entry.plan} />
              ) : null}

              {entry.autopilotRun ? (
                <div className={`autopilot-run-card autopilot-run-${entry.autopilotRun.status}`}>
                  <div className="autopilot-run-header">
                    <span className="autopilot-run-title">
                      {ACTIVE_AUTOPILOT_STATUSES.has(entry.autopilotRun.status) ? (
                        <span className="autopilot-live-dot" aria-hidden="true" />
                      ) : null}
                      {autopilotCardTitle(entry.autopilotRun)}
                    </span>
                    <code>{statusLabel(entry.autopilotRun.status)}</code>
                  </div>
                  {(() => {
                    const activity = currentAutopilotActivity(entry.autopilotRun!);
                    return (
                      <div className={`autopilot-current autopilot-current-${activity.tone}`}>
                        <div>
                          <strong>{activity.title}</strong>
                          <span><PointerText text={activity.detail} /></span>
                        </div>
                        <time>{formatElapsed(entry.autopilotRun!.created_at, nowMs)}</time>
                      </div>
                    );
                  })()}
                  {entry.autopilotRun.pending_approval ? (
                    <div className="autopilot-approval-note">
                      <strong>Review before applying changes</strong>
                      <span>{entry.autopilotRun.pending_approval.explanation}</span>
                      <code>{entry.autopilotRun.pending_approval.tool_name}</code>
                      <div className="chat-approval-actions">
                        <button disabled={chatBusy} onClick={() => approveAutopilot(entry.autopilotRun!.run_id)}>
                          <ActionIcon name="approve" />
                          Approve
                        </button>
                        <button disabled={chatBusy} className="ghost-button" onClick={() => rejectAutopilot(entry.autopilotRun!.run_id)}>
                          <ActionIcon name="reject" />
                          Reject
                        </button>
                        <button disabled={chatBusy} className="ghost-button" onClick={() => cancelAutopilot(entry.autopilotRun!.run_id)}>
                          <ActionIcon name="reject" />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {ACTIVE_AUTOPILOT_STATUSES.has(entry.autopilotRun.status) && !entry.autopilotRun.pending_approval ? (
                    <div className="autopilot-inline-actions">
                      <button
                        disabled={chatBusy && entry.autopilotRun.status !== "running"}
                        className="ghost-button"
                        onClick={() => cancelAutopilot(entry.autopilotRun!.run_id)}
                      >
                        <ActionIcon name="reject" />
                        Cancel
                      </button>
                    </div>
                  ) : null}
                  <details className="autopilot-details">
                    <summary>Run details</summary>
                    <div className="autopilot-run-meta">
                      <span>{entry.autopilotRun.adapter_id}</span>
                      <span>{entry.autopilotRun.steps.length} step{entry.autopilotRun.steps.length === 1 ? "" : "s"}</span>
                      <span>{entry.autopilotRun.observations.length} event{entry.autopilotRun.observations.length === 1 ? "" : "s"}</span>
                      {entry.autopilotRun.pending_approval ? (
                        <span>{entry.autopilotRun.pending_approval.level}</span>
                      ) : null}
                    </div>
                    {entry.autopilotRun.observations.length ? (
                      <ul className="autopilot-observation-list">
                        {entry.autopilotRun.observations.slice(-4).map((obs) => (
                          <li key={obs.id} className={`autopilot-observation-${obs.kind}`}>
                            <span>{obs.kind.replace(/_/g, " ")}</span>
                            <div>
                              <PointerText text={obs.summary} />
                              {observationToolName(obs) ? <code>{observationToolName(obs)}</code> : null}
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </details>
                </div>
              ) : null}

              {entry.errors?.length ? (
                <div className="chat-error-list">
                  {entry.errors.map((err, i) => (
                    <small key={`${entry.id}-err-${i}`}>{err}</small>
                  ))}
                </div>
              ) : null}

              {entry.artifactDiffs?.length ? (
                <div className="chat-artifact-diffs">
                  <small>Changes:</small>
                  {entry.artifactDiffs.map((diff, idx) => (
                    <div key={`${diff.path}-${idx}`} className="chat-diff-item">
                      <div className="chat-diff-header">
                        {isLowRiskArtifactPath(diff.path) ? (
                          <button
                            type="button"
                            className="artifact-link"
                            onClick={() => void viewArtifact(diff.path)}
                          >
                            {diff.path}
                          </button>
                        ) : (
                          <span>{diff.path}</span>
                        )}
                        <span className="chat-diff-op">{diff.operation}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              {entry.artifactPaths?.filter(isLowRiskArtifactPath).length ? (
                <div className="chat-artifact-links">
                  <small>Changed files:</small>
                  {entry.artifactPaths.filter(isLowRiskArtifactPath).map((path) => (
                    <button
                      key={path}
                      type="button"
                      className="ghost-button chat-artifact-link"
                      onClick={() => void viewArtifact(path)}
                    >
                      {path}
                    </button>
                  ))}
                </div>
              ) : null}

              {entry.auditLogUrl ? (
                <a className="chat-audit-link" href={entry.auditLogUrl} target="_blank" rel="noreferrer">
                  View audit log
                </a>
              ) : null}
            </article>
          ))
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

        {cadGenerationProgress ? (
          <div className="chat-progress-card chat-cad-progress">
            <div className="chat-progress-spinner" />
            <div className="chat-progress-text">
              <span className="chat-progress-title">Agent is generating CAD</span>
              <span className="chat-progress-step">
                {cadGenerationProgress.activeStage ?? (cadGenerationProgress.fatalError ? "error" : "done")}
              </span>
              <span className="chat-progress-message">
                {cadGenerationProgress.stages.find((s) => s.id === cadGenerationProgress.activeStage)?.message
                  ?? cadGenerationProgress.fatalError
                  ?? "CAD generation complete"}
              </span>
            </div>
          </div>
        ) : null}

        {simulationProgress ? (
          <div className="chat-progress-card">
            <div className="chat-progress-spinner" />
            <div className="chat-progress-text">
              <span className="chat-progress-step">{simulationProgress.step.replace(/_/g, " ")}</span>
              <span className="chat-progress-message">{simulationProgress.message}</span>
            </div>
          </div>
        ) : null}

        {lastRuntimeRun?.status === "awaiting_approval" ? (
          <ApprovalCard
            busy={chatBusy}
            run={lastRuntimeRun}
            onApprove={() => void approveRun()}
            onReject={() => void rejectRun()}
          />
        ) : null}

        {simulationPending ? (
          <div className="chat-approval-card chat-sim-approval">
            <span>Run Gmsh mesh + CalculiX solver on this geometry?</span>
            <div className="chat-approval-actions">
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
      </div>

      {(() => {
        const selectedConn = chatConnections.find((c) => c.id === selectedChatConnectionId);
        const connStatus = selectedConn?.status ?? "blocked";
        const statusText = connStatus === "ready" ? "Ready" : connStatus === "blocked" ? "Unavailable" : connStatus.replace(/_/g, " ");
        const statusClass = `connection-status status-${connStatus}`;
        return (
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
            <span className={statusClass} title={selectedConn?.detail ?? ""}>
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
        );
      })()}

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
            placeholder={inputPlaceholder}
            disabled={chatBusy}
          />
          {acOpen && acMatches.length > 0 && (
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
          )}
        </div>
        <button
          className="chat-send-button"
          disabled={chatBusy || !message.trim()}
          onClick={() => void sendUnified()}
        >
          <ActionIcon name="send" />
          {sendLabel}
        </button>
      </div>
    </section>
  );
}
