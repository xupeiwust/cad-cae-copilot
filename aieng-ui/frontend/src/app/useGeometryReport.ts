import { useEffect, useState } from "react";

import { api } from "../api";
import type { GeometryReportResponse } from "../types";

type UseGeometryReportArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry is rebuilt (same trigger as the preview asset). */
  geometryVersion?: string | null;
};

/**
 * Loads the project's geometry assembly-check report (floating parts, broken
 * symmetry, per-part boxes) for the viewer overlay. Absent packages / projects
 * without geometry resolve to null — the overlay then offers nothing.
 */
export function useGeometryReport({ selectedId, geometryVersion = null }: UseGeometryReportArgs) {
  const [report, setReport] = useState<GeometryReportResponse | null>(null);

  useEffect(() => {
    setReport(null);
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getGeometryReport(selectedId);
        if (cancelled) return;
        setReport(data && data.available ? data : null);
      } catch {
        // No package / no topology — leave the report empty (overlay hidden).
        if (!cancelled) setReport(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, geometryVersion]);

  return { geometryReport: report };
}
