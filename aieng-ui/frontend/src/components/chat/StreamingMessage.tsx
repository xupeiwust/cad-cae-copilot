import type { StreamingState } from "../../app/useChatTranscript";
import { MarkdownText } from "../MarkdownText";

type StreamingMessageProps = {
  state: StreamingState;
};

export function StreamingMessage({ state }: StreamingMessageProps) {
  if (!state) return null;

  return (
    <article className="transcript-message transcript-message-agent">
      <div className="transcript-speaker">Agent</div>
      {state.status === "tool_call" && state.toolName ? (
        <div className="streaming-tool-hint">
          <span className="streaming-pulse-dot" />
          Calling {state.toolName}…
        </div>
      ) : null}
      {state.text ? <MarkdownText text={state.text} /> : null}
      {state.status === "streaming" ? <span className="streaming-cursor" aria-hidden="true" /> : null}
    </article>
  );
}
