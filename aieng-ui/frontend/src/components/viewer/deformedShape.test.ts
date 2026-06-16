import { describe, expect, it } from "vitest";
import * as THREE from "three";

import { applyDeformation, buildDeformedMesh, computeDeformationScale } from "./deformedShape";

describe("computeDeformationScale", () => {
  it("returns 0 when the maximum displacement is zero", () => {
    const box = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10));
    const vectors: [number, number, number][] = [
      [0, 0, 0],
      [0, 0, 0],
    ];
    expect(computeDeformationScale(vectors, box)).toBe(0);
  });

  it("scales max displacement to the target ratio of the bbox diagonal", () => {
    // Box diagonal = sqrt(3^2 + 3^2 + 3^2) ≈ 5.196.
    // Max displacement = 1. Target ratio default = 0.05.
    // Expected scale = 0.05 * 5.196 / 1 ≈ 0.2598.
    const box = new THREE.Mesh(new THREE.BoxGeometry(3, 3, 3));
    const vectors: [number, number, number][] = [
      [0, 0, 0],
      [1, 0, 0],
    ];
    expect(computeDeformationScale(vectors, box)).toBeCloseTo(0.2598, 3);
  });

  it("honours a custom target ratio", () => {
    const box = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10));
    const vectors: [number, number, number][] = [[2, 0, 0]];
    // Diagonal = sqrt(300) ≈ 17.32. scale = 0.1 * 17.32 / 2 ≈ 0.866.
    expect(computeDeformationScale(vectors, box, 0.1)).toBeCloseTo(0.866, 2);
  });
});

describe("applyDeformation", () => {
  it("offsets each vertex by scale * nearest-node displacement vector", () => {
    const geometry = new THREE.BoxGeometry(2, 2, 2);
    // BoxGeometry has positions, not a color attribute.
    const nodeCoords: [number, number, number][] = [
      [-1, -1, -1],
      [1, 1, 1],
    ];
    const vectors: [number, number, number][] = [
      [0.1, 0.2, 0.3],
      [0.4, 0.5, 0.6],
    ];

    const pos = geometry.attributes.position;
    const original = new Float32Array(pos.array.length);
    original.set(pos.array);

    applyDeformation(geometry, nodeCoords, vectors, 10);

    // Every vertex should be shifted by 10 * its nearest-node vector.
    for (let i = 0; i < pos.count; i += 1) {
      const x = original[i * 3];
      const y = original[i * 3 + 1];
      const z = original[i * 3 + 2];
      const nearest = x + y + z > 0 ? 1 : 0;
      const [dx, dy, dz] = vectors[nearest];
      expect(pos.array[i * 3]).toBeCloseTo(x + 10 * dx, 5);
      expect(pos.array[i * 3 + 1]).toBeCloseTo(y + 10 * dy, 5);
      expect(pos.array[i * 3 + 2]).toBeCloseTo(z + 10 * dz, 5);
    }
  });
});

describe("buildDeformedMesh", () => {
  it("clones the source mesh and applies deformation", () => {
    const source = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2));
    source.position.set(1, 2, 3);
    source.name = "body";

    const nodeCoords: [number, number, number][] = [[0, 0, 0]];
    const vectors: [number, number, number][] = [[0.5, 0, 0]];

    const deformed = buildDeformedMesh(source, nodeCoords, vectors, 2);

    expect(deformed.name).toBe("body_deformed");
    expect(deformed.position.equals(source.position)).toBe(true);
    expect(deformed.geometry).not.toBe(source.geometry);
  });
});
