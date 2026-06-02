import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import {
  BASE_STAGES,
  CHAT_CONNECTION_ID_STORAGE_KEY,
  DEFAULT_CHAT_CONNECTIONS,
  EMPTY_CAE_FIELDS,
} from "../appConstants";
import type { Notice, ShapeIrObject, StageItem, StageState } from "../appTypes";
import {
  createChatId,
  projectViewerUrl,
  resolveAssetFormat,
  withAssetVersion,
} from "../appUtils";
import type {
  ArtifactResponse,
  ChatConnection,
  ProjectRecord,
  ProjectSummary,
  RuntimeConfigSnapshot,
  SolverFieldDescriptor,
} from "../types";
import { useAgentActivityStream } from "./useAgentActivityStream";
import { useAgentRuns } from "./useAgentRuns";
import { mergeLocalAgentCapabilities } from "./workbenchHelpers";
import { resolveEngineeringIntent } from "./engineeringIntent";
import { buildFallbackSummary } from "./projectSummary";
import { useEngineeringActions } from "./useEngineeringActions";
import { useGeometryPointers } from "./useGeometryPointers";
import { useObjectRegistry } from "./useObjectRegistry";
import { useRuntimeSettings } from "./useRuntimeSettings";
import { useBrowserStorageState } from "./useBrowserStorageState";
import { useChatSessions } from "./useChatSessions";
import { useChatTranscript } from "./useChatTranscript";

