/**
 * Pure shaping helpers for the viewer "assembly check" overlay. No React, no I/O.
 *
 * Turns the backend `/geometry-report` payload into the overlay's display model:
 * the named parts that are floating (drawn with a red box) and the parts in a
 * broken / missing-partner symmetry pair (drawn amber), each resolved to its
 * model-frame bounding box from `part_boxes`. A part without a box is dropped
 * (nothing to draw) rather than guessed.
 */

import type { GeometryReportResponse, GeometrySymmetryPair } from "../types";

export type PartBox = { name: string; bbox: number[] };

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

/** Headline counts for the toggle badge. `total` drives whether to offer it. */
export function assemblyAlertCounts(
  report: GeometryReportResponse | null,
): { floating: number; symmetry: number; total: number } {
  const floating = (report?.floating_parts ?? []).length;
  const symmetry = (report?.symmetry ?? []).filter(isBrokenSymmetry).length;
  return { floating, symmetry, total: floating + symmetry };
}
