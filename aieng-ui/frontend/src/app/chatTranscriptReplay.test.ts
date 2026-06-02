import type { ChatHistoryItem } from "../appTypes";
import type { AutopilotAgentPlan, AutopilotRunState } from "../types";
import { chatHistoryToTranscriptItems, type AgentTranscriptEvent } from "./chatTranscript";

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
