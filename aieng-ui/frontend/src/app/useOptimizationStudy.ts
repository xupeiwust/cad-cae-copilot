import { useEffect, useState } from "react";

import { api } from "../api";
import { shapeOptimizationStudy, type OptimizationStudy } from "./optimizationStudy";
import { shapeSurrogateProposals, type SurrogateProposals } from "./surrogatePredictions";

type UseOptimizationStudyArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry or study state may have changed. */
  geometryVersion?: string | null;
};

function reportFromSummary(summary: unknown, key: string): unknown {
  if (!summary || typeof summary !== "object") return null;
  const artifacts = (summary as { artifacts?: unknown }).artifacts;
  if (!artifacts || typeof artifacts !== "object") return null;
  const entry = (artifacts as Record<string, unknown>)[key];
  if (!entry || typeof entry !== "object") return null;
  return (entry as { report?: unknown }).report ?? null;
}

/**
 * Loads the agent-guided design-study artifacts (candidate ranking, recommendation,
 * report) for the Optimization panel. Reads package artifacts directly; no dedicated
 * GET endpoint exists yet. Defensive: missing or malformed artifacts resolve to an
 * empty study — the panel then hides itself.
 */
export function useOptimizationStudy({ selectedId, geometryVersion = null }: UseOptimizationStudyArgs) {
  const [study, setStudy] = useState<OptimizationStudy | null>(null);
  const [surrogate, setSurrogate] = useState<SurrogateProposals | null>(null);

  useEffect(() => {
    setStudy(null);
    setSurrogate(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;

    void (async () => {
      try {
        const summary = await api.getDesignStudySummary(selectedId, controller.signal).catch(() => null);

        if (controller.signal.aborted) return;

        const ranking = reportFromSummary(summary, "ranking");
        const recommendation = reportFromSummary(summary, "recommendation");
        const report = reportFromSummary(summary, "report");

        const shaped = shapeOptimizationStudy(ranking, recommendation, report);
        setStudy(shaped.has_study ? shaped : null);

        const shapedSurrogate = shapeSurrogateProposals(reportFromSummary(summary, "surrogate"));
        setSurrogate(shapedSurrogate.hasProposals ? shapedSurrogate : null);
      } catch {
        if (!controller.signal.aborted) {
          setStudy(null);
          setSurrogate(null);
        }
      }
    })();

    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { optimizationStudy: study, surrogateProposals: surrogate };
}
