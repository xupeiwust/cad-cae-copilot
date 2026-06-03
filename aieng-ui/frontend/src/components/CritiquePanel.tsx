import { useMemo } from "react";

import {
  fixDraftForFinding,
  groupFindingsBySeverity,
  SEVERITY_LABEL,
  type Severity,
} from "../app/critiqueFindings";
import type { CritiqueFinding } from "../types";

type CritiquePanelProps = {
  findings: CritiqueFinding[];
  /** Prefill the composer with a "/modify <suggested_fix>" draft. */
  onUseInChat?: (draft: string) => void;
};

/**
 * Read-only manufacturability/engineering critique (the audit behind cad.critique)
 * surfaced as an actionable panel: findings grouped by severity, each with a one-
 * click "Fix" that drafts a /modify from the finding's suggested_fix into the
 * composer. The edit itself still runs through the approval-gated path — the panel
 * never mutates geometry.
 */
export function CritiquePanel({ findings, onUseInChat }: CritiquePanelProps) {
  const groups = useMemo(() => groupFindingsBySeverity(findings), [findings]);

  if (!findings.length) return null;

  return (
    <section className="critique-card" aria-label="Engineering critique">
      <div className="critique-head">
        <strong>Engineering critique</strong>
        <span>{findings.length} finding{findings.length !== 1 ? "s" : ""}</span>
      </div>

      {groups.map((group) => (
        <div key={group.severity} className="critique-group">
          <div className={`critique-sev critique-sev-${group.severity as Severity}`}>
            {SEVERITY_LABEL[group.severity]}
            <span className="critique-sev-count">{group.findings.length}</span>
          </div>

          {group.findings.map((finding: CritiqueFinding, index) => {
            const draft = fixDraftForFinding(finding);
            return (
              <div key={`${finding.rule ?? "rule"}-${finding.feature ?? index}`} className="critique-row">
                <div className="critique-row-main">
                  <span className="critique-rule">{finding.rule ?? finding.category ?? "finding"}</span>
                  {finding.feature ? <code className="critique-feature">{finding.feature}</code> : null}
                  <span className="critique-observation">{finding.observation}</span>
                </div>
                {draft ? (
                  <button
                    type="button"
                    className="critique-fix"
                    onClick={() => onUseInChat?.(draft)}
                    disabled={!onUseInChat}
                    title={finding.suggested_fix}
                  >
                    Fix
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      ))}

      <div className="critique-foot">
        Click <strong>Fix</strong> to draft a <code>/modify</code> — edits run through approval.
      </div>
    </section>
  );
}
