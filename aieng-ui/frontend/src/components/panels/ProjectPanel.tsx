import { api } from "../../api";
import { ActionIcon } from "../common";
import type { Notice, StageItem } from "../../appTypes";
import type { ProjectRecord } from "../../types";

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
  runBusyTask,
  refreshProjects,
  setNotice,
  runWorkbenchImportFlow,
  runProjectAction,
}: ProjectPanelProps) {
  return (
    <>
      <section className="card">
        <div className="section-heading">
          <h3>Import</h3>
        </div>

        <label className="dropzone">
          <input
            className="dropzone-input"
            type="file"
            accept=".step,.stp,.aieng"
            onChange={(event) => onSelectedFileChange(event.target.files?.[0] ?? null)}
          />
          <div className="dropzone-content">
            <strong>{selectedFile ? selectedFile.name : "Drop a STEP file"}</strong>
            <span>
              {selectedFile
                ? "File selected. Click Import to load it into the workbench."
                : "Supported: .step / .stp / .aieng"}
            </span>
          </div>
        </label>

        <div className="action-row primary-actions">
          <button disabled={busy || !selectedFile} onClick={() => void runWorkbenchImportFlow()}>
            <ActionIcon name="upload" />
            Import
          </button>
        </div>
      </section>

      <section className="card">
        <div className="section-heading">
          <h3>Projects</h3>
        </div>

        <div className="inline-form" style={{ marginBottom: "12px" }}>
          <input
            value={projectName}
            onChange={(event) => onProjectNameChange(event.target.value)}
            placeholder="New project name (optional)"
          />
          <button
            disabled={busy}
            onClick={() =>
              void runBusyTask(async () => {
                const created = await api.createProject(projectName);
                await refreshProjects(created.id);
                setNotice({ tone: "success", title: "Project created", detail: `Created ${created.name}.` });
              })
            }
          >
            <ActionIcon name="plus" />
            New
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void runBusyTask(async () => {
                const sample = await api.createSampleProject();
                await refreshProjects(sample.id);
                setNotice({ tone: "success", title: "Sample loaded", detail: "SFA-5.41 sample loaded." });
              })
            }
          >
            <ActionIcon name="sample" />
            Sample
          </button>
        </div>

        <div className="project-list">
          {projects.map((project) => (
            <button
              key={project.id}
              className={project.id === selectedId ? "project-item active" : "project-item"}
              onClick={() => void refreshProjects(project.id)}
            >
              <div className="project-item-main">
                <strong>{project.name}</strong>
                <small>{project.status}</small>
              </div>
            </button>
          ))}
        </div>
      </section>

      {selectedProject ? (
        <section className="card">
          <div className="section-heading">
            <h3>Project Info</h3>
          </div>
          <div className="project-metadata" style={{ gridTemplateColumns: "1fr" }}>
            <div>
              <span>Source</span>
              <strong>{selectedProject.source_step ?? "-"}</strong>
            </div>
            <div>
              <span>Status</span>
              <strong>{selectedProject.status}</strong>
            </div>
          </div>
          <div className="action-row" style={{ marginTop: "12px" }}>
            <button
              disabled={!selectedId || busy}
              onClick={() =>
                selectedId &&
                void runProjectAction(
                  "preview",
                  () => api.convert(selectedId),
                  "Preview refreshed",
                  "Regenerated preview assets.",
                )
              }
            >
              <ActionIcon name="refresh" />
              Refresh Preview
            </button>
          </div>
        </section>
      ) : null}
    </>
  );
}
