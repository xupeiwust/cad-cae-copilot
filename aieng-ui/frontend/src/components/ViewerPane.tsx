import { ModelViewer } from "./ModelViewer";
import { ActionIcon } from "./common";
import {
  fieldLabel,
  formatTime,
  getDerivedNumber,
  getManifestString,
} from "../appUtils";
import type { BrepGraphSnapshot, CadGenerationProgress, PickedFace } from "../appTypes";
import type { ProjectRecord, ProjectSummary, SolverFieldDescriptor } from "../types";

type ViewerPaneProps = {
  runtimeReady: boolean;
  runtimeProvider: string;
  runtimeDetail: string;
  selectedProject: ProjectRecord | null;
  selectedFile: File | null;
  summary: ProjectSummary | null;
  validationState: string;
  effectiveViewerFormat: string | null;
  activeFieldDescriptor: SolverFieldDescriptor | null;
  effectiveViewerUrl?: string | null;
  onOpenGlobalSettings(): void;
  onOpenSettings(): void;
  pickedFaces: PickedFace[];
  onAddPickedFace(face: PickedFace): void;
  onClearPickedFaces(): void;
  onInsertToChat(text: string): void;
  onRunPreprocess(prompt: string): Promise<void>;
  cadGenerationProgress: CadGenerationProgress | null;
  highlightedFaceIds: Set<string>;
  brepSnapshot: BrepGraphSnapshot | null;
  onClearHighlightedFaces(): void;
};

export function ViewerPane({
  runtimeReady,
  runtimeProvider,
  runtimeDetail,
  selectedProject,
  selectedFile,
  summary,
  validationState,
  effectiveViewerFormat,
  activeFieldDescriptor,
  effectiveViewerUrl,
  onOpenGlobalSettings,
  onOpenSettings,
  pickedFaces,
  onAddPickedFace,
  onClearPickedFaces,
  onInsertToChat,
  onRunPreprocess,
  cadGenerationProgress,
  highlightedFaceIds,
  brepSnapshot,
  onClearHighlightedFaces,
}: ViewerPaneProps) {
  const previewState = activeFieldDescriptor
    ? `${fieldLabel(activeFieldDescriptor.field_name)} 场可视化`
    : effectiveViewerUrl
      ? `${effectiveViewerFormat?.toUpperCase() ?? "模型"} 预览可用`
      : "等待生成预览";

  return (
    <section className="viewer-pane">
      <div className="viewer-header">
        <div className="viewer-heading">
          <h1>AIENG Workbench</h1>
          <div className="viewer-header-status" aria-label="当前模型状态">
            <span>{selectedProject?.name ?? "未选择项目"}</span>
            <span>{validationState}</span>
            <span>{previewState}</span>
          </div>
        </div>
        <div className="runtime-cluster">
          <div className="runtime-actions">
            <div className="runtime-pill">
              {runtimeReady ? `${runtimeProvider} 运行时已就绪` : "CAD 运行时需配置"}
            </div>
            <button type="button" className="ghost-button" onClick={() => onOpenGlobalSettings()} aria-label="打开全局设置">
              <ActionIcon name="global" />
              全局设置
            </button>
            <button type="button" className="ghost-button" onClick={() => onOpenSettings()}>
              <ActionIcon name="settings" />
              环境设置
            </button>
          </div>
          <small className="runtime-note">{runtimeDetail}</small>
        </div>
      </div>

      <div className="viewer-summary-strip">
        <div className="viewer-summary-main">
          <span className="viewer-toolbar-label">Current model</span>
          <strong>{selectedProject?.name ?? selectedFile?.name ?? "No project selected"}</strong>
          <small>{previewState}</small>
        </div>
        <div className="viewer-summary-status">
          <span>{validationState}</span>
          <span>{selectedProject?.updated_at ? `Updated ${formatTime(selectedProject.updated_at)}` : "No update yet"}</span>
        </div>
        <details className="viewer-technical-details">
          <summary>Model details</summary>
          <div className="viewer-technical-grid">
            <div><span>STEP</span><strong>{selectedFile?.name ?? selectedProject?.source_step ?? "None"}</strong></div>
            <div><span>Model ID</span><strong>{getManifestString(summary, "model_id")}</strong></div>
            <div><span>Features</span><strong>{getDerivedNumber(summary, "feature_graph", "count")}</strong></div>
            <div><span>Topology</span><strong>{getDerivedNumber(summary, "topology", "count")}</strong></div>
            <div><span>Package files</span><strong>{summary?.members?.length ?? 0}</strong></div>
          </div>
        </details>
      </div>

      <div className="viewer-stage-shell">
        <div className="viewer-stage-head">
          <div>
            <strong>模型预览</strong>
            <span>{effectiveViewerFormat ? `当前预览：${effectiveViewerFormat.toUpperCase()}` : "导入后将在这里显示模型预览"}</span>
          </div>
          <div className="viewer-stage-badge">
            {activeFieldDescriptor ? `${fieldLabel(activeFieldDescriptor.field_name)} 场可视化` : effectiveViewerUrl ? "预览可用" : "等待生成"}
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
          onInsertToChat={onInsertToChat}
          onRunPreprocess={onRunPreprocess}
          cadGenerationProgress={cadGenerationProgress}
          highlightedFaceIds={highlightedFaceIds}
          brepSnapshot={brepSnapshot}
          onClearHighlightedFaces={onClearHighlightedFaces}
        />
      </div>

    </section>
  );
}
