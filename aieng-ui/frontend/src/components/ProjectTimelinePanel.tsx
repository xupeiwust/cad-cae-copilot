import { Activity, AlertTriangle, CheckCircle2, Clock3, FileText, ShieldCheck } from "lucide-react";

import type { ProjectTimeline, ProjectTimelineEntry, ProjectTimelineEntryKind, TimelineNextAction } from "../app/projectTimeline";

type ProjectTimelinePanelProps = {
  timeline: ProjectTimeline | null;
};

const KIND_ICON: Record<ProjectTimelineEntryKind, typeof Activity> = {
  run: Clock3,
  approval: ShieldCheck,
  tool: Activity,
  artifact: FileText,
  next_action: Activity,
  failure: AlertTriangle,
};

function fmtTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function tone(entry: ProjectTimelineEntry): string {
  if (entry.kind === "failure") return "timeline-entry-failure";
  if (entry.kind === "approval") return "timeline-entry-approval";
  if (entry.kind === "artifact") return "timeline-entry-artifact";
  return "timeline-entry-neutral";
}

function nextActionTone(action: TimelineNextAction): string {
  if (action.availableNow === false) return "project-timeline-next-blocked";
  if (action.availableNow === true) return "project-timeline-next-available";
  return "project-timeline-next-neutral";
}

function nextActionTitle(action: TimelineNextAction): string {
  return action.tool ? `${action.tool}: ${action.label}` : action.label;
}

export function ProjectTimelinePanel({ timeline }: ProjectTimelinePanelProps) {
  if (!timeline || timeline.runCount === 0) return null;
  const visible = timeline.entries.slice(0, 12);

  return (
    <section className="project-timeline-card" aria-label="Project timeline">
      <div className="project-timeline-head">
        <div>
          <strong>Project timeline</strong>
          <span>{timeline.runCount} runtime run{timeline.runCount === 1 ? "" : "s"}</span>
        </div>
        {timeline.warningCount ? (
          <span className="project-timeline-warning">
            <AlertTriangle className="h-3.5 w-3.5" />
            {timeline.warningCount} malformed receipt
          </span>
        ) : (
          <span className="project-timeline-ok">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Read-only
          </span>
        )}
      </div>

      <ol className="project-timeline-list">
        {visible.map((entry) => {
          const Icon = KIND_ICON[entry.kind] ?? Activity;
          return (
            <li key={entry.id} className={`project-timeline-entry ${tone(entry)}`}>
              <div className="project-timeline-icon" aria-hidden="true">
                <Icon className="h-4 w-4" />
              </div>
              <div className="project-timeline-body">
                <div className="project-timeline-row">
                  <strong>{entry.title}</strong>
                  <time dateTime={entry.timestamp}>{fmtTime(entry.timestamp)}</time>
                </div>
                {entry.detail ? <p>{entry.detail}</p> : null}
                {entry.artifacts.length ? (
                  <div className="project-timeline-chips" aria-label="Artifacts">
                    {entry.artifacts.slice(0, 4).map((artifact) => (
                      <code key={artifact}>{artifact}</code>
                    ))}
                  </div>
                ) : null}
                {entry.nextActions.length ? (
                  <div className="project-timeline-next" aria-label="Advisory next actions">
                    {entry.nextActions.slice(0, 3).map((action, index) => (
                      <span key={`${action.tool ?? "advisory"}:${action.label}:${index}`} className={nextActionTone(action)}>
                        <strong>{nextActionTitle(action)}</strong>
                        {action.blockedReason ? <em>Blocked: {action.blockedReason}</em> : null}
                        {action.blockedReasonCodes.length ? <small>{action.blockedReasonCodes.join(", ")}</small> : null}
                        {action.resolvesBlockedReasonCodes.length ? (
                          <small>resolves {action.resolvesBlockedReasonCodes.join(", ")}</small>
                        ) : null}
                        {action.safetyFlags.length ? <small>{action.safetyFlags.join(" · ")}</small> : null}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      <div className="project-timeline-foot">
        Next actions are advisory text only; solver claims require solver-run evidence.
      </div>
    </section>
  );
}
