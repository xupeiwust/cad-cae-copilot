import { useEffect, useState } from "react";

import { api } from "../api";
import type { SimulationReadinessResponse } from "../types";

type UseSimulationReadinessArgs = {
  selectedId: string | null;
  /** Re-fetch when geometry or CAE setup may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the deterministic simulation-readiness report (the classifier behind
 * /simulate) for the CAE Readiness panel. Failures / non-CAE projects resolve to
 * null; the panel decides whether the report is meaningful enough to render.
 */
export function useSimulationReadiness({ selectedId, geometryVersion = null }: UseSimulationReadinessArgs) {
  const [readiness, setReadiness] = useState<SimulationReadinessResponse | null>(null);

  useEffect(() => {
    setReadiness(null);
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getSimulationReadiness(selectedId);
        if (cancelled) return;
        setReadiness(data ?? null);
      } catch {
        if (!cancelled) setReadiness(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, geometryVersion]);

  return { simulationReadiness: readiness };
}
