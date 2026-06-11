import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { ShapeIrObject, ShapeIrObjectRegistry, ShapeIrVerification } from "../appTypes";

type UseObjectRegistryArgs = {
  selectedId: string | null;
  // Re-fetch when the project's geometry is rebuilt (same trigger as the B-Rep snapshot).
  geometryVersion?: string | null;
};

/**
 * Loads registry/object_registry.json for the selected project — the source of
 * truth mapping Shape IR nodes <-> viewer-selectable entities. Exposes the node
 * objects, a face-id -> node lookup (for reverse selection), and the package
 * verification. Absent/non-Shape-IR packages resolve to an empty registry.
 */
export function useObjectRegistry({ selectedId, geometryVersion = null }: UseObjectRegistryArgs) {
  const [registry, setRegistry] = useState<ShapeIrObjectRegistry | null>(null);
  const [verification, setVerification] = useState<ShapeIrVerification | null>(null);

  useEffect(() => {
    setRegistry(null);
    setVerification(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getObjectRegistry(selectedId, controller.signal);
        if (controller.signal.aborted) return;
        setRegistry(data.object_registry ?? null);
        setVerification(data.verification ?? null);
      } catch {
        // 404 = not a Shape IR package; that's fine — no registry panel shown.
        if (!controller.signal.aborted) {
          setRegistry(null);
          setVerification(null);
        }
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedId, geometryVersion]);

  const objects: ShapeIrObject[] = useMemo(() => registry?.objects ?? [], [registry]);

  const faceToNode = useMemo(() => {
    const map = new Map<string, ShapeIrObject>();
    for (const obj of objects) {
      for (const faceId of obj.viewer_selectable_ids ?? []) {
        if (!map.has(faceId)) map.set(faceId, obj);
      }
    }
    return map;
  }, [objects]);

  return { registry, objects, verification, faceToNode };
}
