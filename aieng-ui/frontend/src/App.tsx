import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import {
  AI_FIRST_WORKBENCH_ENABLED,
  BASE_STAGES,
  CONTROL_PANE_MODES,
  DEFAULT_CHAT_CONNECTIONS,
  DEFAULT_LLM_CONFIG,
  DEFAULT_LOCAL_AGENT_CONFIG,
  EMPTY_CAE_FIELDS,
  LLM_CONFIG_STORAGE_KEY,
  LOCAL_AGENT_CONFIG_STORAGE_KEY,
  WORKBENCH_PANE_MODES,
} from "./appConstants";
import type { BrepGraphSnapshot, CadGenerationProgress, ChatHistoryItem, ControlPaneMode, Notice, PickedFace, SelectedGeometryContext, StageItem, StageState, WorkbenchPaneMode } from "./appTypes";
import type { PointerToken } from "./components/PointerText";
import type { AgentActivityEvent } from "./appUtils";
import {
  createChatId,
  extractArtifactPaths,
  formatArtifactChanges,
  formatGeometryResult,
  getProviderLabel,
  getRuntimeDetail,
  isLlmConfigReady,
  jsonBlock,
  applyAgentActivityEvent,
  applyCadProgressEvent,
  emptyCadGenerationProgress,
  normalizeLlmConfig,
  parseBrepGraphSnapshot,
  projectViewerUrl,
  redactSecrets,
  resolveAssetFormat,
  runtimeRunToChatPlan,
  runtimeStatusLabel,
  summarizeAssistantReply,
  withAssetVersion,
} from "./appUtils";
import { NoticeCenter } from "./components/common";
import { PointerProvider } from "./components/PointerText";
import { ViewerPane } from "./components/ViewerPane";
import { WorkbenchRightRail, type WorkbenchRightRailModeId } from "./components/WorkbenchRightRail";
import { SelectionInspectorCard } from "./components/agent/SelectionInspectorCard";
import { AgentPanel } from "./components/panels/AgentPanel";
import { CaePanel } from "./components/panels/CaePanel";
import { ChatPanel } from "./components/panels/ChatPanel";
import { CopilotLoopPanel } from "./components/panels/CopilotLoopPanel";
import { DebugPanel } from "./components/panels/DebugPanel";
import { IntentPlannerCard } from "./components/panels/IntentPlannerCard";
import { ProjectPanel } from "./components/panels/ProjectPanel";
import { RecommendationsPanel } from "./components/panels/RecommendationsPanel";
import { GlobalSettingsDrawer, RuntimeSettingsDrawer } from "./components/settings/RuntimeSettingsDrawer";
import type {
  AgentPlan,
  AutopilotRunState,
  ArtifactDiff,
  ArtifactResponse,
  BenchmarkRun,
  BenchmarkScenario,
  CapabilityDescriptor,
  CapabilityPreview,
  ChatConnection,
  ChatResponse,
  CaeReviewReport,
  LLMConfig,
  LocalAgentCapability,
  LocalAgentConfig,
  ProjectRecord,
  ProjectSummary,
  RuntimeConfig,
  RuntimeConfigSnapshot,
  RuntimeRun,
  SolverFieldDescriptor,
  WorkflowDefinition,
} from "./types";

type EngineeringChatIntent =
  | "generate"
  | "refine"
  | "preprocess"
  | "simulate"
  | "change_material"
  | "refine_mesh"
  | "set_target";

function mergeLocalAgentCapabilities(
  connections: ChatConnection[],
  capabilities: ChatConnection["adapters"] | undefined,
): ChatConnection[] {
  if (!capabilities) return connections;
  const available = capabilities.filter((item) => item.status === "available");
  return connections.map((connection) => (
    connection.id === "local-agent"
      ? {
          ...connection,
          status: available.length ? "ready" : "blocked",
          adapters: capabilities,
          detail: available.length
            ? `Available adapters: ${available.map((item) => item.label).join(", ")}.`
            : capabilities[0]?.diagnostic || connection.detail,
        }
      : connection
  ));
}

function summarizeAutopilotRun(run: AutopilotRunState): string {
  const agentLabel = run.adapter_id === "llm-api" ? "LLM Agent" : "Local Agent";
  if (run.status === "awaiting_approval" && run.pending_approval) {
    return `${agentLabel} paused for approval: ${run.pending_approval.tool_name}. ${run.pending_approval.explanation}`;
  }
  if (run.final_message) return run.final_message;
  const latest = run.observations[run.observations.length - 1];
  if (latest?.summary) return latest.summary;
  if (run.errors.length) return run.errors[0];
  return `${agentLabel} run ${run.status}.`;
}

function autopilotAgentLabel(run?: AutopilotRunState | null): string {
  return run?.adapter_id === "llm-api" ? "LLM Agent" : "Local Agent";
}

