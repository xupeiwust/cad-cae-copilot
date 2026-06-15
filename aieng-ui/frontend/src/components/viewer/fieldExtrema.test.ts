import { describe, expect, it } from "vitest";

import { findFieldExtrema } from "./fieldExtrema";

describe("findFieldExtrema", () => {
  it("locates the peak and min nodes with their coordinates", () => {
    const values = [10, 50, 30, 5];
    const coords: [number, number, number][] = [
      [0, 0, 0],
      [1, 0, 0],
      [2, 0, 0],
      [3, 0, 0],
    ];
    const { max, min } = findFieldExtrema(values, coords);
    expect(max).toEqual({ value: 50, coord: [1, 0, 0], index: 1 });
    expect(min).toEqual({ value: 5, coord: [3, 0, 0], index: 3 });
  });

  it("returns nulls for empty / missing data", () => {
    expect(findFieldExtrema([], [])).toEqual({ max: null, min: null });
    expect(findFieldExtrema(null, null)).toEqual({ max: null, min: null });
    expect(findFieldExtrema([1, 2], undefined)).toEqual({ max: null, min: null });
  });

  it("skips non-finite values and tolerates length mismatch", () => {
    const values = [Number.NaN, 7, 3];
    const coords: [number, number, number][] = [
      [0, 0, 0],
      [1, 1, 1],
    ]; // shorter than values
    const { max, min } = findFieldExtrema(values, coords);
    // only indices 0,1 considered (min length 2); index 0 is NaN → skipped
    expect(max).toEqual({ value: 7, coord: [1, 1, 1], index: 1 });
    expect(min).toEqual({ value: 7, coord: [1, 1, 1], index: 1 });
  });
});
