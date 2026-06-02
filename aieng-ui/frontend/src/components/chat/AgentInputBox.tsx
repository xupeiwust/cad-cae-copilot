import { useRef, type KeyboardEvent } from "react";

import type { PickedFace } from "../../appTypes";
import type { ApprovalMode, AutopilotRunState, ChatConnection } from "../../types";
import { AutoResizeTextarea } from "./AutoResizeTextarea";
import { ComposerControls, ConnectionSelector, getComposerActionState } from "./ComposerControls";
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

  const inputDisabled = selectedConnectionBlocked || (selectedChatConnectionId === "llm-api" && !llmReady);
  const action = getComposerActionState({
    message,
    selectedConnectionId: selectedChatConnectionId,
    selectedConnectionBlocked,
    llmReady,
    activeRunId: activeAutopilotRun ? (activeAutopilotRun.run_id ?? "") : null,
    agentProcessing,
  });

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
      <ConnectionSelector
        chatConnections={chatConnections}
        selectedChatConnectionId={selectedChatConnectionId}
        setSelectedChatConnectionId={setSelectedChatConnectionId}
      />

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
          <ComposerControls
            approvalMode={approvalMode}
            approvalModeDisabled={approvalModeDisabled}
            setApprovalMode={setApprovalMode}
            setSettingsOpen={setSettingsOpen}
            action={action}
            onSend={() => void sendUnified()}
            onStop={() => {
              if (activeAutopilotRun) cancelAutopilot(activeAutopilotRun.run_id);
            }}
          />
        </div>
      </div>
    </div>
  );
}
