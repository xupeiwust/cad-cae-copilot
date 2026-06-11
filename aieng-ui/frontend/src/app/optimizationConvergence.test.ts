import { describe, expect, it } from "vitest";

import {
  buildConvergenceSeries,
  formatIterationObjective,
  isConvergenceMeaningful,
  shapeOptimizationConvergence,
  verdictLabel,
} from "./optimizationConvergence";

function makeArtifact(iterations: unknown[]) {
  return {
    format: "aieng.optimization_iterations",
    format_version: "1",
    schema_version: "0.1",
    iterations,
    latest_verdict: {
      converged: false,
      verdict: "continue",
      reason_codes: [],
      iteration_count: iterations.length,
    },
    config_used: { max_iterations: 20 },
    provenance: {},
  };
}

describe("shapeOptimizationConvergence", () => {
  it("returns null for non-objects", () => {
    expect(shapeOptimizationConvergence(null)).toBeNull();
    expect(shapeOptimizationConvergence("bad")).toBeNull();
    expect(shapeOptimizationConvergence(42)).toBeNull();
  });

  it("returns null when there is no meaningful data", () => {
    expect(shapeOptimizationConvergence({})).toBeNull();
    expect(shapeOptimizationConvergence({ iterations: [] })).toBeNull();
  });

  it("shapes a complete iteration history", () => {
    const artifact = makeArtifact([
      {
        index: 1,
        incumbent_candidate_id: "c1",
        incumbent_objective: 1.23456,
        feasible: true,
        evaluations_total: 4,
        failures_this_round: 0,
        convergence_verdict: "continue",
        safe_to_accept: false,
      },
      {
        index: 2,
        incumbent_candidate_id: "c2",
        incumbent_objective: 0.98765,
        feasible: true,
        evaluations_total: 8,
        failures_this_round: 0,
        convergence_verdict: "converged",
        safe_to_accept: true,
      },
    ]);

    const result = shapeOptimizationConvergence(artifact);
    expect(result).not.toBeNull();
    expect(result!.iterations).toHaveLength(2);
    expect(result!.iterations[0]).toMatchObject({
      index: 1,
      incumbent_candidate_id: "c1",
      incumbent_objective: 1.23456,
      feasible: true,
      evaluations_total: 4,
      convergence_verdict: "continue",
      safe_to_accept: false,
    });
    expect(result!.iterations[1].incumbent_candidate_id).toBe("c2");
    expect(result!.latest_verdict).toMatchObject({
      converged: false,
      verdict: "continue",
      iteration_count: 2,
    });
    expect(result!.config_used).toEqual({ max_iterations: 20 });
  });

  it("drops malformed iterations and keeps valid ones", () => {
    const artifact = makeArtifact([null, "bad", { index: 1, incumbent_objective: 0.5, feasible: true }]);
    const result = shapeOptimizationConvergence(artifact);
    expect(result!.iterations).toHaveLength(1);
    expect(result!.iterations[0].index).toBe(1);
  });

  it("sorts iterations by index", () => {
    const artifact = makeArtifact([
      { index: 3, incumbent_objective: 0.3, feasible: true },
      { index: 1, incumbent_objective: 0.1, feasible: true },
      { index: 2, incumbent_objective: 0.2, feasible: true },
    ]);
    const result = shapeOptimizationConvergence(artifact);
    expect(result!.iterations.map((it) => it.index)).toEqual([1, 2, 3]);
  });

  it("treats only explicit true as feasible / safe_to_accept", () => {
    const artifact = makeArtifact([
      { index: 1, incumbent_objective: 0.5, feasible: "true", safe_to_accept: 1 },
    ]);
    const result = shapeOptimizationConvergence(artifact);
    expect(result!.iterations[0].feasible).toBe(false);
    expect(result!.iterations[0].safe_to_accept).toBe(false);
  });

  it("coerces invalid objectives to null", () => {
    const artifact = makeArtifact([
      { index: 1, incumbent_objective: NaN, feasible: true },
      { index: 2, incumbent_objective: "0.5", feasible: true },
      { index: 3, incumbent_objective: Infinity, feasible: true },
    ]);
    const result = shapeOptimizationConvergence(artifact);
    expect(result!.iterations.map((it) => it.incumbent_objective)).toEqual([null, null, null]);
  });

  it("normalizes a missing or invalid verdict to continue", () => {
    const artifact = makeArtifact([
      { index: 1, incumbent_objective: 0.5, feasible: true, convergence_verdict: undefined },
      { index: 2, incumbent_objective: 0.4, feasible: true, convergence_verdict: "" },
    ]);
    const result = shapeOptimizationConvergence(artifact);
    expect(result!.iterations[0].convergence_verdict).toBe("continue");
    expect(result!.iterations[1].convergence_verdict).toBe("continue");
  });
});

describe("buildConvergenceSeries", () => {
  it("maps iterations to chart points preserving null objectives", () => {
    const convergence = shapeOptimizationConvergence(
      makeArtifact([
        { index: 1, incumbent_objective: 1.0, feasible: true },
        { index: 2, incumbent_objective: null, feasible: false },
        { index: 3, incumbent_objective: 0.8, feasible: true },
      ]),
    )!;

    expect(buildConvergenceSeries(convergence)).toEqual([
      { iteration: 1, objective: 1.0, feasible: true },
      { iteration: 2, objective: null, feasible: false },
      { iteration: 3, objective: 0.8, feasible: true },
    ]);
  });
});

describe("verdictLabel", () => {
  it("returns a known label for built-in verdicts", () => {
    expect(verdictLabel("converged")).toBe("Converged");
    expect(verdictLabel("stop_budget")).toBe("Budget exhausted");
  });

  it("falls back to the raw verdict for unknown values", () => {
    expect(verdictLabel("custom_stop")).toBe("custom_stop");
  });
});

describe("formatIterationObjective", () => {
  it("rounds non-integer numbers to four decimals", () => {
    expect(formatIterationObjective(1.23456)).toBe("1.2346");
  });

  it("renders integers as-is", () => {
    expect(formatIterationObjective(42)).toBe("42");
  });

  it("shows em-dash for null/undefined/non-finite", () => {
    expect(formatIterationObjective(null)).toBe("—");
    expect(formatIterationObjective(undefined)).toBe("—");
    expect(formatIterationObjective(NaN)).toBe("—");
  });
});

describe("isConvergenceMeaningful", () => {
  it("returns true only when iterations exist", () => {
    const convergence = shapeOptimizationConvergence(makeArtifact([{ index: 1, incumbent_objective: 1.0, feasible: true }]));
    expect(isConvergenceMeaningful(convergence)).toBe(true);
  });

  it("returns false for null or empty convergence", () => {
    expect(isConvergenceMeaningful(null)).toBe(false);
    expect(isConvergenceMeaningful(shapeOptimizationConvergence({ iterations: [] }))).toBe(false);
  });
});
