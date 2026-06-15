import { useEffect, useRef } from "react";
import * as THREE from "three";

import type { PickedFace } from "../../../appTypes";
import type { FieldProbe, SolverFieldDescriptor } from "../../../types";
import { displayToModelPoint, type DisplayTransform } from "../../viewer/coordinateFrames";
import { buildUniformGrid, nearestNodeIndex } from "../../viewer/fieldColors";

/**
 * Click-to-query field probe. When the user clicks on the loaded model while a
 * real FRD result field is active, the hook finds the nearest solver node to the
 * hit point and reports its value + coordinates + optional face pointer.
 *
 * The hook co-exists with face picking: a click both selects the face (existing
 * behaviour) and surfaces the probe tooltip.
 */
export function useFieldProbe(
  hostRef: React.RefObject<HTMLDivElement | null>,
  objectRef: React.RefObject<THREE.Object3D | null>,
  cameraRef: React.RefObject<THREE.PerspectiveCamera | null>,
  primitiveFaceRef: React.MutableRefObject<Map<THREE.Object3D, PickedFace>>,
  displayTransformRef: React.MutableRefObject<DisplayTransform>,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  onFieldProbe: (probe: FieldProbe | null) => void,
) {
  const onFieldProbeRef = useRef(onFieldProbe);
  onFieldProbeRef.current = onFieldProbe;

  const fieldDescriptorRef = useRef(fieldDescriptor);
  fieldDescriptorRef.current = fieldDescriptor;

  const descriptorKey = fieldDescriptor
    ? [
        fieldDescriptor.project_id,
        fieldDescriptor.field_name,
        fieldDescriptor.values?.length ?? 0,
        fieldDescriptor.node_coords?.length ?? 0,
      ].join("|")
    : "";

  const gridRef = useRef<ReturnType<typeof buildUniformGrid> | null>(null);
  useEffect(() => {
    const descriptor = fieldDescriptorRef.current;
    if (
      descriptor &&
      descriptor.source === "frd" &&
      Array.isArray(descriptor.node_coords) &&
      descriptor.node_coords.length > 0
    ) {
      gridRef.current = buildUniformGrid(descriptor.node_coords);
    } else {
      gridRef.current = null;
    }
  }, [descriptorKey]);

  useEffect(() => {
    const host = hostRef.current;
    const camera = cameraRef.current;
    if (!host || !camera) return;

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onClick = (event: MouseEvent) => {
      const object3d = objectRef.current;
      const descriptor = fieldDescriptorRef.current;
      if (!object3d || !descriptor) {
        onFieldProbeRef.current(null);
        return;
      }

      if (
        descriptor.source !== "frd" ||
        !Array.isArray(descriptor.values) ||
        !Array.isArray(descriptor.node_coords) ||
        descriptor.values.length === 0
      ) {
        onFieldProbeRef.current(null);
        return;
      }

      const rect = host.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);

      const pickTargets = object3d instanceof THREE.Mesh ? [object3d] : object3d.children;
      const intersects = raycaster.intersectObjects(pickTargets, true);
      if (intersects.length === 0) {
        onFieldProbeRef.current(null);
        return;
      }

      const hit = intersects[0];
      const modelPoint = displayToModelPoint(hit.point, displayTransformRef.current);
      const grid = gridRef.current;
      const nodeCoords = descriptor.node_coords;
      const values = descriptor.values;
      if (!grid || !nodeCoords || !values) {
        onFieldProbeRef.current(null);
        return;
      }

      const idx = nearestNodeIndex(modelPoint.x, modelPoint.y, modelPoint.z, grid, nodeCoords);
      if (idx < 0 || idx >= values.length) {
        onFieldProbeRef.current(null);
        return;
      }

      const mappedFace = primitiveFaceRef.current.get(hit.object);
      onFieldProbeRef.current({
        value: values[idx],
        unit: descriptor.unit ?? null,
        coord: nodeCoords[idx],
        pointer: mappedFace?.pointer ?? null,
        screenX: event.clientX - rect.left,
        screenY: event.clientY - rect.top,
      });
    };

    host.addEventListener("click", onClick);
    return () => {
      host.removeEventListener("click", onClick);
    };
  }, [hostRef, cameraRef, objectRef, primitiveFaceRef, displayTransformRef, descriptorKey]);
}
