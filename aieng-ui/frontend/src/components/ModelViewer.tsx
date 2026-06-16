import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { assemblyAlertCounts } from "../app/geometryReport";
import { useGeometryReport } from "../app/useGeometryReport";
import { useFieldRegions } from "../app/useFieldRegions";
import { useMeshPreview } from "../app/useMeshPreview";
import type { BrepGraphSnapshot, CadGenerationProgress, PickedFace, ViewerLoadState } from "../appTypes";
import { resolveAssetFormat } from "../appUtils";
import type { CaeSetupOverlayResponse, FieldOverlayConfig, FieldProbe, FieldRegionCluster, SolverFieldDescriptor } from "../types";
import { modelToDisplayVec } from "./viewer/coordinateFrames";
import { ViewerOverlays } from "./viewer/ViewerOverlays";
import { DeformationControls } from "./viewer/DeformationControls";
import {
  useThreeScene,
  useAssetLoader,
  useFacePicker,
  useFaceIdentityMaps,
  useHighlightOverlay,
  useAssemblyCheckOverlay,
  useFieldMarkerOverlay,
  useFieldProbe,
  useFieldColorOverlay,
  useCaeSetupOverlay,
  useFieldRegionOverlay,
  useMeshPreviewOverlay,
  useDeformedShape,
  useDeformationOrchestration,
} from "./viewer/hooks";

