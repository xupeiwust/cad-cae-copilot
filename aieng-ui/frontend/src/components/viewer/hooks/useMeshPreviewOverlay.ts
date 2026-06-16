import { useEffect } from "react";
import * as THREE from "three";

import type { MeshPreviewResponse } from "../../../types";
import { type DisplayTransform } from "../../viewer/coordinateFrames";
import { buildMeshPreviewGroup, disposeMeshPreviewGroup } from "../../viewer/meshPreview";

/**
 * FE mesh preview overlay manager.
 *
 * Rebuilds the semi-transparent surface wireframe whenever the toggle, mesh
 * preview payload, or model reload changes.
 */
export function useMeshPreviewOverlay(
  meshPreviewGroupRef: React.RefObject<THREE.Group | null>,
  showMeshPreview: boolean,
  meshPreview: MeshPreviewResponse | null,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  objectReadyKey: number,
) {
  useEffect(() => {
    const group = meshPreviewGroupRef.current;
    if (!group) return;

    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      if (child instanceof THREE.Group) disposeMeshPreviewGroup(child);
    }

    if (!showMeshPreview || !meshPreview) return;
    group.add(buildMeshPreviewGroup(meshPreview, displayTransformRef.current));
  }, [showMeshPreview, meshPreview, objectReadyKey, meshPreviewGroupRef, displayTransformRef]);
}
