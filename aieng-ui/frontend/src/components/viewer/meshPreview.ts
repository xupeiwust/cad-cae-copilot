import * as THREE from "three";

import type { MeshPreviewResponse } from "../../types";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";

const WIREFRAME_COLOR = 0x22d3ee; // cyan-400
const WIREFRAME_OPACITY = 0.35;

/**
 * Build a surface wireframe overlay group from a mesh preview payload.
 *
 * Nodes are transformed from the model frame (mm, Z-up) to the viewer display
 * frame using the same mapping as face picking and highlight overlays.  The
 * result is a semi-transparent `LineSegments` object drawn through the model.
 */
export function buildMeshPreviewGroup(
  preview: MeshPreviewResponse,
  transform: DisplayTransform,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "mesh-preview";

  const rawNodes = preview.nodes ?? [];
  const rawEdges = preview.edges ?? [];
  if (rawNodes.length === 0 || rawEdges.length === 0) return group;

  const positions = new Float32Array(rawEdges.length * 2 * 3);
  let offset = 0;
  for (const [i, j] of rawEdges) {
    const a = rawNodes[i];
    const b = rawNodes[j];
    if (!a || !b) continue;
    const pa = modelToDisplayVec(a[0], a[1], a[2], transform);
    const pb = modelToDisplayVec(b[0], b[1], b[2], transform);
    positions[offset++] = pa.x;
    positions[offset++] = pa.y;
    positions[offset++] = pa.z;
    positions[offset++] = pb.x;
    positions[offset++] = pb.y;
    positions[offset++] = pb.z;
  }

  if (offset === 0) return group;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions.slice(0, offset), 3));

  const material = new THREE.LineBasicMaterial({
    color: WIREFRAME_COLOR,
    transparent: true,
    opacity: WIREFRAME_OPACITY,
    depthTest: false,
  });
  material.polygonOffset = true;
  material.polygonOffsetFactor = -1;

  const lines = new THREE.LineSegments(geometry, material);
  lines.renderOrder = 900;
  group.add(lines);

  return group;
}

/** Dispose every geometry/material under the mesh preview group. */
export function disposeMeshPreviewGroup(group: THREE.Group): void {
  group.traverse((obj) => {
    if (obj instanceof THREE.LineSegments || obj instanceof THREE.Line || obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material.dispose();
    }
  });
}
