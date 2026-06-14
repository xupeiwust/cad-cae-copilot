/**
 * Pure shaping for the Optimization panel. No React, no I/O.
 *
 * Turns design-study artifacts (candidate ranking, recommendation, report)
 * into a read-only display model. The panel itself never mutates geometry;
 * actions draft into the composer and flow through the approval-gated path.
 */

export type CandidateFeasibility = "feasible" | "infeasible" | "unknown" | "failed";

export type ObjectiveDelta = {
  metric?: string | null;
  candidate_value?: number | null;
  baseline_value?: number | null;
  delta_percent?: number | null;
  delta_absolute?: number | null;
  /** Unit of the objective metric (e.g. "kg", "MPa"); "" / null when dimensionless. */
  unit?: string | null;
};

export type OptimizationCandidate = {
  candidate_id: string;
  rank: number;
  feasibility: CandidateFeasibility;
  score?: number | null;
  confidence?: "high" | "medium" | "low" | null;
  metrics?: Record<string, number | string | null>;
  /** Honesty signal: true when metrics are incomplete or proxy-based. */
  has_unknown_metrics?: boolean;
  /** Deepening: per-candidate engineering details surfaced for transparency. */
  constraint_violations?: string[];
  objective_delta?: ObjectiveDelta | null;
  reasons?: string[];
  metrics_missing?: string[];
  recommendation?: string | null;
  execution_status?: string | null;
};

export type OptimizationRecommendation = {
  headline: string | null;
  reason_codes: string[];
  caveats: string[];
  /** Honesty signal: never claims the recommendation is a final decision. */
  advisory_only: boolean;
};

export type IterationHistoryEntry = {
  index?: number;
  incumbent_candidate_id?: string | null;
  incumbent_objective?: number | null;
  feasible?: boolean | null;
  evaluations_total?: number | null;
  convergence_verdict?: string | null;
};

export type OptimizationReport = {
  summary?: string | null;
  variable_count?: number;
  candidate_count?: number;
  /** Deepening: aggregated transparency from the optimization report. */
  feasibility_summary?: Record<string, number>;
  failed_candidates?: Array<{
    candidate_id: string;
    execution_status?: string | null;
    feasibility?: string | null;
    reasons?: string[];
  }>;
  iteration_history?: IterationHistoryEntry[];
  missing_stages?: string[];
};

export type OptimizationProblem = {
  objective?: unknown;
  constraints?: unknown[];
  variable_count?: number;
};

export type OptimizationRanking = {
  best_candidate_id?: string | null;
  next_action?: string | null;
};

export type OptimizationAcceptance = {
  status?: string | null;
  accepted_candidate_id?: string | null;
};

export type OptimizationStudy = {
  has_study: boolean;
  candidates: OptimizationCandidate[];
  recommendation: OptimizationRecommendation | null;
  report: OptimizationReport | null;
  /** Honesty signal: whether the best candidate is safe to accept. */
  safe_to_accept: boolean;
  /** Honesty signal: whether baseline was ever modified (should be false). */
  baseline_modified: boolean | null;
  warnings: string[];
  /** Deepening: problem definition, ranking summary, acceptance state, and iteration history. */
  problem?: OptimizationProblem | null;
  ranking?: OptimizationRanking | null;
  acceptance?: OptimizationAcceptance | null;
};

const FEASIBILITY_ORDER: CandidateFeasibility[] = ["feasible", "unknown", "infeasible", "failed"];

export const FEASIBILITY_LABEL: Record<CandidateFeasibility, string> = {
  feasible: "Feasible",
  infeasible: "Infeasible",
  unknown: "Unknown",
  failed: "Failed",
};

export const FEASIBILITY_HINT: Record<CandidateFeasibility, string> = {
  feasible: "Satisfies constraints and improves the objective.",
  infeasible: "Violates one or more constraints.",
  unknown: "Missing metrics or incomplete evaluation.",
  failed: "Execution failed — no result produced.",
};

/**
 * Shape raw artifact JSON into a typed OptimizationStudy. Defensive: every field
 * is validated at runtime so a malformed or partial artifact never crashes the panel.
 */
