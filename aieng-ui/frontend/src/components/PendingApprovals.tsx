import { Check, X } from "lucide-react";

import type { PendingApproval } from "../app/pendingApprovals";

type PendingApprovalsProps = {
  approvals: PendingApproval[];
  onResolve(permissionId: string, approved: boolean): void;
};

/**
 * MCP-first approval surface (#17). When an external MCP agent calls a gated
 * tool (managed-approval mode), the workbench MCP server blocks server-side and
 * raises an `approval_requested` event; this overlay lets the human approve/deny
 * in the live viewer — the workbench, not the connecting client, is the approval
 * authority. Renders nothing when there is nothing pending.
 */
export function PendingApprovals({ approvals, onResolve }: PendingApprovalsProps) {
  if (!approvals.length) return null;
  return (
    <div className="pending-approvals" role="region" aria-label="Agent approval requests">
      {approvals.map((approval) => (
        <div key={approval.permissionId} className="pending-approval-card">
          <div className="pending-approval-head">
            <span className="pending-approval-badge">approval</span>
            <code>{approval.toolName}</code>
          </div>
          {approval.explanation ? <p className="pending-approval-text">{approval.explanation}</p> : null}
          {approval.codePreview ? (
            <details className="pending-approval-code">
              <summary>Preview</summary>
              <pre>{approval.codePreview}</pre>
            </details>
          ) : null}
          <div className="pending-approval-actions">
            <button type="button" onClick={() => onResolve(approval.permissionId, true)} title="Approve">
              <Check className="button-icon" />
              Approve
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => onResolve(approval.permissionId, false)}
              title="Deny"
            >
              <X className="button-icon" />
              Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
