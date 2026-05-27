import { ActionIcon } from "../common";
import {
  caeModeClass,
  caeModeLabel,
  fieldLabel,
  formatRecordSummary,
  isLowRiskArtifactPath,
} from "../../appUtils";
import type { ArtifactResponse, CaeReviewReport, ProjectSummary, SolverFieldDescriptor } from "../../types";

type CaePanelProps = {
  summary: ProjectSummary | null;
  selectedId: string | null;
  caeSummary: ProjectSummary["cae"] | null;
  hasCaeContext: boolean;
  hasCaeResultArtifacts: boolean;
  renderableCaeFields: string[];
  selectedCaeField: string;
  fieldDescriptor: SolverFieldDescriptor | null;
  caeRefreshing: boolean;
  caeReviewReport: CaeReviewReport | null;
  caeReviewLoading: boolean;
  metricsInputPath: string;
  metricsLoadCaseId: string;
  metricsSoftware: string;
  metricsImporting: boolean;
  frdInputPath: string;
  frdLoadCaseId: string;
  frdSoftware: string;
  frdExtracting: boolean;
  artifactViewerPath: string;
  artifactViewerData: ArtifactResponse | null;
  artifactViewerBusy: boolean;
  setSelectedCaeField(value: string): void;
  setMetricsInputPath(value: string): void;
  setMetricsLoadCaseId(value: string): void;
  setMetricsSoftware(value: string): void;
  setFrdInputPath(value: string): void;
  setFrdLoadCaseId(value: string): void;
  setFrdSoftware(value: string): void;
  setArtifactViewerPath(value: string): void;
  refreshCaeSummary(): Promise<void>;
  generateCaeReviewReport(): Promise<void>;
  importMetricsAndRefresh(): Promise<void>;
  extractFrdAndRefresh(): Promise<void>;
  viewArtifact(path: string): Promise<void>;
};