export function shapeOptimizationStudy(
  rankingArtifact: unknown,
  recommendationArtifact: unknown,
  reportArtifact: unknown,
): OptimizationStudy {
  const candidates: OptimizationCandidate[] = [];
  let safe_to_accept = false;
  let baseline_modified: boolean | null = null;
  const warnings: string[] = [];

  // ── Candidate ranking ──
  if (rankingArtifact && typeof rankingArtifact === "object") {
    const r = rankingArtifact as Record<string, unknown>;
    // Honesty: only an explicit boolean true is "safe to accept" — never coerce
    // truthy strings/numbers (e.g. the string "false") into an accept-safe state.
    safe_to_accept = r.safe_to_accept === true;
    baseline_modified = r.baseline_modified === true ? true : r.baseline_modified === false ? false : null;

    const rawCandidates = Array.isArray(r.candidates) ? r.candidates : [];
    for (const item of rawCandidates) {
      if (!item || typeof item !== "object") continue;
      const c = item as Record<string, unknown>;
      // Drop malformed rows rather than coercing a missing id to "" or an invalid
      // rank to 0 — those would sort to the top and produce bad accept drafts.
      if (typeof c.candidate_id !== "string" || c.candidate_id.length === 0) continue;
      if (typeof c.rank !== "number") continue;
      const feasibility = normalizeFeasibility(c.feasibility);
      const metrics = shapeMetrics(c.metrics);
      candidates.push({
        candidate_id: c.candidate_id,
        rank: c.rank,
        feasibility,
        score: typeof c.score === "number" ? c.score : null,
        confidence: normalizeConfidence(c.confidence),
        metrics,
        has_unknown_metrics: detectUnknownMetrics(metrics),
        constraint_violations: shapeStringArray(c.constraint_violations),
        objective_delta: shapeObjectiveDelta(c.objective_delta),
        reasons: shapeStringArray(c.reasons),
        metrics_missing: shapeStringArray(c.metrics_missing),
        recommendation: typeof c.recommendation === "string" ? c.recommendation : null,
        execution_status: typeof c.execution_status === "string" ? c.execution_status : null,
      });
    }

    // Honesty: warn when baseline was modified (should never happen for design-study v0).
    if (baseline_modified === true) {
      warnings.push("Baseline geometry was modified — this is unexpected for a design study.");
    }
  }

  // ── Recommendation ──
  let recommendation: OptimizationRecommendation | null = null;
  if (recommendationArtifact && typeof recommendationArtifact === "object") {
    const rec = recommendationArtifact as Record<string, unknown>;
    recommendation = {
      headline: typeof rec.headline === "string" ? rec.headline : null,
      reason_codes: Array.isArray(rec.reason_codes) ? rec.reason_codes.filter((s): s is string => typeof s === "string") : [],
      caveats: Array.isArray(rec.caveats) ? rec.caveats.filter((s): s is string => typeof s === "string") : [],
      advisory_only: rec.advisory_only !== false,
    };
  }

  // ── Report ──
  let report: OptimizationReport | null = null;
  let problem: OptimizationProblem | null = null;
  let ranking: OptimizationRanking | null = null;
  let acceptance: OptimizationAcceptance | null = null;

  if (reportArtifact && typeof reportArtifact === "object") {
    const rep = reportArtifact as Record<string, unknown>;
    report = {
      summary: typeof rep.summary === "string" ? rep.summary : null,
      variable_count: typeof rep.variable_count === "number" ? rep.variable_count : undefined,
      candidate_count: typeof rep.candidate_count === "number" ? rep.candidate_count : undefined,
      feasibility_summary: shapeFeasibilitySummary(rep.feasibility_summary),
      failed_candidates: shapeFailedCandidates(rep.failed_candidates),
      iteration_history: shapeIterationHistory(rep.iteration_history),
      missing_stages: shapeStringArray(rep.missing_stages),
    };

    const repProblem = rep.problem && typeof rep.problem === "object" ? (rep.problem as Record<string, unknown>) : null;
    if (repProblem) {
      problem = {
        objective: repProblem.objective ?? undefined,
        constraints: Array.isArray(repProblem.constraints) ? repProblem.constraints : undefined,
        variable_count: typeof repProblem.variable_count === "number" ? repProblem.variable_count : undefined,
      };
    }

    const repRanking = rep.ranking && typeof rep.ranking === "object" ? (rep.ranking as Record<string, unknown>) : null;
    if (repRanking) {
      ranking = {
        best_candidate_id: typeof repRanking.best_candidate_id === "string" ? repRanking.best_candidate_id : null,
        next_action: typeof repRanking.next_action === "string" ? repRanking.next_action : null,
      };
    }

    const repAcceptance = rep.acceptance && typeof rep.acceptance === "object" ? (rep.acceptance as Record<string, unknown>) : null;
    if (repAcceptance) {
      acceptance = {
        status: typeof repAcceptance.status === "string" ? repAcceptance.status : null,
        accepted_candidate_id: typeof repAcceptance.accepted_candidate_id === "string" ? repAcceptance.accepted_candidate_id : null,
      };
    }
  }

  const has_study = candidates.length > 0 || recommendation != null || report != null;

  return {
    has_study,
    candidates: candidates.sort((a, b) => a.rank - b.rank),
    recommendation,
    report,
    safe_to_accept,
    baseline_modified,
    warnings,
    problem,
    ranking,
    acceptance,
  };
}

