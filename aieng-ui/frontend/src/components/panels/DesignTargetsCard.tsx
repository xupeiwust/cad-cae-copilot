import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { DesignTarget, DesignTargetsResponse } from "../../types";

const EMPTY_TARGET: DesignTarget = {
  target_id: "",
  label: "",
  metric: "",
  operator: ">=",
  value: 0,
  unit: null,
  scope: null,
  load_case_id: null,
  priority: "required",
  rationale: null,
};

const SUPPORTED_OPERATORS = [
  { value: "<=", label: "≤" },
  { value: ">=", label: "≥" },
  { value: "<", label: "<" },
  { value: ">", label: ">" },
  { value: "==", label: "=" },
  { value: "within_range", label: "within range" },
  { value: "preserve", label: "preserve" },
  { value: "priority", label: "priority" },
  { value: "reduce_by_at_least", label: "reduce by at least" },
  { value: "increase_by_at_least", label: "increase by at least" },
  { value: "reduce_by_percent", label: "reduce by %" },
  { value: "increase_by_percent", label: "increase by %" },
];

const PRIORITIES = [
  { value: "required", label: "Required" },
  { value: "preferred", label: "Preferred" },
  { value: "informational", label: "Informational" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "critical", label: "Critical" },
];

type DesignTargetsState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: DesignTargetsResponse }
  | { status: "error"; message: string };

type EditMode =
  | { mode: "none" }
  | { mode: "add"; draft: DesignTarget }
  | { mode: "edit"; index: number; draft: DesignTarget }
  | { mode: "import"; text: string };

type DesignTargetsCardProps = {
  projectId: string | null;
  onSaved?: () => void;
  highlighted?: boolean;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  showHealthRerunPrompt?: boolean;
  onRunHealthCheck?: () => void;
  /** Increment to trigger a data refresh without re-mounting. */
  refreshKey?: number | string;
};

