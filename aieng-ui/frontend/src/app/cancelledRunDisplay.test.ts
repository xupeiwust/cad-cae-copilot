import { expect, test } from "vitest";

import type { ChatHistoryItem } from "../appTypes";
import type { AutopilotAgentPlan, AutopilotAgentPlanStep, AutopilotRunState } from "../types";
import {
  chatHistoryToTranscriptItems,
  isStreamingClosingEvent,
  isTerminalAutopilotStatus,
  normalizeTerminalPlanSteps,
  type AgentTranscriptEvent,
  type TranscriptAgentPlanLine,
} from "./chatTranscript";
import { isRunActivelyProcessing, isTerminalAutopilotRun } from "./agentActivityFallback";

const AT = "2026-06-03T00:00:00.000Z";

function step(id: string, status: string, kind = "tool"): AutopilotAgentPlanStep {
  return { id, title: id, kind, status, tool_name: null, skill_name: null, summary: status, evidence: {} };
}

// A realistic mid-flight plan: one step done, one running, the rest never reached
// (pending / approval / blocked) — exactly the shape the cancelled screenshot shows.
function midFlightPlan(planStatus: string): AutopilotAgentPlan {
  return {
    id: "plan-1",
    objective: "Add four short landing legs under the fuselage.",
    status: planStatus,
    current_step_id: "select",
    created_at: AT,
    updated_at: AT,
    steps: [
      step("observe", "completed"),
      step("select", "running", "skill"),
      step("prepare", "pending"),
      step("await", "pending", "approval"),
      step("repair", "running", "repair"),
      step("summarize", "blocked", "summarize"),
    ],
  };
}

function makeRun(status: AutopilotRunState["status"], plan: AutopilotAgentPlan): AutopilotRunState {
  return {
    run_id: `run-${status}`,
    status,
    message: "build",
    project_id: "p",
    session_id: "s",
    adapter_id: "claude-code",
    mode: "autopilot",
    dry_run: false,
    llm_config: {},
    created_at: AT,
    updated_at: AT,
    observations: [],
    steps: [],
    pending_approval: null,
    plan,
    final_message: null,
    errors: [],
    queued_user_messages: [],
  };
}

function projectPlan(run: AutopilotRunState, events: AgentTranscriptEvent[] = []): TranscriptAgentPlanLine {
  const history: ChatHistoryItem[] = [
    { id: run.run_id, role: "assistant", body: "Run", createdAt: AT, mode: "runtime", autopilotRun: run },
  ];
  const plan = chatHistoryToTranscriptItems(history, events).find((i) => i.kind === "plan");
  if (!plan || plan.kind !== "plan") throw new Error("no plan item projected");
  return plan;
}

const ACTIVE_STEP_STATUSES = new Set(["running", "pending", "blocked", "approval"]);

// --- Completion criterion 1 + 2: a cancelled run never displays as active ----

test("cancelled run plan is stopped: no step spins/pends, plan status is cancelled", () => {
  const plan = projectPlan(makeRun("cancelled", midFlightPlan("running")));

  expect(plan.status).toBe("cancelled");
  // No step is left in an active/glowing state.
  for (const s of plan.steps) {
    expect(ACTIVE_STEP_STATUSES.has(s.status)).toBe(false);
  }
  const byId = Object.fromEntries(plan.steps.map((s) => [s.id, s.status]));
  expect(byId.observe).toBe("completed"); // finished work is preserved
  expect(byId.select).toBe("cancelled"); // was running
  expect(byId.repair).toBe("cancelled"); // was running
  expect(byId.prepare).toBe("cancelled"); // was pending
  expect(byId.await).toBe("cancelled"); // was a pending approval step
  expect(byId.summarize).toBe("cancelled"); // was blocked
});

test("cancelled status is authoritative even when the plan still reads blocked/running", () => {
  // Backend did not re-stamp the plan on cancel — plan.status is still "blocked".
  const plan = projectPlan(makeRun("cancelled", midFlightPlan("blocked")));
  expect(plan.status).toBe("cancelled");
  expect(plan.steps.every((s) => !ACTIVE_STEP_STATUSES.has(s.status))).toBe(true);
});

