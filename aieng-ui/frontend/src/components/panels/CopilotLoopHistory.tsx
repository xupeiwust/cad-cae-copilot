import { useCallback, useMemo, useState, type ReactNode } from "react";
import { api } from "../../api";
import type {
  CopilotLoopDecision,
  CopilotLoopExportResponse,
  CopilotLoopMetricSummary,
  CopilotLoopProposalSummary,
  CopilotLoopReportDiff,
  CopilotLoopSummary,
  CopilotLoopTargetSummary,
} from "../../types";

const UNKNOWN = "Unknown";
const NOT_AVAILABLE = "Not available";

export function decisionLabel(decision?: CopilotLoopDecision | null): string {
  switch (decision) {
    case "approved": return "Approved";
    case "rejected": return "Rejected";
    case "pending": return "Pending approval";
    case "blocked": return "Blocked (verification)";
    case "error": return "Error";
    case "none":
    case undefined:
    case null:
      return "No decision";
    default:
      return String(decision);
  }
}

export function decisionBadgeClass(decision?: CopilotLoopDecision | null): string {
  switch (decision) {
    case "approved": return "badge badge-pass";
    case "rejected": return "badge";
    case "pending": return "badge badge-warn";
    case "blocked": return "badge badge-warn";
    case "error": return "badge badge-fail";
    default: return "badge badge-muted";
  }
}

export function statusBadgeClass(status?: string | null): string {
  if (status === "completed") return "badge badge-pass";
  if (status === "error") return "badge badge-fail";
  if (status === "active" || status === "partial") return "badge badge-warn";
  return "badge badge-muted";
}

export function formatProposalLine(proposal?: CopilotLoopProposalSummary | null): string {
  if (!proposal) return NOT_AVAILABLE;
  const feature = proposal.feature_ref ?? UNKNOWN;
  const action = proposal.action_type ?? UNKNOWN;
  const name = proposal.parameter_name ?? UNKNOWN;
  const from = proposal.parameter_from ?? "?";
  const to = proposal.parameter_to ?? "?";
  return `${feature} · ${action} · ${name}: ${String(from)} → ${String(to)}`;
}

export function formatMetricSummary(summary?: CopilotLoopMetricSummary | null): string {
  if (!summary || summary.total === 0) return NOT_AVAILABLE;
  return `${summary.improved} improved · ${summary.regressed} regressed · ${summary.unchanged} unchanged · ${summary.unknown} unknown (of ${summary.total})`;
}

export function formatTargetSummary(summary?: CopilotLoopTargetSummary | null): string {
  if (!summary || summary.total === 0) return NOT_AVAILABLE;
  const parts = [
    `${summary.pass} pass`,
    `${summary.fail} fail`,
  ];
  if (summary.not_evaluated) parts.push(`${summary.not_evaluated} not evaluated`);
  if (summary.unknown) parts.push(`${summary.unknown} unknown`);
  parts.push(`of ${summary.total}`);
  return parts.join(" · ");
}

