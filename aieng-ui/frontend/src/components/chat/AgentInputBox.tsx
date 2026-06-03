import { useRef, type KeyboardEvent } from "react";

import type { LiveSyncStatus } from "../../appUtils";
import type { PickedFace } from "../../appTypes";
import type { ApprovalMode, AutopilotRunState, ChatConnection, RuntimeConfigSnapshot } from "../../types";
import type { ComposerCommand } from "./composerIntent";
import { AutoResizeTextarea } from "./AutoResizeTextarea";
import { ConnectionHealthBar } from "./ConnectionHealthBar";
import { ComposerControls, ConnectionSelector, getComposerActionState } from "./ComposerControls";
import { pointerMentionQuery, usePointerAutocomplete } from "./usePointerAutocomplete";
import { useSlashCommandMenu } from "./useSlashCommandMenu";

type AgentInputBoxProps = {
  chatConnections: ChatConnection[];
  selectedChatConnectionId: string;
  approvalMode: ApprovalMode;
  approvalModeDisabled: boolean;
  selectedConnectionBlocked: boolean;
  llmReady: boolean;
  liveSyncStatus: LiveSyncStatus;
  liveSyncDetail: string;
  runtime: RuntimeConfigSnapshot | null;
  runtimeReady: boolean;
  runtimeProvider: string;
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
  liveSyncStatus,
  liveSyncDetail,
  runtime,
  runtimeReady,
  runtimeProvider,
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
  const slash = useSlashCommandMenu();

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

  function applySlashChoice(command?: ComposerCommand) {
    const result = slash.accept(message, command);
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
    if (slash.open && slash.matches.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        slash.moveSelection(1);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        slash.moveSelection(-1);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applySlashChoice();
        return;
      }
      if (e.key === "Escape") {
        slash.close();
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
    const cursor = el ? el.selectionStart : value.length;
    autocomplete.onInput(value, cursor);
    // The `@` pointer autocomplete has priority: if a mention is active, keep the
    // slash menu closed so the two popups never fight over the same anchor.
    const mentionActive = recentPickedFaces.length > 0 && pointerMentionQuery(value, cursor) !== null;
    if (mentionActive) {
      slash.close();
    } else {
      slash.onInput(value, cursor);
    }
  }

  return (
    <div className="chat-composer">
      <ConnectionSelector
        chatConnections={chatConnections}
        selectedChatConnectionId={selectedChatConnectionId}
        setSelectedChatConnectionId={setSelectedChatConnectionId}
      />
      <ConnectionHealthBar
        chatConnections={chatConnections}
        selectedConnectionId={selectedChatConnectionId}
        selectedConnectionBlocked={selectedConnectionBlocked}
        llmReady={llmReady}
        liveSyncStatus={liveSyncStatus}
        liveSyncDetail={liveSyncDetail}
        runtime={runtime}
        runtimeReady={runtimeReady}
        runtimeProvider={runtimeProvider}
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
          {!autocomplete.open && slash.open && slash.matches.length > 0 ? (
            <div className="chat-autocomplete" aria-label="Slash commands">
              {slash.matches.map((c, i) => (
                <button
                  key={c.command}
                  type="button"
                  className={i === slash.index ? "chat-autocomplete-item active" : "chat-autocomplete-item"}
                  onClick={() => applySlashChoice(c.command)}
                >
                  <span className="chat-autocomplete-badge">cmd</span>
                  <code>{c.label}</code>
                  <span className="chat-autocomplete-label">{c.hint}</span>
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
