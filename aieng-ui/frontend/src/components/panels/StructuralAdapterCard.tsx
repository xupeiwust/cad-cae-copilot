import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type {
  StructuralAdapterCapability,
  StructuralAdapterPreflightResponse,
  StructuralAdapterPreflightStatus,
  StructuralPreparePreviewResponse,
  StructuralSolverInputImportResponse,
  RuntimeRun,
} from "../../types";

type PreflightState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: StructuralAdapterPreflightResponse }
  | { status: "error"; message: string };

type ImportState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: StructuralSolverInputImportResponse }
  | { status: "error"; message: string };

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: StructuralPreparePreviewResponse }
  | { status: "error"; message: string };

type SolverRunState =
  | { status: "idle" }
  | { status: "starting" }
  | { status: "loaded"; run: RuntimeRun }
  | { status: "error"; message: string };

type StructuralAdapterCardProps = {
  projectId?: string | null;
  highlighted?: boolean;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  refreshKey?: number | string;
  /** Fired once per completed solver run so the parent can refresh dependent
   * cards (computed metrics, target comparison) without re-mounting. */
  onSolverRunCompleted?: () => void;
};

type ExtractedMetricsSummary = {
  loadCaseCount: number;
  metricCount: number;
  globalMetricNames: string[];
  loadCaseSamples: Array<{ loadCaseId: string; metricNames: string[] }>;
};

function summarizeExtractedMetrics(value: unknown): ExtractedMetricsSummary | null {
  if (!value || typeof value !== "object") return null;
  const doc = value as Record<string, unknown>;
  const globalMetrics = (doc.global_metrics ?? {}) as Record<string, unknown>;
  const loadCases = (doc.load_cases ?? []) as Array<Record<string, unknown>>;
  const globalNames = Object.keys(globalMetrics);
  let metricCount = globalNames.length;
  const loadCaseSamples: ExtractedMetricsSummary["loadCaseSamples"] = [];
  for (const lc of loadCases) {
    const metrics = (lc.metrics ?? {}) as Record<string, unknown>;
    const names = Object.keys(metrics);
    metricCount += names.length;
    const lcId = typeof lc.load_case_id === "string" ? lc.load_case_id : typeof lc.id === "string" ? lc.id : "";
    if (lcId || names.length) {
      loadCaseSamples.push({ loadCaseId: lcId || "(unnamed)", metricNames: names });
    }
  }
  return {
    loadCaseCount: loadCases.length,
    metricCount,
    globalMetricNames: globalNames,
    loadCaseSamples,
  };
}

function preflightBadgeClass(status?: StructuralAdapterPreflightStatus | null): string {
  if (status === "ready") return "badge badge-pass";
  if (status === "partial") return "badge badge-warn";
  if (status === "unavailable" || status === "not_ready") return "badge badge-fail";
  return "badge badge-muted";
}

function boolBadge(value: boolean, trueLabel: string, falseLabel: string): JSX.Element {
  return <span className={`badge ${value ? "badge-warn" : "badge-muted"}`}>{value ? trueLabel : falseLabel}</span>;
}

function capabilitySummary(capability: StructuralAdapterCapability): string {
  const parts = [capability.category];
  if (capability.requires_approval) parts.push("approval required");
  if (capability.mutates_package) parts.push("mutates package");
  if (capability.runs_external_process) parts.push("external process");
  if (capability.expensive) parts.push("expensive");
  return parts.join(" ? ");
}

function runReadyBadge(ready?: boolean): string {
  if (ready === true) return "badge badge-pass";
  if (ready === false) return "badge badge-warn";
  return "badge badge-muted";
}

