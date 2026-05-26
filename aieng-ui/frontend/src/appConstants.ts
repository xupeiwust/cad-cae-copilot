import type { ChatConnection, LLMConfig } from "./types";
import type { ControlPaneMode, StageItem } from "./appTypes";

export const BASE_STAGES: StageItem[] = [
  { key: "upload", label: "Upload STEP", detail: "Put the selected STEP file into the project", state: "idle" },
  { key: "import", label: "Import aieng", detail: "Generate the .aieng package and enrich topology, AAG, features, and summary", state: "idle" },
  { key: "preview", label: "Generate preview", detail: "Run the FreeCADCmd preview pipeline and prefer GLB output", state: "idle" },
  { key: "semantic", label: "Refresh semantics", detail: "Sync manifest, topology, validation, and summary", state: "idle" },
];

export const CAD_PROVIDER_OPTIONS = [{ value: "freecad", label: "FreeCAD" }] as const;
export const LLM_CONFIG_STORAGE_KEY = "aieng-ui.llm-config";
export const LLM_PROVIDER_SUGGESTIONS = ["openai-compatible", "anthropic", "openai", "azure-openai"] as const;
export const CHAT_SUGGESTIONS = [
  "Summarize the current model semantics and main risks",
  "Check whether the current package is ready for a patch",
  "Give safe weight-reduction steps without changing protected regions",
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
  { id: "chat", label: "Intelligent orchestration", detail: "Chat, planning, and approval" },
  { id: "project", label: "Project data", detail: "Import and semantic summary" },
  { id: "agent", label: "Capability center", detail: "Tools, workflows, and benchmarks" },
  { id: "cae", label: "CAE evidence", detail: "Simulation setup and results" },
  { id: "recommend", label: "Recommendations", detail: "Phase 36 proposals + Phase 37 verification" },
  { id: "copilot", label: "Copilot Loop", detail: "Evidence-grounded closed-loop stepper" },
  { id: "pilot", label: "Intent Planner", detail: "Natural-language pilot console (preview-only)" },
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
