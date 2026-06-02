import { useState } from "react";
import { ChevronsLeft, ChevronsRight, Folder, MessageSquarePlus, Plus, Trash2 } from "lucide-react";

import { api } from "../api";
import { ConfirmDialog } from "./common";
import type { Notice, StageItem } from "../appTypes";
import type { ProjectRecord } from "../types";
import type { ChatSession } from "../api";

type SessionsSidebarProps = {
  collapsed: boolean;
  onCollapsedChange(value: boolean): void;
  projectName: string;
  onProjectNameChange(value: string): void;
  busy: boolean;
  selectedFile: File | null;
  onSelectedFileChange(file: File | null): void;
  selectedId: string | null;
  selectedProject: ProjectRecord | null;
  projects: ProjectRecord[];
  chatSessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession(sessionId: string): void;
  onCreateSession(): void;
  onDeleteSession(sessionId: string): void;
  stages: StageItem[];
  runBusyTask(task: () => Promise<void>): Promise<void>;
  refreshProjects(nextSelectedId?: string | null): Promise<void>;
  setNotice(notice: Notice | null): void;
  runWorkbenchImportFlow(): Promise<void>;
};

export function SessionsSidebar({
  collapsed,
  onCollapsedChange,
  projectName,
  onProjectNameChange,
  busy,
  selectedFile,
  onSelectedFileChange,
  selectedId,
  selectedProject,
  projects,
  chatSessions,
  activeSessionId,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
  runBusyTask,
  refreshProjects,
  setNotice,
  runWorkbenchImportFlow,
}: SessionsSidebarProps) {
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  } | null>(null);

  if (collapsed) {
    return (
      <aside className="sessions-sidebar collapsed">
        <button
          type="button"
          className="sessions-icon-btn"
          onClick={() => onCollapsedChange(false)}
          title="Expand sidebar"
        >
          <ChevronsRight className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="sessions-icon-btn"
          disabled={busy}
          onClick={() =>
            void runBusyTask(async () => {
              const created = await api.createProject(projectName);
              await refreshProjects(created.id);
              setNotice({ tone: "success", title: "Project created", detail: `Created ${created.name}.` });
            })
          }
          title="New project"
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="sessions-icon-btn"
          disabled={!selectedId}
          onClick={onCreateSession}
          title="New session"
        >
          <MessageSquarePlus className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="sessions-sidebar">
      <div className="sessions-sidebar-header">
        <div>
          <strong>Projects</strong>
          <span>{selectedProject?.name ?? "No project selected"}</span>
        </div>
        <button
          type="button"
          className="sessions-icon-btn"
          onClick={() => onCollapsedChange(true)}
          title="Collapse sidebar"
        >
          <ChevronsLeft className="h-4 w-4" />
        </button>
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
          <Plus className="h-4 w-4" />
          <span>New project</span>
        </button>
      </div>

      <div className="sessions-list">
        {projects.map((project) => (
          <div key={project.id} className="session-item-wrap">
            <button
              className={project.id === selectedId ? "session-item active" : "session-item"}
              onClick={() => void refreshProjects(project.id)}
            >
              <span className="session-item-row">
                <Folder className="h-4 w-4" />
                <span className="session-item-name">{project.name}</span>
              </span>
              <span className="session-item-status">{project.status}</span>
            </button>
            <button
              type="button"
              className="session-item-delete"
              title="Delete project"
              aria-label={`Delete project ${project.name}`}
              onClick={(event) => {
                event.stopPropagation();
                setConfirmDialog({
                  open: true,
                  title: `Delete project "${project.name}"?`,
                  message: "This removes its geometry and chat history and cannot be undone.",
                  onConfirm: () => {
                    setConfirmDialog(null);
                    void runBusyTask(async () => {
                      await api.deleteProject(project.id);
                      await refreshProjects(project.id === selectedId ? null : selectedId);
                      setNotice({ tone: "success", title: "Project deleted", detail: `Deleted ${project.name}.` });
                    });
                  },
                });
              }}
            >
              <Trash2 style={{ width: 12, height: 12 }} />
            </button>
          </div>
        ))}
      </div>

      <div className="sessions-thread-panel">
        <div className="sessions-thread-header">
          <strong>Sessions</strong>
          <button
            type="button"
            className="sessions-mini-btn"
            disabled={!selectedId}
            onClick={onCreateSession}
            title="New session"
          >
            <MessageSquarePlus className="h-4 w-4" />
          </button>
        </div>
        <div className="sessions-thread-list">
          {chatSessions.map((session) => (
            <div key={session.id} className="thread-item-wrap">
              <button
                type="button"
                className={session.id === activeSessionId ? "thread-item active" : "thread-item"}
                onClick={() => onSelectSession(session.id)}
              >
                <span className="thread-title">{session.title}</span>
                <span className={`thread-status status-${session.status}`}>{session.status}</span>
              </button>
              <button
                type="button"
                className="thread-item-delete"
                title="Delete session"
                aria-label={`Delete session ${session.title}`}
                onClick={(event) => {
                  event.stopPropagation();
                  setConfirmDialog({
                    open: true,
                    title: `Delete session "${session.title}"?`,
                    message: "This cannot be undone.",
                    onConfirm: () => {
                      setConfirmDialog(null);
                      void runBusyTask(async () => {
                        await onDeleteSession(session.id);
                        setNotice({ tone: "success", title: "Session deleted", detail: `Deleted ${session.title}.` });
                      });
                    },
                  });
                }}
              >
                <Trash2 style={{ width: 12, height: 12 }} />
              </button>
            </div>
          ))}
          {!chatSessions.length ? (
            <span className="thread-empty">No sessions yet</span>
          ) : null}
        </div>
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

      {confirmDialog ? (
        <ConfirmDialog
          open={confirmDialog.open}
          title={confirmDialog.title}
          message={confirmDialog.message}
          onConfirm={confirmDialog.onConfirm}
          onCancel={() => setConfirmDialog(null)}
        />
      ) : null}
    </aside>
  );
}
