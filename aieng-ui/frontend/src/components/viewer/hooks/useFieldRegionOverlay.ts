import { useEffect } from "react";
import * as THREE from "three";

import type { FieldRegionsDocument } from "../../../types";
import { type DisplayTransform } from "../coordinateFrames";
import { buildFieldRegionMarkerGroup, disposeFieldRegionMarkerGroup } from "../fieldRegionMarkers";

/**
 * Field-region cluster marker overlay manager.
 *
 * Draws a 3D marker per high-magnitude cluster whenever the toggle, field
 * regions document, or model reload changes.
 */
export function useFieldRegionOverlay(
  fieldRegionGroupRef: React.RefObject<THREE.Group | null>,
  showFieldRegions: boolean,
  fieldRegions: FieldRegionsDocument | null,
  objectRef: React.RefObject<THREE.Object3D | null>,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  objectReadyKey: number,
) {
  useEffect(() => {
    const group = fieldRegionGroupRef.current;
    if (!group) return;

    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      if (child instanceof THREE.Group) disposeFieldRegionMarkerGroup(child);
    }

    if (!showFieldRegions || !fieldRegions) return;
    const object = objectRef.current;
    if (!object) return;

    group.add(buildFieldRegionMarkerGroup(fieldRegions, object, displayTransformRef.current));
  }, [showFieldRegions, fieldRegions, objectReadyKey, fieldRegionGroupRef, objectRef, displayTransformRef]);
}
