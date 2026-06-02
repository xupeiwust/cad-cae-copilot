import type { AutopilotRunState, ChatConnection } from "../types";

export type EngineeringChatIntent =
  | "generate"
  | "refine"
  | "preprocess"
  | "simulate"
  | "change_material"
  | "refine_mesh"
  | "set_target";

export function mergeLocalAgentCapabilities(
  connections: ChatConnection[],
  capabilities: ChatConnection["adapters"] | undefined,
  llmReady = false,
): ChatConnection[] {
  const adapters = capabilities ?? [];
  const available = adapters.filter((item) => item.status === "available");
  return connections.map((connection) => (
    connection.id === "local-agent"
      ? {
          ...connection,
          status: available.length ? "ready" : "blocked",
          adapters,
          detail: available.length
            ? `Available adapters: ${available.map((item) => item.label).join(", ")}.`
            : adapters[0]?.diagnostic || connection.detail,
        }
      : connection.id === "llm-api"
        ? {
            ...connection,
            status: llmReady ? "ready" : "configurable",
            detail: llmReady
              ? "Model provider is configured and ready for planning through the local approval-gated runtime."
              : connection.detail,
          }
        : connection
  ));
}

export function summarizeAutopilotRun(run: AutopilotRunState): string {
  const agentLabel = run.adapter_id === "llm-api" ? "LLM Agent" : "Local Agent";
  if (run.status === "awaiting_approval" && run.pending_approval) {
    return `${agentLabel} paused for approval: ${run.pending_approval.tool_name}. ${run.pending_approval.explanation}`;
  }
  if (run.final_message) return run.final_message;
  const latest = run.observations[run.observations.length - 1];
  if (latest?.summary) return latest.summary;
  if (run.errors.length) return run.errors[0];
  return `${agentLabel} run ${run.status}.`;
}

export function autopilotAgentLabel(run?: AutopilotRunState | null): string {
  return run?.adapter_id === "llm-api" ? "LLM Agent" : "Local Agent";
}
