/**
 * Pure projection of the backend's natural-language intent resolution.
 *
 * When a run carries no explicit slash command, the backend resolves the message
 * into a routed command and records it on `composer_intent.resolved_intent`
 * (see AGENTS.md "Natural-language intent resolution"). For a dimensional
 * `/modify` it also binds parameter slots to concrete editable feature parameters
 * and records them on a context observation's `parameter_bindings`.
 *
 * This module reads that backend-authored data into a small, render-ready shape so
 * the composer can show a "understood as /build" chip instead of the raw,
 * agent-facing instruction text. Pure and total — never throws.
 */

import type { AutopilotObservation, AutopilotRunState } from "../types";

export type ResolvedParamBinding = {
  slotName: string;
  value: number | null;
  unit: string | null;
  /** true = bound to a parameter, false = not found / ambiguous, null = unverified. */
  known: boolean | null;
  parameterName: string | null;
  cadParameterName: string | null;
  featureId: string | null;
  /** false when the requested value is outside the parameter's declared range. */
  withinBounds: boolean | null;
  reason: string | null;
};

export type ResolvedIntentSummary = {
  /** The routed command the backend inferred (build/modify/critique/explain/simulate). */
  command: string;
  intentType: string | null;
  /** How it was resolved: "llm_classifier" or "keyword_heuristic". */
  source: string;
  confidence: number;
  /** True when the intent was actionable but too weak/ambiguous to route on. */
  needsClarification: boolean;
  /** Resolved dimensional-edit bindings (modify only); empty otherwise. */
  bindings: ResolvedParamBinding[];
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asBoolOrNull(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

/** True when this context observation is one the intent chip already represents. */
export function isIntentResolutionObservation(obs: AutopilotObservation): boolean {
  if (!obs || obs.kind !== "context") return false;
  const data = obs.data ?? {};
  return (
    "intent_resolution" in data ||
    "parameter_slots" in data ||
    "parameter_bindings" in data
  );
}

function extractBindings(observations: AutopilotObservation[]): ResolvedParamBinding[] {
  for (const obs of observations ?? []) {
    const raw = obs?.data?.parameter_bindings;
    if (!Array.isArray(raw)) continue;
    const bindings: ResolvedParamBinding[] = [];
    for (const entry of raw) {
      const b = asRecord(entry);
      if (!b) continue;
      bindings.push({
        slotName: asString(b.slot_name) ?? "",
        value: asNumber(b.value),
        unit: asString(b.unit),
        known: asBoolOrNull(b.known),
        parameterName: asString(b.parameter_name),
        cadParameterName: asString(b.cad_parameter_name),
        featureId: asString(b.feature_id),
        withinBounds: asBoolOrNull(b.value_within_bounds),
        reason: asString(b.reason),
      });
    }
    return bindings;
  }
  return [];
}

/**
 * Read a run's resolved-intent summary, or null when none applies (an explicit
 * slash command, or a plain message with no actionable intent — neither records
 * `resolved_intent`).
 */
export function resolvedIntentFromRun(run: AutopilotRunState): ResolvedIntentSummary | null {
  const composerIntent = asRecord(run?.composer_intent);
  if (!composerIntent) return null;
  const resolved = asRecord(composerIntent.resolved_intent);
  if (!resolved) return null;

  const command = asString(resolved.command);
  const needsClarification = resolved.needs_clarification === true;
  // The chip only has something to say when a command was inferred.
  if (!command) return null;

  return {
    command,
    intentType: asString(resolved.intent_type),
    source: asString(resolved.source) ?? "keyword_heuristic",
    confidence: asNumber(resolved.confidence) ?? 0,
    needsClarification,
    bindings: extractBindings(run.observations ?? []),
  };
}
