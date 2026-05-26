import { useCallback, useEffect, useState } from "react";

import { api } from "../../api";
import type {
  CadRecommendationProposal,
  CadRecommendationsResponse,
  CadVerificationCheck,
  CadVerificationVerdict,
  RuntimeRun,
} from "../../types";

type RecommendationsPanelProps = {
  selectedId: string | null;
};

type Strictness = "lenient" | "default" | "strict";

type ApplyEntry = {
  run?: RuntimeRun;
  acknowledged: boolean;
};

function verdictBadgeClass(verdict?: string): string {
  if (verdict === "pass") return "badge badge-pass";
  if (verdict === "warn") return "badge badge-warn";
  if (verdict === "fail") return "badge badge-fail";
  return "badge";
}

function statusBadgeClass(status?: string): string {
  if (status === "completed") return "badge badge-pass";
  if (status === "failed" || status === "rejected" || status === "cancelled") return "badge badge-fail";
  if (status === "awaiting_approval" || status === "pending" || status === "running") return "badge badge-warn";
  return "badge";
}

function checkStatusGlyph(status?: string): string {
  if (status === "pass") return "[pass]";
  if (status === "fail") return "[fail]";
  if (status === "warn") return "[warn]";
  if (status === "skipped") return "[skip]";
  return "[?]";
}

