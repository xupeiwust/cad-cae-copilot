import type { CSSProperties } from "react";

import type { SolverFieldDescriptor } from "../types";
import { colormapCssStops } from "./viewer/fieldColors";
import { formatFieldValue, legendTicks, resultFieldLabel } from "./viewer/resultFields";

type FieldLegendProps = {
  descriptor: SolverFieldDescriptor | null;
};

const SHELL: CSSProperties = {
  position: "absolute",
  top: 12,
  right: 12,
  zIndex: 5,
  background: "rgba(17, 24, 39, 0.82)",
  color: "#e5e7eb",
  borderRadius: 8,
  padding: "8px 10px",
  font: "12px/1.3 system-ui, sans-serif",
  display: "flex",
  flexDirection: "column",
  gap: 6,
  pointerEvents: "none",
};

// Color scale bar for the active result field: label, gradient, min↔max ticks
// with units. Honest when the descriptor is not real solver data.
export function FieldLegend({ descriptor }: FieldLegendProps) {
  if (!descriptor) return null;
  const label = resultFieldLabel(descriptor.field_name);
  const unit = descriptor.unit ?? "";
  const hasRealData =
    descriptor.source === "frd" && Array.isArray(descriptor.values) && descriptor.values.length > 0;

  if (!hasRealData) {
    return (
      <div className="field-legend" style={SHELL}>
        <strong>{label}</strong>
        <span style={{ opacity: 0.75 }}>No solver result for this field.</span>
      </div>
    );
  }

  const stops = colormapCssStops(descriptor.colormap, 10);
  const gradient = `linear-gradient(to top, ${stops.join(", ")})`;
  // Ticks high→low so the top of the bar (high color) reads as the max.
  const ticks = legendTicks(descriptor.min_value, descriptor.max_value, 5).reverse();

  return (
    <div className="field-legend" style={SHELL}>
      <strong>{label}</strong>
      <div style={{ display: "flex", gap: 8 }}>
        <div
          aria-hidden
          style={{ width: 14, height: 120, borderRadius: 3, background: gradient, border: "1px solid #374151" }}
        />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", height: 120 }}>
          {ticks.map((t, i) => (
            <span key={i} style={{ fontVariantNumeric: "tabular-nums" }}>
              {formatFieldValue(t, unit)}
            </span>
          ))}
        </div>
      </div>
      {descriptor.bbox_status === "suspicious" ? (
        <span style={{ color: "#f59e0b" }}>⚠ results may not align with current geometry</span>
      ) : null}
    </div>
  );
}
