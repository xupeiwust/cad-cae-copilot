import { describe, expect, it } from "vitest";

import {
  controllingNames,
  isToleranceStackupReportMeaningful,
  toleranceStackupRows,
  toleranceStackupRunDraft,
  toleranceStackupSummary,
} from "./toleranceStackupReport";
import type { ToleranceStackupReport } from "../types";

const makeReport = (overrides: Partial<ToleranceStackupReport> = {}): ToleranceStackupReport => ({
  status: "ok",
  tool: "cad.tolerance_stackup",
  nominal_total: 60,
  worst_case: { min: 59.4, max: 60.6, plus_total: 0.6, minus_total: 0.6 },
  rss: { sigma: 0.173205, confidence_level: 0.95, z: 1.96, min: 59.660518, max: 60.339482 },
  contributors: [
    { name: "link_a", nominal: 10, plus: 0.1, minus: 0.1, tolerance_band: 0.2 },
    { name: "link_b", nominal: 20, plus: 0.2, minus: 0.2, tolerance_band: 0.4 },
  ],
  controlling_contributors: {
    worst_case: [{ name: "link_b", tolerance_band: 0.4 }],
    rss: [{ name: "link_b", variance: 0.004444 }],
  },
  assumptions: ["1D linear stack-up."],
  ...overrides,
});

describe("isToleranceStackupReportMeaningful", () => {
  it("returns false for missing, error, or empty reports", () => {
    expect(isToleranceStackupReportMeaningful(null)).toBe(false);
    expect(isToleranceStackupReportMeaningful(makeReport({ status: "error" }))).toBe(false);
    expect(isToleranceStackupReportMeaningful(makeReport({ contributors: [] }))).toBe(false);
  });

  it("returns true for a successful report with contributors", () => {
    expect(isToleranceStackupReportMeaningful(makeReport())).toBe(true);
  });
});

describe("toleranceStackupRows", () => {
  it("normalizes contributor rows", () => {
    const rows = toleranceStackupRows(makeReport());
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ name: "link_a", nominal: 10, plus: 0.1, minus: 0.1 });
  });
});

describe("toleranceStackupSummary", () => {
  it("summarizes nominal and worst-case tolerance band", () => {
    expect(toleranceStackupSummary(makeReport())).toContain("nominal 60.00 mm");
    expect(toleranceStackupSummary(makeReport())).toContain("worst +0.6000 / -0.6000 mm");
  });
});

describe("toleranceStackupRunDraft", () => {
  it("drafts a read-only cad.tolerance_stackup rerun", () => {
    const draft = toleranceStackupRunDraft(makeReport());
    expect(draft).toContain("Run read-only cad.tolerance_stackup");
    expect(draft).toContain('"name":"link_a"');
    expect(draft).toContain("confidence_level=0.95");
  });

  it("returns null without contributors", () => {
    expect(toleranceStackupRunDraft(makeReport({ contributors: [] }))).toBeNull();
  });
});

describe("controllingNames", () => {
  it("deduplicates controlling contributors", () => {
    expect(controllingNames(makeReport())).toEqual(["link_b"]);
  });
});