function normalizeFeasibility(value: unknown): CandidateFeasibility {
  if (value === "feasible" || value === "infeasible" || value === "unknown" || value === "failed") {
    return value;
  }
  return "unknown";
}

function normalizeConfidence(value: unknown): "high" | "medium" | "low" | null {
  if (value === "high" || value === "medium" || value === "low") return value;
  return null;
}

function shapeMetrics(raw: unknown): Record<string, number | string | null> | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const out: Record<string, number | string | null> = {};
  for (const [key, val] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof val === "number" || typeof val === "string") {
      out[key] = val;
    } else if (val === null) {
      out[key] = null;
    } else {
      out[key] = String(val);
    }
  }
  return out;
}

function detectUnknownMetrics(metrics?: Record<string, number | string | null>): boolean {
  if (!metrics) return true;
  return Object.values(metrics).some((v) => v === null || v === undefined);
}

function shapeStringArray(raw: unknown): string[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  return raw.filter((s): s is string => typeof s === "string");
}

function shapeObjectiveDelta(raw: unknown): ObjectiveDelta | null {
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Record<string, unknown>;
  return {
    metric: typeof d.metric === "string" ? d.metric : null,
    candidate_value: typeof d.candidate_value === "number" ? d.candidate_value : null,
    baseline_value: typeof d.baseline_value === "number" ? d.baseline_value : null,
    delta_percent: typeof d.delta_percent === "number" ? d.delta_percent : null,
    delta_absolute: typeof d.delta_absolute === "number" ? d.delta_absolute : null,
    unit: typeof d.unit === "string" && d.unit ? d.unit : null,
  };
}

function shapeFeasibilitySummary(raw: unknown): Record<string, number> | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === "number") out[k] = v;
  }
  return Object.keys(out).length ? out : undefined;
}

function shapeFailedCandidates(raw: unknown): OptimizationReport["failed_candidates"] {
  if (!Array.isArray(raw)) return undefined;
  const out: NonNullable<OptimizationReport["failed_candidates"]> = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const c = item as Record<string, unknown>;
    if (typeof c.candidate_id !== "string") continue;
    out.push({
      candidate_id: c.candidate_id,
      execution_status: typeof c.execution_status === "string" ? c.execution_status : null,
      feasibility: typeof c.feasibility === "string" ? c.feasibility : null,
      reasons: shapeStringArray(c.reasons),
    });
  }
  return out.length ? out : undefined;
}

function shapeIterationHistory(raw: unknown): IterationHistoryEntry[] | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const hist = raw as Record<string, unknown>;
  const items = Array.isArray(hist.iterations) ? hist.iterations : Array.isArray(raw) ? raw : [];
  const out: IterationHistoryEntry[] = [];
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    const it = item as Record<string, unknown>;
    out.push({
      index: typeof it.index === "number" ? it.index : undefined,
      incumbent_candidate_id: typeof it.incumbent_candidate_id === "string" ? it.incumbent_candidate_id : null,
      incumbent_objective: typeof it.incumbent_objective === "number" ? it.incumbent_objective : null,
      feasible: typeof it.feasible === "boolean" ? it.feasible : null,
      evaluations_total: typeof it.evaluations_total === "number" ? it.evaluations_total : null,
      convergence_verdict: typeof it.convergence_verdict === "string" ? it.convergence_verdict : null,
    });
  }
  return out.length ? out : undefined;
}

/**
 * Group candidates by feasibility for display. Order: feasible → unknown → infeasible → failed.
 * Empty groups are omitted. Pure and total.
 */
export function groupCandidatesByFeasibility(
  candidates: OptimizationCandidate[],
): Array<{ feasibility: CandidateFeasibility; candidates: OptimizationCandidate[] }> {
  const buckets = new Map<CandidateFeasibility, OptimizationCandidate[]>();
  for (const c of candidates) {
    const list = buckets.get(c.feasibility) ?? [];
    list.push(c);
    buckets.set(c.feasibility, list);
  }
  const groups: Array<{ feasibility: CandidateFeasibility; candidates: OptimizationCandidate[] }> = [];
  for (const feasibility of FEASIBILITY_ORDER) {
    const list = buckets.get(feasibility);
    if (list && list.length) groups.push({ feasibility, candidates: list });
  }
  return groups;
}

/**
 * A composer-ready accept draft for a candidate. The panel uses this to hand the
 * user a pre-filled command that flows through the existing approval-gated path.
 */
export function acceptDraftForCandidate(candidateId: string): string {
  return `/design-study accept candidate ${candidateId}`;
}

/**
 * Format a metric value for display. Numbers get 4-decimal rounding; null shows as "—".
 */
export function formatMetricValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (!Number.isFinite(value)) return "—";
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
}

/**
 * True when the optimization study is worth surfacing.
 */
export function isStudyMeaningful(study: OptimizationStudy | null): boolean {
  return !!study && study.has_study;
}
