import { expect, test } from "vitest";

import type { EditableParameter } from "../types";
import {
  editDraftForParameter,
  formatNumber,
  formatRange,
  groupParametersByScope,
} from "./editableParameters";

function param(overrides: Partial<EditableParameter>): EditableParameter {
  return {
    feature_id: "f",
    feature_name: "feat",
    feature_type: "named_part",
    scope: "local",
    parameter_name: "thickness_mm",
    cad_parameter_name: "WALL_THICKNESS",
    current_value: 3,
    min_value: 0.15,
    max_value: 15,
    ...overrides,
  };
}

test("groupParametersByScope orders local → global → unscoped and drops empty groups", () => {
  const groups = groupParametersByScope([
    param({ scope: "global", parameter_name: "radius_mm", feature_name: "Global Parameters" }),
    param({ scope: "local", parameter_name: "radius_mm", feature_name: "motor_pod" }),
    param({ scope: "local", parameter_name: "height_mm", feature_name: "leg" }),
  ]);
  expect(groups.map((g) => g.scope)).toEqual(["local", "global"]);
  // local group sorted by feature then parameter name.
  expect(groups[0].parameters.map((p) => p.feature_name)).toEqual(["leg", "motor_pod"]);
});

test("groupParametersByScope normalizes unknown scope to local", () => {
  const groups = groupParametersByScope([param({ scope: "weird" as EditableParameter["scope"] })]);
  expect(groups.length).toBe(1);
  expect(groups[0].scope).toBe("local");
});

test("formatNumber trims trailing .0 and handles null", () => {
  expect(formatNumber(5)).toBe("5");
  expect(formatNumber(4.5)).toBe("4.5");
  expect(formatNumber(null)).toBe("");
  expect(formatNumber(undefined)).toBe("");
});

test("formatRange renders both bounds or empty", () => {
  expect(formatRange(0.15, 15)).toBe("0.15 – 15");
  expect(formatRange(null, null)).toBe("");
  expect(formatRange(2, null)).toBe("2 – ?");
});

test("editDraftForParameter builds a /modify draft with the human name", () => {
  expect(editDraftForParameter(param({ parameter_name: "wall_thickness" }))).toBe(
    "/modify set wall thickness to ",
  );
});
