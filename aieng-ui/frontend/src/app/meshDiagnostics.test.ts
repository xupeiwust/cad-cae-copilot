import { describe, expect, it } from "vitest";

import { meshDiagnosticsSummary } from "./meshDiagnostics";
import type { MeshDiagnosticsResponse } from "../types";

const report = (overrides: Partial<MeshDiagnosticsResponse> = {}): MeshDiagnosticsResponse => ({
  available: true,
  overall_verdict: "ok",
  verdict: "ok",
  element_count: 10,
  tet_count: 10,
  degenerate_element_count: 0,
  poor_element_count: 0,
  broken_element_count: 0,
  set_coverage: {
    verdict: "ok",
    set_count: 2,
    empty_set_count: 0,
    unresolved_set_count: 0,
    sparse_set_count: 0,
  },
  ...overrides,
});

describe("meshDiagnosticsSummary", () => {
  it("hides unavailable diagnostics", () => {
    expect(meshDiagnosticsSummary({ available: false })).toBeNull();
  });

  it("summarizes a clean mesh", () => {
    const summary = meshDiagnosticsSummary(report());
    expect(summary?.label).toBe("mesh ok");
    expect(summary?.detail).toContain("quality and set coverage ok");
  });

  it("surfaces failed element and set coverage counts", () => {
    const summary = meshDiagnosticsSummary(
      report({
        overall_verdict: "fail",
        broken_element_count: 1,
        degenerate_element_count: 2,
        set_coverage: {
          verdict: "fail",
          set_count: 2,
          empty_set_count: 1,
          unresolved_set_count: 1,
          sparse_set_count: 0,
        },
      }),
    );
    expect(summary?.label).toBe("mesh fail");
    expect(summary?.detail).toContain("1 broken elem");
    expect(summary?.detail).toContain("2 degenerate elem");
    expect(summary?.detail).toContain("1 empty set");
    expect(summary?.detail).toContain("1 unresolved set");
  });

  it("surfaces sparse set warnings", () => {
    const summary = meshDiagnosticsSummary(
      report({
        overall_verdict: "warning",
        set_coverage: {
          verdict: "warning",
          set_count: 1,
          empty_set_count: 0,
          unresolved_set_count: 0,
          sparse_set_count: 1,
        },
      }),
    );
    expect(summary?.label).toBe("mesh warn");
    expect(summary?.detail).toContain("1 sparse set");
  });

  it("surfaces high aspect ratio context for poor elements", () => {
    const summary = meshDiagnosticsSummary(
      report({
        overall_verdict: "warning",
        poor_element_count: 1,
        max_aspect_ratio: 18.25,
        worst_element_id: 11,
      }),
    );
    expect(summary?.label).toBe("mesh warn");
    expect(summary?.detail).toContain("1 poor elem");
    expect(summary?.detail).toContain("max aspect 18.3 @ elem 11");
  });
});
