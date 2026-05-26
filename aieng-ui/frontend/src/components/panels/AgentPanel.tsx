import { ActionIcon, JsonDisclosure } from "../common";
import {
  getLlmProviderLabel,
  jsonBlock,
  mutabilityLabel,
  workflowStepLabel,
} from "../../appUtils";
import type { BenchmarkRun, BenchmarkScenario, CapabilityDescriptor, CapabilityPreview, LLMConfig, ProjectSummary, WorkflowDefinition } from "../../types";

type AgentPanelProps = {
  busy: boolean;
  capabilities: CapabilityDescriptor[];
  capabilityCategory: string;
  capabilityCategories: string[];
  capabilityQuery: string;
  filteredCapabilities: CapabilityDescriptor[];
  selectedCapability: CapabilityDescriptor | null;
  capabilityPreview: CapabilityPreview | null;
  workflows: WorkflowDefinition[];
  selectedWorkflow: WorkflowDefinition | null;
  benchmarkScenarios: BenchmarkScenario[];
  selectedScenarioId: string;
  benchmarkRun: BenchmarkRun | null;
  benchmarkBusy: boolean;
  llmConfig: LLMConfig;
  llmReady: boolean;
  summary: ProjectSummary | null;
  setCapabilityCategory(value: string): void;
  setCapabilityQuery(value: string): void;
  setSelectedCapabilityName(value: string): void;
  setCapabilityPreview(value: CapabilityPreview | null): void;
  setSelectedWorkflowId(value: string): void;
  setSelectedScenarioId(value: string): void;
  refreshAgentWorkbench(): Promise<void>;
  previewSelectedCapability(approved?: boolean): Promise<void>;
  runSelectedWorkflow(): Promise<void>;
  runBenchmark(dryRun: boolean): Promise<void>;
};

