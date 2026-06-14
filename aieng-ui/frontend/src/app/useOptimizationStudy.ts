import { useEffect, useState } from "react";

import { api } from "../api";
import { shapeOptimizationStudy, type OptimizationStudy } from "./optimizationStudy";
import { shapeSurrogateProposals, type SurrogateProposals } from "./surrogatePredictions";

type UseOptimizationStudyArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry or study state may have changed. */
  geometryVersion?: string | null;
};

const RANKING_PATH = "analysis/design_study_candidate_ranking.json";
const RECOMMENDATION_PATH = "analysis/optimization_recommendation.json";
const REPORT_PATH = "diagnostics/optimization_report.json";
const SURROGATE_PATH = "analysis/design_study_surrogate_proposals.json";

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
        const [rankingRes, recommendationRes, reportRes, surrogateRes] = await Promise.all([
          api.getProjectArtifact(selectedId, RANKING_PATH, controller.signal).catch(() => null),
          api.getProjectArtifact(selectedId, RECOMMENDATION_PATH, controller.signal).catch(() => null),
          api.getProjectArtifact(selectedId, REPORT_PATH, controller.signal).catch(() => null),
          api.getProjectArtifact(selectedId, SURROGATE_PATH, controller.signal).catch(() => null),
        ]);

        if (controller.signal.aborted) return;

        const ranking = rankingRes?.parsed_json ?? null;
        const recommendation = recommendationRes?.parsed_json ?? null;
        const report = reportRes?.parsed_json ?? null;

        const shaped = shapeOptimizationStudy(ranking, recommendation, report);
        setStudy(shaped.has_study ? shaped : null);

        const shapedSurrogate = shapeSurrogateProposals(surrogateRes?.parsed_json ?? null);
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
