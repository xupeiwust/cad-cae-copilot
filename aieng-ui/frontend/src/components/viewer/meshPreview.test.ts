/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi } from "vitest";
import * as THREE from "three";

import { buildMeshPreviewGroup, disposeMeshPreviewGroup } from "./meshPreview";
import type { MeshPreviewResponse } from "../../types";

vi.mock("three", async () => {
  const actual = await vi.importActual<typeof import("three")>("three");
  return {
    ...actual,
    __esModule: true,
    default: actual,
  };
});

describe("buildMeshPreviewGroup", () => {
  it("returns an empty group when there are no nodes/edges", () => {
    const preview: MeshPreviewResponse = {
      available: true,
      node_count: 0,
      element_count: 0,
      nodes: [],
      edges: [],
    };
    const group = buildMeshPreviewGroup(preview, { scale: 1, isGlb: false });
    expect(group.name).toBe("mesh-preview");
    expect(group.children.length).toBe(0);
  });

  it("builds a LineSegments object for the surface edges", () => {
    const preview: MeshPreviewResponse = {
      available: true,
      node_count: 2,
      element_count: 1,
      nodes: [
        [0, 0, 0],
        [10, 0, 0],
      ],
      edges: [[0, 1]],
    };
    const group = buildMeshPreviewGroup(preview, { scale: 1, isGlb: false });
    expect(group.children.length).toBe(1);
    const lines = group.children[0] as THREE.LineSegments;
    expect(lines).toBeInstanceOf(THREE.LineSegments);
    expect(lines.geometry.attributes.position.count).toBe(2);
  });

  it("transforms nodes to GLB display coordinates", () => {
    const preview: MeshPreviewResponse = {
      available: true,
      node_count: 2,
      element_count: 1,
      nodes: [
        [0, 0, 0],
        [10, 20, 30],
      ],
      edges: [[0, 1]],
    };
    const group = buildMeshPreviewGroup(preview, { scale: 0.001, isGlb: true });
    const lines = group.children[0] as THREE.LineSegments;
    const positions = lines.geometry.attributes.position.array as Float32Array;
    // model (10, 20, 30) mm → display (0.01, 0.03, -0.02)
    expect(positions[3]).toBeCloseTo(0.01);
    expect(positions[4]).toBeCloseTo(0.03);
    expect(positions[5]).toBeCloseTo(-0.02);
  });
});

describe("disposeMeshPreviewGroup", () => {
  it("disposes geometry and material of line segments", () => {
    const preview: MeshPreviewResponse = {
      available: true,
      node_count: 2,
      element_count: 1,
      nodes: [
        [0, 0, 0],
        [10, 0, 0],
      ],
      edges: [[0, 1]],
    };
    const group = buildMeshPreviewGroup(preview, { scale: 1, isGlb: false });
    const lines = group.children[0] as THREE.LineSegments;
    const geometryDispose = vi.spyOn(lines.geometry, "dispose");
    const materialDispose = vi.spyOn(lines.material as THREE.Material, "dispose");

    disposeMeshPreviewGroup(group);

    expect(geometryDispose).toHaveBeenCalled();
    expect(materialDispose).toHaveBeenCalled();
  });
});
