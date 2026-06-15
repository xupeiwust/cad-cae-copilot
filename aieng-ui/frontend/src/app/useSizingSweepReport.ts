import { useEffect, useState } from "react";

import { api } from "../api";
import type { SizingSweepReport } from "../types";

type UseSizingSweepReportArgs = {
  selectedId: string | null;
  /** Re-fetch when geometry or CAE setup may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the latest sizing-sweep report artifact for the workbench panel.
 * Failures / missing reports resolve to null; the panel decides whether the
 * report is meaningful enough to render.
 */
export function useSizingSweepReport({ selectedId, geometryVersion = null }: UseSizingSweepReportArgs) {
  const [report, setReport] = useState<SizingSweepReport | null>(null);

  useEffect(() => {
    setReport(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getSizingSweepReport(selectedId, controller.signal);
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

  return { sizingSweepReport: report };
}
