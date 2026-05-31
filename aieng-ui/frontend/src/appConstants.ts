import type { ChatConnection, LLMConfig } from "./types";
import type { StageItem } from "./appTypes";

export const BASE_STAGES: StageItem[] = [
  { key: "upload", label: "Upload", detail: "Place STEP file into project", state: "idle" },
  { key: "import", label: "Import", detail: "Generate .aieng package and extract topology", state: "idle" },
  { key: "preview", label: "Preview", detail: "Generate 3D preview model", state: "idle" },
  { key: "semantic", label: "Semantic", detail: "Sync manifest, topology and summary", state: "idle" },
];

export const CAD_PROVIDER_OPTIONS = [
  { value: "build123d", label: "build123d / OCP" },
  { value: "freecad", label: "FreeCAD (optional adapter)" },
] as const;
export const LLM_CONFIG_STORAGE_KEY = "aieng-ui.llm-config";
export const LOCAL_AGENT_CONFIG_STORAGE_KEY = "aieng-ui.local-agent-config";
export const CHAT_CONNECTION_ID_STORAGE_KEY = "aieng-ui.chat-connection-id";
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
  api_key: null,
  temperature: 0,
  top_p: 1,
  max_output_tokens: 8192,
  input_price_per_million_tokens: null,
  output_price_per_million_tokens: null,
};
export const DEFAULT_LOCAL_AGENT_CONFIG = {
  preferredAdapterId: null as string | null,
};
export const EMPTY_CAE_FIELDS: string[] = [];

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
    id: "external-cad-adapter",
    label: "External CAD adapter",
    transport: "optional-cad-bridge",
    status: "degraded",
    detail: "Optional bridge for external preview/export adapters; build123d remains the default modelling path.",
    requires_project: true,
    supports_llm: false,
    supports_execution: true,
    approval_gated: true,
    tool_count: 0,
  },
];
