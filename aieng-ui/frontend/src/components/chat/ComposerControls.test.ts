import { test } from "vitest";

import { getComposerActionState } from "./ComposerControls";

test("composer action state", () => {
  const base = {
    message: "",
    selectedConnectionId: "local-agent",
    selectedConnectionBlocked: false,
    llmReady: true,
    activeRunId: null as string | null,
    agentProcessing: false,
  };

  // Active run, genuinely processing, empty input -> Stop.
  let s = getComposerActionState({ ...base, activeRunId: "r1", agentProcessing: true });
  expectEqual(s.mode, "stop", "processing + empty -> stop");
  expectEqual(s.disabled, false, "stop enabled when run has id");
  expectEqual(s.title, "Stop active agent run", "stop title");

  // Active run but NOT processing (stale running) -> Send (no Stop).
  s = getComposerActionState({ ...base, activeRunId: "r1", agentProcessing: false });
  expectEqual(s.mode, "send", "active but not processing -> send");
  expectEqual(s.disabled, true, "send disabled with empty message");

  // Active run, processing, but the user typed something -> Send (message wins).
  s = getComposerActionState({ ...base, message: "add a rib", activeRunId: "r1", agentProcessing: true });
  expectEqual(s.mode, "send", "processing + non-empty message -> send");
  expectEqual(s.disabled, false, "send enabled with a message");

  // Stop mode but the run has no id -> disabled.
  s = getComposerActionState({ ...base, activeRunId: "", agentProcessing: true });
  expectEqual(s.mode, "stop", "empty run id still active -> stop");
  expectEqual(s.disabled, true, "stop disabled without run id");

  // Send disabled when the connection is blocked, even with a message.
  s = getComposerActionState({ ...base, message: "hi", selectedConnectionBlocked: true });
  expectEqual(s.mode, "send", "blocked -> send");
  expectEqual(s.disabled, true, "send disabled when connection blocked");

  // Send disabled when llm-api selected but LLM not ready.
  s = getComposerActionState({ ...base, message: "hi", selectedConnectionId: "llm-api", llmReady: false });
  expectEqual(s.disabled, true, "send disabled when llm not ready");

  // llm-api ready -> send enabled.
  s = getComposerActionState({ ...base, message: "hi", selectedConnectionId: "llm-api", llmReady: true });
  expectEqual(s.disabled, false, "send enabled when llm ready and has message");

  // No active run + message -> Send enabled.
  s = getComposerActionState({ ...base, message: "hi" });
  expectEqual(s.mode, "send", "no run -> send");
  expectEqual(s.disabled, false, "send enabled");
  expectEqual(s.title, "Send", "send title");

  // No active run + empty -> Send disabled (initial load).
  s = getComposerActionState({ ...base });
  expectEqual(s.mode, "send", "no run, empty -> send");
  expectEqual(s.disabled, true, "send disabled when empty (initial load)");

  function expectEqual(actual: unknown, expected: unknown, label: string) {
    if (actual !== expected) {
      throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
  }
});
