import { useState } from "react";
import { MessageSquareText, Send, Square } from "lucide-react";

import type { TranscriptAskUserLine } from "../../app/chatTranscript";
import { PointerText } from "../PointerText";
import { EventDetail } from "./EventDetail";

type AskUserLineProps = {
  item: TranscriptAskUserLine;
  busy: boolean;
  onReply?(runId: string, message: string): void;
  onCancel(runId: string): void;
};

export function AskUserLine({ item, busy, onReply, onCancel }: AskUserLineProps) {
  const runId = item.runId ?? "";
  const [reply, setReply] = useState("");

  function submitReply() {
    const text = reply.trim();
    if (!text || !runId) return;
    onReply?.(runId, text);
    setReply("");
  }

  return (
    <div className="ask-user-line">
      <div className="ask-user-line-main">
        <span className="ask-user-line-badge">
          <MessageSquareText className="button-icon" />
          input needed
        </span>
        <strong><PointerText text={item.question} /></strong>
      </div>
      <div className="ask-user-reply">
        <textarea
          value={reply}
          onChange={(event) => setReply(event.target.value)}
          placeholder="Reply to continue..."
          rows={3}
          disabled={busy || !runId}
        />
        <div className="ask-user-actions">
          <button type="button" disabled={busy || !runId || !reply.trim()} onClick={submitReply} title="Send reply">
            <Send className="button-icon" />
            Send
          </button>
          <button type="button" className="ghost-button" disabled={busy || !runId} onClick={() => onCancel(runId)} title="Cancel run">
            <Square className="button-icon" />
            Stop
          </button>
        </div>
      </div>
      <EventDetail detail={item.detail} label="Question payload" />
    </div>
  );
}
