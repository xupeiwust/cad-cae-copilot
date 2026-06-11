import { describe, expect, it } from "vitest";

import {
  acceptDraftForCandidate,
  formatMetricValue,
  groupCandidatesByFeasibility,
  isStudyMeaningful,
  shapeOptimizationStudy,
  type OptimizationCandidate,
} from "./optimizationStudy";

describe("shapeOptimizationStudy", () => {
  it("returns empty study when all artifacts are null", () => {
    const result = shapeOptimizationStudy(null, null, null);
    expect(result.has_study).toBe(false);
    expect(result.candidates).toEqual([]);
    expect(result.recommendation).toBeNull();
    expect(result.report).toBeNull();
    expect(result.safe_to_accept).toBe(false);
    expect(result.baseline_modified).toBeNull();
    expect(result.warnings).toEqual([]);
  });

  it("shapes candidate ranking with all fields", () => {
    const ranking = {
      candidates: [
        {
          candidate_id: "c1",
          rank: 1,
          feasibility: "feasible",
          score: 0.85,
          confidence: "high",
          metrics: { mass: 1.2, stress: 150 },
        },
      ],
      safe_to_accept: true,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);

    expect(result.has_study).toBe(true);
    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]).toMatchObject({
      candidate_id: "c1",
      rank: 1,
      feasibility: "feasible",
      score: 0.85,
      confidence: "high",
    });
    expect(result.safe_to_accept).toBe(true);
    expect(result.baseline_modified).toBe(false);
    expect(result.warnings).toEqual([]);
  });

  it("flags unknown metrics when a metric is null", () => {
    const ranking = {
      candidates: [
        {
          candidate_id: "c1",
          rank: 1,
          feasibility: "feasible",
          metrics: { mass: 1.2, stress: null },
        },
      ],
      safe_to_accept: false,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates[0].has_unknown_metrics).toBe(true);
  });

  it("warns when baseline was modified", () => {
    const ranking = {
      candidates: [],
      safe_to_accept: false,
      baseline_modified: true,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.warnings).toContain("Baseline geometry was modified — this is unexpected for a design study.");
  });

  it("shapes recommendation with advisory_only defaulting to true", () => {
    const recommendation = {
      headline: "Reduce wall thickness",
      reason_codes: ["lower_mass", "stress_ok"],
      caveats: ["check_buckling"],
    };

    const result = shapeOptimizationStudy(null, recommendation, null);
    expect(result.recommendation).toMatchObject({
      headline: "Reduce wall thickness",
      reason_codes: ["lower_mass", "stress_ok"],
      caveats: ["check_buckling"],
      advisory_only: true,
    });
  });

  it("shapes report summary", () => {
    const report = { summary: "All candidates evaluated", variable_count: 3, candidate_count: 5 };
    const result = shapeOptimizationStudy(null, null, report);
    expect(result.report).toMatchObject({
      summary: "All candidates evaluated",
      variable_count: 3,
      candidate_count: 5,
    });
  });

  it("shapes deep candidate fields from ranking", () => {
    const ranking = {
      candidates: [
        {
          candidate_id: "c1",
          rank: 1,
          feasibility: "infeasible",
          score: -0.5,
          confidence: "low",
          constraint_violations: ["max_stress 200 > limit 150"],
          objective_delta: { metric: "mass", candidate_value: 1.2, baseline_value: 1.5, delta_percent: -20, delta_absolute: -0.3 },
          reasons: ["constraint violated"],
          metrics_missing: ["max_deflection"],
          recommendation: "reject_candidate",
          execution_status: "completed",
        },
      ],
      safe_to_accept: false,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    const c = result.candidates[0];
    expect(c.constraint_violations).toEqual(["max_stress 200 > limit 150"]);
    expect(c.objective_delta).toMatchObject({ metric: "mass", delta_percent: -20 });
    expect(c.reasons).toEqual(["constraint violated"]);
    expect(c.metrics_missing).toEqual(["max_deflection"]);
    expect(c.recommendation).toBe("reject_candidate");
    expect(c.execution_status).toBe("completed");
  });

  it("shapes deep report fields (feasibility summary, failed candidates, iteration history, missing stages)", () => {
    const report = {
      summary: "Study complete",
      feasibility_summary: { feasible: 2, infeasible: 1 },
      failed_candidates: [
        { candidate_id: "c2", execution_status: "compile_failed", feasibility: "failed", reasons: ["compile error"] },
      ],
      iteration_history: {
        iterations: [
          { index: 0, incumbent_candidate_id: "c1", incumbent_objective: 1.2, feasible: true, evaluations_total: 3, convergence_verdict: "continue" },
        ],
      },
      missing_stages: ["acceptance"],
      problem: { objective: { metric: "mass" }, constraints: [{ type: "max_stress" }], variable_count: 2 },
      ranking: { best_candidate_id: "c1", next_action: "accept_candidate" },
      acceptance: { status: "pending", accepted_candidate_id: null },
    };

    const result = shapeOptimizationStudy(null, null, report);
    expect(result.report?.feasibility_summary).toEqual({ feasible: 2, infeasible: 1 });
    expect(result.report?.failed_candidates).toHaveLength(1);
    expect(result.report?.failed_candidates?.[0].candidate_id).toBe("c2");
    expect(result.report?.iteration_history).toHaveLength(1);
    expect(result.report?.iteration_history?.[0].convergence_verdict).toBe("continue");
    expect(result.report?.missing_stages).toEqual(["acceptance"]);
    expect(result.problem).toMatchObject({ variable_count: 2 });
    expect(result.ranking).toMatchObject({ best_candidate_id: "c1", next_action: "accept_candidate" });
    expect(result.acceptance).toMatchObject({ status: "pending" });
  });

  it("tolerates malformed deep fields without crashing", () => {
    const ranking = {
      candidates: [
        {
          candidate_id: "c1",
          rank: 1,
          feasibility: "feasible",
          constraint_violations: ["ok", 123, null],
          objective_delta: "not-an-object",
          reasons: ["ok", 456],
          metrics_missing: [null, "mass"],
          recommendation: 42,
          execution_status: true,
        },
      ],
      safe_to_accept: false,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    const c = result.candidates[0];
    expect(c.constraint_violations).toEqual(["ok"]);
    expect(c.objective_delta).toBeNull();
    expect(c.reasons).toEqual(["ok"]);
    expect(c.metrics_missing).toEqual(["mass"]);
    expect(c.recommendation).toBeNull();
    expect(c.execution_status).toBeNull();
  });

  it("ignores malformed candidates gracefully", () => {
    const ranking = {
      candidates: [null, "bad", { candidate_id: "c1", rank: 1, feasibility: "feasible" }],
      safe_to_accept: false,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0].candidate_id).toBe("c1");
  });

  it("drops candidates with no string id or non-numeric rank (no coercion)", () => {
    const ranking = {
      candidates: [
        { rank: 1, feasibility: "feasible" }, // missing id
        { candidate_id: "", rank: 1, feasibility: "feasible" }, // empty id
        { candidate_id: "c2", feasibility: "feasible" }, // missing rank
        { candidate_id: "c3", rank: 2, feasibility: "feasible" }, // valid
      ],
      safe_to_accept: false,
      baseline_modified: false,
    };
    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates.map((c) => c.candidate_id)).toEqual(["c3"]);
  });

  it("treats only an explicit boolean true as safe_to_accept", () => {
    // a stray truthy string must NOT read as accept-safe
    const ranking = { candidates: [], safe_to_accept: "false", baseline_modified: false };
    expect(shapeOptimizationStudy(ranking, null, null).safe_to_accept).toBe(false);
    const ranking2 = { candidates: [], safe_to_accept: true, baseline_modified: false };
    expect(shapeOptimizationStudy(ranking2, null, null).safe_to_accept).toBe(true);
  });

  it("normalizes unknown feasibility values", () => {
    const ranking = {
      candidates: [{ candidate_id: "c1", rank: 1, feasibility: "garbage" }],
      safe_to_accept: false,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates[0].feasibility).toBe("unknown");
  });

  it("sorts candidates by rank", () => {
    const ranking = {
      candidates: [
        { candidate_id: "c3", rank: 3, feasibility: "feasible" },
        { candidate_id: "c1", rank: 1, feasibility: "feasible" },
        { candidate_id: "c2", rank: 2, feasibility: "feasible" },
      ],
      safe_to_accept: false,
      baseline_modified: false,
    };

    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates.map((c) => c.candidate_id)).toEqual(["c1", "c2", "c3"]);
  });
});

