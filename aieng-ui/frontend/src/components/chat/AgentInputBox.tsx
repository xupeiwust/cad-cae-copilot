import { useRef, type KeyboardEvent } from "react";
import { ArrowUp, SlidersHorizontal, Square } from "lucide-react";

import type { PickedFace } from "../../appTypes";
import type { ApprovalMode, AutopilotRunState, ChatConnection } from "../../types";
import { AutoResizeTextarea } from "./AutoResizeTextarea";
import { usePointerAutocomplete } from "./usePointerAutocomplete";

type AgentInputBoxProps = {
  chatConnections: ChatConnection[];
  selectedChatConnectionId: string;
  approvalMode: ApprovalMode;
  approvalModeDisabled: boolean;
  selectedConnectionBlocked: boolean;
  llmReady: boolean;
  message: string;
  activeAutopilotRun: AutopilotRunState | null;
  /** True only while a run is genuinely processing (running + recently updated).
   *  awaiting_approval / blocked / stale "running" are NOT processing. */
  agentProcessing: boolean;
  recentPickedFaces: PickedFace[];
  setSelectedChatConnectionId(value: string): void;
  setApprovalMode(value: ApprovalMode): void;
  setSettingsOpen(value: boolean): void;
  setMessage(value: string): void;
  sendUnified(promptOverride?: string): Promise<void>;
  cancelAutopilot(runId: string): void;
};

export function AgentInputBox({
  chatConnections,
  selectedChatConnectionId,
  approvalMode,
  approvalModeDisabled,
  selectedConnectionBlocked,
  llmReady,
  message,
  activeAutopilotRun,
  agentProcessing,
  recentPickedFaces,
  setSelectedChatConnectionId,
  setApprovalMode,
  setSettingsOpen,
  setMessage,
  sendUnified,
  cancelAutopilot,
}: AgentInputBoxProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const autocomplete = usePointerAutocomplete(recentPickedFaces);

  const selectedConn = chatConnections.find((c) => c.id === selectedChatConnectionId);
  const connStatus = selectedConn?.status ?? "blocked";
  const statusText = connStatus === "ready" ? "Ready" : connStatus === "blocked" ? "Unavailable" : connStatus.replace(/_/g, " ");
  const inputDisabled = selectedConnectionBlocked || (selectedChatConnectionId === "llm-api" && !llmReady);

  function applySuggestion(face?: PickedFace) {
    const el = textareaRef.current;
    if (!el) return;
    const result = autocomplete.accept(message, el.selectionStart, face);
    if (!result) return;
    setMessage(result.text);
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.selectionStart = result.cursor;
        textareaRef.current.selectionEnd = result.cursor;
        textareaRef.current.focus();
      }
    }, 0);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (autocomplete.open) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        autocomplete.moveSelection(1);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        autocomplete.moveSelection(-1);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applySuggestion();
        return;
      }
      if (e.key === "Escape") {
        autocomplete.close();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (message.trim()) void sendUnified();
    }
  }

  function handleInput(value: string) {
    setMessage(value);
    const el = textareaRef.current;
    autocomplete.onInput(value, el ? el.selectionStart : value.length);
  }

  return (
    <div className="chat-composer">
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

      <div className="chat-input-row">
        <div className="chat-input-wrap">
          {recentPickedFaces.length ? (
            <div className="chat-context-chips" aria-label="Selected geometry">
              {recentPickedFaces.slice(0, 2).map((face) => (
                <code key={face.pointer} title={face.label}>
                  {face.pointer}
                </code>
              ))}
              {recentPickedFaces.length > 2 ? <span>+{recentPickedFaces.length - 2}</span> : null}
            </div>
          ) : null}
          <AutoResizeTextarea
            ref={textareaRef}
            value={message}
            onChange={(e) => handleInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              selectedConnectionBlocked
                ? "Select a project to start..."
                : selectedChatConnectionId === "llm-api" && !llmReady
                  ? "LLM provider configuration loading..."
                  : "Describe what to build"
            }
            disabled={inputDisabled}
          />
          {autocomplete.open && autocomplete.matches.length > 0 ? (
            <div className="chat-autocomplete">
              {autocomplete.matches.map((f, i) => (
                <button
                  key={f.pointer}
                  type="button"
                  className={i === autocomplete.index ? "chat-autocomplete-item active" : "chat-autocomplete-item"}
                  onClick={() => applySuggestion(f)}
                >
                  <span className="chat-autocomplete-badge">{f.surface_type}</span>
                  <code>{f.pointer}</code>
                  <span className="chat-autocomplete-label">{f.label}</span>
                </button>
              ))}
            </div>
          ) : null}
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
            {activeAutopilotRun && agentProcessing && !message.trim() ? (
              <button
                type="button"
                className="chat-action-button chat-action-button-stop"
                disabled={!activeAutopilotRun.run_id}
                onClick={() => cancelAutopilot(activeAutopilotRun.run_id)}
                title="Stop active agent run"
              >
                <Square className="button-icon" />
              </button>
            ) : (
              <button
                type="button"
                className="chat-action-button chat-action-button-send"
                disabled={inputDisabled || !message.trim()}
                onClick={() => void sendUnified()}
                title="Send"
              >
                <ArrowUp className="button-icon" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
