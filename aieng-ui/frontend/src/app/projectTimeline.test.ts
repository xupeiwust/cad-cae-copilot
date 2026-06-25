import { describe, expect, test } from "vitest";

import { buildProjectTimeline } from "./projectTimeline";
import type { RuntimeRun } from "../types";

const baseRun: RuntimeRun = {
  run_id: "run_001",
  created_at: "2026-06-25T10:00:00Z",
  status: "completed",
  message: "Prepare solver",
  plan: [],
  events: [],
  tool_calls: [],
  tool_results: [],
  tool_errors: [],
  errors: [],
  summary: "Done",
};

describe("buildProjectTimeline", () => {
  test("returns an empty timeline for empty project state", () => {
    const timeline = buildProjectTimeline([]);

    expect(timeline.entries).toEqual([]);
    expect(timeline.runCount).toBe(0);
    expect(timeline.warningCount).toBe(0);
  });

  test("collects approval events, receipt artifacts, and advisory next actions", () => {
    const run: RuntimeRun = {
      ...baseRun,
      events: [
        {
          id: "evt_approval",
          run_id: "run_001",
          type: "approval_required",
          timestamp: "2026-06-25T10:00:02Z",
          payload: { tool_name: "cae.run_solver", reason: "Solver execution requires approval." },
        },
      ],
      tool_results: [
        {
          id: "tool_1",
          status: "success",
          output: {
            receipt: {
              operation: "cae.prepare_solver_run",
              status: "ok",
              artifacts_written: [{ path: "simulation/runs/run_001/solver_input.inp" }],
              next_actions: [
                { tool: "cae.run_solver", label: "Run the prepared deck after approval" },
              ],
            },
          },
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);

    expect(timeline.entries.some((entry) => entry.kind === "approval")).toBe(true);
    expect(timeline.entries.some((entry) => entry.artifacts.includes("simulation/runs/run_001/solver_input.inp"))).toBe(true);
    expect(timeline.entries.some((entry) => entry.nextActions.includes("cae.run_solver: Run the prepared deck after approval"))).toBe(true);
  });

  test("malformed non-object tool output is surfaced as a warning without throwing", () => {
    const run: RuntimeRun = {
      ...baseRun,
      tool_results: [
        {
          id: "tool_bad",
          status: "success",
          output: "not a receipt",
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);

    expect(timeline.warningCount).toBe(1);
    expect(timeline.entries.some((entry) => entry.title.includes("tool_bad"))).toBe(true);
  });
});
