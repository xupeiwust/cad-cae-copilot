/**
 * Pure shaping for the Optimization panel. No React, no I/O.
 *
 * Turns design-study artifacts (candidate ranking, recommendation, report)
 * into a read-only display model. The panel itself never mutates geometry;
 * actions draft into the composer and flow through the approval-gated path.
 */

export type CandidateFeasibility = "feasible" | "infeasible" | "unknown" | "failed";

export type OptimizationCandidate = {
  candidate_id: string;
  rank: number;
  feasibility: CandidateFeasibility;
  score?: number | null;
  confidence?: "high" | "medium" | "low" | null;
  metrics?: Record<string, number | string | null>;
  /** Honesty signal: true when metrics are incomplete or proxy-based. */
  has_unknown_metrics?: boolean;
};

export type OptimizationRecommendation = {
  headline: string | null;
  reason_codes: string[];
  caveats: string[];
  /** Honesty signal: never claims the recommendation is a final decision. */
  advisory_only: boolean;
};

export type OptimizationReport = {
  summary?: string | null;
  variable_count?: number;
  candidate_count?: number;
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
    safe_to_accept = Boolean(r.safe_to_accept);
    baseline_modified = r.baseline_modified === true ? true : r.baseline_modified === false ? false : null;

    const rawCandidates = Array.isArray(r.candidates) ? r.candidates : [];
    for (const item of rawCandidates) {
      if (!item || typeof item !== "object") continue;
      const c = item as Record<string, unknown>;
      const feasibility = normalizeFeasibility(c.feasibility);
      const metrics = shapeMetrics(c.metrics);
      candidates.push({
        candidate_id: typeof c.candidate_id === "string" ? c.candidate_id : String(c.candidate_id ?? ""),
        rank: typeof c.rank === "number" ? c.rank : 0,
        feasibility,
        score: typeof c.score === "number" ? c.score : null,
        confidence: normalizeConfidence(c.confidence),
        metrics,
        has_unknown_metrics: detectUnknownMetrics(metrics),
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
  if (reportArtifact && typeof reportArtifact === "object") {
    const rep = reportArtifact as Record<string, unknown>;
    report = {
      summary: typeof rep.summary === "string" ? rep.summary : null,
      variable_count: typeof rep.variable_count === "number" ? rep.variable_count : undefined,
      candidate_count: typeof rep.candidate_count === "number" ? rep.candidate_count : undefined,
    };
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
