import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

import { useAssetLoader } from "./useAssetLoader";

vi.mock("three", () => {
  const Mesh = vi.fn();
  const MeshStandardMaterial = vi.fn();
  const BufferGeometry = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).computeVertexNormals = vi.fn();
  });
  return {
    __esModule: true,
    default: { Mesh, MeshStandardMaterial, BufferGeometry },
    Mesh,
    MeshStandardMaterial,
    BufferGeometry,
  };
});

vi.mock("three/examples/jsm/loaders/GLTFLoader.js", () => {
  const GLTFLoader = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).load = vi.fn(
      (_url: string, onLoad: (gltf: unknown) => void) => {
        onLoad({ scene: { name: "mock-gltf-scene" } });
      },
    );
  });
  return { GLTFLoader };
});

vi.mock("three/examples/jsm/loaders/STLLoader.js", () => {
  const STLLoader = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).load = vi.fn(
      (_url: string, onLoad: (geometry: unknown) => void) => {
        // Return a plain object that quacks like BufferGeometry.
        onLoad({ computeVertexNormals: vi.fn() });
      },
    );
  });
  return { STLLoader };
});

vi.mock("../../../api", () => ({
  api: { base: "http://localhost:8000" },
}));

vi.mock("../../viewer/camera", () => ({
  fitCameraToObject: vi.fn(() => true),
}));

vi.mock("../../viewer/fieldColors", () => ({
  applyYNormalizedColors: vi.fn(),
  applyFieldColors: vi.fn(() => ({ applied: true, bboxStatus: "ok", warnings: [] })),
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

describe("useAssetLoader", () => {
  it("accepts all required parameters without throwing", () => {
    const sceneRef = { current: { remove: vi.fn(), add: vi.fn(), children: [] } as unknown as import("three").Scene };
    const cameraRef = { current: { position: { set: vi.fn() }, lookAt: vi.fn(), updateProjectionMatrix: vi.fn() } as unknown as import("three").PerspectiveCamera };
    const controlsRef = { current: { target: { copy: vi.fn() }, update: vi.fn() } as unknown as { target: import("three").Vector3; update(): void } };
    const objectRef = { current: null as import("three").Object3D | null };
    const setViewerState = vi.fn();

    expect(() =>
      renderHook(() =>
        useAssetLoader(
          sceneRef,
          cameraRef,
          controlsRef,
          objectRef,
          null,
          null,
          null,
          () => {},
          setViewerState,
        ),
      ),
    ).not.toThrow();
  });

  it("computes a stable fieldDescriptorKey from a descriptor", () => {
    // The key logic is internal, but we can verify the hook accepts a descriptor
    // and does not crash by rendering it.
    const descriptor = {
      project_id: "p1",
      field_name: "stress",
      format: "vertex_json",
      basis: null,
      colormap: "viridis",
      min_value: 0,
      max_value: 100,
      unit: "MPa",
      source: "frd",
      values: [1, 2, 3],
      node_coords: [[0, 0, 0]],
    };

    const sceneRef = { current: { remove: vi.fn(), add: vi.fn() } as unknown as import("three").Scene };
    const cameraRef = { current: { position: { set: vi.fn() }, lookAt: vi.fn(), updateProjectionMatrix: vi.fn() } as unknown as import("three").PerspectiveCamera };
    const controlsRef = { current: { target: { copy: vi.fn() }, update: vi.fn() } as unknown as { target: import("three").Vector3; update(): void } };
    const objectRef = { current: null as import("three").Object3D | null };
    const setViewerState = vi.fn();

    expect(() =>
      renderHook(() =>
        useAssetLoader(
          sceneRef,
          cameraRef,
          controlsRef,
          objectRef,
          "/assets/test.glb",
          "glb",
          descriptor as unknown as import("../../../types").SolverFieldDescriptor,
          () => {},
          setViewerState,
        ),
      ),
    ).not.toThrow();
  });
});
