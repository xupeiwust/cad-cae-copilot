import { useState } from "react";
import { Check, MessageSquareText, Square, X } from "lucide-react";

import type { TranscriptApprovalLine } from "../../app/chatTranscript";
import { EventDetail } from "./EventDetail";

type ApprovalLineProps = {
  item: TranscriptApprovalLine;
  busy: boolean;
  onApprove(runId: string): void;
  onReject(runId: string): void;
  onCancel(runId: string): void;
  onRevise?(runId: string, message: string): void;
};

export function ApprovalLine({ item, busy, onApprove, onReject, onCancel, onRevise }: ApprovalLineProps) {
  const runId = item.runId ?? "";
  const [reviseOpen, setReviseOpen] = useState(false);
  const [reviseText, setReviseText] = useState("");

  function handleReviseSubmit() {
    if (!reviseText.trim() || !runId) return;
    onRevise?.(runId, reviseText.trim());
    setReviseOpen(false);
    setReviseText("");
  }

  return (
    <div className="approval-line">
      <div className="approval-line-main">
        <span className="approval-line-badge">approval</span>
        <code>{item.toolName}</code>
        <strong>{item.summary}</strong>
        {item.sideEffectSummary ? <span>{item.sideEffectSummary}</span> : null}
        {item.riskSummary ? <small>{item.riskSummary}</small> : null}
      </div>
      {item.skillPlanBrief || item.skillPlanAssumptions?.length || item.skillPlanWarnings?.length || item.skillPlanVerificationTargets?.length ? (
        <div className="approval-skill-plan">
          {item.skillPlanBrief ? <strong>{item.skillPlanBrief}</strong> : null}
          <ApprovalList label="Assumptions" items={item.skillPlanAssumptions} />
          <ApprovalList label="Warnings" items={item.skillPlanWarnings} tone="warning" />
          <ApprovalList label="Verify" items={item.skillPlanVerificationTargets} />
        </div>
      ) : null}
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
          <button
            type="button"
            className="ghost-button"
            disabled={busy || !runId}
            onClick={() => setReviseOpen((v) => !v)}
            title="Ask revision"
          >
            <MessageSquareText className="button-icon" />
            Revise
          </button>
        ) : null}
        <button type="button" className="ghost-button" disabled={busy || !runId} onClick={() => onCancel(runId)} title="Cancel run">
          <Square className="button-icon" />
          Stop
        </button>
      </div>
      {reviseOpen && (
        <div className="approval-revise-input">
          <textarea
            value={reviseText}
            onChange={(e) => setReviseText(e.target.value)}
            placeholder="Describe what to change..."
            rows={3}
            disabled={busy}
          />
          <div className="approval-revise-actions">
            <button type="button" disabled={busy || !reviseText.trim()} onClick={handleReviseSubmit}>
              Submit revision
            </button>
            <button type="button" className="ghost-button" disabled={busy} onClick={() => { setReviseOpen(false); setReviseText(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}
      <EventDetail detail={item.detail} label="Review payload" />
    </div>
  );
}

function ApprovalList({ label, items, tone }: { label: string; items?: string[]; tone?: "warning" }) {
  if (!items?.length) return null;
  return (
    <div className={`approval-skill-list${tone ? ` approval-skill-list-${tone}` : ""}`}>
      <span>{label}</span>
      <ul>
        {items.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
