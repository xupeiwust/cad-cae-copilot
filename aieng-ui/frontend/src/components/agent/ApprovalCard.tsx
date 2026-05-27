import { ActionIcon } from "../common";
import type { RuntimeRun } from "../../types";

type ApprovalCardProps = {
  busy: boolean;
  run: RuntimeRun;
  onApprove(): void;
  onReject(): void;
};

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function stringField(value: unknown) {
  return typeof value === "string" && value.trim() ? value : null;
}

function sideEffectSummary(input: Record<string, unknown>, fallback: string) {
  const sideEffects = stringList(input.side_effects ?? input.sideEffects);
  if (sideEffects.length) return sideEffects.join("; ");
  return (
    stringField(input.side_effect_summary) ??
    stringField(input.sideEffectSummary) ??
    stringField(input.summary) ??
    fallback
  );
}

export function ApprovalCard({ busy, run, onApprove, onReject }: ApprovalCardProps) {
  const pendingStep = run.plan[run.pending_step_index ?? 0] ?? null;
  const toolName = pendingStep?.name ?? "tool";
  const effectSummary = pendingStep
    ? sideEffectSummary(pendingStep.input ?? {}, pendingStep.description)
    : run.summary || "Approval is required before this tool can run.";

  return (
    <div className="chat-approval-card approval-card">
      <div className="approval-card-copy">
        <span className="approval-card-eyebrow">{run.status.replace(/_/g, " ")}</span>
        <strong>Approval required — {toolName}</strong>
        <small>{effectSummary}</small>
      </div>
      <div className="chat-approval-actions">
        <button disabled={busy} onClick={onApprove}>
          <ActionIcon name="approve" />
          Approve
        </button>
        <button disabled={busy} className="ghost-button" onClick={onReject}>
          <ActionIcon name="reject" />
          Reject
        </button>
      </div>
    </div>
  );
}
