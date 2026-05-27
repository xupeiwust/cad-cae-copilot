import type { ChatStep } from "../../types";

type AgentPlanCardProps = {
  steps: ChatStep[];
};

function planStepTone(status: string) {
  if (status === "failed") return "error";
  if (status === "done" || status === "completed") return "done";
  if (status === "needs_approval" || status === "awaiting_approval") return "approval";
  return "active";
}

function statusLabel(status: string) {
  if (status === "needs_approval" || status === "awaiting_approval") return "approval";
  if (status === "done") return "done";
  return status.replace(/_/g, " ");
}

export function AgentPlanCard({ steps }: AgentPlanCardProps) {
  if (!steps.length) return null;

  return (
    <div className="agent-plan-card">
      {steps.map((step, index) => {
        const tone = planStepTone(step.status);
        return (
          <div key={`${step.tool}-${index}`} className={`agent-plan-step status-${tone}`}>
            <div className="agent-plan-step-head">
              <code>{step.tool}</code>
              <span className={`agent-plan-step-status status-${tone}`}>{statusLabel(step.status)}</span>
            </div>
            <span>{step.description}</span>
          </div>
        );
      })}
    </div>
  );
}
