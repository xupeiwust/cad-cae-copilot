import JSZip from "jszip";
import * as vscode from "vscode";

import type { FaceEntity, PreviewFormat, PreviewPayload } from "./protocol";

const PREVIEW_CANDIDATES: Array<[string, PreviewFormat]> = [
  ["geometry/preview.glb", "glb"],
  ["preview.glb", "glb"],
  ["viewer/model.glb", "glb"],
  ["geometry/preview.stl", "stl"],
  ["preview.stl", "stl"],
  ["viewer/model.stl", "stl"],
];

type JsonObject = Record<string, unknown>;

function asTuple3(value: unknown): [number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 3 || value.some((item) => typeof item !== "number")) return undefined;
  return value as [number, number, number];
}

function asTuple6(value: unknown): [number, number, number, number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 6 || value.some((item) => typeof item !== "number")) return undefined;
  return value as [number, number, number, number, number, number];
}

function normalizeFace(raw: JsonObject): FaceEntity | null {
  const id = String(raw.id ?? raw.entity_id ?? "");
  if (!id) return null;
  const pointer = String(raw.pointer ?? `@face:${id}`);
  const roles = Array.isArray(raw.roles) ? raw.roles.map(String) : [];
  const label = String(raw.label ?? raw.name ?? pointer);
  return {
    id,
    pointer,
    label,
    roles,
    surfaceType: String(raw.surface_type ?? raw.surfaceType ?? "unknown"),
    bodyId: raw.body_id ? String(raw.body_id) : undefined,
    center: asTuple3(raw.center),
    boundingBox: asTuple6(raw.bounding_box),
  };
}

function facesFromTopology(raw: unknown): Record<string, FaceEntity> {
  if (!raw || typeof raw !== "object") return {};
  const topology = raw as JsonObject;
  const entities = Array.isArray(topology.entities) ? topology.entities : [];
  const result: Record<string, FaceEntity> = {};
  for (const entity of entities) {
    if (!entity || typeof entity !== "object" || String((entity as JsonObject).type ?? "") !== "face") continue;
    const face = normalizeFace(entity as JsonObject);
    if (face) result[face.id] = face;
  }
  return result;
}

function facesFromBrepGraph(raw: unknown): Record<string, FaceEntity> {
  if (!raw || typeof raw !== "object") return {};
  const root = raw as JsonObject;
  const graph = root.brep_graph && typeof root.brep_graph === "object" ? root.brep_graph as JsonObject : root;
  const entities = graph.entities && typeof graph.entities === "object" ? graph.entities as JsonObject : null;
  const rawFaces = graph.faces ?? entities?.faces;
  const values = Array.isArray(rawFaces)
    ? rawFaces
    : rawFaces && typeof rawFaces === "object"
      ? Object.values(rawFaces as JsonObject)
      : [];
  const result: Record<string, FaceEntity> = {};
  for (const value of values) {
    if (!value || typeof value !== "object") continue;
    const face = normalizeFace(value as JsonObject);
    if (face) result[face.id] = face;
  }
  return result;
}

async function readJson(zip: JSZip, member: string): Promise<unknown | null> {
  const file = zip.file(member);
  if (!file) return null;
  try {
    return JSON.parse(await file.async("string")) as unknown;
  } catch {
    return null;
  }
}

export async function readAiengPackage(uri: vscode.Uri): Promise<PreviewPayload> {
  const bytes = await vscode.workspace.fs.readFile(uri);
  const zip = await JSZip.loadAsync(bytes);
  const selected = PREVIEW_CANDIDATES.find(([member]) => Boolean(zip.file(member)));
  const brepRaw = await readJson(zip, "graph/brep_graph.json");
  const topologyRaw = await readJson(zip, "geometry/topology_map.json");
  const brepFaces = facesFromBrepGraph(brepRaw);
  const faces = Object.keys(brepFaces).length ? brepFaces : facesFromTopology(topologyRaw);

  if (!selected) {
    return {
      kind: "preview",
      title: uri.path.split("/").pop() ?? "AIENG package",
      source: "package",
      faces,
      facePicking: "unavailable",
      detail: "No embedded GLB/STL preview. Open Live CAD Preview to use backend-assisted conversion.",
      updatedAt: new Date().toISOString(),
    };
  }

  const [member, format] = selected;
  const asset = await zip.file(member)!.async("nodebuffer");
  return {
    kind: "preview",
    title: uri.path.split("/").pop() ?? "AIENG package",
    source: "package",
    format,
    assetBase64: asset.toString("base64"),
    faces,
    facePicking: format === "glb" && Object.keys(faces).length > 0 ? "reliable" : "unavailable",
    detail: Object.keys(faces).length
      ? `${member} · ${Object.keys(faces).length} topology faces`
      : `${member} · preview only, no authoritative topology map`,
    updatedAt: new Date().toISOString(),
  };
}

export function facesFromBackendBrep(raw: unknown): Record<string, FaceEntity> {
  return facesFromBrepGraph(raw);
}
