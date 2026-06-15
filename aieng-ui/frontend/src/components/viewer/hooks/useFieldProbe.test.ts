/**
 * @vitest-environment happy-dom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { render } from "@testing-library/react";

import { useFieldProbe } from "./useFieldProbe";
import type { SolverFieldDescriptor } from "../../../types";

const descriptor: SolverFieldDescriptor = {
  project_id: "p1",
  field_name: "von_mises",
  format: "vertex_json",
  source: "frd",
  min_value: 0,
  max_value: 200,
  unit: "MPa",
  values: [0, 100, 200],
  node_coords: [
    [0, 0, 0],
    [1, 0, 0],
    [2, 0, 0],
  ],
};

vi.mock("three", () => {
  function Vector3(this: any, x = 0, y = 0, z = 0) {
    this.x = x;
    this.y = y;
    this.z = z;
  }
  (Vector3.prototype as any).clone = function () {
    return new (Vector3 as any)(this.x, this.y, this.z);
  };

  function Vector2(this: any, x = 0, y = 0) {
    this.x = x;
    this.y = y;
  }

  function Raycaster(this: any) {
    this.ray = { origin: new (Vector3 as any)(), direction: new (Vector3 as any)() };
  }
  (Raycaster.prototype as any).setFromCamera = vi.fn();
  (Raycaster.prototype as any).intersectObjects = vi.fn((_objects: unknown, _recursive: boolean) => [
    { point: new (Vector3 as any)(1, 0, 0), object: {} },
  ]);

  function Mesh() {}

  return {
    __esModule: true,
    default: {},
    Vector3,
    Vector2,
    Raycaster,
    Mesh,
  };
});

vi.mock("../../viewer/fieldColors", () => ({
  buildUniformGrid: vi.fn(() => ({ cells: new Map() })),
  nearestNodeIndex: vi.fn(() => 1),
}));

function setup() {
  const host = document.createElement("div");
  host.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 200 } as DOMRect);
  const hostRef = { current: host };
  const objectRef = { current: { children: [] } as unknown as import("three").Object3D };
  const cameraRef = { current: {} as unknown as import("three").PerspectiveCamera };
  const primitiveFaceRef = { current: new Map() };
  const displayTransformRef = { current: { scale: 1, isGlb: false } };
  const onFieldProbe = vi.fn();

  function TestComponent() {
    useFieldProbe(hostRef, objectRef, cameraRef, primitiveFaceRef, displayTransformRef, descriptor, onFieldProbe);
    return null;
  }
  render(createElement(TestComponent));
  return { host, onFieldProbe };
}

describe("useFieldProbe", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("reports the nearest node value on click", () => {
    const { host, onFieldProbe } = setup();
    host.dispatchEvent(new MouseEvent("click", { clientX: 50, clientY: 60, bubbles: true }));

    expect(onFieldProbe).toHaveBeenCalledWith(
      expect.objectContaining({
        value: 100,
        unit: "MPa",
        coord: [1, 0, 0],
        pointer: null,
        screenX: 50,
        screenY: 60,
      }),
    );
  });

  it("clears the probe when clicking empty space", async () => {
    const { Raycaster } = await import("three");
    (Raycaster.prototype.intersectObjects as ReturnType<typeof vi.fn>).mockReturnValueOnce([]);
    const { host, onFieldProbe } = setup();
    host.dispatchEvent(new MouseEvent("click", { clientX: 10, clientY: 10, bubbles: true }));

    expect(onFieldProbe).toHaveBeenCalledWith(null);
  });
});
