import { useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import {
  DEFAULT_LLM_CONFIG,
  DEFAULT_LOCAL_AGENT_CONFIG,
  LLM_CONFIG_STORAGE_KEY,
  LOCAL_AGENT_CONFIG_STORAGE_KEY,
} from "../appConstants";
import type { Notice } from "../appTypes";
import {
  getProviderLabel,
  getRuntimeDetail,
  isLlmConfigReady,
  normalizeLlmConfig,
} from "../appUtils";
import type {
  LLMConfig,
  LocalAgentConfig,
  ProjectSummary,
  RuntimeConfig,
  RuntimeConfigSnapshot,
} from "../types";
import { useBrowserStorageState } from "./useBrowserStorageState";

type UseRuntimeSettingsArgs = {
  setSummary: Dispatch<SetStateAction<ProjectSummary | null>>;
};

export function useRuntimeSettings({ setSummary }: UseRuntimeSettingsArgs) {
  const [runtime, setRuntime] = useState<RuntimeConfigSnapshot | null>(null);
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeConfig | null>(null);
  const [runtimeNotice, setRuntimeNotice] = useState<Notice | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [llmConfig, setLlmConfig] = useBrowserStorageState<LLMConfig>(
    LLM_CONFIG_STORAGE_KEY,
    DEFAULT_LLM_CONFIG,
    {
      storage: "local",
      deserialize: (raw) => normalizeLlmConfig(JSON.parse(raw)),
    },
  );
  const [localAgentConfig, setLocalAgentConfig] = useBrowserStorageState<LocalAgentConfig>(
    LOCAL_AGENT_CONFIG_STORAGE_KEY,
    DEFAULT_LOCAL_AGENT_CONFIG,
    {
      storage: "local",
      deserialize: (raw) => {
        const parsed = JSON.parse(raw) as Partial<LocalAgentConfig>;
        return { preferredAdapterId: parsed.preferredAdapterId ?? null };
      },
    },
  );
  const [directApiKey, setDirectApiKey] = useBrowserStorageState<string>(
    "aieng_api_key",
    "",
    {
      storage: "session",
      deserialize: (raw) => raw,
      serialize: (value) => value,
      shouldRemove: (value) => !value,
    },
  );

  const runtimeReady = runtime?.probe.ready ?? false;
  const runtimeProvider = getProviderLabel(runtime?.config.provider);
  const llmReady = isLlmConfigReady(llmConfig);

  function applyRuntimeSnapshot(snapshot: RuntimeConfigSnapshot) {
    setRuntime(snapshot);
    setRuntimeDraft(snapshot.config);
  }

  function updateDirectApiKey(key: string) {
    setDirectApiKey(key);
  }

  function updateRuntimeDraft<K extends keyof RuntimeConfig>(key: K, value: RuntimeConfig[K]) {
    setRuntimeDraft((current) => current ? { ...current, [key]: value } : current);
  }

  function syncRuntimeIntoSummary(snapshot: RuntimeConfigSnapshot) {
    setSummary((current) => current ? { ...current, integration: snapshot } : current);
  }

  function restoreRuntimeDefaults() {
    if (!runtime?.defaults) return;
    setRuntimeDraft(runtime.defaults);
    setRuntimeNotice({ tone: "info", title: "Defaults restored", detail: "Default CAD config restored. Save to apply." });
  }

  async function runRuntimeTask(kind: "save" | "test", task: () => Promise<RuntimeConfigSnapshot>) {
    if (!runtimeDraft) return;
    setRuntimeBusy(true);
    setRuntimeNotice(null);
    try {
      const snapshot = await task();
      applyRuntimeSnapshot(snapshot);
      syncRuntimeIntoSummary(snapshot);
      setRuntimeNotice({
        tone: snapshot.probe.ready ? "success" : "info",
        title: kind === "save" ? "CAD config saved" : "CAD config tested",
        detail: getRuntimeDetail(snapshot),
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setRuntimeNotice({ tone: "error", title: "CAD config operation failed", detail });
    } finally {
      setRuntimeBusy(false);
    }
  }

  function updateLlmConfig<K extends keyof LLMConfig>(key: K, value: LLMConfig[K]) {
    setLlmConfig((current) => ({ ...current, [key]: value }));
  }

  function handleLlmTestResult(status: "config_ok" | "conn_ok" | "error", message: string) {
    setRuntimeNotice(
      status === "config_ok" || status === "conn_ok"
        ? { tone: "success", title: "LLM test passed", detail: message }
        : { tone: "error", title: "LLM test failed", detail: message },
    );
  }

  function applyLlmProviderPreset(provider: string) {
    setLlmConfig((current) => {
      const next = { ...current, provider };
      if (provider === "anthropic") {
        next.api_key_env = "ANTHROPIC_API_KEY";
        next.base_url = "";
      } else if (provider === "azure-openai") {
        next.api_key_env = "AZURE_OPENAI_API_KEY";
      } else {
        next.api_key_env = "OPENAI_API_KEY";
      }
      return next;
    });
  }

  function restoreDefaultLlmConfig() {
    setLlmConfig({ ...DEFAULT_LLM_CONFIG });
  }

  return {
    runtime,
    runtimeDraft,
    runtimeNotice,
    runtimeBusy,
    llmConfig,
    llmReady,
    localAgentConfig,
    directApiKey,
    runtimeReady,
    runtimeProvider,
    setRuntimeNotice,
    setLocalAgentConfig,
    applyRuntimeSnapshot,
    updateDirectApiKey,
    updateRuntimeDraft,
    restoreRuntimeDefaults,
    runRuntimeTask,
    updateLlmConfig,
    handleLlmTestResult,
    applyLlmProviderPreset,
    restoreDefaultLlmConfig,
    testRuntimeConfig: () => api.testRuntimeConfig(runtimeDraft!),
    updateRuntimeConfig: () => api.updateRuntimeConfig(runtimeDraft!),
  };
}
