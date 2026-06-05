import { EventSource } from "eventsource";
import * as vscode from "vscode";

import { facesFromBackendBrep } from "./packageReader";
import type { PreviewFormat, PreviewPayload } from "./protocol";

type Project = {
  id: string;
  name?: string;
  status?: string;
  updated_at?: string;
  named_parts?: string[];
};

function backendUrl(): string {
  return vscode.workspace.getConfiguration("aieng").get<string>("backendUrl", "http://127.0.0.1:8000").replace(/\/+$/, "");
}

async function responseError(response: Response): Promise<Error> {
  const text = await response.text().catch(() => "");
  return new Error(text || `${response.status} ${response.statusText}`);
}

async function fetchJson(path: string): Promise<unknown> {
  const response = await fetch(`${backendUrl()}${path}`);
  if (!response.ok) throw await responseError(response);
  return response.json();
}

async function fetchBytes(path: string): Promise<{ bytes: Buffer; format: PreviewFormat }> {
  const response = await fetch(`${backendUrl()}${path}`);
  if (!response.ok) throw await responseError(response);
  const type = response.headers.get("content-type") ?? "";
  return {
    bytes: Buffer.from(await response.arrayBuffer()),
    format: type.includes("gltf") ? "glb" : "stl",
  };
}

export async function listProjects(): Promise<Project[]> {
  const raw = await fetchJson("/api/projects");
  if (Array.isArray(raw)) return raw as Project[];
  if (raw && typeof raw === "object" && Array.isArray((raw as { projects?: unknown }).projects)) {
    return (raw as { projects: Project[] }).projects;
  }
  return [];
}

export async function chooseLiveProject(): Promise<Project | undefined> {
  const configured = vscode.workspace.getConfiguration("aieng").get<string>("liveProjectId", "").trim();
  const projects = await listProjects();
  if (configured) return projects.find((item) => item.id === configured) ?? { id: configured, name: configured };
  const selected = await vscode.window.showQuickPick(
    projects.map((project) => ({
      label: project.name || project.id,
      description: project.status,
      detail: [project.id, ...(project.named_parts ?? [])].join(" · "),
      project,
    })),
    { placeHolder: "Select an AIENG Workbench project to preview" },
  );
  return selected?.project;
}

export async function loadLivePreview(project: Project): Promise<PreviewPayload> {
  const [asset, brep] = await Promise.all([
    fetchBytes(`/api/projects/${encodeURIComponent(project.id)}/cad-preview`),
    fetchJson(`/api/projects/${encodeURIComponent(project.id)}/brep-graph`).catch(() => null),
  ]);
  const faces = facesFromBackendBrep(brep);
  return {
    kind: "preview",
    title: project.name || project.id,
    source: "live",
    projectId: project.id,
    format: asset.format,
    assetBase64: asset.bytes.toString("base64"),
    faces,
    facePicking: asset.format === "glb" && Object.keys(faces).length > 0 ? "reliable" : "unavailable",
    detail: Object.keys(faces).length
      ? `Live project · ${Object.keys(faces).length} topology faces`
      : "Live project · preview only, no authoritative topology map",
    updatedAt: project.updated_at ?? new Date().toISOString(),
  };
}

export function watchLiveProject(projectId: string, refresh: () => void): vscode.Disposable {
  const source = new EventSource(`${backendUrl()}/api/agent-activity/stream`);
  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as { type?: string; project_id?: string };
      if (
        event.project_id === projectId &&
        (event.type === "viewer_asset_changed" || event.type === "project_changed")
      ) {
        refresh();
      }
    } catch {
      // Ignore malformed/heartbeat events.
    }
  };
  return new vscode.Disposable(() => source.close());
}
