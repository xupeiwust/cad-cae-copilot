type LoadCaseOption = {
  id: string;
  name?: string | null;
  type?: string | null;
};

type LoadCasePickerProps = {
  value: string | null;
  loadCases: LoadCaseOption[];
  onChange(id: string): void;
  disabled?: boolean;
};

// Load-case / analysis-step selector for multi-step CAE results (modal modes,
// buckling eigenvectors, multi-step static analyses, etc.).
export function LoadCasePicker({ value, loadCases, onChange, disabled }: LoadCasePickerProps) {
  if (!loadCases || loadCases.length === 0) return null;

  return (
    <div
      className="load-case-picker"
      style={{
        position: "absolute",
        top: 12,
        left: 220,
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
      <label htmlFor="load-case-picker" style={{ opacity: 0.8 }}>
        Load case
      </label>
      <select
        id="load-case-picker"
        aria-label="Load case"
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: "#111827",
          color: "#e5e7eb",
          border: "1px solid #374151",
          borderRadius: 6,
          padding: "3px 6px",
          minWidth: 140,
        }}
      >
        {loadCases.map((lc) => (
          <option key={lc.id} value={lc.id}>
            {lc.name || lc.id}
            {lc.type ? ` · ${lc.type}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
