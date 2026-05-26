import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type {
  EngineeringTemplateDetail,
  EngineeringTemplateAdoptTargetsResponse,
  EngineeringTemplateCadFixtureResponse,
  EngineeringTemplateParameter,
  EngineeringTemplatePreviewResponse,
  EngineeringTemplateSaveDraftResponse,
  EngineeringTemplateSummary,
  EngineeringTemplateTargetSuggestion,
} from "../../types";

type ListState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; templates: EngineeringTemplateSummary[] }
  | { status: "error"; message: string };

type DetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; detail: EngineeringTemplateDetail }
  | { status: "error"; message: string };

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: EngineeringTemplatePreviewResponse }
  | { status: "error"; message: string };

type SaveState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: EngineeringTemplateSaveDraftResponse }
  | { status: "error"; message: string };

type AdoptState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: EngineeringTemplateAdoptTargetsResponse }
  | { status: "error"; message: string };

type CadFixtureState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: EngineeringTemplateCadFixtureResponse }
  | { status: "error"; message: string };

type Props = {
  projectId: string | null;
  onDraftSaved?: () => void;
  onTargetsAdopted?: () => void;
  onCadFixtureGenerated?: () => void;
};

function defaultParamsFor(detail: EngineeringTemplateDetail): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of detail.parameters) {
    if (p.default !== null && p.default !== undefined) out[p.id] = p.default;
  }
  return out;
}

