import type { ChatHistoryItem } from "../appTypes";
import type { AutopilotAgentPlan, AutopilotRunState } from "../types";
import { chatHistoryToTranscriptItems, type AgentTranscriptEvent } from "./chatTranscript";
import { test } from "vitest";

test("chat transcript replay", () => {

const createdAt = "2026-06-02T00:00:00.000Z";

const staleSnapshotPlan: AutopilotAgentPlan = {
  id: "plan-replay",
  objective: "Inspect and summarize project",
  status: "running",
  current_step_id: "inspect_context",
  created_at: createdAt,
  updated_at: createdAt,
  steps: [
    {
      id: "inspect_context",
      title: "Inspect context",
      kind: "tool",
      status: "running",
      tool_name: "aieng.agent_context",
      skill_name: null,
      summary: "Inspecting context",
      evidence: {},
    },
    {
      id: "summarize_result",
      title: "Summarize",
      kind: "summarize",
      status: "pending",
      tool_name: null,
      skill_name: null,
      summary: "",
      evidence: {},
    },
  ],
};

const runSnapshot: AutopilotRunState = {
  run_id: "run-plan-replay",
  status: "completed",
  message: "inspect",
  project_id: "project-plan-replay",
  session_id: "session-plan-replay",
  adapter_id: "fake",
  mode: "autopilot",
  dry_run: true,
  llm_config: {},
  created_at: createdAt,
  updated_at: "2026-06-02T00:01:00.000Z",
  observations: [],
  steps: [],
  pending_approval: null,
  plan: staleSnapshotPlan,
  final_message: null,
  errors: [],
  queued_user_messages: [],
};

const chatHistory: ChatHistoryItem[] = [{
  id: "assistant-snapshot",
  role: "assistant",
  body: "Run completed",
  createdAt,
  mode: "runtime",
  autopilotRun: runSnapshot,
}];

const replayEvents: AgentTranscriptEvent[] = [
  {
    event_id: "plan-created",
    type: "agent_plan_created",
    run_id: "run-plan-replay",
    project_id: "project-plan-replay",
    session_id: "session-plan-replay",
    status: "running",
    payload: { plan: staleSnapshotPlan },
    created_at: createdAt,
  },
  {
    event_id: "inspect-completed",
    type: "agent_plan_step_updated",
    run_id: "run-plan-replay",
    project_id: "project-plan-replay",
    session_id: "session-plan-replay",
    status: "completed",
    payload: {
      plan_id: "plan-replay",
      current_step_id: "summarize_result",
      step: {
        ...staleSnapshotPlan.steps[0],
        status: "completed",
        summary: "Context inspected",
        evidence: { output: { summary: "context ok" } },
      },
    },
    created_at: "2026-06-02T00:00:30.000Z",
  },
  {
    event_id: "summarize-completed",
    type: "agent_plan_step_updated",
    run_id: "run-plan-replay",
    project_id: "project-plan-replay",
    session_id: "session-plan-replay",
    status: "completed",
    payload: {
      plan_id: "plan-replay",
      current_step_id: "summarize_result",
      step: {
        ...staleSnapshotPlan.steps[1],
        status: "completed",
        summary: "Summary ready",
      },
    },
    created_at: "2026-06-02T00:01:00.000Z",
  },
];

const transcript = chatHistoryToTranscriptItems(chatHistory, replayEvents);
const plans = transcript.filter((item) => item.kind === "plan");

expectEqual(plans.length, 1, "event replay should replace stale run snapshot plan");
expectEqual(plans[0].sourceId, "event-plan:run-plan-replay:plan-replay", "plan source");
expectEqual(plans[0].status, "done", "plan status");
expectEqual(plans[0].currentStepId, "summarize_result", "current step");
expectDeepEqual(
  plans[0].steps.map((step) => [step.id, step.status, step.summary]),
  [
    ["inspect_context", "completed", "Context inspected"],
    ["summarize_result", "completed", "Summary ready"],
  ],
  "step replay state",
);

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function expectDeepEqual(actual: unknown, expected: unknown, label: string) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`${label}: expected ${expectedJson}, got ${actualJson}`);
  }
}
});

