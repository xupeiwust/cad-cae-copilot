import { useEffect } from "react";
import * as THREE from "three";

import type { CaeSetupOverlayResponse } from "../../../types";
import type { BrepGraphSnapshot } from "../../../appTypes";
import { type DisplayTransform } from "../coordinateFrames";
import { buildCaeSetupGroup, disposeCaeSetupGroup } from "../caeSetupOverlay";

/**
 * CAE setup overlay manager.
 *
 * Draws load arrows, constraint glyphs, and bound-face highlights whenever the
 * toggle, CAE setup overlay data, or model reload changes.
 */
export function useCaeSetupOverlay(
  caeSetupGroupRef: React.RefObject<THREE.Group | null>,
  showCaeSetup: boolean,
  caeSetupOverlay: CaeSetupOverlayResponse | null,
  faceMeshesRef: React.MutableRefObject<Map<string, THREE.Mesh[]>>,
  objectRef: React.RefObject<THREE.Object3D | null>,
  brepSnapshot: BrepGraphSnapshot | null,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  objectReadyKey: number,
) {
  useEffect(() => {
    const group = caeSetupGroupRef.current;
    if (!group) return;

    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      if (child instanceof THREE.Group) disposeCaeSetupGroup(child);
    }

    if (!showCaeSetup || !caeSetupOverlay) return;
    const object = objectRef.current;
    if (!object) return;

    group.add(
      buildCaeSetupGroup(
        caeSetupOverlay,
        faceMeshesRef.current,
        object,
        brepSnapshot,
        displayTransformRef.current,
      ),
    );
  }, [
    showCaeSetup,
    caeSetupOverlay,
    objectReadyKey,
    caeSetupGroupRef,
    faceMeshesRef,
    objectRef,
    brepSnapshot,
    displayTransformRef,
  ]);
}
