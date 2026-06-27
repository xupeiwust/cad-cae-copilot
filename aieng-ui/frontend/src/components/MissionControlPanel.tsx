import { AlertTriangle, CheckCircle2, Clipboard, PackageCheck, ShieldCheck } from "lucide-react";

import type { MissionControlModel, MissionControlStatus } from "../app/missionControl";

type MissionControlPanelProps = {
  model: MissionControlModel;
  onCopyDraft?: (draft: string) => void;
};

const STATUS_LABEL: Record<MissionControlStatus, string> = {
  ready: "ready",
  missing: "missing",
  blocked: "blocked",
  unknown: "unknown",
};

function statusIcon(status: MissionControlStatus) {
  if (status === "ready") return <CheckCircle2 className="h-4 w-4" aria-hidden="true" />;
  if (status === "blocked") return <AlertTriangle className="h-4 w-4" aria-hidden="true" />;
  return <ShieldCheck className="h-4 w-4" aria-hidden="true" />;
}

export function MissionControlPanel({ model, onCopyDraft }: MissionControlPanelProps) {
  return (
    <section className="mission-control-card" aria-label="Mission Control">
      <div className="mission-control-head">
        <div className="mission-control-title">
          <PackageCheck className="h-4 w-4" aria-hidden="true" />
          <div>
            <strong>Mission Control</strong>
            <span>{model.projectName}</span>
          </div>
        </div>
        <span className={`mission-status mission-status-${model.packageStatus}`}>
          {STATUS_LABEL[model.packageStatus]}
        </span>
      </div>

      <div className="mission-package">
        <div>
          <span>.aieng evidence package</span>
          <strong>{model.packageName}</strong>
        </div>
        <p>{model.packageDetail}</p>
      </div>

      <div className="mission-headline">
        <strong>{model.headline}</strong>
        <span>Package evidence, runtime state, and approvals stay separate.</span>
      </div>

      <div className="mission-trust-badges" aria-label="Evidence trust status">
        {model.trustBadges.map((badge) => (
          <span key={badge.key} className={`mission-trust-badge mission-trust-${badge.kind}`} title={badge.detail}>
            <strong>{badge.label}</strong>
            <em>{badge.detail}</em>
          </span>
        ))}
      </div>

      <div className="mission-grid">
        {model.cards.map((card) => (
          <article key={card.key} className={`mission-tile mission-tile-${card.status}`}>
            <div className="mission-tile-head">
              <span>{statusIcon(card.status)}</span>
              <strong>{card.label}</strong>
              <em>{STATUS_LABEL[card.status]}</em>
            </div>
            <p>{card.detail}</p>
            {card.meta ? <small>{card.meta}</small> : null}
          </article>
        ))}
      </div>

      <div className="mission-workflow" aria-label="Guided CAD to CAE workflow">
        <div className="mission-workflow-head">
          <strong>CAD to CAE workflow</strong>
          <span>ready / missing evidence / blocked</span>
        </div>
        <ol className="mission-workflow-list">
          {model.workflowSteps.map((step, index) => (
            <li key={step.key} className={`mission-workflow-step mission-workflow-${step.status}`}>
              <div className="mission-workflow-index">{index + 1}</div>
              <div className="mission-workflow-body">
                <div className="mission-workflow-row">
                  <strong>{step.label}</strong>
                  <em>{STATUS_LABEL[step.status]}</em>
                </div>
                <p>{step.detail}</p>
              </div>
              {step.draft ? (
                <button
                  type="button"
                  className="mission-workflow-copy"
                  onClick={() => onCopyDraft?.(step.draft as string)}
                  disabled={!onCopyDraft}
                  title={`Copy ${step.label} prompt`}
                  aria-label={`Copy ${step.label} prompt`}
                >
                  <Clipboard className="h-3 w-3" aria-hidden="true" />
                </button>
              ) : null}
            </li>
          ))}
        </ol>
      </div>

      <div className="mission-action">
        <div>
          <span>Next safe action</span>
          <strong>{model.nextAction.label}</strong>
          <p>{model.nextAction.detail}</p>
        </div>
        {model.nextAction.draft ? (
          <button
            type="button"
            className="mission-copy"
            onClick={() => onCopyDraft?.(model.nextAction.draft as string)}
            disabled={!onCopyDraft}
            title="Copy bounded agent prompt"
          >
            <Clipboard className="h-4 w-4" aria-hidden="true" />
            <span>Copy prompt</span>
          </button>
        ) : null}
      </div>

      <div className="mission-notes">
        {model.evidenceNotes.map((note) => (
          <span key={note}>{note}</span>
        ))}
      </div>
    </section>
  );
}
