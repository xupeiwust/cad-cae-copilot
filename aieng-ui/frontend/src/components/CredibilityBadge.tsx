import { formatCredibilityTier } from "../app/credibilityBadge";
import type { CredibilityStamp } from "../types";

type CredibilityBadgeProps = {
  credibility: CredibilityStamp | null | undefined;
};

/**
 * Small read-only badge rendering the shared V&V-40 credibility tier (#218).
 * Renders nothing when no stamp is present, so it is safe to drop into any
 * result surface. The tone communicates risk-commensurate trust at a glance;
 * the tooltip carries the evidence basis + any downgrade reason.
 */
export function CredibilityBadge({ credibility }: CredibilityBadgeProps) {
  const model = formatCredibilityTier(credibility);
  if (!model) return null;
  return (
    <span
      className={`credibility-badge credibility-${model.tone}`}
      title={model.title}
      data-tier={credibility?.tier}
    >
      {model.label}
    </span>
  );
}
