// Pure, VS Code-free helpers for surfacing advisory operation receipts and
// `next_actions` (issue #341). Display + copy only: nothing here executes a tool,
// runs a solver, or changes approval behavior. All safety flags and blocked
// status are preserved in the text these helpers produce.

export type NextAction = {
  id: string;
  label: string;
  tool: string;
  input: Record<string, unknown>;
  priority?: string | number;
  reason?: string;
  availableNow: boolean;
  blockedReason?: string;
  blockedReasonCodes: string[];
  resolvesBlockedReasonCodes: string[];
  requiresApproval: boolean;
  mutatesPackage: boolean;
  runsSolver: boolean;
  advancesClaim: boolean;
};

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function normalizeAction(raw: Record<string, unknown>): NextAction | undefined {
  const tool = typeof raw.tool === "string" ? raw.tool : "";
  const reason = typeof raw.reason === "string" && raw.reason.trim() ? raw.reason : undefined;
  const blockedReason = typeof raw.blocked_reason === "string" && raw.blocked_reason.trim()
    ? raw.blocked_reason
    : undefined;
  const label = typeof raw.label === "string" && raw.label.trim()
    ? raw.label
    : (tool || reason || blockedReason);
  if (!label) return undefined;
  // Honest default: available unless explicitly false or carrying a blocked reason.
  const availableNow = raw.available_now === false || !tool ? false : !blockedReason && raw.available_now !== false;
  return {
    id: typeof raw.id === "string" ? raw.id : (tool || label),
    label,
    tool,
    input: asRecord(raw.input) ?? {},
    priority: typeof raw.priority === "string" || typeof raw.priority === "number" ? raw.priority : undefined,
    reason,
    availableNow,
    blockedReason: blockedReason ?? (!tool ? reason : undefined),
    blockedReasonCodes: asStringArray(raw.blocked_reason_codes),
    resolvesBlockedReasonCodes: asStringArray(raw.resolves_blocked_reason_codes),
    requiresApproval: raw.requires_approval === true,
    mutatesPackage: raw.mutates_package === true,
    runsSolver: raw.runs_solver === true,
    advancesClaim: raw.advances_claim === true,
  };
}

/**
 * Extract advisory next actions from a tool response. Looks at the top-level
 * `next_actions` first (e.g. `cae.prepare_solver_run`), then falls back to
 * `receipt.next_actions`. Tolerant of missing/malformed payloads — never throws.
 */
export function parseNextActions(response: unknown): NextAction[] {
  const record = asRecord(response);
  if (!record) return [];
  let raw = record.next_actions;
  if (!Array.isArray(raw)) {
    raw = asRecord(record.receipt)?.next_actions;
  }
  if (!Array.isArray(raw)) return [];
  const actions: NextAction[] = [];
  for (const item of raw) {
    const rec = asRecord(item);
    if (!rec) continue;
    const normalized = normalizeAction(rec);
    if (normalized) actions.push(normalized);
  }
  return actions;
}

function safetyFlagWords(action: NextAction): string[] {
  const flags: string[] = [];
  if (action.requiresApproval) flags.push("requires approval");
  if (action.runsSolver) flags.push("runs solver");
  if (action.mutatesPackage) flags.push("mutates package");
  if (action.advancesClaim) flags.push("advances claim");
  return flags;
}

/**
 * One-line status + safety summary for a quick-pick detail row. Always names
 * blocked status, the blocking reason/codes, and every active safety flag.
 */
export function formatActionDetail(action: NextAction): string {
  const parts: string[] = [];
  if (action.availableNow) {
    parts.push("Available");
  } else {
    const reason = action.blockedReason ?? "blocked";
    let blocked = `Blocked: ${reason}`;
    if (action.blockedReasonCodes.length) blocked += ` [${action.blockedReasonCodes.join(", ")}]`;
    parts.push(blocked);
  }
  if (action.resolvesBlockedReasonCodes.length) {
    parts.push(`resolves ${action.resolvesBlockedReasonCodes.join(", ")}`);
  }
  const flags = safetyFlagWords(action);
  if (flags.length) parts.push(flags.join(" · "));
  if (action.tool) parts.push(action.tool);
  else parts.push("advisory only");
  return parts.join("  ·  ");
}

/** A copy-paste invoke-tool JSON body for the action. Never executed here. */
export function toToolCallSnippet(action: NextAction): string {
  if (!action.tool) {
    return JSON.stringify({
      advisory: action.label,
      blocked_reason: action.blockedReason ?? action.reason ?? "Action cannot be executed automatically.",
      blocked_reason_codes: action.blockedReasonCodes,
      resolves_blocked_reason_codes: action.resolvesBlockedReasonCodes,
    }, null, 2);
  }
  return JSON.stringify({
    tool: action.tool,
    input: action.input,
    resolves_blocked_reason_codes: action.resolvesBlockedReasonCodes,
  }, null, 2);
}

/** A natural-language handoff prompt that preserves safety + blocked status. */
export function toHandoffPrompt(action: NextAction): string {
  const lines: string[] = [];
  lines.push(`Suggested next action: ${action.label}`);
  lines.push(action.tool ? `Tool: ${action.tool}` : "Tool: none; advisory only.");
  if (Object.keys(action.input).length) {
    lines.push(`Input: ${JSON.stringify(action.input)}`);
  }
  if (action.availableNow) {
    lines.push("Status: available.");
  } else {
    const reason = action.blockedReason ?? "blocked";
    const codes = action.blockedReasonCodes.length ? ` (codes: ${action.blockedReasonCodes.join(", ")})` : "";
    lines.push(`Status: BLOCKED — ${reason}${codes}. Resolve this before attempting the action.`);
  }
  if (action.resolvesBlockedReasonCodes.length) {
    lines.push(`Resolves blockers: ${action.resolvesBlockedReasonCodes.join(", ")}.`);
  }
  const flags = safetyFlagWords(action);
  if (flags.length) lines.push(`Safety: ${flags.join("; ")}.`);
  lines.push("This is an advisory suggestion copied from AIENG — review it and run the tool yourself if appropriate.");
  return lines.join("\n");
}
