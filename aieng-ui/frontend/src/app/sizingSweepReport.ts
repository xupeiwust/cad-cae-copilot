import type { SizingSweepReport, SizingSweepVariant } from "../types";

export type SizingSweepRow = {
  rank: number;
  value: number;
  status: string;
  objectiveValue: number | null;
  stress: number | null;
  displacement: number | null;
  mass: number | null;
  isRecommended: boolean;
};

export function isSizingSweepReportMeaningful(report: SizingSweepReport | null | undefined): boolean {
  if (!report) return false;
  return Array.isArray(report.variants) && report.variants.length > 0;
}

export function sizingSweepRows(report: SizingSweepReport): SizingSweepRow[] {
  const variants = report.variants ?? [];
  const recValue = report.recommended?.value;
  return variants.map((variant) => {
    const metrics = variant.metrics ?? {};
    return {
      rank: variant.rank ?? 0,
      value: typeof variant.value === "number" ? variant.value : Number(variant.value),
      status: variant.status ?? "unknown",
      objectiveValue: typeof variant.objective_value === "number" ? variant.objective_value : null,
      stress: typeof metrics.max_von_mises_stress === "number" ? metrics.max_von_mises_stress : null,
      displacement: typeof metrics.max_displacement === "number" ? metrics.max_displacement : null,
      mass: typeof metrics.mass === "number" ? metrics.mass : null,
      isRecommended: recValue !== undefined && variant.value === recValue,
    };
  });
}

export function sizingSweepWinnerDraft(report: SizingSweepReport): string | null {
  if (!report.safe_to_apply || !report.recommended) return null;
  const parameterName = report.parameter_name;
  if (!parameterName) return null;
  return `/modify set ${parameterName} to ${report.recommended.value}`;
}

export function sizingSweepRunDraft(report: SizingSweepReport): string | null {
  const featureId = report.feature_id;
  const parameterName = report.parameter_name;
  if (!featureId || !parameterName) return null;
  const values = (report.swept_values?.length ? report.swept_values : report.variants?.map((v) => v.value) ?? [])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (values.length === 0) return null;
  const parts = [
    "Run opt.sizing_sweep",
    report.project_id ? `project_id=${report.project_id}` : null,
    `featureId=${featureId}`,
    `parameterName=${parameterName}`,
    `values=[${values.join(", ")}]`,
    `objective=${report.objective ?? "min_mass"}`,
    report.constraint?.stress_limit != null ? `stress_limit=${report.constraint.stress_limit}` : null,
    report.constraint?.safety_factor != null ? `safety_factor=${report.constraint.safety_factor}` : null,
    report.constraint?.displacement_limit != null ? `displacement_limit=${report.constraint.displacement_limit}` : null,
    "apply_winner=false",
  ].filter(Boolean);
  return parts.join(" ");
}

export function sizingSweepSummary(report: SizingSweepReport): string {
  const feasible = report.feasible_count ?? 0;
  const total = report.variant_count ?? 0;
  if (report.recommended) {
    return `${report.recommendation_reason ?? "Recommended"} (${feasible}/${total} feasible)`;
  }
  if (total === 0) return "No variants evaluated";
  if (feasible === 0) return `No feasible variant among ${total} evaluated`;
  return `${feasible}/${total} feasible`;
}
