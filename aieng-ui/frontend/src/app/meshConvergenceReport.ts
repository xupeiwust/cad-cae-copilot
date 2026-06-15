import type { MeshConvergenceMetricReport, MeshConvergenceReport } from "../types";

export type MeshConvergenceRow = {
  metric: string;
  verdict: string;
  converged: boolean | null;
  gciFinePercent: number | null;
  apparentOrder: number | null;
  extrapolatedValue: number | null;
  relativeChangePercent: number | null;
  levelCount: number;
};

export function isMeshConvergenceReportMeaningful(report: MeshConvergenceReport | null | undefined): boolean {
  if (!report) return false;
  return (report.solved_count ?? 0) >= 2;
}

export function meshConvergenceRows(report: MeshConvergenceReport): MeshConvergenceRow[] {
  const convergence = report.convergence ?? {};
  return Object.entries(convergence).map(([metric, item]) => meshConvergenceRow(metric, item));
}

export function meshConvergenceRow(metric: string, item: MeshConvergenceMetricReport): MeshConvergenceRow {
  return {
    metric,
    verdict: item.verdict ?? "unknown",
    converged: item.converged ?? null,
    gciFinePercent: item.gci_fine_percent ?? null,
    apparentOrder: item.apparent_order ?? null,
    extrapolatedValue: item.extrapolated_value ?? null,
    relativeChangePercent: item.relative_change_finest_pair_percent ?? null,
    levelCount: item.level_count ?? (item.levels?.length ?? 0),
  };
}

export function meshConvergenceRefineDraft(report: MeshConvergenceReport): string | null {
  const sizes = report.mesh_sizes ?? [];
  if (sizes.length === 0) return null;
  const finest = Math.min(...sizes);
  const next = +(finest / 2).toFixed(4);
  return `/simulate mesh_size_mm=${next}`;
}

export function meshConvergenceSummary(report: MeshConvergenceReport): string {
  const verdict = report.overall_verdict ?? "unknown";
  switch (verdict) {
    case "converged":
      return "Mesh-converged within the GCI threshold";
    case "not_converged":
      return "Not yet mesh-converged — consider a finer mesh";
    case "indeterminate":
      return "Indeterminate — add finer meshes or check metric monotonicity";
    case "no_solves":
      return "No successful solves";
    default:
      return `Mesh convergence: ${verdict}`;
  }
}
