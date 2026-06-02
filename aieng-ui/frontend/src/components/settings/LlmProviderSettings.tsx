import { useState } from "react";

import { api } from "../../api";
import { DEFAULT_LLM_CONFIG, LLM_CONFIG_TEMPLATES, LLM_PROVIDER_SUGGESTIONS } from "../../appConstants";
import type { LLMConfig } from "../../types";
import { ActionIcon } from "../common";

type LlmProviderSettingsProps = {
  llmConfig: LLMConfig;
  llmReady: boolean;
  apiKey: string;
  onChange<K extends keyof LLMConfig>(key: K, value: LLMConfig[K]): void;
  onApiKeyChange(value: string): void;
  onPreset(provider: string): void;
  onRestore(): void;
  onTestResult?(status: "config_ok" | "conn_ok" | "error", message: string): void;
};

export function LlmProviderSettings({
  llmConfig,
  llmReady,
  apiKey,
  onChange,
  onApiKeyChange,
  onPreset,
  onRestore,
  onTestResult,
}: LlmProviderSettingsProps) {
  const [testStatus, setTestStatus] = useState<"idle" | "testing_config" | "testing_conn" | "config_ok" | "conn_ok" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");
  const isBusy = testStatus === "testing_config" || testStatus === "testing_conn";

  const keyMasked = apiKey
    ? `${apiKey.slice(0, 10)}${"•".repeat(Math.min(8, apiKey.length - 10))}…`
    : "";
  const selectedTemplate = LLM_CONFIG_TEMPLATES.find((template) => (
    llmConfig.provider === template.provider &&
    llmConfig.model === template.model &&
    (llmConfig.base_url ?? "") === template.base_url
  ));

  async function handleTestConfig() {
    setTestStatus("testing_config");
    setTestMessage("");
    try {
      const result = await api.testLlmProvider(llmConfig, apiKey, false);
      if (result.config_ready) {
        setTestStatus("config_ok");
        setTestMessage("Configuration usable");
        onTestResult?.("config_ok", "Configuration usable");
      } else {
        setTestStatus("error");
        setTestMessage(result.error_message || "Configuration not usable");
        onTestResult?.("error", result.error_message || "Configuration not usable");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setTestStatus("error");
      setTestMessage(msg);
      onTestResult?.("error", msg);
    }
  }

  async function handleVerifyConnection() {
    setTestStatus("testing_conn");
    setTestMessage("");
    try {
      const result = await api.testLlmProvider(llmConfig, apiKey, true);
      if (result.connection_verified) {
        setTestStatus("conn_ok");
        setTestMessage("Connection verified");
        onTestResult?.("conn_ok", "Connection verified");
      } else if (!result.config_ready) {
        setTestStatus("error");
        setTestMessage(result.error_message || "Configuration not usable");
        onTestResult?.("error", result.error_message || "Configuration not usable");
      } else {
        setTestStatus("error");
        setTestMessage(result.error_message || "Connection verification failed");
        onTestResult?.("error", result.error_message || "Connection verification failed");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setTestStatus("error");
      setTestMessage(msg);
      onTestResult?.("error", msg);
    }
  }

  const statusTone =
    testStatus === "config_ok" || testStatus === "conn_ok"
      ? "ok"
      : testStatus === "error"
        ? "error"
        : null;

  return (
    <section className="drawer-section">
      <div className="drawer-section-heading">
        <div>
          <h3>LLM Provider</h3>
          <p>Agent plans, workflows, and benchmarks share this model configuration.</p>
        </div>
        <div className={`llm-readiness-pill ${llmReady ? "ready" : "degraded"}`}>
          {llmReady ? "Configured" : "Needs config"}
        </div>
      </div>

      <div className="llm-template-panel">
        <label className="form-field llm-template-select">
          <span>Template</span>
          <select
            value={selectedTemplate?.id ?? ""}
            onChange={(event) => {
              if (event.target.value) onPreset(event.target.value);
            }}
          >
            {LLM_CONFIG_TEMPLATES.map((template) => (
              <option key={template.id} value={template.id}>
                {template.label} - {template.detail}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="runtime-config-grid llm-config-grid">
        <label className="form-field">
          <span>Provider</span>
          <input
            list="llm-provider-options"
            value={llmConfig.provider}
            onChange={(event) => onChange("provider", event.target.value)}
            placeholder="openai-compatible"
          />
          <datalist id="llm-provider-options">
            {LLM_PROVIDER_SUGGESTIONS.map((provider) => (
              <option key={provider} value={provider} />
            ))}
          </datalist>
        </label>
        <label className="form-field">
          <span>Model</span>
          <input
            value={llmConfig.model}
            onChange={(event) => onChange("model", event.target.value)}
            placeholder="configured-model"
          />
        </label>
        <label className="form-field runtime-config-span">
          <span>API Key</span>
          <div className="api-key-input-row">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder="sk-ant-api03-… or sk-…"
              spellCheck={false}
              autoComplete="off"
            />
            {apiKey ? (
              <button
                type="button"
                className="ghost-button api-key-clear"
                onClick={() => onApiKeyChange("")}
                title="Clear"
              >
                Clear
              </button>
            ) : null}
          </div>
          {apiKey ? (
            <p className="api-key-hint api-key-hint-ok">
              Key set: <code>{keyMasked}</code> — stored in app database and locally.
            </p>
          ) : (
            <p className="api-key-hint">
              No key set. Set an environment variable on the server as an alternative.
            </p>
          )}
        </label>
        <label className="form-field">
          <span>Base URL</span>
          <input
            value={llmConfig.base_url ?? ""}
            onChange={(event) => onChange("base_url", event.target.value)}
            placeholder="https://api.openai.com/v1"
          />
        </label>
        <label className="form-field">
          <span>Temperature</span>
          <input
            type="number"
            min="0"
            max="2"
            step="0.1"
            value={llmConfig.temperature}
            onChange={(event) => onChange("temperature", Number(event.target.value) || 0)}
          />
        </label>
        <label className="form-field">
          <span>Top P</span>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={llmConfig.top_p}
            onChange={(event) => onChange("top_p", Number(event.target.value) || 1)}
          />
        </label>
        <label className="form-field runtime-config-span">
          <span>Max output tokens</span>
          <input
            type="number"
            min="256"
            step="256"
            value={llmConfig.max_output_tokens}
            onChange={(event) => onChange("max_output_tokens", Number(event.target.value) || DEFAULT_LLM_CONFIG.max_output_tokens)}
          />
        </label>
      </div>

      <div className="action-row runtime-config-actions">
        <button type="button" className="ghost-button" onClick={onRestore}>
          <ActionIcon name="restore" />
          Restore defaults
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={handleTestConfig}
          disabled={isBusy}
        >
          <ActionIcon name="test" />
          {testStatus === "testing_config" ? "Checking..." : "Test config"}
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={handleVerifyConnection}
          disabled={isBusy}
        >
          <ActionIcon name="validate" />
          {testStatus === "testing_conn" ? "Verifying..." : "Verify"}
        </button>
      </div>

      {statusTone && (
        <div className={`test-result ${statusTone}`}>
          {testStatus === "config_ok" && "✓ "}
          {testStatus === "conn_ok" && "✓ "}
          {testMessage}
        </div>
      )}
    </section>
  );
}
