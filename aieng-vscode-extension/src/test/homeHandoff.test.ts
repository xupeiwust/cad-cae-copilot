import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildHomeHandoff } from "../homeHandoff";
import type { HomeStateMessage } from "../protocol";

function state(overrides: Partial<HomeStateMessage> = {}): HomeStateMessage {
  return {
    kind: "homeState",
    backendUrl: "http://127.0.0.1:8000",
    status: "connected",
    backendMode: "managed",
    projects: [],
    detail: "Managed backend running - no projects yet",
    startCommand: "conda run -n aieng311",
    agentMcp: {
      configured: true,
      sources: [".mcp.json"],
      detail: "AIENG tools available to your agent via .mcp.json",
    },
    ...overrides,
  };
}

describe("buildHomeHandoff", () => {
  it("blocks project handoff while the backend is unreachable", () => {
    const model = buildHomeHandoff(state({
      status: "unreachable",
      backendMode: "stopped",
      projects: [],
      detail: "Connection refused",
    }));

    assert.equal(model.backend.state, "blocked");
    assert.equal(model.project.state, "blocked");
    assert.equal(model.nextAction.label, "Start or reconnect backend");
    assert.equal(model.nextAction.prompt, null);
  });

  it("points users to the existing MCP setup path when agent tools are missing", () => {
    const model = buildHomeHandoff(state({
      agentMcp: {
        configured: false,
        sources: [],
        detail: "No aieng-workbench MCP server found in this workspace",
      },
    }));

    assert.equal(model.mcp.state, "blocked");
    assert.equal(model.nextAction.label, "Configure agent MCP");
    assert.match(model.nextAction.detail, /\.mcp\.json/);
    assert.match(model.nextAction.prompt ?? "", /aieng-workbench/);
    assert.match(model.nextAction.prompt ?? "", /package evidence/i);
  });

  it("selects the latest project and emits a bounded agent prompt", () => {
    const model = buildHomeHandoff(state({
      projects: [
        {
          id: "old",
          name: "Old bracket",
          status: "ready",
          updatedAt: "2026-06-25T00:00:00Z",
          namedParts: [],
        },
        {
          id: "new",
          name: "Pump bracket",
          status: "ready",
          updatedAt: "2026-06-27T00:00:00Z",
          namedParts: ["base", "gusset"],
        },
      ],
    }));

    assert.equal(model.project.selected?.id, "new");
    assert.equal(model.nextAction.label, "Continue Pump bracket");
    assert.match(model.nextAction.prompt ?? "", /project Pump bracket \(new\)/);
    assert.match(model.nextAction.prompt ?? "", /\.aieng evidence package/);
    assert.match(model.nextAction.prompt ?? "", /approval gates/);
    assert.match(model.nextAction.prompt ?? "", /Do not run solver tools/);
  });

  it("gives an import/setup prompt when backend and MCP are ready but no project exists", () => {
    const model = buildHomeHandoff(state());

    assert.equal(model.project.state, "missing");
    assert.equal(model.nextAction.label, "Create or import a project");
    assert.match(model.nextAction.prompt ?? "", /Set up an AIENG project/);
    assert.match(model.nextAction.prompt ?? "", /STEP or an existing \.aieng package/);
    assert.match(model.nextAction.prompt ?? "", /approval gates/);
  });
});
