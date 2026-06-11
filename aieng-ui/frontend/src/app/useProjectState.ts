import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { Notice } from "../appTypes";
import type { ProjectRecord, ProjectSummary, RuntimeConfigSnapshot } from "../types";
import { buildFallbackSummary } from "./projectSummary";

export function useProjectState() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [projectName, setProjectName] = useState("STEP workbench project");
  const [busy, setBusy] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedId) ?? null,
    [projects, selectedId],
  );

  const refreshProjects = useCallback(async (
    nextSelectedId?: string | null,
    runtimeSnapshot: RuntimeConfigSnapshot | null = null,
  ) => {
    const list = await api.listProjects();
    setProjects(list);
    const candidate = nextSelectedId ?? (selectedId && list.some((item) => item.id === selectedId) ? selectedId : null) ?? list[0]?.id ?? null;
    setSelectedId(candidate);
    if (candidate) {
      try {
        setSummary(await api.getProject(candidate));
      } catch {
        const project = list.find((item) => item.id === candidate) ?? null;
        setSummary(project ? buildFallbackSummary(project, runtimeSnapshot) : null);
      }
    } else {
      setSummary(null);
    }
  }, [selectedId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  return {
    projects,
    setProjects,
    selectedId,
    setSelectedId,
    summary,
    setSummary,
    projectName,
    setProjectName,
    busy,
    setBusy,
    selectedFile,
    setSelectedFile,
    notice,
    setNotice,
    selectedProject,
    refreshProjects,
  };
}
