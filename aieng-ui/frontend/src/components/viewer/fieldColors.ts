import * as THREE from "three";

// Field/solver color mapping: sample a colormap, paint a Y-normalized preview,
// or map per-node solver values onto displayed mesh vertices via a spatial grid.
// All pure THREE.js — no React, unit-testable in isolation.

export const FIELD_COLORMAPS = ["thermal", "coolwarm", "viridis", "grayscale"] as const;
export type FieldColormapName = (typeof FIELD_COLORMAPS)[number];

export type FieldColorOptions = {
  clampMin?: number | null;
  clampMax?: number | null;
  bands?: number | null;
  thresholdMin?: number | null;
  thresholdMax?: number | null;
  maskColor?: THREE.Color | null;
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

// Approximation of matplotlib's viridis, sampled at 11 points and linearly
// interpolated. Expressed in sRGB so it matches the CSS gradient closely.
const VIRIDIS_STOPS: [number, number, number][] = [
  [0.26700401, 0.00487433, 0.32941519],
  [0.28358203, 0.14067818, 0.45875764],
  [0.25393521, 0.26525418, 0.52998327],
  [0.20684336, 0.37157568, 0.55399623],
  [0.16362543, 0.47113298, 0.55814834],
  [0.12756771, 0.56694976, 0.55055605],
  [0.13469223, 0.65863613, 0.51764919],
  [0.26694091, 0.74889532, 0.44059495],
  [0.47765785, 0.82108007, 0.3183956],
  [0.74138862, 0.8733418, 0.15350678],
  [0.99324805, 0.90615665, 0.14393626],
];

function sampleViridis(t: number): THREE.Color {
  const scaled = t * (VIRIDIS_STOPS.length - 1);
  const i = Math.max(0, Math.min(VIRIDIS_STOPS.length - 2, Math.floor(scaled)));
  const f = scaled - i;
  const [r1, g1, b1] = VIRIDIS_STOPS[i];
  const [r2, g2, b2] = VIRIDIS_STOPS[i + 1];
  return new THREE.Color(lerp(r1, r2, f), lerp(g1, g2, f), lerp(b1, b2, f));
}

// CSS color stops across a colormap, for a legend gradient bar (low→high).
export function colormapCssStops(name?: string | null, count = 8): string[] {
  const stops: string[] = [];
  const n = Math.max(2, count);
  for (let i = 0; i < n; i += 1) {
    const c = sampleColormap(i / (n - 1), name);
    stops.push(`rgb(${Math.round(c.r * 255)}, ${Math.round(c.g * 255)}, ${Math.round(c.b * 255)})`);
  }
  return stops;
}

/**
 * Build a CSS `linear-gradient(...)` string for a colormap.
 * When `bands` is >= 2 the gradient is stepped into N solid bands so the legend
 * matches the discrete contour colouring applied to the mesh.
 */
export function colormapCssGradient(name?: string | null, bands?: number | null): string {
  const stops = colormapCssStops(name, 64);
  if (!bands || bands < 2) {
    return `linear-gradient(to top, ${stops.map((color, i) => `${color} ${(i / (stops.length - 1)) * 100}%`).join(", ")})`;
  }
  const bandStops: string[] = [];
  const n = Math.max(2, Math.round(bands));
  for (let i = 0; i < n; i += 1) {
    const t = i / (n - 1);
    const color = stops[Math.round(t * (stops.length - 1))];
    const start = (i / n) * 100;
    const end = ((i + 1) / n) * 100;
    bandStops.push(`${color} ${start.toFixed(2)}%, ${color} ${end.toFixed(2)}%`);
  }
  return `linear-gradient(to top, ${bandStops.join(", ")})`;
}

export function sampleColormap(t: number, name?: string | null): THREE.Color {
  const c = Math.max(0, Math.min(1, t));
  if (name === "coolwarm") {
    // blue(0) -> white(0.5) -> red(1)
    const r = c < 0.5 ? 0.2 + c * 1.6 : 1.0;
    const g = c < 0.5 ? 0.2 + c * 1.6 : 1.0 - (c - 0.5) * 2.0;
    const b = c < 0.5 ? 1.0 : 1.0 - (c - 0.5) * 1.6;
    return new THREE.Color(r, g, b);
  }
  if (name === "viridis") {
    return sampleViridis(c);
  }
  if (name === "grayscale") {
    return new THREE.Color(c, c, c);
  }
  // thermal: blue -> cyan -> green -> yellow -> red
  const r = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 3)));
  const g = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 2)));
  const b = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 1)));
  return new THREE.Color(r, g, b);
}

export function effectiveFieldRange(
  minVal: number,
  maxVal: number,
  options?: FieldColorOptions | null,
): { min: number; max: number } {
  let min = minVal;
  let max = maxVal;
  if (options?.clampMin !== undefined && options.clampMin !== null && Number.isFinite(options.clampMin)) {
    min = options.clampMin;
  }
  if (options?.clampMax !== undefined && options.clampMax !== null && Number.isFinite(options.clampMax)) {
    max = options.clampMax;
  }
  if (min > max) {
    // Invalid clamp range: fall back to the original ordering to avoid an
    // inverted scale, but keep the requested boundary that makes sense.
    min = minVal;
    max = maxVal;
  }
  return { min, max };
}

function isMaskedValue(value: number, options?: FieldColorOptions | null): boolean {
  if (!options) return false;
  if (options.thresholdMin !== undefined && options.thresholdMin !== null && value < options.thresholdMin) {
    return true;
  }
  if (options.thresholdMax !== undefined && options.thresholdMax !== null && value > options.thresholdMax) {
    return true;
  }
  return false;
}

export function normalizeFieldValue(
  value: number,
  minVal: number,
  maxVal: number,
  options?: FieldColorOptions | null,
): number | null {
  if (isMaskedValue(value, options)) return null;
  const range = effectiveFieldRange(minVal, maxVal, options);
  let t = range.max > range.min ? (value - range.min) / (range.max - range.min) : 0;
  t = Math.max(0, Math.min(1, t));
  const bands = options?.bands ?? 0;
  if (bands && bands >= 2) {
    const n = Math.round(bands);
    const band = Math.min(n - 1, Math.floor(t * n));
    t = band / (n - 1);
  }
  return t;
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
  options?: FieldColorOptions | null,
): { applied: boolean; bboxStatus: "aligned" | "suspicious" | null; warnings: string[] } {
  let applied = false;
  const warnings: string[] = [];
  const range = effectiveFieldRange(minVal, maxVal, options);
  const valueRange = range.max > range.min ? range.max - range.min : 1;
  const maskColor = options?.maskColor ?? new THREE.Color(0x888888);

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
      const t = normalizeFieldValue(val, minVal, maxVal, options);
      const col = t === null ? maskColor : sampleColormap(t, colormap);
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
