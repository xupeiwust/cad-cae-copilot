import type { SelectedGeometryContext } from "./appTypes";
import type { AgentPlan, AgentRunResponse, ArtifactDiffResponse, ArtifactResponse, AutopilotRunState, BenchmarkRun, BenchmarkScenario, CadRecommendationsResponse, CaeArtifactDetection, CaePreprocessingSummary, CaeReviewReport, CaeSimulationRunSummary, CapabilityDescriptor, CapabilityPreview, ChatConnection, ChatResponse, ComputedMetricsDocument, ComputedMetricsImportPayload, ComputedMetricsResponse, CopilotLoop, CopilotLoopDemoSeedResponse, CopilotLoopDemoSmokeCheckResponse, CopilotLoopExportRequest, CopilotLoopExportResponse, CopilotLoopList, CopilotLoopReport, CopilotLoopReportDiff, DesignTarget, DesignTargetsDocument, DesignTargetsResponse, EngineeringTemplateAdoptTargetsResponse, EngineeringTemplateCadFixtureResponse, EngineeringTemplateDetail, EngineeringTemplatePreviewResponse, EngineeringTemplateSaveDraftResponse, EngineeringTemplateSummary, FreeCadAdapterPreflightResponse, FreeCadEditParameterRequest, FreeCadEditParameterResponse, FreeCadInspectionEvidenceResponse, FreeCadInspectFeaturesRequest, FreeCadInspectFeaturesResponse, IntentActionExecuteResponse, IntentObserveResponse, IntentPlan, LLMConfig, LocalAgentCapability, ProjectHealthCheckResponse, ProjectRecord, ProjectSummary, ReviewSupportPacketResponse, RuntimeConfig, RuntimeConfigSnapshot, RuntimeEvent, RuntimeRun, RuntimeRunSummary, RuntimeToolInfo, SolverFieldDescriptor, StructuralAdapterPreflightResponse, StructuralPreparePreviewResponse, StructuralSolverInputImportResponse, TargetComparisonResponse, WorkflowDefinition, WorkflowStep } from "./types";

const API = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type PersistedChatMessage = {
  id: number;
  session_id?: string | null;
  project_id: string;
  role: string;
  content: string;
  mode?: string | null;
  created_at: string;
  extra?: Record<string, unknown> | null;
};

