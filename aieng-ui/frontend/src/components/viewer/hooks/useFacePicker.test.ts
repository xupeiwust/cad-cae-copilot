import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

import { useFacePicker } from "./useFacePicker";

// Minimal document stub for Node environment.
const mockDocument = {
  createElement: (tag: string) => {
    const el = { tagName: tag, style: {} as Record<string, string>, childNodes: [] as unknown[] };
    return el as unknown as HTMLElement;
  },
};
// @ts-expect-error — polyfill document in node tests
globalThis.document = mockDocument;

vi.mock("three", () => {
  const Raycaster = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).setFromCamera = vi.fn();
    (this as Record<string, unknown>).intersectObjects = vi.fn(() => []);
  });
  const Vector2 = vi.fn(function (this: unknown, x = 0, y = 0) {
    (this as Record<string, number>).x = x;
    (this as Record<string, number>).y = y;
  });
  const Mesh = vi.fn();
  return {
    __esModule: true,
    default: { Raycaster, Vector2, Mesh },
    Raycaster,
    Vector2,
    Mesh,
  };
});

vi.mock("../../../api", () => ({
  api: {
    pickFace: vi.fn(() => Promise.resolve({ pointer: "@face:1", label: "Face 1", surface_type: "plane", roles: [] })),
  },
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

describe("useFacePicker", () => {
  it("accepts all required parameters without throwing", () => {
    const host = mockDocument.createElement("div") as HTMLDivElement;
    const hostRef = { current: host };
    const objectRef = { current: null as import("three").Object3D | null };
    const cameraRef = { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera };
    const primitiveFaceRef = { current: new Map() };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const onAddPickedFace = vi.fn();
    const setTooltipFace = vi.fn();

    expect(() =>
      renderHook(() =>
        useFacePicker(
          hostRef,
          objectRef,
          cameraRef,
          primitiveFaceRef,
          displayTransformRef,
          "proj-1",
          onAddPickedFace,
          setTooltipFace,
        ),
      ),
    ).not.toThrow();
  });

  it("does nothing when hostRef is null", () => {
    const hostRef = { current: null as HTMLDivElement | null };
    const objectRef = { current: null as import("three").Object3D | null };
    const cameraRef = { current: null as import("three").PerspectiveCamera | null };
    const primitiveFaceRef = { current: new Map() };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };

    expect(() =>
      renderHook(() =>
        useFacePicker(
          hostRef,
          objectRef,
          cameraRef,
          primitiveFaceRef,
          displayTransformRef,
          null,
          () => {},
          () => {},
        ),
      ),
    ).not.toThrow();
  });
});
