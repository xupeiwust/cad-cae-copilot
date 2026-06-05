import { describe, expect, it } from "vitest";

import { buildUniformGrid, nearestNodeIndex, sampleColormap } from "./fieldColors";

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
