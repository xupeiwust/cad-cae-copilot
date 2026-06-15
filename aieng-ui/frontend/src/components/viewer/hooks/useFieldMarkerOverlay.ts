import { useEffect } from "react";
import * as THREE from "three";

import type { SolverFieldDescriptor } from "../../../types";
import { type DisplayTransform } from "../../viewer/coordinateFrames";
import { buildFieldMarkerGroup, disposeFieldMarkerGroup } from "../../viewer/fieldMarkers";

/**
 * Peak/min field-marker overlay manager.
 *
 * Rebuilds the marker spheres (red = field max, blue = field min) whenever the
 * toggle, active field descriptor, or model reload changes. Markers are placed
 * from the descriptor's per-node values + coords; synthetic fields produce none.
 */
export function useFieldMarkerOverlay(
  markerGroupRef: React.RefObject<THREE.Group | null>,
  showFieldMarkers: boolean,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  objectReadyKey: number,
) {
  useEffect(() => {
    const group = markerGroupRef.current;
    if (!group) return;

    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      if (child instanceof THREE.Group) disposeFieldMarkerGroup(child);
    }

    if (!showFieldMarkers || !fieldDescriptor) return;
    group.add(buildFieldMarkerGroup(fieldDescriptor, displayTransformRef.current));
  }, [showFieldMarkers, fieldDescriptor, objectReadyKey, markerGroupRef, displayTransformRef]);
}
