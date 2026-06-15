import { describe, expect, it } from "vitest";
import * as THREE from "three";

import {
  applyFieldColors,
  buildUniformGrid,
  colormapCssGradient,
  effectiveFieldRange,
  nearestNodeIndex,
  normalizeFieldValue,
  sampleColormap,
} from "./fieldColors";

describe("sampleColormap", () => {
  it("clamps t below 0 and above 1", () => {
    expect(sampleColormap(-5)).toEqual(sampleColormap(0));
    expect(sampleColormap(5)).toEqual(sampleColormap(1));
  });

  it("coolwarm endpoints are blue (low) and red (high)", () => {
    const low = sampleColormap(0, "coolwarm");
    const high = sampleColormap(1, "coolwarm");
    expect(low.b).toBeGreaterThan(low.r); // cold end leans blue
    expect(high.r).toBeGreaterThan(high.b); // hot end leans red
  });

  it("grayscale is neutral", () => {
    const c = sampleColormap(0.5, "grayscale");
    expect(c.r).toBeCloseTo(c.g, 5);
    expect(c.g).toBeCloseTo(c.b, 5);
  });

  it("viridis low end is dark and high end is bright yellow", () => {
    const low = sampleColormap(0, "viridis");
    const high = sampleColormap(1, "viridis");
    expect(low.r + low.g + low.b).toBeLessThan(0.8);
    expect(high.r + high.g + high.b).toBeGreaterThan(1.8);
  });
});

describe("effectiveFieldRange", () => {
  it("uses the descriptor range by default", () => {
    expect(effectiveFieldRange(0, 100, null)).toEqual({ min: 0, max: 100 });
  });

  it("applies one-sided clamp overrides", () => {
    expect(effectiveFieldRange(0, 100, { clampMax: 80 })).toEqual({ min: 0, max: 80 });
    expect(effectiveFieldRange(0, 100, { clampMin: 20 })).toEqual({ min: 20, max: 100 });
  });

  it("falls back to the descriptor range when the clamp is invalid", () => {
    expect(effectiveFieldRange(0, 100, { clampMin: 200, clampMax: 50 })).toEqual({
      min: 0,
      max: 100,
    });
  });
});

describe("normalizeFieldValue", () => {
  it("clamps to [0,1] outside the range", () => {
    expect(normalizeFieldValue(-10, 0, 100, null)).toBe(0);
    expect(normalizeFieldValue(110, 0, 100, null)).toBe(1);
  });

  it("uses the clamped range for normalization", () => {
    expect(normalizeFieldValue(50, 0, 100, { clampMax: 50 })).toBe(1);
    expect(normalizeFieldValue(25, 0, 100, { clampMin: 0, clampMax: 50 })).toBeCloseTo(0.5, 5);
  });

  it("quantizes into discrete bands", () => {
    const opts = { bands: 4 };
    // 4 bands map to t = 0, 1/3, 2/3, 1
    expect(normalizeFieldValue(0, 0, 100, opts)).toBe(0);
    expect(normalizeFieldValue(24, 0, 100, opts)).toBe(0);
    expect(normalizeFieldValue(26, 0, 100, opts)).toBeCloseTo(1 / 3, 5);
    expect(normalizeFieldValue(100, 0, 100, opts)).toBe(1);
  });

  it("returns null for values below the threshold", () => {
    expect(normalizeFieldValue(5, 0, 100, { thresholdMin: 10 })).toBeNull();
    expect(normalizeFieldValue(15, 0, 100, { thresholdMin: 10 })).toBe(0.15);
  });

  it("returns null for values above the threshold", () => {
    expect(normalizeFieldValue(90, 0, 100, { thresholdMax: 80 })).toBeNull();
    expect(normalizeFieldValue(50, 0, 100, { thresholdMax: 80 })).toBe(0.5);
  });
});

describe("colormapCssGradient", () => {
  it("returns a continuous linear-gradient by default", () => {
    const gradient = colormapCssGradient("thermal");
    expect(gradient.startsWith("linear-gradient(to top,")).toBe(true);
    expect(gradient.split("%").length).toBeGreaterThan(10);
  });

  it("returns a stepped gradient when bands are requested", () => {
    const gradient = colormapCssGradient("thermal", 3);
    expect(gradient.startsWith("linear-gradient(to top,")).toBe(true);
    const colorStops = gradient.split(",").filter((s) => s.includes("%"));
    expect(colorStops.length).toBe(6); // 3 bands × 2 stop positions
  });
});

describe("applyFieldColors with legend controls", () => {
  function makeMeshWithVertices(vertices: [number, number, number][]): THREE.Mesh {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(vertices.flat()), 3),
    );
    return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial());
  }

  const nodeCoords: [number, number, number][] = [
    [0, 0, 0],
    [1, 0, 0],
  ];
  const values = [0, 100];

  it("masks values below the threshold with the default mask colour", () => {
    const mesh = makeMeshWithVertices([
      [0, 0, 0],
      [1, 0, 0],
    ]);
    applyFieldColors(mesh, values, nodeCoords, 0, 100, "thermal", { thresholdMin: 50 });
    const colors = (mesh.geometry.attributes.color as THREE.BufferAttribute).array as Float32Array;
    const low = new THREE.Color(colors[0], colors[1], colors[2]);
    const high = new THREE.Color(colors[3], colors[4], colors[5]);
    expect(low.r).toBeCloseTo(0.246, 2); // 0x88 in linear colour space
    expect(high.r).toBeGreaterThan(high.b); // hot end of thermal
  });

  it("uses a clamped range for colouring", () => {
    const mesh = makeMeshWithVertices([
      [0, 0, 0],
      [1, 0, 0],
    ]);
    applyFieldColors(mesh, values, nodeCoords, 0, 100, "grayscale", { clampMax: 50 });
    const colors = (mesh.geometry.attributes.color as THREE.BufferAttribute).array as Float32Array;
    const low = colors[0];
    const high = colors[3];
    expect(high).toBe(1); // value 100 capped to top of scale
    expect(low).toBe(0); // value 0 stays at bottom
  });
});

describe("buildUniformGrid / nearestNodeIndex", () => {
  const coords: [number, number, number][] = [
    [0, 0, 0],
    [10, 0, 0],
    [0, 10, 0],
    [10, 10, 10],
  ];

  it("finds the nearest node to a query point", () => {
    const grid = buildUniformGrid(coords);
    expect(nearestNodeIndex(9.5, 0.2, 0.1, grid, coords)).toBe(1);
    expect(nearestNodeIndex(0.1, 9.7, 0.0, grid, coords)).toBe(2);
    expect(nearestNodeIndex(11, 11, 11, grid, coords)).toBe(3);
  });

  it("handles an empty node set without throwing", () => {
    const grid = buildUniformGrid([]);
    expect(grid.cells.size).toBe(0);
    expect(nearestNodeIndex(0, 0, 0, grid, [])).toBe(-1);
  });
});
