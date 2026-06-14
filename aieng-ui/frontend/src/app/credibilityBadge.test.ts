import { expect, test } from "vitest";

import type { CredibilityStamp } from "../types";
import { formatCredibilityTier } from "./credibilityBadge";

function stamp(overrides: Partial<CredibilityStamp>): CredibilityStamp {
  return { tier: "critique_finding", rank: 1, ...overrides };
}

test("returns null when no stamp is present", () => {
  expect(formatCredibilityTier(null)).toBeNull();
  expect(formatCredibilityTier(undefined)).toBeNull();
  // garbage stamp without a tier string
  expect(formatCredibilityTier({ rank: 4 } as unknown as CredibilityStamp)).toBeNull();
});

test("tone escalates with rank; solver is strongest, unverified is caution", () => {
  const solver = formatCredibilityTier(stamp({ tier: "executed_solver_result", rank: 4 }));
  const proxy = formatCredibilityTier(stamp({ tier: "proxy_assembly_result", rank: 3 }));
  const surrogate = formatCredibilityTier(stamp({ tier: "surrogate_prediction", rank: 2 }));
  const critique = formatCredibilityTier(stamp({ tier: "critique_finding", rank: 1 }));
  const unverified = formatCredibilityTier(stamp({ tier: "unverified", rank: 0 }));

  expect(solver?.tone).toBe("strong");
  expect(proxy?.tone).toBe("info");
  expect(surrogate?.tone).toBe("info");
  expect(critique?.tone).toBe("neutral");
  expect(unverified?.tone).toBe("caution");

  // rank carried through for ordering by consumers
  expect(solver!.rank).toBeGreaterThan(proxy!.rank);
  expect(proxy!.rank).toBeGreaterThan(surrogate!.rank);
});

test("uses backend label when present, falls back to a known tier label", () => {
  expect(formatCredibilityTier(stamp({ label: "Custom" }))!.label).toBe("Custom");
  expect(formatCredibilityTier(stamp({ label: undefined }))!.label).toBe("Critique finding");
});

test("tooltip surfaces evidence basis, downgrade reason, and non-certification", () => {
  const model = formatCredibilityTier(
    stamp({
      tier: "unverified",
      rank: 0,
      evidence_basis: "no executed evidence",
      downgrade_reason: "solver_executed is not true",
      production_ready: false,
    }),
  );
  expect(model!.title).toContain("no executed evidence");
  expect(model!.title).toContain("Downgraded: solver_executed is not true");
  expect(model!.title).toContain("Not production-certified.");
});
