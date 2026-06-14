import { useMemo } from "react";

import { shapeEditDiff } from "../app/editDiff";
import type { EditDiffResponse } from "../types";

type EditDiffPanelProps = {
  editDiff: EditDiffResponse | null;
};

/**
 * First-class "this edit changed X" panel (#226): re-surfaces the last CAD
 * edit's topology `regression_diff` + manufacturability `critique_diff` verdicts
 * (persisted to package state) so the trust signal isn't buried in raw tool
 * output. Collateral changes — parts that moved but were NOT the edit's target —
 * are rendered visually distinct. Read-only; renders nothing until an edit exists.
 */
export function EditDiffPanel({ editDiff }: EditDiffPanelProps) {
  const view = useMemo(() => shapeEditDiff(editDiff), [editDiff]);
  if (!view.hasData) return null;

  return (
    <section className="editdiff-card" aria-label="Last edit diff">
      <div className="editdiff-head">
        <strong>Last edit</strong>
        {view.tool ? <code className="editdiff-tool">{view.tool}</code> : null}
        {view.needsAttention ? (
          <span className="editdiff-flag editdiff-flag-bad">needs review</span>
        ) : (
          <span className="editdiff-flag editdiff-flag-good">clean</span>
        )}
      </div>

      {view.regression ? (
        <div className="editdiff-section">
          <div className={`editdiff-verdict editdiff-${view.regression.tone}`}>
            Topology: {view.regression.verdict}
          </div>
          <p className="editdiff-headline">{view.regression.headline}</p>
          {view.regression.changed.length > 0 ? (
            <ul className="editdiff-parts">
              {view.regression.changed.map((part) => (
                <li
                  key={part.name}
                  className={`editdiff-part ${part.collateral ? "editdiff-part-collateral" : ""}`}
                  title={part.collateral ? "Collateral — this part was NOT the edit's target" : "Intended change"}
                >
                  <code>{part.name}</code>
                  {part.maxChangeMm != null ? (
                    <span className="editdiff-delta">{part.maxChangeMm.toFixed(2)}mm</span>
                  ) : null}
                  {part.collateral ? <span className="editdiff-collateral-tag">collateral</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {(view.regression.added.length > 0 || view.regression.removed.length > 0) ? (
            <div className="editdiff-topo-changes">
              {view.regression.added.length > 0 ? <span>+ {view.regression.added.join(", ")}</span> : null}
              {view.regression.removed.length > 0 ? <span>− {view.regression.removed.join(", ")}</span> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {view.critique ? (
        <div className="editdiff-section">
          <div className={`editdiff-verdict editdiff-${view.critique.tone}`}>
            Manufacturability: {view.critique.verdict}
          </div>
          <p className="editdiff-headline">{view.critique.headline}</p>
          {view.critique.introducedCount > 0 ? (
            <span className="editdiff-flag editdiff-flag-bad">
              {view.critique.introducedCount} new finding{view.critique.introducedCount !== 1 ? "s" : ""}
            </span>
          ) : view.critique.resolvedCount > 0 ? (
            <span className="editdiff-flag editdiff-flag-good">
              {view.critique.resolvedCount} resolved
            </span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
