import { useEffect } from "react";
import * as THREE from "three";

import type { FieldOverlayConfig, SolverFieldDescriptor } from "../../../types";
import { buildDeformedMesh } from "../deformedShape";

const GHOST_MATERIAL = new THREE.MeshBasicMaterial({
  color: 0x888888,
  wireframe: true,
  transparent: true,
  opacity: 0.18,
  depthWrite: false,
});

type SavedMaterials = Map<THREE.Mesh, THREE.Material | THREE.Material[]>;

/** Collect every THREE.Mesh nested under `object`. */
function _collectMeshes(object: THREE.Object3D): THREE.Mesh[] {
  const meshes: THREE.Mesh[] = [];
  object.traverse((node) => {
    if (node instanceof THREE.Mesh) meshes.push(node);
  });
  return meshes;
}

/** Swap a mesh's material for the shared ghost wireframe, saving the original. */
function _setGhostMaterial(mesh: THREE.Mesh, saved: SavedMaterials): void {
  if (!saved.has(mesh)) saved.set(mesh, mesh.material);
  mesh.material = GHOST_MATERIAL;
}

/** Restore all materials saved by `_setGhostMaterial`. */
function _restoreMaterials(saved: SavedMaterials): void {
  saved.forEach((material, mesh) => {
    mesh.material = material;
  });
  saved.clear();
}

/**
 * Render an exaggerated deformed-shape overlay on top of the loaded model.
 *
 * When enabled and displacement vectors are available, the original meshes are
 * turned into faint wireframe ghosts and deformed clones (carrying the active
 * field colours) are added to the scene. Disabling restores the original
 * materials and removes the overlay geometry.
 */
export function useDeformedShape(
  objectRef: React.MutableRefObject<THREE.Object3D | null>,
  deformedGroupRef: React.MutableRefObject<THREE.Group | null>,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  enabled: boolean,
  scale: number,
  objectReadyKey: number,
  fieldOverlayConfig?: FieldOverlayConfig | null,
) {
  const vectors = fieldDescriptor?.vectors;
  const nodeCoords = fieldDescriptor?.node_coords;
  const hasVectors = Boolean(
    fieldDescriptor &&
      Array.isArray(vectors) &&
      vectors.length > 0 &&
      Array.isArray(nodeCoords) &&
      nodeCoords.length > 0 &&
      vectors.length === nodeCoords.length,
  );

  useEffect(() => {
    const object = objectRef.current;
    const group = deformedGroupRef.current;
    if (!object || !group) return;

    function disposeChild(child: THREE.Object3D): void {
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose();
        const material = child.material;
        if (Array.isArray(material)) {
          material.forEach((m) => m.dispose());
        } else {
          material.dispose();
        }
      }
    }

    // Always clear the overlay group before rebuilding; restoring original
    // materials is handled by the cleanup phase below.
    for (const child of group.children.slice()) {
      group.remove(child);
      disposeChild(child);
    }

    if (!enabled || !hasVectors || !vectors || !nodeCoords) {
      return;
    }

    const savedMaterials: SavedMaterials = new Map();

    const meshes = _collectMeshes(object);
    for (const mesh of meshes) {
      _setGhostMaterial(mesh, savedMaterials);
      const deformed = buildDeformedMesh(mesh, nodeCoords, vectors, scale);
      group.add(deformed);
    }

    return () => {
      _restoreMaterials(savedMaterials);
      for (const child of group.children.slice()) {
        group.remove(child);
        disposeChild(child);
      }
    };
    // Rebuild whenever the object, active field, displacement data, scale, or
    // legend controls change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    objectReadyKey,
    fieldDescriptor?.field_name,
    fieldDescriptor?.project_id,
    vectors,
    nodeCoords,
    enabled,
    scale,
    fieldOverlayConfig?.colormap,
    fieldOverlayConfig?.clampMin,
    fieldOverlayConfig?.clampMax,
    fieldOverlayConfig?.bands,
    fieldOverlayConfig?.thresholdMin,
    fieldOverlayConfig?.thresholdMax,
  ]);
}
