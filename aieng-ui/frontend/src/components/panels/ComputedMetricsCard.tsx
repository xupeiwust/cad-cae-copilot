import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { ComputedMetricTargetMapping, ComputedMetricValue, ComputedMetricsImportPayload, ComputedMetricsResponse, DesignTargetComparisonItem, TargetComparisonResponse } from "../../types";

type ComputedMetricsState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; response: ComputedMetricsResponse }
  | { status: "error"; message: string };

type ComputedMetricsCardProps = {
  projectId: string | null;
  highlighted?: boolean;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  onSaved?: () => void;
  showHealthRerunPrompt?: boolean;
  onRunHealthCheck?: () => void;
  /** Increment to trigger a data refresh without re-mounting. */
  refreshKey?: number | string;
};

const JSON_EXAMPLE = `{
  "max_von_mises_stress": { "value": 187.4, "unit": "MPa" },
  "max_displacement": { "value": 0.82, "unit": "mm" },
  "mass": { "value": 1.24, "unit": "kg" }
}`;

const CSV_EXAMPLE = `metric,value,unit,load_case_id
max_von_mises_stress,187.4,MPa,load_case_001
max_displacement,0.82,mm,load_case_001
mass,1.24,kg,`;

function mappingBadge(status: ComputedMetricTargetMapping["status"]): string {
  if (status === "mapped") return "badge badge-pass";
  if (status === "missing_metric") return "badge badge-fail";
  if (status === "ambiguous") return "badge badge-warn";
  return "badge badge-muted";
}

function comparisonBadge(status: DesignTargetComparisonItem["status"]): string {
  if (status === "pass") return "badge badge-pass";
  if (status === "fail") return "badge badge-fail";
  if (status === "unknown") return "badge badge-warn";
  return "badge badge-muted";
}

function valueText(value: unknown): string {
  if (value && typeof value === "object" && "value" in value) {
    const actual = (value as { value?: unknown; unit?: unknown }).value;
    const unit = (value as { value?: unknown; unit?: unknown }).unit;
    if (actual === null || actual === undefined) return "n/a";
    return `${actual}${unit ? ` ${unit}` : ""}`;
  }
  if (value === null || value === undefined) return "n/a";
  return String(value);
}

function expectedText(value: unknown): string {
  if (!value || typeof value !== "object") return "n/a";
  const expected = value as Record<string, unknown>;
  const comparator = expected.comparator ? `${expected.comparator} ` : "";
  if (expected.threshold !== undefined) return `${comparator}${expected.threshold}`;
  if (expected.threshold_min !== undefined || expected.threshold_max !== undefined) {
    return `${expected.threshold_min ?? "-inf"} to ${expected.threshold_max ?? "inf"}`;
  }
  return comparator.trim() || "n/a";
}

function metricRows(response: ComputedMetricsResponse | null): Array<{ scope: string; metric: string; value: ComputedMetricValue }> {
  const doc = response?.document;
  if (!doc) return [];
  const rows: Array<{ scope: string; metric: string; value: ComputedMetricValue }> = [];
  Object.entries(doc.global_metrics ?? {}).forEach(([metric, value]) => rows.push({ scope: "global", metric, value }));
  (doc.load_cases ?? []).forEach((loadCase) => {
    Object.entries(loadCase.metrics ?? {}).forEach(([metric, value]) => rows.push({ scope: loadCase.load_case_id, metric, value }));
  });
  return rows;
}

