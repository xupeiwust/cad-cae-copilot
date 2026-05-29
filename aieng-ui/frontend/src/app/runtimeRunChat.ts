import type { ChatHistoryItem } from "../appTypes";
import {
  createChatId,
  extractArtifactPaths,
  formatArtifactChanges,
  formatGeometryResult,
  runtimeRunToChatPlan,
  runtimeStatusLabel,
} from "../appUtils";
import type { ArtifactDiff, RuntimeRun } from "../types";

export function runtimeRunChatEntry(run: RuntimeRun): ChatHistoryItem {
  const statusLabel = runtimeStatusLabel(run.status);
  const geoResult = run.tool_results.find(
    (toolResult) =>
      toolResult.status === "success" &&
      run.tool_calls.find((toolCall) => toolCall.id === toolResult.id && toolCall.name === "freecad.inspect_geometry"),
  );
  const geoLine =
    geoResult && typeof geoResult.output === "object" && geoResult.output !== null
      ? formatGeometryResult(geoResult.output as Record<string, unknown>)
      : null;
  const artifactLine = formatArtifactChanges(run);
  const body = geoLine
    ? `[Local runtime] ${statusLabel} — ${geoLine}${artifactLine ? "\n" + artifactLine : ""}`
    : run.summary
      ? `[Local runtime] ${statusLabel} — ${run.summary}${artifactLine ? "\n" + artifactLine : ""}`
      : `[Local runtime] ${statusLabel}${artifactLine ? "\n" + artifactLine : ""}`;
  const artifactPaths = extractArtifactPaths(run);

  let artifactDiffs: ArtifactDiff[] | undefined;
  const patchResult = run.tool_results.find((toolResult) =>
    toolResult.status === "success" &&
    run.tool_calls.find((toolCall) => toolCall.id === toolResult.id && toolCall.name === "cae.apply_setup_patch"),
  );
  if (patchResult && typeof patchResult.output === "object" && patchResult.output !== null) {
    const diffs = (patchResult.output as Record<string, unknown>).artifact_diffs;
    if (Array.isArray(diffs) && diffs.length > 0) {
      artifactDiffs = diffs as ArtifactDiff[];
    }
  }

  return {
    id: createChatId(),
    role: "assistant",
    body,
    createdAt: new Date().toISOString(),
    mode: "runtime",
    plan: runtimeRunToChatPlan(run),
    errors: run.errors,
    auditLogUrl: null,
    artifactPaths: artifactPaths.length ? artifactPaths : undefined,
    artifactDiffs,
  };
}
