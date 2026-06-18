import type { CSSProperties } from "react";

import type { SolverFieldDescriptor } from "../../types";

type DeformationControlsProps = {
  descriptor?: SolverFieldDescriptor | null;
  enabled: boolean;
  onEnabledChange(enabled: boolean): void;
  scale: number;
  onScaleChange(scale: number): void;
  animationActive?: boolean;
  onAnimationActiveChange?(active: boolean): void;
  animationMode?: "sweep" | "oscillate";
  onAnimationModeChange?(mode: "sweep" | "oscillate"): void;
  disabled?: boolean;
};

const SHELL: CSSProperties = {
  position: "absolute",
  bottom: 12,
  left: 12,
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
  width: 210,
  boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
};

const ROW: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
};

const SLIDER: CSSProperties = {
  flex: 1,
};

const LABEL: CSSProperties = {
  minWidth: 72,
  opacity: 0.85,
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

const PLAY_BUTTON: CSSProperties = {
  ...BUTTON,
  background: "rgba(59, 130, 246, 0.25)",
  borderColor: "#3b82f6",
  minWidth: 56,
};

function _formatScale(scale: number): string {
  if (!Number.isFinite(scale)) return "—";
  if (scale >= 100) return scale.toFixed(0);
  if (scale >= 10) return scale.toFixed(1);
  return scale.toFixed(2);
}

/**
 * Viewer overlay for toggling the exaggerated deformed-shape visualization,
 * adjusting the exaggeration scale, and playing a result animation (#255).
 * Only appears when the active field carries per-node displacement vectors.
 */
export function DeformationControls({
  descriptor,
  enabled,
  onEnabledChange,
  scale,
  onScaleChange,
  animationActive,
  onAnimationActiveChange,
  animationMode,
  onAnimationModeChange,
  disabled,
}: DeformationControlsProps) {
  const hasVectors = Boolean(
    descriptor &&
      Array.isArray(descriptor.vectors) &&
      descriptor.vectors.length > 0 &&
      Array.isArray(descriptor.node_coords) &&
      descriptor.node_coords.length > 0,
  );

  if (!hasVectors) return null;

  const minScale = 0;
  const maxScale = Math.max(200, scale * 2);
  const canAnimate = Boolean(onAnimationActiveChange);

  return (
    <div className="deformation-controls" style={SHELL}>
      <div style={ROW}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={enabled}
            disabled={disabled}
            onChange={(e) => onEnabledChange(e.target.checked)}
          />
          <strong>Show deformed shape</strong>
        </label>
        <button
          type="button"
          style={BUTTON}
          onClick={() => onScaleChange(1)}
          disabled={disabled}
          title="Reset to 1× exaggeration"
        >
          1×
        </button>
      </div>

      {enabled && (
        <div style={ROW}>
          <span style={LABEL}>Exaggeration</span>
          <input
            type="range"
            min={minScale}
            max={maxScale}
            step={Math.max(0.01, maxScale / 20000)}
            value={scale}
            disabled={disabled || animationActive}
            onChange={(e) => onScaleChange(parseFloat(e.target.value))}
            style={SLIDER}
          />
          <span style={{ minWidth: 48, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
            {_formatScale(scale)}×
          </span>
        </div>
      )}

      {enabled && canAnimate && (
        <div style={{ ...ROW, justifyContent: "flex-start", gap: 6 }}>
          <button
            type="button"
            style={PLAY_BUTTON}
            onClick={() => onAnimationActiveChange?.(!animationActive)}
            disabled={disabled}
            title={animationActive ? "Pause animation" : "Play result animation"}
          >
            {animationActive ? "⏸ Pause" : "▶ Play"}
          </button>
          {onAnimationModeChange && (
            <select
              aria-label="Animation mode"
              value={animationMode}
              disabled={disabled || animationActive}
              onChange={(e) => onAnimationModeChange(e.target.value as "sweep" | "oscillate")}
              style={{
                background: "#111827",
                color: "#e5e7eb",
                border: "1px solid #374151",
                borderRadius: 4,
                fontSize: 11,
                padding: "2px 4px",
                flex: 1,
              }}
            >
              <option value="sweep">Sweep 0→1→0</option>
              <option value="oscillate">Oscillate ±1</option>
            </select>
          )}
        </div>
      )}

      {enabled && descriptor?.bbox_status === "suspicious" ? (
        <span style={{ color: "#f59e0b", fontSize: 11 }}>
          ⚠ Results may not align with current geometry.
        </span>
      ) : null}
    </div>
  );
}
