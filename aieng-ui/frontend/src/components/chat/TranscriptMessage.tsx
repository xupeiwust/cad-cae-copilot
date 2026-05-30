import type { TranscriptAgentMessage, TranscriptUserMessage } from "../../app/chatTranscript";
import { MarkdownText } from "../MarkdownText";
import { PointerText } from "../PointerText";

type TranscriptMessageProps = {
  item: TranscriptAgentMessage | TranscriptUserMessage;
};

export function TranscriptMessage({ item }: TranscriptMessageProps) {
  return (
    <article className={`transcript-message transcript-message-${item.role}`}>
      <div className="transcript-speaker">{item.role === "user" ? "You" : "Agent"}</div>
      <MarkdownText text={item.text} />
      {item.role === "user" && item.status === "queued" ? <span className="transcript-queued">queued</span> : null}
    </article>
  );
}
