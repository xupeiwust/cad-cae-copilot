import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import type { CopilotLoop, CopilotLoopDemoSmokeCheckItem, CopilotLoopStep, CopilotLoopSummary, CopilotLoopToolCall, ProjectHealthCheckItem, ProjectHealthCheckResponse, ProjectHealthRecommendedAction } from "../../types";
import { PointerText } from "../PointerText";
import { CopilotLoopComparePanel, CopilotLoopHistoryTable } from "./CopilotLoopHistory";
import { ComputedMetricsCard } from "./ComputedMetricsCard";
import { DesignTargetsCard } from "./DesignTargetsCard";
import { EngineeringTemplateAuthoringCard } from "./EngineeringTemplateAuthoringCard";
import { FreeCadInspectionCard } from "./FreeCadInspectionCard";
import { ReviewSupportPacketCard } from "./ReviewSupportPacketCard";
import { StructuralAdapterCard } from "./StructuralAdapterCard";

function statusClass(status: string): string {
  if (status === "completed") return "badge badge-pass";
  if (status === "error") return "badge badge-fail";
  if (status === "partial" || status === "waiting_for_approval" || status === "running") return "badge badge-warn";
  if (status === "skipped") return "badge";
  return "badge badge-muted";
}

function kindLabel(kind: string): string {
  if (kind === "read_only") return "read-only";
  if (kind === "mutation") return "mutation";
  if (kind === "expensive") return "expensive";
  if (kind === "postprocess") return "postprocess";
  return "review";
}

type ReadinessSection =
  | "project_health"
  | "design_targets"
  | "computed_metrics"
  | "freecad_inspection"
  | "structural_adapter"
  | "copilot_stepper"
  | "loop_history"
  | "report_compare"
  | "stale_evidence";

function sectionForHealthAction(action: ProjectHealthRecommendedAction): ReadinessSection | null {
  const targetSection = action.target?.section;
  if (
    targetSection === "project_health" ||
    targetSection === "design_targets" ||
    targetSection === "computed_metrics" ||
    targetSection === "freecad_inspection" ||
    targetSection === "structural_adapter" ||
    targetSection === "copilot_stepper" ||
    targetSection === "loop_history" ||
    targetSection === "report_compare" ||
    targetSection === "stale_evidence"
  ) {
    return targetSection;
  }
  if (action.id === "add_design_targets") return "design_targets";
  if (action.id === "import_computed_metrics") return "computed_metrics";
  if (action.id === "inspect_cad_features" || action.id === "add_editable_params") return "freecad_inspection";
  if (action.id === "start_loop" || action.id === "run_another_loop") return "copilot_stepper";
  if (action.id === "generate_reports" || action.id === "compare_loops") return "loop_history";
  if (action.id === "review_stale") return "stale_evidence";
  return null;
}

function labelForHealthActionButton(action: ProjectHealthRecommendedAction): string {
  const section = sectionForHealthAction(action);
  if (section === "design_targets") return "Open Design Targets";
  if (section === "computed_metrics") return "Open Computed Metrics";
  if (section === "freecad_inspection") return "Open FreeCAD Inspection";
  if (section === "structural_adapter") return "Open Structural Readiness";
  if (section === "copilot_stepper") return "Go to Copilot Loop";
  if (section === "loop_history") return action.id === "compare_loops" ? "Open report comparison" : "View Loop History";
  if (section === "report_compare") return "Open report comparison";
  if (section === "stale_evidence") return "Review stale evidence";
  if (section === "project_health") return "Open Project Health";
  return "Open section";
}

// v0.33 — contextual approval routing. Maps a Copilot loop step
// (`step.id` from STEP_DEFS in backend/app/copilot_loop.py) to the
// workflow section that should render the approval prompt. Only the
// two steps with `requiresApproval=True` in the backend are routed;
// anything else (unknown id, missing step, multiple simultaneous
// approvals if the runtime ever supports them) falls back to the
// existing root-level approval card so legacy flows keep working.
type ApprovalSectionId = "cad_evidence_change" | "structural_cae";

type ApprovalContext = {
  section: ApprovalSectionId;
  operation: string;
  reason: string;
  safety: string;
};

function approvalContextFor(step: CopilotLoopStep | undefined): ApprovalContext | null {
  if (!step) return null;
  if (step.id === "apply_cad_edit") {
    return {
      section: "cad_evidence_change",
      operation: "Edit FreeCAD parameter",
      reason: "This will modify CAD artifacts and stale downstream evidence.",
      safety: "Approval is required before CAD mutation. Reject leaves the package unchanged.",
    };
  }
  if (step.id === "run_mesh_solver") {
    return {
      section: "structural_cae",
      operation: "Run structural solver",
      reason: "This may run an external process and refresh computed metrics.",
      safety: "Approval is required before running structural CAE. Results remain evidence, not certification.",
    };
  }
  return null;
}

