import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";

import type { TranscriptStatus, TranscriptToolLine } from "../../app/chatTranscript";
import { PointerText } from "../PointerText";
import { EventDetail } from "./EventDetail";

type ToolLineProps = {
  item: TranscriptToolLine;
};

export function ToolLine({ item }: ToolLineProps) {
  return (
    <div className={`tool-line tool-line-${item.status}`}>
      <StatusIcon status={item.status} />
      <code>{item.toolName}</code>
      <span><PointerText text={item.summary} /></span>
      {typeof item.elapsedMs === "number" ? <time>{formatMs(item.elapsedMs)}</time> : null}
      <EventDetail detail={item.detail} />
    </div>
  );
}

export function StatusIcon({ status }: { status: TranscriptStatus }) {
  if (status === "running") return <Loader2 className="transcript-status-icon spin" aria-label="running" />;
  if (status === "done") return <CheckCircle2 className="transcript-status-icon" aria-label="done" />;
  if (status === "failed") return <AlertCircle className="transcript-status-icon" aria-label="failed" />;
  return <Circle className="transcript-status-icon" aria-label={status} />;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
