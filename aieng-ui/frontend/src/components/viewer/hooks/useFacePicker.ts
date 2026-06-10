import { useEffect, useRef } from "react";
import * as THREE from "three";

import { api } from "../../../api";
import type { PickedFace } from "../../../appTypes";
import { displayToModelPoint, type DisplayTransform } from "../../viewer/coordinateFrames";

/**
 * Raycast click handler for face picking.
 *
 * - Fast path: if the hit primitive is already mapped to a B-Rep face via
 *   `primitiveFaceRef`, resolve locally.
 * - Fallback: convert the hit point to model coordinates and call the backend
 *   `pickFace` endpoint.
 */
export function useFacePicker(
  hostRef: React.RefObject<HTMLDivElement | null>,
  objectRef: React.RefObject<THREE.Object3D | null>,
  cameraRef: React.RefObject<THREE.PerspectiveCamera | null>,
  primitiveFaceRef: React.MutableRefObject<Map<THREE.Object3D, PickedFace>>,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  projectId: string | null | undefined,
  onAddPickedFace: (face: PickedFace) => void,
  setTooltipFace: (face: PickedFace | null) => void,
) {
  // Stable callback refs.
  const onAddPickedFaceRef = useRef(onAddPickedFace);
  const setTooltipFaceRef = useRef(setTooltipFace);
  onAddPickedFaceRef.current = onAddPickedFace;
  setTooltipFaceRef.current = setTooltipFace;

  useEffect(() => {
    const host = hostRef.current;
    const camera = cameraRef.current;
    if (!host || !camera) return;

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onClick = (event: MouseEvent) => {
      const object3d = objectRef.current;
      if (!host || !object3d || !projectId) return;

      const rect = host.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);

      const pickTargets = object3d instanceof THREE.Mesh ? [object3d] : object3d.children;
      const intersects = raycaster.intersectObjects(pickTargets, true);
      if (intersects.length === 0) {
        setTooltipFaceRef.current(null);
        return;
      }

      const hit = intersects[0];
      const mappedFace = primitiveFaceRef.current.get(hit.object);
      if (mappedFace) {
        onAddPickedFaceRef.current(mappedFace);
        setTooltipFaceRef.current(mappedFace);
        return;
      }

      const pt = displayToModelPoint(hit.point, displayTransformRef.current);
      api
        .pickFace(projectId, pt.x, pt.y, pt.z)
        .then((data) => {
          if (data && data.pointer) {
            const face: PickedFace = {
              pointer: data.pointer as string,
              label: (data.label as string) || (data.pointer as string),
              surface_type: (data.surface_type as string) || "unknown",
              roles: Array.isArray(data.roles) ? (data.roles as string[]) : [],
            };
            onAddPickedFaceRef.current(face);
            setTooltipFaceRef.current(face);
          }
        })
        .catch(() => setTooltipFaceRef.current(null));
    };

    host.addEventListener("click", onClick);
    return () => {
      host.removeEventListener("click", onClick);
    };
  }, [hostRef, cameraRef, objectRef, primitiveFaceRef, displayTransformRef, projectId]);
}
