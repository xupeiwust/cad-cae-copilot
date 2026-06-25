import type { RuntimeEvent, RuntimeRun, RuntimeToolError, RuntimeToolResult } from "../types";

export type ProjectTimelineEntryKind =
  | "run"
  | "approval"
  | "tool"
  | "snapshot"
  | "artifact"
  | "next_action"
  | "failure";

export type BlockedReasonCodeDetail = {
  code: string;
  label: string;
  description: string;
  recommendedAction: string;
};

export type TimelineDiagnostic = {
  code: string;
  message: string;
  remediation: string | null;
  toolName: string | null;
};

export type TimelineSnapshot = {
  id: string;
  createdAt: string | null;
  toolName: string | null;
  partCount: number | null;
  namedParts: string[];
  restored: boolean;
};

export type TimelineNextAction = {
  label: string;
  tool: string | null;
  availableNow: boolean | null;
  blockedReason: string | null;
  blockedReasonCodes: string[];
  blockedReasonCodeDetails: BlockedReasonCodeDetail[];
  resolvesBlockedReasonCodes: string[];
  resolvesBlockedReasonCodeDetails: BlockedReasonCodeDetail[];
  safetyFlags: string[];
};

export type ProjectTimelineEntry = {
  id: string;
  timestamp: string;
  kind: ProjectTimelineEntryKind;
  status: string;
  title: string;
  detail?: string | null;
  diagnostic?: TimelineDiagnostic | null;
  snapshots: TimelineSnapshot[];
  artifacts: string[];
  nextActions: TimelineNextAction[];
  sourceRunId: string;
};

export type ProjectTimeline = {
  entries: ProjectTimelineEntry[];
  runCount: number;
  warningCount: number;
  diagnosticCount: number;
  snapshotCount: number;
  unstructuredFailureCount: number;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asCodeDetails(value: unknown): BlockedReasonCodeDetail[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const record = asRecord(item);
    const code = record ? asString(record.code) : null;
    if (!record || !code) return [];
    return [{
      code,
      label: asString(record.label) ?? code,
      description: asString(record.description) ?? "",
      recommendedAction: asString(record.recommended_action) ?? asString(record.recommendedAction) ?? "",
    }];
  });
}

function collectArtifacts(value: unknown): string[] {
  const out: string[] = [];
  const pushPath = (item: unknown) => {
    if (typeof item === "string" && item.trim()) {
      out.push(item);
      return;
    }
    const record = asRecord(item);
    const path = record ? asString(record.path) ?? asString(record.artifact_path) : null;
    if (path) out.push(path);
  };

  const record = asRecord(value);
  if (!record) return out;
  for (const key of ["artifacts", "changed_artifacts", "artifacts_written", "evidence_created", "written_artifacts"]) {
    const raw = record[key];
    if (Array.isArray(raw)) raw.forEach(pushPath);
  }
  return Array.from(new Set(out));
}

function snapshotFromRecord(item: unknown, restored: boolean): TimelineSnapshot | null {
  const record = asRecord(item);
  const id = record ? asString(record.snapshot_id) ?? asString(record.id) : null;
  if (!record || !id) return null;
  return {
    id,
    createdAt: asString(record.created_at) ?? asString(record.createdAt),
    toolName: asString(record.tool_name) ?? asString(record.toolName),
    partCount: asNumber(record.part_count) ?? asNumber(record.partCount),
    namedParts: asStringArray(record.named_parts).slice(0, 8),
    restored,
  };
}

