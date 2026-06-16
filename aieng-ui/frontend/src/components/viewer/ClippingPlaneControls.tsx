import type { CSSProperties } from "react";

import type { ClipAxis } from "./clippingPlane";

type ClippingPlaneControlsProps = {
  available: boolean;
  enabled: boolean;
  onEnabledChange(enabled: boolean): void;
  axis: ClipAxis;
  onAxisChange(axis: ClipAxis): void;
  position: number;
  onPositionChange(position: number): void;
  flip: boolean;
  onFlipChange(flip: boolean): void;
  disabled?: boolean;
};

const SHELL: CSSProperties = {
  position: "absolute",
  bottom: 12,
  left: "50%",
  transform: "translateX(-50%)",
  zIndex: 5,
  background: "rgba(17, 24, 39, 0.92)",
  color: "#e5e7eb",
  borderRadius: 8,
  padding: "8px 10px",
  font: "12px/1.3 system-ui, sans-serif",
  display: "flex",
  flexDirection: "column",
  gap: 6,
  pointerEvents: "auto",
  minWidth: 260,
  boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
};

const ROW: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
};

const BUTTON_GROUP: CSSProperties = {
  display: "flex",
  gap: 4,
};

const AXIS_BUTTON_BASE: CSSProperties = {
  background: "rgba(255,255,255,0.1)",
  border: "1px solid #4b5563",
  borderRadius: 4,
  color: "#e5e7eb",
  cursor: "pointer",
  fontSize: 11,
  padding: "2px 8px",
  textTransform: "uppercase",
};

const SLIDER: CSSProperties = {
  flex: 1,
};

const LABEL: CSSProperties = {
  minWidth: 56,
  opacity: 0.85,
};

const ACTION_BUTTON: CSSProperties = {
  background: "rgba(255,255,255,0.1)",
  border: "1px solid #4b5563",
  borderRadius: 4,
  color: "#e5e7eb",
  cursor: "pointer",
  fontSize: 11,
  padding: "2px 6px",
};

export function ClippingPlaneControls({
  available,
  enabled,
  onEnabledChange,
  axis,
  onAxisChange,
  position,
  onPositionChange,
  flip,
  onFlipChange,
  disabled,
}: ClippingPlaneControlsProps) {
  if (!available) return null;

  return (
    <div className="clipping-plane-controls" style={SHELL}>
      <div style={ROW}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled}
            onChange={(e) => onEnabledChange(e.target.checked)}
          />
          <strong>Section plane</strong>
        </label>
        <div style={BUTTON_GROUP}>
          {(["x", "y", "z"] as ClipAxis[]).map((a) => (
            <button
              key={a}
              type="button"
              style={{
                ...AXIS_BUTTON_BASE,
                background: axis === a ? "rgba(59, 130, 246, 0.45)" : AXIS_BUTTON_BASE.background,
                borderColor: axis === a ? "#3b82f6" : AXIS_BUTTON_BASE.borderColor,
              }}
              onClick={() => onAxisChange(a)}
              disabled={disabled || !enabled}
              aria-label={`Set clip axis to ${a}`}
              title={`Clip along ${a.toUpperCase()}`}
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      {enabled && (
        <div style={ROW}>
          <span style={LABEL}>Position</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.005}
            value={position}
            disabled={disabled}
            onChange={(e) => onPositionChange(parseFloat(e.target.value))}
            style={SLIDER}
          />
          <span style={{ minWidth: 44, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
            {(position * 100).toFixed(0)}%
          </span>
        </div>
      )}

      {enabled && (
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            type="button"
            style={ACTION_BUTTON}
            onClick={() => onFlipChange(!flip)}
            disabled={disabled}
            title="Flip which side of the plane is visible"
          >
            Flip side
          </button>
          <button
            type="button"
            style={ACTION_BUTTON}
            onClick={() => {
              onAxisChange("x");
              onPositionChange(0.5);
              onFlipChange(false);
            }}
            disabled={disabled}
            title="Reset to X-axis middle"
          >
            Reset
          </button>
        </div>
      )}
    </div>
  );
}
