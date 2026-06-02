import { ArrowUp, SlidersHorizontal, Square } from "lucide-react";

import type { ApprovalMode, ChatConnection } from "../../types";

export type ComposerActionState = {
  mode: "send" | "stop";
  disabled: boolean;
  label: string;
  title: string;
};

/**
 * Derive the composer primary-action button state. Pure — mirrors the original
 * AgentInputBox logic exactly:
 * - Stop when there is an active run that is genuinely processing and the input
 *   is empty (disabled if the run has no id).
 * - Otherwise Send, disabled when the connection is blocked / LLM not ready, or
 *   the message is empty.
 */
export function getComposerActionState(args: {
  message: string;
  selectedConnectionId: string;
  selectedConnectionBlocked: boolean;
  llmReady: boolean;
  /** run_id of the active run; null when there is no active run. */
  activeRunId: string | null;
  agentProcessing: boolean;
}): ComposerActionState {
  const inputDisabled =
    args.selectedConnectionBlocked || (args.selectedConnectionId === "llm-api" && !args.llmReady);
  const hasMessage = Boolean(args.message.trim());
  const hasActiveRun = args.activeRunId !== null;
  if (hasActiveRun && args.agentProcessing && !hasMessage) {
    return { mode: "stop", disabled: !args.activeRunId, label: "Stop", title: "Stop active agent run" };
  }
  return { mode: "send", disabled: inputDisabled || !hasMessage, label: "Send", title: "Send" };
}

export function ConnectionSelector({
  chatConnections,
  selectedChatConnectionId,
  setSelectedChatConnectionId,
}: {
  chatConnections: ChatConnection[];
  selectedChatConnectionId: string;
  setSelectedChatConnectionId(value: string): void;
}) {
  const selectedConn = chatConnections.find((c) => c.id === selectedChatConnectionId);
  const connStatus = selectedConn?.status ?? "blocked";
  const statusText = connStatus === "ready" ? "Ready" : connStatus === "blocked" ? "Unavailable" : connStatus.replace(/_/g, " ");
  return (
    <div className="chat-input-toolbar">
      <select
        className="chat-connection-select"
        value={selectedChatConnectionId}
        onChange={(e) => setSelectedChatConnectionId(e.target.value)}
      >
        {chatConnections.map((conn) => (
          <option key={conn.id} value={conn.id}>
            {conn.status === "ready" ? "●" : conn.status === "blocked" ? "○" : "◐"} {conn.label}
          </option>
        ))}
      </select>
      <span className={`connection-status status-${connStatus}`} title={selectedConn?.detail ?? ""}>
        {statusText}
      </span>
    </div>
  );
}

export function ComposerControls({
  approvalMode,
  approvalModeDisabled,
  setApprovalMode,
  setSettingsOpen,
  action,
  onSend,
  onStop,
}: {
  approvalMode: ApprovalMode;
  approvalModeDisabled: boolean;
  setApprovalMode(value: ApprovalMode): void;
  setSettingsOpen(value: boolean): void;
  action: ComposerActionState;
  onSend(): void;
  onStop(): void;
}) {
  return (
    <div className="chat-composer-footer">
      <div className="chat-composer-controls">
        <label className="agent-control-field">
          <span>Approval</span>
          <select
            className="agent-control-select"
            value={approvalMode}
            onChange={(e) => setApprovalMode(e.target.value as ApprovalMode)}
            disabled={approvalModeDisabled}
            title="Approval mode"
          >
            <option value="balanced">Balanced</option>
            <option value="strict">Strict</option>
            <option value="manual">Manual</option>
          </select>
        </label>
        <button
          type="button"
          className="chat-composer-icon-button"
          onClick={() => setSettingsOpen(true)}
          title="Settings"
        >
          <SlidersHorizontal className="button-icon" />
        </button>
      </div>
      {action.mode === "stop" ? (
        <button
          type="button"
          className="chat-action-button chat-action-button-stop"
          disabled={action.disabled}
          onClick={onStop}
          title={action.title}
        >
          <Square className="button-icon" />
        </button>
      ) : (
        <button
          type="button"
          className="chat-action-button chat-action-button-send"
          disabled={action.disabled}
          onClick={onSend}
          title={action.title}
        >
          <ArrowUp className="button-icon" />
        </button>
      )}
    </div>
  );
}
