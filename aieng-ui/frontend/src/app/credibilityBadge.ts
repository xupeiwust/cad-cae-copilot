/**
 * Pure shaping for the credibility badge (#218). No React, no I/O.
 *
 * Turns the backend's shared V&V-40 credibility stamp into a small display
 * model — one legible tier + tone + tooltip — so every result-bearing surface
 * (critique, surrogate, proxy-assembly, solver) renders trust the same way
 * instead of each panel re-deriving it from scattered honesty flags.
 */

import type { CredibilityStamp } from "../types";

export type CredibilityTone = "neutral" | "info" | "caution" | "strong";

export type CredibilityBadgeModel = {
  label: string;
  tone: CredibilityTone;
  rank: number;
  title: string;
};

const TIER_LABEL: Record<string, string> = {
  critique_finding: "Critique finding",
  surrogate_prediction: "Surrogate prediction",
  proxy_assembly_result: "Proxy-assembly result",
  executed_solver_result: "Executed-solver result",
  unverified: "Unverified",
};

// Higher rank = more credible. Tone escalates with rank but caps below
// "certified" — even an executed solver result is not production-certified.
const TONE_BY_RANK: Record<number, CredibilityTone> = {
  0: "caution",
  1: "neutral",
  2: "info",
  3: "info",
  4: "strong",
};

/**
 * Build the badge display model from a credibility stamp, or null when none is
 * present (so callers render nothing rather than a misleading default). Pure
 * and total — tolerates a partial/garbage stamp.
 */
export function formatCredibilityTier(
  credibility: CredibilityStamp | null | undefined,
): CredibilityBadgeModel | null {
  if (!credibility || typeof credibility.tier !== "string") return null;

  const tier = credibility.tier;
  const rank = Number.isFinite(credibility.rank) ? Number(credibility.rank) : 0;
  const label = credibility.label || TIER_LABEL[tier] || tier;
  const tone = TONE_BY_RANK[rank] ?? "neutral";

  const titleParts: string[] = [];
  if (credibility.evidence_basis) titleParts.push(credibility.evidence_basis);
  if (credibility.downgrade_reason) titleParts.push(`Downgraded: ${credibility.downgrade_reason}`);
  if (credibility.production_ready === false) titleParts.push("Not production-certified.");
  const title = titleParts.join(" — ") || label;

  return { label, tone, rank, title };
}
