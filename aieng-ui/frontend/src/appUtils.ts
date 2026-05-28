import { DEFAULT_LLM_CONFIG } from "./appConstants";
import type {
  BrepFaceEntity,
  BrepGraphSnapshot,
  BrepSelectionGroup,
  CadGenerationProgress,
  CadStageId,
  CadStageState,
} from "./appTypes";
import type {
  CapabilityDescriptor,
  ChatResponse,
  LLMConfig,
  ProjectRecord,
  ProjectSummary,
  RuntimeConfigSnapshot,
  RuntimeRun,
} from "./types";

const _API_KEY_PATTERNS: RegExp[] = [
  /sk-[A-Za-z0-9_\-]{16,}/g,
  /api[_-]?key["']?\s*[:=]\s*["']?[A-Za-z0-9_\-]{8,}/gi,
  /bearer\s+[A-Za-z0-9_\-.]{16,}/gi,
];

/** Mask any API-key-shaped substring so it never appears in chat history or
 * displayed error messages. Defense-in-depth: backend responses do not echo
 * api_key today, but this guarantees they cannot leak if that ever changes. */
export function redactSecrets(input: string): string {
  let out = input;
  for (const re of _API_KEY_PATTERNS) {
    out = out.replace(re, (match) => {
      const visible = match.slice(0, 6);
      return `${visible}…[redacted]`;
    });
  }
  return out;
}

export function runtimeStatusLabel(status: RuntimeRun["status"]): string {
  if (status === "completed") return "已完成";
  if (status === "awaiting_approval") return "等待审批";
  if (status === "failed") return "执行失败";
  if (status === "rejected") return "已拒绝";
  if (status === "cancelled") return "已取消";
  return status;
}

export function jsonBlock(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

export function formatTime(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function getDerivedNumber(summary: ProjectSummary | null, group: string, key: string) {
  const derived = ((summary as any)?.derived ?? {}) as Record<string, Record<string, unknown>>;
  const value = derived[group]?.[key];
  return typeof value === "number" ? value : 0;
}

export function getManifestString(summary: ProjectSummary | null, key: string) {
  const manifest = (summary?.manifest ?? null) as Record<string, unknown> | null;
  const value = manifest?.[key];
  return value == null ? "-" : String(value);
}

export function getProviderLabel(provider?: string | null) {
  if (provider === "freecad") return "FreeCAD";
  return provider ?? "-";
}

export function getLlmProviderLabel(provider?: string | null) {
  if (provider === "openai-compatible") return "OpenAI-compatible";
  if (provider === "azure-openai") return "Azure OpenAI";
  if (provider === "openai") return "OpenAI";
  if (provider === "anthropic") return "Anthropic";
  return provider ?? "-";
}

export function normalizeLlmConfig(raw: unknown): LLMConfig {
  const base = { ...DEFAULT_LLM_CONFIG };
  if (!raw || typeof raw !== "object") return base;
  const data = raw as Record<string, unknown>;
  return {
    provider: typeof data.provider === "string" && data.provider.trim() ? data.provider : base.provider,
    model: typeof data.model === "string" && data.model.trim() ? data.model : base.model,
    base_url: typeof data.base_url === "string" ? data.base_url : base.base_url,
    api_key_env: typeof data.api_key_env === "string" ? data.api_key_env : base.api_key_env,
    temperature: typeof data.temperature === "number" && Number.isFinite(data.temperature) ? data.temperature : base.temperature,
    top_p: typeof data.top_p === "number" && Number.isFinite(data.top_p) ? data.top_p : base.top_p,
    max_output_tokens:
      typeof data.max_output_tokens === "number" && Number.isFinite(data.max_output_tokens)
        ? data.max_output_tokens
        : base.max_output_tokens,
    input_price_per_million_tokens:
      typeof data.input_price_per_million_tokens === "number" && Number.isFinite(data.input_price_per_million_tokens)
        ? data.input_price_per_million_tokens
        : base.input_price_per_million_tokens,
    output_price_per_million_tokens:
      typeof data.output_price_per_million_tokens === "number" && Number.isFinite(data.output_price_per_million_tokens)
        ? data.output_price_per_million_tokens
        : base.output_price_per_million_tokens,
  };
}

export function isLlmConfigReady(config: LLMConfig) {
  return Boolean(config.provider.trim() && config.model.trim() && (config.api_key_env?.trim() || config.base_url?.trim()));
}

export function getRuntimeDetail(snapshot: RuntimeConfigSnapshot | null) {
  if (!snapshot) return "正在读取 CAD 运行时配置";
  if (snapshot.probe.ready) {
    return `${getProviderLabel(snapshot.config.provider)} / topology=${snapshot.probe.topology_backend_resolved}`;
  }
  const issues = Array.isArray(snapshot.probe.issues) ? snapshot.probe.issues : [];
  return issues.join("；") || snapshot.probe.bridge_error || "运行时检测未通过";
}

export function createChatId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function fieldLabel(field: string) {
  if (field === "stress") return "Von Mises Stress";
  if (field === "displacement") return "Displacement Magnitude";
  return field;
}

export function caeModeLabel(mode: string) {
  if (mode === "cad_only") return "CAD-only";
  if (mode === "cae_setup") return "CAE setup";
  if (mode === "cae_result") return "CAE result (external solver-output)";
  if (mode === "cae_validation") return "CAE validation / review";
  return mode;
}

export function caeModeClass(mode: string) {
  if (mode === "cad_only") return "mode-cad-only";
  if (mode === "cae_setup") return "mode-cae-setup";
  if (mode === "cae_result") return "mode-cae-result";
  if (mode === "cae_validation") return "mode-cae-validation";
  return "";
}

export function mutabilityLabel(capability: CapabilityDescriptor) {
  const parts = [];
  if (capability.mutates_cad) parts.push("CAD");
  if (capability.mutates_package) parts.push(".aieng");
  if (capability.may_update_claim_map) parts.push("claim");
  return parts.length ? parts.join(" + ") : "read-only";
}

export function workflowStepLabel(kind: string) {
  if (kind === "tool") return "runtime tool";
  if (kind === "mcp_tool") return "MCP tool";
  if (kind === "llm") return "LLM";
  if (kind === "approval") return "approval";
  if (kind === "benchmark") return "benchmark";
  if (kind === "artifact") return "artifact";
  return kind;
}

export function formatRecordSummary(record: Record<string, unknown>) {
  return Object.entries(record)
    .filter(([, value]) => value != null && value !== "")
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" / ");
}

export function summarizeAssistantReply(response: ChatResponse, mode: "plan" | "execute") {
  const prefix = mode === "execute" ? "已执行编排请求。" : "已生成编排计划。";
  return `${prefix} ${response.reply}`;
}

export function runtimeRunToChatPlan(run: RuntimeRun): ChatResponse["plan"] {
  return run.plan.map((step) => {
    const tc = run.tool_calls.find((c) => c.name === step.name);
    const tr = tc ? run.tool_results.find((r) => r.id === tc.id) : undefined;
    const status =
      tr?.status === "success"
        ? "done"
        : tr?.status === "needs_approval"
          ? "needs_approval"
          : tr?.status === "error"
            ? "failed"
            : "pending";
    return {
      tool: step.name,
      description: step.description,
      status,
      inputs: typeof step.input === "object" && step.input !== null ? (step.input as Record<string, unknown>) : {},
      output: tr?.output as Record<string, unknown> | null ?? null,
    };
  });
}

export function formatGeometryResult(output: Record<string, unknown>): string {
  if (!output || output.status === "error") {
    const code = output?.code ?? "error";
    const msg = output?.message ?? "Geometry inspection failed.";
    return `几何检查失败 [${code}]: ${msg}`;
  }
  const bb = output.bounding_box as Record<string, number> | undefined;
  const dims = bb
    ? `${bb.xlen?.toFixed(1)} × ${bb.ylen?.toFixed(1)} × ${bb.zlen?.toFixed(1)} mm`
    : "—";
  const vol = typeof output.total_volume_mm3 === "number"
    ? `${(output.total_volume_mm3 / 1000).toFixed(2)} cm³`
    : "—";
  const faces = output.total_face_count ?? "—";
  const solids = output.total_solid_count ?? "—";
  const ver = output.freecad_version ? ` (FreeCAD ${output.freecad_version})` : "";
  return `几何检查完成${ver} — 外形尺寸 ${dims}，体积 ${vol}，${solids} 个实体，${faces} 个面`;
}

export function formatArtifactChanges(run: RuntimeRun): string | null {
  const allArtifacts = run.tool_results.flatMap((tr) => tr.artifacts ?? []);
  if (allArtifacts.length === 0) return null;
  const paths = allArtifacts
    .filter((a): a is Record<string, unknown> => typeof a === "object" && a !== null)
    .map((a) => String(a.path ?? ""))
    .filter(Boolean);
  if (paths.length === 0) return null;
  return "变更文件:\n" + paths.map((p) => `  - ${p}`).join("\n");
}

export function extractArtifactPaths(run: RuntimeRun): string[] {
  const allArtifacts = run.tool_results.flatMap((tr) => tr.artifacts ?? []);
  return allArtifacts
    .filter((a): a is Record<string, unknown> => typeof a === "object" && a !== null)
    .map((a) => String(a.path ?? ""))
    .filter(Boolean);
}

export function isLowRiskArtifactPath(path: string): boolean {
  const lower = path.toLowerCase();
  return [".json", ".txt", ".md", ".yaml", ".yml", ".inp", ".csv", ".log"].some((ext) => lower.endsWith(ext));
}

export function projectViewerUrl(project: ProjectRecord | null) {
  if (!project?.id || !project?.web_asset) return null;
  return `/assets/projects/${project.id}/${project.web_asset}`;
}

export function resolveAssetFormat(assetUrl?: string | null, assetFormat?: string | null) {
  if (assetFormat) return assetFormat;
  if (!assetUrl) return null;
  const normalized = assetUrl.toLowerCase();
  if (normalized.endsWith(".glb")) return "glb";
  if (normalized.endsWith(".stl")) return "stl";
  return null;
}

export function withAssetVersion(assetUrl?: string | null, version?: string | null) {
  if (!assetUrl || !version) return assetUrl ?? null;
  const separator = assetUrl.includes("?") ? "&" : "?";
  return `${assetUrl}${separator}v=${encodeURIComponent(version)}`;
}

// ── CAD generation progress (stream reducer) ─────────────────────────────────

const CAD_STAGE_LABELS: Record<CadStageId, string> = {
  planning: "Planning",
  coding: "Code generation",
  building: "Build geometry",
  retrying: "AI fix attempt",
  writing: "Write artifacts",
  done: "Complete",
};

const CAD_STAGE_ORDER: CadStageId[] = ["planning", "coding", "building", "retrying", "writing", "done"];

export function emptyCadGenerationProgress(): CadGenerationProgress {
  const stages: CadStageState[] = CAD_STAGE_ORDER
    .filter((id) => id !== "retrying") // retrying only appears on demand
    .map((id) => ({ id, label: CAD_STAGE_LABELS[id], status: "pending" }));
  return {
    stages,
    activeStage: null,
    codePreview: null,
    errorPreview: null,
    fatalError: null,
  };
}

/**
 * Fold a single SSE event into the accumulated progress state.
 *
 * The backend emits events of the shape ``{step, message, ...}`` where
 * ``step`` is one of the CadStageId values (plus "error"). We translate that
 * into a per-stage status transition so the UI can render the full timeline,
 * not just the latest snapshot.
 */
export function applyCadProgressEvent(
  prev: CadGenerationProgress | null,
  event: Record<string, unknown>,
): CadGenerationProgress {
  const base = prev ?? emptyCadGenerationProgress();
  const step = String(event.step ?? "");
  const message = typeof event.message === "string" ? event.message : "";

  if (step === "error") {
    const errMessage = message || (typeof event.error === "string" ? event.error : "CAD generation failed");
    return {
      ...base,
      activeStage: null,
      fatalError: errMessage,
      errorPreview: typeof event.error === "string" ? event.error : (typeof event.error_preview === "string" ? event.error_preview : base.errorPreview),
      stages: base.stages.map((s) => (s.status === "active" ? { ...s, status: "failed", message: errMessage } : s)),
    };
  }

  if (!CAD_STAGE_ORDER.includes(step as CadStageId)) {
    // Unknown step — keep state untouched but stamp the message on the
    // currently-active stage if there is one.
    if (!base.activeStage) return base;
    return {
      ...base,
      stages: base.stages.map((s) => (s.id === base.activeStage ? { ...s, message } : s)),
    };
  }

  const targetId = step as CadStageId;
  const targetIndex = CAD_STAGE_ORDER.indexOf(targetId);
  let codePreview = base.codePreview;
  if (typeof event.code_preview === "string" && event.code_preview.length > 0) {
    codePreview = event.code_preview;
  }
  let errorPreview = base.errorPreview;
  if (typeof event.error_preview === "string" && event.error_preview.length > 0) {
    errorPreview = event.error_preview;
  }

  // Insert "retrying" stage on first occurrence if it wasn't there yet.
  let stages = base.stages.slice();
  if (targetId === "retrying" && !stages.some((s) => s.id === "retrying")) {
    const buildingIdx = stages.findIndex((s) => s.id === "building");
    const retryStage: CadStageState = { id: "retrying", label: CAD_STAGE_LABELS.retrying, status: "pending" };
    if (buildingIdx >= 0) {
      stages.splice(buildingIdx + 1, 0, retryStage);
    } else {
      stages.push(retryStage);
    }
  }

  stages = stages.map((s) => {
    if (s.id === targetId) {
      const next: CadStageState = {
        ...s,
        status: targetId === "done" ? "completed" : "active",
        message,
      };
      if (typeof event.elapsed_s === "number") next.elapsedS = event.elapsed_s;
      if (typeof event.attempt === "number") next.attempt = event.attempt;
      return next;
    }
    const idx = CAD_STAGE_ORDER.indexOf(s.id);
    if (idx >= 0 && idx < targetIndex && s.status !== "failed") {
      return { ...s, status: "completed" };
    }
    return s;
  });

  return {
    ...base,
    stages,
    activeStage: targetId === "done" ? null : targetId,
    codePreview,
    errorPreview,
    fatalError: null,
  };
}

// ── agent activity (Phase 2: external agents drive the workbench) ────────────

export type AgentActivityEvent = {
  type: string;            // tool_started | cad_build_progress | tool_completed | connected
  call_id?: string;
  tool?: string;
  project_id?: string | null;
  code_preview?: string | null;
  phase?: string;          // building | writing
  elapsed_s?: number;
  status?: string;
  preview_url?: string | null;
  preview_format?: string | null;
  topology_summary?: { face_count?: number; feature_count?: number } | null;
  message?: string | null;
};

/**
 * Fold a live agent-activity event into a CadGenerationProgress so the existing
 * CadProgressPanel can render an agent-driven CAD build the same way it renders
 * an in-UI generation. Stages are agent-flavoured: the agent already wrote the
 * code (so "Code generation" is completed on tool_started), then we mirror the
 * backend build/writing phases.
 *
 * Returns null for events that aren't a CAD build (e.g. a read-only tool call),
 * so the caller can ignore them for the build panel.
 */
export function applyAgentActivityEvent(
  prev: CadGenerationProgress | null,
  event: AgentActivityEvent,
): CadGenerationProgress | null {
  if (event.tool && event.tool !== "cad.execute_build123d") {
    return prev; // not a CAD build — leave the panel untouched
  }

  if (event.type === "tool_started") {
    const stages: CadStageState[] = [
      { id: "coding", label: "Agent wrote build123d code", status: "completed" },
      { id: "building", label: "Build geometry", status: "active", message: "Agent build started…" },
      { id: "writing", label: "Write artifacts", status: "pending" },
      { id: "done", label: "Complete", status: "pending" },
    ];
    return {
      stages,
      activeStage: "building",
      codePreview: event.code_preview ?? null,
      errorPreview: null,
      fatalError: null,
    };
  }

  if (!prev) return prev;

  if (event.type === "cad_build_progress") {
    const targetId: CadStageId = event.phase === "writing" ? "writing" : "building";
    const stages = prev.stages.map((s) => {
      if (s.id === targetId) {
        return {
          ...s,
          status: "active" as const,
          message: targetId === "building"
            ? `Building geometry… (${event.elapsed_s ?? 0}s)`
            : "Writing artifacts to package…",
          elapsedS: targetId === "building" ? event.elapsed_s : s.elapsedS,
        };
      }
      // mark earlier stages completed
      const order: CadStageId[] = ["coding", "building", "writing", "done"];
      if (order.indexOf(s.id) < order.indexOf(targetId) && s.status !== "failed") {
        return { ...s, status: "completed" as const };
      }
      return s;
    });
    return { ...prev, stages, activeStage: targetId };
  }

  if (event.type === "tool_completed") {
    if (event.status !== "ok") {
      return {
        ...prev,
        activeStage: null,
        fatalError: event.message ?? "Agent CAD build failed",
        stages: prev.stages.map((s) => (s.status === "active" ? { ...s, status: "failed" } : s)),
      };
    }
    return {
      ...prev,
      activeStage: null,
      stages: prev.stages.map((s) => ({ ...s, status: "completed" as const })),
    };
  }

  return prev;
}

/**
 * Normalise a raw /api/projects/{id}/brep-graph response into a snapshot
 * keyed by face_id / group_id / feature_id. Feature ids are surfaced both
 * directly (via selection_groups whose source === "feature_graph") and as
 * a flat featureFaces lookup so @feature: pointer clicks can expand to
 * member faces without re-walking the graph.
 */
export function parseBrepGraphSnapshot(raw: unknown): BrepGraphSnapshot {
  const faces: Record<string, BrepFaceEntity> = {};
  const groups: Record<string, BrepSelectionGroup> = {};
  const featureFaces: Record<string, string[]> = {};
  const numberList = (value: unknown): number[] | null => {
    if (Array.isArray(value)) {
      const nums = value.map((item) => Number(item)).filter((item) => Number.isFinite(item));
      return nums.length === value.length ? nums : null;
    }
    if (typeof value === "string") {
      const parts = value
        .trim()
        .split(/[\s,]+/)
        .filter(Boolean)
        .map((item) => Number(item));
      return parts.length > 0 && parts.every((item) => Number.isFinite(item)) ? parts : null;
    }
    return null;
  };
  const stringList = (value: unknown): string[] => {
    if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
    if (typeof value === "string") {
      return value.split(/[,\s]+/).map((item) => item.trim()).filter(Boolean);
    }
    return [];
  };
  if (!raw || typeof raw !== "object") return { faces, groups, featureFaces };
  const root = raw as Record<string, unknown>;
  const graph = (root.brep_graph ?? root) as Record<string, unknown>;
  const entities = (graph.entities ?? {}) as Record<string, unknown>;
  const faceList = Array.isArray(entities.faces) ? entities.faces : [];
  for (const f of faceList) {
    if (!f || typeof f !== "object") continue;
    const face = f as Record<string, unknown>;
    const id = typeof face.id === "string" ? face.id : undefined;
    if (!id) continue;
    faces[id] = {
      id,
      pointer: typeof face.pointer === "string" ? face.pointer : `@face:${id}`,
      surface_type: typeof face.surface_type === "string" ? face.surface_type : undefined,
      area_mm2: typeof face.area_mm2 === "number" ? face.area_mm2 : null,
      radius_mm: typeof face.radius_mm === "number" ? face.radius_mm : null,
      normal: numberList(face.normal),
      center: numberList(face.center),
      bounding_box: numberList(face.bounding_box) ?? undefined,
      roles: stringList(face.roles),
    };
  }
  const groupList = Array.isArray(graph.selection_groups) ? graph.selection_groups : [];
  for (const g of groupList) {
    if (!g || typeof g !== "object") continue;
    const group = g as Record<string, unknown>;
    const id = typeof group.id === "string" ? group.id : undefined;
    if (!id) continue;
    const members = stringList(group.members);
    groups[id] = {
      id,
      label: typeof group.label === "string" ? group.label : undefined,
      members,
      role: typeof group.role === "string" ? group.role : undefined,
      source: typeof group.source === "string" ? group.source : undefined,
    };
    if (group.source === "feature_graph" && members.length > 0) {
      featureFaces[id] = members;
    }
  }
  return { faces, groups, featureFaces };
}
