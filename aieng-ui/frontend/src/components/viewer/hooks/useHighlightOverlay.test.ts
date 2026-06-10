import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

import { useHighlightOverlay } from "./useHighlightOverlay";

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
  const Mesh = vi.fn();
  return {
    __esModule: true,
    default: { Group, Mesh },
    Group,
    Mesh,
  };
});

vi.mock("../highlights", () => ({
  createPrimitiveOverlay: vi.fn(() => ({ name: "overlay" })),
  createFaceHighlightMesh: vi.fn(() => ({ name: "highlight-mesh" })),
  disposeHighlightObject: vi.fn(),
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

describe("useHighlightOverlay", () => {
  it("accepts all parameters without throwing", () => {
    const highlightGroupRef = { current: null as import("three").Group | null };
    const faceMeshesRef = { current: new Map<string, import("three").Mesh[]>() };
    const objectRef = { current: null as import("three").Object3D | null };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };

    expect(() =>
      renderHook(() =>
        useHighlightOverlay(
          highlightGroupRef,
          faceMeshesRef,
          new Set(),
          null,
          objectRef,
          displayTransformRef,
          0,
        ),
      ),
    ).not.toThrow();
  });

  it("accepts a non-empty highlightedFaceIds set", () => {
    const highlightGroupRef = { current: null as import("three").Group | null };
    const faceMeshesRef = { current: new Map<string, import("three").Mesh[]>() };
    const objectRef = { current: null as import("three").Object3D | null };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };

    expect(() =>
      renderHook(() =>
        useHighlightOverlay(
          highlightGroupRef,
          faceMeshesRef,
          new Set(["face-1", "face-2"]),
          null,
          objectRef,
          displayTransformRef,
          0,
        ),
      ),
    ).not.toThrow();
  });
});
