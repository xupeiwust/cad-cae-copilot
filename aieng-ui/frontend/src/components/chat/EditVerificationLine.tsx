import { AlertTriangle, CheckCircle2, CircleSlash } from "lucide-react";

import type { TranscriptVerificationLine } from "../../app/chatTranscript";
import { verdictLabel, type EditVerificationTone } from "../../app/editVerification";

type EditVerificationLineProps = {
  item: TranscriptVerificationLine;
};

function ToneIcon({ tone }: { tone: EditVerificationTone }) {
  if (tone === "ok") return <CheckCircle2 className="transcript-status-icon" />;
  if (tone === "warn") return <AlertTriangle className="transcript-status-icon" />;
  return <CircleSlash className="transcript-status-icon" />;
}

function formatDelta(maxChangeMm: number | null): string {
  if (maxChangeMm == null) return "";
  return ` Δ${Number.isInteger(maxChangeMm) ? maxChangeMm : Number(maxChangeMm.toFixed(2))}mm`;
}

/**
 * Renders the post-edit regression-diff verdict (the "see what happened" half of
 * point-and-shoot): whether an edit changed only what was intended (clean), moved
 * unrelated parts (collateral — the trust warning), did nothing (no-op), or
 * changed the part set (topology changed). Data is computed by the backend on
 * every cad.edit_parameter / replace_part / remove_part.
 */
export function EditVerificationLine({ item }: EditVerificationLineProps) {
  const { verdict, tone, headline, changed, collateralParts, added, removed } = item.verification;
  const collateral = new Set(collateralParts);

  return (
    <div className={`transcript-verify-line transcript-verify-${tone}`}>
      <ToneIcon tone={tone} />
      <span className="transcript-verify-label">{verdictLabel(verdict)}</span>
      {headline ? <span className="transcript-verify-headline">{headline}</span> : null}

      {changed.length ? (
        <span className="transcript-verify-parts">
          {changed.map((part) => (
            <span
              key={part.part}
              className={`verify-part${collateral.has(part.part) ? " verify-part-collateral" : ""}`}
              title={collateral.has(part.part) ? "Unintended (collateral) change" : "Changed as intended"}
            >
              {part.part}
              {formatDelta(part.maxChangeMm)}
            </span>
          ))}
        </span>
      ) : null}

      {added.length || removed.length ? (
        <span className="transcript-verify-parts">
          {added.map((p) => (
            <span key={`add-${p}`} className="verify-part verify-part-added" title="Part added">+{p}</span>
          ))}
          {removed.map((p) => (
            <span key={`rm-${p}`} className="verify-part verify-part-removed" title="Part removed">−{p}</span>
          ))}
        </span>
      ) : null}
    </div>
  );
}
