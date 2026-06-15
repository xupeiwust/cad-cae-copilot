import { useEffect, useState } from "react";

import { api } from "../api";
import type { MeshPreviewResponse } from "../types";

type UseMeshPreviewArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry or simulation results may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the project's FE mesh preview (surface wireframe + element stats).
 * Failures / missing mesh resolve to null so the overlay toggle stays hidden.
 */
export function useMeshPreview({ selectedId, geometryVersion = null }: UseMeshPreviewArgs) {
  const [preview, setPreview] = useState<MeshPreviewResponse | null>(null);

  useEffect(() => {
    setPreview(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getMeshPreview(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setPreview(data && data.available ? data : null);
      } catch {
        // No package / no mesh — leave the preview empty (toggle hidden).
        if (!controller.signal.aborted) setPreview(null);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { meshPreview: preview };
}
