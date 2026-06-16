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

/**
 * Apply a uniform exaggeration scale to every vertex of a BufferGeometry.
 * Each vertex is matched to its nearest FRD node via the same spatial grid
 * used for field colouring, then offset by `scale * displacement_vector`.
 */
export function applyDeformation(
  geometry: THREE.BufferGeometry,
  nodeCoords: [number, number, number][],
  vectors: [number, number, number][],
  scale: number,
): void {
  const pos = geometry.attributes.position;
  if (!pos || pos.count === 0 || nodeCoords.length === 0 || vectors.length === 0) {
    return;
  }

  const grid = buildUniformGrid(nodeCoords);
  const original = new Float32Array(pos.array.length);
  original.set(pos.array);

  for (let i = 0; i < pos.count; i += 1) {
    const x = original[i * 3];
    const y = original[i * 3 + 1];
    const z = original[i * 3 + 2];
    const nodeIdx = nearestNodeIndex(x, y, z, grid, nodeCoords);
    if (nodeIdx < 0 || nodeIdx >= vectors.length) continue;
    const [dx, dy, dz] = vectors[nodeIdx];
    pos.array[i * 3] = x + scale * dx;
    pos.array[i * 3 + 1] = y + scale * dy;
    pos.array[i * 3 + 2] = z + scale * dz;
  }

  pos.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
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
  applyDeformation(deformedGeo, nodeCoords, vectors, scale);

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
