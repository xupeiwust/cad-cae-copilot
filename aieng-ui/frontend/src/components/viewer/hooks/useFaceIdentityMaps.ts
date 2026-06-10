import { useEffect, useRef } from "react";
import * as THREE from "three";

import type { BrepGraphSnapshot, PickedFace } from "../../../appTypes";
import { IDENTITY_TRANSFORM, deriveGlbScale, type DisplayTransform } from "../../viewer/coordinateFrames";
import { buildFaceIdentityMaps } from "../../viewer/faceIdentity";

/**
 * Build and maintain the viewer↔model coordinate transform and the
 * primitive↔face identity maps whenever the loaded object or B-Rep
 * snapshot changes.
 *
 * Returns three refs so downstream hooks (face picker, highlight overlay,
 * assembly check) can read the current mappings without re-rendering.
 */
export function useFaceIdentityMaps(
  objectRef: React.RefObject<THREE.Object3D | null>,
  brepSnapshot: BrepGraphSnapshot | null,
  resolvedAssetFormat: string | null,
  objectReadyKey: number,
) {
  const displayTransformRef = useRef<DisplayTransform>(IDENTITY_TRANSFORM);
  const primitiveFaceRef = useRef<Map<THREE.Object3D, PickedFace>>(new Map());
  const faceMeshesRef = useRef<Map<string, THREE.Mesh[]>>(new Map());

  useEffect(() => {
    const object = objectRef.current;
    const isGlb = (resolvedAssetFormat ?? "").toLowerCase() === "glb";
    if (!object || !isGlb) {
      displayTransformRef.current = IDENTITY_TRANSFORM;
      primitiveFaceRef.current = new Map();
      faceMeshesRef.current = new Map();
      return;
    }

    const transform: DisplayTransform = { scale: deriveGlbScale(object, brepSnapshot), isGlb: true };
    displayTransformRef.current = transform;

    const maps = brepSnapshot ? buildFaceIdentityMaps(object, brepSnapshot, transform) : null;
    primitiveFaceRef.current = maps?.primitiveToFace ?? new Map();
    faceMeshesRef.current = maps?.faceToPrimitives ?? new Map();
  }, [objectReadyKey, brepSnapshot, resolvedAssetFormat, objectRef]);

  return { displayTransformRef, primitiveFaceRef, faceMeshesRef };
}
