/**
 * Pure shaping for the optimization convergence chart (#frontend-convergence-chart).
 */

export type ConvergenceVerdict =
  | "continue"
  | "converged"
  | "stop_budget"
  | "stop_no_progress"
  | "stop_no_feasible"
  | "stop_failures"
  | "stop_proposer_exhausted"
  | string;

export type OptimizationIteration = {
  index: number;
  incumbent_candidate_id: string | null;
  incumbent_objective: number | null;
  feasible: boolean;
  evaluations_total: number;
  failures_this_round: number;
  convergence_verdict: ConvergenceVerdict;
  safe_to_accept: boolean;
};

export type LatestVerdict = {
  converged: boolean;
  verdict: ConvergenceVerdict;
  reason_codes: string[];
  iteration_count: number;
};

export type OptimizationConvergence = {
  has_data: boolean;
  iterations: OptimizationIteration[];
  latest_verdict: LatestVerdict | null;
  config_used: Record<string, unknown> | null;
};

export type ConvergencePoint = {
  iteration: number;
  objective: number | null;
  feasible: boolean;
};

const VERDICT_LABEL: Record<string, string> = {
  continue: "Running",
  converged: "Converged",
  stop_budget: "Budget exhausted",
  stop_no_progress: "No progress",
  stop_no_feasible: "No feasible candidate",
  stop_failures: "Repeated failures",
  stop_proposer_exhausted: "Proposer exhausted",
};

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

function toBoolean(value: unknown): boolean {
  return value === true;
}

function toInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.floor(value));
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function normalizeVerdict(value: unknown): ConvergenceVerdict {
  if (typeof value !== "string" || value.length === 0) return "continue";
  return value;
}

function normalizeIteration(raw: unknown): OptimizationIteration | null {
  if (!isObject(raw)) return null;
  return {
    index: toInteger(raw.index),
    incumbent_candidate_id: toStringOrNull(raw.incumbent_candidate_id),
    incumbent_objective: toFiniteNumber(raw.incumbent_objective),
    feasible: toBoolean(raw.feasible),
    evaluations_total: toInteger(raw.evaluations_total),
    failures_this_round: toInteger(raw.failures_this_round),
    convergence_verdict: normalizeVerdict(raw.convergence_verdict),
    safe_to_accept: toBoolean(raw.safe_to_accept),
  };
}

function normalizeLatestVerdict(raw: unknown): LatestVerdict | null {
  if (!isObject(raw)) return null;
  return {
    converged: raw.converged === true,
    verdict: normalizeVerdict(raw.verdict),
    reason_codes: Array.isArray(raw.reason_codes)
      ? raw.reason_codes.filter((r): r is string => typeof r === "string")
      : [],
    iteration_count: toInteger(raw.iteration_count),
  };
}

export function shapeOptimizationConvergence(raw: unknown): OptimizationConvergence | null {
  if (!isObject(raw)) return null;

  const rawIterations = Array.isArray(raw.iterations) ? raw.iterations : [];
  const iterations = rawIterations
    .map(normalizeIteration)
    .filter((it): it is OptimizationIteration => it !== null)
    .sort((a, b) => a.index - b.index);

  const latest_verdict = normalizeLatestVerdict(raw.latest_verdict);
  const config_used = isObject(raw.config_used) ? raw.config_used : null;
  const has_data = iterations.length > 0 || latest_verdict != null;

  if (!has_data) return null;

  return {
    has_data,
    iterations,
    latest_verdict,
    config_used,
  };
}

export function buildConvergenceSeries(convergence: OptimizationConvergence): ConvergencePoint[] {
  return convergence.iterations.map((it) => ({
    iteration: it.index,
    objective: it.incumbent_objective,
    feasible: it.feasible,
  }));
}

export function verdictLabel(verdict: ConvergenceVerdict): string {
  return VERDICT_LABEL[verdict] ?? verdict;
}

export function formatIterationObjective(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (!Number.isFinite(value)) return "—";
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
}

export function isConvergenceMeaningful(convergence: OptimizationConvergence | null): boolean {
  return !!convergence && convergence.has_data && convergence.iterations.length > 0;
}