export default function App() {
  const [runtime, setRuntime] = useState<RuntimeConfigSnapshot | null>(null);
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeConfig | null>(null);
  const [runtimeNotice, setRuntimeNotice] = useState<Notice | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [projectName, setProjectName] = useState("STEP workbench project");
  const [message, setMessage] = useState("Check the current project status and generate a reviewable engineering execution plan.");
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [stages, setStages] = useState<StageItem[]>(BASE_STAGES);
  const [selectedCaeField, setSelectedCaeField] = useState("stress");
  const [fieldDescriptor, setFieldDescriptor] = useState<SolverFieldDescriptor | null>(null);
  const [lastRuntimeRun, setLastRuntimeRun] = useState<RuntimeRun | null>(null);
  const [caeRefreshing, setCaeRefreshing] = useState(false);
  const [caeReviewReport, setCaeReviewReport] = useState<CaeReviewReport | null>(null);
  const [caeReviewLoading, setCaeReviewLoading] = useState(false);
  const [metricsInputPath, setMetricsInputPath] = useState("");
  const [metricsLoadCaseId, setMetricsLoadCaseId] = useState("load_case_001");
  const [metricsSoftware, setMetricsSoftware] = useState("");
  const [metricsImporting, setMetricsImporting] = useState(false);
  const [frdInputPath, setFrdInputPath] = useState("");
  const [frdLoadCaseId, setFrdLoadCaseId] = useState("load_case_001");
  const [frdSoftware, setFrdSoftware] = useState("CalculiX");
  const [frdExtracting, setFrdExtracting] = useState(false);
  const [capabilities, setCapabilities] = useState<CapabilityDescriptor[]>([]);
  const [capabilityCategory, setCapabilityCategory] = useState("all");
  const [capabilityQuery, setCapabilityQuery] = useState("");
  const [selectedCapabilityName, setSelectedCapabilityName] = useState<string>("");
  const [capabilityPreview, setCapabilityPreview] = useState<CapabilityPreview | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [benchmarkScenarios, setBenchmarkScenarios] = useState<BenchmarkScenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [benchmarkRun, setBenchmarkRun] = useState<BenchmarkRun | null>(null);
  const [benchmarkBusy, setBenchmarkBusy] = useState(false);
  const [llmConfig, setLlmConfig] = useState<LLMConfig>(DEFAULT_LLM_CONFIG);
  const [localAgentConfig, setLocalAgentConfig] = useState<LocalAgentConfig>(DEFAULT_LOCAL_AGENT_CONFIG);
  const [chatConnections, setChatConnections] = useState<ChatConnection[]>(DEFAULT_CHAT_CONNECTIONS);
  const [selectedChatConnectionId, setSelectedChatConnectionId] = useState<string>("llm-api");
  const [controlPaneMode, setControlPaneMode] = useState<ControlPaneMode>("chat");
  const [workbenchPaneMode, setWorkbenchPaneMode] = useState<WorkbenchPaneMode>("agent");
  const [agentPlan, setAgentPlan] = useState<AgentPlan | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [artifactViewerPath, setArtifactViewerPath] = useState("");
  const [artifactViewerData, setArtifactViewerData] = useState<ArtifactResponse | null>(null);
  const [artifactViewerBusy, setArtifactViewerBusy] = useState(false);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const sidePaneRef = useRef<HTMLElement | null>(null);
  const autopilotPollTimerRef = useRef<number | null>(null);
  const [cadPreviewUrl, setCadPreviewUrl] = useState<string | null>(null);
  const [cadPreviewFormat, setCadPreviewFormat] = useState<string | null>(null);
  const [cadGenerating, setCadGenerating] = useState(false);
  const [cadGenResult, setCadGenResult] = useState<{ code: string; face_count: number; feature_count: number } | null>(null);
  const [cadGenerationProgress, setCadGenerationProgress] = useState<CadGenerationProgress | null>(null);
  const [simulationPending, setSimulationPending] = useState(false);
  const [simulationProgress, setSimulationProgress] = useState<{ step: string; message: string } | null>(null);
  const [heatmapActive, setHeatmapActive] = useState(false);
  const [heatmapRange, setHeatmapRange] = useState<{ min: number; max: number } | null>(null);
  const [pickedFaces, setPickedFaces] = useState<PickedFace[]>([]);
  const [highlightedFaceIds, setHighlightedFaceIds] = useState<Set<string>>(() => new Set());
  const [brepSnapshot, setBrepSnapshot] = useState<BrepGraphSnapshot | null>(null);
  const [directApiKey, setDirectApiKey] = useState<string>(() => {
    try { return window.sessionStorage.getItem("aieng_api_key") ?? ""; } catch { return ""; }
  });

  function updateDirectApiKey(key: string) {
    setDirectApiKey(key);
    try {
      if (key) window.sessionStorage.setItem("aieng_api_key", key);
      else window.sessionStorage.removeItem("aieng_api_key");
    } catch { /* ignore */ }
  }

  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedId) ?? null,
    [projects, selectedId],
  );
  const capabilityCategories = useMemo(() => {
    const values = Array.from(new Set(capabilities.map((item) => item.category))).sort();
    return ["all", ...values];
  }, [capabilities]);
  const filteredCapabilities = useMemo(() => {
    const query = capabilityQuery.trim().toLowerCase();
    return capabilities.filter((item) => {
      const categoryOk = capabilityCategory === "all" || item.category === capabilityCategory;
      const queryOk =
        !query ||
        item.name.toLowerCase().includes(query) ||
        item.purpose.toLowerCase().includes(query) ||
        item.source.toLowerCase().includes(query);
      return categoryOk && queryOk;
    });
  }, [capabilities, capabilityCategory, capabilityQuery]);
  const selectedCapability = useMemo(
    () => capabilities.find((item) => item.name === selectedCapabilityName) ?? filteredCapabilities[0] ?? null,
    [capabilities, filteredCapabilities, selectedCapabilityName],
  );
  const selectedWorkflow = useMemo(
    () => workflows.find((item) => item.id === selectedWorkflowId) ?? workflows[0] ?? null,
    [workflows, selectedWorkflowId],
  );
  const fallbackViewerUrl = useMemo(() => projectViewerUrl(selectedProject), [selectedProject]);
  const heatmapUrl = heatmapActive && selectedId ? `/api/projects/${selectedId}/stress-heatmap` : null;
  const rawViewerUrl = heatmapUrl ?? cadPreviewUrl ?? summary?.viewer_url ?? fallbackViewerUrl;
  const viewerVersion = summary?.project?.updated_at ?? selectedProject?.updated_at ?? null;
  const effectiveViewerUrl = useMemo(
    () => heatmapUrl ?? withAssetVersion(rawViewerUrl, viewerVersion),
    [heatmapUrl, rawViewerUrl, viewerVersion],
  );
  const summaryViewerFormat = typeof summary?.viewer?.asset_format === "string" ? summary.viewer.asset_format : null;
  const effectiveViewerFormat = heatmapActive
    ? "glb"
    : (cadPreviewUrl ? cadPreviewFormat : null) ?? resolveAssetFormat(rawViewerUrl, summaryViewerFormat ?? selectedProject?.web_asset_format ?? null);
  const llmReady = useMemo(() => isLlmConfigReady(llmConfig), [llmConfig]);
  const selectedChatConnection = useMemo(
    () => chatConnections.find((item) => item.id === selectedChatConnectionId) ?? chatConnections[0] ?? DEFAULT_CHAT_CONNECTIONS[0],
    [chatConnections, selectedChatConnectionId],
  );
  const selectedConnectionBlocked = selectedChatConnection.requires_project && !selectedId;
  const chatBusy = agentBusy || busy;
  const availableMcpCapabilityCount = useMemo(
    () => capabilities.filter((item) => item.available && String(item.source).toLowerCase().includes("mcp")).length,
    [capabilities],
  );
  const executableMcpToolCount = useMemo(
    () => capabilities.filter((item) => item.available && item.source === "aieng-ui-runtime" && item.name.startsWith("mcp.")).length,
    [capabilities],
  );
  const activeControlPaneModes = AI_FIRST_WORKBENCH_ENABLED
    ? WORKBENCH_PANE_MODES
    : CONTROL_PANE_MODES;
  const activeControlPaneMode = AI_FIRST_WORKBENCH_ENABLED ? workbenchPaneMode : controlPaneMode;
  const activeControlPaneModeDetail =
    activeControlPaneModes.find((mode) => mode.id === activeControlPaneMode)?.detail ??
    CONTROL_PANE_MODES.find((mode) => mode.id === controlPaneMode)?.detail;
  const showAgentWorkbench = AI_FIRST_WORKBENCH_ENABLED && workbenchPaneMode === "agent";
  const showProjectPanel = AI_FIRST_WORKBENCH_ENABLED ? workbenchPaneMode === "project" : controlPaneMode === "project";
  const showDebugPanel = AI_FIRST_WORKBENCH_ENABLED && workbenchPaneMode === "debug";
  const showLegacyAgentPanel = !AI_FIRST_WORKBENCH_ENABLED && controlPaneMode === "agent";
  const showLegacyCaePanel = !AI_FIRST_WORKBENCH_ENABLED && controlPaneMode === "cae";
  const showRecommendationsPanel = !AI_FIRST_WORKBENCH_ENABLED && controlPaneMode === "recommend";
  const showCopilotLoopPanel = !AI_FIRST_WORKBENCH_ENABLED && controlPaneMode === "copilot";
  const showIntentPlannerPanel = !AI_FIRST_WORKBENCH_ENABLED && controlPaneMode === "pilot";
  const showChatPanel = showAgentWorkbench || (!AI_FIRST_WORKBENCH_ENABLED && controlPaneMode === "chat");
  function handleControlPaneModeChange(mode: WorkbenchRightRailModeId) {
    if (AI_FIRST_WORKBENCH_ENABLED) {
      setWorkbenchPaneMode(mode as WorkbenchPaneMode);
      return;
    }
    setControlPaneMode(mode as ControlPaneMode);
  }

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!runtimeNotice) return;
    const timer = window.setTimeout(() => setRuntimeNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [runtimeNotice]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(LLM_CONFIG_STORAGE_KEY);
      if (!raw) return;
      setLlmConfig(normalizeLlmConfig(JSON.parse(raw)));
    } catch {
      // Ignore malformed local cache and keep defaults.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(LLM_CONFIG_STORAGE_KEY, JSON.stringify(llmConfig));
    } catch {
      // Ignore persistence failures in private mode / restricted environments.
    }
  }, [llmConfig]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(LOCAL_AGENT_CONFIG_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<LocalAgentConfig>;
      setLocalAgentConfig({ preferredAdapterId: parsed.preferredAdapterId ?? null });
    } catch {
      // Keep defaults on malformed cache.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(LOCAL_AGENT_CONFIG_STORAGE_KEY, JSON.stringify(localAgentConfig));
    } catch {
      // Ignore persistence failures.
    }
  }, [localAgentConfig]);

  function buildFallbackSummary(project: ProjectRecord, runtimeSnapshot: RuntimeConfigSnapshot | null = runtime): ProjectSummary {
    return {
      project,
      files: {},
      members: [],
      manifest: null,
      feature_graph: null,
      topology: null,
      validation: null,
      viewer: {
        asset_format: project.web_asset_format ?? null,
        asset_path: project.web_asset ?? null,
        asset_exists: Boolean(project.web_asset),
      },
      viewer_url: projectViewerUrl(project),
      ai_summary: null,
      derived: {},
      summary_error: "project summary unavailable; using project metadata fallback",
      summary_mode: "project_fallback",
      integration: runtimeSnapshot ?? undefined,
    };
  }

  async function refreshProjects(nextSelectedId?: string | null, runtimeSnapshot: RuntimeConfigSnapshot | null = runtime) {
    const list = await api.listProjects();
    setProjects(list);
    const candidate = nextSelectedId ?? selectedId ?? list[0]?.id ?? null;
    setSelectedId(candidate);
    if (candidate) {
      try {
        setSummary(await api.getProject(candidate));
      } catch {
        const project = list.find((item) => item.id === candidate) ?? null;
        setSummary(project ? buildFallbackSummary(project, runtimeSnapshot) : null);
      }
    } else {
      setSummary(null);
    }
  }

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const runtimeSnapshot = await api.runtime();
      if (cancelled) return;
      setRuntime(runtimeSnapshot);
      setRuntimeDraft(runtimeSnapshot.config);
      const [nextCapabilities, nextWorkflows, nextScenarios, nextConnections, localAgents] = await Promise.all([
        api.listCapabilities().catch(() => []),
        api.listWorkflows().catch(() => []),
        api.listBenchmarkScenarios().catch(() => []),
        api.listAgentConnections().catch(() => DEFAULT_CHAT_CONNECTIONS),
        api.listLocalAgentCapabilities().catch(() => ({ adapters: [], available: [] })),
      ]);
      if (cancelled) return;
      setCapabilities(nextCapabilities);
      setSelectedCapabilityName(nextCapabilities[0]?.name ?? "");
      setWorkflows(nextWorkflows);
      setSelectedWorkflowId(nextWorkflows[0]?.id ?? "");
      setBenchmarkScenarios(nextScenarios);
      setSelectedScenarioId(nextScenarios[0]?.id ?? "");
      setChatConnections(mergeLocalAgentCapabilities(
        nextConnections.length ? nextConnections : DEFAULT_CHAT_CONNECTIONS,
        localAgents.adapters,
      ));
      const list = await api.listProjects();
      if (cancelled) return;
      setProjects(list);
      const candidate = list[0]?.id ?? null;
      setSelectedId(candidate);
      if (candidate) {
        try {
          const nextSummary = await api.getProject(candidate);
          if (!cancelled) setSummary(nextSummary);
        } catch {
          if (cancelled) return;
          const project = list.find((item) => item.id === candidate) ?? null;
          setSummary(project ? buildFallbackSummary(project, runtimeSnapshot) : null);
        }
      } else {
        setSummary(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setCadPreviewUrl(null);
    setCadPreviewFormat(null);
    setCadGenResult(null);
    setHighlightedFaceIds(new Set());
    setBrepSnapshot(null);
  }, [selectedId]);

  // Load and cache the B-Rep graph for the active project so PointerText can
  // expand @feature: / @group: clicks into member face_ids, and so the viewer
  // can look up bbox/center metadata for each highlighted face.
  useEffect(() => {
    let cancelled = false;
    if (!selectedId) return;
    void (async () => {
      try {
        let raw: Record<string, unknown>;
        try {
          raw = await api.getBrepGraph(selectedId);
        } catch {
          raw = await api.buildBrepGraph(selectedId);
        }
        if (cancelled) return;
        const snap = parseBrepGraphSnapshot(raw);
        setBrepSnapshot(snap);
      } catch {
        if (!cancelled) setBrepSnapshot(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // Keep a ref to the selected project so the long-lived agent-activity stream
  // handler always filters against the current selection (avoids stale closure).
  const selectedIdRef = useRef<string | null>(selectedId);
  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => () => stopAutopilotPoll(), []);

  // Phase 2: subscribe to the live agent-activity SSE stream. When an external
  // agent (Claude Code/Codex/Copilot) drives a CAD build through the MCP →
  // /api/agent/invoke-tool bridge, the backend publishes progress here and we
  // render the same CadProgressPanel as an in-UI generation — then refresh the
  // viewer to the freshly-built model on completion.
  useEffect(() => {
    const url = `${api.base}/api/agent-activity/stream`;
    const source = new EventSource(url);
    source.onmessage = (msg) => {
      let event: AgentActivityEvent;
      try {
        event = JSON.parse(msg.data) as AgentActivityEvent;
      } catch {
        return;
      }
      if (event.type === "connected") return;

      const current = selectedIdRef.current;
      const isBuildDone =
        event.type === "tool_completed" &&
        event.tool === "cad.execute_build123d" &&
        event.status === "ok" &&
        Boolean(event.project_id);
      const isForCurrent = !event.project_id || !current || event.project_id === current;

      // Agent built a model in a DIFFERENT project than the one on screen: don't
      // yank the user away (there's no multi-project view) — just notify and
      // refresh the sidebar so its status updates, keeping the current selection.
      if (isBuildDone && !isForCurrent) {
        void refreshProjects(selectedIdRef.current);
        setChatHistory((curr) => [
          ...curr,
          {
            id: createChatId(),
            role: "assistant",
            body: `An agent finished building a model in project ${event.project_id}. Select that project to view it.`,
            createdAt: new Date().toISOString(),
          },
        ]);
        return;
      }

      // Autopilot SSE updates — bypass project filtering because they carry run_id.
      if (event.type === "autopilot_update") {
        const ae = event as unknown as Record<string, unknown>;
        const runId = ae.run_id as string;
        const status = ae.status as string;
        void (async () => {
          try {
            const run = await api.getAutopilotRun(runId);
            setChatHistory((current) => {
              const index = current.findIndex((item) => item.autopilotRun?.run_id === runId);
              if (index === -1) return current;
              const updated = [...current];
              updated[index] = {
                ...updated[index],
                autopilotRun: run,
                errors: run.errors,
                body: summarizeAutopilotRun(run),
              };
              return updated;
            });
            if (run.status === "chatting") {
              stopAutopilotPoll();
              setAgentBusy(false);
            } else if (run.status !== "running") {
              stopAutopilotPoll();
              setAgentBusy(false);
              setNotice({
                tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
                title: `${autopilotAgentLabel(run)} — ${run.status}`,
                detail: summarizeAutopilotRun(run),
              });
            }
          } catch {
            // Ignore refresh failures; next SSE or poll will retry.
          }
        })();
        return;
      }

      // Ignore all other activity that doesn't concern the current project.
      if (!isForCurrent) return;

      setCadGenerationProgress((prev) => applyAgentActivityEvent(prev, event));

      if (isBuildDone) {
        // Build for the current project: refresh the viewer in place.
        setCadPreviewUrl(`/api/projects/${event.project_id}/cad-preview?ts=${Date.now()}`);
        setCadPreviewFormat(event.preview_format ?? "glb");
        void refreshProjects(event.project_id);
        window.setTimeout(() => setCadGenerationProgress(null), 1500);
      }
    };
    source.onerror = () => {
      // EventSource auto-reconnects; nothing to do. A persistent failure just
      // means live agent activity won't show (the build still completes).
    };
    return () => source.close();
  }, []);

  useEffect(() => {
    if (!settingsOpen) return;

    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSettingsOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [settingsOpen]);

  function updateRuntimeDraft<K extends keyof RuntimeConfig>(key: K, value: RuntimeConfig[K]) {
    setRuntimeDraft((current) => (current ? { ...current, [key]: value } : current));
  }

  function syncRuntimeIntoSummary(snapshot: RuntimeConfigSnapshot) {
    setSummary((current) => (current ? { ...current, integration: snapshot } : current));
  }

  function restoreRuntimeDefaults() {
    if (!runtime?.defaults) return;
    setRuntimeDraft(runtime.defaults);
    setRuntimeNotice({ tone: "info", title: "已恢复默认值", detail: "表单已回填默认 CAD 配置，保存后才会生效。" });
  }

  async function runRuntimeTask(kind: "save" | "test", task: () => Promise<RuntimeConfigSnapshot>) {
    if (!runtimeDraft) return;
    setRuntimeBusy(true);
    setRuntimeNotice(null);
    try {
      const snapshot = await task();
      setRuntime(snapshot);
      setRuntimeDraft(snapshot.config);
      syncRuntimeIntoSummary(snapshot);
      setRuntimeNotice({
        tone: snapshot.probe.ready ? "success" : "info",
        title: kind === "save" ? "CAD 配置已保存" : "CAD 配置已测试",
        detail: getRuntimeDetail(snapshot),
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setRuntimeNotice({ tone: "error", title: "CAD 配置操作失败", detail });
    } finally {
      setRuntimeBusy(false);
    }
  }

  function resetStages() {
    setStages(BASE_STAGES.map((item) => ({ ...item, state: "idle" })));
  }

  function patchStage(key: string, state: StageState, detail?: string) {
    setStages((current) =>
      current.map((item) =>
        item.key === key ? { ...item, state, detail: detail ?? item.detail } : item,
      ),
    );
  }

  async function runBusyTask(task: () => Promise<void>) {
    setBusy(true);
    try {
      await task();
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "操作失败", detail });
    } finally {
      setBusy(false);
    }
  }

  async function ensureProject() {
    if (selectedId) return selectedId;
    const baseName = selectedFile?.name.replace(/\.(step|stp|aieng)$/i, "") || projectName || "STEP 工作台项目";
    const created = await api.createProject(baseName);
    await refreshProjects(created.id);
    return created.id;
  }

  async function runWorkbenchImportFlow() {
    if (!selectedFile) {
      setNotice({ tone: "info", title: "Select a file first", detail: "Choose a .step, .stp, or .aieng package before importing." });
      return;
    }

    resetStages();
    setChat(null);
    setNotice(null);

    await runBusyTask(async () => {
      const projectId = await ensureProject();
      const isPackageUpload = /\.aieng$/i.test(selectedFile.name);

      patchStage("upload", "active", `Uploading ${selectedFile.name}`);
      await api.uploadFile(projectId, selectedFile);
      patchStage("upload", "done", `${selectedFile.name} uploaded`);

      if (isPackageUpload) {
        patchStage("import", "done", ".aieng package uploaded directly; skipped STEP -> package import.");
      } else {
        patchStage("import", "active", "Building .aieng package from STEP");
        await api.importAieng(projectId);
        patchStage("import", "done", "STEP package imported with topology, AAG, and feature graph artifacts.");
      }

      patchStage("preview", "active", "Generating web preview asset");
      const preview = await api.convert(projectId);
      const previewStatus =
        preview && typeof preview === "object" && "status" in preview && typeof preview.status === "string"
          ? preview.status
          : "ok";
      patchStage(
        "preview",
        previewStatus === "ok" ? "done" : "error",
        previewStatus === "ok"
          ? "Preview asset ready"
          : previewStatus === "unavailable"
            ? "Preview unavailable: configure a CAD runtime to export STEP into a web-viewable asset."
            : "Preview export failed; inspect the backend response for details.",
      );

      patchStage("semantic", "active", "Validating package semantics");
      await api.validate(projectId);
      await refreshProjects(projectId);
      patchStage("semantic", "done", "Semantic validation complete");

      setNotice({
        tone: previewStatus === "ok" ? "success" : "info",
        title: isPackageUpload ? ".aieng package ready" : "STEP import complete",
        detail: isPackageUpload
          ? "Package upload completed. If preview is unavailable, the package is still loaded and usable in the workbench."
          : previewStatus === "ok"
            ? "STEP imported, packaged, validated, and previewed successfully."
            : "STEP imported and validated, but preview export still needs a working CAD runtime.",
      });
    });
  }

  async function runProjectAction(
    key: string,
    action: () => Promise<unknown>,
    title: string,
    detail: string,
  ) {
    if (!selectedId) return;
    setNotice(null);
    await runBusyTask(async () => {
      patchStage(key, "active");
      await action();
      await refreshProjects(selectedId);
      patchStage(key, "done");
      setNotice({ tone: "success", title, detail });
    });
  }

  async function handleGenerateCad(description: string, hints: Record<string, unknown>) {
    if (!selectedId) return;
    setCadGenerating(true);
    try {
      const result = await api.generateCad(selectedId, { description, hints, write_files: true });
      const topo = result.topology_summary as { face_count: number; feature_count: number };
      setCadPreviewUrl(result.preview_url as string);
      setCadPreviewFormat(result.preview_format as string);
      setCadGenResult({ code: result.generated_code as string, face_count: topo.face_count, feature_count: topo.feature_count });
      await refreshProjects(selectedId);
      setNotice({ tone: "success", title: "CAD generated", detail: `${topo.face_count} faces, ${topo.feature_count} features` });
    } catch (err) {
      setNotice({ tone: "error", title: "CAD generation failed", detail: String(err) });
    } finally {
      setCadGenerating(false);
    }
  }

  async function handleRefineCad(feedback: string) {
    if (!selectedId) return;
    setCadGenerating(true);
    try {
      const result = await api.refineCad(selectedId, { feedback, write_files: true });
      const topo = result.topology_summary as { face_count: number; feature_count: number };
      setCadPreviewUrl(result.preview_url as string);
      setCadPreviewFormat(result.preview_format as string);
      setCadGenResult({ code: result.refined_code as string, face_count: topo.face_count, feature_count: topo.feature_count });
      await refreshProjects(selectedId);
      setNotice({ tone: "success", title: "CAD refined", detail: `${topo.face_count} faces, ${topo.feature_count} features` });
    } catch (err) {
      setNotice({ tone: "error", title: "CAD refinement failed", detail: String(err) });
    } finally {
      setCadGenerating(false);
    }
  }

  function detectCadIntent(msg: string): EngineeringChatIntent | null {
    const lower = msg.toLowerCase();

    // Simulation execution - must check before preprocess so "run simulation" doesn't
    // match the "run fea" preprocess trigger.
    const simulatePhrases = [
      "run simulation", "mesh and solve", "start simulation", "execute simulation",
      "run analysis", "run solver", "run the simulation", "start the simulation",
    ];
    if (simulatePhrases.some((t) => lower.includes(t))) return "simulate";
    if (lower.trim() === "simulate" || lower.startsWith("simulate ")) return "simulate";

    // Specific high-priority intents must be evaluated before broad CAD refine
    // triggers such as "change", "make", or "add".
    const setTargetPhrases = [
      "set max stress", "set max displacement", "set stress limit", "set displacement limit",
      "set stress target", "set displacement target", "stress limit", "displacement limit",
      "stress target", "displacement target", "add target", "set target", "design target",
      "stress must be", "displacement must be", "stress should be", "displacement should be",
      "stress <= ", "displacement <= ", "stress < ", "displacement < ",
    ];
    const targetMetricWords = ["stress", "displacement", "deflection", "von mises", "sigma"];
    const hasTargetValue = /\d+\s*(mpa|mm)\b/i.test(msg);
    if (
      setTargetPhrases.some((t) => lower.includes(t)) ||
      (hasTargetValue && targetMetricWords.some((w) => lower.includes(w)) &&
       (lower.includes("set") || lower.includes("limit") || lower.includes("target") ||
        lower.includes("must") || lower.includes("should") || lower.includes("<=") || lower.includes("<")))
    ) {
      return "set_target";
    }

    const changeMaterialPhrases = ["change material", "switch material", "use material", "try material",
      "change to ", "switch to ", "try with ", "use steel", "use aluminum", "use titanium",
      "use al6061", "use al7075", "use ti-6al", "use nylon", "material to "];
    if (changeMaterialPhrases.some((t) => lower.includes(t)) &&
        (lower.includes("material") || lower.includes("steel") || lower.includes("aluminum") ||
         lower.includes("titanium") || lower.includes("nylon") || lower.includes("al6061") ||
         lower.includes("al7075") || lower.includes("ti-6al"))) {
      return "change_material";
    }

    const refineMeshPhrases = ["refine mesh", "finer mesh", "smaller mesh", "mesh to ", "mesh size",
      "mesh refinement", "increase mesh", "denser mesh"];
    if (refineMeshPhrases.some((t) => lower.includes(t))) {
      return "refine_mesh";
    }

    // FEA/simulation setup - check before generate/refine since "set up a simulation" could
    // otherwise match "set up" + part noun heuristics.
    const feaVerbs = ["set up", "setup", "configure", "prepare", "generate fea", "run fea", "start fea"];
    const feaNouns = [
      "fea", "fea setup", "finite element", "simulation setup", "structural analysis",
      "boundary condition", "mesh setup", "preprocessing", "pre-processing",
    ];
    if (feaVerbs.some((t) => lower.includes(t)) && feaNouns.some((n) => lower.includes(n))) {
      return "preprocess";
    }
    if (lower.includes("preprocess") || lower.includes("pre-process")) {
      return "preprocess";
    }

    // CAD generation before refinement so "make a bracket" creates a new part,
    // while "make it thicker" can still refine an existing model.
    const genPhrases = [
      "generate", "create a", "create the", "design a", "design the",
      "make a", "make the", "model a", "model the", "build a", "build the",
      "draw a", "draw the",
      // Chinese
      "生成", "创建", "设计", "画一个", "画个", "画一", "做一个", "做个",
      "建模", "绘制", "画", "做",
    ];
    const partNouns = [
      "part", "bracket", "plate", "housing", "mount", "gear", "enclosure",
      "fixture", "block", "shaft", "flange", "cap", "cover", "holder",
      "beam", "rod", "body", "component", "bushing", "sleeve", "clamp", "adapter",
      // Generic / Chinese
      "咖啡机", "机器", "设备", "产品", "零件", "部件", "组件", "模型", "机",
    ];
    if (genPhrases.some((t) => lower.includes(t)) && partNouns.some((n) => lower.includes(n))) {
      return "generate";
    }

    if (cadGenResult) {
      const refineTriggers = [
        "make", "increase", "decrease", "change", "add", "remove",
        "thicker", "taller", "wider", "longer", "shorter", "bigger", "smaller",
        "refine", "adjust", "update", "modify",
        // Chinese
        "修改", "调整", "加厚", "加宽", "加长", "增大", "减小", "变薄",
        "更新", "优化", "改",
      ];
      if (refineTriggers.some((t) => lower.includes(t))) return "refine";
    }

    return null;
  }

  async function resolveEngineeringIntent(
    prompt: string,
  ): Promise<{ intent: EngineeringChatIntent; materialHint?: string; meshSizeMm?: number } | null> {
    if (selectedId) {
      try {
        const plan = await api.engineeringActionPlan(selectedId, prompt);
        const intent = String(plan.intent ?? "");
        const known: EngineeringChatIntent[] = [
          "generate", "refine", "preprocess", "simulate", "change_material", "refine_mesh", "set_target",
        ];
        if (known.includes(intent as EngineeringChatIntent)) {
          const extracted = (plan.extracted_inputs as Record<string, unknown> | undefined) ?? {};
          const meshSizeRaw = extracted.mesh_size_mm;
          const meshSizeMm = typeof meshSizeRaw === "number" ? meshSizeRaw : undefined;
          const materialHint = typeof extracted.material_hint === "string" ? extracted.material_hint : undefined;
          return { intent: intent as EngineeringChatIntent, materialHint, meshSizeMm };
        }
      } catch {
        // Keep the chat usable if the new backend planner is unavailable.
      }
    }
    const fallback = detectCadIntent(prompt);
    return fallback ? { intent: fallback } : null;
  }

  async function executePreprocessFromPrompt(
    prompt: string,
    options: { materialHint?: string; meshHint?: string } = {},
  ) {
    if (!selectedId) {
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: "Please select or create a project first.", createdAt: new Date().toISOString() },
      ]);
      return;
    }
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        task_description: prompt,
        write_files: true,
      };
      if (options.materialHint) payload.material_hint = options.materialHint;
      if (options.meshHint) payload.mesh_hint = options.meshHint;
      if (directApiKey) payload.api_key = directApiKey;
      const result = await api.aiPreprocessing(selectedId, payload);
      const feaSetup = result.fea_setup as Record<string, unknown>;
      const setupYaml = result.setup_yaml as Record<string, unknown>;
      const material = String(feaSetup?.material ?? setupYaml?.material_name ?? "unknown");
      const bcCount = (feaSetup?.boundary_conditions as unknown[])?.length ?? 0;
      const loadCount = (feaSetup?.loads as unknown[])?.length ?? 0;
      const meshSizeMm = Number(
        (feaSetup?.mesh as Record<string, unknown>)?.target_size_mm ?? 2.5,
      );
      const warnings = (feaSetup?.warnings as string[]) ?? [];
      const written = (result.written_artifacts as string[]) ?? [];
      await refreshProjects(selectedId);
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: "FEA setup generated",
          createdAt: new Date().toISOString(),
          preprocessResult: {
            material,
            bc_count: bcCount,
            load_count: loadCount,
            mesh_size_mm: meshSizeMm,
            written_artifacts: written,
            warnings,
          },
        },
      ]);
    } catch (err) {
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: redactSecrets(`FEA preprocessing failed: ${String(err)}`),
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function executeCadFromPrompt(prompt: string, intent: "generate" | "refine") {
    if (!selectedId) {
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: "Please select or create a project first.", createdAt: new Date().toISOString() },
      ]);
      return;
    }
    setCadGenerating(true);
    setCadGenerationProgress(applyCadProgressEvent(emptyCadGenerationProgress(), { step: "planning", message: "AI is analyzing the design description…" }));
    try {
      const keyPayload = directApiKey ? { api_key: directApiKey } : {};
      if (intent === "generate") {
        const response = await api.generateCadStream(selectedId, { description: prompt, hints: {}, write_files: true, ...keyPayload });
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalResult: Record<string, unknown> | null = null;
        let fatalError: string | null = null;
        while (reader && !fatalError) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;
            let event: Record<string, unknown>;
            try {
              event = JSON.parse(trimmed.slice(6)) as Record<string, unknown>;
            } catch {
              continue; // malformed SSE line
            }
            const step = String(event.step ?? "");
            setCadGenerationProgress((prev) => applyCadProgressEvent(prev, event));
            if (step === "done") {
              finalResult = (event.result as Record<string, unknown>) ?? {};
            } else if (step === "error") {
              fatalError = String(event.message ?? "CAD generation failed");
            }
          }
        }
        if (fatalError) throw new Error(fatalError);
        const result = finalResult ?? {};
        const topo = result.topology_summary as { face_count: number; feature_count: number };
        setCadPreviewUrl(result.preview_url as string);
        setCadPreviewFormat(result.preview_format as string);
        const code = result.generated_code as string;
        setCadGenResult({ code, face_count: topo.face_count, feature_count: topo.feature_count });
        await refreshProjects(selectedId);
        setChatHistory((current) => [
          ...current,
          {
            id: createChatId(),
            role: "assistant",
            body: "Agent generated CAD — preview updated",
            createdAt: new Date().toISOString(),
            cadResult: { face_count: topo.face_count, feature_count: topo.feature_count, code },
          },
        ]);
      } else {
        const result = await api.refineCad(selectedId, { feedback: prompt, write_files: true, ...keyPayload });
        const topo = result.topology_summary as { face_count: number; feature_count: number };
        setCadPreviewUrl(result.preview_url as string);
        setCadPreviewFormat(result.preview_format as string);
        const code = result.refined_code as string;
        setCadGenResult({ code, face_count: topo.face_count, feature_count: topo.feature_count });
        await refreshProjects(selectedId);
        setChatHistory((current) => [
          ...current,
          {
            id: createChatId(),
            role: "assistant",
            body: "Agent refined CAD — preview updated",
            createdAt: new Date().toISOString(),
            cadResult: { face_count: topo.face_count, feature_count: topo.feature_count, code },
          },
        ]);
      }
    } catch (err) {
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: redactSecrets(`CAD ${intent === "generate" ? "generation" : "refinement"} failed: ${String(err)}`),
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setCadGenerating(false);
      setCadGenerationProgress(null);
    }
  }

  async function executeSimulation(meshSizeMmOverride?: number) {
    if (!selectedId) return;
    setSimulationPending(false);
    setBusy(true);
    setSimulationProgress({ step: "starting", message: "Starting simulation…" });
    try {
      const payload: Record<string, unknown> = { confirmed: true };
      if (meshSizeMmOverride != null) payload.mesh_size_mm = meshSizeMmOverride;

      const response = await api.runSimulationStream(selectedId, payload);
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalResult: Record<string, unknown> | null = null;
      let simError: string | null = null;

      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6)) as Record<string, unknown>;
            const step = String(event.step ?? "");
            if (step === "done") {
              finalResult = (event.result as Record<string, unknown>) ?? event;
              setSimulationProgress(null);
              break outer;
            } else if (step === "error") {
              simError = String(event.message ?? "Unknown simulation error");
              setSimulationProgress(null);
              break outer;
            } else {
              setSimulationProgress({ step, message: String(event.message ?? "") });
            }
          } catch {
            // partial or malformed SSE line — skip
          }
        }
      }

      if (simError) throw new Error(simError);

      const result = finalResult ?? {};
      const status = String(result.status ?? "");
      let body: string;
      if (status === "success") {
        const vm = result.von_mises_max_mpa != null ? `σ_max ${(result.von_mises_max_mpa as number).toFixed(1)} MPa` : "";
        const ux = result.displacement_max_mm != null ? `u_max ${(result.displacement_max_mm as number).toFixed(3)} mm` : "";
        body = ["Simulation complete.", vm, ux].filter(Boolean).join("  ·  ");
      } else if (status === "tools_unavailable") {
        body = `Simulation tools not available: ${(result.missing_tools as string[] | undefined)?.join(", ") ?? "unknown"}.`;
      } else {
        body = `Solver returned error (code ${result.returncode ?? "?"}).`;
      }
      setHeatmapActive(false);
      setHeatmapRange(null);
      await refreshProjects(selectedId);
      const fosAdvisory = (result.verdict as Record<string, unknown> | undefined)?.fos_advisory as string[] | undefined;
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body,
          createdAt: new Date().toISOString(),
          simulationResult: {
            status,
            returncode: result.returncode as number | undefined,
            von_mises_max_mpa: result.von_mises_max_mpa as number | null | undefined,
            displacement_max_mm: result.displacement_max_mm as number | null | undefined,
            node_count: result.node_count as number | undefined,
            mesh_size_mm: result.mesh_size_mm as number | undefined,
            written_artifacts: result.written_artifacts as string[] | undefined,
            warnings: result.warnings as string[] | undefined,
            missing_tools: result.missing_tools as string[] | undefined,
            message: result.message as string | undefined,
            diagnosis: result.diagnosis as string[] | undefined,
            verdict: result.verdict as NonNullable<ChatHistoryItem["simulationResult"]>["verdict"],
          },
        },
      ]);
      if (fosAdvisory && fosAdvisory.length > 0) {
        setChatHistory((current) => [
          ...current,
          {
            id: createChatId(),
            role: "assistant",
            body: "Engineering advisory based on Factor-of-Safety analysis:",
            createdAt: new Date().toISOString(),
            advisoryItems: fosAdvisory,
          },
        ]);
      }
    } catch (err) {
      setSimulationProgress(null);
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: redactSecrets(`Simulation failed: ${String(err)}`), createdAt: new Date().toISOString() },
      ]);
    } finally {
      setBusy(false);
      setSimulationProgress(null);
    }
  }

  async function viewStressHeatmap() {
    const newActive = !heatmapActive;
    setHeatmapActive(newActive);
    if (!newActive || !selectedId) {
      setHeatmapRange(null);
      return;
    }
    try {
      const res = await fetch(`/api/projects/${selectedId}/stress-heatmap`, { method: "HEAD" });
      const minStr = res.headers.get("X-Stress-Min-Mpa");
      const maxStr = res.headers.get("X-Stress-Max-Mpa");
      if (minStr && maxStr) {
        const min = parseFloat(minStr);
        const max = parseFloat(maxStr);
        if (!isNaN(min) && !isNaN(max)) setHeatmapRange({ min, max });
      }
    } catch {
      setHeatmapRange(null);
    }
  }

  function selectedGeometryContext(): SelectedGeometryContext | null {
    if (!pickedFaces.length) return null;
    return {
      pointers: pickedFaces.map((face) => face.pointer),
      faces: pickedFaces,
      highlightedFaceIds: Array.from(highlightedFaceIds),
    };
  }

  function withSelectedGeometryPrompt(prompt: string) {
    if (prompt.includes("\n\nSelected geometry:\n")) return prompt;
    const context = selectedGeometryContext();
    if (!context) return prompt;
    const faceLines = context.faces.map((face) => {
      const roles = face.roles.length ? face.roles.join(", ") : "unknown";
      return `- ${face.pointer} ${face.surface_type || "unknown"} roles: ${roles} label: ${face.label}`;
    });
    return `User request:\n${prompt}\n\nSelected geometry:\n${faceLines.join("\n")}`;
  }

  function agentPayloadGeometry() {
    return selectedGeometryContext() ?? undefined;
  }

  async function chatWithProjectContext(prompt: string) {
    if (!selectedId) {
      await runAgentChat(prompt);
      return;
    }
    setBusy(true);
    try {
      const history = chatHistory.slice(-20).map((m) => ({ role: m.role, content: m.body }));
      const result = await api.contextualChat(selectedId, prompt, history, directApiKey || undefined);
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: result.reply,
          createdAt: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: `Engineering assistant error: ${String(err)}`,
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function executeIterationFromPrompt(
    prompt: string,
    intent: "change_material" | "refine_mesh",
    extracted: { materialHint?: string; meshSizeMm?: number } = {},
  ) {
    if (!selectedId) return;

    // Extract material name or mesh size from prompt
    const lower = prompt.toLowerCase();
    let materialHint: string | undefined = extracted.materialHint;
    let meshSizeMm: number | undefined = extracted.meshSizeMm;

    if (intent === "change_material") {
      // Try to pull a known material name from the message
      const knownMaterials: Record<string, string> = {
        "al6061": "Al6061-T6", "al6061-t6": "Al6061-T6",
        "al7075": "Al7075-T6", "al7075-t6": "Al7075-T6",
        "steel-1045": "Steel-1045", "steel 1045": "Steel-1045", "1045": "Steel-1045",
        "steel-316l": "Steel-316L", "316l": "Steel-316L",
        "ti-6al-4v": "Ti-6Al-4V", "titanium": "Ti-6Al-4V", "ti64": "Ti-6Al-4V",
        "nylon": "Nylon-PA66", "pa66": "Nylon-PA66",
        "petg": "PETG-CF", "petg-cf": "PETG-CF",
        "cast iron": "Cast-Iron-Grey",
        "steel": "Steel-1045",
        "aluminum": "Al6061-T6", "aluminium": "Al6061-T6",
      };
      for (const [kw, mat] of Object.entries(knownMaterials)) {
        if (lower.includes(kw)) { materialHint = mat; break; }
      }
    }

    if (intent === "refine_mesh") {
      const numMatch = lower.match(/(\d+(?:\.\d+)?)\s*mm/);
      if (numMatch) meshSizeMm = parseFloat(numMatch[1]);
    }

    setBusy(true);
    try {
      if (intent === "change_material") {
        const matLabel = materialHint ?? "detected material";
        setChatHistory((current) => [...current, {
          id: createChatId(), role: "assistant",
          body: `Re-running AI preprocessing with material hint: ${matLabel}…`,
          createdAt: new Date().toISOString(),
        }]);
        await executePreprocessFromPrompt(prompt, { materialHint });
        // After preprocessing, automatically trigger simulation
        setSimulationPending(true);
        setChatHistory((current) => [...current, {
          id: createChatId(), role: "assistant",
          body: "Preprocessing updated. Ready to re-simulate with new material — approve to run.",
          createdAt: new Date().toISOString(),
        }]);
      } else {
        const meshLabel = meshSizeMm != null ? `${meshSizeMm} mm` : "finer mesh";
        setChatHistory((current) => [...current, {
          id: createChatId(), role: "assistant",
          body: `Re-meshing at ${meshLabel} and solving…`,
          createdAt: new Date().toISOString(),
        }]);
        await executeSimulation(meshSizeMm);
      }
    } finally {
      setBusy(false);
    }
  }

  async function executeSetTargetFromPrompt(prompt: string) {
    if (!selectedId) return;
    setBusy(true);
    try {
      const result = await api.chatSetTarget(selectedId, prompt);
      const { target, action, total_targets } = result;
      const body = `Design target ${action}: ${target.label} ${target.operator} ${target.value}${target.unit ? " " + target.unit : ""} (${total_targets} target${total_targets !== 1 ? "s" : ""} total)`;
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body,
          createdAt: new Date().toISOString(),
          targetResult: {
            action,
            label: target.label,
            metric: target.metric,
            operator: target.operator,
            value: target.value,
            unit: target.unit,
            total_targets,
          },
        },
      ]);
    } catch (err) {
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: `Could not set design target: ${String(err)}`,
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function sendUnified() {
    const prompt = message.trim();
    if (!prompt) return;
    if (selectedChatConnection.id === "local-agent" || selectedChatConnection.id === "llm-api") {
      const chattingRun = chatHistory
        .slice()
        .reverse()
        .find((item) => item.autopilotRun?.status === "chatting")?.autopilotRun;
      if (chattingRun) {
        setChatHistory((current) => [
          ...current,
          { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
        ]);
        setMessage("");
        await updateAutopilotRun(chattingRun.run_id, "approve", prompt);
        return;
      }
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
      setMessage("");
      await runAutopilotAgent(prompt, true);
      return;
    }
    const agentPrompt = withSelectedGeometryPrompt(prompt);

    setChatHistory((current) => [
      ...current,
      { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString() },
    ]);
    setMessage("");

    const plannedAction = await resolveEngineeringIntent(agentPrompt);
    const cadIntent = plannedAction?.intent ?? null;
    if (cadIntent === "simulate") {
      setSimulationPending(true);
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: "Ready to mesh and solve. This will run Gmsh + CalculiX on your geometry — approve to proceed.",
          createdAt: new Date().toISOString(),
        },
      ]);
      return;
    }
    if (cadIntent === "preprocess") {
      await createAgentPlanFromPrompt(prompt, true);
      return;
    }
    if (cadIntent === "generate" || cadIntent === "refine") {
      await executeCadFromPrompt(agentPrompt, cadIntent);
      return;
    }
    if (cadIntent === "change_material" || cadIntent === "refine_mesh") {
      await createAgentPlanFromPrompt(prompt, true);
      return;
    }
    if (cadIntent === "set_target") {
      await createAgentPlanFromPrompt(prompt, true);
      return;
    }

    await runAgentChat(prompt);
  }

  function addPickedFace(face: PickedFace) {
    setPickedFaces((prev) => {
      const filtered = prev.filter((f) => f.pointer !== face.pointer);
      return [face, ...filtered].slice(0, 10);
    });
    const faceId = face.pointer.startsWith("@face:") ? face.pointer.slice("@face:".length) : null;
    if (faceId) {
      setHighlightedFaceIds((prev) => {
        const next = new Set(prev);
        next.add(faceId);
        return next;
      });
    }
  }

  function clearPickedFaces() {
    setPickedFaces([]);
  }

  function insertToChat(text: string) {
    setMessage((prev) => (prev ? prev + " " + text : text));
  }

  async function runPreprocessFromPointer(prompt: string) {
    await executePreprocessFromPrompt(prompt);
  }

  // Toggle a single face in the highlight set, or add many at once (used by
  // @feature: and @group: pointers which expand to multiple member faces).
  function toggleHighlightedFace(faceId: string) {
    setHighlightedFaceIds((prev) => {
      const next = new Set(prev);
      if (next.has(faceId)) next.delete(faceId);
      else next.add(faceId);
      return next;
    });
  }

  function addHighlightedFaces(faceIds: string[]) {
    if (faceIds.length === 0) return;
    setHighlightedFaceIds((prev) => {
      const next = new Set(prev);
      for (const id of faceIds) next.add(id);
      return next;
    });
  }

  function clearHighlightedFaces() {
    setHighlightedFaceIds(new Set());
  }

  function handlePointerClick(token: PointerToken) {
    if (token.kind === "face") {
      toggleHighlightedFace(token.id);
      return;
    }
    if (token.kind === "feature") {
      const faces = brepSnapshot?.featureFaces[token.id]
        ?? brepSnapshot?.groups[token.id]?.members
        ?? [];
      if (faces.length > 0) {
        addHighlightedFaces(faces);
      } else {
        setNotice({ tone: "info", title: "Feature not in B-Rep graph", detail: `No face mapping for @feature:${token.id}. Build the B-Rep graph first.` });
      }
      return;
    }
    if (token.kind === "group") {
      const faces = brepSnapshot?.groups[token.id]?.members ?? [];
      if (faces.length > 0) {
        addHighlightedFaces(faces);
      } else {
        setNotice({ tone: "info", title: "Group has no members", detail: `@group:${token.id}` });
      }
      return;
    }
    if (token.kind === "artifact") {
      try {
        void navigator.clipboard?.writeText(token.id);
        setNotice({ tone: "info", title: "Artifact path copied", detail: token.id });
      } catch {
        setNotice({ tone: "info", title: "Artifact", detail: token.id });
      }
      return;
    }
    // @edge: not yet mapped — surface as a notice so the user gets feedback.
    setNotice({ tone: "info", title: `@${token.kind}:${token.id}`, detail: "No viewer action wired for this pointer kind yet." });
  }

  const semanticSections = [
    {
      title: "Manifest / 校验",
      body: jsonBlock({ manifest: summary?.manifest ?? null, validation: summary?.validation ?? null }),
    },
    {
      title: "Feature / Topology",
      body: jsonBlock({ feature_graph: summary?.feature_graph ?? null, topology: summary?.topology ?? null }),
    },
  ];

  const aiSummary = (summary as any)?.ai_summary as string | undefined;
  const runtimeReady = runtime?.probe.ready ?? false;
  const runtimeProvider = getProviderLabel(runtime?.config.provider);
  const runtimeDetail = getRuntimeDetail(runtime);
  const validationState =
    (summary as any)?.validation?.report_ok === true
      ? "通过"
      : (summary as any)?.validation?.report_ok === false
        ? "失败"
        : "待刷新";
  const integrationBody = jsonBlock({
    integration: summary?.integration ?? null,
    members: summary?.members ?? [],
    viewer: (summary as any)?.viewer ?? null,
  });
  const caeSummary = summary?.cae ?? null;
  const caeFields = caeSummary?.available_fields ?? EMPTY_CAE_FIELDS;
  const hasCaeContext = caeSummary?.present ?? false;
  const hasCaeResultArtifacts = Boolean(
    caeSummary?.results_available ||
      (caeSummary?.result_evidence_count ?? 0) > 0 ||
      caeSummary?.solver_fields?.some((field) => field.available && field.format === "vertex_json") ||
      caeSummary?.artifact_detection?.has_results ||
      caeSummary?.artifact_detection?.has_fields ||
      caeSummary?.result_summary?.status.has_results ||
      caeSummary?.result_summary?.status.has_fields,
  );
  const renderableCaeFields = useMemo(
    () => (hasCaeResultArtifacts ? caeFields : []),
    [caeFields, hasCaeResultArtifacts],
  );
  const activeFieldDescriptor = hasCaeResultArtifacts ? fieldDescriptor : null;

  useEffect(() => {
    if (!renderableCaeFields.length) return;
    if (!renderableCaeFields.includes(selectedCaeField)) {
      setSelectedCaeField(renderableCaeFields[0]);
    }
  }, [renderableCaeFields, selectedCaeField]);

  useEffect(() => {
    if (!selectedId || !hasCaeResultArtifacts || !renderableCaeFields.length) {
      setFieldDescriptor(null);
      return;
    }
    let cancelled = false;
    void api.getFieldDescriptor(selectedId, selectedCaeField)
      .then((desc) => {
        if (cancelled) return;
        setFieldDescriptor((current) => {
          if (
            current &&
            current.project_id === desc.project_id &&
            current.field_name === desc.field_name &&
            current.format === desc.format &&
            current.basis === desc.basis &&
            current.colormap === desc.colormap &&
            current.min_value === desc.min_value &&
            current.max_value === desc.max_value &&
            current.unit === desc.unit &&
            current.source === desc.source
          ) {
            return current;
          }
          return desc;
        });
      })
      .catch(() => { if (!cancelled) setFieldDescriptor(null); });
    return () => { cancelled = true; };
  }, [selectedId, selectedCaeField, hasCaeResultArtifacts, renderableCaeFields]);

  useEffect(() => {
    setChatHistory([]);
  }, [selectedId]);

  useEffect(() => {
    if (!chatLogRef.current) return;
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [chatHistory]);

  useEffect(() => {
    sidePaneRef.current?.scrollTo({ top: 0 });
  }, [controlPaneMode, workbenchPaneMode]);

  function appendRunToChatHistory(run: RuntimeRun) {
    const statusLabel = runtimeStatusLabel(run.status);
    // If a geometry inspection tool completed, produce a human-readable summary line
    const geoResult = run.tool_results.find(
      (tr) =>
        tr.status === "success" &&
        run.tool_calls.find((tc) => tc.id === tr.id && tc.name === "freecad.inspect_geometry")
    );
    const geoLine =
      geoResult && typeof geoResult.output === "object" && geoResult.output !== null
        ? formatGeometryResult(geoResult.output as Record<string, unknown>)
        : null;
    const artifactLine = formatArtifactChanges(run);
    const body = geoLine
      ? `[本地运行时] ${statusLabel} — ${geoLine}${artifactLine ? "\n" + artifactLine : ""}`
      : run.summary
        ? `[本地运行时] ${statusLabel} — ${run.summary}${artifactLine ? "\n" + artifactLine : ""}`
        : `[本地运行时] ${statusLabel}${artifactLine ? "\n" + artifactLine : ""}`;
    const artifactPaths = extractArtifactPaths(run);

    // Extract artifact_diffs from cae.apply_setup_patch output
    let artifactDiffs: ArtifactDiff[] | undefined;
    const patchResult = run.tool_results.find((tr) =>
      tr.status === "success" &&
      run.tool_calls.find((tc) => tc.id === tr.id && tc.name === "cae.apply_setup_patch")
    );
    if (patchResult && typeof patchResult.output === "object" && patchResult.output !== null) {
      const diffs = (patchResult.output as Record<string, unknown>).artifact_diffs;
      if (Array.isArray(diffs) && diffs.length > 0) {
        artifactDiffs = diffs as ArtifactDiff[];
      }
    }

    setChatHistory((current) => [
      ...current,
      {
        id: createChatId(),
        role: "assistant",
        body,
        createdAt: new Date().toISOString(),
        mode: "runtime",
        plan: runtimeRunToChatPlan(run),
        errors: run.errors,
        auditLogUrl: null,
        artifactPaths: artifactPaths.length ? artifactPaths : undefined,
        artifactDiffs,
      },
    ]);
  }

  async function refreshAgentWorkbench() {
    await runBusyTask(async () => {
      const [nextCapabilities, nextWorkflows, nextScenarios, nextConnections, localAgents] = await Promise.all([
        api.listCapabilities(),
        api.listWorkflows(),
        api.listBenchmarkScenarios(),
        api.listAgentConnections().catch(() => DEFAULT_CHAT_CONNECTIONS),
        api.listLocalAgentCapabilities().catch(() => ({ adapters: [], available: [] })),
      ]);
      setCapabilities(nextCapabilities);
      setWorkflows(nextWorkflows);
      setBenchmarkScenarios(nextScenarios);
      setChatConnections(mergeLocalAgentCapabilities(
        nextConnections.length ? nextConnections : DEFAULT_CHAT_CONNECTIONS,
        localAgents.adapters,
      ));
      setSelectedCapabilityName((current) => current || nextCapabilities[0]?.name || "");
      setSelectedWorkflowId((current) => current || nextWorkflows[0]?.id || "");
      setSelectedScenarioId((current) => current || nextScenarios[0]?.id || "");
      setNotice({ tone: "success", title: "Agent 工作台已刷新", detail: "能力注册表、工作流和 benchmark 场景已重新读取。" });
    });
  }

  function openMcpCapabilities() {
    setCapabilityCategory("all");
    setCapabilityQuery("mcp");
    setControlPaneMode("agent");
    if (!capabilities.length) {
      void refreshAgentWorkbench();
    }
  }

  async function previewSelectedCapability(approved = false) {
    if (!selectedCapability) return;
    await runBusyTask(async () => {
      const preview = await api.previewCapability(
        selectedCapability.name,
        selectedId ? { project_id: selectedId } : {},
        approved,
      );
      setCapabilityPreview(preview);
      setNotice({
        tone: preview.status === "success" ? "success" : "info",
        title: preview.approval_required ? "需要审批" : "能力预览完成",
        detail: preview.preview?.warnings?.[0] || preview.errors?.[0] || `${selectedCapability.name} preview ready.`,
      });
    });
  }

  async function runSelectedWorkflow() {
    if (!selectedWorkflow) return;
    const workflowMessage = `run workflow ${selectedWorkflow.id}`;
    await runBusyTask(async () => {
      const run = await api.startRun(workflowMessage, selectedId ?? null, selectedId ? { project_id: selectedId } : null, {
        workflow_id: selectedWorkflow.id,
        steps: selectedWorkflow.steps,
        llm_config: llmConfig,
      });
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      setNotice({
        tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
        title: `工作流 — ${runtimeStatusLabel(run.status)}`,
        detail: run.summary || run.errors[0] || selectedWorkflow.title,
      });
    });
  }

  function updateLlmConfig<K extends keyof LLMConfig>(key: K, value: LLMConfig[K]) {
    setLlmConfig((current) => ({ ...current, [key]: value }));
  }

  function handleLlmTestResult(status: "config_ok" | "conn_ok" | "error", message: string) {
    if (status === "config_ok" || status === "conn_ok") {
      setNotice({ tone: "success", title: "LLM 测试通过", detail: message });
    } else {
      setNotice({ tone: "error", title: "LLM 测试失败", detail: message });
    }
  }

  function applyLlmProviderPreset(provider: string) {
    setLlmConfig((current) => {
      const next = { ...current, provider };
      if (provider === "anthropic") {
        next.api_key_env = "ANTHROPIC_API_KEY";
        next.base_url = "";
      } else if (provider === "azure-openai") {
        next.api_key_env = "AZURE_OPENAI_API_KEY";
      } else {
        next.api_key_env = "OPENAI_API_KEY";
      }
      return next;
    });
  }

  function restoreDefaultLlmConfig() {
    setLlmConfig({ ...DEFAULT_LLM_CONFIG });
  }

  async function runBenchmark(dryRun: boolean) {
    if (!selectedScenarioId || benchmarkBusy) return;
    setBenchmarkBusy(true);
    setNotice(null);
    try {
      const run = await api.startBenchmarkRun({
        scenario_id: selectedScenarioId,
        condition: "both",
        dry_run: dryRun,
        llm_config: llmConfig,
      });
      setBenchmarkRun(run);
      setNotice({
        tone: run.status === "completed" ? "success" : "error",
        title: dryRun ? "Benchmark dry-run 完成" : "Benchmark 运行完成",
        detail: run.errors?.[0] || run.warnings[0] || run.result_path || run.run_id,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "Benchmark 运行失败", detail });
    } finally {
      setBenchmarkBusy(false);
    }
  }

  async function submitRuntime(promptOverride?: string, skipUserMsg = false) {
    const prompt = (promptOverride ?? message).trim();
    if (!prompt) {
      if (!skipUserMsg) setNotice({ tone: "info", title: "请输入请求", detail: "本地运行时需要一条自然语言指令。" });
      return;
    }
    const agentPrompt = withSelectedGeometryPrompt(prompt);
    if (!skipUserMsg) {
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
    }
    await runBusyTask(async () => {
      const run = await api.startRun(agentPrompt, selectedId ?? null);
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      const statusLabel = runtimeStatusLabel(run.status);
      setNotice({
        tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
        title: `本地运行时 — ${statusLabel}`,
        detail: run.summary || run.errors[0] || "",
      });
    });
  }

  async function refreshCaeSummary() {
    if (!selectedId || caeRefreshing) return;
    setCaeRefreshing(true);
    setNotice(null);
    try {
      const run = await api.startRun("refresh cae summary", selectedId, {
        project_id: selectedId,
        overwrite: true,
      });
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      if (run.status === "completed") {
        await refreshProjects(selectedId);
        setNotice({
          tone: "success",
          title: "CAE 摘要已刷新",
          detail: run.summary || "已重新生成 CAE 结果摘要、证据索引和 Markdown 文件。",
        });
      } else {
        setNotice({
          tone: "error",
          title: "CAE 摘要刷新失败",
          detail: run.errors[0] || run.summary || "运行时返回非成功状态。",
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "CAE 摘要刷新失败", detail });
    } finally {
      setCaeRefreshing(false);
    }
  }

  async function generateCaeReviewReport() {
    if (!selectedId || caeReviewLoading) return;
    setCaeReviewLoading(true);
    setNotice(null);
    try {
      const report = await api.getCaeReviewReport(selectedId);
      setCaeReviewReport(report);
      setNotice({
        tone: "success",
        title: "CAE review report generated",
        detail: "Evidence, missingness, stale state, design targets, and claim boundaries were synthesized without running a solver.",
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "CAE review report failed", detail });
    } finally {
      setCaeReviewLoading(false);
    }
  }

  async function importMetricsAndRefresh() {
    if (!selectedId || metricsImporting) return;
    const inputPath = metricsInputPath.trim();
    if (!inputPath) {
      setNotice({ tone: "info", title: "请输入指标文件路径", detail: "需要提供外部 JSON/CSV 指标文件的绝对路径。" });
      return;
    }
    setMetricsImporting(true);
    setNotice(null);
    try {
      // Step 1: generate computed_metrics.json
      const genRun = await api.startRun("generate computed metrics", selectedId, {
        inputPath,
        project_id: selectedId,
        loadCaseId: metricsLoadCaseId.trim() || "load_case_001",
        software: metricsSoftware.trim() || undefined,
      });
      setLastRuntimeRun(genRun);
      appendRunToChatHistory(genRun);
      if (genRun.status !== "completed") {
        setNotice({
          tone: "error",
          title: "计算指标生成失败",
          detail: genRun.errors[0] || genRun.summary || "运行时返回非成功状态。",
        });
        setMetricsImporting(false);
        return;
      }

      // Step 2: refresh CAE summary
      const refreshRun = await api.startRun("refresh cae summary", selectedId, {
        project_id: selectedId,
        overwrite: true,
      });
      setLastRuntimeRun(refreshRun);
      appendRunToChatHistory(refreshRun);
      if (refreshRun.status === "completed") {
        await refreshProjects(selectedId);
        setNotice({
          tone: "success",
          title: "计算指标已导入并刷新摘要",
          detail: refreshRun.summary || "已生成计算指标并重新生成 CAE 结果摘要。",
        });
      } else {
        setNotice({
          tone: "error",
          title: "CAE 摘要刷新失败",
          detail: refreshRun.errors[0] || refreshRun.summary || "运行时返回非成功状态。",
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "导入计算指标失败", detail });
    } finally {
      setMetricsImporting(false);
    }
  }

  async function extractFrdAndRefresh() {
    if (!selectedId || frdExtracting) return;
    const frdPath = frdInputPath.trim();
    if (!frdPath) {
      setNotice({ tone: "info", title: "请输入 FRD 文件路径", detail: "需要提供 CalculiX .frd 结果文件的绝对路径。" });
      return;
    }
    setFrdExtracting(true);
    setNotice(null);
    try {
      const extractRun = await api.startRun("extract solver results", selectedId, {
        project_id: selectedId,
        frdPath: frdPath,
        loadCaseId: frdLoadCaseId.trim() || "load_case_001",
        software: frdSoftware.trim() || "CalculiX",
        refresh_result_summary: true,
      });
      setLastRuntimeRun(extractRun);
      appendRunToChatHistory(extractRun);
      if (extractRun.status !== "completed") {
        setNotice({
          tone: "error",
          title: "FRD 提取失败",
          detail: extractRun.errors[0] || extractRun.summary || "运行时返回非成功状态。",
        });
        setFrdExtracting(false);
        return;
      }
      await refreshProjects(selectedId);
      setNotice({
        tone: "success",
        title: "FRD 结果已提取并刷新摘要",
        detail: extractRun.summary || "已从 .frd 文件提取最大位移和最大 von Mises 应力，并重新生成 CAE 结果摘要。",
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "FRD 提取失败", detail });
    } finally {
      setFrdExtracting(false);
    }
  }

  async function viewArtifact(path: string) {
    if (!selectedId || !path.trim()) return;
    setArtifactViewerPath(path.trim());
    setArtifactViewerBusy(true);
    setArtifactViewerData(null);
    try {
      const data = await api.getProjectArtifact(selectedId, path.trim());
      setArtifactViewerData(data);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setArtifactViewerData({
        path: path.trim(),
        exists: false,
        media_type: "unknown",
        warnings: [detail],
      });
    } finally {
      setArtifactViewerBusy(false);
    }
  }

  async function approveRun() {
    if (!lastRuntimeRun || lastRuntimeRun.status !== "awaiting_approval") return;
    await runBusyTask(async () => {
      const run = await api.approveRun(lastRuntimeRun.run_id);
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      const statusLabel = runtimeStatusLabel(run.status);
      setNotice({
        tone: run.status === "completed" ? "success" : "error",
        title: `运行时审批 — ${statusLabel}`,
        detail: run.summary || run.errors[0] || "已批准并执行",
      });
    });
  }

  async function rejectRun() {
    if (!lastRuntimeRun || lastRuntimeRun.status !== "awaiting_approval") return;
    await runBusyTask(async () => {
      const run = await api.rejectRun(lastRuntimeRun.run_id);
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      setNotice({ tone: "info", title: "运行时审批 — 已拒绝", detail: "已拒绝，待执行工具未运行。" });
    });
  }

  async function createAgentPlanFromPrompt(prompt: string, skipUserMsg = false) {
    setAgentBusy(true);
    setNotice(null);
    try {
      const plan = await api.planAgent({
        message: prompt,
        project_id: selectedId ?? null,
        selected_geometry: agentPayloadGeometry(),
        llm_config: llmConfig,
        dry_run: false,
      });
      setAgentPlan(plan);
      setChatHistory((current) => [
        ...current,
        ...(skipUserMsg ? [] : [{ id: createChatId(), role: "user" as const, body: prompt, createdAt: new Date().toISOString(), mode: "plan" as const }]),
        {
          id: createChatId(),
          role: "assistant",
          body: `[Agent ${plan.mode}] ${plan.reply}`,
          createdAt: new Date().toISOString(),
          mode: "runtime",
          plan: plan.steps.map((step) => ({
            tool: step.tool_name ?? step.id,
            description: step.description || step.tool_name || step.id,
            status: step.approval_required ? "needs_approval" : "pending",
            inputs: step.input ?? {},
            output: null,
          })),
          errors: [...(plan.errors ?? []), ...(plan.warnings ?? [])],
        },
      ]);
      setNotice({
        tone: plan.errors?.length ? "info" : "success",
        title: "Agent 计划已生成",
        detail: plan.preview.warnings[0] || `${plan.steps.length} 个步骤，${plan.requires_approval ? "包含审批闸门" : "无需审批"}`,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "Agent 计划失败", detail });
    } finally {
      setAgentBusy(false);
    }
  }

  async function planAgentChat() {
    const prompt = message.trim();
    if (!prompt) {
      setNotice({ tone: "info", title: "请输入 Agent 目标", detail: "Agent 需要一条建模、检查或分析目标。" });
      return;
    }
    await createAgentPlanFromPrompt(prompt);
  }

  async function runAgentChat(promptOverride?: string) {
    const prompt = (promptOverride ?? message).trim();
    if (!prompt && !agentPlan) {
      if (!promptOverride) setNotice({ tone: "info", title: "请输入 Agent 目标", detail: "可以先生成计划，也可以直接运行 Agent。" });
      return;
    }
    setAgentBusy(true);
    setNotice(null);
    try {
      const result = await api.runAgent({
        message: prompt || agentPlan?.message,
        project_id: selectedId ?? agentPlan?.project_id ?? null,
        selected_geometry: agentPayloadGeometry(),
        llm_config: llmConfig,
        plan: agentPlan ?? undefined,
      });
      setAgentPlan(result.agent);
      setLastRuntimeRun(result.run);
      appendRunToChatHistory(result.run);
      setNotice({
        tone: result.run.status === "completed" ? "success" : result.run.status === "awaiting_approval" ? "info" : "error",
        title: `Agent run — ${runtimeStatusLabel(result.run.status)}`,
        detail: result.run.summary || result.run.errors[0] || result.agent.preview.warnings[0] || result.agent.reply,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      if (!promptOverride) setNotice({ tone: "error", title: "Agent run failed", detail });
      else setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: `Agent error: ${detail}`, createdAt: new Date().toISOString() },
      ]);
    } finally {
      setAgentBusy(false);
    }
  }

  async function probeLocalAgents() {
    const result = await api.listLocalAgentCapabilities().catch(() => ({ adapters: [] as LocalAgentCapability[], available: [] as LocalAgentCapability[] }));
    setChatConnections((current) => mergeLocalAgentCapabilities(current, result.adapters));
    return result;
  }

  function stopAutopilotPoll() {
    if (autopilotPollTimerRef.current !== null) {
      window.clearTimeout(autopilotPollTimerRef.current);
      autopilotPollTimerRef.current = null;
    }
  }

  async function pollAutopilotRun(runId: string) {
    stopAutopilotPoll();
    const poll = async () => {
      try {
        const run = await api.getAutopilotRun(runId);
        setChatHistory((current) => {
          const index = current.findIndex((item) => item.autopilotRun?.run_id === runId);
          if (index === -1) return current;
          const updated = [...current];
          updated[index] = {
            ...updated[index],
            autopilotRun: run,
            errors: run.errors,
            body: summarizeAutopilotRun(run),
          };
          return updated;
        });

        if (run.status === "running") {
          autopilotPollTimerRef.current = window.setTimeout(poll, 3000);
        } else {
          autopilotPollTimerRef.current = null;
          setAgentBusy(false);
          setNotice({
            tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
            title: `${autopilotAgentLabel(run)} — ${run.status}`,
            detail: summarizeAutopilotRun(run),
          });
        }
      } catch (err) {
        autopilotPollTimerRef.current = null;
        setAgentBusy(false);
        const detail = err instanceof Error ? err.message : String(err);
        setNotice({ tone: "error", title: "Agent poll failed", detail });
      }
    };
    autopilotPollTimerRef.current = window.setTimeout(poll, 3000);
  }

  async function runAutopilotAgent(promptOverride?: string, skipUserMsg = false) {
    const prompt = (promptOverride ?? message).trim();
    if (!prompt) {
      if (!promptOverride) setNotice({ tone: "info", title: "请输入 Agent 目标", detail: "Agent 需要一条建模、检查或分析目标。" });
      return;
    }
    const isLlmApi = selectedChatConnection.id === "llm-api";
    const adapters = selectedChatConnection.adapters ?? [];
    const userPreferredId = localAgentConfig.preferredAdapterId;
    let preferredAdapter: LocalAgentCapability | undefined;
    if (!isLlmApi && userPreferredId) {
      preferredAdapter = adapters.find((item) => item.adapter_id === userPreferredId && item.status === "available");
    }
    if (!isLlmApi && !preferredAdapter) {
      preferredAdapter =
        adapters.find((item) => item.adapter_id === "claude-code" && item.status === "available") ??
        adapters.find((item) => item.status === "available");
    }
    if (!isLlmApi && !preferredAdapter) {
      const diagnostic = adapters[0]?.diagnostic || "未检测到可用的 Claude Code 或 Codex CLI 非交互 JSON 模式。";
      setNotice({ tone: "info", title: "Local Agent 不可用", detail: diagnostic });
      if (!skipUserMsg) {
        setChatHistory((current) => [
          ...current,
          { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
        ]);
      }
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: `Local Agent unavailable: ${diagnostic}`, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
      return;
    }
    const adapterId = isLlmApi ? "llm-api" : preferredAdapter!.adapter_id;
    const agentLabel = isLlmApi ? "LLM Agent" : "Local Agent";
    stopAutopilotPoll();
    setAgentBusy(true);
    setNotice(null);
    try {
      const result = await api.runAutopilot({
        message: prompt,
        project_id: selectedId ?? null,
        selected_geometry: agentPayloadGeometry(),
        adapter_id: adapterId,
        ...(isLlmApi ? { llm_config: llmConfig } : {}),
        mode: "autopilot",
        dry_run: false,
      });
      if (!skipUserMsg) {
        setChatHistory((current) => [
          ...current,
          { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
        ]);
      }
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: summarizeAutopilotRun(result),
          createdAt: new Date().toISOString(),
          mode: "runtime",
          autopilotRun: result,
          errors: result.errors,
        },
      ]);
      if (result.status === "running") {
        void pollAutopilotRun(result.run_id);
      } else {
        setAgentBusy(false);
        setNotice({
          tone: result.status === "completed" ? "success" : result.status === "awaiting_approval" ? "info" : "error",
          title: `${agentLabel} — ${result.status}`,
          detail: summarizeAutopilotRun(result),
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: `${agentLabel} run failed`, detail });
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: `${agentLabel} error: ${detail}`, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
      setAgentBusy(false);
    }
  }

  async function updateAutopilotRun(runId: string, action: "approve" | "reject" | "cancel", userMessage?: string) {
    setAgentBusy(true);
    try {
      const result = action === "cancel"
        ? await api.cancelAutopilot(runId)
        : await api.continueAutopilot(runId, action === "approve", userMessage || null);
      setChatHistory((current) => current.map((entry) => (
        entry.autopilotRun?.run_id === runId
          ? {
              ...entry,
              body: summarizeAutopilotRun(result),
              autopilotRun: result,
              errors: result.errors,
            }
          : entry
      )));
      if (result.status === "running") {
        void pollAutopilotRun(runId);
      } else {
        setAgentBusy(false);
        setNotice({
          tone: result.status === "completed" ? "success" : result.status === "cancelled" ? "info" : "error",
          title: `${autopilotAgentLabel(result)} — ${result.status}`,
          detail: summarizeAutopilotRun(result),
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "Agent update failed", detail });
      setAgentBusy(false);
    }
  }

  async function planSelectedChatConnection() {
    if (selectedConnectionBlocked) {
      setNotice({ tone: "info", title: "请选择项目", detail: `${selectedChatConnection.label} 需要当前项目上下文。` });
      return;
    }
    if (selectedChatConnection.id === "llm-api") {
      await runAutopilotAgent();
      return;
    }
    if (selectedChatConnection.id === "local-agent") {
      await runAutopilotAgent();
      return;
    }
    if (selectedChatConnection.id === "mcp-bridge") {
      await submitChat("plan");
      return;
    }
    if (selectedChatConnection.id === "freecad-desktop") {
      const prompt = message.trim();
      await submitRuntime(`inspect geometry through FreeCAD bridge. User request: ${prompt || "inspect current project geometry"}`);
      return;
    }
    await submitRuntime();
  }

  async function runSelectedChatConnection() {
    if (selectedConnectionBlocked) {
      setNotice({ tone: "info", title: "请选择项目", detail: `${selectedChatConnection.label} 需要当前项目上下文。` });
      return;
    }
    if (selectedChatConnection.id === "llm-api") {
      await runAutopilotAgent();
      return;
    }
    if (selectedChatConnection.id === "local-agent") {
      await runAutopilotAgent();
      return;
    }
    if (selectedChatConnection.id === "mcp-bridge") {
      await submitChat("execute");
      return;
    }
    if (selectedChatConnection.id === "freecad-desktop") {
      const prompt = message.trim();
      await submitRuntime(`inspect geometry through FreeCAD bridge. User request: ${prompt || "inspect current project geometry"}`);
      return;
    }
    await submitRuntime();
  }

  async function submitChat(mode: "plan" | "execute", promptOverride?: string, skipUserMsg = false) {
    if (!selectedId) return;
    const prompt = (promptOverride ?? message).trim();
    if (!prompt) {
      if (!skipUserMsg) setNotice({ tone: "info", title: "请输入编排请求", detail: "聊天窗需要一条自然语言指令才能生成计划或执行。" });
      return;
    }
    const agentPrompt = withSelectedGeometryPrompt(prompt);

    if (!skipUserMsg) {
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode },
      ]);
    }

    await runBusyTask(async () => {
      const result = await api.chat(selectedId, agentPrompt, mode === "execute");
      setChat(result);
      if (mode === "execute") {
        await refreshProjects(selectedId);
      }
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: summarizeAssistantReply(result, mode),
          createdAt: new Date().toISOString(),
          mode,
          plan: result.plan,
          errors: result.errors,
          auditLogUrl: result.audit_log_url ?? null,
        },
      ]);
      setNotice({
        tone: mode === "execute" ? "success" : "info",
        title: mode === "execute" ? "已执行安全步骤" : "已生成计划",
        detail: mode === "execute" ? "聊天窗已执行当前请求允许的后端步骤。" : "聊天窗已生成一组可审阅的受保护步骤。",
      });
    });
  }

  function renderAgentToolsPanel() {
    return (
      <AgentPanel
        busy={busy}
        capabilities={capabilities}
        capabilityCategory={capabilityCategory}
        capabilityCategories={capabilityCategories}
        capabilityQuery={capabilityQuery}
        filteredCapabilities={filteredCapabilities}
        selectedCapability={selectedCapability}
        capabilityPreview={capabilityPreview}
        workflows={workflows}
        selectedWorkflow={selectedWorkflow}
        benchmarkScenarios={benchmarkScenarios}
        selectedScenarioId={selectedScenarioId}
        benchmarkRun={benchmarkRun}
        benchmarkBusy={benchmarkBusy}
        llmConfig={llmConfig}
        llmReady={llmReady}
        summary={summary}
        setCapabilityCategory={setCapabilityCategory}
        setCapabilityQuery={setCapabilityQuery}
        setSelectedCapabilityName={setSelectedCapabilityName}
        setCapabilityPreview={setCapabilityPreview}
        setSelectedWorkflowId={setSelectedWorkflowId}
        setSelectedScenarioId={setSelectedScenarioId}
        refreshAgentWorkbench={refreshAgentWorkbench}
        previewSelectedCapability={previewSelectedCapability}
        runSelectedWorkflow={runSelectedWorkflow}
        runBenchmark={runBenchmark}
      />
    );
  }

  function renderCaePanel() {
    return (
      <CaePanel
        summary={summary}
        selectedId={selectedId}
        caeSummary={caeSummary}
        hasCaeContext={hasCaeContext}
        hasCaeResultArtifacts={hasCaeResultArtifacts}
        renderableCaeFields={renderableCaeFields}
        selectedCaeField={selectedCaeField}
        fieldDescriptor={fieldDescriptor}
        caeRefreshing={caeRefreshing}
        caeReviewReport={caeReviewReport}
        caeReviewLoading={caeReviewLoading}
        metricsInputPath={metricsInputPath}
        metricsLoadCaseId={metricsLoadCaseId}
        metricsSoftware={metricsSoftware}
        metricsImporting={metricsImporting}
        frdInputPath={frdInputPath}
        frdLoadCaseId={frdLoadCaseId}
        frdSoftware={frdSoftware}
        frdExtracting={frdExtracting}
        artifactViewerPath={artifactViewerPath}
        artifactViewerData={artifactViewerData}
        artifactViewerBusy={artifactViewerBusy}
        setSelectedCaeField={setSelectedCaeField}
        setMetricsInputPath={setMetricsInputPath}
        setMetricsLoadCaseId={setMetricsLoadCaseId}
        setMetricsSoftware={setMetricsSoftware}
        setFrdInputPath={setFrdInputPath}
        setFrdLoadCaseId={setFrdLoadCaseId}
        setFrdSoftware={setFrdSoftware}
        setArtifactViewerPath={setArtifactViewerPath}
        refreshCaeSummary={refreshCaeSummary}
        generateCaeReviewReport={generateCaeReviewReport}
        importMetricsAndRefresh={importMetricsAndRefresh}
        extractFrdAndRefresh={extractFrdAndRefresh}
        viewArtifact={viewArtifact}
      />
    );
  }

  function renderRecommendationsPanel() {
    return <RecommendationsPanel selectedId={selectedId} />;
  }

  function renderCopilotLoopPanel() {
    return (
      <CopilotLoopPanel
        selectedId={selectedId}
        onSelectProject={(projectId) => {
          void refreshProjects(projectId);
        }}
      />
    );
  }

  function renderIntentPlannerPanel() {
    return <IntentPlannerCard selectedId={selectedId} />;
  }

  const pointerContextValue = useMemo(
    () => ({ highlightedFaceIds, onClickPointer: handlePointerClick }),
    [highlightedFaceIds, brepSnapshot], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <PointerProvider value={pointerContextValue}>
      <NoticeCenter
        notice={notice ?? runtimeNotice}
        onDismiss={() => {
          if (notice) {
            setNotice(null);
          } else {
            setRuntimeNotice(null);
          }
        }}
      />
      <div className="app-shell workbench-shell">
        <ViewerPane
          runtimeReady={runtimeReady}
          runtimeProvider={runtimeProvider}
          runtimeDetail={runtimeDetail}
          selectedProject={selectedProject}
          selectedFile={selectedFile}
          summary={summary}
          validationState={validationState}
          effectiveViewerFormat={effectiveViewerFormat}
          activeFieldDescriptor={activeFieldDescriptor}
          effectiveViewerUrl={effectiveViewerUrl}
          onOpenGlobalSettings={() => setGlobalSettingsOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
          pickedFaces={pickedFaces}
          onAddPickedFace={addPickedFace}
          onClearPickedFaces={clearPickedFaces}
          onInsertToChat={insertToChat}
          onRunPreprocess={runPreprocessFromPointer}
          cadGenerationProgress={cadGenerationProgress}
          highlightedFaceIds={highlightedFaceIds}
          brepSnapshot={brepSnapshot}
          onClearHighlightedFaces={clearHighlightedFaces}
        />

        <WorkbenchRightRail
          ref={sidePaneRef}
          activeMode={activeControlPaneMode}
          activeModeDetail={activeControlPaneModeDetail}
          modes={activeControlPaneModes}
          onModeChange={handleControlPaneModeChange}
          onOpenGlobalSettings={() => setGlobalSettingsOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
        >
          {showProjectPanel ? (
            <ProjectPanel
              projectName={projectName}
              onProjectNameChange={setProjectName}
              busy={busy}
              selectedFile={selectedFile}
              onSelectedFileChange={setSelectedFile}
              selectedId={selectedId}
              selectedProject={selectedProject}
              projects={projects}
              stages={stages}
              summary={summary}
              aiSummary={aiSummary}
              semanticSections={semanticSections}
              integrationBody={integrationBody}
              runBusyTask={runBusyTask}
              refreshProjects={refreshProjects}
              setNotice={setNotice}
              runWorkbenchImportFlow={runWorkbenchImportFlow}
              runProjectAction={runProjectAction}
            />
          ) : null}

          {showDebugPanel ? (
            <DebugPanel
              sections={[
                { id: "tools", label: "Tools", children: renderAgentToolsPanel() },
                { id: "cae", label: "CAE", children: renderCaePanel() },
                { id: "recommendations", label: "Recommendations", children: renderRecommendationsPanel() },
                { id: "loop", label: "Loop", children: renderCopilotLoopPanel() },
                { id: "planner", label: "Planner", children: renderIntentPlannerPanel() },
              ]}
            />
          ) : null}

          {showLegacyAgentPanel ? renderAgentToolsPanel() : null}

          {showLegacyCaePanel ? renderCaePanel() : null}

          {showRecommendationsPanel ? renderRecommendationsPanel() : null}

          {showCopilotLoopPanel ? renderCopilotLoopPanel() : null}

          {showIntentPlannerPanel ? renderIntentPlannerPanel() : null}

          {showAgentWorkbench ? (
            <SelectionInspectorCard
              pickedFaces={pickedFaces}
              onClear={clearPickedFaces}
              onSetPrompt={setMessage}
              onUseInPrompt={insertToChat}
            />
          ) : null}

          {showChatPanel ? (
            <ChatPanel
              chatConnections={chatConnections}
              selectedChatConnectionId={selectedChatConnectionId}
              selectedConnectionBlocked={selectedConnectionBlocked}
              selectedProject={selectedProject}
              selectedId={selectedId}
              chatBusy={chatBusy}
              cadGenerating={cadGenerating}
              cadGenerationProgress={cadGenerationProgress}
              chatHistory={chatHistory}
              chatLogRef={chatLogRef}
              message={message}
              lastRuntimeRun={lastRuntimeRun}
              simulationPending={simulationPending}
              simulationProgress={simulationProgress}
              setSelectedChatConnectionId={setSelectedChatConnectionId}
              setSettingsOpen={setSettingsOpen}
              setMessage={setMessage}
              sendUnified={sendUnified}
              viewArtifact={viewArtifact}
              approveRun={approveRun}
              rejectRun={rejectRun}
              approveAutopilot={(runId) => void updateAutopilotRun(runId, "approve")}
              rejectAutopilot={(runId) => void updateAutopilotRun(runId, "reject")}
              cancelAutopilot={(runId) => void updateAutopilotRun(runId, "cancel")}
              approveSimulation={() => void executeSimulation()}
              rejectSimulation={() => setSimulationPending(false)}
              heatmapActive={heatmapActive}
              heatmapRange={heatmapRange}
              onViewHeatmap={() => void viewStressHeatmap()}
              recentPickedFaces={pickedFaces}
            />
          ) : null}
        </WorkbenchRightRail>
      </div>

      <RuntimeSettingsDrawer
        open={settingsOpen}
        runtime={runtime}
        runtimeDraft={runtimeDraft}
        runtimeBusy={runtimeBusy}
        runtimeNotice={null}
        runtimeProvider={runtimeProvider}
        runtimeReady={runtimeReady}
        llmConfig={llmConfig}
        llmReady={llmReady}
        directApiKey={directApiKey}
        onDirectApiKeyChange={updateDirectApiKey}
        onClose={() => setSettingsOpen(false)}
        onDraftChange={updateRuntimeDraft}
        onLlmChange={updateLlmConfig}
        onLlmPreset={applyLlmProviderPreset}
        onLlmRestore={restoreDefaultLlmConfig}
        onLlmTestResult={handleLlmTestResult}
        onTest={() => void runRuntimeTask("test", () => api.testRuntimeConfig(runtimeDraft!))}
        onSave={() => void runRuntimeTask("save", () => api.updateRuntimeConfig(runtimeDraft!))}
        onRestore={restoreRuntimeDefaults}
        localAgentConfig={localAgentConfig}
        localAdapters={selectedChatConnection.adapters ?? []}
        onLocalAgentChange={(key, value) => setLocalAgentConfig((prev) => ({ ...prev, [key]: value }))}
        onProbeLocalAgents={() => void probeLocalAgents()}
      />
      <GlobalSettingsDrawer open={globalSettingsOpen} onClose={() => setGlobalSettingsOpen(false)} />
    </PointerProvider>
  );
}
