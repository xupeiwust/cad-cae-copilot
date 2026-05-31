import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

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
import { useEncryptedLocalStorage } from "../hooks/useEncryptedLocalStorage";

const LLM_CONFIG_KEY = "llm_config";
const LOCAL_AGENT_CONFIG_KEY = "local_agent_config";

type UseRuntimeSettingsArgs = {
  setSummary: Dispatch<SetStateAction<ProjectSummary | null>>;
};

export function useRuntimeSettings({ setSummary }: UseRuntimeSettingsArgs) {
  const [runtime, setRuntime] = useState<RuntimeConfigSnapshot | null>(null);
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeConfig | null>(null);
  const [runtimeNotice, setRuntimeNotice] = useState<Notice | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [llmConfig, setLlmConfigState] = useState<LLMConfig>(DEFAULT_LLM_CONFIG);
  const [localAgentConfig, setLocalAgentConfigState] = useState<LocalAgentConfig>(DEFAULT_LOCAL_AGENT_CONFIG);
  const [apiKey, setApiKey] = useEncryptedLocalStorage(
    "aieng_api_key",
    "",
    { shouldRemove: (value) => !value },
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const settings = await api.getSettings();
        if (cancelled) return;
        const savedLlm = settings[LLM_CONFIG_KEY];
        if (savedLlm && typeof savedLlm === "object") {
          setLlmConfigState(normalizeLlmConfig(savedLlm as Record<string, unknown>));
        } else {
          const legacyLlm = readLegacyLlmConfig();
          if (legacyLlm) {
            setLlmConfigState(legacyLlm);
            void api.updateSetting(LLM_CONFIG_KEY, legacyLlm).catch(() => {});
          }
        }
        const savedLocal = settings[LOCAL_AGENT_CONFIG_KEY];
        if (savedLocal && typeof savedLocal === "object") {
          const parsed = savedLocal as Partial<LocalAgentConfig>;
          setLocalAgentConfigState({ preferredAdapterId: parsed.preferredAdapterId ?? null });
        } else {
          const legacyLocal = readLegacyLocalAgentConfig();
          if (legacyLocal) {
            setLocalAgentConfigState(legacyLocal);
            void api.updateSetting(LOCAL_AGENT_CONFIG_KEY, legacyLocal).catch(() => {});
          }
        }
      } catch {
        const legacyLlm = readLegacyLlmConfig();
        const legacyLocal = readLegacyLocalAgentConfig();
        if (legacyLlm && !cancelled) setLlmConfigState(legacyLlm);
        if (legacyLocal && !cancelled) setLocalAgentConfigState(legacyLocal);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  function setLlmConfig(value: LLMConfig | ((prev: LLMConfig) => LLMConfig)) {
    setLlmConfigState((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      void api.updateSetting(LLM_CONFIG_KEY, next).catch(() => {});
      return next;
    });
  }

  function setLocalAgentConfig(value: LocalAgentConfig | ((prev: LocalAgentConfig) => LocalAgentConfig)) {
    setLocalAgentConfigState((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      void api.updateSetting(LOCAL_AGENT_CONFIG_KEY, next).catch(() => {});
      return next;
    });
  }

  const runtimeReady = runtime?.probe.ready ?? false;
  const runtimeProvider = getProviderLabel(runtime?.config.provider);
  const llmReady = isLlmConfigReady(llmConfig);

  function applyRuntimeSnapshot(snapshot: RuntimeConfigSnapshot) {
    setRuntime(snapshot);
    setRuntimeDraft(snapshot.config);
  }

  function updateApiKey(key: string) {
    setApiKey(key);
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
        next.base_url = "";
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
    apiKey,
    runtimeReady,
    runtimeProvider,
    setRuntimeNotice,
    setLocalAgentConfig,
    applyRuntimeSnapshot,
    updateApiKey,
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

function readLegacyLlmConfig(): LLMConfig | null {
  try {
    const raw = window.localStorage.getItem(LLM_CONFIG_STORAGE_KEY);
    return raw ? normalizeLlmConfig(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

function readLegacyLocalAgentConfig(): LocalAgentConfig | null {
  try {
    const raw = window.localStorage.getItem(LOCAL_AGENT_CONFIG_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LocalAgentConfig>;
    return { preferredAdapterId: parsed.preferredAdapterId ?? null };
  } catch {
    return null;
  }
}
