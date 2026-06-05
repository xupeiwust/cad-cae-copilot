import * as THREE from "three";

import type { BrepGraphSnapshot } from "../../appTypes";

// ── viewer ↔ model coordinate frames ────────────────────────────────────────
// build123d exports GLB in glTF's Y-up convention scaled to metres, but the
// backend B-Rep faces (geometry/topology_map.json) stay in the original model
// frame: Z-up, millimetres. Picking and face-highlight both compare *viewer*
// coordinates against those B-Rep faces, so without mapping between the frames
// every click resolves to whichever face sits nearest the origin (≈1–2 faces)
// and the highlight overlay never matches a triangle. STL previews are already
// in the model frame, so their transform is the identity.
//   model → display:  (x, y, z) → ( x·s,  z·s, −y·s)
//   display → model:  (x, y, z) → ( x/s, −z/s,  y/s)
export type DisplayTransform = { scale: number; isGlb: boolean };
export const IDENTITY_TRANSFORM: DisplayTransform = { scale: 1, isGlb: false };

export function displayToModelPoint(p: THREE.Vector3, t: DisplayTransform): THREE.Vector3 {
  if (!t.isGlb) return p.clone();
  return new THREE.Vector3(p.x / t.scale, -p.z / t.scale, p.y / t.scale);
}

export function modelToDisplayVec(x: number, y: number, z: number, t: DisplayTransform): THREE.Vector3 {
  if (!t.isGlb) return new THREE.Vector3(x, y, z);
  return new THREE.Vector3(x * t.scale, z * t.scale, -y * t.scale);
}

// Recover the export scale from data (rather than hard-coding mm→m): compare
// the union of B-Rep face bounding boxes (model frame) against the displayed
// object's bounds. Falls back to 0.001 (build123d's mm→m) when unknown.
export function deriveGlbScale(object: THREE.Object3D, snapshot: BrepGraphSnapshot | null): number {
  const FALLBACK = 0.001;
  if (!snapshot) return FALLBACK;
  const mn = [Infinity, Infinity, Infinity];
  const mx = [-Infinity, -Infinity, -Infinity];
  let any = false;
  for (const id in snapshot.faces) {
    const bb = snapshot.faces[id]?.bounding_box;
    if (!bb || bb.length !== 6) continue;
    any = true;
    for (let i = 0; i < 3; i++) {
      mn[i] = Math.min(mn[i], bb[i]);
      mx[i] = Math.max(mx[i], bb[i + 3]);
    }
  }
  if (!any) return FALLBACK;
  const modelMax = Math.max(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]);
  const box = new THREE.Box3().setFromObject(object);
  const dispMax = Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z);
  if (!(modelMax > 0) || !(dispMax > 0) || !Number.isFinite(dispMax)) return FALLBACK;
  return dispMax / modelMax;
}
