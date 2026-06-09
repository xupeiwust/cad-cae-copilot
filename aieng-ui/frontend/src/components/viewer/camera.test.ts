import { expect, test } from "vitest";
import * as THREE from "three";

import { fitCameraToObject } from "./camera";

function controls() {
  return {
    target: new THREE.Vector3(),
    update: () => undefined,
  };
}

test("fits meter-scaled GLB geometry using its real dimensions", () => {
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
  const object = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.02, 0.01));

  expect(fitCameraToObject(camera, controls(), object)).toBe(true);
  expect(camera.position.length()).toBeLessThan(0.5);
  expect(camera.near).toBeLessThan(0.01);
});

test("rejects objects without geometry bounds", () => {
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
  expect(fitCameraToObject(camera, controls(), new THREE.Group())).toBe(false);
});
