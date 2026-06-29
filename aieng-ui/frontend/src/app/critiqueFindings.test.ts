import { expect, test } from "vitest";

import type { CritiqueFinding } from "../types";
import {
  fastenerPlanDraft,
  fastenerPlanHasMatches,
  fastenerPlanSummary,
  fixDraftForFinding,
  groupFindingsBySeverity,
} from "./critiqueFindings";

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

test("standard fastener plan helpers stay advisory and require matches", () => {
  const plan = { status: "ok", advisory_only: true, mutates_geometry: false, matched_count: 2, plan_count: 2 };
  expect(fastenerPlanHasMatches(plan)).toBe(true);
  expect(fastenerPlanSummary(plan)).toBe("2 matched holes; 2 advisory fastener plans");
  expect(fastenerPlanDraft(plan)).toBe("/modify insert standard fasteners for matched mounting holes");
  expect(fastenerPlanHasMatches({ status: "unavailable", matched_count: 0 })).toBe(false);
  expect(fastenerPlanDraft(null)).toBe(null);
});
