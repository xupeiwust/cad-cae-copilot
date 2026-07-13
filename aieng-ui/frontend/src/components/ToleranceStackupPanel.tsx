import { useMemo } from "react";

import { Ruler } from "lucide-react";

import {
  controllingNames,
  formatCompact,
  isToleranceStackupReportMeaningful,
  toleranceStackupRows,
  toleranceStackupRunDraft,
  toleranceStackupSummary,
} from "../app/toleranceStackupReport";
import type { ToleranceStackupReport } from "../types";
import { PanelShell } from "./PanelShell";

type ToleranceStackupPanelProps = {
  report: ToleranceStackupReport | null;
  /** Prefill the composer with a read-only cad.tolerance_stackup rerun draft. */
  onUseInChat?: (draft: string) => void;
};

export function ToleranceStackupPanel({ report, onUseInChat }: ToleranceStackupPanelProps) {
  const rows = useMemo(() => (report ? toleranceStackupRows(report) : []), [report]);
  const runDraft = useMemo(() => (report ? toleranceStackupRunDraft(report) : null), [report]);
  const drivers = useMemo(() => (report ? controllingNames(report) : []), [report]);

  if (!isToleranceStackupReportMeaningful(report)) return null;

  return (
    <PanelShell
      storageKey="tolerancestackup"
      title="Tolerance stack-up"
      icon={<Ruler className="h-4 w-4" aria-hidden="true" />}
      summary={toleranceStackupSummary(report!)}
    >
      {runDraft ? (
        <div className="insp-panel-actions">
          <button
            type="button"
            className="tolerance-stackup-action"
            onClick={() => onUseInChat?.(runDraft)}
            disabled={!onUseInChat}
            title="Draft a read-only cad.tolerance_stackup call into the composer"
          >
            Recheck
          </button>
        </div>
      ) : null}

      <div className="tolerance-stackup-metrics">
        <div>
          <span>Worst-case</span>
          <strong>
            {formatCompact(report!.worst_case?.min)} to {formatCompact(report!.worst_case?.max)} mm
          </strong>
        </div>
        <div>
          <span>RSS {formatCompact(report!.rss?.confidence_level ? report!.rss.confidence_level * 100 : null)}%</span>
          <strong>
            {formatCompact(report!.rss?.min)} to {formatCompact(report!.rss?.max)} mm
          </strong>
        </div>
      </div>

      {drivers.length ? (
        <div className="tolerance-stackup-drivers">
          <span>Top drivers</span>
          {drivers.map((name) => (
            <code key={name}>{name}</code>
          ))}
        </div>
      ) : null}

      <div className="tolerance-stackup-table-wrap">
        <table className="tolerance-stackup-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Nominal</th>
              <th>+Tol</th>
              <th>-Tol</th>
              <th>Band</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td title={row.distribution}>{row.name}</td>
                <td>{formatCompact(row.nominal)}</td>
                <td>{formatCompact(row.plus)}</td>
                <td>{formatCompact(row.minus)}</td>
                <td>{formatCompact(row.toleranceBand)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="tolerance-stackup-foot">
        {(report!.assumptions ?? [])[0] ?? "Read-only 1D stack-up; not a GD&T solver."}
        {report!.artifact_path ? <> <code>{report!.artifact_path}</code></> : null}
      </div>
    </PanelShell>
  );
}
