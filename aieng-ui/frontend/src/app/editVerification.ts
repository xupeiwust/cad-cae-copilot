/**
 * Pure projection of the backend's post-edit regression diff.
 *
 * Every cad.edit_parameter / cad.replace_part / cad.remove_part result carries a
 * `regression_diff` that compares before/after topology by named part — the
 * "did the edit do what I meant, and nothing else?" verification signal. The
 * backend already computes it; this turns it into a render-ready verdict so the
 * transcript can show it (the "see what happened" half of point-and-shoot)
 * instead of leaving it buried in the tool-result detail. Pure and total.
 */

import type { AutopilotObservation } from "../types";

export type EditVerdict = "clean" | "collateral_change" | "identical" | "topology_changed";

/** Display tone for a verdict: ok (intended), warn (surprise), neutral (no-op). */
export type EditVerificationTone = "ok" | "warn" | "neutral";

export type EditChangedPart = {
  part: string;
  /** Largest absolute bbox/center change in mm, or null when unknown. */
  maxChangeMm: number | null;
  /** false = this part was NOT a target (collateral); true = intended; null = unknown. */
  expected: boolean | null;
};

export type EditVerification = {
  verdict: EditVerdict;
  tone: EditVerificationTone;
  headline: string;
  changed: EditChangedPart[];
  collateralParts: string[];
  added: string[];
  removed: string[];
  unchangedCount: number;
  /** The mutating tool this diff came from (edit_parameter / replace_part / remove_part). */
  toolName: string;
};

const VERDICT_TONE: Record<EditVerdict, EditVerificationTone> = {
  clean: "ok",
  collateral_change: "warn",
  topology_changed: "warn",
  identical: "neutral",
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function normalizeVerdict(value: unknown): EditVerdict | null {
  return value === "clean" || value === "collateral_change" || value === "identical" || value === "topology_changed"
    ? value
    : null;
}

/**
 * Build an EditVerification from a mutating tool's result output, or null when the
 * output carries no regression diff (non-edit tools, or an errored edit).
 */
export function editVerificationFromOutput(output: unknown, toolName: string): EditVerification | null {
  const out = asRecord(output);
  if (!out) return null;
  const diff = asRecord(out.regression_diff);
  if (!diff) return null;
  const verdict = normalizeVerdict(diff.verdict);
  if (!verdict) return null;

  const changed: EditChangedPart[] = [];
  if (Array.isArray(diff.changed)) {
    for (const entry of diff.changed) {
      const rec = asRecord(entry);
      if (!rec) continue;
      changed.push({
        part: asString(rec.part),
        maxChangeMm: asNumber(rec.max_change_mm),
        expected: typeof rec.expected === "boolean" ? rec.expected : null,
      });
    }
  }

  return {
    verdict,
    tone: VERDICT_TONE[verdict],
    headline: asString(diff.headline),
    changed,
    collateralParts: stringList(diff.collateral_parts),
    added: stringList(diff.added),
    removed: stringList(diff.removed),
    unchangedCount: asNumber(diff.unchanged_count) ?? 0,
    toolName,
  };
}

/** Convenience: read the verification from a tool_result observation, or null. */
export function editVerificationFromObservation(obs: AutopilotObservation): EditVerification | null {
  if (!obs || obs.kind !== "tool_result") return null;
  const output = obs.data?.output;
  const toolName = typeof obs.data?.tool_name === "string" ? obs.data.tool_name : "";
  return editVerificationFromOutput(output, toolName);
}

/** Short verdict label for the chip header. */
export function verdictLabel(verdict: EditVerdict): string {
  switch (verdict) {
    case "clean":
      return "Clean edit";
    case "collateral_change":
      return "Collateral change";
    case "identical":
      return "No change";
    case "topology_changed":
      return "Topology changed";
  }
}
