import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from "react";

import { api, type ChatSession, type PersistedChatMessage } from "../api";
import {
  BASE_STAGES,
  DEFAULT_CHAT_CONNECTIONS,
  EMPTY_CAE_FIELDS,
} from "../appConstants";
import type { ChatHistoryItem, Notice, ShapeIrObject, StageItem, StageState } from "../appTypes";
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
  RuntimeRun,
  SolverFieldDescriptor,
  AutopilotRunState,
} from "../types";
import { useAgentActivityStream } from "./useAgentActivityStream";
import { useAgentRuns } from "./useAgentRuns";
import { mergeLocalAgentCapabilities, summarizeAutopilotRun } from "./workbenchHelpers";
import { resolveEngineeringIntent } from "./engineeringIntent";
import { buildFallbackSummary } from "./projectSummary";
import { runtimeRunChatEntry } from "./runtimeRunChat";
import { useEngineeringActions } from "./useEngineeringActions";
import { useGeometryPointers } from "./useGeometryPointers";
import { useObjectRegistry } from "./useObjectRegistry";
import { useRuntimeSettings } from "./useRuntimeSettings";

export function useWorkbenchApp() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [projectName, setProjectName] = useState("STEP workbench project");
  const [message, setMessage] = useState("Check the current project status and generate a reviewable engineering execution plan.");
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [stages, setStages] = useState<StageItem[]>(BASE_STAGES);
  const [selectedCaeField, setSelectedCaeField] = useState("stress");
  const [fieldDescriptor, setFieldDescriptor] = useState<SolverFieldDescriptor | null>(null);
  const [chatConnections, setChatConnections] = useState<ChatConnection[]>(DEFAULT_CHAT_CONNECTIONS);
  const [selectedChatConnectionId, setSelectedChatConnectionId] = useState<string>("llm-api");
  const [artifactViewerPath, setArtifactViewerPath] = useState("");
  const [artifactViewerData, setArtifactViewerData] = useState<ArtifactResponse | null>(null);
  const [artifactViewerBusy, setArtifactViewerBusy] = useState(false);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const persistedChatIdsRef = useRef<Set<string>>(new Set());
  // Tracks which project the currently-loaded chatSessions/activeSessionId belong
  // to. Set synchronously (a ref, not state) so the message-fetch effect can tell,
  // within the same commit as a project switch, that activeSessionId is still the
  // PREVIOUS project's session — and skip fetching it (which would 404). Without
  // this, both the session-reset and message-fetch effects run in one commit and
  // the fetch sees the stale session id for one render.
  const sessionsProjectRef = useRef<string | null>(null);
  const persistChatItem = useCallback((item: ChatHistoryItem) => {
    if (!selectedId || !activeSessionId || persistedChatIdsRef.current.has(item.id)) return;
    persistedChatIdsRef.current.add(item.id);
    void api.saveChatMessage(selectedId, {
      session_id: activeSessionId,
      role: item.role,
      content: item.body,
      mode: item.mode,
      created_at: item.createdAt,
      extra: chatItemExtra(item),
    }).catch(() => {
      persistedChatIdsRef.current.delete(item.id);
    });
  }, [activeSessionId, selectedId]);
  const setPersistentChatHistory = useCallback((value: SetStateAction<ChatHistoryItem[]>) => {
    setChatHistory((current) => {
      const next = typeof value === "function" ? value(current) : value;
      const currentIds = new Set(current.map((item) => item.id));
      for (const item of next) {
        if (!currentIds.has(item.id)) persistChatItem(item);
      }
      return next;
    });
  }, [persistChatItem]);
  const runtimeSettings = useRuntimeSettings({ setSummary });
  const {
    runtime,
    runtimeDraft,
    runtimeNotice,
    runtimeBusy,
    llmConfig,
    llmReady,
    localAgentConfig,
    directApiKey,
    runtimeReady,
    runtimeProvider,
    setRuntimeNotice,
    setLocalAgentConfig,
    applyRuntimeSnapshot,
    updateDirectApiKey,
    updateRuntimeDraft,
    restoreRuntimeDefaults,
    runRuntimeTask,
    updateLlmConfig,
    handleLlmTestResult,
    applyLlmProviderPreset,
    restoreDefaultLlmConfig,
  } = runtimeSettings;

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
    directApiKey,
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
  const activeSession = useMemo(
    () => chatSessions.find((item) => item.id === activeSessionId) ?? null,
    [activeSessionId, chatSessions],
  );
  const updateActiveSessionFromRun = useCallback((run: AutopilotRunState) => {
    const projectId = run.project_id ?? selectedId;
    const sessionId = run.session_id ?? activeSessionId;
    if (!projectId || !sessionId) return;
    const status =
      run.status === "running" || run.status === "awaiting_approval" || run.status === "chatting"
        ? "running"
        : run.status === "completed"
          ? "completed"
          : run.status === "cancelled"
            ? "cancelled"
            : run.status === "failed"
              ? "failed"
              : "idle";
    setChatSessions((current) => current.map((session) => (
      session.id === sessionId
        ? { ...session, status, active_run_id: run.run_id, updated_at: run.updated_at }
        : session
    )));
  }, [activeSessionId, selectedId]);
  const handleLiveChatMessage = useCallback((messageRecord: PersistedChatMessage) => {
    setChatHistory((current) => upsertPersistedChatMessage(current, messageRecord));
    persistedChatIdsRef.current.add(`db-${messageRecord.id}`);
    const clientId = getPersistedClientId(messageRecord);
    if (clientId) persistedChatIdsRef.current.add(clientId);
  }, []);
  const handleLiveChatSessionChange = useCallback((session: ChatSession) => {
    setChatSessions((current) => {
      const index = current.findIndex((item) => item.id === session.id);
      if (index === -1) return [session, ...current];
      const updated = [...current];
      updated[index] = session;
      return updated.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    });
  }, []);
  const handleLiveChatSessionDelete = useCallback((sessionId: string) => {
    setChatSessions((current) => current.filter((session) => session.id !== sessionId));
    setActiveSessionId((current) => current === sessionId ? null : current);
  }, []);
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
    setAgentBusy,
    setNotice,
    setChatHistory: setPersistentChatHistory,
    setCadGenerationProgress,
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

  async function sendUnified() {
    const prompt = message.trim();
    if (!prompt) return;
    if (selectedId && activeSessionId && activeSession && /^default session|new session$/i.test(activeSession.title)) {
      const title = prompt.length > 54 ? `${prompt.slice(0, 51)}...` : prompt;
      setChatSessions((current) => current.map((session) => (
        session.id === activeSessionId ? { ...session, title } : session
      )));
      void api.updateChatSession(selectedId, activeSessionId, { title }).catch(() => {});
    }
    if (selectedChatConnection.id === "local-agent" || selectedChatConnection.id === "llm-api") {
      const chattingRun = chatHistory
        .slice()
        .reverse()
        .find((item) => item.autopilotRun?.status === "chatting")?.autopilotRun;
      if (chattingRun) {
        setPersistentChatHistory((current) => [
          ...current,
          { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
        ]);
        setMessage("");
        await updateAutopilotRun(chattingRun.run_id, "approve", prompt);
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
    if (!selectedId) {
      persistedChatIdsRef.current = new Set();
      sessionsProjectRef.current = null;
      setChatSessions([]);
      setActiveSessionId(null);
      setChatHistory([]);
      return;
    }
    // Reset session state immediately so the next effect does not fire
    // getChatMessages with a stale session id from the previous project.
    // Invalidate the ref synchronously: until this project's sessions load,
    // the message-fetch effect sees ref !== selectedId and skips.
    sessionsProjectRef.current = null;
    setActiveSessionId(null);
    setChatHistory([]);
    let cancelled = false;
    void api.getChatSessions(selectedId)
      .then((sessions) => {
        if (cancelled) return;
        sessionsProjectRef.current = selectedId;
        setChatSessions(sessions);
        setActiveSessionId((current) => (
          current && sessions.some((session) => session.id === current)
            ? current
            : sessions[0]?.id ?? null
        ));
      })
      .catch(() => {
        if (!cancelled) {
          setChatSessions([]);
          setActiveSessionId(null);
          setChatHistory([]);
        }
      });
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !activeSessionId) {
      persistedChatIdsRef.current = new Set();
      setChatHistory([]);
      return;
    }
    // Guard against the project-switch race: activeSessionId may still hold the
    // previous project's session for one render. Only fetch once this project's
    // sessions have loaded (ref === selectedId), so we never query a session id
    // that belongs to another project (which the backend correctly 404s).
    if (sessionsProjectRef.current !== selectedId) {
      return;
    }
    const ACTIVE_AUTOPILOT_STATUSES = new Set(["running", "awaiting_approval", "chatting"]);
    let cancelled = false;
    void api.getChatMessages(selectedId, activeSessionId)
      .then((messages) => {
        if (cancelled) return;
        const items = messages.map(persistedMessageToChatItem);
        persistedChatIdsRef.current = new Set(items.map((item) => item.id));
        setChatHistory(items);
        // Refresh any stale in-progress autopilot runs that were snapshotted
        // into the DB before the run reached a terminal state.
        const staleRunIds = new Set<string>();
        for (const item of items) {
          if (item.autopilotRun?.run_id && ACTIVE_AUTOPILOT_STATUSES.has(item.autopilotRun.status)) {
            staleRunIds.add(item.autopilotRun.run_id);
          }
        }
        for (const runId of staleRunIds) {
          api.getAutopilotRun(runId)
            .then((run) => {
              if (!cancelled) {
                setChatHistory((current) => upsertAutopilotChatItem(current, run));
              }
            })
            .catch(() => {
              if (cancelled) return;
              setChatHistory((current) => current.map((item) => {
                if (item.autopilotRun?.run_id !== runId) return item;
                if (!ACTIVE_AUTOPILOT_STATUSES.has(item.autopilotRun.status)) return item;
                return {
                  ...item,
                  body: `${item.body}\n\n*(Run state is no longer available; status may be stale.)*`,
                  autopilotRun: {
                    ...item.autopilotRun,
                    status: "failed" as const,
                    errors: [...(item.autopilotRun.errors || []), "Run state is no longer available."],
                  },
                };
              }));
            });
        }
      })
      .catch(() => {
        persistedChatIdsRef.current = new Set();
        if (!cancelled) setChatHistory([]);
      });
    return () => { cancelled = true; };
  }, [activeSessionId, selectedId]);

  useEffect(() => {
    if (!activeSession?.active_run_id) return;
    const ACTIVE_AUTOPILOT_STATUSES = new Set(["running", "awaiting_approval", "chatting"]);
    let cancelled = false;
    void api.getAutopilotRun(activeSession.active_run_id)
      .then((run) => {
        if (cancelled) return;
        updateActiveSessionFromRun(run);
        setChatHistory((current) => upsertAutopilotChatItem(current, run));
      })
      .catch(() => {
        if (cancelled) return;
        const runId = activeSession.active_run_id;
        setChatHistory((current) => current.map((item) => {
          const run = item.autopilotRun;
          if (!run || run.run_id !== runId) return item;
          if (!ACTIVE_AUTOPILOT_STATUSES.has(run.status)) return item;
          return {
            ...item,
            body: `${item.body}\n\n*(Run state is no longer available; status may be stale.)*`,
            autopilotRun: {
              ...run,
              status: "failed" as const,
              errors: [...(run.errors || []), "Run state is no longer available."],
            },
          };
        }));
      });
    return () => { cancelled = true; };
  }, [activeSession?.active_run_id, updateActiveSessionFromRun]);

  useEffect(() => {
    if (!chatLogRef.current) return;
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [chatHistory]);

  function appendRunToChatHistory(run: RuntimeRun) {
    setPersistentChatHistory((current) => [...current, runtimeRunChatEntry(run)]);
  }

  async function createChatSession(title?: string) {
    if (!selectedId) return;
    const session = await api.createChatSession(selectedId, title ?? "New session");
    setChatSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]);
    setActiveSessionId(session.id);
    persistedChatIdsRef.current = new Set();
    setChatHistory([]);
  }

  function selectChatSession(sessionId: string) {
    setActiveSessionId(sessionId);
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
    directApiKey,
    updateDirectApiKey,
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
  };
}

