import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import type { FieldOverlayConfig, SolverFieldDescriptor } from "../types";
import {
  colormapCssGradient,
  effectiveFieldRange,
  FIELD_COLORMAPS,
} from "./viewer/fieldColors";
import { formatFieldValue, legendTicks, resultFieldLabel } from "./viewer/resultFields";

type FieldLegendProps = {
  descriptor: SolverFieldDescriptor | null;
  config?: FieldOverlayConfig | null;
  onChange?(config: FieldOverlayConfig | null): void;
};

const SHELL: CSSProperties = {
  position: "absolute",
  top: 12,
  right: 12,
  zIndex: 5,
  background: "rgba(17, 24, 39, 0.92)",
  color: "#e5e7eb",
  borderRadius: 8,
  padding: "10px 12px",
  font: "12px/1.3 system-ui, sans-serif",
  display: "flex",
  flexDirection: "column",
  gap: 8,
  pointerEvents: "auto",
  width: 190,
  boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
};

const ROW: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
};

const LABEL: CSSProperties = {
  minWidth: 44,
  opacity: 0.85,
};

const INPUT: CSSProperties = {
  width: 56,
  background: "rgba(255,255,255,0.08)",
  border: "1px solid #374151",
  borderRadius: 4,
  color: "#e5e7eb",
  padding: "2px 4px",
  fontSize: 11,
};

const SELECT: CSSProperties = {
  flex: 1,
  background: "rgba(255,255,255,0.08)",
  border: "1px solid #374151",
  borderRadius: 4,
  color: "#e5e7eb",
  padding: "2px 4px",
  fontSize: 11,
};

const BUTTON: CSSProperties = {
  background: "rgba(255,255,255,0.1)",
  border: "1px solid #4b5563",
  borderRadius: 4,
  color: "#e5e7eb",
  cursor: "pointer",
  fontSize: 11,
  padding: "2px 6px",
};

function valueToInputString(value: number | null | undefined): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return "";
  return value.toString();
}

function parseNumberInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const parsed = parseFloat(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

// Interactive color legend for the active result field. Mirrors the mapping
// applied by `applyFieldColors` so the user sees exactly what the mesh shows.
export function FieldLegend({ descriptor, config, onChange }: FieldLegendProps) {
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

  const effectiveRange = effectiveFieldRange(descriptor.min_value, descriptor.max_value, config);
  const ticks = legendTicks(effectiveRange.min, effectiveRange.max, 5).reverse();
  const gradient = colormapCssGradient(config?.colormap ?? descriptor.colormap, config?.bands);
  const isIsolating = config?.thresholdMin !== undefined && config.thresholdMin !== null;

  return (
    <div className="field-legend" style={SHELL}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{label}</strong>
        <button
          type="button"
          style={BUTTON}
          onClick={() => onChange?.(null)}
          title="Reset range, colormap, bands, and threshold"
        >
          Reset
        </button>
      </div>

      <ControlRow label="Colormap">
        <select
          style={SELECT}
          value={config?.colormap ?? descriptor.colormap ?? "thermal"}
          onChange={(e) =>
            onChange?.({
              ...config,
              colormap: e.target.value,
            })
          }
        >
          {FIELD_COLORMAPS.map((name) => (
            <option key={name} value={name} style={{ background: "#111827" }}>
              {name}
            </option>
          ))}
        </select>
      </ControlRow>

      <ControlRow label="Range">
        <RangeInputs
          descriptor={descriptor}
          config={config}
          onChange={onChange}
        />
      </ControlRow>

      <ControlRow label="Bands">
        <input
          type="number"
          min={2}
          style={{ ...INPUT, width: 48 }}
          value={config?.bands ?? ""}
          placeholder="cont."
          onChange={(e) => {
            const parsed = parseInt(e.target.value, 10);
            const bands = Number.isFinite(parsed) && parsed >= 2 ? parsed : null;
            onChange?.({ ...config, bands });
          }}
          title="Number of discrete contour bands; leave empty for continuous"
        />
      </ControlRow>

      <ControlRow label="Isolate">
        <ThresholdInput descriptor={descriptor} config={config} onChange={onChange} />
      </ControlRow>

      <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
        <div
          aria-hidden
          style={{
            flex: 1,
            height: 120,
            borderRadius: 3,
            background: gradient,
            border: "1px solid #374151",
            position: "relative",
          }}
        >
          {isIsolating && config?.thresholdMin !== null ? (
            <ThresholdLine value={config.thresholdMin!} min={effectiveRange.min} max={effectiveRange.max} />
          ) : null}
        </div>
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

function ControlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={ROW}>
      <span style={LABEL}>{label}</span>
      {children}
    </div>
  );
}

function RangeInputs({
  descriptor,
  config,
  onChange,
}: {
  descriptor: SolverFieldDescriptor;
  config?: FieldOverlayConfig | null;
  onChange?(config: FieldOverlayConfig | null): void;
}) {
  const [minRaw, setMinRaw] = useState(valueToInputString(config?.clampMin));
  const [maxRaw, setMaxRaw] = useState(valueToInputString(config?.clampMax));

  useEffect(() => {
    setMinRaw(valueToInputString(config?.clampMin));
    setMaxRaw(valueToInputString(config?.clampMax));
  }, [config?.clampMin, config?.clampMax]);

  const commit = () => {
    const min = parseNumberInput(minRaw);
    const max = parseNumberInput(maxRaw);
    if (min !== null && max !== null && min > max) {
      // Invalid range: fall back to auto rather than inventing an inverted scale.
      onChange?.({ ...config, clampMin: null, clampMax: null });
      return;
    }
    const next: FieldOverlayConfig = {
      ...config,
      clampMin: min === null || min === descriptor.min_value ? null : min,
      clampMax: max === null || max === descriptor.max_value ? null : max,
    };
    onChange?.(next);
  };

  return (
    <>
      <input
        type="number"
        style={INPUT}
        value={minRaw}
        onChange={(e) => setMinRaw(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        placeholder={formatFieldValue(descriptor.min_value, undefined)}
        title="Manual minimum; empty = auto"
      />
      <span style={{ opacity: 0.6 }}>–</span>
      <input
        type="number"
        style={INPUT}
        value={maxRaw}
        onChange={(e) => setMaxRaw(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        placeholder={formatFieldValue(descriptor.max_value, undefined)}
        title="Manual maximum; empty = auto"
      />
    </>
  );
}

function ThresholdInput({
  descriptor,
  config,
  onChange,
}: {
  descriptor: SolverFieldDescriptor;
  config?: FieldOverlayConfig | null;
  onChange?(config: FieldOverlayConfig | null): void;
}) {
  const [raw, setRaw] = useState(valueToInputString(config?.thresholdMin));

  useEffect(() => {
    setRaw(valueToInputString(config?.thresholdMin));
  }, [config?.thresholdMin]);

  const enabled = config?.thresholdMin !== undefined && config.thresholdMin !== null;

  const commit = () => {
    const value = parseNumberInput(raw);
    if (value === null) {
      const { thresholdMin: _, ...rest } = config ?? {};
      onChange?.(rest);
      return;
    }
    onChange?.({ ...config, thresholdMin: value });
  };

  return (
    <>
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => {
          if (e.target.checked) {
            const fallback = config?.thresholdMin ?? descriptor.min_value;
            onChange?.({ ...config, thresholdMin: fallback });
          } else {
            const { thresholdMin: _, ...rest } = config ?? {};
            onChange?.(rest);
          }
        }}
        title="Hide values below the threshold"
      />
      <input
        type="number"
        style={{ ...INPUT, width: 70 }}
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        disabled={!enabled}
        title="Values below this number are masked in grey"
      />
      <span style={{ opacity: 0.6 }}>{enabled ? ">" : "off"}</span>
    </>
  );
}

function ThresholdLine({
  value,
  min,
  max,
}: {
  value: number;
  min: number;
  max: number;
}) {
  if (max <= min) return null;
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const bottom = `${t * 100}%`;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom,
        height: 1,
        borderTop: "1px dashed rgba(255,255,255,0.85)",
        pointerEvents: "none",
      }}
      title={`Isolate >= ${value}`}
    />
  );
}
