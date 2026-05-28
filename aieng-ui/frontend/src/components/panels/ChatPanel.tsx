import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import type { CadGenerationProgress, ChatHistoryItem, PickedFace } from "../../appTypes";
import { PointerText } from "../PointerText";
import { ActionIcon, JsonDisclosure } from "../common";
import { ApprovalCard } from "../agent/ApprovalCard";
import { AgentPlanCard } from "../agent/AgentPlanCard";
import { AgentResultCard } from "../agent/AgentResultCard";
import { isLowRiskArtifactPath } from "../../appUtils";
import type { ChatConnection, ProjectRecord, RuntimeRun } from "../../types";

type SimulationProgress = { step: string; message: string };

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
  selectedProject,
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
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const acCursorRef = useRef<{ start: number; end: number } | null>(null);

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
    : "Describe a part to generate, or ask about the current model… (Enter to send, Shift+Enter for newline)";

  const sendLabel = chatBusy
    ? cadGenerating ? "Generating…" : "Thinking…"
    : "Send";

  return (
    <section className="card agent-console-card">
      <div className="chat-header">
        <strong>Engineering Agent</strong>
        <div className="chat-header-controls">
          <select
            className="chat-connection-select"
            value={selectedChatConnectionId}
            onChange={(e) => setSelectedChatConnectionId(e.target.value)}
          >
            {chatConnections.map((conn) => (
              <option key={conn.id} value={conn.id}>
                {conn.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="ghost-button icon-only-button"
            onClick={() => setSettingsOpen(true)}
            title="Model settings"
          >
            <ActionIcon name="settings" />
          </button>
        </div>
      </div>

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

              <p><PointerText text={entry.body} /></p>

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
                <div className="autopilot-run-card">
                  <div className="autopilot-run-header">
                    <span>Local Agent</span>
                    <code>{entry.autopilotRun.status}</code>
                  </div>
                  <div className="autopilot-run-meta">
                    <span>{entry.autopilotRun.adapter_id}</span>
                    <span>{entry.autopilotRun.steps.length} step{entry.autopilotRun.steps.length === 1 ? "" : "s"}</span>
                    {entry.autopilotRun.pending_approval ? (
                      <span>{entry.autopilotRun.pending_approval.level}</span>
                    ) : null}
                  </div>
                  {entry.autopilotRun.pending_approval ? (
                    <div className="autopilot-approval-note">
                      <strong>{entry.autopilotRun.pending_approval.tool_name}</strong>
                      <span>{entry.autopilotRun.pending_approval.explanation}</span>
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
                  {entry.autopilotRun.observations.length ? (
                    <ul className="autopilot-observation-list">
                      {entry.autopilotRun.observations.slice(-4).map((obs) => (
                        <li key={obs.id}>
                          <span>{obs.kind}</span>
                          <PointerText text={obs.summary} />
                        </li>
                      ))}
                    </ul>
                  ) : null}
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
      </div>

      <div className="chat-input-row">
        <div className="chat-input-wrap">
          <textarea
            ref={textareaRef}
            rows={2}
            value={message}
            onChange={(e) => handleInput(e.target.value)}
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
          {sendLabel}
        </button>
      </div>
    </section>
  );
}