export function shortDate(iso?: string | null): string {
  if (!iso) return UNKNOWN;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

type HistoryTableProps = {
  summaries: CopilotLoopSummary[];
  activeLoopId?: string | null;
  compareSelection: string[];
  onReopen: (loopId: string) => void;
  onToggleCompare: (loopId: string) => void;
  onCompareNow: () => void;
  onClearCompare: () => void;
};

export function CopilotLoopHistoryTable(props: HistoryTableProps) {
  const { summaries, activeLoopId, compareSelection, onReopen, onToggleCompare, onCompareNow, onClearCompare } = props;
  const canCompare = compareSelection.length === 2;
  const singleLoopOnly = summaries.length === 1;

  if (!summaries.length) {
    return (
      <article className="copilot-loop__subcard copilot-loop__subcard--empty">
        <strong>No prior loops</strong>
        <p className="panel__hint">
          No Copilot loops have been run for this project yet. Click <em>Start loop</em> above, or seed the demo project to see two pre-baked loops.
        </p>
      </article>
    );
  }

  return (
    <article className="copilot-loop__history">
      <header className="copilot-loop__history-header">
        <strong>Loop history ({summaries.length})</strong>
        <div className="button-row">
          <button
            type="button"
            className="primary-button compact-button"
            disabled={!canCompare}
            onClick={onCompareNow}
          >
            Compare selected ({compareSelection.length}/2)
          </button>
          {compareSelection.length ? (
            <button type="button" className="ghost-button compact-button" onClick={onClearCompare}>
              Clear compare
            </button>
          ) : null}
        </div>
      </header>
      <div className="table-scroll">
        <table className="mini-table copilot-loop__history-table">
          <thead>
            <tr>
              <th aria-label="Compare select"></th>
              <th>Loop</th>
              <th>Updated</th>
              <th>Status</th>
              <th>Decision</th>
              <th>Proposal</th>
              <th>Warn / Err</th>
              <th>Report</th>
              <th aria-label="Actions"></th>
            </tr>
          </thead>
          <tbody>
            {summaries.map((s) => {
              const isActive = activeLoopId === s.loop_id;
              const selected = compareSelection.includes(s.loop_id);
              const disabledCompare = !selected && compareSelection.length >= 2;
              return (
                <tr key={s.loop_id} className={isActive ? "copilot-loop__history-row--active" : undefined}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select loop ${s.loop_id} for comparison`}
                      checked={selected}
                      disabled={disabledCompare}
                      onChange={() => onToggleCompare(s.loop_id)}
                    />
                  </td>
                  <td><code>{s.loop_id}</code>{isActive ? <span className="panel__hint"> (open)</span> : null}</td>
                  <td>{shortDate(s.updated_at ?? s.created_at)}</td>
                  <td>
                    <span className={statusBadgeClass(s.status)}>{s.status ?? UNKNOWN}</span>
                    {s.waiting_for_approval ? <span className="badge badge-warn">waiting</span> : null}
                  </td>
                  <td><span className={decisionBadgeClass(s.decision)}>{decisionLabel(s.decision)}</span></td>
                  <td className="copilot-loop__history-proposal">{formatProposalLine(s.proposal_summary)}</td>
                  <td>
                    <span className={s.warning_count ? "badge badge-warn" : "badge badge-muted"}>{s.warning_count ?? 0}</span>{" "}
                    <span className={s.error_count ? "badge badge-fail" : "badge badge-muted"}>{s.error_count ?? 0}</span>
                  </td>
                  <td>
                    {s.report_path ? <code title={s.report_path}>{s.report_path.split("/").pop()}</code> : <span className="panel__hint">{NOT_AVAILABLE}</span>}
                  </td>
                  <td>
                    <button type="button" className="ghost-button compact-button" onClick={() => onReopen(s.loop_id)} disabled={isActive}>
                      {isActive ? "Open" : "Reopen"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="panel__hint">
        Rejected loops are decision records, not engineering failures. Counts and previews are derived from persisted state; missing data is shown as {NOT_AVAILABLE} or {UNKNOWN}.
      </p>
      {singleLoopOnly ? (
        <p className="panel__hint">
          Only one loop exists for this project — comparison needs two. Start another loop or seed the demo project to enable compare.
        </p>
      ) : !canCompare && compareSelection.length < 2 ? (
        <p className="panel__hint">
          Tick the compare checkbox on two loops to enable the side-by-side compare and report diff.
        </p>
      ) : null}
    </article>
  );
}

type CompareCellProps = { label: string; left: ReactNode; right: ReactNode };
function CompareRow({ label, left, right }: CompareCellProps) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{left}</td>
      <td>{right}</td>
    </tr>
  );
}

type CompareProps = {
  projectId: string | null;
  left: CopilotLoopSummary;
  right: CopilotLoopSummary;
  onClose: () => void;
  onReopen: (loopId: string) => void;
};

type DiffState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; diff: CopilotLoopReportDiff };

type ExportState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; result: CopilotLoopExportResponse };

export function CopilotLoopComparePanel({ projectId, left, right, onClose, onReopen }: CompareProps) {
  const both = useMemo(() => [left, right] as const, [left, right]);
  const anyMetrics = both.some((s) => s.metric_summary && s.metric_summary.total > 0);
  const anyTargets = both.some((s) => s.target_summary && s.target_summary.total > 0);

  const [diffState, setDiffState] = useState<DiffState>({ status: "idle" });
  const [showRaw, setShowRaw] = useState(false);
  const [exportState, setExportState] = useState<ExportState>({ status: "idle" });
  const [includeReports, setIncludeReports] = useState(false);
  const [includeDiff, setIncludeDiff] = useState(true);
  const [includeHighlights, setIncludeHighlights] = useState(true);

  const loadDiff = useCallback(async () => {
    if (!projectId) {
      setDiffState({ status: "error", message: "No project selected." });
      return;
    }
    setDiffState({ status: "loading" });
    try {
      const diff = await api.compareCopilotLoopReports(projectId, left.loop_id, right.loop_id);
      setDiffState({ status: "loaded", diff });
    } catch (err) {
      setDiffState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [projectId, left.loop_id, right.loop_id]);

  const runExport = useCallback(async () => {
    if (!projectId) {
      setExportState({ status: "error", message: "No project selected." });
      return;
    }
    setExportState({ status: "loading" });
    try {
      const result = await api.exportCopilotLoopReview(projectId, {
        loop_ids: [left.loop_id, right.loop_id],
        include_reports: includeReports,
        include_diff: includeDiff,
        include_highlights: includeHighlights,
      });
      setExportState({ status: "loaded", result });
    } catch (err) {
      setExportState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [projectId, left.loop_id, right.loop_id, includeReports, includeDiff, includeHighlights]);

  return (
    <article className="copilot-loop__compare">
      <header className="copilot-loop__compare-header">
        <strong>Compare two Copilot loops</strong>
        <button type="button" className="ghost-button compact-button" onClick={onClose}>Close compare</button>
      </header>
      <p className="panel__hint">
        Based on available computed metrics. This comparison does not certify either design and does not advance engineering claims. Missing metrics are shown as {UNKNOWN}.
      </p>
      <div className="table-scroll">
        <table className="mini-table copilot-loop__compare-table">
          <thead>
            <tr>
              <th></th>
              <th>Left · <code>{left.loop_id}</code> <button type="button" className="ghost-button compact-button" onClick={() => onReopen(left.loop_id)}>Open</button></th>
              <th>Right · <code>{right.loop_id}</code> <button type="button" className="ghost-button compact-button" onClick={() => onReopen(right.loop_id)}>Open</button></th>
            </tr>
          </thead>
          <tbody>
            <CompareRow
              label="Updated"
              left={shortDate(left.updated_at ?? left.created_at)}
              right={shortDate(right.updated_at ?? right.created_at)}
            />
            <CompareRow
              label="Loop status"
              left={<span className={statusBadgeClass(left.status)}>{left.status ?? UNKNOWN}</span>}
              right={<span className={statusBadgeClass(right.status)}>{right.status ?? UNKNOWN}</span>}
            />
            <CompareRow
              label="Approval decision"
              left={<span className={decisionBadgeClass(left.decision)}>{decisionLabel(left.decision)}</span>}
              right={<span className={decisionBadgeClass(right.decision)}>{decisionLabel(right.decision)}</span>}
            />
            <CompareRow
              label="Proposal"
              left={formatProposalLine(left.proposal_summary)}
              right={formatProposalLine(right.proposal_summary)}
            />
            <CompareRow
              label="Verification verdict"
              left={left.verification_status ?? UNKNOWN}
              right={right.verification_status ?? UNKNOWN}
            />
            <CompareRow
              label="Stale artifacts"
              left={left.stale_artifact_count ?? 0}
              right={right.stale_artifact_count ?? 0}
            />
            <CompareRow
              label="Warnings / Errors"
              left={`${left.warning_count ?? 0} / ${left.error_count ?? 0}`}
              right={`${right.warning_count ?? 0} / ${right.error_count ?? 0}`}
            />
            <CompareRow
              label="Metric delta summary"
              left={formatMetricSummary(left.metric_summary)}
              right={formatMetricSummary(right.metric_summary)}
            />
            <CompareRow
              label="Design target summary"
              left={formatTargetSummary(left.target_summary)}
              right={formatTargetSummary(right.target_summary)}
            />
            <CompareRow
              label="Report"
              left={left.report_path ? <code>{left.report_path}</code> : <span className="panel__hint">{NOT_AVAILABLE}</span>}
              right={right.report_path ? <code>{right.report_path}</code> : <span className="panel__hint">{NOT_AVAILABLE}</span>}
            />
          </tbody>
        </table>
      </div>
      {!anyMetrics && !anyTargets ? (
        <p className="panel__hint">
          Neither loop carries computed metric deltas or design target results yet. Comparison is structural only; no metric-side comparison is implied.
        </p>
      ) : null}
      <p className="panel__hint">
        A rejected loop is a valid decision record, not an engineering failure. This view is a quick decision-review aid, not a basis for design certification.
      </p>
      <CopilotLoopReportDiffSection
        diffState={diffState}
        onLoadDiff={loadDiff}
        showRaw={showRaw}
        onToggleRaw={() => setShowRaw((v) => !v)}
        leftReportPath={left.report_path}
        rightReportPath={right.report_path}
      />
      <CopilotLoopExportSection
        exportState={exportState}
        onExport={runExport}
        includeReports={includeReports}
        includeDiff={includeDiff}
        includeHighlights={includeHighlights}
        onToggleReports={() => setIncludeReports((v) => !v)}
        onToggleDiff={() => setIncludeDiff((v) => !v)}
        onToggleHighlights={() => setIncludeHighlights((v) => !v)}
      />
    </article>
  );
}

type ExportSectionProps = {
  exportState: ExportState;
  onExport: () => void;
  includeReports: boolean;
  includeDiff: boolean;
  includeHighlights: boolean;
  onToggleReports: () => void;
  onToggleDiff: () => void;
  onToggleHighlights: () => void;
};

function CopilotLoopExportSection({
  exportState,
  onExport,
  includeReports,
  includeDiff,
  includeHighlights,
  onToggleReports,
  onToggleDiff,
  onToggleHighlights,
}: ExportSectionProps) {
  return (
    <section className="copilot-loop__review-export">
      <header className="copilot-loop__review-export-header">
        <strong>Export decision review</strong>
        <button
          type="button"
          className="primary-button compact-button"
          onClick={onExport}
          disabled={exportState.status === "loading"}
        >
          {exportState.status === "loading"
            ? "Exporting…"
            : exportState.status === "loaded"
              ? "Re-export"
              : "Export review"}
        </button>
      </header>
      <p className="panel__hint">
        Writes a Markdown decision-review artifact into the project package and into the project workspace. The export does not certify the design and does not advance engineering claims.
      </p>
      <div className="copilot-loop__review-export-options">
        <label>
          <input type="checkbox" checked={includeHighlights} onChange={onToggleHighlights} />
          Include What Changed highlights
        </label>
        <label>
          <input type="checkbox" checked={includeDiff} onChange={onToggleDiff} />
          Include unified report diff
        </label>
        <label>
          <input type="checkbox" checked={includeReports} onChange={onToggleReports} />
          Embed both raw reports
        </label>
      </div>
      {exportState.status === "error" ? (
        <div className="inline-error">Failed to export review: {exportState.message}</div>
      ) : null}
      {exportState.status === "loaded" ? (
        <article className="copilot-loop__review-export-result">
          <p>
            Export written to <code>{exportState.result.export_path}</code>.
          </p>
          {exportState.result.warnings?.length ? (
            <ul className="warning-list">
              {exportState.result.warnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
            </ul>
          ) : null}
          {exportState.result.export_text ? (
            <pre className="markdown-preview copilot-loop__review-export-preview" aria-label="Export preview">
              {exportState.result.export_text.slice(0, 6000)}
              {exportState.result.export_text.length > 6000 ? "\n\n[…truncated preview]" : ""}
            </pre>
          ) : null}
          <p className="panel__hint">{exportState.result.claim_boundary}</p>
        </article>
      ) : null}
    </section>
  );
}

type DiffSectionProps = {
  diffState: DiffState;
  onLoadDiff: () => void;
  showRaw: boolean;
  onToggleRaw: () => void;
  leftReportPath?: string | null;
  rightReportPath?: string | null;
};

function CopilotLoopReportDiffSection({
  diffState,
  onLoadDiff,
  showRaw,
  onToggleRaw,
  leftReportPath,
  rightReportPath,
}: DiffSectionProps) {
  return (
    <section className="copilot-loop__report-diff">
      <header className="copilot-loop__report-diff-header">
        <strong>Report diff</strong>
        <div className="button-row">
          <button
            type="button"
            className="primary-button compact-button"
            onClick={onLoadDiff}
            disabled={diffState.status === "loading"}
          >
            {diffState.status === "loading"
              ? "Loading…"
              : diffState.status === "loaded"
                ? "Reload report diff"
                : "Load report diff"}
          </button>
          {diffState.status === "loaded" ? (
            <button type="button" className="ghost-button compact-button" onClick={onToggleRaw}>
              {showRaw ? "Show unified diff" : "Show raw reports"}
            </button>
          ) : null}
        </div>
      </header>
      <p className="panel__hint">
        On-demand: this loads two Markdown report artifacts and shows their unified diff. It does not certify either design, does not advance engineering claims, and does not interpret missing content. Missing reports are shown as {NOT_AVAILABLE}.
      </p>
      {diffState.status === "idle" ? (
        <p className="panel__hint">
          Click <em>Load report diff</em> to compare{" "}
          {leftReportPath ? <code>{leftReportPath}</code> : <span>{NOT_AVAILABLE}</span>}
          {" vs "}
          {rightReportPath ? <code>{rightReportPath}</code> : <span>{NOT_AVAILABLE}</span>}.
        </p>
      ) : null}
      {diffState.status === "loading" ? <p className="panel__hint">Loading report diff…</p> : null}
      {diffState.status === "error" ? (
        <div className="inline-error">Failed to load report diff: {diffState.message}</div>
      ) : null}
      {diffState.status === "loaded" ? (
        <CopilotLoopReportDiffView diff={diffState.diff} showRaw={showRaw} />
      ) : null}
    </section>
  );
}

function CopilotLoopReportDiffView({ diff, showRaw }: { diff: CopilotLoopReportDiff; showRaw: boolean }) {
  const bothExist = diff.left_report_exists && diff.right_report_exists;
  return (
    <>
      <div className="copilot-loop__report-diff-meta">
        <span>
          Left:{" "}
          {diff.left_report_exists ? (
            <code>{diff.left_report_path ?? UNKNOWN}</code>
          ) : (
            <span className="panel__hint">{NOT_AVAILABLE}</span>
          )}
          {diff.left_report_truncated ? <em> (truncated)</em> : null}
        </span>
        <span>
          Right:{" "}
          {diff.right_report_exists ? (
            <code>{diff.right_report_path ?? UNKNOWN}</code>
          ) : (
            <span className="panel__hint">{NOT_AVAILABLE}</span>
          )}
          {diff.right_report_truncated ? <em> (truncated)</em> : null}
        </span>
        {bothExist ? (
          <span>
            <span className="badge badge-pass">+{diff.added_lines}</span>{" "}
            <span className="badge badge-fail">−{diff.removed_lines}</span>
          </span>
        ) : null}
      </div>
      {diff.warnings?.length ? (
        <ul className="warning-list">
          {diff.warnings.map((w, idx) => (
            <li key={idx}>{w}</li>
          ))}
        </ul>
      ) : null}
      <CopilotLoopWhatChangedSection highlights={diff.highlights ?? []} />
      {bothExist ? (
        showRaw ? (
          <div className="copilot-loop__report-diff-raw">
            <pre className="markdown-preview" aria-label="Left report">
              {diff.left_text ?? ""}
            </pre>
            <pre className="markdown-preview" aria-label="Right report">
              {diff.right_text ?? ""}
            </pre>
          </div>
        ) : (
          <pre className="markdown-preview copilot-loop__report-diff-unified" aria-label="Unified diff">
            {diff.unified_diff ?? "(no textual differences)"}
          </pre>
        )
      ) : (
        <p className="panel__hint">
          One or both reports are {NOT_AVAILABLE}. Reports are written when a loop reaches the <em>Generate loop report</em> step; nothing is auto-generated here.
        </p>
      )}
      <p className="panel__hint">{diff.claim_boundary}</p>
    </>
  );
}

function highlightStatusClass(status: string): string {
  if (status === "changed") return "badge badge-warn";
  if (status === "missing") return "badge badge-fail";
  if (status === "unknown") return "badge badge-muted";
  return "badge badge-pass";
}

function highlightSeverityClass(severity?: string | null): string {
  if (severity === "critical") return "badge badge-fail";
  if (severity === "warning") return "badge badge-warn";
  return "badge badge-muted";
}

function CopilotLoopWhatChangedSection({
  highlights,
}: {
  highlights: CopilotLoopReportDiff["highlights"] extends infer T ? Exclude<T, undefined> : never;
}) {
  if (!highlights.length) {
    return (
      <section className="copilot-loop__what-changed copilot-loop__subcard--empty">
        <strong>What changed</strong>
        <p className="panel__hint">No structured highlights available.</p>
      </section>
    );
  }
  return (
    <section className="copilot-loop__what-changed">
      <strong>What changed</strong>
      <p className="panel__hint">
        Structured highlights derived from persisted loop state and report presence. They are a guide, not a replacement for the unified diff below. No engineering claim is advanced by this summary.
      </p>
      <div className="table-scroll">
        <table className="mini-table copilot-loop__what-changed-table">
          <thead>
            <tr>
              <th>Highlight</th>
              <th>Status</th>
              <th>Severity</th>
              <th>Left</th>
              <th>Right</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {highlights.map((h) => (
              <tr key={h.id} className={`copilot-loop__what-changed-row--${h.severity ?? "info"}`}>
                <td>{h.label}</td>
                <td><span className={highlightStatusClass(h.status)}>{h.status}</span></td>
                <td><span className={highlightSeverityClass(h.severity)}>{h.severity ?? "info"}</span></td>
                <td>{h.left ?? UNKNOWN}</td>
                <td>{h.right ?? UNKNOWN}</td>
                <td>{h.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
