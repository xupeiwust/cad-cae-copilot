/**
 * Pure shaping helpers for the Editable Parameters panel. No React, no I/O.
 *
 * Turns the backend `cad.list_editable_parameters` / `/editable-parameters`
 * listing into the display model the panel renders: parameters grouped by editing
 * scope (local / global / unscoped) with a stable, user-meaningful order, and
 * small formatting helpers for values and ranges.
 */

import type { EditableParameter } from "../types";

export type ParameterScope = "local" | "global" | "unscoped";

const SCOPE_ORDER: ParameterScope[] = ["local", "global", "unscoped"];

export const SCOPE_LABEL: Record<ParameterScope, string> = {
  local: "Local",
  global: "Global (shared)",
  unscoped: "Unscoped",
};

/** One-line human hint about the editing risk of a scope. */
export const SCOPE_HINT: Record<ParameterScope, string> = {
  local: "Belongs to one part — a safe, local edit.",
  global: "Shared constant — editing ripples across parts.",
  unscoped: "Not matched to a specific part.",
};

export type ParameterGroup = {
  scope: ParameterScope;
  /** Parameters in this group, ordered by feature then parameter name. */
  parameters: EditableParameter[];
};

function normalizeScope(scope: string): ParameterScope {
  return scope === "global" || scope === "unscoped" ? scope : "local";
}

/**
 * Group a flat parameter listing by scope, in display order (local → global →
 * unscoped), each group sorted by feature name then parameter name. Empty groups
 * are omitted. Pure and total.
 */
export function groupParametersByScope(parameters: EditableParameter[]): ParameterGroup[] {
  const buckets = new Map<ParameterScope, EditableParameter[]>();
  for (const param of parameters ?? []) {
    const scope = normalizeScope(param.scope);
    const list = buckets.get(scope) ?? [];
    list.push(param);
    buckets.set(scope, list);
  }
  const groups: ParameterGroup[] = [];
  for (const scope of SCOPE_ORDER) {
    const list = buckets.get(scope);
    if (!list || list.length === 0) continue;
    list.sort(
      (a, b) =>
        (a.feature_name || "").localeCompare(b.feature_name || "") ||
        (a.parameter_name || "").localeCompare(b.parameter_name || ""),
    );
    groups.push({ scope, parameters: list });
  }
  return groups;
}

/** Format a numeric value compactly (drops a trailing `.0`). Empty for null. */
export function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "";
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
}

/** "0.15 – 15" when both bounds are present, else "" . */
export function formatRange(min: number | null | undefined, max: number | null | undefined): string {
  const lo = formatNumber(min);
  const hi = formatNumber(max);
  if (!lo && !hi) return "";
  return `${lo || "?"} – ${hi || "?"}`;
}

/**
 * A composer-ready edit draft for a parameter, e.g.
 * `/modify set wall thickness to ` — the panel uses this to hand the user a
 * pre-filled command that flows through the existing approval-gated edit path.
 * Uses the human parameter name (not the constant), which the backend slot
 * binding resolves back to the constant.
 */
export function editDraftForParameter(param: EditableParameter): string {
  const name = (param.parameter_name || param.cad_parameter_name || "parameter").replace(/_/g, " ");
  return `/modify set ${name} to `;
}
