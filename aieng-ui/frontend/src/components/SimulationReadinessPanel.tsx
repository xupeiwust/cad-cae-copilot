import { useMemo } from "react";

import {
  isReadinessMeaningful,
  readinessRows,
  type ReadinessStatus,
} from "../app/simulationReadiness";
import type { SimulationReadinessResponse } from "../types";

type SimulationReadinessPanelProps = {
  readiness: SimulationReadinessResponse | null;
  /** Prefill the composer with a "/simulate …" draft to fill a missing input. */
  onUseInChat?: (draft: string) => void;
};

const STATUS_WORD: Record<ReadinessStatus, string> = {
  present: "set",
  missing: "missing",
  defaultable: "default",
  unknown: "unknown",
};

/**
 * Read-only CAE readiness surface (the classifier behind /simulate): the six core
 * simulation inputs with present / missing / defaultable / unknown status. A
 * missing required input (material / loads / constraints) gets an "Add" that
 * drafts a /simulate into the composer — setup still flows through the existing
 * approval-gated path; this panel runs no solver and mutates nothing.
 */
export function SimulationReadinessPanel({ readiness, onUseInChat }: SimulationReadinessPanelProps) {
  const rows = useMemo(() => readinessRows(readiness), [readiness]);

  if (!isReadinessMeaningful(readiness)) return null;

  const missingRequired = readiness?.missing_required_inputs ?? [];
  const ready = Boolean(readiness?.ready_for_solver);

  return (
    <section className="readiness-card" aria-label="Simulation readiness">
      <div className="readiness-head">
        <strong>Simulation readiness</strong>
        <span className={ready ? "readiness-ok" : "readiness-blocked"}>
          {ready ? "ready" : `${missingRequired.length} required missing`}
        </span>
      </div>

      {rows.map((row) => (
        <div key={row.key} className="readiness-row">
          <span className={`readiness-status readiness-status-${row.status}`} title={STATUS_WORD[row.status]} />
          <span className="readiness-label">
            {row.label}
            {row.required ? <span className="readiness-required" title="required">*</span> : null}
          </span>
          <span className="readiness-detail">{row.detail ?? STATUS_WORD[row.status]}</span>
          {row.draft ? (
            <button
              type="button"
              className="readiness-add"
              onClick={() => onUseInChat?.(row.draft as string)}
              disabled={!onUseInChat}
              title={`Draft a /simulate to set ${row.label.toLowerCase()}`}
            >
              Add
            </button>
          ) : null}
        </div>
      ))}

      <div className="readiness-foot">
        <code>*</code> required. Click <strong>Add</strong> to draft a <code>/simulate</code> — the solver
        stays approval-gated.
      </div>
    </section>
  );
}