describe("groupCandidatesByFeasibility", () => {
  it("groups candidates in display order", () => {
    const candidates: OptimizationCandidate[] = [
      { candidate_id: "c1", rank: 1, feasibility: "failed" },
      { candidate_id: "c2", rank: 2, feasibility: "feasible" },
      { candidate_id: "c3", rank: 3, feasibility: "unknown" },
      { candidate_id: "c4", rank: 4, feasibility: "infeasible" },
      { candidate_id: "c5", rank: 5, feasibility: "feasible" },
    ];

    const groups = groupCandidatesByFeasibility(candidates);
    expect(groups.map((g) => g.feasibility)).toEqual(["feasible", "unknown", "infeasible", "failed"]);
    expect(groups[0].candidates).toHaveLength(2);
    expect(groups[3].candidates).toHaveLength(1);
  });

  it("omits empty groups", () => {
    const candidates: OptimizationCandidate[] = [
      { candidate_id: "c1", rank: 1, feasibility: "feasible" },
    ];

    const groups = groupCandidatesByFeasibility(candidates);
    expect(groups).toHaveLength(1);
    expect(groups[0].feasibility).toBe("feasible");
  });
});

describe("acceptDraftForCandidate", () => {
  it("returns a composer-ready draft", () => {
    expect(acceptDraftForCandidate("candidate_42")).toBe("/design-study accept candidate candidate_42");
  });
});

