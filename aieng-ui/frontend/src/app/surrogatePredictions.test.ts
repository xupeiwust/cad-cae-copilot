import { expect, test } from "vitest";

import {
  formatPredictionWithBand,
  shapeSurrogateProposals,
} from "./surrogatePredictions";

const ARTIFACT = {
  status: "ok",
  proposals: [
    {
      proposal_rank: 1,
      variable_changes: [{ variable_id: "wall_thickness", new_value: 4.5 }],
      surrogate_prediction: {
        predicted_score: 0.62,
        uncertainty_std: 0.08,
        predicted_score_band: [0.54, 0.7],
        confidence: "medium",
      },
    },
  ],
  validation: {
    method: "leave_one_out_cv",
    n_points: 4,
    has_evaluated_points: true,
    rmse: 0.05,
    mae: 0.04,
    max_abs_error: 0.09,
    relative_rmse: 0.07,
    pearson_r: 0.96,
    note: "advisory",
  },
};

test("shapes proposals with their uncertainty band", () => {
  const out = shapeSurrogateProposals(ARTIFACT);
  expect(out.hasProposals).toBe(true);
  expect(out.predictions).toHaveLength(1);
  const p = out.predictions[0];
  expect(p.predictedScore).toBe(0.62);
  expect(p.band).toEqual([0.54, 0.7]);
  expect(p.uncertaintyStd).toBe(0.08);
  expect(formatPredictionWithBand(p)).toBe("0.620 ± 0.080");
});

test("withholds a prediction that has no usable band (never rendered bare)", () => {
  const out = shapeSurrogateProposals({
    proposals: [
      { proposal_rank: 1, surrogate_prediction: { predicted_score: 0.5 } }, // no std, no band
      {
        proposal_rank: 2,
        surrogate_prediction: { predicted_score: 0.3, uncertainty_std: 0.1 },
      },
    ],
  });
  // first dropped (no band), second derives band from std
  expect(out.withheld).toBe(1);
  expect(out.predictions).toHaveLength(1);
  expect(out.predictions[0].band[0]).toBeCloseTo(0.2, 6);
  expect(out.predictions[0].band[1]).toBeCloseTo(0.4, 6);
});

test("surfaces leave-one-out validation only when evaluated points exist", () => {
  expect(shapeSurrogateProposals(ARTIFACT).validation?.rmse).toBe(0.05);
  const noVal = shapeSurrogateProposals({
    proposals: [],
    validation: { method: "leave_one_out_cv", has_evaluated_points: false },
  });
  expect(noVal.validation).toBeNull();
});

test("empty / malformed artifact yields no proposals", () => {
  expect(shapeSurrogateProposals(null).hasProposals).toBe(false);
  expect(shapeSurrogateProposals({}).hasProposals).toBe(false);
  expect(shapeSurrogateProposals(42).predictions).toEqual([]);
});
