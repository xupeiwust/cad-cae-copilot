export type PreviewFormat = "glb" | "stl";

export type FaceEntity = {
  id: string;
  pointer: string;
  label: string;
  surfaceType: string;
  roles: string[];
  bodyId?: string;
  center?: [number, number, number];
  boundingBox?: [number, number, number, number, number, number];
};

export type PreviewPayload = {
  kind: "preview";
  title: string;
  source: "package" | "live";
  format?: PreviewFormat;
  assetBase64?: string;
  faces: Record<string, FaceEntity>;
  facePicking: "reliable" | "unavailable";
  detail: string;
  projectId?: string;
  updatedAt?: string;
};

export type HostToWebviewMessage = PreviewPayload | {
  kind: "status";
  tone: "info" | "error";
  detail: string;
};

export type WebviewToHostMessage =
  | { kind: "ready" }
  | { kind: "copy"; text: string }
  | { kind: "refresh" };
