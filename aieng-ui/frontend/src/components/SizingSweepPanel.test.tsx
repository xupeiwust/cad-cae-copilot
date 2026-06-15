/**
 * @vitest-environment happy-dom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { SizingSweepPanel } from "./SizingSweepPanel";
import type { SizingSweepReport } from "../types";

afterEach(cleanup);

const makeReport = (): SizingSweepReport => ({
  status: "ok",
  tool: "opt.sizing_sweep",
  parameter_name: "thickness",
  objective: "min_mass",
  objective_metric: "mass",
  variants: [
    {
      value: 2.0,
      metrics: { mass: 1.0, max_von_mises_stress: 260 },
      solver_executed: true,
      status: "infeasible",
      rank: 2,
      objective_value: 1.0,
    },
    {
      value: 3.0,
      metrics: { mass: 1.5, max_von_mises_stress: 180 },
      solver_executed: true,
      status: "feasible",
      rank: 1,
      objective_value: 1.5,
    },
  ],
  variant_count: 2,
  feasible_count: 1,
  recommended: {
    value: 3.0,
    metrics: { mass: 1.5, max_von_mises_stress: 180 },
    solver_executed: true,
    status: "feasible",
    rank: 1,
    objective_value: 1.5,
  },
  recommendation_reason: "value=3.0 minimizes mass",
  safe_to_apply: true,
});

describe("SizingSweepPanel", () => {
  it("renders nothing without a meaningful report", () => {
    const { container } = render(<SizingSweepPanel report={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the variant table and winner button", () => {
    const onUseInChat = vi.fn();
    render(<SizingSweepPanel report={makeReport()} onUseInChat={onUseInChat} />);
    expect(screen.getByText("Sizing sweep")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Apply winner" })).toBeTruthy();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 variants
  });

  it("drafts the winner on button click", () => {
    const onUseInChat = vi.fn();
    render(<SizingSweepPanel report={makeReport()} onUseInChat={onUseInChat} />);
    fireEvent.click(screen.getByRole("button", { name: "Apply winner" }));
    expect(onUseInChat).toHaveBeenCalledWith("/modify set thickness to 3");
  });
});
