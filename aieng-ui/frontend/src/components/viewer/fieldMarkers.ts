import * as THREE from "three";

import type { SolverFieldDescriptor } from "../../types";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";
import { findFieldExtrema } from "./fieldExtrema";

// Peak (max) = red, min = blue — matches the thermal legend (high warm / low cool).
const MAX_COLOR = 0xef4444;
const MIN_COLOR = 0x3b82f6;

function coordsSpan(coords: [number, number, number][]): number {
  const box = new THREE.Box3();
  for (const c of coords) box.expandByPoint(new THREE.Vector3(c[0], c[1], c[2]));
  const size = new THREE.Vector3();
  box.getSize(size);
  return Math.max(size.length(), 1e-6);
}

function marker(center: THREE.Vector3, radius: number, color: number): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 16, 16),
    new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.9 }),
  );
  mesh.position.copy(center);
  mesh.renderOrder = 1001; // draw over the model so the peak is never hidden
  return mesh;
}

/**
 * Build the peak/min marker overlay: a red sphere at the field's maximum node and
 * a blue sphere at its minimum, placed in display coordinates. Only real solver
 * fields (source "frd" with per-node values) get markers — synthetic descriptors
 * return an empty group (honest: don't mark a fabricated field).
 */
export function buildFieldMarkerGroup(
  descriptor: SolverFieldDescriptor | null,
  transform: DisplayTransform,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "field-markers";
  if (
    !descriptor ||
    descriptor.source !== "frd" ||
    !Array.isArray(descriptor.values) ||
    !Array.isArray(descriptor.node_coords) ||
    descriptor.values.length === 0
  ) {
    return group;
  }
  const { max, min } = findFieldExtrema(descriptor.values, descriptor.node_coords);
  if (!max) return group;

  const radius = coordsSpan(descriptor.node_coords) * 0.025;
  const toDisplay = (c: [number, number, number]) => modelToDisplayVec(c[0], c[1], c[2], transform);
  group.add(marker(toDisplay(max.coord), radius, MAX_COLOR));
  if (min && min.index !== max.index) {
    group.add(marker(toDisplay(min.coord), radius, MIN_COLOR));
  }
  return group;
}

export function disposeFieldMarkerGroup(group: THREE.Group): void {
  group.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material.dispose();
    }
  });
}
