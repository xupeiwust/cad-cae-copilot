/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

import { useFacePicker, validatePickFaceResponse } from "./useFacePicker";

const mockPickFace = vi.fn();
let mockIntersects: unknown[] = [];

vi.mock("three", () => {
  const Raycaster = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).setFromCamera = vi.fn();
    (this as Record<string, unknown>).intersectObjects = vi.fn(() => mockIntersects);
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
    pickFace: (...args: unknown[]) => mockPickFace(...args),
  },
}));

vi.mock("../../viewer/coordinateFrames", () => ({
  displayToModelPoint: (p: { x: number; y: number; z: number }) => ({ x: p.x, y: p.y, z: p.z }),
}));

describe("useFacePicker", () => {
  beforeEach(() => {
    mockIntersects = [];
    vi.clearAllMocks();
  });

  it("accepts all required parameters without throwing", () => {
    const host = document.createElement("div");
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

  it("adds mapped face directly when primitiveFaceRef has a hit", async () => {
    const mockFace = { pointer: "@face:1", label: "Face 1", surface_type: "plane", roles: [] };
    const fakeMesh = { uuid: "mesh-1" } as unknown as import("three").Mesh;
    const primitiveFaceRef = { current: new Map([[fakeMesh, mockFace]]) };

    mockIntersects = [{ object: fakeMesh }];

    const host = document.createElement("div");
    host.getBoundingClientRect = vi.fn(() => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => {} }));
    document.body.appendChild(host);
    const hostRef = { current: host };

    const onAddPickedFace = vi.fn();
    const setTooltipFace = vi.fn();

    renderHook(() =>
      useFacePicker(
        hostRef,
        { current: { children: [fakeMesh] } as unknown as import("three").Object3D },
        { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera },
        primitiveFaceRef,
        { current: { scale: 1, isGlb: false } },
        "proj-1",
        onAddPickedFace,
        setTooltipFace,
      ),
    );

    act(() => {
      host.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 50, clientY: 50 }));
    });

    await waitFor(() => {
      expect(onAddPickedFace).toHaveBeenCalledWith(mockFace);
      expect(setTooltipFace).toHaveBeenCalledWith(mockFace);
    });

    document.body.removeChild(host);
  });

  it("calls backend pickFace and validates response on unmapped hit", async () => {
    mockPickFace.mockResolvedValue({
      pointer: "@face:2",
      label: "Face 2",
      surface_type: "cylinder",
      roles: ["load_surface"],
    });

    const fakeMesh = { uuid: "mesh-2" } as unknown as import("three").Mesh;
    mockIntersects = [{ object: fakeMesh, point: { x: 1, y: 2, z: 3 } }];

    const host = document.createElement("div");
    host.getBoundingClientRect = vi.fn(() => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => {} }));
    document.body.appendChild(host);
    const hostRef = { current: host };

    const onAddPickedFace = vi.fn();
    const setTooltipFace = vi.fn();

    renderHook(() =>
      useFacePicker(
        hostRef,
        { current: { children: [fakeMesh] } as unknown as import("three").Object3D },
        { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera },
        { current: new Map() },
        { current: { scale: 1, isGlb: false } },
        "proj-1",
        onAddPickedFace,
        setTooltipFace,
      ),
    );

    act(() => {
      host.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 50, clientY: 50 }));
    });

    await waitFor(() => {
      expect(mockPickFace).toHaveBeenCalledWith("proj-1", 1, 2, 3);
      expect(onAddPickedFace).toHaveBeenCalledWith({
        pointer: "@face:2",
        label: "Face 2",
        surface_type: "cylinder",
        roles: ["load_surface"],
      });
      expect(setTooltipFace).toHaveBeenCalledWith({
        pointer: "@face:2",
        label: "Face 2",
        surface_type: "cylinder",
        roles: ["load_surface"],
      });
    });

    document.body.removeChild(host);
  });

  describe("response validation", () => {
    it("rejects null response", async () => {
      mockPickFace.mockResolvedValue(null);

      const fakeMesh = { uuid: "mesh-3" } as unknown as import("three").Mesh;
      mockIntersects = [{ object: fakeMesh, point: { x: 0, y: 0, z: 0 } }];

      const host = document.createElement("div");
      host.getBoundingClientRect = vi.fn(() => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => {} }));
      document.body.appendChild(host);
      const hostRef = { current: host };
      const onAddPickedFace = vi.fn();
      const setTooltipFace = vi.fn();

      renderHook(() =>
        useFacePicker(
          hostRef,
          { current: { children: [fakeMesh] } as unknown as import("three").Object3D },
          { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera },
          { current: new Map() },
          { current: { scale: 1, isGlb: false } },
          "proj-1",
          onAddPickedFace,
          setTooltipFace,
        ),
      );

      act(() => {
        host.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      await waitFor(() => {
        expect(setTooltipFace).toHaveBeenCalledWith(null);
      });
      expect(onAddPickedFace).not.toHaveBeenCalled();
      document.body.removeChild(host);
    });

    it("rejects missing pointer", async () => {
      mockPickFace.mockResolvedValue({ label: "Face", surface_type: "plane", roles: [] });

      const fakeMesh = { uuid: "mesh-4" } as unknown as import("three").Mesh;
      mockIntersects = [{ object: fakeMesh, point: { x: 0, y: 0, z: 0 } }];

      const host = document.createElement("div");
      host.getBoundingClientRect = vi.fn(() => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => {} }));
      document.body.appendChild(host);
      const hostRef = { current: host };
      const onAddPickedFace = vi.fn();
      const setTooltipFace = vi.fn();

      renderHook(() =>
        useFacePicker(
          hostRef,
          { current: { children: [fakeMesh] } as unknown as import("three").Object3D },
          { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera },
          { current: new Map() },
          { current: { scale: 1, isGlb: false } },
          "proj-1",
          onAddPickedFace,
          setTooltipFace,
        ),
      );

      act(() => {
        host.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      await waitFor(() => {
        expect(setTooltipFace).toHaveBeenCalledWith(null);
      });
      expect(onAddPickedFace).not.toHaveBeenCalled();
      document.body.removeChild(host);
    });

    it("rejects empty string pointer", async () => {
      mockPickFace.mockResolvedValue({ pointer: "", label: "Face", surface_type: "plane", roles: [] });

      const fakeMesh = { uuid: "mesh-5" } as unknown as import("three").Mesh;
      mockIntersects = [{ object: fakeMesh, point: { x: 0, y: 0, z: 0 } }];

      const host = document.createElement("div");
      host.getBoundingClientRect = vi.fn(() => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => {} }));
      document.body.appendChild(host);
      const hostRef = { current: host };
      const onAddPickedFace = vi.fn();
      const setTooltipFace = vi.fn();

      renderHook(() =>
        useFacePicker(
          hostRef,
          { current: { children: [fakeMesh] } as unknown as import("three").Object3D },
          { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera },
          { current: new Map() },
          { current: { scale: 1, isGlb: false } },
          "proj-1",
          onAddPickedFace,
          setTooltipFace,
        ),
      );

      act(() => {
        host.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      await waitFor(() => {
        expect(setTooltipFace).toHaveBeenCalledWith(null);
      });
      expect(onAddPickedFace).not.toHaveBeenCalled();
      document.body.removeChild(host);
    });

    it("rejects non-string pointer", async () => {
      mockPickFace.mockResolvedValue({ pointer: 123, label: "Face", surface_type: "plane", roles: [] });

      const fakeMesh = { uuid: "mesh-6" } as unknown as import("three").Mesh;
      mockIntersects = [{ object: fakeMesh, point: { x: 0, y: 0, z: 0 } }];

      const host = document.createElement("div");
      host.getBoundingClientRect = vi.fn(() => ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => {} }));
      document.body.appendChild(host);
      const hostRef = { current: host };
      const onAddPickedFace = vi.fn();
      const setTooltipFace = vi.fn();

      renderHook(() =>
        useFacePicker(
          hostRef,
          { current: { children: [fakeMesh] } as unknown as import("three").Object3D },
          { current: { position: { set: vi.fn() } } as unknown as import("three").PerspectiveCamera },
          { current: new Map() },
          { current: { scale: 1, isGlb: false } },
          "proj-1",
          onAddPickedFace,
          setTooltipFace,
        ),
      );

      act(() => {
        host.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      await waitFor(() => {
        expect(setTooltipFace).toHaveBeenCalledWith(null);
      });
      expect(onAddPickedFace).not.toHaveBeenCalled();
      document.body.removeChild(host);
    });
  });
});

