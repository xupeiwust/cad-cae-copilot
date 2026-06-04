import { test } from "vitest";

import { applyApprovalEvent, type PendingApproval } from "./pendingApprovals";
import type { AgentTranscriptEvent } from "./chatTranscript";

function expect(condition: unknown, message: string) {
  if (!condition) throw new Error(message);
}

function requested(permissionId: string, extra: Record<string, unknown> = {}): AgentTranscriptEvent {
  return {
    type: "approval_requested",
    project_id: "p1",
    payload: {
      agentic_permission_id: permissionId,
      tool_name: "cad.execute_build123d",
      explanation: "Agent wants to run cad.execute_build123d.",
      code_preview: "result = Box(1,1,1)",
      ...extra,
    },
  } as unknown as AgentTranscriptEvent;
}

function resolved(permissionId: string): AgentTranscriptEvent {
  return {
    type: "approval_resolved",
    payload: { agentic_permission_id: permissionId },
  } as unknown as AgentTranscriptEvent;
}

test("approval_requested appends a pending approval", () => {
  const next = applyApprovalEvent([], requested("abc"));
  expect(next.length === 1, "should append one");
  expect(next[0].permissionId === "abc", "permissionId");
  expect(next[0].toolName === "cad.execute_build123d", "toolName");
  expect(next[0].projectId === "p1", "projectId from event");
  expect(next[0].codePreview === "result = Box(1,1,1)", "codePreview");
});

test("duplicate approval_requested is deduped by permissionId", () => {
  const once = applyApprovalEvent([], requested("abc"));
  const twice = applyApprovalEvent(once, requested("abc"));
  expect(twice.length === 1, "no duplicate");
  expect(twice === once, "returns same array reference when no change");
});

test("approval_resolved removes the matching pending approval", () => {
  const pending = applyApprovalEvent([], requested("abc"));
  const cleared = applyApprovalEvent(pending, resolved("abc"));
  expect(cleared.length === 0, "removed");
});

test("event without a permission id is a no-op", () => {
  const start: PendingApproval[] = [];
  const after = applyApprovalEvent(start, { type: "approval_requested", payload: {} } as unknown as AgentTranscriptEvent);
  expect(after === start, "no-op returns same array");
});

test("unrelated event type is ignored", () => {
  const after = applyApprovalEvent([], { type: "tool_started", payload: { agentic_permission_id: "x" } } as unknown as AgentTranscriptEvent);
  expect(after.length === 0, "ignored");
});
