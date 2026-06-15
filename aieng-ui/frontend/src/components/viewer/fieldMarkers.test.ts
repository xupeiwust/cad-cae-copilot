/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it } from "vitest";
import * as THREE from "three";

import { buildFieldMarkerGroup, disposeFieldMarkerGroup } from "./fieldMarkers";
import type { SolverFieldDescriptor } from "../../types";

const IDENTITY_TRANSFORM = { scale: 1, isGlb: false };

function makeDescriptor(overrides: Partial<SolverFieldDescriptor> = {}): SolverFieldDescriptor {
  return {
    field_name: "von_mises",
    project_id: "p1",
    format: "vertex_json",
    source: "frd",
    min_value: 0,
    max_value: 200,
    unit: "MPa",
    values: [10, 50, 200, 0],
    node_coords: [
      [0, 0, 0],
      [1, 0, 0],
      [2, 0, 0],
      [3, 0, 0],
    ],
    ...overrides,
  };
}

describe("buildFieldMarkerGroup", () => {
  it("returns an empty group for a synthetic/non-FRD descriptor", () => {
    const group = buildFieldMarkerGroup(makeDescriptor({ source: "synthetic" }), IDENTITY_TRANSFORM);
    expect(group.children.length).toBe(0);
  });

  it("returns an empty group when values are missing", () => {
    const group = buildFieldMarkerGroup(makeDescriptor({ values: [], node_coords: [] }), IDENTITY_TRANSFORM);
    expect(group.children.length).toBe(0);
  });

  it("creates labelled max and min markers for a real FRD field", () => {
    const group = buildFieldMarkerGroup(makeDescriptor(), IDENTITY_TRANSFORM);
    const meshes = group.children.filter((c) => c instanceof THREE.Mesh);
    const sprites = group.children.filter((c) => c instanceof THREE.Sprite);
    expect(meshes.length).toBe(2);
    expect(sprites.length).toBe(2);

    // Max node is value 200 at (2,0,0); min node is value 0 at (3,0,0).
    const maxMesh = meshes.find((m) => m.position.x === 2);
    const minMesh = meshes.find((m) => m.position.x === 3);
    expect(maxMesh).toBeDefined();
    expect(minMesh).toBeDefined();
  });

  it("creates only a max marker when min and max coincide", () => {
    const group = buildFieldMarkerGroup(
      makeDescriptor({ values: [5, 5], node_coords: [[0, 0, 0], [1, 0, 0]] }),
      IDENTITY_TRANSFORM,
    );
    const meshes = group.children.filter((c) => c instanceof THREE.Mesh);
    const sprites = group.children.filter((c) => c instanceof THREE.Sprite);
    expect(meshes.length).toBe(1);
    expect(sprites.length).toBe(1);
  });
});

describe("disposeFieldMarkerGroup", () => {
  it("runs without throwing", () => {
    const group = buildFieldMarkerGroup(makeDescriptor(), IDENTITY_TRANSFORM);
    expect(() => disposeFieldMarkerGroup(group)).not.toThrow();
  });
});
