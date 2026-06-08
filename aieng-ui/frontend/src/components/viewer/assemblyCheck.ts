import * as THREE from "three";

import { brokenSymmetryPartBoxes, floatingPartBoxes, type PartBox } from "../../app/geometryReport";
import type { GeometryReportResponse } from "../../types";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";

// Red = floating (detached) part; amber = part in a broken / missing symmetry pair.
const FLOATING_COLOR = 0xef4444;
const SYMMETRY_COLOR = 0xf59e0b;

/**
 * Map a model-frame AABB to a display-frame AABB. The display transform is an
 * axis permutation + scale + sign flip, so it maps an axis-aligned box to an
 * axis-aligned box: expanding by the 8 transformed corners recovers it exactly.
 */
function displayBox(bbox: number[], t: DisplayTransform): THREE.Box3 {
  const [x0, y0, z0, x1, y1, z1] = bbox;
  const box = new THREE.Box3();
  for (const x of [x0, x1]) {
    for (const y of [y0, y1]) {
      for (const z of [z0, z1]) {
        box.expandByPoint(modelToDisplayVec(x, y, z, t));
      }
    }
  }
  return box;
}

function addBoxes(group: THREE.Group, parts: PartBox[], color: number, t: DisplayTransform): void {
  for (const { bbox } of parts) {
    const helper = new THREE.Box3Helper(displayBox(bbox, t), new THREE.Color(color));
    helper.renderOrder = 1000;
    // Draw through the model so the offending part's box is always visible.
    (helper.material as THREE.LineBasicMaterial).depthTest = false;
    group.add(helper);
  }
}

/**
 * Build the assembly-check overlay group: a red wireframe box around each
 * floating part and an amber box around each part in a broken symmetry pair.
 * Pure given the transform; mounts under the viewer scene. Returns an empty
 * group when there is no report (nothing to flag).
 */
export function buildAssemblyCheckGroup(
  report: GeometryReportResponse | null,
  transform: DisplayTransform,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "assembly-check";
  if (!report) return group;
  addBoxes(group, floatingPartBoxes(report), FLOATING_COLOR, transform);
  addBoxes(group, brokenSymmetryPartBoxes(report), SYMMETRY_COLOR, transform);
  return group;
}

/** Dispose every geometry/material under the overlay group before discarding it. */
export function disposeAssemblyCheckGroup(group: THREE.Group): void {
  group.traverse((obj) => {
    if (obj instanceof THREE.Mesh || obj instanceof THREE.Line || obj instanceof THREE.LineSegments) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material.dispose();
    }
  });
}
