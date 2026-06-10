/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { useFaceIdentityMaps } from "./useFaceIdentityMaps";

const mockDeriveGlbScale = vi.fn(() => 0.001);
const mockBuildFaceIdentityMaps = vi.fn(() => ({
  primitiveToFace: new Map(),
  faceToPrimitives: new Map(),
}));

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
  deriveGlbScale: (...args: unknown[]) => (mockDeriveGlbScale as (...a: unknown[]) => unknown)(...args),
}));

vi.mock("../faceIdentity", () => ({
  buildFaceIdentityMaps: (...args: unknown[]) => (mockBuildFaceIdentityMaps as (...a: unknown[]) => unknown)(...args),
}));

describe("useFaceIdentityMaps", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns the three expected refs", () => {
    const objectRef = { current: null as import("three").Object3D | null };

    const { result } = renderHook(() => useFaceIdentityMaps(objectRef, null, null, 0));

    expect(result.current.displayTransformRef).toBeDefined();
    expect(result.current.primitiveFaceRef).toBeDefined();
    expect(result.current.faceMeshesRef).toBeDefined();
  });

  it("initialises displayTransformRef to the identity transform", () => {
    const objectRef = { current: null as import("three").Object3D | null };

    const { result } = renderHook(() => useFaceIdentityMaps(objectRef, null, null, 0));

    expect(result.current.displayTransformRef.current).toEqual({ scale: 1, isGlb: false });
  });

  it("initialises primitiveFaceRef and faceMeshesRef to empty Maps", () => {
    const objectRef = { current: null as import("three").Object3D | null };

    const { result } = renderHook(() => useFaceIdentityMaps(objectRef, null, null, 0));

    expect(result.current.primitiveFaceRef.current.size).toBe(0);
    expect(result.current.faceMeshesRef.current.size).toBe(0);
  });

  it("resets refs to identity for non-GLB format", async () => {
    const fakeObject = { name: "obj", updateMatrixWorld: vi.fn(), traverse: vi.fn() } as unknown as import("three").Object3D;
    const objectRef = { current: fakeObject };

    const { result } = renderHook(() => useFaceIdentityMaps(objectRef, null, "stl", 0));

    await waitFor(() => {
      expect(result.current.displayTransformRef.current).toEqual({ scale: 1, isGlb: false });
      expect(result.current.primitiveFaceRef.current.size).toBe(0);
      expect(result.current.faceMeshesRef.current.size).toBe(0);
    });
  });

  it("computes displayTransform for GLB without brepSnapshot", async () => {
    mockDeriveGlbScale.mockReturnValue(0.001);
    const fakeObject = { name: "obj", updateMatrixWorld: vi.fn(), traverse: vi.fn() } as unknown as import("three").Object3D;
    const objectRef = { current: fakeObject };

    const { result } = renderHook(() => useFaceIdentityMaps(objectRef, null, "glb", 0));

    await waitFor(() => {
      expect(result.current.displayTransformRef.current).toEqual({ scale: 0.001, isGlb: true });
      expect(result.current.primitiveFaceRef.current.size).toBe(0);
      expect(result.current.faceMeshesRef.current.size).toBe(0);
    });
    expect(mockDeriveGlbScale).toHaveBeenCalledWith(fakeObject, null);
  });

  it("populates maps from brepSnapshot for GLB", async () => {
    const primKey = { name: "prim1" } as unknown as import("three").Object3D;
    const mockPrimitiveToFace = new Map([
      [primKey, { pointer: "@face:1", label: "Face 1", surface_type: "plane", roles: [] }],
    ]);
    const mockFaceToPrimitives = new Map([["@face:1", ["mesh1"]]]);
    mockDeriveGlbScale.mockReturnValue(0.001);
    mockBuildFaceIdentityMaps.mockReturnValue({
      primitiveToFace: mockPrimitiveToFace,
      faceToPrimitives: mockFaceToPrimitives,
    });

    const fakeObject = { name: "obj", updateMatrixWorld: vi.fn(), traverse: vi.fn() } as unknown as import("three").Object3D;
    const objectRef = { current: fakeObject };
    const brepSnapshot = { faces: {}, groups: {}, featureFaces: {} };

    const { result } = renderHook(() => useFaceIdentityMaps(objectRef, brepSnapshot, "glb", 0));

    await waitFor(() => {
      expect(result.current.primitiveFaceRef.current.get(primKey)).toEqual({
        pointer: "@face:1",
        label: "Face 1",
        surface_type: "plane",
        roles: [],
      });
      expect(result.current.faceMeshesRef.current.get("@face:1")).toEqual(["mesh1"]);
    });
    expect(mockBuildFaceIdentityMaps).toHaveBeenCalledWith(
      fakeObject,
      brepSnapshot,
      { scale: 0.001, isGlb: true },
    );
  });

  it("re-runs effect when objectReadyKey changes", async () => {
    mockDeriveGlbScale.mockReturnValueOnce(0.001).mockReturnValueOnce(0.002);

    const fakeObject = { name: "obj", updateMatrixWorld: vi.fn(), traverse: vi.fn() } as unknown as import("three").Object3D;
    const objectRef = { current: fakeObject };

    const { result, rerender } = renderHook(
      ({ key }: { key: number }) => useFaceIdentityMaps(objectRef, null, "glb", key),
      { initialProps: { key: 0 } },
    );

    await waitFor(() => {
      expect(result.current.displayTransformRef.current.scale).toBe(0.001);
    });

    rerender({ key: 1 });

    await waitFor(() => {
      expect(result.current.displayTransformRef.current.scale).toBe(0.002);
    });
  });
});
