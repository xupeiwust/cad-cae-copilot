import { engineeringContextSourceLines, type EngineeringContextSource } from "./engineeringContextSource";

function assertDeepEqual(actual: unknown, expected: unknown) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`Expected ${expectedJson}, got ${actualJson}`);
  }
}

const context: EngineeringContextSource = {
  projectId: "proj-123",
  projectName: "CNC bracket",
  selectedFaces: [
    { pointer: "@face:f_top", label: "top face" },
    { pointer: "@face:f_load", label: "load face" },
    { pointer: "@face:f_fixed", label: "fixed face" },
    { pointer: "@face:f_side", label: "side face" },
  ],
  highlightedFaceCount: 5,
  viewerAsset: {
    url: "/api/projects/proj-123/artifacts/geometry.glb?v=2",
    format: "glb",
  },
  shapeIrObjectCount: 2,
  shapeIrVerificationStatus: "verified",
  cae: {
    hasContext: true,
    hasResults: true,
    availableFields: ["stress", "displacement", "strain", "temperature", "factor_of_safety"],
    activeField: "stress",
  },
};

assertDeepEqual(engineeringContextSourceLines(context), [
  "Project: CNC bracket",
  "Viewer: glb /api/projects/proj-123/artifacts/geometry.glb?v=2",
  "Shape IR: 2 objects (verified)",
  "CAE: results available (stress)",
  "Selected faces: @face:f_top, @face:f_load, @face:f_fixed +1",
  "Highlighted faces: 5",
  "CAE fields: stress, displacement, strain, temperature...",
]);

assertDeepEqual(engineeringContextSourceLines({
  selectedFaces: [],
  highlightedFaceCount: 0,
  viewerAsset: null,
  shapeIrObjectCount: 0,
  cae: {
    hasContext: true,
    hasResults: false,
    availableFields: [],
  },
}), [
  "No active project",
  "Viewer: no active asset",
  "Shape IR: no objects",
  "CAE: setup context available",
  "Selected faces: none",
]);
