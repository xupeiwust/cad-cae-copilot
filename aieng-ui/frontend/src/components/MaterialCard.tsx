import type { Material } from "../types/materials";

type MaterialCardProps = {
  material: Material;
  selected?: boolean;
  onSelect?: (material: Material) => void;
  onCompareToggle?: (material: Material) => void;
  isCompareCandidate?: boolean;
};

export function MaterialCard({
  material,
  selected = false,
  onSelect,
  onCompareToggle,
  isCompareCandidate = false,
}: MaterialCardProps) {
  const p = material.properties;
  return (
    <div
      className="material-card"
      style={{
        padding: "12px",
        borderRadius: "10px",
        border: selected
          ? "1px solid rgba(56, 189, 248, 0.6)"
          : "1px solid var(--glass-line, rgba(180, 196, 218, 0.16))",
        background: selected
          ? "rgba(56, 189, 248, 0.08)"
          : "rgba(255, 255, 255, 0.04)",
        cursor: onSelect ? "pointer" : "default",
        transition: "background 0.15s ease, border-color 0.15s ease",
      }}
      onClick={() => onSelect?.(material)}
      role={onSelect ? "button" : undefined}
      aria-pressed={selected}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "8px",
          marginBottom: "8px",
        }}
      >
        <strong
          style={{
            fontSize: "13px",
            color: "var(--text-primary, #e5e5e5)",
            fontWeight: 650,
          }}
        >
          {material.name}
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
          {material.category}
        </span>
      </div>

      {material.description ? (
        <p
          style={{
            fontSize: "11px",
            color: "var(--text-tertiary, #737373)",
            margin: "0 0 8px",
            lineHeight: 1.45,
          }}
        >
          {material.description}
        </p>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "6px",
        }}
      >
        <PropertyRow label="E" value={p.youngs_modulus_mpa} unit="MPa" />
        <PropertyRow label="ν" value={p.poisson_ratio} unit="" />
        <PropertyRow label="ρ" value={p.density_kg_m3} unit="kg/m³" />
        <PropertyRow label="σy" value={p.yield_strength_mpa} unit="MPa" />
      </div>

      {onCompareToggle ? (
        <div style={{ marginTop: "8px", display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            className="ghost-button"
            style={{
              fontSize: "11px",
              padding: "4px 10px",
              borderRadius: "6px",
            }}
            onClick={(e) => {
              e.stopPropagation();
              onCompareToggle(material);
            }}
            title={isCompareCandidate ? "Remove from comparison" : "Add to comparison"}
          >
            {isCompareCandidate ? "− Compare" : "+ Compare"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function PropertyRow({
  label,
  value,
  unit,
}: {
  label: string;
  value: number;
  unit: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: "4px",
        fontSize: "11px",
      }}
    >
      <span style={{ color: "var(--text-tertiary, #737373)", fontWeight: 600 }}>{label}</span>
      <span style={{ color: "var(--text-secondary, #a3a3a3)", fontFamily: "ui-monospace, monospace" }}>
        {typeof value === "number" ? value.toLocaleString() : value}
        {unit ? <span style={{ color: "var(--text-tertiary, #737373)", fontSize: "10px", marginLeft: "2px" }}>{unit}</span> : null}
      </span>
    </div>
  );
}
