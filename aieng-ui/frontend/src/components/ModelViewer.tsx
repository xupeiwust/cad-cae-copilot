import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { api } from "../api";
import type { BrepFaceEntity, BrepGraphSnapshot, CadGenerationProgress, PickedFace, ViewerLoadState } from "../appTypes";
import { fieldLabel, resolveAssetFormat } from "../appUtils";
import type { SolverFieldDescriptor } from "../types";
import { CadProgressPanel } from "./CadProgressPanel";

function sampleColormap(t: number, name?: string | null): THREE.Color {
  const c = Math.max(0, Math.min(1, t));
  if (name === "coolwarm") {
    // blue(0) -> white(0.5) -> red(1)
    const r = c < 0.5 ? 0.2 + c * 1.6 : 1.0;
    const g = c < 0.5 ? 0.2 + c * 1.6 : 1.0 - (c - 0.5) * 2.0;
    const b = c < 0.5 ? 1.0 : 1.0 - (c - 0.5) * 1.6;
    return new THREE.Color(r, g, b);
  }
  // thermal: blue -> cyan -> green -> yellow -> red
  const r = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 3)));
  const g = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 2)));
  const b = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 1)));
  return new THREE.Color(r, g, b);
}

function applyYNormalizedColors(object: THREE.Object3D, colormap?: string | null): boolean {
  let applied = false;
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const geo = node.geometry as THREE.BufferGeometry;
    const pos = geo.attributes.position;
    if (!pos) return;
    let yMin = Infinity;
    let yMax = -Infinity;
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i);
      if (y < yMin) yMin = y;
      if (y > yMax) yMax = y;
    }
    const yRange = yMax > yMin ? yMax - yMin : 1;
    const colors = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      const col = sampleColormap((pos.getY(i) - yMin) / yRange, colormap);
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    node.material = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.1, roughness: 0.65 });
    applied = true;
  });
  return applied;
}

type UniformGrid = {
  cellSize: number;
  minX: number;
  minY: number;
  minZ: number;
  cells: Map<string, number[]>;
};

