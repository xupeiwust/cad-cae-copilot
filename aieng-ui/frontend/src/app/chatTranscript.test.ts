import { describe, expect, it } from "vitest";

import { isTerminalAutopilotStatus } from "./chatTranscript";

describe("isTerminalAutopilotStatus", () => {
  it("treats completed / failed / cancelled as terminal (stopped)", () => {
    expect(isTerminalAutopilotStatus("completed")).toBe(true);
    expect(isTerminalAutopilotStatus("failed")).toBe(true);
    expect(isTerminalAutopilotStatus("cancelled")).toBe(true);
  });

  it("treats active and unknown statuses as non-terminal", () => {
    for (const s of ["running", "awaiting_approval", "chatting", "blocked", "paused", "queued", "some_future_status"]) {
      expect(isTerminalAutopilotStatus(s)).toBe(false);
    }
  });

  it("is safe on null / undefined / non-string input", () => {
    expect(isTerminalAutopilotStatus(null)).toBe(false);
    expect(isTerminalAutopilotStatus(undefined)).toBe(false);
    expect(isTerminalAutopilotStatus(42)).toBe(false);
  });
});
