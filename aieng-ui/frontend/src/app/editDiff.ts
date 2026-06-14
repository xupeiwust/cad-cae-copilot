/**
 * Pure shaping for the Edit Diff panel (#226). No React, no I/O.
 *
 * Re-surfaces the trust signal removed in the MCP-first chat cutover: after a
 * CAD edit, "what changed and is it safe?" The backend persists the last edit's
 * `regression_diff` (topology drift) + `critique_diff` (manufacturability); this
 * turns that payload into a display model where each changed part is tagged
 * `collateral` (changed but NOT the edit's target) so the UI can render it
 * visually distinct, per Zoo's "an edit reads like a diff" framing.
 */

import type { CritiqueDiff, EditDiffResponse, RegressionDiff } from "../types";

export type DiffTone = "good" | "neutral" | "caution" | "bad";

export type ChangedPartRow = {
  name: string;
  /** changed but not the edit's intended target → render visually distinct. */
  collateral: boolean;
  maxChangeMm: number | null;
};

export type RegressionView = {
  verdict: string;
  tone: DiffTone;
  headline: string;
  changed: ChangedPartRow[];
  added: string[];
  removed: string[];
  collateralCount: number;
};

export type CritiqueView = {
  verdict: string;
  tone: DiffTone;
  headline: string;
  introducedCount: number;
  resolvedCount: number;
};

export type EditDiffView = {
  hasData: boolean;
  tool: string | null;
  regression: RegressionView | null;
  critique: CritiqueView | null;
  /** true when either diff is a regression worth the user's attention. */
  needsAttention: boolean;
};

const REGRESSION_TONE: Record<string, DiffTone> = {
  clean: "good",
  identical: "neutral",
  topology_changed: "caution",
  collateral_change: "bad",
};

const CRITIQUE_TONE: Record<string, DiffTone> = {
  clean: "good",
  improved: "good",
  skipped: "neutral",
  warn: "caution",
  fail: "bad",
};

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function shapeRegression(diff: RegressionDiff | null | undefined): RegressionView | null {
  if (!diff || typeof diff.verdict !== "string") return null;
  const collateralSet = new Set((diff.collateral_parts ?? []).map(String));
  const changed: ChangedPartRow[] = (diff.changed ?? []).map((c) => {
    // Collateral = explicitly listed, or flagged expected:false by the backend.
    const collateral = collateralSet.has(c.part) || c.expected === false;
    return { name: String(c.part), collateral, maxChangeMm: num(c.max_change_mm) };
  });
  return {
    verdict: diff.verdict,
    tone: REGRESSION_TONE[diff.verdict] ?? "neutral",
    headline: diff.headline ?? diff.verdict,
    changed,
    added: (diff.added ?? []).map(String),
    removed: (diff.removed ?? []).map(String),
    collateralCount: changed.filter((c) => c.collateral).length,
  };
}

function shapeCritique(diff: CritiqueDiff | null | undefined): CritiqueView | null {
  if (!diff || typeof diff.verdict !== "string") return null;
  return {
    verdict: diff.verdict,
    tone: CRITIQUE_TONE[diff.verdict] ?? "neutral",
    headline: diff.headline ?? diff.verdict,
    introducedCount: num(diff.introduced_count) ?? (diff.introduced?.length ?? 0),
    resolvedCount: num(diff.resolved_count) ?? 0,
  };
}

/** Shape the edit-diff payload into the panel's display model. Pure and total. */
export function shapeEditDiff(resp: EditDiffResponse | null | undefined): EditDiffView {
  const empty: EditDiffView = {
    hasData: false,
    tool: null,
    regression: null,
    critique: null,
    needsAttention: false,
  };
  if (!resp || resp.available !== true) return empty;

  const regression = shapeRegression(resp.regression_diff);
  const critique = shapeCritique(resp.critique_diff);
  if (!regression && !critique) return empty;

  const needsAttention =
    regression?.tone === "bad" ||
    regression?.tone === "caution" ||
    critique?.tone === "bad" ||
    critique?.tone === "caution";

  return {
    hasData: true,
    tool: typeof resp.tool === "string" ? resp.tool : null,
    regression,
    critique,
    needsAttention,
  };
}
