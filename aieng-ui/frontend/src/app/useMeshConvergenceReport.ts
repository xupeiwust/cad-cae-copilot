import { useEffect, useState } from "react";

import { api } from "../api";
import type { MeshConvergenceReport } from "../types";

type UseMeshConvergenceReportArgs = {
  selectedId: string | null;
  /** Re-fetch when geometry or CAE setup may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the latest mesh-convergence report artifact for the workbench panel.
 * Failures / missing reports resolve to null; the panel decides whether the
 * report is meaningful enough to render.
 */
export function useMeshConvergenceReport({ selectedId, geometryVersion = null }: UseMeshConvergenceReportArgs) {
  const [report, setReport] = useState<MeshConvergenceReport | null>(null);

  useEffect(() => {
    setReport(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getMeshConvergenceReport(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setReport(data?.available ? (data.report ?? null) : null);
      } catch {
        if (!controller.signal.aborted) setReport(null);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { meshConvergenceReport: report };
}
