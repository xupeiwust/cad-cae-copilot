/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ConvergenceChart } from "./ConvergenceChart";
import { type OptimizationConvergence } from "../app/optimizationConvergence";

function makeConvergence(iterations: Array<{ index: number; objective: number | null; feasible: boolean; safe?: boolean }>): OptimizationConvergence {
  return {
    has_data: iterations.length > 0,
    iterations: iterations.map((it) => ({
      index: it.index,
      incumbent_candidate_id: `c${it.index}`,
      incumbent_objective: it.objective,
      feasible: it.feasible,
      evaluations_total: it.index * 4,
      failures_this_round: 0,
      convergence_verdict: it.index === iterations.length ? "converged" : "continue",
      safe_to_accept: it.safe ?? false,
    })),
    latest_verdict: {
      converged: true,
      verdict: "converged",
      reason_codes: ["converged_objective_delta"],
      iteration_count: iterations.length,
    },
    config_used: { max_iterations: 20 },
  };
}

describe("ConvergenceChart", () => {
  it("renders the chart title and verdict badge", () => {
    const convergence = makeConvergence([
      { index: 1, objective: 1.0, feasible: true },
      { index: 2, objective: 0.9, feasible: true },
      { index: 3, objective: 0.85, feasible: true },
    ]);

    render(<ConvergenceChart convergence={convergence} />);

    expect(screen.getByRole("img", { name: "Optimization convergence" })).not.toBeNull();
    expect(screen.getByText("Converged")).not.toBeNull();
  });

  it("renders a point for each iteration", () => {
    const convergence = makeConvergence([
      { index: 1, objective: 1.0, feasible: true },
      { index: 2, objective: 0.9, feasible: false },
      { index: 3, objective: null, feasible: false },
    ]);

    const { container } = render(<ConvergenceChart convergence={convergence} />);
    const circles = container.querySelectorAll("circle.convergence-point");
    expect(circles).toHaveLength(2);
    expect(container.querySelectorAll("circle.convergence-point-feasible")).toHaveLength(1);
    expect(container.querySelectorAll("circle.convergence-point-infeasible")).toHaveLength(1);
  });

  it("shows accept-ready legend when any iteration is safe to accept", () => {
    const convergence = makeConvergence([
      { index: 1, objective: 1.0, feasible: true },
      { index: 2, objective: 0.9, feasible: true, safe: true },
    ]);

    render(<ConvergenceChart convergence={convergence} />);
    expect(screen.getByText("✓ accept-ready reached")).not.toBeNull();
  });

  it("uses a custom accessible title when provided", () => {
    const convergence = makeConvergence([{ index: 1, objective: 1.0, feasible: true }]);
    render(<ConvergenceChart convergence={convergence} title="Mass convergence" />);
    expect(screen.getByRole("img", { name: "Mass convergence" })).not.toBeNull();
  });
});
