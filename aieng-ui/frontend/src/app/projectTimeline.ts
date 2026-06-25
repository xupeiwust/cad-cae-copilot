import type { RuntimeEvent, RuntimeRun, RuntimeToolResult } from "../types";

export type ProjectTimelineEntryKind =
  | "run"
  | "approval"
  | "tool"
  | "artifact"
  | "next_action"
  | "failure";

export type ProjectTimelineEntry = {
  id: string;
  timestamp: string;
  kind: ProjectTimelineEntryKind;
  status: string;
  title: string;
  detail?: string | null;
  artifacts: string[];
  nextActions: string[];
  sourceRunId: string;
};

export type ProjectTimeline = {
  entries: ProjectTimelineEntry[];
  runCount: number;
  warningCount: number;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
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

function describeNextAction(item: unknown): string | null {
  if (typeof item === "string" && item.trim()) return item;
  const record = asRecord(item);
  if (!record) return null;
  const tool = asString(record.tool) ?? asString(record.name) ?? asString(record.reference);
  const label = asString(record.label) ?? asString(record.summary) ?? asString(record.description);
  if (tool && label) return `${tool}: ${label}`;
  return tool ?? label;
}

function collectNextActions(value: unknown): string[] {
  const record = asRecord(value);
  if (!record) return [];
  const out: string[] = [];
  for (const key of ["next_actions", "recommended_next_actions", "recommended_next_calls"]) {
    const raw = record[key];
    if (Array.isArray(raw)) {
      for (const item of raw) {
        const text = describeNextAction(item);
        if (text) out.push(text);
      }
    }
  }
  return Array.from(new Set(out));
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

export function buildProjectTimeline(runs: RuntimeRun[]): ProjectTimeline {
  const entries: ProjectTimelineEntry[] = [];
  let warningCount = 0;

  for (const run of runs) {
    entries.push({
      id: `${run.run_id}:run`,
      timestamp: run.created_at,
      kind: run.status === "failed" || run.status === "rejected" || run.status === "cancelled" ? "failure" : "run",
      status: run.status,
      title: run.message || run.summary || "Runtime run",
      detail: run.summary,
      artifacts: [],
      nextActions: [],
      sourceRunId: run.run_id,
    });

    for (const event of run.events ?? []) {
      const payload = asRecord(event.payload);
      const artifacts = collectArtifacts(payload);
      entries.push({
        id: event.id || `${run.run_id}:${event.type}:${event.timestamp}`,
        timestamp: event.timestamp || run.created_at,
        kind: eventKind(event),
        status: event.type,
        title: eventTitle(event),
        detail: payload ? asString(payload.message) ?? asString(payload.reason) : null,
        artifacts,
        nextActions: collectNextActions(payload),
        sourceRunId: run.run_id,
      });
    }

    for (const result of run.tool_results ?? []) {
      const receipt = receiptFromResult(result);
      const output = asRecord(result.output);
      if (result.output !== undefined && output === null) warningCount += 1;
      const artifacts = [
        ...collectArtifacts(output),
        ...collectArtifacts(receipt),
        ...collectArtifacts(result),
      ];
      const nextActions = [
        ...collectNextActions(output),
        ...collectNextActions(receipt),
      ];
      entries.push({
        id: `${run.run_id}:result:${result.id}`,
        timestamp: run.created_at,
        kind: artifacts.length ? "artifact" : result.status === "error" ? "failure" : "tool",
        status: result.status,
        title: resultTitle(result),
        detail: receipt ? asString(receipt.summary) ?? asString(receipt.status) : null,
        artifacts: Array.from(new Set(artifacts)),
        nextActions: Array.from(new Set(nextActions)),
        sourceRunId: run.run_id,
      });
    }
  }

  entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  return { entries, runCount: runs.length, warningCount };
}
