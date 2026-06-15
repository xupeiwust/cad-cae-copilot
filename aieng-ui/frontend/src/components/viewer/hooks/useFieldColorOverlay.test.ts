/**
 * @vitest-environment happy-dom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { createElement } from "react";

import { useFieldColorOverlay } from "./useFieldColorOverlay";

vi.mock("../fieldColors", () => ({
  applyFieldColors: vi.fn(() => ({ applied: true, bboxStatus: "aligned" as const, warnings: [] })),
}));

beforeEach(async () => {
  const { applyFieldColors } = await import("../fieldColors");
  vi.mocked(applyFieldColors).mockClear();
});

afterEach(cleanup);

function renderHook<T>(hook: () => T): { result: { current: T } } {
  let result: T = undefined as unknown as T;
  function TestComponent() {
    result = hook();
    return null;
  }
  render(createElement(TestComponent));
  return { result: { current: result } };
}

describe("useFieldColorOverlay", () => {
  it("re-applies field colours when legend controls change", async () => {
    const { applyFieldColors } = await import("../fieldColors");
    const objectRef = { current: { name: "mesh" } as unknown as import("three").Object3D };
    const descriptor = {
      project_id: "p1",
      field_name: "von_mises",
      format: "vertex_json",
      min_value: 0,
      max_value: 100,
      colormap: "thermal",
      values: [0, 50, 100],
      node_coords: [[0, 0, 0], [1, 0, 0], [2, 0, 0]] as [number, number, number][],
    };

    renderHook(() => useFieldColorOverlay(objectRef, descriptor, { bands: 5 }, 1));

    expect(applyFieldColors).toHaveBeenCalledWith(
      objectRef.current,
      descriptor.values,
      descriptor.node_coords,
      descriptor.min_value,
      descriptor.max_value,
      "thermal",
      { bands: 5 },
    );
  });

  it("does nothing when the descriptor has no real per-node data", async () => {
    const { applyFieldColors } = await import("../fieldColors");
    const objectRef = { current: { name: "mesh" } as unknown as import("three").Object3D };
    const descriptor = {
      project_id: "p1",
      field_name: "von_mises",
      format: "vertex_synthetic",
      min_value: 0,
      max_value: 100,
      values: null,
      node_coords: null,
    };

    renderHook(() => useFieldColorOverlay(objectRef, descriptor, { bands: 5 }, 1));

    expect(applyFieldColors).not.toHaveBeenCalled();
  });
});
