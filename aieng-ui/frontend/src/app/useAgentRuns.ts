import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { ChatHistoryItem, Notice, SelectedGeometryContext } from "../appTypes";
import { createChatId, runtimeStatusLabel } from "../appUtils";
import type {
  AgentPlan,
  ChatConnection,
  LLMConfig,
  LocalAgentCapability,
  LocalAgentConfig,
  RuntimeRun,
} from "../types";
import {
  autopilotAgentLabel,
  mergeLocalAgentCapabilities,
  summarizeAutopilotRun,
} from "./workbenchHelpers";

type UseAgentRunsArgs = {
  selectedId: string | null;
  message: string;
  selectedChatConnection: ChatConnection;
  localAgentConfig: LocalAgentConfig;
  llmConfig: LLMConfig;
  agentPayloadGeometry(): SelectedGeometryContext | undefined;
  appendRunToChatHistory(run: RuntimeRun): void;
  runBusyTask(task: () => Promise<void>): Promise<void>;
  setNotice: Dispatch<SetStateAction<Notice | null>>;
  setChatHistory: Dispatch<SetStateAction<ChatHistoryItem[]>>;
  setChatConnections: Dispatch<SetStateAction<ChatConnection[]>>;
};

export function useAgentRuns({
  selectedId,
  message,
  selectedChatConnection,
  localAgentConfig,
  llmConfig,
  agentPayloadGeometry,
  appendRunToChatHistory,
  runBusyTask,
  setNotice,
  setChatHistory,
  setChatConnections,
}: UseAgentRunsArgs) {
  const [agentPlan, setAgentPlan] = useState<AgentPlan | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [lastRuntimeRun, setLastRuntimeRun] = useState<RuntimeRun | null>(null);
  const autopilotPollTimerRef = useRef<number | null>(null);

  useEffect(() => () => stopAutopilotPoll(), []);

  async function approveRun() {
    if (!lastRuntimeRun || lastRuntimeRun.status !== "awaiting_approval") return;
    await runBusyTask(async () => {
      const run = await api.approveRun(lastRuntimeRun.run_id);
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      const statusLabel = runtimeStatusLabel(run.status);
      setNotice({
        tone: run.status === "completed" ? "success" : "error",
        title: `Runtime approval — ${statusLabel}`,
        detail: run.summary || run.errors[0] || "Approved and executed",
      });
    });
  }

  async function rejectRun() {
    if (!lastRuntimeRun || lastRuntimeRun.status !== "awaiting_approval") return;
    await runBusyTask(async () => {
      const run = await api.rejectRun(lastRuntimeRun.run_id);
      setLastRuntimeRun(run);
      appendRunToChatHistory(run);
      setNotice({ tone: "info", title: "Runtime approval — Rejected", detail: "Rejected, pending tool was not executed." });
    });
  }

  async function createAgentPlanFromPrompt(prompt: string, skipUserMsg = false) {
    setAgentBusy(true);
    setNotice(null);
    try {
      const plan = await api.planAgent({
        message: prompt,
        project_id: selectedId ?? null,
        selected_geometry: agentPayloadGeometry(),
        llm_config: llmConfig,
        dry_run: false,
      });
      setAgentPlan(plan);
      setChatHistory((current) => [
        ...current,
        ...(skipUserMsg ? [] : [{ id: createChatId(), role: "user" as const, body: prompt, createdAt: new Date().toISOString(), mode: "plan" as const }]),
        {
          id: createChatId(),
          role: "assistant",
          body: `[Agent ${plan.mode}] ${plan.reply}`,
          createdAt: new Date().toISOString(),
          mode: "runtime",
          plan: plan.steps.map((step) => ({
            tool: step.tool_name ?? step.id,
            description: step.description || step.tool_name || step.id,
            status: step.approval_required ? "needs_approval" : "pending",
            inputs: step.input ?? {},
            output: null,
          })),
          errors: [...(plan.errors ?? []), ...(plan.warnings ?? [])],
        },
      ]);
      setNotice({
        tone: plan.errors?.length ? "info" : "success",
        title: "Agent plan generated",
        detail: plan.preview.warnings[0] || `${plan.steps.length}  steps, ${plan.requires_approval ? "includes approval gate" : "no approval needed"}`,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "Agent plan failed", detail });
    } finally {
      setAgentBusy(false);
    }
  }

  async function runAgentChat(promptOverride?: string) {
    const prompt = (promptOverride ?? message).trim();
    if (!prompt && !agentPlan) {
      if (!promptOverride) setNotice({ tone: "info", title: "Please enter an agent goal", detail: "Generate a plan first, or run the agent directly." });
      return;
    }
    setAgentBusy(true);
    setNotice(null);
    try {
      const result = await api.runAgent({
        message: prompt || agentPlan?.message,
        project_id: selectedId ?? agentPlan?.project_id ?? null,
        selected_geometry: agentPayloadGeometry(),
        llm_config: llmConfig,
        plan: agentPlan ?? undefined,
      });
      setAgentPlan(result.agent);
      setLastRuntimeRun(result.run);
      appendRunToChatHistory(result.run);
      setNotice({
        tone: result.run.status === "completed" ? "success" : result.run.status === "awaiting_approval" ? "info" : "error",
        title: `Agent run — ${runtimeStatusLabel(result.run.status)}`,
        detail: result.run.summary || result.run.errors[0] || result.agent.preview.warnings[0] || result.agent.reply,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      if (!promptOverride) setNotice({ tone: "error", title: "Agent run failed", detail });
      else setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: `Agent error: ${detail}`, createdAt: new Date().toISOString() },
      ]);
    } finally {
      setAgentBusy(false);
    }
  }

  async function probeLocalAgents() {
    const result = await api.listLocalAgentCapabilities().catch(() => ({ adapters: [] as LocalAgentCapability[], available: [] as LocalAgentCapability[] }));
    setChatConnections((current) => mergeLocalAgentCapabilities(current, result.adapters));
    return result;
  }

  function stopAutopilotPoll() {
    if (autopilotPollTimerRef.current !== null) {
      window.clearTimeout(autopilotPollTimerRef.current);
      autopilotPollTimerRef.current = null;
    }
  }

  async function pollAutopilotRun(runId: string) {
    stopAutopilotPoll();
    const poll = async () => {
      try {
        const run = await api.getAutopilotRun(runId);
        setChatHistory((current) => {
          const index = current.findIndex((item) => item.autopilotRun?.run_id === runId);
          if (index === -1) return current;
          const updated = [...current];
          updated[index] = {
            ...updated[index],
            autopilotRun: run,
            errors: run.errors,
            body: summarizeAutopilotRun(run),
          };
          return updated;
        });

        if (run.status === "running") {
          autopilotPollTimerRef.current = window.setTimeout(poll, 3000);
        } else {
          autopilotPollTimerRef.current = null;
          setAgentBusy(false);
          setNotice({
            tone: run.status === "completed" ? "success" : run.status === "awaiting_approval" ? "info" : "error",
            title: `${autopilotAgentLabel(run)} — ${run.status}`,
            detail: summarizeAutopilotRun(run),
          });
        }
      } catch (err) {
        autopilotPollTimerRef.current = null;
        setAgentBusy(false);
        const detail = err instanceof Error ? err.message : String(err);
        setNotice({ tone: "error", title: "Agent poll failed", detail });
      }
    };
    autopilotPollTimerRef.current = window.setTimeout(poll, 3000);
  }

  async function runAutopilotAgent(promptOverride?: string, skipUserMsg = false) {
    const prompt = (promptOverride ?? message).trim();
    if (!prompt) {
      if (!promptOverride) setNotice({ tone: "info", title: "Please enter an agent goal", detail: "Agent needs a modeling, inspection or analysis goal." });
      return;
    }
    const isLlmApi = selectedChatConnection.id === "llm-api";
    const adapters = selectedChatConnection.adapters ?? [];
    const userPreferredId = localAgentConfig.preferredAdapterId;
    let preferredAdapter: LocalAgentCapability | undefined;
    if (!isLlmApi && userPreferredId) {
      preferredAdapter = adapters.find((item) => item.adapter_id === userPreferredId && item.status === "available");
    }
    if (!isLlmApi && !preferredAdapter) {
      preferredAdapter =
        adapters.find((item) => item.adapter_id === "claude-code" && item.status === "available") ??
        adapters.find((item) => item.status === "available");
    }
    if (!isLlmApi && !preferredAdapter) {
      const diagnostic = adapters[0]?.diagnostic || "No Claude Code or Codex CLI in non-interactive JSON mode detected.";
      setNotice({ tone: "info", title: "Local Agent unavailable", detail: diagnostic });
      if (!skipUserMsg) {
        setChatHistory((current) => [
          ...current,
          { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
        ]);
      }
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: `Local Agent unavailable: ${diagnostic}`, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
      return;
    }
    const adapterId = isLlmApi ? "llm-api" : preferredAdapter!.adapter_id;
    const agentLabel = isLlmApi ? "LLM Agent" : "Local Agent";
    stopAutopilotPoll();
    setAgentBusy(true);
    setNotice(null);
    try {
      const result = await api.runAutopilot({
        message: prompt,
        project_id: selectedId ?? null,
        selected_geometry: agentPayloadGeometry(),
        adapter_id: adapterId,
        ...(isLlmApi ? { llm_config: llmConfig } : {}),
        mode: "autopilot",
        dry_run: false,
      });
      if (!skipUserMsg) {
        setChatHistory((current) => [
          ...current,
          { id: createChatId(), role: "user", body: prompt, createdAt: new Date().toISOString(), mode: "runtime" },
        ]);
      }
      setChatHistory((current) => [
        ...current,
        {
          id: createChatId(),
          role: "assistant",
          body: summarizeAutopilotRun(result),
          createdAt: new Date().toISOString(),
          mode: "runtime",
          autopilotRun: result,
          errors: result.errors,
        },
      ]);
      if (result.status === "running") {
        void pollAutopilotRun(result.run_id);
      } else {
        setAgentBusy(false);
        setNotice({
          tone: result.status === "completed" ? "success" : result.status === "awaiting_approval" ? "info" : "error",
          title: `${agentLabel} — ${result.status}`,
          detail: summarizeAutopilotRun(result),
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: `${agentLabel} run failed`, detail });
      setChatHistory((current) => [
        ...current,
        { id: createChatId(), role: "assistant", body: `${agentLabel} error: ${detail}`, createdAt: new Date().toISOString(), mode: "runtime" },
      ]);
      setAgentBusy(false);
    }
  }

  async function updateAutopilotRun(runId: string, action: "approve" | "reject" | "cancel", userMessage?: string) {
    setAgentBusy(true);
    try {
      const result = action === "cancel"
        ? await api.cancelAutopilot(runId)
        : await api.continueAutopilot(runId, action === "approve", userMessage || null);
      setChatHistory((current) => current.map((entry) => (
        entry.autopilotRun?.run_id === runId
          ? {
              ...entry,
              body: summarizeAutopilotRun(result),
              autopilotRun: result,
              errors: result.errors,
            }
          : entry
      )));
      if (result.status === "running") {
        void pollAutopilotRun(runId);
      } else {
        setAgentBusy(false);
        setNotice({
          tone: result.status === "completed" ? "success" : result.status === "cancelled" ? "info" : "error",
          title: `${autopilotAgentLabel(result)} — ${result.status}`,
          detail: summarizeAutopilotRun(result),
        });
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: "error", title: "Agent update failed", detail });
      setAgentBusy(false);
    }
  }

  return {
    agentPlan,
    agentBusy,
    lastRuntimeRun,
    setAgentBusy,
    stopAutopilotPoll,
    createAgentPlanFromPrompt,
    runAgentChat,
    probeLocalAgents,
    runAutopilotAgent,
    updateAutopilotRun,
    approveRun,
    rejectRun,
  };
}
