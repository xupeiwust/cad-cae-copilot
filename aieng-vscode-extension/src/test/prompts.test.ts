import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { modifyPrompt, projectContextPrompt, starterPrompt } from "../prompts";

function assertBoundedPrompt(prompt: string): void {
  assert.match(prompt, /\.aieng|evidence/i);
  assert.match(prompt, /approval gates/i);
  assert.match(prompt, /structural adapter preflight\/capability status/i);
  assert.match(prompt, /FreeCADCmd, Gmsh, and CalculiX/);
  assert.match(prompt, /do not run solver tools|Do not run solver tools/i);
  assert.match(prompt, /claims/i);
  assert.doesNotMatch(prompt, /\b(ignore|skip|bypass) approval/i);
  assert.doesNotMatch(prompt, /\b(certified|certification|production-ready|validated for production)\b/i);
}

describe("agent handoff prompts", () => {
  it("bounds first-model generation with evidence and approval language", () => {
    const prompt = starterPrompt({ projectId: "p1", projectName: "Bracket" });

    assert.match(prompt, /create the first CAD model/);
    assert.match(prompt, /aieng\.agent_context/);
    assertBoundedPrompt(prompt);
  });

  it("bounds modification prompts and preserves selected face pointers", () => {
    const prompt = modifyPrompt({
      projectId: "p1",
      projectName: "Bracket",
      pointers: ["@face:f_top_001", "@face:f_side_002"],
    });

    assert.match(prompt, /modify project p1/);
    assert.match(prompt, /@face:f_top_001/);
    assert.match(prompt, /@face:f_side_002/);
    assertBoundedPrompt(prompt);
  });

  it("keeps project context copy descriptive instead of executable", () => {
    const prompt = projectContextPrompt({ projectId: "p1", projectName: "Bracket" });

    assert.match(prompt, /Project Bracket \(p1\)/);
    assert.doesNotMatch(prompt, /\b(run|execute|mutate|solve)\b/i);
  });
});
