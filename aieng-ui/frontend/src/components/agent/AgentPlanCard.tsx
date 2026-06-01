import { AlertCircle, CheckCircle2, Circle, Clock3, Loader2, PauseCircle } from "lucide-react";

import type { TranscriptAgentPlanLine } from "../../app/chatTranscript";
import type { AutopilotAgentPlanStep } from "../../types";
import { PointerText } from "../PointerText";
import { EventDetail } from "../chat/EventDetail";

type AgentPlanCardProps = {
  item: TranscriptAgentPlanLine;
};

const STATUS_LABELS: Record<string, string> = {
  pending: "pending",
  running: "running",
  completed: "done",
  blocked: "waiting approval",
  failed: "failed",
  skipped: "skipped",
};

export function AgentPlanCard({ item }: AgentPlanCardProps) {
  return (
    <section className={`agent-plan-card agent-plan-card-${item.status}`} aria-label="Agent plan">
      <div className="agent-plan-card-header">
        <div>
          <span className="agent-plan-eyebrow">Agent plan</span>
          <strong><PointerText text={item.objective} /></strong>
        </div>
        <span className={`agent-plan-state agent-plan-state-${item.status}`}>
          <PlanStatusIcon status={item.status} />
          {item.status === "approval" ? "waiting approval" : item.status}
        </span>
      </div>
      <ol className="agent-plan-steps">
        {item.steps.map((step) => (
          <AgentPlanStepRow key={step.id} step={step} current={step.id === item.currentStepId} />
        ))}
      </ol>
      <EventDetail detail={item.detail} />
    </section>
  );
}

function AgentPlanStepRow({ step, current }: { step: AutopilotAgentPlanStep; current: boolean }) {
  const label = step.kind === "approval" && step.status === "blocked"
    ? "waiting approval"
    : STATUS_LABELS[step.status] ?? step.status;
  const title = step.title || step.id;
  const meta = step.tool_name || step.skill_name || step.summary;
  return (
    <li className={`agent-plan-step agent-plan-step-${step.status}${current ? " agent-plan-step-current" : ""}`}>
      <PlanStatusIcon status={step.status} />
      <div className="agent-plan-step-copy">
        <div className="agent-plan-step-title">
          <span><PointerText text={title} /></span>
          <small>{label}</small>
        </div>
        {meta ? <p><PointerText text={meta} /></p> : null}
      </div>
    </li>
  );
}

function PlanStatusIcon({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="agent-plan-icon spin" aria-label="running" />;
  if (status === "completed" || status === "done") return <CheckCircle2 className="agent-plan-icon" aria-label="done" />;
  if (status === "failed") return <AlertCircle className="agent-plan-icon" aria-label="failed" />;
  if (status === "blocked" || status === "approval") return <PauseCircle className="agent-plan-icon" aria-label="waiting approval" />;
  if (status === "skipped") return <Clock3 className="agent-plan-icon" aria-label="skipped" />;
  return <Circle className="agent-plan-icon" aria-label={status || "pending"} />;
}