describe("formatMetricValue", () => {
  it("formats numbers compactly", () => {
    expect(formatMetricValue(1.23456)).toBe("1.2346");
    expect(formatMetricValue(42)).toBe("42");
  });

  it("shows em-dash for null/undefined", () => {
    expect(formatMetricValue(null)).toBe("—");
    expect(formatMetricValue(undefined)).toBe("—");
  });

  it("returns strings as-is", () => {
    expect(formatMetricValue("hello")).toBe("hello");
  });
});

describe("isStudyMeaningful", () => {
  it("returns true when study has content", () => {
    expect(isStudyMeaningful({ has_study: true, candidates: [], recommendation: null, report: null, safe_to_accept: false, baseline_modified: null, warnings: [] })).toBe(true);
  });

  it("returns false when study is null", () => {
    expect(isStudyMeaningful(null)).toBe(false);
  });

  it("returns false when has_study is false", () => {
    expect(isStudyMeaningful({ has_study: false, candidates: [], recommendation: null, report: null, safe_to_accept: false, baseline_modified: null, warnings: [] })).toBe(false);
  });
});

describe("shapeOptimizationStudy — unknown metrics detection", () => {
  it("marks candidate with null metric as has_unknown_metrics", () => {
    const ranking = {
      candidates: [{ candidate_id: "c1", rank: 1, feasibility: "feasible", metrics: { a: 1, b: null } }],
      safe_to_accept: false,
      baseline_modified: false,
    };
    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates[0].has_unknown_metrics).toBe(true);
  });

  it("marks candidate with all present metrics as not unknown", () => {
    const ranking = {
      candidates: [{ candidate_id: "c1", rank: 1, feasibility: "feasible", metrics: { a: 1, b: 2 } }],
      safe_to_accept: false,
      baseline_modified: false,
    };
    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates[0].has_unknown_metrics).toBe(false);
  });

  it("marks candidate with no metrics as has_unknown_metrics", () => {
    const ranking = {
      candidates: [{ candidate_id: "c1", rank: 1, feasibility: "feasible" }],
      safe_to_accept: false,
      baseline_modified: false,
    };
    const result = shapeOptimizationStudy(ranking, null, null);
    expect(result.candidates[0].has_unknown_metrics).toBe(true);
  });
});
