import { useEffect } from "react";
import * as THREE from "three";

import type { BrepGraphSnapshot } from "../../../appTypes";
import { type DisplayTransform } from "../../viewer/coordinateFrames";
import { createFaceHighlightMesh, createPrimitiveOverlay, disposeHighlightObject } from "../../viewer/highlights";

/**
 * Highlight overlay manager.
 *
 * Clears previous highlights and rebuilds the overlay group whenever the
 * highlighted face set, B-Rep snapshot, or loaded object changes.
 *
 * Preferred path: uses exact tessellated primitives from `faceMeshesRef`.
 * Fallback: reconstructs overlay by matching mesh triangles to face
 * bbox/normal (for older packages without an identity map).
 */
export function useHighlightOverlay(
  highlightGroupRef: React.RefObject<THREE.Group | null>,
  faceMeshesRef: React.MutableRefObject<Map<string, THREE.Mesh[]>>,
  highlightedFaceIds: Set<string>,
  brepSnapshot: BrepGraphSnapshot | null,
  objectRef: React.RefObject<THREE.Object3D | null>,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  objectReadyKey: number,
) {
  useEffect(() => {
    const group = highlightGroupRef.current;
    if (!group) return;

    // Clear previous overlays.
    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      disposeHighlightObject(child);
    }

    if (highlightedFaceIds.size === 0) return;

    // Preferred: overlay the exact tessellated primitive for each selected face.
    const faceMeshes = faceMeshesRef.current;
    if (faceMeshes.size > 0) {
      for (const faceId of highlightedFaceIds) {
        for (const prim of faceMeshes.get(faceId) ?? []) {
          group.add(createPrimitiveOverlay(prim));
        }
      }
      return;
    }

    // Fallback: reconstruct by matching mesh triangles to face bbox/normal.
    if (!brepSnapshot) return;
    const object = objectRef.current;
    if (!object) return;
    const transform = displayTransformRef.current;

    for (const faceId of highlightedFaceIds) {
      const face = brepSnapshot.faces[faceId];
      if (!face) continue;
      const highlightMesh = createFaceHighlightMesh(object, face, transform);
      if (highlightMesh) group.add(highlightMesh);
    }
  }, [highlightedFaceIds, brepSnapshot, objectReadyKey, highlightGroupRef, faceMeshesRef, objectRef, displayTransformRef]);
}
