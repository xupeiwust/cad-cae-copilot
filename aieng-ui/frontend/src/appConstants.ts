import type { ChatConnection, LLMConfig } from "./types";
import type { ControlPaneMode, StageItem, WorkbenchPaneMode } from "./appTypes";

export const BASE_STAGES: StageItem[] = [
  { key: "upload", label: "上传", detail: "将 STEP 文件放入项目", state: "idle" },
  { key: "import", label: "导入", detail: "生成 .aieng 包并提取拓扑和特征", state: "idle" },
  { key: "preview", label: "预览", detail: "生成 3D 预览模型", state: "idle" },
  { key: "semantic", label: "语义", detail: "同步清单、拓扑和摘要", state: "idle" },
];

export const CAD_PROVIDER_OPTIONS = [{ value: "freecad", label: "FreeCAD" }] as const;
export const AI_FIRST_WORKBENCH_ENABLED = true;
export const LLM_CONFIG_STORAGE_KEY = "aieng-ui.llm-config";
export const LLM_PROVIDER_SUGGESTIONS = ["openai-compatible", "anthropic", "openai", "azure-openai"] as const;
export const CHAT_SUGGESTIONS = [
  "总结当前模型的语义和主要风险",
  "检查当前包是否准备好接受修改",
  "给出不改变保护区域的安全减重步骤",
] as const;

export const DEFAULT_LLM_CONFIG: LLMConfig = {
  provider: "openai-compatible",
  model: "configured-model",
  base_url: "",
  api_key_env: "OPENAI_API_KEY",
  temperature: 0,
  top_p: 1,
  max_output_tokens: 8192,
  input_price_per_million_tokens: null,
  output_price_per_million_tokens: null,
};
export const EMPTY_CAE_FIELDS: string[] = [];

export const CONTROL_PANE_MODES: Array<{ id: ControlPaneMode; label: string; detail: string }> = [
  { id: "chat", label: "对话", detail: "聊天、规划和审批" },
  { id: "project", label: "项目", detail: "导入和语义摘要" },
  { id: "agent", label: "工具", detail: "工具、工作流和基准测试" },
  { id: "cae", label: "仿真", detail: "仿真设置和结果" },
  { id: "recommend", label: "推荐", detail: "修改建议和验证" },
  { id: "copilot", label: "Copilot", detail: "闭环优化" },
  { id: "pilot", label: "规划", detail: "自然语言任务规划" },
];

export const WORKBENCH_PANE_MODES: Array<{ id: WorkbenchPaneMode; label: string; detail: string }> = [
  { id: "agent", label: "Agent", detail: "Chat, plans, approvals" },
  { id: "project", label: "Project", detail: "Import and project facts" },
  { id: "debug", label: "Debug", detail: "Tools and raw workflow panels" },
];

export const DEFAULT_CHAT_CONNECTIONS: ChatConnection[] = [
  {
    id: "llm-api",
    label: "LLM API",
    transport: "provider-api",
    status: "configurable",
    detail: "Model provider planning with local runtime execution.",
    requires_project: false,
    supports_llm: true,
    supports_execution: true,
    approval_gated: true,
    tool_count: 0,
  },
  {
    id: "local-agent",
    label: "Local Agent",
    transport: "agent-cli-bridge",
    status: "blocked",
    detail: "Uses local Claude Code or Codex CLI through Workbench approvals.",
    requires_project: false,
    supports_llm: true,
    supports_execution: true,
    approval_gated: true,
    tool_count: 0,
    adapters: [],
  },
  {
    id: "local-runtime",
    label: "Local runtime",
    transport: "fastapi-runtime",
    status: "ready",
    detail: "Local rule orchestration without an API key.",
    requires_project: false,
    supports_llm: false,
    supports_execution: true,
    approval_gated: true,
    tool_count: 0,
  },
  {
    id: "mcp-bridge",
    label: "MCP bridge",
    transport: "freecad-mcp",
    status: "degraded",
    detail: "Bridges guardrails, patch parsing, and preflight.",
    requires_project: true,
    supports_llm: false,
    supports_execution: true,
    approval_gated: true,
    tool_count: 0,
  },
  {
    id: "freecad-desktop",
    label: "FreeCAD desktop",
    transport: "freecadcmd-bridge",
    status: "degraded",
    detail: "Runs geometry checks and controlled CAD actions through FreeCADCmd.",
    requires_project: true,
    supports_llm: false,
    supports_execution: true,
    approval_gated: true,
    tool_count: 0,
  },
];
