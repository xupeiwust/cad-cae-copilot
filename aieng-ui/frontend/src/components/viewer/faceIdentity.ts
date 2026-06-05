import * as THREE from "three";

import type { BrepFaceEntity, BrepGraphSnapshot, PickedFace } from "../../appTypes";
import { displayToModelPoint, type DisplayTransform } from "./coordinateFrames";

// Associate each displayed mesh primitive with its B-Rep face. OCCT emits one
// glTF primitive per face and one glTF node per solid, but the GLB's primitive
// order does NOT match topology_map's face order, so we match by geometry. The
// match is **body-scoped and injective**: primitives are grouped by their solid
// node, each group is matched to its B-Rep body, then the K primitives are
// assigned 1:1 to that body's K faces (greedy by ascending centroid distance).
// This prevents a distant face from "claiming" many primitives — the failure
// mode of a naive global-nearest match, which made several faces of one part
// highlight/select as a single merged surface. Falls back to global-nearest for
// packages without body_id or when primitive/face counts don't line up.
// Returns null if nothing matches.
export function buildFaceIdentityMaps(
  object: THREE.Object3D,
  snapshot: BrepGraphSnapshot,
  transform: DisplayTransform,
): { primitiveToFace: Map<THREE.Object3D, PickedFace>; faceToPrimitives: Map<string, THREE.Mesh[]> } | null {
  const faceCenter = (f: BrepFaceEntity): THREE.Vector3 | null => {
    if (f.center && f.center.length === 3) return new THREE.Vector3(f.center[0], f.center[1], f.center[2]);
    if (f.bounding_box && f.bounding_box.length === 6) {
      const b = f.bounding_box;
      return new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
    }
    return null;
  };

  type FaceRec = { id: string; c: THREE.Vector3 };
  const allFaces: FaceRec[] = [];
  const facesByBody = new Map<string, FaceRec[]>();
  let haveBodyIds = true;
  for (const id in snapshot.faces) {
    const f = snapshot.faces[id];
    const c = faceCenter(f);
    if (!c) continue;
    const rec: FaceRec = { id, c };
    allFaces.push(rec);
    if (!f.body_id) haveBodyIds = false;
    const key = f.body_id ?? "__nobody__";
    const arr = facesByBody.get(key);
    if (arr) arr.push(rec); else facesByBody.set(key, [rec]);
  }
  if (allFaces.length === 0) return null;

  // Collect displayed primitives: vertex centroid (model frame) + owning solid.
  // GLTFLoader wraps each multi-primitive glTF mesh in its own Group (and a
  // single-primitive mesh sits under its node Object3D), so a primitive's
  // immediate parent uniquely identifies its solid — even though the scene
  // nests every solid under one root wrapper node.
  type Prim = { node: THREE.Mesh; c: THREE.Vector3 };
  const groups = new Map<THREE.Object3D, Prim[]>();
  const v = new THREE.Vector3();
  object.updateMatrixWorld(true);
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const pos = (node.geometry as THREE.BufferGeometry).attributes.position;
    if (!pos || pos.count === 0) return;
    let sx = 0, sy = 0, sz = 0;
    for (let i = 0; i < pos.count; i++) {
      v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(node.matrixWorld);
      sx += v.x; sy += v.y; sz += v.z;
    }
    const c = displayToModelPoint(new THREE.Vector3(sx / pos.count, sy / pos.count, sz / pos.count), transform);
    const key = node.parent ?? node;
    const arr = groups.get(key);
    if (arr) arr.push({ node, c }); else groups.set(key, [{ node, c }]);
  });
  if (groups.size === 0) return null;

  const primitiveToFace = new Map<THREE.Object3D, PickedFace>();
  const faceToPrimitives = new Map<string, THREE.Mesh[]>();
  const bind = (node: THREE.Mesh, faceId: string) => {
    const f = snapshot.faces[faceId];
    const pointer = f?.pointer ?? `@face:${faceId}`;
    primitiveToFace.set(node, {
      pointer,
      label: pointer,
      surface_type: f?.surface_type || "unknown",
      roles: f?.roles ?? [],
    });
    const arr = faceToPrimitives.get(faceId);
    if (arr) arr.push(node); else faceToPrimitives.set(faceId, [node]);
  };

  // Greedy injective assignment of primitives → faces by ascending distance.
  const assignInjective = (prims: Prim[], faces: FaceRec[]) => {
    const pairs: Array<{ p: number; f: number; d: number }> = [];
    for (let i = 0; i < prims.length; i++) {
      for (let k = 0; k < faces.length; k++) {
        pairs.push({ p: i, f: k, d: prims[i].c.distanceToSquared(faces[k].c) });
      }
    }
    pairs.sort((a, b) => a.d - b.d);
    const usedP = new Set<number>();
    const usedF = new Set<number>();
    for (const pr of pairs) {
      if (usedP.has(pr.p) || usedF.has(pr.f)) continue;
      usedP.add(pr.p); usedF.add(pr.f);
      bind(prims[pr.p].node, faces[pr.f].id);
    }
  };

  const globalNearest = (prims: Prim[]) => {
    for (const pr of prims) {
      let bestId: string | null = null;
      let bestD = Infinity;
      for (const fc of allFaces) {
        const d = pr.c.distanceToSquared(fc.c);
        if (d < bestD) { bestD = d; bestId = fc.id; }
      }
      if (bestId) bind(pr.node, bestId);
    }
  };

  // Without per-face body ids (older packages) the only option is the legacy
  // global-nearest match — kept so those packages don't regress.
  const canScope = haveBodyIds && facesByBody.size > 1 && !facesByBody.has("__nobody__");
  if (!canScope) {
    globalNearest([...groups.values()].flat());
    return primitiveToFace.size > 0 ? { primitiveToFace, faceToPrimitives } : null;
  }

  // Match each primitive-group (a solid) to a B-Rep body, preferring equal face
  // count and nearest centroid; greedy + injective over all equal-count pairs.
  const centroidOf = (recs: { c: THREE.Vector3 }[]): THREE.Vector3 => {
    const s = new THREE.Vector3();
    for (const r of recs) s.add(r.c);
    return s.multiplyScalar(1 / Math.max(recs.length, 1));
  };
  const groupList = [...groups.values()].map((prims) => ({ prims, c: centroidOf(prims) }));
  const bodyList = [...facesByBody.values()].map((faces) => ({ faces, c: centroidOf(faces) }));
  const bodyPairs: Array<{ g: number; b: number; d: number }> = [];
  for (let g = 0; g < groupList.length; g++) {
    for (let b = 0; b < bodyList.length; b++) {
      if (groupList[g].prims.length !== bodyList[b].faces.length) continue;
      bodyPairs.push({ g, b, d: groupList[g].c.distanceToSquared(bodyList[b].c) });
    }
  }
  bodyPairs.sort((a, b) => a.d - b.d);
  const usedG = new Set<number>();
  const usedB = new Set<number>();
  for (const pr of bodyPairs) {
    if (usedG.has(pr.g) || usedB.has(pr.b)) continue;
    usedG.add(pr.g); usedB.add(pr.b);
    assignInjective(groupList[pr.g].prims, bodyList[pr.b].faces);
  }
  // Groups with no equal-count body (e.g. GLB merged some primitives) fall back.
  for (let g = 0; g < groupList.length; g++) {
    if (!usedG.has(g)) globalNearest(groupList[g].prims);
  }
  return primitiveToFace.size > 0 ? { primitiveToFace, faceToPrimitives } : null;
}
