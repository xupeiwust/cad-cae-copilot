import { useMemo } from "react";

import {
  acceptDraftForCandidate,
  FEASIBILITY_LABEL,
  formatMetricValue,
  groupCandidatesByFeasibility,
  isStudyMeaningful,
  type OptimizationCandidate,
  type OptimizationStudy,
} from "../app/optimizationStudy";

type OptimizationPanelProps = {
  study: OptimizationStudy;
  /** Prefill the composer with an approval-gated accept draft for a candidate. */
  onUseInChat?: (draft: string) => void;
};

/**
 * Read-only optimization study surface (the agent-guided sizing loop behind
 * design-study) surfaced as a workbench panel: candidate ranking grouped by
 * feasibility, advisory recommendation with caveats, and study report summary.
 *
 * Honesty signals are visible, not hidden: advisory_only, safe_to_accept,
 * baseline_modified, and missing-metric unknown states are all rendered.
 *
 * The Accept action drafts a /design-study command into the composer — the actual
 * accept still flows through the existing approval-gated path; this panel never
 * mutates geometry directly.
 */
export function OptimizationPanel({ study, onUseInChat }: OptimizationPanelProps) {
  const groups = useMemo(() => groupCandidatesByFeasibility(study.candidates), [study.candidates]);

  if (!isStudyMeaningful(study)) return null;

  return (
    <section className="optimization-card" aria-label="Optimization study">
      <div className="optimization-head">
        <strong>Optimization study</strong>
        <span>
          {study.candidates.length} candidate{study.candidates.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Honesty banner */}
      {study.warnings.length > 0 && (
        <div className="optimization-warnings">
          {study.warnings.map((w, i) => (
            <span key={i} className="optimization-warning">⚠ {w}</span>
          ))}
        </div>
      )}
      {study.baseline_modified === true && (
        <div className="optimization-honesty optimization-honesty-bad">
          Baseline was modified — unexpected for a sizing study
        </div>
      )}
      {study.baseline_modified === false && (
        <div className="optimization-honesty optimization-honesty-good">
          Baseline untouched
        </div>
      )}

      {/* Candidate ranking */}
      {groups.map((group) => (
        <div key={group.feasibility} className="optimization-group">
          <div className={`optimization-feasibility optimization-feasibility-${group.feasibility}`}>
            {FEASIBILITY_LABEL[group.feasibility]}
            <span className="optimization-feasibility-count">{group.candidates.length}</span>
          </div>

          {group.candidates.map((candidate) => (
            <CandidateRow
              key={candidate.candidate_id}
              candidate={candidate}
              safeToAccept={study.safe_to_accept}
              onUseInChat={onUseInChat}
            />
          ))}
        </div>
      ))}

      {/* Recommendation */}
      {study.recommendation && (
        <div className="optimization-recommendation">
          <div className="optimization-recommendation-head">
            <strong>Recommendation</strong>
            {study.recommendation.advisory_only !== false && (
              <span className="optimization-advisory-badge">Advisory only</span>
            )}
          </div>
          {study.recommendation.headline ? (
            <p className="optimization-recommendation-text">{study.recommendation.headline}</p>
          ) : null}
          {study.recommendation.reason_codes.length > 0 ? (
            <ul className="optimization-reason-list">
              {study.recommendation.reason_codes.map((code, i) => (
                <li key={i}>{code}</li>
              ))}
            </ul>
          ) : null}
          {study.recommendation.caveats.length > 0 ? (
            <div className="optimization-caveats">
              <strong>Caveats</strong>
              {study.recommendation.caveats.map((c, i) => (
                <span key={i} className="optimization-caveat">{c}</span>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {/* Report summary */}
      {study.report?.summary ? (
        <div className="optimization-report">
          <strong>Report</strong>
          <p className="optimization-report-text">{study.report.summary}</p>
        </div>
      ) : null}

      <div className="optimization-foot">
        Click <strong>Accept</strong> to draft a <code>/design-study</code> — acceptance stays approval-gated.
      </div>
    </section>
  );
}

function CandidateRow({
  candidate,
  safeToAccept,
  onUseInChat,
}: {
  candidate: OptimizationCandidate;
  safeToAccept: boolean;
  onUseInChat?: (draft: string) => void;
}) {
  const metricEntries = useMemo(() => Object.entries(candidate.metrics ?? {}), [candidate.metrics]);

  const draft = acceptDraftForCandidate(candidate.candidate_id);
  const canAccept = safeToAccept && candidate.feasibility === "feasible";

  return (
    <div className={`optimization-row ${candidate.has_unknown_metrics ? "optimization-row-unknown" : ""}`}>
      <div className="optimization-row-main">
        <span className="optimization-rank">#{candidate.rank}</span>
        <code className="optimization-candidate-id" title={`candidate ${candidate.candidate_id}`}>
          {candidate.candidate_id}
        </code>
        {candidate.score != null ? (
          <span className="optimization-score" title="score">
            {formatMetricValue(candidate.score)}
          </span>
        ) : null}
        {candidate.confidence ? (
          <span className={`optimization-confidence optimization-confidence-${candidate.confidence}`}>
            {candidate.confidence}
          </span>
        ) : null}
        {candidate.has_unknown_metrics && (
          <span className="optimization-unknown-badge" title="Some metrics are missing or unknown">
            unknown
          </span>
        )}
      </div>

      {metricEntries.length > 0 && (
        <div className="optimization-metrics">
          {metricEntries.map(([key, value]) => (
            <span key={key} className="optimization-metric" title={key}>
              <span className="optimization-metric-key">{key}</span>
              <span className="optimization-metric-value">{formatMetricValue(value)}</span>
            </span>
          ))}
        </div>
      )}

      {canAccept ? (
        <button
          type="button"
          className="optimization-accept"
          onClick={() => onUseInChat?.(draft)}
          disabled={!onUseInChat}
          title={`Draft a /design-study accept for ${candidate.candidate_id}`}
        >
          Accept
        </button>
      ) : (
        <button
          type="button"
          className="optimization-accept optimization-accept-disabled"
          disabled
          title={
            candidate.feasibility !== "feasible"
              ? "Only feasible candidates can be accepted"
              : "Not safe to accept — review warnings"
          }
        >
          Accept
        </button>
      )}
    </div>
  );
}
