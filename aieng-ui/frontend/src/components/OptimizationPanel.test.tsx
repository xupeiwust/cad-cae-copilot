/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { OptimizationPanel } from "./OptimizationPanel";
import { type OptimizationConvergence } from "../app/optimizationConvergence";

const baseStudy = {
  has_study: true,
  candidates: [
    {
      candidate_id: "c1",
      rank: 1,
      feasibility: "feasible" as const,
      score: 0.9,
      confidence: "high" as const,
      metrics: { mass: 1.2 },
      has_unknown_metrics: false,
    },
  ],
  recommendation: null,
  report: null,
  safe_to_accept: true,
  baseline_modified: false,
  warnings: [],
};

function makeConvergence(iterations: Array<{ index: number; objective: number | null; feasible: boolean }>): OptimizationConvergence {
  return {
    has_data: iterations.length > 0,
    iterations: iterations.map((it) => ({
      index: it.index,
      incumbent_candidate_id: `c${it.index}`,
      incumbent_objective: it.objective,
      feasible: it.feasible,
      evaluations_total: it.index * 4,
      failures_this_round: 0,
      convergence_verdict: "continue",
      safe_to_accept: false,
    })),
    latest_verdict: {
      converged: false,
      verdict: "continue",
      reason_codes: [],
      iteration_count: iterations.length,
    },
    config_used: { max_iterations: 20 },
  };
}

describe("OptimizationPanel", () => {
  it("renders nothing when study is null", () => {
    const { container } = render(<OptimizationPanel study={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when study is not meaningful", () => {
    const { container } = render(<OptimizationPanel study={{ ...baseStudy, has_study: false }} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders candidate ranking and accept button", () => {
    render(<OptimizationPanel study={baseStudy} onUseInChat={vi.fn()} />);
    expect(screen.getByText("Optimization study")).not.toBeNull();
    expect(screen.getByText("c1")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Accept" })).not.toBeNull();
  });

  it("renders the convergence chart when convergence data is provided", () => {
    const convergence = makeConvergence([
      { index: 1, objective: 1.0, feasible: true },
      { index: 2, objective: 0.9, feasible: true },
    ]);

    render(<OptimizationPanel study={baseStudy} convergence={convergence} />);
    expect(screen.getByRole("img", { name: "Incumbent objective over iterations" })).not.toBeNull();
  });

  it("omits the convergence chart when convergence has no iterations", () => {
    const convergence: OptimizationConvergence = {
      has_data: false,
      iterations: [],
      latest_verdict: null,
      config_used: null,
    };

    const { container } = render(<OptimizationPanel study={baseStudy} convergence={convergence} />);
    expect(container.querySelector('[role="img"]')).toBeNull();
  });
});
