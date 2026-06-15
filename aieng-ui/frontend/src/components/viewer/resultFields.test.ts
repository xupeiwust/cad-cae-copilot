import { describe, expect, it } from "vitest";

import {
  RESULT_FIELD_GROUPS,
  allResultFieldNames,
  canonicalResultField,
  formatFieldValue,
  legendTicks,
  resultFieldLabel,
} from "./resultFields";
import { colormapCssStops } from "./fieldColors";

describe("result field catalog", () => {
  it("groups the expected CAE fields", () => {
    const groups = RESULT_FIELD_GROUPS.map((g) => g.group);
    expect(groups).toEqual(["Stress", "Principal", "Displacement", "Safety"]);
    const names = allResultFieldNames();
    expect(names).toContain("von_mises");
    expect(names).toContain("s1");
    expect(names).toContain("safety_factor");
    expect(names).toContain("ux");
  });

  it("maps legacy aliases to canonical names", () => {
    expect(canonicalResultField("stress")).toBe("von_mises");
    expect(canonicalResultField("displacement")).toBe("disp_magnitude");
    expect(canonicalResultField("S1")).toBe("s1");
  });

  it("labels fields (incl. aliases) and falls back to the raw name", () => {
    expect(resultFieldLabel("von_mises")).toBe("Von Mises");
    expect(resultFieldLabel("stress")).toBe("Von Mises"); // alias
    expect(resultFieldLabel("safety_factor")).toContain("Safety factor");
    expect(resultFieldLabel("mystery")).toBe("mystery");
  });
});

describe("formatFieldValue", () => {
  it("formats with units and sensible precision", () => {
    expect(formatFieldValue(182.37, "MPa")).toBe("182.4 MPa");
    expect(formatFieldValue(2.5, "")).toBe("2.50");
    expect(formatFieldValue(0.0123, "mm")).toBe("0.0123 mm");
    expect(formatFieldValue(250000, "MPa")).toBe("2.50e+5 MPa");
    expect(formatFieldValue(Number.NaN, "MPa")).toBe("—");
  });
});

describe("legendTicks", () => {
  it("returns evenly spaced ticks across the range", () => {
    expect(legendTicks(0, 100, 5)).toEqual([0, 25, 50, 75, 100]);
  });
  it("handles degenerate ranges", () => {
    expect(legendTicks(5, 5, 5)).toEqual([5]);
  });
});

describe("colormapCssStops", () => {
  it("returns N rgb() stops spanning low→high", () => {
    const stops = colormapCssStops("thermal", 8);
    expect(stops).toHaveLength(8);
    expect(stops[0]).toMatch(/^rgb\(/);
    expect(stops[7]).toMatch(/^rgb\(/);
    // thermal low is blue-ish, high is red-ish → endpoints differ
    expect(stops[0]).not.toEqual(stops[7]);
  });
});
