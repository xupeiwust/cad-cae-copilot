import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { projectActivityFromEvent, projectIdFromEvent } from "../agentActivityModel";

describe("projectActivityFromEvent", () => {
  it("returns undefined for junk or events without a project id", () => {
    assert.equal(projectActivityFromEvent(null), undefined);
    assert.equal(projectActivityFromEvent("{bad json"), undefined);
    assert.equal(projectActivityFromEvent(JSON.stringify({ type: "tool_failed" })), undefined);
  });

  it("preserves the project id and event type", () => {
    const event = projectActivityFromEvent(JSON.stringify({
      type: "viewer_asset_changed",
      project_id: " p1 ",
    }));

    assert.equal(event?.type, "viewer_asset_changed");
    assert.equal(event?.projectId, "p1");
    assert.equal(projectIdFromEvent(JSON.stringify({ type: "x", project_id: "p2" })), "p2");
  });

  it("extracts top-level structured diagnostics", () => {
    const event = projectActivityFromEvent(JSON.stringify({
      type: "tool_failed",
      project_id: "p1",
      diagnostic: {
        code: "tool_execution_error",
        message: "RuntimeError: ccx failed",
        remediation: "Inspect the solver log.",
        tool_name: "cae.run_solver",
      },
    }));

    assert.deepEqual(event?.diagnostic, {
      code: "tool_execution_error",
      message: "RuntimeError: ccx failed",
      remediation: "Inspect the solver log.",
      toolName: "cae.run_solver",
    });
  });

  it("extracts payload diagnostics from runtime event-shaped activity", () => {
    const event = projectActivityFromEvent(JSON.stringify({
      type: "run_failed",
      project_id: "p1",
      payload: {
        tool: "cad.execute_build123d",
        diagnostic: {
          code: "tool_execution_error",
          message: "ValueError: bad input",
          remediation: "Fix the generated script and retry.",
        },
      },
    }));

    assert.deepEqual(event?.diagnostic, {
      code: "tool_execution_error",
      message: "ValueError: bad input",
      remediation: "Fix the generated script and retry.",
      toolName: "cad.execute_build123d",
    });
  });
});
