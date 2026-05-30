import { Check, MessageSquareText, Square, X } from "lucide-react";

import type { TranscriptApprovalLine } from "../../app/chatTranscript";
import { EventDetail } from "./EventDetail";

type ApprovalLineProps = {
  item: TranscriptApprovalLine;
  busy: boolean;
  onApprove(runId: string): void;
  onReject(runId: string): void;
  onCancel(runId: string): void;
  onRevise?(runId: string): void;
};

export function ApprovalLine({ item, busy, onApprove, onReject, onCancel, onRevise }: ApprovalLineProps) {
  const runId = item.runId ?? "";
  return (
    <div className="approval-line">
      <div className="approval-line-main">
        <span className="approval-line-badge">approval</span>
        <code>{item.toolName}</code>
        <strong>{item.summary}</strong>
        {item.sideEffectSummary ? <span>{item.sideEffectSummary}</span> : null}
        {item.riskSummary ? <small>{item.riskSummary}</small> : null}
      </div>
      {item.codePreview ? (
        <details className="approval-code-preview">
          <summary>Code preview</summary>
          <pre>{item.codePreview}</pre>
        </details>
      ) : null}
      <div className="approval-line-actions">
        <button type="button" disabled={busy || !runId} onClick={() => onApprove(runId)} title="Approve">
          <Check className="button-icon" />
          Approve
        </button>
        <button type="button" className="ghost-button" disabled={busy || !runId} onClick={() => onReject(runId)} title="Reject">
          <X className="button-icon" />
          Reject
        </button>
        {onRevise ? (
          <button type="button" className="ghost-button" disabled={busy || !runId} onClick={() => onRevise(runId)} title="Ask revision">
            <MessageSquareText className="button-icon" />
            Revise
          </button>
        ) : null}
        <button type="button" className="ghost-button" disabled={busy || !runId} onClick={() => onCancel(runId)} title="Cancel run">
          <Square className="button-icon" />
          Stop
        </button>
      </div>
      <EventDetail detail={item.detail} label="Review payload" />
    </div>
  );
}
