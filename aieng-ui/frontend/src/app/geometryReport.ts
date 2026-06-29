/**
 * Pure shaping helpers for the viewer "assembly check" overlay. No React, no I/O.
 *
 * Turns the backend `/geometry-report` payload into the overlay's display model:
 * the named parts that are floating (drawn with a red box) and the parts in a
 * broken / missing-partner symmetry pair (drawn amber), plus deep-overlap /
 * containment volumes (drawn purple). All boxes resolve from `part_boxes`; a
 * relationship without enough boxes is dropped rather than guessed.
 */

import type { GeometryReportResponse, GeometrySpatialRelationship, GeometrySymmetryPair } from "../types";

export type PartBox = { name: string; bbox: number[] };
export type SpatialIssueBox = { names: string[]; bbox: number[]; status: string };

function partBox(report: GeometryReportResponse | null, name: string): number[] | null {
  const box = report?.part_boxes?.[name];
  return Array.isArray(box) && box.length >= 6 ? box : null;
}

/** A symmetry pair the report considers wrong (mismatched) or missing a side. */
export function isBrokenSymmetry(entry: GeometrySymmetryPair | null | undefined): boolean {
  return !!entry && (entry.ok === false || entry.status === "missing_partner");
}

/** Distinct part names involved in a broken / missing-partner symmetry pair. */
export function brokenSymmetryNames(report: GeometryReportResponse | null): string[] {
  const names = new Set<string>();
  for (const entry of report?.symmetry ?? []) {
    if (!isBrokenSymmetry(entry)) continue;
    if (entry.part) names.add(entry.part);
    for (const n of entry.pair ?? []) {
      if (n) names.add(String(n));
    }
  }
  return [...names];
}

/** Floating named parts that have a bounding box to draw. */
export function floatingPartBoxes(report: GeometryReportResponse | null): PartBox[] {
  const out: PartBox[] = [];
  for (const name of report?.floating_parts ?? []) {
    const bbox = partBox(report, name);
    if (bbox) out.push({ name, bbox });
  }
  return out;
}

/** Parts of broken symmetry pairs that have a bounding box to draw. */
export function brokenSymmetryPartBoxes(report: GeometryReportResponse | null): PartBox[] {
  const out: PartBox[] = [];
  for (const name of brokenSymmetryNames(report)) {
    const bbox = partBox(report, name);
    if (bbox) out.push({ name, bbox });
  }
  return out;
}

function isSpatialIssue(entry: GeometrySpatialRelationship | null | undefined): boolean {
  return entry?.status === "deep_overlap" || entry?.status === "contained";
}

function intersectionBox(a: number[], b: number[]): number[] | null {
  const box = [
    Math.max(a[0], b[0]),
    Math.max(a[1], b[1]),
    Math.max(a[2], b[2]),
    Math.min(a[3], b[3]),
    Math.min(a[4], b[4]),
    Math.min(a[5], b[5]),
  ];
  return box[0] < box[3] && box[1] < box[4] && box[2] < box[5] ? box : null;
}

/**
 * Interpenetration/containment relationships with a drawable intersection box.
 * We draw the overlapping volume rather than guessing which whole part is wrong.
 */
export function spatialIssueBoxes(report: GeometryReportResponse | null): SpatialIssueBox[] {
  const out: SpatialIssueBox[] = [];
  for (const entry of report?.spatial_relationships ?? []) {
    if (!isSpatialIssue(entry)) continue;
    const names = (entry.parts ?? []).map(String).filter(Boolean);
    if (names.length < 2) continue;
    const a = partBox(report, names[0]);
    const b = partBox(report, names[1]);
    if (!a || !b) continue;
    const bbox = intersectionBox(a, b);
    if (bbox) out.push({ names: names.slice(0, 2), bbox, status: String(entry.status ?? "spatial_issue") });
  }
  return out;
}

/** Headline counts for the toggle badge. `total` drives whether to offer it. */
export function assemblyAlertCounts(
  report: GeometryReportResponse | null,
): { floating: number; symmetry: number; spatial: number; total: number } {
  const floating = (report?.floating_parts ?? []).length;
  const symmetry = (report?.symmetry ?? []).filter(isBrokenSymmetry).length;
  const spatial = (report?.spatial_relationships ?? []).filter(isSpatialIssue).length;
  return { floating, symmetry, spatial, total: floating + symmetry + spatial };
}