function collectSnapshots(value: unknown): TimelineSnapshot[] {
  const record = asRecord(value);
  if (!record) return [];
  const out: TimelineSnapshot[] = [];
  const seen = new Set<string>();
  const push = (snapshot: TimelineSnapshot | null) => {
    if (!snapshot) return;
    const key = `${snapshot.restored ? "restored" : "available"}:${snapshot.id}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(snapshot);
  };

  const snapshots = record.snapshots;
  if (Array.isArray(snapshots)) {
    snapshots.forEach((item) => push(snapshotFromRecord(item, false)));
  }

  const restoredFrom = asString(record.restored_from) ?? asString(record.restoredFrom);
  if (restoredFrom) {
    push({
      id: restoredFrom,
      createdAt: null,
      toolName: asString(record.tool_name) ?? asString(record.toolName),
      partCount: asNumber(record.part_count) ?? asNumber(record.partCount),
      namedParts: asStringArray(record.named_parts).slice(0, 8),
      restored: true,
    });
  }

  return out;
}

function describeNextAction(item: unknown): TimelineNextAction | null {
  if (typeof item === "string" && item.trim()) {
    return {
      label: item,
      tool: null,
      availableNow: null,
      blockedReason: null,
      blockedReasonCodes: [],
      blockedReasonCodeDetails: [],
      resolvesBlockedReasonCodes: [],
      resolvesBlockedReasonCodeDetails: [],
      safetyFlags: [],
    };
  }
  const record = asRecord(item);
  if (!record) return null;
  const tool = asString(record.tool) ?? asString(record.name) ?? asString(record.reference);
  const label = asString(record.label)
    ?? asString(record.summary)
    ?? asString(record.description)
    ?? asString(record.reason)
    ?? asString(record.action)
    ?? tool;
  if (!label) return null;
  const blockedReason = asString(record.blocked_reason);
  const rawAvailable = record.available_now;
  const availableNow = typeof rawAvailable === "boolean" ? rawAvailable : (blockedReason ? false : null);
  const safetyFlags: string[] = [];
  if (record.requires_approval === true) safetyFlags.push("requires approval");
  if (record.runs_solver === true) safetyFlags.push("runs solver");
  if (record.mutates_package === true) safetyFlags.push("mutates package");
  if (record.advances_claim === true) safetyFlags.push("advances claim");
  return {
    label,
    tool,
    availableNow: tool ? availableNow : false,
    blockedReason: blockedReason ?? (!tool ? asString(record.reason) : null),
    blockedReasonCodes: asStringArray(record.blocked_reason_codes),
    blockedReasonCodeDetails: asCodeDetails(record.blocked_reason_code_details),
    resolvesBlockedReasonCodes: asStringArray(record.resolves_blocked_reason_codes),
    resolvesBlockedReasonCodeDetails: asCodeDetails(record.resolves_blocked_reason_code_details),
    safetyFlags,
  };
}

function nextActionKey(action: TimelineNextAction): string {
  return JSON.stringify([
    action.tool,
    action.label,
    action.availableNow,
    action.blockedReason,
    action.blockedReasonCodes,
    action.blockedReasonCodeDetails,
    action.resolvesBlockedReasonCodes,
    action.resolvesBlockedReasonCodeDetails,
    action.safetyFlags,
  ]);
}

function collectNextActions(value: unknown): TimelineNextAction[] {
  const record = asRecord(value);
  if (!record) return [];
  const out: TimelineNextAction[] = [];
  const seen = new Set<string>();
  for (const key of ["next_actions", "recommended_next_actions", "recommended_next_calls"]) {
    const raw = record[key];
    if (Array.isArray(raw)) {
      for (const item of raw) {
        const action = describeNextAction(item);
        if (!action) continue;
        const actionKey = nextActionKey(action);
        if (!seen.has(actionKey)) {
          seen.add(actionKey);
          out.push(action);
        }
      }
    }
  }
  return out;
}

function receiptFromResult(result: RuntimeToolResult): Record<string, unknown> | null {
  const output = asRecord(result.output);
  if (!output) return null;
  return asRecord(output.receipt) ?? asRecord(output.operation_receipt);
}

function eventTitle(event: RuntimeEvent): string {
  const payload = asRecord(event.payload);
  const tool = payload ? asString(payload.tool_name) ?? asString(payload.tool) : null;
  if (tool) return `${event.type}: ${tool}`;
  return event.type.replaceAll("_", " ");
}

function eventDetail(event: RuntimeEvent): string | null {
  const payload = asRecord(event.payload);
  if (!payload) return null;
  const diagnostic = asRecord(payload.diagnostic);
  return asString(diagnostic?.message)
    ?? asString(payload.message)
    ?? asString(payload.reason)
    ?? asString(payload.error);
}

function eventDiagnostic(event: RuntimeEvent): TimelineDiagnostic | null {
  const payload = asRecord(event.payload);
  const diagnostic = payload ? asRecord(payload.diagnostic) : null;
  if (!diagnostic) return null;
  const code = asString(diagnostic.code) ?? asString(payload?.code);
  const message = asString(diagnostic.message) ?? asString(payload?.message) ?? asString(payload?.error);
  if (!code && !message) return null;
  return {
    code: code ?? "diagnostic",
    message: message ?? code ?? "Diagnostic",
    remediation: asString(diagnostic.remediation) ?? asString(payload?.remediation),
    toolName: asString(diagnostic.tool_name) ?? asString(diagnostic.toolName) ?? asString(payload?.tool_name) ?? asString(payload?.tool),
  };
}

function diagnosticFromToolError(error: RuntimeToolError | undefined, fallbackMessage: string | null): TimelineDiagnostic | null {
  const details = asRecord(error?.details);
  const code = asString(details?.code) ?? error?.code ?? (fallbackMessage ? "tool_error" : null);
  const message = asString(details?.message) ?? error?.message ?? fallbackMessage;
  if (!code && !message) return null;
  return {
    code: code ?? "tool_error",
    message: message ?? code ?? "Tool error",
    remediation: asString(details?.remediation),
    toolName: asString(details?.tool_name) ?? asString(details?.toolName) ?? error?.tool_name ?? null,
  };
}

function eventKind(event: RuntimeEvent): ProjectTimelineEntryKind {
  if (event.type.includes("approval")) return "approval";
  if (event.type.includes("failed") || event.type.includes("rejected") || event.type.includes("cancelled")) return "failure";
  if (event.type.includes("tool")) return "tool";
  return "run";
}

function resultTitle(result: RuntimeToolResult): string {
  const receipt = receiptFromResult(result);
  const operation = receipt ? asString(receipt.operation) : null;
  const name = operation ?? result.id;
  return `${name}: ${result.status}`;
}

function resultDetail(output: Record<string, unknown> | null, receipt: Record<string, unknown> | null, fallbackError: string | null): string | null {
  return receipt
    ? asString(receipt.summary) ?? asString(receipt.status)
    : asString(output?.message) ?? fallbackError;
}

export function buildProjectTimeline(runs: RuntimeRun[]): ProjectTimeline {
  const entries: ProjectTimelineEntry[] = [];
  let warningCount = 0;
  let diagnosticCount = 0;
  let unstructuredFailureCount = 0;
  const snapshotIds = new Set<string>();

  for (const run of runs) {
    entries.push({
      id: `${run.run_id}:run`,
      timestamp: run.created_at,
      kind: run.status === "failed" || run.status === "rejected" || run.status === "cancelled" ? "failure" : "run",
      status: run.status,
      title: run.message || run.summary || "Runtime run",
      detail: run.summary,
      diagnostic: null,
      snapshots: [],
      artifacts: [],
      nextActions: [],
      sourceRunId: run.run_id,
    });

    for (const event of run.events ?? []) {
      const payload = asRecord(event.payload);
      const artifacts = collectArtifacts(payload);
      const kind = eventKind(event);
      const diagnostic = eventDiagnostic(event);
      if (diagnostic) diagnosticCount += 1;
      if (kind === "failure" && !diagnostic) unstructuredFailureCount += 1;
      entries.push({
        id: event.id || `${run.run_id}:${event.type}:${event.timestamp}`,
        timestamp: event.timestamp || run.created_at,
        kind,
        status: event.type,
        title: eventTitle(event),
        detail: eventDetail(event),
        diagnostic,
        snapshots: [],
        artifacts,
        nextActions: collectNextActions(payload),
        sourceRunId: run.run_id,
      });
    }

    for (const result of run.tool_results ?? []) {
      const receipt = receiptFromResult(result);
      const output = asRecord(result.output);
      const matchedError = run.tool_errors.find((error) => (
        error.message === result.error
        || (typeof result.error === "string" && error.message.includes(result.error))
      ));
      const fallbackError = asString(result.error);
      if (result.output !== undefined && output === null) warningCount += 1;
      const artifacts = [
        ...collectArtifacts(output),
        ...collectArtifacts(receipt),
        ...collectArtifacts(result),
      ];
      const snapshots = collectSnapshots(output);
      snapshots.forEach((snapshot) => snapshotIds.add(snapshot.id));
      const nextActions = [
        ...collectNextActions(output),
        ...collectNextActions(receipt),
      ];
      const kind = snapshots.length ? "snapshot" : artifacts.length ? "artifact" : result.status === "error" ? "failure" : "tool";
      const diagnostic = diagnosticFromToolError(matchedError, fallbackError);
      if (diagnostic) diagnosticCount += 1;
      if (kind === "failure" && !diagnostic) unstructuredFailureCount += 1;
      entries.push({
        id: `${run.run_id}:result:${result.id}`,
        timestamp: run.created_at,
        kind,
        status: result.status,
        title: resultTitle(result),
        detail: resultDetail(output, receipt, fallbackError),
        diagnostic,
        snapshots,
        artifacts: Array.from(new Set(artifacts)),
        nextActions,
        sourceRunId: run.run_id,
      });
    }
  }

  entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  return { entries, runCount: runs.length, warningCount, diagnosticCount, snapshotCount: snapshotIds.size, unstructuredFailureCount };
}
