import { ModelViewer } from "./ModelViewer";
import { fieldLabel } from "../appUtils";
import type { BrepGraphSnapshot, CadGenerationProgress, PickedFace } from "../appTypes";
import type { ProjectRecord, SolverFieldDescriptor } from "../types";

type ViewerPaneProps = {
  runtimeReady: boolean;
  runtimeProvider: string;
  selectedProject: ProjectRecord | null;
  effectiveViewerFormat: string | null;
  activeFieldDescriptor: SolverFieldDescriptor | null;
  effectiveViewerUrl?: string | null;
  pickedFaces: PickedFace[];
  onAddPickedFace(face: PickedFace): void;
  onClearPickedFaces(): void;
  onCopyPointer(text: string): void;
  cadGenerationProgress: CadGenerationProgress | null;
  highlightedFaceIds: Set<string>;
  brepSnapshot: BrepGraphSnapshot | null;
  onClearHighlightedFaces(): void;
};

export function ViewerPane({
  runtimeReady,
  runtimeProvider,
  selectedProject,
  effectiveViewerFormat,
  activeFieldDescriptor,
  effectiveViewerUrl,
  pickedFaces,
  onAddPickedFace,
  onClearPickedFaces,
  onCopyPointer,
  cadGenerationProgress,
  highlightedFaceIds,
  brepSnapshot,
  onClearHighlightedFaces,
}: ViewerPaneProps) {
  return (
    <section className="viewer-pane">
      <div className="viewer-header">
        <div className="viewer-heading">
          <h1>Workbench</h1>
          <div className="viewer-header-status" aria-label="Model status">
            <span>{selectedProject?.name ?? "No project"}</span>
            {runtimeReady ? (
              <span className="status-ready">{runtimeProvider} ready</span>
            ) : (
              <span>Waiting for model</span>
            )}
          </div>
        </div>
      </div>

      <div className="viewer-stage-shell">
        <div className="viewer-stage-head">
          <div>
            <strong>Model Preview</strong>
            <span>{effectiveViewerFormat ? `${effectiveViewerFormat.toUpperCase()} preview` : "Import a model to preview it here"}</span>
          </div>
          <div className="viewer-stage-badge">
            {activeFieldDescriptor ? `${fieldLabel(activeFieldDescriptor.field_name)} field` : effectiveViewerUrl ? "Ready" : "Waiting"}
          </div>
        </div>
        <ModelViewer
          assetUrl={effectiveViewerUrl}
          assetFormat={effectiveViewerFormat}
          fieldDescriptor={activeFieldDescriptor}
          projectId={selectedProject?.id ?? null}
          pickedFaces={pickedFaces}
          onAddPickedFace={onAddPickedFace}
          onClearPickedFaces={onClearPickedFaces}
          onCopyPointer={onCopyPointer}
          cadGenerationProgress={cadGenerationProgress}
          highlightedFaceIds={highlightedFaceIds}
          brepSnapshot={brepSnapshot}
          onClearHighlightedFaces={onClearHighlightedFaces}
        />
      </div>

    </section>
  );
}
