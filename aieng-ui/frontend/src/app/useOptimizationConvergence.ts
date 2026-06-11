import { useEffect, useState } from "react";

import { api } from "../api";
import { shapeOptimizationConvergence, type OptimizationConvergence } from "./optimizationConvergence";

type UseOptimizationConvergenceArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry or study state may have changed. */
  geometryVersion?: string | null;
};

const ITERATIONS_PATH = "analysis/optimization_iterations.json";

/**
 * Loads the iterative-loop convergence history artifact for the convergence chart.
 * Defensive: missing or malformed artifacts resolve to an empty model — the chart
 * then hides itself.
 */
export function useOptimizationConvergence({ selectedId, geometryVersion = null }: UseOptimizationConvergenceArgs) {
  const [convergence, setConvergence] = useState<OptimizationConvergence | null>(null);

  useEffect(() => {
    setConvergence(null);
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) return;

    void (async () => {
      try {
        const res = await api.getProjectArtifact(selectedId, ITERATIONS_PATH).catch(() => null);
        if (cancelled) return;
        const shaped = shapeOptimizationConvergence(res?.parsed_json ?? null);
        setConvergence(shaped);
      } catch {
        if (!cancelled) setConvergence(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedId, geometryVersion]);

  return { optimizationConvergence: convergence };
}
