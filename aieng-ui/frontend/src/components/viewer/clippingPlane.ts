import * as THREE from "three";

import type { FieldOverlayConfig, SolverFieldDescriptor } from "../../types";
import { buildUniformGrid, nearestNodeIndex, normalizeFieldValue, sampleColormap } from "./fieldColors";

export type ClipAxis = "x" | "y" | "z";

const AXIS_INDEX: Record<ClipAxis, number> = { x: 0, y: 1, z: 2 };

/**
 * Return the plane normal for an axis-aligned clip. `flip` inverts the visible
 * side of the plane.
 */
export function clipNormal(axis: ClipAxis, flip: boolean): THREE.Vector3 {
  const sign = flip ? -1 : 1;
  if (axis === "x") return new THREE.Vector3(sign, 0, 0);
  if (axis === "y") return new THREE.Vector3(0, sign, 0);
  return new THREE.Vector3(0, 0, sign);
}

/**
 * Map a normalized clip position [0, 1] along `axis` to a world-coordinate
 * value based on the object's bounding box.
 */
export function clipCoordinate(
  object: THREE.Object3D,
  axis: ClipAxis,
  position: number,
  box?: THREE.Box3,
): number {
  const b = box ?? new THREE.Box3().setFromObject(object);
  if (b.isEmpty()) return 0;
  const idx = AXIS_INDEX[axis];
  const min = b.min.getComponent(idx);
  const max = b.max.getComponent(idx);
  const t = Math.max(0, Math.min(1, position));
  return min + (max - min) * t;
}

/**
 * Build a THREE.Plane that clips the object at the requested normalized position.
 */
export function buildClipPlane(object: THREE.Object3D, axis: ClipAxis, position: number, flip: boolean): THREE.Plane {
  const coord = clipCoordinate(object, axis, position);
  const normal = clipNormal(axis, flip);
  const point = new THREE.Vector3();
  point.setComponent(AXIS_INDEX[axis], coord);
  return new THREE.Plane(normal, -normal.dot(point));
}

/**
 * Apply a clipping plane to every mesh material under `object`.
 */
export function applyClippingPlane(object: THREE.Object3D, plane: THREE.Plane): void {
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials) {
      material.clippingPlanes = [plane];
    }
  });
}

/**
 * Remove clipping planes from every mesh material under `object`.
 */
export function removeClippingPlane(object: THREE.Object3D): void {
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials) {
      material.clippingPlanes = [];
    }
  });
}

/**
 * Build a colored slice-plane mesh that shows the active field on the cut face.
 * The plane is axis-aligned and sampled at each vertex via nearest-node lookup
 * against the FRD node coordinates.
 */
export function buildClipCapMesh(
  object: THREE.Object3D,
  axis: ClipAxis,
  position: number,
  descriptor: SolverFieldDescriptor,
  config?: FieldOverlayConfig | null,
): THREE.Mesh | null {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return null;

  const values = descriptor.values;
  const nodeCoords = descriptor.node_coords;
  if (!Array.isArray(values) || values.length === 0 || !Array.isArray(nodeCoords) || nodeCoords.length === 0) {
    return null;
  }

  const idx = AXIS_INDEX[axis];
  const center = new THREE.Vector3();
  box.getCenter(center);
  const size = new THREE.Vector3();
  box.getSize(size);

  const coord = clipCoordinate(object, axis, position, box);

  // Dimensions of the plane in the two axes orthogonal to the clip axis.
  const dims = [size.x, size.y, size.z];
  dims.splice(idx, 1);
  const [width, height] = dims;
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;

  // Cap resolution: enough to resolve gradients, but bounded so huge models
  // don't allocate excessive vertices.
  const segmentsX = Math.min(64, Math.max(1, Math.round(width)));
  const segmentsY = Math.min(64, Math.max(1, Math.round(height)));
  const geometry = new THREE.PlaneGeometry(width, height, segmentsX, segmentsY);

  // Rotate the plane so its normal points along the clip axis, then translate
  // it to the clip coordinate.
  if (axis === "x") {
    geometry.rotateY(Math.PI / 2);
  } else if (axis === "y") {
    geometry.rotateX(Math.PI / 2);
  }
  const translation = center.clone();
  translation.setComponent(idx, coord);
  geometry.translate(translation.x, translation.y, translation.z);

  const grid = buildUniformGrid(nodeCoords);
  const pos = geometry.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const maskColor = new THREE.Color(0x888888);

  for (let i = 0; i < pos.count; i++) {
    const vx = pos.getX(i);
    const vy = pos.getY(i);
    const vz = pos.getZ(i);
    const bestIdx = nearestNodeIndex(vx, vy, vz, grid, nodeCoords);
    const val = values[bestIdx] ?? descriptor.min_value;
    const t = normalizeFieldValue(val, descriptor.min_value, descriptor.max_value, config ?? null);
    const col = t === null ? maskColor : sampleColormap(t, config?.colormap ?? descriptor.colormap);
    colors[i * 3] = col.r;
    colors[i * 3 + 1] = col.g;
    colors[i * 3 + 2] = col.b;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));

  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    side: THREE.DoubleSide,
    metalness: 0.1,
    roughness: 0.65,
    // The cap must not itself be clipped away.
    clippingPlanes: [],
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = "clip-cap";
  return mesh;
}

/**
 * Dispose the geometry and material of a clipping-cap mesh.
 */
export function disposeClipCapMesh(mesh: THREE.Mesh): void {
  mesh.geometry.dispose();
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  for (const material of materials) material.dispose();
}
