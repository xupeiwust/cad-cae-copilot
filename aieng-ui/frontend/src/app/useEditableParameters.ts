import { useEffect, useState } from "react";

import { api } from "../api";
import type { EditableParameter } from "../types";

type UseEditableParametersArgs = {
  selectedId: string | null;
  /** Re-fetch when the project's geometry is rebuilt (same trigger as the B-Rep snapshot). */
  geometryVersion?: string | null;
};

/**
 * Loads the project's editable-parameter listing (the read-only discovery surface
 * behind cad.list_editable_parameters) for the Editable Parameters panel. Absent
 * packages / projects with no feature graph resolve to an empty list — the panel
 * then simply does not render.
 */
export function useEditableParameters({ selectedId, geometryVersion = null }: UseEditableParametersArgs) {
  const [parameters, setParameters] = useState<EditableParameter[]>([]);

  useEffect(() => {
    setParameters([]);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getEditableParameters(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setParameters(Array.isArray(data.parameters) ? data.parameters : []);
      } catch {
        // No package / no feature graph — leave the listing empty (panel hidden).
        if (!controller.signal.aborted) setParameters([]);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { editableParameters: parameters };
}