export function ModelViewer({
  assetUrl,
  assetFormat,
  fieldDescriptor,
  fieldOverlayConfig,
  caeSetupOverlay,
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
  fieldOverlayConfig?: FieldOverlayConfig | null;
  caeSetupOverlay?: CaeSetupOverlayResponse | null;
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
  const [fieldProbe, setFieldProbe] = useState<FieldProbe | null>(null);
  const [showCaeSetup, setShowCaeSetup] = useState(true);
  const [showFieldRegions, setShowFieldRegions] = useState(true);
  const [selectedCluster, setSelectedCluster] = useState<FieldRegionCluster | null>(null);

  // Clear the probe readout when the active field or project changes.
  useEffect(() => {
    setFieldProbe(null);
  }, [fieldDescriptor?.project_id, fieldDescriptor?.field_name]);

  const caeSetupAvailable = Boolean(
    caeSetupOverlay &&
      ((caeSetupOverlay.loads && caeSetupOverlay.loads.length > 0) ||
        (caeSetupOverlay.constraints && caeSetupOverlay.constraints.length > 0)),
  );
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
  const { fieldRegions } = useFieldRegions({
    selectedId: projectId ?? null,
    geometryVersion: assetUrl ?? null,
  });
  const { meshPreview } = useMeshPreview({
    selectedId: projectId ?? null,
    geometryVersion: assetUrl ?? null,
  });
  const assemblyAlerts = assemblyAlertCounts(geometryReport);
  const resolvedAssetFormat = resolveAssetFormat(assetUrl, assetFormat);
  const fieldRegionsAvailable = Boolean(fieldRegions && fieldRegions.clusters.length > 0);
  const meshPreviewAvailable = Boolean(meshPreview && meshPreview.element_count && meshPreview.element_count > 0);

  // 1. Three.js scene lifecycle
  const {
    sceneRef,
    cameraRef,
    controlsRef,
    highlightGroupRef,
    assemblyGroupRef,
    markerGroupRef,
    caeSetupGroupRef,
    fieldRegionGroupRef,
    meshPreviewGroupRef,
    deformedGroupRef,
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
    fieldOverlayConfig,
  );

  // 8. Re-apply field colormap when legend controls change.
  useFieldColorOverlay(objectRef, fieldDescriptor, fieldOverlayConfig, objectReadyKey);

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

  // 9. Click-to-query field probe
  useFieldProbe(
    hostRef,
    objectRef,
    cameraRef,
    primitiveFaceRef,
    displayTransformRef,
    fieldDescriptor,
    setFieldProbe,
  );

  // 10. CAE setup overlay (loads, constraints, bound faces)
  useCaeSetupOverlay(
    caeSetupGroupRef,
    showCaeSetup && caeSetupAvailable,
    caeSetupOverlay ?? null,
    faceMeshesRef,
    objectRef,
    brepSnapshot,
    displayTransformRef,
    objectReadyKey,
  );

  // 11. FE mesh preview overlay
  useMeshPreviewOverlay(
    meshPreviewGroupRef,
    showMeshPreview && meshPreviewAvailable,
    meshPreview,
    displayTransformRef,
    objectReadyKey,
  );

  // 11b. Deformed-shape overlay state (availability, toggle, auto scale).
  const {
    deformationAvailable,
    showDeformedShape,
    setShowDeformedShape,
    deformationScale,
    setDeformationScale,
  } = useDeformationOrchestration(fieldDescriptor, objectRef, objectReadyKey);

  // 11c. Displacement-warped deformed shape overlay
  useDeformedShape(
    objectRef,
    deformedGroupRef,
    fieldDescriptor,
    showDeformedShape,
    deformationScale,
    objectReadyKey,
    fieldOverlayConfig,
  );

  // 12. Field-region cluster markers
  useFieldRegionOverlay(
    fieldRegionGroupRef,
    showFieldRegions && fieldRegionsAvailable,
    fieldRegions,
    objectRef,
    displayTransformRef,
    objectReadyKey,
  );

  // 13. Cluster marker picking + framing
  useEffect(() => {
    const host = hostRef.current;
    const camera = cameraRef.current;
    const group = fieldRegionGroupRef.current;
    if (!host || !camera || !group) return;

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onClick = (event: MouseEvent) => {
      if (!showFieldRegions || !fieldRegions) return;
      const rect = host.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(group.children, true);
      if (intersects.length === 0) return;
      let obj: THREE.Object3D | null = intersects[0].object;
      while (obj && obj.userData?.type !== "field-region-cluster" && obj.parent) {
        obj = obj.parent;
      }
      const cluster = obj?.userData?.cluster as FieldRegionCluster | undefined;
      if (cluster) setSelectedCluster(cluster);
    };

    host.addEventListener("click", onClick);
    return () => host.removeEventListener("click", onClick);
  }, [showFieldRegions, fieldRegions, fieldRegionGroupRef]);

  useEffect(() => {
    if (!selectedCluster || !controlsRef.current || !cameraRef.current) return;
    const center = modelToDisplayVec(
      selectedCluster.location.x,
      selectedCluster.location.y,
      selectedCluster.location.z,
      displayTransformRef.current,
    );
    const controls = controlsRef.current;
    const offset = cameraRef.current.position.clone().sub(controls.target);
    controls.target.copy(center);
    cameraRef.current.position.copy(center.clone().add(offset));
    controls.update();
  }, [selectedCluster, controlsRef, cameraRef, displayTransformRef]);

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
      {caeSetupAvailable && (
        <button
          type="button"
          className="viewer-cae-setup-toggle"
          onClick={() => setShowCaeSetup((value) => !value)}
          title="Show loads, constraints, and bound faces from the CAE setup"
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            zIndex: 5,
            padding: "4px 10px",
            fontSize: 12,
            borderRadius: 6,
            border: "1px solid #3a3a3a",
            background: showCaeSetup ? "#1e3a8a" : "rgba(20,20,20,0.78)",
            color: "#f5f5f5",
            cursor: "pointer",
          }}
        >
          {showCaeSetup ? "Hide" : "Show"} CAE setup
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
            top: 44,
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
            top: 80,
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
      {fieldRegionsAvailable && (
        <button
          type="button"
          className="viewer-field-region-toggle"
          onClick={() => setShowFieldRegions((value) => !value)}
          title="Show high-stress / high-displacement field-region clusters in 3D"
          style={{
            position: "absolute",
            bottom: 8,
            right: 8,
            zIndex: 5,
            padding: "4px 10px",
            fontSize: 12,
            borderRadius: 6,
            border: "1px solid #3a3a3a",
            background: showFieldRegions ? "#7f1d1d" : "rgba(20,20,20,0.78)",
            color: "#f5f5f5",
            cursor: "pointer",
          }}
        >
          {showFieldRegions ? "Hide" : "Show"} field regions
        </button>
      )}
      {selectedCluster && (
        <div
          className="viewer-cluster-chip"
          style={{
            position: "absolute",
            top: 8,
            left: "50%",
            transform: "translateX(-50%)",
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
            <strong>{fieldRegions?.metric ?? "Cluster"}</strong>: {selectedCluster.magnitude.value.toPrecision(4)}{" "}
            {selectedCluster.magnitude.unit}
          </span>
          {selectedCluster.feature_ref ? (
            <code style={{ background: "rgba(255,255,255,0.1)", padding: "2px 4px", borderRadius: 4 }}>
              @face:{selectedCluster.feature_ref}
            </code>
          ) : null}
          <button
            type="button"
            onClick={() => setSelectedCluster(null)}
            style={{
              background: "transparent",
              border: "none",
              color: "#f5f5f5",
              cursor: "pointer",
              fontSize: 12,
            }}
            aria-label="Clear selected cluster"
          >
            ×
          </button>
        </div>
      )}
      {deformationAvailable && (
        <DeformationControls
          descriptor={fieldDescriptor}
          enabled={showDeformedShape}
          onEnabledChange={setShowDeformedShape}
          scale={deformationScale}
          onScaleChange={setDeformationScale}
        />
      )}
      <ViewerOverlays
        viewerState={viewerState}
        tooltipFace={tooltipFace}
        fieldProbe={fieldProbe}
        onClearFieldProbe={() => setFieldProbe(null)}
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
