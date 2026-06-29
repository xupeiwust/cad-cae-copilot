import { expect, test } from "vitest";

import type { GeometryReportResponse } from "../types";
import {
  assemblyAlertCounts,
  brokenSymmetryNames,
  brokenSymmetryPartBoxes,
  floatingPartBoxes,
  isBrokenSymmetry,
  spatialIssueBoxes,
} from "./geometryReport";

const REPORT: GeometryReportResponse = {
  available: true,
  units: "mm",
  floating_parts: ["foot_FL", "ghost"], // ghost has no box, so it is dropped from drawable boxes.
  symmetry: [
    { pair: ["arm_L", "arm_R"], ok: false },
    { pair: ["leg_L", "leg_R"], ok: true },
    { part: "ear_L", expected_partner: "ear_R", status: "missing_partner" },
  ],
  spatial_relationships: [
    { parts: ["torso", "buried_insert"], status: "contained" },
    { parts: ["arm_L", "arm_R"], status: "deep_overlap" },
    { parts: ["torso", "wire_bundle"], status: "contained_in_hollow" },
  ],
  part_boxes: {
    torso: [-30, -15, 100, 30, 15, 300],
    buried_insert: [-5, -5, 150, 5, 5, 160],
    foot_FL: [-200, -10, -20, -180, 10, 0],
    arm_L: [-50, -10, 150, -30, 10, 290],
    arm_R: [-40, -8, 160, 50, 10, 250],
    ear_L: [-5, 40, 300, 5, 50, 310],
    wire_bundle: [0, 0, 120, 3, 3, 140],
  },
};

test("floatingPartBoxes returns only floating parts that have a box", () => {
  const boxes = floatingPartBoxes(REPORT);
  expect(boxes.map((b) => b.name)).toEqual(["foot_FL"]);
  expect(boxes[0].bbox).toHaveLength(6);
});

test("brokenSymmetryNames collects mismatched + missing-partner parts, skips ok pairs", () => {
  expect(brokenSymmetryNames(REPORT).sort()).toEqual(["arm_L", "arm_R", "ear_L"]);
});

test("brokenSymmetryPartBoxes resolves names to boxes and skips boxless entries", () => {
  expect(brokenSymmetryPartBoxes(REPORT).map((b) => b.name).sort()).toEqual(["arm_L", "arm_R", "ear_L"]);
});

test("isBrokenSymmetry flags ok=false and missing_partner only", () => {
  expect(isBrokenSymmetry({ ok: false })).toBe(true);
  expect(isBrokenSymmetry({ status: "missing_partner" })).toBe(true);
  expect(isBrokenSymmetry({ ok: true })).toBe(false);
  expect(isBrokenSymmetry(null)).toBe(false);
});

test("assemblyAlertCounts counts floating, broken symmetry, and spatial issues", () => {
  expect(assemblyAlertCounts(REPORT)).toEqual({ floating: 2, symmetry: 2, spatial: 2, total: 6 });
  expect(assemblyAlertCounts(null)).toEqual({ floating: 0, symmetry: 0, spatial: 0, total: 0 });
});

test("spatialIssueBoxes highlights deep overlap / solid containment only", () => {
  const boxes = spatialIssueBoxes(REPORT);
  expect(boxes.map((box) => box.status).sort()).toEqual(["contained", "deep_overlap"]);
  expect(boxes.find((box) => box.status === "contained")?.bbox).toEqual([-5, -5, 150, 5, 5, 160]);
  expect(boxes.find((box) => box.status === "deep_overlap")?.bbox).toEqual([-40, -8, 160, -30, 10, 250]);
});
