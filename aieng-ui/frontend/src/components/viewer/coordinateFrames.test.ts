import { describe, expect, it } from "vitest";
import * as THREE from "three";

import type { BrepGraphSnapshot } from "../../appTypes";
import {
  IDENTITY_TRANSFORM,
  deriveGlbScale,
  displayToModelPoint,
  modelToDisplayVec,
} from "./coordinateFrames";

describe("coordinateFrames", () => {
  it("identity transform is a no-op in both directions", () => {
    const p = new THREE.Vector3(1, 2, 3);
    expect(displayToModelPoint(p, IDENTITY_TRANSFORM)).toMatchObject({ x: 1, y: 2, z: 3 });
    expect(modelToDisplayVec(1, 2, 3, IDENTITY_TRANSFORM)).toMatchObject({ x: 1, y: 2, z: 3 });
  });

  it("displayToModelPoint clones (does not mutate the input) under identity", () => {
    const p = new THREE.Vector3(4, 5, 6);
    const out = displayToModelPoint(p, IDENTITY_TRANSFORM);
    expect(out).not.toBe(p);
  });

  it("model→display→model round-trips for a GLB transform (Z-up mm ↔ Y-up scaled)", () => {
    const t = { scale: 0.001, isGlb: true };
    const display = modelToDisplayVec(10, 20, 30, t);
    // model → display:  (x, y, z) → ( x·s,  z·s, −y·s)
    expect(display.x).toBeCloseTo(0.01);
    expect(display.y).toBeCloseTo(0.03);
    expect(display.z).toBeCloseTo(-0.02);
    const back = displayToModelPoint(display, t);
    expect(back.x).toBeCloseTo(10);
    expect(back.y).toBeCloseTo(20);
    expect(back.z).toBeCloseTo(30);
  });

  it("deriveGlbScale falls back to mm→m when no snapshot or no face bboxes", () => {
    const obj = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1));
    expect(deriveGlbScale(obj, null)).toBe(0.001);
    const empty: BrepGraphSnapshot = { faces: {}, featureFaces: {}, groups: {} } as unknown as BrepGraphSnapshot;
    expect(deriveGlbScale(obj, empty)).toBe(0.001);
  });

  it("deriveGlbScale recovers the export scale from face bbox vs displayed bounds", () => {
    // Model face spans 100mm; displayed box spans 0.1 → scale 0.001.
    const obj = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1));
    const snapshot = {
      faces: { f1: { bounding_box: [0, 0, 0, 100, 100, 100] } },
      featureFaces: {},
      groups: {},
    } as unknown as BrepGraphSnapshot;
    expect(deriveGlbScale(obj, snapshot)).toBeCloseTo(0.001, 5);
  });
});
