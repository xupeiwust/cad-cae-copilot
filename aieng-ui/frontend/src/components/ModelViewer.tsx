import { useRef, useState } from "react";
import * as THREE from "three";

import { assemblyAlertCounts } from "../app/geometryReport";
import { useGeometryReport } from "../app/useGeometryReport";
import { useMeshPreview } from "../app/useMeshPreview";
import type { BrepGraphSnapshot, CadGenerationProgress, PickedFace, ViewerLoadState } from "../appTypes";
import { resolveAssetFormat } from "../appUtils";
import type { SolverFieldDescriptor } from "../types";
import { ViewerOverlays } from "./viewer/ViewerOverlays";
import {
  useThreeScene,
  useAssetLoader,
  useFacePicker,
  useFaceIdentityMaps,
  useHighlightOverlay,
  useAssemblyCheckOverlay,
  useFieldMarkerOverlay,
  useMeshPreviewOverlay,
} from "./viewer/hooks";

export function ModelViewer({
  assetUrl,
  assetFormat,
  fieldDescriptor,
  projectId,
  pickedFaces,
  onAddPickedFace,
  onClearPickedFaces,
  onCopyPointer,
  cadGenerationProgress,
  highlightedFaceIds,
  brepSnapshot,
  onClearHighlightedFaces,
}: {
  assetUrl?: string | null;
  assetFormat?: string | null;
  fieldDescriptor?: SolverFieldDescriptor | null;
  projectId?: string | null;
  pickedFaces: PickedFace[];
  onAddPickedFace(face: PickedFace): void;
  onClearPickedFaces(): void;
  onCopyPointer(text: string): void;
  cadGenerationProgress: CadGenerationProgress | null;
  highlightedFaceIds: Set<string>;
  brepSnapshot: BrepGraphSnapshot | null;
  onClearHighlightedFaces(): void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const objectRef = useRef<THREE.Object3D | null>(null);
  const [objectReadyKey, setObjectReadyKey] = useState(0);
  const [viewerState, setViewerState] = useState<{ status: ViewerLoadState; detail: string }>({
    status: "idle",
    detail: "Waiting for preview asset",
  });
  const [tooltipFace, setTooltipFace] = useState<PickedFace | null>(null);
  const [showAssemblyCheck, setShowAssemblyCheck] = useState(false);
  const [showFieldMarkers, setShowFieldMarkers] = useState(true);
  const [showMeshPreview, setShowMeshPreview] = useState(false);

  // Peak/min markers only make sense for a real solver field with per-node data.
  const fieldMarkersAvailable = Boolean(
    fieldDescriptor &&
      fieldDescriptor.source === "frd" &&
      Array.isArray(fieldDescriptor.values) &&
      fieldDescriptor.values.length > 0,
  );

  const { geometryReport } = useGeometryReport({
    selectedId: projectId ?? null,
    geometryVersion: assetUrl ?? null,
  });
  const { meshPreview } = useMeshPreview({
    selectedId: projectId ?? null,
    geometryVersion: assetUrl ?? null,
  });
  const assemblyAlerts = assemblyAlertCounts(geometryReport);
  const resolvedAssetFormat = resolveAssetFormat(assetUrl, assetFormat);
  const meshPreviewAvailable = Boolean(meshPreview && meshPreview.element_count && meshPreview.element_count > 0);

  // 1. Three.js scene lifecycle
  const {
    sceneRef,
    cameraRef,
    controlsRef,
    highlightGroupRef,
    assemblyGroupRef,
    markerGroupRef,
    meshPreviewGroupRef,
  } = useThreeScene(hostRef);

  // 2. Asset loading
  useAssetLoader(
    sceneRef,
    cameraRef,
    controlsRef,
    objectRef,
    assetUrl,
    assetFormat,
    fieldDescriptor,
    () => setObjectReadyKey((k) => k + 1),
    setViewerState,
  );

  // 3. Face identity maps (viewer↔model transform + primitive↔face)
  const { displayTransformRef, primitiveFaceRef, faceMeshesRef } = useFaceIdentityMaps(
    objectRef,
    brepSnapshot,
    resolvedAssetFormat,
    objectReadyKey,
  );

  // 4. Face picking (raycast + backend fallback)
  useFacePicker(
    hostRef,
    objectRef,
    cameraRef,
    primitiveFaceRef,
    displayTransformRef,
    projectId,
    onAddPickedFace,
    setTooltipFace,
  );

  // 5. Highlight overlay
  useHighlightOverlay(
    highlightGroupRef,
    faceMeshesRef,
    highlightedFaceIds,
    brepSnapshot,
    objectRef,
    displayTransformRef,
    objectReadyKey,
  );

  // 6. Assembly-check overlay
  useAssemblyCheckOverlay(
    assemblyGroupRef,
    showAssemblyCheck,
    geometryReport,
    displayTransformRef,
    objectReadyKey,
  );

  // 7. Field peak/min markers
  useFieldMarkerOverlay(
    markerGroupRef,
    showFieldMarkers && fieldMarkersAvailable,
    fieldDescriptor,
    displayTransformRef,
    objectReadyKey,
  );

  // 8. FE mesh preview overlay
  useMeshPreviewOverlay(
    meshPreviewGroupRef,
    showMeshPreview && meshPreviewAvailable,
    meshPreview,
    displayTransformRef,
    objectReadyKey,
  );

  return (
    <div className="viewer-canvas-shell">
      <div className="viewer-canvas" ref={hostRef} />
      {assemblyAlerts.total > 0 && (
        <button
          type="button"
          className="viewer-assembly-toggle"
          onClick={() => setShowAssemblyCheck((value) => !value)}
          title="Highlight floating parts and broken left/right symmetry detected in the geometry"
          style={{
            position: "absolute",
            top: 8,
            left: 8,
            zIndex: 5,
            padding: "4px 10px",
            fontSize: 12,
            borderRadius: 6,
            border: "1px solid #3a3a3a",
            background: showAssemblyCheck ? "#7f1d1d" : "rgba(20,20,20,0.78)",
            color: "#f5f5f5",
            cursor: "pointer",
          }}
        >
          {showAssemblyCheck ? "Hide" : "Show"} assembly check ({assemblyAlerts.total})
        </button>
      )}
      {fieldMarkersAvailable && (
        <button
          type="button"
          className="viewer-field-marker-toggle"
          onClick={() => setShowFieldMarkers((value) => !value)}
          title="Mark the peak (red) and minimum (blue) of the active result field in 3D"
          style={{
            position: "absolute",
            bottom: 8,
            left: 8,
            zIndex: 5,
            padding: "4px 10px",
            fontSize: 12,
            borderRadius: 6,
            border: "1px solid #3a3a3a",
            background: showFieldMarkers ? "#7f1d1d" : "rgba(20,20,20,0.78)",
            color: "#f5f5f5",
            cursor: "pointer",
          }}
        >
          {showFieldMarkers ? "Hide" : "Show"} peak/min
        </button>
      )}
      {meshPreviewAvailable && (
        <button
          type="button"
          className="viewer-mesh-preview-toggle"
          onClick={() => setShowMeshPreview((value) => !value)}
          title="Overlay the FE mesh surface wireframe and element count"
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            zIndex: 5,
            padding: "4px 10px",
            fontSize: 12,
            borderRadius: 6,
            border: "1px solid #3a3a3a",
            background: showMeshPreview ? "#0e7490" : "rgba(20,20,20,0.78)",
            color: "#f5f5f5",
            cursor: "pointer",
          }}
        >
          {showMeshPreview ? "Hide" : "Show"} mesh
        </button>
      )}
      {showMeshPreview && meshPreview && (
        <div
          className="viewer-mesh-preview-chip"
          style={{
            position: "absolute",
            top: 44,
            right: 8,
            zIndex: 5,
            padding: "4px 10px",
            fontSize: 12,
            borderRadius: 6,
            border: "1px solid #3a3a3a",
            background: "rgba(20,20,20,0.85)",
            color: "#f5f5f5",
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <span>
            <strong>{meshPreview.element_count?.toLocaleString()}</strong> elements
            {meshPreview.target_size_mm !== null && meshPreview.target_size_mm !== undefined
              ? ` · ${meshPreview.target_size_mm} mm`
              : null}
          </span>
          {meshPreview.quality?.coarse_flag ? (
            <span style={{ color: "#facc15" }} title={meshPreview.quality.note ?? undefined}>
              (coarse)
            </span>
          ) : null}
        </div>
      )}
      <ViewerOverlays
        viewerState={viewerState}
        tooltipFace={tooltipFace}
        pickedFaces={pickedFaces}
        highlightedFaceIds={highlightedFaceIds}
        cadGenerationProgress={cadGenerationProgress}
        onCopyPointer={onCopyPointer}
        onClearPickedFaces={onClearPickedFaces}
        onClearHighlightedFaces={onClearHighlightedFaces}
      />
    </div>
  );
}
