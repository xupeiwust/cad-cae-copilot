import { api } from "../../api";
import { ActionIcon, JsonDisclosure } from "../common";
import {
  getDerivedNumber,
  getManifestString,
} from "../../appUtils";
import type { Notice, StageItem, StageState } from "../../appTypes";
import type { ProjectRecord, ProjectSummary } from "../../types";

type ProjectPanelProps = {
  projectName: string;
  onProjectNameChange(value: string): void;
  busy: boolean;
  selectedFile: File | null;
  onSelectedFileChange(file: File | null): void;
  selectedId: string | null;
  selectedProject: ProjectRecord | null;
  projects: ProjectRecord[];
  stages: StageItem[];
  summary: ProjectSummary | null;
  aiSummary?: string;
  semanticSections: Array<{ title: string; body: string }>;
  integrationBody: string;
  runBusyTask(task: () => Promise<void>): Promise<void>;
  refreshProjects(nextSelectedId?: string | null): Promise<void>;
  setNotice(notice: Notice | null): void;
  runWorkbenchImportFlow(): Promise<void>;
  runProjectAction(key: string, action: () => Promise<unknown>, title: string, detail: string): Promise<void>;
};

export function ProjectPanel({
  projectName,
  onProjectNameChange,
  busy,
  selectedFile,
  onSelectedFileChange,
  selectedId,
  selectedProject,
  projects,
  stages,
  summary,
  aiSummary,
  semanticSections,
  integrationBody,
  runBusyTask,
  refreshProjects,
  setNotice,
  runWorkbenchImportFlow,
  runProjectAction,
}: ProjectPanelProps) {

  return (
    <>
      <section className="card workbench-entry-card">
              <div className="section-heading">
                <div>
                  <h2>导入模型</h2>
                  <p>从这里进入工作台主流程：选 STEP、导入、生成预览并刷新语义结果。</p>
                </div>
              </div>

              <div className="inline-form">
                <input value={projectName} onChange={(event) => onProjectNameChange(event.target.value)} placeholder="新项目名称（可选）" />
                <button
                  disabled={busy}
                  onClick={() =>
                    void runBusyTask(async () => {
                      const created = await api.createProject(projectName);
                      await refreshProjects(created.id);
                      setNotice({ tone: "success", title: "项目已创建", detail: `已创建项目 ${created.name}。` });
                    })
                  }
                >
                  <ActionIcon name="plus" />
                  新建项目
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    void runBusyTask(async () => {
                      const sample = await api.createSampleProject();
                      await refreshProjects(sample.id);
                      setNotice({ tone: "success", title: "示例已载入", detail: "已把 SFA-5.41 示例接入工作台。" });
                    })
                  }
                >
                  <ActionIcon name="sample" />
                  载入示例
                </button>
              </div>

              <label className="dropzone">
                <input className="dropzone-input" type="file" accept=".step,.stp,.aieng" onChange={(event) => onSelectedFileChange(event.target.files?.[0] ?? null)} />
                <div className="dropzone-content">
                  <strong>{selectedFile ? selectedFile.name : "选择 STEP 文件"}</strong>
                  <span>{selectedFile ? "文件已就绪，可直接导入当前工作台。" : "支持 .step / .stp，若当前未选项目，会自动创建项目后继续。"}</span>
                </div>
              </label>

              <div className="action-row primary-actions">
                <button disabled={busy || !selectedFile} onClick={() => void runWorkbenchImportFlow()}>
                  <ActionIcon name="upload" />
                  上传并导入到工作台
                </button>
                <button
                  disabled={busy || !selectedId}
                  onClick={() =>
                    selectedId &&
                    void runProjectAction("semantic", () => api.getProject(selectedId), "工作台已刷新", "已刷新当前项目的预览和语义状态。")
                  }
                >
                  <ActionIcon name="refresh" />
                  刷新工作台
                </button>
              </div>

              <div className="workflow-list">
                {stages.map((stage) => (
                  <div key={stage.key} className={`workflow-item status-${stage.state}`}>
                    <div>
                      <strong>{stage.label}</strong>
                      <p>{stage.detail}</p>
                    </div>
                    <span>{stage.state === "idle" ? "待执行" : stage.state === "active" ? "进行中" : stage.state === "done" ? "已完成" : "失败"}</span>
                  </div>
                ))}
              </div>

            </section>

            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>当前项目</h2>
                  <p>聚焦当前选中的项目与最近项目，方便在工作流之间快速切换。</p>
                </div>
              </div>

              <div className="project-list">
                {projects.map((project) => (
                  <button key={project.id} className={project.id === selectedId ? "project-item active" : "project-item"} onClick={() => void refreshProjects(project.id)}>
                    <div className="project-item-main">
                      <strong>{project.name}</strong>
                      <small>{project.id}</small>
                    </div>
                    <span>{project.status}</span>
                  </button>
                ))}
              </div>

              <div className="project-metadata">
                <div><span>STEP</span><strong>{selectedProject?.source_step ?? "-"}</strong></div>
                <div><span>.aieng</span><strong>{selectedProject?.aieng_file ?? "-"}</strong></div>
                <div><span>预览资产</span><strong>{selectedProject?.web_asset ?? "-"}</strong></div>
                <div><span>错误</span><strong>{selectedProject?.last_error ?? "无"}</strong></div>
              </div>
            </section>

            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>高级操作</h2>
                  <p>在主流程之外，按需手动重跑导入、预览和校验能力。</p>
                </div>
              </div>

              <div className="action-grid">
                <button
                  disabled={!selectedId || busy}
                  onClick={() =>
                    selectedId &&
                    void runProjectAction("import", () => api.importAieng(selectedId), "重新导入成功", "已重新生成当前项目的 .aieng 包并补全语义资源。")
                  }
                >
                  <ActionIcon name="import" />
                  重新导入 aieng
                </button>
                <button
                  disabled={!selectedId || busy}
                  onClick={() =>
                    selectedId &&
                    void runProjectAction("preview", () => api.convert(selectedId), "预览已更新", "已重跑 STEP 预览链并刷新模型资产。")
                  }
                >
                  <ActionIcon name="preview" />
                  重新生成预览
                </button>
                <button
                  disabled={!selectedId || busy}
                  onClick={() =>
                    selectedId &&
                    void runProjectAction("semantic", () => api.validate(selectedId), "校验已完成", "已执行后端校验并刷新语义信息。")
                  }
                >
                  <ActionIcon name="validate" />
                  校验语义信息
                </button>
                <button
                  disabled={!selectedId || busy}
                  onClick={() =>
                    selectedId &&
                    void runProjectAction("semantic", () => api.getProject(selectedId), "摘要已刷新", "已刷新当前项目的 manifest、topology 和 validation。")
                  }
                >
                  <ActionIcon name="refresh" />
                  刷新项目摘要
                </button>
              </div>
            </section>

            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>语义摘要</h2>
                  <p>默认先看关键语义结论，再按需展开原始结构与集成信息。</p>
                </div>
              </div>

              <div className="semantic-overview">
                <div><span>模型 ID</span><strong>{getManifestString(summary, "model_id")}</strong></div>
                <div><span>资源成员</span><strong>{summary?.members?.length ?? 0}</strong></div>
                <div><span>特征数</span><strong>{getDerivedNumber(summary, "feature_graph", "count")}</strong></div>
                <div><span>拓扑数</span><strong>{getDerivedNumber(summary, "topology", "count")}</strong></div>
              </div>

              {aiSummary ? (
                <div className="summary-note summary-primary">
                  <strong>AI 摘要</strong>
                  <p>{aiSummary}</p>
                </div>
              ) : (
                <div className="summary-note summary-muted">
                  <strong>AI 摘要</strong>
                  <p>导入并富化后，这里会展示面向人的简要语义说明。</p>
                </div>
              )}

              {summary?.summary_error ? (
                <div className="summary-note">
                  <strong>语义摘要已降级</strong>
                  <p>{summary.summary_error}</p>
                </div>
              ) : null}

              {semanticSections.map((section) => (
                <JsonDisclosure key={section.title} title={`查看 ${section.title}`} body={section.body} />
              ))}
              <JsonDisclosure title="查看集成与预览元数据" body={integrationBody} />
            </section>
    </>
  );
}
