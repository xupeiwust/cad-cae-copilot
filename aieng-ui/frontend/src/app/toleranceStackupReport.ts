import type { ToleranceStackupContributor, ToleranceStackupReport } from "../types";

export type ToleranceStackupRow = {
  name: string;
  nominal: number | null;
  plus: number | null;
  minus: number | null;
  toleranceBand: number | null;
  distribution: string;
};

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function isToleranceStackupReportMeaningful(
  report: ToleranceStackupReport | null | undefined,
): boolean {
  if (!report || report.status !== "ok") return false;
  return Array.isArray(report.contributors) && report.contributors.length > 0;
}

export function toleranceStackupRows(report: ToleranceStackupReport): ToleranceStackupRow[] {
  return (report.contributors ?? []).map((contributor: ToleranceStackupContributor, index) => ({
    name: contributor.name || `contrib_${index + 1}`,
    nominal: asFiniteNumber(contributor.nominal),
    plus: asFiniteNumber(contributor.plus),
    minus: asFiniteNumber(contributor.minus),
    toleranceBand: asFiniteNumber(contributor.tolerance_band),
    distribution: contributor.distribution || "normal",
  }));
}

export function toleranceStackupSummary(report: ToleranceStackupReport): string {
  const nominal = asFiniteNumber(report.nominal_total);
  const worstPlus = asFiniteNumber(report.worst_case?.plus_total);
  const worstMinus = asFiniteNumber(report.worst_case?.minus_total);
  if (nominal !== null && worstPlus !== null && worstMinus !== null) {
    return `nominal ${formatCompact(nominal)} mm, worst +${formatCompact(worstPlus)} / -${formatCompact(worstMinus)} mm`;
  }
  return `${report.contributors?.length ?? 0} contributors`;
}

export function toleranceStackupRunDraft(report: ToleranceStackupReport): string | null {
  const rows = report.contributors ?? [];
  if (rows.length === 0) return null;
  const contributors = rows.map((row, index) => ({
    name: row.name || `contrib_${index + 1}`,
    nominal: row.nominal,
    plus: row.plus,
    minus: row.minus,
    distribution: row.distribution || "normal",
  }));
  return `Run read-only cad.tolerance_stackup with contributors=${JSON.stringify(contributors)} confidence_level=${report.rss?.confidence_level ?? 0.95}`;
}

export function controllingNames(report: ToleranceStackupReport): string[] {
  const names = new Set<string>();
  for (const item of report.controlling_contributors?.worst_case ?? []) {
    if (item.name) names.add(item.name);
  }
  for (const item of report.controlling_contributors?.rss ?? []) {
    if (item.name) names.add(item.name);
  }
  return Array.from(names).slice(0, 3);
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) {
    return value.toExponential(2);
  }
  return value.toPrecision(4);
}