function chatItemExtra(item: ChatHistoryItem): Record<string, unknown> | undefined {
  const {
    id: _id,
    role: _role,
    body: _body,
    createdAt: _createdAt,
    mode: _mode,
    ...extra
  } = item;
  const entries = Object.entries(extra).filter(([, value]) => value !== undefined);
  return Object.fromEntries([["client_id", item.id], ...entries]);
}

function persistedMessageToChatItem(message: PersistedChatMessage): ChatHistoryItem {
  const { client_id: _clientId, ...extra } = (message.extra ?? {}) as Partial<ChatHistoryItem> & { client_id?: string };
  const role = message.role === "assistant" ? "assistant" : "user";
  const mode =
    message.mode === "plan" || message.mode === "execute" || message.mode === "runtime"
      ? message.mode
      : undefined;
  return {
    ...extra,
    id: `db-${message.id}`,
    role,
    body: message.content,
    createdAt: message.created_at,
    mode,
  };
}

function getPersistedClientId(message: PersistedChatMessage): string | null {
  const clientId = (message.extra as { client_id?: unknown } | null | undefined)?.client_id;
  return typeof clientId === "string" && clientId ? clientId : null;
}

function upsertPersistedChatMessage(current: ChatHistoryItem[], message: PersistedChatMessage): ChatHistoryItem[] {
  const dbId = `db-${message.id}`;
  const clientId = getPersistedClientId(message);
  const index = current.findIndex((item) => item.id === dbId || (clientId ? item.id === clientId : false));
  if (index === -1) return [...current, persistedMessageToChatItem(message)];
  const updated = [...current];
  updated[index] = {
    ...updated[index],
    ...persistedMessageToChatItem(message),
    id: updated[index].id,
  };
  return updated;
}

function autopilotRunToChatItem(run: AutopilotRunState): ChatHistoryItem {
  return {
    id: `run-${run.run_id}`,
    role: "assistant",
    body: summarizeAutopilotRun(run),
    createdAt: run.created_at,
    mode: "runtime",
    autopilotRun: run,
    errors: run.errors,
  };
}

function upsertAutopilotChatItem(current: ChatHistoryItem[], run: AutopilotRunState): ChatHistoryItem[] {
  const index = current.findIndex((item) => item.autopilotRun?.run_id === run.run_id);
  if (index === -1) {
    return [...current, autopilotRunToChatItem(run)];
  }
  const updated = [...current];
  updated[index] = {
    ...updated[index],
    body: summarizeAutopilotRun(run),
    autopilotRun: run,
    errors: run.errors,
  };
  return updated;
}


