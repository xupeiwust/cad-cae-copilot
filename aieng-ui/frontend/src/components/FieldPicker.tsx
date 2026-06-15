import { RESULT_FIELD_GROUPS } from "./viewer/resultFields";

type FieldPickerProps = {
  value: string; // canonical field name, or "" for no overlay
  onChange(name: string): void;
  disabled?: boolean;
};

// Post-processing result-field selector — grouped like a CAE post-processor
// (Stress / Principal / Displacement / Safety). Drives which field is painted.
export function FieldPicker({ value, onChange, disabled }: FieldPickerProps) {
  return (
    <div
      className="field-picker"
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        zIndex: 5,
        background: "rgba(17, 24, 39, 0.82)",
        color: "#e5e7eb",
        borderRadius: 8,
        padding: "6px 8px",
        font: "12px/1.3 system-ui, sans-serif",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        pointerEvents: "auto",
      }}
    >
      <label htmlFor="result-field-picker" style={{ opacity: 0.8 }}>
        Result field
      </label>
      <select
        id="result-field-picker"
        aria-label="Result field"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        style={{ background: "#111827", color: "#e5e7eb", border: "1px solid #374151", borderRadius: 6, padding: "3px 6px" }}
      >
        <option value="">None (geometry)</option>
        {RESULT_FIELD_GROUPS.map((group) => (
          <optgroup key={group.group} label={group.group}>
            {group.fields.map((f) => (
              <option key={f.name} value={f.name}>
                {f.label}
                {f.unit ? ` (${f.unit})` : ""}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
