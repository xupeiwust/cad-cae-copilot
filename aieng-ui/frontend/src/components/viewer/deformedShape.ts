import * as THREE from "three";

import { buildUniformGrid, nearestNodeIndex } from "./fieldColors";

/**
 * Compute an exaggeration scale so the maximum displayed displacement is a
 * visible-but-still-readable fraction of the model bounding-box diagonal.
 * The result is a dimensionless multiplier applied to raw displacement vectors.
 */
export function computeDeformationScale(
  vectors: [number, number, number][],
  object: THREE.Object3D,
  targetRatio = 0.05,
): number {
  let maxDisp = 0;
  for (const [dx, dy, dz] of vectors) {
    const mag = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (mag > maxDisp) maxDisp = mag;
  }
  if (maxDisp === 0) return 0;

  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return 0;
  const size = new THREE.Vector3();
  box.getSize(size);
  const diagonal = Math.sqrt(size.x * size.x + size.y * size.y + size.z * size.z);
  if (!Number.isFinite(diagonal) || diagonal === 0) return 0;

  return (targetRatio * diagonal) / maxDisp;
}

type DeformationMap = {
  original: Float32Array;
  vectors: Float32Array;
};

/**
 * Build a reusable vertex -> displacement mapping for a BufferGeometry.
 * Each vertex is matched to its nearest FRD node via the same spatial grid used
 * for field colouring.  The original positions and the per-vertex displacement
 * vectors are stored on `geometry.userData.deformationMap` so the scale can be
 * updated cheaply later (e.g. during animation).
 */
export function prepareDeformation(
  geometry: THREE.BufferGeometry,
  nodeCoords: [number, number, number][],
  vectors: [number, number, number][],
): DeformationMap {
  const pos = geometry.attributes.position;
  const original = new Float32Array(pos.array.length);
  original.set(pos.array as Float32Array);

  const perVertexVectors = new Float32Array(pos.count * 3);
  const grid = nodeCoords.length > 0 ? buildUniformGrid(nodeCoords) : null;

  for (let i = 0; i < pos.count; i += 1) {
    const x = original[i * 3];
    const y = original[i * 3 + 1];
    const z = original[i * 3 + 2];
    const nodeIdx = grid ? nearestNodeIndex(x, y, z, grid, nodeCoords) : -1;
    if (nodeIdx >= 0 && nodeIdx < vectors.length) {
      const [dx, dy, dz] = vectors[nodeIdx];
      perVertexVectors[i * 3] = dx;
      perVertexVectors[i * 3 + 1] = dy;
      perVertexVectors[i * 3 + 2] = dz;
    }
  }

  const map: DeformationMap = { original, vectors: perVertexVectors };
  geometry.userData.deformationMap = map;
  return map;
}

/**
 * Apply a uniform exaggeration scale to every vertex of a BufferGeometry that
 * has previously been prepared with `prepareDeformation`.
 */
export function applyDeformationScale(
  geometry: THREE.BufferGeometry,
  scale: number,
): void {
  const map = geometry.userData.deformationMap as DeformationMap | undefined;
  const pos = geometry.attributes.position;
  if (!map || !pos || pos.count === 0) return;

  const { original, vectors } = map;
  for (let i = 0; i < pos.count; i += 1) {
    pos.array[i * 3] = original[i * 3] + scale * vectors[i * 3];
    pos.array[i * 3 + 1] = original[i * 3 + 1] + scale * vectors[i * 3 + 1];
    pos.array[i * 3 + 2] = original[i * 3 + 2] + scale * vectors[i * 3 + 2];
  }

  pos.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
}

/**
 * Apply a uniform exaggeration scale to every vertex of a BufferGeometry.
 * Each vertex is matched to its nearest FRD node via the same spatial grid
 * used for field colouring, then offset by `scale * displacement_vector`.
 *
 * This is a one-shot convenience; for repeated updates use
 * `prepareDeformation` + `applyDeformationScale`.
 */
export function applyDeformation(
  geometry: THREE.BufferGeometry,
  nodeCoords: [number, number, number][],
  vectors: [number, number, number][],
  scale: number,
): void {
  prepareDeformation(geometry, nodeCoords, vectors);
  applyDeformationScale(geometry, scale);
}

/**
 * Clone a mesh, deform its geometry, and copy the current vertex-color
 * attribute so the deformed shape carries the active field colouring.
 */
export function buildDeformedMesh(
  source: THREE.Mesh,
  nodeCoords: [number, number, number][],
  vectors: [number, number, number][],
  scale: number,
): THREE.Mesh {
  const sourceGeo = source.geometry as THREE.BufferGeometry;
  const deformedGeo = sourceGeo.clone();
  prepareDeformation(deformedGeo, nodeCoords, vectors);
  applyDeformationScale(deformedGeo, scale);

  const hasColors = Boolean(
    deformedGeo.attributes.color && deformedGeo.attributes.color.count > 0,
  );
  const material = new THREE.MeshStandardMaterial({
    vertexColors: hasColors,
    metalness: 0.1,
    roughness: 0.65,
    transparent: false,
  });

  const mesh = new THREE.Mesh(deformedGeo, material);
  mesh.name = `${source.name || "mesh"}_deformed`;
  mesh.position.copy(source.position);
  mesh.rotation.copy(source.rotation);
  mesh.scale.copy(source.scale);
  return mesh;
}

/**
 * Build a faint wireframe ghost of the original mesh to sit behind the
 * deformed shape and make the exaggeration visually obvious.
 */
export function buildGhostMesh(source: THREE.Mesh): THREE.Mesh {
  const ghostGeo = (source.geometry as THREE.BufferGeometry).clone();
  const material = new THREE.MeshBasicMaterial({
    color: 0x888888,
    wireframe: true,
    transparent: true,
    opacity: 0.18,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(ghostGeo, material);
  mesh.name = `${source.name || "mesh"}_ghost`;
  mesh.position.copy(source.position);
  mesh.rotation.copy(source.rotation);
  mesh.scale.copy(source.scale);
  return mesh;
}
