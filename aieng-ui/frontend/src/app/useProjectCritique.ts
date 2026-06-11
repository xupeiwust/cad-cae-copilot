import { useEffect, useState } from "react";

import { api } from "../api";
import type { CritiqueFinding } from "../types";

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

  useEffect(() => {
    setFindings([]);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getProjectCritique(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setFindings(Array.isArray(data.findings) ? data.findings : []);
      } catch {
        if (!controller.signal.aborted) setFindings([]);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { critiqueFindings: findings };
}
