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
  const copy = detail ? `${title} · ` : title;

  return (
    <div
      className={`agent-activity-line agent-activity-${tone}${running ? " is-running" : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="agent-activity-copy">
        <strong>{copy}</strong>
        {detail ? <PointerText text={detail} /> : null}
      </span>
      {elapsed ? <time>{elapsed}</time> : null}
    </div>
  );
}
