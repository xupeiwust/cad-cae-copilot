import { AlertCircle, Ban, CheckCircle2, Circle, Clock3, Loader2, PauseCircle } from "lucide-react";

import type { TranscriptAgentPlanLine } from "../../app/chatTranscript";
import type { AutopilotAgentPlanStep } from "../../types";
import { PointerText } from "../PointerText";
import { EventDetail } from "../chat/EventDetail";

type AgentPlanCardProps = {
  item: TranscriptAgentPlanLine;
};

type PlanDiagnostic = {
  label: string;
  text: string;
  tone: "error" | "warning" | "output";
};

const STATUS_LABELS: Record<string, string> = {
  pending: "pending",
  running: "running",
  completed: "done",
  blocked: "waiting approval",
  failed: "failed",
  skipped: "skipped",
  cancelled: "cancelled",
};

export function AgentPlanCard({ item }: AgentPlanCardProps) {
  const diagnostics = planDiagnostics(item);
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
      {diagnostics.length ? (
        <div className="agent-plan-diagnostics">
          {diagnostics.map((diagnostic) => (
            <div key={`${diagnostic.label}-${diagnostic.text}`} className={`agent-plan-diagnostic agent-plan-diagnostic-${diagnostic.tone}`}>
              <span>{diagnostic.label}</span>
              <p><PointerText text={diagnostic.text} /></p>
            </div>
          ))}
        </div>
      ) : null}
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
  if (status === "cancelled") return <Ban className="agent-plan-icon" aria-label="cancelled" />;
  if (status === "blocked" || status === "approval") return <PauseCircle className="agent-plan-icon" aria-label="waiting approval" />;
  if (status === "skipped") return <Clock3 className="agent-plan-icon" aria-label="skipped" />;
  return <Circle className="agent-plan-icon" aria-label={status || "pending"} />;
}

function planDiagnostics(item: TranscriptAgentPlanLine): PlanDiagnostic[] {
  const diagnostics: PlanDiagnostic[] = [];

  for (const blocker of item.currentBlockers ?? []) {
    pushDiagnostic(diagnostics, { label: "Blocker", text: blocker, tone: "warning" });
  }
  for (const error of item.errors ?? []) {
    pushDiagnostic(diagnostics, { label: "Error", text: error, tone: "error" });
  }

  const prioritySteps = item.steps.filter((step) =>
    step.status === "failed" ||
    step.status === "blocked" ||
    step.id === item.currentStepId,
  );
  for (const step of prioritySteps) {
    const text = stepDiagnosticText(step);
    if (!text) continue;
    pushDiagnostic(diagnostics, {
      label: step.status === "failed" ? "Failed" : step.status === "blocked" ? "Waiting" : "Current",
      text,
      tone: step.status === "failed" ? "error" : step.status === "blocked" ? "warning" : "output",
    });
  }

  if (!diagnostics.some((item) => item.tone === "output")) {
    for (const step of item.steps.filter((step) => step.status === "completed").slice(-2)) {
      const text = stepOutputText(step);
      if (text) pushDiagnostic(diagnostics, { label: "Output", text, tone: "output" });
    }
  }

  return diagnostics.slice(0, 4);
}

function stepDiagnosticText(step: AutopilotAgentPlanStep): string {
  const evidence = step.evidence ?? {};
  return firstString(
    evidence.error,
    evidence.error_message,
    evidence.diagnostic,
    evidence.blocked_reason,
    evidence.blocker,
    evidence.reason,
    evidence.rejection_reason,
    step.summary,
  );
}

function stepOutputText(step: AutopilotAgentPlanStep): string {
  const evidence = step.evidence ?? {};
  const output = objectValue(evidence.output) ?? evidence;
  const namedParts = stringArray(output.named_parts);
  const partsAdded = stringArray(output.parts_added);
  const artifacts = stringArray(output.artifact_paths).concat(stringArray(output.written_artifacts));
  if (partsAdded.length) return `Added ${partsAdded.slice(0, 4).join(", ")}${partsAdded.length > 4 ? "..." : ""}`;
  if (namedParts.length) return `Named parts: ${namedParts.slice(0, 4).join(", ")}${namedParts.length > 4 ? "..." : ""}`;
  if (artifacts.length) return `Artifacts: ${artifacts.slice(0, 3).join(", ")}${artifacts.length > 3 ? "..." : ""}`;
  return firstString(
    output.result_summary,
    output.summary,
    output.message,
    output.verdict,
    output.status,
    step.summary,
  );
}

function pushDiagnostic(items: PlanDiagnostic[], next: PlanDiagnostic) {
  const text = next.text.trim();
  if (!text || items.some((item) => item.text === text && item.label === next.label)) return;
  items.push({ ...next, text: text.length > 280 ? `${text.slice(0, 277)}...` : text });
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}
