/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { useMeshPreviewOverlay } from "./useMeshPreviewOverlay";

const mockBuildMeshPreviewGroup = vi.fn(() => ({ name: "mesh-preview" }));
const mockDisposeMeshPreviewGroup = vi.fn();

vi.mock("three", () => {
  const Group = vi.fn(function (this: unknown) {
    (this as Record<string, unknown>).children = [] as unknown[];
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

vi.mock("../meshPreview", () => ({
  buildMeshPreviewGroup: (...args: unknown[]) =>
    (mockBuildMeshPreviewGroup as (...a: unknown[]) => unknown)(...args),
  disposeMeshPreviewGroup: (...args: unknown[]) =>
    (mockDisposeMeshPreviewGroup as (...a: unknown[]) => void)(...args),
}));

type FakeGroup = { children: unknown[]; remove(child: unknown): void; add(child: unknown): void };

describe("useMeshPreviewOverlay", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not build when toggle is off", () => {
    const fakeGroup: FakeGroup = {
      children: [],
      remove(child: unknown) {
        const idx = this.children.indexOf(child);
        if (idx >= 0) this.children.splice(idx, 1);
      },
      add(child: unknown) {
        this.children.push(child);
      },
    };
    const meshPreviewGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const preview = { available: true, element_count: 10, nodes: [], edges: [] } as unknown as import("../../../types").MeshPreviewResponse;

    renderHook(() => useMeshPreviewOverlay(meshPreviewGroupRef, false, preview, displayTransformRef, 0));

    expect(mockBuildMeshPreviewGroup).not.toHaveBeenCalled();
  });

  it("builds and adds the mesh preview group when toggle is on", async () => {
    const mockGroup = { name: "mesh-preview" };
    mockBuildMeshPreviewGroup.mockReturnValue(mockGroup);

    const fakeGroup: FakeGroup = {
      children: [],
      remove(child: unknown) {
        const idx = this.children.indexOf(child);
        if (idx >= 0) this.children.splice(idx, 1);
      },
      add(child: unknown) {
        this.children.push(child);
      },
    };
    const meshPreviewGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const preview = { available: true, element_count: 10, nodes: [], edges: [] } as unknown as import("../../../types").MeshPreviewResponse;

    renderHook(() => useMeshPreviewOverlay(meshPreviewGroupRef, true, preview, displayTransformRef, 0));

    await waitFor(() => {
      expect(fakeGroup.children).toContain(mockGroup);
    });
    expect(mockBuildMeshPreviewGroup).toHaveBeenCalledWith(preview, { scale: 1, isGlb: false });
  });

  it("clears children when toggling from true to false", async () => {
    const mockGroup = { name: "mesh-preview" };
    mockBuildMeshPreviewGroup.mockReturnValue(mockGroup);

    const fakeGroup: FakeGroup = {
      children: [],
      remove(child: unknown) {
        const idx = this.children.indexOf(child);
        if (idx >= 0) this.children.splice(idx, 1);
      },
      add(child: unknown) {
        this.children.push(child);
      },
    };
    const meshPreviewGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const preview = { available: true, element_count: 10, nodes: [], edges: [] } as unknown as import("../../../types").MeshPreviewResponse;

    const { rerender } = renderHook(
      ({ show }: { show: boolean }) =>
        useMeshPreviewOverlay(meshPreviewGroupRef, show, preview, displayTransformRef, 0),
      { initialProps: { show: true } },
    );

    await waitFor(() => {
      expect(fakeGroup.children).toContain(mockGroup);
    });

    rerender({ show: false });

    await waitFor(() => {
      expect(fakeGroup.children.length).toBe(0);
    });
  });
});
