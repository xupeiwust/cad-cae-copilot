import { expect, test } from "vitest";

import type { EditDiffResponse } from "../types";
import { shapeEditDiff } from "./editDiff";

function resp(overrides: Partial<EditDiffResponse>): EditDiffResponse {
  return { available: true, tool: "cad.edit_parameter", ...overrides };
}

test("unavailable / empty payloads yield no data", () => {
  expect(shapeEditDiff(null).hasData).toBe(false);
  expect(shapeEditDiff({ available: false }).hasData).toBe(false);
  // available but no diffs at all
  expect(shapeEditDiff(resp({})).hasData).toBe(false);
});

test("clean regression is good and needs no attention", () => {
  const view = shapeEditDiff(
    resp({
      regression_diff: {
        verdict: "clean",
        headline: "1 part changed as expected; 2 unchanged.",
        changed: [{ part: "base_plate", max_change_mm: 80, expected: true }],
        collateral_parts: [],
      },
    }),
  );
  expect(view.hasData).toBe(true);
  expect(view.regression?.tone).toBe("good");
  expect(view.regression?.changed[0]).toMatchObject({ name: "base_plate", collateral: false, maxChangeMm: 80 });
  expect(view.needsAttention).toBe(false);
});

test("collateral change is bad and marks the collateral part distinctly", () => {
  const view = shapeEditDiff(
    resp({
      regression_diff: {
        verdict: "collateral_change",
        changed: [
          { part: "arm_L", max_change_mm: 40, expected: true },
          { part: "torso", max_change_mm: 60, expected: false },
        ],
        collateral_parts: ["torso"],
      },
    }),
  );
  expect(view.regression?.tone).toBe("bad");
  expect(view.regression?.collateralCount).toBe(1);
  const torso = view.regression?.changed.find((c) => c.name === "torso");
  const arm = view.regression?.changed.find((c) => c.name === "arm_L");
  expect(torso?.collateral).toBe(true);
  expect(arm?.collateral).toBe(false);
  expect(view.needsAttention).toBe(true);
});

test("critique fail needs attention; improved/clean do not", () => {
  const failing = shapeEditDiff(
    resp({ critique_diff: { verdict: "fail", delta: { high: 1 }, introduced_count: 1 } }),
  );
  expect(failing.critique?.tone).toBe("bad");
  expect(failing.critique?.introducedCount).toBe(1);
  expect(failing.needsAttention).toBe(true);

  const improved = shapeEditDiff(resp({ critique_diff: { verdict: "improved", resolved_count: 2 } }));
  expect(improved.critique?.tone).toBe("good");
  expect(improved.critique?.resolvedCount).toBe(2);
  expect(improved.needsAttention).toBe(false);
});

test("topology_changed is a caution that needs attention", () => {
  const view = shapeEditDiff(
    resp({ regression_diff: { verdict: "topology_changed", added: ["rib"], removed: [] } }),
  );
  expect(view.regression?.tone).toBe("caution");
  expect(view.regression?.added).toEqual(["rib"]);
  expect(view.needsAttention).toBe(true);
});
