import { AlertCircle } from "lucide-react";

import type { ChatTranscriptItem } from "../../app/chatTranscript";
import type { StreamingState } from "../../app/useChatTranscript";
import { AgentPlanCard } from "../agent/AgentPlanCard";
import { PointerText } from "../PointerText";
import { ApprovalLine } from "./ApprovalLine";
import { AskUserLine } from "./AskUserLine";
import { ArtifactLine } from "./ArtifactLine";
import { EventDetail } from "./EventDetail";
import { IntentChip } from "./IntentChip";
import { StreamingMessage } from "./StreamingMessage";
import { TranscriptMessage } from "./TranscriptMessage";
import { StatusIcon } from "./ToolLine";
import { ToolLine } from "./ToolLine";

type ChatTranscriptProps = {
  items: ChatTranscriptItem[];
  busy: boolean;
  streamingState: StreamingState;
  onViewArtifact(path: string): void;
  onApproveAutopilot(runId: string): void;
  onRejectAutopilot(runId: string): void;
  onCancelAutopilot(runId: string): void;
  onReviseAutopilot?(runId: string, message: string): void;
  onReplyAutopilot?(runId: string, message: string): void;
};

export function ChatTranscript({
  items,
  busy,
  streamingState,
  onViewArtifact,
  onApproveAutopilot,
  onRejectAutopilot,
  onCancelAutopilot,
  onReviseAutopilot,
  onReplyAutopilot,
}: ChatTranscriptProps) {
  return (
    <div className="chat-transcript">
      {items.map((item) => {
        if (item.kind === "message") return <TranscriptMessage key={item.id} item={item} />;
        if (item.kind === "intent") return <IntentChip key={item.id} item={item} />;
        if (item.kind === "plan") return <AgentPlanCard key={item.id} item={item} />;
        if (item.kind === "tool") return <ToolLine key={item.id} item={item} />;
        if (item.kind === "ask_user") {
          return (
            <AskUserLine
              key={item.id}
              item={item}
              busy={busy}
              onReply={onReplyAutopilot}
              onCancel={onCancelAutopilot}
            />
          );
        }
        if (item.kind === "approval") {
          return (
            <ApprovalLine
              key={item.id}
              item={item}
              busy={busy}
              onApprove={onApproveAutopilot}
              onReject={onRejectAutopilot}
              onCancel={onCancelAutopilot}
              onRevise={onReviseAutopilot}
            />
          );
        }
        if (item.kind === "artifact") return <ArtifactLine key={item.id} item={item} onViewArtifact={onViewArtifact} />;
        if (item.kind === "error") {
          return (
            <div key={item.id} className="transcript-error-line">
              <AlertCircle className="transcript-status-icon" />
              <span><PointerText text={item.summary} /></span>
              <EventDetail detail={item.detail} />
            </div>
          );
        }
        return (
          <div key={item.id} className={`transcript-status-line transcript-status-${item.status}`}>
            <StatusIcon status={item.status} />
            <span><PointerText text={item.summary} /></span>
            <EventDetail detail={item.detail} />
          </div>
        );
      })}
      {streamingState ? <StreamingMessage state={streamingState} /> : null}
    </div>
  );
}
