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

      <div className="viewer-toolbar">
        <div className="viewer-toolbar-block">
          <span className="viewer-toolbar-label">当前 STEP</span>
          <strong>{selectedFile?.name ?? selectedProject?.source_step ?? "未选择文件"}</strong>
        </div>
        <div className="viewer-toolbar-block">
          <span className="viewer-toolbar-label">模型 ID</span>
          <strong>{getManifestString(summary, "model_id")}</strong>
        </div>
        <div className="viewer-toolbar-block">
          <span className="viewer-toolbar-label">特征数</span>
          <strong>{getDerivedNumber(summary, "feature_graph", "count")}</strong>
        </div>
        <div className="viewer-toolbar-block">
          <span className="viewer-toolbar-label">拓扑实体</span>
          <strong>{getDerivedNumber(summary, "topology", "count")}</strong>
        </div>
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

      <div className="viewer-insights">
        <div className="insight-card"><span>特征数</span><strong>{getDerivedNumber(summary, "feature_graph", "count")}</strong></div>
        <div className="insight-card"><span>拓扑实体</span><strong>{getDerivedNumber(summary, "topology", "count")}</strong></div>
        <div className="insight-card"><span>资源成员</span><strong>{summary?.members?.length ?? 0}</strong></div>
        <div className="insight-card"><span>最近更新</span><strong>{formatTime(selectedProject?.updated_at)}</strong></div>
      </div>
    </section>
  );
}