describe("validatePickFaceResponse", () => {
  it("returns null for null data", () => {
    expect(validatePickFaceResponse(null)).toBeNull();
  });

  it("returns null for undefined data", () => {
    expect(validatePickFaceResponse(undefined)).toBeNull();
  });

  it("returns null for string data", () => {
    expect(validatePickFaceResponse("not an object")).toBeNull();
  });

  it("returns null for missing pointer", () => {
    expect(validatePickFaceResponse({ label: "Face", surface_type: "plane", roles: [] })).toBeNull();
  });

  it("returns null for empty string pointer", () => {
    expect(validatePickFaceResponse({ pointer: "", label: "Face", surface_type: "plane", roles: [] })).toBeNull();
  });

  it("returns null for non-string pointer", () => {
    expect(validatePickFaceResponse({ pointer: 123, label: "Face", surface_type: "plane", roles: [] })).toBeNull();
  });

  it("returns valid PickedFace for minimal valid response", () => {
    expect(validatePickFaceResponse({ pointer: "@face:1" })).toEqual({
      pointer: "@face:1",
      label: "@face:1",
      surface_type: "unknown",
      roles: [],
    });
  });

  it("returns valid PickedFace for full valid response", () => {
    expect(validatePickFaceResponse({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "plane",
      roles: ["load_surface"],
    })).toEqual({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "plane",
      roles: ["load_surface"],
    });
  });

  it("falls back to pointer for non-string label", () => {
    expect(validatePickFaceResponse({
      pointer: "@face:1",
      label: 123,
      surface_type: "plane",
      roles: [],
    })).toEqual({
      pointer: "@face:1",
      label: "@face:1",
      surface_type: "plane",
      roles: [],
    });
  });

  it("falls back to pointer for empty label", () => {
    expect(validatePickFaceResponse({
      pointer: "@face:1",
      label: "",
      surface_type: "plane",
      roles: [],
    })).toEqual({
      pointer: "@face:1",
      label: "@face:1",
      surface_type: "plane",
      roles: [],
    });
  });

  it("defaults surface_type to 'unknown' for non-string", () => {
    expect(validatePickFaceResponse({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: 42,
      roles: [],
    })).toEqual({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "unknown",
      roles: [],
    });
  });

  it("filters non-string roles", () => {
    expect(validatePickFaceResponse({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "plane",
      roles: ["load_surface", 123, null, "constraint_surface"],
    })).toEqual({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "plane",
      roles: ["load_surface", "constraint_surface"],
    });
  });

  it("defaults roles to empty array when not an array", () => {
    expect(validatePickFaceResponse({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "plane",
      roles: "not-an-array",
    })).toEqual({
      pointer: "@face:1",
      label: "Face 1",
      surface_type: "plane",
      roles: [],
    });
  });
});
