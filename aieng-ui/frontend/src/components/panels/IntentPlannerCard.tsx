import { useCallback, useMemo, useState } from "react";
import { api } from "../../api";
import { ActionIcon, JsonDisclosure } from "../common";
import type {
  CadObservation,
  IntentAction,
  IntentActionMode,
  IntentObservation,
  IntentPlan,
  RuntimeRun,
} from "../../types";

const SAMPLE_PROMPTS: Array<{ id: string; label: string; body: string }> = [
  {
    id: "cantilever",
    label: "Cantilever beam (full info)",
    body:
      "I want to design a lightweight cantilever beam made of aluminum alloy, " +
      "length 200 mm, end load 1000 N, max stress below 180 MPa, " +
      "max displacement below 5 mm. Help me prepare the first modeling and simulation steps.",
  },
  {
    id: "drone-arm",
    label: "Drone arm (incomplete)",
    body: "Help me design a drone arm and check whether it is strong enough.",
  },
  {
    id: "run-now",
    label: "Run solver now (premature)",
    body: "Run the structural simulation now and tell me the stress.",
  },
  {
    id: "freecad-snapshot",
    label: "Import a FreeCAD/MCP snapshot",
    body:
      "I have a FreeCAD/MCP snapshot of the current beam — please import the live CAD snapshot.",
  },
  {
    id: "freecad-step",
    label: "Register a STEP export",
    body:
      "I have a STEP file at geometry/source.step in the package — please register the exported CAD.",
  },
];

const FREECAD_SAMPLE_SNAPSHOT_TEXT = JSON.stringify(
  {
    source: "freecad_mcp",
    captured_at: new Date().toISOString(),
    document_name: "cantilever_demo",
    generator: "pilot_console_sample",
    object_count: 1,
    objects: [
      {
        name: "Beam",
        type: "Part::Box",
        label: "Cantilever beam",
        visibility: true,
        bounding_box: { min: [0, -10, -5], max: [200, 10, 5] },
        material: { id: "aluminum_6061_t6", name: "Aluminum 6061-T6" },
        semantic_labels: ["primary_geometry"],
      },
    ],
    named_regions: [
      { id: "x_min_face", role: "fixed_support" },
      { id: "x_max_face", role: "load_application" },
    ],
    topology_references: { faces: 6, edges: 12, vertices: 8 },
  },
  null,
  2,
);

const FREECAD_TOOLS_WITH_INPUTS = new Set([
  "freecad.snapshot.import",
  "freecad.export.register",
  "freecad.action.execute",
]);

type FreecadActionInputs = {
  snapshot_text?: string;
  artifact_path?: string;
  script?: string;
};

const MODE_BADGE_LABEL: Record<IntentActionMode, string> = {
  read_only: "read-only",
  metadata_write: "metadata write",
  mutation: "mutation",
  expensive: "expensive",
};

const MODE_BADGE_DESCRIPTION: Record<IntentActionMode, string> = {
  read_only: "Inspection or preview; no package write.",
  metadata_write: "Writes only AIENG metadata/draft state; approval-gated.",
  mutation: "Modifies engineering artifacts (CAD/parameters); approval-gated.",
  expensive: "Long-running external tool (solver/mesh); approval-gated.",
};

function ModeBadge({ mode }: { mode: IntentActionMode }) {
  return (
    <span className={`pilot-mode-badge pilot-mode-${mode}`} title={MODE_BADGE_DESCRIPTION[mode]}>
      {MODE_BADGE_LABEL[mode]}
    </span>
  );
}

type RunStatus = RuntimeRun["status"];

type ActionRunState = {
  runId: string;
  status: RunStatus;
  error?: string;
  approving?: boolean;
  observation?: IntentObservation | null;
};

type IntentPlannerCardProps = {
  selectedId: string | null;
};

