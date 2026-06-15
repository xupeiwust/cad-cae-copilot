// Result-field catalog + formatting for the post-processing field picker & legend.
// Mirrors the backend FIELD_CATALOG (aieng/simulation/field_derivation.py). Pure
// (no THREE / React) so it is unit-testable in isolation.

export type ResultFieldDef = { name: string; label: string; unit: string };
export type ResultFieldGroup = { group: string; fields: ResultFieldDef[] };

// Grouped exactly as a CAE post-processor presents them.
export const RESULT_FIELD_GROUPS: ResultFieldGroup[] = [
  {
    group: "Stress",
    fields: [
      { name: "von_mises", label: "Von Mises", unit: "MPa" },
      { name: "sxx", label: "Sxx", unit: "MPa" },
      { name: "syy", label: "Syy", unit: "MPa" },
      { name: "szz", label: "Szz", unit: "MPa" },
      { name: "sxy", label: "Sxy", unit: "MPa" },
      { name: "sxz", label: "Sxz", unit: "MPa" },
      { name: "syz", label: "Syz", unit: "MPa" },
    ],
  },
  {
    group: "Principal",
    fields: [
      { name: "s1", label: "S1 (max principal)", unit: "MPa" },
      { name: "s2", label: "S2 (mid principal)", unit: "MPa" },
      { name: "s3", label: "S3 (min principal)", unit: "MPa" },
      { name: "tresca", label: "Tresca", unit: "MPa" },
      { name: "max_shear", label: "Max shear", unit: "MPa" },
    ],
  },
  {
    group: "Displacement",
    fields: [
      { name: "disp_magnitude", label: "Magnitude", unit: "mm" },
      { name: "ux", label: "Ux", unit: "mm" },
      { name: "uy", label: "Uy", unit: "mm" },
      { name: "uz", label: "Uz", unit: "mm" },
    ],
  },
  {
    group: "Safety",
    fields: [{ name: "safety_factor", label: "Safety factor (yield/VM)", unit: "" }],
  },
];

const _BY_NAME: Record<string, ResultFieldDef> = Object.fromEntries(
  RESULT_FIELD_GROUPS.flatMap((g) => g.fields).map((f) => [f.name, f]),
);

// Legacy aliases the backend still accepts.
const _ALIAS: Record<string, string> = { stress: "von_mises", displacement: "disp_magnitude" };

export function canonicalResultField(name: string): string {
  const key = (name ?? "").trim().toLowerCase();
  return _ALIAS[key] ?? key;
}

export function resultFieldLabel(name: string): string {
  const def = _BY_NAME[canonicalResultField(name)];
  return def ? def.label : name;
}

export function allResultFieldNames(): string[] {
  return RESULT_FIELD_GROUPS.flatMap((g) => g.fields.map((f) => f.name));
}

// Compact, readable numeric formatting for legend ticks / probes.
export function formatFieldValue(value: number, unit?: string | null): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  let text: string;
  if (abs !== 0 && (abs >= 1e5 || abs < 1e-3)) {
    text = value.toExponential(2);
  } else if (abs >= 100) {
    text = value.toFixed(1);
  } else if (abs >= 1) {
    text = value.toFixed(2);
  } else {
    text = value.toFixed(4);
  }
  return unit ? `${text} ${unit}` : text;
}

// Evenly-spaced numeric ticks across [min, max] for the legend scale.
export function legendTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count < 2) return [min];
  if (max === min) return [min];
  const ticks: number[] = [];
  for (let i = 0; i < count; i += 1) {
    ticks.push(min + ((max - min) * i) / (count - 1));
  }
  return ticks;
}
