import { describe, expect, it } from "vitest";

import {
  isMeshConvergenceReportMeaningful,
  meshConvergenceRows,
  meshConvergenceRefineDraft,
  meshConvergenceSummary,
} from "./meshConvergenceReport";
import type { MeshConvergenceReport } from "../types";

const makeReport = (overrides: Partial<MeshConvergenceReport> = {}): MeshConvergenceReport => ({
  status: "ok",
  tool: "cae.mesh_convergence",
  mesh_sizes: [1.0, 0.5, 0.25],
  solved_count: 3,
  convergence: {
    max_von_mises_stress: {
      metric: "max_von_mises_stress",
      level_count: 3,
      apparent_order: 2.0,
      extrapolated_value: 10.0,
      gci_fine_percent: 0.8,
      converged: true,
      verdict: "converged",
    },
    max_displacement: {
      metric: "max_displacement",
      level_count: 3,
      converged: true,
      verdict: "converged_flat",
    },
  },
  verdicts: {
    max_von_mises_stress: "converged",
    max_displacement: "converged_flat",
  },
  overall_verdict: "converged",
  ...overrides,
});

describe("isMeshConvergenceReportMeaningful", () => {
  it("returns false for null or insufficient solves", () => {
    expect(isMeshConvergenceReportMeaningful(null)).toBe(false);
    expect(isMeshConvergenceReportMeaningful(makeReport({ solved_count: 1 }))).toBe(false);
  });

  it("returns true with two or more solves", () => {
    expect(isMeshConvergenceReportMeaningful(makeReport())).toBe(true);
  });
});

describe("meshConvergenceRows", () => {
  it("emits a row per metric", () => {
    const rows = meshConvergenceRows(makeReport());
    expect(rows).toHaveLength(2);
    const stress = rows.find((r) => r.metric === "max_von_mises_stress");
    expect(stress?.gciFinePercent).toBe(0.8);
    expect(stress?.apparentOrder).toBe(2.0);
    expect(stress?.extrapolatedValue).toBe(10.0);
  });
});

describe("meshConvergenceRefineDraft", () => {
  it("drafts a finer mesh command", () => {
    expect(meshConvergenceRefineDraft(makeReport())).toBe("/simulate mesh_size_mm=0.125");
  });

  it("returns null without mesh sizes", () => {
    expect(meshConvergenceRefineDraft(makeReport({ mesh_sizes: [] }))).toBeNull();
  });
});

describe("meshConvergenceSummary", () => {
  it("reports converged", () => {
    expect(meshConvergenceSummary(makeReport())).toContain("Mesh-converged");
  });

  it("reports not converged", () => {
    expect(meshConvergenceSummary(makeReport({ overall_verdict: "not_converged" }))).toContain("Not yet mesh-converged");
  });

  it("reports indeterminate", () => {
    expect(meshConvergenceSummary(makeReport({ overall_verdict: "indeterminate" }))).toContain("Indeterminate");
  });
});
