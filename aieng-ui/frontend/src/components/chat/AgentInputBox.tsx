import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";

import type { PickedFace } from "../../appTypes";
import type { ApprovalMode, AutopilotAgentMode, AutopilotRunState, ChatConnection } from "../../types";
import { ActionIcon } from "../common";

type AgentInputBoxProps = {
  chatConnections: ChatConnection[];
  selectedChatConnectionId: string;
  agentMode: AutopilotAgentMode;
  approvalMode: ApprovalMode;
  approvalModeDisabled: boolean;
  selectedConnectionBlocked: boolean;
  llmReady: boolean;
  message: string;
  activeAutopilotRun: AutopilotRunState | null;
  recentPickedFaces: PickedFace[];
  setSelectedChatConnectionId(value: string): void;
  setAgentMode(value: AutopilotAgentMode): void;
  setApprovalMode(value: ApprovalMode): void;
  setSettingsOpen(value: boolean): void;
  setMessage(value: string): void;
  sendUnified(promptOverride?: string): Promise<void>;
  cancelAutopilot(runId: string): void;
};

export function AgentInputBox({
  chatConnections,
  selectedChatConnectionId,
  agentMode,
  approvalMode,
  approvalModeDisabled,
  selectedConnectionBlocked,
  llmReady,
  message,
  activeAutopilotRun,
  recentPickedFaces,
  setSelectedChatConnectionId,
  setAgentMode,
  setApprovalMode,
  setSettingsOpen,
  setMessage,
  sendUnified,
  cancelAutopilot,
}: AgentInputBoxProps) {
  const [acOpen, setAcOpen] = useState(false);
  const [acQuery, setAcQuery] = useState("");
  const [acIndex, setAcIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const acCursorRef = useRef<{ start: number; end: number } | null>(null);

  const selectedConn = chatConnections.find((c) => c.id === selectedChatConnectionId);
  const connStatus = selectedConn?.status ?? "blocked";
  const statusText = connStatus === "ready" ? "Ready" : connStatus === "blocked" ? "Unavailable" : connStatus.replace(/_/g, " ");
  const inputDisabled = selectedConnectionBlocked || (selectedChatConnectionId === "llm-api" && !llmReady);
  const acMatches = useMemo(
    () =>
      recentPickedFaces.filter(
        (f) =>
          f.pointer.toLowerCase().includes(acQuery.toLowerCase()) ||
          f.label.toLowerCase().includes(acQuery.toLowerCase()),
      ),
    [acQuery, recentPickedFaces],
  );

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (!message) el.style.height = "auto";
  }, [message]);

  function closeAutocomplete() {
    setAcOpen(false);
    setAcQuery("");
    acCursorRef.current = null;
  }

  function insertAutocomplete(face: PickedFace) {
    if (!textareaRef.current || !acCursorRef.current) return;
    const { start } = acCursorRef.current;
    const before = message.slice(0, start - 1);
    const after = message.slice(textareaRef.current.selectionStart);
    const replacement = `${before}${face.pointer} ${after}`;
    setMessage(replacement);
    closeAutocomplete();
    setTimeout(() => {
      if (textareaRef.current) {
        const pos = (before + face.pointer + " ").length;
        textareaRef.current.selectionStart = pos;
        textareaRef.current.selectionEnd = pos;
        textareaRef.current.focus();
      }
    }, 0);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (acOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (acMatches.length) setAcIndex((i) => (i + 1) % acMatches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (acMatches.length) setAcIndex((i) => (i - 1 + acMatches.length) % acMatches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (acMatches[acIndex]) insertAutocomplete(acMatches[acIndex]);
        return;
      }
      if (e.key === "Escape") {
        closeAutocomplete();
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
    if (!el) return;
    const cursor = el.selectionStart;
    const textBefore = value.slice(0, cursor);
    const atIdx = textBefore.lastIndexOf("@");
    if (atIdx !== -1 && !textBefore.slice(atIdx + 1).includes(" ") && recentPickedFaces.length) {
      acCursorRef.current = { start: atIdx + 1, end: atIdx + 1 };
      setAcQuery(textBefore.slice(atIdx + 1));
      setAcIndex(0);
      setAcOpen(true);
    } else {
      closeAutocomplete();
    }
  }

  return (
    <>
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
        <div className="agent-mode-controls">
          <label className="agent-control-field">
            <span>Mode</span>
            <select
              className="agent-control-select"
              value={agentMode}
              onChange={(e) => setAgentMode(e.target.value as AutopilotAgentMode)}
              title="Agent mode"
            >
              <option value="assist">Assist</option>
              <option value="autopilot">Autopilot</option>
              <option value="full_agent">Full agent</option>
            </select>
          </label>
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
        </div>
        <button
          type="button"
          className="ghost-button icon-only-button"
          onClick={() => setSettingsOpen(true)}
          title="Settings"
          style={{ marginLeft: "auto" }}
        >
          <ActionIcon name="settings" />
        </button>
      </div>

      <div className="chat-input-row">
        <div className="chat-input-wrap">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => {
              handleInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${e.target.scrollHeight}px`;
            }}
            onKeyDown={handleKeyDown}
            placeholder={
              selectedConnectionBlocked
                ? "Select a project to start..."
                : selectedChatConnectionId === "llm-api" && !llmReady
                  ? "LLM provider configuration loading..."
                  : "Check the current project status and generate a reviewable engineering execution plan."
            }
            disabled={inputDisabled}
          />
          {acOpen && acMatches.length > 0 ? (
            <div className="chat-autocomplete">
              {acMatches.map((f, i) => (
                <button
                  key={f.pointer}
                  type="button"
                  className={i === acIndex ? "chat-autocomplete-item active" : "chat-autocomplete-item"}
                  onClick={() => insertAutocomplete(f)}
                >
                  <span className="chat-autocomplete-badge">{f.surface_type}</span>
                  <code>{f.pointer}</code>
                  <span className="chat-autocomplete-label">{f.label}</span>
                </button>
              ))}
            </div>
          ) : null}
          {activeAutopilotRun && !message.trim() ? (
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
    </>
  );
}
