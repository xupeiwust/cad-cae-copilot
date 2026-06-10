import { useEffect } from "react";
import * as THREE from "three";

import type { GeometryReportResponse } from "../../../types";
import { type DisplayTransform } from "../../viewer/coordinateFrames";
import { buildAssemblyCheckGroup, disposeAssemblyCheckGroup } from "../../viewer/assemblyCheck";

/**
 * Assembly-check overlay manager.
 *
 * Rebuilds the wireframe box overlay (red = floating parts, amber = broken
 * symmetry) whenever the toggle, geometry report, or model reload changes.
 */
export function useAssemblyCheckOverlay(
  assemblyGroupRef: React.RefObject<THREE.Group | null>,
  showAssemblyCheck: boolean,
  geometryReport: GeometryReportResponse | null,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  objectReadyKey: number,
) {
  useEffect(() => {
    const group = assemblyGroupRef.current;
    if (!group) return;

    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      if (child instanceof THREE.Group) disposeAssemblyCheckGroup(child);
    }

    if (!showAssemblyCheck || !geometryReport) return;
    group.add(buildAssemblyCheckGroup(geometryReport, displayTransformRef.current));
  }, [showAssemblyCheck, geometryReport, objectReadyKey, assemblyGroupRef, displayTransformRef]);
}
