export type MaterialCategory =
  | "Aluminum Alloys"
  | "Carbon / Alloy Steels"
  | "Stainless Steels"
  | "Titanium Alloys"
  | "Copper Alloys"
  | "Magnesium Alloys"
  | "Nickel Alloys"
  | "Cobalt Alloys"
  | "Cast Irons"
  | "Plastics / Polymers"
  | "Ceramics"
  | "Composites"
  | "Other";

export type MaterialProperties = {
  youngs_modulus_mpa: number;
  poisson_ratio: number;
  density_kg_m3: number;
  yield_strength_mpa: number;
  /** Ultimate tensile strength, when available (MPa). */
  ultimate_strength_mpa?: number | null;
  /** Thermal expansion coefficient, when available (1e-6 / K). */
  thermal_expansion_c?: number | null;
  /** Thermal conductivity, when available (W / m·K). */
  thermal_conductivity_w_mk?: number | null;
};

export type Material = {
  name: string;
  category: MaterialCategory | string;
  properties: MaterialProperties;
  description?: string | null;
};

export type MaterialComparison = {
  materials: Material[];
  differences: Array<{
    property: string;
    values: Record<string, number | null>;
    unit?: string | null;
  }>;
};

export type MaterialAssignment = {
  part_id: string;
  part_name: string;
  material_name: string;
};
