import { useEffect, useState } from "react";

import { api } from "../api";
import type { ToleranceStackupReport } from "../types";

type UseToleranceStackupReportArgs = {
  selectedId: string | null;
  /** Re-fetch when geometry or manufacturing evidence may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the latest persisted tolerance stack-up report for the workbench panel.
 * Missing reports resolve to null so this panel cannot disturb normal CAD flow.
 */
export function useToleranceStackupReport({
  selectedId,
  geometryVersion = null,
}: UseToleranceStackupReportArgs) {
  const [report, setReport] = useState<ToleranceStackupReport | null>(null);

  useEffect(() => {
    setReport(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getToleranceStackupReport(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        const report = data?.available ? (data.report ?? null) : null;
        setReport(report && data.artifact_path && !report.artifact_path
          ? { ...report, artifact_path: data.artifact_path }
          : report);
      } catch {
        if (!controller.signal.aborted) setReport(null);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { toleranceStackupReport: report };
}