export function DesignTargetsCard({
  projectId,
  onSaved,
  highlighted = false,
  expanded = true,
  onExpandedChange,
  showHealthRerunPrompt = false,
  onRunHealthCheck,
  refreshKey,
}: DesignTargetsCardProps) {
  const [state, setState] = useState<DesignTargetsState>({ status: "idle" });
  const [edit, setEdit] = useState<EditMode>({ mode: "none" });
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setState({ status: "loading" });
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const response = await api.getDesignTargets(projectId);
      setState({ status: "loaded", response });
      setLastRefreshed(new Date().toLocaleString());
    } catch (err) {
      setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      setLastRefreshed(new Date().toLocaleString());
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const targets = useMemo(() => {
    if (state.status === "loaded") return state.response.targets;
    return [];
  }, [state]);

  const handleSave = useCallback(async () => {
    if (!projectId) return;
    setSaveError(null);
    setSaveSuccess(false);

    let payload: DesignTarget[];
    if (edit.mode === "import") {
      try {
        const parsed = JSON.parse(edit.text);
        if (Array.isArray(parsed)) {
          payload = parsed;
        } else if (parsed && typeof parsed === "object" && Array.isArray(parsed.targets)) {
          payload = parsed.targets;
        } else {
          setSaveError("Import JSON must be an array of targets or an object with a 'targets' array.");
          return;
        }
      } catch {
        setSaveError("Invalid JSON.");
        return;
      }
    } else if (edit.mode === "add" || edit.mode === "edit") {
      const draft = edit.draft;
      if (!draft.target_id.trim()) {
        setSaveError("Target ID is required.");
        return;
      }
      if (!draft.label.trim()) {
        setSaveError("Label is required.");
        return;
      }
      if (!draft.metric.trim()) {
        setSaveError("Metric is required.");
        return;
      }
      if (typeof draft.value !== "number" || isNaN(draft.value)) {
        setSaveError("Value must be a number.");
        return;
      }
      if (draft.operator === "within_range") {
        if (typeof draft.threshold_min !== "number" || isNaN(draft.threshold_min)) {
          setSaveError("Range minimum must be a number.");
          return;
        }
        if (typeof draft.threshold_max !== "number" || isNaN(draft.threshold_max)) {
          setSaveError("Range maximum must be a number.");
          return;
        }
        if (draft.threshold_min > draft.threshold_max) {
          setSaveError("Range minimum must be less than or equal to range maximum.");
          return;
        }
      }
      const next = [...targets];
      if (edit.mode === "add") {
        if (next.some((t) => t.target_id === draft.target_id)) {
          setSaveError(`A target with ID "${draft.target_id}" already exists.`);
          return;
        }
        next.push(draft);
      } else {
        next[edit.index] = draft;
      }
      payload = next;
    } else {
      return;
    }

    try {
      await api.saveDesignTargets(projectId, payload);
      setEdit({ mode: "none" });
      setSaveSuccess(true);
      await load();
      if (onSaved) onSaved();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSaveError(msg);
    }
  }, [edit, projectId, targets, load, onSaved]);

  const handleDelete = useCallback(
    async (index: number) => {
      if (!projectId) return;
      const next = targets.filter((_, i) => i !== index);
      try {
        await api.saveDesignTargets(projectId, next);
        setSaveSuccess(true);
        await load();
        if (onSaved) onSaved();
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : String(err));
      }
    },
    [projectId, targets, load, onSaved],
  );

  if (!projectId) {
    return (
      <article className="copilot-loop__demo-card">
        <div className="copilot-loop__demo-health">
          <strong>Design Targets</strong>
          <p className="panel__hint">Select a project to view or edit design targets.</p>
        </div>
      </article>
    );
  }

  if (state.status === "loading") {
    return (
      <article className="copilot-loop__demo-card">
        <div className="copilot-loop__demo-health">
          <strong>Design Targets</strong>
          <p className="panel__hint">Loading…</p>
        </div>
      </article>
    );
  }

  if (state.status === "error") {
    return (
      <article className="copilot-loop__demo-card">
        <div className="copilot-loop__demo-health">
          <strong>Design Targets</strong>
          <div className="inline-error">{(state as { message: string }).message}</div>
        </div>
      </article>
    );
  }

  const response = state.status === "loaded" ? state.response : null;
  const hasPackage = response?.artifact_path !== undefined;
  const noTargets = targets.length === 0;

  return (
    <article className={`copilot-loop__demo-card design-targets-card ${highlighted ? "readiness-highlight" : ""} ${!expanded ? "design-targets-card--collapsed" : ""}`}>
      <div className="copilot-loop__demo-health">
        <div className="copilot-loop__demo-health-header">
          <div>
            <strong>Design Targets</strong>
            <span className="panel__hint">
              {noTargets
                ? "No design targets found. Add targets to enable comparison."
                : `${targets.length} target(s) defined.`}
            </span>
          </div>
          {onExpandedChange ? (
            <button type="button" className="ghost-button compact-button" onClick={() => onExpandedChange(!expanded)}>
              {expanded ? "Collapse" : "Expand"}
            </button>
          ) : null}
        </div>

        {!expanded ? (
          <p className="panel__hint">
            Collapsed. Health-check actions can open this card so you can explicitly author or import design targets.
          </p>
        ) : null}

        {lastRefreshed ? (
          <p className="panel__hint">Last refreshed: {lastRefreshed}</p>
        ) : null}

        {expanded ? (
          <>
        {response?.warnings.length ? (
          <ul className="warning-list">
            {response.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        ) : null}

        {saveSuccess ? (
          <div className="inline-success design-targets-save-success">
            <span>Saved successfully.</span>
            {showHealthRerunPrompt && onRunHealthCheck ? (
              <button type="button" className="ghost-button compact-button" onClick={onRunHealthCheck}>
                Run Project Health Check again
              </button>
            ) : null}
          </div>
        ) : null}
        {saveError ? <div className="inline-error">{saveError}</div> : null}

        {edit.mode === "none" && (
          <>
            {targets.length > 0 && (
              <table className="design-targets-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Label</th>
                    <th>Metric</th>
                    <th>Operator</th>
                    <th>Value</th>
                    <th>Priority</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {targets.map((t, i) => (
                    <tr key={t.target_id}>
                      <td>{t.target_id}</td>
                      <td>{t.label}</td>
                      <td>{t.metric}</td>
                      <td>{SUPPORTED_OPERATORS.find((o) => o.value === t.operator)?.label ?? t.operator}</td>
                      <td>
                        {t.value}
                        {t.unit ? ` ${t.unit}` : ""}
                      </td>
                      <td>
                        <span className={`badge ${t.priority === "critical" || t.priority === "required" ? "badge-fail" : t.priority === "preferred" || t.priority === "high" ? "badge-warn" : "badge-muted"}`}>
                          {t.priority ?? "required"}
                        </span>
                      </td>
                      <td>
                        <div className="button-row">
                          <button
                            type="button"
                            className="ghost-button compact-button"
                            onClick={() => setEdit({ mode: "edit", index: i, draft: { ...t } })}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="ghost-button compact-button"
                            onClick={() => void handleDelete(i)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="button-row">
              <button type="button" className="primary-button compact-button" onClick={() => setEdit({ mode: "add", draft: { ...EMPTY_TARGET } })}>
                Add target
              </button>
              <button type="button" className="ghost-button compact-button" onClick={() => setEdit({ mode: "import", text: "" })}>
                Import JSON
              </button>
              <button type="button" className="ghost-button compact-button" onClick={() => void load()}>
                Refresh
              </button>
            </div>
          </>
        )}

        {(edit.mode === "add" || edit.mode === "edit") && (
          <div className="design-targets-form">
            <strong>{edit.mode === "add" ? "Add Design Target" : "Edit Design Target"}</strong>
            <div className="form-row">
              <label>
                Target ID
                <input
                  type="text"
                  value={edit.draft.target_id}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, target_id: e.target.value } })}
                  placeholder="e.g., mass_reduce_10pct"
                />
              </label>
              <label>
                Label
                <input
                  type="text"
                  value={edit.draft.label}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, label: e.target.value } })}
                  placeholder="e.g., Mass reduction"
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                Metric
                <input
                  type="text"
                  value={edit.draft.metric}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, metric: e.target.value } })}
                  placeholder="e.g., mass_kg"
                />
              </label>
              <label>
                Operator
                <select
                  value={edit.draft.operator}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, operator: e.target.value as DesignTarget["operator"] } })}
                >
                  {SUPPORTED_OPERATORS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="form-row">
              {edit.draft.operator === "within_range" ? (
                <>
                  <label>
                    Range Min
                    <input
                      type="number"
                      step="any"
                      value={edit.draft.threshold_min ?? ""}
                      onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, threshold_min: e.target.value === "" ? null : parseFloat(e.target.value) } })}
                    />
                  </label>
                  <label>
                    Range Max
                    <input
                      type="number"
                      step="any"
                      value={edit.draft.threshold_max ?? edit.draft.value}
                      onChange={(e) => {
                        const next = e.target.value === "" ? null : parseFloat(e.target.value);
                        setEdit({ ...edit, draft: { ...edit.draft, threshold_max: next, value: next ?? 0 } });
                      }}
                    />
                  </label>
                </>
              ) : (
                <label>
                  Value
                  <input
                    type="number"
                    step="any"
                    value={edit.draft.value}
                    onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, value: parseFloat(e.target.value) || 0 } })}
                  />
                </label>
              )}
              <label>
                Unit
                <input
                  type="text"
                  value={edit.draft.unit ?? ""}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, unit: e.target.value || null } })}
                  placeholder="e.g., kg, MPa"
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                Priority
                <select
                  value={edit.draft.priority ?? "required"}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, priority: e.target.value as DesignTarget["priority"] } })}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Load Case ID
                <input
                  type="text"
                  value={edit.draft.load_case_id ?? ""}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, load_case_id: e.target.value || null } })}
                  placeholder="optional"
                />
              </label>
            </div>
            <div className="form-row">
              <label style={{ flex: 1 }}>
                Scope
                <input
                  type="text"
                  value={edit.draft.scope ?? ""}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, scope: e.target.value || null } })}
                  placeholder="optional"
                />
              </label>
            </div>
            <div className="form-row">
              <label style={{ flex: 1 }}>
                Rationale
                <input
                  type="text"
                  value={edit.draft.rationale ?? ""}
                  onChange={(e) => setEdit({ ...edit, draft: { ...edit.draft, rationale: e.target.value || null } })}
                  placeholder="optional"
                />
              </label>
            </div>
            <div className="button-row">
              <button type="button" className="primary-button compact-button" onClick={() => void handleSave()}>
                Save
              </button>
              <button type="button" className="ghost-button compact-button" onClick={() => { setEdit({ mode: "none" }); setSaveError(null); }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {edit.mode === "import" && (
          <div className="design-targets-form">
            <strong>Import Design Targets (JSON)</strong>
            <textarea
              rows={6}
              value={edit.text}
              onChange={(e) => setEdit({ ...edit, text: e.target.value })}
              placeholder={'[\n  {\n    "target_id": "mass_reduce_10pct",\n    "label": "Mass reduction",\n    "metric": "mass_kg",\n    "operator": "reduce_by_at_least",\n    "value": 10,\n    "unit": "%",\n    "priority": "required"\n  }\n]'}
            />
            <div className="button-row">
              <button type="button" className="primary-button compact-button" onClick={() => void handleSave()}>
                Import
              </button>
              <button type="button" className="ghost-button compact-button" onClick={() => { setEdit({ mode: "none" }); setSaveError(null); }}>
                Cancel
              </button>
            </div>
          </div>
        )}
          </>
        ) : null}
      </div>
    </article>
  );
}
