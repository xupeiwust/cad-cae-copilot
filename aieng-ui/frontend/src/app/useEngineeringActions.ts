import { useCallback, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { CadGenerationProgress, ChatHistoryItem } from "../appTypes";
import type { LLMConfig } from "../types";
import {
  applyCadProgressEvent,
  createChatId,
  emptyCadGenerationProgress,
  redactSecrets,
} from "../appUtils";

type CadGenResult = { code: string; face_count: number; feature_count: number };

type UseEngineeringActionsArgs = {
  selectedId: string | null;
  apiKey: string;
  llmConfig: LLMConfig;
  refreshProjects(nextSelectedId?: string | null): Promise<void>;
  setBusy: Dispatch<SetStateAction<boolean>>;
  setChatHistory: Dispatch<SetStateAction<ChatHistoryItem[]>>;
};

export function useEngineeringActions({
  selectedId,
  apiKey,
  llmConfig,
  refreshProjects,
  setBusy,
  setChatHistory,
}: UseEngineeringActionsArgs) {
  const [cadPreviewUrl, setCadPreviewUrl] = useState<string | null>(null);
  const [cadPreviewFormat, setCadPreviewFormat] = useState<string | null>(null);
  const [cadGenerating, setCadGenerating] = useState(false);
  const [cadGenResult, setCadGenResult] = useState<CadGenResult | null>(null);
  const [cadGenerationProgress, setCadGenerationProgress] = useState<CadGenerationProgress | null>(null);
  const [heatmapActive, setHeatmapActive] = useState(false);
  const [heatmapRange, setHeatmapRange] = useState<{ min: number; max: number } | null>(null);

  // Stable identity: a useEffect in useWorkbenchApp depends on this to reset
  // derived preview state on project switch. It only calls stable setters, so
  // an empty dep list is correct and keeps that effect from over-firing.
  const resetProjectDerivedState = useCallback(() => {
    setCadPreviewUrl(null);
    setCadPreviewFormat(null);
    setCadGenResult(null);
  }, []);

  function refreshViewerAsset(projectId: string, previewUrl?: string | null, previewFormat?: string | null) {
    setCadPreviewUrl(`${previewUrl || `/api/projects/${projectId}/cad-preview`}${previewUrl?.includes("?") ? "&" : "?"}ts=${Date.now()}`);
    setCadPreviewFormat(previewFormat ?? "glb");
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
        llm_config: llmConfig,
      };
      if (options.materialHint) payload.material_hint = options.materialHint;
      if (options.meshHint) payload.mesh_hint = options.meshHint;
      if (apiKey) payload.api_key = apiKey;
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
      const keyPayload = apiKey ? { api_key: apiKey } : {};
      if (intent === "generate") {
        const response = await api.generateCadStream(selectedId, { description: prompt, hints: {}, write_files: true, llm_config: llmConfig, ...keyPayload });
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
              continue;
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
        const result = await api.refineCad(selectedId, { feedback: prompt, write_files: true, llm_config: llmConfig, ...keyPayload });
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

  return {
    cadPreviewUrl,
    cadPreviewFormat,
    cadGenerating,
    cadGenResult,
    cadGenerationProgress,
    setCadGenerationProgress,
    heatmapActive,
    heatmapRange,
    refreshViewerAsset,
    resetProjectDerivedState,
    executePreprocessFromPrompt,
    executeCadFromPrompt,
    viewStressHeatmap,
  };
}