function buildUniformGrid(nodeCoords: [number, number, number][]): UniformGrid {
  if (nodeCoords.length === 0) {
    return { cellSize: 1, minX: 0, minY: 0, minZ: 0, cells: new Map() };
  }
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (const [x, y, z] of nodeCoords) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  }
  const dx = maxX - minX, dy = maxY - minY, dz = maxZ - minZ;
  const diagonal = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const cellSize = Math.max(diagonal / Math.sqrt(nodeCoords.length), 1e-6);

  const cells = new Map<string, number[]>();
  for (let i = 0; i < nodeCoords.length; i++) {
    const [x, y, z] = nodeCoords[i];
    const ix = Math.floor((x - minX) / cellSize);
    const iy = Math.floor((y - minY) / cellSize);
    const iz = Math.floor((z - minZ) / cellSize);
    const key = `${ix},${iy},${iz}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key)!.push(i);
  }
  return { cellSize, minX, minY, minZ, cells };
}

function nearestNodeIndex(
  vx: number,
  vy: number,
  vz: number,
  grid: UniformGrid,
  nodeCoords: [number, number, number][],
): number {
  const { cellSize, minX, minY, minZ, cells } = grid;
  const ix = Math.floor((vx - minX) / cellSize);
  const iy = Math.floor((vy - minY) / cellSize);
  const iz = Math.floor((vz - minZ) / cellSize);

  let bestIdx = -1;
  let bestDist = Infinity;
  let searchRadius = 1;

  while (searchRadius <= 3) {
    let foundAny = false;
    for (let dx = -searchRadius; dx <= searchRadius; dx++) {
      for (let dy = -searchRadius; dy <= searchRadius; dy++) {
        for (let dz = -searchRadius; dz <= searchRadius; dz++) {
          if (searchRadius > 1 && Math.abs(dx) < searchRadius && Math.abs(dy) < searchRadius && Math.abs(dz) < searchRadius) {
            continue;
          }
          const key = `${ix + dx},${iy + dy},${iz + dz}`;
          const indices = cells.get(key);
          if (!indices) continue;
          foundAny = true;
          for (const idx of indices) {
            const [nx, ny, nz] = nodeCoords[idx];
            const d = (vx - nx) ** 2 + (vy - ny) ** 2 + (vz - nz) ** 2;
            if (d < bestDist) {
              bestDist = d;
              bestIdx = idx;
            }
          }
        }
      }
    }
    if (bestIdx !== -1) break;
    if (!foundAny && searchRadius >= 3) break;
    searchRadius++;
  }

  if (bestIdx === -1) {
    for (let i = 0; i < nodeCoords.length; i++) {
      const [nx, ny, nz] = nodeCoords[i];
      const d = (vx - nx) ** 2 + (vy - ny) ** 2 + (vz - nz) ** 2;
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }
  }
  return bestIdx;
}

function checkBboxAlignment(
  nodeCoords: [number, number, number][],
  object: THREE.Object3D,
): { status: "aligned" | "suspicious"; reason?: string } {
  const meshBox = new THREE.Box3().setFromObject(object);
  if (meshBox.isEmpty()) return { status: "suspicious", reason: "Mesh bbox empty" };

  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (const [x, y, z] of nodeCoords) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  }

  const frdCenter = new THREE.Vector3((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2);
  const meshCenter = new THREE.Vector3();
  meshBox.getCenter(meshCenter);
  const frdSize = new THREE.Vector3(maxX - minX, maxY - minY, maxZ - minZ);
  const meshSize = new THREE.Vector3();
  meshBox.getSize(meshSize);

  const effectiveMeshSize = new THREE.Vector3(
    meshSize.x < 1e-6 ? 1 : meshSize.x,
    meshSize.y < 1e-6 ? 1 : meshSize.y,
    meshSize.z < 1e-6 ? 1 : meshSize.z,
  );

  const centerDist = frdCenter.distanceTo(meshCenter);
  const meshDiagonal = Math.sqrt(
    effectiveMeshSize.x ** 2 + effectiveMeshSize.y ** 2 + effectiveMeshSize.z ** 2,
  );
  if (meshDiagonal === 0) return { status: "suspicious", reason: "Mesh has zero size" };

  if (centerDist / meshDiagonal > 0.5) {
    return {
      status: "suspicious",
      reason: `Center offset ${(centerDist / meshDiagonal * 100).toFixed(1)}% of diagonal`,
    };
  }

  const sizeRatioX = frdSize.x / (meshSize.x || 1);
  const sizeRatioY = frdSize.y / (meshSize.y || 1);
  const sizeRatioZ = frdSize.z / (meshSize.z || 1);
  if (
    sizeRatioX < 0.01 || sizeRatioX > 100 ||
    sizeRatioY < 0.01 || sizeRatioY > 100 ||
    sizeRatioZ < 0.01 || sizeRatioZ > 100
  ) {
    return { status: "suspicious", reason: "Size ratio out of bounds" };
  }
  return { status: "aligned" };
}

function applyFieldColors(
  object: THREE.Object3D,
  values: number[],
  nodeCoords: [number, number, number][],
  minVal: number,
  maxVal: number,
  colormap?: string | null,
): { applied: boolean; bboxStatus: "aligned" | "suspicious" | null; warnings: string[] } {
  let applied = false;
  const warnings: string[] = [];
  const valueRange = maxVal > minVal ? maxVal - minVal : 1;

  const grid = buildUniformGrid(nodeCoords);
  const bboxCheck = checkBboxAlignment(nodeCoords, object);

  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const geo = node.geometry as THREE.BufferGeometry;
    const pos = geo.attributes.position;
    if (!pos) return;
    const colors = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      const vx = pos.getX(i);
      const vy = pos.getY(i);
      const vz = pos.getZ(i);
      const bestIdx = nearestNodeIndex(vx, vy, vz, grid, nodeCoords);
      const val = values[bestIdx] ?? minVal;
      const t = (val - minVal) / valueRange;
      const col = sampleColormap(t, colormap);
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    node.material = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.1, roughness: 0.65 });
    applied = true;
  });
  if (bboxCheck.reason) warnings.push(bboxCheck.reason);
  return { applied, bboxStatus: bboxCheck.status, warnings };
}

function fitCameraToObject(
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update(): void },
  object: THREE.Object3D,
) {
  const bounds = new THREE.Box3().setFromObject(object);
  if (bounds.isEmpty()) return false;

  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z, 1);
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const distance = (maxDimension / (2 * Math.tan(fov / 2))) * 1.8;

  camera.near = Math.max(distance / 100, 0.1);
  camera.far = Math.max(distance * 20, 1000);
  camera.position.copy(center).add(new THREE.Vector3(distance, distance * 0.7, distance));
  camera.lookAt(center);
  camera.updateProjectionMatrix();

  controls.target.copy(center);
  controls.update();
  return true;
}

function disposeHighlightObject(child: THREE.Object3D) {
  if (child instanceof THREE.Mesh) {
    child.geometry.dispose();
    if (Array.isArray(child.material)) {
      for (const material of child.material) material.dispose();
    } else {
      child.material.dispose();
    }
  }
}

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
type DisplayTransform = { scale: number; isGlb: boolean };
const IDENTITY_TRANSFORM: DisplayTransform = { scale: 1, isGlb: false };

function displayToModelPoint(p: THREE.Vector3, t: DisplayTransform): THREE.Vector3 {
  if (!t.isGlb) return p.clone();
  return new THREE.Vector3(p.x / t.scale, -p.z / t.scale, p.y / t.scale);
}

function modelToDisplayVec(x: number, y: number, z: number, t: DisplayTransform): THREE.Vector3 {
  if (!t.isGlb) return new THREE.Vector3(x, y, z);
  return new THREE.Vector3(x * t.scale, z * t.scale, -y * t.scale);
}

// Recover the export scale from data (rather than hard-coding mm→m): compare
// the union of B-Rep face bounding boxes (model frame) against the displayed
// object's bounds. Falls back to 0.001 (build123d's mm→m) when unknown.
function deriveGlbScale(object: THREE.Object3D, snapshot: BrepGraphSnapshot | null): number {
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

function makeHighlightMaterial(): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color: 0xfacc15,
    transparent: true,
    opacity: 0.62,
    depthTest: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -6,
    polygonOffsetUnits: -6,
  });
}

// Overlay built from a tessellated primitive's *own* geometry — exact for any
// face shape (planar or curved), unlike the bbox-centroid heuristic. Geometry
// is cloned so disposeHighlightObject can free it without touching the model.
function createPrimitiveOverlay(prim: THREE.Mesh): THREE.Mesh {
  const mesh = new THREE.Mesh(prim.geometry.clone(), makeHighlightMaterial());
  prim.updateMatrixWorld(true);
  mesh.matrixAutoUpdate = false;
  mesh.matrix.copy(prim.matrixWorld);
  mesh.matrixWorldNeedsUpdate = true;
  mesh.renderOrder = 1000;
  return mesh;
}

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
function buildFaceIdentityMaps(
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

function createFaceHighlightMesh(object: THREE.Object3D, face: BrepFaceEntity, transform: DisplayTransform): THREE.Mesh | null {
  const bbox = face.bounding_box;
  if (!bbox || bbox.length !== 6) return null;
  // Map the model-frame face bbox/center/normal into the viewer frame so the
  // triangle-centroid test below runs in displayed coordinates.
  const cornerA = modelToDisplayVec(bbox[0], bbox[1], bbox[2], transform);
  const cornerB = modelToDisplayVec(bbox[3], bbox[4], bbox[5], transform);
  const min = new THREE.Vector3(Math.min(cornerA.x, cornerB.x), Math.min(cornerA.y, cornerB.y), Math.min(cornerA.z, cornerB.z));
  const max = new THREE.Vector3(Math.max(cornerA.x, cornerB.x), Math.max(cornerA.y, cornerB.y), Math.max(cornerA.z, cornerB.z));
  const size = new THREE.Vector3().subVectors(max, min);
  const diagonal = Math.max(size.length(), 1e-3);
  const pad = Math.max(diagonal * 0.015, 1e-4);
  const paddedMin = min.clone().subScalar(pad);
  const paddedMax = max.clone().addScalar(pad);
  const center = face.center && face.center.length === 3
    ? modelToDisplayVec(face.center[0], face.center[1], face.center[2], transform)
    : new THREE.Vector3().addVectors(min, max).multiplyScalar(0.5);
  const faceNormal = face.normal && face.normal.length === 3
    ? modelToDisplayVec(face.normal[0], face.normal[1], face.normal[2], transform).normalize()
    : null;
  const planarSurface = (face.surface_type ?? "").toLowerCase().includes("plane");
  const planeTolerance = Math.max(diagonal * 0.04, 0.15);
  const positions: number[] = [];
  const v0 = new THREE.Vector3();
  const v1 = new THREE.Vector3();
  const v2 = new THREE.Vector3();
  const centroid = new THREE.Vector3();
  const triangleNormal = new THREE.Vector3();
  const edge = new THREE.Vector3();

  object.updateMatrixWorld(true);
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const geo = node.geometry as THREE.BufferGeometry;
    const pos = geo.attributes.position;
    if (!pos) return;
    const index = geo.index;
    const triCount = index ? Math.floor(index.count / 3) : Math.floor(pos.count / 3);
    for (let tri = 0; tri < triCount; tri++) {
      const i0 = index ? index.getX(tri * 3) : tri * 3;
      const i1 = index ? index.getX(tri * 3 + 1) : tri * 3 + 1;
      const i2 = index ? index.getX(tri * 3 + 2) : tri * 3 + 2;
      v0.set(pos.getX(i0), pos.getY(i0), pos.getZ(i0)).applyMatrix4(node.matrixWorld);
      v1.set(pos.getX(i1), pos.getY(i1), pos.getZ(i1)).applyMatrix4(node.matrixWorld);
      v2.set(pos.getX(i2), pos.getY(i2), pos.getZ(i2)).applyMatrix4(node.matrixWorld);
      centroid.copy(v0).add(v1).add(v2).multiplyScalar(1 / 3);
      if (
        centroid.x < paddedMin.x || centroid.x > paddedMax.x ||
        centroid.y < paddedMin.y || centroid.y > paddedMax.y ||
        centroid.z < paddedMin.z || centroid.z > paddedMax.z
      ) {
        continue;
      }
      if (planarSurface && faceNormal) {
        triangleNormal.subVectors(v1, v0).cross(edge.subVectors(v2, v0)).normalize();
        const normalAligned = Math.abs(triangleNormal.dot(faceNormal)) > 0.72;
        const closeToPlane = Math.abs(centroid.clone().sub(center).dot(faceNormal)) <= planeTolerance;
        if (!normalAligned || !closeToPlane) continue;
      }
      const offset = faceNormal ? faceNormal.clone().multiplyScalar(Math.max(diagonal * 0.0025, 0.02)) : new THREE.Vector3();
      positions.push(
        v0.x + offset.x, v0.y + offset.y, v0.z + offset.z,
        v1.x + offset.x, v1.y + offset.y, v1.z + offset.z,
        v2.x + offset.x, v2.y + offset.y, v2.z + offset.z,
      );
    }
  });

  if (positions.length < 9) return null;
  const highlightGeometry = new THREE.BufferGeometry();
  highlightGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  highlightGeometry.computeVertexNormals();
  const mesh = new THREE.Mesh(highlightGeometry, makeHighlightMaterial());
  mesh.renderOrder = 1000;
  return mesh;
}

export function ModelViewer({
  assetUrl,
  assetFormat,
  fieldDescriptor,
  projectId,
  pickedFaces,
  onAddPickedFace,
  onClearPickedFaces,
  onInsertToChat,
  onRunPreprocess,
  cadGenerationProgress,
  highlightedFaceIds,
  brepSnapshot,
  onClearHighlightedFaces,
}: {
  assetUrl?: string | null;
  assetFormat?: string | null;
  fieldDescriptor?: SolverFieldDescriptor | null;
  projectId?: string | null;
  pickedFaces: PickedFace[];
  onAddPickedFace(face: PickedFace): void;
  onClearPickedFaces(): void;
  onInsertToChat(text: string): void;
  onRunPreprocess(prompt: string): Promise<void>;
  cadGenerationProgress: CadGenerationProgress | null;
  highlightedFaceIds: Set<string>;
  brepSnapshot: BrepGraphSnapshot | null;
  onClearHighlightedFaces(): void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  // Scene refs shared between the asset-loading effect and the highlight effect.
  const sceneRef = useRef<THREE.Scene | null>(null);
  const highlightGroupRef = useRef<THREE.Group | null>(null);
  const objectRef = useRef<THREE.Object3D | null>(null);
  const [objectReadyKey, setObjectReadyKey] = useState(0);
  const [viewerState, setViewerState] = useState<{ status: ViewerLoadState; detail: string }>({
    status: "idle",
    detail: "Waiting for preview asset",
  });
  const [tooltipFace, setTooltipFace] = useState<PickedFace | null>(null);
  const [preprocessBusy, setPreprocessBusy] = useState(false);
  // Viewer↔model coordinate transform (see DisplayTransform). Held in a ref so
  // the click handler always reads the current value without re-binding.
  const displayTransformRef = useRef<DisplayTransform>(IDENTITY_TRANSFORM);
  // Identity maps from displayed primitive ↔ B-Rep face (built once per load),
  // so pick + highlight resolve exact faces instead of geometry-guessing.
  const primitiveFaceRef = useRef<Map<THREE.Object3D, PickedFace>>(new Map());
  const faceMeshesRef = useRef<Map<string, THREE.Mesh[]>>(new Map());
  const resolvedAssetFormat = resolveAssetFormat(assetUrl, assetFormat);
  const fieldDescriptorKey = fieldDescriptor
    ? [
        fieldDescriptor.project_id,
        fieldDescriptor.field_name,
        fieldDescriptor.format,
        fieldDescriptor.basis ?? "",
        fieldDescriptor.colormap ?? "",
        fieldDescriptor.min_value,
        fieldDescriptor.max_value,
        fieldDescriptor.unit ?? "",
        fieldDescriptor.source ?? "",
        fieldDescriptor.values?.length ?? 0,
        fieldDescriptor.node_coords?.length ?? 0,
      ].join("|")
    : "";

  useEffect(() => {
    if (!hostRef.current) return;

    const host = hostRef.current;
    const getHostSize = () => ({
      width: Math.max(host.clientWidth, 1),
      height: Math.max(host.clientHeight, 1),
    });
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#111111");
    sceneRef.current = scene;
    const highlightGroup = new THREE.Group();
    highlightGroup.name = "pointer-highlights";
    scene.add(highlightGroup);
    highlightGroupRef.current = highlightGroup;

    const initialSize = getHostSize();
    const camera = new THREE.PerspectiveCamera(45, initialSize.width / initialSize.height, 0.1, 1000);
    camera.position.set(3, 3, 5);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setSize(initialSize.width, initialSize.height, false);
    host.innerHTML = "";
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0.5, 0.5, 0.5);

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
    fillLight.position.set(-6, 4, -5);
    scene.add(fillLight);
    scene.add(new THREE.GridHelper(10, 10, 0x333333, 0x222222));

    let object3d: THREE.Object3D | null = null;
    let isDisposed = false;
    const setSafeViewerState = (status: ViewerLoadState, detail: string) => {
      if (!isDisposed) {
        setViewerState({ status, detail });
      }
    };

    const resolvedFormat = resolveAssetFormat(assetUrl, assetFormat);
    const attachObject = (nextObject: THREE.Object3D) => {
      if (object3d) scene.remove(object3d);
      object3d = nextObject;
      objectRef.current = nextObject;
      if (fieldDescriptor?.basis === "y_normalized") {
        applyYNormalizedColors(nextObject, fieldDescriptor.colormap);
      } else if (
        fieldDescriptor?.format === "vertex_json" &&
        fieldDescriptor.values &&
        fieldDescriptor.node_coords
      ) {
        const { applied, bboxStatus, warnings } = applyFieldColors(
          nextObject,
          fieldDescriptor.values,
          fieldDescriptor.node_coords,
          fieldDescriptor.min_value,
          fieldDescriptor.max_value,
          fieldDescriptor.colormap,
        );
        if (applied && fieldDescriptor) {
          fieldDescriptor.bbox_status = bboxStatus;
          if (warnings.length && fieldDescriptor.warnings) {
            fieldDescriptor.warnings.push(...warnings);
          } else if (warnings.length) {
            fieldDescriptor.warnings = warnings;
          }
        }
      }
      scene.add(nextObject);
      if (!fitCameraToObject(camera, controls, nextObject)) {
        setSafeViewerState("error", "Preview asset missing valid geometry bounds, cannot position camera");
        return;
      }
      const fieldNote = (() => {
        if (!fieldDescriptor) return "";
        const label = fieldLabel(fieldDescriptor.field_name);
        if (fieldDescriptor.source === "frd") {
          if (fieldDescriptor.bbox_status === "suspicious") {
            return ` · ${label} overlay (FRD data present, but geometry coordinates may mismatch)`;
          }
          return ` · ${label} overlay (FRD real data)`;
        }
        return ` · ${label} overlay (synthetic preview, not for engineering decisions)`;
      })();
      if (fieldDescriptor?.bbox_status === "suspicious") {
        setSafeViewerState("ready", `Real preview asset loaded${fieldNote} — Warning: FRD coordinates mismatch geometry`);
      } else {
        setSafeViewerState("ready", `Real preview asset loaded${fieldNote}`);
      }
      setObjectReadyKey((current) => current + 1);
    };

    if (assetUrl && resolvedFormat) {
      const absoluteUrl = assetUrl.startsWith("http") ? assetUrl : `${api.base}${assetUrl}`;
      setSafeViewerState("loading", `Loading ${resolvedFormat.toUpperCase()} preview asset`);

      if (resolvedFormat === "glb") {
        new GLTFLoader().load(
          absoluteUrl,
          (gltf: { scene: THREE.Object3D }) => {
            attachObject(gltf.scene);
          },
          undefined,
          (error: unknown) => {
            const detail = error instanceof Error ? error.message : "GLB preview asset failed to load";
            setSafeViewerState("error", detail);
          },
        );
      } else if (resolvedFormat === "stl") {
        new STLLoader().load(
          absoluteUrl,
          (geometry: THREE.BufferGeometry) => {
            geometry.computeVertexNormals();
            const mesh = new THREE.Mesh(
              geometry,
              new THREE.MeshStandardMaterial({ color: 0xaaaaaa, metalness: 0.15, roughness: 0.6 }),
            );
            attachObject(mesh);
          },
          undefined,
          (error: unknown) => {
            const detail = error instanceof Error ? error.message : "STL preview asset failed to load";
            setSafeViewerState("error", detail);
          },
        );
      }
    } else if (assetUrl && !resolvedFormat) {
      setSafeViewerState("error", "Preview asset format not recognized");
    } else {
      setSafeViewerState("idle", "Waiting for preview asset");
    }

    const onResize = () => {
      const size = getHostSize();
      camera.aspect = size.width / size.height;
      camera.updateProjectionMatrix();
      renderer.setSize(size.width, size.height, false);
    };

    // Click-to-pointer: raycast against the loaded object and call backend
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const onClick = (event: MouseEvent) => {
      if (!host || !object3d || !projectId) return;
      const rect = host.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const pickTargets = object3d instanceof THREE.Mesh ? [object3d] : object3d.children;
      const intersects = raycaster.intersectObjects(pickTargets, true);
      if (intersects.length === 0) {
        setTooltipFace(null);
        return;
      }
      const hit = intersects[0];
      // Fast path: the hit primitive is already mapped to its B-Rep face, so
      // resolve the selection locally — exact face, no backend round-trip.
      const mappedFace = primitiveFaceRef.current.get(hit.object);
      if (mappedFace) {
        onAddPickedFace(mappedFace);
        setTooltipFace(mappedFace);
        return;
      }
      // Fallback (older packages, or B-Rep snapshot not loaded yet): convert
      // the hit point to the model frame and let the backend resolve the face.
      const pt = displayToModelPoint(hit.point, displayTransformRef.current);
      api.pickFace(projectId, pt.x, pt.y, pt.z)
        .then((data) => {
          if (data && data.pointer) {
            const face: PickedFace = {
              pointer: data.pointer as string,
              label: (data.label as string) || (data.pointer as string),
              surface_type: (data.surface_type as string) || "unknown",
              roles: Array.isArray(data.roles) ? (data.roles as string[]) : [],
            };
            onAddPickedFace(face);
            setTooltipFace(face);
          }
        })
        .catch(() => setTooltipFace(null));
    };
    host.addEventListener("click", onClick);

    let frame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };

    const resizeObserver = new ResizeObserver(() => onResize());
    resizeObserver.observe(host);
    window.addEventListener("resize", onResize);
    animate();

    return () => {
      isDisposed = true;
      resizeObserver.disconnect();
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(frame);
      host.removeEventListener("click", onClick);
      controls.dispose();
      renderer.dispose();
      host.innerHTML = "";
      sceneRef.current = null;
      highlightGroupRef.current = null;
      objectRef.current = null;
    };
  }, [assetFormat, assetUrl, fieldDescriptorKey]);

  // Keep the viewer↔model transform current whenever the object or B-Rep
  // snapshot changes. Declared before the highlight effect so the ref is set
  // before highlights (and any click) are processed.
  useEffect(() => {
    const object = objectRef.current;
    const isGlb = (resolvedAssetFormat ?? "").toLowerCase() === "glb";
    if (!object || !isGlb) {
      displayTransformRef.current = IDENTITY_TRANSFORM;
      primitiveFaceRef.current = new Map();
      faceMeshesRef.current = new Map();
      return;
    }
    const transform: DisplayTransform = { scale: deriveGlbScale(object, brepSnapshot), isGlb: true };
    displayTransformRef.current = transform;
    const maps = brepSnapshot ? buildFaceIdentityMaps(object, brepSnapshot, transform) : null;
    primitiveFaceRef.current = maps?.primitiveToFace ?? new Map();
    faceMeshesRef.current = maps?.faceToPrimitives ?? new Map();
  }, [objectReadyKey, brepSnapshot, resolvedAssetFormat]);

  // Highlight effect: extracts displayed mesh triangles whose centroids match
  // the selected B-Rep face metadata, then paints a translucent face overlay.
  useEffect(() => {
    const group = highlightGroupRef.current;
    if (!group) return;
    // Clear previous overlays.
    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      disposeHighlightObject(child);
    }
    if (highlightedFaceIds.size === 0) return;

    // Preferred: overlay the exact tessellated primitive for each selected face
    // (works for planar and curved faces alike).
    const faceMeshes = faceMeshesRef.current;
    if (faceMeshes.size > 0) {
      for (const faceId of highlightedFaceIds) {
        for (const prim of faceMeshes.get(faceId) ?? []) {
          group.add(createPrimitiveOverlay(prim));
        }
      }
      return;
    }

    // Fallback: reconstruct the overlay by matching mesh triangles to the
    // face bbox/normal (older packages without an identity map).
    if (!brepSnapshot) return;
    const object = objectRef.current;
    if (!object) return;
    const transform = displayTransformRef.current;
    for (const faceId of highlightedFaceIds) {
      const face = brepSnapshot.faces[faceId];
      if (!face) continue;
      const highlightMesh = createFaceHighlightMesh(object, face, transform);
      if (highlightMesh) group.add(highlightMesh);
    }
  }, [highlightedFaceIds, brepSnapshot, objectReadyKey]);

  return (
    <div className="viewer-canvas-shell">
      <div className="viewer-canvas" ref={hostRef} />
      {viewerState.status !== "ready" ? (
        <div className={`viewer-overlay state-${viewerState.status}`}>
          <strong>
            {viewerState.status === "error"
              ? "Preview load failed"
              : viewerState.status === "loading"
                ? "Loading model"
                : "Waiting for preview"}
          </strong>
          <span>{viewerState.detail}</span>
        </div>
      ) : null}
      {tooltipFace && (
        <div className="viewer-face-tooltip">
          <div className="viewer-face-tooltip-row">
            <span className="viewer-face-tooltip-badge">{tooltipFace.surface_type}</span>
            <strong>{tooltipFace.pointer}</strong>
          </div>
          <div className="viewer-face-tooltip-label">{tooltipFace.label}</div>
          {tooltipFace.roles.length > 0 && (
            <div className="viewer-face-tooltip-roles">{tooltipFace.roles.join(", ")}</div>
          )}
          <div className="viewer-face-tooltip-actions">
            <button
              type="button"
              className="viewer-face-action-btn"
              disabled={preprocessBusy}
              onClick={() => {
                setPreprocessBusy(true);
                void onRunPreprocess(`Apply a 500 N load on ${tooltipFace.pointer}`).finally(() => setPreprocessBusy(false));
              }}
              title="AI-preprocess: 500 N load"
            >
              {preprocessBusy ? "…" : "Apply load here"}
            </button>
            <button
              type="button"
              className="viewer-face-action-btn"
              disabled={preprocessBusy}
              onClick={() => {
                setPreprocessBusy(true);
                void onRunPreprocess(`Set ${tooltipFace.pointer} as fixed support`).finally(() => setPreprocessBusy(false));
              }}
              title="AI-preprocess: fixed support"
            >
              {preprocessBusy ? "…" : "Set as support"}
            </button>
            <button
              type="button"
              className="viewer-face-action-btn secondary"
              onClick={() => onInsertToChat(tooltipFace.pointer)}
            >
              Use in chat
            </button>
          </div>
          <small>Shift+Click to multi-select</small>
        </div>
      )}
      {pickedFaces.length > 0 && (
        <div className="viewer-face-multisel">
          <div className="viewer-face-multisel-header">
            <strong>{pickedFaces.length} face{pickedFaces.length !== 1 ? "s" : ""} selected</strong>
            <button type="button" className="ghost-button compact-button" onClick={onClearPickedFaces}>
              Clear
            </button>
          </div>
          <div className="viewer-face-multisel-list">
            {pickedFaces.map((f) => (
              <div key={f.pointer} className="viewer-face-multisel-item">
                <span className="viewer-face-multisel-badge">{f.surface_type}</span>
                <code>{f.pointer}</code>
                <button
                  type="button"
                  className="viewer-face-multisel-use"
                  onClick={() => onInsertToChat(f.pointer)}
                  title="Insert into chat"
                >
                  ↵
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {highlightedFaceIds.size > 0 && (
        <div className="viewer-face-highlight-badge">
          <span>
            <strong>{highlightedFaceIds.size}</strong> face{highlightedFaceIds.size !== 1 ? "s" : ""} highlighted
          </span>
          <button type="button" className="ghost-button compact-button" onClick={onClearHighlightedFaces}>
            Clear
          </button>
        </div>
      )}
      {cadGenerationProgress && (
        <div className="viewer-cad-progress-overlay">
          <CadProgressPanel progress={cadGenerationProgress} />
        </div>
      )}
    </div>
  );
}
