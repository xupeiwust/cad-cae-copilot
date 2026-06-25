import { useEffect, useState } from "react";

import { api } from "../api";
import type { AgentActivityEvent } from "../appUtils";
import type { RuntimeRun } from "../types";
import { buildProjectTimeline, type ProjectTimeline } from "./projectTimeline";

type UseProjectTimelineArgs = {
  selectedId: string | null;
  geometryVersion?: string | null;
  refreshKey?: number;
  limit?: number;
};

export function useProjectTimeline({ selectedId, geometryVersion = null, refreshKey = 0, limit = 8 }: UseProjectTimelineArgs) {
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
        let activityEvents: AgentActivityEvent[] = [];
        try {
          const recent = await api.getRecentActivity(selectedId, 50);
          activityEvents = Array.isArray(recent.events) ? recent.events : [];
        } catch {
          activityEvents = [];
        }
        if (!cancelled) setTimeline(buildProjectTimeline(runs, activityEvents));
      } catch {
        if (!cancelled) setTimeline(buildProjectTimeline([]));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedId, geometryVersion, refreshKey, limit]);

  return { projectTimeline: timeline };
}