export function CaePanel({
  summary,
  selectedId,
  caeSummary,
  hasCaeContext,
  hasCaeResultArtifacts,
  renderableCaeFields,
  selectedCaeField,
  fieldDescriptor,
  caeRefreshing,
  caeReviewReport,
  caeReviewLoading,
  metricsInputPath,
  metricsLoadCaseId,
  metricsSoftware,
  metricsImporting,
  frdInputPath,
  frdLoadCaseId,
  frdSoftware,
  frdExtracting,
  artifactViewerPath,
  artifactViewerData,
  artifactViewerBusy,
  setSelectedCaeField,
  setMetricsInputPath,
  setMetricsLoadCaseId,
  setMetricsSoftware,
  setFrdInputPath,
  setFrdLoadCaseId,
  setFrdSoftware,
  setArtifactViewerPath,
  refreshCaeSummary,
  generateCaeReviewReport,
  importMetricsAndRefresh,
  extractFrdAndRefresh,
  viewArtifact,
}: CaePanelProps) {
  return (
    <>
      {summary ? (
              <section className="card">
                <div className="section-heading">
                  <div>
                    <h2>仿真状态</h2>
                  </div>
                </div>

                <div className="summary-note summary-primary" style={{ marginBottom: 12 }}>
                  <strong>审查报告</strong>
                  <p style={{ fontSize: 12, margin: "4px 0 8px" }}>
                    只读审查：检查仿真准备度、结果指标、过期证据和设计目标。
                  </p>
                  <div className="action-row">
                    <button
                      disabled={caeReviewLoading || !selectedId}
                      onClick={() => void generateCaeReviewReport()}
                    >
                      <ActionIcon name="report" />
                      {caeReviewLoading ? "生成中..." : "生成报告"}
                    </button>
                    {caeReviewReport ? (
                      <span className="summary-muted" style={{ fontSize: 12 }}>
                        {caeReviewReport.package_name} — claims advanced: {caeReviewReport.sections.claim_boundary.claims_advanced ? "yes" : "no"}
                      </span>
                    ) : null}
                  </div>
                  {caeReviewReport ? (
                    <div style={{ marginTop: 10 }}>
                      <div className="cae-overview-grid">
                        <div><span>Evidence</span><strong>{caeReviewReport.sections.available_evidence.evidence_count}</strong></div>
                        <div><span>Missing</span><strong>{caeReviewReport.sections.missing_information.items.length}</strong></div>
                        <div><span>Stale</span><strong>{caeReviewReport.sections.stale_evidence.requires_revalidation ? "yes" : "no"}</strong></div>
                        <div><span>Targets</span><strong>{caeReviewReport.sections.design_targets.present ? "yes" : "no"}</strong></div>
                      </div>
                      <pre className="artifact-preview" style={{ maxHeight: 260, marginTop: 10, whiteSpace: "pre-wrap" }}>
                        {caeReviewReport.markdown}
                      </pre>
                    </div>
                  ) : null}
                </div>

                {caeSummary?.artifact_detection ? (
                  <>
                    <div className={`cae-mode-badge ${caeModeClass(caeSummary.artifact_detection.mode)}`}>
                      {caeModeLabel(caeSummary.artifact_detection.mode)}
                    </div>
                    <div className="cae-artifact-grid">
                      {Object.entries(caeSummary.artifact_detection.artifacts).map(([path, present]) => (
                        <div key={path} className={`cae-artifact-item ${present ? "present" : "missing"}`}>
                          <span className="cae-artifact-icon">{present ? "✓" : "✗"}</span>
                          {present && isLowRiskArtifactPath(path) ? (
                            <button
                              type="button"
                              className="cae-artifact-path artifact-link"
                              onClick={() => void viewArtifact(path)}
                              title={`查看 ${path}`}
                            >
                              {path}
                            </button>
                          ) : (
                            <span className="cae-artifact-path">{path}</span>
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="cae-artifact-footer">
                      检测到 {caeSummary.artifact_detection.detected_count} / {caeSummary.artifact_detection.total_count} 个文件。
                    </div>
                    <div className="action-row" style={{ marginTop: 10 }}>
                      <button
                        disabled={caeRefreshing || !selectedId}
                        onClick={() => void refreshCaeSummary()}
                      >
                        <ActionIcon name="refresh" />
                        {caeRefreshing ? "正在刷新 CAE 摘要…" : "刷新 CAE 摘要"}
                      </button>
                      <span className="summary-muted" style={{ fontSize: 12 }}>
                        重新生成 CAE 摘要（不执行求解器）
                      </span>
                    </div>
                    <div className="summary-note" style={{ marginTop: 12 }}>
                      <strong>导入外部指标</strong>
                      <input
                        type="text"
                        placeholder="C:\path\to\metrics.json or metrics.csv"
                        value={metricsInputPath}
                        onChange={(e) => setMetricsInputPath(e.target.value)}
                        style={{ width: "100%", marginBottom: 6 }}
                      />
                      <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                        <input
                          type="text"
                          placeholder="Load case ID"
                          value={metricsLoadCaseId}
                          onChange={(e) => setMetricsLoadCaseId(e.target.value)}
                          style={{ flex: 1 }}
                        />
                        <input
                          type="text"
                          placeholder="Software (e.g. FreeCAD FEM)"
                          value={metricsSoftware}
                          onChange={(e) => setMetricsSoftware(e.target.value)}
                          style={{ flex: 1 }}
                        />
                      </div>
                      <div className="action-row">
                        <button
                          disabled={metricsImporting || !selectedId}
                          onClick={() => void importMetricsAndRefresh()}
                        >
                          <ActionIcon name="import" />
                          {metricsImporting ? "正在导入并刷新…" : "导入计算指标并刷新摘要"}
                        </button>
                      </div>
                    </div>
                    <div className="summary-note" style={{ marginTop: 12 }}>
                      <strong>提取 FRD 结果</strong>
                      <input
                        type="text"
                        placeholder="C:\path\to\job.frd"
                        value={frdInputPath}
                        onChange={(e) => setFrdInputPath(e.target.value)}
                        style={{ width: "100%", marginBottom: 6 }}
                      />
                      <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                        <input
                          type="text"
                          placeholder="Load case ID"
                          value={frdLoadCaseId}
                          onChange={(e) => setFrdLoadCaseId(e.target.value)}
                          style={{ flex: 1 }}
                        />
                        <input
                          type="text"
                          placeholder="Software (e.g. CalculiX)"
                          value={frdSoftware}
                          onChange={(e) => setFrdSoftware(e.target.value)}
                          style={{ flex: 1 }}
                        />
                      </div>
                      <div className="action-row">
                        <button
                          disabled={frdExtracting || !selectedId}
                          onClick={() => void extractFrdAndRefresh()}
                        >
                          <ActionIcon name="import" />
                          {frdExtracting ? "正在提取并刷新…" : "提取 FRD 结果并刷新摘要"}
                        </button>
                      </div>
                    </div>
                    {caeSummary?.preprocessing_summary ? (
                      <div className="summary-note" style={{ marginTop: 10 }}>
                        <strong>前处理</strong>
                        <p>{caeSummary.preprocessing_summary.llm_summary.one_line}</p>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", marginTop: 6 }}>
                          <small>材料: {caeSummary.preprocessing_summary.status.has_materials ? "✓" : "✗"}</small>
                          <small>载荷: {caeSummary.preprocessing_summary.status.has_loads ? "✓" : "✗"}</small>
                          <small>边界条件: {caeSummary.preprocessing_summary.status.has_boundary_conditions ? "✓" : "✗"}</small>
                          <small>网格: {caeSummary.preprocessing_summary.status.has_mesh ? "✓" : "✗"}</small>
                          <small>求解器设置: {caeSummary.preprocessing_summary.status.has_solver_settings ? "✓" : "✗"}</small>
                          <small>就绪: <strong>{caeSummary.preprocessing_summary.status.ready_for_solver ? "是" : "否"}</strong></small>
                        </div>
                        {caeSummary.preprocessing_summary.status.missing_items.length > 0 ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>Missing:</strong> {caeSummary.preprocessing_summary.status.missing_items.join(", ")}</small>
                          </div>
                        ) : null}
                        <div style={{ marginTop: 6 }}>
                          <small className="summary-muted">基于文件检测，未执行求解器。</small>
                        </div>
                      </div>
                    ) : null}
                    {caeSummary?.simulation_run_summary ? (
                      <div className="summary-note" style={{ marginTop: 10 }}>
                        <strong>仿真记录</strong>
                        <p>{caeSummary.simulation_run_summary.llm_summary.one_line}</p>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", marginTop: 6 }}>
                          <small>有记录: {caeSummary.simulation_run_summary.status.has_simulation_runs ? "是" : "否"}</small>
                          <small>次数: {caeSummary.simulation_run_summary.status.run_count}</small>
                          <small>最近: {caeSummary.simulation_run_summary.status.latest_run_id ?? "无"}</small>
                          <small>已完成: {caeSummary.simulation_run_summary.status.has_completed_run ? "是" : "否"}</small>
                          <small>收敛: {caeSummary.simulation_run_summary.status.has_converged_run ? "是" : "否"}</small>
                          <small>失败: {caeSummary.simulation_run_summary.status.has_failed_run ? "是" : "否"}</small>
                        </div>
                        {caeSummary.simulation_run_summary.runs.length > 0 ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>Latest run:</strong> {caeSummary.simulation_run_summary.runs[0].solver} / {caeSummary.simulation_run_summary.runs[0].software} — {caeSummary.simulation_run_summary.runs[0].analysis_type} — {caeSummary.simulation_run_summary.runs[0].state}</small>
                          </div>
                        ) : null}
                        {caeSummary.simulation_run_summary.status.warnings.length > 0 ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>警告:</strong> {caeSummary.simulation_run_summary.status.warnings.length}</small>
                          </div>
                        ) : null}
                        <div style={{ marginTop: 6 }}>
                          <small className="summary-muted">仅基于元数据，未执行求解器。</small>
                        </div>
                      </div>
                    ) : null}
                    {caeSummary?.result_summary ? (
                      <div className="summary-note" style={{ marginTop: 10 }}>
                        <strong>后处理</strong>
                        <p>{caeSummary.result_summary.llm_summary.one_line}</p>
                        {caeSummary.result_summary.source.solver !== "external_or_unknown" ? (
                          <small>Solver: {caeSummary.result_summary.source.solver}</small>
                        ) : null}
                        {caeSummary.result_summary.source.software ? (
                          <small> | Software: {caeSummary.result_summary.source.software}</small>
                        ) : null}
                        {caeSummary.result_summary.load_cases.length > 0 ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>Load cases ({caeSummary.result_summary.load_cases.length}):</strong></small>
                            <ul style={{ margin: "4px 0", paddingLeft: 16 }}>
                              {caeSummary.result_summary.load_cases.map((lc) => (
                                <li key={lc.id}>
                                  <small>{lc.name} ({lc.type}){lc.magnitude != null ? ` — ${lc.magnitude}${lc.unit ? ` ${lc.unit}` : ""}` : ""}</small>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {caeSummary.result_summary.solver_settings ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>Solver settings:</strong> {caeSummary.result_summary.solver_settings.solver_type ?? "unknown"}{caeSummary.result_summary.solver_settings.analysis_type ? ` / ${caeSummary.result_summary.solver_settings.analysis_type}` : ""}</small>
                          </div>
                        ) : null}
                        {caeSummary.result_summary.field_metadata && caeSummary.result_summary.field_metadata.count > 0 ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>Field metadata:</strong> {caeSummary.result_summary.field_metadata.count} field(s) registered{caeSummary.result_summary.field_metadata.format ? ` (${caeSummary.result_summary.field_metadata.format})` : ""}</small>
                          </div>
                        ) : null}
                        {caeSummary.result_summary.computed_values.extrema_computed ? (
                          <div style={{ marginTop: 6 }}>
                            <small><strong>Imported computed metrics</strong>{caeSummary.result_summary.computed_values.computed_by ? ` — ${caeSummary.result_summary.computed_values.computed_by}` : ""}</small>
                            <div style={{ marginTop: 2 }}>
                              {caeSummary.result_summary.computed_values.max_von_mises_stress ? (
                                <small>σ_max: {caeSummary.result_summary.computed_values.max_von_mises_stress.value} {caeSummary.result_summary.computed_values.max_von_mises_stress.unit || ""} | </small>
                              ) : null}
                              {caeSummary.result_summary.computed_values.max_displacement ? (
                                <small>U_max: {caeSummary.result_summary.computed_values.max_displacement.value} {caeSummary.result_summary.computed_values.max_displacement.unit || ""} | </small>
                              ) : null}
                              {caeSummary.result_summary.computed_values.minimum_safety_factor ? (
                                <small>SF_min: {caeSummary.result_summary.computed_values.minimum_safety_factor.value}</small>
                              ) : null}
                            </div>
                          </div>
                        ) : null}
                        {caeSummary.result_summary.design_target_comparisons?.present ? (
                          <div style={{ marginTop: 10 }}>
                            <small><strong>设计目标对比</strong></small>
                            {caeSummary.result_summary.design_target_comparisons.summary ? (
                              <div style={{ marginTop: 4 }}>
                                <small>
                                  Total {caeSummary.result_summary.design_target_comparisons.summary.total ?? 0}
                                  {", "} pass: {caeSummary.result_summary.design_target_comparisons.summary.pass ?? 0}
                                  {", "} fail: {caeSummary.result_summary.design_target_comparisons.summary.fail ?? 0}
                                  {", "} unknown: {caeSummary.result_summary.design_target_comparisons.summary.unknown ?? 0}
                                  {", "} not evaluated: {caeSummary.result_summary.design_target_comparisons.summary.not_evaluated ?? 0}
                                </small>
                              </div>
                            ) : null}
                            {caeSummary.result_summary.design_target_comparisons.items && caeSummary.result_summary.design_target_comparisons.items.length > 0 ? (
                              <table style={{ marginTop: 6, fontSize: "0.85em", width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                  <tr style={{ borderBottom: "1px solid #ddd" }}>
                                    <th style={{ textAlign: "left", padding: "2px 4px" }}><small>目标</small></th>
                                    <th style={{ textAlign: "left", padding: "2px 4px" }}><small>预期</small></th>
                                    <th style={{ textAlign: "left", padding: "2px 4px" }}><small>实际</small></th>
                                    <th style={{ textAlign: "left", padding: "2px 4px" }}><small>状态</small></th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {caeSummary.result_summary.design_target_comparisons.items.map((item) => (
                                    <tr key={item.target_id} style={{ borderBottom: "1px solid #eee" }}>
                                      <td style={{ padding: "2px 4px" }}>
                                        <small>{item.target_id}</small>
                                        {item.target_type ? <small style={{ display: "block", color: "#666" }}>{item.target_type}</small> : null}
                                      </td>
                                      <td style={{ padding: "2px 4px" }}>
                                        <small>{item.expected && typeof item.expected === "object" && "threshold" in item.expected ? String(item.expected.threshold) : "—"}</small>
                                      </td>
                                      <td style={{ padding: "2px 4px" }}>
                                        <small>{item.actual && typeof item.actual === "object" && "value" in item.actual ? String(item.actual.value) : "—"}</small>
                                      </td>
                                      <td style={{ padding: "2px 4px" }}>
                                        <span style={{
                                          padding: "2px 6px",
                                          borderRadius: 4,
                                          fontSize: "0.75em",
                                          fontWeight: 600,
                                          backgroundColor:
                                            item.status === "pass" ? "#d4edda" :
                                            item.status === "fail" ? "#f8d7da" :
                                            item.status === "unknown" ? "#fff3cd" : "#e2e3e5",
                                          color:
                                            item.status === "pass" ? "#155724" :
                                            item.status === "fail" ? "#721c24" :
                                            item.status === "unknown" ? "#856404" : "#383d41",
                                        }}>
                                          {item.status === "pass" ? "达标" :
                                           item.status === "fail" ? "未达标" :
                                           item.status === "unknown" ? "证据不足" : "未评估"}
                                        </span>
                                        {item.notes ? <small style={{ display: "block", color: "#666", marginTop: 2 }}>{item.notes}</small> : null}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : null}
                            <div style={{ marginTop: 4 }}>
                              <small className="summary-muted">非工程认证，不自动推进声明。</small>
                            </div>
                          </div>
                        ) : caeSummary.result_summary.status.has_results ? (
                          <div style={{ marginTop: 10 }}>
                            <small className="summary-muted">无设计目标对比数据。</small>
                          </div>
                        ) : null}
                        {caeSummary.result_summary.llm_summary.limitations.length ? (
                          <div style={{ marginTop: 6 }}>
                            <small>
                              Limitations: {caeSummary.result_summary.llm_summary.limitations.join(" ")}
                            </small>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="summary-note summary-muted">
                    <strong>仿真扫描不可用</strong>
                    <p>请配置 aieng 以启用 CAE 文件扫描。</p>
                  </div>
                )}

                {hasCaeContext ? (
                  <>
                    <div className="cae-overview-grid" style={{ marginTop: 14 }}>
                      <div><span>约束</span><strong>{caeSummary?.constraints_count ?? 0}</strong></div>
                      <div><span>载荷</span><strong>{caeSummary?.loads_count ?? 0}</strong></div>
                      <div><span>边界条件</span><strong>{caeSummary?.boundary_conditions_count ?? 0}</strong></div>
                      <div><span>结果证据</span><strong>{caeSummary?.result_evidence_count ?? 0}</strong></div>
                    </div>

                    <div className={hasCaeResultArtifacts ? "summary-note summary-primary" : "summary-note summary-muted"}>
                      <strong>{hasCaeResultArtifacts ? "已检测到 CAE 结果证据" : "仅检测到 CAE 上下文"}</strong>
                      <p>
                        {hasCaeResultArtifacts
                          ? "当前项目包含可用于 CAE 可视层的结果或场数据。选择标量场后，3D 预览会叠加对应的结果颜色。"
                          : "当前项目包含分析目标、约束或外部 CAE 交接信息，但还没有可渲染的求解结果。UI 会优雅降级，不阻断现有 CAD 预览。"}
                      </p>
                    </div>

                    {renderableCaeFields.length ? (
                      <div className="cae-field-shell">
                        <div className="cae-field-head">
                          <div>
                            <strong>Scalar Field Visualization</strong>
                            <span>
                              {fieldDescriptor?.source === "frd"
                                ? "使用 FRD 节点场数据映射到当前几何"
                                : "使用结果契约提供的标量场描述渲染"}
                            </span>
                          </div>
                          <select value={selectedCaeField} onChange={(event) => setSelectedCaeField(event.target.value)}>
                            {renderableCaeFields.map((field) => (
                              <option key={field} value={field}>
                                {fieldLabel(field)}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="cae-legend ready" />
                        <div className="cae-legend-scale">
                          <span>{fieldDescriptor ? `${fieldDescriptor.min_value} ${fieldDescriptor.unit ?? ""}`.trim() : "Low"}</span>
                          <strong>{fieldLabel(selectedCaeField)}</strong>
                          <span>{fieldDescriptor ? `${fieldDescriptor.max_value} ${fieldDescriptor.unit ?? ""}`.trim() : "High"}</span>
                        </div>
                      </div>
                    ) : hasCaeContext ? (
                      <div className="cae-field-shell pending-result">
                        <div className="cae-field-head">
                          <div>
                            <strong>Scalar Field Visualization</strong>
                            <span>未检测到可渲染的 CAE 结果场，3D 视图保持 CAD-only 预览。</span>
                          </div>
                        </div>
                        <div className="cae-legend pending" />
                        <div className="cae-legend-scale">
                          <span>No field</span>
                          <strong>Awaiting solver output</strong>
                          <span>CAD-only</span>
                        </div>
                      </div>
                    ) : null}

                    {caeSummary?.simulation_targets?.length ? (
                      <div className="cae-section-block">
                        <strong>Simulation Targets</strong>
                        <div className="cae-chip-list">
                          {caeSummary.simulation_targets.map((target, index) => (
                            <div key={`${String(target.id ?? index)}`} className="cae-chip-card">
                              <span>{String(target.metric ?? target.target ?? "simulation_target")}</span>
                              <strong>
                                {String(target.operator ?? "")}
                                {target.value != null ? ` ${String(target.value)}` : ""}
                              </strong>
                              <small>{String(target.reason ?? "")}</small>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {caeSummary?.protected_regions?.length ? (
                      <div className="cae-section-block">
                        <strong>Fixtures / Protected Regions</strong>
                        <div className="cae-list">
                          {caeSummary.protected_regions.map((item, index) => (
                            <div key={`${String(item.id ?? index)}`} className="cae-list-item">
                              <span>{String(item.target ?? item.id ?? "protected_region")}</span>
                              <strong>{String(item.type ?? "constraint")}</strong>
                              <small>{String(item.reason ?? "")}</small>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {caeSummary?.loads?.length ? (
                      <div className="cae-section-block">
                        <strong>Loads</strong>
                        <div className="cae-list">
                          {caeSummary.loads.map((item, index) => (
                            <div key={`${String((item as Record<string, unknown>).id ?? index)}`} className="cae-list-item compact">
                              <span>{formatRecordSummary(item as Record<string, unknown>) || `load_${index + 1}`}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {caeSummary?.boundary_conditions?.length ? (
                      <div className="cae-section-block">
                        <strong>Boundary Conditions</strong>
                        <div className="cae-list">
                          {caeSummary.boundary_conditions.map((item, index) => (
                            <div key={`${String((item as Record<string, unknown>).id ?? index)}`} className="cae-list-item compact">
                              <span>{formatRecordSummary(item as Record<string, unknown>) || `bc_${index + 1}`}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {caeSummary?.evidence?.length ? (
                      <div className="cae-section-block">
                        <strong>Evidence Ledger</strong>
                        <div className="cae-list">
                          {caeSummary.evidence.map((item, index) => {
                            const record = item as Record<string, unknown>;
                            return (
                              <div key={`${String(record.evidence_id ?? index)}`} className="cae-list-item">
                                <span>{String(record.evidence_type ?? "evidence")}</span>
                                <strong>{String(record.verification_status ?? "unknown")}</strong>
                                <small>{String(record.artifact_path ?? record.notes ?? "")}</small>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : null}
              </section>
            ) : (
              <section className="card">
                <div className="section-heading">
                  <div>
                    <h2>CAE Artifact Status</h2>
                    <p>选择或创建项目后，这里会显示 CAE 证据、约束、载荷和结果摘要。</p>
                  </div>
                </div>
                <div className="summary-note summary-muted">
                  <strong>暂无项目上下文</strong>
                  <p>当前没有选中项目，CAE 面板暂时没有可审计资源。</p>
                </div>
              </section>
            )}

            {selectedId ? (
              <section className="card">
                <div className="section-heading">
                  <div>
                    <h2>文件检查器</h2>
                  </div>
                </div>

                <div className="action-row" style={{ gap: 8 }}>
                  <input
                    type="text"
                    placeholder="e.g. results/computed_metrics.json"
                    value={artifactViewerPath}
                    onChange={(e) => setArtifactViewerPath(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button
                    disabled={artifactViewerBusy || !artifactViewerPath.trim()}
                    onClick={() => void viewArtifact(artifactViewerPath)}
                  >
                    <ActionIcon name="view" />
                    {artifactViewerBusy ? "加载中…" : "查看"}
                  </button>
                </div>

                {artifactViewerData ? (
                  <div style={{ marginTop: 10 }}>
                    {!artifactViewerData.exists ? (
                      <div className="summary-note summary-muted">
                        <strong>Artifact not found</strong>
                        <p>Path: {artifactViewerData.path}</p>
                      </div>
                    ) : (
                      <>
                        <div className="capability-facts" style={{ marginBottom: 8 }}>
                          <div><span>Path</span><strong>{artifactViewerData.path}</strong></div>
                          <div><span>Type</span><strong>{artifactViewerData.media_type}</strong></div>
                          <div><span>Size</span><strong>{artifactViewerData.size_bytes != null ? `${artifactViewerData.size_bytes} bytes` : "-"}</strong></div>
                        </div>
                        {artifactViewerData.warnings.length > 0 ? (
                          <div className="side-effect-list" style={{ marginBottom: 8 }}>
                            {artifactViewerData.warnings.map((w) => (
                              <span key={w}>{w}</span>
                            ))}
                          </div>
                        ) : null}
                        {artifactViewerData.parsed_json != null ? (
                          <details className="fold-block" open>
                            <summary className="fold-summary">Parsed JSON</summary>
                            <pre className="json-block">{JSON.stringify(artifactViewerData.parsed_json, null, 2)}</pre>
                          </details>
                        ) : artifactViewerData.text != null ? (
                          <details className="fold-block" open>
                            <summary className="fold-summary">Text content</summary>
                            <pre className="json-block">{artifactViewerData.text}</pre>
                          </details>
                        ) : (
                          <div className="summary-note summary-muted">
                            <strong>Binary or unreadable content</strong>
                            <p>This artifact exists but is not displayable as JSON or text.</p>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ) : null}
              </section>
            ) : null}
    </>
  );
}