function coerceParamForSubmit(p: EngineeringTemplateParameter, raw: string | boolean): unknown {
  if (p.kind === "number") {
    if (raw === "" || raw === null) return null;
    const n = Number(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (p.kind === "boolean") return Boolean(raw);
  return raw;
}

function renderField(
  p: EngineeringTemplateParameter,
  value: unknown,
  onChange: (next: unknown) => void,
): JSX.Element {
  const labelText = (
    <>
      <strong>{p.label}</strong>
      {p.unit ? <span className="panel__hint"> ({p.unit})</span> : null}
      {!p.required ? <span className="panel__hint"> (optional)</span> : null}
    </>
  );
  if (p.kind === "select") {
    return (
      <label className="field-stack" key={p.id}>
        <span>{labelText}</span>
        <select value={String(value ?? "")} onChange={(e) => onChange(coerceParamForSubmit(p, e.target.value))}>
          {(p.choices ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="panel__hint">{p.description}</span>
      </label>
    );
  }
  if (p.kind === "boolean") {
    return (
      <label className="field-stack" key={p.id}>
        <span>
          <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(coerceParamForSubmit(p, e.target.checked))} />
          {" "}{labelText}
        </span>
        <span className="panel__hint">{p.description}</span>
      </label>
    );
  }
  // number / string
  return (
    <label className="field-stack" key={p.id}>
      <span>{labelText}</span>
      <input
        type={p.kind === "number" ? "number" : "text"}
        value={value === undefined || value === null ? "" : String(value)}
        min={p.min ?? undefined}
        max={p.max ?? undefined}
        step="any"
        onChange={(e) => onChange(coerceParamForSubmit(p, e.target.value))}
      />
      <span className="panel__hint">{p.description}</span>
    </label>
  );
}

export function EngineeringTemplateAuthoringCard({ projectId, onDraftSaved, onTargetsAdopted, onCadFixtureGenerated }: Props) {
  const [listState, setListState] = useState<ListState>({ status: "idle" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailState, setDetailState] = useState<DetailState>({ status: "idle" });
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [previewState, setPreviewState] = useState<PreviewState>({ status: "idle" });
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  const [adoptState, setAdoptState] = useState<AdoptState>({ status: "idle" });
  const [cadFixtureState, setCadFixtureState] = useState<CadFixtureState>({ status: "idle" });

  useEffect(() => {
    let cancelled = false;
    setListState({ status: "loading" });
    api
      .listEngineeringTemplates()
      .then((res) => {
        if (cancelled) return;
        setListState({ status: "loaded", templates: res.templates });
        if (!selectedId && res.templates.length) setSelectedId(res.templates[0].id);
      })
      .catch((err) => {
        if (cancelled) return;
        setListState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setDetailState({ status: "loading" });
    setPreviewState({ status: "idle" });
    setSaveState({ status: "idle" });
    setAdoptState({ status: "idle" });
    setCadFixtureState({ status: "idle" });
    api
      .getEngineeringTemplate(selectedId)
      .then((detail) => {
        if (cancelled) return;
        setDetailState({ status: "loaded", detail });
        setParams(defaultParamsFor(detail));
      })
      .catch((err) => {
        if (cancelled) return;
        setDetailState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const detail = detailState.status === "loaded" ? detailState.detail : null;

  const runPreview = useCallback(async () => {
    if (!projectId || !detail) return;
    setPreviewState({ status: "loading" });
    try {
      const response = await api.previewEngineeringTemplate(projectId, detail.id, params);
      setPreviewState({ status: "loaded", response });
    } catch (err) {
      setPreviewState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [detail, params, projectId]);

  const runSave = useCallback(async () => {
    if (!projectId || !detail) return;
    setSaveState({ status: "loading" });
    try {
      const response = await api.saveEngineeringTemplateDraft(projectId, detail.id, params);
      setSaveState({ status: "loaded", response });
      if (response.ok && onDraftSaved) onDraftSaved();
    } catch (err) {
      setSaveState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [detail, params, projectId, onDraftSaved]);

  const runAdoptTargets = useCallback(async () => {
    if (!projectId || !detail) return;
    setAdoptState({ status: "loading" });
    try {
      const currentSuggestions =
        previewState.status === "loaded" && previewState.response.ok
          ? previewState.response.design_target_suggestions
          : undefined;
      const response = await api.adoptEngineeringTemplateTargets(projectId, detail.id, currentSuggestions);
      setAdoptState({ status: "loaded", response });
      if (response.ok && response.adopted_count > 0) onTargetsAdopted?.();
    } catch (err) {
      setAdoptState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [detail, onTargetsAdopted, previewState, projectId]);

  const runGenerateCadFixture = useCallback(async () => {
    if (!projectId || !detail) return;
    setCadFixtureState({ status: "loading" });
    try {
      const response = await api.generateEngineeringTemplateCadFixture(projectId, detail.id, params);
      setCadFixtureState({ status: "loaded", response });
      if (response.ok) onCadFixtureGenerated?.();
    } catch (err) {
      setCadFixtureState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [detail, onCadFixtureGenerated, params, projectId]);

  const errors = previewState.status === "loaded" ? previewState.response.errors : [];
  const warnings = previewState.status === "loaded" ? previewState.response.warnings : [];
  const previewOk = previewState.status === "loaded" && previewState.response.ok;
  const suggestions: EngineeringTemplateTargetSuggestion[] = useMemo(() => {
    if (previewState.status !== "loaded") return [];
    return previewState.response.design_target_suggestions ?? [];
  }, [previewState]);

  return (
    <article className="copilot-loop__demo-card engineering-template-card">
      <div className="copilot-loop__demo-health">
        <div className="copilot-loop__demo-health-header">
          <div>
            <strong>Engineering Template Authoring</strong>
            <span className="panel__hint">
              Generate a controlled parametric CAD + FEA setup <em>draft</em> from a small template library.
              Template output is a draft — it does not certify design safety and does not run CAD/CAE tools.
            </span>
          </div>
        </div>

        {!projectId ? (
          <p className="panel__hint">Select a project to author and save a template draft.</p>
        ) : null}

        {listState.status === "loading" ? <p className="panel__hint">Loading templates…</p> : null}
        {listState.status === "error" ? <div className="inline-error">Could not list templates: {listState.message}</div> : null}

        {listState.status === "loaded" ? (
          <label className="field-stack">
            <span><strong>Template</strong></span>
            <select value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value || null)}>
              {listState.templates.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
            <span className="panel__hint">
              {listState.templates.find((t) => t.id === selectedId)?.description ?? ""}
            </span>
          </label>
        ) : null}

        {detailState.status === "loading" ? <p className="panel__hint">Loading template…</p> : null}
        {detailState.status === "error" ? <div className="inline-error">Could not load template: {detailState.message}</div> : null}

        {detail ? (
          <>
            <article className="copilot-loop__subcard">
              <strong>Parameters</strong>
              <p className="panel__hint">Defaults are pre-filled. Edit and click <em>Preview draft</em>; nothing is written until you click <em>Save draft</em>.</p>
              <div className="freecad-inspection-card__edit-grid">
                {detail.parameters.map((p) =>
                  renderField(p, params[p.id] ?? p.default, (next) => setParams((cur) => ({ ...cur, [p.id]: next }))),
                )}
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="primary-button compact-button"
                  onClick={() => void runPreview()}
                  disabled={!projectId || previewState.status === "loading"}
                >
                  {previewState.status === "loading" ? "Building preview…" : "Preview draft"}
                </button>
                <button
                  type="button"
                  className="ghost-button compact-button"
                  onClick={() => void runSave()}
                  disabled={!projectId || saveState.status === "loading" || !previewOk}
                  title={!previewOk ? "Run a successful preview first." : "Write draft artifacts into task/ in the package."}
                >
                  {saveState.status === "loading" ? "Saving draft…" : "Save draft"}
                </button>
              </div>
              <div className="copilot-loop__action-safety">
                <span className="safety-badge">draft only</span>
                <span className="safety-badge safety-badge--ok">no CAD execution</span>
                <span className="safety-badge safety-badge--ok">no mesh / solver execution</span>
                <span className="safety-badge safety-badge--ok">no claim advancement</span>
              </div>
              <p className="panel__hint freecad-inspection-card__claim-boundary">{detail.claim_boundary}</p>
            </article>

            {previewState.status === "error" ? (
              <div className="inline-error">Preview failed: {previewState.message}</div>
            ) : null}

            {previewState.status === "loaded" && !previewOk ? (
              <article className="copilot-loop__subcard">
                <strong>Validation errors</strong>
                <ul className="error-list">
                  {errors.map((e, idx) => (
                    <li key={idx}><code>{e.field ?? ""}</code>: {e.message}</li>
                  ))}
                </ul>
                {warnings.length ? (
                  <ul className="warning-list">
                    {warnings.map((w, idx) => <li key={idx}>{w}</li>)}
                  </ul>
                ) : null}
              </article>
            ) : null}

            {previewState.status === "loaded" && previewOk ? (
              <>
                {warnings.length ? (
                  <ul className="warning-list">
                    {warnings.map((w, idx) => <li key={idx}>{w}</li>)}
                  </ul>
                ) : null}

                <article className="copilot-loop__subcard">
                  <header className="freecad-inspection-card__result-header">
                    <strong>CAD script preview</strong>
                    <span className="badge badge-muted">inert text — not executed</span>
                  </header>
                  <p className="panel__hint">
                    Generated draft script. AIENG does not execute this text. Open it in a sandboxed CAD environment after explicit review.
                  </p>
                  <pre className="engineering-template-card__preview">{previewState.response.cad_script_preview}</pre>
                </article>

                <article className="copilot-loop__subcard">
                  <header className="freecad-inspection-card__result-header">
                    <strong>FEA setup draft</strong>
                    <span className="badge badge-muted">claim advancement: none</span>
                  </header>
                  <pre className="engineering-template-card__preview">
                    {JSON.stringify(previewState.response.fea_setup_draft, null, 2)}
                  </pre>
                </article>

                <article className="copilot-loop__subcard">
                  <header className="freecad-inspection-card__result-header">
                    <strong>Design target suggestions</strong>
                    <span className="badge badge-muted">suggestions only</span>
                  </header>
                  <p className="panel__hint">
                    Suggestions are <strong>not</strong> written into <code>task/design_targets.yaml</code>. To adopt one,
                    open the Design Targets card above and author it explicitly.
                  </p>
                  {suggestions.length ? (
                    <div className="table-scroll">
                      <table className="mini-table">
                        <thead>
                          <tr>
                            <th>Target id</th>
                            <th>Metric</th>
                            <th>Operator</th>
                            <th>Value</th>
                            <th>Unit</th>
                            <th>Rationale</th>
                          </tr>
                        </thead>
                        <tbody>
                          {suggestions.map((s) => (
                            <tr key={s.target_id}>
                              <td><code>{s.target_id}</code></td>
                              <td>{s.metric}</td>
                              <td>{s.operator}</td>
                              <td>{s.value}</td>
                              <td>{s.unit}</td>
                              <td><span className="panel__hint">{s.rationale}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="panel__hint">No suggestions for these parameters.</p>
                  )}
                </article>
              </>
            ) : null}

            {saveState.status === "error" ? <div className="inline-error">Save failed: {saveState.message}</div> : null}

            {adoptState.status === "error" ? <div className="inline-error">Adopt targets failed: {adoptState.message}</div> : null}
            {cadFixtureState.status === "error" ? <div className="inline-error">CAD fixture generation failed: {cadFixtureState.message}</div> : null}

            {saveState.status === "loaded" ? (
              <article className={`copilot-loop__subcard ${saveState.response.ok ? "" : "copilot-loop__subcard--empty"}`}>
                <strong>{saveState.response.ok ? "Draft saved" : "Save did not complete"}</strong>
                {saveState.response.ok ? (
                  <>
                    <p className="panel__hint">
                      Four draft artifacts written into the project package. The existing <code>task/design_targets.yaml</code> was not modified.
                    </p>
                    <ul className="artifact-list">
                      {(saveState.response.draft_paths ?? []).map((p) => <li key={p}><code>{p}</code></li>)}
                    </ul>
                    <div className="button-row">
                      <button
                        type="button"
                        className="primary-button compact-button"
                        onClick={() => void runAdoptTargets()}
                        disabled={adoptState.status === "loading"}
                      >
                        {adoptState.status === "loading" ? "Adopting targets…" : "Adopt suggested design targets"}
                      </button>
                    </div>
                    <p className="panel__hint">
                      Adoption is explicit metadata editing: it writes <code>task/design_targets.yaml</code> only.
                      It does not run CAD, mesh, solver, or advance claims.
                    </p>
                  </>
                ) : (
                  <ul className="error-list">
                    {saveState.response.errors.map((e, idx) => <li key={idx}>{e.message}</li>)}
                  </ul>
                )}
              </article>
            ) : null}

            {previewOk && suggestions.length ? (
              <article className="copilot-loop__subcard">
                <header className="freecad-inspection-card__result-header">
                  <strong>Template → Design Targets handoff</strong>
                  <span className="badge badge-warn">explicit write</span>
                </header>
                <p className="panel__hint">
                  Adopt the previewed target suggestions into <code>task/design_targets.yaml</code>.
                  This is user-driven metadata authoring, not validation or certification.
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="primary-button compact-button"
                    onClick={() => void runAdoptTargets()}
                    disabled={adoptState.status === "loading"}
                  >
                    {adoptState.status === "loading" ? "Adopting targets…" : "Adopt previewed design targets"}
                  </button>
                </div>
              </article>
            ) : null}

            {adoptState.status === "loaded" ? (
              <article className={`copilot-loop__subcard ${adoptState.response.ok ? "" : "copilot-loop__subcard--empty"}`}>
                <strong>{adoptState.response.ok ? "Design targets handoff complete" : "Design targets handoff did not complete"}</strong>
                {adoptState.response.ok ? (
                  <>
                    <dl className="compact-dl">
                      <dt>Artifact</dt>
                      <dd><code>{adoptState.response.artifact_path ?? "task/design_targets.yaml"}</code></dd>
                      <dt>Adopted</dt>
                      <dd>{adoptState.response.adopted_count}</dd>
                      <dt>Skipped duplicates</dt>
                      <dd>{adoptState.response.skipped_duplicate_ids.length}</dd>
                    </dl>
                    {adoptState.response.warnings.length ? (
                      <ul className="warning-list">
                        {adoptState.response.warnings.map((w, idx) => <li key={idx}>{w}</li>)}
                      </ul>
                    ) : null}
                    <p className="panel__hint freecad-inspection-card__claim-boundary">{adoptState.response.claim_boundary}</p>
                  </>
                ) : (
                  <ul className="error-list">
                    {adoptState.response.errors.map((e, idx) => <li key={idx}>{e.message}</li>)}
                  </ul>
                )}
              </article>
            ) : null}

            {previewOk ? (
              <article className="copilot-loop__subcard">
                <header className="freecad-inspection-card__result-header">
                  <strong>Template CAD fixture</strong>
                  <span className="badge badge-warn">approval-required write</span>
                </header>
                <p className="panel__hint">
                  Write deterministic geometry metadata to <code>geometry/template_cad_fixture.json</code>.
                  This is not a STEP/FCStd model and no CAD tool is executed. Downstream mesh, solver, metrics,
                  and summaries will be marked stale.
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="primary-button compact-button"
                    onClick={() => void runGenerateCadFixture()}
                    disabled={cadFixtureState.status === "loading"}
                    title="Approval-gated fixture write; no external CAD execution."
                  >
                    {cadFixtureState.status === "loading" ? "Writing CAD fixture…" : "Approve + write CAD fixture"}
                  </button>
                </div>
              </article>
            ) : null}

            {cadFixtureState.status === "loaded" ? (
              <article className={`copilot-loop__subcard ${cadFixtureState.response.ok ? "" : "copilot-loop__subcard--empty"}`}>
                <strong>{cadFixtureState.response.ok ? "CAD fixture written" : "CAD fixture was not written"}</strong>
                {cadFixtureState.response.ok ? (
                  <>
                    <dl className="compact-dl">
                      <dt>Artifact</dt>
                      <dd><code>{cadFixtureState.response.artifact_path ?? "geometry/template_cad_fixture.json"}</code></dd>
                      <dt>Stale marker</dt>
                      <dd><code>{cadFixtureState.response.revalidation_status_path ?? "state/revalidation_status.json"}</code></dd>
                      <dt>Stale artifacts</dt>
                      <dd>{cadFixtureState.response.stale_artifacts?.length ?? 0}</dd>
                      <dt>CAD execution</dt>
                      <dd>{cadFixtureState.response.cad_execution_performed ? "yes" : "no"}</dd>
                    </dl>
                    {cadFixtureState.response.warnings.length ? (
                      <ul className="warning-list">
                        {cadFixtureState.response.warnings.map((w, idx) => <li key={idx}>{w}</li>)}
                      </ul>
                    ) : null}
                    <p className="panel__hint freecad-inspection-card__claim-boundary">{cadFixtureState.response.claim_boundary}</p>
                  </>
                ) : (
                  <ul className="error-list">
                    {cadFixtureState.response.errors.map((e, idx) => <li key={idx}>{e.message}</li>)}
                  </ul>
                )}
              </article>
            ) : null}
          </>
        ) : null}
      </div>
    </article>
  );
}
