import { useState } from "react";

import { api } from "../../api";
import {
  CAD_PROVIDER_OPTIONS,
  DEFAULT_LLM_CONFIG,
  LLM_PROVIDER_SUGGESTIONS,
} from "../../appConstants";
import type { Notice } from "../../appTypes";
import { getLlmProviderLabel } from "../../appUtils";
import { useI18n, type Language } from "../../i18n";
import type { LLMConfig, RuntimeConfig, RuntimeConfigSnapshot } from "../../types";
import { ActionIcon } from "../common";

type LlmProviderSettingsProps = {
  llmConfig: LLMConfig;
  llmReady: boolean;
  onChange<K extends keyof LLMConfig>(key: K, value: LLMConfig[K]): void;
  onPreset(provider: string): void;
  onRestore(): void;
  onTestResult?(status: "config_ok" | "conn_ok" | "error", message: string): void;
};

function LlmProviderSettings({
  llmConfig,
  llmReady,
  onChange,
  onPreset,
  onRestore,
  onTestResult,
}: LlmProviderSettingsProps) {
  const [testStatus, setTestStatus] = useState<"idle" | "testing_config" | "testing_conn" | "config_ok" | "conn_ok" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");

  async function handleTestConfig() {
    setTestStatus("testing_config");
    setTestMessage("");
    try {
      const result = await api.testLlmProvider(llmConfig, false);
      if (result.config_ready) {
        setTestStatus("config_ok");
        setTestMessage("配置可用 ✓");
        onTestResult?.("config_ok", "配置可用 ✓");
      } else {
        setTestStatus("error");
        setTestMessage(result.error_message || "配置不可用");
        onTestResult?.("error", result.error_message || "配置不可用");
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
      const result = await api.testLlmProvider(llmConfig, true);
      if (result.connection_verified) {
        setTestStatus("conn_ok");
        setTestMessage("连接已验证 ✓");
        onTestResult?.("conn_ok", "连接已验证 ✓");
      } else if (!result.config_ready) {
        setTestStatus("error");
        setTestMessage(result.error_message || "配置不可用");
        onTestResult?.("error", result.error_message || "配置不可用");
      } else {
        setTestStatus("error");
        setTestMessage(result.error_message || "连接验证失败");
        onTestResult?.("error", result.error_message || "连接验证失败");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setTestStatus("error");
      setTestMessage(msg);
      onTestResult?.("error", msg);
    }
  }

  return (
    <section className="drawer-section">
      <div className="drawer-section-heading">
        <div>
          <h3>LLM Provider</h3>
          <p>Agent plan、workflow 和 benchmark 共用这份模型配置。</p>
        </div>
        <div className={`llm-readiness-pill ${llmReady ? "ready" : "degraded"}`}>
          {llmReady ? "已配置" : "待配置"}
        </div>
      </div>

      <div className="llm-preset-row">
        {LLM_PROVIDER_SUGGESTIONS.map((provider) => (
          <button
            key={provider}
            type="button"
            className={llmConfig.provider === provider ? "ghost-button llm-preset active" : "ghost-button llm-preset"}
            onClick={() => onPreset(provider)}
          >
            {getLlmProviderLabel(provider)}
          </button>
        ))}
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
          <input value={llmConfig.model} onChange={(event) => onChange("model", event.target.value)} placeholder="configured-model" />
        </label>
        <label className="form-field">
          <span>API key env</span>
          <input
            value={llmConfig.api_key_env ?? ""}
            onChange={(event) => onChange("api_key_env", event.target.value)}
            placeholder="OPENAI_API_KEY"
          />
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
          恢复 LLM 默认
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={handleTestConfig}
          disabled={testStatus === "testing_config" || testStatus === "testing_conn"}
        >
          <ActionIcon name="test" />
          {testStatus === "testing_config" ? "检测中..." : "测试配置"}
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={handleVerifyConnection}
          disabled={testStatus === "testing_config" || testStatus === "testing_conn"}
        >
          <ActionIcon name="validate" />
          {testStatus === "testing_conn" ? "验证中..." : "验证连接"}
        </button>
      </div>
      {testStatus === "config_ok" && <div className="test-result ok">{testMessage}</div>}
      {testStatus === "conn_ok" && <div className="test-result ok">{testMessage}</div>}
      {testStatus === "error" && <div className="test-result error">{testMessage}</div>}
    </section>
  );
}

type RuntimeSettingsDrawerProps = {
  open: boolean;
  runtime: RuntimeConfigSnapshot | null;
  runtimeDraft: RuntimeConfig | null;
  runtimeBusy: boolean;
  runtimeNotice: Notice | null;
  runtimeProvider: string;
  runtimeReady: boolean;
  llmConfig: LLMConfig;
  llmReady: boolean;
  directApiKey: string;
  onDirectApiKeyChange(key: string): void;
  onClose(): void;
  onDraftChange<K extends keyof RuntimeConfig>(key: K, value: RuntimeConfig[K]): void;
  onLlmChange<K extends keyof LLMConfig>(key: K, value: LLMConfig[K]): void;
  onLlmPreset(provider: string): void;
  onLlmRestore(): void;
  onLlmTestResult?(status: "config_ok" | "conn_ok" | "error", message: string): void;
  onTest(): void;
  onSave(): void;
  onRestore(): void;
};

export function RuntimeSettingsDrawer({
  open,
  runtime,
  runtimeDraft,
  runtimeBusy,
  runtimeNotice,
  runtimeProvider,
  runtimeReady,
  llmConfig,
  llmReady,
  directApiKey,
  onDirectApiKeyChange,
  onClose,
  onDraftChange,
  onLlmChange,
  onLlmPreset,
  onLlmRestore,
  onLlmTestResult,
  onTest,
  onSave,
  onRestore,
}: RuntimeSettingsDrawerProps) {
  if (!open) return null;

  const keyMasked = directApiKey
    ? `${directApiKey.slice(0, 10)}${"•".repeat(Math.min(8, directApiKey.length - 10))}…`
    : "";

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="settings-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="环境设置"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-header">
          <div>
            <h2>环境设置</h2>
            <p>集中管理 LLM Provider 和 CAD Runtime。主工作区只显示当前状态与常用操作。</p>
          </div>
          <button type="button" className="ghost-button drawer-close" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="drawer-body">
          <section className="drawer-section">
            <div className="drawer-section-heading">
              <div>
                <h3>Anthropic API Key</h3>
                <p>Enables contextual chat, CAD generation, and FEA preprocessing. Paste your key to connect instantly.</p>
              </div>
              <div className={`llm-readiness-pill ${directApiKey ? "ready" : "degraded"}`}>
                {directApiKey ? "Connected" : "Not set"}
              </div>
            </div>
            <div className="api-key-input-row">
              <input
                type="password"
                className="api-key-input"
                value={directApiKey}
                onChange={(e) => onDirectApiKeyChange(e.target.value)}
                placeholder="sk-ant-api03-…"
                spellCheck={false}
                autoComplete="off"
                aria-label="Anthropic API key"
              />
              {directApiKey ? (
                <button
                  type="button"
                  className="ghost-button api-key-clear"
                  onClick={() => onDirectApiKeyChange("")}
                  title="Clear API key"
                >
                  Clear
                </button>
              ) : null}
            </div>
            {directApiKey ? (
              <p className="api-key-hint api-key-hint-ok">
                Key set: <code>{keyMasked}</code> — session only, cleared when you close this tab.
              </p>
            ) : (
              <p className="api-key-hint">
                No key set. Alternatively, set <code>ANTHROPIC_API_KEY</code> as an environment variable on the server before starting.
              </p>
            )}
          </section>

          <LlmProviderSettings
            llmConfig={llmConfig}
            llmReady={llmReady}
            onChange={onLlmChange}
            onPreset={onLlmPreset}
            onRestore={onLlmRestore}
            onTestResult={onLlmTestResult}
          />

          <section className="drawer-section">
            <div className="drawer-section-heading">
              <div>
                <h3>CAD Runtime</h3>
                <p>STEP 导入、预览、语义刷新和 FreeCAD MCP 能力使用这组配置。</p>
              </div>
            </div>

            <div className="runtime-config-grid">
              <label className="form-field">
                <span>CAD Provider</span>
                <select
                  value={runtimeDraft?.provider ?? "freecad"}
                  disabled={runtimeBusy}
                  onChange={(event) => onDraftChange("provider", event.target.value)}
                >
                  {CAD_PROVIDER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>Topology Backend</span>
                <select
                  value={runtimeDraft?.topology_backend ?? "auto"}
                  disabled={runtimeBusy}
                  onChange={(event) => onDraftChange("topology_backend", event.target.value)}
                >
                  <option value="auto">auto</option>
                  <option value="mock">mock</option>
                  <option value="occ">occ</option>
                </select>
              </label>
              <label className="form-field runtime-config-span">
                <span>FreeCAD Home</span>
                <input
                  value={runtimeDraft?.freecad_home ?? ""}
                  disabled={runtimeBusy}
                  onChange={(event) => onDraftChange("freecad_home", event.target.value)}
                  placeholder="FreeCAD 安装目录"
                />
              </label>
              <label className="form-field runtime-config-span">
                <span>FREECAD_MCP_ROOT</span>
                <input
                  value={runtimeDraft?.freecad_mcp_root ?? ""}
                  disabled={runtimeBusy}
                  onChange={(event) => onDraftChange("freecad_mcp_root", event.target.value)}
                  placeholder="aieng-freecad-mcp 仓库目录"
                />
              </label>
              <label className="form-field runtime-config-span">
                <span>AIENG_ROOT</span>
                <input
                  value={runtimeDraft?.aieng_root ?? ""}
                  disabled={runtimeBusy}
                  onChange={(event) => onDraftChange("aieng_root", event.target.value)}
                  placeholder="aieng 仓库目录"
                />
              </label>
            </div>

            <div className="action-row runtime-config-actions">
              <button disabled={!runtimeDraft || runtimeBusy} onClick={onTest}>
                <ActionIcon name="test" />
                测试 CAD 配置
              </button>
              <button disabled={!runtimeDraft || runtimeBusy} onClick={onSave}>
                <ActionIcon name="save" />
                保存 CAD 配置
              </button>
              <button disabled={!runtime?.defaults || runtimeBusy} onClick={onRestore}>
                <ActionIcon name="restore" />
                恢复 CAD 默认
              </button>
            </div>

            <div className="runtime-probe-grid">
              <div>
                <span>当前 Provider</span>
                <strong>{runtimeProvider}</strong>
              </div>
              <div>
                <span>运行时状态</span>
                <strong>{runtimeReady ? "已就绪" : "待配置"}</strong>
              </div>
              <div>
                <span>拓扑后端</span>
                <strong>{runtime?.probe.topology_backend_resolved ?? "-"}</strong>
              </div>
              <div>
                <span>FreeCADCmd</span>
                <strong>{runtime?.probe.freecad_cmd_exists ? "已找到" : "未找到"}</strong>
              </div>
            </div>
          </section>

          {runtime?.probe.issues?.length ? (
            <div className="summary-note">
              <strong>检测问题</strong>
              <p>{runtime.probe.issues.join("；")}</p>
            </div>
          ) : null}

          {runtime?.probe.bridge_error ? (
            <div className="summary-note">
              <strong>Bridge 探测</strong>
              <p>{runtime.probe.bridge_error}</p>
            </div>
          ) : null}

          {runtimeNotice ? (
            <div className={`result-banner result-${runtimeNotice.tone}`}>
              <strong>{runtimeNotice.title}</strong>
              <span>{runtimeNotice.detail}</span>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

type GlobalSettingsDrawerProps = {
  open: boolean;
  onClose(): void;
};

const LANGUAGE_OPTIONS: Array<{ value: Language; label: string; description: string }> = [
  { value: "en", label: "English", description: "Default" },
  { value: "zh-CN", label: "中文", description: "简体中文" },
];

export function GlobalSettingsDrawer({ open, onClose }: GlobalSettingsDrawerProps) {
  const { language, setLanguage } = useI18n();
  const currentLanguage = LANGUAGE_OPTIONS.find((option) => option.value === language) ?? LANGUAGE_OPTIONS[0];

  if (!open) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="settings-drawer global-settings-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="全局设置"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-header">
          <div>
            <h2>全局设置</h2>
            <p>管理工作台偏好和界面显示。环境配置仍保留在专用抽屉中。</p>
          </div>
          <button type="button" className="ghost-button drawer-close" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="drawer-body">
          <section className="drawer-section">
            <div className="drawer-section-heading">
              <div>
                <h3>界面设置</h3>
                <p>选择工作台界面的显示语言。</p>
              </div>
            </div>

            <div className="global-setting-row">
              <div>
                <strong>语言</strong>
                <span>当前语言: <span data-i18n-skip>{currentLanguage.label}</span></span>
              </div>
              <div className="language-choice-group" role="radiogroup" aria-label="语言">
                {LANGUAGE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={language === option.value ? "ghost-button language-choice active" : "ghost-button language-choice"}
                    aria-pressed={language === option.value}
                    onClick={() => setLanguage(option.value)}
                  >
                    <strong data-i18n-skip>{option.label}</strong>
                    <small data-i18n-skip>{option.description}</small>
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}
