/**
 * Pure shaping for the Critique panel. No React, no I/O.
 *
 * Turns the deterministic `cad.critique` result into the panel's display model:
 * findings grouped by severity (high → medium → low) and a `/modify` fix draft
 * built from each finding's `suggested_fix` — so a critique becomes a one-click
 * fix loop instead of a buried report.
 */

import type { CritiqueFinding } from "../types";

export type Severity = "high" | "medium" | "low";

const SEVERITY_ORDER: Severity[] = ["high", "medium", "low"];

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export type CritiqueGroup = {
  severity: Severity;
  findings: CritiqueFinding[];
};

function normalizeSeverity(value: string | undefined): Severity {
  return value === "high" || value === "medium" || value === "low" ? value : "low";
}

/**
 * Group findings by severity in display order (high → medium → low). Empty groups
 * are omitted; within a group, original order is preserved. Pure and total.
 */
export function groupFindingsBySeverity(findings: CritiqueFinding[] | undefined): CritiqueGroup[] {
  const buckets = new Map<Severity, CritiqueFinding[]>();
  for (const finding of findings ?? []) {
    const severity = normalizeSeverity(finding.severity);
    const list = buckets.get(severity) ?? [];
    list.push(finding);
    buckets.set(severity, list);
  }
  const groups: CritiqueGroup[] = [];
  for (const severity of SEVERITY_ORDER) {
    const list = buckets.get(severity);
    if (list && list.length) groups.push({ severity, findings: list });
  }
  return groups;
}

/**
 * A composer-ready fix draft for a finding, or null when it carries no
 * `suggested_fix`. The suggested fix rides in as the /modify instruction; the
 * backend intent + parameter binding resolve it to a concrete edit.
 */
export function fixDraftForFinding(finding: CritiqueFinding): string | null {
  const fix = (finding.suggested_fix ?? "").trim();
  if (!fix) return null;
  return `/modify ${fix}`;
}
