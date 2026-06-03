import { expect, test } from "vitest";

import type { SimulationReadinessResponse } from "../types";
import { isReadinessMeaningful, readinessRows } from "./simulationReadiness";

function report(overrides: Partial<SimulationReadinessResponse> = {}): SimulationReadinessResponse {
  return {
    setup_source: "setup_artifact",
    ready_for_solver: false,
    inputs: {
      material: { status: "missing" },
      loads: { status: "present" },
      constraints: { status: "missing" },
      analysis_type: { status: "present", detail: "static" },
      mesh: { status: "defaultable" },
      solver: { status: "defaultable" },
    },
    missing_required_inputs: ["material", "constraints"],
    ...overrides,
  };
}

test("readinessRows orders required inputs first and flags them", () => {
  const rows = readinessRows(report());
  expect(rows.map((r) => r.key)).toEqual([
    "material", "loads", "constraints", "analysis_type", "mesh", "solver",
  ]);
  expect(rows.find((r) => r.key === "material")?.required).toBe(true);
  expect(rows.find((r) => r.key === "mesh")?.required).toBe(false);
});

test("a missing required input gets a /simulate draft; a present one does not", () => {
  const rows = readinessRows(report());
  expect(rows.find((r) => r.key === "material")?.draft).toBe("/simulate set the material to ");
  expect(rows.find((r) => r.key === "loads")?.draft).toBe(null); // present
  expect(rows.find((r) => r.key === "mesh")?.draft).toBe(null); // not required
});

test("present input keeps its detail; status normalizes unknown", () => {
  const rows = readinessRows(report());
  expect(rows.find((r) => r.key === "analysis_type")?.detail).toBe("static");
});

test("isReadinessMeaningful gates out pure-CAD projects (not_found / absent)", () => {
  expect(isReadinessMeaningful(report())).toBe(true);
  expect(isReadinessMeaningful(report({ setup_source: "not_found" }))).toBe(false);
  expect(isReadinessMeaningful(report({ setup_source: undefined }))).toBe(false);
  expect(isReadinessMeaningful(null)).toBe(false);
});
