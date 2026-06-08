import { expect, test } from "vitest";

import type { GeometryReportResponse } from "../types";
import {
  assemblyAlertCounts,
  brokenSymmetryNames,
  brokenSymmetryPartBoxes,
  floatingPartBoxes,
  isBrokenSymmetry,
} from "./geometryReport";

const REPORT: GeometryReportResponse = {
  available: true,
  units: "mm",
  floating_parts: ["foot_FL", "ghost"], // ghost has no box → dropped
  symmetry: [
    { pair: ["arm_L", "arm_R"], ok: false },
    { pair: ["leg_L", "leg_R"], ok: true }, // ok → ignored
    { part: "ear_L", expected_partner: "ear_R", status: "missing_partner" },
  ],
  part_boxes: {
    foot_FL: [-200, -10, -20, -180, 10, 0],
    arm_L: [-50, -10, 150, -30, 10, 290],
    arm_R: [30, -10, 150, 50, 10, 250],
    ear_L: [-5, 40, 300, 5, 50, 310],
  },
};

test("floatingPartBoxes returns only floating parts that have a box", () => {
  const boxes = floatingPartBoxes(REPORT);
  expect(boxes.map((b) => b.name)).toEqual(["foot_FL"]); // ghost dropped (no box)
  expect(boxes[0].bbox).toHaveLength(6);
});

test("brokenSymmetryNames collects mismatched + missing-partner parts, skips ok pairs", () => {
  expect(brokenSymmetryNames(REPORT).sort()).toEqual(["arm_L", "arm_R", "ear_L"]);
});

test("brokenSymmetryPartBoxes resolves names to boxes (skips boxless)", () => {
  expect(brokenSymmetryPartBoxes(REPORT).map((b) => b.name).sort()).toEqual(["arm_L", "arm_R", "ear_L"]);
});

test("isBrokenSymmetry flags ok=false and missing_partner only", () => {
  expect(isBrokenSymmetry({ ok: false })).toBe(true);
  expect(isBrokenSymmetry({ status: "missing_partner" })).toBe(true);
  expect(isBrokenSymmetry({ ok: true })).toBe(false);
  expect(isBrokenSymmetry(null)).toBe(false);
});

test("assemblyAlertCounts counts floating parts + broken symmetry pairs", () => {
  expect(assemblyAlertCounts(REPORT)).toEqual({ floating: 2, symmetry: 2, total: 4 });
  expect(assemblyAlertCounts(null)).toEqual({ floating: 0, symmetry: 0, total: 0 });
});