export function StructuralAdapterCard({
  projectId,
  highlighted = false,
  expanded = true,
  onExpandedChange,
  refreshKey,
  onSolverRunCompleted,
}: StructuralAdapterCardProps) {
  const [preflightState, setPreflightState] = useState<PreflightState>({ status: "idle" });
  const [importState, setImportState] = useState<ImportState>({ status: "idle" });
  const [previewState, setPreviewState] = useState<PreviewState>({ status: "idle" });
  const [solverRunState, setSolverRunState] = useState<SolverRunState>({ status: "idle" });
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [deckText, setDeckText] = useState("");
  const [runId, setRunId] = useState("run_001");
  const [loadCaseId, setLoadCaseId] = useState("load_case_001");
  const [extractResults, setExtractResults] = useState(true);
  const [refreshSummary, setRefreshSummary] = useState(true);
  const [completionNotifiedRunId, setCompletionNotifiedRunId] = useState<string | null>(null);

  useEffect(() => {
    setPreflightState({ status: "idle" });
    setImportState({ status: "idle" });
    setPreviewState({ status: "idle" });
    setSolverRunState({ status: "idle" });
    setLastRefreshed(null);
    setDeckText("");
    setRunId("run_001");
    setLoadCaseId("load_case_001");
    setExtractResults(true);
    setRefreshSummary(true);
    setCompletionNotifiedRunId(null);
  }, [projectId]);

  const runPreflight = useCallback(async () => {
    setPreflightState({ status: "loading" });
    try {
      const response = await api.getStructuralAdapterPreflight();
      setPreflightState({ status: "loaded", response });
      setLastRefreshed(new Date().toLocaleString());
    } catch (err) {
      setPreflightState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      setLastRefreshed(new Date().toLocaleString());
    }
  }, []);

  const runPreparePreview = useCallback(async () => {
    if (!projectId) return;
    setPreviewState({ status: "loading" });
    try {
      const response = await api.getStructuralPreparePreview(projectId, {
        run_id: runId,
        load_case_id: loadCaseId,
        extract_results: extractResults,
        refresh_summary: refreshSummary,
      });
      setPreviewState({ status: "loaded", response });
    } catch (err) {
      setPreviewState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [extractResults, loadCaseId, projectId, refreshSummary, runId]);

  const importSolverInput = useCallback(async () => {
    if (!projectId || !deckText.trim()) return;
    setImportState({ status: "loading" });
    try {
      const response = await api.importStructuralSolverInput(projectId, {
        text: deckText,
        run_id: runId,
        overwrite: true,
      });
      setImportState({ status: "loaded", response });
      void runPreparePreview();
    } catch (err) {
      setImportState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [deckText, projectId, runId, runPreparePreview]);

  const startSolverRun = useCallback(async () => {
    if (!projectId) return;
    setSolverRunState({ status: "starting" });
    try {
      const run = await api.startRun(
        "execute solver run",
        projectId,
        {
          project_id: projectId,
          run_id: runId,
          load_case_id: loadCaseId,
          input_deck_path: `simulation/runs/${runId}/solver_input.inp`,
          extract_results: extractResults,
          refresh_summary: refreshSummary,
        },
      );
      setSolverRunState({ status: "loaded", run });
    } catch (err) {
      setSolverRunState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [extractResults, loadCaseId, projectId, refreshSummary, runId]);

  const approveSolverRun = useCallback(async () => {
    if (solverRunState.status !== "loaded") return;
    setSolverRunState({ status: "starting" });
    try {
      const run = await api.approveRun(solverRunState.run.run_id);
      setSolverRunState({ status: "loaded", run });
    } catch (err) {
      setSolverRunState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [solverRunState]);

  const rejectSolverRun = useCallback(async () => {
    if (solverRunState.status !== "loaded") return;
    setSolverRunState({ status: "starting" });
    try {
      const run = await api.rejectRun(solverRunState.run.run_id);
      setSolverRunState({ status: "loaded", run });
    } catch (err) {
      setSolverRunState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [solverRunState]);

  useEffect(() => {
    if (!refreshKey) return;
    void runPreflight();
  }, [refreshKey, runPreflight]);

  const response = preflightState.status === "loaded" ? preflightState.response : null;
  const capabilities = response?.capabilities ?? [];
  const checkedPaths = useMemo(
    () => Object.entries(response?.checked_paths ?? {}),
    [response?.checked_paths],
  );
  const estimatedOutputs = response?.preflight.estimated_outputs ?? [];
  const prepareResponse = previewState.status === "loaded" ? previewState.response : null;
  const imported = importState.status === "loaded" ? importState.response : null;
  const solverRun = solverRunState.status === "loaded" ? solverRunState.run : null;
  const solverToolResult = solverRun?.tool_results?.[0]?.output as Record<string, unknown> | undefined;
  const waitingApproval = solverRun?.status === "awaiting_approval";

  const solverExecutionPerformed = solverToolResult?.solver_execution_performed === true;
  const extractedMetricsSummary = useMemo(
    () => summarizeExtractedMetrics(solverToolResult?.extracted_metrics),
    [solverToolResult?.extracted_metrics],
  );
  const refreshedSummaries = Array.isArray(solverToolResult?.refreshed_summaries)
    ? (solverToolResult?.refreshed_summaries as string[])
    : [];
  const solverWarnings = Array.isArray(solverToolResult?.warnings)
    ? (solverToolResult?.warnings as string[])
    : [];
  const frdExtractionAttempted = solverExecutionPerformed && extractResults;
  const frdExtractionFailedNote = frdExtractionAttempted && !extractedMetricsSummary
    ? solverWarnings.find((w) => /FRD extraction|extraction failed/i.test(w)) ?? null
    : null;

  // Fire onSolverRunCompleted once per completed solver run so the parent can
  // refresh the Computed Metrics and target comparison cards. We only fire when
  // the runtime status reaches "completed" (not awaiting_approval, not failed),
  // and only once per run_id.
  useEffect(() => {
    if (!onSolverRunCompleted) return;
    if (!solverRun) return;
    if (solverRun.status !== "completed") return;
    if (completionNotifiedRunId === solverRun.run_id) return;
    setCompletionNotifiedRunId(solverRun.run_id);
    onSolverRunCompleted();
  }, [solverRun, onSolverRunCompleted, completionNotifiedRunId]);

  return (
    <article className={[
      "copilot-loop__demo-card",
      "structural-adapter-card",
      highlighted ? "readiness-highlight" : "",
      !expanded ? "structural-adapter-card--collapsed" : "",
    ].filter(Boolean).join(" ")}>
      <div className="copilot-loop__demo-health">
        <div className="copilot-loop__demo-health-header">
          <div>
            <strong>Structural adapter readiness</strong>
            <span className="panel__hint">
              Readiness, fixture import, and approval-gated solver review. Mesh is not generated here automatically.
            </span>
          </div>
          <div className="button-row">
            <button
              type="button"
              className="primary-button compact-button"
              onClick={() => void runPreflight()}
              disabled={preflightState.status === "loading"}
            >
              {preflightState.status === "loading" ? "Checking structural adapter..." : "Run structural adapter preflight"}
            </button>
            {onExpandedChange ? (
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={() => onExpandedChange(!expanded)}
              >
                {expanded ? "Collapse" : "Expand"}
              </button>
            ) : null}
          </div>
        </div>

        {!projectId ? (
          <p className="panel__hint">
            No project selected. Environment readiness can still be checked, but project-specific solver-run preview requires a project package.
          </p>
        ) : null}

        {lastRefreshed ? <p className="panel__hint">Last refreshed: {lastRefreshed}</p> : null}

        {!expanded ? (
          <p className="panel__hint">
            Collapsed. Expand to inspect Gmsh / CalculiX / FreeCAD readiness, import a solver-input fixture, and review solver-run preflight conditions.
          </p>
        ) : null}

        {expanded ? (
          <>
            <p className="panel__hint">
              Unavailable is not an error; it means this host lacks the required external tools for structural CAD/CAE execution. AIENG still remains usable for review, import, and evidence workflows.
            </p>

            {preflightState.status === "error" ? (
              <div className="inline-error">Structural preflight failed: {preflightState.message}</div>
            ) : null}

            {response ? (
              <>
                <article className="copilot-loop__subcard">
                  <header className="freecad-inspection-card__result-header">
                    <strong>
                      {response.adapter_label ?? "Structural adapter"}{" "}
                      <span className={preflightBadgeClass(response.preflight.status)}>
                        {response.preflight.status}
                      </span>
                    </strong>
                    <span className="badge badge-muted">claim advancement: none</span>
                  </header>
                  <p className="panel__hint">{response.safety_note}</p>
                  <p className="panel__hint freecad-inspection-card__claim-boundary">{response.claim_boundary}</p>
                  {response.preflight.missing_dependencies.length ? (
                    <>
                      <p className="panel__hint">Missing dependencies:</p>
                      <ul className="artifact-list">
                        {response.preflight.missing_dependencies.map((dep) => (
                          <li key={dep}><code>{dep}</code></li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="panel__hint">All checked dependencies are currently present.</p>
                  )}
                  {response.preflight.warnings.length ? (
                    <ul className="warning-list">
                      {response.preflight.warnings.map((warning, idx) => <li key={idx}>{warning}</li>)}
                    </ul>
                  ) : null}
                  {response.preflight.errors.length ? (
                    <ul className="error-list">
                      {response.preflight.errors.map((error, idx) => <li key={idx}>{error}</li>)}
                    </ul>
                  ) : null}
                  {estimatedOutputs.length ? (
                    <>
                      <p className="panel__hint">Estimated outputs if later-approved execution becomes available:</p>
                      <ul className="artifact-list">
                        {estimatedOutputs.map((path) => <li key={path}><code>{path}</code></li>)}
                      </ul>
                    </>
                  ) : null}
                </article>

                {checkedPaths.length ? (
                  <article className="copilot-loop__subcard">
                    <strong>Checked paths</strong>
                    <div className="table-scroll">
                      <table className="mini-table">
                        <thead>
                          <tr>
                            <th>Dependency</th>
                            <th>Path</th>
                            <th>Present</th>
                          </tr>
                        </thead>
                        <tbody>
                          {checkedPaths.map(([key, value]) => (
                            <tr key={key}>
                              <td><code>{key}</code></td>
                              <td><code>{value.path}</code></td>
                              <td>{value.present ? "yes" : "no"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </article>
                ) : null}

                <article className="copilot-loop__subcard">
                  <strong>Capability manifest</strong>
                  <p className="panel__hint">
                    The manifest shows what structural operations AIENG may wrap later. This card does not execute any of them.
                  </p>
                  <div className="copilot-stepper">
                    {capabilities.map((capability) => (
                      <article key={capability.id} className="copilot-step copilot-step--not_started">
                        <header className="copilot-step__header">
                          <div>
                            <strong>{capability.label}</strong>
                            <span>{capabilitySummary(capability)}</span>
                          </div>
                          <div className="copilot-step__badges">
                            <span className="badge">{capability.category}</span>
                            {capability.requires_approval ? <span className="badge badge-warn">approval</span> : null}
                          </div>
                        </header>
                        <div className="copilot-loop__action-safety">
                          {boolBadge(capability.mutates_package, "mutates package", "no package mutation")}
                          {boolBadge(capability.runs_external_process, "runs external process", "no external process")}
                          {boolBadge(capability.expensive, "expensive", "not expensive")}
                          <span className="safety-badge safety-badge--ok">claim advancement: {capability.claim_advancement}</span>
                        </div>
                        {capability.output_artifacts.length ? (
                          <>
                            <p className="panel__hint">Output artifacts:</p>
                            <ul className="artifact-list">
                              {capability.output_artifacts.map((artifact) => <li key={artifact}><code>{artifact}</code></li>)}
                            </ul>
                          </>
                        ) : null}
                        {capability.stale_artifacts_on_success.length ? (
                          <>
                            <p className="panel__hint">Artifacts that would become stale on success:</p>
                            <ul className="artifact-list">
                              {capability.stale_artifacts_on_success.map((artifact) => <li key={artifact}><code>{artifact}</code></li>)}
                            </ul>
                          </>
                        ) : null}
                      </article>
                    ))}
                  </div>
                </article>
              </>
            ) : (
              <p className="panel__hint">
                Run the structural adapter preflight to inspect this environment before attempting any future structural CAD/CAE execution workflow.
              </p>
            )}

            {projectId ? (
              <article className="copilot-loop__subcard">
                <header className="freecad-inspection-card__result-header">
                  <strong>Structural fixture deck import</strong>
                  <span className="badge badge-warn">explicit write</span>
                </header>
                <p className="panel__hint">
                  Paste a CalculiX <code>.inp</code> deck and explicitly import it into <code>simulation/runs/{runId}/solver_input.inp</code>. This writes only the deck artifact; it does not run a solver.
                </p>
                <div className="freecad-inspection-card__edit-grid">
                  <label className="field-stack">
                    <span>Run ID</span>
                    <input value={runId} onChange={(event) => setRunId(event.target.value)} />
                  </label>
                  <label className="field-stack">
                    <span>Load case ID</span>
                    <input value={loadCaseId} onChange={(event) => setLoadCaseId(event.target.value)} />
                  </label>
                </div>
                <label className="field-stack">
                  <span>CalculiX solver input (.inp)</span>
                  <textarea
                    rows={10}
                    value={deckText}
                    placeholder="*HEADING&#10;Bracket fixture&#10;*NODE&#10;...&#10;*STEP&#10;*STATIC&#10;*END STEP"
                    onChange={(event) => setDeckText(event.target.value)}
                  />
                </label>
                <div className="button-row">
                  <button
                    type="button"
                    className="primary-button compact-button"
                    onClick={() => void importSolverInput()}
                    disabled={importState.status === "loading" || !deckText.trim()}
                  >
                    {importState.status === "loading" ? "Importing deck..." : "Import solver input deck"}
                  </button>
                  <button
                    type="button"
                    className="ghost-button compact-button"
                    onClick={() => void runPreparePreview()}
                    disabled={previewState.status === "loading"}
                  >
                    {previewState.status === "loading" ? "Reviewing preflight..." : "Review solver-run preflight"}
                  </button>
                </div>
                <div className="copilot-loop__action-safety">
                  <span className="safety-badge">import is explicit user action</span>
                  <span className="safety-badge safety-badge--ok">no solver execution</span>
                  <span className="safety-badge safety-badge--ok">no claim advancement</span>
                </div>
                <label className="field-stack">
                  <span>
                    <input type="checkbox" checked={extractResults} onChange={(event) => setExtractResults(event.target.checked)} /> Extract results after a future run
                  </span>
                </label>
                <label className="field-stack">
                  <span>
                    <input type="checkbox" checked={refreshSummary} onChange={(event) => setRefreshSummary(event.target.checked)} /> Refresh summaries after a future run
                  </span>
                </label>
                {importState.status === "error" ? <div className="inline-error">Deck import failed: {importState.message}</div> : null}
                {imported ? (
                  <div className="freecad-inspection-card__edit-result freecad-inspection-card__edit-result--ok">
                    <strong>Deck imported</strong>
                    <p className="panel__hint">Artifact: <code>{imported.artifact.path}</code></p>
                    <p className="panel__hint">Keyword count: {imported.keyword_count}</p>
                    {imported.keywords.length ? <p className="panel__hint">Keywords: {imported.keywords.join(", ")}</p> : null}
                    {imported.warnings.length ? (
                      <ul className="warning-list">
                        {imported.warnings.map((warning, idx) => <li key={idx}>{warning}</li>)}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ) : null}

            {previewState.status === "error" ? (
              <div className="inline-error">Structural prepare preview failed: {previewState.message}</div>
            ) : null}

            {prepareResponse ? (
              <article className="copilot-loop__subcard">
                <header className="freecad-inspection-card__result-header">
                  <strong>
                    Structural solver-run preflight review{" "}
                    <span className={runReadyBadge(prepareResponse.ready_to_run)}>
                      {prepareResponse.ready_to_run ? "ready_to_run" : "not_ready"}
                    </span>
                  </strong>
                  <span className="badge badge-muted">read-only</span>
                </header>
                <p className="panel__hint">{prepareResponse.safety_note}</p>
                <p className="panel__hint freecad-inspection-card__claim-boundary">{prepareResponse.claim_boundary}</p>
                <dl className="compact-dl">
                  <dt>Run ID</dt>
                  <dd><code>{prepareResponse.run_id ?? runId}</code></dd>
                  <dt>Load case</dt>
                  <dd><code>{prepareResponse.load_case_id ?? loadCaseId}</code></dd>
                  <dt>Input deck</dt>
                  <dd><code>{prepareResponse.input_deck_artifact ?? `simulation/runs/${runId}/solver_input.inp`}</code></dd>
                  <dt>Approval</dt>
                  <dd>{prepareResponse.requires_approval ? "required for future execution" : "not required"}</dd>
                </dl>
                {prepareResponse.preflight ? (
                  <div className="table-scroll">
                    <table className="mini-table">
                      <thead>
                        <tr><th>Check</th><th>Status</th></tr>
                      </thead>
                      <tbody>
                        <tr><td>Mesh present</td><td>{prepareResponse.preflight.has_mesh ? "yes" : "no"}</td></tr>
                        <tr><td>Solver settings present</td><td>{prepareResponse.preflight.has_solver_settings ? "yes" : "no"}</td></tr>
                        <tr><td>Load case present</td><td>{prepareResponse.preflight.has_load_case ? "yes" : "no"}</td></tr>
                        <tr><td>Input deck present</td><td>{prepareResponse.preflight.has_input_deck ? "yes" : "no"}</td></tr>
                        <tr><td>ccx available</td><td>{prepareResponse.preflight.ccx_available ? "yes" : "no"}</td></tr>
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {prepareResponse.preflight?.missing_items.length ? (
                  <>
                    <p className="panel__hint">Missing items:</p>
                    <ul className="artifact-list">
                      {prepareResponse.preflight.missing_items.map((item) => <li key={item}><code>{item}</code></li>)}
                    </ul>
                  </>
                ) : (
                  <p className="panel__hint">No missing preflight items reported.</p>
                )}
                {prepareResponse.warnings.length ? (
                  <ul className="warning-list">
                    {prepareResponse.warnings.map((warning, idx) => <li key={idx}>{warning}</li>)}
                  </ul>
                ) : null}
                {prepareResponse.planned_artifacts?.length ? (
                  <>
                    <p className="panel__hint">Artifacts a future approved run could write:</p>
                    <ul className="artifact-list">
                      {prepareResponse.planned_artifacts.map((artifact) => <li key={artifact.path}><code>{artifact.path}</code></li>)}
                    </ul>
                  </>
                ) : null}
              </article>
            ) : null}

            {projectId ? (
              <article className="copilot-loop__subcard">
                <header className="freecad-inspection-card__result-header">
                  <strong>Approval-gated structural solver run</strong>
                  <span className="badge badge-warn">approval required</span>
                </header>
                <p className="panel__hint">
                  This reuses the existing <code>cae.run_solver</code> runtime tool. Starting a run does not execute it silently: the request pauses for approval first, and unavailable <code>ccx</code> is reported honestly after approval.
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="primary-button compact-button"
                    onClick={() => void startSolverRun()}
                    disabled={solverRunState.status === "starting" || !prepareResponse?.ready_to_run}
                  >
                    {solverRunState.status === "starting" ? "Submitting run..." : "Start approval-gated solver run"}
                  </button>
                  {!prepareResponse?.ready_to_run ? (
                    <span className="panel__hint">Run the preflight review first and resolve missing items before starting.</span>
                  ) : null}
                </div>
                <div className="copilot-loop__action-safety">
                  <span className="safety-badge">explicit user action</span>
                  <span className="safety-badge">approval gate preserved</span>
                  <span className="safety-badge safety-badge--ok">claim advancement: none</span>
                </div>
                {solverRunState.status === "error" ? <div className="inline-error">Solver run request failed: {solverRunState.message}</div> : null}
                {solverRun ? (
                  <div className={`freecad-inspection-card__edit-result ${solverRun.status === "completed" ? "freecad-inspection-card__edit-result--ok" : "freecad-inspection-card__edit-result--warn"}`}>
                    <strong>Runtime run status: {solverRun.status}</strong>
                    <p className="panel__hint">Run ID: <code>{solverRun.run_id}</code></p>
                    <p className="panel__hint">{solverRun.summary}</p>
                    {waitingApproval ? (
                      <>
                        <p className="panel__hint">Approving will attempt real solver execution using the imported deck. Rejecting is not an error and leaves the package unchanged by the solver.</p>
                        <div className="button-row">
                          <button
                            type="button"
                            className="primary-button compact-button"
                            onClick={() => void approveSolverRun()}
                            disabled={solverRunState.status === "starting"}
                          >
                            Approve & run solver
                          </button>
                          <button
                            type="button"
                            className="ghost-button compact-button danger"
                            onClick={() => void rejectSolverRun()}
                            disabled={solverRunState.status === "starting"}
                          >
                            Reject
                          </button>
                        </div>
                      </>
                    ) : null}
                    {solverToolResult ? (
                      <>
                        {typeof solverToolResult.message === "string" ? <p className="panel__hint">{solverToolResult.message}</p> : null}
                        <dl className="compact-dl">
                          <dt>Tool status</dt>
                          <dd><code>{String(solverToolResult.status ?? "unknown")}</code></dd>
                          <dt>Executed</dt>
                          <dd>{solverToolResult.solver_execution_performed ? "yes" : "no"}</dd>
                          <dt>Return code</dt>
                          <dd>{solverToolResult.return_code === undefined ? "n/a" : String(solverToolResult.return_code)}</dd>
                        </dl>
                        {Array.isArray(solverToolResult.artifacts) && solverToolResult.artifacts.length ? (
                          <>
                            <p className="panel__hint">Artifacts written:</p>
                            <ul className="artifact-list">
                              {(solverToolResult.artifacts as Array<{ path?: string }>).map((artifact, idx) => artifact?.path ? <li key={`${artifact.path}-${idx}`}><code>{artifact.path}</code></li> : null)}
                            </ul>
                          </>
                        ) : null}
                        {Array.isArray(solverToolResult.warnings) && solverToolResult.warnings.length ? (
                          <ul className="warning-list">
                            {(solverToolResult.warnings as string[]).map((warning, idx) => <li key={idx}>{warning}</li>)}
                          </ul>
                        ) : null}
                        {Array.isArray(solverToolResult.errors) && solverToolResult.errors.length ? (
                          <ul className="error-list">
                            {(solverToolResult.errors as string[]).map((error, idx) => <li key={idx}>{error}</li>)}
                          </ul>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ) : null}

            {solverExecutionPerformed ? (
              <article className="copilot-loop__subcard">
                <header className="freecad-inspection-card__result-header">
                  <strong>
                    Post-run result extraction{" "}
                    <span className={extractedMetricsSummary ? "badge badge-pass" : frdExtractionFailedNote ? "badge badge-fail" : "badge badge-muted"}>
                      {extractedMetricsSummary
                        ? "extracted"
                        : frdExtractionFailedNote
                          ? "extraction failed"
                          : extractResults
                            ? "no FRD produced"
                            : "skipped"}
                    </span>
                  </strong>
                  <span className="badge badge-muted">claim advancement: none</span>
                </header>
                <p className="panel__hint">
                  Extracted metrics are evidence inputs only; they do not certify the design or advance engineering claims. Failed extraction never fabricates values.
                </p>
                {extractedMetricsSummary ? (
                  <>
                    <dl className="compact-dl">
                      <dt>Load cases extracted</dt>
                      <dd>{extractedMetricsSummary.loadCaseCount}</dd>
                      <dt>Metrics extracted</dt>
                      <dd>{extractedMetricsSummary.metricCount}</dd>
                    </dl>
                    {extractedMetricsSummary.globalMetricNames.length ? (
                      <>
                        <p className="panel__hint">Global metrics:</p>
                        <ul className="artifact-list">
                          {extractedMetricsSummary.globalMetricNames.map((name) => (
                            <li key={`global-${name}`}><code>{name}</code></li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {extractedMetricsSummary.loadCaseSamples.length ? (
                      <>
                        <p className="panel__hint">Per-load-case metrics:</p>
                        <ul className="artifact-list">
                          {extractedMetricsSummary.loadCaseSamples.map((sample) => (
                            <li key={`lc-${sample.loadCaseId}`}>
                              <code>{sample.loadCaseId}</code>:{" "}
                              {sample.metricNames.length
                                ? sample.metricNames.map((m) => <code key={m} style={{ marginRight: 4 }}>{m}</code>)
                                : <span className="panel__hint">(no metrics)</span>}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    <p className="panel__hint">
                      The Computed Metrics card and Target Comparison now reflect these solver-generated metrics — no separate import step.
                    </p>
                  </>
                ) : frdExtractionFailedNote ? (
                  <>
                    <p className="panel__hint">FRD extraction did not complete. The package was not updated with computed metrics.</p>
                    <ul className="warning-list">
                      <li>{frdExtractionFailedNote}</li>
                    </ul>
                  </>
                ) : extractResults ? (
                  <p className="panel__hint">
                    No FRD result file was produced by the solver run, so no metrics could be extracted. The package was not updated.
                  </p>
                ) : (
                  <p className="panel__hint">
                    Extraction was disabled for this run (the &quot;Extract results&quot; checkbox was off). To close the loop, re-run with extraction enabled.
                  </p>
                )}
                {refreshedSummaries.length ? (
                  <>
                    <p className="panel__hint">Refreshed summaries:</p>
                    <div className="copilot-loop__action-safety">
                      {refreshedSummaries.map((name) => (
                        <span key={name} className="safety-badge safety-badge--ok">{name}</span>
                      ))}
                    </div>
                  </>
                ) : null}
              </article>
            ) : null}
          </>
        ) : null}
      </div>
    </article>
  );
}
