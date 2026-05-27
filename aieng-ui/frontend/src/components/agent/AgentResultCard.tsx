import type { ChatHistoryItem } from "../../appTypes";

type AgentResultCardProps = {
  cadResult?: ChatHistoryItem["cadResult"];
  heatmapActive: boolean;
  heatmapRange: { min: number; max: number } | null;
  onViewHeatmap(): void;
  simulationResult?: ChatHistoryItem["simulationResult"];
};

export function AgentResultCard({
  cadResult,
  heatmapActive,
  heatmapRange,
  onViewHeatmap,
  simulationResult,
}: AgentResultCardProps) {
  if (!cadResult && !simulationResult) return null;

  return (
    <>
      {cadResult ? (
        <div className="agent-result-card chat-cad-result">
          <div className="chat-cad-stats">
            <span>{cadResult.face_count} faces</span>
            <span>{cadResult.feature_count} features</span>
            <span>preview updated</span>
          </div>
          <details>
            <summary>View generated code</summary>
            <pre className="chat-cad-code">{cadResult.code}</pre>
          </details>
        </div>
      ) : null}

      {simulationResult ? (
        <div className={`agent-result-card chat-sim-result${simulationResult.status === "success" ? "" : " chat-sim-result-error"}`}>
          {simulationResult.status === "success" ? (
            <>
              <div className="chat-sim-stats">
                {simulationResult.von_mises_max_mpa != null ? (
                  <span>σ<sub>max</sub> {(simulationResult.von_mises_max_mpa as number).toFixed(1)} MPa</span>
                ) : null}
                {simulationResult.displacement_max_mm != null ? (
                  <span>u<sub>max</sub> {(simulationResult.displacement_max_mm as number).toFixed(3)} mm</span>
                ) : null}
                {simulationResult.verdict?.fos?.fos != null ? (
                  <span className={`chat-fos-badge chat-fos-${simulationResult.verdict.fos.rating}`}>
                    FoS {simulationResult.verdict.fos.fos.toFixed(2)}
                  </span>
                ) : null}
                {simulationResult.node_count != null ? (
                  <span>{simulationResult.node_count.toLocaleString()} nodes</span>
                ) : null}
                {simulationResult.mesh_size_mm != null ? (
                  <span>mesh {simulationResult.mesh_size_mm} mm</span>
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
          ) : simulationResult.status === "tools_unavailable" ? (
            <p className="chat-sim-missing">
              Tools not installed: {simulationResult.missing_tools?.join(", ")}
            </p>
          ) : (
            <>
              <p className="chat-sim-missing">
                Solver error (code {simulationResult.returncode ?? "?"})
              </p>
              {simulationResult.diagnosis?.length ? (
                <ul className="chat-sim-diagnosis">
                  {simulationResult.diagnosis.map((diagnosis, index) => (
                    <li key={index}>{diagnosis}</li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
          {simulationResult.written_artifacts?.length ? (
            <div className="chat-preprocess-files">
              {simulationResult.written_artifacts.map((artifact) => (
                <span key={artifact} className="chat-preprocess-file">{artifact}</span>
              ))}
            </div>
          ) : null}
          {(simulationResult.warnings?.length ?? 0) > 0 ? (
            <details>
              <summary>{simulationResult.warnings!.length} warning{simulationResult.warnings!.length !== 1 ? "s" : ""}</summary>
              <ul className="chat-preprocess-warnings">
                {simulationResult.warnings!.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </details>
          ) : null}

          {simulationResult.verdict && simulationResult.verdict.overall !== "no_targets" ? (
            <div className={`chat-verdict chat-verdict-${simulationResult.verdict.overall}`}>
              <div className="chat-verdict-header">
                <span className="chat-verdict-badge">
                  {simulationResult.verdict.overall === "pass" ? "PASS" :
                   simulationResult.verdict.overall === "fail" ? "FAIL" :
                   simulationResult.verdict.overall === "partial" ? "PARTIAL" : "UNKNOWN"}
                </span>
                <span className="chat-verdict-counts">
                  {simulationResult.verdict.pass_count} passed · {simulationResult.verdict.fail_count} failed
                </span>
              </div>
              {simulationResult.verdict.items.filter((item) => item.status !== "not_evaluated").map((item) => (
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
              {simulationResult.verdict.suggestions.length > 0 ? (
                <details className="chat-verdict-suggestions">
                  <summary>Suggestions ({simulationResult.verdict.suggestions.length})</summary>
                  <ul>
                    {simulationResult.verdict.suggestions.map((suggestion, index) => (
                      <li key={index}>{suggestion}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
