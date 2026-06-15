import { describe, expect, it } from "vitest";

import {
  isSizingSweepReportMeaningful,
  sizingSweepRows,
  sizingSweepSummary,
  sizingSweepWinnerDraft,
} from "./sizingSweepReport";
import type { SizingSweepReport } from "../types";

const makeReport = (overrides: Partial<SizingSweepReport> = {}): SizingSweepReport => ({
  status: "ok",
  tool: "opt.sizing_sweep",
  parameter_name: "thickness",
  objective: "min_mass",
  objective_metric: "mass",
  variants: [
    {
      value: 2.0,
      metrics: { mass: 1.0, max_von_mises_stress: 260, max_displacement: 0.1 },
      solver_executed: true,
      status: "infeasible",
      rank: 2,
      objective_value: 1.0,
    },
    {
      value: 3.0,
      metrics: { mass: 1.5, max_von_mises_stress: 180, max_displacement: 0.12 },
      solver_executed: true,
      status: "feasible",
      rank: 1,
      objective_value: 1.5,
    },
  ],
  variant_count: 2,
  feasible_count: 1,
  recommended: {
    value: 3.0,
    metrics: { mass: 1.5, max_von_mises_stress: 180, max_displacement: 0.12 },
    solver_executed: true,
    status: "feasible",
    rank: 1,
    objective_value: 1.5,
  },
  recommendation_reason: "value=3.0 minimizes mass",
  safe_to_apply: true,
  ...overrides,
});

describe("isSizingSweepReportMeaningful", () => {
  it("returns false for null/empty reports", () => {
    expect(isSizingSweepReportMeaningful(null)).toBe(false);
    expect(isSizingSweepReportMeaningful(makeReport({ variants: [] }))).toBe(false);
  });

  it("returns true when variants exist", () => {
    expect(isSizingSweepReportMeaningful(makeReport())).toBe(true);
  });
});

describe("sizingSweepRows", () => {
  it("marks the recommended variant", () => {
    const rows = sizingSweepRows(makeReport());
    expect(rows).toHaveLength(2);
    expect(rows.find((r) => r.value === 3.0)?.isRecommended).toBe(true);
    expect(rows.find((r) => r.value === 2.0)?.isRecommended).toBe(false);
  });

  it("extracts metrics into typed columns", () => {
    const rows = sizingSweepRows(makeReport());
    const rec = rows.find((r) => r.isRecommended);
    expect(rec?.mass).toBe(1.5);
    expect(rec?.stress).toBe(180);
    expect(rec?.displacement).toBe(0.12);
  });
});

describe("sizingSweepWinnerDraft", () => {
  it("drafts a /modify command when safe to apply", () => {
    expect(sizingSweepWinnerDraft(makeReport())).toBe("/modify set thickness to 3");
  });

  it("returns null when no recommendation", () => {
    expect(sizingSweepWinnerDraft(makeReport({ recommended: null, safe_to_apply: false }))).toBeNull();
  });

  it("returns null when parameter name is missing", () => {
    expect(sizingSweepWinnerDraft(makeReport({ parameter_name: undefined }))).toBeNull();
  });
});

describe("sizingSweepSummary", () => {
  it("summarizes recommendation", () => {
    expect(sizingSweepSummary(makeReport())).toContain("value=3.0 minimizes mass");
  });

  it("reports no feasible variant", () => {
    expect(sizingSweepSummary(makeReport({ feasible_count: 0, recommended: null }))).toContain("No feasible");
  });
});
