import { describe, expect, test } from "vitest";

import type { ChatConnection, LocalAgentCapability, RuntimeConfigSnapshot } from "../../types";
import { deriveConnectionHealth } from "./ConnectionHealthBar";

const claudeAdapter: LocalAgentCapability = {
  adapter_id: "claude-code",
  label: "Claude Code CLI",
  status: "available",
  command: "claude",
  command_path: "C:/Users/example/.local/bin/claude.exe",
  version: "2.1.141",
  supports_non_interactive: true,
  supports_json: true,
  supports_json_schema: true,
  supports_tool_disable: true,
  diagnostic: "Safe non-interactive JSON mode detected.",
  probe_duration_ms: 120,
};

const codexMissingAdapter: LocalAgentCapability = {
  adapter_id: "codex-cli",
  label: "Codex CLI",
  status: "missing",
  command: "codex",
  command_path: null,
  version: null,
  supports_non_interactive: false,
  supports_json: false,
  supports_json_schema: false,
  supports_tool_disable: false,
  diagnostic: "Command not found on PATH: codex",
  probe_duration_ms: 7,
};

function localAgent(adapters: LocalAgentCapability[] = [claudeAdapter]): ChatConnection {
  return {
    id: "local-agent",
    label: "Local agents",
    transport: "agent-cli-bridge",
    status: "ready",
    detail: "Local agent bridge is ready.",
    requires_project: true,
    supports_llm: false,
    supports_execution: true,
    approval_gated: true,
    tool_count: 47,
    adapters,
  };
}

function llmApi(detail = "Configure an API key."): ChatConnection {
  return {
    id: "llm-api",
    label: "LLM API",
    transport: "provider-api",
    status: "configurable",
    detail,
    requires_project: false,
    supports_llm: true,
    supports_execution: true,
    approval_gated: false,
    tool_count: 47,
  };
}

function runtimeSnapshot(overrides: Partial<RuntimeConfigSnapshot["probe"]> = {}): RuntimeConfigSnapshot {
  return {
    config: {
      provider: "build123d",
      aieng_root: "",
      freecad_mcp_root: "",
      freecad_home: "",
      topology_backend: "occ",
    },
    defaults: {
      provider: "build123d",
      aieng_root: "",
      freecad_mcp_root: "",
      freecad_home: "",
      topology_backend: "occ",
    },
    probe: {
      provider: "build123d",
      topology_backend_requested: "occ",
      topology_backend_resolved: "occ",
      aieng_root: "",
      aieng_src_exists: true,
      freecad_mcp_root: "",
      freecad_mcp_src_exists: false,
      freecad_home: "",
      freecad_cmd: "",
      freecad_python: "",
      freecad_cmd_exists: false,
      freecad_python_exists: false,
      build123d_available: true,
      ocp_available: true,
      ready: true,
      issues: [],
      ...overrides,
    },
    config_path: "runtime.json",
    persisted_exists: true,
  };
}

function byId(badges: ReturnType<typeof deriveConnectionHealth>, id: string) {
  const badge = badges.find((item) => item.id === id);
  if (!badge) throw new Error(`Missing badge ${id}`);
  return badge;
}