function ProposalCard({
  proposal,
  verdict,
  selectedId,
  applyEntry,
  onApply,
  onApprove,
  onReject,
  onAcknowledgeWarn,
  applyBusy,
}: {
  proposal: CadRecommendationProposal;
  verdict: CadVerificationVerdict | undefined;
  selectedId: string | null;
  applyEntry: ApplyEntry | undefined;
  onApply(proposal: CadRecommendationProposal): Promise<void>;
  onApprove(runId: string): Promise<void>;
  onReject(runId: string): Promise<void>;
  onAcknowledgeWarn(proposalId: string): void;
  applyBusy: boolean;
}) {
  const change = proposal.parameter_change;
  const targets = (proposal.targets_addressed ?? []).join(", ");
  const verdictKind = verdict?.verdict;
  const failBlocks = verdictKind === "fail";
  const run = applyEntry?.run;
  // Warn-verdict proposals require an explicit checkbox before Apply unlocks.
  const needsAck = verdictKind === "warn" && !run;
  const canApply =
    !!selectedId &&
    !failBlocks &&
    (!needsAck || applyEntry?.acknowledged === true) &&
    !applyBusy &&
    !run;

  return (
    <div className="proposal-card">
      <div className="proposal-card__header">
        <span className="proposal-card__rank">#{proposal.rank ?? "?"}</span>
        <strong>{proposal.feature_ref}</strong>
        <span className="proposal-card__action">{proposal.action_type}</span>
        <span className="proposal-card__confidence">
          confidence: {proposal.confidence ?? "?"}
        </span>
        <span className={verdictBadgeClass(verdictKind)}>
          {verdictKind?.toUpperCase() ?? "NO VERDICT"}
        </span>
      </div>
      {change ? (
        <div className="proposal-card__row">
          <em>change:</em> {change.name} {String(change.from)} {"->"} {String(change.to)}
        </div>
      ) : null}
      {proposal.rationale ? (
        <div className="proposal-card__row">
          <em>rationale:</em> {proposal.rationale}
        </div>
      ) : null}
      {proposal.expected_impact ? (
        <div className="proposal-card__row">
          <em>expected impact:</em> {proposal.expected_impact}
        </div>
      ) : null}
      {targets ? (
        <div className="proposal-card__row">
          <em>targets addressed:</em> {targets}
        </div>
      ) : null}
      {proposal.risks && proposal.risks.length > 0 ? (
        <ul className="proposal-card__risks">
          {proposal.risks.map((risk, idx) => (
            <li key={idx}>risk: {risk}</li>
          ))}
        </ul>
      ) : null}
      {verdict?.checks && verdict.checks.length > 0 ? (
        <details className="proposal-card__verdict-details">
          <summary>Verification checks ({verdict.checks.length})</summary>
          <ul className="proposal-card__checks">
            {verdict.checks.map((check: CadVerificationCheck) => (
              <li key={check.check_id}>
                <code>{checkStatusGlyph(check.status)}</code> {check.check_id}: {check.message}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="proposal-card__apply">
        {failBlocks ? (
          <div className="proposal-card__apply-blocked">
            Verification failed &mdash; the trust-layer blocks execution for this proposal.
          </div>
        ) : null}

        {needsAck && !failBlocks ? (
          <label className="proposal-card__apply-ack">
            <input
              type="checkbox"
              checked={applyEntry?.acknowledged ?? false}
              onChange={() => onAcknowledgeWarn(proposal.proposal_id)}
              disabled={!!run}
            />{" "}
            I acknowledge the warning predictions and want to apply this proposal anyway.
          </label>
        ) : null}

        {!run ? (
          <button
            className="proposal-card__apply-btn"
            disabled={!canApply}
            onClick={() => void onApply(proposal)}
            title={
              failBlocks
                ? "Verdict is fail; cannot apply."
                : needsAck
                  ? "Acknowledge the warning before applying."
                  : "Submit cad.edit_parameter to the runtime (approval-gated)."
            }
          >
            Apply proposal
          </button>
        ) : (
          <div className="proposal-card__run-status">
            <span className={statusBadgeClass(run.status)}>{run.status}</span>
            <code className="proposal-card__run-id">{run.run_id}</code>
            {run.status === "awaiting_approval" ? (
              <>
                <button
                  className="proposal-card__approve-btn"
                  disabled={applyBusy}
                  onClick={() => void onApprove(run.run_id)}
                >
                  Approve &amp; execute
                </button>
                <button
                  className="proposal-card__reject-btn"
                  disabled={applyBusy}
                  onClick={() => void onReject(run.run_id)}
                >
                  Reject
                </button>
              </>
            ) : null}
            {run.errors && run.errors.length > 0 ? (
              <ul className="proposal-card__run-errors">
                {run.errors.map((err, idx) => (
                  <li key={idx}>{err}</li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

export function RecommendationsPanel({ selectedId }: RecommendationsPanelProps) {
  const [strictness, setStrictness] = useState<Strictness>("default");
  const [data, setData] = useState<CadRecommendationsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // run state keyed by proposal_id so each card tracks its own submission
  const [applyState, setApplyState] = useState<Record<string, ApplyEntry>>({});
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  const load = useCallback(
    async (mode: Strictness) => {
      if (!selectedId) {
        setData(null);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const result = await api.getCadRecommendations(selectedId, mode);
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [selectedId],
  );

  useEffect(() => {
    setApplyState({});
    setApplyError(null);
    void load(strictness);
  }, [load, selectedId, strictness]);

  const acknowledgeWarn = useCallback((proposalId: string) => {
    setApplyState((prev) => {
      const existing = prev[proposalId];
      const acknowledged = existing?.acknowledged ?? false;
      return {
        ...prev,
        [proposalId]: {
          run: existing?.run,
          acknowledged: !acknowledged,
        },
      };
    });
  }, []);

  const applyProposal = useCallback(
    async (proposal: CadRecommendationProposal) => {
      if (!selectedId) return;
      const change = proposal.parameter_change;
      if (!change?.name || change.to === undefined || change.to === null) {
        setApplyError("Proposal is missing parameter_change.name or .to; cannot apply.");
        return;
      }
      setApplyBusy(true);
      setApplyError(null);
      try {
        const run = await api.startRun("edit cad parameter", selectedId, {
          project_id: selectedId,
          featureId: proposal.feature_ref,
          parameterName: change.name,
          newValue: change.to,
        });
        setApplyState((prev) => ({
          ...prev,
          [proposal.proposal_id]: { run, acknowledged: true },
        }));
      } catch (err) {
        setApplyError(err instanceof Error ? err.message : String(err));
      } finally {
        setApplyBusy(false);
      }
    },
    [selectedId],
  );

  const approveProposalRun = useCallback(
    async (runId: string) => {
      setApplyBusy(true);
      setApplyError(null);
      try {
        const run = await api.approveRun(runId);
        // Update the matching applyState entry with the new run object.
        setApplyState((prev) => {
          const next: Record<string, ApplyEntry> = { ...prev };
          for (const [proposalId, entry] of Object.entries(prev)) {
            if (entry.run?.run_id === runId) {
              next[proposalId] = { ...entry, run };
            }
          }
          return next;
        });
        // If the run completed successfully, re-fetch recommendations so the
        // updated evidence flows back into the panel.
        if (run.status === "completed") {
          await load(strictness);
        }
      } catch (err) {
        setApplyError(err instanceof Error ? err.message : String(err));
      } finally {
        setApplyBusy(false);
      }
    },
    [load, strictness],
  );

  const rejectProposalRun = useCallback(async (runId: string) => {
    setApplyBusy(true);
    setApplyError(null);
    try {
      const run = await api.rejectRun(runId);
      setApplyState((prev) => {
        const next: Record<string, ApplyEntry> = { ...prev };
        for (const [proposalId, entry] of Object.entries(prev)) {
          if (entry.run?.run_id === runId) {
            next[proposalId] = { ...entry, run };
          }
        }
        return next;
      });
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplyBusy(false);
    }
  }, []);

  if (!selectedId) {
    return (
      <section className="panel">
        <header className="panel__header">
          <h2>CAD Modification Recommendations</h2>
        </header>
        <p className="panel__hint">Select a project to inspect recommendations.</p>
      </section>
    );
  }

  const summary = data?.verification?.summary ?? { pass: 0, warn: 0, fail: 0, total: 0 };
  const verdictsByProposalId: Record<string, CadVerificationVerdict> = {};
  for (const verdict of data?.verification?.verdicts ?? []) {
    if (verdict.proposal_id) {
      verdictsByProposalId[verdict.proposal_id] = verdict;
    }
  }

  const proposals = data?.recommendations?.proposals ?? [];
  const oneLine = data?.recommendations?.llm_summary?.one_line ?? "";

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>CAD Modification Recommendations</h2>
        <div className="panel__actions">
          <label>
            Strictness:{" "}
            <select
              value={strictness}
              onChange={(e) => setStrictness(e.target.value as Strictness)}
              disabled={loading}
            >
              <option value="lenient">lenient</option>
              <option value="default">default</option>
              <option value="strict">strict</option>
            </select>
          </label>
          <button onClick={() => void load(strictness)} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </header>

      <p className="panel__hint">
        Phase 36 ranks CAD-modification candidates from design targets + per-feature stress;
        Phase 37 verifies each proposal through schema, manufacturability, and regression checks.
        Verdicts are predictions, not certifications &mdash; re-simulation is required before
        accepting any change. No claims are advanced.
      </p>

      <p className="panel__hint">
        Apply submits <code>cad.edit_parameter</code> to the runtime; execution is
        approval-gated. After a run completes, the recommendation list refreshes from the
        updated package.
      </p>

      {error ? <div className="panel__error">Error: {error}</div> : null}
      {applyError ? <div className="panel__error">Apply error: {applyError}</div> : null}

      {data ? (
        <>
          <div className="recommendations__summary">
            <span>
              <strong>{summary.total ?? 0}</strong> proposal(s):{" "}
              <span className="badge badge-pass">{summary.pass ?? 0} pass</span>{" "}
              <span className="badge badge-warn">{summary.warn ?? 0} warn</span>{" "}
              <span className="badge badge-fail">{summary.fail ?? 0} fail</span>
            </span>
            {oneLine ? <span className="recommendations__one-line">{oneLine}</span> : null}
          </div>

          {proposals.length === 0 ? (
            <p className="panel__hint">
              No CAD modification proposals under the current evidence. Check that the package
              has design targets, computed metrics, per-feature stress, and parsed features.
            </p>
          ) : (
            <div className="recommendations__list">
              {proposals.map((proposal) => (
                <ProposalCard
                  key={proposal.proposal_id}
                  proposal={proposal}
                  verdict={verdictsByProposalId[proposal.proposal_id]}
                  selectedId={selectedId}
                  applyEntry={applyState[proposal.proposal_id]}
                  onApply={applyProposal}
                  onApprove={approveProposalRun}
                  onReject={rejectProposalRun}
                  onAcknowledgeWarn={acknowledgeWarn}
                  applyBusy={applyBusy}
                />
              ))}
            </div>
          )}

          {data.recommendations?.skipped_features?.length ? (
            <details className="recommendations__skipped">
              <summary>
                Skipped features ({data.recommendations.skipped_features.length})
              </summary>
              <ul>
                {data.recommendations.skipped_features.map((skip, idx) => (
                  <li key={idx}>
                    {skip.feature_ref}: {skip.reason}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : loading ? (
        <p className="panel__hint">Loading recommendations...</p>
      ) : null}
    </section>
  );
}
