import { useEffect, useState } from "react";

import { api } from "../api";
import type { MeshDiagnosticsResponse } from "../types";

type UseMeshDiagnosticsArgs = {
  selectedId: string | null;
  /** Re-fetch when geometry, mesh, or simulation artifacts may have changed. */
  geometryVersion?: string | null;
};

export function useMeshDiagnostics({ selectedId, geometryVersion = null }: UseMeshDiagnosticsArgs) {
  const [diagnostics, setDiagnostics] = useState<MeshDiagnosticsResponse | null>(null);

  useEffect(() => {
    setDiagnostics(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getMeshDiagnostics(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setDiagnostics(data && data.available ? data : null);
      } catch {
        if (!controller.signal.aborted) setDiagnostics(null);
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { meshDiagnostics: diagnostics };
}
