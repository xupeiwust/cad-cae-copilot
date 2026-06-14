import { useEffect, useState } from "react";

import { api } from "../api";
import type { EditDiffResponse } from "../types";

type UseEditDiffArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry is rebuilt (same trigger as the preview asset). */
  geometryVersion?: string | null;
};

/**
 * Loads the most recent edit's diff (#226) for the Edit Diff panel — the
 * `regression_diff` / `critique_diff` the backend persisted on the last CAD
 * mutation. Projects with no edit yet / no package resolve to null (panel hidden).
 */
export function useEditDiff({ selectedId, geometryVersion = null }: UseEditDiffArgs) {
  const [editDiff, setEditDiff] = useState<EditDiffResponse | null>(null);

  useEffect(() => {
    setEditDiff(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getEditDiff(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setEditDiff(data && data.available ? data : null);
      } catch {
        if (!controller.signal.aborted) setEditDiff(null);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { editDiff };
}
