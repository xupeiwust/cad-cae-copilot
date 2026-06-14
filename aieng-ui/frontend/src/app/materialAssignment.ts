/**
 * Pure shaping for the material assignment flow (#225). No React, no I/O.
 *
 * The Material Library can pick + compare materials but had no path to actually
 * assign one. This builds the assignment target list (all parts, or a specific
 * named part) and a composer-ready `/modify` draft. The assignment still flows
 * through the existing plan-confirmed, approval-gated `set_part_material` path —
 * the panel drafts, the agent + approval apply (materials are per-part, so the
 * targets are named parts, not faces).
 */

export const ALL_PARTS_TARGET = "__all__";

export type AssignmentTarget = {
  value: string;
  label: string;
};

/** Target options: "All named parts" first, then each named part. Pure. */
export function assignmentTargets(parts: string[] | null | undefined): AssignmentTarget[] {
  const named = (parts ?? []).filter((p) => typeof p === "string" && p.trim().length > 0);
  return [
    { value: ALL_PARTS_TARGET, label: `All named parts${named.length ? ` (${named.length})` : ""}` },
    ...named.map((p) => ({ value: p, label: p.replace(/_/g, " ") })),
  ];
}

/**
 * A composer-ready material-assignment draft, or null when material/target is
 * missing. Routes through `/modify` so the connecting agent applies it via the
 * approval-gated `set_part_material` tool — never a silent mutation.
 */
export function materialAssignmentDraft(
  materialName: string | null | undefined,
  target: string | null | undefined,
): string | null {
  const material = (materialName ?? "").trim();
  const tgt = (target ?? "").trim();
  if (!material || !tgt) return null;
  if (tgt === ALL_PARTS_TARGET) {
    return `/modify assign material ${material} to all named parts`;
  }
  return `/modify assign material ${material} to part ${tgt}`;
}
