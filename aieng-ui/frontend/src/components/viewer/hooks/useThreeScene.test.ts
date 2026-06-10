import { describe, expect, it, vi } from "vitest";
import { createElement, useState } from "react";
import { renderToString } from "react-dom/server";

import { useThreeScene } from "./useThreeScene";

// Provide a minimal document stub for the Node test environment.
const mockDocument = {
  createElement: (tag: string) => {
    const el = { tagName: tag, style: {} as Record<string, string>, childNodes: [] as unknown[] };
    return el as unknown as HTMLElement;
  },
};
// @ts-expect-error — polyfill document in node tests
globalThis.document = mockDocument;

// Mock Three.js so the hook can run in a Node test environment.
vi.mock("three", () => {
  const Vector3 = vi.fn(function (this: unknown, x = 0, y = 0, z = 0) {
    (this as Record<string, number>).x = x;
    (this as Record<string, number>).y = y;
    (this as Record<string, number>).z = z;
  });
  const Color = vi.fn(function (this: unknown, c: string) {
    (this as Record<string, unknown>).color = c;
  });
  const Scene = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).children = [];
    (this as Record<string, unknown>).background = null;
    (this as Record<string, unknown>).add = vi.fn((child: unknown) => {
      (this as { children: unknown[] }).children.push(child);
    });
  });
  const PerspectiveCamera = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).position = new Vector3();
    (this as Record<string, unknown>).aspect = 1;
    (this as Record<string, unknown>).updateProjectionMatrix = vi.fn();
  });
  const WebGLRenderer = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).domElement = mockDocument.createElement("canvas");
    (this as Record<string, unknown>).setPixelRatio = vi.fn();
    (this as Record<string, unknown>).setSize = vi.fn();
    (this as Record<string, unknown>).render = vi.fn();
    (this as Record<string, unknown>).dispose = vi.fn();
  });
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
  const AmbientLight = vi.fn();
  const DirectionalLight = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).position = new Vector3();
  });
  const GridHelper = vi.fn();

  return {
    __esModule: true,
    default: {
      Scene,
      PerspectiveCamera,
      WebGLRenderer,
      Group,
      AmbientLight,
      DirectionalLight,
      GridHelper,
      Color,
      Vector3,
      SRGBColorSpace: "srgb",
    },
    Scene,
    PerspectiveCamera,
    WebGLRenderer,
    Group,
    AmbientLight,
    DirectionalLight,
    GridHelper,
    Color,
    Vector3,
    SRGBColorSpace: "srgb",
  };
});

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => {
  const OrbitControls = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).target = { set: vi.fn() };
    (this as Record<string, unknown>).enableDamping = false;
    (this as Record<string, unknown>).update = vi.fn();
    (this as Record<string, unknown>).dispose = vi.fn();
  });
  return { OrbitControls };
});

/**
 * Lightweight server-render helper.  useEffect does **not** run, but we can
 * at least verify the hook returns the expected ref shape.
 */
function renderHook<T>(hook: () => T): { result: { current: T } } {
  let result: T = undefined as unknown as T;
  function TestComponent() {
    result = hook();
    return null;
  }
  renderToString(createElement(TestComponent));
  return { result: { current: result } };
}

describe("useThreeScene", () => {
  it("returns the expected ref objects", () => {
    const host = mockDocument.createElement("div") as HTMLDivElement;
    host.style.width = "800px";
    host.style.height = "600px";
    const hostRef = { current: host };

    const { result } = renderHook(() => useThreeScene(hostRef));

    expect(result.current.sceneRef).toBeDefined();
    expect(result.current.cameraRef).toBeDefined();
    expect(result.current.rendererRef).toBeDefined();
    expect(result.current.controlsRef).toBeDefined();
    expect(result.current.highlightGroupRef).toBeDefined();
    expect(result.current.assemblyGroupRef).toBeDefined();
  });

  it("returns null refs before the effect has run", () => {
    const hostRef = { current: null as HTMLDivElement | null };
    const { result } = renderHook(() => useThreeScene(hostRef));

    // Before mount (or when host is null) the refs are still null.
    expect(result.current.sceneRef.current).toBeNull();
    expect(result.current.cameraRef.current).toBeNull();
  });
});
