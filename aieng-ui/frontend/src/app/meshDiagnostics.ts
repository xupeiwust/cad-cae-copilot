import type { MeshDiagnosticsResponse } from "../types";

export type MeshDiagnosticsSummary = {
  verdict: string;
  label: string;
  detail: string;
  color: string;
};

const VERDICT_LABEL: Record<string, string> = {
  ok: "mesh ok",
  warning: "mesh warn",
  fail: "mesh fail",
  unknown: "mesh unknown",
};

const VERDICT_COLOR: Record<string, string> = {
  ok: "#86efac",
  warning: "#facc15",
  fail: "#fca5a5",
  unknown: "#cbd5e1",
};

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function meshDiagnosticsSummary(
  diagnostics: MeshDiagnosticsResponse | null | undefined,
): MeshDiagnosticsSummary | null {
  if (!diagnostics?.available) return null;
  const verdict = String(diagnostics.overall_verdict || diagnostics.verdict || "unknown");
  const coverage = diagnostics.set_coverage;
  const issues: string[] = [];

  const broken = num(diagnostics.broken_element_count);
  const degenerate = num(diagnostics.degenerate_element_count);
  const poor = num(diagnostics.poor_element_count);
  const empty = num(coverage?.empty_set_count);
  const unresolved = num(coverage?.unresolved_set_count);
  const sparse = num(coverage?.sparse_set_count);

  if (broken) issues.push(`${broken} broken elem`);
  if (degenerate) issues.push(`${degenerate} degenerate elem`);
  if (poor) issues.push(`${poor} poor elem`);
  if (empty) issues.push(`${empty} empty set`);
  if (unresolved) issues.push(`${unresolved} unresolved set`);
  if (sparse) issues.push(`${sparse} sparse set`);

  if (issues.length === 0) {
    if (verdict === "ok") issues.push("quality and set coverage ok");
    else if (verdict === "unknown") issues.push("diagnostic coverage unknown");
    else issues.push("review diagnostics");
  }

  return {
    verdict,
    label: VERDICT_LABEL[verdict] ?? `mesh ${verdict}`,
    detail: issues.join("; "),
    color: VERDICT_COLOR[verdict] ?? VERDICT_COLOR.unknown,
  };
}
