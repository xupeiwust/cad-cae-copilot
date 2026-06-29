import { useEffect, useState } from "react";

import { api } from "../api";
import type { CredibilityStamp, CritiqueFinding, StandardFastenerPlanSummary } from "../types";

type UseProjectCritiqueArgs = {
  selectedId: string | null;
  /** Re-run when the project's geometry is rebuilt (same trigger as the B-Rep snapshot). */
  geometryVersion?: string | null;
};

/**
 * Loads the deterministic engineering critique for the selected project (the
 * read-only audit behind cad.critique) for the Critique panel. No-geometry
 * projects / failures resolve to no findings — the panel then does not render.
 */
export function useProjectCritique({ selectedId, geometryVersion = null }: UseProjectCritiqueArgs) {
  const [findings, setFindings] = useState<CritiqueFinding[]>([]);
  const [credibility, setCredibility] = useState<CredibilityStamp | null>(null);
  const [standardFastenerPlan, setStandardFastenerPlan] = useState<StandardFastenerPlanSummary | null>(null);

  useEffect(() => {
    setFindings([]);
    setCredibility(null);
    setStandardFastenerPlan(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getProjectCritique(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setFindings(Array.isArray(data.findings) ? data.findings : []);
        setCredibility(data.credibility ?? null);
        setStandardFastenerPlan(data.standard_fastener_plan ?? null);
      } catch {
        if (!controller.signal.aborted) {
          setFindings([]);
          setCredibility(null);
          setStandardFastenerPlan(null);
        }
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { critiqueFindings: findings, critiqueCredibility: credibility, standardFastenerPlan };
}
