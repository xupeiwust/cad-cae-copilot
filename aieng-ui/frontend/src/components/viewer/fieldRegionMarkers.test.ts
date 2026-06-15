/**
 * @vitest-environment happy-dom
 */
import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { buildFieldRegionMarkerGroup } from "./fieldRegionMarkers";
import { IDENTITY_TRANSFORM } from "./coordinateFrames";
import type { FieldRegionsDocument } from "../../types";

const makeDocument = (): FieldRegionsDocument => ({
  schema_version: "0.1.0",
  format_version: "0.1.0",
  source_frd: "results/run_001/result.frd",
  field: "von_mises",
  metric: "max_von_mises_stress",
  cluster_count: 2,
  clusters: [
    {
      id: "c1",
      location: { x: 1, y: 0, z: 0 },
      magnitude: { value: 200, unit: "MPa" },
      node_count: 12,
      feature_ref: "face_001",
    },
    {
      id: "c2",
      location: { x: 0, y: 1, z: 0 },
      magnitude: { value: 150, unit: "MPa" },
      node_count: 8,
      feature_ref: null,
    },
  ],
  warnings: [],
});

describe("buildFieldRegionMarkerGroup", () => {
  it("creates one marker group per cluster", () => {
    const object = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshStandardMaterial());
    const group = buildFieldRegionMarkerGroup(makeDocument(), object, IDENTITY_TRANSFORM);
    expect(group.children).toHaveLength(2);
  });

  it("attaches cluster metadata to marker groups", () => {
    const object = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshStandardMaterial());
    const group = buildFieldRegionMarkerGroup(makeDocument(), object, IDENTITY_TRANSFORM);
    const first = group.children[0];
    expect(first.userData.type).toBe("field-region-cluster");
    expect(first.userData.cluster.id).toBe("c1");
  });
});
