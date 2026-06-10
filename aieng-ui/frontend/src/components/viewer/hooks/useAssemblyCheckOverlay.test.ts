import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

import { useAssemblyCheckOverlay } from "./useAssemblyCheckOverlay";

vi.mock("three", () => {
  const Group = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).children = [];
    (this as Record<string, unknown>).add = vi.fn((child: unknown) => {
      (this as { children: unknown[] }).children.push(child);
    });
    (this as Record<string, unknown>).remove = vi.fn((child: unknown) => {
      const arr = (this as { children: unknown[] }).children;
      const idx = arr.indexOf(child);
      if (idx >= 0) arr.splice(idx, 1);
    });
  });
  return {
    __esModule: true,
    default: { Group },
    Group,
  };
});

vi.mock("../assemblyCheck", () => ({
  buildAssemblyCheckGroup: vi.fn(() => ({ name: "assembly-check" })),
  disposeAssemblyCheckGroup: vi.fn(),
}));

function renderHook<T>(hook: () => T): { result: { current: T } } {
  let result: T = undefined as unknown as T;
  function TestComponent() {
    result = hook();
    return null;
  }
  renderToString(createElement(TestComponent));
  return { result: { current: result } };
}

describe("useAssemblyCheckOverlay", () => {
  it("accepts all parameters without throwing", () => {
    const assemblyGroupRef = { current: null as import("three").Group | null };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };

    expect(() =>
      renderHook(() =>
        useAssemblyCheckOverlay(
          assemblyGroupRef,
          false,
          null,
          displayTransformRef,
          0,
        ),
      ),
    ).not.toThrow();
  });

  it("accepts showAssemblyCheck=true with a report", () => {
    const assemblyGroupRef = { current: null as import("three").Group | null };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const report = { floating_parts: [], broken_symmetry: [] } as unknown as import("../../../types").GeometryReportResponse;

    expect(() =>
      renderHook(() =>
        useAssemblyCheckOverlay(
          assemblyGroupRef,
          true,
          report,
          displayTransformRef,
          0,
        ),
      ),
    ).not.toThrow();
  });
});