test("cancelled run via event replay also normalizes running steps", () => {
  const created: AgentTranscriptEvent = {
    event_id: "created",
    type: "agent_plan_created",
    run_id: "run-evt",
    payload: { plan: midFlightPlan("running") },
    created_at: AT,
  };
  const cancelled: AgentTranscriptEvent = {
    event_id: "cancel",
    type: "run_cancelled",
    run_id: "run-evt",
    content: "Autopilot run cancelled.",
    created_at: "2026-06-03T00:00:05.000Z",
  };
  // No run snapshot in history — the cancellation is known only from events.
  const plan = chatHistoryToTranscriptItems([], [created, cancelled]).find((i) => i.kind === "plan");
  expect(plan && plan.kind === "plan").toBe(true);
  if (plan && plan.kind === "plan") {
    expect(plan.status).toBe("cancelled");
    expect(plan.steps.every((s) => !ACTIVE_STEP_STATUSES.has(s.status))).toBe(true);
  }
});

// --- Completion criterion 3: cancelled rows carry a stopped tone -------------

test("run_cancelled event row uses the cancelled (not blocked) status", () => {
  const event: AgentTranscriptEvent = {
    event_id: "c1",
    type: "run_cancelled",
    run_id: "run-x",
    content: "Run cancelled",
    created_at: AT,
  };
  const rows = chatHistoryToTranscriptItems([], [event]);
  const statusRow = rows.find((r) => r.kind === "status" && r.summary === "Run cancelled");
  expect(statusRow && statusRow.kind === "status" ? statusRow.status : null).toBe("cancelled");
});

// --- Completion criterion 4 + streaming: terminal helpers treat cancelled ----

test("cancelled is terminal and not actively processing", () => {
  expect(isTerminalAutopilotStatus("cancelled")).toBe(true);
  const run = makeRun("cancelled", midFlightPlan("running"));
  expect(isTerminalAutopilotRun(run)).toBe(true);
  expect(isRunActivelyProcessing(run, Date.parse(AT) + 1000)).toBe(false);
});

test("run_cancelled and terminal run_status_changed close the streaming bubble", () => {
  expect(isStreamingClosingEvent({ type: "run_cancelled", run_id: "r" })).toBe(true);
  expect(isStreamingClosingEvent({ type: "run_status_changed", run_id: "r", status: "cancelled" })).toBe(true);
  // Non-terminal waiting states must NOT close it.
  expect(isStreamingClosingEvent({ type: "run_status_changed", run_id: "r", status: "awaiting_approval" })).toBe(false);
});

// --- Completion criterion 6 / "do not": completed/failed/blocked intact ------

test("completed run still marks unreached pending steps as skipped (unchanged)", () => {
  const plan = projectPlan(makeRun("completed", midFlightPlan("completed")));
  expect(plan.status).toBe("done");
  const byId = Object.fromEntries(plan.steps.map((s) => [s.id, s.status]));
  expect(byId.prepare).toBe("skipped"); // pending -> skipped
  expect(byId.await).toBe("skipped");
});

test("blocked (non-terminal) run keeps its live pending/blocked steps — not cancelled", () => {
  const plan = projectPlan(makeRun("blocked", midFlightPlan("blocked")));
  expect(plan.status).toBe("blocked");
  const byId = Object.fromEntries(plan.steps.map((s) => [s.id, s.status]));
  // A genuinely blocked run is still active: do not make it look cancelled.
  expect(byId.prepare).toBe("pending");
  expect(byId.summarize).toBe("blocked");
  expect(isTerminalAutopilotStatus("blocked")).toBe(false);
  expect(isTerminalAutopilotStatus("awaiting_approval")).toBe(false);
});

// --- normalizeTerminalPlanSteps unit coverage --------------------------------

test("normalizeTerminalPlanSteps rules", () => {
  const steps = [step("a", "completed"), step("b", "running"), step("c", "pending"), step("d", "blocked"), step("e", "failed")];

  const cancelled = normalizeTerminalPlanSteps(steps, "cancelled").map((s) => s.status);
  expect(cancelled).toEqual(["completed", "cancelled", "cancelled", "cancelled", "failed"]);

  const completed = normalizeTerminalPlanSteps(steps, "completed").map((s) => s.status);
  expect(completed).toEqual(["completed", "running", "skipped", "blocked", "failed"]);

  // failed is left untouched (historical behavior preserved).
  const failed = normalizeTerminalPlanSteps(steps, "failed");
  expect(failed).toBe(steps);
});
