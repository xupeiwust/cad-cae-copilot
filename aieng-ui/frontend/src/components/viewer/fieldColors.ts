import * as THREE from "three";

// Field/solver color mapping: sample a colormap, paint a Y-normalized preview,
// or map per-node solver values onto displayed mesh vertices via a spatial grid.
// All pure THREE.js — no React, unit-testable in isolation.

export function sampleColormap(t: number, name?: string | null): THREE.Color {
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

export function applyYNormalizedColors(object: THREE.Object3D, colormap?: string | null): boolean {
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

export function buildUniformGrid(nodeCoords: [number, number, number][]): UniformGrid {
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

export function nearestNodeIndex(
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

export function checkBboxAlignment(
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

export function applyFieldColors(
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
