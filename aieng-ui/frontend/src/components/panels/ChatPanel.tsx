import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import type { CadGenerationProgress, ChatHistoryItem, PickedFace } from "../../appTypes";
import { PointerText } from "../PointerText";
import { ActionIcon, JsonDisclosure } from "../common";
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

              {entry.cadResult ? (
                <div className="chat-cad-result">
                  <div className="chat-cad-stats">
                    <span>{entry.cadResult.face_count} faces</span>
                    <span>{entry.cadResult.feature_count} features</span>
                    <span>preview updated</span>
                  </div>
                  <details>
                    <summary>View generated code</summary>
                    <pre className="chat-cad-code">{entry.cadResult.code}</pre>
                  </details>
                </div>
              ) : null}

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

              {entry.simulationResult ? (
                <div className={`chat-sim-result${entry.simulationResult.status === "success" ? "" : " chat-sim-result-error"}`}>
                  {entry.simulationResult.status === "success" ? (
                    <>
                      <div className="chat-sim-stats">
                        {entry.simulationResult.von_mises_max_mpa != null ? (
                          <span>σ<sub>max</sub> {(entry.simulationResult.von_mises_max_mpa as number).toFixed(1)} MPa</span>
                        ) : null}
                        {entry.simulationResult.displacement_max_mm != null ? (
                          <span>u<sub>max</sub> {(entry.simulationResult.displacement_max_mm as number).toFixed(3)} mm</span>
                        ) : null}
                        {entry.simulationResult.verdict?.fos?.fos != null ? (
                          <span className={`chat-fos-badge chat-fos-${entry.simulationResult.verdict.fos.rating}`}>
                            FoS {entry.simulationResult.verdict.fos.fos.toFixed(2)}
                          </span>
                        ) : null}
                        {entry.simulationResult.node_count != null ? (
                          <span>{entry.simulationResult.node_count.toLocaleString()} nodes</span>
                        ) : null}
                        {entry.simulationResult.mesh_size_mm != null ? (
                          <span>mesh {entry.simulationResult.mesh_size_mm} mm</span>
                        ) : null}
                      </div>
                      <div className="chat-heatmap-row">
                        <button
                          type="button"
                          className={`chat-heatmap-btn${heatmapActive ? " active" : ""}`}
                          onClick={onViewHeatmap}
                        >
                          {heatmapActive ? "View Model" : "View Stress Heatmap"}
                        </button>
                        {heatmapActive ? (
                          <div className="chat-heatmap-colorbar">
                            <span className="chat-heatmap-colorbar-label">
                              {heatmapRange ? `${heatmapRange.min.toFixed(0)} MPa` : "low"}
                            </span>
                            <div className="chat-heatmap-colorbar-strip" />
                            <span className="chat-heatmap-colorbar-label">
                              {heatmapRange ? `${heatmapRange.max.toFixed(0)} MPa` : "high"}
                            </span>
                          </div>
                        ) : null}
                      </div>
                    </>
                  ) : entry.simulationResult.status === "tools_unavailable" ? (
                    <p className="chat-sim-missing">
                      Tools not installed: {entry.simulationResult.missing_tools?.join(", ")}
                    </p>
                  ) : (
                    <>
                      <p className="chat-sim-missing">
                        Solver error (code {entry.simulationResult.returncode ?? "?"})
                      </p>
                      {entry.simulationResult.diagnosis?.length ? (
                        <ul className="chat-sim-diagnosis">
                          {entry.simulationResult.diagnosis.map((d, i) => (
                            <li key={i}>{d}</li>
                          ))}
                        </ul>
                      ) : null}
                    </>
                  )}
                  {entry.simulationResult.written_artifacts?.length ? (
                    <div className="chat-preprocess-files">
                      {entry.simulationResult.written_artifacts.map((f) => (
                        <span key={f} className="chat-preprocess-file">{f}</span>
                      ))}
                    </div>
                  ) : null}
                  {(entry.simulationResult.warnings?.length ?? 0) > 0 ? (
                    <details>
                      <summary>{entry.simulationResult.warnings!.length} warning{entry.simulationResult.warnings!.length !== 1 ? "s" : ""}</summary>
                      <ul className="chat-preprocess-warnings">
                        {entry.simulationResult.warnings!.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}

                  {entry.simulationResult.verdict && entry.simulationResult.verdict.overall !== "no_targets" ? (
                    <div className={`chat-verdict chat-verdict-${entry.simulationResult.verdict.overall}`}>
                      <div className="chat-verdict-header">
                        <span className="chat-verdict-badge">
                          {entry.simulationResult.verdict.overall === "pass" ? "PASS" :
                           entry.simulationResult.verdict.overall === "fail" ? "FAIL" :
                           entry.simulationResult.verdict.overall === "partial" ? "PARTIAL" : "UNKNOWN"}
                        </span>
                        <span className="chat-verdict-counts">
                          {entry.simulationResult.verdict.pass_count} passed · {entry.simulationResult.verdict.fail_count} failed
                        </span>
                      </div>
                      {entry.simulationResult.verdict.items.filter((i) => i.status !== "not_evaluated").map((item) => (
                        <div key={item.target_id} className={`chat-verdict-item chat-verdict-item-${item.status}`}>
                          <span className="chat-verdict-item-label">{item.label}</span>
                          <span className="chat-verdict-item-values">
                            {item.actual_value != null ? item.actual_value.toFixed(2) : "—"}
                            {item.unit ? ` ${item.unit}` : ""}
                            {" "}
                            {item.operator} {item.threshold != null ? item.threshold : "—"}
                            {item.unit ? ` ${item.unit}` : ""}
                          </span>
                          <span className={`chat-verdict-item-status status-${item.status === "pass" ? "done" : item.status === "fail" ? "error" : "active"}`}>
                            {item.status}
                          </span>
                        </div>
                      ))}
                      {entry.simulationResult.verdict.suggestions.length > 0 ? (
                        <details className="chat-verdict-suggestions">
                          <summary>Suggestions ({entry.simulationResult.verdict.suggestions.length})</summary>
                          <ul>
                            {entry.simulationResult.verdict.suggestions.map((s, i) => (
                              <li key={i}>{s}</li>
                            ))}
                          </ul>
                        </details>
                      ) : null}
                    </div>
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
                <div className="chat-plan-list">
                  {entry.plan.map((step, index) => (
                    <div
                      key={`${step.tool}-${index}`}
                      className={`chat-plan-item status-${
                        step.status === "failed" ? "error" : step.status === "done" ? "done" : "active"
                      }`}
                    >
                      <strong>{step.tool}</strong>
                      <span>{step.description}</span>
                    </div>
                  ))}
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
          <div className="chat-approval-card">
            <span>
              Approval required —{" "}
              {lastRuntimeRun.plan[lastRuntimeRun.pending_step_index ?? 0]?.name ?? "tool"}
            </span>
            <div className="chat-approval-actions">
              <button disabled={chatBusy} onClick={() => void approveRun()}>
                <ActionIcon name="approve" />
                Approve
              </button>
              <button disabled={chatBusy} className="ghost-button" onClick={() => void rejectRun()}>
                <ActionIcon name="reject" />
                Reject
              </button>
            </div>
          </div>
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