export function AgentPanel({
  busy,
  capabilityCategory,
  capabilityCategories,
  capabilityQuery,
  filteredCapabilities,
  selectedCapability,
  capabilityPreview,
  workflows,
  selectedWorkflow,
  benchmarkScenarios,
  selectedScenarioId,
  benchmarkRun,
  benchmarkBusy,
  llmConfig,
  llmReady,
  summary,
  setCapabilityCategory,
  setCapabilityQuery,
  setSelectedCapabilityName,
  setCapabilityPreview,
  setSelectedWorkflowId,
  setSelectedScenarioId,
  refreshAgentWorkbench,
  previewSelectedCapability,
  runSelectedWorkflow,
  runBenchmark,
}: AgentPanelProps) {
  return (
    <>
      <section className="card agent-workbench-card">
              <div className="section-heading">
                <div>
                  <h2>Capability Browser</h2>
                  <p>统一查看 runtime、MCP、.aieng 包工具和 benchmark 能力，先看副作用，再决定是否进入流程。</p>
                </div>
                <button className="ghost-button" type="button" disabled={busy} onClick={() => void refreshAgentWorkbench()}>
                  <ActionIcon name="refresh" />
                  刷新能力
                </button>
              </div>

              <div className="capability-toolbar">
                <select value={capabilityCategory} onChange={(event) => setCapabilityCategory(event.target.value)}>
                  {capabilityCategories.map((category) => (
                    <option key={category} value={category}>
                      {category === "all" ? "all categories" : category}
                    </option>
                  ))}
                </select>
                <input
                  value={capabilityQuery}
                  onChange={(event) => setCapabilityQuery(event.target.value)}
                  placeholder="搜索 tool / source / purpose"
                />
              </div>

              <div className="capability-browser">
                <div className="capability-list">
                  {filteredCapabilities.slice(0, 40).map((capability) => (
                    <button
                      type="button"
                      key={`${capability.source}-${capability.name}`}
                      className={capability.name === selectedCapability?.name ? "capability-item active" : "capability-item"}
                      onClick={() => {
                        setSelectedCapabilityName(capability.name);
                        setCapabilityPreview(null);
                      }}
                    >
                      <strong>{capability.name}</strong>
                      <span>{capability.category} / {capability.source}</span>
                    </button>
                  ))}
                </div>

                <div className="capability-detail">
                  {selectedCapability ? (
                    <>
                      <div className="capability-detail-head">
                        <div>
                          <strong>{selectedCapability.name}</strong>
                          <span>{selectedCapability.purpose}</span>
                        </div>
                        <small className={selectedCapability.available ? "capability-available" : "capability-missing"}>
                          {selectedCapability.available ? "available" : "unavailable"}
                        </small>
                      </div>
                      <div className="capability-facts">
                        <div><span>Mutability</span><strong>{mutabilityLabel(selectedCapability)}</strong></div>
                        <div><span>Dry-run</span><strong>{selectedCapability.dry_run_support}</strong></div>
                        <div><span>Runtime</span><strong>{selectedCapability.runtime_requirements.join(", ") || "none"}</strong></div>
                        <div><span>Inputs</span><strong>{selectedCapability.required_inputs.length} required</strong></div>
                      </div>
                      {selectedCapability.unavailable_reason ? (
                        <div className="summary-note summary-muted">
                          <strong>Capability gap</strong>
                          <p>{selectedCapability.unavailable_reason}</p>
                        </div>
                      ) : null}
                      {selectedCapability.side_effects.length ? (
                        <div className="side-effect-list">
                          {selectedCapability.side_effects.map((effect) => (
                            <span key={effect}>{effect}</span>
                          ))}
                        </div>
                      ) : null}
                      <div className="action-row">
                        <button disabled={busy} onClick={() => void previewSelectedCapability(false)}>
                          <ActionIcon name="preview" />
                          Preview
                        </button>
                        <button className="ghost-button" disabled={busy} onClick={() => void previewSelectedCapability(true)}>
                          <ActionIcon name="validate" />
                          Preview as approved
                        </button>
                      </div>
                      {capabilityPreview ? (
                        <JsonDisclosure title="查看 capability preview" body={jsonBlock(capabilityPreview)} defaultOpen />
                      ) : null}
                    </>
                  ) : (
                    <div className="summary-note summary-muted">
                      <strong>暂无能力</strong>
                      <p>后端未返回 capability registry。请检查 aieng 和 freecad-mcp 路径配置。</p>
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>Agent Flow Panel</h2>
                  <p>把一组工具、LLM、benchmark、审批和 artifact 步骤作为可审计 workflow 运行。</p>
                </div>
              </div>

              <label className="form-field">
                <span>Workflow</span>
                <select value={selectedWorkflow?.id ?? ""} onChange={(event) => setSelectedWorkflowId(event.target.value)}>
                  {workflows.map((workflow) => (
                    <option key={workflow.id} value={workflow.id}>
                      {workflow.title}
                    </option>
                  ))}
                </select>
              </label>

              {selectedWorkflow ? (
                <>
                  <div className="summary-note summary-muted">
                    <strong>{selectedWorkflow.title}</strong>
                    <p>{selectedWorkflow.description}</p>
                  </div>
                  <div className="workflow-step-list">
                    {selectedWorkflow.steps.map((step) => (
                      <div key={step.id} className="workflow-step-item">
                        <span>{workflowStepLabel(step.kind)}</span>
                        <strong>{step.tool_name ?? step.id}</strong>
                        {step.approval_required ? <small>approval required</small> : null}
                      </div>
                    ))}
                  </div>
                  <div className="action-row">
                    <button disabled={busy || !selectedWorkflow} onClick={() => void runSelectedWorkflow()}>
                      <ActionIcon name="run" />
                      运行选中工作流
                    </button>
                  </div>
                </>
              ) : (
                <div className="summary-note summary-muted">
                  <strong>暂无 workflow</strong>
                  <p>后端未返回工作流定义。</p>
                </div>
              )}
            </section>

            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>Benchmark Panel</h2>
                  <p>复用环境设置中的同一份 Provider 配置，支持 dry-run 估算和真实 LLM A/B 运行。</p>
                </div>
              </div>

              <div className="runtime-config-grid">
                <label className="form-field">
                  <span>Scenario</span>
                  <select value={selectedScenarioId} onChange={(event) => setSelectedScenarioId(event.target.value)}>
                    {benchmarkScenarios.map((scenario) => (
                      <option key={scenario.id} value={scenario.id}>
                        {scenario.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="summary-note summary-muted llm-inline-note runtime-config-span">
                  <strong>{getLlmProviderLabel(llmConfig.provider)} / {llmConfig.model}</strong>
                  <p>{llmReady ? "Benchmark 会直接复用当前 LLM Provider 配置。" : "当前 Provider 配置不完整，benchmark 可能无法走真实 LLM 路径。"}</p>
                </div>
              </div>

              <div className="action-row runtime-config-actions">
                <button disabled={benchmarkBusy || !selectedScenarioId} onClick={() => void runBenchmark(true)}>
                  <ActionIcon name="test" />
                  Dry-run / 成本估算
                </button>
                <button className="ghost-button" disabled={benchmarkBusy || !selectedScenarioId} onClick={() => void runBenchmark(false)}>
                  <ActionIcon name="run" />
                  真实运行 benchmark
                </button>
              </div>

              {benchmarkRun ? (
                <div className="benchmark-result">
                  <div className="capability-facts">
                    <div><span>Run</span><strong>{benchmarkRun.run_id}</strong></div>
                    <div><span>Status</span><strong>{benchmarkRun.status}</strong></div>
                    <div><span>Mode</span><strong>{benchmarkRun.dry_run ? "dry-run" : "run"}</strong></div>
                    <div><span>Result</span><strong>{benchmarkRun.result_path ?? "-"}</strong></div>
                  </div>
                  {benchmarkRun.warnings.length ? (
                    <div className="side-effect-list">
                      {benchmarkRun.warnings.map((warning) => <span key={warning}>{warning}</span>)}
                    </div>
                  ) : null}
                  <JsonDisclosure title="查看 benchmark run payload" body={jsonBlock(benchmarkRun)} />
                </div>
              ) : null}
            </section>

            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>Semantic Map</h2>
                  <p>把 .aieng 资源按可用、缺失和证据链状态压缩成一个扫描视图。</p>
                </div>
              </div>
              <div className="semantic-map-grid">
                {[
                  ["manifest", Boolean(summary?.manifest)],
                  ["feature_graph", Boolean(summary?.feature_graph)],
                  ["topology", Boolean(summary?.topology)],
                  ["constraints", Boolean(summary?.constraints)],
                  ["validation", Boolean(summary?.validation)],
                  ["ai_summary", Boolean(summary?.ai_summary)],
                  ["cae_context", Boolean(summary?.cae?.present)],
                  ["result_summary", Boolean(summary?.cae?.result_summary)],
                ].map(([label, present]) => (
                  <div key={String(label)} className={present ? "semantic-map-item present" : "semantic-map-item missing"}>
                    <span>{String(label)}</span>
                    <strong>{present ? "present" : "missing"}</strong>
                  </div>
                ))}
              </div>
            </section>
    </>
  );
}
