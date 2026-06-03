import { expect, test } from "vitest";

import type { AutopilotObservation, AutopilotRunState } from "../types";
import { runToTranscriptItems } from "./chatTranscript";
import { isIntentResolutionObservation, resolvedIntentFromRun } from "./resolvedIntent";

const AT = "2026-06-03T00:00:00.000Z";

function makeRun(overrides: Partial<AutopilotRunState> = {}): AutopilotRunState {
  return {
    run_id: "run-1",
    status: "completed",
    message: "change the wall thickness to 5mm",
    project_id: "p",
    session_id: "s",
    adapter_id: "fake",
    mode: "autopilot",
    dry_run: false,
    llm_config: {},
    created_at: AT,
    updated_at: AT,
    observations: [],
    steps: [],
    pending_approval: null,
    plan: null,
    final_message: null,
    errors: [],
    queued_user_messages: [],
    ...overrides,
  };
}

function obs(kind: string, summary: string, data: Record<string, unknown>): AutopilotObservation {
  return { id: `${kind}-${summary.slice(0, 6)}`, kind, summary, data, created_at: AT };
}

// --- resolvedIntentFromRun ---------------------------------------------------

test("null when there is no resolved_intent (explicit command or plain message)", () => {
  expect(resolvedIntentFromRun(makeRun({ composer_intent: null }))).toBe(null);
  expect(resolvedIntentFromRun(makeRun({ composer_intent: { command: "build" } }))).toBe(null);
  expect(resolvedIntentFromRun(makeRun({ composer_intent: {} }))).toBe(null);
});

test("confident natural-language resolution maps to a summary", () => {
  const run = makeRun({
    composer_intent: {
      command: "modify",
      intent_source: "keyword_heuristic",
      resolved_intent: {
        command: "modify",
        intent_type: "modify_geometry",
        source: "keyword_heuristic",
        confidence: 0.6,
        needs_clarification: false,
      },
    },
  });
  const summary = resolvedIntentFromRun(run);
  expect(summary?.command).toBe("modify");
  expect(summary?.source).toBe("keyword_heuristic");
  expect(summary?.confidence).toBe(0.6);
  expect(summary?.needsClarification).toBe(false);
  expect(summary?.bindings).toEqual([]);
});

test("clarification resolution is surfaced with needsClarification", () => {
  const run = makeRun({
    composer_intent: {
      resolved_intent: { command: "modify", confidence: 0.2, needs_clarification: true, source: "llm_classifier" },
    },
  });
  const summary = resolvedIntentFromRun(run);
  expect(summary?.needsClarification).toBe(true);
  expect(summary?.command).toBe("modify");
});

test("parameter bindings are extracted from observations (known / unresolved / unverified)", () => {
  const run = makeRun({
    composer_intent: { command: "modify", resolved_intent: { command: "modify", confidence: 0.6, source: "keyword_heuristic" } },
    observations: [
      obs("context", "bias", {
        parameter_slots: [{ name: "wall thickness", value: 5 }],
        parameter_bindings: [
          {
            slot_name: "wall thickness", value: 5, unit: "mm", known: true,
            parameter_name: "thickness_mm", cad_parameter_name: "WALL_THICKNESS",
            feature_id: "feat_global_params", value_within_bounds: true,
          },
          { slot_name: "radius", value: 4, unit: "mm", known: false, reason: "ambiguous: matches 2 editable parameters" },
        ],
      }),
    ],
  });
  const summary = resolvedIntentFromRun(run);
  expect(summary?.bindings.length).toBe(2);
  expect(summary?.bindings[0]).toMatchObject({
    slotName: "wall thickness", known: true, cadParameterName: "WALL_THICKNESS", featureId: "feat_global_params",
  });
  expect(summary?.bindings[1]).toMatchObject({ slotName: "radius", known: false });
});

// --- isIntentResolutionObservation ------------------------------------------

test("isIntentResolutionObservation matches only intent context observations", () => {
  expect(isIntentResolutionObservation(obs("context", "x", { intent_resolution: {} }))).toBe(true);
  expect(isIntentResolutionObservation(obs("context", "x", { parameter_slots: [] }))).toBe(true);
  expect(isIntentResolutionObservation(obs("context", "x", { parameter_bindings: [] }))).toBe(true);
  // Other context observations (command instruction, mention bindings) are untouched.
  expect(isIntentResolutionObservation(obs("context", "x", { composer_command: "build" }))).toBe(false);
  expect(isIntentResolutionObservation(obs("tool_result", "x", { parameter_slots: [] }))).toBe(false);
  // Follow-up normalized intent stays VISIBLE (its own key) — not folded into the
  // run-level chip, so it shows inline near the follow-up message.
  expect(isIntentResolutionObservation(obs("context", "x", { followup_intent: { command: "explain" } }))).toBe(false);
});

// --- projection into the transcript -----------------------------------------

test("runToTranscriptItems emits one intent chip and suppresses the raw context lines", () => {
  const run = makeRun({
    composer_intent: {
      command: "modify",
      resolved_intent: { command: "modify", confidence: 0.6, source: "keyword_heuristic", needs_clarification: false },
    },
    observations: [
      obs("context", "No explicit /command was used; resolved ... to /modify ...", {
        intent_resolution: { command: "modify" },
      }),
      obs("context", "The user requested dimensional edit(s) ...", {
        parameter_slots: [{ name: "wall thickness", value: 5 }],
        parameter_bindings: [],
      }),
      obs("context", "The user explicitly invoked /modify ...", { composer_command: "modify" }),
    ],
  });

  const items = runToTranscriptItems(run);
  const intentItems = items.filter((i) => i.kind === "intent");
  expect(intentItems.length).toBe(1);

  // The two intent-bearing context observations are not rendered as status lines.
  const statusSummaries = items.filter((i) => i.kind === "status").map((i) => (i as { summary: string }).summary);
  expect(statusSummaries.some((s) => s.includes("resolved"))).toBe(false);
  expect(statusSummaries.some((s) => s.includes("dimensional edit"))).toBe(false);
  // A non-intent context observation still renders.
  expect(statusSummaries.some((s) => s.includes("explicitly invoked"))).toBe(true);
});

test("no intent chip for an explicit-command run", () => {
  const run = makeRun({ composer_intent: { command: "build" } });
  expect(runToTranscriptItems(run).some((i) => i.kind === "intent")).toBe(false);
});
