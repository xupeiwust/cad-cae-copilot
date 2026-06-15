import { useEffect } from "react";
import * as THREE from "three";

import type { FieldOverlayConfig, SolverFieldDescriptor } from "../../../types";
import { applyFieldColors } from "../fieldColors";

/**
 * Re-apply the active field colormap to the loaded object whenever the user
 * changes legend controls (clamp, bands, colormap, threshold). This keeps the
 * asset load path decoupled from overlay configuration changes.
 */
export function useFieldColorOverlay(
  objectRef: React.MutableRefObject<THREE.Object3D | null>,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  config: FieldOverlayConfig | null | undefined,
  objectReadyKey: number,
) {
  const descriptor = fieldDescriptor;
  const hasRealData = Boolean(
    descriptor &&
      descriptor.format === "vertex_json" &&
      Array.isArray(descriptor.values) &&
      descriptor.values.length > 0 &&
      Array.isArray(descriptor.node_coords) &&
      descriptor.node_coords.length > 0,
  );

  useEffect(() => {
    const object = objectRef.current;
    if (!object || !hasRealData || !descriptor) return;

    applyFieldColors(
      object,
      descriptor.values!,
      descriptor.node_coords!,
      descriptor.min_value,
      descriptor.max_value,
      config?.colormap ?? descriptor.colormap,
      config ?? null,
    );
    // objectReadyKey is enough to trigger the first application after the asset
    // loader attaches the mesh; subsequent updates come from `config` changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [objectReadyKey, descriptor?.project_id, descriptor?.field_name, config?.colormap, config?.clampMin, config?.clampMax, config?.bands, config?.thresholdMin, config?.thresholdMax]);
}
