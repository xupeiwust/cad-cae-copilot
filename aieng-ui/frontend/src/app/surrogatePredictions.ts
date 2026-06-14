/**
 * Pure shaping for surrogate proposals (#219). No React, no I/O.
 *
 * Trust discipline (borrowed from PhysicsX / SimScale): a surrogate-predicted
 * number is NEVER surfaced without its uncertainty envelope. This shaper turns
 * the backend `design_study_surrogate_proposals.json` artifact into a display
 * model where every rendered prediction carries a band; any prediction missing
 * a usable band is *withheld* (counted, not shown as a bare number) rather than
 * presented as if it were exact. It also surfaces the leave-one-out
 * surrogate-vs-evaluated error band when the backend computed one.
 */

export type SurrogateBand = [number, number];

export type SurrogatePrediction = {
  rank: number;
  variableChanges: { variableId: string; value: number }[];
  predictedScore: number;
  uncertaintyStd: number;
  band: SurrogateBand;
  confidence: string | null;
};

export type SurrogateValidation = {
  method: string;
  nPoints: number;
  rmse: number | null;
  mae: number | null;
  maxAbsError: number | null;
  relativeRmse: number | null;
  pearsonR: number | null;
  note: string | null;
};

export type SurrogateProposals = {
  hasProposals: boolean;
  status: string | null;
  predictions: SurrogatePrediction[];
  /** Present only when the backend cross-validated against evaluated points. */
  validation: SurrogateValidation | null;
  /** Predictions dropped for lacking a usable uncertainty band (never shown bare). */
  withheld: number;
  reasonCodes: string[];
};

const EMPTY: SurrogateProposals = {
  hasProposals: false,
  status: null,
  predictions: [],
  validation: null,
  withheld: 0,
  reasonCodes: [],
};

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Derive the [lo, hi] band for a prediction, or null when no usable envelope
 * exists. Prefers the explicit `predicted_score_band`; falls back to
 * mean ± uncertainty_std. A prediction with neither is NOT renderable.
 */
function bandFor(pred: Record<string, unknown>, score: number): SurrogateBand | null {
  const raw = pred.predicted_score_band;
  if (Array.isArray(raw) && raw.length === 2) {
    const lo = num(raw[0]);
    const hi = num(raw[1]);
    if (lo !== null && hi !== null) return [Math.min(lo, hi), Math.max(lo, hi)];
  }
  const std = num(pred.uncertainty_std);
  if (std !== null && std >= 0) return [score - std, score + std];
  return null;
}

function shapeValidation(raw: unknown): SurrogateValidation | null {
  if (!raw || typeof raw !== "object") return null;
  const v = raw as Record<string, unknown>;
  if (v.has_evaluated_points !== true) return null; // honest: only show a real band
  return {
    method: str(v.method) ?? "leave_one_out_cv",
    nPoints: num(v.n_points) ?? 0,
    rmse: num(v.rmse),
    mae: num(v.mae),
    maxAbsError: num(v.max_abs_error),
    relativeRmse: num(v.relative_rmse),
    pearsonR: num(v.pearson_r),
    note: str(v.note),
  };
}

/** Shape the raw artifact into the display model. Pure and total. */
export function shapeSurrogateProposals(artifact: unknown): SurrogateProposals {
  if (!artifact || typeof artifact !== "object") return EMPTY;
  const a = artifact as Record<string, unknown>;

  const reasonCodes = Array.isArray(a.reason_codes)
    ? a.reason_codes.filter((c): c is string => typeof c === "string")
    : [];
  const rawProposals = Array.isArray(a.proposals) ? a.proposals : [];

  const predictions: SurrogatePrediction[] = [];
  let withheld = 0;

  rawProposals.forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const p = item as Record<string, unknown>;
    const pred = (p.surrogate_prediction ?? {}) as Record<string, unknown>;
    const score = num(pred.predicted_score);
    if (score === null) {
      withheld += 1;
      return;
    }
    const band = bandFor(pred, score);
    if (band === null) {
      // Discipline: never render a predicted number without its band.
      withheld += 1;
      return;
    }
    const changes = Array.isArray(p.variable_changes) ? p.variable_changes : [];
    predictions.push({
      rank: num(p.proposal_rank) ?? index + 1,
      variableChanges: changes
        .filter((c): c is Record<string, unknown> => !!c && typeof c === "object")
        .map((c) => ({ variableId: str(c.variable_id) ?? "?", value: num(c.new_value) ?? 0 })),
      predictedScore: score,
      uncertaintyStd: num(pred.uncertainty_std) ?? (band[1] - band[0]) / 2,
      band,
      confidence: str(pred.confidence),
    });
  });

  return {
    hasProposals: predictions.length > 0,
    status: str(a.status),
    predictions,
    validation: shapeValidation(a.validation),
    withheld,
    reasonCodes,
  };
}

/** Format a predicted score with its ±band, e.g. "0.62 ± 0.08". Pure. */
export function formatPredictionWithBand(pred: SurrogatePrediction, digits = 3): string {
  return `${pred.predictedScore.toFixed(digits)} ± ${pred.uncertaintyStd.toFixed(digits)}`;
}