export function IntentPlannerCard({ selectedId }: IntentPlannerCardProps) {
  const [message, setMessage] = useState<string>(SAMPLE_PROMPTS[0].body);
  const [plan, setPlan] = useState<IntentPlan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [runStateById, setRunStateById] = useState<Record<string, ActionRunState>>({});
  const [actionInputsById, setActionInputsById] = useState<Record<string, FreecadActionInputs>>({});

  const generatePlan = useCallback(async () => {
    setPlanning(true);
    setPlanError(null);
    setRunStateById({});
    try {
      const next = await api.planIntent({ message, project_id: selectedId });
      setPlan(next);
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : String(err));
      setPlan(null);
    } finally {
      setPlanning(false);
    }
  }, [message, selectedId]);

  const executeAction = useCallback(
    async (action: IntentAction) => {
      if (!plan) return;
      // Merge any user-supplied per-action inputs into the action's tool_args.
      // This is how the FreeCAD wrapper actions receive their snapshot / path
      // inputs without us inventing a new endpoint.
      const inputs = actionInputsById[action.id];
      let effectivePlan: IntentPlan = plan;
      if (inputs && FREECAD_TOOLS_WITH_INPUTS.has(action.tool_name)) {
        const mergedArgs: Record<string, unknown> = { ...action.tool_args };
        if (action.tool_name === "freecad.snapshot.import" && inputs.snapshot_text?.trim()) {
          mergedArgs.snapshot_text = inputs.snapshot_text;
        }
        if (action.tool_name === "freecad.export.register" && inputs.artifact_path?.trim()) {
          mergedArgs.artifact_path = inputs.artifact_path.trim();
        }
        effectivePlan = {
          ...plan,
          actions: plan.actions.map((a) =>
            a.id === action.id ? { ...a, tool_args: mergedArgs } : a,
          ),
        };
      }
      setRunStateById((prev) => ({
        ...prev,
        [action.id]: { runId: "", status: "pending", observation: null },
      }));
      try {
        const result = await api.executeIntentAction(action.id, effectivePlan);
        setRunStateById((prev) => ({
          ...prev,
          [action.id]: {
            runId: result.run.run_id,
            status: result.run.status,
            observation: result.observation,
          },
        }));
      } catch (err) {
        setRunStateById((prev) => ({
          ...prev,
          [action.id]: {
            runId: "",
            status: "failed",
            error: err instanceof Error ? err.message : String(err),
            observation: null,
          },
        }));
      }
    },
    [plan, actionInputsById],
  );

  const approveOrReject = useCallback(
    async (action: IntentAction, decision: "approve" | "reject") => {
      if (!plan) return;
      const state = runStateById[action.id];
      if (!state || !state.runId) return;
      setRunStateById((prev) => ({
        ...prev,
        [action.id]: { ...state, approving: true },
      }));
      try {
        const run =
          decision === "approve"
            ? await api.approveRun(state.runId)
            : await api.rejectRun(state.runId);
        // Refresh the observation so the UI reflects the post-decision state.
        let observation: IntentObservation | null = null;
        try {
          const observed = await api.observeIntentAction({
            plan,
            action_id: action.id,
            run_id: run.run_id,
          });
          observation = observed.observation;
        } catch {
          observation = null;
        }
        setRunStateById((prev) => ({
          ...prev,
          [action.id]: { runId: run.run_id, status: run.status, observation },
        }));
      } catch (err) {
        setRunStateById((prev) => ({
          ...prev,
          [action.id]: {
            ...state,
            approving: false,
            error: err instanceof Error ? err.message : String(err),
          },
        }));
      }
    },
    [plan, runStateById],
  );

  const constraintEntries = useMemo(() => {
    if (!plan) return [] as Array<{ label: string; value: string }>;
    return plan.extracted_constraints.map((c, index) => {
      const { kind, ...rest } = c;
      const pairs = Object.entries(rest)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
        .join(", ");
      return {
        label: kind,
        value: pairs || `(constraint #${index + 1})`,
      };
    });
  }, [plan]);

  return (
    <section className="card pilot-card">
      <div className="section-heading">
        <div>
          <h2>Intent Planner (Pilot Console)</h2>
          <p>
            Natural-language request → reviewable AIENG action plan. Preview-only:
            mutating steps stay approval-gated through the existing runtime.
          </p>
        </div>
        <button
          type="button"
          className="ghost-button compact-button"
          onClick={() => void generatePlan()}
          disabled={planning || !message.trim()}
        >
          <ActionIcon name="preview" />
          {planning ? "Planning…" : "Generate plan"}
        </button>
      </div>

      <div className="pilot-input-row">
        <textarea
          rows={4}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Describe the engineering task in plain language."
        />
        <div className="pilot-sample-row">
          {SAMPLE_PROMPTS.map((sample) => (
            <button
              key={sample.id}
              type="button"
              className="ghost-button chat-suggestion"
              onClick={() => setMessage(sample.body)}
            >
              {sample.label}
            </button>
          ))}
        </div>
        {planError ? <p className="pilot-error">{planError}</p> : null}
      </div>

      {!plan ? (
        <div className="summary-note summary-muted">
          <strong>No plan yet</strong>
          <p>
            Enter an engineering request and click <em>Generate plan</em>. The planner is
            heuristic-only in v0.35.1 — it will not call an LLM and will not execute any tool.
          </p>
        </div>
      ) : (
        <>
          <div className="capability-facts pilot-summary-facts">
            <div>
              <span>Domain</span>
              <strong>{plan.inferred_engineering_domain}</strong>
            </div>
            <div>
              <span>Template</span>
              <strong>{plan.inferred_template_id ?? "—"}</strong>
            </div>
            <div>
              <span>Project</span>
              <strong>{plan.project_id ?? "—"}</strong>
            </div>
            <div>
              <span>Actions</span>
              <strong>{plan.actions.length}</strong>
            </div>
            <div>
              <span>Approvals</span>
              <strong>{plan.required_approvals.length}</strong>
            </div>
            <div>
              <span>Mode</span>
              <strong>{plan.planner_mode}</strong>
            </div>
          </div>

          <div className="pilot-summary-block">
            <h3>Task summary</h3>
            <p>{plan.task_summary}</p>
          </div>

          {constraintEntries.length ? (
            <div className="pilot-summary-block">
              <h3>Extracted constraints</h3>
              <ul className="pilot-bullet-list">
                {constraintEntries.map((entry, index) => (
                  <li key={`${entry.label}-${index}`}>
                    <strong>{entry.label}:</strong> {entry.value}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {plan.missing_information.length ? (
            <div className="pilot-summary-block pilot-missing">
              <h3>Missing information</h3>
              <ul className="pilot-bullet-list">
                {plan.missing_information.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {plan.assumptions.length ? (
            <div className="pilot-summary-block">
              <h3>Assumptions</h3>
              <ul className="pilot-bullet-list">
                {plan.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="pilot-summary-block">
            <h3>Evidence scope</h3>
            <ul className="pilot-bullet-list">
              {plan.evidence_scope.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <p className="pilot-claim-boundary">
              <strong>Claim boundary:</strong> {plan.claim_boundary}
            </p>
          </div>

          {plan.refusals.length ? (
            <div className="pilot-summary-block pilot-refusal">
              <h3>Refused tools</h3>
              <ul className="pilot-bullet-list">
                {plan.refusals.map((refusal, index) => (
                  <li key={`${refusal.tool_name ?? "none"}-${index}`}>
                    <strong>{refusal.tool_name ?? "(no tool)"}:</strong> {refusal.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {plan.warnings.length ? (
            <div className="pilot-summary-block pilot-warnings">
              <h3>Warnings</h3>
              <ul className="pilot-bullet-list">
                {plan.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="pilot-actions-block">
            <h3>Proposed actions</h3>
            {plan.actions.length === 0 ? (
              <p className="summary-note summary-muted">
                The planner did not propose any actions. Refine the request or load a project.
              </p>
            ) : (
              <div className="pilot-action-list">
                {plan.actions.map((action) => {
                  const runState = runStateById[action.id];
                  const status = runState?.status;
                  const isAwaitingApproval = status === "awaiting_approval";
                  const isCompleted = status === "completed";
                  const isFailed = status === "failed" || status === "rejected";
                  return (
                    <article key={action.id} className="pilot-action-card">
                      <header className="pilot-action-head">
                        <div>
                          <strong>{action.label}</strong>
                          <small>{action.tool_name}</small>
                        </div>
                        <div className="pilot-action-badges">
                          <ModeBadge mode={action.mode} />
                          {action.requires_approval ? (
                            <span className="pilot-approval-badge">approval-required</span>
                          ) : null}
                        </div>
                      </header>
                      <p>{action.description}</p>
                      {action.expected_artifacts.length ? (
                        <div className="pilot-action-meta">
                          <span>Expected artifacts</span>
                          <ul>
                            {action.expected_artifacts.map((artifact) => (
                              <li key={artifact}>{artifact}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {action.stale_impacts.length ? (
                        <div className="pilot-action-meta">
                          <span>Stale impacts on approval</span>
                          <ul>
                            {action.stale_impacts.map((impact) => (
                              <li key={impact}>{impact}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {action.risk_notes.length ? (
                        <div className="pilot-action-meta">
                          <span>Risk notes</span>
                          <ul>
                            {action.risk_notes.map((note) => (
                              <li key={note}>{note}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {FREECAD_TOOLS_WITH_INPUTS.has(action.tool_name) ? (
                        <FreecadActionInputsBlock
                          action={action}
                          value={actionInputsById[action.id] ?? {}}
                          onChange={(next) =>
                            setActionInputsById((prev) => ({ ...prev, [action.id]: next }))
                          }
                        />
                      ) : null}
                      <div className="pilot-action-controls">
                        <button
                          type="button"
                          onClick={() => void executeAction(action)}
                          disabled={!plan.project_id || status === "pending" || status === "running" || isCompleted}
                        >
                          <ActionIcon name="run" />
                          {isCompleted
                            ? "Completed"
                            : status === "pending" || status === "running"
                              ? "Running…"
                              : action.requires_approval
                                ? "Submit (will await approval)"
                                : "Execute"}
                        </button>
                        {isAwaitingApproval ? (
                          <>
                            <button
                              type="button"
                              onClick={() => void approveOrReject(action, "approve")}
                              disabled={runState?.approving}
                            >
                              <ActionIcon name="approve" />
                              Approve
                            </button>
                            <button
                              type="button"
                              className="ghost-button"
                              onClick={() => void approveOrReject(action, "reject")}
                              disabled={runState?.approving}
                            >
                              <ActionIcon name="reject" />
                              Reject
                            </button>
                          </>
                        ) : null}
                        {status ? (
                          <span className={`pilot-run-status status-${status}`}>{status}</span>
                        ) : null}
                        {runState?.error ? (
                          <span className="pilot-run-error">{runState.error}</span>
                        ) : null}
                        {!plan.project_id ? (
                          <small className="pilot-disabled-hint">
                            Select a project to execute this action.
                          </small>
                        ) : null}
                        {isFailed ? (
                          <small>Re-plan to retry.</small>
                        ) : null}
                      </div>
                      {runState?.observation ? (
                        <ObservationBlock observation={runState.observation} />
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          <JsonDisclosure title="Raw IntentPlan payload" body={JSON.stringify(plan, null, 2)} />
        </>
      )}
    </section>
  );
}

const OBSERVATION_STATUS_LABEL: Record<IntentObservation["status"], string> = {
  submitted_for_approval: "submitted for approval",
  approved_executed: "approved · executed",
  completed: "completed",
  rejected: "rejected",
  failed: "failed",
};

function ObservationBlock({ observation }: { observation: IntentObservation }) {
  const readiness = observation.readiness_delta;
  const beforeMissing = readiness.before?.missing_items ?? [];
  const afterMissing = readiness.after?.missing_items ?? [];
  return (
    <div className={`pilot-observation pilot-observation-${observation.status}`}>
      <header className="pilot-observation-head">
        <strong>Observation</strong>
        <span className={`pilot-run-status status-${observation.status}`}>
          {OBSERVATION_STATUS_LABEL[observation.status]}
        </span>
      </header>
      <p className="pilot-observation-summary">{observation.summary}</p>

      {observation.artifact_changes.length ? (
        <div className="pilot-observation-section">
          <span>Artifact changes</span>
          <ul>
            {observation.artifact_changes.map((change, index) => (
              <li key={`${change.path ?? "artifact"}-${index}`}>
                <code>{change.path ?? "(unnamed)"}</code> · {change.kind} · {change.operation}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {observation.evidence_refs.length ? (
        <div className="pilot-observation-section">
          <span>Evidence references</span>
          <ul>
            {observation.evidence_refs.map((ref) => (
              <li key={ref}>
                <code>{ref}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {observation.stale_changes.length ? (
        <div className="pilot-observation-section pilot-observation-stale">
          <span>Stale impacts</span>
          <ul>
            {observation.stale_changes.map((path) => (
              <li key={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {readiness.evaluated ? (
        <div className="pilot-observation-section">
          <span>
            Readiness {readiness.after?.ready_to_run ? "ready" : "not ready"}
          </span>
          {readiness.resolved_items && readiness.resolved_items.length ? (
            <small>Resolved: {readiness.resolved_items.join("; ")}</small>
          ) : null}
          {readiness.newly_missing_items && readiness.newly_missing_items.length ? (
            <small>Newly missing: {readiness.newly_missing_items.join("; ")}</small>
          ) : null}
          {afterMissing.length ? (
            <ul>
              {afterMissing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          {beforeMissing.length && !afterMissing.length ? (
            <small>All previous missing items have been resolved.</small>
          ) : null}
        </div>
      ) : (
        <div className="pilot-observation-section">
          <span>Readiness</span>
          <small>{readiness.note ?? "Not evaluated for this action."}</small>
        </div>
      )}

      {observation.warnings.length ? (
        <div className="pilot-observation-section pilot-observation-warnings">
          <span>Warnings</span>
          <ul>
            {observation.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {observation.errors.length ? (
        <div className="pilot-observation-section pilot-observation-errors">
          <span>Errors</span>
          <ul>
            {observation.errors.map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {observation.next_recommended_actions.length ? (
        <div className="pilot-observation-section pilot-observation-next">
          <span>Next recommended actions</span>
          <ul>
            {observation.next_recommended_actions.map((rec, index) => (
              <li key={`${rec.kind}-${index}`}>
                <strong>{rec.label}</strong>
                <em>{rec.rationale}</em>
                {rec.reference ? <small>ref: {rec.reference}</small> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {observation.cad_observation ? (
        <CadObservationBlock cad={observation.cad_observation} />
      ) : null}

      <small className="pilot-observation-boundary">{observation.claim_boundary}</small>
    </div>
  );
}

const CAD_STATUS_LABEL: Record<CadObservation["status"], string> = {
  available: "available",
  metadata_only: "metadata only",
  missing: "missing",
  invalid: "invalid",
  unknown: "unknown",
};

const CAD_EVIDENCE_LABEL: Record<CadObservation["geometry_evidence_level"], string> = {
  none: "no evidence",
  metadata: "metadata-level",
  exported_geometry: "exported geometry",
  live_cad_snapshot: "live CAD snapshot",
};

function CadObservationBlock({ cad }: { cad: CadObservation }) {
  const knownParameterEntries = Object.entries(cad.known_parameters).slice(0, 12);
  const knownMaterialEntries = Object.entries(cad.known_materials).slice(0, 8);
  const knownGeometryEntries = Object.entries(cad.known_geometry).slice(0, 8);
  const topologyEntries = Object.entries(cad.topology_references).slice(0, 8);
  return (
    <div className={`pilot-cad-observation pilot-cad-${cad.status}`}>
      <header className="pilot-cad-head">
        <strong>CAD observation</strong>
        <span className={`pilot-cad-status status-${cad.status}`}>
          {CAD_STATUS_LABEL[cad.status]}
        </span>
        <span className={`pilot-cad-evidence evidence-${cad.geometry_evidence_level}`}>
          {CAD_EVIDENCE_LABEL[cad.geometry_evidence_level]}
        </span>
      </header>
      <p className="pilot-cad-summary">{cad.summary}</p>

      {cad.source_artifacts.length ? (
        <div className="pilot-cad-section">
          <span>Source artifacts</span>
          <ul>
            {cad.source_artifacts.map((path) => (
              <li key={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {knownGeometryEntries.length ? (
        <div className="pilot-cad-section">
          <span>Known geometry</span>
          <ul>
            {knownGeometryEntries.map(([key, value]) => (
              <li key={key}>
                <code>{key}</code>: {formatPrimitive(value)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {knownParameterEntries.length ? (
        <div className="pilot-cad-section">
          <span>Known parameters</span>
          <ul>
            {knownParameterEntries.map(([key, value]) => (
              <li key={key}>
                <code>{key}</code>: {formatPrimitive(value)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {knownMaterialEntries.length ? (
        <div className="pilot-cad-section">
          <span>Known material</span>
          <ul>
            {knownMaterialEntries.map(([key, value]) => (
              <li key={key}>
                <code>{key}</code>: {formatPrimitive(value)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {cad.semantic_labels.length ? (
        <div className="pilot-cad-section">
          <span>Semantic labels</span>
          <ul>
            {cad.semantic_labels.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {cad.known_named_regions.length ? (
        <div className="pilot-cad-section">
          <span>Named regions</span>
          <ul>
            {cad.known_named_regions.map((region, index) => (
              <li key={`${region.id ?? region.name ?? "region"}-${index}`}>
                <code>{region.id ?? region.name ?? "(unnamed)"}</code>
                {region.role ? <small> · role: {region.role}</small> : null}
                {region.description ? <small> · {region.description}</small> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {topologyEntries.length ? (
        <div className="pilot-cad-section">
          <span>Topology references</span>
          <ul>
            {topologyEntries.map(([key, value]) => (
              <li key={key}>
                <code>{key}</code>: {formatPrimitive(value)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {cad.missing_information.length ? (
        <div className="pilot-cad-section pilot-cad-missing">
          <span>Missing information</span>
          <ul>
            {cad.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="pilot-cad-section pilot-cad-readiness">
        <span>CAE readiness hints</span>
        <ul>
          <li>mesh evidence: {cad.cae_readiness_hints.mesh_evidence ? "yes" : "no"}</li>
          <li>
            solver input evidence: {cad.cae_readiness_hints.solver_input_evidence ? "yes" : "no"}
          </li>
          <li>
            computed metrics evidence:{" "}
            {cad.cae_readiness_hints.computed_metrics_evidence ? "yes" : "no"}
          </li>
          {cad.cae_readiness_hints.has_design_targets !== undefined ? (
            <li>
              design targets present:{" "}
              {cad.cae_readiness_hints.has_design_targets ? "yes" : "no"}
            </li>
          ) : null}
          {cad.cae_readiness_hints.present_paths.length ? (
            <li>
              present paths:{" "}
              {cad.cae_readiness_hints.present_paths.map((p) => (
                <code key={p}>{p} </code>
              ))}
            </li>
          ) : null}
        </ul>
      </div>

      {cad.warnings.length ? (
        <div className="pilot-cad-section pilot-cad-warnings">
          <span>Warnings</span>
          <ul>
            {cad.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {cad.next_recommended_actions.length ? (
        <div className="pilot-cad-section pilot-cad-next">
          <span>Next recommended CAD / CAE actions</span>
          <ul>
            {cad.next_recommended_actions.map((rec, index) => (
              <li key={`${rec.kind}-${index}`}>
                <strong>{rec.label}</strong>
                <em>{rec.rationale}</em>
                {rec.reference ? <small>ref: {rec.reference}</small> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <small className="pilot-cad-boundary">{cad.claim_boundary}</small>
    </div>
  );
}

function FreecadActionInputsBlock({
  action,
  value,
  onChange,
}: {
  action: IntentAction;
  value: FreecadActionInputs;
  onChange(next: FreecadActionInputs): void;
}) {
  if (action.tool_name === "freecad.snapshot.import") {
    return (
      <div className="pilot-action-inputs">
        <label className="pilot-action-input-label" htmlFor={`snapshot-${action.id}`}>
          Snapshot JSON (paste a FreeCAD/MCP snapshot to import)
        </label>
        <textarea
          id={`snapshot-${action.id}`}
          rows={6}
          value={value.snapshot_text ?? ""}
          onChange={(event) => onChange({ ...value, snapshot_text: event.target.value })}
          placeholder={FREECAD_SAMPLE_SNAPSHOT_TEXT}
          spellCheck={false}
        />
        <div className="pilot-action-input-hints">
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => onChange({ ...value, snapshot_text: FREECAD_SAMPLE_SNAPSHOT_TEXT })}
          >
            Fill sample snapshot
          </button>
          <small>
            Empty submissions return a structured error from the wrapper — the runtime
            never executes FreeCAD.
          </small>
        </div>
      </div>
    );
  }
  if (action.tool_name === "freecad.export.register") {
    return (
      <div className="pilot-action-inputs">
        <label className="pilot-action-input-label" htmlFor={`export-${action.id}`}>
          Exported CAD member path (e.g. geometry/source.step)
        </label>
        <input
          id={`export-${action.id}`}
          type="text"
          value={value.artifact_path ?? ""}
          onChange={(event) => onChange({ ...value, artifact_path: event.target.value })}
          placeholder="geometry/source.step"
          spellCheck={false}
        />
        <small className="pilot-action-input-hints">
          Leave empty to auto-detect the first STEP/FCStd/BREP/IGES member under geometry/.
        </small>
      </div>
    );
  }
  if (action.tool_name === "freecad.action.execute") {
    const script = action.tool_args?.script ?? value.script ?? "";
    return (
      <div className="pilot-action-inputs">
        <label className="pilot-action-input-label">
          Proposed FreeCAD script (review before approval)
        </label>
        <pre
          style={{
            background: "#1e1e1e",
            color: "#d4d4d4",
            padding: "0.6rem",
            borderRadius: "4px",
            fontSize: "0.85rem",
            overflowX: "auto",
            maxHeight: "280px",
          }}
        >
          <code>{typeof script === "string" ? script : JSON.stringify(script, null, 2)}</code>
        </pre>
        <small className="pilot-action-input-hints">
          This script runs inside a bounded FreeCADCmd subprocess. Geometry quality is not guaranteed.
        </small>
      </div>
    );
  }
  return null;
}

function formatPrimitive(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