export type ChatSession = {
  id: string;
  project_id: string;
  title: string;
  status: string;
  active_run_id?: string | null;
  created_at: string;
  updated_at: string;
};

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const timeoutMs = init?.timeoutMs ?? 30000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API}${path}`, {
      headers: {
        ...(init?.headers ?? {}),
      },
      ...init,
      signal: controller.signal,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    return response.json() as Promise<T>;
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  base: API,
  runtime: () => request<RuntimeConfigSnapshot>("/api/runtime"),
  getRuntimeConfig: () => request<RuntimeConfigSnapshot>("/api/runtime-config"),
  updateRuntimeConfig: (payload: RuntimeConfig) =>
    request<RuntimeConfigSnapshot>("/api/runtime-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  testRuntimeConfig: (payload: RuntimeConfig) =>
    request<RuntimeConfigSnapshot>("/api/runtime-config/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getSettings: () => request<Record<string, unknown>>("/api/settings"),
  getSetting: (key: string) =>
    request<{ key: string; value: unknown }>(`/api/settings/${encodeURIComponent(key)}`),
  updateSetting: (key: string, value: unknown) =>
    request<{ key: string; value: unknown; updated_at: string }>(`/api/settings/${encodeURIComponent(key)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    }),
  deleteSetting: (key: string) =>
    request<{ deleted: boolean; key: string }>(`/api/settings/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),
  testLlmProvider: (config: LLMConfig, verifyConnection: boolean) =>
    request<{
      config_ready: boolean;
      connection_verified: boolean;
      provider: string;
      model: string;
      base_url?: string | null;
      api_key_present: boolean;
      error_message: string | null;
    }>("/api/llm/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm_config: config, verify_connection: verifyConnection }),
    }),
  listCapabilities: () => request<CapabilityDescriptor[]>("/api/capabilities"),
  previewCapability: (operationName: string, inputs: Record<string, unknown> = {}, approved = false) =>
    request<CapabilityPreview>("/api/capabilities/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation_name: operationName, inputs, approved }),
    }),
  listWorkflows: () => request<WorkflowDefinition[]>("/api/runtime/workflows"),
  planAgent: (payload: {
    message: string;
    project_id?: string | null;
    llm_config?: LLMConfig;
    patch_json?: Record<string, unknown> | null;
    dry_run?: boolean;
    selected_geometry?: SelectedGeometryContext | null;
  }) =>
    request<AgentPlan>("/api/agent/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  runAgent: (payload: {
    message?: string;
    project_id?: string | null;
    llm_config?: LLMConfig;
    patch_json?: Record<string, unknown> | null;
    dry_run?: boolean;
    selected_geometry?: SelectedGeometryContext | null;
    plan?: AgentPlan;
  }) =>
    request<AgentRunResponse>("/api/agent/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listAgentConnections: () => request<ChatConnection[]>("/api/agent/connections"),
  listLocalAgentCapabilities: () =>
    request<{ adapters: LocalAgentCapability[]; available: LocalAgentCapability[] }>("/api/local-agents/capabilities"),
  runAutopilot: (payload: {
    message: string;
    project_id?: string | null;
    session_id?: string | null;
    adapter_id?: string;
    selected_geometry?: SelectedGeometryContext | null;
    llm_config?: LLMConfig;
    mode?: "assist" | "autopilot" | "full_agent";
    dry_run?: boolean;
  }) =>
    request<AutopilotRunState>("/api/agent/autopilot/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      timeoutMs: 300000,
    }),
  continueAutopilot: (runId: string, approved: boolean, userMessage?: string | null) =>
    request<AutopilotRunState>(`/api/agent/autopilot/runs/${runId}/continue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved, user_message: userMessage ?? undefined }),
      timeoutMs: 300000,
    }),
  getAutopilotRun: (runId: string) =>
    request<AutopilotRunState>(`/api/agent/autopilot/runs/${runId}`),
  cancelAutopilot: (runId: string) =>
    request<AutopilotRunState>(`/api/agent/autopilot/runs/${runId}/cancel`, {
      method: "POST",
    }),
  planIntent: (payload: { message: string; project_id?: string | null }) =>
    request<IntentPlan>("/api/intent-planner/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  executeIntentAction: (actionId: string, plan: IntentPlan) =>
    request<IntentActionExecuteResponse>(`/api/intent-planner/actions/${actionId}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    }),
  observeIntentAction: (payload: { plan: IntentPlan; action_id: string; run_id: string }) =>
    request<IntentObserveResponse>(`/api/intent-planner/observe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listBenchmarkScenarios: () => request<BenchmarkScenario[]>("/api/benchmarks/scenarios"),
  startBenchmarkRun: (payload: {
    scenario_id: string;
    condition?: string;
    dry_run?: boolean;
    llm_config: LLMConfig;
  }) =>
    request<BenchmarkRun>("/api/benchmarks/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getBenchmarkRun: (runId: string) => request<BenchmarkRun>(`/api/benchmarks/runs/${runId}`),
  listProjects: () => request<ProjectRecord[]>("/api/projects"),
  createProject: (name: string) =>
    request<ProjectRecord>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  createSampleProject: () => request<ProjectRecord>("/api/projects/sample", { method: "POST" }),
  getProject: (projectId: string) => request<ProjectSummary>(`/api/projects/${projectId}`),
  getProjectHealthCheck: (projectId: string) =>
    request<ProjectHealthCheckResponse>(`/api/projects/${projectId}/health-check`),
  getFreeCadAdapterPreflight: () =>
    request<FreeCadAdapterPreflightResponse>(`/api/adapters/freecad/preflight`),
  getStructuralAdapterPreflight: () =>
    request<StructuralAdapterPreflightResponse>(`/api/adapters/structural/preflight`),
  importStructuralSolverInput: (projectId: string, payload: { text: string; run_id?: string; overwrite?: boolean }) =>
    request<StructuralSolverInputImportResponse>(`/api/projects/${projectId}/solver-input`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getStructuralPreparePreview: (projectId: string, payload: { run_id?: string; load_case_id?: string; extract_results?: boolean; refresh_summary?: boolean } = {}) =>
    request<StructuralPreparePreviewResponse>(`/api/projects/${projectId}/structural/prepare-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listEngineeringTemplates: () =>
    request<{ schema_version: string; templates: EngineeringTemplateSummary[]; claim_advancement: "none"; claim_boundary: string }>(
      `/api/engineering-templates`,
    ),
  getEngineeringTemplate: (templateId: string) =>
    request<EngineeringTemplateDetail>(`/api/engineering-templates/${templateId}`),
  previewEngineeringTemplate: (projectId: string, templateId: string, parameters: Record<string, unknown>) =>
    request<EngineeringTemplatePreviewResponse>(
      `/api/projects/${projectId}/engineering-templates/${templateId}/preview`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parameters }),
      },
    ),
  saveEngineeringTemplateDraft: (projectId: string, templateId: string, parameters: Record<string, unknown>) =>
    request<EngineeringTemplateSaveDraftResponse>(
      `/api/projects/${projectId}/engineering-templates/${templateId}/save-draft`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parameters }),
      },
    ),
  adoptEngineeringTemplateTargets: (projectId: string, templateId: string, suggestions?: unknown[]) =>
    request<EngineeringTemplateAdoptTargetsResponse>(
      `/api/projects/${projectId}/engineering-templates/${templateId}/adopt-targets`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(suggestions ? { suggestions } : {}),
      },
    ),
  generateEngineeringTemplateCadFixture: (projectId: string, templateId: string, parameters?: Record<string, unknown>) =>
    request<EngineeringTemplateCadFixtureResponse>(
      `/api/projects/${projectId}/engineering-templates/${templateId}/generate-cad-fixture`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved: true, ...(parameters ? { parameters } : {}) }),
      },
    ),
  getReviewSupportPacketPreview: (projectId: string) =>
    request<ReviewSupportPacketResponse>(`/api/projects/${projectId}/review-support-packet/preview`),
  exportReviewSupportPacket: (projectId: string, payload: { packet_id?: string; include_preview_markdown?: boolean } = {}) =>
    request<ReviewSupportPacketResponse>(`/api/projects/${projectId}/review-support-packet/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getFreeCadInspectionEvidence: (projectId: string) =>
    request<FreeCadInspectionEvidenceResponse>(`/api/projects/${projectId}/freecad/inspection-evidence`),
  inspectFreeCadFeatures: (projectId: string, payload: FreeCadInspectFeaturesRequest = {}) =>
    request<FreeCadInspectFeaturesResponse>(
      `/api/projects/${projectId}/freecad/inspect-features`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),
  editFreeCadParameter: (projectId: string, payload: FreeCadEditParameterRequest) =>
    request<FreeCadEditParameterResponse>(`/api/projects/${projectId}/freecad/edit-parameter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getDesignTargets: (projectId: string) =>
    request<DesignTargetsResponse>(`/api/projects/${projectId}/design-targets`),
  saveDesignTargets: (projectId: string, payload: DesignTargetsDocument | DesignTarget[]) =>
    request<DesignTargetsResponse>(`/api/projects/${projectId}/design-targets`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getComputedMetrics: (projectId: string) =>
    request<ComputedMetricsResponse>(`/api/projects/${projectId}/computed-metrics`),
  getTargetComparison: (projectId: string) =>
    request<TargetComparisonResponse>(`/api/projects/${projectId}/target-comparison`),
  previewComputedMetrics: (projectId: string, payload: ComputedMetricsImportPayload) =>
    request<ComputedMetricsResponse>(`/api/projects/${projectId}/computed-metrics/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  saveComputedMetrics: (projectId: string, payload: ComputedMetricsImportPayload | ComputedMetricsDocument) =>
    request<ComputedMetricsResponse>(`/api/projects/${projectId}/computed-metrics`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  uploadFile: async (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ProjectRecord>(`/api/projects/${projectId}/upload`, {
      method: "POST",
      body: form,
    });
  },
  importAieng: (projectId: string) => request(`/api/projects/${projectId}/import-aieng`, { method: "POST" }),
  validate: (projectId: string) => request(`/api/projects/${projectId}/validate`, { method: "POST" }),
  convert: (projectId: string) => request(`/api/projects/${projectId}/convert`, { method: "POST" }),
  chat: (projectId: string, message: string, execute: boolean, sessionId?: string | null) =>
    request<ChatResponse>(`/api/projects/${projectId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, execute, ...(sessionId ? { session_id: sessionId } : {}) }),
    }),
  getFieldDescriptor: (projectId: string, fieldName: string) =>
    request<SolverFieldDescriptor>(`/api/projects/${projectId}/fields/${fieldName}`),
  listRuns: () => request<RuntimeRunSummary[]>("/api/runtime/runs"),
  startRun: (message: string, projectId?: string | null, toolInput?: Record<string, unknown> | null, extras?: { workflow_id?: string; steps?: WorkflowStep[]; llm_config?: LLMConfig }) =>
    request<RuntimeRun>("/api/runtime/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        project_id: projectId ?? null,
        ...(toolInput ? { tool_input: toolInput } : {}),
        ...(extras?.workflow_id ? { workflow_id: extras.workflow_id } : {}),
        ...(extras?.steps ? { steps: extras.steps } : {}),
        ...(extras?.llm_config ? { llm_config: extras.llm_config } : {}),
      }),
    }),
  getRun: (runId: string) => request<RuntimeRun>(`/api/runtime/runs/${runId}`),
  getRunEvents: (runId: string) => request<RuntimeEvent[]>(`/api/runtime/runs/${runId}/events`),
  approveRun: (runId: string) =>
    request<RuntimeRun>(`/api/runtime/runs/${runId}/approve`, { method: "POST" }),
  rejectRun: (runId: string) =>
    request<RuntimeRun>(`/api/runtime/runs/${runId}/reject`, { method: "POST" }),
  listTools: () => request<RuntimeToolInfo[]>("/api/runtime/tools"),
  getCaeArtifacts: (projectId: string) =>
    request<CaeArtifactDetection>(`/api/projects/${projectId}/cae-artifacts`),
  getCaePreprocessingSummary: (projectId: string) =>
    request<CaePreprocessingSummary>(`/api/projects/${projectId}/cae-preprocessing-summary`),
  getCaeSimulationRunSummary: (projectId: string) =>
    request<CaeSimulationRunSummary>(`/api/projects/${projectId}/cae-simulation-run-summary`),
  getCaeReviewReport: (projectId: string) =>
    request<CaeReviewReport>(`/api/projects/${projectId}/cae-review-report`),
  getCadRecommendations: (projectId: string, strictness: "lenient" | "default" | "strict" = "default") =>
    request<CadRecommendationsResponse>(
      `/api/projects/${projectId}/cad-recommendations?strictness=${strictness}`,
    ),
  startCopilotLoop: (projectId: string, payload: Record<string, unknown> = {}) =>
    request<CopilotLoop>(`/api/projects/${projectId}/copilot-loop/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listCopilotLoops: (projectId: string) =>
    request<CopilotLoopList>(`/api/projects/${projectId}/copilot-loops`),
  compareCopilotLoopReports: (projectId: string, leftLoopId: string, rightLoopId: string) =>
    request<CopilotLoopReportDiff>(
      `/api/projects/${projectId}/copilot-loops/compare-reports?left=${encodeURIComponent(leftLoopId)}&right=${encodeURIComponent(rightLoopId)}`,
    ),
  exportCopilotLoopReview: (projectId: string, payload: CopilotLoopExportRequest) =>
    request<CopilotLoopExportResponse>(
      `/api/projects/${projectId}/copilot-loops/export-review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),
  seedCopilotLoopDemo: (payload: { name?: string; reset?: boolean } = {}) =>
    request<CopilotLoopDemoSeedResponse>(`/api/demo/copilot-loop/seed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  resetCopilotLoopDemo: () =>
    request<{ removed: Array<{ project_id: string; name?: string }>; notice: string }>(
      `/api/demo/copilot-loop/reset`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    ),
  runCopilotLoopDemoSmokeCheck: (payload: { reset?: boolean } = {}) =>
    request<CopilotLoopDemoSmokeCheckResponse>(`/api/demo/copilot-loop/smoke-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getCopilotLoop: (projectId: string, loopId: string) =>
    request<CopilotLoop>(`/api/projects/${projectId}/copilot-loop/${loopId}`),
  advanceCopilotLoop: (projectId: string, loopId: string) =>
    request<CopilotLoop>(`/api/projects/${projectId}/copilot-loop/${loopId}/advance`, { method: "POST" }),
  approveCopilotLoop: (projectId: string, loopId: string) =>
    request<CopilotLoop>(`/api/projects/${projectId}/copilot-loop/${loopId}/approve`, { method: "POST" }),
  rejectCopilotLoop: (projectId: string, loopId: string) =>
    request<CopilotLoop>(`/api/projects/${projectId}/copilot-loop/${loopId}/reject`, { method: "POST" }),
  getCopilotLoopReport: (projectId: string, loopId: string) =>
    request<CopilotLoopReport>(`/api/projects/${projectId}/copilot-loop/${loopId}/report`),
  generateCad: (projectId: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/generate-cad`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  generateCadStream: async (projectId: string, body: Record<string, unknown>): Promise<Response> => {
    const response = await fetch(`${API}/api/projects/${projectId}/generate-cad-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response;
  },
  refineCad: (projectId: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/refine-cad`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  aiPreprocessing: (projectId: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/ai-preprocessing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  engineeringActionPlan: (projectId: string, message: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/engineering-action-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  pickFace: (projectId: string, x: number, y: number, z: number) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/brep/pick-face`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x, y, z }),
    }),
  getBrepGraph: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/brep-graph`),
  buildBrepGraph: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/brep-graph/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
  runSimulation: (projectId: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/run-simulation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  runSimulationStream: async (projectId: string, body: Record<string, unknown>): Promise<Response> => {
    const response = await fetch(`${API}/api/projects/${projectId}/run-simulation-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response;
  },
  getSimulationTools: () =>
    request<Record<string, unknown>>("/api/simulation/tools"),
  chatSetTarget: (projectId: string, message: string) =>
    request<{
      ok: boolean;
      target: {
        target_id: string; label: string; metric: string;
        operator: string; value: number; unit: string;
      };
      action: "added" | "updated";
      total_targets: number;
    }>(`/api/projects/${projectId}/chat-set-target`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  contextualChat: (
    projectId: string,
    message: string,
    history: Array<{ role: string; content: string }>,
    apiKey?: string,
    sessionId?: string | null,
  ) =>
    request<{ reply: string; context_used: boolean; project_id: string }>(
      `/api/projects/${projectId}/contextual-chat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history, ...(apiKey ? { api_key: apiKey } : {}), ...(sessionId ? { session_id: sessionId } : {}) }),
      },
    ),
  getChatSessions: (projectId: string) =>
    request<ChatSession[]>(`/api/projects/${projectId}/chat-sessions`),
  createChatSession: (projectId: string, title?: string) =>
    request<ChatSession>(`/api/projects/${projectId}/chat-sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  updateChatSession: (
    projectId: string,
    sessionId: string,
    payload: { title?: string; status?: string; active_run_id?: string | null },
  ) =>
    request<ChatSession>(`/api/projects/${projectId}/chat-sessions/${sessionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteChatSession: (projectId: string, sessionId: string) =>
    request<{ deleted: boolean; project_id: string; session_id: string }>(
      `/api/projects/${projectId}/chat-sessions/${sessionId}`,
      { method: "DELETE" },
    ),
  getChatMessages: (projectId: string, sessionId?: string | null) =>
    request<PersistedChatMessage[]>(
      `/api/projects/${projectId}/chat-messages${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`,
    ),
  saveChatMessage: (
    projectId: string,
    payload: {
      role: string;
      content: string;
      session_id?: string | null;
      mode?: string;
      created_at?: string;
      extra?: Record<string, unknown>;
    },
  ) =>
    request<PersistedChatMessage>(
      `/api/projects/${projectId}/chat-messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),
  clearChatMessages: (projectId: string, sessionId?: string | null) =>
    request<{ deleted: number; project_id: string }>(`/api/projects/${projectId}/chat-messages${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`, {
      method: "DELETE",
    }),
  getProjectArtifact: (projectId: string, path: string) =>
    request<ArtifactResponse>(`/api/projects/${projectId}/artifact?path=${encodeURIComponent(path)}`),
  diffArtifactJson: (projectId: string, before: unknown, after: unknown) =>
    request<ArtifactDiffResponse>(`/api/projects/${projectId}/artifact/diff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ before, after }),
    }),
};