export function ComputedMetricsCard({
  projectId,
  highlighted = false,
  expanded = true,
  onExpandedChange,
  onSaved,
  showHealthRerunPrompt = false,
  onRunHealthCheck,
  refreshKey,
}: ComputedMetricsCardProps) {
  const [state, setState] = useState<ComputedMetricsState>({ status: "idle" });
  const [format, setFormat] = useState<"json" | "csv">("json");
  const [text, setText] = useState(JSON_EXAMPLE);
  const [preview, setPreview] = useState<ComputedMetricsResponse | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [comparison, setComparison] = useState<TargetComparisonResponse | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setState({ status: "loading" });
    setSaveError(null);
    try {
      const [response, comparisonResponse] = await Promise.all([
        api.getComputedMetrics(projectId),
        api.getTargetComparison(projectId).catch(() => null),
      ]);
      setState({ status: "loaded", response });
      setComparison(comparisonResponse);
      setLastRefreshed(new Date().toLocaleString());
    } catch (err) {
      setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      setComparison(null);
      setLastRefreshed(new Date().toLocaleString());
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const loadedResponse = state.status === "loaded" ? state.response : null;
  const visibleRows = useMemo(() => metricRows(preview ?? loadedResponse).slice(0, 20), [preview, loadedResponse]);
  const mappings = (preview ?? loadedResponse)?.target_mapping ?? [];
  const comparisonItems = comparison?.items ?? [];
  const hasPreview = preview !== null;

  const buildPayload = useCallback((): ComputedMetricsImportPayload => ({ format, text }), [format, text]);

  const handlePreview = useCallback(async () => {
    if (!projectId) return;
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const response = await api.previewComputedMetrics(projectId, buildPayload());
      setPreview(response);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    }
  }, [buildPayload, projectId]);

  const handleSave = useCallback(async () => {
    if (!projectId) return;
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const payload = preview?.document ? { format: "json" as const, document: preview.document } : buildPayload();
      const response = await api.saveComputedMetrics(projectId, payload);
      setPreview(response);
      setSaveSuccess(true);
      await load();
      onSaved?.();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    }
  }, [buildPayload, load, onSaved, preview, projectId]);

  if (!projectId) {
    return (
      <article className="copilot-loop__demo-card">
        <div className="copilot-loop__demo-health">
          <strong>Computed Metrics</strong>
          <p className="panel__hint">Select a project to view or import computed metrics.</p>
        </div>
      </article>
    );
  }

  return (
    <article className={`copilot-loop__demo-card computed-metrics-card ${highlighted ? "readiness-highlight" : ""} ${!expanded ? "computed-metrics-card--collapsed" : ""}`}>
      <div className="copilot-loop__demo-health">
        <div className="copilot-loop__demo-health-header">
          <div>
            <strong>Computed Metrics</strong>
            <span className="panel__hint">
              {loadedResponse?.artifact_path
                ? `${loadedResponse.metrics_count} metric(s), ${loadedResponse.load_case_count} load case(s).`
                : "Import postprocessed scalar metrics before target mapping."}
            </span>
          </div>
          {onExpandedChange ? (
            <button type="button" className="ghost-button compact-button" onClick={() => onExpandedChange(!expanded)}>
              {expanded ? "Collapse" : "Expand"}
            </button>
          ) : null}
        </div>

        {!expanded ? <p className="panel__hint">Collapsed. Health-check actions can open this card for explicit metric import.</p> : null}

        {lastRefreshed ? <p className="panel__hint">Last refreshed: {lastRefreshed}</p> : null}

        {expanded ? (
          <>
            <p className="panel__hint">
              Preview is read-only. Save writes only <code>results/computed_metrics.json</code>; it does not run solvers, edit CAD, or advance claims.
            </p>

            {state.status === "loading" ? <p className="panel__hint">Loading…</p> : null}
            {state.status === "error" ? <div className="inline-error">{state.message}</div> : null}
            {loadedResponse?.warnings.length ? (
              <ul className="warning-list">{loadedResponse.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            ) : null}

            {visibleRows.length ? (
              <table className="computed-metrics-table">
                <thead>
                  <tr>
                    <th>Scope</th>
                    <th>Metric</th>
                    <th>Value</th>
                    <th>Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={`${row.scope}:${row.metric}`}>
                      <td>{row.scope}</td>
                      <td>{row.metric}</td>
                      <td>{row.value.value}</td>
                      <td>{row.value.unit ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="panel__hint">No computed metrics found yet.</p>
            )}

            <div className="computed-metrics-import">
              <div className="button-row">
                <label className="computed-metrics-format">
                  Format
                  <select
                    value={format}
                    onChange={(e) => {
                      const next = e.target.value as "json" | "csv";
                      setFormat(next);
                      setText(next === "json" ? JSON_EXAMPLE : CSV_EXAMPLE);
                      setPreview(null);
                    }}
                  >
                    <option value="json">JSON</option>
                    <option value="csv">CSV</option>
                  </select>
                </label>
                <button type="button" className="ghost-button compact-button" onClick={() => void load()}>
                  Refresh
                </button>
              </div>
              <textarea rows={format === "json" ? 8 : 6} value={text} onChange={(e) => setText(e.target.value)} />
              <div className="button-row">
                <button type="button" className="ghost-button compact-button" onClick={() => void handlePreview()}>
                  Preview
                </button>
                <button type="button" className="primary-button compact-button" onClick={() => void handleSave()} disabled={hasPreview && preview?.ok === false}>
                  Save computed metrics
                </button>
              </div>
            </div>

            {preview ? (
              <div className={`computed-metrics-preview ${preview.ok ? "computed-metrics-preview--ok" : "computed-metrics-preview--error"}`}>
                <strong>Preview: {preview.ok ? "valid" : "has validation errors"}</strong>
                <span className="panel__hint">{preview.metrics_count} metric(s), {preview.load_case_count} load case(s).</span>
                {preview.errors.length ? (
                  <ul className="warning-list">
                    {preview.errors.map((err, i) => (
                      <li key={i}>{err.code}: {err.message}{err.row ? ` (row ${err.row})` : ""}{err.field ? ` [${err.field}]` : ""}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {mappings.length ? (
              <div className="computed-metrics-mapping">
                <strong>Target mapping</strong>
                <table className="computed-metrics-table">
                  <thead>
                    <tr>
                      <th>Target</th>
                      <th>Metric</th>
                      <th>Status</th>
                      <th>Summary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mappings.map((m) => (
                      <tr key={m.target_id}>
                        <td>{m.target_label}</td>
                        <td>{m.metric || "—"}</td>
                        <td><span className={mappingBadge(m.status)}>{m.status}</span></td>
                        <td>{m.summary}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="panel__hint">Mapping only checks metric availability. It does not certify the design or evaluate claims.</p>
              </div>
            ) : null}

            {comparisonItems.length ? (
              <div className="computed-metrics-mapping target-comparison-results">
                <div className="copilot-loop__demo-health-header">
                  <div>
                    <strong>Target comparison</strong>
                    <span className="panel__hint">
                      {comparison?.summary.pass ?? 0} pass, {comparison?.summary.fail ?? 0} fail, {comparison?.summary.unknown ?? 0} unknown.
                    </span>
                  </div>
                </div>
                <table className="computed-metrics-table">
                  <thead>
                    <tr>
                      <th>Target</th>
                      <th>Status</th>
                      <th>Actual</th>
                      <th>Expected</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonItems.map((item) => (
                      <tr key={item.target_id}>
                        <td>{item.target_label || item.target_id}</td>
                        <td><span className={comparisonBadge(item.status)}>{item.status}</span></td>
                        <td>{valueText(item.actual)}</td>
                        <td>{expectedText(item.expected)}</td>
                        <td>{item.reason_code || item.notes || "deterministic comparison"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="panel__hint">{comparison?.claim_boundary}</p>
              </div>
            ) : null}

            {saveSuccess ? (
              <div className="inline-success computed-metrics-save-success">
                <span>Saved successfully.</span>
                {showHealthRerunPrompt && onRunHealthCheck ? (
                  <button type="button" className="ghost-button compact-button" onClick={onRunHealthCheck}>
                    Run Project Health Check again
                  </button>
                ) : null}
              </div>
            ) : null}
            {saveError ? <div className="inline-error">{saveError}</div> : null}
          </>
        ) : null}
      </div>
    </article>
  );
}
