import { useState } from "react";

import type { CadGenerationProgress, CadStageStatus } from "../appTypes";

/**
 * Overlay panel that visualises the CAD generation pipeline as a vertical
 * step list with the LLM-generated build123d code preview underneath. The
 * panel replaces the previous spinner-only overlay so the user can see what
 * the system is actually doing during the (potentially minute-long) build.
 */
export function CadProgressPanel({ progress }: { progress: CadGenerationProgress }) {
  const [codeOpen, setCodeOpen] = useState(false);

  const completed = progress.stages.filter((s) => s.status === "completed").length;
  const total = progress.stages.length;
  const fractionPct = total > 0 ? Math.round((completed / total) * 100) : 0;

  const hasActive = progress.activeStage !== null;
  const headlineStage = progress.stages.find((s) => s.id === progress.activeStage) ?? progress.stages[progress.stages.length - 1];

  return (
    <div className="cad-progress-panel" role="status" aria-live="polite">
      <header className="cad-progress-panel__head">
        <div className="cad-progress-panel__title">
          {hasActive ? (
            <span className="cad-progress-panel__spinner" aria-hidden="true" />
          ) : progress.fatalError ? (
            <span className="cad-progress-panel__icon cad-progress-panel__icon--error">!</span>
          ) : (
            <span className="cad-progress-panel__icon cad-progress-panel__icon--done">✓</span>
          )}
          <strong>
            {progress.fatalError
              ? "CAD generation failed"
              : hasActive
                ? headlineStage.label
                : "CAD generation complete"}
          </strong>
        </div>
        <span className="cad-progress-panel__counter">{completed}/{total}</span>
      </header>

      <div className="cad-progress-bar" aria-hidden="true">
        <div className="cad-progress-bar__fill" style={{ width: `${fractionPct}%` }} />
      </div>

      <ul className="cad-progress-stage-list">
        {progress.stages.map((stage) => (
          <li key={stage.id} className={`cad-progress-stage cad-progress-stage--${stage.status}`}>
            <StageStatusIcon status={stage.status} />
            <div className="cad-progress-stage__body">
              <span className="cad-progress-stage__label">{stage.label}</span>
              {stage.message ? (
                <span className="cad-progress-stage__message">
                  {stage.message}
                  {stage.status === "active" && typeof stage.elapsedS === "number"
                    ? ` (${stage.elapsedS}s)`
                    : null}
                </span>
              ) : null}
              {stage.id === "retrying" && typeof stage.attempt === "number" ? (
                <span className="cad-progress-stage__hint">
                  Attempt {stage.attempt + 1}
                </span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {progress.codePreview ? (
        <div className="cad-progress-codeblock">
          <button
            type="button"
            className="cad-progress-codeblock__toggle"
            onClick={() => setCodeOpen((v) => !v)}
            aria-expanded={codeOpen}
          >
            <span>{codeOpen ? "▾" : "▸"}</span>
            <span>LLM-generated build123d code ({progress.codePreview.length} chars preview)</span>
          </button>
          {codeOpen ? (
            <pre className="cad-progress-codeblock__pre">{progress.codePreview}</pre>
          ) : null}
        </div>
      ) : null}

      {progress.errorPreview ? (
        <details className="cad-progress-errorblock">
          <summary>Last error</summary>
          <pre>{progress.errorPreview}</pre>
        </details>
      ) : null}

      {progress.fatalError ? (
        <div className="cad-progress-panel__fatal">{progress.fatalError}</div>
      ) : null}
    </div>
  );
}

function StageStatusIcon({ status }: { status: CadStageStatus }) {
  if (status === "completed") {
    return <span className="cad-progress-stage__icon cad-progress-stage__icon--completed" aria-hidden="true">✓</span>;
  }
  if (status === "active") {
    return <span className="cad-progress-stage__icon cad-progress-stage__icon--active" aria-hidden="true" />;
  }
  if (status === "failed") {
    return <span className="cad-progress-stage__icon cad-progress-stage__icon--failed" aria-hidden="true">✗</span>;
  }
  return <span className="cad-progress-stage__icon cad-progress-stage__icon--pending" aria-hidden="true">○</span>;
}
