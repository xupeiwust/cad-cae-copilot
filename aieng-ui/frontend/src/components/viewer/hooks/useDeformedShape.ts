import { useEffect, useRef } from "react";
import * as THREE from "three";

import type { FieldOverlayConfig, SolverFieldDescriptor } from "../../../types";
import { applyDeformationScale, buildDeformedMesh } from "../deformedShape";

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

function _disposeMesh(child: THREE.Object3D): void {
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

/**
 * Render an exaggerated deformed-shape overlay on top of the loaded model.
 *
 * When enabled and displacement vectors are available, the original meshes are
 * turned into faint wireframe ghosts and deformed clones (carrying the active
 * field colours) are added to the scene. Disabling restores the original
 * materials and removes the overlay geometry.
 *
 * Supports two playback modes for #255 result animation:
 *  - "sweep": scale oscillates 0 -> amplitude -> 0 (good for static deflections)
 *  - "oscillate": scale oscillates -amplitude -> +amplitude (good for modal /
 *    buckling mode shapes where the sign of the eigenvector is arbitrary)
 */
export function useDeformedShape(
  objectRef: React.MutableRefObject<THREE.Object3D | null>,
  deformedGroupRef: React.MutableRefObject<THREE.Group | null>,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  enabled: boolean,
  scale: number,
  objectReadyKey: number,
  fieldOverlayConfig?: FieldOverlayConfig | null,
  animate?: boolean,
  animationMode: "sweep" | "oscillate" = "sweep",
  animationSpeed = 1.0,
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

  const savedMaterialsRef = useRef<SavedMaterials>(new Map());
  const deformedMeshesRef = useRef<THREE.Mesh[]>([]);

  // Build (or rebuild) the deformed mesh clones when the geometry, active field,
  // or legend config changes.  This is deliberately separate from scale updates
  // so animation does not pay the cost of re-cloning every frame.
  useEffect(() => {
    const object = objectRef.current;
    const group = deformedGroupRef.current;
    if (!object || !group) return;

    // Tear down any previous overlay.
    _restoreMaterials(savedMaterialsRef.current);
    for (const child of group.children.slice()) {
      group.remove(child);
      _disposeMesh(child);
    }
    deformedMeshesRef.current = [];

    if (!enabled || !hasVectors || !vectors || !nodeCoords) {
      return;
    }

    const meshes = _collectMeshes(object);
    for (const mesh of meshes) {
      _setGhostMaterial(mesh, savedMaterialsRef.current);
      const deformed = buildDeformedMesh(mesh, nodeCoords, vectors, scale);
      group.add(deformed);
      deformedMeshesRef.current.push(deformed);
    }

    return () => {
      _restoreMaterials(savedMaterialsRef.current);
      for (const child of group.children.slice()) {
        group.remove(child);
        _disposeMesh(child);
      }
      deformedMeshesRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    objectReadyKey,
    fieldDescriptor?.field_name,
    fieldDescriptor?.project_id,
    fieldDescriptor?.load_case_id,
    vectors,
    nodeCoords,
    enabled,
    fieldOverlayConfig?.colormap,
    fieldOverlayConfig?.clampMin,
    fieldOverlayConfig?.clampMax,
    fieldOverlayConfig?.bands,
    fieldOverlayConfig?.thresholdMin,
    fieldOverlayConfig?.thresholdMax,
  ]);

  // Apply manual scale changes when not animating.
  useEffect(() => {
    if (animate) return;
    for (const mesh of deformedMeshesRef.current) {
      applyDeformationScale(mesh.geometry as THREE.BufferGeometry, scale);
    }
  }, [scale, animate]);

  // Animate the deformed shape by updating geometry positions every frame.
  useEffect(() => {
    if (!animate || deformedMeshesRef.current.length === 0) return;

    const start = performance.now();
    const periodMs = 2000 / Math.max(0.1, animationSpeed);
    let rafId = 0;

    function tick(now: number) {
      const t = ((now - start) / periodMs) * 2 * Math.PI;
      let effectiveScale: number;
      if (animationMode === "oscillate") {
        effectiveScale = scale * Math.sin(t);
      } else {
        effectiveScale = scale * (0.5 + 0.5 * Math.sin(t));
      }
      for (const mesh of deformedMeshesRef.current) {
        applyDeformationScale(mesh.geometry as THREE.BufferGeometry, effectiveScale);
      }
      rafId = requestAnimationFrame(tick);
    }

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [animate, animationMode, animationSpeed, scale]);
}
