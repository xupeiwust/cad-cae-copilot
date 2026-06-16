import { useEffect, useState } from "react";

import { api } from "../api";
import type { FieldRegionsDocument } from "../types";

const FIELD_REGIONS_PATHS = ["analysis/field_regions.json", "results/field_regions.json"];

type UseFieldRegionsArgs = {
  selectedId: string | null;
  /** Re-fetch when results may have changed. */
  geometryVersion?: string | null;
};

/**
 * Loads the latest field-regions artifact for cluster marker visualization.
 * Failures / missing artifacts resolve to null.
 */
export function useFieldRegions({ selectedId, geometryVersion = null }: UseFieldRegionsArgs) {
  const [document, setDocument] = useState<FieldRegionsDocument | null>(null);

  useEffect(() => {
    setDocument(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      for (const path of FIELD_REGIONS_PATHS) {
        try {
          const res = await api.getProjectArtifact(selectedId, path, controller.signal);
          if (controller.signal.aborted) return;
          const parsed = res?.parsed_json;
          if (
            parsed &&
            typeof parsed === "object" &&
            Array.isArray((parsed as Record<string, unknown>).clusters)
          ) {
            setDocument(parsed as FieldRegionsDocument);
            return;
          }
        } catch {
          // try next path
        }
      }
      setDocument(null);
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  return { fieldRegions: document };
}
