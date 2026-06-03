import { expect, test } from "vitest";

import type { CritiqueFinding } from "../types";
import { fixDraftForFinding, groupFindingsBySeverity } from "./critiqueFindings";

function f(overrides: Partial<CritiqueFinding>): CritiqueFinding {
  return { severity: "medium", rule: "min_wall_thickness", observation: "wall is 1.2mm", ...overrides };
}

test("groupFindingsBySeverity orders high → medium → low and drops empty", () => {
  const groups = groupFindingsBySeverity([
    f({ severity: "low" }),
    f({ severity: "high" }),
    f({ severity: "medium" }),
    f({ severity: "high" }),
  ]);
  expect(groups.map((g) => g.severity)).toEqual(["high", "medium", "low"]);
  expect(groups[0].findings.length).toBe(2);
});

test("unknown severity normalizes to low", () => {
  const groups = groupFindingsBySeverity([f({ severity: "weird" as CritiqueFinding["severity"] })]);
  expect(groups[0].severity).toBe("low");
});

test("fixDraftForFinding builds a /modify from suggested_fix, else null", () => {
  expect(fixDraftForFinding(f({ suggested_fix: "increase WALL_THICKNESS to 3mm" }))).toBe(
    "/modify increase WALL_THICKNESS to 3mm",
  );
  expect(fixDraftForFinding(f({ suggested_fix: "  " }))).toBe(null);
  expect(fixDraftForFinding(f({}))).toBe(null);
});
