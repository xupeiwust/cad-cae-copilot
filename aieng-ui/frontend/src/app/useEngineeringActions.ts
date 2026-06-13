import { useCallback, useState } from "react";

import type { CadGenerationProgress } from "../appTypes";

type UseEngineeringActionsArgs = {
  selectedId: string | null;
};

export function useEngineeringActions({ selectedId }: UseEngineeringActionsArgs) {
  const [cadPreviewUrl, setCadPreviewUrl] = useState<string | null>(null);
  const [cadPreviewFormat, setCadPreviewFormat] = useState<string | null>(null);
  const [cadGenerationProgress, setCadGenerationProgress] = useState<CadGenerationProgress | null>(null);
  const [heatmapActive, setHeatmapActive] = useState(false);
  const [heatmapRange, setHeatmapRange] = useState<{ min: number; max: number } | null>(null);

  // Stable identity: a useEffect in useWorkbenchApp depends on this to reset
  // derived preview state on project switch. It only calls stable setters, so
  // an empty dep list is correct and keeps that effect from over-firing.
  const resetProjectDerivedState = useCallback(() => {
    setCadPreviewUrl(null);
    setCadPreviewFormat(null);
  }, []);

  function refreshViewerAsset(projectId: string, previewUrl?: string | null, previewFormat?: string | null) {
    setCadPreviewUrl(`${previewUrl || `/api/projects/${projectId}/cad-preview`}${previewUrl?.includes("?") ? "&" : "?"}ts=${Date.now()}`);
    setCadPreviewFormat(previewFormat ?? "glb");
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
    cadGenerationProgress,
    setCadGenerationProgress,
    heatmapActive,
    heatmapRange,
    refreshViewerAsset,
    resetProjectDerivedState,
    viewStressHeatmap,
  };
}
