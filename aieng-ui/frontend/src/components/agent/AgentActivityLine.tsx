import { PointerText } from "../PointerText";

export type AgentActivityTone = "running" | "approval" | "done" | "error" | "idle";

type AgentActivityLineProps = {
  title: string;
  detail?: string;
  tone?: AgentActivityTone;
  running?: boolean;
  elapsed?: string;
};

export function AgentActivityLine({
  title,
  detail,
  tone = "idle",
  running = false,
  elapsed,
}: AgentActivityLineProps) {
  return (
    <div
      className={`agent-activity-line agent-activity-${tone}${running ? " is-running" : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="agent-activity-orb" aria-hidden="true" />
      <div className="agent-activity-copy">
        <strong>{title}</strong>
        {detail ? <span><PointerText text={detail} /></span> : null}
      </div>
      {elapsed ? <time>{elapsed}</time> : null}
    </div>
  );
}