function getNested<T = unknown>(obj: unknown, path: string[]): T | undefined {
  let cur: unknown = obj;
  for (const key of path) {
    if (!cur || typeof cur !== "object" || !(key in cur)) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur as T;
}

function ProposalReviewCard({ loop, step }: { loop: CopilotLoop; step: CopilotLoopStep }) {
  const proposal = loop.context?.selected_proposal as Record<string, unknown> | undefined;
  if (!proposal) {
    if (step.status === "skipped" || step.status === "not_started") {
      return (
        <article className="copilot-loop__subcard copilot-loop__subcard--empty">
          <strong>No CAD modification proposal</strong>
          <p className="panel__hint">
            The recommendation step did not return an applicable proposal for the current evidence. This is an honest empty state; nothing was applied.
          </p>
        </article>
      );
    }
    return null;
  }
  const change = proposal.parameter_change as Record<string, unknown> | undefined;
  const targets = Array.isArray(proposal.targets_addressed) ? proposal.targets_addressed.join(", ") : "";
  return (
    <article className="copilot-loop__subcard">
      <strong>Selected proposal</strong>
      <dl className="compact-dl">
        <dt>Feature</dt>
        <dd>{String(proposal.feature_ref ?? "unknown")}</dd>
        <dt>Action</dt>
        <dd>{String(proposal.action_type ?? "unknown")}</dd>
        <dt>Parameter</dt>
        <dd>
          {String(change?.name ?? "n/a")}: {String(change?.from ?? "?")} → {String(change?.to ?? "?")}
        </dd>
        {targets ? (
          <>
            <dt>Targets</dt>
            <dd>{targets}</dd>
          </>
        ) : null}
      </dl>
      <p className="panel__hint">This is a hypothesis/proposal, not evidence. It must be approved, executed, and re-simulated before design acceptance.</p>
    </article>
  );
}

function VerificationResultCard({ step }: { step: CopilotLoopStep }) {
  const verdict = getNested<Record<string, unknown>>(step.data, ["verdict"]);
  if (!verdict) {
    if (step.status === "skipped") {
      return (
        <article className="copilot-loop__subcard copilot-loop__subcard--empty">
          <strong>Verification skipped</strong>
          <p className="panel__hint">No proposal was available, so no verification verdict was produced.</p>
        </article>
      );
    }
    return null;
  }
  const checks = Array.isArray(verdict.checks) ? verdict.checks as Array<Record<string, unknown>> : [];
  const verdictKind = String(verdict.verdict);
  return (
    <article className="copilot-loop__subcard">
      <strong>
        Verification result:{" "}
        <span className={statusClass(verdictKind === "fail" ? "error" : verdictKind === "warn" ? "partial" : "completed")}>
          {verdictKind}
        </span>
      </strong>
      {verdictKind === "fail" ? (
        <p className="panel__hint">A failed verdict blocks the CAD mutation. The mutation step will be skipped, not retried silently.</p>
      ) : null}
      {checks.length ? (
        <ul className="copilot-loop__checks">
          {checks.map((check, idx) => (
            <li key={`${String(check.check_id ?? idx)}`}>
              <span className={statusClass(check.status === "fail" ? "error" : check.status === "warn" ? "partial" : "completed")}>{String(check.status)}</span>
              <code>{String(check.check_id ?? "check")}</code>
              <span>{String(check.message ?? "")}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function MetricComparisonCard({ loop, step }: { loop: CopilotLoop; step: CopilotLoopStep }) {
  const rows = getNested<Array<Record<string, unknown>>>(loop.context, ["metric_comparison", "metrics"]);
  if (!rows?.length) {
    if (step.status === "skipped" || step.status === "partial" || step.status === "not_started") {
      return (
        <article className="copilot-loop__subcard copilot-loop__subcard--empty">
          <strong>No before/after metric delta available</strong>
          <p className="panel__hint">
            Either the package has no computed metrics for comparison, or the solver did not run. Comparison is not faked when evidence is missing.
          </p>
        </article>
      );
    }
    return null;
  }
  return (
    <article className="copilot-loop__subcard">
      <strong>Metric comparison</strong>
      <div className="table-scroll">
        <table className="mini-table">
          <thead>
            <tr><th>Metric</th><th>Before</th><th>After</th><th>Delta</th><th>Direction</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={String(row.metric)}>
                <td>{String(row.metric)}</td>
                <td>{row.before === null || row.before === undefined ? "—" : String(row.before)}</td>
                <td>{row.after === null || row.after === undefined ? "—" : String(row.after)}</td>
                <td>{row.delta === null || row.delta === undefined ? "—" : String(row.delta)}</td>
                <td>{String(row.direction ?? "unknown")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="panel__hint">Comparison is based on available computed metrics. This does not certify the design.</p>
    </article>
  );
}

function StaleEvidenceCard({ step, loop }: { step: CopilotLoopStep; loop: CopilotLoop }) {
  const apply = loop.steps.find((s) => s.id === "apply_cad_edit");
  if (apply?.status === "skipped" && step.status === "skipped") {
    return (
      <article className="copilot-loop__subcard copilot-loop__subcard--empty">
        <strong>No new stale evidence</strong>
        <p className="panel__hint">No CAD edit was applied, so no downstream evidence was invalidated by this loop.</p>
      </article>
    );
  }
  if (step.status === "skipped") {
    return (
      <article className="copilot-loop__subcard copilot-loop__subcard--empty">
        <strong>No stale evidence marker present</strong>
        <p className="panel__hint">
          The package does not currently declare any geometry-dependent artifacts as stale. If a geometry change happened outside the loop, run the revalidation tool to record it.
        </p>
      </article>
    );
  }
  if (!step.artifacts?.length) return null;
  return (
    <article className="copilot-loop__subcard">
      <strong>Stale downstream artifacts</strong>
      <p className="panel__hint">These artifacts remain in the package for audit but must not be cited as evidence for the modified geometry until they are regenerated.</p>
      <ul className="artifact-list">
        {step.artifacts.slice(0, 12).map((artifact) => (
          <li key={artifact.path}><code>{artifact.path}</code></li>
        ))}
      </ul>
      {step.artifacts.length > 12 ? <p className="panel__hint">+{step.artifacts.length - 12} more stale artifact(s)</p> : null}
    </article>
  );
}

function SolverReadinessCard({ step }: { step: CopilotLoopStep }) {
  if (step.id !== "run_mesh_solver") return null;
  if (step.status === "skipped" || step.status === "error" || step.status === "partial") {
    return (
      <article className="copilot-loop__subcard copilot-loop__subcard--empty">
        <strong>Mesh/solver not executed</strong>
        <p className="panel__hint">
          Preflight indicated the solver toolchain is unavailable or the input deck is missing on this host. Missing FreeCAD/Gmsh/CalculiX does not produce fake success.
        </p>
      </article>
    );
  }
  return null;
}

function LoopReportCard({ loop, step }: { loop: CopilotLoop; step: CopilotLoopStep }) {
  const report = loop.context?.report as Record<string, unknown> | undefined;
  if (!report) {
    if (step.status === "not_started") {
      return (
        <article className="copilot-loop__subcard copilot-loop__subcard--empty">
          <strong>Report not generated yet</strong>
          <p className="panel__hint">Advance the loop to the final step to write the closed-loop Copilot report into the package.</p>
        </article>
      );
    }
    if (step.status === "partial") {
      return (
        <article className="copilot-loop__subcard copilot-loop__subcard--empty">
          <strong>Report generated locally only</strong>
          <p className="panel__hint">The report markdown was generated but could not be written into the .aieng package. Check the warnings above.</p>
        </article>
      );
    }
    return null;
  }
  const markdown = typeof report.markdown === "string" ? report.markdown : "";
  return (
    <article className="copilot-loop__subcard">
      <strong>Loop report</strong>
      {report.artifact_path ? <p>Package artifact: <code>{String(report.artifact_path)}</code></p> : null}
      {markdown ? <pre className="markdown-preview">{markdown.slice(0, 4000)}</pre> : null}
    </article>
  );
}

function ToolCalls({ calls }: { calls?: CopilotLoopToolCall[] }) {
  if (!calls?.length) return null;
  return (
    <ul className="copilot-loop__toolcalls">
      {calls.map((call, idx) => (
        <li key={`${call.toolName}-${call.runId ?? idx}`}>
          <code>{call.toolName}</code>
          <span className={statusClass(call.status)}>{call.status}</span>
          {call.runId ? <small>run {call.runId}</small> : null}
        </li>
      ))}
    </ul>
  );
}

function StepCard({ step, loop }: { step: CopilotLoopStep; loop: CopilotLoop }) {
  return (
    <article className={`copilot-step copilot-step--${step.status}`}>
      <header className="copilot-step__header">
        <div>
          <strong><PointerText text={step.title} /></strong>
          <span><PointerText text={step.summary} /></span>
        </div>
        <div className="copilot-step__badges">
          <span className={statusClass(step.status)}>{step.status}</span>
          <span className="badge">{kindLabel(step.kind)}</span>
          {step.requiresApproval ? <span className="badge badge-warn">approval</span> : null}
        </div>
      </header>
      {step.limitation ? <p className="panel__hint"><PointerText text={step.limitation} /></p> : null}
      {step.warnings?.length ? (
        <ul className="warning-list">
          {step.warnings.map((warning, idx) => <li key={idx}><PointerText text={warning} /></li>)}
        </ul>
      ) : null}
      {step.errors?.length ? (
        <ul className="error-list">
          {step.errors.map((error, idx) => <li key={idx}><PointerText text={error} /></li>)}
        </ul>
      ) : null}
      <ToolCalls calls={step.toolCalls} />
      {step.artifacts?.length ? (
        <ul className="artifact-list">
          {step.artifacts.map((artifact) => <li key={artifact.path}><code>{artifact.path}</code> {artifact.label ? <span>{artifact.label}</span> : null}</li>)}
        </ul>
      ) : null}
      {step.id === "recommend_modification" ? <ProposalReviewCard loop={loop} step={step} /> : null}
      {step.id === "verify_proposal" ? <VerificationResultCard step={step} /> : null}
      {step.id === "mark_stale" ? <StaleEvidenceCard step={step} loop={loop} /> : null}
      {step.id === "run_mesh_solver" ? <SolverReadinessCard step={step} /> : null}
      {step.id === "compare_targets" ? <MetricComparisonCard loop={loop} step={step} /> : null}
      {step.id === "generate_report" ? <LoopReportCard loop={loop} step={step} /> : null}
    </article>
  );
}

type CopilotLoopPanelProps = {
  selectedId: string | null;
  onSelectProject?: (projectId: string) => void;
};

export function CopilotLoopPanel({ selectedId, onSelectProject }: CopilotLoopPanelProps) {
  const [loop, setLoop] = useState<CopilotLoop | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoredFromHistory, setRestoredFromHistory] = useState(false);
  const [summaries, setSummaries] = useState<CopilotLoopSummary[]>([]);
  const [compareSelection, setCompareSelection] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const projectHealthRef = useRef<HTMLElement | null>(null);
  const designTargetsRef = useRef<HTMLDivElement | null>(null);
  const computedMetricsRef = useRef<HTMLDivElement | null>(null);
  const freeCadInspectionRef = useRef<HTMLDivElement | null>(null);
  const structuralAdapterRef = useRef<HTMLDivElement | null>(null);
  const copilotStepperRef = useRef<HTMLElement | null>(null);
  const loopHistoryRef = useRef<HTMLDivElement | null>(null);
  const reportCompareRef = useRef<HTMLDivElement | null>(null);
  const [designTargetsExpanded, setDesignTargetsExpanded] = useState(true);
  const [computedMetricsExpanded, setComputedMetricsExpanded] = useState(true);
  const [freeCadInspectionExpanded, setFreeCadInspectionExpanded] = useState(true);
  const [structuralAdapterExpanded, setStructuralAdapterExpanded] = useState(false);
  const [freeCadInspectionRefreshKey, setFreeCadInspectionRefreshKey] = useState(0);
  const [designTargetsRefreshKey, setDesignTargetsRefreshKey] = useState(0);
  const [computedMetricsRefreshKey, setComputedMetricsRefreshKey] = useState(0);
  const [highlightedReadinessSection, setHighlightedReadinessSection] = useState<ReadinessSection | null>(null);
  const [readinessGuidance, setReadinessGuidance] = useState<string | null>(null);
  const [healthRerunPrompt, setHealthRerunPrompt] = useState(false);
  type DemoState =
    | { status: "idle" }
    | { status: "loading"; action: "seed" | "reset" }
    | { status: "error"; message: string }
    | {
        status: "loaded";
        seededProjectId: string;
        projectName: string;
        loopCount: number;
        reused: boolean;
        nextAction: string;
      };
  const [demoState, setDemoState] = useState<DemoState>({ status: "idle" });
  type SmokeCheckState =
    | { status: "idle" }
    | { status: "loading"; reset?: boolean }
    | { status: "loaded"; result: { ok: boolean; project_id?: string; reused?: boolean; checks: CopilotLoopDemoSmokeCheckItem[]; export_path?: string | null; warnings: string[]; claim_boundary: string } }
    | { status: "error"; message: string };
  const [smokeCheckState, setSmokeCheckState] = useState<SmokeCheckState>({ status: "idle" });
  type HealthCheckState =
    | { status: "idle" }
    | { status: "loading" }
    | { status: "loaded"; result: ProjectHealthCheckResponse }
    | { status: "error"; message: string };
  const [healthCheckState, setHealthCheckState] = useState<HealthCheckState>({ status: "idle" });

  const waitingStep = useMemo(
    () => loop?.steps.find((step) => step.status === "waiting_for_approval"),
    [loop],
  );
  const nextStep = useMemo(
    () => loop?.steps.find((step) => step.status === "not_started"),
    [loop],
  );
  const loopRejected = useMemo(
    () => Boolean(loop?.context && (loop.context as Record<string, unknown>).apply_rejected),
    [loop],
  );
  // v0.33 — route the active approval prompt to the workflow section that
  // triggered it. Returns null for unknown / legacy / multi-approval cases,
  // which keeps the existing root-level approval card visible as fallback.
  const waitingApprovalContext = useMemo(
    () => approvalContextFor(waitingStep),
    [waitingStep],
  );

  const refreshHistory = useCallback(async (projectId: string) => {
    try {
      const listing = await api.listCopilotLoops(projectId);
      setSummaries(listing.loops ?? []);
      return listing.loops ?? [];
    } catch (err) {
      // Listing is best-effort. Leave the existing summaries in place.
      // eslint-disable-next-line no-console
      console.warn("copilot loop listing failed", err);
      return [] as CopilotLoopSummary[];
    }
  }, []);

  // On project change: refresh history and silently restore the most recent
  // loop. The runtime persists loop state on every advance/approve/reject.
  useEffect(() => {
    if (!selectedId) {
      setLoop(null);
      setRestoredFromHistory(false);
      setSummaries([]);
      setCompareSelection([]);
      setCompareOpen(false);
      setReadinessGuidance(null);
      setHighlightedReadinessSection(null);
      setHealthRerunPrompt(false);
      return;
    }
    let cancelled = false;
    (async () => {
      const loops = await refreshHistory(selectedId);
      if (cancelled) return;
      const newest = loops[0];
      if (!newest) {
        setLoop(null);
        setRestoredFromHistory(false);
        return;
      }
      try {
        const full = await api.getCopilotLoop(selectedId, newest.loop_id);
        if (cancelled) return;
        setLoop(full);
        setRestoredFromHistory(true);
      } catch (err) {
        if (cancelled) return;
        setLoop(null);
        setRestoredFromHistory(false);
        // eslint-disable-next-line no-console
        console.warn("copilot loop recovery failed", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshHistory]);

  const runAction = useCallback(async (action: "start" | "advance" | "approve" | "reject") => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      let updated: CopilotLoop;
      if (action === "start") {
        updated = await api.startCopilotLoop(selectedId);
        setRestoredFromHistory(false);
      } else if (!loop) {
        throw new Error("Start a loop first.");
      } else if (action === "advance") {
        updated = await api.advanceCopilotLoop(selectedId, loop.loop_id);
      } else if (action === "approve") {
        updated = await api.approveCopilotLoop(selectedId, loop.loop_id);
      } else {
        updated = await api.rejectCopilotLoop(selectedId, loop.loop_id);
      }
      setLoop(updated);
      // Keep the history table in sync — decisions, status, report paths
      // change on advance/approve/reject and history must not go stale.
      void refreshHistory(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [loop, selectedId, refreshHistory]);

  const handleReopen = useCallback(async (loopId: string) => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const full = await api.getCopilotLoop(selectedId, loopId);
      setLoop(full);
      setRestoredFromHistory(true);
      setCompareOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [selectedId]);

  const toggleCompare = useCallback((loopId: string) => {
    setCompareSelection((prev) => {
      if (prev.includes(loopId)) return prev.filter((id) => id !== loopId);
      if (prev.length >= 2) return prev;
      return [...prev, loopId];
    });
  }, []);

  const clearCompare = useCallback(() => {
    setCompareSelection([]);
    setCompareOpen(false);
  }, []);

  const openCompare = useCallback(() => {
    if (compareSelection.length === 2) setCompareOpen(true);
  }, [compareSelection.length]);

  const compareLeft = useMemo(
    () => summaries.find((s) => s.loop_id === compareSelection[0]) ?? null,
    [summaries, compareSelection],
  );
  const compareRight = useMemo(
    () => summaries.find((s) => s.loop_id === compareSelection[1]) ?? null,
    [summaries, compareSelection],
  );

  const seedDemo = useCallback(async (action: "seed" | "reset" = "seed") => {
    setDemoState({ status: "loading", action });
    try {
      const result = await api.seedCopilotLoopDemo(action === "reset" ? { reset: true } : {});
      setDemoState({
        status: "loaded",
        seededProjectId: result.project_id,
        projectName: result.project_name,
        loopCount: result.loops?.length ?? 0,
        reused: Boolean(result.reused),
        nextAction: result.next_action ?? "Compare the rejected and approved loops.",
      });
      if (onSelectProject) {
        onSelectProject(result.project_id);
      }
    } catch (err) {
      setDemoState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [onSelectProject]);

  const runSmokeCheck = useCallback(async (reset = false) => {
    setSmokeCheckState({ status: "loading", reset });
    try {
      const result = await api.runCopilotLoopDemoSmokeCheck({ reset });
      setSmokeCheckState({ status: "loaded", result });
      // If smoke-check created a new demo project, update demoState too.
      if (result.project_id && !result.reused) {
        setDemoState({
          status: "loaded",
          seededProjectId: result.project_id,
          projectName: "Demo · Bracket lightweighting",
          loopCount: 2,
          reused: false,
          nextAction: "Compare the rejected and approved loops.",
        });
        if (onSelectProject) {
          onSelectProject(result.project_id);
        }
      }
    } catch (err) {
      setSmokeCheckState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [onSelectProject]);

  const runHealthCheck = useCallback(async () => {
    if (!selectedId) {
      setHealthCheckState({ status: "error", message: "Select a project first." });
      return;
    }
    setHealthCheckState({ status: "loading" });
    setHealthRerunPrompt(false);
    try {
      const result = await api.getProjectHealthCheck(selectedId);
      setHealthCheckState({ status: "loaded", result });
    } catch (err) {
      setHealthCheckState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [selectedId]);

  const scrollToReadinessSection = useCallback((section: ReadinessSection) => {
    const element =
      section === "project_health"
        ? projectHealthRef.current
        : section === "design_targets"
          ? designTargetsRef.current
          : section === "computed_metrics"
            ? computedMetricsRef.current
            : section === "freecad_inspection"
              ? freeCadInspectionRef.current
              : section === "structural_adapter"
                ? structuralAdapterRef.current
                : section === "loop_history"
                ? loopHistoryRef.current
                : section === "report_compare"
                  ? reportCompareRef.current
                  : copilotStepperRef.current;
    window.setTimeout(() => {
      element?.scrollIntoView({ behavior: "smooth", block: "start" });
      element?.focus?.({ preventScroll: true });
    }, 0);
  }, []);

  const handleHealthActionNavigation = useCallback((action: ProjectHealthRecommendedAction) => {
    const section = sectionForHealthAction(action);
    if (!section) return;
    if (section === "design_targets") {
      setDesignTargetsExpanded(true);
      setDesignTargetsRefreshKey((k) => k + 1);
    }
    if (section === "computed_metrics") {
      setComputedMetricsExpanded(true);
      setComputedMetricsRefreshKey((k) => k + 1);
    }
    if (section === "freecad_inspection") {
      setFreeCadInspectionExpanded(true);
      setFreeCadInspectionRefreshKey((k) => k + 1);
    }
    if (section === "structural_adapter") {
      setStructuralAdapterExpanded(true);
    }
    if (section === "report_compare" && compareSelection.length === 2) setCompareOpen(true);
    setReadinessGuidance(
      `${labelForHealthActionButton(action)} opened as navigation guidance only. Nothing was auto-fixed, saved, approved, or run.`,
    );
    setHighlightedReadinessSection(section);
    scrollToReadinessSection(section);
    window.setTimeout(() => {
      setHighlightedReadinessSection((current) => (current === section ? null : current));
    }, 2600);
  }, [compareSelection.length, scrollToReadinessSection]);

  const handleDesignTargetsSaved = useCallback(() => {
    setHealthRerunPrompt(true);
    setReadinessGuidance("Design targets were saved explicitly. Run Project Health Check again to confirm readiness changed.");
    setHighlightedReadinessSection("project_health");
  }, []);

  const handleComputedMetricsSaved = useCallback(() => {
    setHealthRerunPrompt(true);
    setReadinessGuidance("Computed metrics were imported explicitly. Run Project Health Check again to confirm readiness changed.");
    setHighlightedReadinessSection("project_health");
  }, []);

  const handleFreeCadInspected = useCallback(() => {
    setHealthRerunPrompt(true);
    setReadinessGuidance(
      "FreeCAD feature evidence was written. Read-only — no CAD edit, no solver, no claim advancement. Run Project Health Check again to confirm CAD readiness changed.",
    );
    setHighlightedReadinessSection("project_health");
  }, []);

  const handleStructuralSolverRunCompleted = useCallback(() => {
    // Closing the structural CAE loop: solver run produced new computed metrics
    // inside the .aieng package. Bump the Computed Metrics card so it (and its
    // embedded target-comparison view) re-fetches without re-mounting.
    setComputedMetricsRefreshKey((k) => k + 1);
  }, []);

  const rerunHealthCheckFromPrompt = useCallback(() => {
    scrollToReadinessSection("project_health");
    void runHealthCheck();
  }, [runHealthCheck, scrollToReadinessSection]);

  return (
    <section className="panel-section copilot-loop-panel">
      <header ref={copilotStepperRef} tabIndex={-1} className={`panel-section-header ${highlightedReadinessSection === "copilot_stepper" || highlightedReadinessSection === "stale_evidence" ? "readiness-highlight" : ""}`}>
        <div>
          <span className="eyebrow">Closed-loop Copilot Stepper v0.1</span>
          <h3>Evidence-grounded CAD/CAE loop</h3>
        </div>
        <div className="button-row">
          <button type="button" className="ghost-button compact-button" disabled={!selectedId || busy} onClick={() => void runAction("start")}>
            Start loop
          </button>
          <button type="button" className="primary-button compact-button" disabled={!loop || busy || !!waitingStep || !nextStep} onClick={() => void runAction("advance")}>
            Advance next step
          </button>
        </div>
      </header>
      <div className="claim-boundary-banner">
        <strong>Claim boundary: review record only</strong>
        <p>
          This Copilot loop does not certify designs or advance engineering claims. Fixture data, imported metrics,
          and real solver outputs remain evidence inputs until a qualified engineer accepts a conclusion.
        </p>
      </div>
      <p className="panel__hint">
        This panel composes existing AIENG recommendation, verification, runtime approval, CAE summary, and report
        tools into <strong>six workflow sections</strong>. It is a reviewable Copilot loop, not an autonomous
        engineering agent.
      </p>
      <section className="workflow-section workflow-section--readiness" aria-labelledby="workflow-readiness-header">
        <header className="workflow-section__header">
          <div>
            <span className="workflow-section__eyebrow">1 · Readiness &amp; Guidance</span>
            <h4 id="workflow-readiness-header" className="workflow-section__title">
              Project readiness, demo seed, and recommended next actions
            </h4>
          </div>
        </header>
        <p className="workflow-section__hint">
          Read-only inspection of the selected project, plus a deterministic demo seed and a one-click health check.
          Suggested-action buttons jump straight to the section that needs attention.
        </p>
      <article className="copilot-loop__demo-card">
        <header className="copilot-loop__demo-card-header">
          <div>
            <strong>Try the Copilot Loop demo</strong>
            <p className="panel__hint">
              A 5-minute deterministic walkthrough of the Decision Review Workbench. Creates a bracket-lightweighting fixture project with one rejected and one approved Copilot loop.
            </p>
          </div>
          <div className="button-row">
            <button
              type="button"
              className="primary-button compact-button"
              onClick={() => void seedDemo("seed")}
              disabled={demoState.status === "loading"}
            >
              {demoState.status === "loading" && demoState.action === "seed"
                ? "Seeding…"
                : demoState.status === "loaded"
                  ? "Open demo project"
                  : "Seed demo project"}
            </button>
            {demoState.status === "loaded" ? (
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={() => void seedDemo("reset")}
              >
                Reset demo project
              </button>
            ) : null}
          </div>
        </header>
        <ul className="copilot-loop__demo-bullets">
          <li>Deterministic fixture data — no FreeCAD/Gmsh/CalculiX required.</li>
          <li>Does not certify a design; does not advance engineering claims.</li>
          <li>Demo projects are flagged in metadata so they can be reset without touching real projects.</li>
        </ul>
        <div className="claim-boundary-banner claim-boundary-banner--compact">
          <strong>Demo data boundary</strong>
          <p>
            Fixture loops use mock metrics for repeatable review. Imported metrics and real solver outputs are
            separate evidence inputs; neither one is treated as certification or automatic claim acceptance.
          </p>
        </div>
        {demoState.status === "loaded" ? (
          <div className="copilot-loop__demo-success">
            <strong>{demoState.reused ? "Demo project opened (reused)" : "Demo project ready"}</strong>
            <dl className="compact-dl">
              <dt>Project</dt>
              <dd><code>{demoState.seededProjectId}</code> · {demoState.projectName}</dd>
              <dt>Loops</dt>
              <dd>{demoState.loopCount} pre-baked (one rejected, one approved)</dd>
              <dt>Next step</dt>
              <dd>{demoState.nextAction}</dd>
            </dl>
            {selectedId === demoState.seededProjectId ? (
              <p className="panel__hint">The demo project is now selected. Scroll down to the loop history table.</p>
            ) : (
              <p className="panel__hint">
                Select <code>{demoState.seededProjectId}</code> from the project list to view its loops.
              </p>
            )}
          </div>
        ) : null}
        {demoState.status === "error" ? (
          <div className="inline-error">Failed to {demoState.message.includes("reset") ? "reset" : "seed"} demo: {demoState.message}</div>
        ) : null}

        {/* Demo Health Check */}
        <div className="copilot-loop__demo-health">
          <div className="copilot-loop__demo-health-header">
            <strong>Demo health check</strong>
            <p className="panel__hint">Runs the deterministic demo chain locally to verify seed, compare, export, and claim boundary.</p>
          </div>
          <div className="button-row">
            <button
              type="button"
              className="primary-button compact-button"
              onClick={() => void runSmokeCheck(false)}
              disabled={smokeCheckState.status === "loading"}
            >
              {smokeCheckState.status === "loading" && !smokeCheckState.reset
                ? "Running…"
                : "Run demo health check"}
            </button>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={() => void runSmokeCheck(true)}
              disabled={smokeCheckState.status === "loading"}
            >
              {smokeCheckState.status === "loading" && smokeCheckState.reset
                ? "Running with reset…"
                : "Reset & check"}
            </button>
          </div>
          {smokeCheckState.status === "loaded" ? (
            <div className={`copilot-loop__demo-health-result ${smokeCheckState.result.ok ? "copilot-loop__demo-health-result--pass" : "copilot-loop__demo-health-result--fail"}`}>
              <strong>{smokeCheckState.result.ok ? "Demo health check passed. The local decision-review demo chain is working." : "Demo health check failed locally. Review the failed checklist items below."}</strong>
              {!smokeCheckState.result.ok ? (
                <p className="panel__hint">Fix the failed items before presenting the demo to a reviewer.</p>
              ) : null}
              {smokeCheckState.result.project_id ? (
                <dl className="compact-dl">
                  <dt>Project</dt>
                  <dd><code>{smokeCheckState.result.project_id}</code></dd>
                  {smokeCheckState.result.export_path ? (
                    <>
                      <dt>Export</dt>
                      <dd><code>{smokeCheckState.result.export_path}</code></dd>
                    </>
                  ) : null}
                </dl>
              ) : null}
              {smokeCheckState.result.checks.length ? (
                <ul className="copilot-loop__demo-health-checklist">
                  {smokeCheckState.result.checks.map((c) => (
                    <li key={c.id} className={`copilot-loop__demo-health-check copilot-loop__demo-health-check--${c.status}`}>
                      <span className={`badge ${c.status === "passed" ? "badge-pass" : c.status === "failed" ? "badge-fail" : "badge-warn"}`}>{c.status}</span>
                      <span className="copilot-loop__demo-health-check-label">{c.label}</span>
                      <span className="copilot-loop__demo-health-check-summary">{c.summary}</span>
                      {c.details?.length ? (
                        <ul className="copilot-loop__demo-health-check-details">
                          {c.details.map((d, i) => <li key={i}>{d}</li>)}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {smokeCheckState.result.warnings.length ? (
                <ul className="warning-list">
                  {smokeCheckState.result.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              ) : null}
              {smokeCheckState.result.claim_boundary ? (
                <div className="claim-boundary-banner claim-boundary-banner--compact claim-boundary-snippet">
                  <strong>Claim boundary verified</strong>
                  <p>{smokeCheckState.result.claim_boundary}</p>
                </div>
              ) : null}
            </div>
          ) : null}
          {smokeCheckState.status === "error" ? (
            <div className="inline-error">Smoke check failed: {smokeCheckState.message}</div>
          ) : null}
        </div>
      </article>
      <article ref={projectHealthRef} tabIndex={-1} className={`copilot-loop__demo-card ${highlightedReadinessSection === "project_health" ? "readiness-highlight" : ""}`}>
        <div className="copilot-loop__demo-health">
          <div className="copilot-loop__demo-health-header">
            <strong>Project Health Check</strong>
            <span className="panel__hint">Read-only inspection of the selected project.</span>
          </div>
          {readinessGuidance ? (
            <div className="guided-readiness-hint">
              <strong>Guided readiness</strong>
              <span>{readinessGuidance}</span>
            </div>
          ) : null}
          {healthRerunPrompt ? (
            <div className="guided-readiness-hint guided-readiness-hint--action">
              <span>Project metadata/evidence changed. Re-run the read-only health check to verify the suggested action is resolved.</span>
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={rerunHealthCheckFromPrompt}
                disabled={healthCheckState.status === "loading" || !selectedId}
              >
                Run Project Health Check again
              </button>
            </div>
          ) : null}
          <div className="button-row">
            <button
              type="button"
              className="primary-button compact-button"
              onClick={() => void runHealthCheck()}
              disabled={healthCheckState.status === "loading" || !selectedId}
            >
              {healthCheckState.status === "loading" ? "Running…" : "Run health check"}
            </button>
          </div>
          {healthCheckState.status === "loaded" ? (
            <div className={`copilot-loop__demo-health-result ${healthCheckState.result.readiness === "ready" ? "copilot-loop__demo-health-result--pass" : healthCheckState.result.readiness === "not_ready" ? "copilot-loop__demo-health-result--fail" : "copilot-loop__demo-health-result--warn"}`}>
              <strong>Readiness: {healthCheckState.result.readiness}</strong>
              {healthCheckState.result.overall_next_action ? (
                <p className="panel__hint">{healthCheckState.result.overall_next_action}</p>
              ) : null}
              {healthCheckState.result.checks.length ? (
                <ul className="copilot-loop__demo-health-checklist">
                  {healthCheckState.result.checks.map((item: ProjectHealthCheckItem) => (
                    <li key={item.id} className={`copilot-loop__demo-health-check copilot-loop__demo-health-check--${item.status}`}>
                      <span className={`badge ${item.status === "passed" ? "badge-pass" : item.status === "failed" ? "badge-fail" : item.status === "warning" ? "badge-warn" : "badge-muted"}`}>{item.status}</span>
                      <span className="copilot-loop__demo-health-check-label">{item.label}</span>
                      <span className="copilot-loop__demo-health-check-summary">{item.summary}</span>
                      {item.next_action ? <span className="panel__hint">→ {item.next_action}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {/* Suggested next actions */}
              {healthCheckState.result.recommended_actions.length ? (
                <div className="copilot-loop__actions">
                  <strong className="copilot-loop__actions-title">Suggested next actions</strong>
                  {["high", "medium", "low"].map((priority) => {
                    const group = healthCheckState.result.recommended_actions.filter((a: ProjectHealthRecommendedAction) => a.priority === priority);
                    if (!group.length) return null;
                    return (
                      <div key={priority} className={`copilot-loop__action-group copilot-loop__action-group--${priority}`}>
                        <div className="copilot-loop__action-group-header">
                          <span className={`badge ${priority === "high" ? "badge-fail" : priority === "medium" ? "badge-warn" : "badge-muted"}`}>{priority}</span>
                        </div>
                        <ul className="copilot-loop__action-list">
                          {group.map((action: ProjectHealthRecommendedAction) => {
                            const section = sectionForHealthAction(action);
                            return (
                              <li key={action.id} className="copilot-loop__action-item">
                                <div className="copilot-loop__action-main">
                                  <span className="copilot-loop__action-label">{action.label}</span>
                                  <span className="copilot-loop__action-type">{action.action_type}</span>
                                </div>
                                <p className="copilot-loop__action-summary">{action.summary}</p>
                                <div className="copilot-loop__action-meta">
                                  <span className="panel__hint">Source: {action.source_check_ids.join(", ")}</span>
                                  {section ? (
                                    <button
                                      type="button"
                                      className="ghost-button compact-button copilot-loop__action-button"
                                      onClick={() => handleHealthActionNavigation(action)}
                                    >
                                      {labelForHealthActionButton(action)}
                                    </button>
                                  ) : null}
                                  <span className="copilot-loop__action-safety">
                                    <span className={`safety-badge ${!action.safety.mutates_package ? "safety-badge--ok" : ""}`}>does not mutate package</span>
                                    <span className={`safety-badge ${!action.safety.runs_solver ? "safety-badge--ok" : ""}`}>does not run solver</span>
                                    <span className={`safety-badge ${!action.safety.advances_claim ? "safety-badge--ok" : ""}`}>does not advance claim</span>
                                  </span>
                                </div>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="panel__hint">No suggested actions. This project appears ready for the current Copilot Loop review workflow.</p>
              )}
            </div>
          ) : null}
          {healthCheckState.status === "error" ? (
            <div className="inline-error">Health check failed: {healthCheckState.message}</div>
          ) : null}
        </div>
      </article>
      </section>

      <section className="workflow-section workflow-section--inputs" aria-labelledby="workflow-inputs-header">
        <header className="workflow-section__header">
          <div>
            <span className="workflow-section__eyebrow">2 · Inputs</span>
            <h4 id="workflow-inputs-header" className="workflow-section__title">
              Design targets and computed metrics
            </h4>
          </div>
        </header>
        <p className="workflow-section__hint">
          Author or import the design targets and computed metrics that downstream comparison evaluates.
          Imports are explicit user actions; no solver runs from this section.
        </p>
      <div ref={designTargetsRef} tabIndex={-1}>
        <DesignTargetsCard
          projectId={selectedId}
          onSaved={handleDesignTargetsSaved}
          highlighted={highlightedReadinessSection === "design_targets"}
          expanded={designTargetsExpanded}
          onExpandedChange={setDesignTargetsExpanded}
          showHealthRerunPrompt={healthRerunPrompt}
          onRunHealthCheck={rerunHealthCheckFromPrompt}
          refreshKey={designTargetsRefreshKey}
        />
      </div>
      <div ref={computedMetricsRef} tabIndex={-1}>
        <ComputedMetricsCard
          projectId={selectedId}
          onSaved={handleComputedMetricsSaved}
          highlighted={highlightedReadinessSection === "computed_metrics"}
          expanded={computedMetricsExpanded}
          onExpandedChange={setComputedMetricsExpanded}
          showHealthRerunPrompt={healthRerunPrompt}
          onRunHealthCheck={rerunHealthCheckFromPrompt}
          refreshKey={computedMetricsRefreshKey}
        />
      </div>
      <EngineeringTemplateAuthoringCard
        projectId={selectedId}
        onDraftSaved={() => {
          // Saving a draft adds an informational Project Health check + a new
          // Review Support Packet section. Prompt a health re-run so the
          // reviewer sees the new state without manual refresh.
          setHealthRerunPrompt(true);
          setReadinessGuidance(
            "Engineering template draft saved. Re-run the read-only Project Health Check to see the draft surfaced as an informational check.",
          );
          setHighlightedReadinessSection("project_health");
          setComputedMetricsRefreshKey((k) => k + 1);
        }}
        onTargetsAdopted={() => {
          setHealthRerunPrompt(true);
          setReadinessGuidance(
            "Template target suggestions were explicitly adopted into Design Targets. Re-run Project Health Check to confirm target readiness improved.",
          );
          setHighlightedReadinessSection("project_health");
          setDesignTargetsRefreshKey((k) => k + 1);
        }}
        onCadFixtureGenerated={() => {
          setHealthRerunPrompt(true);
          setReadinessGuidance(
            "Template CAD fixture written. Downstream mesh, solver, metrics, and summaries are now stale until refreshed through approved workflows.",
          );
          setHighlightedReadinessSection("stale_evidence");
        }}
      />
      </section>

      <section className="workflow-section workflow-section--cad" aria-labelledby="workflow-cad-header">
        <header className="workflow-section__header">
          <div>
            <span className="workflow-section__eyebrow">3 · CAD Evidence &amp; Change</span>
            <h4 id="workflow-cad-header" className="workflow-section__title">
              FreeCAD feature inspection and approval-gated parameter edits
            </h4>
          </div>
          <span className="workflow-section__safety">CAD edit requires approval</span>
        </header>
        <p className="workflow-section__hint">
          Read-only inspection writes parsed-feature evidence; parameter edits are approval-gated and never apply silently.
          Missing FreeCAD bridge is reported honestly.
        </p>
      <div ref={freeCadInspectionRef} tabIndex={-1}>
        <FreeCadInspectionCard
          projectId={selectedId}
          highlighted={highlightedReadinessSection === "freecad_inspection"}
          expanded={freeCadInspectionExpanded}
          onExpandedChange={setFreeCadInspectionExpanded}
          onInspected={handleFreeCadInspected}
          showHealthRerunPrompt={healthRerunPrompt}
          onRunHealthCheck={rerunHealthCheckFromPrompt}
          refreshKey={freeCadInspectionRefreshKey}
        />
      </div>
      {waitingStep && waitingApprovalContext?.section === "cad_evidence_change" ? (
        <aside
          className="workflow-section__approval workflow-section__approval--cad"
          role="alert"
          aria-live="polite"
        >
          <div className="workflow-section__approval-title">
            <span className="badge badge-warn">Approval required</span>
            <strong>{waitingApprovalContext.operation}</strong>
          </div>
          <p className="workflow-section__approval-reason">{waitingApprovalContext.reason}</p>
          <p className="panel__hint">{waitingApprovalContext.safety}</p>
          <p className="panel__hint">Rejecting is not an error; it records an honest skipped path and does not execute the operation. The package will remain byte-identical.</p>
          <div className="workflow-section__approval-actions">
            <button
              type="button"
              className="primary-button compact-button"
              disabled={busy}
              onClick={() => void runAction("approve")}
            >
              Approve &amp; execute
            </button>
            <button
              type="button"
              className="ghost-button compact-button danger"
              disabled={busy}
              onClick={() => void runAction("reject")}
            >
              Reject
            </button>
          </div>
        </aside>
      ) : null}
      </section>

      <section className="workflow-section workflow-section--structural" aria-labelledby="workflow-structural-header">
        <header className="workflow-section__header">
          <div>
            <span className="workflow-section__eyebrow">4 · Structural CAE</span>
            <h4 id="workflow-structural-header" className="workflow-section__title">
              Adapter readiness, deck import, and approval-gated solver run
            </h4>
          </div>
          <span className="workflow-section__safety">Structural solver run requires approval</span>
        </header>
        <p className="workflow-section__hint">
          External CalculiX execution runs only after explicit approval. Missing solver tools are reported honestly —
          never faked. After a successful run the closed-loop FRD extraction refreshes Inputs (Section 2) and Target
          Comparison (Section 5).
        </p>
      <div ref={structuralAdapterRef} tabIndex={-1}>
        <StructuralAdapterCard
          projectId={selectedId}
          highlighted={highlightedReadinessSection === "structural_adapter"}
          expanded={structuralAdapterExpanded}
          onExpandedChange={setStructuralAdapterExpanded}
          onSolverRunCompleted={handleStructuralSolverRunCompleted}
        />
      </div>
      {waitingStep && waitingApprovalContext?.section === "structural_cae" ? (
        <aside
          className="workflow-section__approval workflow-section__approval--structural"
          role="alert"
          aria-live="polite"
        >
          <div className="workflow-section__approval-title">
            <span className="badge badge-warn">Approval required</span>
            <strong>{waitingApprovalContext.operation}</strong>
          </div>
          <p className="workflow-section__approval-reason">{waitingApprovalContext.reason}</p>
          <p className="panel__hint">{waitingApprovalContext.safety}</p>
          <p className="panel__hint">Rejecting is not an error; it records an honest skipped path and does not execute the operation. The package will remain byte-identical.</p>
          <div className="workflow-section__approval-actions">
            <button
              type="button"
              className="primary-button compact-button"
              disabled={busy}
              onClick={() => void runAction("approve")}
            >
              Approve &amp; execute
            </button>
            <button
              type="button"
              className="ghost-button compact-button danger"
              disabled={busy}
              onClick={() => void runAction("reject")}
            >
              Reject
            </button>
          </div>
        </aside>
      ) : null}
      </section>

      <section className="workflow-section workflow-section--comparison" aria-labelledby="workflow-comparison-header">
        <header className="workflow-section__header">
          <div>
            <span className="workflow-section__eyebrow">5 · Target Comparison</span>
            <h4 id="workflow-comparison-header" className="workflow-section__title">
              Pass / fail / unknown against design targets
            </h4>
          </div>
          <span className="workflow-section__safety">Not certification</span>
        </header>
        <p className="workflow-section__hint">
          Target comparison is a deterministic check against the imported (or solver-generated) computed metrics —
          not a safety verdict on the design itself. The live comparison view is rendered inside the
          <strong> Computed Metrics</strong> card in Section 2 and refreshes automatically after a successful
          structural solver run.
        </p>
        <article className="copilot-loop__demo-card workflow-section__anchor">
          <p className="panel__hint">
            Open the <strong>Computed Metrics</strong> card above to see the current pass / fail breakdown,
            or use <strong>Export packet</strong> in Section 6 to freeze the current comparison into a
            review artifact.
          </p>
        </article>
      </section>

      <section className="workflow-section workflow-section--review" aria-labelledby="workflow-review-header">
        <header className="workflow-section__header">
          <div>
            <span className="workflow-section__eyebrow">6 · Review &amp; Export</span>
            <h4 id="workflow-review-header" className="workflow-section__title">
              Engineering review packet, Copilot loop history, and comparison
            </h4>
          </div>
          <span className="workflow-section__safety">Review support only</span>
        </header>
        <p className="workflow-section__hint">
          Bundle the existing project evidence into a Markdown + JSON review packet, or inspect persisted Copilot
          loops. Packet generation does not certify the design or advance engineering claims.
        </p>
      <ReviewSupportPacketCard projectId={selectedId} refreshKey={computedMetricsRefreshKey} />
      {!selectedId ? <p className="empty-state">Select a project with a .aieng package to start a loop.</p> : null}
      {error ? <div className="inline-error">{error}</div> : null}
      {restoredFromHistory && loop ? (
        <p className="panel__hint">Restored a persisted loop. Start a new loop, reopen an older one from history, or compare two side-by-side.</p>
      ) : null}
      {selectedId ? (
        <div ref={loopHistoryRef} tabIndex={-1} className={highlightedReadinessSection === "loop_history" ? "readiness-highlight" : ""}>
          <CopilotLoopHistoryTable
            summaries={summaries}
            activeLoopId={loop?.loop_id ?? null}
            compareSelection={compareSelection}
            onReopen={(id) => void handleReopen(id)}
            onToggleCompare={toggleCompare}
            onCompareNow={openCompare}
            onClearCompare={clearCompare}
          />
        </div>
      ) : null}
      {compareOpen && compareLeft && compareRight ? (
        <div ref={reportCompareRef} tabIndex={-1} className={highlightedReadinessSection === "report_compare" ? "readiness-highlight" : ""}>
          <CopilotLoopComparePanel
            projectId={selectedId}
            left={compareLeft}
            right={compareRight}
            onClose={() => setCompareOpen(false)}
            onReopen={(id) => void handleReopen(id)}
          />
        </div>
      ) : null}
      </section>
      {waitingStep && waitingApprovalContext === null ? (
        <article className="approval-card">
          <strong>Approval required: {waitingStep.title}</strong>
          <p>{waitingStep.summary}</p>
          <p className="panel__hint">Rejecting is not an error; it records an honest skipped path and does not execute the operation. The package will remain byte-identical.</p>
          <div className="button-row">
            <button type="button" className="primary-button compact-button" disabled={busy} onClick={() => void runAction("approve")}>Approve & execute</button>
            <button type="button" className="ghost-button compact-button danger" disabled={busy} onClick={() => void runAction("reject")}>Reject</button>
          </div>
        </article>
      ) : null}
      {loopRejected && !waitingStep ? (
        <article className="approval-card approval-card--rejected">
          <strong>CAD edit was rejected</strong>
          <p>No mutation was applied. The remaining steps either operate on the unchanged baseline or are skipped. The loop report will record the rejection explicitly.</p>
        </article>
      ) : null}
      {loop ? (
        <>
          <div className="copilot-loop__meta">
            <span>Loop <code>{loop.loop_id}</code></span>
            <span className={statusClass(loop.status)}>{loop.status}</span>
            {nextStep ? <span>Next: {nextStep.title}</span> : <span>All steps have a terminal status.</span>}
          </div>
          <div className="copilot-stepper">
            {loop.steps.map((step) => <StepCard key={step.id} step={step} loop={loop} />)}
          </div>
        </>
      ) : selectedId ? (
        <p className="empty-state">No loop started yet. Start a loop to inspect evidence and proceed step-by-step.</p>
      ) : null}
    </section>
  );
}
