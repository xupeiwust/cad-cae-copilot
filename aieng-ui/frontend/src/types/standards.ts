export type StandardPartCategory = {
  id: string;
  displayName: string;
  description?: string | null;
  partTypes: StandardPartType[];
};

export type StandardPartType = {
  name: string;
  displayName: string;
  category: string;
  description?: string | null;
  standardReference?: string | null;
  editableParameters: string[];
};

export type StandardPartPreset = {
  name: string;
  displayName: string;
  parameters: Record<string, number>;
};

export type StandardPartSpec = {
  partType: string;
  category: string;
  description?: string | null;
  standardReference?: string | null;
  presets: StandardPartPreset[];
  defaultParameters: Record<string, number>;
  parameterUnits: Record<string, string>;
  parameterDescriptions?: Record<string, string> | null;
};

export type InsertResult = {
  ok: boolean;
  part_id?: string | null;
  message?: string | null;
  warnings?: string[];
};