describe("deriveConnectionHealth", () => {
  test("Claude Code available, runtime ready, and live events derive ready badges", () => {
    const badges = deriveConnectionHealth({
      chatConnections: [localAgent()],
      selectedConnectionId: "local-agent",
      llmReady: true,
      liveSyncStatus: "live",
      liveSyncDetail: "Live updates connected",
      runtime: runtimeSnapshot(),
      runtimeReady: true,
      runtimeProvider: "build123d / OCP",
    });

    expect(badges.map((badge) => badge.tone)).toEqual(["ready", "ready", "ready", "ready"]);
    expect(byId(badges, "agent").status).toBe("Claude Code CLI ready");
  });

  test("Codex missing is surfaced without blocking an available Claude adapter", () => {
    const badges = deriveConnectionHealth({
      chatConnections: [localAgent([claudeAdapter, codexMissingAdapter])],
      selectedConnectionId: "local-agent",
      llmReady: true,
      liveSyncStatus: "live",
      runtime: runtimeSnapshot(),
      runtimeReady: true,
      runtimeProvider: "build123d / OCP",
    });

    const agent = byId(badges, "agent");
    expect(agent.tone).toBe("warning");
    expect(agent.detail).toContain("Codex CLI");
    expect(agent.detail).toContain("Command not found");
  });

  test("LLM API selected without key shows a warning", () => {
    const agent = byId(deriveConnectionHealth({
      chatConnections: [llmApi("OpenAI API key is not configured.")],
      selectedConnectionId: "llm-api",
      llmReady: false,
      liveSyncStatus: "live",
      runtime: runtimeSnapshot(),
      runtimeReady: true,
      runtimeProvider: "build123d / OCP",
    }), "agent");

    expect(agent.tone).toBe("warning");
    expect(agent.status).toBe("LLM needs key");
    expect(agent.detail).toContain("API key");
  });

  test("polling and reconnecting event states warn instead of pretending to be live", () => {
    const polling = deriveConnectionHealth({
      chatConnections: [localAgent()],
      selectedConnectionId: "local-agent",
      llmReady: true,
      liveSyncStatus: "polling",
      runtime: runtimeSnapshot(),
      runtimeReady: true,
      runtimeProvider: "build123d / OCP",
    });
    expect(byId(polling, "events").tone).toBe("warning");
    expect(byId(polling, "events").status).toBe("Polling");

    const reconnecting = deriveConnectionHealth({
      chatConnections: [localAgent()],
      selectedConnectionId: "local-agent",
      llmReady: true,
      liveSyncStatus: "reconnecting",
      runtime: runtimeSnapshot(),
      runtimeReady: true,
      runtimeProvider: "build123d / OCP",
    });
    expect(byId(reconnecting, "events").tone).toBe("warning");
    expect(byId(reconnecting, "events").status).toBe("Reconnecting");
  });

  test("runtime degraded and missing states use warning/error tones", () => {
    const degraded = byId(deriveConnectionHealth({
      chatConnections: [localAgent()],
      selectedConnectionId: "local-agent",
      llmReady: true,
      liveSyncStatus: "live",
      runtime: runtimeSnapshot({ ready: false, issues: ["Topology probe warning"] }),
      runtimeReady: false,
      runtimeProvider: "build123d / OCP",
    }), "runtime");
    expect(degraded.tone).toBe("warning");
    expect(degraded.status).toBe("Degraded");

    const missing = byId(deriveConnectionHealth({
      chatConnections: [localAgent()],
      selectedConnectionId: "local-agent",
      llmReady: true,
      liveSyncStatus: "live",
      runtime: runtimeSnapshot({ ready: false, ocp_available: false, issues: ["OCP missing"] }),
      runtimeReady: false,
      runtimeProvider: "build123d / OCP",
    }), "runtime");
    expect(missing.tone).toBe("error");
    expect(missing.status).toBe("Missing");
  });

  test("no data yet derives loading states and no processing state", () => {
    const badges = deriveConnectionHealth({
      chatConnections: [],
      selectedConnectionId: "local-agent",
      llmReady: false,
      liveSyncStatus: undefined,
      runtime: null,
      runtimeReady: null,
      runtimeProvider: null,
    });

    expect(byId(badges, "backend").tone).toBe("loading");
    expect(byId(badges, "events").tone).toBe("loading");
    expect(byId(badges, "agent").status).toBe("Loading");
    expect(byId(badges, "runtime").status).toBe("Checking");
    expect(badges.some((badge) => /processing|working/i.test(badge.status))).toBe(false);
  });

  test("selected connection blocked detail uses the blocked reason", () => {
    const agent = byId(deriveConnectionHealth({
      chatConnections: [localAgent()],
      selectedConnectionId: "local-agent",
      selectedConnectionBlocked: true,
      llmReady: true,
      liveSyncStatus: "live",
      runtime: runtimeSnapshot(),
      runtimeReady: true,
      runtimeProvider: "build123d / OCP",
    }), "agent");

    expect(agent.tone).toBe("error");
    expect(agent.detail).toBe("Local agent bridge is ready.");
  });
});
