/**
 * Pure shaping for the Simulation Readiness panel. No React, no I/O.
 *
 * Turns `build_simulation_readiness_report` output into ordered rows the panel
 * renders, and builds a `/simulate` draft for a missing required input so the
 * user can fill the gap through the existing approval-gated path. Pure and total.
 */

import type { SimulationReadinessInput, SimulationReadinessResponse } from "../types";

export type ReadinessStatus = "present" | "missing" | "defaultable" | "unknown";

/** Display order = the six core inputs, required ones first. */
const INPUT_ORDER = ["material", "loads", "constraints", "analysis_type", "mesh", "solver"] as const;

export const INPUT_LABEL: Record<string, string> = {
  material: "Material",
  loads: "Loads",
  constraints: "Constraints",
  analysis_type: "Analysis type",
  mesh: "Mesh",
  solver: "Solver",
};

/** Required inputs whose absence blocks a solver run. */
const REQUIRED = new Set(["material", "loads", "constraints"]);

// A /simulate draft that fills a missing required input.
const MISSING_DRAFT: Record<string, string> = {
  material: "/simulate set the material to ",
  loads: "/simulate add a load of ",
  constraints: "/simulate add a fixed support on ",
};

export type ReadinessRow = {
  key: string;
  label: string;
  status: ReadinessStatus;
  required: boolean;
  detail: string | null;
  /** Composer draft to fill this input, when it is a missing required one. */
  draft: string | null;
};

function normalizeStatus(value: string | undefined): ReadinessStatus {
  return value === "present" || value === "missing" || value === "defaultable" ? value : "unknown";
}

/** Build ordered readiness rows from the report's inputs map. Pure and total. */
export function readinessRows(report: SimulationReadinessResponse | null): ReadinessRow[] {
  const inputs = report?.inputs ?? {};
  const rows: ReadinessRow[] = [];
  for (const key of INPUT_ORDER) {
    const input: SimulationReadinessInput | undefined = inputs[key];
    if (!input) continue;
    const status = normalizeStatus(input.status);
    const required = REQUIRED.has(key);
    rows.push({
      key,
      label: INPUT_LABEL[key] ?? key,
      status,
      required,
      detail: typeof input.detail === "string" && input.detail ? input.detail : null,
      draft: required && status === "missing" ? MISSING_DRAFT[key] ?? null : null,
    });
  }
  return rows;
}

/**
 * True when the readiness report is worth surfacing — i.e. the project is a CAE
 * candidate (a setup artifact / cae block exists). A pure CAD project with no CAE
 * setup (`setup_source` of `not_found` / absent) hides the panel to avoid noise.
 */
export function isReadinessMeaningful(report: SimulationReadinessResponse | null): boolean {
  if (!report) return false;
  const source = report.setup_source;
  return typeof source === "string" && source.length > 0 && source !== "not_found";
}