export function useWorkbenchApp() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [projectName, setProjectName] = useState("STEP workbench project");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [stages, setStages] = useState<StageItem[]>(BASE_STAGES);
  const [selectedCaeField, setSelectedCaeField] = useState("stress");
  const [fieldDescriptor, setFieldDescriptor] = useState<SolverFieldDescriptor | null>(null);
  const [chatConnections, setChatConnections] = useState<ChatConnection[]>(DEFAULT_CHAT_CONNECTIONS);
  const [selectedChatConnectionId, setSelectedChatConnectionId] = useBrowserStorageState<string>(
    CHAT_CONNECTION_ID_STORAGE_KEY,
    "llm-api",
    { storage: "local" },
  );
  const [artifactViewerPath, setArtifactViewerPath] = useState("");
  const [artifactViewerData, setArtifactViewerData] = useState<ArtifactResponse | null>(null);
  const [artifactViewerBusy, setArtifactViewerBusy] = useState(false);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const llmReadyRef = useRef(false);
  const {
    chatSessions,
    activeSessionId,
    activeSession,
    sessionsReady,
    createChatSession,
    selectChatSession,
    updateActiveSessionFromRun,
    handleLiveChatSessionChange,
    handleLiveChatSessionDelete,
    renameActiveSessionForPrompt,
  } = useChatSessions({ selectedId });
  const {
    chatHistory,
    agentEvents,
    setChatHistory,
    setPersistentChatHistory,
    handleLiveChatMessage,
    handleLiveAgentEvent,
    appendRunToChatHistory,
    clearAgentEvents,
    streamingState,
    clearStreamingState,
  } = useChatTranscript({
    selectedId,
    activeSessionId,
    activeRunId: activeSession?.active_run_id,
    sessionsReady,
    onAutopilotRunUpdate: updateActiveSessionFromRun,
  });
  const runtimeSettings = useRuntimeSettings({ setSummary });
  const {
    runtime,
    runtimeDraft,
    runtimeNotice,
    runtimeBusy,
    llmConfig,
    llmReady,
    localAgentConfig,
    apiKey,
    apiKeyHydrated,
    runtimeReady,
    runtimeProvider,
    setRuntimeNotice,
    setLocalAgentConfig,
    applyRuntimeSnapshot,
    updateApiKey,
    updateRuntimeDraft,
    restoreRuntimeDefaults,
    runRuntimeTask,
    updateLlmConfig,
    handleLlmTestResult,
    applyLlmProviderPreset,
    restoreDefaultLlmConfig,
  } = runtimeSettings;
  llmReadyRef.current = llmReady;

  const {
    cadPreviewUrl,
    cadPreviewFormat,
    cadGenerating,
    cadGenResult,
    cadGenerationProgress,
    setCadGenerationProgress,
    simulationPending,
    simulationProgress,
    setSimulationPending,
    heatmapActive,
    heatmapRange,
    refreshViewerAsset,
    resetProjectDerivedState,
    executePreprocessFromPrompt,
    executeCadFromPrompt,
    executeSimulation,
    viewStressHeatmap,
  } = useEngineeringActions({
    selectedId,
    apiKey,
    llmConfig,
    refreshProjects,
    setBusy,
    setChatHistory: setPersistentChatHistory,
  });
  const {
    pickedFaces,
    highlightedFaceIds,
    brepSnapshot,
    addPickedFace,
    clearPickedFaces,
    insertToChat,
    runPreprocessFromPointer,
    clearHighlightedFaces,
    setHighlightedFacesExact,
    selectedGeometryContext,
    withSelectedGeometryPrompt,
    agentPayloadGeometry,
    pointerContextValue,
  } = useGeometryPointers({
    selectedId,
    // Bumps whenever the selected project's geometry is rebuilt (e.g. an agent
    // cad.execute_build123d). Forces the B-Rep snapshot to re-fetch so the
    // face highlight + pick work on freshly-built geometry without re-selecting.
    geometryVersion: projects.find((item) => item.id === selectedId)?.updated_at ?? null,
    setMessage,
    setNotice,
    executePreprocessFromPrompt,
  });

  // Shape IR object registry: maps Shape IR nodes <-> viewer-selectable entities.
  const geometryVersion = projects.find((item) => item.id === selectedId)?.updated_at ?? null;
  const { objects: shapeIrObjects, verification: shapeIrVerification } = useObjectRegistry({
    selectedId,
    geometryVersion,
  });
  const [selectedShapeIrNodeId, setSelectedShapeIrNodeId] = useState<string | null>(null);
  useEffect(() => {
    setSelectedShapeIrNodeId(null);
  }, [selectedId]);
  const selectShapeIrNode = useCallback(
    (node: ShapeIrObject) => {
      setSelectedShapeIrNodeId(node.node_id);
      setHighlightedFacesExact(node.viewer_selectable_ids ?? []);
    },
    [setHighlightedFacesExact],
  );

  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedId) ?? null,
    [projects, selectedId],
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
  const selectedChatConnection = useMemo(
    () => chatConnections.find((item) => item.id === selectedChatConnectionId) ?? chatConnections[0] ?? DEFAULT_CHAT_CONNECTIONS[0],
    [chatConnections, selectedChatConnectionId],
  );
  const selectedConnectionBlocked = selectedChatConnection.requires_project && !selectedId;
  const {
    agentBusy,
    lastRuntimeRun,
    setAgentBusy,
    stopAutopilotPoll,
    createAgentPlanFromPrompt,
    runAgentChat,
    probeLocalAgents,
    runAutopilotAgent,
    updateAutopilotRun,
    approveRun,
    rejectRun,
  } = useAgentRuns({
    selectedId,
    activeSessionId,
    message,
    selectedChatConnection,
    localAgentConfig,
    llmConfig,
    apiKey,
    agentPayloadGeometry,
    appendRunToChatHistory,
    runBusyTask,
    setNotice,
    setChatHistory: setPersistentChatHistory,
    setChatConnections,
    onAutopilotRunUpdate: updateActiveSessionFromRun,
  });
  const {
    liveSyncStatus,
    liveSyncDetail,
    liveSyncLastEventAt,
  } = useAgentActivityStream({
    selectedId,
    activeSessionId,
    agentBusy,
    cadGenerationProgress,
    refreshProjects,
    refreshViewerAsset,
    stopAutopilotPoll,
    onAutopilotRunUpdate: updateActiveSessionFromRun,
    onChatMessage: handleLiveChatMessage,
    onChatSessionChange: handleLiveChatSessionChange,
    onChatSessionDelete: handleLiveChatSessionDelete,
    onAgentEvent: handleLiveAgentEvent,
    setAgentBusy,
    setNotice,
    setChatHistory: setPersistentChatHistory,
    setCadGenerationProgress,
    clearStreamingState,
  });
  const chatBusy = agentBusy || busy;
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
      applyRuntimeSnapshot(runtimeSnapshot);
      const [nextConnections, localAgents] = await Promise.all([
        api.listAgentConnections().catch(() => DEFAULT_CHAT_CONNECTIONS),
        api.listLocalAgentCapabilities().catch(() => ({ adapters: [], available: [] })),
      ]);
      if (cancelled) return;
      setChatConnections(mergeLocalAgentCapabilities(
        nextConnections.length ? nextConnections : DEFAULT_CHAT_CONNECTIONS,
        localAgents.adapters,
        llmReadyRef.current,
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
    setChatConnections((current) => mergeLocalAgentCapabilities(current, undefined, llmReady));
  }, [llmReady]);

  useEffect(() => {
    resetProjectDerivedState();
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

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
      setNotice({ tone: "error", title: "Operation failed", detail });
    } finally {
      setBusy(false);
    }
  }

  async function ensureProject() {
    if (selectedId) return selectedId;
    const baseName = selectedFile?.name.replace(/\.(step|stp|aieng)$/i, "") || projectName || "STEP workbench project";
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
            ? "Preview unavailable: no embedded GLB/STL preview was found, and STEP preview conversion is not available."
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
            : "STEP imported and validated, but preview export still needs an embedded GLB/STL asset or a STEP preview converter.",
      });
    });
  }

  async function sendUnified(promptOverride?: string) {
    clearAgentEvents();
    clearStreamingState();
    const prompt = (promptOverride ?? message).trim();
    if (!prompt) return;
    renameActiveSessionForPrompt(prompt);
    if (selectedChatConnection.id === "local-agent" || selectedChatConnection.id === "llm-api") {
      const activeAutopilotRun = chatHistory
        .slice()
        .reverse()
        .find((item) => item.autopilotRun && ["running", "awaiting_approval", "chatting", "blocked"].includes(item.autopilotRun.status))?.autopilotRun;
      if (activeAutopilotRun) {
        setPersistentChatHistory((current) => [
          ...current,
          {
            id: createChatId(),
            role: "user",
            body: prompt,
            createdAt: new Date().toISOString(),
            mode: "runtime",
          },
        ]);
        setMessage("");
        const action = activeAutopilotRun.status === "running"
          ? "follow-up"
          : "reply";
        await updateAutopilotRun(activeAutopilotRun.run_id, action, prompt);
        return;
      }
      setPersistentChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
      setMessage("");
      await runAutopilotAgent(prompt, true);
      return;
    }
    const agentPrompt = withSelectedGeometryPrompt(prompt);

    setPersistentChatHistory((current) => [
      ...current,
      { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString() },
    ]);
    setMessage("");

    const plannedAction = await resolveEngineeringIntent({
      selectedId,
      prompt: agentPrompt,
      hasCadResult: Boolean(cadGenResult),
    });
    const cadIntent = plannedAction?.intent ?? null;
    if (cadIntent === "simulate") {
      setSimulationPending(true);
      setPersistentChatHistory((current) => [
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
    const el = chatLogRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [chatHistory]);

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

  return {
    pointerContextValue,
    notice,
    runtimeNotice,
    setNotice,
    setRuntimeNotice,
    selectedProject,
    chatSessions,
    activeSessionId,
    activeSession,
    sidebarCollapsed,
    setSidebarCollapsed,
    createChatSession,
    selectChatSession,
    setSettingsOpen,
    projectName,
    setProjectName,
    busy,
    selectedFile,
    setSelectedFile,
    selectedId,
    projects,
    stages,
    runBusyTask,
    refreshProjects,
    runWorkbenchImportFlow,
    runtimeReady,
    runtimeProvider,
    effectiveViewerFormat,
    activeFieldDescriptor,
    effectiveViewerUrl,
    pickedFaces,
    addPickedFace,
    clearPickedFaces,
    insertToChat,
    runPreprocessFromPointer,
    cadGenerationProgress,
    highlightedFaceIds,
    brepSnapshot,
    clearHighlightedFaces,
    shapeIrObjects,
    shapeIrVerification,
    selectedShapeIrNodeId,
    selectShapeIrNode,
    chatConnections,
    selectedChatConnectionId,
    selectedConnectionBlocked,
    chatBusy,
    cadGenerating,
    chatHistory,
    agentEvents,
    chatLogRef,
    message,
    lastRuntimeRun,
    simulationPending,
    simulationProgress,
    setSelectedChatConnectionId,
    setMessage,
    sendUnified,
    viewArtifact,
    approveRun,
    rejectRun,
    updateAutopilotRun,
    executeSimulation,
    setSimulationPending,
    heatmapActive,
    heatmapRange,
    viewStressHeatmap,
    settingsOpen,
    runtime,
    runtimeDraft,
    runtimeBusy,
    llmConfig,
    llmReady,
    apiKey,
    apiKeyHydrated,
    updateApiKey,
    updateRuntimeDraft,
    updateLlmConfig,
    applyLlmProviderPreset,
    restoreDefaultLlmConfig,
    handleLlmTestResult,
    runRuntimeTask,
    restoreRuntimeDefaults,
    localAgentConfig,
    selectedChatConnection,
    probeLocalAgents,
    setLocalAgentConfig,
    globalSettingsOpen,
    setGlobalSettingsOpen,
    streamingState,
  };
}
