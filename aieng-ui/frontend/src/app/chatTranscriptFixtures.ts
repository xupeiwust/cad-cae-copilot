import type { AutopilotRunState } from "../types";
import type { ChatTranscriptItem } from "./chatTranscript";

const BASE_RUN = {
  project_id: "fixture-project",
  session_id: "fixture-session",
  adapter_id: "fixture-agent",
  mode: "assist",
  dry_run: false,
  llm_config: {},
  steps: [],
  queued_user_messages: [],
} satisfies Partial<AutopilotRunState>;

function runFixture(
  runId: string,
  status: AutopilotRunState["status"],
  overrides: Partial<AutopilotRunState> = {},
): AutopilotRunState {
  const now = "2026-05-30T00:00:00.000Z";
  return {
    ...BASE_RUN,
    run_id: runId,
    status,
    message: `fixture ${status}`,
    created_at: now,
    updated_at: now,
    observations: [],
    pending_approval: null,
    final_message: null,
    errors: [],
    ...overrides,
  };
}

export const transcriptMappingFixtures = {
  running: runFixture("fixture-running", "running", {
    observations: [{
      id: "obs-tool-started",
      kind: "tool_started",
      summary: "Inspecting project context",
      data: { tool_name: "aieng.agent_context" },
      created_at: "2026-05-30T00:00:01.000Z",
    }],
  }),
  awaitingApproval: runFixture("fixture-approval", "awaiting_approval", {
    pending_approval: {
      id: "approval-cad-build",
      tool_name: "cad.execute_build123d",
      input: { project_id: "fixture-project" },
      level: "write",
      explanation: "CAD geometry write requires approval.",
      side_effect_summary: "Replace project geometry.",
      risk_summary: "Mutates the active package.",
      target_project_id: "fixture-project",
      code_preview: "result = Box(10, 10, 2)",
      artifact_preview: null,
      recommended_action: "approve",
      created_at: "2026-05-30T00:01:01.000Z",
    },
  }),
  completed: runFixture("fixture-completed", "completed", {
    observations: [{
      id: "obs-artifact",
      kind: "artifact_ready",
      summary: "Viewer preview ready",
      data: {
        preview_url: "/api/projects/fixture-project/preview.glb",
        artifact_paths: ["geometry/model.glb"],
        named_parts: ["base_plate", "rib_main"],
      },
      created_at: "2026-05-30T00:02:01.000Z",
    }],
    final_message: "Geometry is ready.",
  }),
  failed: runFixture("fixture-failed", "failed", {
    errors: ["cad.execute_build123d failed"],
  }),
  blocked: runFixture("fixture-blocked", "blocked", {
    final_message: "I need a target project before continuing.",
  }),
  chatting: runFixture("fixture-chatting", "chatting", {
    observations: [{
      id: "obs-chat",
      kind: "chat",
      summary: "Which material should I assume?",
      data: { content: "Which material should I assume?" },
      created_at: "2026-05-30T00:05:01.000Z",
    }],
  }),
} satisfies Record<string, AutopilotRunState>;

export const transcriptMappingExpectedShapes = {
  running: ["tool"],
  awaitingApproval: ["approval"],
  completed: ["artifact", "message"],
  failed: ["error"],
  blocked: ["message"],
  chatting: ["message"],
} satisfies Record<keyof typeof transcriptMappingFixtures, Array<ChatTranscriptItem["kind"]>>;
