export type EngineeringContextSource = {
  projectId?: string | null;
  projectName?: string | null;
  selectedFaces: Array<{ pointer: string; label: string; surface_type?: string | null }>;
  highlightedFaceCount: number;
  viewerAsset?: { url?: string | null; format?: string | null } | null;
  shapeIrObjectCount: number;
  shapeIrVerificationStatus?: string | null;
  cae: {
    hasContext: boolean;
    hasResults: boolean;
    availableFields: string[];
    activeField?: string | null;
  };
};

export function engineeringContextSourceLines(context: EngineeringContextSource): string[] {
  const lines = [
    context.projectName
      ? `Project: ${context.projectName}`
      : context.projectId
        ? `Project: ${context.projectId}`
        : "No active project",
    context.viewerAsset?.url
      ? `Viewer: ${context.viewerAsset.format || "asset"} ${context.viewerAsset.url}`
      : "Viewer: no active asset",
    context.shapeIrObjectCount
      ? `Shape IR: ${context.shapeIrObjectCount} object${context.shapeIrObjectCount === 1 ? "" : "s"}${context.shapeIrVerificationStatus ? ` (${context.shapeIrVerificationStatus})` : ""}`
      : "Shape IR: no objects",
    context.cae.hasResults
      ? `CAE: results available${context.cae.activeField ? ` (${context.cae.activeField})` : ""}`
      : context.cae.hasContext
        ? "CAE: setup context available"
        : "CAE: not ready",
  ];

  lines.push(
    context.selectedFaces.length
      ? `Selected faces: ${context.selectedFaces.slice(0, 3).map((face) => face.pointer).join(", ")}${context.selectedFaces.length > 3 ? ` +${context.selectedFaces.length - 3}` : ""}`
      : "Selected faces: none",
  );

  if (context.highlightedFaceCount) {
    lines.push(`Highlighted faces: ${context.highlightedFaceCount}`);
  }

  if (context.cae.availableFields.length) {
    lines.push(`CAE fields: ${context.cae.availableFields.slice(0, 4).join(", ")}${context.cae.availableFields.length > 4 ? "..." : ""}`);
  }

  return lines;
}
