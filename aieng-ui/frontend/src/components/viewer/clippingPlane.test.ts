import { describe, expect, it, vi } from "vitest";
import * as THREE from "three";

import type { SolverFieldDescriptor } from "../../types";
import {
  applyClippingPlane,
  buildClipCapMesh,
  buildClipPlane,
  clipCoordinate,
  clipNormal,
  disposeClipCapMesh,
  removeClippingPlane,
} from "./clippingPlane";

function makeBoxObject(min: number, max: number): THREE.Object3D {
  const geometry = new THREE.BoxGeometry(max - min, max - min, max - min);
  geometry.translate((min + max) / 2, (min + max) / 2, (min + max) / 2);
  const material = new THREE.MeshStandardMaterial();
  return new THREE.Mesh(geometry, material);
}

function makeDescriptor(): SolverFieldDescriptor {
  return {
    field_name: "stress",
    project_id: "p1",
    format: "vertex_json",
    basis: "frd_nearest_node",
    min_value: 0,
    max_value: 100,
    unit: "MPa",
    colormap: "thermal",
    source: "frd",
    values: [0, 50, 100, 25, 75],
    node_coords: [
      [0, 0, 0],
      [10, 0, 0],
      [10, 10, 0],
      [0, 10, 0],
      [5, 5, 10],
    ],
  };
}

describe("clipNormal", () => {
  it("points along the positive axis by default", () => {
    expect(clipNormal("x", false)).toEqual(new THREE.Vector3(1, 0, 0));
    expect(clipNormal("y", false)).toEqual(new THREE.Vector3(0, 1, 0));
    expect(clipNormal("z", false)).toEqual(new THREE.Vector3(0, 0, 1));
  });

  it("negates when flipped", () => {
    expect(clipNormal("x", true)).toEqual(new THREE.Vector3(-1, 0, 0));
    expect(clipNormal("y", true)).toEqual(new THREE.Vector3(0, -1, 0));
    expect(clipNormal("z", true)).toEqual(new THREE.Vector3(0, 0, -1));
  });
});

describe("clipCoordinate", () => {
  it("maps normalized position to the object bbox along the requested axis", () => {
    const object = makeBoxObject(0, 10);
    expect(clipCoordinate(object, "x", 0)).toBeCloseTo(0);
    expect(clipCoordinate(object, "x", 0.5)).toBeCloseTo(5);
    expect(clipCoordinate(object, "x", 1)).toBeCloseTo(10);
    expect(clipCoordinate(object, "y", 0.25)).toBeCloseTo(2.5);
  });

  it("clamps positions outside [0, 1]", () => {
    const object = makeBoxObject(0, 10);
    expect(clipCoordinate(object, "x", -0.5)).toBeCloseTo(0);
    expect(clipCoordinate(object, "x", 1.5)).toBeCloseTo(10);
  });

  it("returns 0 for an empty object", () => {
    const empty = new THREE.Object3D();
    expect(clipCoordinate(empty, "x", 0.5)).toBe(0);
  });
});

describe("buildClipPlane", () => {
  it("creates a plane at the normalized coordinate with the correct normal", () => {
    const object = makeBoxObject(0, 10);
    const plane = buildClipPlane(object, "y", 0.3, false);
    expect(plane.normal).toEqual(new THREE.Vector3(0, 1, 0));
    // For normal (0,1,0) and point (0,3,0): constant = -3.
    expect(plane.constant).toBeCloseTo(-3);
  });

  it("inverts the plane constant when flipped", () => {
    const object = makeBoxObject(0, 10);
    const plane = buildClipPlane(object, "y", 0.3, true);
    expect(plane.normal).toEqual(new THREE.Vector3(0, -1, 0));
    expect(plane.constant).toBeCloseTo(3);
  });
});

describe("applyClippingPlane / removeClippingPlane", () => {
  it("assigns the plane to every mesh material and removes it on cleanup", () => {
    const object = new THREE.Group();
    const meshA = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial());
    const meshB = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), [
      new THREE.MeshStandardMaterial(),
      new THREE.MeshStandardMaterial(),
    ]);
    object.add(meshA, meshB);

    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    applyClippingPlane(object, plane);

    expect(meshA.material.clippingPlanes).toEqual([plane]);
    expect(meshB.material[0].clippingPlanes).toEqual([plane]);
    expect(meshB.material[1].clippingPlanes).toEqual([plane]);

    removeClippingPlane(object);

    expect(meshA.material.clippingPlanes).toEqual([]);
    expect(meshB.material[0].clippingPlanes).toEqual([]);
    expect(meshB.material[1].clippingPlanes).toEqual([]);
  });
});

describe("buildClipCapMesh", () => {
  it("returns null when the object has no geometry", () => {
    const descriptor = makeDescriptor();
    expect(buildClipCapMesh(new THREE.Object3D(), "x", 0.5, descriptor)).toBeNull();
  });

  it("returns null when the descriptor lacks values or coordinates", () => {
    const object = makeBoxObject(0, 10);
    const descriptor = { ...makeDescriptor(), values: null } as unknown as SolverFieldDescriptor;
    expect(buildClipCapMesh(object, "x", 0.5, descriptor)).toBeNull();
  });

  it("returns a double-sided mesh with per-vertex colors", () => {
    const object = makeBoxObject(0, 10);
    const descriptor = makeDescriptor();
    const mesh = buildClipCapMesh(object, "x", 0.5, descriptor);
    expect(mesh).not.toBeNull();
    if (!mesh) return;

    expect(mesh.name).toBe("clip-cap");
    expect(mesh.material).toMatchObject({ side: THREE.DoubleSide, vertexColors: true });
    expect(mesh.geometry.attributes.position.count).toBeGreaterThan(0);
    expect(mesh.geometry.attributes.color.count).toBe(mesh.geometry.attributes.position.count);
  });
});

describe("disposeClipCapMesh", () => {
  it("disposes the geometry and material", () => {
    const object = makeBoxObject(0, 10);
    const mesh = buildClipCapMesh(object, "x", 0.5, makeDescriptor());
    expect(mesh).not.toBeNull();
    if (!mesh) return;

    const geometrySpy = vi.spyOn(mesh.geometry, "dispose");
    const materialSpy = vi.spyOn(mesh.material as THREE.Material, "dispose");

    disposeClipCapMesh(mesh);
    expect(geometrySpy).toHaveBeenCalled();
    expect(materialSpy).toHaveBeenCalled();
  });
});
