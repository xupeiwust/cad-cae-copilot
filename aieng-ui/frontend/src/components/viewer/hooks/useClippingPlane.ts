import { useEffect } from "react";
import * as THREE from "three";

import type { FieldOverlayConfig, SolverFieldDescriptor } from "../../../types";
import type { ClipAxis } from "../clippingPlane";
import {
  applyClippingPlane,
  buildClipCapMesh,
  buildClipPlane,
  disposeClipCapMesh,
  removeClippingPlane,
} from "../clippingPlane";

const CLIP_CAP_GROUP_NAME = "clip-cap-group";

/**
 * Manage an axis-aligned clipping plane for the loaded model.
 *
 * When enabled, every mesh material under `objectRef` is clipped by the plane,
 * and a colored cap plane showing the active field on the cut face is added to
 * the scene. Disabling restores materials and removes the cap.
 */
export function useClippingPlane(
  rendererRef: React.MutableRefObject<THREE.WebGLRenderer | null>,
  sceneRef: React.MutableRefObject<THREE.Scene | null>,
  objectRef: React.MutableRefObject<THREE.Object3D | null>,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  config: FieldOverlayConfig | null | undefined,
  enabled: boolean,
  axis: ClipAxis,
  position: number,
  flip: boolean,
  objectReadyKey: number,
) {
  useEffect(() => {
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const object = objectRef.current;
    if (!renderer || !scene || !object) return;

    // Clean up any previously-created cap group.
    const existingGroup = scene.getObjectByName(CLIP_CAP_GROUP_NAME);
    if (existingGroup) {
      scene.remove(existingGroup);
      existingGroup.traverse((child) => {
        if (child instanceof THREE.Mesh && child.name === "clip-cap") {
          disposeClipCapMesh(child);
        }
      });
    }

    if (!enabled) {
      renderer.localClippingEnabled = false;
      removeClippingPlane(object);
      return;
    }

    const plane = buildClipPlane(object, axis, position, flip);
    applyClippingPlane(object, plane);
    renderer.localClippingEnabled = true;

    if (fieldDescriptor) {
      const cap = buildClipCapMesh(object, axis, position, fieldDescriptor, config);
      if (cap) {
        const group = new THREE.Group();
        group.name = CLIP_CAP_GROUP_NAME;
        group.add(cap);
        scene.add(group);
      }
    }

    return () => {
      renderer.localClippingEnabled = false;
      removeClippingPlane(object);
      const group = scene.getObjectByName(CLIP_CAP_GROUP_NAME);
      if (group) {
        scene.remove(group);
        group.traverse((child) => {
          if (child instanceof THREE.Mesh && child.name === "clip-cap") {
            disposeClipCapMesh(child);
          }
        });
      }
    };
    // Rebuild whenever the object, clip parameters, active field, or legend
    // controls change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    enabled,
    axis,
    position,
    flip,
    objectReadyKey,
    fieldDescriptor?.field_name,
    fieldDescriptor?.project_id,
    fieldDescriptor?.values?.length,
    fieldDescriptor?.node_coords?.length,
    config?.colormap,
    config?.clampMin,
    config?.clampMax,
    config?.bands,
    config?.thresholdMin,
    config?.thresholdMax,
  ]);
}
