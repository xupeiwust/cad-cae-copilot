import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

import { useFaceIdentityMaps } from "./useFaceIdentityMaps";

vi.mock("three", () => {
  const Object3D = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).updateMatrixWorld = vi.fn();
    (this as Record<string, unknown>).traverse = vi.fn();
  });
  const Mesh = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).updateMatrixWorld = vi.fn();
    (this as Record<string, unknown>).traverse = vi.fn();
    (this as Record<string, unknown>).parent = null;
  });
  const Box3 = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).setFromObject = vi.fn(() => ({
      isEmpty: () => false,
      getCenter: () => ({ x: 0, y: 0, z: 0 }),
      getSize: () => ({ x: 1, y: 1, z: 1 }),
      max: { x: 1, y: 1, z: 1 },
      min: { x: 0, y: 0, z: 0 },
    }));
    (this as Record<string, unknown>).isEmpty = () => false;
    (this as Record<string, unknown>).max = { x: 1, y: 1, z: 1 };
    (this as Record<string, unknown>).min = { x: 0, y: 0, z: 0 };
  });
  const Vector3 = vi.fn(function (this: unknown, x = 0, y = 0, z = 0) {
    (this as Record<string, number>).x = x;
    (this as Record<string, number>).y = y;
    (this as Record<string, number>).z = z;
    (this as Record<string, unknown>).clone = vi.fn(() => new Vector3(x, y, z));
    (this as Record<string, unknown>).add = vi.fn(() => this);
    (this as Record<string, unknown>).multiplyScalar = vi.fn(() => this);
    (this as Record<string, unknown>).distanceToSquared = vi.fn(() => 1);
  });
  return {
    __esModule: true,
    default: { Object3D, Mesh, Box3, Vector3 },
    Object3D,
    Mesh,
    Box3,
    Vector3,
  };
});

vi.mock("../coordinateFrames", () => ({
  IDENTITY_TRANSFORM: { scale: 1, isGlb: false },
  deriveGlbScale: vi.fn(() => 0.001),
}));

vi.mock("../faceIdentity", () => ({
  buildFaceIdentityMaps: vi.fn(() => ({
    primitiveToFace: new Map(),
    faceToPrimitives: new Map(),
  })),
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

describe("useFaceIdentityMaps", () => {
  it("returns the three expected refs", () => {
    const objectRef = { current: null as import("three").Object3D | null };

    const { result } = renderHook(() =>
      useFaceIdentityMaps(objectRef, null, null, 0),
    );

    expect(result.current.displayTransformRef).toBeDefined();
    expect(result.current.primitiveFaceRef).toBeDefined();
    expect(result.current.faceMeshesRef).toBeDefined();
  });

  it("initialises displayTransformRef to the identity transform", () => {
    const objectRef = { current: null as import("three").Object3D | null };

    const { result } = renderHook(() =>
      useFaceIdentityMaps(objectRef, null, null, 0),
    );

    // Before the effect runs (server render) the ref holds the initial value.
    expect(result.current.displayTransformRef.current).toEqual({ scale: 1, isGlb: false });
  });

  it("initialises primitiveFaceRef and faceMeshesRef to empty Maps", () => {
    const objectRef = { current: null as import("three").Object3D | null };

    const { result } = renderHook(() =>
      useFaceIdentityMaps(objectRef, null, null, 0),
    );

    expect(result.current.primitiveFaceRef.current.size).toBe(0);
    expect(result.current.faceMeshesRef.current.size).toBe(0);
  });
});
