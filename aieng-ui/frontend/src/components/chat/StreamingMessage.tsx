import type { StreamingState } from "../../app/useChatTranscript";
import { MarkdownText } from "../MarkdownText";

type StreamingMessageProps = {
  state: StreamingState;
};

export function StreamingMessage({ state }: StreamingMessageProps) {
  if (!state) return null;

  const isProgress = state.kind === "progress";

  if (isProgress) {
    return (
      <div className="streaming-progress-line" role="status" aria-live="polite">
        <span className="streaming-progress-pulse" aria-hidden="true" />
        {/* key forces re-mount on text change so the fade-in animation replays */}
        <span className="streaming-progress-text" key={state.text}>{state.text}</span>
      </div>
    );
  }

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
