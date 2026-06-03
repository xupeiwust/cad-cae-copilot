import { expect, test } from "vitest";

import type { AutopilotObservation, AutopilotRunState } from "../types";
import { runToTranscriptItems } from "./chatTranscript";
import { editVerificationFromOutput, verdictLabel } from "./editVerification";

function output(regression_diff: unknown): Record<string, unknown> {
  return { status: "ok", regression_diff };
}

test("clean verdict maps to ok tone with intended changed parts", () => {
  const v = editVerificationFromOutput(
    output({
      verdict: "clean",
      headline: "1 part(s) changed as expected; 2 unchanged.",
      changed: [{ part: "wall", max_change_mm: 2, expected: true }],
      collateral_parts: [],
      added: [],
      removed: [],
      unchanged_count: 2,
    }),
    "cad.edit_parameter",
  );
  expect(v?.verdict).toBe("clean");
  expect(v?.tone).toBe("ok");
  expect(v?.changed[0]).toMatchObject({ part: "wall", maxChangeMm: 2, expected: true });
});

test("collateral_change maps to warn and lists collateral parts", () => {
  const v = editVerificationFromOutput(
    output({
      verdict: "collateral_change",
      headline: "WARNING: 1 unrelated part(s) also changed: rib.",
      changed: [
        { part: "wall", max_change_mm: 2, expected: true },
        { part: "rib", max_change_mm: 1.5, expected: false },
      ],
      collateral_parts: ["rib"],
    }),
    "cad.edit_parameter",
  );
  expect(v?.tone).toBe("warn");
  expect(v?.collateralParts).toEqual(["rib"]);
});

test("identical maps to neutral; topology_changed to warn", () => {
  expect(editVerificationFromOutput(output({ verdict: "identical" }), "x")?.tone).toBe("neutral");
  expect(editVerificationFromOutput(output({ verdict: "topology_changed", added: ["fin"] }), "x")?.tone).toBe("warn");
});

test("null when there is no regression diff or an unknown verdict", () => {
  expect(editVerificationFromOutput({ status: "ok" }, "x")).toBe(null);
  expect(editVerificationFromOutput(output({ verdict: "weird" }), "x")).toBe(null);
  expect(editVerificationFromOutput(null, "x")).toBe(null);
});

test("verdictLabel covers all verdicts", () => {
  expect(verdictLabel("clean")).toBe("Clean edit");
  expect(verdictLabel("collateral_change")).toBe("Collateral change");
  expect(verdictLabel("identical")).toBe("No change");
  expect(verdictLabel("topology_changed")).toBe("Topology changed");
});

// --- projection -------------------------------------------------------------

const AT = "2026-06-03T00:00:00.000Z";

function runWithToolResult(diff: unknown): AutopilotRunState {
  const obs: AutopilotObservation = {
    id: "o1",
    kind: "tool_result",
    summary: "Executed tool call: cad.edit_parameter",
    data: { tool_name: "cad.edit_parameter", output: output(diff) },
    created_at: AT,
  };
  return {
    run_id: "r1", status: "completed", message: "set wall thickness to 5mm",
    project_id: "p", session_id: "s", adapter_id: "fake", mode: "autopilot", dry_run: false,
    llm_config: {}, created_at: AT, updated_at: AT, observations: [obs], steps: [],
    pending_approval: null, plan: null, final_message: null, errors: [], queued_user_messages: [],
  };
}

test("runToTranscriptItems emits a verification line after an edit tool result", () => {
  const items = runToTranscriptItems(
    runWithToolResult({ verdict: "clean", headline: "ok", changed: [{ part: "wall", max_change_mm: 2, expected: true }] }),
  );
  const verify = items.filter((i) => i.kind === "verification");
  expect(verify.length).toBe(1);
  // The tool line is still present, and the verify line is distinct.
  expect(items.some((i) => i.kind === "tool")).toBe(true);
});

test("no verification line for a tool result without a regression diff", () => {
  const run = runWithToolResult(undefined);
  // Strip the diff entirely.
  run.observations[0].data = { tool_name: "cad.critique", output: { status: "ok", findings: [] } };
  expect(runToTranscriptItems(run).some((i) => i.kind === "verification")).toBe(false);
});
