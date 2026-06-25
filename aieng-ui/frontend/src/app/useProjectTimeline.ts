import { useEffect, useState } from "react";

import { api } from "../api";
import type { RuntimeRun } from "../types";
import { buildProjectTimeline, type ProjectTimeline } from "./projectTimeline";

type UseProjectTimelineArgs = {
  selectedId: string | null;
  geometryVersion?: string | null;
  limit?: number;
};

export function useProjectTimeline({ selectedId, geometryVersion = null, limit = 8 }: UseProjectTimelineArgs) {
  const [timeline, setTimeline] = useState<ProjectTimeline>(() => buildProjectTimeline([]));

  useEffect(() => {
    setTimeline(buildProjectTimeline([]));
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;

    void (async () => {
      try {
        const summaries = await api.listRuns();
        if (cancelled) return;
        const runIds = summaries
          .filter((run) => run.project_id === selectedId)
          .slice(0, limit)
          .map((run) => run.run_id);
        const runs: RuntimeRun[] = [];
        for (const runId of runIds) {
          try {
            const run = await api.getRun(runId);
            if (!cancelled) runs.push(run);
          } catch {
            // A missing historical run should not block the workbench.
          }
        }
        if (!cancelled) setTimeline(buildProjectTimeline(runs));
      } catch {
        if (!cancelled) setTimeline(buildProjectTimeline([]));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedId, geometryVersion, limit]);

  return { projectTimeline: timeline };
}
