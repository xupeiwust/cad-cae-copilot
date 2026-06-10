/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { useAssemblyCheckOverlay } from "./useAssemblyCheckOverlay";

const mockBuildAssemblyCheckGroup = vi.fn(() => ({ name: "assembly-check" }));
const mockDisposeAssemblyCheckGroup = vi.fn();

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

vi.mock("../assemblyCheck", () => ({
  buildAssemblyCheckGroup: (...args: unknown[]) => (mockBuildAssemblyCheckGroup as (...a: unknown[]) => unknown)(...args),
  disposeAssemblyCheckGroup: (...args: unknown[]) => (mockDisposeAssemblyCheckGroup as (...a: unknown[]) => void)(...args),
}));

type FakeGroup = { children: unknown[]; remove(child: unknown): void; add(child: unknown): void };

describe("useAssemblyCheckOverlay", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

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

  it("clears group children and does not build when showAssemblyCheck is false", async () => {
    const fakeGroup: FakeGroup = {
      children: [{ name: "old-child" }],
      remove(child: unknown) {
        const idx = this.children.indexOf(child);
        if (idx >= 0) this.children.splice(idx, 1);
      },
      add(child: unknown) {
        this.children.push(child);
      },
    };

    const assemblyGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const report = { floating_parts: [], broken_symmetry: [] } as unknown as import("../../../types").GeometryReportResponse;

    renderHook(() =>
      useAssemblyCheckOverlay(assemblyGroupRef, false, report, displayTransformRef, 0),
    );

    await waitFor(() => {
      expect(fakeGroup.children.length).toBe(0);
    });
    expect(mockBuildAssemblyCheckGroup).not.toHaveBeenCalled();
  });

  it("builds assembly check group and adds it when showAssemblyCheck is true", async () => {
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

    const mockCheckGroup = { name: "assembly-check" };
    mockBuildAssemblyCheckGroup.mockReturnValue(mockCheckGroup);

    const assemblyGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const report = { floating_parts: [], broken_symmetry: [] } as unknown as import("../../../types").GeometryReportResponse;

    renderHook(() =>
      useAssemblyCheckOverlay(assemblyGroupRef, true, report, displayTransformRef, 0),
    );

    await waitFor(() => {
      expect(fakeGroup.children).toContain(mockCheckGroup);
    });
    expect(mockBuildAssemblyCheckGroup).toHaveBeenCalledWith(report, { scale: 1, isGlb: false });
  });

  it("clears children when toggling from true to false", async () => {
    const mockCheckGroup = { name: "assembly-check" };
    mockBuildAssemblyCheckGroup.mockReturnValue(mockCheckGroup);

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

    const assemblyGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const report = { floating_parts: [], broken_symmetry: [] } as unknown as import("../../../types").GeometryReportResponse;

    const { rerender } = renderHook(
      ({ show }: { show: boolean }) =>
        useAssemblyCheckOverlay(assemblyGroupRef, show, report, displayTransformRef, 0),
      { initialProps: { show: true } },
    );

    await waitFor(() => {
      expect(fakeGroup.children).toContain(mockCheckGroup);
    });

    rerender({ show: false });

    await waitFor(() => {
      expect(fakeGroup.children.length).toBe(0);
    });
  });

  it("rebuilds overlay when objectReadyKey changes", async () => {
    const mockCheckGroup1 = { name: "check-1" };
    const mockCheckGroup2 = { name: "check-2" };
    mockBuildAssemblyCheckGroup
      .mockReturnValueOnce(mockCheckGroup1)
      .mockReturnValueOnce(mockCheckGroup2);

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

    const assemblyGroupRef = { current: fakeGroup as unknown as import("three").Group };
    const displayTransformRef = { current: { scale: 1, isGlb: false } };
    const report = { floating_parts: [], broken_symmetry: [] } as unknown as import("../../../types").GeometryReportResponse;

    const { rerender } = renderHook(
      ({ key }: { key: number }) =>
        useAssemblyCheckOverlay(assemblyGroupRef, true, report, displayTransformRef, key),
      { initialProps: { key: 0 } },
    );

    await waitFor(() => {
      expect(fakeGroup.children).toContain(mockCheckGroup1);
    });

    rerender({ key: 1 });

    await waitFor(() => {
      expect(fakeGroup.children).toContain(mockCheckGroup2);
      expect(fakeGroup.children).not.toContain(mockCheckGroup1);
    });
  });
});
