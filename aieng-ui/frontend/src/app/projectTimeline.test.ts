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
    expect(timeline.entries.some((entry) => entry.nextActions.some((action) => (
      action.tool === "cae.run_solver"
      && action.label === "Run the prepared deck after approval"
    )))).toBe(true);
  });

  test("preserves blocked reasons, reason codes, and safety flags on next actions", () => {
    const run: RuntimeRun = {
      ...baseRun,
      tool_results: [
        {
          id: "tool_1",
          status: "success",
          output: {
            receipt: {
              operation: "cae.prepare_solver_run",
              status: "blocked",
              next_actions: [
                {
                  label: "Install CalculiX and add ccx to PATH",
                  reason: "Solver executable is missing.",
                  blocked_reason_codes: ["solver_missing"],
                },
                {
                  tool: "cae.run_solver",
                  label: "Run the prepared deck",
                  available_now: false,
                  blocked_reason: "Approval is required.",
                  blocked_reason_codes: ["approval_required"],
                  blocked_reason_code_details: [{
                    code: "approval_required",
                    label: "Approval required",
                    description: "Human approval is required.",
                    recommended_action: "Approve after reviewing the planned solver run.",
                  }],
                  resolves_blocked_reason_codes: ["deck_not_prepared"],
                  resolves_blocked_reason_code_details: [{
                    code: "deck_not_prepared",
                    label: "Solver deck not prepared",
                    description: "The solver input deck is missing.",
                    recommended_action: "Generate solver input.",
                  }],
                  requires_approval: true,
                  mutates_package: true,
                  runs_solver: true,
                },
              ],
            },
          },
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);
    const entry = timeline.entries.find((item) => item.id === "run_001:result:tool_1");

    expect(entry?.nextActions).toEqual([
      expect.objectContaining({
        tool: null,
        label: "Install CalculiX and add ccx to PATH",
        availableNow: false,
        blockedReason: "Solver executable is missing.",
        blockedReasonCodes: ["solver_missing"],
      }),
      expect.objectContaining({
        tool: "cae.run_solver",
        label: "Run the prepared deck",
        availableNow: false,
        blockedReason: "Approval is required.",
        blockedReasonCodes: ["approval_required"],
        blockedReasonCodeDetails: [expect.objectContaining({
          code: "approval_required",
          recommendedAction: "Approve after reviewing the planned solver run.",
        })],
        resolvesBlockedReasonCodes: ["deck_not_prepared"],
        resolvesBlockedReasonCodeDetails: [expect.objectContaining({
          code: "deck_not_prepared",
          label: "Solver deck not prepared",
        })],
        safetyFlags: ["requires approval", "runs solver", "mutates package"],
      }),
    ]);
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

  test("surfaces structured tool failure diagnostics as event detail", () => {
    const run: RuntimeRun = {
      ...baseRun,
      status: "failed",
      events: [
        {
          id: "evt_failed",
          run_id: "run_001",
          type: "tool_failed",
          timestamp: "2026-06-25T10:00:03Z",
          payload: {
            tool: "cae.run_solver",
            error: "RuntimeError: ccx failed",
            diagnostic: {
              code: "tool_execution_error",
              message: "RuntimeError: ccx failed",
              remediation: "Inspect the solver log.",
            },
          },
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);
    const entry = timeline.entries.find((item) => item.id === "evt_failed");

    expect(entry?.kind).toBe("failure");
    expect(entry?.detail).toBe("RuntimeError: ccx failed");
    expect(entry?.diagnostic).toEqual(expect.objectContaining({
      code: "tool_execution_error",
      remediation: "Inspect the solver log.",
      toolName: "cae.run_solver",
    }));
  });

  test("surfaces structured rejection diagnostics as event detail", () => {
    const run: RuntimeRun = {
      ...baseRun,
      status: "rejected",
      events: [
        {
          id: "evt_rejected",
          run_id: "run_001",
          type: "run_rejected",
          timestamp: "2026-06-25T10:00:04Z",
          payload: {
            tool: "cae.run_solver",
            diagnostic: {
              code: "approval_rejected",
              message: "User rejected approval for cae.run_solver",
              remediation: "No action was executed.",
            },
          },
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);
    const entry = timeline.entries.find((item) => item.id === "evt_rejected");

    expect(entry?.kind).toBe("failure");
    expect(entry?.detail).toBe("User rejected approval for cae.run_solver");
    expect(entry?.diagnostic).toEqual(expect.objectContaining({
      code: "approval_rejected",
      remediation: "No action was executed.",
      toolName: "cae.run_solver",
    }));
  });

  test("uses tool result errors as fallback failure detail", () => {
    const run: RuntimeRun = {
      ...baseRun,
      status: "failed",
      tool_results: [
        {
          id: "tool_error",
          status: "error",
          error: "RuntimeError: legacy failure",
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);
    const entry = timeline.entries.find((item) => item.id === "run_001:result:tool_error");

    expect(entry?.kind).toBe("failure");
    expect(entry?.detail).toBe("RuntimeError: legacy failure");
    expect(entry?.diagnostic).toEqual(expect.objectContaining({
      code: "tool_error",
      message: "RuntimeError: legacy failure",
    }));
  });

  test("matches tool_errors details onto error result entries", () => {
    const run: RuntimeRun = {
      ...baseRun,
      status: "failed",
      tool_results: [
        {
          id: "tool_error",
          status: "error",
          error: "ValueError: bad input",
        },
      ],
      tool_errors: [
        {
          code: "tool_execution_error",
          message: "ValueError: bad input",
          tool_name: "cad.execute_build123d",
          details: {
            code: "tool_execution_error",
            message: "ValueError: bad input",
            remediation: "Fix the generated script and retry.",
            tool_name: "cad.execute_build123d",
          },
        },
      ],
    };

    const timeline = buildProjectTimeline([run]);
    const entry = timeline.entries.find((item) => item.id === "run_001:result:tool_error");

    expect(entry?.diagnostic).toEqual(expect.objectContaining({
      code: "tool_execution_error",
      remediation: "Fix the generated script and retry.",
      toolName: "cad.execute_build123d",
    }));
  });
});
