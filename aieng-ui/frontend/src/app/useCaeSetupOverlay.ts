import { useEffect, useState } from "react";

import { api } from "../api";
import type { CaeSetupOverlayResponse } from "../types";

type UseCaeSetupOverlayArgs = {
  selectedId: string | null;
  /** Re-fetch when geometry or CAE setup may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the CAE setup overlay for the 3D viewer (loads, constraints, bound faces).
 * Failures / missing setup resolve to null; the viewer decides whether to render.
 */
export function useCaeSetupOverlay({ selectedId, geometryVersion = null }: UseCaeSetupOverlayArgs) {
  const [overlay, setOverlay] = useState<CaeSetupOverlayResponse | null>(null);

  useEffect(() => {
    setOverlay(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getCaeSetupOverlay(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setOverlay(data?.available ? data : null);
      } catch {
        if (!controller.signal.aborted) setOverlay(null);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { caeSetupOverlay: overlay };
}
