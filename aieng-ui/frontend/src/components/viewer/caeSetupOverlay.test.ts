/**
 * @vitest-environment happy-dom
 */
import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { buildCaeSetupGroup } from "./caeSetupOverlay";
import { IDENTITY_TRANSFORM } from "./coordinateFrames";
import type { CaeSetupOverlayResponse } from "../../types";

function makeOverlay(): CaeSetupOverlayResponse {
  return {
    available: true,
    project_id: "p1",
    loads: [
      {
        id: "load_1",
        type: "force",
        value_n: 100,
        direction: [0, 0, -1],
        face_ids: ["face_load"],
        faces: [
          {
            face_id: "face_load",
            center_mm: [1, 0, 0],
            normal: [0, 0, 1],
            surface_type: "plane",
            stale: false,
          },
        ],
      },
    ],
    constraints: [
      {
        id: "bc_1",
        type: "fixed",
        face_ids: ["face_fixed"],
        faces: [
          {
            face_id: "face_fixed",
            center_mm: [0, 1, 0],
            normal: [0, 1, 0],
            surface_type: "plane",
            stale: false,
          },
        ],
      },
    ],
  };
}

function makeCubeObject(): THREE.Object3D {
  const geometry = new THREE.BoxGeometry(2, 2, 2);
  const material = new THREE.MeshStandardMaterial();
  const mesh = new THREE.Mesh(geometry, material);
  return mesh;
}

describe("buildCaeSetupGroup", () => {
  it("creates load arrows and constraint glyphs", () => {
    const object = makeCubeObject();
    const group = buildCaeSetupGroup(makeOverlay(), new Map(), object, null, IDENTITY_TRANSFORM);
    expect(group.children.length).toBeGreaterThan(0);
  });

  it("highlights bound faces when primitive map is provided", () => {
    const object = makeCubeObject();
    const prim = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial());
    object.add(prim);
    const faceMeshes = new Map<string, THREE.Mesh[]>([["face_load", [prim]]]);
    const group = buildCaeSetupGroup(makeOverlay(), faceMeshes, object, null, IDENTITY_TRANSFORM);
    const overlays = group.children.filter((c) => c instanceof THREE.Mesh);
    expect(overlays.length).toBeGreaterThan(0);
  });
});
