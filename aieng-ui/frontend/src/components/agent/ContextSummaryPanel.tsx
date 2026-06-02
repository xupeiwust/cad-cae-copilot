import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";

import { api, type ContextSummary } from "../../api";
import { PointerText } from "../PointerText";

type ContextSummaryPanelProps = {
  projectId: string | null;
  sessionId: string | null;
};

export function ContextSummaryPanel({ projectId, sessionId }: ContextSummaryPanelProps) {
  const [summary, setSummary] = useState<ContextSummary | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSummary(null);
    setError(null);
    if (!projectId || !sessionId) return;

    setBusy(true);
    api.getChatSessionContextSummary(projectId, sessionId)
      .then((response) => {
        if (!cancelled) setSummary(response.context_summary ?? null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, sessionId]);

  if (!projectId || !sessionId) return null;

  async function refreshSummary() {
    if (!projectId || !sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api.refreshChatSessionContextSummary(projectId, sessionId);
      setSummary(response.context_summary ?? null);
      setExpanded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const headerState = busy ? "Updating" : summary ? formatTime(summary.updated_at) : "No summary";
  const riskCount = summary?.risks.length ?? 0;
  const pendingCount = summary?.pending_steps.length ?? 0;

  return (
    <section className="context-summary-panel" aria-label="Context summary">
      <div className="context-summary-header">
        <button
          type="button"
          className="context-summary-toggle"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronDown className="context-summary-icon" /> : <ChevronRight className="context-summary-icon" />}
          <span>Context</span>
        </button>
        <span className="context-summary-meta">{headerState}</span>
        {riskCount || pendingCount ? (
          <span className="context-summary-counts">
            {pendingCount ? `${pendingCount} pending` : null}
            {pendingCount && riskCount ? " / " : null}
            {riskCount ? `${riskCount} risk${riskCount === 1 ? "" : "s"}` : null}
          </span>
        ) : null}
        <button
          type="button"
          className="ghost-button icon-only-button context-summary-refresh"
          onClick={() => void refreshSummary()}
          disabled={busy}
          title="Refresh context"
        >
          <RefreshCw className={busy ? "context-summary-icon spin" : "context-summary-icon"} />
        </button>
      </div>

      {summary ? (
        <>
          <div className="context-summary-compact">
            <span className="context-summary-label">Goal</span>
            <strong><PointerText text={summary.goal || "Untitled session"} /></strong>
            <span className="context-summary-label">Next</span>
            <span><PointerText text={summary.next_action || summary.current_state} /></span>
          </div>
          {expanded ? (
            <div className="context-summary-details">
              <SummaryBlock label="State" values={[summary.current_state]} />
              <SummaryBlock label="Pending" values={summary.pending_steps} empty="None" />
              <SummaryBlock label="Risks" values={summary.risks} empty="None" tone="risk" />
              <SummaryBlock label="Decisions" values={summary.important_decisions} empty="None" />
              <SummaryBlock label="Files" values={summary.relevant_files} empty="None" code />
            </div>
          ) : null}
        </>
      ) : (
        <div className="context-summary-empty">
          {error ? (
            <>
              <AlertTriangle className="context-summary-icon" />
              <span>{error}</span>
            </>
          ) : (
            <span>{busy ? "Loading summary" : "No summary yet"}</span>
          )}
        </div>
      )}
    </section>
  );
}

function SummaryBlock({
  label,
  values,
  empty,
  tone,
  code,
}: {
  label: string;
  values: string[];
  empty?: string;
  tone?: "risk";
  code?: boolean;
}) {
  const visible = values.filter(Boolean).slice(0, 5);
  const remaining = values.filter(Boolean).length - visible.length;
  return (
    <div className={`context-summary-block${tone ? ` context-summary-block-${tone}` : ""}`}>
      <span className="context-summary-label">{label}</span>
      {visible.length ? (
        <ul>
          {visible.map((value, index) => (
            <li key={`${label}-${index}`}>
              {code ? <code>{value}</code> : <PointerText text={value} />}
            </li>
          ))}
          {remaining > 0 ? <li className="context-summary-more">+{remaining} more</li> : null}
        </ul>
      ) : (
        <span className="context-summary-muted">{empty ?? "Empty"}</span>
      )}
    </div>
  );
}

function formatTime(value: string | undefined): string {
  if (!value) return "Saved";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "Saved";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}
