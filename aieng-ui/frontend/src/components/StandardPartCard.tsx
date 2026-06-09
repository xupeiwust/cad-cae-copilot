import type { StandardPartSpec, StandardPartPreset } from "../types/standards";

type StandardPartCardProps = {
  spec: StandardPartSpec;
  selectedPreset?: string | null;
  onPresetSelect?: (presetName: string) => void;
  onInsert?: (params: Record<string, number>) => void;
  onParameterChange?: (key: string, value: number) => void;
  currentParameters?: Record<string, number>;
};

export function StandardPartCard({
  spec,
  selectedPreset,
  onPresetSelect,
  onInsert,
  onParameterChange,
  currentParameters,
}: StandardPartCardProps) {
  const params = currentParameters ?? spec.defaultParameters;

  return (
    <div
      style={{
        padding: "12px",
        borderRadius: "10px",
        border: "1px solid var(--glass-line, rgba(180, 196, 218, 0.16))",
        background: "rgba(255, 255, 255, 0.04)",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "8px" }}>
        <strong style={{ fontSize: "13px", color: "var(--text-primary, #e5e5e5)", fontWeight: 650 }}>
          {spec.partType}
        </strong>
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            padding: "2px 8px",
            borderRadius: "999px",
            background: "rgba(148, 163, 184, 0.12)",
            color: "var(--text-secondary, #a3a3a3)",
            whiteSpace: "nowrap",
          }}
        >
          {spec.category}
        </span>
      </div>

      {spec.description ? (
        <p style={{ fontSize: "11px", color: "var(--text-tertiary, #737373)", margin: 0, lineHeight: 1.45 }}>
          {spec.description}
        </p>
      ) : null}

      {spec.standardReference ? (
        <p style={{ fontSize: "10px", color: "var(--text-tertiary, #737373)", margin: 0 }}>
          Ref: {spec.standardReference}
        </p>
      ) : null}

      {/* Presets */}
      {spec.presets.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {spec.presets.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className={selectedPreset === preset.name ? "compact-button" : "ghost-button compact-button"}
              onClick={() => onPresetSelect?.(preset.name)}
              style={{ fontSize: "11px", padding: "4px 10px", borderRadius: "999px" }}
            >
              {preset.displayName}
            </button>
          ))}
        </div>
      )}

      {/* Parameter editor */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "8px",
        }}
      >
        {Object.entries(params).map(([key, value]) => {
          const unit = spec.parameterUnits[key] ?? "";
          const desc = spec.parameterDescriptions?.[key] ?? key;
          return (
            <label key={key} style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ fontSize: "10px", color: "var(--text-tertiary, #737373)", fontWeight: 600 }}>
                {desc}
                {unit ? <span style={{ fontWeight: 400, marginLeft: "3px" }}>({unit})</span> : null}
              </span>
              <input
                type="number"
                step="any"
                value={value}
                onChange={(e) => onParameterChange?.(key, parseFloat(e.target.value))}
                style={{ fontSize: "12px", padding: "6px 8px" }}
              />
            </label>
          );
        })}
      </div>

      {/* 3D preview placeholder */}
      <div
        style={{
          height: "120px",
          borderRadius: "8px",
          border: "1px dashed var(--glass-line, rgba(180, 196, 218, 0.16))",
          background: "rgba(255, 255, 255, 0.02)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: "6px",
        }}
      >
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary, #737373)" strokeWidth="1.5">
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
        <span style={{ fontSize: "11px", color: "var(--text-tertiary, #737373)" }}>3D preview placeholder</span>
      </div>

      {onInsert && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            className="compact-button"
            onClick={() => onInsert(params)}
            style={{ fontSize: "12px", padding: "6px 14px" }}
          >
            Insert into project
          </button>
        </div>
      )}
    </div>
  );
}
