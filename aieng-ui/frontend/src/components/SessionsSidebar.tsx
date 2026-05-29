import { api } from "../api";
import type { Notice, StageItem } from "../appTypes";
import type { ProjectRecord } from "../types";

type SessionsSidebarProps = {
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
};

export function SessionsSidebar({
  projectName,
  onProjectNameChange,
  busy,
  selectedFile,
  onSelectedFileChange,
  selectedId,
  selectedProject,
  projects,
  runBusyTask,
  refreshProjects,
  setNotice,
  runWorkbenchImportFlow,
}: SessionsSidebarProps) {
  return (
    <aside className="sessions-sidebar">
      <div className="sessions-sidebar-header">
        <strong>Projects</strong>
      </div>

      <div className="sessions-sidebar-actions">
        <button
          className="sessions-new-btn"
          disabled={busy}
          onClick={() =>
            void runBusyTask(async () => {
              const created = await api.createProject(projectName);
              await refreshProjects(created.id);
              setNotice({ tone: "success", title: "Project created", detail: `Created ${created.name}.` });
            })
          }
        >
          + New project
        </button>
      </div>

      <div className="sessions-list">
        {projects.map((project) => (
          <button
            key={project.id}
            className={project.id === selectedId ? "session-item active" : "session-item"}
            onClick={() => void refreshProjects(project.id)}
          >
            <span className="session-item-name">{project.name}</span>
            <span className="session-item-status">{project.status}</span>
          </button>
        ))}
      </div>

      <div className="sessions-import">
        <label className="sessions-dropzone"
        >
          <input
            type="file"
            accept=".step,.stp,.aieng"
            onChange={(event) => onSelectedFileChange(event.target.files?.[0] ?? null)}
          />
          <span>{selectedFile ? selectedFile.name : "Drop or click to import STEP"}</span>
        </label>
        <button
          className="sessions-import-btn"
          disabled={busy || !selectedFile}
          onClick={() => void runWorkbenchImportFlow()}
        >
          Import
        </button>
      </div>
    </aside>
  );
}