test("chat transcript collapses duplicate phase/status rows and terminalizes completed progress", () => {
  const events: AgentTranscriptEvent[] = [
    {
      event_id: "phase-1",
      type: "agent_phase_changed",
      run_id: "run-dup",
      project_id: "project-dup",
      session_id: "session-dup",
      status: "running",
      content: "Prepared full prompt for fake.",
      payload: { phase: "prompt_prepared", progress_event: true },
      created_at: "2026-06-02T00:00:01.000Z",
    },
    {
      event_id: "phase-2",
      type: "agent_phase_changed",
      run_id: "run-dup",
      project_id: "project-dup",
      session_id: "session-dup",
      status: "running",
      content: "Prepared full prompt for fake.",
      payload: { phase: "prompt_prepared", progress_event: true },
      created_at: "2026-06-02T00:00:02.000Z",
    },
    {
      event_id: "status-1",
      type: "run_status_changed",
      run_id: "run-dup",
      project_id: "project-dup",
      session_id: "session-dup",
      status: "running",
      content: "Invoking fake for the next action.",
      payload: { adapter_id: "fake" },
      created_at: "2026-06-02T00:00:03.000Z",
    },
    {
      event_id: "status-2",
      type: "run_status_changed",
      run_id: "run-dup",
      project_id: "project-dup",
      session_id: "session-dup",
      status: "running",
      content: "Invoking fake for the next action.",
      payload: { adapter_id: "fake" },
      created_at: "2026-06-02T00:00:04.000Z",
    },
    {
      event_id: "complete",
      type: "run_status_changed",
      run_id: "run-dup",
      project_id: "project-dup",
      session_id: "session-dup",
      status: "completed",
      content: "Autopilot run completed.",
      payload: {},
      created_at: "2026-06-02T00:00:05.000Z",
    },
  ];

  const transcript = chatHistoryToTranscriptItems([], events);
  const promptRows = transcript.filter(
    (item) => item.kind === "status" && item.summary.includes("prompt prepared"),
  );
  const invokingRows = transcript.filter(
    (item) => item.kind === "status" && item.summary === "Invoking fake for the next action.",
  );
  const activeRows = transcript.filter(
    (item) =>
      item.runId === "run-dup" &&
      (item.kind === "status" || item.kind === "tool" || item.kind === "artifact") &&
      item.status === "running",
  );

  expectLocalEqual(promptRows.length, 1, "duplicate phase rows");
  expectLocalEqual(invokingRows.length, 1, "duplicate status rows");
  expectLocalEqual(activeRows.length, 0, "completed run should not leave active progress rows");

  function expectLocalEqual(actual: unknown, expected: unknown, label = "value") {
    if (actual !== expected) {
      throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
  }
});

test("completed run shows unreached pending plan steps as skipped, active run keeps pending", () => {
  const at = "2026-06-02T00:00:00.000Z";
  const makePlan = (status: string): AutopilotAgentPlan => ({
    id: "plan-x",
    objective: "Build something",
    status,
    current_step_id: "summarize_result",
    created_at: at,
    updated_at: at,
    steps: [
      { id: "execute_tool", title: "Execute", kind: "tool", status: "completed", tool_name: null, skill_name: null, summary: "done", evidence: {} },
      { id: "await_approval", title: "Await", kind: "approval", status: "pending", tool_name: null, skill_name: null, summary: "", evidence: {} },
    ],
  });
  const makeRun = (status: AutopilotRunState["status"], plan: AutopilotAgentPlan): AutopilotRunState => ({
    run_id: `run-${status}`,
    status,
    message: "build",
    project_id: "p",
    session_id: "s",
    adapter_id: "fake",
    mode: "autopilot",
    dry_run: true,
    llm_config: {},
    created_at: at,
    updated_at: at,
    observations: [],
    steps: [],
    pending_approval: null,
    plan,
    final_message: status === "completed" ? "Done." : null,
    errors: [],
    queued_user_messages: [],
  });

  const planStepStatuses = (run: AutopilotRunState): string => {
    const history: ChatHistoryItem[] = [{ id: run.run_id, role: "assistant", body: "Run", createdAt: at, mode: "runtime", autopilotRun: run }];
    const item = chatHistoryToTranscriptItems(history, []).find((i) => i.kind === "plan");
    return item && item.kind === "plan" ? item.steps.map((s) => `${s.id}:${s.status}`).join(",") : "NO_PLAN";
  };

  // Completed run: the unreached await_approval step is shown as skipped.
  check(
    planStepStatuses(makeRun("completed", makePlan("completed"))),
    "execute_tool:completed,await_approval:skipped",
    "completed run marks pending step skipped",
  );
  // Active (running) run: the pending step is left as-is.
  check(
    planStepStatuses(makeRun("running", makePlan("running"))),
    "execute_tool:completed,await_approval:pending",
    "running run keeps pending step",
  );

  function check(actual: unknown, expected: unknown, label: string) {
    if (actual !== expected) {
      throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
  }
});
