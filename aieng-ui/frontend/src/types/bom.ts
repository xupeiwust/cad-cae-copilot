export type BOMItem = {
  id: string;
  name: string;
  quantity: number;
  material?: string | null;
  isStandardPart: boolean;
  standardPartType?: string | null;
  standardPartPreset?: string | null;
  parameters?: Record<string, number> | null;
};

export type BOMData = {
  projectId: string;
  items: BOMItem[];
  totalCount: number;
  standardPartCount: number;
  customPartCount: number;
  generatedAt: string;
};
